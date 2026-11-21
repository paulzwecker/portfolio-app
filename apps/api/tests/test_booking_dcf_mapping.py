"""Synthetic regression for Booking's *return* terminal convention.

No private workbook, quotes, company facts, or production credentials are used.
The real cached source parity is exercised separately in source_data tests.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from synthetic_financial_fixtures import dcf_fixture

from portfolio_api.domain.schemas import FinancialModelRevisionCreate
from portfolio_api.financial_models import DcfCalculation
from portfolio_api.legacy_import import Cell, Workbook
from portfolio_api.model_input_migration import (
    BOOKING_GORDON_RETURN_MAPPING_VERSION,
    _calculate,
    _map_portfolio_dcf,
)
from portfolio_api.return_semantics import UFCF_ENTERPRISE_HMODEL_IRR, UFCF_ENTERPRISE_IRR


def _synthetic_booking_workbook() -> Workbook:
    synthetic = dcf_fixture()
    inputs = synthetic["input"]
    base = inputs["base"]
    cells: dict[str, Cell] = {}

    def put(address: str, value: object) -> None:
        cells[address] = Cell(value=str(value))

    put("B15", "USD")
    put("B12", "https://example.org/fictional-source")
    put("B4", "20")
    for name, address in {
        "base_revenue": "B17",
        "base_ebit_margin": "B18",
        "base_tax_rate": "B19",
        "base_da_to_revenue": "B20",
        "base_capex_to_revenue": "B21",
        "base_nwc_to_revenue": "B22",
        "net_cash_debt": "B23",
        "diluted_shares": "B24",
    }.items():
        put(address, base[name])

    for scenario, columns, probability, growth in zip(
        inputs["scenarios"],
        ("EFGHI", "JKLMN", "OPQRS"),
        ("AO4", "AO5", "AO6"),
        ("B205", "C205", "D205"),
        strict=True,
    ):
        put(probability, scenario["probability"])
        put(growth, scenario["terminal_growth"])
        for col, year in zip(columns, scenario["years"], strict=True):
            for field, row in {
                "revenue_growth": 16,
                "ebit_margin": 17,
                "da_to_revenue": 18,
                "capex_to_revenue": 19,
                "nwc_to_revenue": 20,
                "tax_rate": 21,
                "discount_rate": 22,
            }.items():
                put(f"{col}{row}", year[field])
            put(f"{col}24", scenario["year10_ufcf_growth"])

    for address in ("AA200", "AA201", "AA202"):
        cells[address] = Cell(value="1", formula="synthetic Y10 UFCF + Gordon terminal, no premium")
    return Workbook(
        path=Path("fictional_booking_model.xlsx"),
        sha256="a" * 64,
        sheets={"P-BKNG": cells},
    )


def test_booking_uses_existing_gordon_return_without_changing_dcf_fair_value() -> None:
    model = _map_portfolio_dcf(
        _synthetic_booking_workbook(), "P-BKNG", datetime(2026, 11, 20, tzinfo=UTC)
    )
    assert isinstance(model.values, FinancialModelRevisionCreate)
    assert model.mapping_version == BOOKING_GORDON_RETURN_MAPPING_VERSION
    assert model.return_methodology_code == UFCF_ENTERPRISE_HMODEL_IRR
    assert model.legacy_return_basis == (
        "ENTERPRISE_UFCF_HMODEL_GORDON_TERMINAL_VS_IMPLIED_ENTERPRISE_COST"
    )
    assert "linear UFCF growth fade" in model.legacy_return_semantics
    assert all(scenario.tail_ufcf_growth is None for scenario in model.values.scenarios)
    assert model.input_cell_map["scenarios.BASE.years"] == "J16:N22"
    assert "formula=" in model.source_references["legacy_return_terminal.BASE"]
    assert "P-BKNG!B125;" in model.source_references["alternative_5y_gordon.BEAR"]
    assert "P-BKNG!B160;" in model.source_references["alternative_5y_gordon.BASE"]
    assert "P-BKNG!B195;" in model.source_references["alternative_5y_gordon.BULL"]

    corrected = _calculate(model)
    old_method = _calculate(replace(model, return_methodology_code=UFCF_ENTERPRISE_IRR))
    assert isinstance(corrected, DcfCalculation)
    assert isinstance(old_method, DcfCalculation)
    assert corrected.weighted_fv == old_method.weighted_fv
    assert corrected.bear_fv == old_method.bear_fv
    assert corrected.base_fv == old_method.base_fv
    assert corrected.bull_fv == old_method.bull_fv
    assert corrected.expected_cash_flow_irr != old_method.expected_cash_flow_irr
    assert corrected.expected_excess != old_method.expected_excess
    assert (
        corrected.scenarios[1].return_terminal_value < old_method.scenarios[1].return_terminal_value
    )


def test_booking_mapping_version_differs_from_existing_portfolio_dcf_cohort() -> None:
    model = _map_portfolio_dcf(
        _synthetic_booking_workbook(), "P-BKNG", datetime(2026, 11, 20, tzinfo=UTC)
    )
    assert model.mapping_version != "portfolio-ufcf-dcf-2026-10-06-v1"
    assert "2026-11-20" in model.mapping_version
