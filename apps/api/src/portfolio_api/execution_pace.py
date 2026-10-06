"""Auditable Execution Pace decisions, separate from business Execution scores.

The branch order and thresholds reproduce the Portfolio tab's EXEC-v1 rules.
Input selection and persistence live here so every decision records the exact
point-in-time facts and references used by the rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import queries
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    ExecutionPace,
    ExecutionPaceDecision,
    ExecutionPaceDecisionStatus,
    ExecutionPaceRun,
    ExecutionPaceRunStatus,
    Lifecycle,
    LifecycleEvent,
    Portfolio,
)

METHODOLOGY_VERSION = "legacy-execution-pace-v1"
ALLOCATION_HOLD_BAND = Decimal("0.003")
LEGACY_ACCELERATION_IRR = Decimal("0.15")
LEGACY_VALUATION_BANDS: tuple[
    tuple[Decimal, Literal["DEEP_DISCOUNT", "DISCOUNT", "NEAR_FAIR", "RICH"]], ...
] = (
    (Decimal("0.25"), "DEEP_DISCOUNT"),
    (Decimal("0.10"), "DISCOUNT"),
    (Decimal("-0.10"), "NEAR_FAIR"),
    (Decimal("-0.25"), "RICH"),
)


@dataclass(frozen=True)
class PaceResult:
    status: ExecutionPaceDecisionStatus
    pace: ExecutionPace | None
    reason: str


def valuation_zone(
    weighted_upside: Decimal | None,
) -> Literal["DEEP_DISCOUNT", "DISCOUNT", "NEAR_FAIR", "RICH", "VERY_RICH"] | None:
    """Return the workbook's documented FV-zone label for weighted upside."""
    if weighted_upside is None:
        return None
    for threshold, label in LEGACY_VALUATION_BANDS:
        if weighted_upside >= threshold:
            return label
    return "VERY_RICH"


def normalize_price_regime(regime: str | None, trend_state: str | None) -> str | None:
    """Apply the Portfolio sheet's explicit regime-to-pace label mapping."""
    raw = (regime or "").strip().upper()
    mapped = {
        "RECOVERING FROM DEEP CORRECTION": "DEEP RECOVERY",
        "RECOVERING": "RECOVERY",
        "DEEP CORRECTION": "DEEP CORR",
        "HEALTHY UPTREND": "UPTREND",
        "PULLBACK / WEAKENING": "PULLBACK",
        "BASE / SIDEWAYS": "SIDEWAYS",
        "DOWNTREND": "DOWNTREND",
        "CORRECTION": "CORRECTION",
        "EXTENDED": "EXTENDED",
    }
    if raw in mapped:
        return mapped[raw]
    if raw in {"UPTREND", "STRONG UPTREND", "WEAKENING", "PULLBACK", "SIDEWAYS"}:
        return raw
    if not raw:
        fallback = (trend_state or "").strip().upper()
        return fallback or None
    return None


