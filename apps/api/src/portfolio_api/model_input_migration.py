"""Assess and import parity-proven legacy model inputs as native model revisions.

The adapter reads cached OOXML values from the reviewed workbook snapshot,
recalculates with existing engines, and never evaluates workbook formulas or writes
legacy output values to native state. Import still requires exact canonical identity
and current application price validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain import schemas, services
from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelMigrationAssessment,
    FinancialModelMigrationStatus,
    FinancialModelOutput,
    FinancialModelRevision,
    FinancialModelType,
    Listing,
    Security,
)
from portfolio_api.financial_model_archetypes import (
    ArchetypeCalculation,
    calculate_owner_cash_flow,
)
from portfolio_api.financial_models import (
    DcfCalculation,
    MarketPriceInput,
    calculate_ufcf_dcf,
)
from portfolio_api.legacy_import import Workbook
from portfolio_api.model_migration_inventory import DEFAULT_OUTPUT as INVENTORY_PATH
from portfolio_api.model_migration_inventory import DEFAULT_WORKBOOK as DEFAULT_WORKBOOK
from portfolio_api.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REPORT = (
    REPOSITORY_ROOT / "docs" / "reconciliation" / "native-model-input-import-2026-10-06.json"
)
MAPPING_VERSION = "legacy-native-input-v1"
PORTFOLIO_DCF_MAPPING_VERSION = "portfolio-ufcf-dcf-2026-10-06-v1"
TOLERANCE = Decimal("0.0000001")
SCENARIO_ORDER = ("BEAR", "BASE", "BULL")
SCENARIO_COLUMNS = {
    "BEAR": ("E", "F", "G", "H", "I"),
    "BASE": ("J", "K", "L", "M", "N"),
    "BULL": ("O", "P", "Q", "R", "S"),
}
TOST_SCENARIO_ROWS = {"BEAR": (37, 38), "BASE": (39, 40), "BULL": (41, 42)}
TOST_VALUATION_ROWS = {"BEAR": 46, "BASE": 47, "BULL": 48}
PORTFOLIO_DCF_LISTING_REQUIREMENTS: dict[str, tuple[str, str, str, str]] = {
    # Values are cross-checked against the current operational coverage receipt;
    # the database identity query remains the final import guard.
    "P-ADYEN": ("Adyen", "ADYEN", "AMS", "EUR"),
    "P-AMD": ("AMD", "AMD", "NASDAQ", "USD"),
    "P-AMZN": ("Amazon", "AMZN", "NASDAQ", "USD"),
    "P-ASML": ("ASML Holding", "ASML", "AMS", "EUR"),
    "P-BKNG": ("Booking Holdings", "BKNG", "NASDAQ", "USD"),
    "P-CELH": ("Celsius Holdings", "CELH", "NASDAQ", "USD"),
    "P-HIMS": ("Hims & Hers", "HIMS", "NYSE", "USD"),
    "P-ISRG": ("Intuitive Surgical", "ISRG", "NASDAQ", "USD"),
    "P-MA": ("Mastercard", "MA", "NYSE", "USD"),
    "P-MELI": ("MercadoLibre", "MELI", "NASDAQ", "USD"),
    "P-MSCI": ("MSCI Inc.", "MSCI", "NYSE", "USD"),
    "P-MSFT": ("Microsoft", "MSFT", "NASDAQ", "USD"),
    # The workbook links NVO to CPH:NOVO-B and explicitly labels DKK. This
    # mapping is only safe while that exact listing remains the canonical one.
    "P-NVO": ("Novo Nordisk", "NOVO-B", "CPH", "DKK"),
    # These three tabs are title-classified as owner-cash models in the first
    # inventory. Their explicit operating rows are UFCF DCFs, so they are tested
    # against the existing DCF method and never forced into the owner-cash method.
    "P-CPRT": ("Copart", "CPRT", "NASDAQ", "USD"),
    "P-MORN": ("Morningstar", "MORN", "NASDAQ", "USD"),
    "P-UBER": ("Uber Technologies", "UBER", "NYSE", "USD"),
}
PORTFOLIO_DCF_MODEL_KEYS = tuple(PORTFOLIO_DCF_LISTING_REQUIREMENTS)
EXPECTED_MODEL_KEYS = ("P-GOOGL", *PORTFOLIO_DCF_MODEL_KEYS, "W-TOST")
PARITY_PROVEN_MODEL_KEYS = ("P-GOOGL", "P-ISRG", "P-MA", "P-CPRT", "P-UBER", "W-TOST")


@dataclass(frozen=True)
class MappedModel:
    model_key: str
    company_name: str
    ticker: str
    venue: str
    security_type: str
    model_type: FinancialModelType
    model_name: str
    model_currency: str
    values: schemas.FinancialModelRevisionCreate | schemas.OwnerCashFlowRevisionCreate
    source_price: Decimal
    source_price_cell: str
    input_cell_map: dict[str, str]
    source_references: dict[str, str]
    units: str
    legacy_return_semantics: str
    legacy_return_basis: str
    expected_irr_comparability: str
    mapping_version: str = MAPPING_VERSION


def _cell(workbook: Workbook, sheet: str, address: str) -> str:
    cell = workbook.cell(sheet, address)
    if cell.value is None or not cell.value.strip():
        raise ValueError(f"Required cached source value is missing at {sheet}!{address}")
    return cell.value.strip()


def _decimal(workbook: Workbook, sheet: str, address: str) -> Decimal:
    raw = _cell(workbook, sheet, address)
    try:
        value = Decimal(raw.removesuffix("%")) / (100 if raw.endswith("%") else 1)
    except InvalidOperation as error:
        raise ValueError(
            f"Expected a finite decimal at {sheet}!{address}; found {raw!r}"
        ) from error
    if not value.is_finite():
        raise ValueError(f"Expected a finite decimal at {sheet}!{address}; found {raw!r}")
    return value


def _column_number(column: str) -> int:
    value = 0
    for character in column:
        value = value * 26 + ord(character.upper()) - 64
    return value


def _column_name(value: int) -> str:
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(remainder + 65) + result
    return result


def _next_column(column: str, offset: int) -> str:
    return _column_name(_column_number(column) + offset)


def _model_currency(workbook: Workbook, model_key: str, source_cell: str) -> str:
    value = _cell(workbook, model_key, source_cell).upper()
    match = re.search(r"\b([A-Z]{3})\b", value)
    if match is None:
        raise ValueError(f"Model currency is not explicit at {model_key}!{source_cell}")
    return match.group(1)


def _source_cell_evidence(workbook: Workbook, model_key: str, address: str) -> str:
    cell = workbook.cell(model_key, address)
    return f"{model_key}!{address}; cached_value={cell.value!r}; formula={cell.formula!r}"


def _revision_metadata(
    workbook: Workbook,
    model_key: str,
    accepted_at: datetime,
    mapping_version: str = MAPPING_VERSION,
) -> dict[str, object]:
    return {
        "base_revision_id": None,
        "source_revision_id": f"legacy:{workbook.sha256}:{model_key}:{mapping_version}",
        "actor": "IMPORT",
        "source": (
            f"reference/workbook/{workbook.path.name}#{model_key}; "
            f"sha256={workbook.sha256}; source effective date unavailable"
        ),
        "rationale": (
            "Imported mapped assumptions from the frozen legacy model tab. "
            "The workbook does not record a trustworthy effective date."
        ),
        # This is the acceptance time, not a reconstructed workbook effective date.
        "effective_at": accepted_at,
    }


def _map_googl(workbook: Workbook, accepted_at: datetime) -> MappedModel:
    key = "P-GOOGL"
    cells: dict[str, str] = {
        "base.base_revenue": "B17",
        "base.base_ebit_margin": "B18",
        "base.base_tax_rate": "B19",
        "base.base_da_to_revenue": "B20",
        "base.base_capex_to_revenue": "B21",
        "base.base_nwc_to_revenue": "B22",
        "base.net_cash_debt": "B23",
        "base.diluted_shares": "B24",
        "scenarios.BEAR.probability": "AO4",
        "scenarios.BASE.probability": "AO5",
        "scenarios.BULL.probability": "AO6",
        "scenarios.BEAR.terminal_growth": "B205",
        "scenarios.BASE.terminal_growth": "C205",
        "scenarios.BULL.terminal_growth": "D205",
        "scenarios.BEAR.year10_ufcf_growth": "E24:I24",
        "scenarios.BASE.year10_ufcf_growth": "J24:N24",
        "scenarios.BULL.year10_ufcf_growth": "O24:S24",
        "model_currency": "B15",
        "source_price_for_parity_only": "B4",
    }
    base = {
        name: _decimal(workbook, key, address)
        for name, address in {
            "base_revenue": "B17",
            "base_ebit_margin": "B18",
            "base_tax_rate": "B19",
            "base_da_to_revenue": "B20",
            "base_capex_to_revenue": "B21",
            "base_nwc_to_revenue": "B22",
            "net_cash_debt": "B23",
            "diluted_shares": "B24",
        }.items()
    }
    currency = _model_currency(workbook, key, "B15")
    if currency != "USD":
        raise ValueError(f"Unexpected P-GOOGL model currency {currency}; expected USD")

    scenarios: list[dict[str, object]] = []
    probability_rows = {"BEAR": "AO4", "BASE": "AO5", "BULL": "AO6"}
    growth_targets = {"BEAR": "E24", "BASE": "J24", "BULL": "O24"}
    for scenario in SCENARIO_ORDER:
        start_column = SCENARIO_COLUMNS[scenario][0]
        years = []
        for year, column in enumerate(SCENARIO_COLUMNS[scenario], start=1):
            years.append(
                {
                    "forecast_year": year,
                    "revenue_growth": _decimal(workbook, key, f"{column}16"),
                    "ebit_margin": _decimal(workbook, key, f"{column}17"),
                    "da_to_revenue": _decimal(workbook, key, f"{column}18"),
                    "capex_to_revenue": _decimal(workbook, key, f"{column}19"),
                    "nwc_to_revenue": _decimal(workbook, key, f"{column}20"),
                    "tax_rate": _decimal(workbook, key, f"{column}21"),
                    "discount_rate": _decimal(workbook, key, f"{column}22"),
                }
            )
        terminal_cells = {
            "BEAR": "B205",
            "BASE": "C205",
            "BULL": "D205",
        }
        first_target = growth_targets[scenario]
        target_row = 24
        target_cells = [f"{_next_column(start_column, offset)}{target_row}" for offset in range(5)]
        targets = {_decimal(workbook, key, address) for address in target_cells}
        if len(targets) != 1:
            raise ValueError(f"{key} {scenario} Y10 UFCF growth target differs across years")
        cells[f"scenarios.{scenario}.years"] = (
            f"{SCENARIO_COLUMNS[scenario][0]}16:{SCENARIO_COLUMNS[scenario][-1]}22"
        )
        scenarios.append(
            {
                "scenario": scenario,
                "probability": _decimal(workbook, key, probability_rows[scenario]),
                "terminal_growth": _decimal(workbook, key, terminal_cells[scenario]),
                "year10_ufcf_growth": _decimal(workbook, key, first_target),
                "rationale": (
                    f"Imported legacy {scenario.title()} assumptions from {key}!"
                    f"{SCENARIO_COLUMNS[scenario][0]}16:{SCENARIO_COLUMNS[scenario][-1]}24."
                ),
                "years": years,
            }
        )
        cells[f"scenarios.{scenario}.rationale"] = "source labels and mapped assumption range"

    values = schemas.FinancialModelRevisionCreate.model_validate(
        {**_revision_metadata(workbook, key, accepted_at), "base": base, "scenarios": scenarios}
    )
    return MappedModel(
        model_key=key,
        company_name="Alphabet",
        ticker="GOOGL",
        venue="NASDAQ",
        security_type="COMMON_STOCK",
        model_type=FinancialModelType.UFCF_DCF_10Y_FADE,
        model_name="Alphabet 10-Year Secular Growth Fade DCF",
        model_currency=currency,
        values=values,
        source_price=_decimal(workbook, key, "B4"),
        source_price_cell="B4",
        input_cell_map=cells,
        source_references={"company_source": _cell(workbook, key, "B12")},
        units=(
            "Revenue, enterprise cash flows, and net cash/debt are USD billions; "
            "shares are billions; "
            "valuation and price are USD per GOOGL share."
        ),
        legacy_return_semantics=(
            "P-GOOGL legacy Expected Cash-Flow IRR is an enterprise UFCF / terminal-value IRR "
            "against implied enterprise cost. It is retained for legacy parity and is not the "
            "canonical shareholder-distribution IRR definition."
        ),
        legacy_return_basis="ENTERPRISE_UFCF_TERMINAL_VALUE_VS_IMPLIED_ENTERPRISE_COST",
        expected_irr_comparability="NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR",
    )


def _map_portfolio_dcf(workbook: Workbook, model_key: str, accepted_at: datetime) -> MappedModel:
    """Map a reviewed active Portfolio tab into the existing UFCF DCF schema.

    The source cells are mapped explicitly and every candidate still has to pass
    the same per-tab projections, normalized outputs, and return-stream checks.
    """
    try:
        company_name, ticker, venue, expected_currency = PORTFOLIO_DCF_LISTING_REQUIREMENTS[
            model_key
        ]
    except KeyError as error:
        raise ValueError(f"No reviewed exact listing mapping exists for {model_key}") from error

    currency = _model_currency(workbook, model_key, "B15")
    if currency != expected_currency:
        raise ValueError(
            f"{model_key} source currency {currency} does not match the reviewed "
            f"{venue}:{ticker} listing currency {expected_currency}"
        )

    base_cells = {
        "base_revenue": "B17",
        "base_ebit_margin": "B18",
        "base_tax_rate": "B19",
        "base_da_to_revenue": "B20",
        "base_capex_to_revenue": "B21",
        "base_nwc_to_revenue": "B22",
        "net_cash_debt": "B23",
        "diluted_shares": "B24",
    }
    base = {name: _decimal(workbook, model_key, address) for name, address in base_cells.items()}
    probability_cells = {"BEAR": "AO4", "BASE": "AO5", "BULL": "AO6"}
    terminal_growth_cells = {"BEAR": "B205", "BASE": "C205", "BULL": "D205"}
    scenario_years: dict[str, tuple[str, ...]] = {
        "BEAR": SCENARIO_COLUMNS["BEAR"],
        "BASE": SCENARIO_COLUMNS["BASE"],
        "BULL": SCENARIO_COLUMNS["BULL"],
    }
    scenarios: list[dict[str, object]] = []
    input_cells: dict[str, str] = {
        **{f"base.{name}": address for name, address in base_cells.items()},
        **{f"scenarios.{name}.probability": address for name, address in probability_cells.items()},
        **{
            f"scenarios.{name}.terminal_growth": address
            for name, address in terminal_growth_cells.items()
        },
        "model_currency": "B15",
        "source_price_for_parity_only": "B4",
    }

    for scenario in SCENARIO_ORDER:
        columns = scenario_years[scenario]
        if model_key in {"P-CPRT", "P-MORN", "P-UBER"}:
            # These owner-titled tabs define the fade target as terminal growth.
            # The workbook's B210:D210 formulas are the Year 10 UFCF growth
            # endpoints; row 24 does not carry all three scenario targets.
            target_cells = [f"{scenario_column}210" for scenario_column in "BCD"]
            scenario_index = SCENARIO_ORDER.index(scenario)
            target_cells = [target_cells[scenario_index]]
        else:
            target_cells = [f"{column}24" for column in columns]
        target_values = {_decimal(workbook, model_key, address) for address in target_cells}
        if len(target_values) != 1:
            raise ValueError(
                f"{model_key} {scenario} Year 10 UFCF growth target differs across "
                "forecast columns; the native schema accepts one explicit target"
            )
        years = [
            {
                "forecast_year": year,
                "revenue_growth": _decimal(workbook, model_key, f"{column}16"),
                "ebit_margin": _decimal(workbook, model_key, f"{column}17"),
                "da_to_revenue": _decimal(workbook, model_key, f"{column}18"),
                "capex_to_revenue": _decimal(workbook, model_key, f"{column}19"),
                "nwc_to_revenue": _decimal(workbook, model_key, f"{column}20"),
                "tax_rate": _decimal(workbook, model_key, f"{column}21"),
                "discount_rate": _decimal(workbook, model_key, f"{column}22"),
            }
            for year, column in enumerate(columns, start=1)
        ]
        first_target = target_cells[0]
        input_cells[f"scenarios.{scenario}.years"] = f"{columns[0]}16:{columns[-1]}22"
        input_cells[f"scenarios.{scenario}.year10_ufcf_growth"] = ",".join(target_cells)
        input_cells[f"scenarios.{scenario}.rationale"] = "source scenario labels and mapped range"
        scenarios.append(
            {
                "scenario": scenario,
                "probability": _decimal(workbook, model_key, probability_cells[scenario]),
                "terminal_growth": _decimal(workbook, model_key, terminal_growth_cells[scenario]),
                "year10_ufcf_growth": _decimal(workbook, model_key, first_target),
                "rationale": (
                    f"Mapped the explicit {scenario.title()} operating and Year 10 growth "
                    f"assumptions from {model_key}; source cells are recorded in the receipt."
                ),
                "years": years,
            }
        )

    values = schemas.FinancialModelRevisionCreate.model_validate(
        {
            **_revision_metadata(workbook, model_key, accepted_at, PORTFOLIO_DCF_MAPPING_VERSION),
            "base": base,
            "scenarios": scenarios,
        }
    )
    owner_title_evidence = model_key in {"P-CPRT", "P-MORN", "P-UBER"}
    target_source_cells = (
        {"BEAR": "B210", "BASE": "C210", "BULL": "D210"}
        if owner_title_evidence
        else {"BEAR": "E24", "BASE": "J24", "BULL": "O24"}
    )
    source_references = {
        "company_source": _cell(workbook, model_key, "B12"),
        "source_tab_title": model_key,
        "valuation_formula": "; ".join(
            _source_cell_evidence(workbook, model_key, address)
            for address in ("L202", "M202", "N202")
        ),
        "expected_return_formula_or_published_value": _source_cell_evidence(
            workbook, model_key, "AA212"
        ),
        "source_price_for_parity_only": _source_cell_evidence(workbook, model_key, "B4"),
    }
    for scenario, address in target_source_cells.items():
        source_references[f"year10_growth_target.{scenario}"] = _source_cell_evidence(
            workbook, model_key, address
        )
    return MappedModel(
        model_key=model_key,
        company_name=company_name,
        ticker=ticker,
        venue=venue,
        security_type="COMMON_STOCK",
        model_type=FinancialModelType.UFCF_DCF_10Y_FADE,
        model_name=f"{company_name} 10-Year UFCF DCF",
        model_currency=currency,
        values=values,
        source_price=_decimal(workbook, model_key, "B4"),
        source_price_cell="B4",
        input_cell_map=input_cells,
        source_references=source_references,
        units=(
            f"Operating values, enterprise cash flows and net cash/debt are {currency} billions; "
            f"shares are billions; valuation and parity quote are {currency} "
            "per exact listing share."
        ),
        legacy_return_semantics=(
            (
                "The legacy tab title refers to owner cash, but its explicit operating rows and "
                "valuation formulas implement probability-weighted enterprise UFCF and terminal "
                "value against implied enterprise cost. It is therefore evaluated as the existing "
                "UFCF DCF method, not forced into the owner-cash-flow archetype. "
            )
            if owner_title_evidence
            else "The legacy Expected Cash-Flow IRR uses probability-weighted enterprise UFCF and "
            "terminal value against implied enterprise cost; it is not canonical shareholder-"
            "distribution IRR."
        )
        + " Preserve the source method label and do not silently treat it as canonical "
        "shareholder-distribution IRR.",
        legacy_return_basis="ENTERPRISE_UFCF_TERMINAL_VALUE_VS_IMPLIED_ENTERPRISE_COST",
        expected_irr_comparability="NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR",
        mapping_version=PORTFOLIO_DCF_MAPPING_VERSION,
    )


def _map_tost(workbook: Workbook, accepted_at: datetime) -> MappedModel:
    key = "W-TOST"
    currency = _model_currency(workbook, key, "C5")
    if currency != "USD":
        raise ValueError(f"Unexpected W-TOST model currency {currency}; expected USD")
    cells: dict[str, str] = {
        "base.base_revenue": "B5",
        "base.diluted_shares": "B8",
        "base.net_cash": "B17",
        "scenarios.BEAR.probability": "B46",
        "scenarios.BASE.probability": "B47",
        "scenarios.BULL.probability": "B48",
        "scenarios.BEAR.required_return": "M37",
        "scenarios.BASE.required_return": "M39",
        "scenarios.BULL.required_return": "M41",
        "scenarios.BEAR.terminal_growth": "N37",
        "scenarios.BASE.terminal_growth": "N39",
        "scenarios.BULL.terminal_growth": "N41",
        "model_currency": "C5",
        "source_price_for_parity_only": "B7",
    }
    base = {
        "base_revenue": _decimal(workbook, key, "B5"),
        "net_cash": _decimal(workbook, key, "B17"),
        "diluted_shares": _decimal(workbook, key, "B8"),
    }
    scenarios: list[dict[str, object]] = []
    probability_cells = {"BEAR": "B46", "BASE": "B47", "BULL": "B48"}
    for scenario in SCENARIO_ORDER:
        growth_row, margin_row = TOST_SCENARIO_ROWS[scenario]
        required_return = f"M{growth_row}"
        terminal_growth = f"N{growth_row}"
        years = []
        for year, source_column_number in enumerate(range(3, 13), start=1):
            column = _column_name(source_column_number)
            growth_cell = f"{column}{growth_row}"
            margin_cell = f"{column}{margin_row}"
            years.append(
                {
                    "forecast_year": year,
                    "revenue_growth": _decimal(workbook, key, growth_cell),
                    "owner_cash_flow_margin": _decimal(workbook, key, margin_cell),
                }
            )
        cells[f"scenarios.{scenario}.revenue_growth"] = f"C{growth_row}:L{growth_row}"
        cells[f"scenarios.{scenario}.owner_cash_flow_margin"] = f"C{margin_row}:L{margin_row}"
        scenarios.append(
            {
                "scenario": scenario,
                "probability": _decimal(workbook, key, probability_cells[scenario]),
                "required_return": _decimal(workbook, key, required_return),
                "terminal_growth": _decimal(workbook, key, terminal_growth),
                "rationale": (
                    f"Imported legacy {scenario.title()} assumptions from "
                    f"{key}!A{growth_row}:N{margin_row}."
                ),
                "years": years,
            }
        )
        cells[f"scenarios.{scenario}.rationale"] = f"A{growth_row}:N{margin_row}"

    values = schemas.OwnerCashFlowRevisionCreate.model_validate(
        {**_revision_metadata(workbook, key, accepted_at), "base": base, "scenarios": scenarios}
    )
    return MappedModel(
        model_key=key,
        company_name="Toast",
        ticker="TOST",
        venue="NYSE",
        security_type="COMMON_STOCK",
        model_type=FinancialModelType.OWNER_CASH_FLOW_10Y,
        model_name="Toast 10-Year Owner Cash-Flow Model",
        model_currency=currency,
        values=values,
        source_price=_decimal(workbook, key, "B7"),
        source_price_cell="B7",
        input_cell_map=cells,
        source_references={
            "base.base_revenue": _cell(workbook, key, "D5"),
            "base.diluted_shares": _cell(workbook, key, "D8"),
            "base.net_cash": _cell(workbook, key, "D17"),
        },
        units=(
            "Revenue, owner cash flow, and net cash are USD billions; diluted shares are "
            "billions; per-share values are USD."
        ),
        legacy_return_semantics=(
            "W-TOST Expected Cash-Flow IRR is calculated from one probability-weighted owner-cash "
            "stream and the legacy terminal-value convention. The source does not document "
            "owner cash flow as a guaranteed distribution. Preserve the source label and method."
        ),
        legacy_return_basis="PROBABILITY_WEIGHTED_OWNER_CASH_FLOW_AND_LEGACY_TERMINAL_VALUE",
        expected_irr_comparability="NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR",
    )


def map_supported_models(workbook: Workbook, accepted_at: datetime) -> list[MappedModel]:
    """Map only tabs with complete source parity; other candidates stay in the assessment report."""
    mappers = dict(_supported_model_mappers())
    return [mappers[key](workbook, accepted_at) for key in PARITY_PROVEN_MODEL_KEYS]


def _dcf_candidate_mapper(
    model_key: str,
) -> Callable[[Workbook, datetime], MappedModel]:
    def mapper(workbook: Workbook, accepted_at: datetime) -> MappedModel:
        return _map_portfolio_dcf(workbook, model_key, accepted_at)

    return mapper


def _supported_model_mappers() -> list[tuple[str, Callable[[Workbook, datetime], MappedModel]]]:
    return [
        ("P-GOOGL", _map_googl),
        *((model_key, _dcf_candidate_mapper(model_key)) for model_key in PORTFOLIO_DCF_MODEL_KEYS),
        ("W-TOST", _map_tost),
    ]


def _mapping_version_for(model_key: str) -> str:
    return (
        PORTFOLIO_DCF_MAPPING_VERSION
        if model_key in PORTFOLIO_DCF_LISTING_REQUIREMENTS
        else MAPPING_VERSION
    )


def _legacy_inventory_rows() -> dict[str, dict[str, Any]]:
    data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return {str(row["model_tab"]): row for row in data["models"]}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _input_digest(mapped: MappedModel) -> str:
    payload = mapped.values.model_dump(
        mode="json",
        exclude={
            "effective_at",
            "source_revision_id",
            "source",
            "rationale",
            "actor",
            "base_revision_id",
        },
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _source_price(mapped: MappedModel) -> MarketPriceInput:
    # Used only to test source methodology parity. No source-price observation with
    # an invented date is created or attached to an accepted application revision.
    return MarketPriceInput(
        observation_id=None,
        price=mapped.source_price,
        currency=mapped.model_currency,
        effective_at=None,
        freshness="FRESH",
    )


def _calculate(mapped: MappedModel) -> DcfCalculation | ArchetypeCalculation:
    if mapped.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        assert isinstance(mapped.values, schemas.FinancialModelRevisionCreate)
        return calculate_ufcf_dcf(
            mapped.values, model_currency=mapped.model_currency, market_price=_source_price(mapped)
        )
    assert isinstance(mapped.values, schemas.OwnerCashFlowRevisionCreate)
    return calculate_owner_cash_flow(
        mapped.values, model_currency=mapped.model_currency, market_price=_source_price(mapped)
    )


def _scenario_result(calculation: DcfCalculation | ArchetypeCalculation, scenario_name: str) -> Any:
    return next(row for row in calculation.scenarios if row.scenario.value == scenario_name)


def _check(
    *,
    field: str,
    source: str,
    actual: Decimal,
    expected: Decimal,
    tolerance: Decimal = TOLERANCE,
) -> dict[str, object]:
    difference = abs(actual - expected)
    return {
        "field": field,
        "source": source,
        "actual": str(actual),
        "expected": str(expected),
        "absolute_difference": str(difference),
        "tolerance": str(tolerance),
        "status": "PASS" if difference <= tolerance else "DATA_CHECK",
    }


def _annotate_parity_blockers(report: dict[str, Any], error: str | None = None) -> None:
    if report.get("status") == FinancialModelMigrationStatus.PARITY_PASS.value:
        report["blocking_categories"] = []
        report["blocking_summary"] = None
        return

    reason = error or ""
    failures = [
        comparison
        for group_name in ("projection_reconciliation", "output_reconciliation")
        for comparison in report.get(group_name, {}).get("comparisons", [])
        if comparison.get("status") != "PASS"
    ]
    fields = [str(item.get("field", "")) for item in failures]
    categories: list[str] = []
    summary: str
    if "Required cached source value is missing" in reason:
        categories.append("MISSING_SOURCE_DATA")
        summary = reason
    elif "base.base_capex_to_revenue" in reason and "greater than or equal to 0" in reason:
        categories.append("INVALID_SOURCE_ASSUMPTION")
        summary = (
            "The source capex-to-revenue assumption is negative and fails native input validation."
        )
    else:
        if any(f".year_{year}." in field for field in fields for year in range(6, 11)):
            categories.append("METHODOLOGY_MISMATCH")
        if any(field == "legacy_return_stream.period_0" for field in fields):
            categories.extend(("RETURN_NOT_COMPARABLE", "SHARE_BASIS_MISMATCH"))
        elif any(
            field in {"expected_cash_flow_irr", "expected_excess"}
            or field.startswith("legacy_return_stream.")
            for field in fields
        ):
            categories.append("RETURN_NOT_COMPARABLE")
        if any(
            field in {"bear_fv", "base_fv", "bull_fv", "weighted_fv", "weighted_upside"}
            for field in fields
        ):
            categories.append("DATA_CHECK")
        if not categories:
            categories.append("DATA_CHECK")
        categories = list(dict.fromkeys(categories))
        if "METHODOLOGY_MISMATCH" in categories:
            summary = "Year 6–10 source UFCF projections do not match the supported linear fade."
        elif "SHARE_BASIS_MISMATCH" in categories:
            summary = "The source return stream uses a different initial price/share basis."
        elif "RETURN_NOT_COMPARABLE" in categories:
            summary = (
                "The source Expected IRR/return stream does not reconcile to the "
                "supported DCF return stream."
            )
        else:
            summary = "One or more normalized source outputs exceed the existing parity tolerance."

    report["blocking_categories"] = categories
    report["blocking_summary"] = summary


def _reconcile_model(workbook: Workbook, mapped: MappedModel) -> dict[str, Any]:
    calculation = _calculate(mapped)
    sheet = mapped.model_key
    projections: list[dict[str, object]] = []
    outputs: list[dict[str, object]] = []

    for scenario_name in SCENARIO_ORDER:
        scenario = _scenario_result(calculation, scenario_name)
        if mapped.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
            projection_row = {"BEAR": 40, "BASE": 60, "BULL": 80}[scenario_name]
            tail_column = {"BEAR": "G", "BASE": "H", "BULL": "I"}[scenario_name]
            for year, projection in enumerate(scenario.projections, start=1):
                if year <= 5:
                    address = f"{_column_name(year + 2)}{projection_row}"
                    field = f"{scenario_name}.year_{year}.present_value_ufcf"
                    actual = projection.present_value_ufcf
                else:
                    address = f"{tail_column}{196 + year}"
                    field = f"{scenario_name}.year_{year}.unlevered_free_cash_flow"
                    actual = projection.unlevered_free_cash_flow
                projections.append(
                    _check(
                        field=field,
                        source=f"{sheet}!{address}",
                        actual=actual,
                        expected=_decimal(workbook, sheet, address),
                    )
                )
        else:
            assert mapped.model_type == FinancialModelType.OWNER_CASH_FLOW_10Y
            assert isinstance(mapped.values, schemas.OwnerCashFlowRevisionCreate)
            assert isinstance(scenario.projections[0].owner_cash_flow, Decimal)
            revenue_row = TOST_VALUATION_ROWS[scenario_name]
            growth_row, margin_row = TOST_SCENARIO_ROWS[scenario_name]
            for year, projection in enumerate(scenario.projections, start=1):
                column = _column_name(year + 2)
                source_revenue = _decimal(workbook, sheet, f"{column}{revenue_row}")
                source_margin = _decimal(workbook, sheet, f"{column}{margin_row}")
                source_cash_flow = source_revenue * source_margin
                source_per_share = source_cash_flow / mapped.values.base.diluted_shares
                source_required_return = _decimal(workbook, sheet, f"M{growth_row}")
                source_pv_per_share = source_per_share / (
                    (Decimal(1) + source_required_return) ** year
                )
                projections.extend(
                    [
                        _check(
                            field=f"{scenario_name}.year_{year}.revenue",
                            source=f"{sheet}!{column}{revenue_row}",
                            actual=projection.revenue,
                            expected=source_revenue,
                        ),
                        _check(
                            field=f"{scenario_name}.year_{year}.owner_cash_flow",
                            source=f"{sheet}!{column}{revenue_row}*{column}{margin_row}",
                            actual=projection.owner_cash_flow,
                            expected=source_cash_flow,
                        ),
                        _check(
                            field=f"{scenario_name}.year_{year}.owner_cash_flow_per_share",
                            source=f"({sheet}!{column}{revenue_row}*{column}{margin_row})/{sheet}!B8",
                            actual=projection.owner_cash_flow_per_share,
                            expected=source_per_share,
                        ),
                        _check(
                            field=f"{scenario_name}.year_{year}.present_value_per_share",
                            source=f"owner CF per share/(1+{sheet}!M{growth_row})^{year}",
                            actual=projection.present_value_per_share,
                            expected=source_pv_per_share,
                        ),
                    ]
                )
                if year == 10:
                    source_terminal = (
                        source_per_share
                        * (Decimal(1) + _decimal(workbook, sheet, f"N{growth_row}"))
                        / (source_required_return - _decimal(workbook, sheet, f"N{growth_row}"))
                    )
                    projections.append(
                        _check(
                            field=f"{scenario_name}.year_10.terminal_value_per_share",
                            source=f"{sheet}!L{revenue_row}*L{margin_row} terminal formula",
                            actual=projection.terminal_value_per_share,
                            expected=source_terminal,
                        )
                    )

    output_cells: dict[str, str]
    if mapped.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        output_cells = {
            "bear_fv": "L202",
            "base_fv": "M202",
            "bull_fv": "N202",
            "bear_probability": "AO4",
            "base_probability": "AO5",
            "bull_probability": "AO6",
            "weighted_fv": "AO7",
            "weighted_upside": "AO8",
            "expected_cash_flow_irr": "AA212",
            "hurdle": "AB212",
            "expected_excess": "AC212",
        }
        source_cashflow_cells = [f"{_column_name(column)}212" for column in range(16, 27)]
    else:
        output_cells = {
            "bear_fv": "M46",
            "base_fv": "M47",
            "bull_fv": "M48",
            "bear_probability": "B46",
            "base_probability": "B47",
            "bull_probability": "B48",
            "weighted_fv": "B52",
            "weighted_upside": "B53",
            "expected_cash_flow_irr": "B55",
            "hurdle": "B54",
            "expected_excess": "B56",
        }
        source_cashflow_cells = [f"{_column_name(column)}61" for column in range(2, 13)]

    result_fields: dict[str, Decimal] = {
        "bear_fv": calculation.bear_fv,
        "base_fv": calculation.base_fv,
        "bull_fv": calculation.bull_fv,
        "bear_probability": calculation.bear_probability,
        "base_probability": calculation.base_probability,
        "bull_probability": calculation.bull_probability,
        "weighted_fv": calculation.weighted_fv,
        "weighted_upside": cast(Decimal, calculation.weighted_upside),
        "expected_cash_flow_irr": cast(Decimal, calculation.expected_cash_flow_irr),
        "hurdle": calculation.hurdle,
        "expected_excess": cast(Decimal, calculation.expected_excess),
    }
    for field, address in output_cells.items():
        outputs.append(
            _check(
                field=field,
                source=f"{sheet}!{address}",
                actual=result_fields[field],
                expected=_decimal(workbook, sheet, address),
            )
        )

    # Compare the full return stream as well as its reported IRR. The initial
    # workbook quote is used for source parity only and has no effective timestamp.
    if mapped.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        assert isinstance(mapped.values, schemas.FinancialModelRevisionCreate)
        flows: list[Decimal] = []
        for year in range(1, 11):
            flows.append(
                sum(
                    (
                        next(
                            p.unlevered_free_cash_flow
                            for p in _scenario_result(calculation, name).projections
                            if p.forecast_year == year
                        )
                        * _scenario_result(calculation, name).probability
                        for name in SCENARIO_ORDER
                    ),
                    Decimal(0),
                )
            )
        flows[-1] += sum(
            (
                _scenario_result(calculation, name).terminal_value
                * _scenario_result(calculation, name).probability
                for name in SCENARIO_ORDER
            ),
            Decimal(0),
        )
        initial_cost = -(
            mapped.source_price * mapped.values.base.diluted_shares
            - mapped.values.base.net_cash_debt
        )
    else:
        assert isinstance(mapped.values, schemas.OwnerCashFlowRevisionCreate)
        flows = [Decimal(0) for _ in range(10)]
        terminal_total = Decimal(0)
        for name in SCENARIO_ORDER:
            scenario = _scenario_result(calculation, name)
            for projection in scenario.projections:
                flows[projection.forecast_year - 1] += (
                    projection.owner_cash_flow_per_share * scenario.probability
                )
                if projection.forecast_year == 10:
                    assert projection.terminal_value_per_share is not None
                    terminal_total += projection.terminal_value_per_share * scenario.probability
                    terminal_total += (
                        mapped.values.base.net_cash
                        / mapped.values.base.diluted_shares
                        * scenario.probability
                    )
        flows[-1] += terminal_total
        initial_cost = -mapped.source_price
    return_stream = [initial_cost, *flows]
    for index, (source_cell, actual) in enumerate(
        zip(source_cashflow_cells, return_stream, strict=True)
    ):
        outputs.append(
            _check(
                field=f"legacy_return_stream.period_{index}",
                source=f"{sheet}!{source_cell}",
                actual=actual,
                expected=_decimal(workbook, sheet, source_cell),
                tolerance=Decimal("0.000001") if mapped.model_key == "P-GOOGL" else TOLERANCE,
            )
        )

    all_checks = [*projections, *outputs]
    failed = [item for item in all_checks if item["status"] != "PASS"]
    return {
        "calculation": calculation,
        "projection_reconciliation": {
            "compared": len(projections),
            "passed": sum(item["status"] == "PASS" for item in projections),
            "status": "PASS"
            if all(item["status"] == "PASS" for item in projections)
            else "DATA_CHECK",
            "comparisons": projections,
        },
        "output_reconciliation": {
            "compared": len(outputs),
            "passed": sum(item["status"] == "PASS" for item in outputs),
            "status": "PASS" if all(item["status"] == "PASS" for item in outputs) else "DATA_CHECK",
            "comparisons": outputs,
        },
        "status": "PARITY_PASS" if not failed else "DATA_CHECK",
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _identity(session: Session, mapped: MappedModel) -> tuple[Company, Listing]:
    rows = session.execute(
        select(Company, Listing, Security)
        .join(Security, Security.company_id == Company.id)
        .join(Listing, Listing.security_id == Security.id)
        .where(
            Company.name == mapped.company_name,
            Company.is_demo.is_(False),
            Listing.ticker == mapped.ticker,
            Listing.venue == mapped.venue,
            Listing.currency == mapped.model_currency,
            Security.security_type == mapped.security_type,
            Security.is_demo.is_(False),
            Listing.is_demo.is_(False),
        )
    ).all()
    if len(rows) != 1:
        raise ValueError(
            f"Exact non-demo identity/listing match required for {mapped.model_key}: "
            f"{mapped.company_name} / {mapped.venue}:{mapped.ticker} / {mapped.model_currency}; "
            f"found {len(rows)}"
        )
    company, listing, _security = rows[0]
    return company, listing


def _source_price_report(mapped: MappedModel) -> dict[str, object]:
    return {
        "value": str(mapped.source_price),
        "currency": mapped.model_currency,
        "source_cell": f"{mapped.model_key}!{mapped.source_price_cell}",
        "effective_at": None,
        "use": "PARITY_ONLY_NOT_STORED_AS_MARKET_DATA",
    }


def _base_report(
    workbook: Workbook, mapped: MappedModel, inventory: dict[str, Any]
) -> dict[str, Any]:
    reconciliation = _reconcile_model(workbook, mapped)
    calculation = reconciliation.pop("calculation")
    return_comparisons = [
        comparison
        for comparison in reconciliation["output_reconciliation"]["comparisons"]
        if comparison["field"] in {"expected_cash_flow_irr", "expected_excess"}
        or str(comparison["field"]).startswith("legacy_return_stream.")
    ]
    return_parity = (
        "PARITY_PASS"
        if return_comparisons and all(item["status"] == "PASS" for item in return_comparisons)
        else "DATA_CHECK"
    )
    report: dict[str, Any] = {
        "model_key": mapped.model_key,
        "company_name": mapped.company_name,
        "canonical_ticker": mapped.ticker,
        "lifecycle": inventory.get("lifecycle"),
        "model_type": mapped.model_type.value,
        "methodology_family": inventory.get("methodology_family"),
        "native_methodology": mapped.model_type.value,
        "model_currency": mapped.model_currency,
        "listing_requirement": {
            "ticker": mapped.ticker,
            "venue": mapped.venue,
            "currency": mapped.model_currency,
            "security_type": mapped.security_type,
        },
        "units": mapped.units,
        "source": {
            "workbook": f"reference/workbook/{workbook.path.name}",
            "workbook_sha256": workbook.sha256,
            "tab": mapped.model_key,
            "effective_date": None,
            "effective_date_note": "No trustworthy workbook effective date is recorded.",
        },
        "input_mapping": {
            "status": "COMPLETE",
            "input_digest": _input_digest(mapped),
            "source_cells": mapped.input_cell_map,
            "source_references": mapped.source_references,
        },
        "source_price_for_parity": _source_price_report(mapped),
        "legacy_return_semantics": mapped.legacy_return_semantics,
        "expected_irr": {
            "source_label": "Expected Cash-Flow IRR",
            "source_return_basis": mapped.legacy_return_basis,
            "native_method_return_parity": return_parity,
            "canonical_shareholder_irr_comparability": mapped.expected_irr_comparability,
            "legacy_semantics": mapped.legacy_return_semantics,
            "reinterpreted_as_canonical_shareholder_irr": False,
        },
        "projection_reconciliation": reconciliation["projection_reconciliation"],
        "output_reconciliation": reconciliation["output_reconciliation"],
        "status": reconciliation["status"],
        "current_application_recalculation": None,
        "accepted_model": None,
    }
    # An untyped private calculation object is intentionally kept out of JSON;
    # consumers get only the explicit source comparisons and persisted outputs.
    del calculation
    return report


def _existing_assessment(
    session: Session, mapped: MappedModel, workbook: Workbook
) -> FinancialModelMigrationAssessment | None:
    return session.scalar(
        select(FinancialModelMigrationAssessment).where(
            FinancialModelMigrationAssessment.source_model_key == mapped.model_key,
            FinancialModelMigrationAssessment.source_workbook_sha256 == workbook.sha256,
            FinancialModelMigrationAssessment.mapping_version == mapped.mapping_version,
        )
    )


def _existing_model(
    session: Session, company_id: UUID, listing_id: UUID, mapped: MappedModel
) -> FinancialModel | None:
    return session.scalar(
        select(FinancialModel)
        .where(
            FinancialModel.company_id == company_id,
            FinancialModel.valuation_listing_id == listing_id,
            FinancialModel.model_type == mapped.model_type,
        )
        .with_for_update()
    )


def _current_application_state(session: Session, model: FinancialModel) -> dict[str, object]:
    current = session.get(FinancialModelRevision, model.current_revision_id)
    if current is None:
        return {"status": "DATA_CHECK", "reason": "Model has no current accepted revision."}
    output = session.scalar(
        select(FinancialModelOutput).where(FinancialModelOutput.revision_id == current.id)
    )
    if output is None:
        return {
            "status": "DATA_CHECK",
            "reason": "Accepted revision has no stored calculation output.",
        }
    return {
        "status": output.status,
        "price_status": output.price_status,
        "price": _json_safe(output.current_price),
        "price_effective_at": _json_safe(output.price_effective_at),
        "weighted_upside": _json_safe(output.weighted_upside),
        "expected_cash_flow_irr": _json_safe(output.expected_cash_flow_irr),
        "expected_excess": _json_safe(output.expected_excess),
        "unavailable_reason": output.price_unavailable_reason or output.irr_unavailable_reason,
    }


def _create_native_model(
    session: Session, company_id: UUID, listing_id: UUID, mapped: MappedModel
) -> tuple[FinancialModel, FinancialModelRevision]:
    if mapped.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        assert isinstance(mapped.values, schemas.FinancialModelRevisionCreate)
        create = schemas.FinancialModelCreate(
            model_type="UFCF_DCF_10Y_FADE",
            model_name=mapped.model_name,
            valuation_listing_id=listing_id,
            model_currency=mapped.model_currency,
            source_model_key=mapped.model_key,
            initial_revision=mapped.values,
        )
        model = services.create_financial_model(session, company_id, create)
    else:
        assert isinstance(mapped.values, schemas.OwnerCashFlowRevisionCreate)
        create_owner = schemas.OwnerCashFlowModelCreate(
            model_name=mapped.model_name,
            valuation_listing_id=listing_id,
            model_currency=mapped.model_currency,
            source_model_key=mapped.model_key,
            initial_revision=mapped.values,
        )
        model = services.create_owner_cash_flow_model(session, company_id, create_owner)
    revision = session.get(FinancialModelRevision, model.current_revision_id)
    if revision is None:
        raise RuntimeError(f"Accepted revision was not created for {mapped.model_key}")
    return model, revision


def import_native_model_inputs(
    session: Session,
    workbook: Workbook,
    *,
    accepted_at: datetime,
    apply: bool,
) -> dict[str, Any]:
    if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
        raise ValueError("accepted_at must be timezone-aware")
    inventory_doc = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    if workbook.sha256 != inventory_doc["source"]["sha256"]:
        raise ValueError("Workbook hash differs from the model migration inventory source snapshot")
    inventory = _legacy_inventory_rows()
    results: list[dict[str, Any]] = []
    for model_key, mapper in _supported_model_mappers():
        try:
            mapped = mapper(workbook, accepted_at)
            row = inventory[model_key]
            report = _base_report(workbook, mapped, row)
        except (ValueError, KeyError) as error:
            result: dict[str, Any] = {
                "model_key": model_key,
                "status": FinancialModelMigrationStatus.PARTIAL_MAPPING.value,
                "reason": str(error),
                "mapping_version": _mapping_version_for(model_key),
                "accepted_model": None,
            }
            _annotate_parity_blockers(result, str(error))
            results.append(result)
            continue

        report["mapping_version"] = mapped.mapping_version
        _annotate_parity_blockers(report)
        if report["status"] != FinancialModelMigrationStatus.PARITY_PASS.value:
            results.append(report)
            continue

        try:
            company, listing = _identity(session, mapped)
        except ValueError as error:
            report["status"] = FinancialModelMigrationStatus.BLOCKED.value
            report["identity_blocker"] = str(error)
            results.append(report)
            continue

        report["identity"] = {
            "company_id": str(company.id),
            "company_name": company.name,
            "listing_id": str(listing.id),
            "ticker": listing.ticker,
            "venue": listing.venue,
            "currency": listing.currency,
        }
        assessment = _existing_assessment(session, mapped, workbook)
        if assessment is not None:
            if assessment.input_digest != report["input_mapping"]["input_digest"]:
                report["status"] = FinancialModelMigrationStatus.BLOCKED.value
                report["identity_blocker"] = (
                    "The import key already exists with a different input digest."
                )
                results.append(report)
                continue
            stored_report = cast(dict[str, Any], assessment.report)
            results.append({**stored_report, "apply_status": "ALREADY_IMPORTED"})
            continue

        source_revision_id = mapped.values.source_revision_id
        existing_model = _existing_model(session, company.id, listing.id, mapped)
        if existing_model is not None:
            existing_revision = session.scalar(
                select(FinancialModelRevision).where(
                    FinancialModelRevision.model_id == existing_model.id,
                    FinancialModelRevision.source_revision_id == source_revision_id,
                )
            )
            if existing_revision is None:
                report["status"] = FinancialModelMigrationStatus.BLOCKED.value
                report["identity_blocker"] = (
                    "A model already exists for this listing and method but does not carry "
                    "this immutable legacy source revision. It was left unchanged."
                )
                results.append(report)
                continue
            report["status"] = FinancialModelMigrationStatus.BLOCKED.value
            report["identity_blocker"] = (
                "The source revision exists without its migration assessment receipt; "
                "manual reconciliation is required before retry."
            )
            results.append(report)
            continue

        if not apply:
            report["apply_status"] = "DRY_RUN_READY"
            results.append(report)
            continue

        try:
            with session.begin_nested():
                model, revision = _create_native_model(session, company.id, listing.id, mapped)
                report["accepted_model"] = {
                    "model_id": str(model.id),
                    "revision_id": str(revision.id),
                    "revision_number": revision.revision_number,
                    "source_revision_id": revision.source_revision_id,
                    "effective_at": _json_safe(revision.effective_at),
                    "recorded_at": _json_safe(revision.recorded_at),
                }
                report["current_application_recalculation"] = _current_application_state(
                    session, model
                )
                receipt = FinancialModelMigrationAssessment(
                    model_id=model.id,
                    revision_id=revision.id,
                    source_model_key=mapped.model_key,
                    source_workbook_sha256=workbook.sha256,
                    mapping_version=mapped.mapping_version,
                    status=cast(str, report["status"]),
                    input_digest=cast(str, report["input_mapping"]["input_digest"]),
                    report=cast(dict[str, object], _json_safe(report)),
                )
                session.add(receipt)
                session.flush()
            report["apply_status"] = "IMPORTED"
            results.append(report)
        except (services.DomainError, ValueError) as error:
            report["status"] = FinancialModelMigrationStatus.BLOCKED.value
            report["identity_blocker"] = str(error)
            results.append(report)

    mapping_versions = sorted(
        {
            str(item.get("mapping_version", _mapping_version_for(str(item["model_key"]))))
            for item in results
        }
    )
    return {
        "report_version": "2.0.0",
        "mapping_version": mapping_versions[0] if len(mapping_versions) == 1 else "MIXED",
        "mapping_versions": mapping_versions,
        "mode": "APPLIED" if apply else "DRY_RUN",
        "workbook": f"reference/workbook/{workbook.path.name}",
        "workbook_sha256": workbook.sha256,
        "source_effective_date": None,
        "source_effective_date_note": "The workbook has no trustworthy effective date.",
        "run_at": _json_safe(accepted_at),
        "input_sets_imported": sum(item.get("apply_status") == "IMPORTED" for item in results),
        "input_sets_already_imported": sum(
            item.get("apply_status") == "ALREADY_IMPORTED" for item in results
        ),
        "status_counts": {
            status.value: sum(item.get("status") == status.value for item in results)
            for status in FinancialModelMigrationStatus
        },
        "models": results,
    }


def build_native_model_parity_report(
    workbook: Workbook, *, assessed_at: datetime
) -> dict[str, Any]:
    """Create a read-only source-parity receipt without querying application state."""
    if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
        raise ValueError("assessed_at must be timezone-aware")
    inventory_doc = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    if workbook.sha256 != inventory_doc["source"]["sha256"]:
        raise ValueError("Workbook hash differs from the model migration inventory source snapshot")
    inventory = _legacy_inventory_rows()
    results: list[dict[str, Any]] = []
    for model_key, mapper in _supported_model_mappers():
        try:
            mapped = mapper(workbook, assessed_at)
            report = _base_report(workbook, mapped, inventory[model_key])
            report["mapping_version"] = mapped.mapping_version
            _annotate_parity_blockers(report)
            report["application_identity_validation"] = "NOT_CHECKED_PARITY_ONLY"
            report["apply_status"] = "NOT_APPLIED"
            results.append(report)
        except (ValueError, KeyError) as error:
            result = {
                "model_key": model_key,
                "mapping_version": _mapping_version_for(model_key),
                "status": FinancialModelMigrationStatus.PARTIAL_MAPPING.value,
                "reason": str(error),
                "application_identity_validation": "NOT_CHECKED_PARITY_ONLY",
                "apply_status": "NOT_APPLIED",
                "accepted_model": None,
            }
            _annotate_parity_blockers(result, str(error))
            results.append(result)

    status_counts = {
        status.value: sum(item.get("status") == status.value for item in results)
        for status in FinancialModelMigrationStatus
    }
    mapping_versions = sorted({str(item["mapping_version"]) for item in results})
    blocking_category_counts: dict[str, int] = {}
    return_parity_counts: dict[str, int] = {}
    return_comparability_counts: dict[str, int] = {}
    for item in results:
        for category in item.get("blocking_categories", []):
            blocking_category_counts[category] = blocking_category_counts.get(category, 0) + 1
        expected_irr = item.get("expected_irr")
        if isinstance(expected_irr, dict):
            parity = str(expected_irr["native_method_return_parity"])
            comparability = str(expected_irr["canonical_shareholder_irr_comparability"])
            return_parity_counts[parity] = return_parity_counts.get(parity, 0) + 1
            return_comparability_counts[comparability] = (
                return_comparability_counts.get(comparability, 0) + 1
            )
    return {
        "report_version": "2.0.0",
        "mapping_version": mapping_versions[0] if len(mapping_versions) == 1 else "MIXED",
        "mapping_versions": mapping_versions,
        "mode": "PARITY_ONLY",
        "canonical_application_state": "NOT_QUERIED",
        "workbook": f"reference/workbook/{workbook.path.name}",
        "workbook_sha256": workbook.sha256,
        "source_effective_date": None,
        "source_effective_date_note": "The workbook has no trustworthy effective date.",
        "assessed_at": _json_safe(assessed_at),
        "input_sets_imported": 0,
        "input_sets_already_imported": 0,
        "parity_pass_model_keys": [
            str(item["model_key"])
            for item in results
            if item.get("status") == FinancialModelMigrationStatus.PARITY_PASS.value
        ],
        "status_counts": status_counts,
        "blocking_category_counts": blocking_category_counts,
        "expected_irr_native_method_parity_counts": dict(sorted(return_parity_counts.items())),
        "expected_irr_canonical_comparability_counts": dict(
            sorted(return_comparability_counts.items())
        ),
        "models": results,
    }


def load_source_workbook(path: Path = DEFAULT_WORKBOOK) -> Workbook:
    return Workbook.read(path, lambda name: name in EXPECTED_MODEL_KEYS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--apply", action="store_true", help="accept parity-passing model revisions"
    )
    parser.add_argument(
        "--parity-only",
        action="store_true",
        help="write source parity results without querying or changing application state",
    )
    args = parser.parse_args(argv)
    if args.parity_only and args.apply:
        parser.error("--parity-only cannot be combined with --apply")

    assessed_at = datetime.now(UTC)
    try:
        workbook = load_source_workbook(args.workbook)
        if args.parity_only:
            report = build_native_model_parity_report(workbook, assessed_at=assessed_at)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(
                f"Wrote parity-only native model report to {args.output}; "
                f"parity_pass={len(report['parity_pass_model_keys'])}, "
                "application identity and acceptance were not checked"
            )
            return 0
    except Exception as error:
        print(f"Native model input parity assessment failed: {error}", file=sys.stderr)
        return 2

    settings = Settings()
    engine = create_database_engine(settings)
    if engine is None:
        print(
            "Database is unavailable; configure DATABASE_URL before importing models.",
            file=sys.stderr,
        )
        return 2
    try:
        with Session(engine) as session, session.begin():
            report = import_native_model_inputs(
                session, workbook, accepted_at=assessed_at, apply=args.apply
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception as error:
        print(f"Native model input import failed: {error}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()

    print(
        f"Wrote {report['mode'].lower()} native model migration report to {args.output}; "
        f"imported={report['input_sets_imported']}, "
        f"already_imported={report['input_sets_already_imported']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
