"""Deterministic calculation for the explicitly supported legacy UFCF DCF method."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from portfolio_api.domain.models import DcfScenario
from portfolio_api.domain.schemas import DcfCalculationInput

PriceState = Literal[
    "FRESH", "STALE", "QUALITY_CHECK", "NO_DATA", "CURRENCY_MISMATCH", "CURRENCY_UNKNOWN"
]


@dataclass(frozen=True)
class MarketPriceInput:
    observation_id: UUID | None
    price: Decimal | None
    currency: str | None
    effective_at: datetime | None
    freshness: Literal["FRESH", "STALE", "QUALITY_CHECK", "NO_DATA"]


@dataclass(frozen=True)
class DcfProjectionCalculation:
    scenario: DcfScenario
    forecast_year: int
    revenue: Decimal | None
    ebit: Decimal | None
    nopat: Decimal | None
    depreciation_amortization: Decimal | None
    capex: Decimal | None
    net_working_capital: Decimal | None
    change_in_nwc: Decimal | None
    unlevered_free_cash_flow: Decimal
    revenue_growth: Decimal
    discount_rate: Decimal
    discount_factor: Decimal
    present_value_ufcf: Decimal
    terminal_value: Decimal | None


@dataclass(frozen=True)
class DcfScenarioCalculation:
    scenario: DcfScenario
    probability: Decimal
    fair_value_per_share: Decimal
    terminal_value: Decimal
    projections: tuple[DcfProjectionCalculation, ...]


@dataclass(frozen=True)
class DcfCalculation:
    scenarios: tuple[DcfScenarioCalculation, ...]
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
    price_effective_at: datetime | None


def _irr(cash_flows: list[Decimal]) -> Decimal | None:
    nonzero_signs = [1 if value > 0 else -1 for value in cash_flows if value != 0]
    if (
        len(nonzero_signs) < 2
        or sum(a != b for a, b in zip(nonzero_signs, nonzero_signs[1:], strict=False)) != 1
    ):
        return None

    def npv(rate: Decimal) -> Decimal:
        return sum(
            (value / ((Decimal(1) + rate) ** period) for period, value in enumerate(cash_flows)),
            Decimal(0),
        )

    low = Decimal("-0.999999999999")
    high = Decimal(1)
    low_value = npv(low)
    high_value = npv(high)
    while low_value * high_value > 0 and high < Decimal(1024):
        high *= 2
        high_value = npv(high)
    if low_value == 0:
        return low
    if high_value == 0:
        return high
    if low_value * high_value > 0:
        return None
    for _ in range(180):
        middle = (low + high) / 2
        middle_value = npv(middle)
        if middle_value == 0:
            return middle
        if low_value * middle_value > 0:
            low, low_value = middle, middle_value
        else:
            high, high_value = middle, middle_value
    return (low + high) / 2


def calculate_ufcf_dcf(
    revision: DcfCalculationInput,
    *,
    model_currency: str,
    market_price: MarketPriceInput,
) -> DcfCalculation:
    """Run the 5-year detailed / 5-year UFCF growth-fade model using exact decimals.

    Years 6-10 intentionally project only UFCF growth, as in the source methodology;
    they do not pretend to contain detailed revenue or operating-statement forecasts.
    """
    with localcontext() as context:
        context.prec = 38
        base = revision.base
        calculations: dict[DcfScenario, DcfScenarioCalculation] = {}
        for scenario in revision.scenarios:
            name = scenario.scenario
            ordered_years = sorted(scenario.years, key=lambda item: item.forecast_year)
            revenue = base.base_revenue
            prior_nwc = base.base_revenue * base.base_nwc_to_revenue
            detailed_cash_flows: list[Decimal] = []
            projections: list[DcfProjectionCalculation] = []
            prior_fcf: Decimal | None = None

            for year_input in ordered_years:
                forecast_year = year_input.forecast_year
                revenue *= Decimal(1) + year_input.revenue_growth
                ebit = revenue * year_input.ebit_margin
                nopat = ebit * (Decimal(1) - year_input.tax_rate)
                da = revenue * year_input.da_to_revenue
                capex = revenue * year_input.capex_to_revenue
                nwc = revenue * year_input.nwc_to_revenue
                change_in_nwc = nwc - prior_nwc
                ufcf = nopat + da - capex - change_in_nwc
                factor = Decimal(1) / ((Decimal(1) + year_input.discount_rate) ** forecast_year)
                pv = ufcf * factor
                detailed_cash_flows.append(ufcf)
                projections.append(
                    DcfProjectionCalculation(
                        scenario=name,
                        forecast_year=forecast_year,
                        revenue=revenue,
                        ebit=ebit,
                        nopat=nopat,
                        depreciation_amortization=da,
                        capex=capex,
                        net_working_capital=nwc,
                        change_in_nwc=change_in_nwc,
                        unlevered_free_cash_flow=ufcf,
                        revenue_growth=year_input.revenue_growth,
                        discount_rate=year_input.discount_rate,
                        discount_factor=factor,
                        present_value_ufcf=pv,
                        terminal_value=None,
                    )
                )
                prior_nwc = nwc
                prior_fcf = ufcf

            y4_ufcf, y5_ufcf = detailed_cash_flows[-2:]
            if y4_ufcf == 0:
                raise ValueError(f"{name} Year 4 UFCF is zero; the legacy fade rate is undefined")
            y5_growth = y5_ufcf / y4_ufcf - Decimal(1)
            final_discount_rate = ordered_years[-1].discount_rate
            previous_ufcf = prior_fcf
            last_ufcf = prior_fcf
            for forecast_year in range(6, 11):
                assert previous_ufcf is not None
                fade_fraction = Decimal(forecast_year - 5) / Decimal(5)
                growth = y5_growth + (scenario.year10_ufcf_growth - y5_growth) * fade_fraction
                ufcf = previous_ufcf * (Decimal(1) + growth)
                factor = Decimal(1) / ((Decimal(1) + final_discount_rate) ** forecast_year)
                projections.append(
                    DcfProjectionCalculation(
                        scenario=name,
                        forecast_year=forecast_year,
                        revenue=None,
                        ebit=None,
                        nopat=None,
                        depreciation_amortization=None,
                        capex=None,
                        net_working_capital=None,
                        change_in_nwc=None,
                        unlevered_free_cash_flow=ufcf,
                        revenue_growth=growth,
                        discount_rate=final_discount_rate,
                        discount_factor=factor,
                        present_value_ufcf=ufcf * factor,
                        terminal_value=None,
                    )
                )
                previous_ufcf = ufcf
                last_ufcf = ufcf

            if last_ufcf is None:
                raise ValueError(f"{name} did not produce a Year 10 UFCF")
            spread = final_discount_rate - scenario.terminal_growth
            if spread <= 0:
                raise ValueError(f"{name} terminal growth must remain below its discount rate")
            terminal_value = (
                last_ufcf * (Decimal(1) + scenario.terminal_growth) / spread
                + last_ufcf
                * Decimal("2.5")
                * (scenario.year10_ufcf_growth - scenario.terminal_growth)
                / spread
            )
            last = projections[-1]
            projections[-1] = DcfProjectionCalculation(
                **{**last.__dict__, "terminal_value": terminal_value}
            )
            terminal_pv = terminal_value / ((Decimal(1) + final_discount_rate) ** 10)
            enterprise_value = sum(item.present_value_ufcf for item in projections) + terminal_pv
            fair_value = (enterprise_value + base.net_cash_debt) / base.diluted_shares
            calculations[name] = DcfScenarioCalculation(
                scenario=name,
                probability=scenario.probability,
                fair_value_per_share=fair_value,
                terminal_value=terminal_value,
                projections=tuple(projections),
            )

        by_name = calculations
        order = (DcfScenario.BEAR, DcfScenario.BASE, DcfScenario.BULL)
        ordered = tuple(by_name[name] for name in order)
        weighted_fv = sum(
            (scenario.fair_value_per_share * scenario.probability for scenario in ordered),
            Decimal(0),
        )
        hurdle = sum(
            (
                scenario.probability
                * next(
                    item.discount_rate for item in scenario.projections if item.forecast_year == 5
                )
                for scenario in ordered
            ),
            Decimal(0),
        )

        price_status: PriceState = market_price.freshness
        unavailable_reason: str | None = None
        comparable_fresh_price = market_price.price is not None and market_price.price > 0
        if market_price.price is not None and market_price.currency is None:
            price_status = "CURRENCY_UNKNOWN"
            unavailable_reason = "The listing quote currency is unknown."
            comparable_fresh_price = False
        elif market_price.currency is not None and market_price.currency != model_currency:
            price_status = "CURRENCY_MISMATCH"
            unavailable_reason = (
                f"The {market_price.currency} listing quote is not converted to {model_currency}."
            )
            comparable_fresh_price = False
        elif price_status == "FRESH" and not comparable_fresh_price:
            price_status = "QUALITY_CHECK"
            unavailable_reason = "The latest fresh listing observation has no valid close."
        elif price_status != "FRESH":
            unavailable_reason = {
                "STALE": "The latest listing observation is stale.",
                "QUALITY_CHECK": "The latest listing observation did not pass data quality checks.",
                "NO_DATA": "No listing price observation is available.",
            }[price_status]

        weighted_upside = None
        expected_irr = None
        expected_excess = None
        irr_unavailable_reason = None
        if comparable_fresh_price and market_price.currency == model_currency:
            assert market_price.price is not None
            weighted_upside = weighted_fv / market_price.price - Decimal(1)
            enterprise_cost = market_price.price * base.diluted_shares - base.net_cash_debt
            if enterprise_cost <= 0:
                irr_unavailable_reason = "Current implied enterprise value is not positive."
            else:
                expected_flows: list[Decimal] = []
                for forecast_year in range(1, 11):
                    expected_flows.append(
                        sum(
                            (
                                next(
                                    projection.unlevered_free_cash_flow
                                    for projection in scenario.projections
                                    if projection.forecast_year == forecast_year
                                )
                                * scenario.probability
                                for scenario in ordered
                            ),
                            Decimal(0),
                        )
                    )
                expected_flows[-1] += sum(
                    (scenario.terminal_value * scenario.probability for scenario in ordered),
                    Decimal(0),
                )
                cash_flows = [-enterprise_cost, *expected_flows]
                expected_irr = _irr(cash_flows)
                if expected_irr is None:
                    irr_unavailable_reason = (
                        "Probability-weighted UFCF has no unique conventional IRR root."
                    )
                else:
                    expected_excess = expected_irr - hurdle
        else:
            irr_unavailable_reason = unavailable_reason or "A fresh comparable price is required."

        complete = weighted_upside is not None and expected_irr is not None
        return DcfCalculation(
            scenarios=ordered,
            bear_fv=by_name[DcfScenario.BEAR].fair_value_per_share,
            base_fv=by_name[DcfScenario.BASE].fair_value_per_share,
            bull_fv=by_name[DcfScenario.BULL].fair_value_per_share,
            bear_probability=by_name[DcfScenario.BEAR].probability,
            base_probability=by_name[DcfScenario.BASE].probability,
            bull_probability=by_name[DcfScenario.BULL].probability,
            weighted_fv=weighted_fv,
            weighted_upside=weighted_upside,
            expected_cash_flow_irr=expected_irr,
            hurdle=hurdle,
            expected_excess=expected_excess,
            status="COMPLETE" if complete else "PARTIAL",
            price_status=price_status,
            price_unavailable_reason=unavailable_reason,
            irr_unavailable_reason=irr_unavailable_reason,
            current_price=market_price.price,
            price_observation_id=market_price.observation_id,
            price_effective_at=market_price.effective_at,
        )
