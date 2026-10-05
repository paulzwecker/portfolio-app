"""Parity fixtures for heterogeneous workbook-native valuation methods."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from portfolio_api.domain.schemas import OwnerCashFlowInput, ResidualIncomeInput
from portfolio_api.financial_model_archetypes import (
    calculate_owner_cash_flow,
    calculate_residual_income,
)
from portfolio_api.financial_models import MarketPriceInput

FIXTURES = Path(__file__).parent / "fixtures"
TOLERANCE = Decimal("0.0000001")


def load_case(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    ("filename", "schema", "calculator", "currency"),
    [
        ("w_tost_owner_cash_flow_v1.json", OwnerCashFlowInput, calculate_owner_cash_flow, "USD"),
        ("w_hdfc_residual_income_v1.json", ResidualIncomeInput, calculate_residual_income, "INR"),
    ],
)
def test_workbook_archetype_outputs_reconcile(
    filename: str,
    schema: Any,
    calculator: Any,
    currency: str,
) -> None:
    fixture: dict[str, Any] = load_case(filename)
    revision = schema.model_validate(fixture["input"])
    price = fixture["market_price"]
    result = calculator(
        revision,
        model_currency=currency,
        market_price=MarketPriceInput(
            None, Decimal(price["price"]), price["currency"], None, "FRESH"
        ),
    )
    expected = fixture["expected"]
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
        assert abs(getattr(result, field) - Decimal(expected[field])) <= TOLERANCE, field
    assert result.status == "COMPLETE"


def test_owner_cash_flow_and_residual_income_leave_price_dependent_outputs_missing() -> None:
    tost = load_case("w_tost_owner_cash_flow_v1.json")
    hdfc = load_case("w_hdfc_residual_income_v1.json")
    cases: list[tuple[dict[str, Any], Any, Any, str]] = [
        (tost, OwnerCashFlowInput, calculate_owner_cash_flow, "USD"),
        (hdfc, ResidualIncomeInput, calculate_residual_income, "INR"),
    ]
    for fixture, schema, calculate, currency in cases:
        result = calculate(
            schema.model_validate(fixture["input"]),
            model_currency=currency,
            market_price=MarketPriceInput(None, None, currency, None, "NO_DATA"),
        )
        assert result.weighted_fv > 0
        assert result.weighted_upside is None
        assert result.expected_cash_flow_irr is None
        assert result.expected_excess is None
        assert result.status == "PARTIAL"
        assert result.price_status == "NO_DATA"


def test_residual_income_uses_explicit_equity_method_and_rejects_invalid_terminal_spread() -> None:
    fixture = load_case("w_hdfc_residual_income_v1.json")
    raw = fixture["input"]
    raw["scenarios"][1]["terminal_growth"] = "0.12"
    with pytest.raises(ValidationError, match="below cost of equity"):
        ResidualIncomeInput.model_validate(raw)


def test_owner_cash_flow_requires_all_ten_method_specific_margin_and_growth_years() -> None:
    fixture = load_case("w_tost_owner_cash_flow_v1.json")
    raw = fixture["input"]
    raw["scenarios"][0]["years"].pop()
    with pytest.raises(ValidationError):
        OwnerCashFlowInput.model_validate(raw)
