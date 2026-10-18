"""Bounded recurring factual-data and research operations worker.

The worker is deliberately separate from FastAPI request handling. It reuses
the provider, Sheets, trigger, research-queue, ranking and Execution Pace
services already owned by the domain modules. It never accepts proposals or
issues portfolio transactions.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.agent_work_sheet_sync import publish_agent_work_feed
from portfolio_api.database import create_database_engine
from portfolio_api.domain import queries
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Actor,
    ExecutionPaceDecision,
    ExecutionPaceRun,
    ExternalIngestionAttempt,
    ExternalIngestionRun,
    OperationalJobAttempt,
    OperationalJobRequest,
    PriceObservation,
    RankingDefinition,
    RankingEntry,
    RankingRun,
    RankingType,
    RecurringOperationRun,
    RecurringOperationsWorkerState,
)
from portfolio_api.domain.services import create_ranking_run
from portfolio_api.execution_pace import create_execution_pace_run
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import PROVIDERS, run_scheduled
from portfolio_api.google_sheets_sync import run_sync_check
from portfolio_api.health import check_readiness
from portfolio_api.manual_operations import JOB_DOMAINS
from portfolio_api.market_data_ingestion import DEFAULT_LOOKBACK_DAYS, active_market_listings
from portfolio_api.market_data_startup import (
    ADVISORY_LOCK_KEY as MARKET_DATA_LOCK_KEY,
)
from portfolio_api.market_data_startup import (
    ADVISORY_LOCK_NAMESPACE as MARKET_DATA_LOCK_NAMESPACE,
)
from portfolio_api.market_data_startup import (
    configure_yahoo_no_proxy,
)
from portfolio_api.migrations import expected_heads
from portfolio_api.networking import bypass_known_local_port_nine_proxy
from portfolio_api.portfolio_sheet_sync import PortfolioSheetPublishError
from portfolio_api.research_agent_operations import (
    ResearchAgentOperationError,
    deliver_agent_work,
    record_delivery_failure,
    record_sheet_agent_work_deliveries,
    run_acknowledgment_inbox_check,
)
from portfolio_api.research_queue import get_research_queue
from portfolio_api.research_sheet_sync import run_research_sync_check
from portfolio_api.research_triggers import refresh_research_triggers
from portfolio_api.risk_assessments import run_risk_sync_check
from portfolio_api.settings import Settings

logger = logging.getLogger(__name__)

LOCK_NAMESPACE = 1_347_906_132
LOCK_KEY = 1_397_962_052
TICK_SECONDS = 60
WORKER_STALE_AFTER = timedelta(minutes=5)
JOB_STALE_AFTER = timedelta(hours=2)
FAILURE_BACKOFF_INITIAL = timedelta(minutes=15)
FAILURE_BACKOFF_MAX = timedelta(hours=6)
BLOCKED_BACKOFF = timedelta(hours=6)
SEC_RETRY_LIMIT_PER_UTC_DAY = 2
SEC_GOOGLE_API_HOSTS = (
    "www.sec.gov",
    "data.sec.gov",
    "googleapis.com",
    ".googleapis.com",
    "oauth2.googleapis.com",
)

SEC_FUNDAMENTALS = "SEC_FUNDAMENTALS"
SEC_FILINGS = "SEC_FILINGS"
FMP_CONSENSUS = "FMP_CONSENSUS"
SHEETS_DISCOVERY = "SHEETS_DISCOVERY"
RESEARCH_TRIGGER_SCAN = "RESEARCH_TRIGGER_SCAN"
AGENT_WORK_FEED = "AGENT_WORK_FEED"
DECISION_RECOMPUTE = "DECISION_RECOMPUTE"

AGENT_ROLES = (
    "DATA_UNIVERSE_STEWARD",
    "PORTFOLIO_THESIS_SENTINEL",
    "MODEL_ALLOCATION_STEWARD",
)
RANKING_TYPES = (RankingType.PORTFOLIO, RankingType.WATCHLIST, RankingType.RESEARCH)

JOB_CADENCES_SECONDS = {
    SEC_FUNDAMENTALS: 24 * 60 * 60,
    SEC_FILINGS: 24 * 60 * 60,
    FMP_CONSENSUS: 24 * 60 * 60,
    SHEETS_DISCOVERY: 60 * 60,
    RESEARCH_TRIGGER_SCAN: 60 * 60,
    AGENT_WORK_FEED: 60 * 60,
    DECISION_RECOMPUTE: 60 * 60,
}


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Recurring-operation timestamps must include a timezone offset")
    return current.astimezone(UTC)


def configure_external_operations_no_proxy(
    environment: MutableMapping[str, str] | None = None,
) -> bool:
    """Bypass the known dead local proxy for SEC/Google APIs in this worker only."""

    return bypass_known_local_port_nine_proxy(SEC_GOOGLE_API_HOSTS, environment)


def _json_fingerprint(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def wait_for_database(engine: Engine, timeout_seconds: int = 180) -> bool:
    deadline = time.monotonic() + timeout_seconds
    heads = expected_heads()
    while time.monotonic() < deadline:
        if check_readiness(engine, heads).status == "ok":
            return True
        time.sleep(3)
    return False


def _latest_operation(session: Session, job_name: str) -> RecurringOperationRun | None:
    return session.scalar(
        select(RecurringOperationRun)
        .where(RecurringOperationRun.job_name == job_name)
        .order_by(RecurringOperationRun.started_at.desc(), RecurringOperationRun.id.desc())
        .limit(1)
    )


def _recover_abandoned_job(
    session: Session, latest: RecurringOperationRun, now_at: datetime
) -> bool:
    if latest.status != "RUNNING":
        return False
    if now_at - latest.started_at <= JOB_STALE_AFTER:
        return True
    latest.status = "FAILED"
    latest.finished_at = now_at
    latest.next_attempt_at = now_at + FAILURE_BACKOFF_INITIAL
    latest.failure_code = "WORKER_INTERRUPTED"
    latest.failure_message = "The recurring worker stopped before this operation completed."
    session.commit()
    return False


def _configuration_recovered(
    job_name: str, latest: RecurringOperationRun, settings: Settings
) -> bool:
    if job_name in {SEC_FUNDAMENTALS, SEC_FILINGS}:
        return latest.failure_code == "SEC_USER_AGENT_MISSING" and bool(settings.sec_user_agent)
    if job_name == SHEETS_DISCOVERY:
        return (
            latest.failure_code == "GOOGLE_SHEETS_NOT_CONFIGURED"
            and bool(settings.google_sheets_spreadsheet_id)
            and bool(settings.google_sheets_service_account_file)
        )
    if job_name == FMP_CONSENSUS:
        return (
            latest.failure_code in {"FMP_DISABLED_BY_POLICY", "FMP_CREDENTIAL_MISSING"}
            and settings.fmp_consensus_ingestion_enabled
            and settings.fmp_api_key is not None
        )
    return False


def operation_due(
    session: Session,
    job_name: str,
    now_at: datetime,
    cadence_seconds: int,
    settings: Settings,
) -> bool:
    """Return whether a job is due, recovering a stale RUNNING marker safely."""

    if cadence_seconds <= 0:
        return False
    latest = _latest_operation(session, job_name)
    if latest is None:
        return True
    if _recover_abandoned_job(session, latest, now_at):
        return False
    if _configuration_recovered(job_name, latest, settings):
        return True
    return latest.next_attempt_at is None or latest.next_attempt_at <= now_at


def _failure_streak(session: Session, job_name: str) -> int:
    streak = 0
    rows = session.scalars(
        select(RecurringOperationRun)
        .where(RecurringOperationRun.job_name == job_name)
        .order_by(RecurringOperationRun.started_at.desc())
        .limit(10)
    )
    for row in rows:
        if row.status not in {"FAILED", "BLOCKED"}:
            break
        streak += 1
    return streak


def _next_attempt(
    session: Session,
    job_name: str,
    status: str,
    finished_at: datetime,
    cadence_seconds: int,
) -> datetime:
    if status in {"FAILED", "BLOCKED"}:
        streak = _failure_streak(session, job_name)
        if status == "BLOCKED":
            return finished_at + BLOCKED_BACKOFF
        seconds = min(
            FAILURE_BACKOFF_INITIAL.total_seconds() * (2 ** max(0, streak - 1)),
            FAILURE_BACKOFF_MAX.total_seconds(),
        )
        return finished_at + timedelta(seconds=seconds)
    return finished_at + timedelta(seconds=cadence_seconds)


def _begin_operation(engine: Engine, job_name: str, started_at: datetime) -> UUID:
    run = RecurringOperationRun(job_name=job_name, status="RUNNING", started_at=started_at)
    with Session(engine) as session:
        session.add(run)
        session.commit()
        return run.id


def _finish_operation(
    engine: Engine,
    run_id: UUID,
    *,
    result: dict[str, object],
    status: str,
    cadence_seconds: int,
    finished_at: datetime,
    retry_after_seconds: int | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> None:
    with Session(engine) as session:
        run = session.get(RecurringOperationRun, run_id)
        if run is None:
            return
        run.status = status
        run.finished_at = finished_at
        run.failure_code = failure_code
        run.failure_message = failure_message[:2000] if failure_message else None
        run.result = result
        run.next_attempt_at = (
            finished_at + timedelta(seconds=max(1, retry_after_seconds))
            if retry_after_seconds is not None
            else _next_attempt(session, run.job_name, status, finished_at, cadence_seconds)
        )
        session.commit()


def _classified_status(result: dict[str, object]) -> str:
    status = str(result.get("status", "SUCCEEDED")).upper()
    if status in {"FAILED", "PARTIAL", "BLOCKED", "SKIPPED"}:
        return status
    return "SUCCEEDED"


def _run_one_job(
    engine: Engine,
    settings: Settings,
    job_name: str,
    cadence_seconds: int,
    now_at: datetime,
    action: Callable[[], dict[str, object]],
) -> dict[str, object]:
    with Session(engine) as session:
        if not operation_due(session, job_name, now_at, cadence_seconds, settings):
            return {"status": "NOT_DUE", "job_name": job_name}
    run_id = _begin_operation(engine, job_name, now_at)
    try:
        result = action()
        status = _classified_status(result)
        failure_code = str(result.get("failure_code")) if result.get("failure_code") else None
        failure_message = (
            str(result.get("failure_message")) if result.get("failure_message") else None
        )
        retry_after_seconds = result.get("retry_after_seconds")
        if status == "BLOCKED" and failure_code is None:
            failure_code = str(result.get("reason_code", "PREREQUISITE_BLOCKED"))
        if status == "FAILED" and failure_code is None:
            failure_code = "OPERATION_FAILED"
    except Exception as error:  # keep one failed integration from stopping other jobs
        logger.exception("Recurring job %s failed", job_name)
        result = {"status": "FAILED", "failure_code": type(error).__name__}
        status = "FAILED"
        failure_code = type(error).__name__
        failure_message = str(error)
    _finish_operation(
        engine,
        run_id,
        result=result,
        status=status,
        cadence_seconds=cadence_seconds,
        finished_at=_utc(),
        retry_after_seconds=(
            int(retry_after_seconds) if isinstance(retry_after_seconds, int) else None
        ),
        failure_code=failure_code,
        failure_message=failure_message,
    )
    return {"job_name": job_name, "run_id": str(run_id), **result, "operation_status": status}


def _run_sec_domain(
    engine: Engine, settings: Settings, domain: ExternalDataDomain, now_at: datetime
) -> dict[str, object]:
    if not settings.sec_user_agent:
        return {
            "status": "BLOCKED",
            "failure_code": "SEC_USER_AGENT_MISSING",
            "failure_message": (
                "Configure SEC_USER_AGENT with the application name and contact email."
            ),
        }
    with Session(engine) as session:
        latest = session.scalar(
            select(ExternalIngestionRun)
            .where(
                ExternalIngestionRun.provider_id == PROVIDERS[domain],
                ExternalIngestionRun.domain == domain.value,
            )
            .order_by(ExternalIngestionRun.created_at.desc())
            .limit(1)
        )
        replay_of = None
        replay_scope: dict[str, Any] | None = None
        replay_count = 0
        if latest is not None and latest.created_at.date() == now_at.date():
            last_attempt = session.scalar(
                select(ExternalIngestionAttempt)
                .where(ExternalIngestionAttempt.run_id == latest.id)
                .order_by(ExternalIngestionAttempt.attempt_number.desc())
                .limit(1)
            )
            if (
                latest.status in {"COMPLETE", "PARTIAL"}
                and last_attempt is not None
                and not last_attempt.retryable
            ):
                return {
                    "status": latest.status,
                    "report": latest.report,
                    "external_run_id": str(latest.id),
                    "idempotent_reuse": True,
                }
            replay_count = (
                session.scalar(
                    select(func.count(ExternalIngestionRun.id)).where(
                        ExternalIngestionRun.replay_of_run_id.is_not(None),
                        ExternalIngestionRun.domain == domain.value,
                        ExternalIngestionRun.created_at
                        >= datetime.combine(now_at.date(), datetime.min.time(), UTC),
                    )
                )
                or 0
            )
            if (
                latest.status in {"FAILED", "PARTIAL"}
                and last_attempt is not None
                and last_attempt.retryable
                and replay_count < SEC_RETRY_LIMIT_PER_UTC_DAY
            ):
                replay_of = latest.id
                replay_scope = latest.request_scope
        report = run_scheduled(
            session,
            settings,
            domains=[domain],
            run_date=now_at.date(),
            replay_of_run_id=replay_of,
            replay_scope=replay_scope,
        )
        session.commit()
        result: dict[str, object] = {"status": report["status"], "report": report}
        if str(report.get("status", "")).upper() in {"FAILED", "PARTIAL"}:
            latest_after_run = session.scalar(
                select(ExternalIngestionRun)
                .where(
                    ExternalIngestionRun.provider_id == PROVIDERS[domain],
                    ExternalIngestionRun.domain == domain.value,
                )
                .order_by(ExternalIngestionRun.created_at.desc())
                .limit(1)
            )
            if latest_after_run is not None:
                last_attempt_after_run = session.scalar(
                    select(ExternalIngestionAttempt)
                    .where(ExternalIngestionAttempt.run_id == latest_after_run.id)
                    .order_by(ExternalIngestionAttempt.attempt_number.desc())
                    .limit(1)
                )
                if (
                    last_attempt_after_run is not None
                    and last_attempt_after_run.retryable
                    and replay_count < SEC_RETRY_LIMIT_PER_UTC_DAY
                ):
                    result["retry_after_seconds"] = int(FAILURE_BACKOFF_INITIAL.total_seconds())
        return result


def _run_sheets_discovery(
    engine: Engine, settings: Settings, *, manual: bool = False
) -> dict[str, object]:
    if settings.google_sheets_poll_seconds == 0 and not manual:
        return {"status": "SKIPPED", "reason": "Google Sheets polling is disabled."}
    if not settings.google_sheets_spreadsheet_id:
        return {
            "status": "BLOCKED",
            "failure_code": "GOOGLE_SHEETS_NOT_CONFIGURED",
            "failure_message": "Set GOOGLE_SHEETS_SPREADSHEET_ID to enable inbox discovery.",
        }
    with Session(engine) as session:
        model = run_sync_check(session, settings)
        research = run_research_sync_check(session, settings)
        risk = run_risk_sync_check(session, settings)
        acknowledgment = run_acknowledgment_inbox_check(session, settings)
        session.commit()
        checks = {
            "model": model.run.status,
            "research": research.run.status,
            "risk": risk.run.status,
            "acknowledgments": acknowledgment.status,
        }
        statuses = {status.upper() for status in checks.values()}
        overall = (
            "FAILED"
            if "FAILED" in statuses and not statuses.intersection({"SUCCEEDED", "CONNECTED"})
            else "PARTIAL"
            if statuses.intersection({"FAILED", "PARTIAL", "BLOCKED"})
            else "SUCCEEDED"
        )
        return {
            "status": overall,
            "checks": checks,
            "model_candidates": model.run.new_count,
            "research_candidates": research.run.new_count,
            "risk_candidates": risk.run.new_count,
            "acknowledgments_captured": acknowledgment.captured,
            "acknowledgments_replayed": acknowledgment.replayed,
            "acknowledgment_issues": len(acknowledgment.issues),
        }


def _run_trigger_scan(
    engine: Engine, now_at: datetime, *, company_id: UUID | None = None
) -> dict[str, object]:
    with Session(engine) as session:
        refresh = refresh_research_triggers(
            session, as_of=now_at, lookback_days=30, company_id=company_id
        )
        queue = get_research_queue(session, as_of=now_at)
        session.commit()
        return {
            "status": "SUCCEEDED",
            "examined": refresh.examined,
            "created": refresh.created,
            "replayed": refresh.replayed,
            "open_queue_items": queue.counts.open,
            "portfolio_queue_items": queue.counts.portfolio,
            "watchlist_queue_items": queue.counts.watchlist,
            "candidate_queue_items": queue.counts.candidate,
        }


def _publish_agent_feeds(engine: Engine, settings: Settings, now_at: datetime) -> dict[str, object]:
    if not settings.google_sheets_spreadsheet_id or not settings.google_sheets_service_account_file:
        return {
            "status": "BLOCKED",
            "failure_code": "GOOGLE_SHEETS_NOT_CONFIGURED",
            "failure_message": (
                "A workbook ID and service-account file are required for feed publication."
            ),
        }
    outcomes: dict[str, object] = {}
    for role in AGENT_ROLES:
        with Session(engine) as session:
            work: s.ResearchAgentWorkContractV1 | None = None
            try:
                work = deliver_agent_work(
                    session,
                    role,
                    s.ResearchAgentWorkRequest(as_of=now_at, limit=10, offset=0),
                    channel="GOOGLE_SHEETS",
                )
                published = publish_agent_work_feed(session, work, settings)
                if published.read_back_verified:
                    record_sheet_agent_work_deliveries(session, work, published.published_at)
                session.commit()
                outcomes[role] = {
                    "status": published.status,
                    "work_items": published.work_item_count,
                    "added_rows": published.added_count,
                    "read_back_verified": published.read_back_verified,
                    "reason": published.status_reason,
                }
            except (PortfolioSheetPublishError, ResearchAgentOperationError) as error:
                session.rollback()
                if work is not None:
                    for item in work.items:
                        record_delivery_failure(
                            session,
                            role=role,
                            work_type=item.work_type,
                            work_key=item.work_key,
                            fingerprint=item.work_fingerprint,
                            attempt_id=str(uuid4()),
                            channel="GOOGLE_SHEETS",
                            reason=str(error),
                            observed_at=now_at,
                        )
                    session.commit()
                outcomes[role] = {"status": "FAILED", "reason": str(error)}
            except Exception as error:
                session.rollback()
                outcomes[role] = {"status": "FAILED", "reason": type(error).__name__}
    statuses = {
        str(value.get("status", "FAILED")).upper()
        for value in outcomes.values()
        if isinstance(value, dict)
    }
    overall = (
        "FAILED"
        if statuses == {"FAILED"}
        else "PARTIAL"
        if statuses.intersection({"FAILED", "BLOCKED"})
        else "SUCCEEDED"
    )
    return {"status": overall, "roles": outcomes}


def _manual_job_steps(request: OperationalJobRequest) -> list[tuple[str, list[str]]]:
    job_name = request.job_name
    if job_name == "REFRESH_ALL":
        return [
            ("MARKET_AND_FX", ["MARKET_DATA", "CORPORATE_ACTIONS", "FX"]),
            ("SEC_FUNDAMENTALS", ["REPORTED_FUNDAMENTALS"]),
            ("SEC_FILINGS", ["SOURCE_DOCUMENTS"]),
            ("SHEETS_DISCOVERY", ["MODEL_SYNC", "RESEARCH_SYNC", "RISK_SYNC", "ACKNOWLEDGMENTS"]),
            ("RESEARCH_REFRESH", ["RESEARCH_TRIGGERS", "RESEARCH_QUEUE"]),
            ("AGENT_WORK_FEED", ["AGENT_WORK_FEED"]),
        ]
    if job_name == "COMPANY_REFRESH":
        return [
            ("MARKET_AND_FX", ["MARKET_DATA", "CORPORATE_ACTIONS", "FX"]),
            ("SEC_FUNDAMENTALS", ["REPORTED_FUNDAMENTALS"]),
            ("SEC_FILINGS", ["SOURCE_DOCUMENTS"]),
            ("RESEARCH_REFRESH", ["RESEARCH_TRIGGERS", "RESEARCH_QUEUE"]),
        ]
    if job_name == "MARKET_AND_FX":
        return [("MARKET_AND_FX", JOB_DOMAINS[job_name])]
    if job_name in {
        "MARKET_DATA",
        "FX",
        "SEC_FUNDAMENTALS",
        "SEC_FILINGS",
        "SHEETS_DISCOVERY",
        "RESEARCH_REFRESH",
        "AGENT_WORK_FEED",
    }:
        return [(job_name, JOB_DOMAINS[job_name])]
    return []


def _manual_result_status(result: dict[str, object]) -> str:
    value = str(result.get("status", "FAILED")).upper()
    if value in {"SUCCEEDED", "COMPLETE", "CONNECTED"}:
        return "SUCCEEDED"
    if value == "DEFERRED":
        return "DEFERRED"
    if value in {"PARTIAL", "PARTIAL_COVERAGE", "RUNNING", "RETRYING"}:
        return "PARTIAL"
    if value in {"BLOCKED", "SKIPPED", "NOT_APPLICABLE"}:
        return "BLOCKED"
    return "FAILED"


def _run_manual_market_step(
    engine: Engine,
    settings: Settings,
    request: OperationalJobRequest,
    now_at: datetime,
    *,
    include_market: bool,
    include_fx: bool,
) -> dict[str, object]:
    from portfolio_api.external_data import ExternalDataDomain

    domains = []
    if include_market:
        domains.append(ExternalDataDomain.MARKET_DATA)
    if include_fx:
        domains.append(ExternalDataDomain.FX)
    company_ids = {request.company_id} if request.company_id else None
    with Session(engine) as session:
        selected, _held = active_market_listings(session, company_ids)
        initial_backfill_needed = any(
            (
                session.scalar(
                    select(func.count(func.distinct(PriceObservation.market_date))).where(
                        PriceObservation.listing_id == listing.id,
                        PriceObservation.provider == "YAHOO_FINANCE",
                        PriceObservation.price_kind == "DAILY_CLOSE",
                        PriceObservation.data_quality.in_(("PASS", "PASS_VERIFIED_FALLBACK")),
                        PriceObservation.split_adjusted_close.is_not(None),
                    )
                )
                or 0
            )
            < 252
            for listing, _security, _company in selected
        )
    lookback_days = DEFAULT_LOOKBACK_DAYS if include_market and initial_backfill_needed else 90
    with engine.connect() as connection:
        acquired: bool = connection.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
            {"namespace": MARKET_DATA_LOCK_NAMESPACE, "lock_key": MARKET_DATA_LOCK_KEY},
        ).scalar_one()
        connection.commit()
        if not acquired:
            return {
                "status": "DEFERRED",
                "reason": "The scheduled market refresh currently holds the provider lock.",
                "retry_after_seconds": 60,
            }
        try:
            configure_yahoo_no_proxy()
            with Session(bind=connection) as session:
                report = run_scheduled(
                    session,
                    settings,
                    domains=domains,
                    lookback_days=lookback_days,
                    company_ids=company_ids,
                    request_nonce=request.id,
                    run_date=now_at.date(),
                )
                session.commit()
            return {"status": report.get("status", "FAILED"), "report": report}
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                {"namespace": MARKET_DATA_LOCK_NAMESPACE, "lock_key": MARKET_DATA_LOCK_KEY},
            )


def _run_manual_step(
    engine: Engine,
    settings: Settings,
    request: OperationalJobRequest,
    step_name: str,
    now_at: datetime,
) -> dict[str, object]:
    if step_name == "MARKET_DATA":
        return _run_manual_market_step(
            engine, settings, request, now_at, include_market=True, include_fx=False
        )
    if step_name == "FX":
        return _run_manual_market_step(
            engine, settings, request, now_at, include_market=False, include_fx=True
        )
    if step_name == "MARKET_AND_FX":
        return _run_manual_market_step(
            engine, settings, request, now_at, include_market=True, include_fx=True
        )
    if step_name in {"SEC_FUNDAMENTALS", "SEC_FILINGS"}:
        if not settings.sec_user_agent:
            return {
                "status": "BLOCKED",
                "failure_code": "SEC_USER_AGENT_MISSING",
                "failure_message": (
                    "Configure SEC_USER_AGENT with application name and monitored contact."
                ),
            }
        domain = (
            ExternalDataDomain.REPORTED_FUNDAMENTALS
            if step_name == "SEC_FUNDAMENTALS"
            else ExternalDataDomain.SOURCE_DOCUMENTS
        )
        with Session(engine) as session:
            report = run_scheduled(
                session,
                settings,
                domains=[domain],
                company_ids={request.company_id} if request.company_id else None,
                request_nonce=request.id,
                run_date=now_at.date(),
            )
            session.commit()
        return {"status": report.get("status", "FAILED"), "report": report}
    if step_name == "SHEETS_DISCOVERY":
        return _run_sheets_discovery(engine, settings, manual=True)
    if step_name == "RESEARCH_REFRESH":
        return _run_trigger_scan(engine, now_at, company_id=request.company_id)
    if step_name == "AGENT_WORK_FEED":
        return _publish_agent_feeds(engine, settings, now_at)
    return {
        "status": "BLOCKED",
        "failure_code": "UNSUPPORTED_MANUAL_OPERATION",
        "failure_message": "No existing service is registered for this operation.",
    }


def process_manual_job_requests(
    engine: Engine,
    settings: Settings,
    *,
    now_at: datetime | None = None,
) -> dict[str, object]:
    """Claim and execute at most one durable manual request using existing services."""

    current = _utc(now_at)
    request_id: UUID | None = None
    with Session(engine) as session:
        request = session.scalar(
            select(OperationalJobRequest)
            .where(
                (
                    (OperationalJobRequest.status == "QUEUED")
                    & (
                        OperationalJobRequest.next_attempt_at.is_(None)
                        | (OperationalJobRequest.next_attempt_at <= current)
                    )
                )
                | (
                    (OperationalJobRequest.status == "RUNNING")
                    & (OperationalJobRequest.started_at <= current - JOB_STALE_AFTER)
                )
            )
            .order_by(OperationalJobRequest.requested_at, OperationalJobRequest.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if request is None:
            return {"status": "IDLE", "processed": 0}
        if request.status == "RUNNING":
            stale_attempts = list(
                session.scalars(
                    select(OperationalJobAttempt).where(
                        OperationalJobAttempt.request_id == request.id,
                        OperationalJobAttempt.status == "RUNNING",
                        OperationalJobAttempt.finished_at.is_(None),
                    )
                )
            )
            for attempt in stale_attempts:
                attempt.status = "FAILED"
                attempt.finished_at = current
                attempt.error_code = "WORKER_INTERRUPTED"
                attempt.error_message = "Worker stopped before this step recorded an outcome."
        request.status = "RUNNING"
        request.started_at = request.started_at or current
        request.finished_at = None
        request.next_attempt_at = None
        request.attempt_count += 1
        request_id = request.id
        session.commit()

    if request_id is None:
        return {"status": "IDLE", "processed": 0}
    step_results: list[dict[str, object]] = []
    with Session(engine) as session:
        request = session.get(OperationalJobRequest, request_id)
        if request is None:
            return {"status": "FAILED", "reason": "Request disappeared after claim."}
        steps = _manual_job_steps(request)
        attempt_number = request.attempt_count
        job_snapshot = request
        for step_name, affected_domains in steps:
            started_at = datetime.now(UTC)
            attempt = OperationalJobAttempt(
                request_id=request.id,
                attempt_number=attempt_number,
                step_name=step_name,
                status="RUNNING",
                affected_domains=affected_domains,
                started_at=started_at,
                result={},
            )
            session.add(attempt)
            session.commit()
            try:
                result = _run_manual_step(engine, settings, job_snapshot, step_name, current)
            except Exception as error:
                logger.exception("Manual operation step failed: %s", step_name)
                result = {
                    "status": "FAILED",
                    "failure_code": type(error).__name__,
                    "failure_message": str(error)[:2000],
                }
            status = _manual_result_status(result)
            finished_at = datetime.now(UTC)
            attempt.status = status
            attempt.finished_at = finished_at
            attempt.result = cast(dict[str, object], json.loads(json.dumps(result, default=str)))
            failure_code = result.get("failure_code")
            failure_message = result.get("failure_message") or result.get("reason")
            attempt.error_code = failure_code if isinstance(failure_code, str) else None
            attempt.error_message = failure_message if isinstance(failure_message, str) else None
            step_results.append(
                {
                    "step_name": step_name,
                    "status": status,
                    "affected_domains": affected_domains,
                    "attempt_id": str(attempt.id),
                    "result": attempt.result,
                }
            )
            request.result = {"steps": step_results}
            if status == "DEFERRED":
                request.status = "QUEUED"
                retry_after = result.get("retry_after_seconds", 60)
                seconds = retry_after if isinstance(retry_after, int) else 60
                request.next_attempt_at = current + timedelta(seconds=seconds)
                request.error_code = "DEPENDENCY_BUSY"
                request.error_message = str(result.get("reason", "A dependency is busy."))
                session.commit()
                return {
                    "status": "DEFERRED",
                    "request_id": str(request.id),
                    "next_attempt_at": request.next_attempt_at.isoformat(),
                }
            session.commit()
        statuses = {str(item["status"]) for item in step_results}
        if statuses and statuses <= {"SUCCEEDED"}:
            request.status = "SUCCEEDED"
        elif "SUCCEEDED" not in statuses and statuses <= {"BLOCKED"}:
            request.status = "BLOCKED"
        elif "SUCCEEDED" not in statuses and statuses <= {"FAILED"}:
            request.status = "FAILED"
        else:
            request.status = "PARTIAL"
        request.finished_at = datetime.now(UTC)
        errors: list[tuple[str | None, str | None]] = []
        for item in step_results:
            step_result = item.get("result")
            if isinstance(step_result, dict):
                code = step_result.get("failure_code")
                message = step_result.get("failure_message") or step_result.get("reason")
                if code or message:
                    errors.append(
                        (
                            code if isinstance(code, str) else None,
                            message if isinstance(message, str) else None,
                        )
                    )
        first_error = errors[0] if errors else (None, None)
        request.error_code, request.error_message = first_error
        request.result = {"steps": step_results, "status": request.status}
        session.commit()
        return {"status": request.status, "request_id": str(request.id), "steps": step_results}


def _ranking_signature(session: Session, run_id: UUID) -> str:
    rows = list(
        session.scalars(
            select(RankingEntry)
            .where(RankingEntry.run_id == run_id)
            .order_by(RankingEntry.company_id)
        )
    )
    return _json_fingerprint(
        [
            {
                "company_id": row.company_id,
                "status": row.status,
                "reason": row.reason,
                "position": row.position,
                "input_snapshot": row.input_snapshot,
            }
            for row in rows
        ]
    )


def _latest_ranking_run(session: Session, ranking_type: RankingType) -> RankingRun | None:
    return session.scalar(
        select(RankingRun)
        .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
        .where(RankingDefinition.ranking_type == ranking_type.value)
        .order_by(RankingRun.as_of.desc(), RankingRun.recorded_at.desc(), RankingRun.id.desc())
        .limit(1)
    )


def _recompute_ranking(session: Session, ranking_type: RankingType) -> dict[str, object]:
    previous = _latest_ranking_run(session, ranking_type)
    previous_signature = _ranking_signature(session, previous.id) if previous else None
    savepoint = session.begin_nested()
    try:
        run = create_ranking_run(
            session,
            s.RankingRunCreate(
                ranking_type=ranking_type,
                actor=Actor.SYSTEM,
                reason="Canonical inputs changed; deterministic scheduled recomputation.",
                source="recurring-operations",
            ),
        )
        signature = _ranking_signature(session, run.id)
        ranked_count = (
            session.scalar(
                select(func.count(RankingEntry.id)).where(
                    RankingEntry.run_id == run.id, RankingEntry.status == "RANKED"
                )
            )
            or 0
        )
        if signature == previous_signature:
            savepoint.rollback()
            return {"status": "SKIPPED", "reason": "Inputs and outcomes match the latest run."}
        if previous is None and ranked_count == 0:
            savepoint.rollback()
            return {"status": "BLOCKED", "reason": "No ranked entries are currently eligible."}
        savepoint.commit()
        return {"status": "SUCCEEDED", "run_id": str(run.id), "ranked_count": ranked_count}
    except Exception as error:
        savepoint.rollback()
        return {"status": "FAILED", "reason": type(error).__name__}


def _execution_signature(session: Session, run_id: UUID) -> str:
    rows = list(
        session.scalars(
            select(ExecutionPaceDecision)
            .where(ExecutionPaceDecision.run_id == run_id)
            .order_by(ExecutionPaceDecision.company_id)
        )
    )
    return _json_fingerprint(
        [
            {
                "company_id": row.company_id,
                "decision_status": row.decision_status,
                "pace": row.pace,
                "reason": row.reason,
                "input_snapshot": row.input_snapshot,
            }
            for row in rows
        ]
    )


def _recompute_execution(session: Session) -> dict[str, object]:
    previous = session.scalar(
        select(ExecutionPaceRun)
        .order_by(ExecutionPaceRun.as_of.desc(), ExecutionPaceRun.recorded_at.desc())
        .limit(1)
    )
    previous_signature = _execution_signature(session, previous.id) if previous else None
    savepoint = session.begin_nested()
    try:
        run = create_execution_pace_run(
            session,
            s.ExecutionPaceRunCreate(
                actor=Actor.SYSTEM,
                reason="Canonical decision inputs changed; deterministic scheduled recomputation.",
                source="recurring-operations",
            ),
        )
        signature = _execution_signature(session, run.id)
        available = (
            session.scalar(
                select(func.count(ExecutionPaceDecision.id)).where(
                    ExecutionPaceDecision.run_id == run.id,
                    ExecutionPaceDecision.decision_status == "AVAILABLE",
                )
            )
            or 0
        )
        if signature == previous_signature:
            savepoint.rollback()
            return {"status": "SKIPPED", "reason": "Inputs and outcomes match the latest run."}
        if previous is None and available == 0:
            savepoint.rollback()
            return {
                "status": "BLOCKED",
                "reason": "No Execution Pace decision is currently available.",
            }
        savepoint.commit()
        return {"status": "SUCCEEDED", "run_id": str(run.id), "available_count": available}
    except Exception as error:
        savepoint.rollback()
        return {"status": "FAILED", "reason": type(error).__name__}


def _run_decision_recompute(engine: Engine) -> dict[str, object]:
    with Session(engine) as session:
        results = {
            ranking_type.value: _recompute_ranking(session, ranking_type)
            for ranking_type in RANKING_TYPES
        }
        results["EXECUTION_PACE"] = _recompute_execution(session)
        session.commit()
    states = {str(value["status"]) for value in results.values() if isinstance(value, dict)}
    overall = "FAILED" if states == {"FAILED"} else "PARTIAL" if "FAILED" in states else "SUCCEEDED"
    return {"status": overall, "results": results}


def _record_heartbeat(
    engine: Engine,
    instance_id: UUID,
    *,
    started_at: datetime,
    now_at: datetime,
    status: str = "RUNNING",
    error: str | None = None,
    stopped: bool = False,
) -> None:
    with Session(engine) as session:
        state = session.get(RecurringOperationsWorkerState, "primary")
        if state is None:
            state = RecurringOperationsWorkerState(
                worker_key="primary",
                instance_id=instance_id,
                status=status,
                process_started_at=started_at,
                last_heartbeat_at=now_at,
                stopped_at=now_at if stopped else None,
                last_error=error,
            )
            session.add(state)
        else:
            state.instance_id = instance_id
            state.status = status
            state.process_started_at = started_at
            state.last_heartbeat_at = now_at
            state.stopped_at = now_at if stopped else None
            state.last_error = error
        session.commit()


def run_recurring_cycle(
    settings: Settings,
    *,
    now_at: datetime | None = None,
    engine: Engine | None = None,
    instance_id: UUID | None = None,
    process_started_at: datetime | None = None,
) -> dict[str, object]:
    """Run due jobs once; the scheduler lock prevents duplicate concurrent cycles."""

    if not settings.recurring_operations_enabled:
        return {"status": "DISABLED", "reason": "RECURRING_OPERATIONS_ENABLED is false."}
    owned_engine = engine is None
    current_engine = engine or create_database_engine(settings)
    if current_engine is None:
        return {"status": "BLOCKED", "reason": "DATABASE_URL is not configured."}
    current = _utc(now_at)
    instance = instance_id or uuid4()
    started = _utc(process_started_at or current)
    try:
        if not wait_for_database(current_engine):
            return {
                "status": "BLOCKED",
                "reason": "Database or Alembic schema is not ready.",
            }
        with current_engine.connect() as connection:
            acquired: bool = connection.execute(
                text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
                {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
            ).scalar_one()
            connection.commit()
            if not acquired:
                return {
                    "status": "SKIPPED",
                    "reason": "Another recurring operations cycle is active.",
                }
            try:
                _record_heartbeat(
                    current_engine,
                    instance,
                    started_at=started,
                    now_at=current,
                )
                manual = process_manual_job_requests(current_engine, settings, now_at=current)
                jobs: list[dict[str, object]] = []
                jobs.append(
                    _run_one_job(
                        current_engine,
                        settings,
                        SEC_FUNDAMENTALS,
                        JOB_CADENCES_SECONDS[SEC_FUNDAMENTALS],
                        current,
                        lambda: _run_sec_domain(
                            current_engine,
                            settings,
                            ExternalDataDomain.REPORTED_FUNDAMENTALS,
                            current,
                        ),
                    )
                )
                jobs.append(
                    _run_one_job(
                        current_engine,
                        settings,
                        SEC_FILINGS,
                        JOB_CADENCES_SECONDS[SEC_FILINGS],
                        current,
                        lambda: _run_sec_domain(
                            current_engine, settings, ExternalDataDomain.SOURCE_DOCUMENTS, current
                        ),
                    )
                )
                if settings.fmp_consensus_ingestion_enabled:
                    jobs.append(
                        _run_one_job(
                            current_engine,
                            settings,
                            FMP_CONSENSUS,
                            JOB_CADENCES_SECONDS[FMP_CONSENSUS],
                            current,
                            lambda: _run_fmp_consensus(current_engine, settings, current),
                        )
                    )
                if settings.google_sheets_poll_seconds != 0:
                    jobs.append(
                        _run_one_job(
                            current_engine,
                            settings,
                            SHEETS_DISCOVERY,
                            settings.google_sheets_poll_seconds,
                            current,
                            lambda: _run_sheets_discovery(current_engine, settings),
                        )
                    )
                jobs.append(
                    _run_one_job(
                        current_engine,
                        settings,
                        RESEARCH_TRIGGER_SCAN,
                        JOB_CADENCES_SECONDS[RESEARCH_TRIGGER_SCAN],
                        current,
                        lambda: _run_trigger_scan(current_engine, current),
                    )
                )
                jobs.append(
                    _run_one_job(
                        current_engine,
                        settings,
                        AGENT_WORK_FEED,
                        JOB_CADENCES_SECONDS[AGENT_WORK_FEED],
                        current,
                        lambda: _publish_agent_feeds(current_engine, settings, current),
                    )
                )
                jobs.append(
                    _run_one_job(
                        current_engine,
                        settings,
                        DECISION_RECOMPUTE,
                        JOB_CADENCES_SECONDS[DECISION_RECOMPUTE],
                        current,
                        lambda: _run_decision_recompute(current_engine),
                    )
                )
                return {
                    "status": "COMPLETE",
                    "at": current.isoformat(),
                    "jobs": jobs,
                    "manual_request": manual,
                }
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                    {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
                )
    finally:
        if owned_engine:
            current_engine.dispose()


def _run_fmp_consensus(engine: Engine, settings: Settings, now_at: datetime) -> dict[str, object]:
    if not settings.fmp_consensus_ingestion_enabled:
        return {
            "status": "SKIPPED",
            "failure_code": "FMP_DISABLED_BY_POLICY",
            "reason": (
                "FMP consensus ingestion is disabled until storage/display rights are confirmed."
            ),
        }
    if settings.fmp_api_key is None:
        return {
            "status": "BLOCKED",
            "failure_code": "FMP_CREDENTIAL_MISSING",
            "failure_message": "FMP consensus ingestion is enabled but FMP_API_KEY is missing.",
        }
    with Session(engine) as session:
        report = run_scheduled(
            session,
            settings,
            domains=[ExternalDataDomain.CONSENSUS_ESTIMATES],
            run_date=now_at.date(),
        )
        session.commit()
        return {"status": report["status"], "report": report}


def recurring_operations_status(
    session: Session, settings: Settings, *, now_at: datetime | None = None
) -> s.RecurringOperationsStatusRead:
    current = _utc(now_at)
    worker = session.get(RecurringOperationsWorkerState, "primary")
    if not settings.recurring_operations_enabled:
        worker_state = "DISABLED"
    elif worker is None:
        worker_state = "NOT_STARTED"
    elif worker.status == "STOPPED":
        worker_state = "STOPPED"
    elif current - worker.last_heartbeat_at > WORKER_STALE_AFTER:
        worker_state = "STALE"
    else:
        worker_state = worker.status

    cadences = dict(JOB_CADENCES_SECONDS)
    cadences[SHEETS_DISCOVERY] = settings.google_sheets_poll_seconds
    jobs: list[s.RecurringOperationJobRead] = []
    for name in (
        SEC_FUNDAMENTALS,
        SEC_FILINGS,
        FMP_CONSENSUS,
        SHEETS_DISCOVERY,
        RESEARCH_TRIGGER_SCAN,
        AGENT_WORK_FEED,
        DECISION_RECOMPUTE,
    ):
        latest = _latest_operation(session, name)
        last_success = session.scalar(
            select(func.max(RecurringOperationRun.finished_at)).where(
                RecurringOperationRun.job_name == name,
                RecurringOperationRun.status.in_(("SUCCEEDED", "PARTIAL")),
            )
        )
        status = latest.status if latest is not None else "NOT_RUN"
        failure_code = latest.failure_code if latest is not None else None
        failure_message = latest.failure_message if latest is not None else None
        next_attempt = latest.next_attempt_at if latest is not None else None
        result = latest.result if latest is not None else {}
        if name in {SEC_FUNDAMENTALS, SEC_FILINGS} and not settings.sec_user_agent:
            status = "BLOCKED"
            failure_code = "SEC_USER_AGENT_MISSING"
            failure_message = (
                "Configure SEC_USER_AGENT with application name and monitored contact."
            )
        elif name == FMP_CONSENSUS and not settings.fmp_consensus_ingestion_enabled:
            status = "SKIPPED"
            failure_code = "FMP_DISABLED_BY_POLICY"
            failure_message = "FMP raw-data ingestion remains disabled pending appropriate rights."
        elif name == FMP_CONSENSUS and settings.fmp_api_key is None:
            status = "BLOCKED"
            failure_code = "FMP_CREDENTIAL_MISSING"
            failure_message = "Set FMP_API_KEY only after confirming storage and display rights."
        elif name == SHEETS_DISCOVERY and settings.google_sheets_poll_seconds == 0:
            status = "SKIPPED"
            failure_code = "POLLING_DISABLED"
            failure_message = "Set GOOGLE_SHEETS_POLL_SECONDS to a value of at least 60 to poll."
        elif name in {SHEETS_DISCOVERY, AGENT_WORK_FEED} and (
            not settings.google_sheets_spreadsheet_id
            or not settings.google_sheets_service_account_file
            or not settings.google_sheets_service_account_file.exists()
        ):
            status = "BLOCKED"
            failure_code = "GOOGLE_SHEETS_NOT_CONFIGURED"
            failure_message = "Configure the workbook ID and an external service-account key file."
        jobs.append(
            s.RecurringOperationJobRead(
                job_name=cast(s.RecurringOperationJobName, name),
                status=cast(s.RecurringOperationJobStatus, status),
                cadence_seconds=cadences[name],
                last_attempt_at=latest.started_at if latest else None,
                last_successful_at=last_success,
                next_attempt_at=next_attempt,
                failure_code=failure_code,
                failure_message=failure_message,
                result=result,
            )
        )

    return s.RecurringOperationsStatusRead(
        enabled=settings.recurring_operations_enabled,
        worker_state=cast(s.RecurringOperationsWorkerStatus, worker_state),
        worker_started_at=worker.process_started_at if worker else None,
        worker_last_seen_at=worker.last_heartbeat_at if worker else None,
        sec_user_agent_configured=bool(settings.sec_user_agent),
        google_sheets_configured=bool(settings.google_sheets_spreadsheet_id),
        google_sheets_credentials_available=bool(
            settings.google_sheets_service_account_file
            and settings.google_sheets_service_account_file.exists()
        ),
        google_sheets_poll_seconds=settings.google_sheets_poll_seconds,
        fmp_consensus_ingestion_enabled=settings.fmp_consensus_ingestion_enabled,
        jobs=jobs,
        market_data=queries.market_refresh_status(session),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one due-job cycle and exit")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=TICK_SECONDS,
        help="scheduler check interval; minimum 10 seconds",
    )
    args = parser.parse_args(argv)
    if args.interval_seconds < 10:
        parser.error("--interval-seconds must be at least 10")
    settings = Settings()
    stop_requested = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_requested.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    if not settings.recurring_operations_enabled:
        print(json.dumps({"status": "DISABLED", "reason": "RECURRING_OPERATIONS_ENABLED=false"}))
        if not args.once:
            while not stop_requested.wait(args.interval_seconds):
                pass
        return 0
    proxy_bypass_applied = configure_external_operations_no_proxy()
    if proxy_bypass_applied:
        logger.info(
            "Added process-local NO_PROXY entries for SEC and Google APIs after detecting "
            "the known loopback port-9 development proxy."
        )
    engine = create_database_engine(
        settings,
        write_operation="recurring_operations_worker",
        write_operation_kind="ingestion",
    )
    if engine is None:
        print(json.dumps({"status": "BLOCKED", "reason": "DATABASE_URL is not configured."}))
        return 2
    instance_id = uuid4()
    started_at = datetime.now(UTC)
    try:
        while not stop_requested.is_set():
            try:
                report = run_recurring_cycle(
                    settings,
                    engine=engine,
                    instance_id=instance_id,
                    process_started_at=started_at,
                )
                report["external_api_proxy_bypass_applied"] = proxy_bypass_applied
                print(json.dumps(report, indent=2, sort_keys=True, default=str), flush=True)
            except Exception as error:
                logger.exception("Recurring operations cycle failed")
                try:
                    _record_heartbeat(
                        engine,
                        instance_id,
                        started_at=started_at,
                        now_at=datetime.now(UTC),
                        status="FAILED",
                        error=type(error).__name__,
                    )
                except Exception:
                    logger.exception("Could not record recurring-worker failure state")
                print(
                    json.dumps({"status": "FAILED", "reason": type(error).__name__}),
                    flush=True,
                )
            if args.once:
                return 0
            stop_requested.wait(args.interval_seconds)
        return 0
    finally:
        try:
            _record_heartbeat(
                engine,
                instance_id,
                started_at=started_at,
                now_at=datetime.now(UTC),
                status="STOPPED",
                stopped=True,
            )
        except Exception:
            logger.exception("Could not record recurring-worker shutdown state")
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
