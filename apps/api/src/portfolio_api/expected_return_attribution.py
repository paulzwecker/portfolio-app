"""Point-in-time attribution for native expected-return revisions.

Native revisions use a symmetric four-factor Shapley bridge, recalculated by
their retained deterministic model engine. Legacy outputs are never inferred.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, localcontext
from math import factorial
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    FinancialModelType,
)
from portfolio_api.domain.services import DomainError
from portfolio_api.financial_model_archetypes import (
    ArchetypeCalculation,
    calculate_owner_cash_flow,
    calculate_residual_income,
)
from portfolio_api.financial_models import (
    DcfCalculation,
    MarketPriceInput,
    calculate_ufcf_dcf,
)

type AttributionInput = s.DcfCalculationInput | s.OwnerCashFlowInput | s.ResidualIncomeInput
type AttributionStatus = Literal[
    "ATTRIBUTED",
    "OUTPUTS_ONLY",
    "MISSING_RETURN",
    "RETURN_SEMANTICS_CHANGE",
    "MODEL_SERIES_CHANGE",
    "METHODOLOGY_CHANGE",
    "INPUTS_UNAVAILABLE",
    "RECALCULATION_MISMATCH",
    "UNDATED",
]
FACTOR_CODES = (
    "MARKET_PRICE",
    "SCENARIO_PROBABILITIES",
    "REQUIRED_RETURN_ASSUMPTIONS",
    "MODEL_ASSUMPTIONS",
)
RECALCULATION_TOLERANCE = Decimal("0.000000000001")


def symmetric_shapley_decomposition(
    evaluate: Callable[[int], Decimal], factors: tuple[str, ...] = FACTOR_CODES
) -> dict[str, Decimal]:
    """Calculate order-independent effects for binary counterfactual factors."""
    count = len(factors)
    if count == 0:
        return {}
    worlds = {mask: evaluate(mask) for mask in range(1 << count)}
    result: dict[str, Decimal] = {}
    denominator = Decimal(factorial(count))
    for index, factor in enumerate(factors):
        bit = 1 << index
        contribution = Decimal(0)
        for mask in range(1 << count):
            if mask & bit:
                continue
            size = mask.bit_count()
            weight = Decimal(factorial(size) * factorial(count - size - 1)) / denominator
            contribution += weight * (worlds[mask | bit] - worlds[mask])
        result[factor] = contribution
    return result


def company_expected_return_attribution(
    session: Session,
    company_id: UUID,
    prior_point_id: str,
    current_point_id: str,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyExpectedReturnAttributionRead:
    """Compare two retained points without changing or synthesizing their history."""
    history = q.company_expected_return_history(session, company_id, as_of, known_at)
    points = {point.point_id: point for point in history.history}
    prior = points.get(prior_point_id)
    current = points.get(current_point_id)
    if prior is None or current is None:
        raise DomainError(
            "Both attribution points must belong to this company and requested history cutoff",
            404,
        )
    if prior.point_id == current.point_id:
        raise DomainError("Choose two different history points", 422)
    if (
        prior.effective_at is not None
        and current.effective_at is not None
        and (prior.effective_at, prior.recorded_at) > (current.effective_at, current.recorded_at)
    ):
        raise DomainError("The prior point must not follow the current point", 422)

    prior_state, current_state = _state_read(prior), _state_read(current)
    context = _context_changes(prior, current)
    if prior.effective_at is None or current.effective_at is None:
        return _unavailable(
            company_id,
            "UNDATED",
            prior_state,
            current_state,
            None,
            None,
            "Both endpoints need an effective timestamp for a point-in-time comparison.",
            context,
        )
    old_irr, new_irr = prior.expected_cash_flow_irr, current.expected_cash_flow_irr
    if old_irr is None or new_irr is None:
        return _unavailable(
            company_id,
            "MISSING_RETURN",
            prior_state,
            current_state,
            None,
            None,
            "At least one endpoint has no valid Expected IRR. Missing values are not zero.",
            context,
        )
    if prior.return_semantics != current.return_semantics:
        return _unavailable(
            company_id,
            "RETURN_SEMANTICS_CHANGE",
            prior_state,
            current_state,
            None,
            None,
            "Legacy normalized fields and native shareholder-cash-flow IRR "
            "are not assumed comparable.",
            context,
        )

    total = new_irr - old_irr
    if prior.return_semantics == "LEGACY_NORMALIZED_FIELD":
        return _unavailable(
            company_id,
            "OUTPUTS_ONLY",
            prior_state,
            current_state,
            total,
            total,
            "Legacy snapshots retain reported outputs but not accepted inputs for a "
            "supported counterfactual. The full change remains unexplained.",
            context,
        )
    if prior.model_id is None or prior.model_id != current.model_id:
        return _unavailable(
            company_id,
            "MODEL_SERIES_CHANGE",
            prior_state,
            current_state,
            total,
            total,
            "The endpoints belong to different model series. The arithmetic change is shown, "
            "but no cross-model effects are attributed.",
            context,
        )
    if (
        prior.model_type != current.model_type
        or prior.methodology_version != current.methodology_version
    ):
        return _unavailable(
            company_id,
            "METHODOLOGY_CHANGE",
            prior_state,
            current_state,
            total,
            total,
            "The model type or methodology version changed. The arithmetic change remains "
            "residual; methods are not cross-recalculated.",
            context,
        )

    try:
        recalculation = _native_counterfactuals(session, prior, current, old_irr, new_irr)
    except (ValueError, LookupError, ArithmeticError, DomainError) as error:
        return _unavailable(
            company_id,
            "INPUTS_UNAVAILABLE",
            prior_state,
            current_state,
            total,
            total,
            f"Complete counterfactuals could not be calculated from retained inputs: {error}",
            context,
        )
    if recalculation is None:
        return _unavailable(
            company_id,
            "INPUTS_UNAVAILABLE",
            prior_state,
            current_state,
            total,
            total,
            "The source revisions do not retain a complete, comparable price and assumption set. "
            "The full change remains unexplained.",
            context,
        )
    worlds, endpoints_match = recalculation
    if not endpoints_match:
        return _unavailable(
            company_id,
            "RECALCULATION_MISMATCH",
            prior_state,
            current_state,
            total,
            total,
            "Recalculation did not reproduce both stored endpoint IRRs within tolerance; "
            "no driver effects are reported.",
            context,
        )

    with localcontext() as decimal_context:
        decimal_context.prec = 38
        contributions = symmetric_shapley_decomposition(lambda mask: worlds[mask], FACTOR_CODES)
        residual = total - sum(contributions.values(), Decimal(0))
    descriptions = {
        "MARKET_PRICE": (
            "Market-price movement",
            "The exact accepted reference prices are substituted into the same revision engines.",
        ),
        "SCENARIO_PROBABILITIES": (
            "Scenario-probability changes",
            "Weights the retained scenario shareholder cash flows; scenario IRRs are not averaged.",
        ),
        "REQUIRED_RETURN_ASSUMPTIONS": (
            "Required-return assumptions",
            "Changes to discount rates, required return or cost of equity affect model valuation. "
            "A lower hurdle is a changed return constraint, not improved company economics.",
        ),
        "MODEL_ASSUMPTIONS": (
            "Operating and model assumptions",
            "Other accepted cash-flow, balance-sheet and terminal assumptions. Fair-value changes "
            "are shown as context, not used as a proxy for IRR effects.",
        ),
    }
    drivers = [
        s.ExpectedReturnAttributionDriverRead(
            code=code,
            label=descriptions[code][0],
            effect=contributions[code],
            explanation=descriptions[code][1],
        )
        for code in FACTOR_CODES
    ]
    return s.CompanyExpectedReturnAttributionRead(
        company_id=company_id,
        status="ATTRIBUTED",
        method="SYMMETRIC_COUNTERFACTUAL_SHAPLEY",
        prior=prior_state,
        current=current_state,
        expected_irr_change=total,
        drivers=drivers,
        residual=residual,
        residual_reason=(
            "Endpoint change minus the four symmetric effects. This retains any stored-output "
            "rounding or reconciliation difference without assigning it to a driver."
            if residual != 0
            else None
        ),
        context_changes=context,
        estimate_context_note=(
            "Point-in-time consensus observations, observation IDs and source references are "
            "retained at both endpoints. Current native engines do not consume consensus "
            "estimates, so estimate revisions are context only and receive no causal contribution."
        ),
    )


def _native_counterfactuals(
    session: Session,
    prior: s.ExpectedReturnHistoryPointRead,
    current: s.ExpectedReturnHistoryPointRead,
    prior_irr: Decimal,
    current_irr: Decimal,
) -> tuple[dict[int, Decimal], bool] | None:
    if prior.revision_id is None or current.revision_id is None or prior.model_id is None:
        return None
    model = session.get(FinancialModel, prior.model_id)
    old_row = session.get(FinancialModelRevision, prior.revision_id)
    new_row = session.get(FinancialModelRevision, current.revision_id)
    if model is None or old_row is None or new_row is None:
        return None
    old_output = session.scalar(
        select(FinancialModelOutput).where(FinancialModelOutput.revision_id == old_row.id)
    )
    new_output = session.scalar(
        select(FinancialModelOutput).where(FinancialModelOutput.revision_id == new_row.id)
    )
    if old_output is None or new_output is None:
        return None
    if (
        old_output.price_status != "FRESH"
        or new_output.price_status != "FRESH"
        or old_output.current_price is None
        or new_output.current_price is None
        or old_output.current_price <= 0
        or new_output.current_price <= 0
        or old_output.model_currency != new_output.model_currency
        or model.model_currency != old_output.model_currency
    ):
        return None

    if model.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        old_input: AttributionInput = _dcf_input(
            q.financial_model_revision(session, model.id, old_row.id)
        )
        new_input: AttributionInput = _dcf_input(
            q.financial_model_revision(session, model.id, new_row.id)
        )
    elif model.model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        old_input = _owner_cash_flow_input(
            q.extended_financial_model_revision(session, model.id, old_row.id)
        )
        new_input = _owner_cash_flow_input(
            q.extended_financial_model_revision(session, model.id, new_row.id)
        )
    elif model.model_type == FinancialModelType.RESIDUAL_INCOME_10Y_FADE:
        old_input = _residual_income_input(
            q.extended_financial_model_revision(session, model.id, old_row.id)
        )
        new_input = _residual_income_input(
            q.extended_financial_model_revision(session, model.id, new_row.id)
        )
    else:
        return None

    old_price, new_price = _price_input(old_output), _price_input(new_output)
    worlds: dict[int, Decimal] = {}
    for mask in range(1 << len(FACTOR_CODES)):
        revision = _merge_inputs(old_input, new_input, mask)
        price = new_price if mask & 1 else old_price
        calculation = _calculate(model.model_type, revision, model.model_currency, price)
        if calculation.expected_cash_flow_irr is None:
            return None
        worlds[mask] = calculation.expected_cash_flow_irr
    full_mask = (1 << len(FACTOR_CODES)) - 1
    matches = (
        abs(worlds[0] - prior_irr) <= RECALCULATION_TOLERANCE
        and abs(worlds[full_mask] - current_irr) <= RECALCULATION_TOLERANCE
    )
    return worlds, matches


def _price_input(output: FinancialModelOutput) -> MarketPriceInput:
    return MarketPriceInput(
        observation_id=output.price_observation_id,
        price=output.current_price,
        currency=output.model_currency,
        effective_at=output.price_effective_at,
        freshness="FRESH",
    )


def _dcf_input(value: s.FinancialModelRevisionRead) -> s.DcfCalculationInput:
    return s.DcfCalculationInput.model_validate(
        {
            "base": value.base.model_dump(),
            "scenarios": [
                {
                    "scenario": scenario.scenario,
                    "probability": scenario.probability,
                    "terminal_growth": scenario.terminal_growth,
                    "year10_ufcf_growth": scenario.year10_ufcf_growth,
                    "rationale": scenario.rationale,
                    "years": [
                        {
                            key: getattr(year, key)
                            for key in (
                                "forecast_year",
                                "revenue_growth",
                                "ebit_margin",
                                "tax_rate",
                                "da_to_revenue",
                                "capex_to_revenue",
                                "nwc_to_revenue",
                                "discount_rate",
                            )
                        }
                        for year in scenario.years
                    ],
                }
                for scenario in value.scenarios
            ],
        }
    )


def _owner_cash_flow_input(
    value: s.OwnerCashFlowRevisionRead | s.ResidualIncomeRevisionRead,
) -> s.OwnerCashFlowInput:
    if not isinstance(value, s.OwnerCashFlowRevisionRead):
        raise ValueError("Stored inputs do not match the owner-cash-flow archetype")
    return s.OwnerCashFlowInput.model_validate(
        {
            "base": value.base.model_dump(),
            "scenarios": [
                {
                    "scenario": item.scenario,
                    "probability": item.probability,
                    "required_return": item.required_return,
                    "terminal_growth": item.terminal_growth,
                    "rationale": item.rationale,
                    "years": [
                        {
                            "forecast_year": year.forecast_year,
                            "revenue_growth": year.revenue_growth,
                            "owner_cash_flow_margin": year.owner_cash_flow_margin,
                        }
                        for year in item.years
                    ],
                }
                for item in value.scenarios
            ],
        }
    )


def _residual_income_input(
    value: s.OwnerCashFlowRevisionRead | s.ResidualIncomeRevisionRead,
) -> s.ResidualIncomeInput:
    if not isinstance(value, s.ResidualIncomeRevisionRead):
        raise ValueError("Stored inputs do not match the residual-income archetype")
    return s.ResidualIncomeInput.model_validate(
        {
            "base": value.base.model_dump(),
            "scenarios": [
                {
                    "scenario": item.scenario,
                    "probability": item.probability,
                    "starting_roe": item.starting_roe,
                    "cost_of_equity": item.cost_of_equity,
                    "terminal_growth": item.terminal_growth,
                    "mature_roe": item.mature_roe,
                    "rationale": item.rationale,
                }
                for item in value.scenarios
            ],
        }
    )


def _merge_inputs(
    prior: AttributionInput, current: AttributionInput, mask: int
) -> AttributionInput:
    model_now = bool(mask & (1 << FACTOR_CODES.index("MODEL_ASSUMPTIONS")))
    probability_now = bool(mask & (1 << FACTOR_CODES.index("SCENARIO_PROBABILITIES")))
    rate_now = bool(mask & (1 << FACTOR_CODES.index("REQUIRED_RETURN_ASSUMPTIONS")))
    model_input = current if model_now else prior
    probability_input = current if probability_now else prior
    rate_input = current if rate_now else prior

    if isinstance(prior, s.DcfCalculationInput) and isinstance(current, s.DcfCalculationInput):
        assert isinstance(model_input, s.DcfCalculationInput)
        assert isinstance(probability_input, s.DcfCalculationInput)
        assert isinstance(rate_input, s.DcfCalculationInput)
        probabilities = {row.scenario: row.probability for row in probability_input.scenarios}
        rates = {row.scenario: row for row in rate_input.scenarios}
        dcf_scenarios = []
        for row in model_input.scenarios:
            rate_years = {
                year.forecast_year: year.discount_rate for year in rates[row.scenario].years
            }
            dcf_scenarios.append(
                row.model_copy(
                    update={
                        "probability": probabilities[row.scenario],
                        "years": [
                            year.model_copy(
                                update={"discount_rate": rate_years[year.forecast_year]}
                            )
                            for year in row.years
                        ],
                    }
                )
            )
        return s.DcfCalculationInput(base=model_input.base, scenarios=dcf_scenarios)
    if isinstance(prior, s.OwnerCashFlowInput) and isinstance(current, s.OwnerCashFlowInput):
        assert isinstance(model_input, s.OwnerCashFlowInput)
        assert isinstance(probability_input, s.OwnerCashFlowInput)
        assert isinstance(rate_input, s.OwnerCashFlowInput)
        owner_probabilities = {row.scenario: row.probability for row in probability_input.scenarios}
        owner_rates = {row.scenario: row.required_return for row in rate_input.scenarios}
        owner_scenarios = [
            row.model_copy(
                update={
                    "probability": owner_probabilities[row.scenario],
                    "required_return": owner_rates[row.scenario],
                }
            )
            for row in model_input.scenarios
        ]
        return s.OwnerCashFlowInput(base=model_input.base, scenarios=owner_scenarios)
    if isinstance(prior, s.ResidualIncomeInput) and isinstance(current, s.ResidualIncomeInput):
        assert isinstance(model_input, s.ResidualIncomeInput)
        assert isinstance(probability_input, s.ResidualIncomeInput)
        assert isinstance(rate_input, s.ResidualIncomeInput)
        income_probabilities = {
            row.scenario: row.probability for row in probability_input.scenarios
        }
        income_rates = {row.scenario: row.cost_of_equity for row in rate_input.scenarios}
        income_scenarios = [
            row.model_copy(
                update={
                    "probability": income_probabilities[row.scenario],
                    "cost_of_equity": income_rates[row.scenario],
                }
            )
            for row in model_input.scenarios
        ]
        return s.ResidualIncomeInput(base=model_input.base, scenarios=income_scenarios)
    raise ValueError("Prior and current revisions use different input contracts")


def _calculate(
    model_type: str,
    revision: AttributionInput,
    currency: str,
    price: MarketPriceInput,
) -> DcfCalculation | ArchetypeCalculation:
    if model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        if not isinstance(revision, s.DcfCalculationInput):
            raise ValueError("Stored inputs do not match UFCF DCF")
        return calculate_ufcf_dcf(revision, model_currency=currency, market_price=price)
    if model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        if not isinstance(revision, s.OwnerCashFlowInput):
            raise ValueError("Stored inputs do not match owner cash flow")
        return calculate_owner_cash_flow(revision, model_currency=currency, market_price=price)
    if model_type == FinancialModelType.RESIDUAL_INCOME_10Y_FADE:
        if not isinstance(revision, s.ResidualIncomeInput):
            raise ValueError("Stored inputs do not match residual income")
        return calculate_residual_income(revision, model_currency=currency, market_price=price)
    raise ValueError(f"Unsupported model type {model_type}")


def _state_read(
    point: s.ExpectedReturnHistoryPointRead,
) -> s.ExpectedReturnAttributionStateRead:
    return s.ExpectedReturnAttributionStateRead(
        point_id=point.point_id,
        source_kind=point.source_kind,
        effective_at=point.effective_at,
        recorded_at=point.recorded_at,
        series_id=point.series_id,
        model_id=point.model_id,
        revision_id=point.revision_id,
        revision_number=point.revision_number,
        model_type=point.model_type,
        methodology_version=point.methodology_version,
        return_semantics=point.return_semantics,
        model_currency=point.model_currency,
        expected_cash_flow_irr=point.expected_cash_flow_irr,
        hurdle=point.hurdle,
        expected_excess=point.expected_excess,
        bear_fv=point.bear_fv,
        base_fv=point.base_fv,
        bull_fv=point.bull_fv,
        bear_probability=point.bear_probability,
        base_probability=point.base_probability,
        bull_probability=point.bull_probability,
        weighted_fv=point.weighted_fv,
        market_price=point.market_price,
        estimate_context=point.estimate_context,
        source=point.source,
        source_revision_id=point.source_revision_id,
        rationale=point.rationale,
    )


def _context_changes(
    prior: s.ExpectedReturnHistoryPointRead, current: s.ExpectedReturnHistoryPointRead
) -> s.ExpectedReturnAttributionContextChangesRead:
    same_model_context = (
        prior.series_id == current.series_id
        and prior.return_semantics == current.return_semantics
        and prior.model_type == current.model_type
        and prior.methodology_version == current.methodology_version
    )
    same_currency = (
        prior.model_currency is not None and prior.model_currency == current.model_currency
    )

    def delta(field: str) -> Decimal | None:
        if not same_model_context:
            return None
        if field in {"weighted_fv", "bear_fv", "base_fv", "bull_fv"} and not same_currency:
            return None
        old, new = getattr(prior, field), getattr(current, field)
        return new - old if old is not None and new is not None else None

    return s.ExpectedReturnAttributionContextChangesRead(
        weighted_fv=delta("weighted_fv"),
        bear_fv=delta("bear_fv"),
        base_fv=delta("base_fv"),
        bull_fv=delta("bull_fv"),
        bear_probability=delta("bear_probability"),
        base_probability=delta("base_probability"),
        bull_probability=delta("bull_probability"),
        hurdle=delta("hurdle"),
        expected_excess=delta("expected_excess"),
    )


def _unavailable(
    company_id: UUID,
    status: AttributionStatus,
    prior: s.ExpectedReturnAttributionStateRead,
    current: s.ExpectedReturnAttributionStateRead,
    change: Decimal | None,
    residual: Decimal | None,
    reason: str,
    context: s.ExpectedReturnAttributionContextChangesRead,
) -> s.CompanyExpectedReturnAttributionRead:
    return s.CompanyExpectedReturnAttributionRead(
        company_id=company_id,
        status=status,
        method="UNAVAILABLE",
        prior=prior,
        current=current,
        expected_irr_change=change,
        drivers=[],
        residual=residual,
        residual_reason=reason,
        context_changes=context,
        estimate_context_note=(
            "Point-in-time consensus observations, observation IDs and source references remain "
            "linked in both endpoint states. Estimate changes are not causal drivers unless the "
            "accepted model methodology consumes them."
        ),
    )