def derive_execution_pace(snapshot: s.ExecutionPaceInputSnapshot) -> PaceResult:
    """Apply the legacy branch order after refusing incomplete critical inputs."""
    if snapshot.target_revision_id is None or snapshot.target_weight is None:
        return _review("No accepted, explicit target weight is available.")
    if snapshot.holding_snapshot_id is None or snapshot.current_weight is None:
        return _review("A complete current holding snapshot and current weight are required.")
    if snapshot.allocation_status != "VALUED":
        return _review("Current portfolio weights are incomplete or not fresh.")
    if snapshot.model_source_kind is None or snapshot.model_source_id is None:
        return _review("No unique current model output is linked to an exact valuation listing.")
    if snapshot.model_effective_at is None:
        return _review("The model output has no effective timestamp.")
    if snapshot.model_output_quality != "COMPLETE":
        return _review("The current model output is partial or has a data-quality issue.")
    if snapshot.model_contract_status not in {None, "PASS"}:
        return _review("The current normalized model contract is not in PASS state.")
    if snapshot.model_review_flag and re.search(
        r"REASSESSMENT|DATA INVALID", snapshot.model_review_flag, flags=re.IGNORECASE
    ):
        return _review("The model carries a reassessment or invalid-data review flag.")
    if snapshot.valuation_listing_id is None or snapshot.model_currency is None:
        return _review("Model currency or exact valuation listing identity is unavailable.")
    if snapshot.valuation_currency != snapshot.model_currency:
        return _review("Model and exact-listing quote currencies do not match.")
    if snapshot.price_freshness != "FRESH" or snapshot.price_quality not in {
        "PASS",
        "PASS_VERIFIED_FALLBACK",
    }:
        return _review("The exact-listing market price is missing, stale, or quality-checked.")
    if snapshot.price is None or snapshot.price <= 0 or snapshot.price_observation_id is None:
        return _review("A positive exact-listing price observation is required.")
    if snapshot.model_price_status != "AVAILABLE":
        return _review("Expected IRR does not have a fresh, currency-comparable source price.")
    if snapshot.model_price_effective_at is None:
        return _review("The Expected IRR source price has no effective timestamp.")
    if snapshot.price_market_date is None:
        return _review("The latest exact-listing market date is unavailable.")
    if snapshot.model_price_effective_at.date() < snapshot.price_market_date.date():
        return _review("Expected IRR predates a later exact-listing market price.")
    if snapshot.valuation_zone is None or snapshot.weighted_upside is None:
        return _review("Weighted Fair Value and a comparable current price are required.")
    if snapshot.price_regime_quality != "PASS" or snapshot.price_regime_freshness != "FRESH":
        return _review("Price-regime inputs are missing, stale, or not in PASS state.")
    if snapshot.price_regime is None:
        return _review("The legacy price-regime label cannot be mapped safely.")
    gap = snapshot.allocation_gap
    if gap is None:
        return _review("Allocation gap is unavailable.")
    underweight = gap > Decimal(0)
    correction_or_recovery = _contains(snapshot.price_regime, "CORR", "RECOVERY")
    is_discount = "DISCOUNT" in snapshot.valuation_zone
    is_rich = "RICH" in snapshot.valuation_zone
    uptrend_or_extended = _contains(snapshot.price_regime, "UPTREND", "EXTENDED")
    downtrend_or_pullback = _contains(snapshot.price_regime, "DOWNTREND", "PULLBACK")

    if abs(gap) < ALLOCATION_HOLD_BAND:
        return _available(ExecutionPace.HOLD, "Allocation gap is inside the 0.3% hold band.")

    if underweight:
        if snapshot.expected_irr is None or snapshot.hurdle is None:
            return _review("Expected IRR and hurdle are required before accelerating a buy.")
        if snapshot.expected_irr < snapshot.hurdle:
            return _available(ExecutionPace.WAIT_LIMIT, "Expected IRR is below the model hurdle.")
        if is_rich:
            return _available(
                ExecutionPace.WAIT_LIMIT, "Valuation is rich against Weighted Fair Value."
            )
        momentum, momentum_issue = _momentum_for_rule(snapshot)
        if momentum_issue:
            return _review(momentum_issue)
        assert momentum is not None
        positive_estimates = "POSITIVE" in momentum
        negative_estimates = "NEGATIVE" in momentum
        if negative_estimates:
            if is_discount and correction_or_recovery:
                return _available(
                    ExecutionPace.SMALL_LADDER,
                    "Negative estimate revisions cap buying at a small ladder despite discount "
                    "and correction context.",
                )
            return _available(
                ExecutionPace.SLOW_LIMIT,
                "Negative estimate revisions slow additions and require a limit.",
            )
        if is_discount:
            if (positive_estimates or snapshot.expected_irr >= LEGACY_ACCELERATION_IRR) and (
                correction_or_recovery
            ):
                return _available(
                    ExecutionPace.ACCELERATE,
                    "Discount plus positive estimates or at least 15% Expected IRR aligns with "
                    "correction/recovery context.",
                )
            if correction_or_recovery:
                return _available(
                    ExecutionPace.BUILD, "Discount and correction/recovery support building."
                )
            if "EXTENDED" in snapshot.price_regime:
                return _available(
                    ExecutionPace.SLOW_LIMIT, "Price is extended; additions stay limited."
                )
            return _available(
                ExecutionPace.NORMAL_BUILD, "Discount supports normal-paced additions."
            )
        if positive_estimates and correction_or_recovery:
            return _available(
                ExecutionPace.NORMAL_BUILD,
                "Positive estimate revisions and correction/recovery support normal building "
                "near fair value.",
            )
        if uptrend_or_extended:
            return _available(
                ExecutionPace.SLOW_LIMIT, "Uptrend or extension limits the buying pace."
            )
        if downtrend_or_pullback:
            return _available(
                ExecutionPace.WAIT_LIMIT, "Downtrend or pullback calls for waiting on a limit."
            )
        return _available(
            ExecutionPace.LADDER, "No documented faster or slower branch applies; use a ladder."
        )

    if snapshot.target_weight == 0:
        if is_discount and correction_or_recovery:
            return _available(
                ExecutionPace.PATIENT_EXIT,
                "The target is zero, but discount and correction/recovery support a patient exit.",
            )
        fast_exit_regime = _contains(snapshot.price_regime, "UPTREND", "EXTENDED", "RECOVERY")
        if fast_exit_regime and is_rich:
            return _available(
                ExecutionPace.TRIM_FASTER,
                "A zero target and rich valuation support a faster trim.",
            )
        if fast_exit_regime:
            momentum, momentum_issue = _momentum_for_rule(snapshot)
            if momentum_issue:
                return _review(momentum_issue)
            assert momentum is not None
            negative_estimates = "NEGATIVE" in momentum
            if negative_estimates:
                return _available(
                    ExecutionPace.TRIM_FASTER,
                    "A zero target and negative estimate revisions support a faster trim.",
                )
        return _available(ExecutionPace.NORMAL_EXIT, "A zero target calls for a normal-paced exit.")

    if is_discount and correction_or_recovery:
        return _available(
            ExecutionPace.PATIENT_TRIM,
            "The position is above a positive target, but discount and correction/recovery "
            "support patient trimming.",
        )
    if is_rich and uptrend_or_extended:
        return _available(
            ExecutionPace.TRIM_FASTER,
            "Rich valuation with an uptrend or extension supports faster trimming.",
        )
    return _available(
        ExecutionPace.NORMAL_TRIM,
        "The position is above its positive target; trim at a normal pace.",
    )


