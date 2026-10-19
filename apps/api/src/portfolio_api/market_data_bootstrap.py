"""Bounded, resumable bootstrap of historical prices, FX and corporate actions.

The command reuses the reviewed Yahoo crosswalk and existing provider normalizers.
It does not run as a worker and deliberately accepts only development or rehearsal
database targets.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.bootstrap_preflight import BootstrapPreflightError, verify_database_preflight
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import DatabaseWriteTargetError
from portfolio_api.domain.models import (
    Company,
    CorporateAction,
    CurrentLifecycle,
    ExternalRawPayload,
    FxObservation,
    LifecycleEvent,
    Listing,
    MarketDataBatch,
    MarketDataBootstrapCheckpoint,
    MarketDataBootstrapRun,
    PriceObservation,
    Security,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.market_data_ingestion import (
    CROSSWALK_PATH,
    active_market_listings,
    apply_provider_import,
    fx_provider_batch_plan,
    market_provider_batch_plan,
    portfolio_fx_requirements,
)
from portfolio_api.settings import REPOSITORY_PATH, Settings
from portfolio_api.yahoo_finance import (
    FX_SYMBOLS,
    YAHOO_PROVIDER_ID,
    YAHOO_SCHEMA_VERSION,
    YahooChartNormalizer,
    YahooFinanceProvider,
    YahooFxNormalizer,
    YahooListingCrosswalk,
    YahooListingMapping,
    yahoo_mapping_for_listing,
)

BOOTSTRAP_VERSION = "historical-market-bootstrap-v1"
MAX_HISTORY_DAYS = 3650
MAX_CHECKPOINTS_PER_INVOCATION = 10
DEFAULT_CHECKPOINTS_PER_INVOCATION = 5
MAX_CHECKPOINT_ATTEMPTS = 3
MIN_PROVIDER_REQUEST_INTERVAL_SECONDS = 1.0
LOCK_NAMESPACE = 1296319029  # ASCII-like namespace for the market bootstrap runner.
LOCK_KEY = 1112759376
NO_DATA_CODES = frozenset({"PROVIDER_RESULT_EMPTY", "PRICE_HISTORY_EMPTY", "FX_SERIES_EMPTY"})


class MarketDataBootstrapError(RuntimeError):
    """Safe-to-display bootstrap validation or execution failure."""


class MarketDataBootstrapExecutionError(RuntimeError):
    """A checkpoint stopped before its outcome was committed and can be resumed."""


class ProviderAdapter(Protocol):
    failures: list[Any]

    def bind_listing_ids(self, listing_ids: dict[UUID, YahooListingMapping]) -> None: ...

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_date_window(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise MarketDataBootstrapError("The start date must be on or before the end date.")
    if end_date > _now().date():
        raise MarketDataBootstrapError("The end date cannot be in the future.")
    if (end_date - start_date).days > MAX_HISTORY_DAYS:
        raise MarketDataBootstrapError(
            "A bootstrap window is limited to ten years; split older history into a separate run."
        )


def _load_crosswalk(path: Path) -> tuple[YahooListingCrosswalk, str]:
    try:
        raw = path.read_bytes()
        return YahooListingCrosswalk.model_validate_json(raw), _sha256(raw)
    except Exception:
        raise MarketDataBootstrapError(
            "The reviewed Yahoo listing crosswalk is unavailable or invalid."
        ) from None


def _lifecycle_by_company(session: Session) -> dict[UUID, str]:
    return {
        company_id: state
        for company_id, state in session.execute(
            select(LifecycleEvent.company_id, LifecycleEvent.new_state).join(
                CurrentLifecycle, CurrentLifecycle.event_id == LifecycleEvent.id
            )
        )
    }


def _listing_identity(
    listing: Listing,
    security: Security,
    company: Company | None,
    lifecycle: str | None,
) -> dict[str, Any]:
    return {
        "listing_id": str(listing.id),
        "security_id": str(security.id),
        "company_id": str(company.id) if company else None,
        "company_name": company.name if company else None,
        "lifecycle": lifecycle or ("HELD_WITHOUT_LIFECYCLE" if company else "HELD_STANDALONE"),
        "venue": listing.venue,
        "ticker": listing.ticker,
        "currency": listing.currency,
        "security_type": security.security_type,
    }


def _mapping_matches_canonical_identity(
    mapping: YahooListingMapping,
    listing: Listing,
    security: Security,
    company: Company | None,
) -> bool:
    return bool(
        mapping.verification_status == "VERIFIED"
        and (mapping.canonical_listing_id is None or mapping.canonical_listing_id == listing.id)
        and (mapping.canonical_security_id is None or mapping.canonical_security_id == security.id)
        and (
            mapping.canonical_company_id is None
            or (company is not None and mapping.canonical_company_id == company.id)
        )
    )


def _fx_scope(
    session: Session, listings: Sequence[tuple[Listing, Security, Company | None]]
) -> tuple[str | None, set[tuple[str, str]]]:
    base_currency, required = portfolio_fx_requirements(session)
    if base_currency is not None:
        required.update(
            (listing.currency, base_currency)
            for listing, _security, _company in listings
            if listing.currency and listing.currency != base_currency
        )
    return base_currency, required


def preview_market_data_bootstrap(
    session: Session,
    *,
    crosswalk: YahooListingCrosswalk,
    crosswalk_sha256: str,
    start_date: date,
    end_date: date,
    target_environment: str,
) -> dict[str, Any]:
    """Build a data-free request inventory without calling the provider or writing rows."""
    _validate_date_window(start_date, end_date)
    if target_environment not in {"development", "rehearsal"}:
        raise MarketDataBootstrapError("Historical market bootstrap is disabled for production.")
    selected, _held_ids = active_market_listings(session)
    lifecycle = _lifecycle_by_company(session)
    mapped = 0
    blocked: list[dict[str, str]] = []
    listing_rows: list[tuple[Listing, Security, Company | None]] = []
    for listing, security, company in selected:
        listing_rows.append((listing, security, company))
        mapping = yahoo_mapping_for_listing(
            crosswalk,
            venue=listing.venue,
            ticker=listing.ticker,
            currency=listing.currency,
            security_type=security.security_type,
        )
        if mapping is None or not _mapping_matches_canonical_identity(
            mapping, listing, security, company
        ):
            blocked.append(
                {
                    "subject_kind": "LISTING",
                    "subject_key": str(listing.id),
                    "code": "VERIFIED_PROVIDER_MAPPING_MISSING_OR_AMBIGUOUS",
                }
            )
        else:
            mapped += 1
    base_currency, required_fx_pairs = _fx_scope(session, listing_rows)
    fx_unmapped = sorted(pair for pair in required_fx_pairs if pair not in FX_SYMBOLS)
    return {
        "status": (
            "READY"
            if (selected or required_fx_pairs) and not blocked and not fx_unmapped
            else "BLOCKED"
        ),
        "provider_id": YAHOO_PROVIDER_ID,
        "provider_schema_version": YAHOO_SCHEMA_VERSION,
        "crosswalk_sha256": crosswalk_sha256,
        "target_environment": target_environment,
        "date_window": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "listing_scope": "canonical PORTFOLIO/WATCHLIST listings plus exact held listings",
        "selected_listing_count": len(selected),
        "verified_listing_mapping_count": mapped,
        "unresolved_listings": blocked,
        "portfolio_base_currency": base_currency,
        "required_fx_pairs": [f"{base}/{quote}" for base, quote in sorted(required_fx_pairs)],
        "allowlisted_fx_pairs": [
            f"{base}/{quote}"
            for base, quote in sorted(required_fx_pairs)
            if (base, quote) in FX_SYMBOLS
        ],
        "unmapped_fx_pairs": [f"{base}/{quote}" for base, quote in fx_unmapped],
        "provider_requests_planned": mapped + len(required_fx_pairs) - len(fx_unmapped),
        "database_writes": 0,
        "provider_requests": 0,
        "lifecycle_counts": {
            state: sum(value == state for value in lifecycle.values())
            for state in ("PORTFOLIO", "WATCHLIST")
        },
    }


def prepare_market_data_bootstrap(
    session: Session,
    *,
    crosswalk: YahooListingCrosswalk,
    crosswalk_sha256: str,
    start_date: date,
    end_date: date,
    target_environment: str,
) -> MarketDataBootstrapRun:
    """Freeze the exact identity and currency-pair scope for later bounded invocations."""
    preview = preview_market_data_bootstrap(
        session,
        crosswalk=crosswalk,
        crosswalk_sha256=crosswalk_sha256,
        start_date=start_date,
        end_date=end_date,
        target_environment=target_environment,
    )
    selected, _held_ids = active_market_listings(session)
    lifecycle = _lifecycle_by_company(session)
    run_id = uuid4()
    checkpoints: list[MarketDataBootstrapCheckpoint] = []
    listing_manifest: list[dict[str, Any]] = []
    for listing, security, company in selected:
        identity = _listing_identity(
            listing,
            security,
            company,
            lifecycle.get(company.id) if company else None,
        )
        mapping = yahoo_mapping_for_listing(
            crosswalk,
            venue=listing.venue,
            ticker=listing.ticker,
            currency=listing.currency,
            security_type=security.security_type,
        )
        valid_mapping = mapping is not None and _mapping_matches_canonical_identity(
            mapping, listing, security, company
        )
        mapping_data = mapping.model_dump(mode="json") if valid_mapping and mapping else None
        status = "PENDING" if valid_mapping else "BLOCKED"
        code = None if valid_mapping else "VERIFIED_PROVIDER_MAPPING_MISSING_OR_AMBIGUOUS"
        details = {"identity": identity, "mapping": mapping_data}
        listing_manifest.append(details)
        checkpoints.append(
            MarketDataBootstrapCheckpoint(
                id=uuid4(),
                run_id=run_id,
                subject_kind="LISTING",
                subject_key=str(listing.id),
                company_id=company.id if company else None,
                listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
                status=status,
                attempt_count=0,
                retryable=False,
                failure_code=code,
                failure_message=(
                    "No unique verified provider mapping matches the exact canonical listing."
                    if code
                    else None
                ),
                report=details,
            )
        )
    base_currency, required_fx_pairs = _fx_scope(session, selected)
    fx_manifest: list[dict[str, Any]] = []
    for base, quote in sorted(required_fx_pairs):
        supported = (base, quote) in FX_SYMBOLS
        fx_manifest.append(
            {
                "base_currency": base,
                "quote_currency": quote,
                "provider_symbol": FX_SYMBOLS.get((base, quote)),
                "allowlisted": supported,
            }
        )
        checkpoints.append(
            MarketDataBootstrapCheckpoint(
                id=uuid4(),
                run_id=run_id,
                subject_kind="FX_PAIR",
                subject_key=f"{base}/{quote}",
                base_currency=base,
                quote_currency=quote,
                start_date=start_date,
                end_date=end_date,
                status="PENDING" if supported else "BLOCKED",
                attempt_count=0,
                retryable=False,
                failure_code=None if supported else "FX_PAIR_NOT_ALLOWLISTED",
                failure_message=(
                    None
                    if supported
                    else "No reviewed provider series exists for this exact currency pair."
                ),
                report={
                    "pair": f"{base}/{quote}",
                    "provider_symbol": FX_SYMBOLS.get((base, quote)),
                },
            )
        )
    frozen_scope = {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "provider_id": YAHOO_PROVIDER_ID,
        "provider_schema_version": YAHOO_SCHEMA_VERSION,
        "price_normalizer_version": YahooChartNormalizer.version,
        "fx_normalizer_version": YahooFxNormalizer.version,
        "date_window": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "listing_scope": "canonical PORTFOLIO/WATCHLIST listings plus exact held listings",
        "base_currency": base_currency,
        "listings": listing_manifest,
        "fx_pairs": fx_manifest,
        "unmapped_fx_pairs": preview["unmapped_fx_pairs"],
    }
    digest = _sha256(
        _canonical_json(
            {
                "target_environment": target_environment,
                "crosswalk_sha256": crosswalk_sha256,
                "scope": frozen_scope,
            }
        ).encode("utf-8")
    )
    run = MarketDataBootstrapRun(
        id=run_id,
        input_digest=digest,
        provider_id=YAHOO_PROVIDER_ID,
        provider_schema_version=YAHOO_SCHEMA_VERSION,
        crosswalk_sha256=crosswalk_sha256,
        target_environment=target_environment,
        start_date=start_date,
        end_date=end_date,
        scope=frozen_scope,
        status="PREPARED",
        prepared_at=_now(),
        report={"status": "PREPARED", "preview": preview},
    )
    if not checkpoints or any(checkpoint.status == "BLOCKED" for checkpoint in checkpoints):
        run.status = "BLOCKED"
        run.finished_at = _now()
        run.report = {
            "status": "BLOCKED",
            "reason": (
                "EMPTY_BOOTSTRAP_SCOPE"
                if not checkpoints
                else "UNRESOLVED_PROVIDER_IDENTITY_OR_FX_MAPPING"
            ),
            "preview": preview,
        }
    session.add(run)
    session.flush()
    session.add_all(checkpoints)
    session.flush()
    return run


def _identity_still_matches(
    session: Session,
    checkpoint: MarketDataBootstrapCheckpoint,
    crosswalk: YahooListingCrosswalk,
) -> tuple[bool, str | None]:
    if checkpoint.subject_kind != "LISTING" or checkpoint.listing_id is None:
        return True, None
    listing = session.get(Listing, checkpoint.listing_id)
    if listing is None:
        return False, "CANONICAL_LISTING_MISSING"
    security = session.get(Security, listing.security_id)
    if security is None:
        return False, "CANONICAL_SECURITY_MISSING"
    company = session.get(Company, security.company_id) if security.company_id else None
    lifecycle = _lifecycle_by_company(session).get(company.id) if company is not None else None
    frozen_identity = checkpoint.report.get("identity")
    if not isinstance(frozen_identity, dict) or frozen_identity != _listing_identity(
        listing, security, company, lifecycle
    ):
        return False, "CANONICAL_LISTING_IDENTITY_CHANGED"
    mapping = yahoo_mapping_for_listing(
        crosswalk,
        venue=listing.venue,
        ticker=listing.ticker,
        currency=listing.currency,
        security_type=security.security_type,
    )
    frozen_mapping = checkpoint.report.get("mapping")
    if (
        mapping is None
        or not _mapping_matches_canonical_identity(mapping, listing, security, company)
        or mapping.model_dump(mode="json") != frozen_mapping
    ):
        return False, "REVIEWED_LISTING_CROSSWALK_CHANGED"
    return True, None


def _fx_pair_still_matches(
    run: MarketDataBootstrapRun,
    checkpoint: MarketDataBootstrapCheckpoint,
) -> tuple[bool, str | None]:
    pair = (checkpoint.base_currency or "", checkpoint.quote_currency or "")
    expected_symbol = FX_SYMBOLS.get(pair)
    frozen_pairs = run.scope.get("fx_pairs")
    if not isinstance(frozen_pairs, list):
        return False, "FROZEN_FX_SCOPE_INVALID"
    frozen_pair = next(
        (
            item
            for item in frozen_pairs
            if isinstance(item, dict)
            and item.get("base_currency") == pair[0]
            and item.get("quote_currency") == pair[1]
        ),
        None,
    )
    checkpoint_report = checkpoint.report if isinstance(checkpoint.report, dict) else {}
    if (
        expected_symbol is None
        or not isinstance(frozen_pair, dict)
        or frozen_pair.get("allowlisted") is not True
        or frozen_pair.get("provider_symbol") != expected_symbol
        or checkpoint_report.get("pair") != f"{pair[0]}/{pair[1]}"
        or checkpoint_report.get("provider_symbol") != expected_symbol
    ):
        return False, "FROZEN_FX_PAIR_CHANGED_OR_UNSUPPORTED"
    return True, None


def _advisory_lock(engine: Engine) -> Any:
    class Lock:
        def __init__(self, active_engine: Engine) -> None:
            self.connection = active_engine.connect()

        def __enter__(self) -> Lock:
            acquired: bool = bool(
                self.connection.execute(
                    text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
                    {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
                ).scalar_one()
            )
            self.connection.commit()
            if not acquired:
                self.connection.close()
                raise MarketDataBootstrapError(
                    "Another market-data bootstrap is running; retry after it finishes."
                )
            return self

        def __exit__(self, *_args: Any) -> None:
            try:
                self.connection.execute(
                    text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                    {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
                )
                self.connection.commit()
            finally:
                self.connection.close()

    return Lock(engine)


def _retry_delay(attempt_number: int) -> int:
    delay: int = 2 ** max(0, int(attempt_number) - 1)
    return min(30, delay)


def _query_for_checkpoint(
    checkpoint: MarketDataBootstrapCheckpoint, requested_at: datetime
) -> ProviderQuery:
    if checkpoint.subject_kind == "LISTING" and checkpoint.listing_id is not None:
        return ProviderQuery(
            domain=ExternalDataDomain.MARKET_DATA,
            subjects=(
                CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=checkpoint.listing_id),
            ),
            start_date=checkpoint.start_date,
            end_date=checkpoint.end_date,
            requested_at=requested_at,
        )
    if (
        checkpoint.subject_kind == "FX_PAIR"
        and checkpoint.base_currency
        and checkpoint.quote_currency
    ):
        return ProviderQuery(
            domain=ExternalDataDomain.FX,
            subjects=(
                CanonicalSubjectRef(
                    kind=CanonicalSubjectKind.CURRENCY_PAIR,
                    base_currency=checkpoint.base_currency,
                    quote_currency=checkpoint.quote_currency,
                ),
            ),
            start_date=checkpoint.start_date,
            end_date=checkpoint.end_date,
            requested_at=requested_at,
        )
    raise MarketDataBootstrapError("The stored checkpoint identity is invalid.")


def _temporal_issues(
    plan: dict[str, Any],
    *,
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for row in plan["prices"]:
        observed_at = row.get("observed_at")
        recorded_at = row.get("recorded_at")
        if observed_at is not None and recorded_at is not None and observed_at > recorded_at:
            issues.append(
                {"source_ref": str(row["source_ref"]), "code": "OBSERVATION_AFTER_RETRIEVAL"}
            )
        if row["price_kind"] == "DAILY_CLOSE" and not (
            start_date <= row["market_date"].date() <= end_date
        ):
            issues.append(
                {"source_ref": str(row["source_ref"]), "code": "PRICE_OUTSIDE_REQUESTED_WINDOW"}
            )
    for row in plan["fx"]:
        observed_at = row.get("observed_at")
        recorded_at = row.get("recorded_at")
        if observed_at is not None and recorded_at is not None and observed_at > recorded_at:
            issues.append(
                {"source_ref": str(row["source_ref"]), "code": "OBSERVATION_AFTER_RETRIEVAL"}
            )
        is_current_quote = row["source_ref"] in plan["report"].get("current_quote_source_refs", [])
        if not is_current_quote and not start_date <= row["effective_at"].date() <= end_date:
            issues.append(
                {"source_ref": str(row["source_ref"]), "code": "FX_OUTSIDE_REQUESTED_WINDOW"}
            )
    records = plan.get("records", [])
    retrieved_at = min((record.retrieved_at for record in records), default=None)
    for row in plan["actions"]:
        observed_at = row.get("observed_at")
        if observed_at is not None and retrieved_at is not None and observed_at > retrieved_at:
            issues.append(
                {
                    "source_action_id": str(row["source_action_id"]),
                    "code": "OBSERVATION_AFTER_RETRIEVAL",
                }
            )
        effective_date = row["effective_date"].date()
        if not start_date <= effective_date <= end_date:
            issues.append(
                {
                    "source_action_id": str(row["source_action_id"]),
                    "code": "ACTION_OUTSIDE_REQUESTED_WINDOW",
                }
            )
    return issues


def _quarantine_temporal_plan(plan: dict[str, Any], issues: list[dict[str, str]]) -> None:
    """Keep the raw response receipt but do not persist canonical rows with invalid times."""
    plan["prices"] = []
    plan["actions"] = []
    plan["fx"] = []
    plan["report"]["temporal_rejections"] = issues
    plan["report"]["accepted_subjects"] = 0
    plan["report"]["daily_price_rows"] = 0
    plan["report"]["current_quote_rows"] = 0
    plan["report"]["corporate_action_rows"] = 0
    plan["report"]["fx_observation_rows"] = 0
    rejected_key = (
        "rejected_subjects" if "rejected_subjects" in plan["report"] else "rejected_pairs"
    )
    plan["report"].setdefault(rejected_key, []).append(
        {
            "code": "TEMPORAL_ORDER_INVALID",
            "message": "The provider times failed consistency checks.",
        }
    )
    plan["batch"]["reconciliation"] = plan["report"]


def _coverage_for_plan(
    checkpoint: MarketDataBootstrapCheckpoint, plan: dict[str, Any] | None
) -> dict[str, Any]:
    if plan is None:
        return {
            "price_status": "UNAVAILABLE" if checkpoint.subject_kind == "LISTING" else None,
            "action_status": "UNAVAILABLE" if checkpoint.subject_kind == "LISTING" else None,
            "fx_status": "UNAVAILABLE" if checkpoint.subject_kind == "FX_PAIR" else None,
            "daily_price_rows": 0,
            "current_quote_rows": 0,
            "corporate_action_rows": 0,
            "fx_observation_rows": 0,
            "provider_current_quote_rows_skipped": 0,
            "earliest_effective_date": None,
            "latest_effective_date": None,
            "normalization_warnings": [],
        }
    provider_report = plan["report"]
    if checkpoint.subject_kind == "LISTING":
        item: dict[str, Any] = next(iter(provider_report.get("mapped_listings", [])), {})
        daily_rows = int(provider_report.get("daily_price_rows", 0) or 0)
        current_quote_rows = int(provider_report.get("current_quote_rows", 0) or 0)
        current_quote_rows = int(provider_report.get("current_quote_rows", 0) or 0)
        action_rows = int(provider_report.get("corporate_action_rows", 0) or 0)
        price_status = "AVAILABLE" if daily_rows else "UNAVAILABLE"
        return {
            "price_status": price_status,
            "action_status": "UNVERIFIED" if action_rows else "NO_ACTIONS_REPORTED",
            "daily_price_rows": daily_rows,
            "current_quote_rows": current_quote_rows,
            "corporate_action_rows": action_rows,
            "fx_observation_rows": 0,
            "provider_current_quote_rows_skipped": int(
                provider_report.get("provider_current_quote_rows_skipped", 0) or 0
            ),
            "earliest_effective_date": item.get("earliest_history_date"),
            "latest_effective_date": item.get("latest_history_date"),
            "normalization_warnings": provider_report.get("normalization_warnings", []),
        }
    pairs = provider_report.get("accepted_pairs", [])
    pair = pairs[0] if pairs else {}
    fx_rows = int(provider_report.get("fx_observation_rows", 0) or 0)
    return {
        "price_status": None,
        "action_status": None,
        "fx_status": "AVAILABLE" if fx_rows else "UNAVAILABLE",
        "daily_price_rows": 0,
        "current_quote_rows": 0,
        "corporate_action_rows": 0,
        "fx_observation_rows": fx_rows,
        "provider_current_quote_rows_skipped": int(
            provider_report.get("provider_current_quote_rows_skipped", 0) or 0
        ),
        "daily_fx_observation_rows": int(pair.get("daily_observation_rows", 0) or 0),
        "current_fx_quote_rows": int(pair.get("current_quote_rows", 0) or 0),
        "earliest_effective_date": pair.get("earliest_effective_at"),
        "latest_effective_date": pair.get("latest_effective_at"),
        "normalization_warnings": provider_report.get("normalization_warnings", []),
    }


def _canonical_batch_counts(session: Session, batch_id: UUID) -> dict[str, int]:
    return {
        "raw_payloads": int(
            session.scalar(
                select(func.count())
                .select_from(ExternalRawPayload)
                .where(ExternalRawPayload.batch_id == batch_id)
            )
            or 0
        ),
        "price_observations": int(
            session.scalar(
                select(func.count())
                .select_from(PriceObservation)
                .where(PriceObservation.batch_id == batch_id)
            )
            or 0
        ),
        "corporate_actions": int(
            session.scalar(
                select(func.count())
                .select_from(CorporateAction)
                .where(CorporateAction.batch_id == batch_id)
            )
            or 0
        ),
        "fx_observations": int(
            session.scalar(
                select(func.count())
                .select_from(FxObservation)
                .where(FxObservation.batch_id == batch_id)
            )
            or 0
        ),
    }


def _canonical_batch_fingerprint(session: Session, batch_id: UUID) -> str:
    """Hash the exact persisted rows belonging to one provider response batch."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for model in (ExternalRawPayload, PriceObservation, CorporateAction, FxObservation):
        columns = [
            column.name
            for column in model.__table__.columns
            if not (model is ExternalRawPayload and column.name == "payload_bytes")
        ]
        rows: list[dict[str, Any]] = []
        for item in session.scalars(select(model).where(model.batch_id == batch_id)):
            rows.append({column: getattr(item, column) for column in columns})
        tables[model.__tablename__] = sorted(rows, key=lambda row: str(row.get("id", "")))
    return _sha256(_canonical_json(tables).encode("utf-8"))


