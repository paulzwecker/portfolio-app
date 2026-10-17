"""Read-only current-quote recalculation for immutable accepted native revisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    FinancialModelType,
    Listing,
    Security,
)
from portfolio_api.financial_model_archetypes import (
    ArchetypeCalculation,
    calculate_owner_cash_flow,
    calculate_residual_income,
)
from portfolio_api.financial_models import DcfCalculation, MarketPriceInput, calculate_ufcf_dcf


@dataclass(frozen=True)
class NativeCurrentCalculation:
    """A transient calculation paired with its accepted revision and current quote."""

    read: s.CurrentNativeModelCalculationRead
    outputs: s.FinancialModelCalculationOutputsRead
    accepted_output: FinancialModelOutput | None


def _dcf_inputs(session: Session, revision: FinancialModelRevision) -> s.DcfCalculationInput:
    from portfolio_api.domain import queries

    revision_read = queries._financial_model_revision_read(session, revision)
    scenarios = [
        s.DcfScenarioInput(
            scenario=scenario.scenario,
            probability=scenario.probability,
            terminal_growth=scenario.terminal_growth,
            year10_ufcf_growth=scenario.year10_ufcf_growth,
            rationale=scenario.rationale,
            years=[
                s.DcfYearAssumptionInput.model_validate(
                    year.model_dump(exclude={"id", "scenario_id"})
                )
                for year in scenario.years
            ],
            tail_ufcf_growth=(
                [
                    s.DcfTailGrowthAssumptionInput.model_validate(
                        item.model_dump(exclude={"id", "scenario_id"})
                    )
                    for item in scenario.tail_ufcf_growth
                ]
                if scenario.tail_ufcf_growth is not None
                else None
            ),
        )
        for scenario in revision_read.scenarios
    ]
    return s.DcfCalculationInput(base=revision_read.base, scenarios=scenarios)


def _calculation_outputs(
    calculation: DcfCalculation | ArchetypeCalculation,
    *,
    return_methodology: s.ReturnMethodologyRead,
    model_currency: str,
    forward_fundamental_cagr: Decimal | None,
) -> s.FinancialModelCalculationOutputsRead:
    def stored(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        with localcontext() as context:
            context.prec = 60
            return value.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP)

    return s.FinancialModelCalculationOutputsRead(
        return_methodology=return_methodology,
        status=calculation.status,
        model_currency=model_currency,
        price_observation_id=calculation.price_observation_id,
        current_price=calculation.current_price,
        price_effective_at=calculation.price_effective_at,
        price_status=calculation.price_status,
        price_unavailable_reason=calculation.price_unavailable_reason,
        irr_unavailable_reason=calculation.irr_unavailable_reason,
        bear_fv=stored(calculation.bear_fv),
        base_fv=stored(calculation.base_fv),
        bull_fv=stored(calculation.bull_fv),
        bear_probability=stored(calculation.bear_probability),
        base_probability=stored(calculation.base_probability),
        bull_probability=stored(calculation.bull_probability),
        weighted_fv=stored(calculation.weighted_fv),
        weighted_upside=stored(calculation.weighted_upside),
        expected_cash_flow_irr=stored(calculation.expected_cash_flow_irr),
        hurdle=stored(calculation.hurdle),
        expected_excess=stored(calculation.expected_excess),
        forward_fundamental_cagr=stored(forward_fundamental_cagr),
    )


def calculate_native_revision_at_quote(
    *,
    model_type: str,
    model_currency: str,
    valuation_listing_id: UUID,
    quote_listing_id: UUID | None,
    revision_inputs: s.DcfCalculationInput | s.OwnerCashFlowInput | s.ResidualIncomeInput,
    return_methodology: s.ReturnMethodologyRead,
    forward_fundamental_cagr: Decimal | None,
    accepted_output_id: UUID,
    accepted_reference_price: Decimal | None,
    accepted_reference_price_observation_id: UUID | None,
    accepted_reference_price_effective_at: datetime | None,
    market_price: MarketPriceInput,
    market_price_read: s.ExpectedReturnMarketPriceRead,
    model_id: UUID,
    model_name: str,
    revision_id: UUID,
    revision_number: int,
    methodology_version: str,
    effective_at: datetime,
    recorded_at: datetime,
    calculated_as_of: datetime,
    known_at: datetime,
) -> NativeCurrentCalculation:
    """Recalculate accepted inputs at one exact canonical listing quote, without writes."""

    if quote_listing_id is not None and quote_listing_id != valuation_listing_id:
        raise ValueError("Current model price must come from its exact valuation listing")

    calculation: DcfCalculation | ArchetypeCalculation
    if model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        if not isinstance(revision_inputs, s.DcfCalculationInput):
            raise ValueError("UFCF DCF revision inputs have the wrong model type")
        calculation = calculate_ufcf_dcf(
            revision_inputs,
            model_currency=model_currency,
            market_price=market_price,
            return_methodology_code=return_methodology.code,
        )
    elif model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        if not isinstance(revision_inputs, s.OwnerCashFlowInput):
            raise ValueError("Owner cash-flow revision inputs have the wrong model type")
        if return_methodology.code != "OWNER_CASH_FLOW_EQUITY_IRR":
            raise ValueError("Owner cash-flow methodology metadata is inconsistent")
        calculation = calculate_owner_cash_flow(
            revision_inputs, model_currency=model_currency, market_price=market_price
        )
    elif model_type == FinancialModelType.RESIDUAL_INCOME_10Y_FADE:
        if not isinstance(revision_inputs, s.ResidualIncomeInput):
            raise ValueError("Residual-income revision inputs have the wrong model type")
        if return_methodology.code != "RESIDUAL_INCOME_EQUITY_IRR":
            raise ValueError("Residual-income methodology metadata is inconsistent")
        calculation = calculate_residual_income(
            revision_inputs, model_currency=model_currency, market_price=market_price
        )
    else:
        raise ValueError(f"Unsupported native financial model type: {model_type}")

    outputs = _calculation_outputs(
        calculation,
        return_methodology=return_methodology,
        model_currency=model_currency,
        forward_fundamental_cagr=forward_fundamental_cagr,
    )
    read = s.CurrentNativeModelCalculationRead(
        model_id=model_id,
        model_name=model_name,
        model_type=model_type,
        revision_id=revision_id,
        revision_number=revision_number,
        methodology_version=methodology_version,
        effective_at=effective_at,
        recorded_at=recorded_at,
        calculated_as_of=calculated_as_of,
        known_at=known_at,
        accepted_output_id=accepted_output_id,
        accepted_reference_price=accepted_reference_price,
        accepted_reference_price_observation_id=accepted_reference_price_observation_id,
        accepted_reference_price_effective_at=accepted_reference_price_effective_at,
        market_price=market_price_read,
        outputs=outputs,
    )
    return NativeCurrentCalculation(
        read=read,
        outputs=outputs,
        accepted_output=None,
    )


def current_native_model_calculation(
    session: Session,
    model: FinancialModel,
    revision: FinancialModelRevision,
    *,
    as_of: date | datetime,
    known_at: datetime,
) -> NativeCurrentCalculation | None:
    """Recalculate one accepted revision against its exact listing at two cutoffs."""
    from portfolio_api.domain import queries
    from portfolio_api.domain.queries import listing_market_data

    effective_cutoff = (
        datetime.combine(as_of, time.max, UTC)
        if isinstance(as_of, date) and not isinstance(as_of, datetime)
        else as_of.astimezone(UTC)
    )
    knowledge_cutoff = known_at.astimezone(UTC)
    if revision.effective_at > effective_cutoff or revision.recorded_at > knowledge_cutoff:
        return None
    source_output = session.scalar(
        select(FinancialModelOutput).where(FinancialModelOutput.revision_id == revision.id)
    )
    if source_output is None or source_output.return_methodology is None:
        return None
    listing = session.get(Listing, model.valuation_listing_id)
    if listing is None:
        return None
    security = session.get(Security, listing.security_id)
    if security is None or security.company_id != model.company_id:
        return None

    market = listing_market_data(
        session,
        listing,
        history_limit=0,
        market_as_of=effective_cutoff.date(),
        known_at=knowledge_cutoff,
    )
    quote = market.latest
    quote_id = quote.listing_id if quote else None
    quote_currency = quote.currency if quote else listing.currency
    quote_price = quote.split_adjusted_close if quote else None
    quote_freshness = market.freshness
    if quote is not None and quote.currency != listing.currency:
        quote_freshness = "QUALITY_CHECK"

    market_price = MarketPriceInput(
        observation_id=quote.id if quote else None,
        price=quote_price,
        currency=quote_currency,
        effective_at=quote.market_date if quote else None,
        freshness=quote_freshness,
    )
    if quote is None:
        market_status = "NO_DATA"
        market_reason = "No exact-listing price observation is known at this cutoff."
    elif quote_freshness == "QUALITY_CHECK":
        market_status = "DATA_CHECK"
        market_reason = "The exact-listing quote currency or quality is inconsistent."
    elif not model.model_currency:
        market_status = "CURRENCY_UNKNOWN"
        market_reason = "The model currency is not documented."
    elif quote_currency != model.model_currency:
        market_status = "CURRENCY_MISMATCH"
        market_reason = (
            f"The {quote_currency} listing quote is not converted to {model.model_currency}."
        )
    elif market.freshness == "STALE":
        market_status = "STALE"
        market_reason = "The latest exact-listing observation is stale."
    elif quote_price is None or quote_price <= 0:
        market_status = "DATA_CHECK"
        market_reason = "The exact-listing quote has no positive split-adjusted close."
    else:
        market_status = "AVAILABLE"
        market_reason = None
    market_price_read = s.ExpectedReturnMarketPriceRead(
        status=market_status,
        listing_id=listing.id,
        ticker=listing.ticker,
        venue=listing.venue,
        listing_currency=listing.currency,
        quote=quote.provider_close if quote else None,
        quote_currency=quote.currency if quote else None,
        model_reference_price=quote.split_adjusted_close if quote else None,
        model_currency=model.model_currency,
        effective_at=quote.market_date if quote else None,
        observed_at=quote.observed_at if quote else None,
        recorded_at=quote.recorded_at if quote else None,
        provider=quote.provider if quote else None,
        adjustment_basis=quote.adjustment_basis if quote else None,
        observation_id=quote.id if quote else None,
        source_ref=quote.source_ref if quote else None,
        reason=market_reason,
    )

    try:
        if model.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
            revision_inputs: s.DcfCalculationInput | s.OwnerCashFlowInput | s.ResidualIncomeInput
            revision_inputs = _dcf_inputs(session, revision)
        else:
            revision_read = queries._extended_financial_model_revision_read(session, revision)
            if isinstance(revision_read, s.OwnerCashFlowRevisionRead):
                revision_inputs = s.OwnerCashFlowInput(
                    base=revision_read.base, scenarios=revision_read.scenarios
                )
            elif isinstance(revision_read, s.ResidualIncomeRevisionRead):
                revision_inputs = s.ResidualIncomeInput(
                    base=revision_read.base, scenarios=revision_read.scenarios
                )
            else:
                return None
        result = calculate_native_revision_at_quote(
            model_type=model.model_type,
            model_currency=model.model_currency,
            valuation_listing_id=model.valuation_listing_id,
            quote_listing_id=quote_id,
            revision_inputs=revision_inputs,
            return_methodology=s.ReturnMethodologyRead.model_validate(
                source_output.return_methodology
            ),
            forward_fundamental_cagr=source_output.forward_fundamental_cagr,
            accepted_output_id=source_output.id,
            accepted_reference_price=source_output.current_price,
            accepted_reference_price_observation_id=source_output.price_observation_id,
            accepted_reference_price_effective_at=source_output.price_effective_at,
            market_price=market_price,
            market_price_read=market_price_read,
            model_id=model.id,
            model_name=model.model_name,
            revision_id=revision.id,
            revision_number=revision.revision_number,
            methodology_version=revision.methodology_version,
            effective_at=revision.effective_at,
            recorded_at=revision.recorded_at,
            calculated_as_of=effective_cutoff,
            known_at=knowledge_cutoff,
        )
    except (ValueError, TypeError):
        return None
    return replace(result, accepted_output=source_output)


def current_native_model_calculations(
    session: Session,
    company_id: UUID,
    *,
    as_of: date,
    known_at: datetime,
) -> list[s.CurrentNativeModelCalculationRead]:
    """Return derived current quotes for accepted native revisions known at the cutoffs."""

    effective_cutoff = datetime.combine(as_of, time.max, UTC)
    knowledge_cutoff = known_at.astimezone(UTC)
    models = list(
        session.scalars(
            select(FinancialModel)
            .where(
                FinancialModel.company_id == company_id,
                FinancialModel.created_at <= knowledge_cutoff,
            )
            .order_by(FinancialModel.model_name, FinancialModel.id)
        )
    )
    results: list[s.CurrentNativeModelCalculationRead] = []
    for model in models:
        revision = session.scalar(
            select(FinancialModelRevision)
            .where(
                FinancialModelRevision.model_id == model.id,
                FinancialModelRevision.effective_at <= effective_cutoff,
                FinancialModelRevision.recorded_at <= knowledge_cutoff,
            )
            .order_by(
                FinancialModelRevision.effective_at.desc(),
                FinancialModelRevision.revision_number.desc(),
                FinancialModelRevision.recorded_at.desc(),
            )
            .limit(1)
        )
        if revision is None:
            continue
        result = current_native_model_calculation(
            session,
            model,
            revision,
            as_of=as_of,
            known_at=knowledge_cutoff,
        )
        if result is not None:
            results.append(result.read)
    return results
