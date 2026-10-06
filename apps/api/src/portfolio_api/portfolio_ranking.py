"""Documented Portfolio Score calculation and immutable rank inputs."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    LifecycleEvent,
    Listing,
    ModelOutputSnapshot,
    ModelOutputSnapshotKind,
    Portfolio,
    PriceObservation,
    RankingEntryStatus,
    ScoreAssessment,
    ScoreDefinition,
    ScoreDefinitionStatus,
    ScoreDimension,
    Security,
)
from portfolio_api.market_data import FRESH_DAYS

PORTFOLIO_SCORE_VERSION = "LEGACY_IRR_FIRST_ALLOCATION_V1"
PORTFOLIO_RANK_CONTEXT_VERSION = "portfolio-rank-inputs-v1"
NATIVE_RETURN_SEMANTICS = "NATIVE_SHAREHOLDER_CASH_FLOW"
LEGACY_RETURN_SEMANTICS = "LEGACY_NORMALIZED_EXPECTED_IRR"

ZERO = Decimal("0")
ONE = Decimal("1")
FIFTEEN_PERCENT = Decimal("0.15")
THIRTY_PERCENT = Decimal("0.30")
TWENTY_PERCENT = Decimal("0.20")
TEN_PERCENT = Decimal("0.10")
FIVE_PERCENT = Decimal("0.05")
ONE_PERCENT = Decimal("0.01")
TWENTY_FIVE_PERCENT = Decimal("0.25")
TWO = Decimal("2")
FIVE = Decimal("5")
SIX = Decimal("6")
ONE_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PortfolioScoreInputs:
    lifecycle: str | None
    current_weight: Decimal
    target_weight: Decimal
    expected_irr: Decimal
    durability_10y: Decimal
    compounder_quality: Decimal
    execution: Decimal
    risk: Decimal
    valuation_uncertainty: Decimal
    expected_excess: Decimal


@dataclass(frozen=True)
class PortfolioScoreResult:
    score: Decimal
    contributions: dict[str, Decimal]


@dataclass(frozen=True)
class PortfolioRankCandidate:
    semantics: str
    ticker: str
    score: Decimal
    input_snapshot: dict[str, Any]


def calculate_portfolio_score(inputs: PortfolioScoreInputs) -> PortfolioScoreResult:
    """Apply the legacy Overview!S formula exactly, with no missing-to-zero defaults."""
    if not ZERO <= inputs.current_weight <= ONE:
        raise ValueError("current weight must be between zero and one")
    if not ZERO <= inputs.target_weight <= ONE:
        raise ValueError("target weight must be between zero and one")
    for name, score, minimum in (
        ("10Y Durability", inputs.durability_10y, ZERO),
        ("Compounder Quality", inputs.compounder_quality, ZERO),
        ("Execution", inputs.execution, ONE),
        ("Risk", inputs.risk, ONE),
    ):
        if not minimum <= score <= FIVE:
            raise ValueError(f"{name} is outside its documented score scale")
    if inputs.valuation_uncertainty < ZERO:
        raise ValueError("valuation uncertainty cannot be negative")

    target_gap = inputs.target_weight - inputs.current_weight
    target_denominator = max(inputs.target_weight, ONE_PERCENT)
    # The legacy Overview!S formula grants this component only to explicit
    # Portfolio lifecycle rows (A="P"). Other lifecycle states get no credit.
    target_underweight = (
        min(max(target_gap, ZERO) / target_denominator, ONE)
        if inputs.lifecycle == "PORTFOLIO"
        else ZERO
    )
    irr_component = max(min(inputs.expected_irr, TWENTY_FIVE_PERCENT), ZERO) / (TWENTY_FIVE_PERCENT)
    durability_component = inputs.durability_10y / FIVE
    compounder_component = inputs.compounder_quality / FIVE
    execution_component = inputs.execution / FIVE
    risk_component = (SIX - inputs.risk) / FIVE
    uncertainty_penalty = min(inputs.valuation_uncertainty, TWO) / TWO
    excess_penalty = max(min(-inputs.expected_excess, FIVE_PERCENT), ZERO) / FIVE_PERCENT

    contributions = {
        "target_underweight": target_underweight * FIFTEEN_PERCENT * ONE_HUNDRED,
        "expected_irr": irr_component * THIRTY_PERCENT * ONE_HUNDRED,
        "durability_10y": durability_component * FIFTEEN_PERCENT * ONE_HUNDRED,
        "compounder_quality": compounder_component * TWENTY_PERCENT * ONE_HUNDRED,
        "execution": execution_component * TEN_PERCENT * ONE_HUNDRED,
        "risk": risk_component * TEN_PERCENT * ONE_HUNDRED,
        "valuation_uncertainty_penalty": -uncertainty_penalty * TEN_PERCENT * ONE_HUNDRED,
        "negative_expected_excess_penalty": -excess_penalty * FIVE_PERCENT * ONE_HUNDRED,
    }
    return PortfolioScoreResult(sum(contributions.values(), ZERO), contributions)


def portfolio_score_positions(
    rows: list[tuple[UUID, str, Decimal]],
) -> dict[UUID, int]:
    """Sort a comparable score cohort by score descending, then ticker ascending."""
    ordered = sorted(rows, key=lambda row: (-row[2], row[1]))
    return {
        company_id: position for position, (company_id, _ticker, _score) in enumerate(ordered, 1)
    }


def build_portfolio_rank_entries(
    session: Session, companies: list[Company], as_of: datetime
) -> list[tuple[UUID, RankingEntryStatus, str, int | None, dict[str, Any] | None]]:
    """Build a point-in-time Portfolio Rank from supported canonical inputs."""
    company_ids = {company.id for company in companies}
    if not company_ids:
        return []
    cutoff = as_of.astimezone(UTC)

    # Imported here to keep the query and write-service dependency one-way.
    from portfolio_api.domain import queries

    portfolio = session.scalar(
        select(Portfolio)
        .where(Portfolio.created_at <= cutoff)
        .order_by(Portfolio.created_at)
        .limit(1)
    )
    if portfolio is None:
        return [
            (
                company.id,
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "No portfolio exists as of this ranking run.",
                None,
                None,
            )
            for company in companies
        ]
    portfolio_view = queries.overview(session, portfolio.id, as_of=cutoff)
    contexts = {row.company.id: row for row in portfolio_view.companies}
    lifecycle_by_company: dict[UUID, str] = {}
    for company_id, lifecycle in session.execute(
        select(LifecycleEvent.company_id, LifecycleEvent.new_state)
        .where(LifecycleEvent.effective_at <= cutoff, LifecycleEvent.recorded_at <= cutoff)
        .order_by(LifecycleEvent.sequence.desc())
    ):
        lifecycle_by_company.setdefault(company_id, lifecycle)
    score_rows = _score_contexts(session, company_ids, cutoff)

    native_models = list(
        session.scalars(
            select(FinancialModel)
            .where(
                FinancialModel.company_id.in_(company_ids),
                FinancialModel.created_at <= cutoff,
            )
            .order_by(FinancialModel.company_id, FinancialModel.model_name, FinancialModel.id)
        )
    )
    models_by_company: dict[UUID, list[FinancialModel]] = defaultdict(list)
    models_by_id = {model.id: model for model in native_models}
    for current_model in native_models:
        models_by_company[current_model.company_id].append(current_model)
    revisions = (
        list(
            session.scalars(
                select(FinancialModelRevision)
                .where(
                    FinancialModelRevision.model_id.in_(models_by_id),
                    FinancialModelRevision.effective_at <= cutoff,
                    FinancialModelRevision.recorded_at <= cutoff,
                )
                .order_by(
                    FinancialModelRevision.model_id,
                    FinancialModelRevision.revision_number,
                    FinancialModelRevision.recorded_at,
                )
            )
        )
        if models_by_id
        else []
    )
    revision_by_model: dict[UUID, FinancialModelRevision] = {}
    for model_revision in revisions:
        revision_by_model[model_revision.model_id] = model_revision
    outputs = (
        list(
            session.scalars(
                select(FinancialModelOutput).where(
                    FinancialModelOutput.revision_id.in_([revision.id for revision in revisions])
                )
            )
        )
        if revisions
        else []
    )
    output_by_revision = {output.revision_id: output for output in outputs}

    legacy_rows = list(
        session.scalars(
            select(ModelOutputSnapshot)
            .where(
                ModelOutputSnapshot.company_id.in_(company_ids),
                ModelOutputSnapshot.snapshot_kind == ModelOutputSnapshotKind.CURRENT_CONTRACT,
                ModelOutputSnapshot.recorded_at <= cutoff,
                (ModelOutputSnapshot.effective_at.is_(None))
                | (ModelOutputSnapshot.effective_at <= cutoff),
            )
            .order_by(
                ModelOutputSnapshot.company_id,
                ModelOutputSnapshot.model_key,
                ModelOutputSnapshot.recorded_at.desc(),
                ModelOutputSnapshot.id,
            )
        )
    )
    latest_legacy: dict[tuple[UUID, str], ModelOutputSnapshot] = {}
    for legacy_snapshot in legacy_rows:
        latest_legacy.setdefault(
            (legacy_snapshot.company_id, legacy_snapshot.model_key), legacy_snapshot
        )
    legacy_by_company: dict[UUID, list[ModelOutputSnapshot]] = defaultdict(list)
    for (company_id, _model_key), legacy_snapshot in latest_legacy.items():
        legacy_by_company[company_id].append(legacy_snapshot)

    results: dict[UUID, tuple[RankingEntryStatus, str, int | None, dict[str, Any] | None]] = {}
    candidates: dict[UUID, PortfolioRankCandidate] = {}
    for company in companies:
        context = contexts.get(company.id)
        if context is None:
            complete_membership = (
                portfolio_view.snapshot is not None
                and portfolio_view.snapshot.completeness == "COMPLETE"
                and portfolio_view.target_revision is not None
            )
            status = (
                RankingEntryStatus.NOT_ELIGIBLE
                if complete_membership
                else RankingEntryStatus.INPUTS_UNAVAILABLE
            )
            reason = (
                "No positive current or strategic target allocation was observed."
                if complete_membership
                else "Complete current holdings and accepted targets are required to establish "
                "Portfolio Rank membership."
            )
            results[company.id] = (status, reason, None, None)
            continue

        observed_positive_holding = any(
            position.quantity is not None and position.quantity > ZERO
            for position in context.positions
        )
        positive_current = context.current_weight is not None and context.current_weight > ZERO
        positive_target = context.target_weight is not None and context.target_weight > ZERO
        if not (positive_current or positive_target or observed_positive_holding):
            complete_membership = (
                portfolio_view.snapshot is not None
                and portfolio_view.snapshot.completeness == "COMPLETE"
                and portfolio_view.target_revision is not None
            )
            if complete_membership:
                results[company.id] = (
                    RankingEntryStatus.NOT_ELIGIBLE,
                    "No positive current or strategic target allocation was observed.",
                    None,
                    None,
                )
            else:
                results[company.id] = (
                    RankingEntryStatus.INPUTS_UNAVAILABLE,
                    "Incomplete portfolio observations prevent a reliable membership decision.",
                    None,
                    None,
                )
            continue

        score_context = score_rows[company.id]
        score_snapshot = _portfolio_input_snapshot(
            portfolio_view,
            context,
            score_context,
            None,
            None,
            None,
            lifecycle=lifecycle_by_company.get(company.id),
        )

        # Current weight and target are distinct facts. No missing target is
        # translated to zero, and a stale/incomplete market valuation is a check.
        if portfolio_view.snapshot is None:
            results[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "No point-in-time holdings snapshot establishes the current portfolio weight.",
                None,
                score_snapshot,
            )
            continue
        if portfolio_view.snapshot.completeness != "COMPLETE":
            results[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                "The current holdings snapshot is partial, so current portfolio weight is not "
                "complete.",
                None,
                score_snapshot,
            )
            continue
        if portfolio_view.target_revision is None:
            results[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "No accepted strategic target revision is available for the documented score.",
                None,
                score_snapshot,
            )
            continue
        if context.target_weight is None:
            results[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "No target weight was authored for this company; missing target is not treated "
                "as zero.",
                None,
                score_snapshot,
            )
            continue
        if (
            portfolio_view.valuation_status != "VALUED"
            or context.allocation_status != "VALUED"
            or context.current_weight is None
        ):
            results[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                f"Current market weight is not comparable: {context.allocation_status}.",
                None,
                score_snapshot,
            )
            continue

        missing_scores = [
            name
            for name in ("durability_10y", "compounder_quality", "execution", "risk")
            if score_context[name]["status"] != "ASSESSED" or score_context[name]["score"] is None
        ]
        invalid_scores = [
            name
            for name in ("durability_10y", "compounder_quality", "execution", "risk")
            if score_context[name]["status"] == "INVALID"
            or score_context[name]["definition_error"] is not None
        ]
        if invalid_scores:
            results[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                f"Invalid canonical score assessment(s): {', '.join(invalid_scores)}.",
                None,
                score_snapshot,
            )
            continue
        if missing_scores:
            results[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                f"Missing assessed Portfolio Score input(s): {', '.join(missing_scores)}.",
                None,
                score_snapshot,
            )
            continue

        model, revision, output, semantics, source_snapshot, model_error = _model_inputs(
            session,
            company,
            models_by_company.get(company.id, []),
            revision_by_model,
            output_by_revision,
            legacy_by_company.get(company.id, []),
            as_of=cutoff,
        )
        if model_error is not None:
            status, reason = model_error
            snapshot = _portfolio_input_snapshot(
                portfolio_view,
                context,
                score_context,
                source_snapshot,
                output,
                None,
                lifecycle=lifecycle_by_company.get(company.id),
            )
            results[company.id] = (status, reason, None, snapshot)
            continue
        assert output is not None and semantics is not None and source_snapshot is not None
        if output.expected_cash_flow_irr is None:
            snapshot = _portfolio_input_snapshot(
                portfolio_view,
                context,
                score_context,
                source_snapshot,
                output,
                None,
                lifecycle=lifecycle_by_company.get(company.id),
            )
            results[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "The accepted current model source has no numeric Expected IRR.",
                None,
                snapshot,
            )
            continue
        required_output_fields = (output.bear_fv, output.weighted_fv, output.bull_fv)
        if any(value is None for value in required_output_fields):
            snapshot = _portfolio_input_snapshot(
                portfolio_view,
                context,
                score_context,
                source_snapshot,
                output,
                None,
                lifecycle=lifecycle_by_company.get(company.id),
            )
            results[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "Bear, Weighted, and Bull Fair Value are all required for documented valuation "
                "uncertainty.",
                None,
                snapshot,
            )
            continue
        if output.hurdle is None:
            snapshot = _portfolio_input_snapshot(
                portfolio_view,
                context,
                score_context,
                source_snapshot,
                output,
                None,
                lifecycle=lifecycle_by_company.get(company.id),
            )
            results[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "Hurdle is required to preserve the documented Expected Excess penalty.",
                None,
                snapshot,
            )
            continue

        assert output.bear_fv is not None and output.weighted_fv is not None
        assert output.bull_fv is not None and output.expected_cash_flow_irr is not None
        if output.weighted_fv <= ZERO or output.bull_fv < output.bear_fv:
            snapshot = _portfolio_input_snapshot(
                portfolio_view,
                context,
                score_context,
                source_snapshot,
                output,
                None,
                lifecycle=lifecycle_by_company.get(company.id),
            )
            results[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                "Fair Value outputs do not support a positive, ordered valuation range.",
                None,
                snapshot,
            )
            continue

        expected_excess = output.expected_excess
        if expected_excess is None:
            # Expected Excess = Expected IRR - Hurdle is an explicit project
            # domain identity, so it may be derived when those two inputs exist.
            expected_excess = output.expected_cash_flow_irr - output.hurdle
        uncertainty = (output.bull_fv - output.bear_fv) / output.weighted_fv
        score_inputs = PortfolioScoreInputs(
            lifecycle=lifecycle_by_company.get(company.id),
            current_weight=context.current_weight,
            target_weight=context.target_weight,
            expected_irr=output.expected_cash_flow_irr,
            durability_10y=cast(Decimal, score_context["durability_10y"]["decimal_score"]),
            compounder_quality=cast(Decimal, score_context["compounder_quality"]["decimal_score"]),
            execution=cast(Decimal, score_context["execution"]["decimal_score"]),
            risk=cast(Decimal, score_context["risk"]["decimal_score"]),
            valuation_uncertainty=uncertainty,
            expected_excess=expected_excess,
        )
        try:
            calculation = calculate_portfolio_score(score_inputs)
        except ValueError as error:
            snapshot = _portfolio_input_snapshot(
                portfolio_view,
                context,
                score_context,
                source_snapshot,
                output,
                None,
                lifecycle=lifecycle_by_company.get(company.id),
            )
            results[company.id] = (RankingEntryStatus.DATA_CHECK, str(error), None, snapshot)
            continue

        ticker = cast(str | None, source_snapshot["listing_ticker"])
        full_snapshot = _portfolio_input_snapshot(
            portfolio_view,
            context,
            score_context,
            source_snapshot,
            output,
            calculation,
            lifecycle=lifecycle_by_company.get(company.id),
            expected_excess=expected_excess,
            uncertainty=uncertainty,
        )
        if ticker is None:
            results[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                "No canonical listing ticker is available for the documented tie-break.",
                None,
                full_snapshot,
            )
            continue
        candidates[company.id] = PortfolioRankCandidate(
            semantics=semantics,
            ticker=ticker,
            score=calculation.score,
            input_snapshot=full_snapshot,
        )

    selected_semantics = (
        NATIVE_RETURN_SEMANTICS
        if any(candidate.semantics == NATIVE_RETURN_SEMANTICS for candidate in candidates.values())
        else LEGACY_RETURN_SEMANTICS
    )
    comparable: list[tuple[UUID, str, Decimal]] = []
    for company_id, candidate in candidates.items():
        if candidate.semantics != selected_semantics:
            results[company_id] = (
                RankingEntryStatus.DATA_CHECK,
                "Native shareholder-cash-flow Portfolio Scores and legacy normalized-output "
                "Portfolio Scores are not assumed comparable; this run ranks only the native "
                "cohort.",
                None,
                candidate.input_snapshot,
            )
            continue
        comparable.append((company_id, candidate.ticker, candidate.score))

    duplicate_tickers = {
        ticker for ticker, count in Counter(row[1] for row in comparable).items() if count > 1
    }
    sortable: list[tuple[UUID, str, Decimal]] = []
    for company_id, ticker, score in comparable:
        if ticker in duplicate_tickers:
            results[company_id] = (
                RankingEntryStatus.DATA_CHECK,
                f"Ticker {ticker} is not unique in the eligible population; the documented "
                "tie-break cannot assign an auditable ordinal.",
                None,
                candidates[company_id].input_snapshot,
            )
        else:
            sortable.append((company_id, ticker, score))

    positions = portfolio_score_positions(sortable)
    for company_id, position in positions.items():
        results[company_id] = (
            RankingEntryStatus.RANKED,
            "Ranked by the documented IRR-First Allocation Score descending, then canonical "
            "listing ticker ascending. Target weight, current weight, gap, and Execution Pace "
            "remain separate state.",
            position,
            candidates[company_id].input_snapshot,
        )

    return [
        (
            company.id,
            *results.get(
                company.id,
                (
                    RankingEntryStatus.INPUTS_UNAVAILABLE,
                    "A complete Portfolio Score could not be established for this run.",
                    None,
                    None,
                ),
            ),
        )
        for company in companies
    ]


def _score_contexts(
    session: Session, company_ids: set[UUID], as_of: datetime
) -> dict[UUID, dict[str, dict[str, Any]]]:
    expected = {
        ScoreDimension.DURABILITY_10Y: ("HIGHER_IS_BETTER", ZERO),
        ScoreDimension.COMPOUNDER_QUALITY: ("HIGHER_IS_BETTER", ZERO),
        ScoreDimension.EXECUTION: ("HIGHER_IS_BETTER", ONE),
        ScoreDimension.RISK: ("HIGHER_IS_RISK", ONE),
    }
    definitions = list(
        session.scalars(
            select(ScoreDefinition)
            .where(
                ScoreDefinition.dimension.in_(tuple(expected)),
                ScoreDefinition.status == ScoreDefinitionStatus.ACTIVE,
                ScoreDefinition.effective_from <= as_of,
                ScoreDefinition.recorded_at <= as_of,
            )
            .order_by(ScoreDefinition.dimension, ScoreDefinition.version.desc())
        )
    )
    definition_by_dimension: dict[str, ScoreDefinition] = {}
    for definition in definitions:
        definition_by_dimension.setdefault(definition.dimension, definition)
    assessments = (
        list(
            session.scalars(
                select(ScoreAssessment)
                .where(
                    ScoreAssessment.company_id.in_(company_ids),
                    ScoreAssessment.score_definition_id.in_([item.id for item in definitions]),
                    ScoreAssessment.effective_at <= as_of,
                    ScoreAssessment.recorded_at <= as_of,
                )
                .order_by(
                    ScoreAssessment.company_id,
                    ScoreAssessment.score_definition_id,
                    ScoreAssessment.effective_at.desc(),
                    ScoreAssessment.recorded_at.desc(),
                    ScoreAssessment.id.desc(),
                )
            )
        )
        if definitions
        else []
    )
    latest: dict[tuple[UUID, UUID], ScoreAssessment] = {}
    for assessment in assessments:
        latest.setdefault((assessment.company_id, assessment.score_definition_id), assessment)

    result: dict[UUID, dict[str, dict[str, Any]]] = {}
    for company_id in company_ids:
        dimensions: dict[str, dict[str, Any]] = {}
        for dimension in expected:
            key = dimension.name.lower()
            active_definition = definition_by_dimension.get(dimension)
            selected_assessment = (
                latest.get((company_id, active_definition.id)) if active_definition else None
            )
            status = selected_assessment.status if selected_assessment else "NOT_ASSESSED"
            score = (
                selected_assessment.score
                if selected_assessment and selected_assessment.status == "ASSESSED"
                else None
            )
            definition_error = None
            if active_definition is None:
                definition_error = "No effective canonical score definition is available."
            elif (
                active_definition.directionality != expected[dimension][0]
                or active_definition.minimum_score != expected[dimension][1]
                or active_definition.maximum_score != FIVE
            ):
                definition_error = (
                    f"{dimension.value} definition does not match the supported scale."
                )
            elif (
                score is not None
                and not active_definition.minimum_score <= score <= active_definition.maximum_score
            ):
                definition_error = f"{dimension.value} assessment is outside its active definition."
            dimensions[key] = {
                "score": score,
                "decimal_score": score,
                "status": status,
                "assessment_id": selected_assessment.id if selected_assessment else None,
                "effective_at": selected_assessment.effective_at if selected_assessment else None,
                "recorded_at": selected_assessment.recorded_at if selected_assessment else None,
                "source": selected_assessment.source if selected_assessment else None,
                "definition_error": definition_error,
            }
        result[company_id] = dimensions
    return result


def _model_inputs(
    session: Session,
    company: Company,
    models: list[FinancialModel],
    revision_by_model: dict[UUID, FinancialModelRevision],
    output_by_revision: dict[UUID, FinancialModelOutput],
    contracts: list[ModelOutputSnapshot],
    *,
    as_of: datetime,
) -> tuple[
    FinancialModel | None,
    FinancialModelRevision | None,
    FinancialModelOutput | ModelOutputSnapshot | None,
    str | None,
    dict[str, Any] | None,
    tuple[RankingEntryStatus, str] | None,
]:
    effective_native = [
        (model, revision_by_model[model.id]) for model in models if model.id in revision_by_model
    ]
    if len(effective_native) > 1:
        return (
            None,
            None,
            None,
            None,
            None,
            (
                RankingEntryStatus.DATA_CHECK,
                "More than one accepted native model series is effective for this company; the "
                "Portfolio Score cannot choose a methodology or listing.",
            ),
        )
    if effective_native:
        model, revision = effective_native[0]
        output = output_by_revision.get(revision.id)
        source = _native_model_source(session, model, revision, output)
        if output is None:
            return (
                model,
                revision,
                None,
                NATIVE_RETURN_SEMANTICS,
                source,
                (
                    RankingEntryStatus.DATA_CHECK,
                    "The accepted native model revision has no output.",
                ),
            )
        if output.status != "COMPLETE":
            return (
                model,
                revision,
                output,
                NATIVE_RETURN_SEMANTICS,
                source,
                (RankingEntryStatus.DATA_CHECK, "The native model status is not COMPLETE."),
            )
        if model.model_currency != output.model_currency:
            return (
                model,
                revision,
                output,
                NATIVE_RETURN_SEMANTICS,
                source,
                (RankingEntryStatus.DATA_CHECK, "Native model/output currencies are inconsistent."),
            )
        price_error = _native_price_error(session, model, output, as_of)
        if price_error:
            return (
                model,
                revision,
                output,
                NATIVE_RETURN_SEMANTICS,
                source,
                (RankingEntryStatus.DATA_CHECK, price_error),
            )
        if output.expected_cash_flow_irr is None:
            return (
                model,
                revision,
                output,
                NATIVE_RETURN_SEMANTICS,
                source,
                (
                    RankingEntryStatus.INPUTS_UNAVAILABLE,
                    output.irr_unavailable_reason
                    or "Native Expected Cash-Flow IRR is unavailable.",
                ),
            )
        return model, revision, output, NATIVE_RETURN_SEMANTICS, source, None

    if len(contracts) > 1:
        return (
            None,
            None,
            None,
            None,
            None,
            (
                RankingEntryStatus.DATA_CHECK,
                "Multiple current legacy model-output contracts exist; no single Portfolio Score "
                "input can be selected safely.",
            ),
        )
    if not contracts:
        return (
            None,
            None,
            None,
            None,
            None,
            (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "No point-in-time model output provides the Portfolio Score valuation inputs.",
            ),
        )
    snapshot = contracts[0]
    listing, listing_error = _legacy_listing(session, company, snapshot, models, as_of)
    source = _legacy_model_source(session, snapshot, listing)
    if listing_error:
        return (
            None,
            None,
            snapshot,
            LEGACY_RETURN_SEMANTICS,
            source,
            (RankingEntryStatus.DATA_CHECK, listing_error),
        )
    if snapshot.contract_status != "PASS" or snapshot.output_quality != "COMPLETE":
        status = (
            RankingEntryStatus.INPUTS_UNAVAILABLE
            if snapshot.output_quality == "UNAVAILABLE"
            else RankingEntryStatus.DATA_CHECK
        )
        return (
            None,
            None,
            snapshot,
            LEGACY_RETURN_SEMANTICS,
            source,
            (status, "The legacy model status is not a complete PASS contract."),
        )
    if snapshot.currency_status != "DOCUMENTED" or snapshot.model_currency is None:
        return (
            None,
            None,
            snapshot,
            LEGACY_RETURN_SEMANTICS,
            source,
            (RankingEntryStatus.DATA_CHECK, "Legacy model currency is unknown."),
        )
    required_field_names = {
        "bear_fv",
        "weighted_fv",
        "bull_fv",
        "expected_cash_flow_irr",
        "hurdle",
    }
    issue_fields = {issue.get("field") for issue in snapshot.field_issues}
    if issue_fields & required_field_names:
        return (
            None,
            None,
            snapshot,
            LEGACY_RETURN_SEMANTICS,
            source,
            (
                RankingEntryStatus.DATA_CHECK,
                "A required legacy model output has a field-level issue.",
            ),
        )
    if any(
        value is None
        for value in (
            snapshot.expected_cash_flow_irr,
            snapshot.bear_fv,
            snapshot.weighted_fv,
            snapshot.bull_fv,
            snapshot.hurdle,
        )
    ):
        return (
            None,
            None,
            snapshot,
            LEGACY_RETURN_SEMANTICS,
            source,
            (RankingEntryStatus.INPUTS_UNAVAILABLE, "A required model output is unavailable."),
        )
    return None, None, snapshot, LEGACY_RETURN_SEMANTICS, source, None


def _native_price_error(
    session: Session,
    model: FinancialModel,
    output: FinancialModelOutput,
    as_of: datetime,
) -> str | None:
    if output.price_status != "FRESH" or output.price_effective_at is None:
        return "The native model output has no fresh, dated reference price."
    age_days = (as_of.date() - output.price_effective_at.astimezone(UTC).date()).days
    if age_days < 0 or age_days > FRESH_DAYS:
        return "The native model reference price is outside the five-day freshness window."
    latest_price = session.scalar(
        select(PriceObservation)
        .where(
            PriceObservation.listing_id == model.valuation_listing_id,
            PriceObservation.market_date <= as_of,
            PriceObservation.recorded_at <= as_of,
            or_(PriceObservation.observed_at.is_(None), PriceObservation.observed_at <= as_of),
            PriceObservation.data_quality.in_(("PASS", "PASS_VERIFIED_FALLBACK")),
        )
        .order_by(PriceObservation.market_date.desc(), PriceObservation.recorded_at.desc())
        .limit(1)
    )
    if latest_price is None:
        return "No exact-listing market price is available for the native model."
    if (
        latest_price.market_date.astimezone(UTC).date()
        > output.price_effective_at.astimezone(UTC).date()
    ):
        return "A later exact-listing price exists than the price used by the native model output."
    return None


def _native_model_source(
    session: Session,
    model: FinancialModel,
    revision: FinancialModelRevision,
    output: FinancialModelOutput | None,
) -> dict[str, Any]:
    listing = session.get(Listing, model.valuation_listing_id)
    return {
        "source_kind": "NATIVE_MODEL_REVISION",
        "record_id": str(output.id if output else revision.id),
        "model_id": str(model.id),
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "model_key": model.source_model_key or model.model_name,
        "model_type": revision.model_type,
        "methodology_version": revision.methodology_version,
        "source": revision.source,
        "effective_at": revision.effective_at.isoformat(),
        "recorded_at": revision.recorded_at.isoformat(),
        "effective_time_status": "KNOWN",
        "model_currency": model.model_currency,
        "currency_status": "DOCUMENTED" if model.model_currency else "UNKNOWN",
        "output_quality": output.status if output else "UNAVAILABLE",
        "contract_status": None,
        "price_status": output.price_status if output else None,
        "price_effective_at": output.price_effective_at.isoformat()
        if output and output.price_effective_at
        else None,
        "price_observation_id": str(output.price_observation_id)
        if output and output.price_observation_id
        else None,
        "listing_id": str(listing.id) if listing else None,
        "listing_ticker": listing.ticker if listing else None,
        "listing_venue": listing.venue if listing else None,
    }


def _legacy_listing(
    session: Session,
    company: Company,
    snapshot: ModelOutputSnapshot,
    models: list[FinancialModel],
    as_of: datetime,
) -> tuple[Listing | None, str | None]:
    matches = [model for model in models if model.source_model_key == snapshot.model_key]
    if len(matches) > 1:
        return None, "Legacy model key maps to multiple native model listings."
    if matches:
        listing = session.get(Listing, matches[0].valuation_listing_id)
        if listing is None or listing.created_at > as_of:
            return None, "Legacy model's exact valuation listing is unavailable as of this run."
        return listing, None
    listings = list(
        session.scalars(
            select(Listing)
            .join(Security, Security.id == Listing.security_id)
            .where(
                Security.company_id == company.id,
                Security.created_at <= as_of,
                Listing.created_at <= as_of,
            )
            .order_by(Listing.ticker, Listing.venue, Listing.id)
        )
    )
    if len(listings) != 1:
        return None, "No unique exact listing maps to the legacy model key."
    return listings[0], None


def _legacy_model_source(
    session: Session, snapshot: ModelOutputSnapshot, listing: Listing | None
) -> dict[str, Any]:
    return {
        "source_kind": "IMPORTED_CURRENT_CONTRACT",
        "record_id": str(snapshot.id),
        "model_id": None,
        "revision_id": None,
        "revision_number": None,
        "model_key": snapshot.model_key,
        "model_type": None,
        "methodology_version": snapshot.contract_version,
        "source": snapshot.source,
        "effective_at": snapshot.effective_at.isoformat() if snapshot.effective_at else None,
        "recorded_at": snapshot.recorded_at.isoformat(),
        "effective_time_status": "KNOWN" if snapshot.effective_at else "UNKNOWN",
        "model_currency": snapshot.model_currency,
        "currency_status": snapshot.currency_status,
        "output_quality": snapshot.output_quality,
        "contract_status": snapshot.contract_status,
        "price_status": None,
        "price_effective_at": None,
        "price_observation_id": None,
        "listing_id": str(listing.id) if listing else None,
        "listing_ticker": listing.ticker if listing else None,
        "listing_venue": listing.venue if listing else None,
    }


def _portfolio_input_snapshot(
    portfolio_view: Any,
    context: Any,
    score_context: dict[str, dict[str, Any]],
    model_source: dict[str, Any] | None,
    output: FinancialModelOutput | ModelOutputSnapshot | None,
    calculation: PortfolioScoreResult | None,
    *,
    lifecycle: str | None,
    expected_excess: Decimal | None = None,
    uncertainty: Decimal | None = None,
) -> dict[str, Any]:
    if output is None:
        expected_irr = bear_fv = weighted_fv = bull_fv = hurdle = None
    else:
        expected_irr = output.expected_cash_flow_irr
        bear_fv = output.bear_fv
        weighted_fv = output.weighted_fv
        bull_fv = output.bull_fv
        hurdle = output.hurdle
        if expected_excess is None:
            expected_excess = output.expected_excess
        if (
            uncertainty is None
            and bear_fv is not None
            and weighted_fv is not None
            and weighted_fv != ZERO
            and bull_fv is not None
        ):
            uncertainty = (bull_fv - bear_fv) / weighted_fv

    snapshot = s.PortfolioRankInputSnapshot.model_validate(
        {
            "context_version": PORTFOLIO_RANK_CONTEXT_VERSION,
            "score_formula": PORTFOLIO_SCORE_VERSION,
            "portfolio_score": calculation.score if calculation else None,
            "current_weight": context.current_weight,
            "target_weight": context.target_weight,
            "target_minus_current_gap": context.allocation_gap,
            "allocation_status": context.allocation_status,
            "lifecycle": lifecycle,
            "holding_snapshot_id": portfolio_view.snapshot.id if portfolio_view.snapshot else None,
            "holding_effective_at": (
                portfolio_view.snapshot.effective_at if portfolio_view.snapshot else None
            ),
            "target_revision_id": (
                portfolio_view.target_revision.id if portfolio_view.target_revision else None
            ),
            "target_effective_at": (
                portfolio_view.target_revision.effective_at
                if portfolio_view.target_revision
                else None
            ),
            "expected_irr": expected_irr,
            "expected_excess": expected_excess,
            "hurdle": hurdle,
            "bear_fair_value": bear_fv,
            "weighted_fair_value": weighted_fv,
            "bull_fair_value": bull_fv,
            "valuation_uncertainty": uncertainty,
            "durability_10y": _score_snapshot(score_context["durability_10y"]),
            "compounder_quality": _score_snapshot(score_context["compounder_quality"]),
            "execution": _score_snapshot(score_context["execution"]),
            "risk": _score_snapshot(score_context["risk"]),
            "model_source": model_source,
            "score_contributions": {
                "target_underweight": (
                    calculation.contributions["target_underweight"] if calculation else None
                ),
                "expected_irr": calculation.contributions["expected_irr"] if calculation else None,
                "durability_10y": calculation.contributions["durability_10y"]
                if calculation
                else None,
                "compounder_quality": calculation.contributions["compounder_quality"]
                if calculation
                else None,
                "execution": calculation.contributions["execution"] if calculation else None,
                "risk": calculation.contributions["risk"] if calculation else None,
                "valuation_uncertainty_penalty": (
                    calculation.contributions["valuation_uncertainty_penalty"]
                    if calculation
                    else None
                ),
                "negative_expected_excess_penalty": (
                    calculation.contributions["negative_expected_excess_penalty"]
                    if calculation
                    else None
                ),
            },
            "context_note": (
                "Reproduces the source IRR-First Allocation Score: target-underweight credit, "
                "Expected Cash-Flow IRR, 10Y Durability, Compounder Quality, Execution, Risk, "
                "valuation-range uncertainty penalty, and negative Expected Excess penalty. "
                "Current weight, strategic target, and their gap remain separate facts; the rank "
                "does not change targets, holdings, or Execution Pace. Missing inputs remain null."
            ),
        }
    )
    return snapshot.model_dump(mode="json")


def _score_snapshot(score: dict[str, Any]) -> dict[str, Any]:
    if score["definition_error"]:
        return {
            "score": None,
            "status": "INVALID",
            "assessment_id": score["assessment_id"],
            "effective_at": score["effective_at"],
            "recorded_at": score["recorded_at"],
            "source": score["source"],
        }
    return {
        "score": score["score"],
        "status": score["status"],
        "assessment_id": score["assessment_id"],
        "effective_at": score["effective_at"],
        "recorded_at": score["recorded_at"],
        "source": score["source"],
    }
