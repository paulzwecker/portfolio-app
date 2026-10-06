"""Deterministic Estimate Momentum derived from one selected consensus stream.

The implementation follows the later documented workbook formula set. Workbook
persistence and up/down breadth inputs are deliberately omitted because the
canonical consensus observations do not contain those facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from portfolio_api.domain import schemas as s

METHODOLOGY_VERSION = "legacy-estimate-momentum-v2-partial-1"
WINDOWS: tuple[tuple[Literal["12M", "6M", "3M"], int, Decimal], ...] = (
    ("12M", 12, Decimal("0.30")),
    ("6M", 6, Decimal("0.20")),
    ("3M", 3, Decimal("0.15")),
)
PERIOD_WEIGHTS = (Decimal("0.60"), Decimal("0.40"))
METRIC_WEIGHTS = {"REVENUE": Decimal("0.70"), "EPS": Decimal("0.30")}
EXPECTED_COMPONENTS = 20
REFERENCE_MAX_AGE_DAYS = 14
CURRENT_FRESH_DAYS = 14


@dataclass(frozen=True)
class ConsensusObservationPoint:
    """The normalized subset of a stored observation used by this calculation."""

    id: UUID
    provider_mapping_id: UUID
    provider_id: str
    metric: str
    period_type: str
    forecast_period: str
    period_end: date | None
    value: Decimal
    analyst_count: int | None
    currency: str | None
    unit: str
    snapshot_date: date
    observed_at: datetime | None
    recorded_at: datetime
    data_quality: str
    quality_reason: str | None


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_month = divmod(month_index, 12)
    month = zero_month + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, month, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _point_order(point: ConsensusObservationPoint) -> tuple[date, datetime, datetime]:
    midnight = datetime.combine(point.snapshot_date, time.min, UTC)
    observed = point.observed_at or midnight
    return point.snapshot_date, observed, point.recorded_at


def _direction(
    score: Decimal | None,
) -> Literal["POSITIVE", "MILD_POSITIVE", "NEUTRAL_MIXED", "MILD_NEGATIVE", "NEGATIVE"] | None:
    if score is None:
        return None
    if score >= Decimal("0.35"):
        return "POSITIVE"
    if score >= Decimal("0.12"):
        return "MILD_POSITIVE"
    if score > Decimal("-0.12"):
        return "NEUTRAL_MIXED"
    if score > Decimal("-0.35"):
        return "MILD_NEGATIVE"
    return "NEGATIVE"


def _confidence_band(
    confidence: Decimal,
) -> Literal["HIGH", "MEDIUM", "LOW", "COLLECTING", "NO_DATA"]:
    if confidence >= Decimal("0.75"):
        return "HIGH"
    if confidence >= Decimal("0.50"):
        return "MEDIUM"
    if confidence >= Decimal("0.35"):
        return "LOW"
    if confidence > 0:
        return "COLLECTING"
    return "NO_DATA"


def _weighted_available(
    values: list[tuple[Decimal, Decimal]],
) -> Decimal | None:
    if not values:
        return None
    weight = sum((item[1] for item in values), Decimal(0))
    if weight == 0:
        return None
    return sum((score * item_weight for score, item_weight in values), Decimal(0)) / weight


def _period_score(period: s.EstimateMomentumPeriodRead) -> Decimal | None:
    components = [
        (window.component_score, weight)
        for window, (_, _, weight) in zip(period.windows, WINDOWS, strict=True)
        if window.component_score is not None
    ]
    return _weighted_available(
        [(score, weight) for score, weight in components if score is not None]
    )


def calculate_estimate_momentum(
    *,
    company_id: UUID,
    as_of: date,
    known_at: datetime | None,
    continuity_status: str,
    selected_provider_id: str | None,
    selected_mapping_id: UUID | None,
    observations: list[ConsensusObservationPoint],
) -> s.CompanyEstimateMomentumRead:
    """Calculate the as-of signal without blending providers or future observations."""
    by_id = [
        point
        for point in observations
        if selected_mapping_id is not None
        and point.provider_mapping_id == selected_mapping_id
        and point.provider_id == selected_provider_id
        and point.snapshot_date <= as_of
        and (
            point.observed_at is None or point.observed_at <= datetime.combine(as_of, time.max, UTC)
        )
        and (known_at is None or point.recorded_at <= known_at)
        and (known_at is None or point.observed_at is None or point.observed_at <= known_at)
    ]
    by_id.sort(key=_point_order)
    any_invalid = any(point.data_quality == "INVALID" for point in by_id)
    any_data_check = any(point.data_quality == "DATA_CHECK" for point in by_id)
    data_quality: Literal["PASS", "DATA_CHECK", "INVALID", "NO_DATA"] = (
        "INVALID"
        if any_invalid
        else "DATA_CHECK"
        if any_data_check
        else "PASS"
        if by_id
        else "NO_DATA"
    )

    if continuity_status == "NO_MAPPING":
        return _unavailable(
            company_id,
            as_of,
            known_at,
            selected_provider_id,
            "NO_MAPPING",
            "No consensus source is selected for this as-of date.",
            data_quality,
        )
    if continuity_status == "AMBIGUOUS_FALLBACK":
        return _unavailable(
            company_id,
            as_of,
            known_at,
            selected_provider_id,
            "AMBIGUOUS_SOURCE",
            "Fallback source precedence is ambiguous; no provider series is selected.",
            data_quality,
        )
    if selected_mapping_id is None or selected_provider_id is None:
        return _unavailable(
            company_id,
            as_of,
            known_at,
            selected_provider_id,
            "INSUFFICIENT_HISTORY",
            "A source is selected, but it has no observations available for this as-of query.",
            data_quality,
        )

    annual = [
        point
        for point in by_id
        if point.period_type == "ANNUAL"
        and point.period_end is not None
        and point.period_end > as_of
        and point.metric in METRIC_WEIGHTS
    ]
    period_keys = sorted(
        {(point.metric, point.period_end) for point in annual if point.period_end is not None},
        key=lambda item: (item[0], item[1]),
    )
    future_by_metric: dict[str, list[date]] = {"REVENUE": [], "EPS": []}
    for metric, period_end in period_keys:
        assert period_end is not None
        if period_end not in future_by_metric[metric]:
            future_by_metric[metric].append(period_end)
    for metric in future_by_metric:
        future_by_metric[metric] = sorted(future_by_metric[metric])[:2]

    periods: list[s.EstimateMomentumPeriodRead] = []
    period_scores: dict[tuple[str, str], Decimal | None] = {}
    current_points: list[ConsensusObservationPoint] = []
    for metric in ("REVENUE", "EPS"):
        for period_index, period_end in enumerate(future_by_metric[metric]):
            horizon: Literal["FY+1", "FY+2"] = "FY+1" if period_index == 0 else "FY+2"
            rows = [
                point
                for point in annual
                if point.metric == metric and point.period_end == period_end
            ]
            identities = {(point.currency, point.unit) for point in rows}
            latest_by_identity = {
                identity: max(
                    (point for point in rows if (point.currency, point.unit) == identity),
                    key=_point_order,
                )
                for identity in identities
            }
            latest_row = max(rows, key=_point_order)
            current_points.append(latest_row)
            if len(identities) != 1:
                period = s.EstimateMomentumPeriodRead(
                    metric=metric,
                    horizon=horizon,
                    forecast_period=latest_row.forecast_period,
                    period_end=period_end,
                    currency=None,
                    unit=latest_row.unit,
                    analyst_count=latest_row.analyst_count,
                    current_value=None,
                    current_snapshot_date=latest_row.snapshot_date,
                    data_quality="DATA_CHECK",
                    quality_reason=(
                        "Currency or unit changed within this provider's annual series; "
                        "the values are not compared."
                    ),
                    windows=[
                        s.EstimateMomentumWindowRead(
                            window=window,
                            status="DATA_CHECK",
                            reference_value=None,
                            reference_snapshot_date=None,
                            reference_days_before_target=None,
                            revision_fraction=None,
                            component_score=None,
                            reason="Currency/unit comparability is unresolved.",
                        )
                        for window, _, _ in WINDOWS
                    ],
                )
                periods.append(period)
                period_scores[(metric, horizon)] = None
                continue

            identity = next(iter(identities))
            series = [point for point in rows if (point.currency, point.unit) == identity]
            current = latest_by_identity[identity]
            current_ok = current.data_quality == "PASS"
            windows: list[s.EstimateMomentumWindowRead] = []
            for window, months, _weight in WINDOWS:
                target_date = _subtract_months(as_of, months)
                anchor = max(
                    (
                        point
                        for point in series
                        if point.snapshot_date <= target_date
                        and (
                            point.observed_at is None
                            or point.observed_at <= datetime.combine(target_date, time.max, UTC)
                        )
                    ),
                    key=_point_order,
                    default=None,
                )
                if not current_ok:
                    read = s.EstimateMomentumWindowRead(
                        window=window,
                        status="DATA_CHECK",
                        reference_value=anchor.value if anchor else None,
                        reference_snapshot_date=anchor.snapshot_date if anchor else None,
                        reference_days_before_target=(target_date - anchor.snapshot_date).days
                        if anchor
                        else None,
                        revision_fraction=None,
                        component_score=None,
                        reason=current.quality_reason
                        or "The current estimate is not PASS quality.",
                    )
                elif anchor is None:
                    read = s.EstimateMomentumWindowRead(
                        window=window,
                        status="MISSING_REFERENCE",
                        reference_value=None,
                        reference_snapshot_date=None,
                        reference_days_before_target=None,
                        revision_fraction=None,
                        component_score=None,
                        reason=(
                            f"No same-provider observation exists on or before the {window} "
                            "reference date."
                        ),
                    )
                elif anchor.data_quality != "PASS":
                    read = s.EstimateMomentumWindowRead(
                        window=window,
                        status="DATA_CHECK",
                        reference_value=anchor.value,
                        reference_snapshot_date=anchor.snapshot_date,
                        reference_days_before_target=(target_date - anchor.snapshot_date).days,
                        revision_fraction=None,
                        component_score=None,
                        reason=anchor.quality_reason
                        or "The reference estimate is not PASS quality.",
                    )
                elif (target_date - anchor.snapshot_date).days > REFERENCE_MAX_AGE_DAYS:
                    read = s.EstimateMomentumWindowRead(
                        window=window,
                        status="STALE_REFERENCE",
                        reference_value=anchor.value,
                        reference_snapshot_date=anchor.snapshot_date,
                        reference_days_before_target=(target_date - anchor.snapshot_date).days,
                        revision_fraction=None,
                        component_score=None,
                        reason=(
                            f"The closest earlier point-in-time snapshot is more than "
                            f"{REFERENCE_MAX_AGE_DAYS} days before the reference date."
                        ),
                    )
                elif anchor.value <= 0:
                    read = s.EstimateMomentumWindowRead(
                        window=window,
                        status="INVALID_BASELINE",
                        reference_value=anchor.value,
                        reference_snapshot_date=anchor.snapshot_date,
                        reference_days_before_target=(target_date - anchor.snapshot_date).days,
                        revision_fraction=None,
                        component_score=None,
                        reason="The legacy percentage-change denominator must be positive.",
                    )
                else:
                    change = current.value / anchor.value - Decimal(1)
                    component = max(Decimal(-2), min(Decimal(2), change / Decimal("0.05")))
                    read = s.EstimateMomentumWindowRead(
                        window=window,
                        status="AVAILABLE",
                        reference_value=anchor.value,
                        reference_snapshot_date=anchor.snapshot_date,
                        reference_days_before_target=(target_date - anchor.snapshot_date).days,
                        revision_fraction=change,
                        component_score=component,
                        reason=None,
                    )
                windows.append(read)
            period = s.EstimateMomentumPeriodRead(
                metric=metric,
                horizon=horizon,
                forecast_period=current.forecast_period,
                period_end=period_end,
                currency=current.currency,
                unit=current.unit,
                analyst_count=current.analyst_count,
                current_value=current.value if current_ok else None,
                current_snapshot_date=current.snapshot_date,
                data_quality=current.data_quality,
                quality_reason=current.quality_reason,
                windows=windows,
            )
            periods.append(period)
            period_scores[(metric, horizon)] = _period_score(period)

    periods.sort(key=lambda item: (item.metric != "REVENUE", item.period_end))
    coverage_count = sum(
        1 for period in periods for window in period.windows if window.component_score is not None
    )
    coverage_fraction = Decimal(coverage_count) / Decimal(EXPECTED_COMPONENTS)
    confidence = min(Decimal(1), coverage_fraction * Decimal(2))
    confidence_band = _confidence_band(confidence)
    latest_current = max(current_points, key=_point_order, default=None)
    freshness: Literal["FRESH", "STALE", "DATA_CHECK", "NO_DATA"]
    if latest_current is None:
        freshness = "NO_DATA"
    elif latest_current.data_quality != "PASS":
        freshness = "DATA_CHECK"
    else:
        freshness = (
            "FRESH"
            if (as_of - latest_current.snapshot_date).days <= CURRENT_FRESH_DAYS
            else "STALE"
        )

    metric_scores: dict[str, Decimal | None] = {}
    for metric in METRIC_WEIGHTS:
        first = period_scores.get((metric, "FY+1"))
        second = period_scores.get((metric, "FY+2"))
        if first is not None and second is not None:
            metric_scores[metric] = first * PERIOD_WEIGHTS[0] + second * PERIOD_WEIGHTS[1]
        elif first is not None:
            metric_scores[metric] = first
        else:
            metric_scores[metric] = second
    available_metric_scores: list[tuple[Decimal, Decimal]] = []
    for metric, weight in METRIC_WEIGHTS.items():
        score = metric_scores[metric]
        if score is not None:
            available_metric_scores.append((score, weight))
    raw_score = _weighted_available(available_metric_scores)
    direction = _direction(raw_score)
    if not annual:
        availability: Literal[
            "AVAILABLE", "DIRECTION_ONLY", "INSUFFICIENT_HISTORY", "NO_MAPPING", "AMBIGUOUS_SOURCE"
        ] = "INSUFFICIENT_HISTORY"
        reason = (
            "The selected source has no future annual Revenue/EPS estimates with resolved "
            "fiscal-period ends."
        )
    elif raw_score is None:
        availability = "INSUFFICIENT_HISTORY"
        reason = (
            "No same-provider point-in-time reference comparison passed quality and freshness "
            "checks; missing history is not treated as neutral."
        )
    elif confidence < Decimal("0.35"):
        availability = "DIRECTION_ONLY"
        reason = (
            f"Direction is visible, but only {coverage_count} of {EXPECTED_COMPONENTS} "
            "legacy revision-component opportunities are covered."
        )
    else:
        availability = "AVAILABLE"
        reason = None

    latest_snapshot_date = None if latest_current is None else latest_current.snapshot_date
    return s.CompanyEstimateMomentumRead(
        company_id=company_id,
        methodology_version=METHODOLOGY_VERSION,
        availability=availability,
        direction=direction,
        raw_score=raw_score,
        confidence_adjusted_score=raw_score * confidence if raw_score is not None else None,
        confidence=confidence,
        confidence_band=confidence_band,
        coverage_fraction=coverage_fraction,
        coverage_count=coverage_count,
        coverage_total=EXPECTED_COMPONENTS,
        freshness=freshness,
        data_quality=data_quality,
        provider_id=selected_provider_id,
        latest_snapshot_date=latest_snapshot_date,
        as_of=as_of,
        known_at=known_at,
        reason=reason,
        periods=periods,
    )


def _unavailable(
    company_id: UUID,
    as_of: date,
    known_at: datetime | None,
    provider_id: str | None,
    availability: Literal["NO_MAPPING", "AMBIGUOUS_SOURCE", "INSUFFICIENT_HISTORY"],
    reason: str,
    data_quality: Literal["PASS", "DATA_CHECK", "INVALID", "NO_DATA"],
) -> s.CompanyEstimateMomentumRead:
    return s.CompanyEstimateMomentumRead(
        company_id=company_id,
        methodology_version=METHODOLOGY_VERSION,
        availability=availability,
        direction=None,
        raw_score=None,
        confidence_adjusted_score=None,
        confidence=Decimal(0),
        confidence_band="NO_DATA",
        coverage_fraction=Decimal(0),
        coverage_count=0,
        coverage_total=EXPECTED_COMPONENTS,
        freshness="DATA_CHECK" if data_quality in {"DATA_CHECK", "INVALID"} else "NO_DATA",
        data_quality=data_quality,
        provider_id=provider_id,
        latest_snapshot_date=None,
        as_of=as_of,
        known_at=known_at,
        reason=reason,
        periods=[],
    )