def _fetch_one_checkpoint(
    session: Session,
    run: MarketDataBootstrapRun,
    checkpoint: MarketDataBootstrapCheckpoint,
    *,
    provider: ProviderAdapter,
    crosswalk: YahooListingCrosswalk,
) -> tuple[dict[str, Any] | None, dict[str, Any], list[Any]]:
    requested_at = _now()
    query = _query_for_checkpoint(checkpoint, requested_at)
    if checkpoint.subject_kind == "LISTING":
        listing = session.get(Listing, checkpoint.listing_id)
        if listing is None:
            raise MarketDataBootstrapError("The canonical listing no longer exists.")
        security = session.get(Security, listing.security_id)
        if security is None:
            raise MarketDataBootstrapError("The canonical security no longer exists.")
        identity_ok, identity_error = _identity_still_matches(session, checkpoint, crosswalk)
        if not identity_ok:
            raise MarketDataBootstrapError(identity_error or "Canonical listing identity changed.")
        mapping = YahooListingMapping.model_validate(checkpoint.report["mapping"])
        provider.bind_listing_ids({listing.id: mapping})
        records = list(asyncio.run(provider.fetch(query)))
        failures = list(provider.failures)
        normalizer = YahooChartNormalizer(
            {f"LISTING:{listing.id}": (listing.id, mapping)},
            requested_start=checkpoint.start_date,
            requested_end=checkpoint.end_date,
        )
        plans = [market_provider_batch_plan(query, records, normalizer)]
        plan = plans[0]
    else:
        provider.bind_listing_ids({})
        records = list(asyncio.run(provider.fetch(query)))
        failures = list(provider.failures)
        plan = fx_provider_batch_plan(query, records, YahooFxNormalizer())
    if plan is not None:
        report = plan["report"]
        if checkpoint.subject_kind == "LISTING":
            current_quotes = [row for row in plan["prices"] if row["price_kind"] == "CURRENT_QUOTE"]
            plan["prices"] = [row for row in plan["prices"] if row["price_kind"] == "DAILY_CLOSE"]
            report["provider_current_quote_rows_skipped"] = len(current_quotes)
            report["current_quote_rows"] = 0
        else:
            current_refs = set(report.get("current_quote_source_refs", []))
            daily_fx_rows = [row for row in plan["fx"] if row["source_ref"] not in current_refs]
            skipped_quotes = len(plan["fx"]) - len(daily_fx_rows)
            plan["fx"] = daily_fx_rows
            report["provider_current_quote_rows_skipped"] = skipped_quotes
            report["fx_observation_rows"] = len(daily_fx_rows)
            for accepted_pair in report.get("accepted_pairs", []):
                pair_rows = [
                    row
                    for row in daily_fx_rows
                    if row["base_currency"] == checkpoint.base_currency
                    and row["quote_currency"] == checkpoint.quote_currency
                ]
                accepted_pair["rows"] = len(pair_rows)
                accepted_pair["daily_observation_rows"] = len(pair_rows)
                accepted_pair["current_quote_rows"] = 0
                if pair_rows:
                    accepted_pair["earliest_effective_at"] = min(
                        row["effective_at"] for row in pair_rows
                    ).isoformat()
                    accepted_pair["latest_effective_at"] = max(
                        row["effective_at"] for row in pair_rows
                    ).isoformat()
        plan["batch"]["reconciliation"] = report
    return plan, {"query": query.model_dump(mode="json", exclude={"requested_at"})}, failures