def create_execution_pace_run(
    session: Session, value: s.ExecutionPaceRunCreate
) -> ExecutionPaceRun:
    """Capture a point-in-time portfolio decision run without mutating upstream state."""
    as_of = (value.as_of or datetime.now(UTC)).astimezone(UTC)
    portfolio = session.scalar(
        select(Portfolio).order_by(Portfolio.created_at, Portfolio.id).limit(1)
    )
    if portfolio is None:
        raise ValueError(
            "An application portfolio must exist before Execution Pace can be recorded"
        )

    portfolio_view = queries.overview(session, portfolio.id, as_of)
    contexts = {context.company.id: context for context in portfolio_view.companies}
    companies = list(session.scalars(select(Company).order_by(Company.name, Company.id)))
    lifecycle_rows = session.scalars(
        select(LifecycleEvent)
        .where(
            LifecycleEvent.company_id.in_([company.id for company in companies]),
            LifecycleEvent.effective_at <= as_of,
            LifecycleEvent.recorded_at <= as_of,
        )
        .order_by(
            LifecycleEvent.company_id,
            LifecycleEvent.effective_at.desc(),
            LifecycleEvent.recorded_at.desc(),
        )
    ).all()
    lifecycle_by_company: dict[UUID, Lifecycle] = {}
    for event in lifecycle_rows:
        lifecycle_by_company.setdefault(event.company_id, Lifecycle(event.new_state))
    entries: list[ExecutionPaceDecision] = []
    for company in companies:
        context = contexts.get(company.id)
        lifecycle = lifecycle_by_company.get(company.id)
        if context is None:
            snapshot = _empty_snapshot(lifecycle, None, None, None, None, None)
            result = PaceResult(
                status=ExecutionPaceDecisionStatus.NOT_APPLICABLE,
                pace=None,
                reason="Company has no current holding or explicit target allocation.",
            )
            entries.append(_decision_row(company.id, result, snapshot))
            continue
        estimate = queries.company_estimate_momentum(session, company.id, as_of.date(), as_of)
        return_history = queries.company_expected_return_history(
            session, company.id, as_of.date(), as_of
        )
        model_point, model_issue = _select_current_model_point(
            return_history.history,
            held_listing_ids={position.listing_id for position in context.positions},
        )
        market_rows = queries.company_market_data(
            session, company.id, history_limit=0, market_as_of=as_of.date(), known_at=as_of
        )
        market = next(
            (
                item
                for item in market_rows
                if model_point is not None and item.listing.id == model_point.valuation_listing_id
            ),
            None,
        )
        snapshot = _build_snapshot(
            lifecycle=lifecycle,
            context=context,
            portfolio_view=portfolio_view,
            estimate=estimate,
            model_point=model_point,
            model_issue=model_issue,
            market=market,
            as_of=as_of,
        )
        result = derive_execution_pace(snapshot)
        entries.append(_decision_row(company.id, result, snapshot))

    available = sum(
        item.decision_status == ExecutionPaceDecisionStatus.AVAILABLE for item in entries
    )
    review = sum(item.decision_status == ExecutionPaceDecisionStatus.REVIEW for item in entries)
    unavailable = sum(
        item.decision_status == ExecutionPaceDecisionStatus.UNAVAILABLE for item in entries
    )
    run_status = (
        ExecutionPaceRunStatus.UNAVAILABLE
        if available == 0 and (review > 0 or unavailable > 0)
        else ExecutionPaceRunStatus.PARTIAL
        if review > 0 or unavailable > 0
        else ExecutionPaceRunStatus.COMPLETE
    )
    run = ExecutionPaceRun(
        portfolio_id=portfolio.id,
        as_of=as_of,
        methodology_version=METHODOLOGY_VERSION,
        status=run_status,
        actor=value.actor,
        reason=value.reason,
        source=value.source,
    )
    session.add(run)
    session.flush()
    for entry in entries:
        entry.run_id = run.id
        session.add(entry)
    session.flush()
    return run


