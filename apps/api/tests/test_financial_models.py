"""Regression checks for the one accepted native valuation methodology."""

import json
from decimal import Decimal
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
