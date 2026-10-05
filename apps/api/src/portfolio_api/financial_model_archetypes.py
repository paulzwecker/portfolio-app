"""Independent deterministic engines for two workbook-proven model archetypes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from portfolio_api.domain.models import DcfScenario
from portfolio_api.domain.schemas import OwnerCashFlowInput, ResidualIncomeInput
from portfolio_api.financial_models import MarketPriceInput, PriceState, _irr


@dataclass(frozen=True)
class OwnerCashFlowProjectionCalculation:
    scenario: DcfScenario
    forecast_year: int
    revenue: Decimal
    owner_cash_flow: Decimal
    owner_cash_flow_per_share: Decimal
    present_value_per_share: Decimal
    terminal_value_per_share: Decimal | None


@dataclass(frozen=True)
class ResidualIncomeProjectionCalculation:
    scenario: DcfScenario
    forecast_year: int
    beginning_book_value_per_share: Decimal
    return_on_equity: Decimal
    net_income_per_share: Decimal
    dividend_per_share: Decimal
    ending_book_value_per_share: Decimal
    residual_income_per_share: Decimal
    present_value_residual_income: Decimal
    terminal_value_per_share: Decimal | None


@dataclass(frozen=True)
class ArchetypeScenarioCalculation:
    scenario: DcfScenario
    probability: Decimal
    fair_value_per_share: Decimal
    terminal_value_per_share: Decimal
    projections: tuple[
        OwnerCashFlowProjectionCalculation | ResidualIncomeProjectionCalculation, ...
    ]


@dataclass(frozen=True)
class ArchetypeCalculation:
    scenarios: tuple[ArchetypeScenarioCalculation, ...]
    bear_fv: Decimal
    base_fv: Decimal
    bull_fv: Decimal
    bear_probability: Decimal
    base_probability: Decimal
    bull_probability: Decimal
    weighted_fv: Decimal
    weighted_upside: Decimal | None
    expected_cash_flow_irr: Decimal | None
    hurdle: Decimal
    expected_excess: Decimal | None
    status: Literal["COMPLETE", "PARTIAL"]
    price_status: PriceState
    price_unavailable_reason: str | None
    irr_unavailable_reason: str | None
    current_price: Decimal | None
    price_observation_id: UUID | None
    price_effective_at: object | None


def _market_state(
    model_currency: str, market_price: MarketPriceInput
) -> tuple[PriceState, str | None, bool]:
    state: PriceState = market_price.freshness
    reason = None
    valid = market_price.price is not None and market_price.price > 0
    if market_price.price is not None and market_price.currency is None:
        state, reason, valid = "CURRENCY_UNKNOWN", "The listing quote currency is unknown.", False
    elif market_price.currency is not None and market_price.currency != model_currency:
        state = "CURRENCY_MISMATCH"
        reason = f"The {market_price.currency} listing quote is not converted to {model_currency}."
        valid = False
    elif state == "FRESH" and not valid:
        state, reason = "QUALITY_CHECK", "The latest fresh listing observation has no valid close."
    elif state != "FRESH":
        reason = {
            "STALE": "The latest listing observation is stale.",
            "QUALITY_CHECK": "The latest listing observation did not pass data quality checks.",
            "NO_DATA": "No listing price observation is available.",
        }[state]
        valid = False
    return state, reason, valid and market_price.currency == model_currency


def _normalized(
    *,
    scenarios: tuple[ArchetypeScenarioCalculation, ...],
    hurdle: Decimal,
    expected_flows: list[Decimal],
    terminal_flows: list[Decimal],
    model_currency: str,
    market_price: MarketPriceInput,
) -> ArchetypeCalculation:
    by_name = {row.scenario: row for row in scenarios}
    bear, base, bull = (
        by_name[name] for name in (DcfScenario.BEAR, DcfScenario.BASE, DcfScenario.BULL)
    )
    weighted_fv = sum((row.fair_value_per_share * row.probability for row in scenarios), Decimal(0))
    price_status, price_reason, can_use_price = _market_state(model_currency, market_price)
    weighted_upside = None
    expected_irr = None
    expected_excess = None
    irr_reason = price_reason
    if can_use_price:
        assert market_price.price is not None
        weighted_upside = weighted_fv / market_price.price - Decimal(1)
        cash_flows = [-market_price.price]
        cash_flows.extend(expected_flows[:-1])
        cash_flows.append(expected_flows[-1] + sum(terminal_flows, Decimal(0)))
        expected_irr = _irr(cash_flows)
        if expected_irr is None:
            irr_reason = (
                "Probability-weighted shareholder cash flows have no unique conventional IRR root."
            )
        else:
            expected_excess = expected_irr - hurdle
            irr_reason = None
    return ArchetypeCalculation(
        scenarios=scenarios,
        bear_fv=bear.fair_value_per_share,
        base_fv=base.fair_value_per_share,
        bull_fv=bull.fair_value_per_share,
        bear_probability=bear.probability,
        base_probability=base.probability,
        bull_probability=bull.probability,
        weighted_fv=weighted_fv,
        weighted_upside=weighted_upside,
        expected_cash_flow_irr=expected_irr,
        hurdle=hurdle,
        expected_excess=expected_excess,
        status="COMPLETE"
        if weighted_upside is not None and expected_irr is not None
        else "PARTIAL",
        price_status=price_status,
        price_unavailable_reason=price_reason,
        irr_unavailable_reason=irr_reason,
        current_price=market_price.price,
        price_observation_id=market_price.observation_id,
        price_effective_at=market_price.effective_at,
    )


def calculate_owner_cash_flow(
    revision: OwnerCashFlowInput,
    *,
    model_currency: str,
    market_price: MarketPriceInput,
) -> ArchetypeCalculation:
    """TOST-style owner-CF DCF: SBC-adjusted shareholder cash flow plus net cash."""
    with localcontext() as context:
        context.prec = 38
        base = revision.base
        results: list[ArchetypeScenarioCalculation] = []
        expected_flows = [Decimal(0) for _ in range(10)]
        terminal_flows: list[Decimal] = []
        hurdle = Decimal(0)
        for scenario in sorted(
            revision.scenarios, key=lambda item: ("BEAR", "BASE", "BULL").index(item.scenario.value)
        ):
            revenue = base.base_revenue
            projections: list[OwnerCashFlowProjectionCalculation] = []
            discounted = Decimal(0)
            for year in sorted(scenario.years, key=lambda item: item.forecast_year):
                revenue *= Decimal(1) + year.revenue_growth
                owner_cf = revenue * year.owner_cash_flow_margin
                per_share = owner_cf / base.diluted_shares
                present_value = per_share / (
                    (Decimal(1) + scenario.required_return) ** year.forecast_year
                )
                terminal = None
                if year.forecast_year == 10:
                    terminal = (
                        per_share
                        * (Decimal(1) + scenario.terminal_growth)
                        / (scenario.required_return - scenario.terminal_growth)
                    )
                discounted += present_value
                projections.append(
                    OwnerCashFlowProjectionCalculation(
                        scenario=scenario.scenario,
                        forecast_year=year.forecast_year,
                        revenue=revenue,
                        owner_cash_flow=owner_cf,
                        owner_cash_flow_per_share=per_share,
                        present_value_per_share=present_value,
                        terminal_value_per_share=terminal,
                    )
                )
                expected_flows[year.forecast_year - 1] += per_share * scenario.probability
                if year.forecast_year == 10:
                    assert terminal is not None
                    terminal_flows.append(terminal * scenario.probability)
            net_cash_per_share = base.net_cash / base.diluted_shares
            terminal_flows[-1] += net_cash_per_share * scenario.probability
            terminal_value = projections[-1].terminal_value_per_share
            assert terminal_value is not None
            fair_value = (
                discounted
                + terminal_value / ((Decimal(1) + scenario.required_return) ** 10)
                + net_cash_per_share
            )
            results.append(
                ArchetypeScenarioCalculation(
                    scenario=scenario.scenario,
                    probability=scenario.probability,
                    fair_value_per_share=fair_value,
                    terminal_value_per_share=terminal_value,
                    projections=tuple(projections),
                )
            )
            hurdle += scenario.required_return * scenario.probability
        return _normalized(
            scenarios=tuple(results),
            hurdle=hurdle,
            expected_flows=expected_flows,
            terminal_flows=[sum(terminal_flows, Decimal(0))],
            model_currency=model_currency,
            market_price=market_price,
        )


def calculate_residual_income(
    revision: ResidualIncomeInput,
    *,
    model_currency: str,
    market_price: MarketPriceInput,
) -> ArchetypeCalculation:
    """HDFC-style equity valuation: book value plus discounted residual income."""
    with localcontext() as context:
        context.prec = 38
        base = revision.base
        results: list[ArchetypeScenarioCalculation] = []
        expected_flows = [Decimal(0) for _ in range(10)]
        terminal_flows: list[Decimal] = []
        hurdle = Decimal(0)
        order = (DcfScenario.BEAR, DcfScenario.BASE, DcfScenario.BULL)
        for scenario in sorted(revision.scenarios, key=lambda item: order.index(item.scenario)):
            book = base.current_book_value_per_share
            projections: list[ResidualIncomeProjectionCalculation] = []
            discounted_ri = Decimal(0)
            for year_number in range(1, 11):
                if year_number <= 5:
                    roe = scenario.starting_roe
                else:
                    fade = Decimal(year_number - 5) / Decimal(5)
                    roe = (
                        scenario.starting_roe + (scenario.mature_roe - scenario.starting_roe) * fade
                    )
                begin = book
                net_income = begin * roe
                dividend = net_income * base.payout_ratio
                book = begin + net_income - dividend
                residual = (roe - scenario.cost_of_equity) * begin
                pv = residual / ((Decimal(1) + scenario.cost_of_equity) ** year_number)
                terminal = None
                if year_number == 10:
                    terminal = (
                        (scenario.mature_roe - scenario.cost_of_equity)
                        * book
                        * (Decimal(1) + scenario.terminal_growth)
                        / (scenario.cost_of_equity - scenario.terminal_growth)
                    )
                discounted_ri += pv
                projection = ResidualIncomeProjectionCalculation(
                    scenario=scenario.scenario,
                    forecast_year=year_number,
                    beginning_book_value_per_share=begin,
                    return_on_equity=roe,
                    net_income_per_share=net_income,
                    dividend_per_share=dividend,
                    ending_book_value_per_share=book,
                    residual_income_per_share=residual,
                    present_value_residual_income=pv,
                    terminal_value_per_share=terminal,
                )
                projections.append(projection)
                expected_flows[year_number - 1] += dividend * scenario.probability
                if year_number == 10:
                    assert terminal is not None
                    terminal_flows.append((book + terminal) * scenario.probability)
            terminal_value = projections[-1].terminal_value_per_share
            assert terminal_value is not None
            fair_value = (
                base.current_book_value_per_share
                + discounted_ri
                + terminal_value / ((Decimal(1) + scenario.cost_of_equity) ** 10)
            )
            results.append(
                ArchetypeScenarioCalculation(
                    scenario=scenario.scenario,
                    probability=scenario.probability,
                    fair_value_per_share=fair_value,
                    terminal_value_per_share=terminal_value,
                    projections=tuple(projections),
                )
            )
            hurdle += scenario.cost_of_equity * scenario.probability
        return _normalized(
            scenarios=tuple(results),
            hurdle=hurdle,
            expected_flows=expected_flows,
            terminal_flows=[sum(terminal_flows, Decimal(0))],
            model_currency=model_currency,
            market_price=market_price,
        )
