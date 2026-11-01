"""Versioned direct-Sheets package for the single P-GOOGL DCF proof of concept.

The module exports declared cells with the Google Sheets API, freezes typed cell
evidence privately, and replays it through the existing native model mapper and
DCF engine. It never evaluates formulas or reads XLSX calculation caches.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.bootstrap_preflight import (
    verify_database_preflight,
    verify_database_read_only_preflight,
)
from portfolio_api.database import create_database_engine
from portfolio_api.domain import schemas
from portfolio_api.domain.models import (
    FinancialModel,
    FinancialModelRevision,
    FinancialModelType,
)
from portfolio_api.legacy_import import Cell, Workbook
from portfolio_api.model_input_migration import (
    DEFAULT_WORKBOOK,
    MappedModel,
    _create_native_model,
    _identity,
    _input_digest,
    _map_googl,
    _reconcile_model,
)
from portfolio_api.settings import Settings
from portfolio_api.sheets_portfolio_vertical_slice import (
    SHEETS_API,
    SheetsPortfolioError,
    SheetsPortfolioReader,
    _sha256,
)
from portfolio_api.workbook_sources import SnapshotStore
from portfolio_api.workbook_value_validation import _cell_grid_index, _column_name, _column_number

PACKAGE_VERSION: Literal["financial-model-package-v1"] = "financial-model-package-v1"
PACKAGE_DIRECTORY = "financial-model-packages-v1"
PACKAGE_MODEL_KEY: Literal["P-GOOGL"] = "P-GOOGL"
__all__ = ["_input_digest", "_sha256"]
PACKAGE_IDENTITY = {
    "company_name": "Alphabet",
    "canonical_ticker": "GOOGL",
    "listing_ticker": "GOOGL",
    "listing_venue": "NASDAQ",
    "security_type": "COMMON_STOCK",
    "listing_currency": "USD",
    "model_currency": "USD",
    "model_type": "UFCF_DCF_10Y_FADE",
    "methodology_version": "ufcf-dcf-fade-v1",
    "return_methodology_code": "UFCF_ENTERPRISE_IRR",
    "economic_cash_flow_basis": ("ENTERPRISE_UFCF_TERMINAL_VALUE_VS_IMPLIED_ENTERPRISE_COST"),
    "return_perspective": "ENTERPRISE",
    "return_comparability": "NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR",
    "operating_value_unit": "USD_BILLIONS",
    "share_count_unit": "BILLIONS_OF_SHARES",
    "per_share_unit": "USD_PER_GOOGL_LISTING_SHARE",
}
_PACKAGE_FIELDS = (
    "spreadsheetId,sheets(properties(title),data(startRow,startColumn,"
    "rowData(values(userEnteredValue,effectiveValue,effectiveFormat(numberFormat(type,pattern))))))"
)
_STRUCTURE_FIELDS = (
    "spreadsheetId,properties(timeZone),sheets(properties(sheetId,title,"
    "gridProperties(rowCount,columnCount)))"
)
_RANGE_PATTERN = re.compile(r"^'P-GOOGL'!([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RUN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_MAX_PACKAGE_CALLS = 48
_MAX_PACKAGE_CELLS = 512
_REQUEST_SPACING_SECONDS = 0.12
MAX_PROBABILITY_SUM_RESIDUAL = Decimal("0.000000000000001")

# Every field read is either a documented native input, a legacy published output
# used by the approved parity contract, or evidence for the legacy return stream.
P_GOOGL_RANGES = (
    "'P-GOOGL'!B4:B4",
    "'P-GOOGL'!B12:B12",
    "'P-GOOGL'!B15:B15",
    "'P-GOOGL'!B17:B24",
    "'P-GOOGL'!E16:S22",
    "'P-GOOGL'!E24:S24",
    "'P-GOOGL'!B205:D205",
    "'P-GOOGL'!AO4:AO8",
    "'P-GOOGL'!L202:N202",
    "'P-GOOGL'!C40:G40",
    "'P-GOOGL'!C60:G60",
    "'P-GOOGL'!C80:G80",
    "'P-GOOGL'!G202:G206",
    "'P-GOOGL'!H202:H206",
    "'P-GOOGL'!I202:I206",
    "'P-GOOGL'!P212:Z212",
    "'P-GOOGL'!AA212:AC212",
)
P_GOOGL_PROBABILITY_RANGE = "'P-GOOGL'!AO4:AO6"
P_GOOGL_PROBABILITY_CELLS = {"BEAR": "AO4", "BASE": "AO5", "BULL": "AO6"}


class PackageError(ValueError):
    """Sanitized package capture, integrity, validation, or import error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class StrictPackageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PackageIdentity(StrictPackageModel):
    source_model_key: Literal["P-GOOGL"]
    company_name: Literal["Alphabet"]
    canonical_ticker: Literal["GOOGL"]
    listing_ticker: Literal["GOOGL"]
    listing_venue: Literal["NASDAQ"]
    security_type: Literal["COMMON_STOCK"]
    listing_currency: Literal["USD"]
    model_currency: Literal["USD"]
    model_type: Literal["UFCF_DCF_10Y_FADE"]
    methodology_version: Literal["ufcf-dcf-fade-v1"]
    return_methodology_code: Literal["UFCF_ENTERPRISE_IRR"]
    economic_cash_flow_basis: Literal["ENTERPRISE_UFCF_TERMINAL_VALUE_VS_IMPLIED_ENTERPRISE_COST"]
    return_perspective: Literal["ENTERPRISE"]
    return_comparability: Literal["NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR"]
    operating_value_unit: Literal["USD_BILLIONS"]
    share_count_unit: Literal["BILLIONS_OF_SHARES"]
    per_share_unit: Literal["USD_PER_GOOGL_LISTING_SHARE"]


class PackageScalar(StrictPackageModel):
    kind: Literal["NUMBER", "STRING", "BOOLEAN", "FORMULA", "ERROR"]
    value: str | bool
    detail: str | None = None

    @model_validator(mode="after")
    def scalar_kind_matches_value(self) -> PackageScalar:
        if self.kind in {"NUMBER", "ERROR", "FORMULA", "STRING"} and not isinstance(
            self.value, str
        ):
            raise ValueError("The source scalar value does not match its declared type")
        if self.kind == "NUMBER":
            try:
                number = Decimal(cast(str, self.value))
            except InvalidOperation as error:
                raise ValueError(
                    "A numeric source value must be an exact decimal string"
                ) from error
            if not number.is_finite():
                raise ValueError("A numeric source value must be finite")
        if self.kind == "BOOLEAN" and not isinstance(self.value, bool):
            raise ValueError("A boolean source value must be a JSON boolean")
        return self


class PackageCell(StrictPackageModel):
    state: Literal[
        "BLANK",
        "FORMULA_EMPTY_RESULT",
        "EMPTY_STRING",
        "NUMBER_ZERO",
        "NUMBER",
        "STRING",
        "BOOLEAN",
        "ERROR",
    ]
    transport_state: Literal[
        "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE",
        "EXPLICIT_EMPTY_CELL_DATA",
        "CELL_VALUE_DATA_PRESENT",
        "CELL_METADATA_ONLY",
    ]
    user_entered_value: PackageScalar | None
    effective_value: PackageScalar | None
    number_format_type: str | None
    number_format_pattern: str | None

    @model_validator(mode="after")
    def state_matches_values_and_transport(self) -> PackageCell:
        entered = self.user_entered_value
        effective = self.effective_value
        if self.transport_state == "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE":
            if any(
                value is not None
                for value in (
                    entered,
                    effective,
                    self.number_format_type,
                    self.number_format_pattern,
                )
            ):
                raise ValueError("An omitted source cell cannot contain returned data")
        elif self.transport_state == "EXPLICIT_EMPTY_CELL_DATA":
            if any(
                value is not None
                for value in (
                    entered,
                    effective,
                    self.number_format_type,
                    self.number_format_pattern,
                )
            ):
                raise ValueError("An explicit empty cell cannot contain returned data")
        elif self.transport_state == "CELL_METADATA_ONLY":
            if entered is not None or effective is not None:
                raise ValueError("A metadata-only cell cannot contain a cell value")
        elif entered is None and effective is None:
            raise ValueError("A value-present cell must contain an entered or effective value")

        if effective is None:
            expected_state = (
                "FORMULA_EMPTY_RESULT"
                if entered is not None and entered.kind == "FORMULA"
                else "BLANK"
            )
        elif effective.kind == "ERROR":
            expected_state = "ERROR"
        elif effective.kind == "NUMBER":
            expected_state = "NUMBER_ZERO" if Decimal(cast(str, effective.value)) == 0 else "NUMBER"
        elif effective.kind == "STRING":
            expected_state = (
                "FORMULA_EMPTY_RESULT"
                if effective.value == "" and entered is not None and entered.kind == "FORMULA"
                else "EMPTY_STRING"
                if effective.value == ""
                else "STRING"
            )
        else:
            expected_state = "BOOLEAN"
        if self.state != expected_state:
            raise ValueError("The source cell state does not match its typed value")
        return self


