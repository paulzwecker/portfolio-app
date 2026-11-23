"""One-shot, bounded market refresh launched beside the local development servers."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import MutableMapping
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import CLOUD_MARKET_WRITE_OPERATION
from portfolio_api.domain.models import (
    ExternalIngestionRun,
    FinancialModel,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    PriceObservation,
)
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import (
    CLOUD_RETRY_COOLDOWN,
    MAX_ATTEMPTS,
    record_cloud_market_preflight,
    resolve_cloud_market_preflights,
    run_scheduled,
)
from portfolio_api.health import check_readiness
from portfolio_api.market_data_bootstrap import (
    MarketDataBootstrapError,
    _load_crosswalk,
    preview_market_data_bootstrap,
)
from portfolio_api.market_data_ingestion import (
    CROSSWALK_PATH,
    DEFAULT_LOOKBACK_DAYS,
    active_market_listings,
    portfolio_fx_requirements,
)
from portfolio_api.migrations import expected_heads
from portfolio_api.networking import bypass_known_local_port_nine_proxy
from portfolio_api.settings import REPOSITORY_PATH, Settings
from portfolio_api.yahoo_finance import (
    DEFAULT_YAHOO_RETRIES,
    FX_SYMBOLS,
    load_yahoo_crosswalk,
    yahoo_mapping_for_listing,
)

ADVISORY_LOCK_NAMESPACE = 1_347_906_132
ADVISORY_LOCK_KEY = 1_397_962_051
FRESH_MARKET_DAYS = 5
FRESH_RUN_HOURS = 72
FRESH_ACTION_DAYS = 7
DEFAULT_READY_WAIT_SECONDS = 180
DEFAULT_READY_POLL_SECONDS = 3
DEFAULT_RETRY_WAIT_SECONDS = 60
CLOUD_CORRECTION_DAYS = 90
CLOUD_MAX_SUBJECTS = 30


def run_cloud_incremental_refresh(
    session: Session,
    settings: Settings,
    at: datetime,
    *,
    company_id: UUID | None = None,
    portfolio_id: UUID | None = None,
    refresh_slot: str | None = None,
    history_start: date | None = None,
    include_fx: bool = True,
) -> dict[str, object]:
    """Freeze and bound the existing scheduled importer to the reviewed market scope."""
    if settings.database_target_environment is None:
        return {
            "status": "BLOCKED",
            "phase": "PREFLIGHT",
            "failure_code": "EXPLICIT_TARGET_REQUIRED",
        }
    if at.tzinfo is None or at.utcoffset() is None:
        return {
            "status": "BLOCKED",
            "phase": "PREFLIGHT",
            "failure_code": "TIMEZONE_AWARE_CUTOFF_REQUIRED",
        }
    if session.in_transaction():
        return {
            "status": "BLOCKED",
            "phase": "PREFLIGHT",
            "failure_code": "CLEAN_REFRESH_TRANSACTION_REQUIRED",
        }
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    crosswalk, digest = _load_crosswalk(CROSSWALK_PATH)
    end = at.astimezone(UTC).date()
    if history_start is not None and company_id is None:
        raise MarketDataBootstrapError("A historical market refresh requires a single company.")
    start = history_start or end - timedelta(days=CLOUD_CORRECTION_DAYS - 1)
    window_days = (end - start).days + 1
    if portfolio_id is not None:
        if company_id is not None or history_start is not None:
            raise MarketDataBootstrapError(
                "Holdings close cannot be combined with company scope or backfill."
            )
        snapshot = session.scalar(
            select(HoldingSnapshot)
            .where(
                HoldingSnapshot.portfolio_id == portfolio_id,
                HoldingSnapshot.effective_at <= at,
                HoldingSnapshot.recorded_at <= at,
            )
            .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
            .limit(1)
        )
        if snapshot is None or snapshot.completeness != "COMPLETE":
            return {
                "status": "BLOCKED",
                "phase": "PREFLIGHT",
                "failure_code": "COMPLETE_SNAPSHOT_REQUIRED",
            }
        positions = session.execute(
            select(HoldingPosition.listing_id, HoldingPosition.quantity).where(
                HoldingPosition.snapshot_id == snapshot.id
            )
        ).all()
        if any(quantity is None for _, quantity in positions):
            return {
                "status": "BLOCKED",
                "phase": "PREFLIGHT",
                "failure_code": "UNKNOWN_HELD_QUANTITY",
            }
        listing_ids = {
            listing_id
            for listing_id, quantity in positions
            if quantity is not None and quantity > 0
        }
        if not listing_ids:
            return {"status": "NOT_APPLICABLE", "phase": "PREFLIGHT_EMPTY"}
    else:
        models = select(FinancialModel.valuation_listing_id).where(
            FinancialModel.current_revision_id.is_not(None)
        )
        if company_id is not None:
            models = models.where(FinancialModel.company_id == company_id)
        listing_ids = set(session.scalars(models))
    company_scope = {company_id} if company_id is not None else None
    preview = preview_market_data_bootstrap(
        session,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        start_date=start,
        end_date=end,
        target_environment=settings.database_target_environment,
        company_id=company_id,
        include_listing_ids=listing_ids,
        exact_price_scope=portfolio_id is not None,
    )
    if preview["status"] != "READY":
        return {
            "status": "BLOCKED",
            "phase": "PREFLIGHT",
            "failure_code": "MARKET_SCOPE_REVIEW_REQUIRED",
            "preview": preview,
        }
    listing_rows, _held = active_market_listings(
        session, company_scope, include_listing_ids=listing_ids
    )
    if portfolio_id is not None:
        listing_rows = [row for row in listing_rows if row[0].id in listing_ids]
    listing_keys = {(listing.venue, listing.ticker) for listing, _, _ in listing_rows}
    if len({(venue.casefold(), ticker.casefold()) for venue, ticker in listing_keys}) != len(
        listing_rows
    ):
        return {
            "status": "BLOCKED",
            "phase": "PREFLIGHT",
            "failure_code": "AMBIGUOUS_CANONICAL_LISTING_KEYS",
        }
    pairs = {tuple(pair.split("/")) for pair in preview["required_fx_pairs"]}
    if not include_fx or history_start is not None:
        pairs.clear()
    subject_count = len(listing_keys) + len(pairs)
    if subject_count > CLOUD_MAX_SUBJECTS:
        return {
            "status": "BLOCKED",
            "phase": "PREFLIGHT",
            "failure_code": "MARKET_SCOPE_BUDGET_EXCEEDED",
            "subject_count": subject_count,
            "maximum_subjects": CLOUD_MAX_SUBJECTS,
        }
    if subject_count == 0:
        return {"status": "NOT_APPLICABLE", "phase": "PREFLIGHT_EMPTY"}
    domains = [ExternalDataDomain.MARKET_DATA] if listing_keys else []
    if pairs:
        domains.append(ExternalDataDomain.FX)
    result = run_scheduled(
        session,
        settings,
        domains=domains,
        start_date=start,
        end_date=end,
        lookback_days=window_days,
        run_date=end,
        listing_key_filter=listing_keys,
        company_ids=company_scope,
        market_refresh_slot=refresh_slot,
        frozen_listing_ids={listing.id for listing, _, _ in listing_rows},
        fx_pair_filter=pairs,
        frozen_yahoo_crosswalk=(crosswalk, digest),
        retry_failed=True,
    )
    return {
        **result,
        "phase": "INGESTION",
        "scope_version": (
            "cloud-market-history-v1" if history_start else "cloud-market-correction-v1"
        ),
        "subject_count": subject_count,
        "maximum_subjects": CLOUD_MAX_SUBJECTS,
        "correction_days": window_days,
        "provider_http_attempt_upper_bound": subject_count * (DEFAULT_YAHOO_RETRIES + 1),
        "maximum_attempts_per_domain": MAX_ATTEMPTS,
        "retry_cooldown_seconds": int(CLOUD_RETRY_COOLDOWN.total_seconds()),
    }


def configure_yahoo_no_proxy(environment: MutableMapping[str, str] | None = None) -> bool:
    """Bypass only the known local port-9 development proxy for Yahoo chart hosts.

    Other proxy configurations, including corporate proxies, remain untouched.
    Operators can also set the normal NO_PROXY variables themselves when direct
    access to Yahoo has been approved for the development machine.
    """

    return bypass_known_local_port_nine_proxy(
        ("query1.finance.yahoo.com", "query2.finance.yahoo.com"), environment
    )


def _latest_run(session: Session, domain: str) -> ExternalIngestionRun | None:
    return session.scalar(
        select(ExternalIngestionRun)
        .where(
            ExternalIngestionRun.provider_id == "YAHOO_FINANCE",
            ExternalIngestionRun.domain == domain,
            ExternalIngestionRun.report["preflight_resolved_at"].as_string().is_(None),
        )
        .order_by(
            func.coalesce(
                ExternalIngestionRun.last_attempt_started_at, ExternalIngestionRun.started_at
            ).desc(),
            ExternalIngestionRun.created_at.desc(),
            ExternalIngestionRun.id.desc(),
        )
        .limit(1)
    )


def market_refresh_due(session: Session, settings: Settings, at: datetime) -> tuple[bool, str]:
    """Check exact active-listing history, quotes, FX and operational freshness."""

    listings, _held = active_market_listings(session)
    if not listings:
        return False, "No active or held listing identities are available."
    crosswalk = load_yahoo_crosswalk(
        REPOSITORY_PATH / "reference" / "market-data" / "providers" / "yahoo-listings.json"
    )
    base_currency, required_pairs = portfolio_fx_requirements(session)
    if base_currency:
        required_pairs.update(
            (listing.currency, base_currency)
            for listing, _security, _company in listings
            if listing.currency and listing.currency != base_currency
        )
    if ("TWD", "EUR") in FX_SYMBOLS:
        required_pairs.add(("TWD", "EUR"))

    market_cutoff = at.date() - timedelta(days=FRESH_MARKET_DAYS)
    mapped_count = 0
    for listing, security, _company in listings:
        mapping = yahoo_mapping_for_listing(
            crosswalk,
            venue=listing.venue,
            ticker=listing.ticker,
            currency=listing.currency,
            security_type=security.security_type,
        )
        if mapping is None:
            continue
        mapped_count += 1
        history_count, latest_history = session.execute(
            select(
                func.count(func.distinct(PriceObservation.market_date)),
                func.max(PriceObservation.market_date),
            ).where(
                PriceObservation.listing_id == listing.id,
                PriceObservation.provider == "YAHOO_FINANCE",
                PriceObservation.price_kind == "DAILY_CLOSE",
                PriceObservation.data_quality.in_(("PASS", "PASS_VERIFIED_FALLBACK")),
                PriceObservation.split_adjusted_close.is_not(None),
            )
        ).one()
        if history_count < 252 or latest_history is None or latest_history.date() < market_cutoff:
            return True, (
                f"Historical price coverage needs refresh for {listing.venue}:{listing.ticker}."
            )
        latest_quote = session.scalar(
            select(PriceObservation)
            .where(
                PriceObservation.listing_id == listing.id,
                PriceObservation.provider == "YAHOO_FINANCE",
                PriceObservation.price_kind == "CURRENT_QUOTE",
                PriceObservation.data_quality.in_(("PASS", "PASS_VERIFIED_FALLBACK")),
                PriceObservation.split_adjusted_close.is_not(None),
            )
            .order_by(PriceObservation.market_date.desc(), PriceObservation.recorded_at.desc())
            .limit(1)
        )
        if latest_quote is None or latest_quote.market_date.date() < market_cutoff:
            return True, f"Current quote is missing or stale for {listing.venue}:{listing.ticker}."

    if mapped_count == 0:
        return False, "No active listing has a reviewed Yahoo mapping."
    for base, quote in sorted(required_pairs):
        latest_fx = session.scalar(
            select(FxObservation)
            .where(
                FxObservation.provider == "YAHOO_FINANCE",
                FxObservation.base_currency == base,
                FxObservation.quote_currency == quote,
                FxObservation.data_quality == "PASS",
            )
            .order_by(FxObservation.effective_at.desc(), FxObservation.recorded_at.desc())
            .limit(1)
        )
        if latest_fx is None or latest_fx.effective_at.date() < market_cutoff:
            return True, f"Dated FX coverage needs refresh for {base}/{quote}."

    market_run = _latest_run(session, "MARKET_DATA")
    fx_run = _latest_run(session, "FX")
    for run, label in ((market_run, "market"), (fx_run, "FX")):
        if run is None or run.last_successful_at is None:
            return True, f"No successful {label} ingestion run is recorded."
        if at - run.last_successful_at > timedelta(hours=FRESH_RUN_HOURS):
            return True, f"The last successful {label} ingestion run is older than 72 hours."
    action_run = _latest_run(session, "CORPORATE_ACTIONS")
    if (
        action_run is None
        or action_run.last_successful_at is None
        or at - action_run.last_successful_at > timedelta(days=FRESH_ACTION_DAYS)
    ):
        return True, "Corporate-action source checks are due."
    return False, "Canonical prices, FX and ingestion runs are current."


def wait_for_database(engine: Engine, timeout_seconds: int, poll_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    heads = expected_heads()
    while time.monotonic() < deadline:
        status = check_readiness(engine, heads)
        if status.status == "ok":
            return True
        time.sleep(poll_seconds)
    return False


def run_startup_refresh(
    settings: Settings,
    *,
    ready_wait_seconds: int = DEFAULT_READY_WAIT_SECONDS,
    ready_poll_seconds: int = DEFAULT_READY_POLL_SECONDS,
    allow_local_proxy_bypass: bool = True,
    cloud_incremental: bool = False,
    company_id: UUID | None = None,
    portfolio_id: UUID | None = None,
    refresh_slot: str | None = None,
    history_start: date | None = None,
) -> dict[str, object]:
    engine = create_database_engine(
        settings,
        write_operation=CLOUD_MARKET_WRITE_OPERATION
        if cloud_incremental
        else "market_data_startup_ingestion",
        write_operation_kind="ingestion",
    )
    if engine is None:
        return {"status": "BLOCKED", "reason": "DATABASE_URL is not configured."}
    started = datetime.now(UTC)
    try:
        if not wait_for_database(engine, ready_wait_seconds, ready_poll_seconds):
            return {
                "status": "BLOCKED",
                "reason": "Database or Alembic schema did not become ready before timeout.",
                "wait_seconds": ready_wait_seconds,
            }
        bypassed = configure_yahoo_no_proxy() if allow_local_proxy_bypass else False
        with engine.connect() as connection:
            lock_acquired: bool = connection.execute(
                text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
                {"namespace": ADVISORY_LOCK_NAMESPACE, "lock_key": ADVISORY_LOCK_KEY},
            ).scalar_one()
            if not lock_acquired:
                return {"status": "SKIPPED", "reason": "Another startup market refresh is active."}
            # Release SQLAlchemy's transaction used to acquire the session-scoped
            # PostgreSQL lock. The lock survives COMMIT; the ingestion Session can
            # then commit canonical batches and run records normally.
            connection.commit()
            try:
                with Session(bind=connection) as session:
                    if cloud_incremental:
                        checked_at = datetime.now(UTC)
                        try:
                            report = run_cloud_incremental_refresh(
                                session,
                                settings,
                                checked_at,
                                company_id=company_id,
                                portfolio_id=portfolio_id,
                                refresh_slot=refresh_slot,
                                history_start=history_start,
                            )
                        except MarketDataBootstrapError:
                            report = {
                                "status": "BLOCKED",
                                "phase": "PREFLIGHT",
                                "failure_code": "MARKET_SOURCE_INVALID",
                            }
                        if portfolio_id is None and report.get("phase") == "PREFLIGHT":
                            session.rollback()
                            diagnostic = record_cloud_market_preflight(
                                session, report, checked_at, company_id=company_id
                            )
                            report["preflight_run_id"] = diagnostic["run_id"]
                        elif portfolio_id is None and report.get("phase") == "INGESTION":
                            resolve_cloud_market_preflights(
                                session, checked_at, company_id=company_id
                            )
                        return {
                            "status": report["status"],
                            "failure_code": report.get("failure_code"),
                            "proxy_bypass_applied": bypassed,
                            "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
                            "report": report,
                        }
                    due, reason = market_refresh_due(session, settings, datetime.now(UTC))
                    if not due:
                        return {
                            "status": "SKIPPED",
                            "reason": reason,
                            "proxy_bypass_applied": bypassed,
                            "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
                        }
                    report = run_scheduled(
                        session,
                        settings,
                        domains=[ExternalDataDomain.MARKET_DATA, ExternalDataDomain.FX],
                        lookback_days=DEFAULT_LOOKBACK_DAYS,
                    )
                    return {
                        "status": report.get("status", "UNKNOWN"),
                        "reason": reason,
                        "proxy_bypass_applied": bypassed,
                        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
                        "report": report,
                    }
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                    {"namespace": ADVISORY_LOCK_NAMESPACE, "lock_key": ADVISORY_LOCK_KEY},
                )
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one readiness check and refresh attempt, then exit",
    )
    args = parser.parse_args(argv)
    settings = Settings()
    while True:
        try:
            report = run_startup_refresh(settings)
        except Exception as error:
            # Market refresh is operationally independent; an outage must not
            # prevent the API and web development servers from staying available.
            report = {"status": "FAILED", "reason": type(error).__name__}
        print(json.dumps(report, indent=2, sort_keys=True, default=str), flush=True)
        if args.once:
            return 0
        if report.get("status") == "BLOCKED":
            time.sleep(DEFAULT_RETRY_WAIT_SECONDS)
            continue
        now_utc = datetime.now(UTC)
        next_run = datetime.combine(now_utc.date() + timedelta(days=1), datetime.min.time(), UTC)
        # Start shortly after UTC day rollover so daily run keys stay stable.
        next_run += timedelta(minutes=5)
        time.sleep(max(DEFAULT_RETRY_WAIT_SECONDS, (next_run - now_utc).total_seconds()))


if __name__ == "__main__":
    raise SystemExit(main())