def _select_current_model_point(
    history: list[s.ExpectedReturnHistoryPointRead], held_listing_ids: set[UUID]
) -> tuple[s.ExpectedReturnHistoryPointRead | None, str | None]:
    native = [
        point
        for point in history
        if point.source_kind == "NATIVE_MODEL_REVISION" and point.is_current_at_cutoff
    ]
    candidates = native
    if not candidates:
        imported = [point for point in history if point.source_kind == "IMPORTED_CURRENT_CONTRACT"]
        latest_by_series: dict[str, s.ExpectedReturnHistoryPointRead] = {}
        for point in sorted(
            imported,
            key=lambda item: (
                item.effective_at is None,
                item.effective_at or item.recorded_at,
                item.recorded_at,
                item.series_id,
            ),
        ):
            latest_by_series[point.series_id] = point
        candidates = list(latest_by_series.values())
    if len(candidates) > 1 and held_listing_ids:
        held_matches = [
            point for point in candidates if point.valuation_listing_id in held_listing_ids
        ]
        if len(held_matches) == 1:
            candidates = held_matches
    if not candidates:
        return None, "No current native revision or imported current model-output contract exists."
    if len(candidates) != 1:
        return (
            None,
            "Multiple current model/listing candidates exist; no single output is selected.",
        )
    return candidates[0], None


