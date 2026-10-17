"""Regression checks for the one accepted native valuation methodology."""

import json
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from portfolio_api.domain.schemas import FinancialModelRevisionCreate
from portfolio_api.financial_models import MarketPriceInput, _irr, calculate_ufcf_dcf

FIXTURE = Path(__file__).parent / "fixtures" / "p_googl_ufcf_dcf_v1.json"


@pytest.fixture
def parity_case() -> tuple[dict[str, object], FinancialModelRevisionCreate]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    revision = FinancialModelRevisionCreate.model_validate(fixture["input"])
    return fixture, revision


def reference_price(fixture: dict[str, object]) -> MarketPriceInput:
    record = fixture["market_price"]
    assert isinstance(record, dict)
    return MarketPriceInput(
        observation_id=None,
        price=Decimal(str(record["price"])),
        currency=str(record["currency"]),
        effective_at=None,
        freshness="FRESH",
    )


def test_p_googl_ufcf_dcf_reconciles_cached_scenarios_and_normalized_outputs(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    fixture, revision = parity_case
    result = calculate_ufcf_dcf(
        revision, model_currency="USD", market_price=reference_price(fixture)
    )
    expected = fixture["expected"]
    assert isinstance(expected, dict)
    for field in (
        "bear_fv",
        "base_fv",
        "bull_fv",
        "weighted_fv",
        "weighted_upside",
        "expected_cash_flow_irr",
        "hurdle",
        "expected_excess",
    ):
        actual = getattr(result, field)
        assert actual is not None
        assert abs(actual - Decimal(str(expected[field]))) <= Decimal("0.0000001")
    bear = result.scenarios[0]
    base = result.scenarios[1]
    bull = result.scenarios[2]
    assert abs(
        bear.projections[0].unlevered_free_cash_flow - Decimal(str(expected["bear_y1_ufcf"]))
    ) <= Decimal("0.0000001")
    assert abs(
        base.projections[4].unlevered_free_cash_flow - Decimal(str(expected["base_y5_ufcf"]))
    ) <= Decimal("0.0000001")
    assert abs(
        bull.projections[9].unlevered_free_cash_flow - Decimal(str(expected["bull_y10_ufcf"]))
    ) <= Decimal("0.0000001")
    assert result.status == "COMPLETE"


def test_price_and_currency_gaps_leave_market_dependent_outputs_null(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    fixture, revision = parity_case
    no_price = calculate_ufcf_dcf(
        revision,
        model_currency="USD",
        market_price=MarketPriceInput(None, None, "USD", None, "NO_DATA"),
    )
    assert no_price.weighted_fv > 0
    assert no_price.weighted_upside is None
    assert no_price.expected_cash_flow_irr is None
    assert no_price.expected_excess is None
    assert no_price.status == "PARTIAL"
    assert no_price.price_unavailable_reason == "No listing price observation is available."

    mismatched_currency = calculate_ufcf_dcf(
        revision,
        model_currency="USD",
        market_price=MarketPriceInput(None, Decimal("300"), "EUR", None, "FRESH"),
    )
    assert mismatched_currency.weighted_fv > 0
    assert mismatched_currency.weighted_upside is None
    assert mismatched_currency.expected_cash_flow_irr is None
    assert mismatched_currency.price_status == "CURRENCY_MISMATCH"

    unknown_currency = calculate_ufcf_dcf(
        revision,
        model_currency="USD",
        market_price=MarketPriceInput(None, Decimal("300"), None, None, "FRESH"),
    )
    assert unknown_currency.weighted_upside is None
    assert unknown_currency.expected_cash_flow_irr is None
    assert unknown_currency.price_status == "CURRENCY_UNKNOWN"


def test_years_six_to_ten_only_claim_the_legacy_ufcf_growth_fade(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    fixture, revision = parity_case
    result = calculate_ufcf_dcf(
        revision, model_currency="USD", market_price=reference_price(fixture)
    )
    for scenario in result.scenarios:
        assert all(
            item.revenue is None and item.ebit is None and item.nopat is None and item.capex is None
            for item in scenario.projections[5:]
        )
        assert scenario.projections[9].terminal_value is not None


def test_explicit_ufcf_tail_uses_each_supplied_growth_rate(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    fixture, revision = parity_case
    raw = revision.model_dump(mode="json")
    expected_rates: dict[str, list[str]] = {}
    for scenario in raw["scenarios"]:
        endpoint = scenario["year10_ufcf_growth"]
        rates = ["0.11", "0.09", "0.07", "0.06", str(endpoint)]
        scenario["tail_ufcf_growth"] = [
            {"forecast_year": year, "ufcf_growth": rate}
            for year, rate in zip(range(6, 11), rates, strict=True)
        ]
        expected_rates[scenario["scenario"]] = rates

    explicit = FinancialModelRevisionCreate.model_validate(raw)
    result = calculate_ufcf_dcf(
        explicit,
        model_currency="USD",
        market_price=reference_price(fixture),
    )
    for scenario in result.scenarios:
        expected = [Decimal(value) for value in expected_rates[scenario.scenario.value]]
        actual = scenario.projections[5:]
        assert [item.revenue_growth for item in actual] == expected
        previous = scenario.projections[4].unlevered_free_cash_flow
        with localcontext() as context:
            context.prec = 38
            for projection, growth in zip(actual, expected, strict=True):
                assert projection.unlevered_free_cash_flow == previous * (Decimal(1) + growth)
                previous = projection.unlevered_free_cash_flow


def test_explicit_tail_uses_distinct_h_model_terminal_for_expected_irr(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    fixture, revision = parity_case
    raw = revision.model_dump(mode="json")
    for scenario in raw["scenarios"]:
        endpoint = scenario["year10_ufcf_growth"]
        scenario["tail_ufcf_growth"] = [
            {"forecast_year": year, "ufcf_growth": str(endpoint)} for year in range(6, 11)
        ]
    explicit = FinancialModelRevisionCreate.model_validate(raw)
    result = calculate_ufcf_dcf(
        explicit,
        model_currency="USD",
        market_price=reference_price(fixture),
        return_methodology_code="UFCF_ENTERPRISE_HMODEL_IRR",
    )
    for scenario in result.scenarios:
        scenario_input = next(
            item for item in explicit.scenarios if item.scenario == scenario.scenario
        )
        last_ufcf = scenario.projections[-1].unlevered_free_cash_flow
        spread = scenario.projections[-1].discount_rate - scenario_input.terminal_growth
        with localcontext() as context:
            context.prec = 38
            expected_terminal = last_ufcf * (Decimal(1) + scenario_input.terminal_growth) / spread
        assert scenario.return_terminal_value == expected_terminal
        assert scenario.terminal_value != scenario.return_terminal_value


def test_explicit_ufcf_tail_requires_five_rates_and_matching_terminal_endpoint(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    _, revision = parity_case
    raw = revision.model_dump(mode="json")

    incomplete = json.loads(json.dumps(raw))
    incomplete["scenarios"][0]["tail_ufcf_growth"] = [{"forecast_year": 6, "ufcf_growth": "0.1"}]
    with pytest.raises(ValidationError, match="exactly years 6 through 10"):
        FinancialModelRevisionCreate.model_validate(incomplete)

    inconsistent_endpoint = json.loads(json.dumps(raw))
    inconsistent_endpoint["scenarios"][0]["tail_ufcf_growth"] = [
        {"forecast_year": year, "ufcf_growth": "0.1" if year < 10 else "0.2"}
        for year in range(6, 11)
    ]
    with pytest.raises(ValidationError, match="match the terminal growth endpoint"):
        FinancialModelRevisionCreate.model_validate(inconsistent_endpoint)


def test_revision_rejects_bad_probability_sums_years_and_terminal_spreads(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    _, revision = parity_case
    raw = revision.model_dump(mode="json")

    probability_change = json.loads(json.dumps(raw))
    probability_change["scenarios"][0]["probability"] = "0.2"
    with pytest.raises(ValidationError, match="probabilities must sum exactly"):
        FinancialModelRevisionCreate.model_validate(probability_change)

    missing_year = json.loads(json.dumps(raw))
    missing_year["scenarios"][0]["years"].pop()
    with pytest.raises(ValidationError):
        FinancialModelRevisionCreate.model_validate(missing_year)

    invalid_terminal = json.loads(json.dumps(raw))
    invalid_terminal["scenarios"][1]["terminal_growth"] = "0.1"
    with pytest.raises(ValidationError, match="Terminal growth"):
        FinancialModelRevisionCreate.model_validate(invalid_terminal)


def test_financial_model_decimals_reject_binary_floats(
    parity_case: tuple[dict[str, object], FinancialModelRevisionCreate],
) -> None:
    _, revision = parity_case
    raw = revision.model_dump(mode="json")
    raw["base"]["base_revenue"] = 498.0
    with pytest.raises(ValidationError):
        FinancialModelRevisionCreate.model_validate(raw)


def test_irr_rejects_multiple_cashflow_sign_changes() -> None:
    assert _irr([Decimal("-100"), Decimal("230"), Decimal("-132")]) is None
