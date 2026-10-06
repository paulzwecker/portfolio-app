"""Point-in-time comparison of native revenue forecasts with estimates, actuals and prices."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from portfolio_api.domain import queries
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    ConsensusEstimateMetric,
    ConsensusEstimatePeriodType,
    FinancialModel,
    FinancialModelRevision,
    FinancialModelType,
    FundamentalMetric,
    FundamentalPeriodType,
    Listing,
    PriceObservation,
    now,
)

FISCAL_YEAR_MAPPING_BASIS = "NO_EXPLICIT_MODEL_FISCAL_YEAR_ANCHOR"
MAX_RETURN_DATE_LAG_DAYS = 7
ACCEPTED_PRICE_QUALITY = {"PASS", "PASS_VERIFIED_FALLBACK"}


def _day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, UTC)


def _price_statement(
    listing_id: UUID, effective_cutoff: datetime, known_at: datetime
) -> Select[PriceObservation]:
    return (
        select(PriceObservation)
        .where(
            PriceObservation.listing_id == listing_id,
            PriceObservation.price_kind == "DAILY_CLOSE",
            PriceObservation.market_date <= effective_cutoff,
            PriceObservation.recorded_at <= known_at,
            or_(PriceObservation.observed_at.is_(None), PriceObservation.observed_at <= known_at),
        )
        .order_by(
            PriceObservation.market_date.desc(),
            case(
                (PriceObservation.data_quality == "PASS", 0),
                (PriceObservation.data_quality == "PASS_VERIFIED_FALLBACK", 1),
                (PriceObservation.data_quality == "UNSPECIFIED", 2),
                else_=3,
            ),
            case((PriceObservation.provider == "YAHOO_FINANCE", 0), else_=1),
            PriceObservation.recorded_at.desc(),
        )
        .limit(1)
    )


def _price_read(
    listing: Listing,
    observation: PriceObservation | None,
    *,
    as_of: date,
) -> s.TemporalPriceRead:
    if observation is None:
        return s.TemporalPriceRead(
            status="NO_DATA",
            listing=s.ListingRead.model_validate(listing),
            market_date=None,
            close=None,
            total_return_close=None,
            currency=listing.currency,
            provider=None,
            observed_at=None,
            recorded_at=None,
            data_quality=None,
            age_days=None,
            reason="No daily close was known for this listing by the requested cutoff.",
        )
    age_days = (as_of - observation.market_date.date()).days
    reason = None
    status = "AVAILABLE"
    if observation.data_quality not in ACCEPTED_PRICE_QUALITY:
        status = "DATA_CHECK"
        reason = f"Price observation quality is {observation.data_quality}."
    elif observation.split_adjusted_close is None:
        status = "DATA_CHECK"
        reason = "The observation has no split-adjusted close."
    elif observation.observed_at is None:
        status = "DATA_CHECK"
        reason = "The source observation timestamp is unknown; recorded time bounds availability."
    elif age_days > MAX_RETURN_DATE_LAG_DAYS:
        status = "STALE"
        reason = f"The latest known close is {age_days} days before the requested date."
    return s.TemporalPriceRead(
        status=status,
        listing=s.ListingRead.model_validate(listing),
        market_date=observation.market_date,
        close=observation.split_adjusted_close,
        total_return_close=observation.total_return_close,
        currency=observation.currency,
        provider=observation.provider,
        observed_at=observation.observed_at,
        recorded_at=observation.recorded_at,
        data_quality=observation.data_quality,
        age_days=age_days,
        reason=reason,
    )


def _subsequent_return(
    session: Session,
    listing_id: UUID,
    start: PriceObservation | None,
    *,
    as_of: date,
    horizon_days: int,
    outcome_known_at: datetime,
) -> s.TemporalReturnRead:
    target_date = as_of + timedelta(days=horizon_days)

    def unavailable(status: str, reason: str) -> s.TemporalReturnRead:
        return s.TemporalReturnRead(
            status=status,
            horizon_days=horizon_days,
            target_date=target_date,
            start_market_date=start.market_date if start else None,
            end_market_date=None,
            start_total_return_close=start.total_return_close if start else None,
            end_total_return_close=None,
            return_fraction=None,
            actual_days=None,
            basis="TOTAL_RETURN_CLOSE",
            reason=reason,
        )

    if start is None:
        return unavailable("NO_BASE_PRICE", "No baseline daily close was known at forecast time.")
    age_days = (as_of - start.market_date.date()).days
    if age_days > MAX_RETURN_DATE_LAG_DAYS:
        return unavailable(
            "STALE_BASE_PRICE", "The baseline close is outside the freshness window."
        )
    if (
        start.data_quality not in ACCEPTED_PRICE_QUALITY
        or start.total_return_close is None
        or start.observed_at is None
    ):
        return unavailable(
            "BASE_PRICE_DATA_CHECK",
            "A trusted baseline total-return close is unavailable.",
        )
    horizon_cutoff = min(_day_end(target_date), _day_end(outcome_known_at.date()))
    end = session.scalar(
        _price_statement(listing_id, horizon_cutoff, outcome_known_at).where(
            PriceObservation.market_date > _day_end(as_of),
            PriceObservation.market_date > start.market_date,
        )
    )
    if end is None:
        status = "HORIZON_NOT_REACHED" if outcome_known_at.date() < target_date else "NO_END_PRICE"
        return unavailable(status, "No eligible daily close was available by the outcome cutoff.")
    actual_days = (end.market_date.date() - as_of).days
    if (target_date - end.market_date.date()).days > MAX_RETURN_DATE_LAG_DAYS:
        return s.TemporalReturnRead(
            status="OUTSIDE_HORIZON_TOLERANCE",
            horizon_days=horizon_days,
            target_date=target_date,
            start_market_date=start.market_date,
            end_market_date=end.market_date,
            start_total_return_close=start.total_return_close,
            end_total_return_close=end.total_return_close,
            return_fraction=None,
            actual_days=actual_days,
            basis="TOTAL_RETURN_CLOSE",
            reason="The last eligible close is more than seven days before the horizon date.",
        )
    if (
        end.data_quality not in ACCEPTED_PRICE_QUALITY
        or end.total_return_close is None
        or end.observed_at is None
        or end.currency != start.currency
    ):
        return s.TemporalReturnRead(
            status="END_PRICE_DATA_CHECK",
            horizon_days=horizon_days,
            target_date=target_date,
            start_market_date=start.market_date,
            end_market_date=end.market_date,
            start_total_return_close=start.total_return_close,
            end_total_return_close=end.total_return_close,
            return_fraction=None,
            actual_days=actual_days,
            basis="TOTAL_RETURN_CLOSE",
            reason=(
                "The endpoint is low quality, lacks a total-return value, "
                "or has a currency mismatch."
            ),
        )
    return s.TemporalReturnRead(
        status="AVAILABLE",
        horizon_days=horizon_days,
        target_date=target_date,
        start_market_date=start.market_date,
        end_market_date=end.market_date,
        start_total_return_close=start.total_return_close,
        end_total_return_close=end.total_return_close,
        return_fraction=end.total_return_close / start.total_return_close - Decimal(1),
        actual_days=actual_days,
        basis="TOTAL_RETURN_CLOSE",
        reason=None,
    )


def _revision_for_as_of(
    session: Session,
    model_id: UUID,
    effective_cutoff: datetime,
    known_at: datetime,
) -> FinancialModelRevision | None:
    return session.scalar(
        select(FinancialModelRevision)
        .where(
            FinancialModelRevision.model_id == model_id,
            FinancialModelRevision.effective_at <= effective_cutoff,
            FinancialModelRevision.recorded_at <= known_at,
        )
        .order_by(
            FinancialModelRevision.effective_at.desc(),
            FinancialModelRevision.recorded_at.desc(),
            FinancialModelRevision.revision_number.desc(),
        )
        .limit(1)
    )


def _model_forecasts(
    session: Session,
    company_id: UUID,
    *,
    as_of: date,
    forecast_known_at: datetime,
    horizon_days: int,
    outcome_known_at: datetime,
) -> list[s.TemporalModelForecastRead]:
    models = session.scalars(
        select(FinancialModel)
        .where(FinancialModel.company_id == company_id)
        .order_by(FinancialModel.model_name, FinancialModel.id)
    ).all()
    results: list[s.TemporalModelForecastRead] = []
    effective_cutoff = min(_day_end(as_of), forecast_known_at)
    for model in models:
        revision = _revision_for_as_of(session, model.id, effective_cutoff, forecast_known_at)
        listing = session.get(Listing, model.valuation_listing_id)
        if listing is None:
            continue
        if revision is None:
            status = "NO_REVISION_KNOWN_AT_CUTOFF"
            projection_year = None
            value = None
        elif model.model_type == FinancialModelType.RESIDUAL_INCOME_10Y_FADE:
            status = "UNSUPPORTED_METHOD_FOR_REVENUE"
            projection_year = None
            value = None
        else:
            # The canonical model stores ordinal forecast_year values only. Its
            # revision effective time is not a fiscal-period anchor.
            status = "FISCAL_YEAR_MAPPING_UNAVAILABLE"
            projection_year = None
            value = None
        start_price = session.scalar(
            _price_statement(listing.id, effective_cutoff, forecast_known_at)
        )
        price_read = _price_read(listing, start_price, as_of=as_of)
        return_read = _subsequent_return(
            session,
            listing.id,
            start_price,
            as_of=as_of,
            horizon_days=horizon_days,
            outcome_known_at=outcome_known_at,
        )
        results.append(
            s.TemporalModelForecastRead(
                model_id=model.id,
                model_name=model.model_name,
                model_type=model.model_type,
                model_currency=model.model_currency,
                valuation_listing=s.ListingRead.model_validate(listing),
                status=status,
                forecast_year=projection_year,
                fiscal_year_mapping_basis=FISCAL_YEAR_MAPPING_BASIS,
                value=value,
                unit="currency",
                revision_id=revision.id if revision else None,
                revision_number=revision.revision_number if revision else None,
                methodology_version=revision.methodology_version if revision else None,
                revision_source=revision.source if revision else None,
                rationale=revision.rationale if revision else None,
                effective_at=revision.effective_at if revision else None,
                recorded_at=revision.recorded_at if revision else None,
                price_at_forecast=price_read,
                subsequent_market_return=return_read,
            )
        )
    return results


def _consensus_value(
    session: Session,
    company_id: UUID,
    fiscal_year: int,
    *,
    as_of: date,
    known_at: datetime,
    effective_cutoff: datetime,
) -> s.TemporalAlignedValueRead:
    estimates = queries.company_consensus_estimates(
        session,
        company_id,
        as_of=as_of,
        known_at=known_at,
        effective_cutoff=effective_cutoff,
    )
    provider = next((item for item in estimates.providers if item.selected), None)
    if provider is None:
        return _empty_value(estimates.continuity_status)
    matches = [
        item
        for item in provider.periods
        if item.metric == ConsensusEstimateMetric.REVENUE
        and item.period_type == ConsensusEstimatePeriodType.ANNUAL
        and item.period_end is not None
        and item.period_end.year == fiscal_year
    ]
    if len(matches) > 1:
        return _empty_value("AMBIGUOUS_FISCAL_PERIOD")
    if not matches:
        annual_revenue = [
            item
            for item in provider.periods
            if item.metric == ConsensusEstimateMetric.REVENUE
            and item.period_type == ConsensusEstimatePeriodType.ANNUAL
        ]
        if annual_revenue and all(item.period_end is None for item in annual_revenue):
            return _empty_value("FISCAL_PERIOD_MAPPING_UNAVAILABLE")
        return _empty_value("NO_MATCHING_FISCAL_PERIOD")
    estimate = matches[0]
    observation = estimate.current_observation
    if observation is None:
        return _empty_value("NO_OBSERVATION")
    return s.TemporalAlignedValueRead(
        status="AVAILABLE" if observation.data_quality == "PASS" else "DATA_CHECK",
        value=observation.value,
        currency=observation.currency,
        unit=observation.unit,
        source_name=observation.provider_id,
        source_reference=observation.source_ref,
        source_observation_id=observation.id,
        period_end=observation.period_end,
        effective_at=provider.effective_from,
        observed_at=observation.observed_at,
        recorded_at=observation.recorded_at,
        data_quality=observation.data_quality,
        quality_reason=observation.quality_reason,
        low_value=observation.low_value,
        high_value=observation.high_value,
        analyst_count=observation.analyst_count,
    )


def _actual_value(
    session: Session,
    company_id: UUID,
    fiscal_year: int,
    *,
    outcome_known_at: datetime,
) -> s.TemporalAlignedValueRead:
    facts = queries.company_reported_fundamentals(
        session,
        company_id,
        period_type=FundamentalPeriodType.ANNUAL,
        as_of=outcome_known_at.date(),
        known_at=outcome_known_at,
        effective_cutoff=outcome_known_at,
    )
    matches = [
        item
        for item in facts.periods
        if item.metric == FundamentalMetric.REVENUE and item.fiscal_year == fiscal_year
    ]
    if not matches:
        return _empty_value("NOT_REPORTED")
    if len(matches) > 1:
        return _empty_value("AMBIGUOUS_FISCAL_PERIOD")
    period = matches[0]
    observation = period.selected_observation
    if period.selection_status != "AVAILABLE" or observation is None:
        return s.TemporalAlignedValueRead(
            status=period.selection_status,
            value=None,
            currency=period.currency,
            unit=period.unit,
            source_name=None,
            source_reference=None,
            source_observation_id=None,
            period_end=period.period_end.date(),
            effective_at=None,
            observed_at=None,
            recorded_at=None,
            data_quality=None,
            quality_reason="The canonical actual is not uniquely available.",
        )
    status = "AVAILABLE" if observation.data_quality == "PASS" else "DATA_CHECK"
    return s.TemporalAlignedValueRead(
        status=status,
        value=observation.value,
        currency=observation.currency,
        unit=observation.unit,
        source_name=observation.provider_id,
        source_reference=observation.source_ref,
        source_observation_id=observation.id,
        period_end=observation.period_end.date(),
        effective_at=observation.filed_at,
        observed_at=observation.observed_at,
        recorded_at=observation.recorded_at,
        data_quality=observation.data_quality,
        quality_reason=observation.quality_reason,
    )


def _empty_value(status: str) -> s.TemporalAlignedValueRead:
    return s.TemporalAlignedValueRead(
        status=status,
        value=None,
        currency=None,
        unit=None,
        source_name=None,
        source_reference=None,
        source_observation_id=None,
        period_end=None,
        effective_at=None,
        observed_at=None,
        recorded_at=None,
        data_quality=None,
        quality_reason=None,
    )


def _comparison_status(
    models: list[s.TemporalModelForecastRead],
    consensus: s.TemporalAlignedValueRead,
    actual: s.TemporalAlignedValueRead,
) -> str:
    forecasts = [item for item in models if item.status == "AVAILABLE" and item.value is not None]
    if any(item.status == "FISCAL_YEAR_MAPPING_UNAVAILABLE" for item in models):
        return "FISCAL_YEAR_MAPPING_UNAVAILABLE"
    if any(item.status == "UNSUPPORTED_METHOD_FOR_REVENUE" for item in models):
        return "UNSUPPORTED_MODEL_METHOD_FOR_REVENUE"
    if not forecasts:
        return "NO_MODEL_FORECAST"
    if (
        consensus.status != "AVAILABLE"
        or actual.status != "AVAILABLE"
        or consensus.value is None
        or actual.value is None
    ):
        return "INCOMPLETE"
    values: list[tuple[str | None, str | None]] = [
        (item.model_currency, item.unit) for item in forecasts
    ]
    values.extend([(consensus.currency, consensus.unit), (actual.currency, actual.unit)])
    if any(currency is None for currency, _ in values):
        return "UNKNOWN_CURRENCY"
    if len({currency for currency, _ in values}) > 1:
        return "CURRENCY_MISMATCH"
    canonical_units = {unit.casefold() for _, unit in values if unit is not None}
    if len(canonical_units) > 1:
        return "UNIT_MISMATCH"
    return "COMPARABLE"


def company_temporal_alignment(
    session: Session,
    company_id: UUID,
    *,
    fiscal_year: int,
    as_of: date,
    known_at: datetime | None = None,
    outcome_known_at: datetime | None = None,
    horizon_days: int = 365,
) -> s.CompanyTemporalAlignmentRead:
    """Compare revenue inputs known at a forecast date with later canonical outcomes."""

    if known_at is not None and (known_at.tzinfo is None or known_at.utcoffset() is None):
        raise ValueError("known_at must be timezone-aware")
    if outcome_known_at is not None and (
        outcome_known_at.tzinfo is None or outcome_known_at.utcoffset() is None
    ):
        raise ValueError("outcome_known_at must be timezone-aware")
    forecast_known_at = (known_at or _day_end(as_of)).astimezone(UTC)
    if forecast_known_at > _day_end(as_of):
        raise ValueError("known_at cannot be later than the as_of cutoff")
    if horizon_days < 1 or horizon_days > 3650:
        raise ValueError("horizon_days must be between 1 and 3650")
    outcome_cutoff = (outcome_known_at or now()).astimezone(UTC)
    models = _model_forecasts(
        session,
        company_id,
        as_of=as_of,
        forecast_known_at=forecast_known_at,
        horizon_days=horizon_days,
        outcome_known_at=outcome_cutoff,
    )
    consensus = _consensus_value(
        session,
        company_id,
        fiscal_year,
        as_of=as_of,
        known_at=forecast_known_at,
        effective_cutoff=min(_day_end(as_of), forecast_known_at),
    )
    actual = _actual_value(session, company_id, fiscal_year, outcome_known_at=outcome_cutoff)
    return s.CompanyTemporalAlignmentRead(
        company_id=company_id,
        metric="REVENUE",
        fiscal_year=fiscal_year,
        as_of=as_of,
        forecast_known_at=forecast_known_at,
        outcome_known_at=outcome_cutoff,
        horizon_days=horizon_days,
        fiscal_year_mapping_basis=FISCAL_YEAR_MAPPING_BASIS,
        comparison_status=_comparison_status(models, consensus, actual),
        model_forecasts=models,
        consensus=consensus,
        actual=actual,
    )
