"""Read-only entry-price analysis of accepted, method-specific return cash flows."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import overload
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.current_model_calculation import (
    current_native_model_calculation,
    dcf_inputs_for_revision,
)
from portfolio_api.domain import queries
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    DcfScenario,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    FinancialModelType,
    Listing,
    Security,
)
from portfolio_api.domain.services import DomainError
from portfolio_api.financial_model_archetypes import (
    ArchetypeCalculation,
    OwnerCashFlowProjectionCalculation,
    ResidualIncomeProjectionCalculation,
    calculate_owner_cash_flow,
    calculate_residual_income,
)
from portfolio_api.financial_models import (
    DcfCalculation,
    MarketPriceInput,
    _irr,
    calculate_ufcf_dcf,
)
from portfolio_api.return_semantics import (
    OWNER_CASH_FLOW_EQUITY_IRR,
    RESIDUAL_INCOME_EQUITY_IRR,
    UFCF_ENTERPRISE_HMODEL_IRR,
    UFCF_ENTERPRISE_IRR,
)

NativeInputs = s.DcfCalculationInput | s.OwnerCashFlowInput | s.ResidualIncomeInput
ZERO = Decimal(0)
TOLERANCE = Decimal("0.000000000001")


@overload
def stored(value: Decimal) -> Decimal: ...


@overload
def stored(value: None) -> None: ...


def stored(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 60
        return value.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP)


def _calculate(
    inputs: NativeInputs, currency: str, method: str, price: Decimal | None = None
) -> DcfCalculation | ArchetypeCalculation:
    quote = MarketPriceInput(
        None, price, currency, None, "FRESH" if price is not None else "NO_DATA"
    )
    if isinstance(inputs, s.DcfCalculationInput):
        if method not in {UFCF_ENTERPRISE_IRR, UFCF_ENTERPRISE_HMODEL_IRR}:
            raise ValueError("Unsupported DCF return method")
        return calculate_ufcf_dcf(
            inputs, model_currency=currency, market_price=quote, return_methodology_code=method
        )
    if isinstance(inputs, s.OwnerCashFlowInput) and method == OWNER_CASH_FLOW_EQUITY_IRR:
        return calculate_owner_cash_flow(inputs, model_currency=currency, market_price=quote)
    if isinstance(inputs, s.ResidualIncomeInput) and method == RESIDUAL_INCOME_EQUITY_IRR:
        return calculate_residual_income(inputs, model_currency=currency, market_price=quote)
    raise ValueError("Accepted model and return method do not match")


@dataclass(frozen=True)
class ReturnStream:
    """Per-share units; bridge is added to PV only for enterprise entry pricing."""

    annual: tuple[Decimal, ...]
    terminal: Decimal
    opening_bridge: Decimal

    def flows(self) -> list[Decimal]:
        return [*self.annual[:-1], self.annual[-1] + self.terminal]


def _streams(
    inputs: NativeInputs, calculation: DcfCalculation | ArchetypeCalculation
) -> list[tuple[DcfScenario, Decimal, ReturnStream]]:
    result = []
    if isinstance(inputs, s.DcfCalculationInput) and isinstance(calculation, DcfCalculation):
        for case in calculation.scenarios:
            result.append(
                (
                    case.scenario,
                    case.probability,
                    ReturnStream(
                        tuple(
                            p.unlevered_free_cash_flow / inputs.base.diluted_shares
                            for p in case.projections
                        ),
                        case.return_terminal_value / inputs.base.diluted_shares,
                        inputs.base.net_cash_debt / inputs.base.diluted_shares,
                    ),
                )
            )
        return result
    if not isinstance(calculation, ArchetypeCalculation):
        raise ValueError("Unsupported calculation stream")
    for archetype_case in calculation.scenarios:
        if isinstance(inputs, s.OwnerCashFlowInput):
            owner_rows = archetype_case.projections
            if not all(isinstance(p, OwnerCashFlowProjectionCalculation) for p in owner_rows):
                raise ValueError("Invalid owner-cash-flow projections")
            annual = tuple(
                p.owner_cash_flow_per_share
                for p in owner_rows
                if isinstance(p, OwnerCashFlowProjectionCalculation)
            )
            terminal = (
                archetype_case.terminal_value_per_share
                + inputs.base.net_cash / inputs.base.diluted_shares
            )
        elif isinstance(inputs, s.ResidualIncomeInput):
            residual_rows = archetype_case.projections
            if not all(isinstance(p, ResidualIncomeProjectionCalculation) for p in residual_rows):
                raise ValueError("Invalid residual-income projections")
            annual = tuple(
                p.dividend_per_share
                for p in residual_rows
                if isinstance(p, ResidualIncomeProjectionCalculation)
            )
            last = residual_rows[-1]
            assert isinstance(last, ResidualIncomeProjectionCalculation)
            terminal = archetype_case.terminal_value_per_share + last.ending_book_value_per_share
        else:
            raise ValueError("Unsupported native inputs")
        result.append(
            (
                archetype_case.scenario,
                archetype_case.probability,
                ReturnStream(annual, terminal, ZERO),
            )
        )
    return result


def _entry_price(
    stream: ReturnStream, target: Decimal
) -> tuple[Decimal | None, str | None, s.ReturnHurdleContributionsRead | None]:
    annual_pv = sum(
        (flow / (1 + target) ** year for year, flow in enumerate(stream.annual, 1)), ZERO
    )
    terminal_pv = stream.terminal / (1 + target) ** 10
    entry_cost = annual_pv + terminal_pv
    price = entry_cost + stream.opening_bridge
    if entry_cost <= 0 or price <= 0:
        return (
            None,
            "The accepted return stream does not support a positive entry cost and price.",
            None,
        )
    # Reconcile the returned decimal price, not an unobservable higher-precision value.
    price = stored(price)
    assert price is not None
    entry_cost = price - stream.opening_bridge
    if price <= 0 or entry_cost <= 0:
        return None, "The target price is below the supported positive decimal precision.", None
    rate = _irr([-entry_cost, *stream.flows()])
    if rate is None or abs(rate - target) > TOLERANCE:
        return (
            None,
            "The accepted cash flows do not reconcile to one conventional target IRR.",
            None,
        )
    return (
        price,
        None,
        s.ReturnHurdleContributionsRead(
            annual_cash_flow_pv_per_share=stored(annual_pv),
            terminal_pv_per_share=stored(terminal_pv),
            opening_balance_sheet_per_share=stored(stream.opening_bridge),
        ),
    )


@dataclass(frozen=True)
class HurdleCalculation:
    accepted_hurdle: Decimal
    weighted_entry_price: Decimal | None
    reconciled_irr: Decimal | None
    unavailable_reason: str | None
    scenarios: list[s.ReturnHurdleScenarioRead]
    contributions: s.ReturnHurdleContributionsRead | None
    cash_flows: list[s.ReturnHurdleCashFlowRead]
    hypothetical_expected_irr: Decimal | None
    hypothetical_unavailable_reason: str | None


def calculate_return_hurdle(
    inputs: NativeInputs,
    *,
    currency: str,
    method: str,
    required_return: Decimal,
    entry_price: Decimal | None = None,
) -> HurdleCalculation:
    """Discount the frozen native return stream; target is not a model-rate edit."""
    # Keep non-HTTP callers under the same exact-decimal/bounded input contract.
    s.ReturnHurdleRequest(
        base_revision_id=UUID(int=0), required_return=required_return, entry_price=entry_price
    )
    with localcontext() as context:
        context.prec = 60
        baseline = _calculate(inputs, currency, method)
        cases = _streams(inputs, baseline)
        weighted = ReturnStream(
            tuple(
                sum((prob * stream.annual[i] for _, prob, stream in cases), ZERO) for i in range(10)
            ),
            sum((prob * stream.terminal for _, prob, stream in cases), ZERO),
            sum((prob * stream.opening_bridge for _, prob, stream in cases), ZERO),
        )
        price, reason, contributions = _entry_price(weighted, required_return)
        reconciled = None
        if price is not None:
            reconciled = _calculate(inputs, currency, method, price).expected_cash_flow_irr
            if reconciled is None or abs(reconciled - required_return) > TOLERANCE:
                price, reconciled, contributions = None, None, None
                reason = "The entry price does not reconcile to the accepted native return engine."
        scenarios = []
        for name, probability, stream in cases:
            case_price, case_reason, _ = _entry_price(stream, required_return)
            scenarios.append(
                s.ReturnHurdleScenarioRead(
                    scenario=name,
                    probability=probability,
                    status="AVAILABLE" if case_price is not None else "UNAVAILABLE",
                    required_entry_price=stored(case_price),
                    unavailable_reason=case_reason,
                )
            )
        hypothetical = (
            _calculate(inputs, currency, method, entry_price) if entry_price is not None else None
        )
        return HurdleCalculation(
            accepted_hurdle=baseline.hurdle,
            weighted_entry_price=stored(price),
            reconciled_irr=stored(reconciled),
            unavailable_reason=reason,
            scenarios=scenarios,
            contributions=contributions,
            cash_flows=[
                s.ReturnHurdleCashFlowRead(
                    forecast_year=year,
                    annual_cash_flow_per_share=stored(flow),
                    terminal_cash_flow_per_share=stored(weighted.terminal if year == 10 else ZERO),
                )
                for year, flow in enumerate(weighted.annual, 1)
            ],
            hypothetical_expected_irr=stored(hypothetical.expected_cash_flow_irr)
            if hypothetical
            else None,
            hypothetical_unavailable_reason=hypothetical.irr_unavailable_reason
            if hypothetical
            else None,
        )


def model_return_hurdle(
    session: Session, model_id: UUID, request: s.ReturnHurdleRequest
) -> s.ReturnHurdleRead:
    now = datetime.now(UTC)
    model = session.get(FinancialModel, model_id)
    if model is None or model.model_type not in set(FinancialModelType):
        raise DomainError("Native financial model not found", 404)
    if model.current_revision_id != request.base_revision_id:
        raise DomainError("The model changed since it was read; reload before analysis", 409)
    revision = session.get(FinancialModelRevision, request.base_revision_id)
    if revision is None or revision.model_id != model.id or revision.model_type != model.model_type:
        raise DomainError("Current model revision is inconsistent", 409)
    if model.created_at > now or revision.effective_at > now or revision.recorded_at > now:
        raise DomainError("The model revision is not yet effective and known", 409)
    accepted = session.scalar(
        select(FinancialModelOutput).where(FinancialModelOutput.revision_id == revision.id)
    )
    if (
        accepted is None
        or accepted.return_methodology is None
        or accepted.return_methodology.version != 1
    ):
        raise DomainError("A supported accepted return methodology is required", 409)
    if (
        accepted.return_methodology.effective_from > now
        or accepted.return_methodology.recorded_at > now
    ):
        raise DomainError("The return methodology is not yet effective and known", 409)
    listing = session.get(Listing, model.valuation_listing_id)
    security = session.get(Security, listing.security_id) if listing else None
    if listing is None or security is None or security.company_id != model.company_id:
        raise DomainError("The model valuation listing identity is inconsistent", 409)
    if model.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        inputs: NativeInputs = dcf_inputs_for_revision(session, revision)
    else:
        read = queries._extended_financial_model_revision_read(session, revision)
        if isinstance(read, s.OwnerCashFlowRevisionRead):
            inputs = s.OwnerCashFlowInput(base=read.base, scenarios=read.scenarios)
        elif isinstance(read, s.ResidualIncomeRevisionRead):
            inputs = s.ResidualIncomeInput(base=read.base, scenarios=read.scenarios)
        else:
            raise DomainError("Accepted native inputs are unavailable", 409)
    try:
        calculation = calculate_return_hurdle(
            inputs,
            currency=model.model_currency,
            method=accepted.return_methodology.code,
            required_return=request.required_return,
            entry_price=request.entry_price,
        )
        current = current_native_model_calculation(
            session, model, revision, as_of=now, known_at=now
        )
    except (ValueError, TypeError) as error:
        raise DomainError("Accepted inputs or return methodology are inconsistent", 409) from error
    if current is None:
        raise DomainError("Current native model evidence is inconsistent", 409)
    market_price = current.read.market_price
    if any(
        stamp is not None and stamp > now
        for stamp in (market_price.effective_at, market_price.observed_at, market_price.recorded_at)
    ):
        market_price = market_price.model_copy(
            update={
                "status": "DATA_CHECK",
                "reason": "The quote is not yet effective and known at this calculation time.",
            }
        )
    available_quote = market_price.status == "AVAILABLE"
    current_price = current.outputs.current_price if available_quote else None
    current_irr = current.outputs.expected_cash_flow_irr if available_quote else None
    gap = None
    if current_price is not None and calculation.weighted_entry_price is not None:
        with localcontext() as context:
            context.prec = 60
            gap = calculation.weighted_entry_price / current_price - 1
    return s.ReturnHurdleRead(
        calculation_version="native-return-hurdle-v1",
        company_id=model.company_id,
        model_id=model.id,
        model_name=model.model_name,
        model_type=model.model_type,
        valuation_listing_id=listing.id,
        ticker=listing.ticker,
        venue=listing.venue,
        model_currency=model.model_currency,
        revision_id=revision.id,
        revision_number=revision.revision_number,
        methodology_version=revision.methodology_version,
        source=revision.source,
        effective_at=revision.effective_at,
        recorded_at=revision.recorded_at,
        calculated_at=now,
        return_methodology=s.ReturnMethodologyRead.model_validate(accepted.return_methodology),
        required_return=request.required_return,
        accepted_hurdle=stored(calculation.accepted_hurdle),
        status="AVAILABLE" if calculation.weighted_entry_price is not None else "UNAVAILABLE",
        unavailable_reason=calculation.unavailable_reason,
        weighted_entry_price=calculation.weighted_entry_price,
        reconciled_irr=calculation.reconciled_irr,
        scenarios=calculation.scenarios,
        contributions=calculation.contributions,
        cash_flows=calculation.cash_flows,
        hypothetical_entry_price=request.entry_price,
        hypothetical_expected_irr=calculation.hypothetical_expected_irr,
        hypothetical_status="NOT_REQUESTED"
        if request.entry_price is None
        else ("AVAILABLE" if calculation.hypothetical_expected_irr is not None else "UNAVAILABLE"),
        hypothetical_unavailable_reason=calculation.hypothetical_unavailable_reason,
        market_price=market_price,
        current_price=stored(current_price),
        current_expected_irr=stored(current_irr),
        current_price_gap_to_required=stored(gap),
    )
