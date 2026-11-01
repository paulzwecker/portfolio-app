from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from portfolio_api.legacy_import import Cell
from portfolio_api.model_outputs import (
    _decimal,
    _explicit_currency,
    _read_output_values,
    _timestamp,
)


def test_model_contract_numeric_values_preserve_zero_missing_and_percentage_units() -> None:
    assert _decimal("0") == Decimal(0)
    assert _decimal("12.5%") == Decimal("0.125")
    assert _decimal(None) is None
    assert _decimal("   ") is None
    assert _decimal("n/a") is None


def test_effective_time_requires_an_explicit_timezone() -> None:
    assert _timestamp("2026-10-05T12:30:00+02:00") == datetime(2026, 10, 5, 10, 30, tzinfo=UTC)
    assert _timestamp("2026-10-05T12:30:00") is None
    assert _timestamp("unknown") is None


def test_currency_is_read_only_from_an_explicit_currency_label() -> None:
    cells = {
        "A1": SimpleNamespace(value="Model Currency"),
        "B1": SimpleNamespace(value="USD"),
        "A2": SimpleNamespace(value="Current Price Currency"),
        "B2": SimpleNamespace(value="EUR"),
    }
    assert _explicit_currency(cells) == ("USD", "A1")
    assert _explicit_currency({"B1": SimpleNamespace(value="USD")}) == (None, None)


def test_empty_formula_cache_keeps_model_output_null_and_sets_data_check_issue() -> None:
    outputs, issues = _read_output_values(
        cells={"BA4": Cell(None, "n", "=B1*2")},
        coordinate=lambda row: f"BA{row}",
        source="P-SYN",
        validate_contract_labels=False,
        expected_labels={},
    )

    assert outputs["bear_fv"] is None
    assert issues == [
        {
            "field": "bear_fv",
            "reason": "Formula cache is empty; the output remains null and unavailable.",
            "raw_value": "",
            "source": "P-SYN!BA4",
        }
    ]
