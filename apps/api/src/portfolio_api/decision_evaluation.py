"""Point-in-time diagnostics for model scenarios and immutable decision snapshots."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api import forecast_accuracy
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    ExecutionPaceDecision,
    ExecutionPaceRun,
    ForecastAccuracySourceType,
    Listing,
    ModelOutputSnapshot,
    RankingDefinition,
    RankingEntry,
    RankingRun,
    RankingType,
    Security,
)
from portfolio_api.domain.services import company as require_company
from portfolio_api.temporal_alignment import snapshot_market_return

MINIMUM_CROSS_SECTION_SAMPLE = 5
MAX_SIGNAL_RUNS_PER_TYPE = 10
MAX_SCENARIO_GROUPS = 60
DEFAULT_HORIZONS_DAYS = (365, 1095)


@dataclass(frozen=True)
class _Signal:
    signal_type: str
    signal_id: UUID
    run_id: UUID
    run_as_of: datetime
    recorded_at: datetime
    source_methodology: str
    status: str
    value: str | None
    position: int | None
    expected_irr: Decimal | None
    return_methodology: dict[str, Any] | None
    listing: Listing | None
    model_currency: str | None
    price_observation_id: UUID | None
    estimate_momentum_direction: str | None = None
    estimate_momentum_availability: str | None = None
    estimate_momentum_freshness: str | None = None
    estimate_momentum_quality: str | None = None
    reason: str = ""


def discrete_crps(scenarios: list[tuple[Decimal, Decimal]], actual: Decimal) -> Decimal:
    """Continuous ranked probability score for a finite numeric distribution."""
    if not scenarios:
        raise ValueError("At least one scenario is required")
    if any(probability < 0 for _, probability in scenarios):
        raise ValueError("Scenario probabilities cannot be negative")
    if abs(sum((probability for _, probability in scenarios), Decimal(0)) - Decimal(1)) > Decimal(
        "0.00000001"
    ):
        raise ValueError("Scenario probabilities must sum to one")
    first_term = sum(
        (probability * abs(value - actual) for value, probability in scenarios), Decimal(0)
    )
    pair_term = sum(
        (
            left_probability * right_probability * abs(left_value - right_value)
            for left_value, left_probability in scenarios
            for right_value, right_probability in scenarios
        ),
        Decimal(0),
    ) / Decimal(2)
    return first_term - pair_term


def _average_ranks(values: list[Decimal]) -> list[Decimal]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [Decimal(0)] * len(values)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        average_rank = (Decimal(index + 1) + Decimal(end)) / Decimal(2)
        for item in order[index:end]:
            ranks[item] = average_rank
        index = end
    return ranks


def spearman_correlation(left: list[Decimal], right: list[Decimal]) -> Decimal | None:
    """Spearman rho with average ranks for ties; no statistic for fewer than two pairs."""
    if len(left) != len(right) or len(left) < 2:
        return None
    x = _average_ranks(left)
    y = _average_ranks(right)
    mean_x = sum(x, Decimal(0)) / Decimal(len(x))
    mean_y = sum(y, Decimal(0)) / Decimal(len(y))
    centered_x = [value - mean_x for value in x]
    centered_y = [value - mean_y for value in y]
    variance_x = sum((value * value for value in centered_x), Decimal(0))
    variance_y = sum((value * value for value in centered_y), Decimal(0))
    if variance_x == 0 or variance_y == 0:
        return None
    covariance = sum((a * b for a, b in zip(centered_x, centered_y, strict=True)), Decimal(0))
    return covariance / (variance_x * variance_y).sqrt()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Evaluation timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _scenario_evaluations(
    session: Session, company_id: UUID, outcome_known_at: datetime
) -> list[s.ScenarioEvaluationRead]:
    history = forecast_accuracy.company_forecast_accuracy(
        session,
        company_id,
        source=ForecastAccuracySourceType.FINANCIAL_MODEL,
        outcome_known_at=outcome_known_at,
        limit=500,
    )
    groups: dict[tuple[UUID, str, int], list[s.ForecastAccuracyObservationRead]] = defaultdict(list)
    for row in history.observations:
        if row.revision_id is not None and row.forecast_year is not None:
            groups[(row.revision_id, row.metric.value, row.forecast_year)].append(row)

    result: list[s.ScenarioEvaluationRead] = []
    for rows in groups.values():
        first = rows[0]
        if (
            first.model_type is None
            or first.revision_id is None
            or first.revision_number is None
            or first.forecast_year is None
            or first.forecast_known_at is None
        ):
            continue
        by_scenario: dict[str, s.ForecastAccuracyObservationRead] = {}
        for row in rows:
            if row.scenario is not None:
                by_scenario.setdefault(row.scenario, row)
        scenarios = [
            s.ScenarioForecastPointRead(
                scenario=name,
                probability=by_scenario[name].scenario_probability,
                value=by_scenario[name].value,
            )
            for name in ("BEAR", "BASE", "BULL")
            if name in by_scenario
        ]
        actual = first.actual
        score_status = "NOT_EVALUATED"
        score: Decimal | None = None
        reason: str | None = None
        ordered_rows = [by_scenario.get(name) for name in ("BEAR", "BASE", "BULL")]
        if any(row is None for row in ordered_rows):
            reason = "All three explicit Bear/Base/Bull projections are required."
        else:
            complete_rows = [row for row in ordered_rows if row is not None]
            metadata = {
                (row.currency, row.unit, row.metric, row.forecast_year) for row in complete_rows
            }
            if len(metadata) != 1:
                score_status = "DATA_CHECK"
                reason = "Scenario units, currency, metric, or forecast period do not match."
            elif any(
                row.value is None or row.scenario_probability is None for row in complete_rows
            ):
                reason = "A scenario value or probability is unavailable."
            elif any(row.error.status != "AVAILABLE" for row in complete_rows):
                statuses = sorted({row.status for row in complete_rows})
                reason = (
                    "Scenario outcome cannot be scored: "
                    + ", ".join(statuses)
                    + ". "
                    + (first.status_reason or first.actual.reason or "")
                ).strip()
            elif actual.value is None or actual.data_quality != "PASS":
                reason = actual.reason or "A later, quality-passing actual is unavailable."
            elif actual.currency != first.currency or actual.unit != first.unit:
                score_status = "DATA_CHECK"
                reason = (
                    "Forecast and actual currency/unit do not match; no conversion is inferred."
                )
            else:
                try:
                    score = discrete_crps(
                        [
                            (row.value, row.scenario_probability)
                            for row in complete_rows
                            if row.value is not None and row.scenario_probability is not None
                        ],
                        actual.value,
                    )
                    score_status = "AVAILABLE"
                except ValueError as error:
                    score_status = "DATA_CHECK"
                    reason = str(error)
        if (
            all(row is not None for row in ordered_rows)
            and first.fiscal_year is None
            and score_status == "NOT_EVALUATED"
        ):
            # Model year 1, 2, ... is not an annual fiscal-period identity.
            reason = (
                "Ordinal model years have no documented fiscal-period anchor, so later "
                "reported facts cannot be joined without inventing a mapping."
            )
        result.append(
            s.ScenarioEvaluationRead(
                model_name=first.source_name,
                model_type=first.model_type,
                methodology_version=first.methodology_version,
                revision_id=first.revision_id,
                revision_number=first.revision_number,
                forecast_known_at=first.forecast_known_at,
                metric=first.metric,
                forecast_year=first.forecast_year,
                fiscal_year=first.fiscal_year,
                fiscal_period=first.fiscal_period,
                period_end=first.period_end,
                currency=first.currency,
                unit=first.unit,
                scenarios=scenarios,
                actual_status=actual.status,
                actual_value=actual.value,
                actual_published_at=actual.published_at,
                actual_observed_at=actual.observed_at,
                actual_recorded_at=actual.recorded_at,
                score_status=score_status,
                continuous_ranked_probability_score=score,
                probability_calibration_status="NOT_ESTIMABLE_NO_OUTCOME_EVENT_DEFINITION",
                reason=reason,
            )
        )
    result.sort(
        key=lambda row: (row.forecast_known_at, row.revision_number, row.forecast_year),
        reverse=True,
    )
    return result[:MAX_SCENARIO_GROUPS]


def _valuation_scenarios(
    session: Session, company_id: UUID, cutoff: datetime
) -> list[s.ValuationScenarioContextRead]:
    snapshots = session.scalars(
        select(ModelOutputSnapshot)
        .where(
            ModelOutputSnapshot.company_id == company_id,
            ModelOutputSnapshot.recorded_at <= cutoff,
            ModelOutputSnapshot.effective_at.is_(None)
            | (ModelOutputSnapshot.effective_at <= cutoff),
        )
        .order_by(ModelOutputSnapshot.recorded_at.desc(), ModelOutputSnapshot.id.desc())
        .limit(20)
    ).all()
    result = []
    for item in snapshots:
        methodology = item.return_methodology
        result.append(
            s.ValuationScenarioContextRead(
                snapshot_id=item.id,
                model_key=item.model_key,
                snapshot_kind=item.snapshot_kind,
                snapshot_status=item.output_quality,
                methodology=methodology.code if methodology else None,
                methodology_version=methodology.version if methodology else None,
                currency=item.model_currency,
                bear_fair_value=item.bear_fv,
                bear_probability=item.bear_probability,
                base_fair_value=item.base_fv,
                base_probability=item.base_probability,
                bull_fair_value=item.bull_fv,
                bull_probability=item.bull_probability,
                effective_at=item.effective_at,
                recorded_at=item.recorded_at,
                source=item.source,
                evaluation_status="NOT_FIXED_HORIZON",
                reason=(
                    "Fair Value is a valuation reference, not a fixed-date stock-price forecast; "
                    "no price-target accuracy score is assigned."
                ),
            )
        )
    return result


def _source_parts(snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source = snapshot.get("model_source") or snapshot.get("return_source") or {}
    if not isinstance(source, dict):
        source = {}
    method = source.get("return_methodology")
    return source, method if isinstance(method, dict) else {}


def _ranking_signal(
    session: Session,
    run: RankingRun,
    definition: RankingDefinition,
    entry: RankingEntry,
) -> _Signal:
    snapshot = entry.input_snapshot or {}
    source, method = _source_parts(snapshot)
    listing_id = _uuid(source.get("listing_id") or snapshot.get("listing_id"))
    listing = session.get(Listing, listing_id) if listing_id else None
    if listing is not None:
        security = session.get(Security, listing.security_id)
        if security is None or security.company_id != entry.company_id:
            listing = None
    return _Signal(
        signal_type=f"{definition.ranking_type}_RANK",
        signal_id=entry.id,
        run_id=run.id,
        run_as_of=run.as_of,
        recorded_at=run.recorded_at,
        source_methodology=f"{definition.ranking_type.title()} Rank v{definition.version}",
        status=entry.status,
        value=str(entry.position) if entry.position is not None else None,
        position=entry.position,
        expected_irr=_decimal(snapshot.get("expected_irr")),
        return_methodology=method,
        listing=listing,
        model_currency=(str(source["model_currency"]) if source.get("model_currency") else None),
        price_observation_id=_uuid(
            snapshot.get("price_observation_id") or source.get("price_observation_id")
        ),
        reason=entry.reason,
    )


def _execution_signal(
    session: Session,
    run: ExecutionPaceRun,
    decision: ExecutionPaceDecision,
) -> _Signal:
    snapshot = decision.input_snapshot
    listing_id = _uuid(snapshot.get("valuation_listing_id"))
    listing = session.get(Listing, listing_id) if listing_id else None
    if listing is not None:
        security = session.get(Security, listing.security_id)
        if security is None or security.company_id != decision.company_id:
            listing = None
    return _Signal(
        signal_type="EXECUTION_PACE",
        signal_id=decision.id,
        run_id=run.id,
        run_as_of=run.as_of,
        recorded_at=run.recorded_at,
        source_methodology=f"Execution Pace {run.methodology_version}",
        status=decision.decision_status,
        value=decision.pace,
        position=None,
        expected_irr=_decimal(snapshot.get("expected_irr")),
        return_methodology=None,
        listing=listing,
        model_currency=(
            str(snapshot["model_currency"]) if snapshot.get("model_currency") else None
        ),
        price_observation_id=decision.price_observation_id,
        estimate_momentum_direction=_string(snapshot.get("estimate_momentum_direction")),
        estimate_momentum_availability=_string(snapshot.get("estimate_momentum_availability")),
        estimate_momentum_freshness=_string(snapshot.get("estimate_momentum_freshness")),
        estimate_momentum_quality=_string(snapshot.get("estimate_momentum_quality")),
        reason=decision.reason,
    )


def _outcome_read(
    session: Session,
    signal: _Signal,
    horizon_days: int,
    cutoff: datetime,
) -> s.DecisionOutcomeRead:
    if signal.listing is None:
        market_return = None
        start = end = None
        status = "EXACT_LISTING_UNAVAILABLE"
        reason: str | None = (
            "No exact valuation listing was retained in the immutable signal snapshot."
        )
        target_date = signal.run_as_of.date()
    else:
        evidence = snapshot_market_return(
            session,
            listing_id=signal.listing.id,
            start_observation_id=signal.price_observation_id,
            signal_as_of=signal.run_as_of,
            signal_recorded_at=signal.recorded_at,
            horizon_days=horizon_days,
            outcome_known_at=cutoff,
        )
        market_return = evidence.result
        start, end = evidence.start, evidence.end
        status = market_return.status
        reason = market_return.reason
        target_date = market_return.target_date

    annualized = None
    if market_return is not None and market_return.return_fraction is not None:
        days = market_return.actual_days
        if days and days > 0:
            try:
                gross = Decimal(1) + market_return.return_fraction
                annualized = gross ** (Decimal(365) / Decimal(days)) - Decimal(1)
            except (InvalidOperation, ValueError):
                annualized = None
    return s.DecisionOutcomeRead(
        horizon_days=horizon_days,
        status=status,
        target_date=target_date,
        start_market_date=market_return.start_market_date if market_return else None,
        end_market_date=market_return.end_market_date if market_return else None,
        total_return=market_return.return_fraction if market_return else None,
        annualized_return=annualized,
        basis="PROVIDER_TOTAL_RETURN_CLOSE" if market_return else "UNAVAILABLE",
        start_observation_id=start.id if start else None,
        end_observation_id=end.id if end else None,
        start_provider=start.provider if start else None,
        end_provider=end.provider if end else None,
        currency=start.currency if start else (signal.listing.currency if signal.listing else None),
        reason=reason,
    )


def _signal_read(
    session: Session,
    signal: _Signal,
    horizons: list[int],
    cutoff: datetime,
) -> s.DecisionSignalEvaluationRead:
    return s.DecisionSignalEvaluationRead(
        signal_type=signal.signal_type,
        signal_id=signal.signal_id,
        run_id=signal.run_id,
        run_as_of=signal.run_as_of,
        recorded_at=signal.recorded_at,
        source_methodology=signal.source_methodology,
        status=signal.status,
        value=signal.value,
        position=signal.position,
        expected_irr=signal.expected_irr,
        return_methodology=str(signal.return_methodology.get("code"))
        if signal.return_methodology and signal.return_methodology.get("code")
        else None,
        return_methodology_version=int(signal.return_methodology["version"])
        if signal.return_methodology and signal.return_methodology.get("version") is not None
        else None,
        return_perspective=str(signal.return_methodology.get("perspective"))
        if signal.return_methodology and signal.return_methodology.get("perspective")
        else None,
        valuation_listing_id=signal.listing.id if signal.listing else None,
        valuation_ticker=signal.listing.ticker if signal.listing else None,
        valuation_venue=signal.listing.venue if signal.listing else None,
        listing_currency=signal.listing.currency if signal.listing else None,
        model_currency=signal.model_currency,
        estimate_momentum_direction=signal.estimate_momentum_direction,
        estimate_momentum_availability=signal.estimate_momentum_availability,
        estimate_momentum_freshness=signal.estimate_momentum_freshness,
        estimate_momentum_quality=signal.estimate_momentum_quality,
        price_observation_id=signal.price_observation_id,
        outcomes=[_outcome_read(session, signal, horizon, cutoff) for horizon in horizons],
        reason=signal.reason,
    )


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _summary(
    *,
    signal_type: str,
    run_id: UUID,
    run_as_of: datetime,
    source_methodology: str,
    horizon_days: int,
    grouping: str,
    group_value: str,
    currency: str | None,
    returns: list[Decimal],
    left_values: list[Decimal] | None = None,
    right_values: list[Decimal] | None = None,
    reverse_correlation: bool = False,
    interpretation: str,
) -> s.DecisionEvaluationSummaryRead:
    count = len(returns)
    status = "AVAILABLE" if count >= MINIMUM_CROSS_SECTION_SAMPLE else "INSUFFICIENT_SAMPLE"
    correlation = None
    mean = median = None
    if status == "AVAILABLE":
        mean = sum(returns, Decimal(0)) / Decimal(count)
        median = _median(returns)
        if left_values is not None and right_values is not None:
            correlation = spearman_correlation(left_values, right_values)
            if reverse_correlation and correlation is not None:
                correlation = -correlation
            if correlation is None:
                status = "INSUFFICIENT_VARIATION"
    return s.DecisionEvaluationSummaryRead(
        signal_type=signal_type,
        run_id=run_id,
        run_as_of=run_as_of,
        source_methodology=source_methodology,
        horizon_days=horizon_days,
        grouping=grouping,
        group_value=group_value,
        listing_currency=currency,
        sample_count=count,
        minimum_sample_count=MINIMUM_CROSS_SECTION_SAMPLE,
        status=status,
        spearman_correlation=correlation,
        mean_annualized_return=mean,
        median_annualized_return=median,
        interpretation=interpretation,
    )


def _summaries(
    signals_by_run: dict[UUID, list[_Signal]],
    outcomes_by_signal: dict[tuple[UUID, int], s.DecisionOutcomeRead],
    horizons: list[int],
    run_info: dict[UUID, tuple[datetime, str]],
) -> list[s.DecisionEvaluationSummaryRead]:
    result: list[s.DecisionEvaluationSummaryRead] = []
    for run_id, signals in signals_by_run.items():
        run_as_of, source_methodology = run_info[run_id]
        for horizon in horizons:
            available = [
                (signal, outcomes_by_signal[(signal.signal_id, horizon)])
                for signal in signals
                if (signal.signal_id, horizon) in outcomes_by_signal
                and outcomes_by_signal[(signal.signal_id, horizon)].status == "AVAILABLE"
                and outcomes_by_signal[(signal.signal_id, horizon)].annualized_return is not None
            ]
            grouped: dict[tuple[str, str, str | None], list[tuple[_Signal, Decimal]]] = defaultdict(
                list
            )
            for signal, outcome in available:
                assert outcome.annualized_return is not None
                currency = signal.listing.currency if signal.listing else None
                method = signal.return_methodology or {}
                method_key = (
                    f"{method.get('code')}@{method.get('version')}"
                    if method.get("code") is not None
                    else "UNCLASSIFIED"
                )
                if signal.signal_type.endswith("_RANK") and signal.status == "RANKED":
                    group_key = ("RANK_POSITION", method_key, currency)
                    grouped[group_key].append((signal, outcome.annualized_return))
                    if (
                        signal.expected_irr is not None
                        and method.get("perspective") == "EQUITY"
                        and signal.model_currency == currency
                        and signal.price_observation_id is not None
                    ):
                        irr_key = ("EXPECTED_IRR", method_key, currency)
                        grouped[irr_key].append((signal, outcome.annualized_return))
                elif signal.signal_type == "EXECUTION_PACE" and signal.status == "AVAILABLE":
                    grouped[("EXECUTION_PACE", signal.value or "UNKNOWN", currency)].append(
                        (signal, outcome.annualized_return)
                    )
                    if (
                        signal.estimate_momentum_direction
                        and signal.estimate_momentum_availability in {"AVAILABLE", "DIRECTION_ONLY"}
                        and signal.estimate_momentum_freshness == "FRESH"
                        and signal.estimate_momentum_quality == "PASS"
                        and signal.price_observation_id is not None
                    ):
                        grouped[
                            (
                                "ESTIMATE_MOMENTUM",
                                f"{signal.estimate_momentum_direction} · {method_key}",
                                currency,
                            )
                        ].append((signal, outcome.annualized_return))

            for (grouping, group_value, currency), pairs in grouped.items():
                returns = [value for _, value in pairs]
                if grouping == "RANK_POSITION":
                    result.append(
                        _summary(
                            signal_type="RANK_RETURN_ASSOCIATION",
                            run_id=run_id,
                            run_as_of=run_as_of,
                            source_methodology=source_methodology,
                            horizon_days=horizon,
                            grouping="RETURN_METHOD_AND_LISTING_CURRENCY",
                            group_value=group_value,
                            currency=currency,
                            returns=returns,
                            left_values=[Decimal(signal.position or 0) for signal, _ in pairs],
                            right_values=returns,
                            reverse_correlation=True,
                            interpretation=(
                                "Cross-sectional association only; positive rho means better rank "
                                "positions coincided with higher realized returns."
                            ),
                        )
                    )
                elif grouping == "EXPECTED_IRR":
                    result.append(
                        _summary(
                            signal_type="EXPECTED_IRR_RETURN_ASSOCIATION",
                            run_id=run_id,
                            run_as_of=run_as_of,
                            source_methodology=source_methodology,
                            horizon_days=horizon,
                            grouping="EXACT_EQUITY_METHOD_AND_MODEL_CURRENCY",
                            group_value=group_value,
                            currency=currency,
                            returns=returns,
                            left_values=[signal.expected_irr or Decimal(0) for signal, _ in pairs],
                            right_values=returns,
                            interpretation=(
                                "Cross-sectional association only, limited to exact equity return "
                                "method/version and model currency. It is not a causal estimate."
                            ),
                        )
                    )
                elif grouping in {"EXECUTION_PACE", "ESTIMATE_MOMENTUM"}:
                    result.append(
                        _summary(
                            signal_type=f"{grouping}_OUTCOME",
                            run_id=run_id,
                            run_as_of=run_as_of,
                            source_methodology=source_methodology,
                            horizon_days=horizon,
                            grouping="EXACT_SIGNAL_STATE_AND_LISTING_CURRENCY",
                            group_value=group_value,
                            currency=currency,
                            returns=returns,
                            interpretation=(
                                "Descriptive outcome distribution only; it does not establish "
                                "timing skill or causation."
                            ),
                        )
                    )
    return result


def company_decision_evaluation(
    session: Session,
    company_id: UUID,
    *,
    outcome_known_at: datetime | None = None,
    horizons_days: list[int] | None = None,
) -> s.CompanyDecisionEvaluationRead:
    """Read historical scenarios and decision snapshots without changing canonical state."""
    require_company(session, company_id)
    cutoff = _utc(outcome_known_at or datetime.now(UTC))
    if cutoff > datetime.now(UTC):
        raise ValueError("outcome_known_at cannot be in the future")
    horizons = horizons_days or list(DEFAULT_HORIZONS_DAYS)
    if not horizons or len(horizons) > 3 or len(set(horizons)) != len(horizons):
        raise ValueError("Provide one to three distinct outcome horizons")
    if any(horizon < 1 or horizon > 3650 for horizon in horizons):
        raise ValueError("horizons_days must be between 1 and 3650")

    company_rank_rows = session.execute(
        select(RankingRun, RankingDefinition, RankingEntry)
        .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
        .join(RankingEntry, RankingEntry.run_id == RankingRun.id)
        .where(
            RankingEntry.company_id == company_id,
            RankingDefinition.ranking_type.in_([RankingType.PORTFOLIO, RankingType.WATCHLIST]),
            RankingRun.as_of <= cutoff,
            RankingRun.recorded_at <= cutoff,
        )
        .order_by(RankingRun.as_of.desc(), RankingRun.recorded_at.desc())
    ).all()
    selected_rank_rows: list[tuple[RankingRun, RankingDefinition, RankingEntry]] = []
    rank_counts: dict[str, int] = defaultdict(int)
    for row in company_rank_rows:
        ranking_type = str(row[1].ranking_type)
        if rank_counts[ranking_type] < MAX_SIGNAL_RUNS_PER_TYPE:
            selected_rank_rows.append(row)
            rank_counts[ranking_type] += 1
    selected_run_ids = {run.id for run, _, _ in selected_rank_rows}
    peer_entries = (
        session.scalars(select(RankingEntry).where(RankingEntry.run_id.in_(selected_run_ids))).all()
        if selected_run_ids
        else []
    )
    definitions_by_id = {definition.id: definition for _, definition, _ in selected_rank_rows}
    rank_runs = {run.id: run for run, _, _ in selected_rank_rows}
    ranking_signals = [
        _ranking_signal(
            session,
            rank_runs[entry.run_id],
            definitions_by_id[rank_runs[entry.run_id].definition_id],
            entry,
        )
        for entry in peer_entries
        if entry.run_id in rank_runs
    ]
    company_rank_signals = [
        _ranking_signal(session, run, definition, entry)
        for run, definition, entry in selected_rank_rows
    ]

    company_pace_rows = session.execute(
        select(ExecutionPaceRun, ExecutionPaceDecision)
        .join(ExecutionPaceDecision, ExecutionPaceDecision.run_id == ExecutionPaceRun.id)
        .where(
            ExecutionPaceDecision.company_id == company_id,
            ExecutionPaceRun.as_of <= cutoff,
            ExecutionPaceRun.recorded_at <= cutoff,
        )
        .order_by(ExecutionPaceRun.as_of.desc(), ExecutionPaceRun.recorded_at.desc())
    ).all()[:MAX_SIGNAL_RUNS_PER_TYPE]
    pace_run_ids = {run.id for run, _ in company_pace_rows}
    peer_decisions = (
        session.execute(
            select(ExecutionPaceRun, ExecutionPaceDecision)
            .join(ExecutionPaceDecision, ExecutionPaceDecision.run_id == ExecutionPaceRun.id)
            .where(ExecutionPaceRun.id.in_(pace_run_ids))
        ).all()
        if pace_run_ids
        else []
    )
    pace_signals = [_execution_signal(session, run, decision) for run, decision in peer_decisions]
    company_pace_signals = [
        _execution_signal(session, run, decision) for run, decision in company_pace_rows
    ]

    all_signals = ranking_signals + pace_signals
    outcomes_by_signal: dict[tuple[UUID, int], s.DecisionOutcomeRead] = {}
    for signal in all_signals:
        for horizon in horizons:
            outcomes_by_signal[(signal.signal_id, horizon)] = _outcome_read(
                session, signal, horizon, cutoff
            )
    company_signal_reads = [
        _signal_read(session, signal, horizons, cutoff)
        for signal in company_rank_signals + company_pace_signals
    ]
    signals_by_run: dict[UUID, list[_Signal]] = defaultdict(list)
    run_info: dict[UUID, tuple[datetime, str]] = {}
    for signal in all_signals:
        signals_by_run[signal.run_id].append(signal)
        run_info[signal.run_id] = (signal.run_as_of, signal.source_methodology)

    return s.CompanyDecisionEvaluationRead(
        company_id=company_id,
        outcome_known_at=cutoff,
        horizon_days=horizons,
        minimum_cross_section_sample=MINIMUM_CROSS_SECTION_SAMPLE,
        scenario_evaluations=_scenario_evaluations(session, company_id, cutoff),
        valuation_scenarios=_valuation_scenarios(session, company_id, cutoff),
        signals=company_signal_reads,
        summaries=_summaries(signals_by_run, outcomes_by_signal, horizons, run_info),
        portfolio_implementation_status="NOT_AVAILABLE_NO_TRANSACTION_LEDGER",
        portfolio_implementation_reason=(
            "Holdings snapshots and targets do not establish transaction timing, cash flows, "
            "or implementation returns. No transaction ledger is available for this analysis."
        ),
        limitations=[
            (
                "Research Rank is excluded because it prioritizes research attention, "
                "not investment returns."
            ),
            (
                "Expected IRR comparisons require the same equity method/version and "
                "model currency. Enterprise IRR is not bridged to share returns."
            ),
            (
                "Returns use exact-listing provider total-return closes in listing currency; "
                "cross-currency comparisons are not made."
            ),
            (
                "Provider-adjusted total-return history may include unverified dividend/action "
                "handling; source providers and observation IDs remain visible."
            ),
            (
                "Snapshot associations are descriptive and do not establish that a rank, pace, "
                "or estimate revision caused an outcome."
            ),
            (
                "Model-year projections need explicit fiscal periods; Fair Value is never scored "
                "as a fixed-date price target."
            ),
            (
                "Probability calibration needs a defined outcome event. CRPS requires complete, "
                "fiscal-period-aligned numeric scenarios."
            ),
            (
                "Portfolio implementation returns need transaction-level holdings and "
                "cash-flow history, which is unavailable."
            ),
        ],
    )