def _build_snapshot(
    *,
    lifecycle: Lifecycle | None,
    context: s.CompanyPortfolioContext,
    portfolio_view: s.PortfolioOverview,
    estimate: s.CompanyEstimateMomentumRead,
    model_point: s.ExpectedReturnHistoryPointRead | None,
    model_issue: str | None,
    market: s.ListingMarketData | None,
    as_of: datetime,
) -> s.ExecutionPaceInputSnapshot:
    notes: list[str] = []
    if model_issue:
        notes.append(model_issue)
    if market is None:
        notes.append("No market-data row matches the model's exact valuation listing.")
    source_id = _model_source_id(model_point)
    latest = market.latest if market else None
    regime = market.price_regime if market else None
    raw_regime = regime.regime if regime else None
    normalized_regime = normalize_price_regime(raw_regime, regime.trend_state if regime else None)
    if regime is not None and normalized_regime is None:
        notes.append("The observed price-regime label is outside the migrated rule mapping.")
    model_price = model_point.market_price if model_point else None
    fair_value = model_point.weighted_fv if model_point else None
    current_price = latest.split_adjusted_close if latest else None
    weighted_upside = (
        fair_value / current_price - Decimal(1)
        if fair_value is not None and current_price is not None and current_price > 0
        else None
    )
    zone = valuation_zone(weighted_upside)
    range_ratio = (
        (model_point.bull_fv - model_point.bear_fv) / fair_value
        if model_point is not None
        and model_point.bull_fv is not None
        and model_point.bear_fv is not None
        and fair_value is not None
        and fair_value > 0
        else None
    )
    price_age = (as_of.date() - latest.market_date.date()).days if latest is not None else None
    regime_age = (as_of.date() - regime.as_of.date()).days if regime is not None else None
    regime_freshness: Literal["FRESH", "STALE", "DATA_CHECK", "NO_DATA"] = (
        "NO_DATA"
        if regime is None
        else "DATA_CHECK"
        if regime.data_quality != "PASS" or regime_age is None or regime_age < 0
        else "STALE"
        if regime_age > 5
        else "FRESH"
    )
    snapshot = s.ExecutionPaceInputSnapshot(
        context_version="execution-pace-inputs-v1",
        lifecycle=lifecycle,
        target_revision_id=portfolio_view.target_revision.id
        if portfolio_view.target_revision
        else None,
        target_effective_at=portfolio_view.target_revision.effective_at
        if portfolio_view.target_revision
        else None,
        holding_snapshot_id=portfolio_view.snapshot.id if portfolio_view.snapshot else None,
        holding_effective_at=portfolio_view.snapshot.effective_at
        if portfolio_view.snapshot
        else None,
        allocation_status=context.allocation_status if portfolio_view.snapshot else None,
        current_weight=context.current_weight,
        target_weight=context.target_weight,
        allocation_gap=context.allocation_gap,
        model_source_kind=(
            "NATIVE_MODEL_REVISION"
            if model_point is not None and model_point.source_kind == "NATIVE_MODEL_REVISION"
            else "IMPORTED_CURRENT_CONTRACT"
            if model_point is not None
            else None
        ),
        model_source_id=source_id,
        model_revision_id=model_point.revision_id if model_point else None,
        model_output_snapshot_id=(
            source_id
            if model_point and model_point.source_kind == "IMPORTED_CURRENT_CONTRACT"
            else None
        ),
        model_key=model_point.model_key if model_point else None,
        return_semantics=model_point.return_semantics if model_point else None,
        model_effective_at=model_point.effective_at if model_point else None,
        model_recorded_at=model_point.recorded_at if model_point else None,
        model_currency=model_point.model_currency if model_point else None,
        model_output_quality=model_point.output_quality if model_point else None,
        model_contract_status=model_point.contract_status if model_point else None,
        model_review_flag=model_point.output_status if model_point else None,
        expected_irr=model_point.expected_cash_flow_irr if model_point else None,
        hurdle=model_point.hurdle if model_point else None,
        valuation_listing_id=model_point.valuation_listing_id if model_point else None,
        valuation_ticker=model_point.valuation_ticker if model_point else None,
        valuation_venue=model_point.valuation_venue if model_point else None,
        valuation_currency=(market.listing.currency if market else None),
        price_observation_id=latest.id if latest else None,
        price_market_date=latest.market_date if latest else None,
        price_recorded_at=latest.recorded_at if latest else None,
        price_currency=latest.currency if latest else None,
        price=current_price,
        price_provider=latest.provider if latest else None,
        price_quality=latest.data_quality if latest else None,
        price_freshness=(market.freshness if market else "NO_DATA"),
        model_price_status=model_price.status if model_price else None,
        model_price_effective_at=model_price.effective_at if model_price else None,
        model_price_observation_id=model_price.observation_id if model_price else None,
        model_reference_price=model_price.model_reference_price if model_price else None,
        model_price_currency=model_price.model_currency if model_price else None,
        weighted_fair_value=fair_value,
        weighted_upside=weighted_upside,
        valuation_zone=zone,
        valuation_range_ratio=range_ratio,
        estimate_momentum_availability=estimate.availability,
        estimate_momentum_direction=estimate.direction,
        estimate_momentum_freshness=estimate.freshness,
        estimate_momentum_quality=estimate.data_quality,
        estimate_provider_id=estimate.provider_id,
        estimate_latest_snapshot_date=estimate.latest_snapshot_date,
        estimate_momentum_reason=estimate.reason,
        price_regime_source_ref=regime.source_ref if regime else None,
        price_regime_as_of=regime.as_of if regime else None,
        price_regime_quality=regime.data_quality if regime else None,
        price_regime_raw=raw_regime,
        price_regime=normalized_regime,
        price_regime_freshness=regime_freshness,
        context_notes=notes,
    )
    # Retain a concrete stale-price note for users and auditors.
    if (
        market is not None
        and market.freshness == "FRESH"
        and price_age is not None
        and price_age > 5
    ):
        snapshot.context_notes.append("The quote is older than the five-day freshness limit.")
    return snapshot


def _model_source_id(point: s.ExpectedReturnHistoryPointRead | None) -> UUID | None:
    if point is None:
        return None
    if point.source_kind == "NATIVE_MODEL_REVISION":
        return point.revision_id
    if point.point_id.startswith("imported:"):
        try:
            return UUID(point.point_id.removeprefix("imported:"))
        except ValueError:
            return None
    return None