class PackageSource(StrictPackageModel):
    source_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: Literal["application/vnd.google-apps.spreadsheet"]
    modified_time: str = Field(min_length=1, max_length=80)
    drive_revision_id: str | None = Field(default=None, max_length=160)
    drive_checksum: str | None = Field(default=None, max_length=128)
    spreadsheet_time_zone: str | None = Field(default=None, max_length=100)
    sheet_id: int = Field(ge=0)
    sheet_title: Literal["P-GOOGL"]
    source_effective_at: None = None
    capture_semantics: Literal["observed-consistent-state-not-transactional-snapshot"]
    declared_ranges: tuple[str, ...]


class PackageRevision(StrictPackageModel):
    base_revision_id: UUID | None
    external_revision_id: str = Field(min_length=1, max_length=160)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_effective_at: None = None
    author_identity: None = None
    authored_at: None = None
    acceptance_state: Literal["PROPOSAL_NOT_ACCEPTED"]


class PublishedProjection(StrictPackageModel):
    scenario: Literal["BEAR", "BASE", "BULL"]
    forecast_year: int = Field(ge=1, le=10)
    metric: Literal["present_value_ufcf", "unlevered_free_cash_flow"]
    source_cell: str = Field(pattern=r"^[A-Z]{1,3}[0-9]+$")
    value: Decimal


class PublishedOutputs(StrictPackageModel):
    currency: Literal["USD"]
    parity_reference_price: Decimal
    parity_reference_price_cell: Literal["B4"]
    bear_fair_value_per_share: Decimal
    base_fair_value_per_share: Decimal
    bull_fair_value_per_share: Decimal
    weighted_fair_value_per_share: Decimal
    weighted_upside: Decimal
    expected_cash_flow_irr: Decimal
    hurdle: Decimal
    expected_excess: Decimal
    projections: tuple[PublishedProjection, ...] = Field(min_length=30, max_length=30)
    return_stream: tuple[Decimal, ...] = Field(min_length=11, max_length=11)


class ScenarioProbabilityValues(StrictPackageModel):
    bear: Decimal
    base: Decimal
    bull: Decimal


class ProbabilityNormalization(StrictPackageModel):
    method: Literal["BASE_RESIDUAL_V1"]
    maximum_absolute_sum_residual: Decimal
    original_sum: Decimal
    residual_to_one: Decimal
    original_probabilities: ScenarioProbabilityValues
    normalized_probabilities: ScenarioProbabilityValues
    adjusted_scenario: Literal["BASE"]
    base_adjustment: Decimal

    @model_validator(mode="after")
    def normalization_is_exact_and_bounded(self) -> ProbabilityNormalization:
        original = self.original_probabilities
        normalized = self.normalized_probabilities
        original_values = (original.bear, original.base, original.bull)
        normalized_values = (normalized.bear, normalized.base, normalized.bull)
        if any(value < 0 or value > 1 for value in (*original_values, *normalized_values)):
            raise ValueError("Scenario probabilities must be fractions between zero and one")
        with localcontext() as context:
            context.prec = 50
            computed_sum = sum(original_values, Decimal(0))
            normalized_sum = sum(normalized_values, Decimal(0))
            expected_residual = Decimal(1) - computed_sum
            expected_base = Decimal(1) - original.bear - original.bull
        if computed_sum != self.original_sum or expected_residual != self.residual_to_one:
            raise ValueError("The probability normalization evidence does not match its inputs")
        if abs(self.residual_to_one) > self.maximum_absolute_sum_residual:
            raise ValueError("The probability sum residual exceeds the normalization bound")
        if normalized_sum != Decimal(1):
            raise ValueError("Normalized scenario probabilities must sum exactly to one")
        if (
            normalized.bear != original.bear
            or normalized.bull != original.bull
            or normalized.base != expected_base
            or self.base_adjustment != normalized.base - original.base
        ):
            raise ValueError("The probability normalization must adjust only Base by the residual")
        return self


class FinancialModelPackage(StrictPackageModel):
    contract_version: Literal["financial-model-package-v1"]
    identity: PackageIdentity
    revision: PackageRevision
    inputs: schemas.DcfCalculationInput
    published_outputs: PublishedOutputs
    source: PackageSource
    source_cells: dict[str, PackageCell]
    probability_normalization: ProbabilityNormalization | None = None


@dataclass(frozen=True)
class StoredPackage:
    run_id: str
    payload_sha256: str
    manifest: dict[str, Any]
    package: FinancialModelPackage


@dataclass(frozen=True)
class ValidatedPackage:
    package: FinancialModelPackage
    payload_sha256: str
    mapped_model: MappedModel
    parity_report: dict[str, Any]


def _strict_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return _sha256(
        _strict_json({key: item for key, item in value.items() if key != "manifest_sha256"}).encode(
            "utf-8"
        )
    )


def _range_coordinates(a1_range: str) -> list[tuple[int, int, str]]:
    match = _RANGE_PATTERN.fullmatch(a1_range)
    if match is None:
        raise PackageError("PACKAGE_RANGE_INVALID", "The P-GOOGL range contract is invalid.")
    first_column, first_row, last_column, last_row = match.groups()
    start_column = _column_number(first_column)
    end_column = _column_number(last_column)
    start_row_number, end_row_number = int(first_row), int(last_row)
    if start_column > end_column or start_row_number > end_row_number:
        raise PackageError("PACKAGE_RANGE_INVALID", "The P-GOOGL range contract is invalid.")
    return [
        (row, column, f"{_column_name(column)}{row}")
        for row in range(start_row_number, end_row_number + 1)
        for column in range(start_column, end_column + 1)
    ]


def _expected_source_cells() -> tuple[dict[str, tuple[str, int, int]], ...]:
    result: list[dict[str, tuple[str, int, int]]] = []
    seen: set[str] = set()
    for a1_range in P_GOOGL_RANGES:
        coordinates = _range_coordinates(a1_range)
        for row, column, address in coordinates:
            if address in seen:
                raise RuntimeError("The declared P-GOOGL range contract has duplicate cells")
            seen.add(address)
            result.append({address: (a1_range, row, column)})
    if len(result) > _MAX_PACKAGE_CELLS:
        raise RuntimeError("The declared P-GOOGL package exceeds its cell bound")
    return tuple(result)


EXPECTED_PACKAGE_CELLS = frozenset(address for item in _expected_source_cells() for address in item)


def _atom(raw: Any, *, entered: bool) -> PackageScalar | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or len(raw) != 1:
        raise PackageError("PACKAGE_SOURCE_CELL_MALFORMED", "A source cell value is malformed.")
    kind, value = next(iter(raw.items()))
    if kind == "numberValue":
        if isinstance(value, (bool, float)) or not isinstance(value, (int, Decimal)):
            raise PackageError(
                "PACKAGE_SOURCE_CELL_MALFORMED", "A numeric source cell is not an exact decimal."
            )
        number = Decimal(value)
        if not number.is_finite():
            raise PackageError("PACKAGE_SOURCE_CELL_MALFORMED", "A source number is not finite.")
        return PackageScalar(kind="NUMBER", value=format(number, "f"))
    if kind == "stringValue" and isinstance(value, str):
        return PackageScalar(kind="STRING", value=value)
    if kind == "boolValue" and isinstance(value, bool):
        return PackageScalar(kind="BOOLEAN", value=value)
    if kind == "formulaValue" and entered and isinstance(value, str):
        return PackageScalar(kind="FORMULA", value=value)
    if kind == "errorValue" and not entered and isinstance(value, dict):
        error_type = value.get("type")
        message = value.get("message")
        if not isinstance(error_type, str) or not error_type:
            error_type = "UNKNOWN"
        return PackageScalar(
            kind="ERROR", value=error_type, detail=message if isinstance(message, str) else None
        )
    raise PackageError("PACKAGE_SOURCE_CELL_MALFORMED", "A source cell has an unsupported type.")


def _package_cell(raw: dict[str, Any], transport_state: str) -> PackageCell:
    entered = _atom(raw.get("userEnteredValue"), entered=True)
    effective = _atom(raw.get("effectiveValue"), entered=False)
    if effective is None:
        state = (
            "FORMULA_EMPTY_RESULT" if entered is not None and entered.kind == "FORMULA" else "BLANK"
        )
    elif effective.kind == "ERROR":
        state = "ERROR"
    elif effective.kind == "NUMBER":
        state = "NUMBER_ZERO" if Decimal(cast(str, effective.value)) == 0 else "NUMBER"
    elif effective.kind == "STRING":
        state = (
            "FORMULA_EMPTY_RESULT"
            if effective.value == "" and entered is not None and entered.kind == "FORMULA"
            else "EMPTY_STRING"
            if effective.value == ""
            else "STRING"
        )
    elif effective.kind == "BOOLEAN":
        state = "BOOLEAN"
    else:
        raise PackageError("PACKAGE_SOURCE_CELL_MALFORMED", "A cell effective value is invalid.")
    number_format = raw.get("effectiveFormat")
    number_format = number_format.get("numberFormat") if isinstance(number_format, dict) else None
    if number_format is not None and not isinstance(number_format, dict):
        raise PackageError("PACKAGE_SOURCE_CELL_MALFORMED", "A cell format is malformed.")
    format_type = number_format.get("type") if isinstance(number_format, dict) else None
    pattern = number_format.get("pattern") if isinstance(number_format, dict) else None
    if format_type is not None and not isinstance(format_type, str):
        raise PackageError("PACKAGE_SOURCE_CELL_MALFORMED", "A cell format type is malformed.")
    if pattern is not None and not isinstance(pattern, str):
        raise PackageError("PACKAGE_SOURCE_CELL_MALFORMED", "A cell format pattern is malformed.")
    return PackageCell(
        state=cast(Any, state),
        transport_state=cast(Any, transport_state),
        user_entered_value=entered,
        effective_value=effective,
        number_format_type=format_type,
        number_format_pattern=pattern,
    )


