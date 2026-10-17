"""Point-in-time accuracy comparisons over canonical forecast and actual records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.domain.consensus_policy import select_consensus_source
from portfolio_api.domain.models import (
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
    DcfProjection,
    DcfScenarioAssumptions,
    FinancialModel,
    FinancialModelRevision,
    FinancialModelType,
    ForecastAccuracyMetric,
    ForecastAccuracySourceType,
    FundamentalMetric,
    OwnerCashFlowProjection,
    OwnerCashFlowScenarioAssumptions,
    ResearchForecast,
    ResearchRevision,
    ResidualIncomeProjection,
    ResidualIncomeScenarioAssumptions,
    now,
)

MIN_AGGREGATE_SAMPLE_COUNT = 5
METRIC_ORDER = (
    ForecastAccuracyMetric.REVENUE,
    ForecastAccuracyMetric.EPS,
    ForecastAccuracyMetric.EBIT,
    ForecastAccuracyMetric.EBITDA,
    ForecastAccuracyMetric.FREE_CASH_FLOW,
)


@dataclass(frozen=True)
class ForecastCandidate:
    source_type: ForecastAccuracySourceType
    source_name: str
    source_reference: str | None
    author_id: str | None
    stream_key: str | None
    methodology: str | None
    methodology_version: str | None
    model_type: str | None
    scenario: str | None
    scenario_probability: Decimal | None
    forecast_id: UUID | None
    revision_id: UUID | None
    revision_number: int | None
    supersedes_revision_id: UUID | None
    supersedes_observation_id: UUID | None
    metric: ForecastAccuracyMetric
    period_type: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    forecast_period_label: str | None
    period_end: date | None
    forecast_year: int | None
    forecast_basis: str | None
    value: Decimal | None
    currency: str | None
    unit: str | None
    confidence: str | None
    analyst_count: int | None
    observed_at: datetime | None
    effective_at: datetime | None
    recorded_at: datetime | None
    forecast_known_at: datetime | None
    status: str
    status_reason: str | None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone offset")
    return value.astimezone(UTC)


def _latest_known_time(observed_at: datetime | None, recorded_at: datetime) -> datetime:
    recorded = _utc(recorded_at)
    return max(_utc(observed_at), recorded) if observed_at is not None else recorded


def _candidate_status(candidate: ForecastCandidate) -> tuple[str, str | None]:
    if candidate.status != "AVAILABLE":
        return candidate.status, candidate.status_reason
    if candidate.source_type == ForecastAccuracySourceType.FINANCIAL_MODEL:
        if candidate.forecast_basis in {
            "UNLEVERED_FREE_CASH_FLOW",
            "OWNER_CASH_FLOW",
            "NET_INCOME_PER_SHARE",
        }:
            return (
                "MODEL_BASIS_NOT_COMPARABLE",
                "The method-specific projected cash-flow/share basis is not an exact "
                "reported metric bridge.",
            )
        return (
            "SCENARIO_NOT_EVALUATED",
            "Scenario-conditional model projections are not scored as point forecasts; "
            "the method also lacks a fiscal-year anchor.",
        )
    if candidate.scenario not in (None, "POINT"):
        return (
            "SCENARIO_NOT_EVALUATED",
            "Conditional Bear/Base/Bull research scenarios are not scored as point forecasts.",
        )
    if candidate.value is None:
        return "FORECAST_UNAVAILABLE", "The source did not publish a usable numeric forecast."
    if candidate.period_type is None or (
        candidate.period_end is None
        and (candidate.fiscal_year is None or candidate.fiscal_period is None)
    ):
        return (
            "FISCAL_PERIOD_MAPPING_UNAVAILABLE",
            "The forecast does not identify an absolute fiscal period that can be aligned safely.",
        )
    return "AVAILABLE", None


def _research_candidates(
    session: Session,
    company_id: UUID,
    *,
    cutoff: datetime,
    metric_filter: ForecastAccuracyMetric | None,
) -> list[ForecastCandidate]:
    rows = session.execute(
        select(ResearchForecast, ResearchRevision)
        .join(ResearchRevision, ResearchRevision.id == ResearchForecast.revision_id)
        .where(
            ResearchRevision.company_id == company_id,
            ResearchRevision.status == "PUBLISHED",
            ResearchRevision.recorded_at <= cutoff,
            ResearchRevision.observed_at <= cutoff,
        )
        .order_by(
            ResearchRevision.observed_at.desc(),
            ResearchRevision.recorded_at.desc(),
            ResearchForecast.fiscal_year.desc(),
        )
    ).all()
    result: list[ForecastCandidate] = []
    for forecast, revision in rows:
        try:
            metric = ForecastAccuracyMetric(forecast.metric)
        except ValueError:
            continue
        if metric_filter is not None and metric != metric_filter:
            continue
        known_at = _latest_known_time(revision.observed_at, revision.recorded_at)
        status = {
            "AVAILABLE": "AVAILABLE",
            "UNAVAILABLE": "FORECAST_UNAVAILABLE",
            "DATA_CHECK": "FORECAST_DATA_CHECK",
        }.get(forecast.availability_status, "FORECAST_DATA_CHECK")
        reason = forecast.availability_reason
        if revision.status != "PUBLISHED":
            status, reason = "FORECAST_WITHDRAWN", "This research stream was withdrawn."
        result.append(
            ForecastCandidate(
                source_type=ForecastAccuracySourceType.AGENT_RESEARCH,
                source_name=revision.author_id,
                source_reference=revision.source_reference,
                author_id=revision.author_id,
                stream_key=revision.stream_key,
                methodology="AGENT_AUTHORED_RESEARCH",
                methodology_version=revision.contract_version,
                model_type=None,
                scenario=forecast.scenario,
                scenario_probability=None,
                forecast_id=forecast.id,
                revision_id=revision.id,
                revision_number=revision.revision_number,
                supersedes_revision_id=revision.supersedes_revision_id,
                supersedes_observation_id=None,
                metric=metric,
                period_type=forecast.period_type,
                fiscal_year=forecast.fiscal_year,
                fiscal_period=forecast.fiscal_period,
                forecast_period_label=None,
                period_end=forecast.period_end,
                forecast_year=None,
                forecast_basis=forecast.metric,
                value=forecast.value,
                currency=forecast.currency,
                unit=forecast.unit,
                confidence=forecast.confidence,
                analyst_count=None,
                observed_at=revision.observed_at,
                effective_at=None,
                recorded_at=revision.recorded_at,
                forecast_known_at=known_at,
                status=status,
                status_reason=reason,
            )
        )
    return result


def _selected_mapping_at(
    session: Session, company_id: UUID, known_at: datetime
) -> tuple[ConsensusEstimateProviderMapping | None, str]:
    mappings = list(
        session.scalars(
            select(ConsensusEstimateProviderMapping).where(
                ConsensusEstimateProviderMapping.company_id == company_id,
                ConsensusEstimateProviderMapping.effective_from <= known_at,
                ConsensusEstimateProviderMapping.recorded_at <= known_at,
            )
        )
    )
    latest_by_source: dict[tuple[str, str], ConsensusEstimateProviderMapping] = {}
    for item in sorted(
        mappings,
        key=lambda row: (row.effective_from, row.recorded_at),
        reverse=True,
    ):
        latest_by_source.setdefault((item.role, item.provider_id), item)
    return select_consensus_source(list(latest_by_source.values()))


def _consensus_candidates(
    session: Session,
    company_id: UUID,
    *,
    cutoff: datetime,
    metric_filter: ForecastAccuracyMetric | None,
) -> list[ForecastCandidate]:
    rows = session.scalars(
        select(ConsensusEstimateObservation)
        .where(
            ConsensusEstimateObservation.company_id == company_id,
            ConsensusEstimateObservation.recorded_at <= cutoff,
            ConsensusEstimateObservation.snapshot_date <= cutoff.date(),
            (ConsensusEstimateObservation.observed_at.is_(None))
            | (ConsensusEstimateObservation.observed_at <= cutoff),
        )
        .order_by(
            ConsensusEstimateObservation.observed_at.desc().nullslast(),
            ConsensusEstimateObservation.recorded_at.desc(),
            ConsensusEstimateObservation.period_end,
        )
    ).all()
    result: list[ForecastCandidate] = []
    for observation in rows:
        metric = ForecastAccuracyMetric(observation.metric)
        if metric_filter is not None and metric != metric_filter:
            continue
        mapping = session.get(ConsensusEstimateProviderMapping, observation.provider_mapping_id)
        if mapping is None:
            selected_status, selected_mapping = "NO_MAPPING", None
        else:
            observed_for_policy = (
                _latest_known_time(observation.observed_at, observation.recorded_at)
                if observation.observed_at is not None
                else _utc(observation.recorded_at)
            )
            selected_mapping, selected_status = _selected_mapping_at(
                session, company_id, observed_for_policy
            )

        known_at = (
            _latest_known_time(observation.observed_at, observation.recorded_at)
            if observation.observed_at is not None
            else None
        )
        status = "AVAILABLE"
        reason = None
        if observation.observed_at is None:
            status = "SOURCE_OBSERVATION_TIME_UNKNOWN"
            reason = (
                "The source snapshot has no observation timestamp; recorded time alone "
                "cannot establish its forecast horizon."
            )
        elif selected_status == "AMBIGUOUS_FALLBACK":
            status = "PROVIDER_SELECTION_AMBIGUOUS"
            reason = "No unique provider stream was selected at the observation time."
        elif selected_mapping is None:
            status = "NO_SELECTED_PROVIDER"
            reason = (
                "No primary or unambiguous fallback mapping was effective at the observation time."
            )
        elif mapping is None or selected_mapping.id != mapping.id:
            status = "ALTERNATE_PROVIDER_NOT_SELECTED"
            reason = "This provider was not the selected continuity source at the observation time."
        elif observation.data_quality != "PASS":
            status = "FORECAST_DATA_CHECK"
            reason = (
                observation.quality_reason or f"Consensus quality is {observation.data_quality}."
            )
        result.append(
            ForecastCandidate(
                source_type=ForecastAccuracySourceType.ANALYST_CONSENSUS,
                source_name=observation.provider_id,
                source_reference=observation.source_ref,
                author_id=None,
                stream_key=None,
                methodology="THIRD_PARTY_CONSENSUS",
                methodology_version=None,
                model_type=None,
                scenario="POINT",
                scenario_probability=None,
                forecast_id=observation.id,
                revision_id=None,
                revision_number=None,
                supersedes_revision_id=None,
                supersedes_observation_id=observation.supersedes_observation_id,
                metric=metric,
                period_type=observation.period_type,
                fiscal_year=None,
                fiscal_period=None,
                forecast_period_label=observation.forecast_period,
                period_end=observation.period_end,
                forecast_year=None,
                forecast_basis="PROVIDER_MEAN",
                value=observation.value,
                currency=observation.currency,
                unit=observation.unit,
                confidence=None,
                analyst_count=observation.analyst_count,
                observed_at=observation.observed_at,
                effective_at=None,
                recorded_at=observation.recorded_at,
                forecast_known_at=known_at,
                status=status,
                status_reason=reason,
            )
        )
    return result


def _model_candidate(
    *,
    model: FinancialModel,
    revision: FinancialModelRevision,
    metric: ForecastAccuracyMetric,
    value: Decimal | None,
    scenario: str,
    probability: Decimal,
    forecast_year: int,
    basis: str,
) -> ForecastCandidate:
    known_at = _latest_known_time(revision.effective_at, revision.recorded_at)
    return ForecastCandidate(
        source_type=ForecastAccuracySourceType.FINANCIAL_MODEL,
        source_name=model.model_name,
        source_reference=revision.source,
        author_id=revision.proposal_author_id or revision.actor,
        stream_key=None,
        methodology=revision.model_type,
        methodology_version=revision.methodology_version,
        model_type=FinancialModelType(revision.model_type),
        scenario=scenario,
        scenario_probability=probability,
        forecast_id=None,
        revision_id=revision.id,
        revision_number=revision.revision_number,
        supersedes_revision_id=revision.base_revision_id,
        supersedes_observation_id=None,
        metric=metric,
        period_type=None,
        fiscal_year=None,
        fiscal_period=None,
        forecast_period_label=None,
        period_end=None,
        forecast_year=forecast_year,
        forecast_basis=basis,
        value=value,
        currency=model.model_currency,
        unit="currency/share" if metric == ForecastAccuracyMetric.EPS else "currency",
        confidence=None,
        analyst_count=None,
        observed_at=None,
        effective_at=revision.effective_at,
        recorded_at=revision.recorded_at,
        forecast_known_at=known_at,
        status="AVAILABLE",
        status_reason=None,
    )


def _model_candidates(
    session: Session,
    company_id: UUID,
    *,
    cutoff: datetime,
    metric_filter: ForecastAccuracyMetric | None,
) -> list[ForecastCandidate]:
    revisions = session.execute(
        select(FinancialModel, FinancialModelRevision)
        .join(FinancialModelRevision, FinancialModelRevision.model_id == FinancialModel.id)
        .where(
            FinancialModel.company_id == company_id,
            FinancialModelRevision.recorded_at <= cutoff,
            FinancialModelRevision.effective_at <= cutoff,
        )
        .order_by(
            FinancialModelRevision.effective_at.desc(),
            FinancialModelRevision.revision_number.desc(),
        )
    ).all()
    result: list[ForecastCandidate] = []
    for model, revision in revisions:
        if revision.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
            dcf_scenarios = session.scalars(
                select(DcfScenarioAssumptions).where(
                    DcfScenarioAssumptions.revision_id == revision.id
                )
            ).all()
            dcf_scenario_by_id = {item.id: item for item in dcf_scenarios}
            if dcf_scenario_by_id:
                dcf_projections = session.scalars(
                    select(DcfProjection).where(
                        DcfProjection.scenario_id.in_(dcf_scenario_by_id.keys())
                    )
                ).all()
                for dcf_projection in dcf_projections:
                    dcf_scenario = dcf_scenario_by_id[dcf_projection.scenario_id]
                    dcf_values = (
                        (ForecastAccuracyMetric.REVENUE, dcf_projection.revenue, "REVENUE"),
                        (ForecastAccuracyMetric.EBIT, dcf_projection.ebit, "EBIT"),
                        (
                            ForecastAccuracyMetric.FREE_CASH_FLOW,
                            dcf_projection.unlevered_free_cash_flow,
                            "UNLEVERED_FREE_CASH_FLOW",
                        ),
                    )
                    for metric, value, basis in dcf_values:
                        if value is not None and (metric_filter is None or metric == metric_filter):
                            result.append(
                                _model_candidate(
                                    model=model,
                                    revision=revision,
                                    metric=metric,
                                    value=value,
                                    scenario=dcf_scenario.scenario,
                                    probability=dcf_scenario.probability,
                                    forecast_year=dcf_projection.forecast_year,
                                    basis=basis,
                                )
                            )
        elif revision.model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
            owner_scenarios = session.scalars(
                select(OwnerCashFlowScenarioAssumptions).where(
                    OwnerCashFlowScenarioAssumptions.revision_id == revision.id
                )
            ).all()
            owner_scenario_by_id = {item.id: item for item in owner_scenarios}
            if owner_scenario_by_id:
                owner_projections = session.scalars(
                    select(OwnerCashFlowProjection).where(
                        OwnerCashFlowProjection.scenario_id.in_(owner_scenario_by_id.keys())
                    )
                ).all()
                for owner_projection in owner_projections:
                    owner_scenario = owner_scenario_by_id[owner_projection.scenario_id]
                    owner_values = (
                        (ForecastAccuracyMetric.REVENUE, owner_projection.revenue, "REVENUE"),
                        (
                            ForecastAccuracyMetric.FREE_CASH_FLOW,
                            owner_projection.owner_cash_flow,
                            "OWNER_CASH_FLOW",
                        ),
                    )
                    for metric, value, basis in owner_values:
                        if metric_filter not in (None, metric):
                            continue
                        result.append(
                            _model_candidate(
                                model=model,
                                revision=revision,
                                metric=metric,
                                value=value,
                                scenario=owner_scenario.scenario,
                                probability=owner_scenario.probability,
                                forecast_year=owner_projection.forecast_year,
                                basis=basis,
                            )
                        )
        elif revision.model_type == FinancialModelType.RESIDUAL_INCOME_10Y_FADE:
            residual_scenarios = session.scalars(
                select(ResidualIncomeScenarioAssumptions).where(
                    ResidualIncomeScenarioAssumptions.revision_id == revision.id
                )
            ).all()
            residual_scenario_by_id = {item.id: item for item in residual_scenarios}
            if residual_scenario_by_id:
                residual_projections = session.scalars(
                    select(ResidualIncomeProjection).where(
                        ResidualIncomeProjection.scenario_id.in_(residual_scenario_by_id.keys())
                    )
                ).all()
                for residual_projection in residual_projections:
                    residual_scenario = residual_scenario_by_id[residual_projection.scenario_id]
                    if metric_filter not in (None, ForecastAccuracyMetric.EPS):
                        continue
                    result.append(
                        _model_candidate(
                            model=model,
                            revision=revision,
                            metric=ForecastAccuracyMetric.EPS,
                            value=residual_projection.net_income_per_share,
                            scenario=residual_scenario.scenario,
                            probability=residual_scenario.probability,
                            forecast_year=residual_projection.forecast_year,
                            basis="NET_INCOME_PER_SHARE",
                        )
                    )
    return result


def _actual_read_empty(status: str, reason: str) -> s.ForecastAccuracyActualRead:
    return s.ForecastAccuracyActualRead(
        status=status,
        metric=None,
        period_type=None,
        fiscal_year=None,
        fiscal_period=None,
        period_end=None,
        value=None,
        currency=None,
        unit=None,
        provider_id=None,
        source_reference=None,
        source_observation_id=None,
        published_at=None,
        observed_at=None,
        recorded_at=None,
        revision_context=None,
        supersedes_observation_id=None,
        data_quality=None,
        reason=reason,
    )


def _period_matches(candidate: ForecastCandidate, period: s.ReportedFundamentalPeriodRead) -> bool:
    if candidate.period_type != period.period_type.value:
        return False
    if candidate.period_end is not None:
        return (
            candidate.period_end == period.period_end.date()
            and (
                candidate.fiscal_year is None
                or period.fiscal_year is None
                or candidate.fiscal_year == period.fiscal_year
            )
            and (
                candidate.fiscal_period is None
                or period.fiscal_period is None
                or candidate.fiscal_period == period.fiscal_period
            )
        )
    return (
        candidate.fiscal_year is not None
        and candidate.fiscal_period is not None
        and candidate.fiscal_year == period.fiscal_year
        and candidate.fiscal_period == period.fiscal_period
    )


def _actual_from_period(
    period: s.ReportedFundamentalPeriodRead,
) -> s.ForecastAccuracyActualRead:
    observation = period.selected_observation
    return s.ForecastAccuracyActualRead(
        status=period.selection_status,
        metric=period.metric.value,
        period_type=period.period_type.value,
        fiscal_year=period.fiscal_year,
        fiscal_period=period.fiscal_period,
        period_end=period.period_end.date(),
        value=period.value,
        currency=period.currency,
        unit=period.unit,
        provider_id=observation.provider_id if observation else None,
        source_reference=observation.source_ref if observation else None,
        source_observation_id=observation.id if observation else None,
        published_at=observation.filed_at if observation else None,
        observed_at=observation.observed_at if observation else None,
        recorded_at=observation.recorded_at if observation else None,
        revision_context=observation.revision_context.value if observation else None,
        supersedes_observation_id=observation.supersedes_observation_id if observation else None,
        data_quality=observation.data_quality.value if observation else None,
        reason=observation.quality_reason if observation else None,
    )


def _publication_relation(
    periods: list[s.ReportedFundamentalPeriodRead], forecast_known_at: datetime
) -> str | None:
    forecast_time = _utc(forecast_known_at)
    had_prior_actual = False
    same_day_date_only = False
    for period in periods:
        for observation in period.observations:
            published = observation.filed_at
            if published is None:
                continue
            published = _utc(published)
            if any(
                value is not None and _utc(value) <= forecast_time
                for value in (observation.observed_at, observation.recorded_at)
            ):
                return "ACTUAL_KNOWN_AT_FORECAST"
            if published.date() < forecast_time.date():
                had_prior_actual = True
            elif published.date() == forecast_time.date():
                if published.time().replace(tzinfo=None) == time.min:
                    same_day_date_only = True
                elif published <= forecast_time:
                    had_prior_actual = True
    if had_prior_actual:
        return "ACTUAL_ALREADY_PUBLIC_AT_FORECAST"
    if same_day_date_only:
        return "PUBLICATION_ORDER_UNCERTAIN"
    return None


def _actual_for_candidate(
    candidate: ForecastCandidate,
    facts: s.CompanyReportedFundamentalsRead,
    *,
    outcome_known_at: datetime,
) -> tuple[s.ForecastAccuracyActualRead, str | None, str | None]:
    if candidate.period_type is None or (
        candidate.period_end is None
        and (candidate.fiscal_year is None or candidate.fiscal_period is None)
    ):
        return (
            _actual_read_empty(
                "FISCAL_PERIOD_MAPPING_UNAVAILABLE",
                "No explicit fiscal period is available for the model projection.",
            ),
            "FISCAL_PERIOD_MAPPING_UNAVAILABLE",
            "A forecast cannot be joined to an actual without an explicit fiscal period.",
        )

    if candidate.metric != ForecastAccuracyMetric.REVENUE:
        messages = {
            ForecastAccuracyMetric.EPS: (
                "Canonical reported facts do not include diluted EPS; net income per "
                "share is not substituted."
            ),
            ForecastAccuracyMetric.EBIT: (
                "Operating income is retained as a distinct fact and is not silently "
                "treated as exact EBIT."
            ),
            ForecastAccuracyMetric.EBITDA: "No canonical reported EBITDA fact is available.",
            ForecastAccuracyMetric.FREE_CASH_FLOW: (
                "Free cash flow is not a canonical reported fact; capex sign "
                "conventions are not bridged here."
            ),
        }
        return (
            _actual_read_empty("NO_EXACT_ACTUAL_METRIC", messages[candidate.metric]),
            "NO_EXACT_ACTUAL_METRIC",
            messages[candidate.metric],
        )

    period_matches = [
        period
        for period in facts.periods
        if period.metric == FundamentalMetric.REVENUE and _period_matches(candidate, period)
    ]
    if not period_matches:
        if candidate.period_end is not None and candidate.period_end > outcome_known_at.date():
            reason = "The forecast period has not ended by the selected outcome cutoff."
            return _actual_read_empty("PERIOD_NOT_ENDED", reason), "PERIOD_NOT_ENDED", reason
        reason = (
            "No canonical reported Revenue fact is available for this fiscal period "
            "by the outcome cutoff."
        )
        return _actual_read_empty("NOT_REPORTED", reason), "NOT_REPORTED", reason

    compatible = [
        period
        for period in period_matches
        if period.currency == candidate.currency and period.unit == candidate.unit
    ]
    if candidate.currency is None:
        actual = (
            _actual_from_period(period_matches[0])
            if len(period_matches) == 1
            else _actual_read_empty(
                "AMBIGUOUS_ACTUAL", "More than one reported currency exists for this fiscal period."
            )
        )
        reason = "The forecast currency is unknown, so values cannot be compared."
        return actual, "UNKNOWN_CURRENCY", reason
    if not compatible:
        actual = (
            _actual_from_period(period_matches[0])
            if len(period_matches) == 1
            else _actual_read_empty(
                "AMBIGUOUS_ACTUAL",
                "More than one reported currency/unit exists for this fiscal period.",
            )
        )
        if any(period.currency == candidate.currency for period in period_matches):
            reason = "Forecast and reported fact use different units."
            return actual, "UNIT_MISMATCH", reason
        reason = "Forecast and reported fact use different currencies; no FX conversion is applied."
        return actual, "CURRENCY_MISMATCH", reason
    if len(compatible) > 1:
        reason = "Multiple canonical Revenue periods match the forecast period and currency."
        return _actual_read_empty("AMBIGUOUS_ACTUAL", reason), "AMBIGUOUS_ACTUAL", reason

    period = compatible[0]
    actual = _actual_from_period(period)
    if period.selection_status != "AVAILABLE" or period.value is None:
        status = "ACTUAL_CONFLICT" if period.selection_status == "CONFLICT" else "ACTUAL_DATA_CHECK"
        return (
            actual,
            status,
            actual.reason or "The actual does not have an unambiguous passing quality state.",
        )
    observation = period.selected_observation
    if observation is None or observation.data_quality.value != "PASS":
        return (
            actual,
            "ACTUAL_DATA_CHECK",
            actual.reason or "The reported fact is not quality checked for comparison.",
        )
    if candidate.forecast_known_at is None:
        reason = "The forecast source has no trustworthy knowledge timestamp."
        return actual, "FORECAST_TIME_UNKNOWN", reason

    publication_relation = _publication_relation(period_matches, candidate.forecast_known_at)
    if publication_relation in {
        "ACTUAL_ALREADY_PUBLIC_AT_FORECAST",
        "ACTUAL_KNOWN_AT_FORECAST",
    }:
        reason = (
            "At least one filing or canonical observation for this fiscal fact was already "
            "known by the forecast's knowledge time."
        )
        return actual, publication_relation, reason
    if publication_relation == "PUBLICATION_ORDER_UNCERTAIN":
        reason = (
            "The actual and forecast share a date, but the filing record has date-only precision."
        )
        return actual, publication_relation, reason
    return actual, None, None


def _error_read(
    candidate: ForecastCandidate,
    actual: s.ForecastAccuracyActualRead,
    row_status: str,
    reason: str | None,
) -> s.ForecastAccuracyErrorRead:
    if row_status != "AVAILABLE" or candidate.value is None or actual.value is None:
        return s.ForecastAccuracyErrorRead(
            status="UNAVAILABLE",
            signed_error=None,
            absolute_error=None,
            signed_percentage_error=None,
            absolute_percentage_error=None,
            reason=reason or row_status,
        )
    signed = candidate.value - actual.value
    absolute = abs(signed)
    if actual.value == 0:
        return s.ForecastAccuracyErrorRead(
            status="RELATIVE_ERROR_UNDEFINED_ZERO_ACTUAL",
            signed_error=signed,
            absolute_error=absolute,
            signed_percentage_error=None,
            absolute_percentage_error=None,
            reason=(
                "Absolute error is defined, but relative error is undefined when "
                "actual equals zero."
            ),
        )
    signed_percentage = signed / abs(actual.value)
    return s.ForecastAccuracyErrorRead(
        status="AVAILABLE",
        signed_error=signed,
        absolute_error=absolute,
        signed_percentage_error=signed_percentage,
        absolute_percentage_error=abs(signed_percentage),
        reason=None,
    )


def _horizon(known_at: datetime | None, period_end: date | None) -> tuple[int | None, str | None]:
    if known_at is None or period_end is None:
        return None, None
    days = (period_end - _utc(known_at).date()).days
    if days < 0:
        bucket = "AFTER_PERIOD_END"
    elif days <= 90:
        bucket = "0_90_DAYS"
    elif days <= 180:
        bucket = "91_180_DAYS"
    elif days <= 365:
        bucket = "181_365_DAYS"
    else:
        bucket = "OVER_365_DAYS"
    return days, bucket


def _row_read(
    candidate: ForecastCandidate,
    facts: s.CompanyReportedFundamentalsRead,
    *,
    outcome_known_at: datetime,
) -> s.ForecastAccuracyObservationRead:
    status, reason = _candidate_status(candidate)
    if status == "AVAILABLE":
        actual, actual_status, actual_reason = _actual_for_candidate(
            candidate, facts, outcome_known_at=outcome_known_at
        )
        if actual_status is not None:
            status, reason = actual_status, actual_reason
        elif actual.status != "AVAILABLE" or actual.value is None:
            status = "ACTUAL_DATA_CHECK"
            reason = actual.reason or "The actual is unavailable or not accepted for comparison."
        elif candidate.currency != actual.currency:
            status = "CURRENCY_MISMATCH"
            reason = "Forecast and actual currencies differ; no implicit conversion is performed."
        elif candidate.unit != actual.unit:
            status = "UNIT_MISMATCH"
            reason = "Forecast and actual units differ."
    else:
        actual = _actual_read_empty(
            "FISCAL_PERIOD_MAPPING_UNAVAILABLE"
            if candidate.source_type == ForecastAccuracySourceType.FINANCIAL_MODEL
            else "NOT_EVALUATED",
            reason or "Forecast is not eligible for an accuracy comparison.",
        )
    if candidate.source_type == ForecastAccuracySourceType.FINANCIAL_MODEL and status in {
        "FISCAL_PERIOD_MAPPING_UNAVAILABLE",
        "MODEL_BASIS_NOT_COMPARABLE",
        "SCENARIO_NOT_EVALUATED",
    }:
        actual = _actual_read_empty(
            "FISCAL_PERIOD_MAPPING_UNAVAILABLE",
            "The model projection has no explicit fiscal-period anchor.",
        )
    horizon_days, horizon_bucket = _horizon(candidate.forecast_known_at, candidate.period_end)
    error = _error_read(candidate, actual, status, reason)
    return s.ForecastAccuracyObservationRead(
        source_type=candidate.source_type,
        source_name=candidate.source_name,
        source_reference=candidate.source_reference,
        author_id=candidate.author_id,
        stream_key=candidate.stream_key,
        methodology=candidate.methodology,
        methodology_version=candidate.methodology_version,
        model_type=candidate.model_type,
        scenario=candidate.scenario,
        scenario_probability=candidate.scenario_probability,
        forecast_id=candidate.forecast_id,
        revision_id=candidate.revision_id,
        revision_number=candidate.revision_number,
        supersedes_revision_id=candidate.supersedes_revision_id,
        supersedes_observation_id=candidate.supersedes_observation_id,
        metric=candidate.metric,
        period_type=candidate.period_type,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.fiscal_period,
        forecast_period_label=candidate.forecast_period_label,
        period_end=candidate.period_end,
        forecast_year=candidate.forecast_year,
        forecast_basis=candidate.forecast_basis,
        value=candidate.value,
        currency=candidate.currency,
        unit=candidate.unit,
        confidence=candidate.confidence,
        analyst_count=candidate.analyst_count,
        observed_at=candidate.observed_at,
        effective_at=candidate.effective_at,
        recorded_at=candidate.recorded_at,
        forecast_known_at=candidate.forecast_known_at,
        horizon_days=horizon_days,
        horizon_bucket=horizon_bucket,
        status=status,
        status_reason=reason,
        actual=actual,
        error=error,
    )


def _summaries(
    rows: list[s.ForecastAccuracyObservationRead],
) -> list[s.ForecastAccuracySummaryRead]:
    groups: dict[
        tuple[
            ForecastAccuracySourceType,
            str,
            str | None,
            str | None,
            ForecastAccuracyMetric,
            str,
            str,
        ],
        list[s.ForecastAccuracyObservationRead],
    ] = {}
    for row in rows:
        if row.period_type is None or row.horizon_bucket is None:
            continue
        key = (
            row.source_type,
            row.source_name,
            row.methodology,
            row.methodology_version,
            row.metric,
            row.period_type.value,
            row.horizon_bucket,
        )
        groups.setdefault(key, []).append(row)

    summaries: list[s.ForecastAccuracySummaryRead] = []
    for (
        source_type,
        source_name,
        methodology,
        methodology_version,
        metric,
        period_type,
        horizon_bucket,
    ), items in groups.items():
        # Repeated snapshots of the same issuer-period do not inflate the sample.
        latest_by_period: dict[tuple[Any, ...], s.ForecastAccuracyObservationRead] = {}
        for item in items:
            period_key = (
                item.fiscal_year,
                item.fiscal_period,
                item.period_end,
            )
            current = latest_by_period.get(period_key)
            if current is None or (item.forecast_known_at or datetime.min.replace(tzinfo=UTC)) > (
                current.forecast_known_at or datetime.min.replace(tzinfo=UTC)
            ):
                latest_by_period[period_key] = item
        eligible = [
            item
            for item in latest_by_period.values()
            if item.status == "AVAILABLE" and item.error.absolute_percentage_error is not None
        ]
        count = len(eligible)
        if count < MIN_AGGREGATE_SAMPLE_COUNT:
            summaries.append(
                s.ForecastAccuracySummaryRead(
                    source_type=source_type,
                    source_name=source_name,
                    methodology=methodology,
                    methodology_version=methodology_version,
                    metric=metric,
                    period_type=period_type,
                    horizon_bucket=horizon_bucket,
                    sample_count=count,
                    minimum_sample_count=MIN_AGGREGATE_SAMPLE_COUNT,
                    status="INSUFFICIENT_SAMPLE",
                    mean_absolute_percentage_error=None,
                    mean_signed_percentage_error=None,
                    reason=(
                        "Aggregate error is withheld until at least five distinct "
                        "fiscal periods are comparable."
                    ),
                )
            )
            continue
        absolute = [item.error.absolute_percentage_error for item in eligible]
        signed = [item.error.signed_percentage_error for item in eligible]
        assert all(item is not None for item in absolute)
        assert all(item is not None for item in signed)
        summaries.append(
            s.ForecastAccuracySummaryRead(
                source_type=source_type,
                source_name=source_name,
                methodology=methodology,
                methodology_version=methodology_version,
                metric=metric,
                period_type=period_type,
                horizon_bucket=horizon_bucket,
                sample_count=count,
                minimum_sample_count=MIN_AGGREGATE_SAMPLE_COUNT,
                status="AVAILABLE",
                mean_absolute_percentage_error=sum(
                    (cast(Decimal, value) for value in absolute), Decimal(0)
                )
                / count,
                mean_signed_percentage_error=sum(
                    (cast(Decimal, value) for value in signed), Decimal(0)
                )
                / count,
                reason=None,
            )
        )
    return sorted(
        summaries,
        key=lambda item: (
            item.metric.value,
            item.source_name,
            item.period_type.value,
            item.horizon_bucket,
            item.source_type.value,
        ),
    )


def company_forecast_accuracy(
    session: Session,
    company_id: UUID,
    *,
    metric: ForecastAccuracyMetric | None = None,
    source: ForecastAccuracySourceType | None = None,
    period_type: str | None = None,
    fiscal_year: int | None = None,
    fiscal_period: str | None = None,
    outcome_known_at: datetime | None = None,
    limit: int = 200,
) -> s.CompanyForecastAccuracyRead:
    """Compare recorded forecasts only with exact, later-published reported facts."""
    services.company(session, company_id)
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if period_type not in (None, "ANNUAL", "QUARTERLY"):
        raise ValueError("period_type must be ANNUAL or QUARTERLY")
    if fiscal_period is not None and fiscal_period not in ("FY", "Q1", "Q2", "Q3", "Q4"):
        raise ValueError("fiscal_period must be FY or Q1 through Q4")
    if fiscal_period is not None and period_type == "ANNUAL" and fiscal_period != "FY":
        raise ValueError("Annual forecasts must use fiscal period FY")
    if fiscal_period is not None and period_type == "QUARTERLY" and fiscal_period == "FY":
        raise ValueError("Quarterly forecasts must use fiscal period Q1 through Q4")
    cutoff = _utc(outcome_known_at or now())

    candidates = _research_candidates(session, company_id, cutoff=cutoff, metric_filter=metric)
    candidates.extend(
        _consensus_candidates(session, company_id, cutoff=cutoff, metric_filter=metric)
    )
    candidates.extend(_model_candidates(session, company_id, cutoff=cutoff, metric_filter=metric))
    if source is not None:
        candidates = [item for item in candidates if item.source_type == source]
    if period_type is not None:
        candidates = [item for item in candidates if item.period_type == period_type]
    if fiscal_year is not None:
        candidates = [item for item in candidates if item.fiscal_year == fiscal_year]
    if fiscal_period is not None:
        candidates = [item for item in candidates if item.fiscal_period == fiscal_period]

    facts = queries.company_reported_fundamentals(
        session,
        company_id,
        period_type=period_type,
        as_of=cutoff.date(),
        known_at=cutoff,
        effective_cutoff=cutoff,
    )
    reads = [_row_read(item, facts, outcome_known_at=cutoff) for item in candidates]
    reads.sort(
        key=lambda row: (
            row.forecast_known_at or datetime.min.replace(tzinfo=UTC),
            row.period_end or date.min,
            row.source_type.value,
            row.source_name,
        ),
        reverse=True,
    )
    total_count = len(reads)
    return s.CompanyForecastAccuracyRead(
        company_id=company_id,
        outcome_known_at=cutoff,
        selected_metric=metric,
        selected_source=source,
        selected_period_type=period_type,
        selected_fiscal_year=fiscal_year,
        selected_fiscal_period=fiscal_period,
        total_count=total_count,
        returned_count=min(total_count, limit),
        truncated=total_count > limit,
        observations=reads[:limit],
        summaries=_summaries(reads),
    )
