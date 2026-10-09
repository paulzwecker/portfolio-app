"""One-shot scheduled worker for the canonical external-data pipelines.

Run from cron or a systemd timer. The database holds idempotency, freshness and
attempt records; canonical observations remain in their domain-owned tables.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from portfolio_api.consensus_estimates import (
    FMP_PROVIDER_ID,
    FmpConsensusProvider,
    persist_provider_response,
)
from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    CompanyProviderIdentifier,
    ConsensusEstimateProviderMapping,
    CurrentLifecycle,
    ExternalIngestionAttempt,
    ExternalIngestionRun,
    LifecycleEvent,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    ProviderTransportError,
    parse_retry_after_seconds,
)
from portfolio_api.market_data_ingestion import (
    CROSSWALK_PATH,
    DEFAULT_CORPORATE_ACTION_OVERLAP_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    active_market_listings,
    apply_provider_import,
    build_provider_import,
    portfolio_fx_requirements,
)
from portfolio_api.reported_fundamentals import (
    SEC_PROVIDER_ID,
    _load_cik_mappings,
    sync_reported_fundamentals,
)
from portfolio_api.settings import Settings
from portfolio_api.source_documents import sync_sec_source_documents
from portfolio_api.yahoo_finance import (
    FX_SYMBOLS,
    YAHOO_PROVIDER_ID,
    YahooFinanceProvider,
    load_yahoo_crosswalk,
    yahoo_mapping_for_listing,
)

MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 30.0
ABANDONED_RUN_AGE = timedelta(hours=4)
DAILY_DOMAINS = (
    ExternalDataDomain.REPORTED_FUNDAMENTALS,
    ExternalDataDomain.SOURCE_DOCUMENTS,
    ExternalDataDomain.CONSENSUS_ESTIMATES,
    ExternalDataDomain.FX,
    ExternalDataDomain.MARKET_DATA,
    ExternalDataDomain.CORPORATE_ACTIONS,
)
YAHOO_DOMAINS = frozenset(
    {
        ExternalDataDomain.FX,
        ExternalDataDomain.MARKET_DATA,
        ExternalDataDomain.CORPORATE_ACTIONS,
    }
)
YAHOO_MARKET_DOMAINS = frozenset(
    {ExternalDataDomain.MARKET_DATA, ExternalDataDomain.CORPORATE_ACTIONS}
)
PROVIDERS = {
    ExternalDataDomain.REPORTED_FUNDAMENTALS: SEC_PROVIDER_ID,
    ExternalDataDomain.SOURCE_DOCUMENTS: SEC_PROVIDER_ID,
    ExternalDataDomain.CONSENSUS_ESTIMATES: FMP_PROVIDER_ID,
    ExternalDataDomain.FX: YAHOO_PROVIDER_ID,
    ExternalDataDomain.MARKET_DATA: YAHOO_PROVIDER_ID,
    ExternalDataDomain.CORPORATE_ACTIONS: YAHOO_PROVIDER_ID,
}
FRESHNESS_MAX_AGE = {
    ExternalDataDomain.REPORTED_FUNDAMENTALS: timedelta(hours=72),
    ExternalDataDomain.SOURCE_DOCUMENTS: timedelta(hours=72),
    ExternalDataDomain.CONSENSUS_ESTIMATES: timedelta(hours=72),
    ExternalDataDomain.FX: timedelta(hours=72),
    ExternalDataDomain.MARKET_DATA: timedelta(hours=72),
    ExternalDataDomain.CORPORATE_ACTIONS: timedelta(days=7),
}


@dataclass(frozen=True)
class DomainOutcome:
    status: str
    report: dict[str, Any]
    failure_code: str | None = None
    failure_message: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class RunClaim:
    run_id: UUID
    provider_id: str
    domain: ExternalDataDomain
    created: bool
    status: str
    request_scope: dict[str, Any]


def retry_delay_seconds(attempt_number: int, retry_after_seconds: float | None = None) -> float:
    """Exponential retry with a hard cap; provider Retry-After may raise the delay."""

    if attempt_number < 1:
        raise ValueError("attempt_number must be positive")
    backoff = 1.0 * (2 ** (attempt_number - 1))
    delay = min(
        MAX_RETRY_DELAY_SECONDS,
        max(backoff, retry_after_seconds or 0.0),
    )
    return float(delay)


def classify_transport_error(error: Exception) -> tuple[str, str, bool, float | None]:
    """Return a safe persistent error code/message and bounded-retry guidance."""

    if isinstance(error, ProviderTransportError):
        return (
            error.code,
            str(error)[:2000],
            error.retryable,
            error.retry_after_seconds,
        )
    if isinstance(error, urllib.error.HTTPError):
        retryable = error.code == 429 or 500 <= error.code <= 599
        code = "RATE_LIMITED" if error.code == 429 else f"HTTP_{error.code}"
        raw_retry_after = error.headers.get("Retry-After") if error.headers else None
        retry_after = parse_retry_after_seconds(raw_retry_after)
        return code, f"Provider returned HTTP {error.code}.", retryable, retry_after
    if isinstance(error, (TimeoutError, urllib.error.URLError, ConnectionError)):
        return (
            "NETWORK_ERROR",
            "Provider network request failed; transport details omitted.",
            True,
            None,
        )
    if isinstance(error, SQLAlchemyError):
        retryable = isinstance(error, OperationalError)
        return (
            "DATABASE_ERROR",
            "Canonical persistence failed; database connection details omitted.",
            retryable,
            None,
        )
    if isinstance(error, ValueError):
        return "INGESTION_VALIDATION_ERROR", str(error)[:2000], False, None
    return (
        "INGESTION_ERROR",
        f"{type(error).__name__} raised; inspect worker logs for details.",
        False,
        None,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(value, default=str)))


def active_company_states(session: Session) -> dict[UUID, str]:
    rows = session.execute(
        select(LifecycleEvent.company_id, LifecycleEvent.new_state)
        .join(CurrentLifecycle, CurrentLifecycle.event_id == LifecycleEvent.id)
        .where(LifecycleEvent.new_state.in_(("PORTFOLIO", "WATCHLIST")))
    ).all()
    states = {company_id: state for company_id, state in rows}
    return states


def _company_order(states: dict[UUID, str]) -> list[UUID]:
    return sorted(
        states,
        key=lambda company_id: (
            0 if states[company_id] == "PORTFOLIO" else 1,
            str(company_id),
        ),
    )


def _lifecycle_counts(states: dict[UUID, str]) -> dict[str, int]:
    return {
        lifecycle: sum(value == lifecycle for value in states.values())
        for lifecycle in ("PORTFOLIO", "WATCHLIST")
    }


def _states_from_scope(scope: dict[str, Any]) -> dict[UUID, str] | None:
    raw_states = scope.get("company_states")
    if not isinstance(raw_states, list):
        return None
    states: dict[UUID, str] = {}
    for item in raw_states:
        if (
            isinstance(item, dict)
            and isinstance(item.get("company_id"), str)
            and item.get("lifecycle") in {"PORTFOLIO", "WATCHLIST"}
        ):
            states[UUID(item["company_id"])] = str(item["lifecycle"])
    return states


def _sec_mapping_scope(session: Session, company_ids: list[UUID]) -> list[dict[str, str]]:
    if not company_ids:
        return []
    rows = session.scalars(
        select(CompanyProviderIdentifier).where(
            CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
            CompanyProviderIdentifier.identifier_type == "SEC_CIK",
            CompanyProviderIdentifier.company_id.in_(company_ids),
        )
    )
    return [
        {"company_id": str(row.company_id), "cik": row.identifier_value}
        for row in sorted(rows, key=lambda item: (str(item.company_id), item.identifier_value))
    ]


def _fmp_mappings(
    session: Session, company_ids: list[UUID], *, mapping_ids: list[UUID] | None = None
) -> list[ConsensusEstimateProviderMapping]:
    if not company_ids:
        return []
    current = datetime.now(UTC)
    statement = select(ConsensusEstimateProviderMapping).where(
        ConsensusEstimateProviderMapping.provider_id == FMP_PROVIDER_ID,
        ConsensusEstimateProviderMapping.effective_from <= current,
        ConsensusEstimateProviderMapping.company_id.in_(company_ids),
    )
    if mapping_ids is not None:
        statement = statement.where(ConsensusEstimateProviderMapping.id.in_(mapping_ids))
    rows = list(
        session.scalars(
            statement.order_by(
                ConsensusEstimateProviderMapping.company_id,
                ConsensusEstimateProviderMapping.effective_from.desc(),
                ConsensusEstimateProviderMapping.role.desc(),
                ConsensusEstimateProviderMapping.priority,
                ConsensusEstimateProviderMapping.id,
            )
        )
    )
    latest: dict[UUID, ConsensusEstimateProviderMapping] = {}
    for row in rows:
        latest.setdefault(row.company_id, row)
    active_order = {company_id: index for index, company_id in enumerate(company_ids)}
    return sorted(latest.values(), key=lambda row: active_order[row.company_id])


def _scope_for_domain(
    session: Session,
    domain: ExternalDataDomain,
    *,
    start_date: date | None,
    end_date: date,
    lookback_days: int,
) -> dict[str, Any]:
    if domain in {
        ExternalDataDomain.FX,
        ExternalDataDomain.MARKET_DATA,
        ExternalDataDomain.CORPORATE_ACTIONS,
    }:
        selected, _held_ids = active_market_listings(session)
        scope: dict[str, Any] = {
            "scope": "active",
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat(),
            "lookback_days": lookback_days,
        }
        if domain == ExternalDataDomain.FX:
            base_currency, required_fx_pairs = portfolio_fx_requirements(session)
            if ("TWD", "EUR") in FX_SYMBOLS:
                required_fx_pairs.add(("TWD", "EUR"))
            crosswalk = load_yahoo_crosswalk(CROSSWALK_PATH)
            if base_currency is not None:
                for listing, security, _company in selected:
                    mapping = yahoo_mapping_for_listing(
                        crosswalk,
                        venue=listing.venue,
                        ticker=listing.ticker,
                        currency=listing.currency,
                        security_type=security.security_type,
                    )
                    if mapping is not None and mapping.currency != base_currency:
                        required_fx_pairs.add((mapping.currency, base_currency))
            scope["required_fx_pairs"] = [list(pair) for pair in sorted(required_fx_pairs)]
        else:
            listing_keys = sorted(
                {(listing.venue, listing.ticker) for listing, _security, _company in selected},
                key=lambda item: (item[0].casefold(), item[1].casefold()),
            )
            scope["corporate_action_overlap_days"] = DEFAULT_CORPORATE_ACTION_OVERLAP_DAYS
            scope["listing_keys"] = [
                {"venue": venue, "ticker": ticker} for venue, ticker in listing_keys
            ]
        return scope
    states = active_company_states(session)
    company_ids = _company_order(states)
    company_scope: dict[str, Any] = {
        "company_ids": [str(item) for item in company_ids],
        "company_states": [
            {"company_id": str(company_id), "lifecycle": states[company_id]}
            for company_id in company_ids
        ],
        "lifecycle_counts": _lifecycle_counts(states),
    }
    if domain in {ExternalDataDomain.REPORTED_FUNDAMENTALS, ExternalDataDomain.SOURCE_DOCUMENTS}:
        company_scope["verified_cik_mappings"] = _sec_mapping_scope(session, company_ids)
    elif domain == ExternalDataDomain.CONSENSUS_ESTIMATES:
        company_scope["fmp_mapping_ids"] = [
            str(item.id) for item in _fmp_mappings(session, company_ids)
        ]
    return company_scope


def _idempotency_key(
    provider_id: str,
    domain: ExternalDataDomain,
    scope: dict[str, Any],
    run_date: date,
    replay_nonce: UUID | None,
) -> str:
    digest = hashlib.sha256(_canonical_json(scope).encode("utf-8")).hexdigest()[:20]
    if replay_nonce is not None:
        return f"replay:{provider_id}:{domain.value}:{replay_nonce}:{digest}"
    return f"daily:{provider_id}:{domain.value}:{run_date.isoformat()}:{digest}"


def _selected_domains(domains: list[ExternalDataDomain] | None) -> set[ExternalDataDomain]:
    selected = set(domains or DAILY_DOMAINS)
    if selected & YAHOO_MARKET_DOMAINS:
        # Prices and actions use the same chart response. FX has a separate
        # subject and date window, so a targeted FX backfill stays FX-only.
        selected.update(YAHOO_MARKET_DOMAINS)
    return selected


def parse_fx_pair(value: str) -> tuple[str, str]:
    """Parse an explicit supported base/quote pair for a targeted FX run."""

    parts = value.strip().upper().split("/")
    if len(parts) != 2 or any(len(part) != 3 for part in parts) or parts[0] == parts[1]:
        raise ValueError("FX pairs must use BASE/QUOTE with two distinct three-letter codes")
    pair = (parts[0], parts[1])
    if pair not in FX_SYMBOLS:
        raise ValueError(f"No reviewed Yahoo FX mapping exists for {pair[0]}/{pair[1]}")
    return pair


def _mark_interrupted_run(session: Session, run: ExternalIngestionRun, at: datetime) -> None:
    started_at = run.last_attempt_started_at or run.started_at
    if at - started_at < ABANDONED_RUN_AGE:
        return
    attempt_number = max(run.attempt_count, 1)
    existing = session.scalar(
        select(ExternalIngestionAttempt.id).where(
            ExternalIngestionAttempt.run_id == run.id,
            ExternalIngestionAttempt.attempt_number == attempt_number,
        )
    )
    if existing is None:
        session.add(
            ExternalIngestionAttempt(
                id=uuid4(),
                run_id=run.id,
                attempt_number=attempt_number,
                status="FAILED",
                started_at=started_at,
                finished_at=at,
                retryable=False,
                failure_code="WORKER_INTERRUPTED",
                failure_message="The worker stopped before recording this attempt outcome.",
                report={"recovered_by": "next operator invocation"},
            )
        )
    run.attempt_count = attempt_number
    run.status = "FAILED"
    run.finished_at = at
    run.failure_code = "WORKER_INTERRUPTED"
    run.failure_message = "The worker stopped before recording this run outcome."
    run.report = {"status": "FAILED", "reason": "WORKER_INTERRUPTED"}
    session.commit()


def _claim_run(
    session: Session,
    provider_id: str,
    domain: ExternalDataDomain,
    request_scope: dict[str, Any],
    *,
    run_date: date,
    replay_nonce: UUID | None = None,
    replay_of_run_id: UUID | None = None,
) -> RunClaim:
    current = datetime.now(UTC)
    run_id = uuid4()
    key = _idempotency_key(provider_id, domain, request_scope, run_date, replay_nonce)
    statement = (
        pg_insert(ExternalIngestionRun)
        .values(
            id=run_id,
            provider_id=provider_id,
            domain=domain.value,
            idempotency_key=key,
            replay_of_run_id=replay_of_run_id,
            status="RUNNING",
            requested_at=current,
            created_at=current,
            started_at=current,
            last_attempt_started_at=None,
            finished_at=None,
            last_successful_at=None,
            attempt_count=0,
            max_attempts=MAX_ATTEMPTS,
            request_scope=request_scope,
            report={"status": "RUNNING"},
        )
        .on_conflict_do_nothing(index_elements=[ExternalIngestionRun.idempotency_key])
        .returning(ExternalIngestionRun.id)
    )
    inserted_id = session.execute(statement).scalar_one_or_none()
    session.commit()
    if inserted_id is not None:
        return RunClaim(run_id, provider_id, domain, True, "RUNNING", request_scope)
    existing = session.scalar(
        select(ExternalIngestionRun).where(ExternalIngestionRun.idempotency_key == key)
    )
    if existing is None:
        raise RuntimeError("Idempotent ingestion run could not be loaded after insert conflict")
    _mark_interrupted_run(session, existing, current)
    session.refresh(existing)
    return RunClaim(
        existing.id,
        provider_id,
        domain,
        False,
        existing.status,
        existing.request_scope,
    )


def _failure_outcome(error: Exception) -> tuple[str, str, bool, float | None]:
    return classify_transport_error(error)


def _execute_cycle(
    session: Session,
    claims: list[RunClaim],
    operation: Callable[[], dict[ExternalDataDomain, DomainOutcome]],
) -> None:
    if not claims:
        return
    attempt_number = 0
    while attempt_number < MAX_ATTEMPTS:
        attempt_number += 1
        started_at = datetime.now(UTC)
        for claim in claims:
            run = session.get(ExternalIngestionRun, claim.run_id)
            if run is None:
                raise RuntimeError("Claimed ingestion run was removed")
            run.attempt_count = attempt_number
            run.last_attempt_started_at = started_at
            run.status = "RUNNING"
        session.commit()
        try:
            outcomes = operation()
            missing = [claim.domain.value for claim in claims if claim.domain not in outcomes]
            if missing:
                raise RuntimeError(f"Provider cycle omitted domain outcomes: {', '.join(missing)}")
            session.commit()
            finished_at = datetime.now(UTC)
            for claim in claims:
                outcome = outcomes[claim.domain]
                run = session.get(ExternalIngestionRun, claim.run_id)
                if run is None:
                    raise RuntimeError("Claimed ingestion run was removed before completion")
                run.status = outcome.status
                run.finished_at = finished_at
                run.failure_code = outcome.failure_code
                run.failure_message = outcome.failure_message
                run.report = _json_object(outcome.report)
                run.last_successful_at = (
                    finished_at if outcome.status in {"COMPLETE", "PARTIAL"} else None
                )
                session.add(
                    ExternalIngestionAttempt(
                        id=uuid4(),
                        run_id=claim.run_id,
                        attempt_number=attempt_number,
                        status=("SUCCEEDED" if outcome.status == "COMPLETE" else outcome.status),
                        started_at=started_at,
                        finished_at=finished_at,
                        retryable=outcome.retryable,
                        failure_code=outcome.failure_code,
                        failure_message=outcome.failure_message,
                        report=_json_object(outcome.report),
                    )
                )
            session.commit()
            return
        except Exception as error:
            session.rollback()
            code, message, retryable, retry_after = _failure_outcome(error)
            finished_at = datetime.now(UTC)
            will_retry = retryable and attempt_number < MAX_ATTEMPTS
            for claim in claims:
                run = session.get(ExternalIngestionRun, claim.run_id)
                if run is None:
                    continue
                run.status = "RUNNING" if will_retry else "FAILED"
                run.finished_at = None if will_retry else finished_at
                run.failure_code = code
                run.failure_message = message
                run.report = {
                    "status": "RETRYING" if will_retry else "FAILED",
                    "failure_code": code,
                    "failure_message": message,
                    "retryable": retryable,
                }
                session.add(
                    ExternalIngestionAttempt(
                        id=uuid4(),
                        run_id=claim.run_id,
                        attempt_number=attempt_number,
                        status="FAILED",
                        started_at=started_at,
                        finished_at=finished_at,
                        retryable=retryable,
                        failure_code=code,
                        failure_message=message,
                        report={"retry_after_seconds": retry_after},
                    )
                )
            session.commit()
            if will_retry:
                time.sleep(retry_delay_seconds(attempt_number, retry_after))


def _coverage_outcome(
    *,
    report: dict[str, Any],
    target_count: int,
    mapped_count: int,
    successful_count: int,
    issue_count: int,
    no_mapping_code: str,
    no_success_code: str,
) -> DomainOutcome:
    if target_count == 0:
        return DomainOutcome("NOT_APPLICABLE", {**report, "status": "NOT_APPLICABLE"})
    if mapped_count == 0:
        return DomainOutcome(
            "BLOCKED",
            {**report, "status": "BLOCKED", "reason": no_mapping_code},
            no_mapping_code,
            "No reviewed provider identity is available for active companies.",
        )
    if successful_count == 0:
        return DomainOutcome(
            "FAILED",
            {**report, "status": "FAILED", "reason": no_success_code},
            no_success_code,
            "No active subject produced a usable canonical observation.",
        )
    if mapped_count < target_count or issue_count:
        return DomainOutcome(
            "PARTIAL",
            {**report, "status": "PARTIAL"},
            "PARTIAL_COVERAGE",
            f"{target_count - mapped_count} active subjects lack a provider mapping; "
            f"{issue_count} provider or normalization checks remain.",
        )
    return DomainOutcome("COMPLETE", {**report, "status": "COMPLETE"})


def _fundamentals_operation(
    session: Session,
    settings: Settings,
    states: dict[UUID, str],
    *,
    mapping_scope: list[dict[str, Any]] | None = None,
) -> DomainOutcome:
    ordered_ids = _company_order(states)
    mapped = _load_cik_mappings(session, company_ids=ordered_ids)
    if mapping_scope is not None:
        allowed = {
            UUID(item["company_id"]): item["cik"]
            for item in mapping_scope
            if isinstance(item.get("company_id"), str) and isinstance(item.get("cik"), str)
        }
        mapped = {
            company_id: cik for company_id, cik in mapped.items() if allowed.get(company_id) == cik
        }
    mapped_ids = [company_id for company_id in ordered_ids if company_id in mapped]
    missing_ids = [company_id for company_id in ordered_ids if company_id not in mapped]
    base_report: dict[str, Any] = {
        "provider_id": SEC_PROVIDER_ID,
        "domain": ExternalDataDomain.REPORTED_FUNDAMENTALS.value,
        "target_company_count": len(ordered_ids),
        "mapped_company_count": len(mapped_ids),
        "unmapped_active_company_ids": [str(item) for item in missing_ids],
        "lifecycle_counts": _lifecycle_counts(states),
        "source_policy": "SEC Company Facts primary; standard concepts only",
    }
    if not ordered_ids:
        return DomainOutcome("NOT_APPLICABLE", {**base_report, "status": "NOT_APPLICABLE"})
    if not settings.sec_user_agent:
        return DomainOutcome(
            "BLOCKED",
            {**base_report, "status": "BLOCKED", "reason": "MISSING_SEC_USER_AGENT"},
            "MISSING_SEC_USER_AGENT",
            "SEC_USER_AGENT is not configured.",
        )
    if not mapped_ids:
        return DomainOutcome(
            "BLOCKED",
            {**base_report, "status": "BLOCKED", "reason": "NO_VERIFIED_CIK_MAPPINGS"},
            "NO_VERIFIED_CIK_MAPPINGS",
            "Active companies have no reviewed SEC CIK mapping.",
        )
    results = asyncio.run(sync_reported_fundamentals(session, settings, company_ids=mapped_ids))
    fact_count = 0
    data_check_count = 0
    warning_count = 0
    error_count = 0
    result_company_ids: set[str] = set()
    company_fact_counts: dict[str, int] = {}
    for item in results:
        company_id = item.get("company_id")
        if isinstance(company_id, str):
            result_company_ids.add(company_id)
        reconciliation = item.get("reconciliation", {})
        if not isinstance(reconciliation, dict):
            continue
        source_fact_count = int(reconciliation.get("source_fact_count", 0) or 0)
        fact_count += source_fact_count
        if isinstance(company_id, str):
            company_fact_counts[company_id] = source_fact_count
        data_check_count += int(reconciliation.get("data_check_count", 0) or 0)
        issues = reconciliation.get("issues", [])
        if isinstance(issues, list):
            warning_count += sum(
                isinstance(issue, dict) and issue.get("severity") == "WARNING" for issue in issues
            )
            error_count += sum(
                isinstance(issue, dict) and issue.get("severity") == "ERROR" for issue in issues
            )
    mapped_company_ids = {str(item) for item in mapped_ids}
    missing_response_ids = sorted(mapped_company_ids - result_company_ids)
    companies_without_facts = sorted(
        company_id
        for company_id in mapped_company_ids
        if company_fact_counts.get(company_id, 0) == 0
    )
    report = {
        **base_report,
        "mapped_results": results,
        "missing_provider_response_company_ids": missing_response_ids,
        "mapped_companies_without_facts": companies_without_facts,
        "normalized_source_fact_count": fact_count,
        "data_check_fact_count": data_check_count,
        "normalization_warning_count": warning_count,
        "normalization_error_count": error_count,
    }
    issue_count = (
        len(missing_ids)
        + len(missing_response_ids)
        + len(companies_without_facts)
        + data_check_count
        + warning_count
        + error_count
    )
    return _coverage_outcome(
        report=report,
        target_count=len(ordered_ids),
        mapped_count=len(mapped_ids),
        successful_count=fact_count,
        issue_count=issue_count,
        no_mapping_code="NO_VERIFIED_CIK_MAPPINGS",
        no_success_code="NO_NORMALIZED_REPORTED_FACTS",
    )


def _source_documents_operation(
    session: Session,
    settings: Settings,
    states: dict[UUID, str],
    *,
    mapping_scope: list[dict[str, Any]] | None = None,
) -> DomainOutcome:
    ordered_ids = _company_order(states)
    mapped = _load_cik_mappings(session, company_ids=ordered_ids)
    if mapping_scope is not None:
        allowed = {
            UUID(item["company_id"]): item["cik"]
            for item in mapping_scope
            if isinstance(item.get("company_id"), str) and isinstance(item.get("cik"), str)
        }
        mapped = {
            company_id: cik for company_id, cik in mapped.items() if allowed.get(company_id) == cik
        }
    mapped_ids = [company_id for company_id in ordered_ids if company_id in mapped]
    missing_ids = [company_id for company_id in ordered_ids if company_id not in mapped]
    base_report: dict[str, Any] = {
        "provider_id": SEC_PROVIDER_ID,
        "domain": ExternalDataDomain.SOURCE_DOCUMENTS.value,
        "target_company_count": len(ordered_ids),
        "mapped_company_count": len(mapped_ids),
        "unmapped_active_company_ids": [str(item) for item in missing_ids],
        "lifecycle_counts": _lifecycle_counts(states),
        "source_policy": "SEC EDGAR submissions metadata; filing bodies remain at SEC",
    }
    if not ordered_ids:
        return DomainOutcome("NOT_APPLICABLE", {**base_report, "status": "NOT_APPLICABLE"})
    if not settings.sec_user_agent:
        return DomainOutcome(
            "BLOCKED",
            {**base_report, "status": "BLOCKED", "reason": "MISSING_SEC_USER_AGENT"},
            "MISSING_SEC_USER_AGENT",
            "SEC_USER_AGENT is not configured.",
        )
    if not mapped_ids:
        return DomainOutcome(
            "BLOCKED",
            {**base_report, "status": "BLOCKED", "reason": "NO_VERIFIED_CIK_MAPPINGS"},
            "NO_VERIFIED_CIK_MAPPINGS",
            "Active companies have no reviewed SEC CIK mapping.",
        )
    results = asyncio.run(sync_sec_source_documents(session, settings, company_ids=mapped_ids))
    result = results[0] if results else {}
    reconciliation = result.get("reconciliation", {})
    if not isinstance(reconciliation, dict):
        reconciliation = {}
    raw_history_skips = result.get("history_files_skipped_as_unchanged", 0)
    document_count = int(
        reconciliation.get("documents_imported", result.get("documents_imported", 0)) or 0
    ) + int(reconciliation.get("documents_reused", 0) or 0)
    unsupported = int(reconciliation.get("unsupported_forms", 0) or 0)
    malformed = int(reconciliation.get("malformed_filing_rows", 0) or 0)
    conflicts = int(reconciliation.get("existing_metadata_conflicts", 0) or 0)
    unlinked = int(reconciliation.get("amendments_unlinked", 0) or 0)
    data_checks = int(reconciliation.get("data_check_documents", 0) or 0)
    raw_missing_filings = reconciliation.get("companies_without_supported_filings", [])
    missing_filings = raw_missing_filings if isinstance(raw_missing_filings, list) else []
    issues = reconciliation.get("issues", [])
    issue_count = (
        len(missing_ids)
        + len(missing_filings)
        + unsupported
        + malformed
        + conflicts
        + unlinked
        + data_checks
        + (len(issues) if isinstance(issues, list) else 0)
        + (1 if document_count == 0 else 0)
    )
    report = {
        **base_report,
        "provider_result": result,
        "mapped_companies_without_supported_filings": missing_filings,
        "normalized_document_count": document_count,
        "history_files_skipped_as_unchanged": (
            raw_history_skips if isinstance(raw_history_skips, int) else 0
        ),
        "unsupported_form_count": unsupported,
        "malformed_record_count": malformed,
        "metadata_conflict_count": conflicts,
        "unlinked_amendment_count": unlinked,
        "data_check_document_count": data_checks,
    }
    return _coverage_outcome(
        report=report,
        target_count=len(ordered_ids),
        mapped_count=len(mapped_ids),
        successful_count=document_count,
        issue_count=issue_count,
        no_mapping_code="NO_VERIFIED_CIK_MAPPINGS",
        no_success_code="NO_SOURCE_DOCUMENTS_NORMALIZED",
    )


def _consensus_operation(
    session: Session,
    settings: Settings,
    states: dict[UUID, str],
    *,
    mapping_ids: list[UUID] | None = None,
) -> DomainOutcome:
    ordered_ids = _company_order(states)
    mappings = _fmp_mappings(session, ordered_ids, mapping_ids=mapping_ids)
    mapped_ids = {item.company_id for item in mappings}
    missing_ids = [company_id for company_id in ordered_ids if company_id not in mapped_ids]
    base_report: dict[str, Any] = {
        "provider_id": FMP_PROVIDER_ID,
        "domain": ExternalDataDomain.CONSENSUS_ESTIMATES.value,
        "target_company_count": len(ordered_ids),
        "mapped_company_count": len(mappings),
        "unmapped_active_company_ids": [str(item) for item in missing_ids],
        "lifecycle_counts": _lifecycle_counts(states),
        "source_policy": "FMP continuity per reviewed FMP mapping; no cross-vendor synthesis",
        "provider_mapping_ids": [str(item.id) for item in mappings],
        "provider_mappings": [
            {
                "mapping_id": str(item.id),
                "company_id": str(item.company_id),
                "provider_symbol": item.provider_symbol,
                "role": item.role,
                "priority": item.priority,
                "currency": item.currency,
            }
            for item in mappings
        ],
    }
    if not ordered_ids:
        return DomainOutcome("NOT_APPLICABLE", {**base_report, "status": "NOT_APPLICABLE"})
    if settings.fmp_api_key is None:
        return DomainOutcome(
            "BLOCKED",
            {**base_report, "status": "BLOCKED", "reason": "MISSING_FMP_API_KEY"},
            "MISSING_FMP_API_KEY",
            "FMP_API_KEY is not configured.",
        )
    if not mappings:
        return DomainOutcome(
            "BLOCKED",
            {**base_report, "status": "BLOCKED", "reason": "NO_ACTIVE_FMP_MAPPINGS"},
            "NO_ACTIVE_FMP_MAPPINGS",
            "Active companies have no reviewed FMP provider mapping.",
        )
    symbols = {mapping.company_id: mapping.provider_symbol for mapping in mappings}
    query = ProviderQuery(
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
        subjects=tuple(
            CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=company_id)
            for company_id in symbols
        ),
        requested_at=datetime.now(UTC),
    )
    provider = FmpConsensusProvider(settings.fmp_api_key.get_secret_value(), symbols)
    records = asyncio.run(provider.fetch(query))
    mapping_by_symbol = {mapping.provider_symbol: mapping for mapping in mappings}
    result_rows = []
    unknown_records = []
    normalized_by_company: dict[UUID, int] = {item.company_id: 0 for item in mappings}
    for record in records:
        symbol = (record.source_record_id or "").rsplit(":", maxsplit=1)[0]
        mapping = mapping_by_symbol.get(symbol)
        if mapping is None:
            unknown_records.append(record.source_record_id)
            continue
        persisted_result = persist_provider_response(session, record, mapping)
        result_rows.append(
            {
                "provider_symbol": mapping.provider_symbol,
                "provider_mapping_id": str(mapping.id),
                "company_id": str(mapping.company_id),
                "source_record_id": record.source_record_id,
                **persisted_result,
            }
        )
        reconciliation = persisted_result.get("reconciliation", {})
        if isinstance(reconciliation, dict):
            normalized_by_company[mapping.company_id] += int(
                reconciliation.get("normalized_facts", 0) or 0
            )
    normalized = sum(
        int((item.get("reconciliation") or {}).get("normalized_facts", 0) or 0)
        for item in result_rows
        if isinstance(item.get("reconciliation"), dict)
    )
    data_checks = sum(
        int((item.get("reconciliation") or {}).get("data_check_facts", 0) or 0)
        for item in result_rows
        if isinstance(item.get("reconciliation"), dict)
    )
    no_estimates_company_ids = [
        str(company_id)
        for company_id, company_fact_count in normalized_by_company.items()
        if company_fact_count == 0
    ]
    report = {
        **base_report,
        "provider_response_count": len(records),
        "unknown_provider_responses": unknown_records,
        "provider_batches": result_rows,
        "normalized_estimate_count": normalized,
        "data_check_estimate_count": data_checks,
        "mapped_companies_without_estimates": no_estimates_company_ids,
    }
    issue_count = (
        len(missing_ids) + len(unknown_records) + data_checks + len(no_estimates_company_ids)
    )
    return _coverage_outcome(
        report=report,
        target_count=len(ordered_ids),
        mapped_count=len(mappings),
        successful_count=normalized,
        issue_count=issue_count,
        no_mapping_code="NO_ACTIVE_FMP_MAPPINGS",
        no_success_code="NO_NORMALIZED_ESTIMATES",
    )


def _domain_status_for_yahoo(
    domain: ExternalDataDomain,
    report: dict[str, Any],
    persisted: dict[str, Any],
) -> DomainOutcome:
    market_batches = report.get("market_data_batches", [])
    fx_batches = report.get("fx_batches", [])
    market_accepted = sum(int(batch.get("accepted_subjects", 0) or 0) for batch in market_batches)
    market_rows = sum(
        int(batch.get("daily_price_rows", 0) or 0) + int(batch.get("current_quote_rows", 0) or 0)
        for batch in market_batches
    )
    action_rows = sum(int(batch.get("corporate_action_rows", 0) or 0) for batch in market_batches)
    fx_accepted = sum(len(batch.get("accepted_pairs", [])) for batch in fx_batches)
    fx_rows = sum(int(batch.get("fx_observation_rows", 0) or 0) for batch in fx_batches)
    unresolved = report.get("unresolved_listings", [])
    active_without_listing = report.get("active_company_without_listing", [])
    market_failures = report.get("provider_fetch_failures", [])
    fx_failures = report.get("fx_fetch_failures", [])
    market_rejected = sum(len(batch.get("rejected_subjects", [])) for batch in market_batches)
    fx_rejected = sum(len(batch.get("rejected_pairs", [])) for batch in fx_batches)
    persisted_totals = persisted.get("persistence", {}).get("inserted_totals", {})

    relevant_failures = fx_failures if domain == ExternalDataDomain.FX else market_failures
    retryable = any(
        isinstance(failure, dict) and failure.get("retryable") is True
        for failure in relevant_failures
    )

    if domain == ExternalDataDomain.MARKET_DATA:
        targeted = int(report.get("selected_listing_count", 0) or 0)
        mapped = int(report.get("verified_listing_mapping_count", 0) or 0)
        issue_count = (
            len(unresolved) + len(active_without_listing) + len(market_failures) + market_rejected
        )
        accepted = market_accepted
        detail = {
            "requested_listing_count": targeted,
            "verified_listing_mapping_count": mapped,
            "accepted_listing_response_count": accepted,
            "market_price_rows_received": market_rows,
            "unresolved_listings": unresolved,
            "active_companies_without_listing": active_without_listing,
            "provider_fetch_failures": market_failures,
            "normalization_rejections": market_rejected,
            "price_observations_inserted": persisted_totals.get("price_observations", 0),
        }
        no_mapping_code = "NO_VERIFIED_LISTING_MAPPINGS"
        no_success_code = "NO_MARKET_DATA_RESPONSES"
    elif domain == ExternalDataDomain.CORPORATE_ACTIONS:
        targeted = int(report.get("selected_listing_count", 0) or 0)
        mapped = int(report.get("verified_listing_mapping_count", 0) or 0)
        unverified_count = action_rows
        issue_count = (
            len(unresolved)
            + len(active_without_listing)
            + len(market_failures)
            + market_rejected
            + unverified_count
        )
        accepted = market_accepted
        detail = {
            "requested_listing_count": targeted,
            "verified_listing_mapping_count": mapped,
            "accepted_listing_response_count": accepted,
            "corporate_actions_received": action_rows,
            "corporate_actions_inserted": persisted_totals.get("corporate_actions", 0),
            "unverified_corporate_actions": unverified_count,
            "data_quality_state": "DATA_CHECK" if unverified_count else "COMPLETE",
            "unresolved_listings": unresolved,
            "provider_fetch_failures": market_failures,
        }
        no_mapping_code = "NO_VERIFIED_LISTING_MAPPINGS"
        no_success_code = "NO_CORPORATE_ACTION_RESPONSES"
    else:
        required = report.get("required_fx_pairs", [])
        not_due = report.get("fx_pairs_not_due", [])
        unmapped = report.get("unmapped_fx_pairs", [])
        mapped = max(0, len(required) - len(unmapped))
        issue_count = len(unmapped) + len(fx_failures) + fx_rejected
        accepted = fx_accepted + len(not_due)
        targeted = len(required)
        detail = {
            "required_fx_pairs": required,
            "unmapped_fx_pairs": unmapped,
            "pairs_already_current_for_requested_date": not_due,
            "accepted_fx_pairs": fx_accepted,
            "fx_observation_rows_received": fx_rows,
            "provider_fetch_failures": fx_failures,
            "normalization_rejections": fx_rejected,
            "fx_observations_inserted": persisted_totals.get("fx_observations", 0),
        }
        no_mapping_code = "NO_SUPPORTED_FX_PAIRS"
        no_success_code = "NO_FX_RESPONSES"

    summary = {
        "provider_id": YAHOO_PROVIDER_ID,
        "domain": domain.value,
        "request_scope": {
            "start_date": report.get("lookback_start"),
            "end_date": report.get("end_date"),
            "scope": report.get("scope"),
        },
        "domain_report": detail,
    }
    if domain in {ExternalDataDomain.MARKET_DATA, ExternalDataDomain.CORPORATE_ACTIONS}:
        active_without_listing = report.get("active_company_without_listing", [])
        if targeted == 0 and active_without_listing:
            return DomainOutcome(
                "BLOCKED",
                {**summary, "status": "BLOCKED", "reason": "NO_ACTIVE_CANONICAL_LISTINGS"},
                "NO_ACTIVE_CANONICAL_LISTINGS",
                "Active companies have no canonical listing to query.",
            )
    if targeted == 0:
        return DomainOutcome("NOT_APPLICABLE", {**summary, "status": "NOT_APPLICABLE"})
    if mapped == 0:
        return DomainOutcome(
            "BLOCKED",
            {**summary, "status": "BLOCKED", "reason": no_mapping_code},
            no_mapping_code,
            "No exact reviewed provider mapping is available for this domain scope.",
        )
    if accepted == 0:
        return DomainOutcome(
            "FAILED",
            {**summary, "status": "FAILED", "reason": no_success_code},
            no_success_code,
            "No provider response could be normalized for this domain.",
            retryable=retryable,
        )
    if mapped < targeted or issue_count:
        return DomainOutcome(
            "PARTIAL",
            {**summary, "status": "PARTIAL"},
            "PARTIAL_COVERAGE",
            f"{issue_count} provider, identity, or quality checks remain for {domain.value}.",
            retryable=retryable,
        )
    return DomainOutcome("COMPLETE", {**summary, "status": "COMPLETE"})


def _yahoo_operation(
    session: Session,
    crosswalk_path: Any,
    *,
    start_date: date | None,
    end_date: date,
    lookback_days: int,
    corporate_action_overlap_days: int,
    listing_keys: set[tuple[str, str]] | None,
    fx_pairs: set[tuple[str, str]] | None,
) -> dict[ExternalDataDomain, DomainOutcome]:
    crosswalk = load_yahoo_crosswalk(crosswalk_path)
    provider = YahooFinanceProvider(crosswalk)
    report = asyncio.run(
        build_provider_import(
            session,
            provider=provider,
            crosswalk=crosswalk,
            end_date=end_date,
            start_date=start_date,
            lookback_days=lookback_days,
            corporate_action_overlap_days=corporate_action_overlap_days,
            listing_keys=listing_keys,
            fx_pairs=fx_pairs,
        )
    )
    plans = report.pop("plans")
    persisted = apply_provider_import(session, {**report, "plans": plans})
    return {domain: _domain_status_for_yahoo(domain, report, persisted) for domain in YAHOO_DOMAINS}


def _run_result(session: Session, claim: RunClaim) -> dict[str, Any]:
    run = session.get(ExternalIngestionRun, claim.run_id)
    if run is None:
        return {
            "domain": claim.domain.value,
            "provider_id": claim.provider_id,
            "status": "MISSING_RUN_RECORD",
            "run_id": str(claim.run_id),
        }
    return {
        "domain": claim.domain.value,
        "provider_id": claim.provider_id,
        "status": run.status,
        "run_id": str(run.id),
        "attempt_count": run.attempt_count,
        "idempotent_reuse": not claim.created,
        "failure_code": run.failure_code,
        "report": run.report,
    }


def run_scheduled(
    session: Session,
    settings: Settings,
    *,
    domains: list[ExternalDataDomain] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    replay_of_run_id: UUID | None = None,
    replay_scope: dict[str, Any] | None = None,
    fx_pair_filter: set[tuple[str, str]] | None = None,
    run_date: date | None = None,
    yahoo_crosswalk_path: Any = CROSSWALK_PATH,
) -> dict[str, Any]:
    end_date = end_date or datetime.now(UTC).date()
    run_date = run_date or datetime.now(UTC).date()
    selected = _selected_domains(domains)
    ordered = [domain for domain in DAILY_DOMAINS if domain in selected]
    states: dict[UUID, str] | None = (
        _states_from_scope(replay_scope) if replay_scope is not None else None
    )
    claims: dict[ExternalDataDomain, RunClaim] = {}
    for domain in ordered:
        if (
            domain
            in {
                ExternalDataDomain.REPORTED_FUNDAMENTALS,
                ExternalDataDomain.SOURCE_DOCUMENTS,
                ExternalDataDomain.CONSENSUS_ESTIMATES,
            }
            and states is None
        ):
            states = active_company_states(session)
        scope = (
            replay_scope
            if replay_scope is not None and replay_of_run_id is not None
            else _scope_for_domain(
                session,
                domain,
                start_date=start_date,
                end_date=end_date,
                lookback_days=lookback_days,
            )
        )
        if domain == ExternalDataDomain.FX and fx_pair_filter is not None:
            scope["required_fx_pairs"] = [list(pair) for pair in sorted(fx_pair_filter)]
        claim = _claim_run(
            session,
            PROVIDERS[domain],
            domain,
            scope,
            run_date=run_date,
            replay_nonce=replay_of_run_id,
            replay_of_run_id=replay_of_run_id,
        )
        if claim.created:
            claims[domain] = claim

    # The Yahoo adapter requests price/action and FX facts in one provider cycle,
    # then records separate run outcomes for each canonical domain.
    yahoo_claims = [
        claims[domain] for domain in ordered if domain in YAHOO_DOMAINS and domain in claims
    ]
    if yahoo_claims:
        market_claim = next(
            (claim for claim in yahoo_claims if claim.domain in YAHOO_MARKET_DOMAINS), None
        )
        fx_claim = next(
            (claim for claim in yahoo_claims if claim.domain == ExternalDataDomain.FX), None
        )
        market_scope = market_claim.request_scope if market_claim is not None else {}
        fx_scope = fx_claim.request_scope if fx_claim is not None else {}
        raw_listing_keys = market_scope.get("listing_keys", [])
        listing_keys = {
            (item["venue"].casefold(), item["ticker"].casefold())
            for item in raw_listing_keys
            if isinstance(item, dict)
            and isinstance(item.get("venue"), str)
            and isinstance(item.get("ticker"), str)
        }
        raw_fx_pairs = fx_scope.get("required_fx_pairs", [])
        fx_pairs = {
            (item[0], item[1])
            for item in raw_fx_pairs
            if isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        }
        if replay_of_run_id is not None and replay_scope is not None:
            start_value = replay_scope.get("start_date")
            end_value = replay_scope.get("end_date")
            start_date = date.fromisoformat(start_value) if start_value else None
            end_date = date.fromisoformat(end_value) if end_value else end_date
            lookback_days = int(replay_scope.get("lookback_days", lookback_days))
        corporate_action_overlap_days = int(
            market_scope.get("corporate_action_overlap_days", DEFAULT_CORPORATE_ACTION_OVERLAP_DAYS)
        )

        def yahoo_cycle() -> dict[ExternalDataDomain, DomainOutcome]:
            return _yahoo_operation(
                session,
                yahoo_crosswalk_path,
                start_date=start_date,
                end_date=end_date,
                lookback_days=lookback_days,
                corporate_action_overlap_days=corporate_action_overlap_days,
                listing_keys=listing_keys,
                fx_pairs=fx_pairs,
            )

        _execute_cycle(session, yahoo_claims, yahoo_cycle)

    for domain in ordered:
        if domain not in claims or domain in YAHOO_DOMAINS:
            continue
        claim = claims[domain]
        if states is None:
            states = active_company_states(session)
        state_snapshot = dict(states)
        mapping_ids = None
        mapping_scope = None
        if replay_scope is not None and domain in {
            ExternalDataDomain.REPORTED_FUNDAMENTALS,
            ExternalDataDomain.SOURCE_DOCUMENTS,
        }:
            raw_mapping_scope = replay_scope.get("verified_cik_mappings")
            if isinstance(raw_mapping_scope, list):
                mapping_scope = [item for item in raw_mapping_scope if isinstance(item, dict)]
        if domain == ExternalDataDomain.CONSENSUS_ESTIMATES and replay_scope is not None:
            mapping_ids = [UUID(value) for value in replay_scope.get("fmp_mapping_ids", [])] or None

        def company_cycle(
            domain: ExternalDataDomain = domain,
            state_snapshot: dict[UUID, str] = state_snapshot,
            mapping_ids: list[UUID] | None = mapping_ids,
            mapping_scope: list[dict[str, Any]] | None = mapping_scope,
        ) -> dict[ExternalDataDomain, DomainOutcome]:
            if domain == ExternalDataDomain.REPORTED_FUNDAMENTALS:
                outcome = _fundamentals_operation(
                    session, settings, state_snapshot, mapping_scope=mapping_scope
                )
            elif domain == ExternalDataDomain.SOURCE_DOCUMENTS:
                outcome = _source_documents_operation(
                    session, settings, state_snapshot, mapping_scope=mapping_scope
                )
            else:
                outcome = _consensus_operation(
                    session, settings, state_snapshot, mapping_ids=mapping_ids
                )
            return {domain: outcome}

        _execute_cycle(session, [claim], company_cycle)

    report_rows = [_run_result(session, claims[domain]) for domain in ordered if domain in claims]
    # Include previously completed same-day rows so repeated scheduling is observable and cheap.
    reused_domains = [domain for domain in ordered if domain not in claims]
    for domain in reused_domains:
        scope = (
            replay_scope
            if replay_scope is not None and replay_of_run_id is not None
            else _scope_for_domain(
                session,
                domain,
                start_date=start_date,
                end_date=end_date,
                lookback_days=lookback_days,
            )
        )
        key = _idempotency_key(PROVIDERS[domain], domain, scope, run_date, replay_of_run_id)
        existing = session.scalar(
            select(ExternalIngestionRun).where(ExternalIngestionRun.idempotency_key == key)
        )
        if existing is not None:
            report_rows.append(
                {
                    "domain": domain.value,
                    "provider_id": PROVIDERS[domain],
                    "status": existing.status,
                    "run_id": str(existing.id),
                    "attempt_count": existing.attempt_count,
                    "idempotent_reuse": True,
                    "failure_code": existing.failure_code,
                    "report": existing.report,
                }
            )
    order_index = {domain.value: index for index, domain in enumerate(DAILY_DOMAINS)}
    report_rows.sort(key=lambda item: order_index.get(item["domain"], 999))
    statuses = {row["status"] for row in report_rows}
    overall = (
        "FAILED"
        if "FAILED" in statuses
        else "BLOCKED"
        if "BLOCKED" in statuses
        else "PARTIAL"
        if "PARTIAL" in statuses or "RUNNING" in statuses
        else "COMPLETE"
    )
    return {
        "status": overall,
        "run_date": run_date.isoformat(),
        "scheduled_domains": [domain.value for domain in ordered],
        "domains": report_rows,
    }


def freshness_status(
    last_successful_at: datetime | None,
    *,
    now_at: datetime,
    max_age: timedelta,
    has_run: bool,
) -> tuple[str, float | None]:
    if last_successful_at is None:
        return ("STALE" if has_run else "UNKNOWN"), None
    age = max(0.0, (now_at - last_successful_at).total_seconds())
    return ("FRESH" if age <= max_age.total_seconds() else "STALE"), age


def status_report(session: Session, *, now_at: datetime | None = None) -> dict[str, Any]:
    now_at = now_at or datetime.now(UTC)
    domains: list[dict[str, Any]] = []
    for domain in DAILY_DOMAINS:
        provider = PROVIDERS[domain]
        latest = session.scalar(
            select(ExternalIngestionRun)
            .where(
                ExternalIngestionRun.provider_id == provider,
                ExternalIngestionRun.domain == domain.value,
            )
            .order_by(ExternalIngestionRun.created_at.desc())
            .limit(1)
        )
        last_success = session.scalar(
            select(ExternalIngestionRun)
            .where(
                ExternalIngestionRun.provider_id == provider,
                ExternalIngestionRun.domain == domain.value,
                ExternalIngestionRun.status.in_(("COMPLETE", "PARTIAL")),
                ExternalIngestionRun.last_successful_at.is_not(None),
            )
            .order_by(ExternalIngestionRun.last_successful_at.desc())
            .limit(1)
        )
        successful_at = last_success.last_successful_at if last_success else None
        freshness, age = (
            ("NOT_APPLICABLE", None)
            if latest is not None and latest.status == "NOT_APPLICABLE"
            else freshness_status(
                successful_at,
                now_at=now_at,
                max_age=FRESHNESS_MAX_AGE[domain],
                has_run=latest is not None,
            )
        )
        domains.append(
            {
                "provider_id": provider,
                "domain": domain.value,
                "cadence": "DAILY",
                "freshness_max_age_hours": FRESHNESS_MAX_AGE[domain].total_seconds() / 3600,
                "freshness": freshness,
                "last_successful_at": successful_at.isoformat() if successful_at else None,
                "last_success_age_seconds": age,
                "latest_run": (
                    {
                        "run_id": str(latest.id),
                        "status": latest.status,
                        "created_at": latest.created_at.isoformat(),
                        "finished_at": (
                            latest.finished_at.isoformat() if latest.finished_at else None
                        ),
                        "attempt_count": latest.attempt_count,
                        "failure_code": latest.failure_code,
                        "report": latest.report,
                    }
                    if latest
                    else None
                ),
            }
        )
    failed_attempts = list(
        session.scalars(
            select(ExternalIngestionAttempt)
            .where(ExternalIngestionAttempt.status.in_(("FAILED", "PARTIAL", "BLOCKED")))
            .order_by(ExternalIngestionAttempt.finished_at.desc())
            .limit(20)
        )
    )
    failures = []
    for attempt in failed_attempts:
        run = session.get(ExternalIngestionRun, attempt.run_id)
        failures.append(
            {
                "run_id": str(attempt.run_id),
                "attempt_number": attempt.attempt_number,
                "provider_id": run.provider_id if run else None,
                "domain": run.domain if run else None,
                "outcome": attempt.status,
                "failed_at": attempt.finished_at.isoformat(),
                "retryable": attempt.retryable,
                "failure_code": attempt.failure_code,
                "failure_message": attempt.failure_message,
            }
        )
    return {"generated_at": now_at.isoformat(), "domains": domains, "recent_failures": failures}


def _output_exit_code(report: dict[str, Any]) -> int:
    return {"COMPLETE": 0, "PARTIAL": 2, "BLOCKED": 2, "FAILED": 1}.get(
        str(report.get("status")), 1
    )


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run_parser = subcommands.add_parser("run", help="run today's idempotent due ingestion cycle")
    run_parser.add_argument(
        "--domain",
        choices=[domain.value for domain in DAILY_DOMAINS],
        action="append",
        help=(
            "restrict the run; market data and corporate actions share a chart cycle, "
            "while FX can run independently"
        ),
    )
    run_parser.add_argument("--start-date", type=date.fromisoformat)
    run_parser.add_argument("--end-date", type=date.fromisoformat)
    run_parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    run_parser.add_argument(
        "--fx-pair",
        action="append",
        help="limit FX ingestion to an exact reviewed BASE/QUOTE pair; repeatable",
    )
    replay_parser = subcommands.add_parser("replay", help="re-run the stored scope of one run")
    replay_parser.add_argument("run_id", type=UUID)
    status_parser = subcommands.add_parser(
        "status", help="show per-provider freshness and failures"
    )
    status_parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "run":
        end_date = args.end_date or datetime.now(UTC).date()
        if args.start_date and args.start_date > end_date:
            parser.error("--start-date must be on or before --end-date")
        if args.lookback_days < 1:
            parser.error("--lookback-days must be positive")
        try:
            fx_pair_filter = (
                {parse_fx_pair(value) for value in args.fx_pair} if args.fx_pair else None
            )
        except ValueError as error:
            parser.error(str(error))
        requested_domains = (
            {ExternalDataDomain(value) for value in args.domain} if args.domain else None
        )
        if (
            fx_pair_filter is not None
            and requested_domains is not None
            and ExternalDataDomain.FX not in requested_domains
        ):
            parser.error("--fx-pair requires FX to be among the selected domains")
    settings = Settings()
    engine = create_database_engine(settings)
    if engine is None:
        parser.error("DATABASE_URL is required for external-data operations")
    try:
        with Session(engine) as session:
            if args.command == "status":
                report = status_report(session)
                report["recent_failures"] = report["recent_failures"][: max(0, args.limit)]
            elif args.command == "run":
                domains = (
                    [ExternalDataDomain(value) for value in args.domain] if args.domain else None
                )
                report = run_scheduled(
                    session,
                    settings,
                    domains=domains,
                    start_date=args.start_date,
                    end_date=end_date,
                    lookback_days=args.lookback_days,
                    fx_pair_filter=fx_pair_filter,
                )
            else:
                original = session.get(ExternalIngestionRun, args.run_id)
                if original is None:
                    parser.error(f"Unknown external ingestion run: {args.run_id}")
                domain = ExternalDataDomain(original.domain)
                scope = original.request_scope
                start_value = scope.get("start_date") if isinstance(scope, dict) else None
                end_value = scope.get("end_date") if isinstance(scope, dict) else None
                start_date = (
                    date.fromisoformat(start_value) if isinstance(start_value, str) else None
                )
                end_date = date.fromisoformat(end_value) if isinstance(end_value, str) else None
                lookback = scope.get("lookback_days", DEFAULT_LOOKBACK_DAYS)
                report = run_scheduled(
                    session,
                    settings,
                    domains=[domain],
                    start_date=start_date,
                    end_date=end_date,
                    lookback_days=(
                        lookback if isinstance(lookback, int) else DEFAULT_LOOKBACK_DAYS
                    ),
                    replay_of_run_id=original.id,
                    replay_scope=scope if isinstance(scope, dict) else None,
                )
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error": type(error).__name__}), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return _output_exit_code(report) if args.command != "status" else 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