def _decimal_cell(source_cells: Mapping[str, PackageCell], address: str) -> Decimal:
    cell = source_cells.get(address)
    if cell is None:
        raise PackageError(
            "PACKAGE_REQUIRED_CELL_MISSING", f"Required P-GOOGL cell {address} is absent."
        )
    if cell.effective_value is None or cell.effective_value.kind != "NUMBER":
        raise PackageError(
            "PACKAGE_REQUIRED_CELL_UNAVAILABLE",
            f"Required numeric P-GOOGL source cell {address} is {cell.state}.",
        )
    try:
        value = Decimal(cast(str, cell.effective_value.value))
    except InvalidOperation as error:
        raise PackageError(
            "PACKAGE_REQUIRED_CELL_UNAVAILABLE",
            f"Required P-GOOGL source cell {address} is invalid.",
        ) from error
    if not value.is_finite():
        raise PackageError(
            "PACKAGE_REQUIRED_CELL_UNAVAILABLE",
            f"Required P-GOOGL source cell {address} is invalid.",
        )
    return value


def _outputs_from_cells(source_cells: Mapping[str, PackageCell]) -> PublishedOutputs:
    def number(address: str) -> Decimal:
        return _decimal_cell(source_cells, address)

    projections: list[PublishedProjection] = []
    projection_rows = {"BEAR": (40, "G"), "BASE": (60, "H"), "BULL": (80, "I")}
    for scenario, (projection_row, tail_column) in projection_rows.items():
        for forecast_year, column_number in enumerate(range(3, 8), start=1):
            address = f"{_column_name(column_number)}{projection_row}"
            projections.append(
                PublishedProjection(
                    scenario=cast(Literal["BEAR", "BASE", "BULL"], scenario),
                    forecast_year=forecast_year,
                    metric="present_value_ufcf",
                    source_cell=address,
                    value=number(address),
                )
            )
        for forecast_year, row_number in enumerate(range(202, 207), start=6):
            address = f"{tail_column}{row_number}"
            projections.append(
                PublishedProjection(
                    scenario=cast(Literal["BEAR", "BASE", "BULL"], scenario),
                    forecast_year=forecast_year,
                    metric="unlevered_free_cash_flow",
                    source_cell=address,
                    value=number(address),
                )
            )
    return PublishedOutputs(
        currency="USD",
        parity_reference_price=number("B4"),
        parity_reference_price_cell="B4",
        bear_fair_value_per_share=number("L202"),
        base_fair_value_per_share=number("M202"),
        bull_fair_value_per_share=number("N202"),
        weighted_fair_value_per_share=number("AO7"),
        weighted_upside=number("AO8"),
        expected_cash_flow_irr=number("AA212"),
        hurdle=number("AB212"),
        expected_excess=number("AC212"),
        projections=tuple(projections),
        return_stream=tuple(number(f"{_column_name(column)}212") for column in range(16, 27)),
    )


def _workbook_from_source_cells(
    source_cells: Mapping[str, PackageCell], payload_sha256: str
) -> Workbook:
    sheet: dict[str, Cell] = {}
    for address, item in source_cells.items():
        value = item.effective_value
        if value is None or value.kind == "ERROR":
            cell_value: str | None = None
            kind: str | None = None
        elif value.kind == "NUMBER":
            cell_value = cast(str, value.value)
            kind = "n"
        elif value.kind == "STRING":
            cell_value = cast(str, value.value)
            kind = "str"
        elif value.kind == "BOOLEAN":
            cell_value = "TRUE" if value.value else "FALSE"
            kind = "b"
        else:
            cell_value = None
            kind = None
        entered = item.user_entered_value
        sheet[address] = Cell(
            value=cell_value,
            kind=kind,
            formula=cast(str, entered.value)
            if entered is not None and entered.kind == "FORMULA"
            else None,
            number_format_type=item.number_format_type,
            number_format_code=item.number_format_pattern,
        )
    return Workbook(
        path=Path("google-sheets-P-GOOGL-package.json"),
        sha256=payload_sha256,
        sheets={PACKAGE_MODEL_KEY: sheet},
        source_name="direct-google-sheets-package",
    )


def _workbook_from_package(package: FinancialModelPackage, payload_sha256: str) -> Workbook:
    return _workbook_from_source_cells(package.source_cells, payload_sha256)


def _normalized_source_probabilities(
    source_cells: Mapping[str, PackageCell],
) -> tuple[dict[str, Decimal], ProbabilityNormalization | None]:
    original: dict[str, Decimal] = {}
    for scenario, address in P_GOOGL_PROBABILITY_CELLS.items():
        cell = source_cells.get(address)
        if cell is None:
            raise PackageError(
                "PACKAGE_PROBABILITY_MISSING", "A required P-GOOGL scenario probability is absent."
            )
        if cell.number_format_type != "PERCENT":
            raise PackageError(
                "PACKAGE_PROBABILITY_UNIT_UNSUPPORTED",
                "P-GOOGL scenario probabilities must use the declared percent display format.",
            )
        probability = _decimal_cell(source_cells, address)
        if probability < 0 or probability > 1:
            raise PackageError(
                "PACKAGE_PROBABILITY_INVALID",
                "P-GOOGL scenario probabilities must be fractions from zero through one.",
            )
        original[scenario] = probability

    with localcontext() as context:
        context.prec = 50
        original_sum = sum(original.values(), Decimal(0))
        residual_to_one = Decimal(1) - original_sum
        normalized = dict(original)
        if residual_to_one == 0:
            return normalized, None
        if abs(residual_to_one) > MAX_PROBABILITY_SUM_RESIDUAL:
            raise PackageError(
                "PACKAGE_PROBABILITY_SUM_INVALID",
                "P-GOOGL scenario probabilities do not sum to one within the serialization bound.",
            )
        normalized_base = Decimal(1) - original["BEAR"] - original["BULL"]
        if normalized_base < 0 or normalized_base > 1:
            raise PackageError(
                "PACKAGE_PROBABILITY_NORMALIZATION_INVALID",
                "The Base probability residual would fall outside zero through one.",
            )
        normalized["BASE"] = normalized_base
        normalization = ProbabilityNormalization(
            method="BASE_RESIDUAL_V1",
            maximum_absolute_sum_residual=MAX_PROBABILITY_SUM_RESIDUAL,
            original_sum=original_sum,
            residual_to_one=residual_to_one,
            original_probabilities=ScenarioProbabilityValues(
                bear=original["BEAR"], base=original["BASE"], bull=original["BULL"]
            ),
            normalized_probabilities=ScenarioProbabilityValues(
                bear=normalized["BEAR"], base=normalized["BASE"], bull=normalized["BULL"]
            ),
            adjusted_scenario="BASE",
            base_adjustment=normalized_base - original["BASE"],
        )
    return normalized, normalization


def _map_source_cells_to_model(
    source_cells: Mapping[str, PackageCell], effective_at: datetime, payload_sha256: str
) -> tuple[MappedModel, ProbabilityNormalization | None]:
    normalized_probabilities, normalization = _normalized_source_probabilities(source_cells)
    workbook = _workbook_from_source_cells(source_cells, payload_sha256)
    sheet = workbook.sheets[PACKAGE_MODEL_KEY]
    for scenario, address in P_GOOGL_PROBABILITY_CELLS.items():
        current = sheet[address]
        normalized_text = format(normalized_probabilities[scenario], "f")
        if current.value != normalized_text:
            sheet[address] = replace(current, value=normalized_text, kind="n")
    try:
        mapped = _map_googl(workbook, effective_at)
    except (ValueError, KeyError) as error:
        raise PackageError("PACKAGE_INPUT_MAPPING_INVALID", str(error)) from None
    return mapped, normalization


