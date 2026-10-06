"""Explicit transactional operations. Callers own commit/rollback boundaries."""

import hashlib
import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    CashPosition,
    Company,
    CurrentLifecycle,
    DcfModelAssumptions,
    DcfProjection,
    DcfScenarioAssumptions,
    DcfYearAssumption,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    FinancialModelType,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    Lifecycle,
    LifecycleEvent,
    Listing,
    OwnerCashFlowAssumptions,
    OwnerCashFlowProjection,
    OwnerCashFlowScenarioAssumptions,
    OwnerCashFlowYearAssumption,
    Portfolio,
    PriceObservation,
    RankingDefinition,
    RankingDefinitionStatus,
    RankingEntry,
    RankingEntryStatus,
    RankingImplementationStatus,
    RankingRun,
    RankingRunStatus,
    RankingType,
    ResidualIncomeAssumptions,
    ResidualIncomeProjection,
    ResidualIncomeScenarioAssumptions,
    ScoreAssessment,
    ScoreDefinition,
    ScoreDefinitionStatus,
    Security,
    TargetAllocation,
    TargetRevision,
    now,
)
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
    calculate_ufcf_dcf,
)
from portfolio_api.portfolio_ranking import build_portfolio_rank_entries
from portfolio_api.research_ranking import build_research_rank_entries
from portfolio_api.watchlist_ranking import build_watchlist_rank_entries