def _empty_snapshot(
    lifecycle: Lifecycle | None,
    current_weight: Decimal | None,
    target_weight: Decimal | None,
    allocation_gap: Decimal | None,
    target_revision_id: UUID | None,
    holding_snapshot_id: UUID | None,
) -> s.ExecutionPaceInputSnapshot:
    return s.ExecutionPaceInputSnapshot(
        context_version="execution-pace-inputs-v1",
        lifecycle=lifecycle,
        target_revision_id=target_revision_id,
        target_effective_at=None,
        holding_snapshot_id=holding_snapshot_id,
        holding_effective_at=None,
        allocation_status=None,
        current_weight=current_weight,
        target_weight=target_weight,
        allocation_gap=allocation_gap,
        model_source_kind=None,
        model_source_id=None,
        model_revision_id=None,
        model_output_snapshot_id=None,
        model_key=None,
        return_semantics=None,
        model_effective_at=None,
        model_recorded_at=None,
        model_currency=None,
        model_output_quality=None,
        model_contract_status=None,
        model_review_flag=None,
        expected_irr=None,
        hurdle=None,
        valuation_listing_id=None,
        valuation_ticker=None,
        valuation_venue=None,
        valuation_currency=None,
        price_observation_id=None,
        price_market_date=None,
        price_recorded_at=None,
        price_currency=None,
        price=None,
        price_provider=None,
        price_quality=None,
        price_freshness="NO_DATA",
        model_price_status=None,
        model_price_effective_at=None,
        model_price_observation_id=None,
        model_reference_price=None,
        model_price_currency=None,
        weighted_fair_value=None,
        weighted_upside=None,
        valuation_zone=None,
        valuation_range_ratio=None,
        estimate_momentum_availability=None,
        estimate_momentum_direction=None,
        estimate_momentum_freshness=None,
        estimate_momentum_quality=None,
        estimate_provider_id=None,
        estimate_latest_snapshot_date=None,
        estimate_momentum_reason=None,
        price_regime_source_ref=None,
        price_regime_as_of=None,
        price_regime_quality=None,
        price_regime_raw=None,
        price_regime=None,
        price_regime_freshness="NO_DATA",
        context_notes=[],
    )


def _decision_row(
    company_id: UUID, result: PaceResult, snapshot: s.ExecutionPaceInputSnapshot
) -> ExecutionPaceDecision:
    return ExecutionPaceDecision(
        company_id=company_id,
        target_revision_id=snapshot.target_revision_id,
        holding_snapshot_id=snapshot.holding_snapshot_id,
        model_revision_id=snapshot.model_revision_id,
        model_output_snapshot_id=snapshot.model_output_snapshot_id,
        price_observation_id=snapshot.price_observation_id,
        decision_status=result.status,
        pace=result.pace,
        reason=result.reason,
        input_snapshot=snapshot.model_dump(mode="json"),
    )


def _review(reason: str) -> PaceResult:
    return PaceResult(ExecutionPaceDecisionStatus.REVIEW, None, reason)


def _available(pace: ExecutionPace, reason: str) -> PaceResult:
    return PaceResult(ExecutionPaceDecisionStatus.AVAILABLE, pace, reason)


def _contains(value: str | None, *parts: str) -> bool:
    normalized = (value or "").upper()
    return any(part in normalized for part in parts)


def _momentum_for_rule(snapshot: s.ExecutionPaceInputSnapshot) -> tuple[str | None, str | None]:
    """Return the estimate state only for branches whose documented rule consumes it."""
    if snapshot.estimate_momentum_availability not in {"AVAILABLE", "DIRECTION_ONLY"}:
        return None, "Estimate Momentum has no usable point-in-time history for this branch."
    if snapshot.estimate_momentum_freshness != "FRESH":
        return None, "Estimate Momentum is stale or has a freshness data check."
    if snapshot.estimate_momentum_quality != "PASS":
        return None, "Estimate Momentum source quality is not PASS."
    if snapshot.estimate_momentum_availability == "AVAILABLE":
        if snapshot.estimate_momentum_direction is None:
            return None, "Available Estimate Momentum has no direction."
        return snapshot.estimate_momentum_direction.replace("_MIXED", ""), None
    # The workbook maps its low-confidence, observed state to COLLECTING.
    # No observation history is not equivalent to that explicit state.
    return "COLLECTING", None