def _plan_error(plan: dict[str, Any] | None, failures: list[Any]) -> tuple[str, str, bool] | None:
    if failures:
        failure = failures[0]
        return (
            str(getattr(failure, "code", "PROVIDER_REQUEST_FAILED"))[:80],
            "Provider request failed after bounded retries.",
            bool(getattr(failure, "retryable", False)),
        )
    if plan is None:
        return "PROVIDER_NO_RESPONSE", "The provider returned no response record.", False
    report = plan["report"]
    rejected_key = "rejected_subjects" if "rejected_subjects" in report else "rejected_pairs"
    rejected = report.get(rejected_key, [])
    if rejected:
        codes = {str(item.get("code", "")) for item in rejected if isinstance(item, dict)}
        if codes and codes.issubset(NO_DATA_CODES):
            return (
                "NO_PROVIDER_DATA",
                "The provider returned a valid response with no observations.",
                False,
            )
        return "NORMALIZATION_REJECTED", "Provider identity or response validation failed.", False
    return None


def _run_report(session: Session, run: MarketDataBootstrapRun) -> dict[str, Any]:
    checkpoints = list(
        session.scalars(
            select(MarketDataBootstrapCheckpoint)
            .where(MarketDataBootstrapCheckpoint.run_id == run.id)
            .order_by(
                MarketDataBootstrapCheckpoint.subject_kind,
                MarketDataBootstrapCheckpoint.subject_key,
            )
        )
    )
    statuses: dict[str, int] = defaultdict(int)
    listing_coverage: list[dict[str, Any]] = []
    fx_coverage: list[dict[str, Any]] = []
    company_rows: dict[str, dict[str, Any]] = {}
    currency_rows: dict[str, dict[str, Any]] = {}
    totals = {
        "raw_payloads": 0,
        "price_observations": 0,
        "corporate_actions": 0,
        "fx_observations": 0,
    }
    unverified_actions = 0
    unavailable_count = 0
    failed_count = 0
    blocked_count = 0
    pending_count = 0
    retryable_count = 0
    for checkpoint in checkpoints:
        statuses[checkpoint.status] += 1
        details: dict[str, Any] = (
            dict(checkpoint.report) if isinstance(checkpoint.report, dict) else {}
        )
        coverage_value = details.get("coverage")
        coverage: dict[str, Any] = dict(coverage_value) if isinstance(coverage_value, dict) else {}
        canonical_counts_value = coverage.get("canonical_counts")
        canonical_counts: dict[str, Any] = (
            dict(canonical_counts_value) if isinstance(canonical_counts_value, dict) else {}
        )
        for key in totals:
            totals[key] += int(canonical_counts.get(key, 0) or 0)
        identity_value = details.get("identity")
        identity: dict[str, Any] = dict(identity_value) if isinstance(identity_value, dict) else {}
        if checkpoint.subject_kind == "LISTING":
            mapping_value = details.get("mapping")
            provider_mapping: dict[str, Any] = (
                dict(mapping_value) if isinstance(mapping_value, dict) else {}
            )
            listing_result = {
                **identity,
                "provider_mapping": provider_mapping,
                "status": checkpoint.status,
                "failure_code": checkpoint.failure_code,
                "retryable": checkpoint.retryable,
                "requested_date_range": {
                    "start": checkpoint.start_date.isoformat(),
                    "end": checkpoint.end_date.isoformat(),
                },
                **coverage,
                "batch_id": str(checkpoint.batch_id) if checkpoint.batch_id else None,
            }
            listing_coverage.append(listing_result)
            company_id = identity.get("company_id") or "UNASSIGNED"
            company = company_rows.setdefault(
                company_id,
                {
                    "company_id": identity.get("company_id"),
                    "company_name": identity.get("company_name"),
                    "listing_count": 0,
                    "available_price_listings": 0,
                    "unavailable_price_listings": 0,
                    "current_only_price_listings": 0,
                },
            )
            company["listing_count"] += 1
            if coverage.get("price_status") == "AVAILABLE":
                company["available_price_listings"] += 1
            elif coverage.get("price_status") == "UNAVAILABLE":
                company["unavailable_price_listings"] += 1
            elif coverage.get("price_status") == "CURRENT_ONLY":
                company["current_only_price_listings"] += 1
            currency = str(identity.get("currency") or "UNKNOWN")
            currency_row = currency_rows.setdefault(
                currency,
                {"currency": currency, "listing_count": 0, "daily_price_rows": 0},
            )
            currency_row["listing_count"] += 1
            currency_row["daily_price_rows"] += int(coverage.get("daily_price_rows", 0) or 0)
            if coverage.get("action_status") == "UNVERIFIED":
                unverified_actions += int(coverage.get("corporate_action_rows", 0) or 0)
            if coverage.get("price_status") == "UNAVAILABLE":
                unavailable_count += 1
        else:
            pair = f"{checkpoint.base_currency}/{checkpoint.quote_currency}"
            fx_coverage.append(
                {
                    "base_currency": checkpoint.base_currency,
                    "quote_currency": checkpoint.quote_currency,
                    "status": checkpoint.status,
                    "fx_status": coverage.get("fx_status"),
                    "failure_code": checkpoint.failure_code,
                    "retryable": checkpoint.retryable,
                    "requested_date_range": {
                        "start": checkpoint.start_date.isoformat(),
                        "end": checkpoint.end_date.isoformat(),
                    },
                    "observation_rows": int(coverage.get("fx_observation_rows", 0) or 0),
                    "daily_observation_rows": int(
                        coverage.get("daily_fx_observation_rows", 0) or 0
                    ),
                    "current_quote_rows": int(coverage.get("current_fx_quote_rows", 0) or 0),
                    "earliest_effective_date": coverage.get("earliest_effective_date"),
                    "latest_effective_date": coverage.get("latest_effective_date"),
                    "batch_id": str(checkpoint.batch_id) if checkpoint.batch_id else None,
                    "pair": pair,
                }
            )
            currency_row = currency_rows.setdefault(
                str(checkpoint.quote_currency),
                {
                    "currency": str(checkpoint.quote_currency),
                    "listing_count": 0,
                    "daily_price_rows": 0,
                },
            )
            currency_row.setdefault("fx_pairs", []).append(pair)
            currency_row.setdefault("fx_observation_rows", 0)
            currency_row["fx_observation_rows"] += int(coverage.get("fx_observation_rows", 0) or 0)
            if coverage.get("fx_status") == "UNAVAILABLE":
                unavailable_count += 1
        if checkpoint.status == "FAILED":
            failed_count += 1
            retryable_count += int(
                checkpoint.retryable and checkpoint.attempt_count < MAX_CHECKPOINT_ATTEMPTS
            )
        if checkpoint.status == "BLOCKED":
            blocked_count += 1
        if checkpoint.status == "PENDING":
            pending_count += 1
    complete = all(checkpoint.status == "COMPLETE" for checkpoint in checkpoints)
    terminal_failure = any(
        checkpoint.status == "FAILED"
        and (not checkpoint.retryable or checkpoint.attempt_count >= MAX_CHECKPOINT_ATTEMPTS)
        for checkpoint in checkpoints
    )
    status = (
        "BLOCKED"
        if not checkpoints
        else "FAILED"
        if terminal_failure and not pending_count
        else "PARTIAL"
        if not complete or unavailable_count or failed_count or blocked_count or unverified_actions
        else "COMPLETE"
    )
    return {
        "status": status,
        "run_id": str(run.id),
        "input_digest": run.input_digest,
        "provider_id": run.provider_id,
        "provider_schema_version": run.provider_schema_version,
        "crosswalk_sha256": run.crosswalk_sha256,
        "date_window": {"start": run.start_date.isoformat(), "end": run.end_date.isoformat()},
        "target_environment": run.target_environment,
        "checkpoint_counts": dict(sorted(statuses.items())),
        "pending_checkpoints": pending_count,
        "retryable_checkpoints": retryable_count,
        "failed_checkpoints": failed_count,
        "blocked_checkpoints": blocked_count,
        "unavailable_coverages": unavailable_count,
        "unverified_corporate_actions": unverified_actions,
        "canonical_totals": totals,
        "company_coverage": sorted(
            company_rows.values(), key=lambda item: str(item["company_name"])
        ),
        "listing_coverage": listing_coverage,
        "currency_coverage": sorted(currency_rows.values(), key=lambda item: str(item["currency"])),
        "fx_coverage": fx_coverage,
    }