def _mapped_model(
    package: FinancialModelPackage, payload_sha256: str, effective_at: datetime
) -> MappedModel:
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise PackageError(
            "PACKAGE_ACCEPTANCE_TIME_INVALID", "Use a timezone-aware acceptance time."
        )
    mapped, normalization = _map_source_cells_to_model(
        package.source_cells, effective_at.astimezone(UTC), payload_sha256
    )
    if normalization != package.probability_normalization:
        raise PackageError(
            "PACKAGE_PROBABILITY_NORMALIZATION_MISMATCH",
            "The recorded probability normalization does not match the source cells.",
        )
    mapped_inputs = schemas.DcfCalculationInput.model_validate(
        {
            "base": mapped.values.base.model_dump(),
            "scenarios": [s.model_dump() for s in mapped.values.scenarios],
        }
    )
    if mapped_inputs.model_dump(mode="json") != package.inputs.model_dump(mode="json"):
        raise PackageError(
            "PACKAGE_INPUT_SOURCE_MISMATCH",
            "The normalized package inputs do not match their preserved source cells.",
        )
    if _input_digest(mapped) != package.revision.input_sha256:
        raise PackageError(
            "PACKAGE_INPUT_DIGEST_MISMATCH", "The package input digest does not match its inputs."
        )
    expected_revision_id = f"google-sheets:{PACKAGE_MODEL_KEY}:{package.revision.input_sha256}"
    if package.revision.external_revision_id != expected_revision_id:
        raise PackageError(
            "PACKAGE_REVISION_ID_INVALID", "The external model revision ID is not content-derived."
        )
    if package.revision.base_revision_id is not None:
        mapped = replace(
            mapped,
            values=mapped.values.model_copy(
                update={"base_revision_id": package.revision.base_revision_id}
            ),
        )
    source = (
        f"Google Sheets {PACKAGE_VERSION}; source_identity_sha256="
        f"{package.source.source_identity_sha256}; source_modified_at="
        f"{package.source.modified_time}; drive_revision_id="
        f"{package.source.drive_revision_id or 'unavailable'}; package_sha256={payload_sha256}; "
        "P-GOOGL; source effective date unavailable"
    )
    values = mapped.values.model_copy(
        update={
            "source_revision_id": package.revision.external_revision_id,
            "source": source,
            "rationale": (
                "Imported the source-authored P-GOOGL assumptions from a validated, "
                "versioned Google Sheets model package. The source effective date is unavailable."
            ),
            "base_revision_id": package.revision.base_revision_id,
            "effective_at": effective_at.astimezone(UTC),
            "actor": "IMPORT",
        }
    )
    return replace(mapped, values=values, mapping_version=PACKAGE_VERSION)


def _expected_identity() -> PackageIdentity:
    return PackageIdentity.model_validate(
        {"source_model_key": PACKAGE_MODEL_KEY, **PACKAGE_IDENTITY}
    )


def _validate_package_shape(package: FinancialModelPackage) -> None:
    if package.identity != _expected_identity():
        raise PackageError("PACKAGE_IDENTITY_INVALID", "The package identity is unsupported.")
    if set(package.source_cells) != EXPECTED_PACKAGE_CELLS:
        raise PackageError(
            "PACKAGE_CELL_SCOPE_INVALID",
            "The package does not contain exactly the declared P-GOOGL cells.",
        )
    if package.source.declared_ranges != P_GOOGL_RANGES:
        raise PackageError("PACKAGE_RANGE_SCOPE_INVALID", "The package range scope is unsupported.")
    if package.source.sheet_title != PACKAGE_MODEL_KEY or package.source.sheet_id < 0:
        raise PackageError("PACKAGE_SOURCE_IDENTITY_INVALID", "The package source tab is invalid.")
    expected_outputs = _outputs_from_cells(package.source_cells)
    if expected_outputs.model_dump(mode="json") != package.published_outputs.model_dump(
        mode="json"
    ):
        raise PackageError(
            "PACKAGE_OUTPUT_SOURCE_MISMATCH",
            "Published outputs do not match the preserved source cells.",
        )


def _compare_probability_inputs_with_parity_fixture(
    package: FinancialModelPackage,
) -> dict[str, Any]:
    fixture_workbook = Workbook.read(DEFAULT_WORKBOOK, lambda name: name == PACKAGE_MODEL_KEY)
    fixture_mapped = _map_googl(fixture_workbook, datetime(2000, 1, 1, tzinfo=UTC))
    if not isinstance(fixture_mapped.values, schemas.FinancialModelRevisionCreate):
        raise PackageError(
            "PACKAGE_PARITY_FIXTURE_INVALID", "The P-GOOGL parity fixture is not a DCF model."
        )
    fixture_probabilities = {
        scenario.scenario.value: scenario.probability
        for scenario in fixture_mapped.values.scenarios
    }
    fixture_formulas = {
        address: fixture_workbook.sheets[PACKAGE_MODEL_KEY][address].formula
        for address in P_GOOGL_PROBABILITY_CELLS.values()
    }
    comparison: dict[str, Any] = {}
    proposed_revision = False
    for scenario, address in P_GOOGL_PROBABILITY_CELLS.items():
        source_probability = _decimal_cell(package.source_cells, address)
        fixture_probability = fixture_probabilities[scenario]
        delta = source_probability - fixture_probability
        source_cell = package.source_cells[address]
        source_entered = source_cell.user_entered_value
        source_formula = (
            cast(str, source_entered.value)
            if source_entered is not None and source_entered.kind == "FORMULA"
            else None
        )
        fixture_formula = fixture_formulas[address]
        formula_matches = (
            source_formula is None
            and fixture_formula is None
            or source_formula is not None
            and fixture_formula is not None
            and source_formula.strip().removeprefix("=").strip()
            == fixture_formula.strip().removeprefix("=").strip()
        )
        if delta == 0:
            status = "EXACT_MATCH"
        elif abs(delta) <= MAX_PROBABILITY_SUM_RESIDUAL:
            status = "SERIALIZATION_SCALE_DIFFERENCE"
        else:
            status = "SOURCE_INPUT_DIFFERS_FROM_PARITY_FIXTURE"
            proposed_revision = True
        if not formula_matches:
            proposed_revision = True
        comparison[scenario] = {
            "source_cell": address,
            "source_minus_fixture": format(delta, "f"),
            "status": status,
            "formula_matches_parity_fixture": formula_matches,
        }
    return {
        "status": "PROPOSED_SOURCE_REVISION" if proposed_revision else "FIXTURE_INPUTS_MATCH",
        "normalization_applied": package.probability_normalization is not None,
        "normalization": (
            package.probability_normalization.model_dump(mode="json")
            if package.probability_normalization is not None
            else None
        ),
        "scenarios": comparison,
    }


def validate_financial_model_package(
    package: FinancialModelPackage, payload_sha256: str, *, validated_at: datetime | None = None
) -> ValidatedPackage:
    """Replay the package against the existing P-GOOGL mapper and numerical parity contract."""
    if not _HASH_PATTERN.fullmatch(payload_sha256):
        raise PackageError("PACKAGE_HASH_INVALID", "The package hash is invalid.")
    _validate_package_shape(package)
    timestamp = validated_at or datetime.now(UTC)
    workbook = _workbook_from_package(package, payload_sha256)
    mapped = _mapped_model(package, payload_sha256, timestamp)
    try:
        reconciliation = _reconcile_model(workbook, mapped)
    except (ValueError, KeyError, StopIteration) as error:
        raise PackageError("PACKAGE_PARITY_CALCULATION_FAILED", str(error)) from None
    report = {
        "contract_version": PACKAGE_VERSION,
        "payload_sha256": payload_sha256,
        "model_key": PACKAGE_MODEL_KEY,
        "model_type": PACKAGE_IDENTITY["model_type"],
        "methodology_version": PACKAGE_IDENTITY["methodology_version"],
        "return_methodology_code": PACKAGE_IDENTITY["return_methodology_code"],
        "return_comparability": PACKAGE_IDENTITY["return_comparability"],
        "source_identity_sha256": package.source.source_identity_sha256,
        "source_revision_id": package.source.drive_revision_id,
        "source_effective_at": None,
        "source_cell_count": len(package.source_cells),
        "projection_reconciliation": reconciliation["projection_reconciliation"],
        "output_reconciliation": reconciliation["output_reconciliation"],
        "probability_input_comparison": _compare_probability_inputs_with_parity_fixture(package),
        "status": reconciliation["status"],
        "acceptance_state": package.revision.acceptance_state,
    }
    return ValidatedPackage(package, payload_sha256, mapped, report)


def _source_scalar_for_cell(cell: PackageCell) -> Any:
    value = cell.effective_value
    if value is None:
        return None
    if value.kind == "NUMBER":
        return Decimal(cast(str, value.value))
    if value.kind == "STRING":
        return value.value
    if value.kind == "BOOLEAN":
        return value.value
    return {"error": value.value, "detail": value.detail} if value.kind == "ERROR" else None


