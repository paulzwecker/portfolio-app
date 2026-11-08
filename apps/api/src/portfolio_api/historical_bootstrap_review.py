"""Bounded read-only review of dates in the latest historical bootstrap batch."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Listing,
    MarketDataBatch,
    MarketDataBootstrapCheckpoint,
    MarketDataBootstrapRun,
    PriceObservation,
)
from portfolio_api.market_sessions import scheduled_session_review

MAX_LISTINGS = 30
MAX_DAILY_TIMESTAMPS = 366


def latest_historical_bootstrap_review(
    session: Session,
    *,
    checked_at: datetime | None = None,
    run_id: UUID | None = None,
    offset: int = 0,
) -> s.HistoricalBootstrapReviewRead:
    """Review stored batch dates, without reconciling payloads or changing receipts."""
    if offset < 0 or offset > 10000 or (offset and run_id is None):
        raise ValueError("Invalid page")
    at = checked_at or datetime.now(UTC)
    query = select(MarketDataBootstrapRun).where(MarketDataBootstrapRun.prepared_at <= at)
    if run_id is not None:
        query = query.where(MarketDataBootstrapRun.id == run_id)
    run = session.scalar(
        query.order_by(
            MarketDataBootstrapRun.prepared_at.desc(), MarketDataBootstrapRun.id.desc()
        ).limit(1)
    )
    if run is None:
        if run_id is not None:
            raise LookupError("Run unavailable")
        return s.HistoricalBootstrapReviewRead(
            run_id=None,
            run_status=None,
            prepared_at=None,
            requested_start=None,
            requested_end=None,
            checked_at=at,
            listing_count=0,
            fx_checkpoint_count=0,
            offset=0,
            omitted_listing_count=0,
            listings=[],
        )
    counts = dict(
        session.execute(
            select(MarketDataBootstrapCheckpoint.subject_kind, func.count())
            .where(MarketDataBootstrapCheckpoint.run_id == run.id)
            .group_by(MarketDataBootstrapCheckpoint.subject_kind)
        ).all()
    )
    listing_count = int(counts.get("LISTING", 0))
    if offset and offset >= listing_count:
        raise ValueError("Page outside run")
    checkpoints = session.scalars(
        select(MarketDataBootstrapCheckpoint)
        .where(
            MarketDataBootstrapCheckpoint.run_id == run.id,
            MarketDataBootstrapCheckpoint.subject_kind == "LISTING",
        )
        .order_by(MarketDataBootstrapCheckpoint.subject_key, MarketDataBootstrapCheckpoint.id)
        .offset(offset)
        .limit(MAX_LISTINGS)
    ).all()
    rows = [_listing_review(session, run, checkpoint, at) for checkpoint in checkpoints]
    return s.HistoricalBootstrapReviewRead(
        run_id=run.id,
        run_status=run.status,
        prepared_at=run.prepared_at,
        requested_start=run.start_date,
        requested_end=run.end_date,
        checked_at=at,
        listing_count=listing_count,
        fx_checkpoint_count=int(counts.get("FX_PAIR", 0)),
        offset=offset,
        omitted_listing_count=max(0, listing_count - offset - len(rows)),
        listings=rows,
    )


def _listing_review(
    session: Session,
    run: MarketDataBootstrapRun,
    checkpoint: MarketDataBootstrapCheckpoint,
    at: datetime,
) -> s.HistoricalBootstrapListingReviewRead:
    def recorded_diagnostics() -> s.HistoricalBootstrapCheckpointDiagnosticsRead:
        report = checkpoint.report if isinstance(checkpoint.report, dict) else {}
        coverage = report.get("coverage")
        coverage = coverage if isinstance(coverage, dict) else {}

        def count(value: object) -> int | None:
            return value if type(value) is int and 0 <= value <= 1000000 else None

        raw_count = count(coverage.get("raw_response_count"))
        warnings = coverage.get("normalization_warnings")
        rejections = report.get("normalization_rejections")
        return s.HistoricalBootstrapCheckpointDiagnosticsRead(
            failure_kind=(
                "NO_PROVIDER_DATA"
                if checkpoint.failure_code == "NO_PROVIDER_DATA"
                else "OTHER"
                if checkpoint.failure_code
                else "NONE"
            ),
            raw_response_count=raw_count,
            normalized_daily_rows=count(coverage.get("daily_price_rows"))
            if raw_count is not None
            else None,
            provider_failure_count=count(report.get("provider_failure_count")),
            normalization_rejection_count=count(len(rejections))
            if isinstance(rejections, list)
            else None,
            normalization_warning_count=count(len(warnings))
            if coverage.get("normalization_warnings_captured") is True
            and isinstance(warnings, list)
            else None,
            retryable=checkpoint.retryable,
        )

    def result(
        reason: str,
        review: s.ScheduledSessionReviewRead | None = None,
        window_review: s.ScheduledSessionReviewRead | None = None,
        diagnostics: s.HistoricalBootstrapCheckpointDiagnosticsRead | None = None,
    ) -> s.HistoricalBootstrapListingReviewRead:
        return s.HistoricalBootstrapListingReviewRead.model_validate(
            {
                "subject_key": checkpoint.subject_key,
                "checkpoint_status": checkpoint.status,
                "reason": reason,
                "scheduled_session_review": review,
                "requested_window_review": window_review,
                "checkpoint_diagnostics": diagnostics,
            }
        )

    if checkpoint.finished_at is None or checkpoint.finished_at > at:
        return result("CHECKPOINT_NOT_COMPLETE")
    if checkpoint.status in {"UNAVAILABLE", "FAILED", "BLOCKED"}:
        return result(f"CHECKPOINT_{checkpoint.status}", diagnostics=recorded_diagnostics())
    if checkpoint.status != "COMPLETE":
        return result("CHECKPOINT_NOT_COMPLETE")
    identity = checkpoint.report.get("identity") if isinstance(checkpoint.report, dict) else None
    listing = session.get(Listing, checkpoint.listing_id) if checkpoint.listing_id else None
    if (
        not isinstance(identity, dict)
        or listing is None
        or any(
            (
                identity.get("listing_id") != str(listing.id),
                identity.get("security_id") != str(listing.security_id),
                identity.get("venue") != listing.venue,
                identity.get("ticker") != listing.ticker,
                identity.get("currency") != listing.currency,
            )
        )
    ):
        return result("IDENTITY_CHANGED")
    if not listing.currency:
        return result("LISTING_CURRENCY_UNAVAILABLE")
    batch = session.get(MarketDataBatch, checkpoint.batch_id) if checkpoint.batch_id else None
    if (
        batch is None
        or not checkpoint.source_digest
        or any(
            (
                batch.source_kind != "PROVIDER_RESPONSE",
                batch.source_digest != checkpoint.source_digest,
                batch.provider_id != run.provider_id,
                batch.recorded_at > at,
            )
        )
    ):
        return result("BATCH_UNVERIFIED")
    start = max(checkpoint.start_date, date(2026, 1, 1))
    end = min(checkpoint.end_date, date(2026, 12, 31))
    if start > end:
        return result("NO_SCHEDULE")
    first = datetime.combine(start, time.min, UTC)
    after = datetime.combine(end + timedelta(days=1), time.min, UTC)
    timestamps = session.scalars(
        select(PriceObservation.market_date)
        .where(
            PriceObservation.listing_id == listing.id,
            PriceObservation.batch_id == batch.id,
            PriceObservation.provider == run.provider_id,
            PriceObservation.currency == listing.currency,
            PriceObservation.price_kind == "DAILY_CLOSE",
            PriceObservation.data_quality.in_(("PASS", "PASS_VERIFIED_FALLBACK")),
            PriceObservation.split_adjusted_close.is_not(None),
            PriceObservation.recorded_at <= at,
            or_(PriceObservation.observed_at.is_(None), PriceObservation.observed_at <= at),
            PriceObservation.market_date >= first,
            PriceObservation.market_date < after,
        )
        .distinct()
        .order_by(PriceObservation.market_date)
        .limit(MAX_DAILY_TIMESTAMPS + 1)
    ).all()
    if len(timestamps) > MAX_DAILY_TIMESTAMPS:
        return result("DATE_LIMIT_EXCEEDED")
    if not timestamps:
        return result("NO_DAILY_CLOSES", diagnostics=recorded_diagnostics())
    dates = [value.astimezone(UTC).date() for value in timestamps]
    review = scheduled_session_review(listing.venue, dates, at)
    window = scheduled_session_review(
        listing.venue, dates, at, window_start=checkpoint.start_date, window_end=checkpoint.end_date
    )
    return result("AVAILABLE", review, window) if review else result("NO_SCHEDULE")