def _checkpoint_is_eligible(checkpoint: MarketDataBootstrapCheckpoint, at: datetime) -> bool:
    if checkpoint.status == "PENDING":
        return True
    return bool(
        checkpoint.status == "FAILED"
        and checkpoint.retryable
        and checkpoint.attempt_count < MAX_CHECKPOINT_ATTEMPTS
        and (checkpoint.next_attempt_at is None or checkpoint.next_attempt_at <= at)
    )


def _next_checkpoint(
    session: Session, run_id: UUID, at: datetime
) -> MarketDataBootstrapCheckpoint | None:
    candidates = list(
        session.scalars(
            select(MarketDataBootstrapCheckpoint)
            .where(
                MarketDataBootstrapCheckpoint.run_id == run_id,
                MarketDataBootstrapCheckpoint.status.in_(("PENDING", "FAILED")),
            )
            .order_by(
                MarketDataBootstrapCheckpoint.subject_kind,
                MarketDataBootstrapCheckpoint.subject_key,
            )
            .with_for_update(skip_locked=True)
        )
    )
    return next((item for item in candidates if _checkpoint_is_eligible(item, at)), None)


def _process_checkpoint(
    session: Session,
    run: MarketDataBootstrapRun,
    checkpoint: MarketDataBootstrapCheckpoint,
    *,
    provider: ProviderAdapter,
    crosswalk: YahooListingCrosswalk,
    min_request_interval_seconds: float,
) -> None:
    if checkpoint.status == "RUNNING":
        # The caller holds the run-level advisory lock, proving the former process ended.
        checkpoint.status = "FAILED"
        checkpoint.retryable = checkpoint.attempt_count < MAX_CHECKPOINT_ATTEMPTS
        checkpoint.failure_code = "WORKER_INTERRUPTED"
        checkpoint.failure_message = "The prior invocation ended before this checkpoint committed."
        checkpoint.next_attempt_at = _now()
    if checkpoint.status == "FAILED" and not _checkpoint_is_eligible(checkpoint, _now()):
        return
    if checkpoint.subject_kind == "LISTING":
        identity_ok, identity_error = _identity_still_matches(session, checkpoint, crosswalk)
        if not identity_ok:
            checkpoint.status = "BLOCKED"
            checkpoint.failure_code = identity_error or "CANONICAL_IDENTITY_CHANGED"
            checkpoint.failure_message = (
                "The frozen listing identity no longer matches canonical state."
            )
            checkpoint.retryable = False
            checkpoint.finished_at = _now()
            session.commit()
            return
    else:
        pair_ok, pair_error = _fx_pair_still_matches(run, checkpoint)
        if not pair_ok:
            checkpoint.status = "BLOCKED"
            checkpoint.failure_code = pair_error or "FROZEN_FX_PAIR_INVALID"
            checkpoint.failure_message = (
                "The frozen FX pair no longer matches the reviewed allowlist."
            )
            checkpoint.retryable = False
            checkpoint.finished_at = _now()
            session.commit()
            return
    checkpoint.status = "RUNNING"
    checkpoint.attempt_count += 1
    checkpoint.started_at = _now()
    checkpoint.finished_at = None
    checkpoint.failure_code = None
    checkpoint.failure_message = None
    checkpoint.next_attempt_at = None
    run.status = "RUNNING"
    run.started_at = run.started_at or checkpoint.started_at
    run.finished_at = None
    session.commit()

    # Rate-limit across this invocation and resumed invocations of this bootstrap.
    latest_request = session.scalar(
        select(func.max(MarketDataBootstrapRun.last_provider_request_at))
    )
    if latest_request is not None and min_request_interval_seconds > 0:
        remaining = min_request_interval_seconds - (_now() - latest_request).total_seconds()
        if remaining > 0:
            time.sleep(remaining)
    request_started = _now()
    run.last_provider_request_at = request_started
    session.commit()

    try:
        plan, query_report, failures = _fetch_one_checkpoint(
            session, run, checkpoint, provider=provider, crosswalk=crosswalk
        )
    except MarketDataBootstrapError as identity_error:
        checkpoint.status = "BLOCKED"
        checkpoint.failure_code = "CANONICAL_IDENTITY_CHANGED"
        checkpoint.failure_message = str(identity_error)
        checkpoint.retryable = False
        checkpoint.finished_at = _now()
        session.commit()
        return
    except Exception:
        session.rollback()
        # Leave the committed RUNNING row. The next invocation will mark it interrupted.
        raise MarketDataBootstrapExecutionError(
            "Provider processing stopped before the checkpoint could be recorded. Resume the run."
        ) from None

    plan_error = _plan_error(plan, failures)
    temporal_issues = (
        _temporal_issues(plan, start_date=checkpoint.start_date, end_date=checkpoint.end_date)
        if plan is not None
        else []
    )
    if plan is not None:
        plan["batch"]["query_scope"] = {
            **plan["batch"].get("query_scope", {}),
            "market_data_bootstrap_run_id": str(run.id),
            "market_data_bootstrap_checkpoint_id": str(checkpoint.id),
        }
        plan["report"]["query_scope"] = plan["batch"]["query_scope"]
        plan["batch"]["reconciliation"] = plan["report"]
        if temporal_issues:
            _quarantine_temporal_plan(plan, temporal_issues)
            plan_error = (
                "TEMPORAL_ORDER_INVALID",
                "Provider observation times failed consistency checks; raw bytes were retained.",
                False,
            )
    coverage = _coverage_for_plan(checkpoint, plan)
    if plan is not None:
        normalizer_report = plan["report"]
        envelope = {
            "status": "DRY_RUN",
            "provider_id": YAHOO_PROVIDER_ID,
            "market_data_batches": [normalizer_report]
            if checkpoint.subject_kind == "LISTING"
            else [],
            "fx_batches": [normalizer_report] if checkpoint.subject_kind == "FX_PAIR" else [],
            "provider_fetch_failures": [],
            "fx_fetch_failures": [],
            "unresolved_listings": [],
            "unmapped_fx_pairs": [],
            "selection_issues": [],
            "plans": [plan],
        }
        persistence = apply_provider_import(session, envelope)
        batch = session.scalar(
            select(MarketDataBatch).where(
                MarketDataBatch.source_digest == plan["batch"]["source_digest"],
                MarketDataBatch.normalizer_version == plan["batch"]["normalizer_version"],
            )
        )
        if batch is not None:
            checkpoint.batch_id = batch.id
            checkpoint.source_digest = batch.source_digest
            coverage["canonical_counts"] = _canonical_batch_counts(session, batch.id)
            coverage["canonical_fingerprint"] = _canonical_batch_fingerprint(session, batch.id)
        else:
            coverage["canonical_counts"] = {
                "raw_payloads": 0,
                "price_observations": 0,
                "corporate_actions": 0,
                "fx_observations": 0,
            }
            coverage["canonical_fingerprint"] = None
        coverage["normalization_warnings"] = normalizer_report.get("normalization_warnings", [])
        coverage["raw_response_count"] = len(plan["records"])
        coverage["source_payload_hashes"] = [record.payload_sha256 for record in plan["records"]]
        coverage["source_records"] = [
            {
                "source_record_id": record.source_record_id,
                "retrieved_at": record.retrieved_at.isoformat(),
                "payload_sha256": record.payload_sha256,
            }
            for record in plan["records"]
        ]
        coverage["batch_status"] = (
            persistence.get("persistence", {}).get("batches", [{}])[0].get("status")
        )
    else:
        coverage["canonical_counts"] = {
            "raw_payloads": 0,
            "price_observations": 0,
            "corporate_actions": 0,
            "fx_observations": 0,
        }
        coverage["canonical_fingerprint"] = None
    if plan_error is not None:
        checkpoint.status = "UNAVAILABLE" if plan_error[0] == "NO_PROVIDER_DATA" else "FAILED"
        checkpoint.failure_code = plan_error[0]
        checkpoint.failure_message = plan_error[1]
        checkpoint.retryable = plan_error[2] and checkpoint.attempt_count < MAX_CHECKPOINT_ATTEMPTS
        checkpoint.next_attempt_at = (
            _now() + timedelta(seconds=_retry_delay(checkpoint.attempt_count))
            if checkpoint.retryable
            else None
        )
    else:
        checkpoint.status = "COMPLETE"
        checkpoint.failure_code = None
        checkpoint.failure_message = None
        checkpoint.retryable = False
        checkpoint.next_attempt_at = None
    checkpoint.finished_at = _now()
    checkpoint.report = {
        **(checkpoint.report if isinstance(checkpoint.report, dict) else {}),
        "request": query_report,
        "coverage": coverage,
        "provider_failure_count": len(failures),
        "provider_failure_codes": [
            str(getattr(failure, "code", "PROVIDER_REQUEST_FAILED"))[:80] for failure in failures
        ],
        "normalization_rejections": (
            plan["report"].get("rejected_subjects", plan["report"].get("rejected_pairs", []))
            if plan is not None
            else []
        ),
        "temporal_rejections": temporal_issues,
    }
    session.commit()