def _package_from_cells(
    *,
    source_metadata: dict[str, Any],
    structure: dict[str, Any],
    source_cells: dict[str, PackageCell],
    captured_at: datetime,
) -> FinancialModelPackage:
    # Build the model inputs using the same reviewed mapper that the XLSX parity
    # inventory uses; the workbook object here is only an in-memory typed adapter.
    mapped, probability_normalization = _map_source_cells_to_model(
        source_cells, captured_at, "0" * 64
    )
    inputs = schemas.DcfCalculationInput.model_validate(
        {
            "base": mapped.values.base.model_dump(),
            "scenarios": [scenario.model_dump() for scenario in mapped.values.scenarios],
        }
    )
    input_sha256 = _input_digest(mapped)
    revision = PackageRevision(
        base_revision_id=None,
        external_revision_id=f"google-sheets:{PACKAGE_MODEL_KEY}:{input_sha256}",
        input_sha256=input_sha256,
        source_effective_at=None,
        author_identity=None,
        authored_at=None,
        acceptance_state="PROPOSAL_NOT_ACCEPTED",
    )
    package = FinancialModelPackage(
        contract_version=PACKAGE_VERSION,
        identity=_expected_identity(),
        revision=revision,
        inputs=inputs,
        published_outputs=_outputs_from_cells(source_cells),
        source=PackageSource(
            source_identity_sha256=source_metadata["source_identity_sha256"],
            mime_type="application/vnd.google-apps.spreadsheet",
            modified_time=source_metadata["modified_time"],
            drive_revision_id=source_metadata.get("head_revision_id"),
            drive_checksum=source_metadata.get("checksum"),
            spreadsheet_time_zone=structure.get("time_zone"),
            sheet_id=structure["sheet_id"],
            sheet_title=PACKAGE_MODEL_KEY,
            source_effective_at=None,
            capture_semantics="observed-consistent-state-not-transactional-snapshot",
            declared_ranges=P_GOOGL_RANGES,
        ),
        source_cells=source_cells,
        probability_normalization=probability_normalization,
    )
    _validate_package_shape(package)
    return package


