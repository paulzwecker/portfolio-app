"""Configuration-driven, read-only Google Sheets DCF model package exporter.

Contract v2 freezes exact live Sheets cell evidence and reuses the existing
model-input mappers and deterministic DCF parity checks. It does not import or
accept a model revision.
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
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from portfolio_api.domain import schemas
from portfolio_api.financial_model_package import (
    PackageCell,
    PackageError,
    ProbabilityNormalization,
    _manifest_digest,
    _normalized_source_probabilities,
    _package_cell,
    _sanitized_validation_error,
    _strict_json,
)
from portfolio_api.financial_model_package import (
    _input_digest as _input_digest,
)
from portfolio_api.financial_model_package import (
    _sha256 as _sha256,
)
from portfolio_api.financial_model_package_templates import (
    DCF_MODEL_TEMPLATES,
    DcfModelTemplate,
    get_dcf_model_template,
)
from portfolio_api.legacy_import import Cell, Workbook
from portfolio_api.model_input_migration import (
    MappedModel,
    _map_googl,
    _map_portfolio_dcf,
    _reconcile_model,
)
from portfolio_api.settings import Settings
from portfolio_api.sheets_portfolio_vertical_slice import (
    SHEETS_API,
    SheetsPortfolioError,
    SheetsPortfolioReader,
)
from portfolio_api.workbook_sources import SnapshotStore
from portfolio_api.workbook_value_validation import (
    _cell_grid_index,
    _column_name,
    _column_number,
)

CONTRACT_VERSION: Literal["financial-model-package-v2"] = "financial-model-package-v2"
PACKAGE_DIRECTORY = "financial-model-packages-v2"
MAX_PACKAGE_CALLS = 48
MAX_PACKAGE_CELLS = 512
RANGE_PATTERN = re.compile(r"^'([^']+)'!([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RUN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
STRUCTURE_FIELDS = (
    "spreadsheetId,properties(timeZone),sheets(properties(sheetId,title,"
    "gridProperties(rowCount,columnCount)))"
)
CELL_FIELDS = (
    "spreadsheetId,sheets(properties(title),data(startRow,startColumn,"
    "rowData(values(userEnteredValue,effectiveValue,effectiveFormat(numberFormat(type,pattern))))))"
)


class StrictPackageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DcfPackageIdentity(StrictPackageModel):
    source_model_key: str = Field(pattern=r"^P-[A-Z0-9-]+$")
    template_id: str = Field(min_length=1, max_length=100)
    template_version: str = Field(min_length=1, max_length=80)
    mapping_version: str = Field(min_length=1, max_length=100)
    company_name: str = Field(min_length=1, max_length=180)
    canonical_ticker: str = Field(min_length=1, max_length=24)
    listing_ticker: str = Field(min_length=1, max_length=24)
    listing_venue: str = Field(min_length=1, max_length=30)
    security_type: Literal["COMMON_STOCK"]
    listing_currency: str = Field(pattern=r"^[A-Z]{3}$")
    model_currency: str = Field(pattern=r"^[A-Z]{3}$")
    model_type: Literal["UFCF_DCF_10Y_FADE"]
    methodology_version: Literal["ufcf-dcf-fade-v1", "ufcf-dcf-explicit-tail-v1"]
    return_methodology_code: Literal["UFCF_ENTERPRISE_IRR", "UFCF_ENTERPRISE_HMODEL_IRR"]
    economic_cash_flow_basis: str = Field(min_length=1, max_length=160)
    return_perspective: Literal["ENTERPRISE"]
    return_comparability: Literal["NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR"]
    operating_value_unit: str = Field(pattern=r"^[A-Z]{3}_BILLIONS$")
    share_count_unit: Literal["BILLIONS_OF_SHARES"]
    per_share_unit: str = Field(min_length=1, max_length=80)
    legacy_return_semantics: str = Field(min_length=1, max_length=1200)


class DcfPackageSource(StrictPackageModel):
    source_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: Literal["application/vnd.google-apps.spreadsheet"]
    modified_time: str = Field(min_length=1, max_length=80)
    drive_revision_id: str | None = Field(default=None, max_length=160)
    drive_checksum: str | None = Field(default=None, max_length=128)
    spreadsheet_time_zone: str | None = Field(default=None, max_length=100)
    sheet_id: int = Field(ge=0)
    sheet_title: str = Field(min_length=1, max_length=100)
    source_effective_at: None = None
    capture_semantics: Literal["observed-consistent-state-not-transactional-snapshot"]
    declared_ranges: tuple[str, ...] = Field(min_length=1, max_length=30)


class DcfPackageRevision(StrictPackageModel):
    base_revision_id: UUID | None
    external_revision_id: str = Field(min_length=1, max_length=160)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_effective_at: None = None
    author_identity: None = None
    authored_at: None = None
    acceptance_state: Literal["PROPOSAL_NOT_ACCEPTED"]


class DcfPublishedProjection(StrictPackageModel):
    scenario: Literal["BEAR", "BASE", "BULL"]
    forecast_year: int = Field(ge=1, le=10)
    metric: Literal["present_value_ufcf", "unlevered_free_cash_flow"]
    source_cell: str = Field(pattern=r"^[A-Z]{1,3}[0-9]+$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    value: Decimal


class DcfPublishedOutputs(StrictPackageModel):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    parity_reference_price: Decimal
    parity_reference_price_cell: str = Field(pattern=r"^[A-Z]{1,3}[0-9]+$")
    bear_fair_value_per_share: Decimal
    base_fair_value_per_share: Decimal
    bull_fair_value_per_share: Decimal
    weighted_fair_value_per_share: Decimal
    weighted_upside: Decimal
    expected_cash_flow_irr: Decimal
    hurdle: Decimal
    expected_excess: Decimal
    projections: tuple[DcfPublishedProjection, ...] = Field(min_length=30, max_length=30)
    return_stream: tuple[Decimal, ...] = Field(min_length=11, max_length=11)


class DcfModelPackage(StrictPackageModel):
    contract_version: Literal["financial-model-package-v2"]
    identity: DcfPackageIdentity
    revision: DcfPackageRevision
    inputs: schemas.DcfCalculationInput
    input_cell_map: dict[str, str]
    published_outputs: DcfPublishedOutputs
    source: DcfPackageSource
    source_cells: dict[str, PackageCell]
    probability_normalization: ProbabilityNormalization | None = None

    @model_validator(mode="after")
    def enforce_model_package_contract(self) -> DcfModelPackage:
        template = get_dcf_model_template(self.identity.source_model_key)
        _validate_package_shape(self, template)
        return self


@dataclass(frozen=True)
class DcfModelPackageRun:
    run_id: str
    payload_sha256: str
    manifest: dict[str, Any]
    package: DcfModelPackage


@dataclass(frozen=True)
class DcfModelPackageValidation:
    package: DcfModelPackage
    payload_sha256: str
    mapped_model: MappedModel
    parity_report: dict[str, Any]


def _a1_range(sheet: str, bare_range: str) -> str:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)(?::([A-Z]+)([0-9]+))?", bare_range)
    if match is None:
        raise PackageError("PACKAGE_TEMPLATE_INVALID", "A reviewed model range is malformed.")
    start_column, start_row, end_column, end_row = match.groups()
    end = f":{end_column or start_column}{end_row or start_row}"
    return f"'{sheet}'!{start_column}{start_row}{end}"


def _a1_coordinates(a1_range: str) -> list[tuple[int, int, str]]:
    match = RANGE_PATTERN.fullmatch(a1_range)
    if match is None:
        raise PackageError("PACKAGE_RANGE_INVALID", "A declared source range is malformed.")
    _sheet, first_column, first_row, last_column, last_row = match.groups()
    row_start, row_end = int(first_row), int(last_row)
    column_start, column_end = _column_number(first_column), _column_number(last_column)
    if row_start < 1 or row_end < row_start or column_end < column_start:
        raise PackageError("PACKAGE_RANGE_INVALID", "A declared source range is invalid.")
    return [
        (row, column, f"{_column_name(column)}{row}")
        for row in range(row_start, row_end + 1)
        for column in range(column_start, column_end + 1)
    ]


def _qualified_ranges(template: DcfModelTemplate) -> tuple[str, ...]:
    return tuple(_a1_range(template.model_key, item) for item in template.ranges)


def _expected_input_cell_map(template: DcfModelTemplate) -> dict[str, str]:
    """Expand a reviewed declarative template into its exact native field map."""
    cells = dict(template.base_input_cells)
    cells.update(
        {
            f"scenarios.{scenario}.probability": address
            for scenario, address in template.probability_cells
        }
    )
    cells.update(
        {
            f"scenarios.{scenario}.terminal_growth": address
            for scenario, address in template.terminal_growth_cells
        }
    )
    cells.update({"model_currency": "B15", "source_price_for_parity_only": "B4"})
    year10_growth = dict(template.year10_growth_cells)
    tail_growth = dict(template.tail_growth_ranges)

    def source_address(addresses: tuple[str, ...]) -> str:
        """Render mapped source cells in the same explicit form as the native mapper."""
        if len(addresses) == 1:
            return addresses[0]
        coordinates = [_cell_address_parts(address) for address in addresses]
        rows = {row for _column, row in coordinates}
        columns = [column for column, _row in coordinates]
        if len(rows) == 1 and columns == list(range(columns[0], columns[0] + len(columns))):
            return f"{addresses[0]}:{addresses[-1]}"
        return ",".join(addresses)

    first_row = min(row for _name, row in template.year_assumption_rows)
    last_row = max(row for _name, row in template.year_assumption_rows)
    for scenario, columns in template.scenario_columns:
        cells[f"scenarios.{scenario}.years"] = f"{columns[0]}{first_row}:{columns[-1]}{last_row}"
        cells[f"scenarios.{scenario}.rationale"] = template.scenario_rationale
        cells[f"scenarios.{scenario}.year10_ufcf_growth"] = source_address(year10_growth[scenario])
        if scenario in tail_growth:
            cells[f"scenarios.{scenario}.tail_ufcf_growth"] = tail_growth[scenario]
    return cells


def _cell_address_parts(address: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", address)
    if match is None:
        raise PackageError("PACKAGE_TEMPLATE_INVALID", "A model source cell is malformed.")
    column, row = match.groups()
    return _column_number(column), int(row)


def _template_range_cells(template: DcfModelTemplate) -> tuple[tuple[int, int, str], ...]:
    cells: dict[str, tuple[int, int, str]] = {}
    for bare_range in template.ranges:
        qualified = _a1_range(template.model_key, bare_range)
        for row, column, address in _a1_coordinates(qualified):
            if address in cells:
                raise PackageError("PACKAGE_TEMPLATE_INVALID", "A model template repeats a cell.")
            cells[address] = (row, column, address)
    if not cells or len(cells) > MAX_PACKAGE_CELLS:
        raise PackageError("PACKAGE_CELL_LIMIT_EXCEEDED", "The reviewed package scope is invalid.")
    return tuple(cells[key] for key in sorted(cells, key=lambda value: _cell_sort_key(value)))


def _cell_sort_key(address: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", address)
    if match is None:
        raise PackageError("PACKAGE_CELL_ADDRESS_INVALID", "A package cell address is invalid.")
    return int(match.group(2)), _column_number(match.group(1))


def _required_decimal(cells: Mapping[str, PackageCell], address: str) -> Decimal:
    cell = cells.get(address)
    if cell is None or cell.effective_value is None or cell.effective_value.kind != "NUMBER":
        raise PackageError(
            "PACKAGE_REQUIRED_CELL_UNAVAILABLE",
            f"A required numeric model input or output is unavailable at {address}.",
        )
    try:
        value = Decimal(cast(str, cell.effective_value.value))
    except Exception:
        raise PackageError(
            "PACKAGE_REQUIRED_CELL_UNAVAILABLE", "A required model value is not a valid decimal."
        ) from None
    if not value.is_finite():
        raise PackageError(
            "PACKAGE_REQUIRED_CELL_UNAVAILABLE", "A required model value is not finite."
        )
    return value


def _workbook_from_cells(
    model_key: str, cells: Mapping[str, PackageCell], payload_sha256: str
) -> Workbook:
    sheet: dict[str, Cell] = {}
    for address, item in cells.items():
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
            formula=(
                cast(str, entered.value)
                if entered is not None and entered.kind == "FORMULA"
                else None
            ),
            number_format_type=item.number_format_type,
            number_format_code=item.number_format_pattern,
        )
    return Workbook(
        path=Path(f"google-sheets-{model_key}-package.json"),
        sha256=payload_sha256,
        sheets={model_key: sheet},
        source_name="direct-google-sheets-dcf-package",
    )


def _mapped_model(
    template: DcfModelTemplate,
    cells: Mapping[str, PackageCell],
    effective_at: datetime,
    payload_sha256: str,
) -> tuple[Workbook, MappedModel, ProbabilityNormalization | None]:
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise PackageError("PACKAGE_CAPTURE_TIME_INVALID", "Use a timezone-aware timestamp.")
    normalized_probabilities, normalization = _normalized_source_probabilities(cells)
    workbook = _workbook_from_cells(template.model_key, cells, payload_sha256)
    sheet = workbook.sheets[template.model_key]
    for scenario, address in (("BEAR", "AO4"), ("BASE", "AO5"), ("BULL", "AO6")):
        if address not in sheet:
            raise PackageError(
                "PACKAGE_PROBABILITY_MISSING", "A required scenario probability is absent."
            )
        current = sheet[address]
        normalized_text = format(normalized_probabilities[scenario], "f")
        if current.value != normalized_text:
            sheet[address] = replace(current, value=normalized_text, kind="n")
    try:
        mapped = (
            _map_googl(workbook, effective_at.astimezone(UTC))
            if template.mapper == "GOOGL"
            else _map_portfolio_dcf(workbook, template.model_key, effective_at.astimezone(UTC))
        )
    except (KeyError, ValueError, ValidationError) as error:
        raise PackageError(
            "PACKAGE_INPUT_MAPPING_INVALID",
            f"The reviewed DCF mapping rejected its inputs ({type(error).__name__}).",
        ) from None
    if (
        mapped.model_key != template.model_key
        or mapped.company_name != template.company_name
        or mapped.ticker != template.ticker
        or mapped.venue != template.venue
        or mapped.model_currency != template.currency
        or mapped.model_type.value != "UFCF_DCF_10Y_FADE"
    ):
        raise PackageError(
            "PACKAGE_TEMPLATE_IDENTITY_MISMATCH",
            "The model did not match its reviewed exact identity and currency mapping.",
        )
    if not isinstance(mapped.values, schemas.FinancialModelRevisionCreate):
        raise PackageError("PACKAGE_METHOD_UNSUPPORTED", "The selected template is not a UFCF DCF.")
    if mapped.input_cell_map != _expected_input_cell_map(template):
        raise PackageError(
            "PACKAGE_TEMPLATE_MAPPING_MISMATCH",
            "The existing source mapper differs from the declarative model template.",
        )
    return workbook, mapped, normalization


def _validate_mapped_identity(
    package: DcfModelPackage,
    template: DcfModelTemplate,
    mapped: MappedModel,
) -> None:
    if not isinstance(mapped.values, schemas.FinancialModelRevisionCreate):
        raise PackageError("PACKAGE_METHOD_UNSUPPORTED", "The package mapper is not a native DCF.")
    expected_methodology = (
        "ufcf-dcf-explicit-tail-v1"
        if any(scenario.tail_ufcf_growth is not None for scenario in mapped.values.scenarios)
        else "ufcf-dcf-fade-v1"
    )
    identity = package.identity
    expected_values = {
        "source_model_key": template.model_key,
        "template_id": template.template_id,
        "template_version": template.template_version,
        "mapping_version": template.mapping_version,
        "company_name": mapped.company_name,
        "canonical_ticker": mapped.ticker,
        "listing_ticker": mapped.ticker,
        "listing_venue": mapped.venue,
        "security_type": mapped.security_type,
        "listing_currency": template.currency,
        "model_currency": mapped.model_currency,
        "model_type": "UFCF_DCF_10Y_FADE",
        "methodology_version": expected_methodology,
        "return_methodology_code": mapped.return_methodology_code,
        "economic_cash_flow_basis": mapped.legacy_return_basis,
        "return_perspective": "ENTERPRISE",
        "return_comparability": "NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR",
        "operating_value_unit": f"{template.currency}_BILLIONS",
        "share_count_unit": "BILLIONS_OF_SHARES",
        "per_share_unit": f"{template.currency}_PER_{mapped.ticker}_LISTING_SHARE",
        "legacy_return_semantics": mapped.legacy_return_semantics,
    }
    if any(getattr(identity, field) != value for field, value in expected_values.items()):
        raise PackageError(
            "PACKAGE_TEMPLATE_IDENTITY_MISMATCH",
            "Package metadata does not match the reviewed source-to-model mapping.",
        )


def _output_values(
    template: DcfModelTemplate, cells: Mapping[str, PackageCell]
) -> DcfPublishedOutputs:
    def number(address: str) -> Decimal:
        return _required_decimal(cells, address)

    projections: list[DcfPublishedProjection] = []
    projection_rows = dict(template.projection_rows)
    tail_columns = dict(template.projection_tail_columns)
    output_cells = dict(template.output_cells)
    package_scenario_order: tuple[Literal["BEAR", "BASE", "BULL"], ...] = (
        "BEAR",
        "BASE",
        "BULL",
    )
    for scenario in package_scenario_order:
        row = projection_rows[scenario]
        for year, column in enumerate(template.projection_value_columns, start=1):
            address = f"{column}{row}"
            projections.append(
                DcfPublishedProjection(
                    scenario=scenario,
                    forecast_year=year,
                    metric="present_value_ufcf",
                    source_cell=address,
                    currency=template.currency,
                    value=number(address),
                )
            )
        for year, row_number in enumerate(template.projection_tail_rows, start=6):
            address = f"{tail_columns[scenario]}{row_number}"
            projections.append(
                DcfPublishedProjection(
                    scenario=scenario,
                    forecast_year=year,
                    metric="unlevered_free_cash_flow",
                    source_cell=address,
                    currency=template.currency,
                    value=number(address),
                )
            )
    return DcfPublishedOutputs(
        currency=template.currency,
        parity_reference_price=number(output_cells["parity_reference_price"]),
        parity_reference_price_cell=output_cells["parity_reference_price"],
        bear_fair_value_per_share=number(output_cells["bear_fair_value_per_share"]),
        base_fair_value_per_share=number(output_cells["base_fair_value_per_share"]),
        bull_fair_value_per_share=number(output_cells["bull_fair_value_per_share"]),
        weighted_fair_value_per_share=number(output_cells["weighted_fair_value_per_share"]),
        weighted_upside=number(output_cells["weighted_upside"]),
        expected_cash_flow_irr=number(output_cells["expected_cash_flow_irr"]),
        hurdle=number(output_cells["hurdle"]),
        expected_excess=number(output_cells["expected_excess"]),
        projections=tuple(projections),
        return_stream=tuple(number(f"{column}212") for column in template.return_stream_columns),
    )


def build_dcf_model_package(
    template: DcfModelTemplate,
    *,
    source_metadata: Mapping[str, Any],
    structure: Mapping[str, Any],
    source_cells: dict[str, PackageCell],
    captured_at: datetime,
) -> DcfModelPackage:
    """Build and validate the strict package from one frozen typed cell set."""
    provisional_hash = "0" * 64
    workbook, mapped, normalization = _mapped_model(
        template, source_cells, captured_at, provisional_hash
    )
    if not isinstance(mapped.values, schemas.FinancialModelRevisionCreate):
        raise PackageError(
            "PACKAGE_METHOD_UNSUPPORTED", "Only native UFCF DCF revisions are supported."
        )
    inputs = schemas.DcfCalculationInput.model_validate(
        {
            "base": mapped.values.base.model_dump(),
            "scenarios": [scenario.model_dump() for scenario in mapped.values.scenarios],
        }
    )
    input_digest = _input_digest(mapped)
    methodology_version: Literal["ufcf-dcf-fade-v1", "ufcf-dcf-explicit-tail-v1"] = (
        "ufcf-dcf-explicit-tail-v1"
        if any(scenario.tail_ufcf_growth is not None for scenario in mapped.values.scenarios)
        else "ufcf-dcf-fade-v1"
    )
    if mapped.security_type != "COMMON_STOCK":
        raise PackageError(
            "PACKAGE_SECURITY_UNSUPPORTED", "The reviewed DCF package requires common stock."
        )
    if mapped.return_methodology_code not in {
        "UFCF_ENTERPRISE_IRR",
        "UFCF_ENTERPRISE_HMODEL_IRR",
    }:
        raise PackageError(
            "PACKAGE_RETURN_METHOD_UNSUPPORTED",
            "The reviewed DCF package has an unsupported enterprise return method.",
        )
    return_methodology_code: Literal["UFCF_ENTERPRISE_IRR", "UFCF_ENTERPRISE_HMODEL_IRR"] = cast(
        Literal["UFCF_ENTERPRISE_IRR", "UFCF_ENTERPRISE_HMODEL_IRR"],
        mapped.return_methodology_code,
    )
    identity = DcfPackageIdentity(
        source_model_key=template.model_key,
        template_id=template.template_id,
        template_version=template.template_version,
        mapping_version=template.mapping_version,
        company_name=mapped.company_name,
        canonical_ticker=mapped.ticker,
        listing_ticker=mapped.ticker,
        listing_venue=mapped.venue,
        security_type="COMMON_STOCK",
        listing_currency=template.currency,
        model_currency=mapped.model_currency,
        model_type="UFCF_DCF_10Y_FADE",
        methodology_version=methodology_version,
        return_methodology_code=return_methodology_code,
        economic_cash_flow_basis=mapped.legacy_return_basis,
        return_perspective="ENTERPRISE",
        return_comparability="NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR",
        operating_value_unit=f"{template.currency}_BILLIONS",
        share_count_unit="BILLIONS_OF_SHARES",
        per_share_unit=f"{template.currency}_PER_{mapped.ticker}_LISTING_SHARE",
        legacy_return_semantics=mapped.legacy_return_semantics,
    )
    package = DcfModelPackage(
        contract_version=CONTRACT_VERSION,
        identity=identity,
        revision=DcfPackageRevision(
            base_revision_id=None,
            external_revision_id=f"google-sheets:{template.model_key}:{input_digest}",
            input_sha256=input_digest,
            source_effective_at=None,
            author_identity=None,
            authored_at=None,
            acceptance_state="PROPOSAL_NOT_ACCEPTED",
        ),
        inputs=inputs,
        input_cell_map=dict(mapped.input_cell_map),
        published_outputs=_output_values(template, source_cells),
        source=DcfPackageSource(
            source_identity_sha256=str(source_metadata["source_identity_sha256"]),
            mime_type="application/vnd.google-apps.spreadsheet",
            modified_time=str(source_metadata["modified_time"]),
            drive_revision_id=source_metadata.get("head_revision_id"),
            drive_checksum=source_metadata.get("checksum"),
            spreadsheet_time_zone=(
                str(structure["time_zone"]) if isinstance(structure.get("time_zone"), str) else None
            ),
            sheet_id=int(structure["sheet_id"]),
            sheet_title=template.model_key,
            source_effective_at=None,
            capture_semantics="observed-consistent-state-not-transactional-snapshot",
            declared_ranges=_qualified_ranges(template),
        ),
        source_cells=source_cells,
        probability_normalization=normalization,
    )
    _validate_package_shape(package, template)
    _validate_mapped_identity(package, template, mapped)
    return package


def _validate_package_shape(package: DcfModelPackage, template: DcfModelTemplate) -> None:
    identity = package.identity
    expected_method = (
        "UFCF_ENTERPRISE_HMODEL_IRR" if template.model_key == "P-AMZN" else "UFCF_ENTERPRISE_IRR"
    )
    if (
        package.contract_version != CONTRACT_VERSION
        or identity.source_model_key != template.model_key
        or identity.template_id != template.template_id
        or identity.template_version != template.template_version
        or identity.mapping_version != template.mapping_version
        or identity.company_name != template.company_name
        or identity.canonical_ticker != template.ticker
        or identity.listing_ticker != template.ticker
        or identity.listing_venue != template.venue
        or identity.listing_currency != template.currency
        or identity.model_currency != template.currency
        or identity.model_type != "UFCF_DCF_10Y_FADE"
        or identity.return_methodology_code != expected_method
    ):
        raise PackageError(
            "PACKAGE_TEMPLATE_IDENTITY_MISMATCH",
            "Package identity does not match the selected reviewed DCF template.",
        )
    if package.source.sheet_title != template.model_key:
        raise PackageError(
            "PACKAGE_SOURCE_TAB_INVALID", "The source tab does not match the template."
        )
    expected_ranges = _qualified_ranges(template)
    if package.source.declared_ranges != expected_ranges:
        raise PackageError(
            "PACKAGE_RANGE_SCOPE_INVALID", "Package ranges differ from the template."
        )
    expected_cells = {item[2] for item in _template_range_cells(template)}
    if set(package.source_cells) != expected_cells:
        raise PackageError(
            "PACKAGE_CELL_SCOPE_INVALID",
            "Package cells differ from the exact reviewed template scope.",
        )
    if package.input_cell_map != _expected_input_cell_map(template):
        raise PackageError(
            "PACKAGE_TEMPLATE_MAPPING_MISMATCH",
            "Package field-to-cell mappings differ from the reviewed template.",
        )
    for address in template.required_formula_cells:
        cell = package.source_cells[address]
        if cell.user_entered_value is None or cell.user_entered_value.kind != "FORMULA":
            raise PackageError(
                "PACKAGE_TEMPLATE_SIGNATURE_MISMATCH",
                "A required published-output or template formula is absent.",
            )
    _output_values(template, package.source_cells)


def validate_dcf_model_package(
    package: DcfModelPackage,
    payload_sha256: str,
    *,
    validated_at: datetime | None = None,
) -> DcfModelPackageValidation:
    if not HASH_PATTERN.fullmatch(payload_sha256):
        raise PackageError("PACKAGE_HASH_INVALID", "The package hash is invalid.")
    template = get_dcf_model_template(package.identity.source_model_key)
    _validate_package_shape(package, template)
    canonical = _strict_json(package.model_dump(mode="json")).encode("utf-8")
    if _sha256(canonical) != payload_sha256:
        raise PackageError("PACKAGE_HASH_MISMATCH", "The package payload hash is invalid.")
    timestamp = validated_at or datetime.now(UTC)
    workbook, mapped, normalization = _mapped_model(
        template, package.source_cells, timestamp, payload_sha256
    )
    if normalization != package.probability_normalization:
        raise PackageError(
            "PACKAGE_PROBABILITY_NORMALIZATION_MISMATCH",
            "Recorded probability normalization does not match source evidence.",
        )
    if not isinstance(mapped.values, schemas.FinancialModelRevisionCreate):
        raise PackageError("PACKAGE_METHOD_UNSUPPORTED", "The package mapper is not a native DCF.")
    mapped_inputs = schemas.DcfCalculationInput.model_validate(
        {
            "base": mapped.values.base.model_dump(),
            "scenarios": [scenario.model_dump() for scenario in mapped.values.scenarios],
        }
    )
    if mapped_inputs.model_dump(mode="json") != package.inputs.model_dump(mode="json"):
        raise PackageError(
            "PACKAGE_INPUT_SOURCE_MISMATCH",
            "Package inputs do not match their preserved source cells.",
        )
    if _input_digest(mapped) != package.revision.input_sha256:
        raise PackageError("PACKAGE_INPUT_DIGEST_MISMATCH", "The model input digest is invalid.")
    if package.revision.external_revision_id != (
        f"google-sheets:{template.model_key}:{package.revision.input_sha256}"
    ):
        raise PackageError("PACKAGE_REVISION_ID_INVALID", "The source revision ID is invalid.")
    _validate_mapped_identity(package, template, mapped)
    if _output_values(template, package.source_cells).model_dump(mode="json") != (
        package.published_outputs.model_dump(mode="json")
    ):
        raise PackageError(
            "PACKAGE_OUTPUT_SOURCE_MISMATCH", "Published outputs do not match source cells."
        )
    try:
        reconciliation = _reconcile_model(workbook, mapped)
    except (KeyError, ValueError, StopIteration) as error:
        raise PackageError(
            "PACKAGE_PARITY_CALCULATION_FAILED",
            f"Native DCF reconciliation failed ({type(error).__name__}).",
        ) from None
    report = {
        "contract_version": CONTRACT_VERSION,
        "template_id": template.template_id,
        "template_version": template.template_version,
        "model_key": template.model_key,
        "payload_sha256": payload_sha256,
        "source_identity_sha256": package.source.source_identity_sha256,
        "source_revision_id": package.source.drive_revision_id,
        "source_effective_at": None,
        "methodology_version": package.identity.methodology_version,
        "return_methodology_code": package.identity.return_methodology_code,
        "return_comparability": package.identity.return_comparability,
        "source_cell_count": len(package.source_cells),
        "projection_reconciliation": reconciliation["projection_reconciliation"],
        "output_reconciliation": reconciliation["output_reconciliation"],
        "status": reconciliation["status"],
        "acceptance_state": package.revision.acceptance_state,
    }
    return DcfModelPackageValidation(package, payload_sha256, mapped, report)


def _a1_values_for_api(template: DcfModelTemplate) -> tuple[tuple[str, int], ...]:
    results: list[tuple[str, int]] = []
    for bare_range in template.ranges:
        qualified = _a1_range(template.model_key, bare_range)
        results.append((qualified, len(_a1_coordinates(qualified))))
    return tuple(results)


class DcfModelPackageStore:
    """Private, content-addressed v2 blobs with append-only capture manifests."""

    def __init__(self, root: Path) -> None:
        self.store = SnapshotStore(root / PACKAGE_DIRECTORY)
        self.root = self.store.root
        self.blob_root = self.store.blob_root
        self.report_root = self.root / "reports"
        if self.report_root.is_symlink():
            raise PackageError("PACKAGE_STORE_INVALID", "The private report path is invalid.")
        self.report_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with suppress(OSError):
            self.report_root.chmod(0o700)

    def capture(
        self,
        package: DcfModelPackage,
        *,
        captured_at: datetime,
        request_count: int,
        logical_request_count: int,
    ) -> DcfModelPackageRun:
        payload = _strict_json(package.model_dump(mode="json")).encode("utf-8")
        digest = _sha256(payload)
        blob = self.blob_root / f"{digest}.json"
        if blob.exists():
            if blob.is_symlink() or not blob.is_file() or _sha256(blob.read_bytes()) != digest:
                raise PackageError(
                    "PACKAGE_BLOB_CORRUPTED", "A stored package blob failed its hash check."
                )
        else:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".dcf-package-", dir=self.blob_root
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, blob)
                except FileExistsError:
                    if (
                        blob.is_symlink()
                        or not blob.is_file()
                        or _sha256(blob.read_bytes()) != digest
                    ):
                        raise PackageError(
                            "PACKAGE_BLOB_CORRUPTED", "A concurrent blob failed its hash check."
                        ) from None
                with suppress(OSError):
                    blob.chmod(0o600)
            finally:
                if temporary.exists():
                    temporary.unlink()
        run_id = uuid4().hex
        manifest: dict[str, Any] = {
            "run_id": run_id,
            "contract_version": CONTRACT_VERSION,
            "status": "CAPTURED_REVIEW_REQUIRED",
            "review_required": True,
            "captured_at": captured_at.astimezone(UTC).isoformat(),
            "payload_sha256": digest,
            "payload_path": f"blobs/sha256/{digest}.json",
            "source_identity_sha256": package.source.source_identity_sha256,
            "source_modified_at": package.source.modified_time,
            "drive_revision_id": package.source.drive_revision_id,
            "model_key": package.identity.source_model_key,
            "template_id": package.identity.template_id,
            "source_cell_count": len(package.source_cells),
            "range_count": len(package.source.declared_ranges),
            "request_count": request_count,
            "logical_request_count": logical_request_count,
            "capture_semantics": package.source.capture_semantics,
        }
        manifest["manifest_sha256"] = _manifest_digest(manifest)
        try:
            self.store._write_manifest(manifest)
        except Exception as error:
            raise PackageError(
                "PACKAGE_MANIFEST_WRITE_FAILED", "The private capture manifest failed."
            ) from error
        return DcfModelPackageRun(run_id, digest, manifest, package)

    def load(self, run_id: str, expected_sha256: str | None = None) -> DcfModelPackageRun:
        if not RUN_PATTERN.fullmatch(run_id):
            raise PackageError("PACKAGE_RUN_ID_INVALID", "Use a valid package run ID.")
        try:
            manifest = self.store.manifest(run_id)
        except Exception:
            raise PackageError("PACKAGE_RUN_NOT_FOUND", "The package run was not found.") from None
        digest = manifest.get("payload_sha256")
        if (
            manifest.get("contract_version") != CONTRACT_VERSION
            or manifest.get("status") != "CAPTURED_REVIEW_REQUIRED"
            or manifest.get("review_required") is not True
            or manifest.get("manifest_sha256") != _manifest_digest(manifest)
            or not isinstance(digest, str)
            or not HASH_PATTERN.fullmatch(digest)
            or (expected_sha256 is not None and digest != expected_sha256)
        ):
            raise PackageError(
                "PACKAGE_MANIFEST_INVALID", "The v2 package manifest failed validation."
            )
        relative = f"blobs/sha256/{digest}.json"
        if manifest.get("payload_path") != relative:
            raise PackageError("PACKAGE_PATH_INVALID", "The v2 package path is invalid.")
        path = self.root / relative
        if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != digest:
            raise PackageError(
                "PACKAGE_HASH_MISMATCH", "The stored v2 package failed its hash check."
            )
        payload = path.read_bytes()
        try:
            package = DcfModelPackage.model_validate_json(payload)
        except ValidationError as error:
            raise PackageError(
                "PACKAGE_SCHEMA_INVALID", _sanitized_validation_error(error)
            ) from None
        if _strict_json(package.model_dump(mode="json")).encode("utf-8") != payload:
            raise PackageError("PACKAGE_ENCODING_INVALID", "The package is not canonical JSON.")
        if (
            package.source.source_identity_sha256 != manifest.get("source_identity_sha256")
            or package.identity.source_model_key != manifest.get("model_key")
            or package.identity.template_id != manifest.get("template_id")
        ):
            raise PackageError(
                "PACKAGE_PROVENANCE_MISMATCH", "Package provenance did not match its manifest."
            )
        return DcfModelPackageRun(run_id, digest, manifest, package)

    def write_report(self, name: str, report: Mapping[str, Any]) -> Path:
        target = self.report_root / f"{name}-{uuid4().hex}.json"
        payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
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


@dataclass(frozen=True)
class DcfCaptureResult:
    package: DcfModelPackage
    payload_sha256: str
    source_stable: bool
    validation: DcfModelPackageValidation
    request_count: int
    logical_request_count: int
    stored_run: DcfModelPackageRun | None


class DcfModelPackageExporter:
    """Capture only model keys present in the reviewed template registry."""

    def __init__(
        self,
        settings: Settings,
        store: DcfModelPackageStore,
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
        self._logical_requests = 0
        self.reader.request_attempt_count = 0

    def _structure(self, template: DcfModelTemplate) -> dict[str, Any]:
        url = f"{SHEETS_API}/{quote(self.reader.spreadsheet_id, safe='')}"
        response = self.reader._get_json(url, {"fields": STRUCTURE_FIELDS})
        self._logical_requests += 1
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
        matches = [
            item.get("properties")
            for item in sheets
            if isinstance(item, dict)
            and isinstance(item.get("properties"), dict)
            and item["properties"].get("title") == template.model_key
        ]
        if len(matches) != 1:
            raise PackageError(
                "PACKAGE_SOURCE_TAB_INVALID", "The exact reviewed model tab is not unique."
            )
        sheet = matches[0]
        if not isinstance(sheet, dict):
            raise PackageError(
                "PACKAGE_STRUCTURE_INVALID", "The reviewed model worksheet structure is invalid."
            )
        grid = sheet.get("gridProperties")
        sheet_id = sheet.get("sheetId")
        if (
            not isinstance(grid, dict)
            or isinstance(sheet_id, bool)
            or not isinstance(sheet_id, int)
            or isinstance(grid.get("rowCount"), bool)
            or not isinstance(grid.get("rowCount"), int)
            or isinstance(grid.get("columnCount"), bool)
            or not isinstance(grid.get("columnCount"), int)
            or grid["rowCount"] < template.min_row_count
            or grid["columnCount"] < template.min_column_count
        ):
            raise PackageError(
                "PACKAGE_SOURCE_TAB_INVALID", "The model tab dimensions are incompatible."
            )
        return {
            "sheet_id": sheet_id,
            "sheet_title": template.model_key,
            "row_count": grid["rowCount"],
            "column_count": grid["columnCount"],
            "time_zone": time_zone if isinstance(time_zone, str) else None,
        }

    def _sweep(self, template: DcfModelTemplate) -> dict[str, PackageCell]:
        ranges = _a1_values_for_api(template)
        result: dict[str, PackageCell] = {}
        for a1_range, area in ranges:
            if self._logical_requests >= MAX_PACKAGE_CALLS:
                raise PackageError(
                    "PACKAGE_REQUEST_LIMIT_EXCEEDED", "The bounded request budget was exceeded."
                )
            response = self.reader._get_json(
                f"{SHEETS_API}/{quote(self.reader.spreadsheet_id, safe='')}",
                {"ranges": a1_range, "includeGridData": "true", "fields": CELL_FIELDS},
            )
            self._logical_requests += 1
            if response.get("spreadsheetId") != self.reader.spreadsheet_id:
                raise PackageError(
                    "PACKAGE_SOURCE_IDENTITY_MISMATCH", "Sheets returned another spreadsheet."
                )
            try:
                values, _formats, sheets, presence, stats = _cell_grid_index(
                    response, [(template.model_key, a1_range, area)]
                )
            except ValueError as error:
                raise PackageError(
                    "PACKAGE_RANGE_INCOMPLETE",
                    f"A requested model range failed validation ({type(error).__name__}).",
                ) from None
            if template.model_key not in sheets or stats["coordinates_covered"] != area:
                raise PackageError(
                    "PACKAGE_RANGE_INCOMPLETE", "A requested model range was not fully returned."
                )
            for row, column, address in _a1_coordinates(a1_range):
                raw = values[template.model_key].get((row, column))
                if raw is None or address in result:
                    raise PackageError(
                        "PACKAGE_RANGE_INCOMPLETE",
                        "A requested model cell is absent or duplicated.",
                    )
                result[address] = _package_cell(raw, presence[template.model_key][(row, column)])
        expected = {item[2] for item in _template_range_cells(template)}
        if set(result) != expected:
            raise PackageError(
                "PACKAGE_CELL_SCOPE_INVALID", "The captured cell scope differs from the template."
            )
        for address in template.required_formula_cells:
            cell = result[address]
            if cell.user_entered_value is None or cell.user_entered_value.kind != "FORMULA":
                raise PackageError(
                    "PACKAGE_TEMPLATE_SIGNATURE_MISMATCH", "A required template formula is absent."
                )
        return result

    def capture(self, model_key: str, *, dry_run: bool = False) -> DcfCaptureResult:
        try:
            template = get_dcf_model_template(model_key)
        except ValueError:
            raise PackageError(
                "PACKAGE_TEMPLATE_UNSUPPORTED", "No reviewed template supports that model key."
            ) from None
        captured_at = self.clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise PackageError(
                "PACKAGE_CAPTURE_TIME_INVALID", "The capture clock must be timezone-aware."
            )
        self._logical_requests = 0
        self.reader.request_attempt_count = 0
        if len(template.ranges) * 2 + 4 > MAX_PACKAGE_CALLS:
            raise PackageError(
                "PACKAGE_REQUEST_LIMIT_EXCEEDED",
                "The reviewed template exceeds the fixed request budget.",
            )
        source_cells_count = len(_template_range_cells(template))
        if source_cells_count > MAX_PACKAGE_CELLS:
            raise PackageError(
                "PACKAGE_CELL_LIMIT_EXCEEDED",
                "The reviewed template exceeds the fixed cell budget.",
            )
        try:
            before_metadata = self.reader._drive_metadata()
            self._logical_requests += 1
            before_structure = self._structure(template)
            first = self._sweep(template)
            second = self._sweep(template)
            after_structure = self._structure(template)
            after_metadata = self.reader._drive_metadata()
            self._logical_requests += 1
        except SheetsPortfolioError as error:
            raise PackageError(error.code, str(error)) from None
        first_json = _strict_json(
            {key: value.model_dump(mode="json") for key, value in first.items()}
        )
        second_json = _strict_json(
            {key: value.model_dump(mode="json") for key, value in second.items()}
        )
        source_stable = (
            before_metadata == after_metadata
            and before_structure == after_structure
            and first_json == second_json
        )
        if not source_stable:
            raise PackageError(
                "PACKAGE_SOURCE_CHANGED_DURING_CAPTURE",
                "The source metadata, model structure, values, or formulas changed during capture.",
            )
        package = build_dcf_model_package(
            template,
            source_metadata=before_metadata,
            structure=before_structure,
            source_cells=first,
            captured_at=captured_at.astimezone(UTC),
        )
        payload = _strict_json(package.model_dump(mode="json")).encode("utf-8")
        payload_hash = _sha256(payload)
        validation = validate_dcf_model_package(package, payload_hash, validated_at=captured_at)
        if validation.parity_report["status"] != "PARITY_PASS":
            raise PackageError(
                "PACKAGE_PARITY_FAILED",
                "The live model does not reconcile with the existing deterministic DCF engine.",
            )
        stored = None
        if not dry_run:
            stored = self.store.capture(
                package,
                captured_at=captured_at.astimezone(UTC),
                request_count=self.reader.request_attempt_count,
                logical_request_count=self._logical_requests,
            )
        return DcfCaptureResult(
            package=package,
            payload_sha256=payload_hash,
            source_stable=source_stable,
            validation=validation,
            request_count=self.reader.request_attempt_count,
            logical_request_count=self._logical_requests,
            stored_run=stored,
        )


def _default_store_root() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "PortfolioResearch" / "workbook-snapshots"
    return Path.home() / ".portfolio-research" / "workbook-snapshots"


def _summary(run: DcfModelPackageRun | DcfCaptureResult) -> dict[str, Any]:
    package = run.package
    if isinstance(run, DcfModelPackageRun):
        request_count = run.manifest.get("request_count")
        logical_request_count = run.manifest.get("logical_request_count")
    else:
        request_count = run.request_count
        logical_request_count = run.logical_request_count
    return {
        "status": (
            "CAPTURED_REVIEW_REQUIRED"
            if isinstance(run, DcfModelPackageRun)
            else "DRY_RUN_VALIDATED"
        ),
        "run_id": run.run_id if isinstance(run, DcfModelPackageRun) else None,
        "payload_sha256": run.payload_sha256,
        "contract_version": CONTRACT_VERSION,
        "model_key": package.identity.source_model_key,
        "template_id": package.identity.template_id,
        "methodology_version": package.identity.methodology_version,
        "return_methodology_code": package.identity.return_methodology_code,
        "model_currency": package.identity.model_currency,
        "listing": f"{package.identity.listing_venue}:{package.identity.listing_ticker}",
        "source_cell_count": len(package.source_cells),
        "source_range_count": len(package.source.declared_ranges),
        "acceptance_state": package.revision.acceptance_state,
        "base_revision_present": package.revision.base_revision_id is not None,
        "source_stable": run.source_stable if isinstance(run, DcfCaptureResult) else None,
        "parity_status": (
            run.validation.parity_report["status"] if isinstance(run, DcfCaptureResult) else None
        ),
        "request_count": request_count,
        "logical_request_count": logical_request_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--model-key", required=True, choices=tuple(DCF_MODEL_TEMPLATES))
    capture.add_argument("--store", type=Path)
    capture.add_argument("--dry-run", action="store_true")
    capture.add_argument("--confirm-read-only-source-capture", action="store_true")
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--store", type=Path)
    inspect.add_argument("--run-id", required=True)
    inspect.add_argument("--payload-sha256", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--store", type=Path)
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--payload-sha256", required=True)
    args = parser.parse_args(argv)
    store = DcfModelPackageStore(args.store or _default_store_root())
    try:
        if args.command == "capture":
            if not args.confirm_read_only_source_capture:
                raise PackageError(
                    "PACKAGE_CAPTURE_CONFIRMATION_REQUIRED",
                    "Pass the read-only capture confirmation flag.",
                )
            result = DcfModelPackageExporter(Settings(), store).capture(
                args.model_key, dry_run=args.dry_run
            )
            if args.dry_run:
                print(json.dumps(_summary(result), sort_keys=True))
            else:
                assert result.stored_run is not None
                print(json.dumps(_summary(result.stored_run), sort_keys=True))
            return 0
        package_run = store.load(args.run_id, args.payload_sha256)
        if args.command == "inspect":
            print(json.dumps(_summary(package_run), sort_keys=True))
            return 0
        validation = validate_dcf_model_package(package_run.package, package_run.payload_sha256)
        report_path = store.write_report("validation", validation.parity_report)
        report = validation.parity_report
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "model_key": report["model_key"],
                    "payload_sha256": package_run.payload_sha256,
                    "projection_checks": report["projection_reconciliation"]["passed"],
                    "output_checks": report["output_reconciliation"]["passed"],
                    "private_report": str(report_path),
                },
                sort_keys=True,
            )
        )
        return 0 if report["status"] == "PARITY_PASS" else 2
    except (PackageError, SheetsPortfolioError, ValidationError, ValueError) as error:
        code = (
            error.code
            if isinstance(error, (PackageError, SheetsPortfolioError))
            else "PACKAGE_INVALID"
        )
        print(f"{code}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