def _recover_interrupted_checkpoints(session: Session, run_id: UUID) -> None:
    now_at = _now()
    for checkpoint in session.scalars(
        select(MarketDataBootstrapCheckpoint).where(
            MarketDataBootstrapCheckpoint.run_id == run_id,
            MarketDataBootstrapCheckpoint.status == "RUNNING",
        )
    ):
        checkpoint.status = "FAILED"
        checkpoint.failure_code = "WORKER_INTERRUPTED"
        checkpoint.failure_message = (
            "The prior invocation stopped before this checkpoint committed."
        )
        checkpoint.retryable = checkpoint.attempt_count < MAX_CHECKPOINT_ATTEMPTS
        checkpoint.next_attempt_at = now_at if checkpoint.retryable else None
        checkpoint.finished_at = now_at
    session.commit()


def execute_market_data_bootstrap(
    engine: Engine,
    run_id: UUID,
    *,
    crosswalk: YahooListingCrosswalk,
    crosswalk_sha256: str,
    provider: ProviderAdapter,
    max_checkpoints: int = DEFAULT_CHECKPOINTS_PER_INVOCATION,
    min_request_interval_seconds: float = MIN_PROVIDER_REQUEST_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Process at most N request checkpoints. Each checkpoint commits independently."""
    if max_checkpoints < 1 or max_checkpoints > MAX_CHECKPOINTS_PER_INVOCATION:
        raise MarketDataBootstrapError(
            f"--max-checkpoints must be between 1 and {MAX_CHECKPOINTS_PER_INVOCATION}."
        )
    with _advisory_lock(engine), Session(engine) as session:
        run = session.get(MarketDataBootstrapRun, run_id)
        if run is None:
            raise MarketDataBootstrapError("The market-data bootstrap run does not exist.")
        if run.crosswalk_sha256 != crosswalk_sha256:
            run.status = "BLOCKED"
            run.finished_at = _now()
            run.report = {
                "status": "BLOCKED",
                "failure_code": "REVIEWED_CROSSWALK_CHANGED",
                "message": "The reviewed provider crosswalk changed; prepare a new run.",
            }
            session.commit()
            return run.report
        if run.status in {"COMPLETE", "FAILED", "BLOCKED"}:
            report = _run_report(session, run)
            report["status"] = run.status
            return report
        _recover_interrupted_checkpoints(session, run.id)
        processed = 0
        while processed < max_checkpoints:
            checkpoint = _next_checkpoint(session, run.id, _now())
            if checkpoint is None:
                break
            _process_checkpoint(
                session,
                run,
                checkpoint,
                provider=provider,
                crosswalk=crosswalk,
                min_request_interval_seconds=min_request_interval_seconds,
            )
            processed += 1
        session.refresh(run)
        report = _run_report(session, run)
        run.status = report["status"]
        has_more = report["pending_checkpoints"] > 0 or report["retryable_checkpoints"] > 0
        run.finished_at = None if has_more else _now()
        run.report = report
        session.commit()
        return report


def reconcile_market_data_bootstrap(session: Session, run_id: UUID) -> dict[str, Any]:
    run = session.get(MarketDataBootstrapRun, run_id)
    if run is None:
        raise MarketDataBootstrapError("The market-data bootstrap run does not exist.")
    checkpoint_reports: list[dict[str, Any]] = []
    differences: list[dict[str, str]] = []
    for checkpoint in session.scalars(
        select(MarketDataBootstrapCheckpoint)
        .where(MarketDataBootstrapCheckpoint.run_id == run.id)
        .order_by(
            MarketDataBootstrapCheckpoint.subject_kind, MarketDataBootstrapCheckpoint.subject_key
        )
    ):
        actual: dict[str, int] | None = None
        actual_fingerprint: str | None = None
        checkpoint_details: dict[str, Any] = dict(checkpoint.report)
        coverage_value = checkpoint_details.get("coverage")
        checkpoint_coverage: dict[str, Any] = (
            dict(coverage_value) if isinstance(coverage_value, dict) else {}
        )
        expected_value = checkpoint_coverage.get("canonical_counts")
        expected: dict[str, Any] = dict(expected_value) if isinstance(expected_value, dict) else {}
        if checkpoint.batch_id is not None:
            batch = session.get(MarketDataBatch, checkpoint.batch_id)
            if batch is None:
                differences.append({"subject_key": checkpoint.subject_key, "code": "BATCH_MISSING"})
            elif batch.source_digest != checkpoint.source_digest:
                differences.append(
                    {"subject_key": checkpoint.subject_key, "code": "BATCH_DIGEST_MISMATCH"}
                )
            else:
                actual = _canonical_batch_counts(session, batch.id)
                actual_fingerprint = _canonical_batch_fingerprint(session, batch.id)
                if actual != expected:
                    differences.append(
                        {
                            "subject_key": checkpoint.subject_key,
                            "code": "CANONICAL_ROW_COUNT_MISMATCH",
                        }
                    )
                expected_fingerprint = checkpoint_coverage.get("canonical_fingerprint")
                if actual_fingerprint != expected_fingerprint:
                    differences.append(
                        {
                            "subject_key": checkpoint.subject_key,
                            "code": "CANONICAL_FINGERPRINT_MISMATCH",
                        }
                    )
                if checkpoint.subject_kind == "LISTING":
                    temporal_bad = session.scalar(
                        select(func.count())
                        .select_from(PriceObservation)
                        .where(
                            PriceObservation.batch_id == batch.id,
                            PriceObservation.observed_at.is_not(None),
                            PriceObservation.observed_at > PriceObservation.recorded_at,
                        )
                    )
                    if temporal_bad:
                        differences.append(
                            {
                                "subject_key": checkpoint.subject_key,
                                "code": "OBSERVATION_AFTER_RETRIEVAL",
                            }
                        )
        checkpoint_reports.append(
            {
                "subject_kind": checkpoint.subject_kind,
                "subject_key": checkpoint.subject_key,
                "status": checkpoint.status,
                "batch_id": str(checkpoint.batch_id) if checkpoint.batch_id else None,
                "expected_counts": expected,
                "actual_counts": actual,
                "expected_fingerprint": checkpoint_coverage.get("canonical_fingerprint"),
                "actual_fingerprint": actual_fingerprint,
                "reconciliation": (
                    "MISMATCH"
                    if any(issue["subject_key"] == checkpoint.subject_key for issue in differences)
                    else "MATCHED"
                    if checkpoint.status in {"COMPLETE", "UNAVAILABLE"}
                    else "INCOMPLETE"
                ),
            }
        )
    report = _run_report(session, run)
    checkpoint_incomplete = any(
        checkpoint.status not in {"COMPLETE", "UNAVAILABLE"}
        for checkpoint in session.scalars(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run.id
            )
        )
    )
    report["reconciliation"] = {
        "status": (
            "MISMATCH" if differences else "INCOMPLETE" if checkpoint_incomplete else "MATCHED"
        ),
        "differences": differences,
        "checkpoints": checkpoint_reports,
    }
    return report


def _validate_private_report_path(path: Path) -> None:
    absolute = path.absolute()
    resolved = path.resolve(strict=False)
    repository = REPOSITORY_PATH.resolve()
    if absolute.is_relative_to(repository) or resolved.is_relative_to(repository):
        raise MarketDataBootstrapError("Reports must be written outside the repository.")
    if path.is_symlink():
        raise MarketDataBootstrapError("The private report path cannot be a symlink.")
    if path.exists():
        raise MarketDataBootstrapError(
            "The private report file already exists; choose a new unique path."
        )


def _write_private_report(path: Path, report: dict[str, Any]) -> Path:
    _validate_private_report_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise MarketDataBootstrapError("The private report could not be written.") from None
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "prepare"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--start-date", type=date.fromisoformat, required=True)
        subparser.add_argument("--end-date", type=date.fromisoformat, required=True)
        subparser.add_argument(
            "--target-environment", choices=("development", "rehearsal"), required=True
        )
        subparser.add_argument("--report", type=Path)
    for command in ("run", "resume", "status", "reconcile"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--run-id", type=UUID, required=True)
        subparser.add_argument(
            "--target-environment", choices=("development", "rehearsal"), required=True
        )
        subparser.add_argument("--report", type=Path)
        if command in {"run", "resume"}:
            subparser.add_argument(
                "--max-checkpoints",
                type=int,
                default=DEFAULT_CHECKPOINTS_PER_INVOCATION,
            )
    return parser


def _verify_target(engine: Engine, settings: Settings, requested_environment: str) -> None:
    verify_database_preflight(
        engine,
        configured_target_environment=settings.database_target_environment,
        requested_target_environment=requested_environment,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings: Settings
    engine: Engine | None = None
    try:
        if args.report:
            _validate_private_report_path(args.report)
        settings = Settings()
        if settings.database_url is None:
            raise MarketDataBootstrapError("DATABASE_URL is required for target verification.")
        engine = create_database_engine(
            settings,
            write_operation=f"market_data_bootstrap.{args.command}",
            write_operation_kind="ingestion",
        )
        if engine is None:
            raise MarketDataBootstrapError("DATABASE_URL is required for target verification.")
        _verify_target(engine, settings, args.target_environment)
        crosswalk, crosswalk_sha256 = _load_crosswalk(CROSSWALK_PATH)
        with Session(engine) as session:
            if args.command == "preview":
                report = preview_market_data_bootstrap(
                    session,
                    crosswalk=crosswalk,
                    crosswalk_sha256=crosswalk_sha256,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    target_environment=args.target_environment,
                )
            elif args.command == "prepare":
                with session.begin():
                    prepared_run = prepare_market_data_bootstrap(
                        session,
                        crosswalk=crosswalk,
                        crosswalk_sha256=crosswalk_sha256,
                        start_date=args.start_date,
                        end_date=args.end_date,
                        target_environment=args.target_environment,
                    )
                report = _run_report(session, prepared_run)
                report["status"] = prepared_run.status
            elif args.command in {"run", "resume"}:
                report = execute_market_data_bootstrap(
                    engine,
                    args.run_id,
                    crosswalk=crosswalk,
                    crosswalk_sha256=crosswalk_sha256,
                    provider=YahooFinanceProvider(crosswalk, concurrency=1, retries=3),
                    max_checkpoints=args.max_checkpoints,
                )
            elif args.command == "status":
                status_run = session.get(MarketDataBootstrapRun, args.run_id)
                if status_run is None:
                    raise MarketDataBootstrapError("The market-data bootstrap run does not exist.")
                report = _run_report(session, status_run)
            else:
                report = reconcile_market_data_bootstrap(session, args.run_id)
        if args.report:
            _write_private_report(args.report, report)
        print(
            json.dumps(
                {
                    "status": report.get("status", "FAILED"),
                    "run_id": report.get("run_id"),
                    "checkpoint_counts": report.get("checkpoint_counts", {}),
                    "report_saved": bool(args.report),
                },
                sort_keys=True,
            )
        )
        command_succeeded = report.get("status") in {
            "READY",
            "PREPARED",
            "COMPLETE",
            "MATCHED",
        }
        if args.command == "reconcile":
            reconciliation = report.get("reconciliation")
            command_succeeded = (
                isinstance(reconciliation, dict) and reconciliation.get("status") == "MATCHED"
            )
        return 0 if command_succeeded else 2
    except MarketDataBootstrapExecutionError:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error": "checkpoint_interrupted_resume_same_run",
                }
            ),
            file=sys.stderr,
        )
        return 1
    except (MarketDataBootstrapError, BootstrapPreflightError, DatabaseWriteTargetError):
        print(
            json.dumps({"status": "BLOCKED", "error": "target_or_source_validation_failed"}),
            file=sys.stderr,
        )
        return 2
    except Exception:
        print(
            json.dumps({"status": "FAILED", "error": "market_data_bootstrap_failed"}),
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