class FinancialModelPackageStore:
    """P-GOOGL package blobs and append-only capture manifests in the private store."""

    def __init__(self, root: Path) -> None:
        self.store = SnapshotStore(root / PACKAGE_DIRECTORY)
        self.root = self.store.root
        self.blob_root = self.store.blob_root
        self.run_root = self.store.run_root
        self.report_root = self.root / "reports"
        if self.report_root.is_symlink():
            raise PackageError(
                "PACKAGE_STORE_INVALID", "The private package report path is invalid."
            )
        self.report_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with suppress(OSError):
            self.report_root.chmod(0o700)

    def _write_blob(self, payload: bytes, digest: str) -> str:
        if _sha256(payload) != digest:
            raise PackageError("PACKAGE_HASH_INVALID", "The package payload hash is inconsistent.")
        target = self.blob_root / f"{digest}.json"
        if target.exists():
            if (
                target.is_symlink()
                or not target.is_file()
                or _sha256(target.read_bytes()) != digest
            ):
                raise PackageError(
                    "PACKAGE_BLOB_CORRUPTED", "A stored package failed its hash check."
                )
            return target.relative_to(self.root).as_posix()
        descriptor, temporary_name = tempfile.mkstemp(prefix=".package-", dir=self.blob_root)
        temporary = Path(temporary_name)
        try:
            if hasattr(os, "fchmod"):
                with suppress(OSError):
                    os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if (
                    target.is_symlink()
                    or not target.is_file()
                    or _sha256(target.read_bytes()) != digest
                ):
                    raise PackageError(
                        "PACKAGE_BLOB_CORRUPTED", "A concurrent package blob failed its hash check."
                    ) from None
            with suppress(OSError):
                target.chmod(0o600)
            return target.relative_to(self.root).as_posix()
        except PackageError:
            raise
        except OSError as error:
            raise PackageError(
                "PACKAGE_STORE_WRITE_FAILED", "The package blob could not be stored."
            ) from error
        finally:
            if temporary.exists():
                temporary.unlink()

    def capture(
        self,
        package: FinancialModelPackage,
        *,
        captured_at: datetime,
        request_count: int,
        logical_request_count: int | None = None,
    ) -> StoredPackage:
        payload = _strict_json(package.model_dump(mode="json")).encode("utf-8")
        digest = _sha256(payload)
        relative_path = self._write_blob(payload, digest)
        run_id = uuid4().hex
        manifest: dict[str, Any] = {
            "run_id": run_id,
            "contract_version": PACKAGE_VERSION,
            "status": "CAPTURED_REVIEW_REQUIRED",
            "review_required": True,
            "captured_at": captured_at.astimezone(UTC).isoformat(),
            "payload_sha256": digest,
            "payload_path": relative_path,
            "source_identity_sha256": package.source.source_identity_sha256,
            "source_modified_at": package.source.modified_time,
            "drive_revision_id": package.source.drive_revision_id,
            "model_key": PACKAGE_MODEL_KEY,
            "source_cell_count": len(package.source_cells),
            "range_count": len(P_GOOGL_RANGES),
            "request_count": request_count,
            "logical_request_count": (
                logical_request_count if logical_request_count is not None else request_count
            ),
            "capture_semantics": package.source.capture_semantics,
        }
        manifest["manifest_sha256"] = _manifest_digest(manifest)
        try:
            self.store._write_manifest(manifest)
        except Exception as error:
            raise PackageError(
                "PACKAGE_MANIFEST_WRITE_FAILED", "The package manifest could not be stored."
            ) from error
        return StoredPackage(run_id, digest, manifest, package)

    def load(self, run_id: str, expected_sha256: str | None = None) -> StoredPackage:
        if not _RUN_PATTERN.fullmatch(run_id):
            raise PackageError("PACKAGE_RUN_ID_INVALID", "Use a valid package run ID.")
        try:
            manifest = self.store.manifest(run_id)
        except Exception:
            raise PackageError("PACKAGE_RUN_NOT_FOUND", "The package run was not found.") from None
        digest = manifest.get("payload_sha256")
        if (
            manifest.get("contract_version") != PACKAGE_VERSION
            or manifest.get("status") != "CAPTURED_REVIEW_REQUIRED"
            or manifest.get("review_required") is not True
            or manifest.get("manifest_sha256") != _manifest_digest(manifest)
            or not isinstance(digest, str)
            or not _HASH_PATTERN.fullmatch(digest)
            or (expected_sha256 is not None and digest != expected_sha256)
        ):
            raise PackageError(
                "PACKAGE_MANIFEST_INVALID", "The package manifest failed validation."
            )
        relative = f"blobs/sha256/{digest}.json"
        if manifest.get("payload_path") != relative:
            raise PackageError("PACKAGE_PATH_INVALID", "The package path is invalid.")
        path = self.root / relative
        if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != digest:
            raise PackageError("PACKAGE_HASH_MISMATCH", "The stored package failed its hash check.")
        payload = path.read_bytes()
        try:
            package = FinancialModelPackage.model_validate_json(payload)
        except ValidationError as error:
            raise PackageError(
                "PACKAGE_SCHEMA_INVALID", _sanitized_validation_error(error)
            ) from None
        if _strict_json(package.model_dump(mode="json")).encode("utf-8") != payload:
            raise PackageError(
                "PACKAGE_ENCODING_INVALID", "The stored package is not canonical JSON."
            )
        if package.source.source_identity_sha256 != manifest.get("source_identity_sha256"):
            raise PackageError(
                "PACKAGE_PROVENANCE_MISMATCH", "The package source identity did not match."
            )
        _validate_package_shape(package)
        return StoredPackage(run_id, digest, manifest, package)

    def write_report(self, prefix: str, report: Mapping[str, Any]) -> Path:
        target = self.report_root / f"{prefix}-{uuid4().hex}.json"
        payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        descriptor, temporary_name = tempfile.mkstemp(prefix=".report-", dir=self.report_root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            with suppress(OSError):
                target.chmod(0o600)
            return target
        finally:
            if temporary.exists():
                temporary.unlink()


class PGooglSheetsExporter:
    """Bounded read-only exporter for the declared P-GOOGL model cell contract."""

    def __init__(
        self,
        settings: Settings,
        store: FinancialModelPackageStore,
        session: Any | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        try:
            self.reader = SheetsPortfolioReader(settings, session, sleeper=sleeper, clock=clock)
        except SheetsPortfolioError as error:
            raise PackageError(error.code, str(error)) from None
        self.store = store
        self.clock = clock
        self._request_count = 0
        self.reader.request_attempt_count = 0

    def _model_structure(self) -> dict[str, Any]:
        url = f"{SHEETS_API}/{quote(self.reader.spreadsheet_id, safe='')}"
        response = self.reader._get_json(url, {"fields": _STRUCTURE_FIELDS})
        self._request_count += 1
        if response.get("spreadsheetId") != self.reader.spreadsheet_id:
            raise PackageError(
                "PACKAGE_SOURCE_IDENTITY_MISMATCH", "Sheets returned another spreadsheet."
            )
        properties = response.get("properties")
        time_zone = properties.get("timeZone") if isinstance(properties, dict) else None
        sheets = response.get("sheets")
        if not isinstance(sheets, list):
            raise PackageError(
                "PACKAGE_STRUCTURE_INVALID", "Sheets returned no worksheet structure."
            )
        matches: list[dict[str, Any]] = []
        for item in sheets:
            sheet_properties = item.get("properties") if isinstance(item, dict) else None
            if (
                isinstance(sheet_properties, dict)
                and sheet_properties.get("title") == PACKAGE_MODEL_KEY
            ):
                matches.append(sheet_properties)
        if len(matches) != 1:
            raise PackageError(
                "PACKAGE_SOURCE_TAB_INVALID", "The exact P-GOOGL tab was not unique."
            )
        sheet = matches[0]
        grid = sheet.get("gridProperties")
        sheet_id = sheet.get("sheetId")
        if (
            not isinstance(grid, dict)
            or isinstance(sheet_id, bool)
            or not isinstance(sheet_id, int)
            or not isinstance(grid.get("rowCount"), int)
            or not isinstance(grid.get("columnCount"), int)
            or grid["rowCount"] < 212
            or grid["columnCount"] < _column_number("AO")
        ):
            raise PackageError(
                "PACKAGE_SOURCE_TAB_INVALID", "The P-GOOGL tab dimensions are incomplete."
            )
        return {
            "sheet_id": sheet_id,
            "sheet_title": PACKAGE_MODEL_KEY,
            "row_count": grid["rowCount"],
            "column_count": grid["columnCount"],
            "time_zone": time_zone if isinstance(time_zone, str) else None,
        }

    def _sweep(self) -> dict[str, PackageCell]:
        result: dict[str, PackageCell] = {}
        for a1_range in P_GOOGL_RANGES:
            if self._request_count >= _MAX_PACKAGE_CALLS:
                raise PackageError(
                    "PACKAGE_REQUEST_LIMIT_EXCEEDED", "The P-GOOGL request budget was exceeded."
                )
            response = self.reader._get_json(
                f"{SHEETS_API}/{quote(self.reader.spreadsheet_id, safe='')}",
                {"ranges": a1_range, "includeGridData": "true", "fields": _PACKAGE_FIELDS},
            )
            self._request_count += 1
            if response.get("spreadsheetId") != self.reader.spreadsheet_id:
                raise PackageError(
                    "PACKAGE_SOURCE_IDENTITY_MISMATCH", "Sheets returned another spreadsheet."
                )
            match = _RANGE_PATTERN.fullmatch(a1_range)
            if match is None:
                raise PackageError(
                    "PACKAGE_RANGE_INVALID", "The P-GOOGL range contract is invalid."
                )
            coordinates = _range_coordinates(a1_range)
            try:
                values, _formats, sheets, presence, stats = _cell_grid_index(
                    response, [(PACKAGE_MODEL_KEY, a1_range, len(coordinates))]
                )
            except ValueError as error:
                raise PackageError(
                    "PACKAGE_RANGE_INCOMPLETE",
                    f"Requested range {a1_range} failed validation: {error}",
                ) from None
            if PACKAGE_MODEL_KEY not in sheets or stats["coordinates_covered"] != len(coordinates):
                raise PackageError(
                    "PACKAGE_RANGE_INCOMPLETE",
                    f"Requested range {a1_range} was not fully returned.",
                )
            for row, column, address in coordinates:
                raw = values[PACKAGE_MODEL_KEY].get((row, column))
                if raw is None or address in result:
                    raise PackageError(
                        "PACKAGE_RANGE_INCOMPLETE",
                        f"Requested range {a1_range} omitted a cell coordinate.",
                    )
                result[address] = _package_cell(raw, presence[PACKAGE_MODEL_KEY][(row, column)])
        if set(result) != EXPECTED_PACKAGE_CELLS:
            raise PackageError(
                "PACKAGE_CELL_SCOPE_INVALID", "The exporter did not capture the declared cells."
            )
        return result

    def _probability_sweep(self) -> dict[str, PackageCell]:
        response = self.reader._get_json(
            f"{SHEETS_API}/{quote(self.reader.spreadsheet_id, safe='')}",
            {
                "ranges": P_GOOGL_PROBABILITY_RANGE,
                "includeGridData": "true",
                "fields": _PACKAGE_FIELDS,
            },
        )
        self._request_count += 1
        if response.get("spreadsheetId") != self.reader.spreadsheet_id:
            raise PackageError(
                "PACKAGE_SOURCE_IDENTITY_MISMATCH", "Sheets returned another spreadsheet."
            )
        coordinates = _range_coordinates(P_GOOGL_PROBABILITY_RANGE)
        try:
            values, _formats, sheets, presence, stats = _cell_grid_index(
                response,
                [(PACKAGE_MODEL_KEY, P_GOOGL_PROBABILITY_RANGE, len(coordinates))],
            )
        except ValueError as error:
            raise PackageError(
                "PACKAGE_PROBABILITY_RANGE_INCOMPLETE",
                f"The probability range failed validation: {error}",
            ) from None
        if PACKAGE_MODEL_KEY not in sheets or stats["coordinates_covered"] != len(coordinates):
            raise PackageError(
                "PACKAGE_PROBABILITY_RANGE_INCOMPLETE",
                "Sheets did not return all three probability cell coordinates.",
            )
        result: dict[str, PackageCell] = {}
        for row, column, address in coordinates:
            raw = values[PACKAGE_MODEL_KEY].get((row, column))
            if raw is None:
                raise PackageError(
                    "PACKAGE_PROBABILITY_RANGE_INCOMPLETE",
                    "Sheets omitted a probability cell coordinate.",
                )
            result[address] = _package_cell(raw, presence[PACKAGE_MODEL_KEY][(row, column)])
        return result

    def diagnose_probabilities(self) -> dict[str, Any]:
        """Capture exact private evidence for the three scenario probabilities only."""
        captured_at = self.clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise PackageError(
                "PACKAGE_CAPTURE_TIME_INVALID", "The capture clock must be timezone-aware."
            )
        self._request_count = 0
        self.reader.request_attempt_count = 0
        try:
            before_metadata = self.reader._drive_metadata()
            self._request_count += 1
            before_structure = self._model_structure()
            first = self._probability_sweep()
            second = self._probability_sweep()
            after_structure = self._model_structure()
            after_metadata = self.reader._drive_metadata()
            self._request_count += 1
        except SheetsPortfolioError as error:
            raise PackageError(error.code, str(error)) from None

        metadata_stable = before_metadata == after_metadata
        structure_stable = before_structure == after_structure
        values_stable = _strict_json(
            {key: value.model_dump(mode="json") for key, value in first.items()}
        ) == _strict_json({key: value.model_dump(mode="json") for key, value in second.items()})
        source_stable = metadata_stable and structure_stable and values_stable

        parity_fixture = Workbook.read(DEFAULT_WORKBOOK, lambda name: name == PACKAGE_MODEL_KEY)
        fixture_mapped = _map_googl(parity_fixture, captured_at.astimezone(UTC))
        if not isinstance(fixture_mapped.values, schemas.FinancialModelRevisionCreate):
            raise PackageError(
                "PACKAGE_PARITY_FIXTURE_INVALID", "The P-GOOGL parity fixture is not a DCF model."
            )
        fixture_probabilities = {
            scenario.scenario.value: scenario.probability
            for scenario in fixture_mapped.values.scenarios
        }
        fixture_formulas = {
            address: parity_fixture.sheets[PACKAGE_MODEL_KEY][address].formula
            for address in P_GOOGL_PROBABILITY_CELLS.values()
        }

        def probability_detail(
            source_cells: Mapping[str, PackageCell], scenario: str, address: str
        ) -> dict[str, Any]:
            cell = source_cells[address]
            try:
                effective_decimal: str | None = format(_decimal_cell(source_cells, address), "f")
            except PackageError:
                effective_decimal = None
            entered = cell.user_entered_value
            effective = cell.effective_value
            source_formula = (
                cast(str, entered.value)
                if entered is not None and entered.kind == "FORMULA"
                else None
            )
            fixture_formula = fixture_formulas[address]
            source_minus_fixture = (
                Decimal(effective_decimal) - fixture_probabilities[scenario]
                if effective_decimal is not None
                else None
            )
            value_comparison_status = (
                "UNAVAILABLE"
                if source_minus_fixture is None
                else "EXACT_MATCH"
                if source_minus_fixture == 0
                else "SERIALIZATION_SCALE_DIFFERENCE"
                if abs(source_minus_fixture) <= MAX_PROBABILITY_SUM_RESIDUAL
                else "SOURCE_INPUT_DIFFERS_FROM_PARITY_FIXTURE"
            )
            formula_matches_fixture = (
                source_formula is None
                and fixture_formula is None
                or source_formula is not None
                and fixture_formula is not None
                and source_formula.strip().removeprefix("=").strip()
                == fixture_formula.strip().removeprefix("=").strip()
            )
            return {
                "scenario": scenario,
                "source_cell": address,
                "state": cell.state,
                "transport_state": cell.transport_state,
                "source_kind": (
                    "FORMULA" if source_formula is not None else "LITERAL" if entered else "BLANK"
                ),
                "user_entered_value": entered.model_dump(mode="json") if entered else None,
                "effective_value": effective.model_dump(mode="json") if effective else None,
                "effective_decimal": effective_decimal,
                "number_format_type": cell.number_format_type,
                "number_format_pattern": cell.number_format_pattern,
                "parity_fixture_value": format(fixture_probabilities[scenario], "f"),
                "parity_fixture_formula": fixture_formula,
                "source_minus_parity_fixture": (
                    format(source_minus_fixture, "f") if source_minus_fixture is not None else None
                ),
                "value_comparison_status": value_comparison_status,
                "value_matches_parity_fixture": (
                    effective_decimal is not None
                    and Decimal(effective_decimal) == fixture_probabilities[scenario]
                ),
                "formula_matches_parity_fixture": formula_matches_fixture,
            }

        first_details = {
            scenario: probability_detail(first, scenario, address)
            for scenario, address in P_GOOGL_PROBABILITY_CELLS.items()
        }
        second_details = {
            scenario: probability_detail(second, scenario, address)
            for scenario, address in P_GOOGL_PROBABILITY_CELLS.items()
        }

        def exact_sum(source_cells: Mapping[str, PackageCell]) -> Decimal | None:
            values: list[Decimal] = []
            for address in P_GOOGL_PROBABILITY_CELLS.values():
                try:
                    values.append(_decimal_cell(source_cells, address))
                except PackageError:
                    return None
            return sum(values, Decimal(0))

        first_sum = exact_sum(first)
        second_sum = exact_sum(second)
        stable_sum = second_sum if source_stable else None
        report = {
            "diagnostic_version": "p-googl-scenario-probabilities-v1",
            "status": "CAPTURED_REVIEW_REQUIRED" if source_stable else "SOURCE_CHANGED",
            "captured_at": captured_at.astimezone(UTC).isoformat(),
            "source_identity_sha256": before_metadata["source_identity_sha256"],
            "source_modified_at_before": before_metadata["modified_time"],
            "source_modified_at_after": after_metadata["modified_time"],
            "drive_revision_id_before": before_metadata.get("head_revision_id"),
            "drive_revision_id_after": after_metadata.get("head_revision_id"),
            "metadata_stable": metadata_stable,
            "structure_stable": structure_stable,
            "probability_values_stable": values_stable,
            "source_stable": source_stable,
            "scenario_mapping": P_GOOGL_PROBABILITY_CELLS,
            "first_read": first_details,
            "second_read": second_details,
            "first_read_exact_sum": format(first_sum, "f") if first_sum is not None else None,
            "second_read_exact_sum": format(second_sum, "f") if second_sum is not None else None,
            "stable_exact_sum": format(stable_sum, "f") if stable_sum is not None else None,
            "stable_delta_from_one": (
                format(stable_sum - Decimal(1), "f") if stable_sum is not None else None
            ),
            "sum_equals_one_exactly": stable_sum == Decimal(1) if stable_sum is not None else None,
            "any_percent_format": any(
                detail["number_format_type"] == "PERCENT" for detail in first_details.values()
            ),
            "all_values_match_parity_fixture": all(
                detail["value_matches_parity_fixture"] for detail in first_details.values()
            ),
            "probability_input_comparison_status": (
                "PROPOSED_SOURCE_REVISION"
                if any(
                    detail["value_comparison_status"] == "SOURCE_INPUT_DIFFERS_FROM_PARITY_FIXTURE"
                    for detail in first_details.values()
                )
                else "FIXTURE_INPUTS_MATCH_WITH_SERIALIZATION_DIFFERENCE"
                if any(
                    detail["value_comparison_status"] == "SERIALIZATION_SCALE_DIFFERENCE"
                    for detail in first_details.values()
                )
                else "FIXTURE_INPUTS_MATCH"
            ),
            "all_formulas_match_parity_fixture": all(
                detail["formula_matches_parity_fixture"] for detail in first_details.values()
            ),
            "normalization_applied": False,
            "request_attempt_count": self.reader.request_attempt_count,
            "logical_request_count": self._request_count,
        }
        path = self.store.write_report("probability-diagnostic", report)
        return {
            "status": report["status"],
            "source_stable": source_stable,
            "sum_equals_one_exactly": report["sum_equals_one_exactly"],
            "all_values_match_parity_fixture": report["all_values_match_parity_fixture"],
            "all_formulas_match_parity_fixture": report["all_formulas_match_parity_fixture"],
            "private_report_written": path.is_file(),
        }

    def capture(self) -> StoredPackage:
        if len(P_GOOGL_RANGES) * 2 + 4 > _MAX_PACKAGE_CALLS:
            raise PackageError(
                "PACKAGE_REQUEST_LIMIT_EXCEEDED", "The fixed P-GOOGL request budget is invalid."
            )
        captured_at = self.clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise PackageError(
                "PACKAGE_CAPTURE_TIME_INVALID", "The capture clock must be timezone-aware."
            )
        self._request_count = 0
        try:
            before_metadata = self.reader._drive_metadata()
            self._request_count += 1
            before_structure = self._model_structure()
            first = self._sweep()
            second = self._sweep()
            after_structure = self._model_structure()
            after_metadata = self.reader._drive_metadata()
            self._request_count += 1
        except SheetsPortfolioError as error:
            raise PackageError(error.code, str(error)) from None
        if (
            before_metadata != after_metadata
            or before_structure != after_structure
            or _strict_json({key: value.model_dump(mode="json") for key, value in first.items()})
            != _strict_json({key: value.model_dump(mode="json") for key, value in second.items()})
        ):
            raise PackageError(
                "PACKAGE_SOURCE_CHANGED_DURING_CAPTURE",
                "The source metadata, tab structure, values, or formulas changed during capture.",
            )
        package = _package_from_cells(
            source_metadata=before_metadata,
            structure=before_structure,
            source_cells=first,
            captured_at=captured_at.astimezone(UTC),
        )
        validated = validate_financial_model_package(
            package,
            _sha256(_strict_json(package.model_dump(mode="json")).encode("utf-8")),
            validated_at=captured_at,
        )
        if validated.parity_report["status"] != "PARITY_PASS":
            raise PackageError(
                "PACKAGE_PARITY_FAILED",
                "The P-GOOGL source values do not pass the approved native parity checks.",
            )
        return self.store.capture(
            package,
            captured_at=captured_at,
            request_count=self.reader.request_attempt_count,
            logical_request_count=self._request_count,
        )


def preview_financial_model_package_import(
    session: Session,
    package: FinancialModelPackage,
    payload_sha256: str,
    *,
    at: datetime | None = None,
    lock_for_acceptance: bool = False,
) -> dict[str, Any]:
    validated = validate_financial_model_package(package, payload_sha256, validated_at=at)
    if validated.parity_report["status"] != "PARITY_PASS":
        return {**validated.parity_report, "status": "BLOCKED_PARITY"}
    try:
        company, listing = _identity(session, validated.mapped_model)
    except ValueError as error:
        return {
            **validated.parity_report,
            "status": "BLOCKED_IDENTITY",
            "identity_reason": str(error),
        }
    query = select(FinancialModel).where(
        FinancialModel.company_id == company.id,
        FinancialModel.valuation_listing_id == listing.id,
        FinancialModel.model_type == FinancialModelType.UFCF_DCF_10Y_FADE,
    )
    if lock_for_acceptance:
        query = query.with_for_update()
    existing = session.scalar(query)
    if existing is None:
        if package.revision.base_revision_id is not None:
            return {
                **validated.parity_report,
                "status": "BLOCKED_BASE_MODEL_MISSING",
                "package_base_revision_id": str(package.revision.base_revision_id),
            }
        return {
            **validated.parity_report,
            "status": "READY_FOR_EXPLICIT_ACCEPTANCE",
            "canonical_company_id": str(company.id),
            "canonical_listing_id": str(listing.id),
            "existing_model_id": None,
            "base_revision_id": package.revision.base_revision_id,
        }
    existing_revision_id = session.scalar(
        select(FinancialModelRevision.id).where(
            FinancialModelRevision.model_id == existing.id,
            FinancialModelRevision.source_revision_id == package.revision.external_revision_id,
        )
    )
    if existing_revision_id is not None:
        return {
            **validated.parity_report,
            "status": "ALREADY_ACCEPTED",
            "canonical_company_id": str(company.id),
            "canonical_listing_id": str(listing.id),
            "existing_model_id": str(existing.id),
            "existing_revision_id": str(existing_revision_id),
        }
    if package.revision.base_revision_id is None:
        return {
            **validated.parity_report,
            "status": "BLOCKED_MODEL_EXISTS_WITHOUT_BASE",
            "existing_model_id": str(existing.id),
            "current_revision_id": str(existing.current_revision_id),
        }
    if package.revision.base_revision_id != existing.current_revision_id:
        return {
            **validated.parity_report,
            "status": "BLOCKED_STALE_BASE",
            "existing_model_id": str(existing.id),
            "package_base_revision_id": str(package.revision.base_revision_id),
            "current_revision_id": str(existing.current_revision_id),
        }
    return {
        **validated.parity_report,
        "status": "READY_FOR_EXPLICIT_ACCEPTANCE",
        "canonical_company_id": str(company.id),
        "canonical_listing_id": str(listing.id),
        "existing_model_id": str(existing.id),
        "base_revision_id": str(package.revision.base_revision_id),
    }


def accept_financial_model_package(
    session: Session,
    package: FinancialModelPackage,
    payload_sha256: str,
    *,
    accepted_at: datetime,
) -> dict[str, Any]:
    """Accept one exact validated package through existing native model services."""
    preview = preview_financial_model_package_import(
        session,
        package,
        payload_sha256,
        at=accepted_at,
        lock_for_acceptance=True,
    )
    if preview["status"] == "ALREADY_ACCEPTED":
        return preview
    if preview["status"] != "READY_FOR_EXPLICIT_ACCEPTANCE":
        return preview
    validated = validate_financial_model_package(package, payload_sha256, validated_at=accepted_at)
    company, listing = _identity(session, validated.mapped_model)
    existing = (
        session.get(FinancialModel, UUID(preview["existing_model_id"]))
        if preview.get("existing_model_id")
        else None
    )
    try:
        if existing is None:
            model, revision = _create_native_model(
                session, company.id, listing.id, validated.mapped_model
            )
        else:
            from portfolio_api.domain.services import append_financial_model_revision

            if not isinstance(validated.mapped_model.values, schemas.FinancialModelRevisionCreate):
                raise PackageError(
                    "PACKAGE_METHOD_UNSUPPORTED",
                    "The canonical P-GOOGL package requires the DCF revision contract.",
                )
            revision = append_financial_model_revision(
                session, existing.id, validated.mapped_model.values
            )
            model = existing
    except Exception as error:
        # Keep API/service validation text private to avoid accidental source-data leakage.
        raise PackageError(
            "PACKAGE_CANONICAL_IMPORT_FAILED",
            f"Canonical model service rejected the package ({type(error).__name__}).",
        ) from None
    return {
        **preview,
        "status": "ACCEPTED",
        "model_id": str(model.id),
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "source_revision_id": revision.source_revision_id,
        "base_revision_id": revision.base_revision_id,
        "methodology_version": revision.methodology_version,
        "effective_at": revision.effective_at.astimezone(UTC).isoformat(),
        "recorded_at": revision.recorded_at.astimezone(UTC).isoformat(),
    }


def _sanitized_validation_error(error: ValidationError) -> str:
    first = error.errors(include_input=False)[:1]
    if not first:
        return "The financial-model package does not match its versioned schema."
    location = ".".join(str(part) for part in first[0].get("loc", ()))
    return f"The financial-model package field {location or 'unknown'} is invalid."


def _write_json_report(
    store: FinancialModelPackageStore, prefix: str, report: Mapping[str, Any]
) -> Path:
    return store.write_report(prefix, report)


def _summary(package_run: StoredPackage) -> dict[str, Any]:
    return {
        "status": package_run.manifest["status"],
        "run_id": package_run.run_id,
        "payload_sha256": package_run.payload_sha256,
        "contract_version": PACKAGE_VERSION,
        "model_key": PACKAGE_MODEL_KEY,
        "source_cell_count": len(package_run.package.source_cells),
        "declared_range_count": len(P_GOOGL_RANGES),
        "request_count": package_run.manifest["request_count"],
        "logical_request_count": package_run.manifest["logical_request_count"],
        "source_revision_id": package_run.package.revision.external_revision_id,
        "acceptance_state": package_run.package.revision.acceptance_state,
        "probability_normalization_applied": (
            package_run.package.probability_normalization is not None
        ),
    }


def _default_store_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise PackageError(
            "PACKAGE_STORE_NOT_CONFIGURED", "Set --store to a private local snapshot directory."
        )
    return Path(local_app_data) / "PortfolioResearch" / "workbook-snapshots"


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("schema", help="print the public JSON Schema for package v1")
    capture = subparsers.add_parser("capture", help="read and freeze the configured P-GOOGL sheet")
    capture.add_argument("--store", type=Path)
    capture.add_argument("--confirm-read-only-source-capture", action="store_true", required=True)
    probability_diagnostic = subparsers.add_parser(
        "diagnose-probabilities",
        help="privately compare live P-GOOGL probabilities with the approved parity fixture",
    )
    probability_diagnostic.add_argument("--store", type=Path)
    probability_diagnostic.add_argument(
        "--confirm-read-only-source-diagnostic", action="store_true", required=True
    )
    for command in ("inspect", "validate", "preview", "accept"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--store", type=Path)
        sub.add_argument("--run-id", required=True)
        sub.add_argument("--payload-sha256")
        if command in {"preview", "accept"}:
            sub.add_argument(
                "--target-environment",
                choices=("development", "rehearsal", "production"),
                required=True,
            )
        if command == "accept":
            sub.add_argument("--expected-payload-sha256", required=True)
            sub.add_argument("--approve-payload-sha256", required=True)
            sub.add_argument(
                "--confirm-explicit-model-acceptance", action="store_true", required=True
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            print(json.dumps(FinancialModelPackage.model_json_schema(), sort_keys=True))
            return 0
        store = FinancialModelPackageStore(args.store or _default_store_root())
        if args.command == "capture":
            package_run = PGooglSheetsExporter(Settings(), store).capture()
            print(json.dumps(_summary(package_run), sort_keys=True))
            return 0
        if args.command == "diagnose-probabilities":
            result = PGooglSheetsExporter(Settings(), store).diagnose_probabilities()
            print(json.dumps(result, sort_keys=True))
            return 0 if result["source_stable"] else 2
        package_run = store.load(args.run_id, args.payload_sha256)
        if args.command == "inspect":
            print(json.dumps(_summary(package_run), sort_keys=True))
            return 0
        validation = validate_financial_model_package(
            package_run.package, package_run.payload_sha256
        )
        if args.command == "validate":
            path = _write_json_report(store, "validation", validation.parity_report)
            print(
                json.dumps(
                    {
                        "status": validation.parity_report["status"],
                        "payload_sha256": package_run.payload_sha256,
                        "projection_checks": validation.parity_report["projection_reconciliation"][
                            "passed"
                        ],
                        "output_checks": validation.parity_report["output_reconciliation"][
                            "passed"
                        ],
                        "probability_input_status": validation.parity_report[
                            "probability_input_comparison"
                        ]["status"],
                        "private_report": str(path),
                    },
                    sort_keys=True,
                )
            )
            return 0 if validation.parity_report["status"] == "PARITY_PASS" else 2
        settings = Settings()
        read_only = args.command == "preview"
        if read_only:
            engine = create_database_engine(settings, read_only=True)
        else:
            if (
                args.expected_payload_sha256 != package_run.payload_sha256
                or args.approve_payload_sha256 != package_run.payload_sha256
                or args.expected_payload_sha256 != args.approve_payload_sha256
            ):
                raise PackageError(
                    "PACKAGE_APPROVAL_HASH_MISMATCH",
                    "The two explicit package approvals must match the stored hash.",
                )
            engine = create_database_engine(
                settings,
                write_operation="financial_model_package_import",
                write_operation_kind="import",
            )
        if engine is None:
            raise PackageError(
                "DATABASE_NOT_CONFIGURED", "Set DATABASE_URL for a guarded database operation."
            )
        try:
            if read_only:
                verify_database_read_only_preflight(
                    engine,
                    configured_target_environment=settings.database_target_environment,
                    requested_target_environment=args.target_environment,
                )
            else:
                verify_database_preflight(
                    engine,
                    configured_target_environment=settings.database_target_environment,
                    requested_target_environment=args.target_environment,
                )
            with Session(engine) as session, session.begin():
                report = (
                    preview_financial_model_package_import(
                        session, package_run.package, package_run.payload_sha256
                    )
                    if read_only
                    else accept_financial_model_package(
                        session,
                        package_run.package,
                        package_run.payload_sha256,
                        accepted_at=datetime.now(UTC),
                    )
                )
            report_path = _write_json_report(store, args.command, report)
        finally:
            engine.dispose()
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "payload_sha256": package_run.payload_sha256,
                    "private_report": str(report_path),
                },
                sort_keys=True,
            )
        )
        return (
            0
            if report["status"] in {"READY_FOR_EXPLICIT_ACCEPTANCE", "ALREADY_ACCEPTED", "ACCEPTED"}
            else 2
        )
    except (PackageError, SheetsPortfolioError, ValidationError) as error:
        code = (
            error.code
            if isinstance(error, (PackageError, SheetsPortfolioError))
            else "PACKAGE_SCHEMA_INVALID"
        )
        print(f"{code}: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"PACKAGE_OPERATION_FAILED: ({type(error).__name__})", file=sys.stderr)
        return 2


def main() -> int:
    return _cli()


if __name__ == "__main__":
    raise SystemExit(main())