class DomainError(Exception):
    def __init__(self, detail: str, status: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


def company(session: Session, company_id: UUID, *, lock: bool = False) -> Company:
    item = session.scalar(
        select(Company).where(Company.id == company_id).with_for_update()
        if lock
        else select(Company).where(Company.id == company_id)
    )
    if item is None:
        raise DomainError("Company not found", 404)
    return item


def portfolio(session: Session, portfolio_id: UUID, *, lock: bool = False) -> Portfolio:
    statement = select(Portfolio).where(Portfolio.id == portfolio_id)
    item = session.scalar(statement.with_for_update() if lock else statement)
    if item is None:
        raise DomainError("Portfolio not found", 404)
    return item


def create_company(session: Session, value: s.CompanyCreate, *, demo: bool = False) -> Company:
    item = Company(**value.model_dump(), is_demo=demo)
    session.add(item)
    session.flush()
    return item


def create_security(session: Session, company_id: UUID, value: s.SecurityCreate) -> Security:
    issuer = company(session, company_id)
    if value.underlying_security_id is not None:
        underlying = session.get(Security, value.underlying_security_id)
        if underlying is None or underlying.company_id != company_id:
            raise DomainError("Underlying security must belong to the same company")
        if value.security_type != "ADR" or underlying.security_type == "ADR":
            raise DomainError("Only an ADR may reference an underlying ordinary/preferred security")
    item = Security(company_id=company_id, **value.model_dump(), is_demo=issuer.is_demo)
    session.add(item)
    session.flush()
    return item


def create_listing(session: Session, security_id: UUID, value: s.ListingCreate) -> Listing:
    security = session.get(Security, security_id)
    if security is None:
        raise DomainError("Security not found", 404)
    item = Listing(security_id=security_id, **value.model_dump(), is_demo=security.is_demo)
    session.add(item)
    session.flush()
    return item


def record_fx_observation(session: Session, value: s.FxObservationCreate) -> FxObservation:
    if value.base_currency == value.quote_currency:
        raise DomainError("FX observation currencies must differ")
    observation = FxObservation(**value.model_dump())
    session.add(observation)
    session.flush()
    return observation


def _latest_model_market_price(
    session: Session, model: FinancialModel
) -> tuple[MarketPriceInput, PriceObservation | None]:
    listing = session.get(Listing, model.valuation_listing_id)
    if listing is None:
        raise DomainError("The model valuation listing no longer exists", 409)
    return _latest_listing_market_price(session, listing)


def _latest_listing_market_price(
    session: Session, listing: Listing
) -> tuple[MarketPriceInput, PriceObservation | None]:
    from portfolio_api.domain.queries import listing_market_data

    market = listing_market_data(session, listing, history_limit=0)
    latest = market.latest
    if latest is None:
        return (
            MarketPriceInput(None, None, listing.currency, None, "NO_DATA"),
            None,
        )
    return (
        MarketPriceInput(
            observation_id=latest.id,
            price=latest.split_adjusted_close,
            currency=latest.currency,
            effective_at=latest.market_date,
            freshness=market.freshness,
        ),
        session.get(PriceObservation, latest.id),
    )


def _calculation_preview(
    calculation: DcfCalculation,
    *,
    model_currency: str,
    model_id: UUID | None = None,
    base_revision_id: UUID | None = None,
    current_revision_id: UUID | None = None,
    current_revision_number: int | None = None,
) -> s.FinancialModelCalculationPreviewRead:
    def rounded(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        with localcontext() as context:
            context.prec = 60
            return value.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP)

    outputs = s.FinancialModelCalculationOutputsRead(
        status=calculation.status,
        model_currency=model_currency,
        price_observation_id=calculation.price_observation_id,
        current_price=calculation.current_price,
        price_effective_at=calculation.price_effective_at,
        price_status=calculation.price_status,
        price_unavailable_reason=calculation.price_unavailable_reason,
        irr_unavailable_reason=calculation.irr_unavailable_reason,
        bear_fv=rounded(calculation.bear_fv),
        base_fv=rounded(calculation.base_fv),
        bull_fv=rounded(calculation.bull_fv),
        bear_probability=rounded(calculation.bear_probability),
        base_probability=rounded(calculation.base_probability),
        bull_probability=rounded(calculation.bull_probability),
        weighted_fv=rounded(calculation.weighted_fv),
        weighted_upside=rounded(calculation.weighted_upside),
        expected_cash_flow_irr=rounded(calculation.expected_cash_flow_irr),
        hurdle=rounded(calculation.hurdle),
        expected_excess=rounded(calculation.expected_excess),
        forward_fundamental_cagr=None,
    )
    projections = [
        s.DcfProjectionCalculationPreviewRead(
            scenario=projection.scenario,
            forecast_year=projection.forecast_year,
            revenue=rounded(projection.revenue),
            ebit=rounded(projection.ebit),
            nopat=rounded(projection.nopat),
            depreciation_amortization=rounded(projection.depreciation_amortization),
            capex=rounded(projection.capex),
            net_working_capital=rounded(projection.net_working_capital),
            change_in_nwc=rounded(projection.change_in_nwc),
            unlevered_free_cash_flow=rounded(projection.unlevered_free_cash_flow),
            revenue_growth=rounded(projection.revenue_growth),
            discount_rate=rounded(projection.discount_rate),
            discount_factor=rounded(projection.discount_factor),
            present_value_ufcf=rounded(projection.present_value_ufcf),
            terminal_value=rounded(projection.terminal_value),
        )
        for scenario in calculation.scenarios
        for projection in scenario.projections
    ]
    return s.FinancialModelCalculationPreviewRead(
        model_id=model_id,
        base_revision_id=base_revision_id,
        current_revision_id=current_revision_id,
        current_revision_number=current_revision_number,
        model_currency=model_currency,
        outputs=outputs,
        projections=projections,
    )


def preview_financial_model_initial_calculation(
    session: Session,
    company_id: UUID,
    value: s.FinancialModelInitialCalculationPreviewCreate,
) -> s.FinancialModelCalculationPreviewRead:
    issuer = company(session, company_id)
    listing = session.get(Listing, value.valuation_listing_id)
    if listing is None:
        raise DomainError("Valuation listing not found", 404)
    security = session.get(Security, listing.security_id)
    if security is None or security.company_id != issuer.id:
        raise DomainError("Valuation listing must belong to the model company")
    existing = session.scalar(
        select(FinancialModel.id).where(
            FinancialModel.company_id == company_id,
            FinancialModel.valuation_listing_id == listing.id,
            FinancialModel.model_type == FinancialModelType.UFCF_DCF_10Y_FADE,
        )
    )
    if existing is not None:
        raise DomainError("A model already exists for this listing and methodology", 409)
    market_price, _ = _latest_listing_market_price(session, listing)
    try:
        calculation = calculate_ufcf_dcf(
            value, model_currency=value.model_currency, market_price=market_price
        )
    except ValueError as error:
        raise DomainError(str(error)) from None
    return _calculation_preview(calculation, model_currency=value.model_currency)


def preview_financial_model_revision_calculation(
    session: Session,
    model_id: UUID,
    value: s.FinancialModelRevisionCalculationPreviewCreate,
) -> s.FinancialModelCalculationPreviewRead:
    model = session.scalar(select(FinancialModel).where(FinancialModel.id == model_id))
    if model is None:
        raise DomainError("Financial model not found", 404)
    if model.current_revision_id != value.base_revision_id:
        raise DomainError("The model changed since it was read; reload before previewing", 409)
    current = session.get(FinancialModelRevision, model.current_revision_id)
    if current is None or current.model_id != model.id:
        raise DomainError("Current model revision is inconsistent; reload before previewing", 409)
    market_price, _ = _latest_model_market_price(session, model)
    try:
        calculation = calculate_ufcf_dcf(
            value, model_currency=model.model_currency, market_price=market_price
        )
    except ValueError as error:
        raise DomainError(str(error)) from None
    return _calculation_preview(
        calculation,
        model_currency=model.model_currency,
        model_id=model.id,
        base_revision_id=value.base_revision_id,
        current_revision_id=current.id,
        current_revision_number=current.revision_number,
    )


def _append_dcf_revision(
    session: Session,
    model: FinancialModel,
    value: s.FinancialModelRevisionCreate,
    *,
    contract_digest: str | None = None,
) -> FinancialModelRevision:
    current_id = model.current_revision_id
    if current_id != value.base_revision_id:
        raise DomainError("The model changed since it was read; reload before revising", 409)
    if (
        value.source_revision_id is not None
        and session.scalar(
            select(FinancialModelRevision.id).where(
                FinancialModelRevision.model_id == model.id,
                FinancialModelRevision.source_revision_id == value.source_revision_id,
            )
        )
        is not None
    ):
        raise DomainError("That external revision identity has already been accepted", 409)

    market_price, _ = _latest_model_market_price(session, model)
    try:
        calculation = calculate_ufcf_dcf(
            value, model_currency=model.model_currency, market_price=market_price
        )
    except ValueError as error:
        raise DomainError(str(error)) from None

    revision_number = 1
    if current_id is not None:
        current = session.get(FinancialModelRevision, current_id)
        if current is None or current.model_id != model.id:
            raise DomainError("Current model revision is inconsistent; reload before revising", 409)
        revision_number = current.revision_number + 1
    revision = FinancialModelRevision(
        model_id=model.id,
        model_type=FinancialModelType.UFCF_DCF_10Y_FADE,
        revision_number=revision_number,
        base_revision_id=value.base_revision_id,
        methodology_version="ufcf-dcf-fade-v1",
        source_revision_id=value.source_revision_id,
        contract_digest=contract_digest,
        actor=value.actor,
        source=value.source,
        rationale=value.rationale,
        effective_at=value.effective_at,
    )
    session.add(revision)
    session.flush()
    session.add(DcfModelAssumptions(revision_id=revision.id, **value.base.model_dump()))
    scenario_rows: dict[str, DcfScenarioAssumptions] = {}
    for scenario in value.scenarios:
        row = DcfScenarioAssumptions(
            revision_id=revision.id,
            scenario=scenario.scenario,
            probability=scenario.probability,
            terminal_growth=scenario.terminal_growth,
            year10_ufcf_growth=scenario.year10_ufcf_growth,
            rationale=scenario.rationale,
        )
        session.add(row)
        session.flush()
        scenario_rows[scenario.scenario.value] = row
        session.add_all(
            DcfYearAssumption(scenario_id=row.id, **year.model_dump()) for year in scenario.years
        )
    session.add_all(
        DcfProjection(
            scenario_id=scenario_rows[projection.scenario].id,
            forecast_year=projection.forecast_year,
            revenue=projection.revenue,
            ebit=projection.ebit,
            nopat=projection.nopat,
            depreciation_amortization=projection.depreciation_amortization,
            capex=projection.capex,
            net_working_capital=projection.net_working_capital,
            change_in_nwc=projection.change_in_nwc,
            unlevered_free_cash_flow=projection.unlevered_free_cash_flow,
            revenue_growth=projection.revenue_growth,
            discount_rate=projection.discount_rate,
            discount_factor=projection.discount_factor,
            present_value_ufcf=projection.present_value_ufcf,
            terminal_value=projection.terminal_value,
        )
        for scenario in calculation.scenarios
        for projection in scenario.projections
    )
    session.add(
        FinancialModelOutput(
            revision_id=revision.id,
            status=calculation.status,
            model_currency=model.model_currency,
            price_observation_id=calculation.price_observation_id,
            current_price=calculation.current_price,
            price_effective_at=calculation.price_effective_at,
            price_status=calculation.price_status,
            price_unavailable_reason=calculation.price_unavailable_reason,
            irr_unavailable_reason=calculation.irr_unavailable_reason,
            bear_fv=calculation.bear_fv,
            base_fv=calculation.base_fv,
            bull_fv=calculation.bull_fv,
            bear_probability=calculation.bear_probability,
            base_probability=calculation.base_probability,
            bull_probability=calculation.bull_probability,
            weighted_fv=calculation.weighted_fv,
            weighted_upside=calculation.weighted_upside,
            expected_cash_flow_irr=calculation.expected_cash_flow_irr,
            hurdle=calculation.hurdle,
            expected_excess=calculation.expected_excess,
            # The legacy model's forward CAGR is maintained by the Research Universe
            # domain and is not derived by this DCF calculation.
            forward_fundamental_cagr=None,
        )
    )
    session.flush()
    model.current_revision_id = revision.id
    session.flush()
    return revision


def create_financial_model(
    session: Session, company_id: UUID, value: s.FinancialModelCreate
) -> FinancialModel:
    issuer = company(session, company_id, lock=True)
    listing = session.get(Listing, value.valuation_listing_id)
    if listing is None:
        raise DomainError("Valuation listing not found", 404)
    security = session.get(Security, listing.security_id)
    if security is None or security.company_id != issuer.id:
        raise DomainError("Valuation listing must belong to the model company")
    existing = session.scalar(
        select(FinancialModel.id).where(
            FinancialModel.company_id == company_id,
            FinancialModel.valuation_listing_id == listing.id,
            FinancialModel.model_type == value.model_type,
        )
    )
    if existing is not None:
        raise DomainError("A model already exists for this listing and methodology", 409)
    if value.initial_revision.base_revision_id is not None:
        raise DomainError("The initial model revision cannot name a base revision")
    model = FinancialModel(
        company_id=company_id,
        valuation_listing_id=listing.id,
        model_type=value.model_type,
        model_name=value.model_name,
        model_currency=value.model_currency,
        source_model_key=value.source_model_key,
    )
    session.add(model)
    session.flush()
    _append_dcf_revision(session, model, value.initial_revision)
    return model


def append_financial_model_revision(
    session: Session, model_id: UUID, value: s.FinancialModelRevisionCreate
) -> FinancialModelRevision:
    model = session.scalar(
        select(FinancialModel).where(FinancialModel.id == model_id).with_for_update()
    )
    if model is None:
        raise DomainError("Financial model not found", 404)
    return _append_dcf_revision(session, model, value)


def _archetype_preview(
    calculation: ArchetypeCalculation,
    *,
    model_currency: str,
    model_type: FinancialModelType,
    model_id: UUID | None = None,
    base_revision_id: UUID | None = None,
    current_revision_id: UUID | None = None,
    current_revision_number: int | None = None,
) -> s.OwnerCashFlowCalculationPreviewRead | s.ResidualIncomeCalculationPreviewRead:
    def rounded(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        with localcontext() as context:
            context.prec = 60
            return value.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP)

    outputs = s.FinancialModelCalculationOutputsRead(
        status=calculation.status,
        model_currency=model_currency,
        price_observation_id=calculation.price_observation_id,
        current_price=calculation.current_price,
        price_effective_at=calculation.price_effective_at,
        price_status=calculation.price_status,
        price_unavailable_reason=calculation.price_unavailable_reason,
        irr_unavailable_reason=calculation.irr_unavailable_reason,
        bear_fv=rounded(calculation.bear_fv),
        base_fv=rounded(calculation.base_fv),
        bull_fv=rounded(calculation.bull_fv),
        bear_probability=rounded(calculation.bear_probability),
        base_probability=rounded(calculation.base_probability),
        bull_probability=rounded(calculation.bull_probability),
        weighted_fv=rounded(calculation.weighted_fv),
        weighted_upside=rounded(calculation.weighted_upside),
        expected_cash_flow_irr=rounded(calculation.expected_cash_flow_irr),
        hurdle=rounded(calculation.hurdle),
        expected_excess=rounded(calculation.expected_excess),
        forward_fundamental_cagr=None,
    )
    common = dict(
        model_id=model_id,
        base_revision_id=base_revision_id,
        current_revision_id=current_revision_id,
        current_revision_number=current_revision_number,
        model_currency=model_currency,
        outputs=outputs,
    )
    if model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        owner_projections: list[OwnerCashFlowProjectionCalculation] = []
        for scenario in calculation.scenarios:
            for projection in scenario.projections:
                if not isinstance(projection, OwnerCashFlowProjectionCalculation):
                    raise DomainError(
                        "Owner cash-flow calculation returned invalid projections", 500
                    )
                owner_projections.append(projection)
        return s.OwnerCashFlowCalculationPreviewRead(
            **common,
            projections=[
                s.OwnerCashFlowProjectionRead(
                    scenario=projection.scenario,
                    forecast_year=projection.forecast_year,
                    revenue=rounded(projection.revenue),
                    owner_cash_flow=rounded(projection.owner_cash_flow),
                    owner_cash_flow_per_share=rounded(projection.owner_cash_flow_per_share),
                    present_value_per_share=rounded(projection.present_value_per_share),
                    terminal_value_per_share=rounded(projection.terminal_value_per_share),
                )
                for projection in owner_projections
            ],
        )
    residual_projections: list[ResidualIncomeProjectionCalculation] = []
    for scenario in calculation.scenarios:
        for projection in scenario.projections:
            if not isinstance(projection, ResidualIncomeProjectionCalculation):
                raise DomainError("Residual-income calculation returned invalid projections", 500)
            residual_projections.append(projection)
    return s.ResidualIncomeCalculationPreviewRead(
        **common,
        projections=[
            s.ResidualIncomeProjectionRead(
                scenario=projection.scenario,
                forecast_year=projection.forecast_year,
                beginning_book_value_per_share=rounded(projection.beginning_book_value_per_share),
                return_on_equity=rounded(projection.return_on_equity),
                net_income_per_share=rounded(projection.net_income_per_share),
                dividend_per_share=rounded(projection.dividend_per_share),
                ending_book_value_per_share=rounded(projection.ending_book_value_per_share),
                residual_income_per_share=rounded(projection.residual_income_per_share),
                present_value_residual_income=rounded(projection.present_value_residual_income),
                terminal_value_per_share=rounded(projection.terminal_value_per_share),
            )
            for projection in residual_projections
        ],
    )


def _append_archetype_revision(
    session: Session,
    model: FinancialModel,
    value: s.OwnerCashFlowRevisionCreate | s.ResidualIncomeRevisionCreate,
    model_type: FinancialModelType,
    *,
    contract_digest: str | None = None,
) -> FinancialModelRevision:
    if model.model_type != model_type:
        raise DomainError("The revision method does not match the financial model type", 409)
    if model.current_revision_id != value.base_revision_id:
        raise DomainError("The model changed since it was read; reload before revising", 409)
    if (
        value.source_revision_id is not None
        and session.scalar(
            select(FinancialModelRevision.id).where(
                FinancialModelRevision.model_id == model.id,
                FinancialModelRevision.source_revision_id == value.source_revision_id,
            )
        )
        is not None
    ):
        raise DomainError("That external revision identity has already been accepted", 409)

    market_price, _ = _latest_model_market_price(session, model)
    try:
        if model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
            assert isinstance(value, s.OwnerCashFlowRevisionCreate)
            calculation = calculate_owner_cash_flow(
                value, model_currency=model.model_currency, market_price=market_price
            )
        else:
            assert isinstance(value, s.ResidualIncomeRevisionCreate)
            calculation = calculate_residual_income(
                value, model_currency=model.model_currency, market_price=market_price
            )
    except ValueError as error:
        raise DomainError(str(error)) from None

    current = (
        session.get(FinancialModelRevision, model.current_revision_id)
        if model.current_revision_id
        else None
    )
    revision = FinancialModelRevision(
        model_id=model.id,
        model_type=model_type,
        revision_number=(current.revision_number + 1) if current else 1,
        base_revision_id=value.base_revision_id,
        methodology_version=(
            "owner-cash-flow-10y-v1"
            if model_type == FinancialModelType.OWNER_CASH_FLOW_10Y
            else "residual-income-10y-fade-v1"
        ),
        source_revision_id=value.source_revision_id,
        contract_digest=contract_digest,
        actor=value.actor,
        source=value.source,
        rationale=value.rationale,
        effective_at=value.effective_at,
    )
    session.add(revision)
    session.flush()

    scenario_rows: dict[str, UUID] = {}
    if model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        assert isinstance(value, s.OwnerCashFlowRevisionCreate)
        session.add(OwnerCashFlowAssumptions(revision_id=revision.id, **value.base.model_dump()))
        for owner_scenario in value.scenarios:
            owner_scenario_row = OwnerCashFlowScenarioAssumptions(
                revision_id=revision.id,
                scenario=owner_scenario.scenario,
                probability=owner_scenario.probability,
                required_return=owner_scenario.required_return,
                terminal_growth=owner_scenario.terminal_growth,
                rationale=owner_scenario.rationale,
            )
            session.add(owner_scenario_row)
            session.flush()
            scenario_rows[owner_scenario.scenario.value] = owner_scenario_row.id
            session.add_all(
                OwnerCashFlowYearAssumption(
                    revision_id=revision.id,
                    scenario_id=owner_scenario_row.id,
                    **year.model_dump(),
                )
                for year in owner_scenario.years
            )
        session.add_all(
            OwnerCashFlowProjection(
                revision_id=revision.id,
                scenario_id=scenario_rows[projection.scenario.value],
                forecast_year=projection.forecast_year,
                revenue=projection.revenue,
                owner_cash_flow=projection.owner_cash_flow,
                owner_cash_flow_per_share=projection.owner_cash_flow_per_share,
                present_value_per_share=projection.present_value_per_share,
                terminal_value_per_share=projection.terminal_value_per_share,
            )
            for scenario in calculation.scenarios
            for projection in scenario.projections
            if isinstance(projection, OwnerCashFlowProjectionCalculation)
        )
    else:
        assert isinstance(value, s.ResidualIncomeRevisionCreate)
        session.add(ResidualIncomeAssumptions(revision_id=revision.id, **value.base.model_dump()))
        for ri_scenario in value.scenarios:
            ri_scenario_row = ResidualIncomeScenarioAssumptions(
                revision_id=revision.id,
                scenario=ri_scenario.scenario,
                probability=ri_scenario.probability,
                starting_roe=ri_scenario.starting_roe,
                cost_of_equity=ri_scenario.cost_of_equity,
                terminal_growth=ri_scenario.terminal_growth,
                mature_roe=ri_scenario.mature_roe,
                rationale=ri_scenario.rationale,
            )
            session.add(ri_scenario_row)
            session.flush()
            scenario_rows[ri_scenario.scenario.value] = ri_scenario_row.id
        session.add_all(
            ResidualIncomeProjection(
                revision_id=revision.id,
                scenario_id=scenario_rows[projection.scenario.value],
                forecast_year=projection.forecast_year,
                beginning_book_value_per_share=projection.beginning_book_value_per_share,
                return_on_equity=projection.return_on_equity,
                net_income_per_share=projection.net_income_per_share,
                dividend_per_share=projection.dividend_per_share,
                ending_book_value_per_share=projection.ending_book_value_per_share,
                residual_income_per_share=projection.residual_income_per_share,
                present_value_residual_income=projection.present_value_residual_income,
                terminal_value_per_share=projection.terminal_value_per_share,
            )
            for scenario in calculation.scenarios
            for projection in scenario.projections
            if isinstance(projection, ResidualIncomeProjectionCalculation)
        )
    session.add(
        FinancialModelOutput(
            revision_id=revision.id,
            status=calculation.status,
            model_currency=model.model_currency,
            price_observation_id=calculation.price_observation_id,
            current_price=calculation.current_price,
            price_effective_at=calculation.price_effective_at,
            price_status=calculation.price_status,
            price_unavailable_reason=calculation.price_unavailable_reason,
            irr_unavailable_reason=calculation.irr_unavailable_reason,
            bear_fv=calculation.bear_fv,
            base_fv=calculation.base_fv,
            bull_fv=calculation.bull_fv,
            bear_probability=calculation.bear_probability,
            base_probability=calculation.base_probability,
            bull_probability=calculation.bull_probability,
            weighted_fv=calculation.weighted_fv,
            weighted_upside=calculation.weighted_upside,
            expected_cash_flow_irr=calculation.expected_cash_flow_irr,
            hurdle=calculation.hurdle,
            expected_excess=calculation.expected_excess,
            forward_fundamental_cagr=None,
        )
    )
    session.flush()
    model.current_revision_id = revision.id
    session.flush()
    return revision


def _create_archetype_model(
    session: Session,
    company_id: UUID,
    model_type: FinancialModelType,
    model_name: str,
    valuation_listing_id: UUID,
    model_currency: str,
    source_model_key: str | None,
    initial_revision: s.OwnerCashFlowRevisionCreate | s.ResidualIncomeRevisionCreate,
) -> FinancialModel:
    issuer = company(session, company_id, lock=True)
    listing = session.get(Listing, valuation_listing_id)
    security = session.get(Security, listing.security_id) if listing else None
    if listing is None or security is None or security.company_id != issuer.id:
        raise DomainError("Valuation listing must belong to the model company")
    if initial_revision.base_revision_id is not None:
        raise DomainError("The initial model revision cannot name a base revision")
    existing = session.scalar(
        select(FinancialModel.id).where(
            FinancialModel.company_id == company_id,
            FinancialModel.valuation_listing_id == listing.id,
            FinancialModel.model_type == model_type,
        )
    )
    if existing is not None:
        raise DomainError("A model already exists for this listing and methodology", 409)
    model = FinancialModel(
        company_id=company_id,
        valuation_listing_id=listing.id,
        model_type=model_type,
        model_name=model_name,
        model_currency=model_currency,
        source_model_key=source_model_key,
    )
    session.add(model)
    session.flush()
    _append_archetype_revision(session, model, initial_revision, model_type)
    return model


def create_owner_cash_flow_model(
    session: Session, company_id: UUID, value: s.OwnerCashFlowModelCreate
) -> FinancialModel:
    return _create_archetype_model(
        session,
        company_id,
        FinancialModelType.OWNER_CASH_FLOW_10Y,
        value.model_name,
        value.valuation_listing_id,
        value.model_currency,
        value.source_model_key,
        value.initial_revision,
    )


def create_residual_income_model(
    session: Session, company_id: UUID, value: s.ResidualIncomeModelCreate
) -> FinancialModel:
    return _create_archetype_model(
        session,
        company_id,
        FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
        value.model_name,
        value.valuation_listing_id,
        value.model_currency,
        value.source_model_key,
        value.initial_revision,
    )


def append_owner_cash_flow_revision(
    session: Session, model_id: UUID, value: s.OwnerCashFlowRevisionCreate
) -> FinancialModelRevision:
    model = session.scalar(
        select(FinancialModel).where(FinancialModel.id == model_id).with_for_update()
    )
    if model is None:
        raise DomainError("Financial model not found", 404)
    return _append_archetype_revision(session, model, value, FinancialModelType.OWNER_CASH_FLOW_10Y)


def append_residual_income_revision(
    session: Session, model_id: UUID, value: s.ResidualIncomeRevisionCreate
) -> FinancialModelRevision:
    model = session.scalar(
        select(FinancialModel).where(FinancialModel.id == model_id).with_for_update()
    )
    if model is None:
        raise DomainError("Financial model not found", 404)
    return _append_archetype_revision(
        session, model, value, FinancialModelType.RESIDUAL_INCOME_10Y_FADE
    )


def preview_owner_cash_flow_initial(
    session: Session, company_id: UUID, value: s.OwnerCashFlowInitialPreviewCreate
) -> s.OwnerCashFlowCalculationPreviewRead:
    issuer = company(session, company_id)
    listing = session.get(Listing, value.valuation_listing_id)
    security = session.get(Security, listing.security_id) if listing else None
    if listing is None or security is None or security.company_id != issuer.id:
        raise DomainError("Valuation listing must belong to the model company")
    market_price, _ = _latest_listing_market_price(session, listing)
    result = _archetype_preview(
        calculate_owner_cash_flow(
            value, model_currency=value.model_currency, market_price=market_price
        ),
        model_currency=value.model_currency,
        model_type=FinancialModelType.OWNER_CASH_FLOW_10Y,
    )
    return cast(s.OwnerCashFlowCalculationPreviewRead, result)


def preview_residual_income_initial(
    session: Session, company_id: UUID, value: s.ResidualIncomeInitialPreviewCreate
) -> s.ResidualIncomeCalculationPreviewRead:
    issuer = company(session, company_id)
    listing = session.get(Listing, value.valuation_listing_id)
    security = session.get(Security, listing.security_id) if listing else None
    if listing is None or security is None or security.company_id != issuer.id:
        raise DomainError("Valuation listing must belong to the model company")
    market_price, _ = _latest_listing_market_price(session, listing)
    result = _archetype_preview(
        calculate_residual_income(
            value, model_currency=value.model_currency, market_price=market_price
        ),
        model_currency=value.model_currency,
        model_type=FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
    )
    return cast(s.ResidualIncomeCalculationPreviewRead, result)


def preview_owner_cash_flow_revision(
    session: Session, model_id: UUID, value: s.OwnerCashFlowRevisionPreviewCreate
) -> s.OwnerCashFlowCalculationPreviewRead:
    model = session.get(FinancialModel, model_id)
    if model is None or model.model_type != FinancialModelType.OWNER_CASH_FLOW_10Y:
        raise DomainError("Owner cash-flow model not found", 404)
    if model.current_revision_id != value.base_revision_id:
        raise DomainError("The model changed since it was read; reload before previewing", 409)
    current = session.get(FinancialModelRevision, model.current_revision_id)
    market_price, _ = _latest_model_market_price(session, model)
    result = _archetype_preview(
        calculate_owner_cash_flow(
            value, model_currency=model.model_currency, market_price=market_price
        ),
        model_currency=model.model_currency,
        model_type=FinancialModelType.OWNER_CASH_FLOW_10Y,
        model_id=model.id,
        base_revision_id=value.base_revision_id,
        current_revision_id=current.id if current else None,
        current_revision_number=current.revision_number if current else None,
    )
    return cast(s.OwnerCashFlowCalculationPreviewRead, result)


def preview_residual_income_revision(
    session: Session, model_id: UUID, value: s.ResidualIncomeRevisionPreviewCreate
) -> s.ResidualIncomeCalculationPreviewRead:
    model = session.get(FinancialModel, model_id)
    if model is None or model.model_type != FinancialModelType.RESIDUAL_INCOME_10Y_FADE:
        raise DomainError("Residual-income model not found", 404)
    if model.current_revision_id != value.base_revision_id:
        raise DomainError("The model changed since it was read; reload before previewing", 409)
    current = session.get(FinancialModelRevision, model.current_revision_id)
    market_price, _ = _latest_model_market_price(session, model)
    result = _archetype_preview(
        calculate_residual_income(
            value, model_currency=model.model_currency, market_price=market_price
        ),
        model_currency=model.model_currency,
        model_type=FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
        model_id=model.id,
        base_revision_id=value.base_revision_id,
        current_revision_id=current.id if current else None,
        current_revision_number=current.revision_number if current else None,
    )
    return cast(s.ResidualIncomeCalculationPreviewRead, result)


def _additional_contract_digest(value: s.AdditionalModelPortableContractV2) -> str:
    canonical = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def export_additional_model_contract(
    session: Session, model_id: UUID
) -> s.AdditionalModelPortableContractV2:
    from portfolio_api.domain import queries

    model = session.get(FinancialModel, model_id)
    if model is None or model.model_type not in {
        FinancialModelType.OWNER_CASH_FLOW_10Y,
        FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
    }:
        raise DomainError("Extended financial model not found", 404)
    read = queries.extended_financial_model(session, model.id)
    revision = read.current_revision
    common = dict(
        source_revision_id=f"external-modeling:{uuid4()}",
        actor="IMPORT",
        source="Portable spreadsheet model contract v2",
        rationale=None,
        effective_at=now(),
    )
    method_type = FinancialModelType(model.model_type)
    if method_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        if not isinstance(revision, s.OwnerCashFlowRevisionRead):
            raise DomainError("Owner cash-flow revision state is inconsistent", 409)
        candidate = s.AdditionalModelContractCandidate(
            **common,
            owner_cash_flow=s.OwnerCashFlowInput(
                base=revision.base,
                scenarios=revision.scenarios,
            ),
        )
    else:
        if not isinstance(revision, s.ResidualIncomeRevisionRead):
            raise DomainError("Residual-income revision state is inconsistent", 409)
        candidate = s.AdditionalModelContractCandidate(
            **common,
            residual_income=s.ResidualIncomeInput(
                base=revision.base,
                scenarios=revision.scenarios,
            ),
        )
    return s.AdditionalModelPortableContractV2(
        exported_at=now(),
        model_id=read.id,
        company_id=read.company_id,
        model_type=read.model_type,
        model_name=read.model_name,
        valuation_listing_id=read.valuation_listing.id,
        model_currency=read.model_currency,
        source_model_key=read.source_model_key,
        base_revision_id=read.current_revision_id,
        base_revision_number=revision.revision_number,
        candidate_revision=candidate,
    )


def _additional_input_changes(
    current: dict[str, object], proposed: dict[str, object]
) -> list[s.AdditionalModelContractFieldChange]:
    def flatten(value: object, prefix: str = "") -> dict[str, str | None]:
        if isinstance(value, dict):
            return {
                key: item
                for name, child in value.items()
                for key, item in flatten(child, f"{prefix}.{name}" if prefix else name).items()
            }
        if isinstance(value, list):
            return {
                key: item
                for index, child in enumerate(value)
                for key, item in flatten(child, f"{prefix}[{index}]").items()
            }
        return {prefix: str(value) if value is not None else None}

    before, after = flatten(current), flatten(proposed)
    return [
        s.AdditionalModelContractFieldChange(
            path=path,
            previous=before.get(path),
            proposed=after.get(path),
        )
        for path in sorted(before.keys() | after.keys())
        if before.get(path) != after.get(path)
    ]


def preview_additional_model_contract(
    session: Session,
    model_id: UUID,
    value: s.AdditionalModelPortableContractV2,
) -> s.AdditionalModelContractPreviewRead:
    from portfolio_api.domain import queries

    model = session.get(FinancialModel, model_id)
    if model is None or model.model_type not in {
        FinancialModelType.OWNER_CASH_FLOW_10Y,
        FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
    }:
        raise DomainError("Extended financial model not found", 404)
    read = queries.extended_financial_model(session, model.id)
    current_revision = session.get(FinancialModelRevision, read.current_revision_id)
    if current_revision is None:
        raise DomainError("Current model revision is unavailable", 409)
    current_outputs_row = session.scalar(
        select(FinancialModelOutput).where(FinancialModelOutput.revision_id == current_revision.id)
    )
    if current_outputs_row is None:
        raise DomainError("Current model outputs are unavailable", 409)
    current_outputs = s.FinancialModelCalculationOutputsRead.model_validate(current_outputs_row)
    digest = _additional_contract_digest(value)
    existing_digest_revision = session.scalar(
        select(FinancialModelRevision).where(
            FinancialModelRevision.model_id == model.id,
            FinancialModelRevision.contract_digest == digest,
        )
    )
    existing_source_revision = session.scalar(
        select(FinancialModelRevision).where(
            FinancialModelRevision.model_id == model.id,
            FinancialModelRevision.source_revision_id
            == value.candidate_revision.source_revision_id,
        )
    )
    identity_matches = (
        value.model_id == model.id
        and value.company_id == model.company_id
        and value.model_type == model.model_type
        and value.model_name == model.model_name
        and value.valuation_listing_id == model.valuation_listing_id
        and value.model_currency == model.model_currency
        and value.source_model_key == model.source_model_key
    )
    already = existing_digest_revision is not None
    source_reused = existing_source_revision is not None and not already
    base_current = (
        value.base_revision_id == current_revision.id
        and value.base_revision_number == current_revision.revision_number
    )
    status: Literal["READY", "NO_CHANGES", "RATIONALE_REQUIRED", "CONFLICT", "ALREADY_IMPORTED"]
    reason: str | None = None
    changes: list[s.AdditionalModelContractFieldChange] = []
    output_changes: list[s.AdditionalModelContractFieldChange] = []
    calculated: s.FinancialModelCalculationOutputsRead | None = None
    if already:
        status = "ALREADY_IMPORTED"
        reason = "This exact portable contract is already an accepted revision."
    elif not identity_matches or not base_current or source_reused:
        status = "CONFLICT"
        reason = (
            "The model identity, source revision identity or base revision changed. "
            "Export the current revision and reconcile."
        )
    else:
        current_read = read.current_revision
        method_type = FinancialModelType(model.model_type)
        if method_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
            if not isinstance(current_read, s.OwnerCashFlowRevisionRead):
                raise DomainError("Owner cash-flow revision state is inconsistent", 409)
            owner_current_input = s.OwnerCashFlowInput(
                base=current_read.base, scenarios=current_read.scenarios
            )
            owner_proposed_input = value.candidate_revision.owner_cash_flow
            if owner_proposed_input is None:
                raise DomainError("Owner cash-flow contract input is missing")
            changes = _additional_input_changes(
                owner_current_input.model_dump(mode="json"),
                owner_proposed_input.model_dump(mode="json"),
            )
            owner_draft = s.OwnerCashFlowRevisionPreviewCreate(
                base_revision_id=current_revision.id, **owner_proposed_input.model_dump()
            )
            market, _ = _latest_model_market_price(session, model)
            owner_calculation = calculate_owner_cash_flow(
                owner_draft, model_currency=model.model_currency, market_price=market
            )
            owner_preview = _archetype_preview(
                owner_calculation,
                model_currency=model.model_currency,
                model_type=method_type,
                model_id=model.id,
                base_revision_id=current_revision.id,
                current_revision_id=current_revision.id,
                current_revision_number=current_revision.revision_number,
            )
        else:
            if not isinstance(current_read, s.ResidualIncomeRevisionRead):
                raise DomainError("Residual-income revision state is inconsistent", 409)
            residual_current_input = s.ResidualIncomeInput(
                base=current_read.base, scenarios=current_read.scenarios
            )
            residual_proposed_input = value.candidate_revision.residual_income
            if residual_proposed_input is None:
                raise DomainError("Residual-income contract input is missing")
            changes = _additional_input_changes(
                residual_current_input.model_dump(mode="json"),
                residual_proposed_input.model_dump(mode="json"),
            )
            residual_draft = s.ResidualIncomeRevisionPreviewCreate(
                base_revision_id=current_revision.id,
                **residual_proposed_input.model_dump(),
            )
            market, _ = _latest_model_market_price(session, model)
            residual_calculation = calculate_residual_income(
                residual_draft, model_currency=model.model_currency, market_price=market
            )
            residual_preview = _archetype_preview(
                residual_calculation,
                model_currency=model.model_currency,
                model_type=method_type,
                model_id=model.id,
                base_revision_id=current_revision.id,
                current_revision_id=current_revision.id,
                current_revision_number=current_revision.revision_number,
            )
            preview = residual_preview
        if method_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
            preview = owner_preview
        calculated = preview.outputs
        output_fields = (
            "bear_fv",
            "base_fv",
            "bull_fv",
            "weighted_fv",
            "weighted_upside",
            "expected_cash_flow_irr",
            "hurdle",
            "expected_excess",
        )
        output_changes = [
            s.AdditionalModelContractFieldChange(
                path=field,
                previous=str(getattr(current_outputs, field))
                if getattr(current_outputs, field) is not None
                else None,
                proposed=str(getattr(calculated, field))
                if getattr(calculated, field) is not None
                else None,
            )
            for field in output_fields
            if getattr(current_outputs, field) != getattr(calculated, field)
        ]
        if not changes:
            status = "NO_CHANGES"
            reason = "The method inputs are unchanged; no new revision is needed."
        elif not value.candidate_revision.rationale:
            status = "RATIONALE_REQUIRED"
            reason = "Add a rationale before importing changed assumptions."
        else:
            status = "READY"
    return s.AdditionalModelContractPreviewRead(
        status=status,
        model_id=model.id,
        base_revision_id=value.base_revision_id,
        current_revision_id=current_revision.id,
        current_revision_number=current_revision.revision_number,
        source_revision_id=value.candidate_revision.source_revision_id,
        changes=changes,
        output_changes=output_changes,
        current_outputs=s.FinancialModelCalculationOutputsRead.model_validate(current_outputs),
        calculated_outputs=calculated,
        reason=reason,
    )


def import_additional_model_contract(
    session: Session,
    model_id: UUID,
    value: s.AdditionalModelPortableContractV2,
) -> s.AdditionalModelContractImportRead:
    from portfolio_api.domain import queries

    model = session.scalar(
        select(FinancialModel).where(FinancialModel.id == model_id).with_for_update()
    )
    if model is None:
        raise DomainError("Extended financial model not found", 404)
    preview = preview_additional_model_contract(session, model_id, value)
    digest = _additional_contract_digest(value)
    if preview.status == "ALREADY_IMPORTED":
        revision = session.scalar(
            select(FinancialModelRevision).where(
                FinancialModelRevision.model_id == model.id,
                FinancialModelRevision.contract_digest == digest,
            )
        )
        if revision is None:
            raise DomainError("Imported contract receipt is inconsistent", 409)
        return s.AdditionalModelContractImportRead(
            status="ALREADY_IMPORTED",
            model=queries.extended_financial_model(session, model.id),
            revision=queries.extended_financial_model_revision(session, model.id, revision.id),
        )
    if preview.status != "READY":
        raise DomainError(preview.reason or "Portable model contract is not ready to import", 409)
    candidate = value.candidate_revision
    common = dict(
        base_revision_id=value.base_revision_id,
        source_revision_id=candidate.source_revision_id,
        actor="IMPORT",
        source=candidate.source,
        rationale=candidate.rationale,
        effective_at=candidate.effective_at,
    )
    method_type = FinancialModelType(model.model_type)
    if method_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        if candidate.owner_cash_flow is None or candidate.rationale is None:
            raise DomainError("Owner cash-flow input and rationale are required")
        owner_revision_input = s.OwnerCashFlowRevisionCreate(
            **common, **candidate.owner_cash_flow.model_dump()
        )
        revision = _append_archetype_revision(
            session,
            model,
            owner_revision_input,
            method_type,
            contract_digest=digest,
        )
    else:
        if candidate.residual_income is None or candidate.rationale is None:
            raise DomainError("Residual-income input and rationale are required")
        residual_revision_input = s.ResidualIncomeRevisionCreate(
            **common, **candidate.residual_income.model_dump()
        )
        revision = _append_archetype_revision(
            session,
            model,
            residual_revision_input,
            method_type,
            contract_digest=digest,
        )
    return s.AdditionalModelContractImportRead(
        status="IMPORTED",
        model=queries.extended_financial_model(session, model.id),
        revision=queries.extended_financial_model_revision(session, model.id, revision.id),
    )


def _contract_digest(value: s.FinancialModelContractV1) -> str:
    canonical = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def export_financial_model_contract(session: Session, model_id: UUID) -> s.FinancialModelContractV1:
    from portfolio_api.domain import queries

    model = queries.financial_model(session, model_id)
    current = model.current_revision
    candidate = s.FinancialModelContractCandidateRevision(
        source_revision_id=f"google-sheets:{uuid4()}",
        actor="IMPORT",
        source="Google Sheets portable contract",
        rationale=current.rationale,
        effective_at=now(),
        base=current.base.model_dump(),
        scenarios=[
            {
                "scenario": scenario.scenario,
                "probability": scenario.probability,
                "terminal_growth": scenario.terminal_growth,
                "year10_ufcf_growth": scenario.year10_ufcf_growth,
                "rationale": scenario.rationale,
                "years": [
                    year.model_dump(
                        exclude={"id", "scenario_id"},
                    )
                    for year in scenario.years
                ],
            }
            for scenario in current.scenarios
        ],
    )
    return s.FinancialModelContractV1(
        contract_version="1.0.0",
        exported_at=now(),
        model=s.FinancialModelContractIdentity(
            model_id=model.id,
            company_id=model.company_id,
            model_type=model.model_type,
            model_name=model.model_name,
            valuation_listing_id=model.valuation_listing.id,
            valuation_listing=model.valuation_listing,
            model_currency=model.model_currency,
            source_model_key=model.source_model_key,
        ),
        base_revision=s.FinancialModelContractBaseRevision(
            revision_id=current.id,
            revision_number=current.revision_number,
            methodology_version=current.methodology_version,
        ),
        candidate_revision=candidate,
        base_calculation=s.FinancialModelContractCalculation(
            revision_id=current.id,
            outputs=current.outputs,
            projections=current.projections,
        ),
    )


def _contract_input_fields(
    value: s.FinancialModelContractV1,
) -> dict[str, str | None]:
    fields: dict[str, str | None] = {}
    candidate = value.candidate_revision
    for key, item in candidate.base.model_dump().items():
        fields[f"base.{key}"] = None if item is None else str(item)
    for scenario in candidate.scenarios:
        prefix = f"scenarios.{scenario.scenario}"
        fields[f"{prefix}.probability"] = str(scenario.probability)
        fields[f"{prefix}.terminal_growth"] = str(scenario.terminal_growth)
        fields[f"{prefix}.year10_ufcf_growth"] = str(scenario.year10_ufcf_growth)
        fields[f"{prefix}.rationale"] = scenario.rationale
        for year in scenario.years:
            year_prefix = f"{prefix}.years.{year.forecast_year}"
            for key, item in year.model_dump().items():
                if key != "forecast_year":
                    fields[f"{year_prefix}.{key}"] = None if item is None else str(item)
    fields["revision.rationale"] = candidate.rationale
    return fields


def _revision_input_fields(
    value: s.FinancialModelRevisionRead,
) -> dict[str, str | None]:
    fields: dict[str, str | None] = {}
    for key, item in value.base.model_dump().items():
        fields[f"base.{key}"] = None if item is None else str(item)
    for scenario in value.scenarios:
        prefix = f"scenarios.{scenario.scenario}"
        fields[f"{prefix}.probability"] = str(scenario.probability)
        fields[f"{prefix}.terminal_growth"] = str(scenario.terminal_growth)
        fields[f"{prefix}.year10_ufcf_growth"] = str(scenario.year10_ufcf_growth)
        fields[f"{prefix}.rationale"] = scenario.rationale
        for year in scenario.years:
            year_prefix = f"{prefix}.years.{year.forecast_year}"
            for key, item in year.model_dump(exclude={"id", "scenario_id"}).items():
                if key != "forecast_year":
                    fields[f"{year_prefix}.{key}"] = None if item is None else str(item)
    fields["revision.rationale"] = value.rationale
    return fields


def _contract_output_summary(
    *,
    model_currency: str,
    calculation: DcfCalculation,
) -> s.FinancialModelContractOutputSummary:
    # The supported deterministic calculation has an intentionally small output
    # interface; this adapter keeps transport logic out of the calculation module.
    result = calculation

    def stored(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        with localcontext() as context:
            context.prec = 50
            return value.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP)

    return s.FinancialModelContractOutputSummary(
        status=result.status,
        model_currency=model_currency,
        price_status=result.price_status,
        current_price=result.current_price,
        price_effective_at=result.price_effective_at,
        price_unavailable_reason=result.price_unavailable_reason,
        bear_fv=stored(result.bear_fv),
        base_fv=stored(result.base_fv),
        bull_fv=stored(result.bull_fv),
        weighted_fv=stored(result.weighted_fv),
        weighted_upside=stored(result.weighted_upside),
        expected_cash_flow_irr=stored(result.expected_cash_flow_irr),
        hurdle=stored(result.hurdle),
        expected_excess=stored(result.expected_excess),
        irr_unavailable_reason=result.irr_unavailable_reason,
    )


def _stored_contract_output_summary(
    output: s.FinancialModelOutputsRead,
) -> s.FinancialModelContractOutputSummary:
    return s.FinancialModelContractOutputSummary(
        status=output.status,
        model_currency=output.model_currency,
        price_status=output.price_status,
        current_price=output.current_price,
        price_effective_at=output.price_effective_at,
        price_unavailable_reason=output.price_unavailable_reason,
        bear_fv=output.bear_fv,
        base_fv=output.base_fv,
        bull_fv=output.bull_fv,
        weighted_fv=output.weighted_fv,
        weighted_upside=output.weighted_upside,
        expected_cash_flow_irr=output.expected_cash_flow_irr,
        hurdle=output.hurdle,
        expected_excess=output.expected_excess,
        irr_unavailable_reason=output.irr_unavailable_reason,
    )


def _output_changes(
    previous: s.FinancialModelContractOutputSummary,
    proposed: s.FinancialModelContractOutputSummary | None,
) -> list[s.FinancialModelContractFieldChange]:
    if proposed is None:
        return []
    before = previous.model_dump(mode="json")
    after = proposed.model_dump(mode="json")
    return [
        s.FinancialModelContractFieldChange(
            path=f"outputs.{key}",
            previous=None if before[key] is None else str(before[key]),
            proposed=None if after[key] is None else str(after[key]),
        )
        for key in before
        if before[key] != after[key]
    ]


def _financial_model_contract_preview(
    session: Session,
    model: FinancialModel,
    value: s.FinancialModelContractV1,
) -> tuple[s.FinancialModelContractPreviewRead, s.FinancialModelRevisionCreate | None, str]:
    from portfolio_api.domain import queries

    current_model = queries.financial_model(session, model.id)
    current = current_model.current_revision
    if (
        value.model.model_id != model.id
        or value.model.company_id != model.company_id
        or value.model.model_type != model.model_type
        or value.model.valuation_listing_id != model.valuation_listing_id
        or value.model.model_currency != model.model_currency
        or value.model.model_name != model.model_name
        or value.model.source_model_key != model.source_model_key
        or value.model.valuation_listing != current_model.valuation_listing
    ):
        raise DomainError("The portable contract identifies a different model or listing", 409)

    source_id = value.candidate_revision.source_revision_id
    digest = _contract_digest(value)
    imported = session.scalar(
        select(FinancialModelRevision).where(
            FinancialModelRevision.model_id == model.id,
            FinancialModelRevision.source_revision_id == source_id,
        )
    )
    current_summary = _stored_contract_output_summary(current.outputs)
    if imported is not None:
        already_imported = imported.contract_digest == digest
        response = s.FinancialModelContractPreviewRead(
            status="ALREADY_IMPORTED" if already_imported else "CONFLICT",
            model_id=model.id,
            base_revision_id=value.base_revision.revision_id,
            current_revision_id=current.id,
            current_revision_number=current.revision_number,
            source_revision_id=source_id,
            actor="IMPORT",
            source=value.candidate_revision.source,
            effective_at=value.candidate_revision.effective_at,
            proposed_revision_number=None,
            already_imported_revision_id=imported.id if already_imported else None,
            reason=(
                "This exact contract was already accepted."
                if already_imported
                else "This external revision identity was already used with different content."
            ),
            changes=[],
            output_changes=[],
            current_outputs=current_summary,
            calculated_outputs=None,
        )
        return response, None, digest

    base_row = session.get(FinancialModelRevision, value.base_revision.revision_id)
    if base_row is None or base_row.model_id != model.id:
        response = s.FinancialModelContractPreviewRead(
            status="CONFLICT",
            model_id=model.id,
            base_revision_id=value.base_revision.revision_id,
            current_revision_id=current.id,
            current_revision_number=current.revision_number,
            source_revision_id=source_id,
            actor="IMPORT",
            source=value.candidate_revision.source,
            effective_at=value.candidate_revision.effective_at,
            proposed_revision_number=None,
            already_imported_revision_id=None,
            reason="The named base revision does not belong to this model.",
            changes=[],
            output_changes=[],
            current_outputs=current_summary,
            calculated_outputs=None,
        )
        return response, None, digest

    base_detail = queries.financial_model_revision(session, model.id, base_row.id)
    snapshot = value.base_calculation
    snapshot_matches = (
        base_row.revision_number == value.base_revision.revision_number
        and base_row.methodology_version == value.base_revision.methodology_version
        and snapshot.revision_id == base_detail.id
        and snapshot.outputs.model_dump(mode="json") == base_detail.outputs.model_dump(mode="json")
        and [row.model_dump(mode="json") for row in snapshot.projections]
        == [row.model_dump(mode="json") for row in base_detail.projections]
    )
    if not snapshot_matches:
        status: Literal[
            "READY",
            "NO_CHANGES",
            "RATIONALE_REQUIRED",
            "CONFLICT",
            "INVALID_BASE_SNAPSHOT",
            "ALREADY_IMPORTED",
        ] = "INVALID_BASE_SNAPSHOT"
        reason: str | None = "The exported base calculation does not match the stored revision."
    else:
        status = "CONFLICT" if current.id != base_row.id else "READY"
        reason = (
            "The application has advanced since this contract was exported. "
            "Re-export and reapply the edits."
            if status == "CONFLICT"
            else None
        )

    revision_value = s.FinancialModelRevisionCreate(
        base_revision_id=value.base_revision.revision_id,
        **value.candidate_revision.model_dump(),
    )
    old_fields = _revision_input_fields(base_detail)
    new_fields = _contract_input_fields(value)
    changes = [
        s.FinancialModelContractFieldChange(
            path=key,
            previous=old_fields.get(key),
            proposed=new_fields.get(key),
        )
        for key in sorted(old_fields.keys() | new_fields.keys())
        if old_fields.get(key) != new_fields.get(key)
    ]
    changed_model_inputs = any(
        not change.path.startswith("revision.rationale") for change in changes
    )
    rationale_changed = old_fields["revision.rationale"] != new_fields["revision.rationale"]

    calculation_summary: s.FinancialModelContractOutputSummary | None = None
    if snapshot_matches:
        market_price, _ = _latest_model_market_price(session, model)
        try:
            calculation = calculate_ufcf_dcf(
                revision_value, model_currency=model.model_currency, market_price=market_price
            )
            calculation_summary = _contract_output_summary(
                model_currency=model.model_currency,
                calculation=calculation,
            )
        except ValueError as error:
            raise DomainError(str(error)) from None
        if current.id == base_row.id:
            if not changes:
                status = "NO_CHANGES"
                reason = "The candidate contains no model input or rationale changes."
            elif changed_model_inputs and not rationale_changed:
                status = "RATIONALE_REQUIRED"
                reason = "Add a revision rationale when changing model inputs."

    response = s.FinancialModelContractPreviewRead(
        status=status,
        model_id=model.id,
        base_revision_id=base_row.id,
        current_revision_id=current.id,
        current_revision_number=current.revision_number,
        source_revision_id=source_id,
        actor="IMPORT",
        source=value.candidate_revision.source,
        effective_at=value.candidate_revision.effective_at,
        proposed_revision_number=(current.revision_number + 1 if status == "READY" else None),
        already_imported_revision_id=None,
        reason=reason,
        changes=changes,
        output_changes=_output_changes(current_summary, calculation_summary),
        current_outputs=current_summary,
        calculated_outputs=calculation_summary,
    )
    return response, revision_value, digest


def preview_financial_model_contract(
    session: Session, model_id: UUID, value: s.FinancialModelContractV1
) -> s.FinancialModelContractPreviewRead:
    model = session.get(FinancialModel, model_id)
    if model is None:
        raise DomainError("Financial model not found", 404)
    preview, _, _ = _financial_model_contract_preview(session, model, value)
    return preview


def import_financial_model_contract(
    session: Session, model_id: UUID, value: s.FinancialModelContractV1
) -> s.FinancialModelContractImportRead:
    from portfolio_api.domain import queries

    model = session.scalar(
        select(FinancialModel).where(FinancialModel.id == model_id).with_for_update()
    )
    if model is None:
        raise DomainError("Financial model not found", 404)
    preview, revision_value, digest = _financial_model_contract_preview(session, model, value)
    if preview.status == "ALREADY_IMPORTED":
        revision_id = preview.already_imported_revision_id
        if revision_id is None:
            raise DomainError("Imported contract identity is inconsistent", 409)
        return s.FinancialModelContractImportRead(
            status="ALREADY_IMPORTED",
            model=queries.financial_model(session, model_id),
            revision=queries.financial_model_revision(session, model_id, revision_id),
        )
    if preview.status == "CONFLICT":
        raise DomainError(preview.reason or "The model changed since export", 409)
    if preview.status != "READY" or revision_value is None:
        raise DomainError(preview.reason or "The contract is not ready to import")

    revision = _append_dcf_revision(
        session,
        model,
        revision_value,
        contract_digest=digest,
    )
    return s.FinancialModelContractImportRead(
        status="IMPORTED",
        model=queries.financial_model(session, model_id),
        revision=queries.financial_model_revision(session, model_id, revision.id),
    )


def transition_lifecycle(
    session: Session, company_id: UUID, value: s.LifecycleChange
) -> LifecycleEvent:
    company(session, company_id, lock=True)
    projection = session.get(CurrentLifecycle, company_id)
    previous = session.get(LifecycleEvent, projection.event_id) if projection else None
    actual_event_id = previous.id if previous else None
    if actual_event_id != value.expected_event_id:
        raise DomainError("Lifecycle changed since it was read; reload before transitioning", 409)
    if previous and previous.new_state == value.new_state:
        raise DomainError("The company already has this lifecycle state", 409)
    if previous and value.effective_at < previous.effective_at:
        raise DomainError("Backdated lifecycle transitions are outside Milestone 1A")
    event = LifecycleEvent(
        company_id=company_id,
        sequence=previous.sequence + 1 if previous else 1,
        previous_state=previous.new_state if previous else None,
        **value.model_dump(exclude={"expected_event_id"}),
    )
    session.add(event)
    session.flush()
    if projection is None:
        session.add(CurrentLifecycle(company_id=company_id, event_id=event.id))
    else:
        projection.event_id = event.id
    session.flush()
    return event


def create_portfolio(
    session: Session, value: s.PortfolioCreate, *, demo: bool = False
) -> Portfolio:
    # Serialize the initial one-portfolio policy without baking it into future schema.
    session.execute(text("SELECT pg_advisory_xact_lock(1347375700)"))
    if session.scalar(select(Portfolio.id).limit(1)) is not None:
        raise DomainError("Milestone 1A supports one logical portfolio", 409)
    item = Portfolio(**value.model_dump(), is_demo=demo)
    session.add(item)
    session.flush()
    return item


def record_holdings(
    session: Session, portfolio_id: UUID, value: s.SnapshotCreate
) -> HoldingSnapshot:
    portfolio(session, portfolio_id, lock=True)
    for position in value.positions:
        if session.get(Listing, position.listing_id) is None:
            raise DomainError("A held listing was not found", 404)
    snapshot = HoldingSnapshot(
        portfolio_id=portfolio_id,
        **value.model_dump(exclude={"positions", "cash_positions"}),
    )
    session.add(snapshot)
    session.flush()
    session.info["new_snapshot_ids"] = {snapshot.id}
    try:
        session.add_all(
            HoldingPosition(snapshot_id=snapshot.id, **p.model_dump()) for p in value.positions
        )
        session.add_all(
            CashPosition(snapshot_id=snapshot.id, **p.model_dump()) for p in value.cash_positions
        )
        session.flush()
    finally:
        session.info.pop("new_snapshot_ids", None)
    return snapshot


def create_targets(session: Session, portfolio_id: UUID, value: s.TargetCreate) -> TargetRevision:
    portfolio(session, portfolio_id, lock=True)
    for allocation in value.allocations:
        company(session, allocation.company_id)
    revision = TargetRevision(
        portfolio_id=portfolio_id,
        status="DRAFT",
        **value.model_dump(exclude={"allocations"}),
    )
    session.add(revision)
    session.flush()
    session.add_all(
        TargetAllocation(revision_id=revision.id, **a.model_dump()) for a in value.allocations
    )
    session.flush()
    return revision


def accept_targets(session: Session, portfolio_id: UUID, revision_id: UUID) -> TargetRevision:
    portfolio(session, portfolio_id, lock=True)
    revision = session.scalar(
        select(TargetRevision)
        .where(
            TargetRevision.id == revision_id,
            TargetRevision.portfolio_id == portfolio_id,
        )
        .with_for_update()
    )
    if revision is None:
        raise DomainError("Target revision not found", 404)
    if revision.status != "DRAFT":
        raise DomainError("An accepted target revision is immutable; author a new revision", 409)
    latest = session.scalar(
        select(TargetRevision)
        .where(
            TargetRevision.portfolio_id == portfolio_id,
            TargetRevision.status == "ACCEPTED",
        )
        .order_by(TargetRevision.effective_at.desc(), TargetRevision.accepted_at.desc())
        .limit(1)
    )
    if latest is not None and revision.effective_at < latest.effective_at:
        raise DomainError("Backdated target acceptance is outside Milestone 1A")
    allocations = session.scalars(
        select(TargetAllocation).where(TargetAllocation.revision_id == revision_id)
    ).all()
    if (
        any(not 0 <= a.weight <= 1 for a in allocations)
        or sum((a.weight for a in allocations), Decimal(0)) > 1
    ):
        raise DomainError("Invested target weights must remain in [0,1] and sum to at most 1")
    revision.status = "ACCEPTED"
    revision.accepted_at = now()
    session.flush()
    return revision


def create_score_assessment(
    session: Session, company_id: UUID, value: s.ScoreAssessmentCreate
) -> ScoreAssessment:
    company(session, company_id)
    definition = session.scalar(
        select(ScoreDefinition).where(
            ScoreDefinition.dimension == value.dimension,
            ScoreDefinition.status == ScoreDefinitionStatus.ACTIVE,
            ScoreDefinition.effective_from <= now(),
        )
    )
    if definition is None:
        raise DomainError("No effective score definition is configured", 409)
    if value.score is not None and not (
        definition.minimum_score <= value.score <= definition.maximum_score
    ):
        raise DomainError(
            f"Score must be between {definition.minimum_score} and {definition.maximum_score} "
            f"for {definition.dimension} version {definition.version}"
        )

    previous = session.scalar(
        select(ScoreAssessment)
        .where(
            ScoreAssessment.company_id == company_id,
            ScoreAssessment.score_definition_id == definition.id,
        )
        .order_by(
            ScoreAssessment.effective_at.desc(),
            ScoreAssessment.recorded_at.desc(),
            ScoreAssessment.id.desc(),
        )
        .limit(1)
    )
    expected_previous = previous.id if previous else None
    if value.superseded_assessment_id != expected_previous:
        raise DomainError(
            "A newer score assessment exists; reload before recording a revision", 409
        )
    if previous is not None and value.effective_at < previous.effective_at:
        raise DomainError("Score revisions cannot be backdated ahead of existing assessments")

    recorded_at = now()
    if previous is not None and recorded_at <= previous.recorded_at:
        recorded_at = previous.recorded_at + timedelta(microseconds=1)
    assessment = ScoreAssessment(
        company_id=company_id,
        score_definition_id=definition.id,
        recorded_at=recorded_at,
        **value.model_dump(exclude={"dimension"}),
    )
    session.add(assessment)
    session.flush()
    return assessment


def create_ranking_run(session: Session, value: s.RankingRunCreate) -> RankingRun:
    """Persist a run's universe and explicit blockers; never guess ordinal positions."""
    run_as_of = now()
    definition = session.scalar(
        select(RankingDefinition).where(
            RankingDefinition.ranking_type == value.ranking_type,
            RankingDefinition.status == RankingDefinitionStatus.ACTIVE,
            RankingDefinition.effective_from <= run_as_of,
            RankingDefinition.recorded_at <= run_as_of,
        )
    )
    if definition is None:
        raise DomainError("No effective definition exists for this ranking type", 409)
    if (
        not (
            value.ranking_type
            in (RankingType.WATCHLIST, RankingType.PORTFOLIO, RankingType.RESEARCH)
            and definition.implementation_status == RankingImplementationStatus.READY
        )
        and definition.implementation_status != RankingImplementationStatus.NOT_MIGRATED
    ):
        raise DomainError("No registered ranking implementation exists for this definition", 409)

    issuers = list(
        session.scalars(
            select(Company)
            .where(Company.created_at <= run_as_of)
            .order_by(Company.name, Company.id)
        )
    )
    lifecycles: dict[UUID, Lifecycle] = {}
    for company_id, lifecycle in session.execute(
        select(LifecycleEvent.company_id, LifecycleEvent.new_state)
        .where(
            LifecycleEvent.effective_at <= run_as_of,
            LifecycleEvent.recorded_at <= run_as_of,
        )
        .order_by(LifecycleEvent.sequence.desc())
    ):
        lifecycles.setdefault(company_id, Lifecycle(lifecycle))
    entry_states: list[
        tuple[UUID, RankingEntryStatus, str, int | None, dict[str, object] | None]
    ] = []
    if value.ranking_type == RankingType.WATCHLIST:
        entry_states = build_watchlist_rank_entries(
            session,
            issuers,
            {company_id: lifecycle.value for company_id, lifecycle in lifecycles.items()},
            run_as_of,
        )
    elif value.ranking_type == RankingType.RESEARCH:
        entry_states = build_research_rank_entries(session, issuers, run_as_of)
    elif value.ranking_type == RankingType.PORTFOLIO:
        entry_states = build_portfolio_rank_entries(session, issuers, run_as_of)

    ranked_count = sum(status == RankingEntryStatus.RANKED for _, status, _, _, _ in entry_states)
    if ranked_count == 0:
        run_status = RankingRunStatus.UNAVAILABLE
    elif all(
        status
        in (
            RankingEntryStatus.RANKED,
            RankingEntryStatus.NOT_ELIGIBLE,
            RankingEntryStatus.EXCLUDED,
        )
        for _, status, _, _, _ in entry_states
    ):
        run_status = RankingRunStatus.COMPLETE
    else:
        run_status = RankingRunStatus.PARTIAL
    previous_run = session.scalar(
        select(RankingRun)
        .where(RankingRun.definition_id == definition.id)
        .order_by(
            RankingRun.as_of.desc(),
            RankingRun.recorded_at.desc(),
            RankingRun.id.desc(),
        )
        .limit(1)
    )
    recorded_at = now()
    if previous_run is not None and recorded_at <= previous_run.recorded_at:
        recorded_at = previous_run.recorded_at + timedelta(microseconds=1)
    run = RankingRun(
        definition_id=definition.id,
        as_of=run_as_of,
        recorded_at=recorded_at,
        status=run_status,
        actor=value.actor,
        reason=value.reason,
        source=value.source,
    )
    session.add(run)
    session.flush()
    session.add_all(
        RankingEntry(
            run_id=run.id,
            company_id=company_id,
            position=position,
            status=status,
            reason=reason,
            input_snapshot=input_snapshot,
        )
        for company_id, status, reason, position, input_snapshot in entry_states
    )
    session.flush()
    return run
