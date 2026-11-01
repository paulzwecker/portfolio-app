"""Bounded, read-only comparison of one frozen XLSX export with live Sheets values."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from portfolio_api.legacy_import import Workbook
from portfolio_api.settings import Settings
from portfolio_api.workbook_semantics import (
    SEMANTIC_FINGERPRINT_VERSION,
    NormalizedCellValue,
    SemanticMode,
    importer_empty_value_policy,
    importer_field_semantics,
    importer_source_role,
    importer_source_value_policy,
    importer_value_cells,
    live_cell_normalization,
    normalize_source_cell,
)
from portfolio_api.workbook_sources import (
    DRIVE_FILES_API,
    GOOGLE_SHEET_MIME,
    PORTFOLIO_PROFILE,
    SnapshotStore,
    WorkbookSourceError,
    _google_source,
)

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
MAX_RANGES_PER_REQUEST = 60
MAX_CELLS_PER_REQUEST = 8_000
# A whole comparison is fenced by one metadata read before both value sweeps and one
# metadata read after them. These are per-comparison ceilings, not sample sizes.
# Exceeding any ceiling blocks before live value requests.
MAX_VALIDATION_CONTRACT_CELLS = 30_000
MAX_VALIDATION_REQUESTED_CELLS_PER_PASS = 60_000
MAX_VALIDATION_RANGES = 4_000
MAX_VALIDATION_CHUNKS_PER_PASS = 70
REQUEST_SPACING_SECONDS = 1.05
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
ValidationScope = Literal["canonical-bootstrap", "optional-model-research", "all-importers"]
COMPARISON_REPORT_VERSION = 6
COMPARISON_CONTRACT_VERSION = "portfolio-live-value-comparison-v6"
EXCEPTION_LEDGER_VERSION = 1

CANONICAL_BOOTSTRAP_DOMAINS = frozenset(
    {
        "identity_lifecycle_and_cached_ranks",
        "holdings_and_cash",
        "strategic_targets",
        "quality_assessments",
        "listing_identity_crosswalk",
        "research_priority_inputs",
        "investment_scores",
    }
)
OPTIONAL_MODEL_RESEARCH_DOMAINS = frozenset(
    {
        "published_model_outputs",
        "published_model_output_currency",
        "published_model_output_history",
        "legacy_estimate_history",
    }
)


class ValueComparisonError(ValueError):
    """Sanitized failure while comparing a reviewed frozen source snapshot."""


class ProjectionReadError(ValueComparisonError):
    """A bounded live-range request failed, with sanitized progress attached."""

    def __init__(self, message: str, progress: dict[str, int]) -> None:
        super().__init__(message)
        self.progress = progress


def _column_number(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - 64
    return result


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_position(address: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", address)
    if match is None:
        raise ValueComparisonError("The importer contract contains an invalid cell address.")
    return int(match.group(2)), _column_number(match.group(1))


def _ranges_for_workbook(
    workbook: Workbook,
    definitions: Sequence[Any] | None = None,
) -> list[tuple[str, str, int]]:
    """Create deterministic compact ranges for the selected importer-owned cells."""
    positions: dict[str, set[tuple[int, int]]] = defaultdict(set)
    selected_definitions = (
        definitions if definitions is not None else importer_value_cells(workbook)
    )
    for item in selected_definitions:
        positions[item.sheet].add(_cell_position(item.address))

    result: list[tuple[str, str, int]] = []
    for sheet, cells in sorted(positions.items()):
        columns_by_row: dict[int, list[int]] = defaultdict(list)
        for row, column in cells:
            columns_by_row[row].append(column)
        row_segments: list[tuple[int, int, int, int]] = []
        for row, columns in sorted(columns_by_row.items()):
            ordered = sorted(set(columns))
            start = previous = ordered[0]
            for column in ordered[1:]:
                if column != previous + 1:
                    row_segments.append((row, start, row, previous))
                    start = column
                previous = column
            row_segments.append((row, start, row, previous))

        merged: list[tuple[int, int, int, int]] = []
        for row_start, col_start, row_end, col_end in row_segments:
            if (
                merged
                and merged[-1][1] == col_start
                and merged[-1][3] == col_end
                and merged[-1][2] + 1 == row_start
            ):
                prior = merged[-1]
                merged[-1] = (prior[0], prior[1], row_end, prior[3])
            else:
                merged.append((row_start, col_start, row_end, col_end))

        escaped_sheet = "'" + sheet.replace("'", "''") + "'"
        for row_start, col_start, row_end, col_end in merged:
            width = col_end - col_start + 1
            rows_per_range = max(1, MAX_CELLS_PER_REQUEST // width)
            for chunk_start in range(row_start, row_end + 1, rows_per_range):
                chunk_end = min(row_end, chunk_start + rows_per_range - 1)
                start_cell = f"{_column_name(col_start)}{chunk_start}"
                end_cell = f"{_column_name(col_end)}{chunk_end}"
                area = (chunk_end - chunk_start + 1) * width
                result.append((sheet, f"{escaped_sheet}!{start_cell}:{end_cell}", area))
    return result


def _definitions_for_scope(workbook: Workbook, scope: ValidationScope) -> list[Any]:
    all_definitions = importer_value_cells(workbook)
    all_domains = {item.domain for item in all_definitions}
    known_domains = CANONICAL_BOOTSTRAP_DOMAINS | OPTIONAL_MODEL_RESEARCH_DOMAINS
    unknown_domains = all_domains - known_domains
    if unknown_domains:
        raise ValueComparisonError(
            "The importer contract includes an unclassified validation domain; comparison blocked."
        )
    if scope == "all-importers":
        return all_definitions
    if scope == "canonical-bootstrap":
        return [item for item in all_definitions if item.domain in CANONICAL_BOOTSTRAP_DOMAINS]
    if scope == "optional-model-research":
        return [item for item in all_definitions if item.domain in OPTIONAL_MODEL_RESEARCH_DOMAINS]
    raise ValueComparisonError("Unsupported workbook comparison scope.")


def _validation_plan(workbook: Workbook, scope: ValidationScope) -> dict[str, Any]:
    """Build the entire deterministic work plan and enforce the per-run budget pre-network."""
    definitions = _definitions_for_scope(workbook, scope)
    ranges = _ranges_for_workbook(workbook, definitions)
    groups = _group_ranges(ranges)
    requested_cells = sum(item[2] for item in ranges)
    metrics: dict[str, Any] = {
        "scope": scope,
        "scope_domains": sorted({item.domain for item in definitions}),
        "required_cells": len(definitions),
        "ranges": len(ranges),
        "chunks_per_pass": len(groups),
        "estimated_value_requests": 2 * len(groups),
        "metadata_requests": 2,
        "estimated_total_requests": 2 * len(groups) + 2,
        "maximum_http_attempts_including_retries": (
            2 * len(groups) * MAX_RETRIES + 2 * MAX_RETRIES
        ),
        "ranges_per_request_limit": MAX_RANGES_PER_REQUEST,
        "requested_cells_per_request_limit": MAX_CELLS_PER_REQUEST,
        "requested_cells_per_pass": requested_cells,
        "optional_model_research_cells_excluded": (
            sum(
                item.domain in OPTIONAL_MODEL_RESEARCH_DOMAINS
                for item in importer_value_cells(workbook)
            )
            if scope == "canonical-bootstrap"
            else 0
        ),
    }
    exceeded = {
        "contract_cells": metrics["required_cells"] > MAX_VALIDATION_CONTRACT_CELLS,
        "requested_cells_per_pass": (requested_cells > MAX_VALIDATION_REQUESTED_CELLS_PER_PASS),
        "ranges": len(ranges) > MAX_VALIDATION_RANGES,
        "chunks_per_pass": len(groups) > MAX_VALIDATION_CHUNKS_PER_PASS,
    }
    limits = {
        "contract_cells": MAX_VALIDATION_CONTRACT_CELLS,
        "requested_cells_per_pass": MAX_VALIDATION_REQUESTED_CELLS_PER_PASS,
        "ranges": MAX_VALIDATION_RANGES,
        "chunks_per_pass": MAX_VALIDATION_CHUNKS_PER_PASS,
    }
    metrics["work_budget_limits"] = limits
    metrics["work_budget_exceeded"] = [key for key, value in exceeded.items() if value]
    return {"definitions": definitions, "ranges": ranges, "groups": groups, "metrics": metrics}


def _group_ranges(
    ranges: list[tuple[str, str, int]],
) -> list[list[tuple[str, str, int]]]:
    deduplicated: dict[tuple[str, str], tuple[str, str, int]] = {}
    for item in ranges:
        sheet, address, area = item
        if area <= 0:
            raise ValueComparisonError("The importer contract generated an empty range.")
        key = (sheet, address)
        prior = deduplicated.get(key)
        if prior is not None and prior[2] != area:
            raise ValueComparisonError("Duplicate importer ranges have conflicting dimensions.")
        deduplicated[key] = item

    def sort_key(item: tuple[str, str, int]) -> tuple[Any, ...]:
        sheet, address, _area = item
        match = re.search(r"!([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)$", address)
        if match is None:
            raise ValueComparisonError("The importer contract generated an invalid A1 range.")
        start_column, start_row, end_column, end_row = match.groups()
        return (
            sheet,
            int(start_row),
            _column_number(start_column),
            int(end_row),
            _column_number(end_column),
        )

    ordered_ranges = sorted(deduplicated.values(), key=sort_key)
    groups: list[list[tuple[str, str, int]]] = []
    current: list[tuple[str, str, int]] = []
    current_cells = 0
    for item in ordered_ranges:
        if item[2] > MAX_CELLS_PER_REQUEST:
            raise ValueComparisonError(
                "A single importer range exceeds the per-request Google Sheets cell limit."
            )
        if current and (
            len(current) >= MAX_RANGES_PER_REQUEST
            or current_cells + item[2] > MAX_CELLS_PER_REQUEST
        ):
            groups.append(current)
            current = []
            current_cells = 0
        current.append(item)
        current_cells += item[2]
    if current:
        groups.append(current)
    return groups


def _metadata(
    session: Any,
    file_id: str,
    *,
    on_request: Callable[[], None] | None = None,
) -> dict[str, Any]:
    url = f"{DRIVE_FILES_API}/{quote(file_id, safe='')}"
    response = _get_with_retry(
        session,
        url,
        params={"fields": "id,mimeType,modifiedTime,headRevisionId,md5Checksum"},
        on_request=on_request,
    )
    if response.status_code != 200:
        raise ValueComparisonError(f"Google Drive metadata returned HTTP {response.status_code}.")
    try:
        value = response.json()
    except (TypeError, ValueError) as error:
        raise ValueComparisonError("Google Drive returned invalid metadata.") from error
    if not isinstance(value, dict) or value.get("id") != file_id:
        raise ValueComparisonError(
            "Google Drive metadata did not match the configured source identity."
        )
    return value


def _get_with_retry(
    session: Any,
    url: str,
    *,
    params: Any,
    on_request: Callable[[], None] | None = None,
) -> Any:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if on_request is not None:
                on_request()
            response = session.get(url, params=params, timeout=(5, REQUEST_TIMEOUT_SECONDS))
        except Exception as error:
            if attempt == MAX_RETRIES:
                raise ValueComparisonError(
                    "Google APIs could not be reached after bounded retries; "
                    "check the configured network proxy."
                ) from error
            time.sleep(min(2.0, 0.25 * 2 ** (attempt - 1)))
            continue
        if response.status_code in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
            retry_after = next(
                (
                    value
                    for key, value in response.headers.items()
                    if key.casefold() == "retry-after"
                ),
                None,
            )
            try:
                delay = (
                    min(60.0, max(REQUEST_SPACING_SECONDS, float(retry_after)))
                    if retry_after
                    else max(REQUEST_SPACING_SECONDS, 0.25 * 2 ** (attempt - 1))
                )
            except ValueError:
                delay = max(REQUEST_SPACING_SECONDS, 0.25 * 2 ** (attempt - 1))
            time.sleep(delay)
            continue
        return response
    raise ValueComparisonError("Google API retry limit was reached.")


def _parse_requested_range(
    requested: tuple[str, str, int],
) -> tuple[str, int, int, int, int]:
    sheet, address, expected_area = requested
    match = re.fullmatch(r"'((?:[^']|'')+)'!([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)", address)
    if match is None:
        raise ValueComparisonError("The importer contract contains an invalid requested range.")
    range_sheet = match.group(1).replace("''", "'")
    start_column = _column_number(match.group(2))
    start_row = int(match.group(3))
    end_column = _column_number(match.group(4))
    end_row = int(match.group(5))
    area = (end_row - start_row + 1) * (end_column - start_column + 1)
    if (
        range_sheet != sheet
        or start_row < 1
        or end_row < start_row
        or end_column < start_column
        or area != expected_area
    ):
        raise ValueComparisonError("The importer contract contains inconsistent range bounds.")
    return sheet, start_row, start_column, end_row, end_column


def _response_grid_index(value: Any, *, default: int = 0) -> int:
    if value is None:
        # GridData uses zero-based integer coordinates. The REST JSON encoding may
        # omit a default zero field, so absence means zero; a nonzero requested
        # origin still fails the exact-origin check below if its coordinate is absent.
        return default
    if isinstance(value, bool):
        raise ValueComparisonError("Google Sheets returned malformed grid coordinates.")
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueComparisonError("Google Sheets returned malformed grid coordinates.")
        return int(value)
    if isinstance(value, int):
        return value
    raise ValueComparisonError("Google Sheets returned malformed grid coordinates.")


def _cell_grid_index(
    response: dict[str, Any],
    requested_ranges: list[tuple[str, str, int]],
) -> tuple[
    dict[str, dict[tuple[int, int], dict[str, Any]]],
    dict[str, dict[tuple[int, int], str | None]],
    set[str],
    dict[str, dict[tuple[int, int], str]],
    dict[str, int],
]:
    """Index coordinates in requested ranges with a matching GridData envelope.

    Sheets may omit default-zero origins and trailing empty RowData/CellData entries.
    Omitted cells are represented as verified absence only when the corresponding
    requested range envelope is present and its returned data is structurally valid.
    Dimension metadata is optional and is validated when supplied.
    """
    values: dict[str, dict[tuple[int, int], dict[str, Any]]] = defaultdict(dict)
    formats: dict[str, dict[tuple[int, int], str | None]] = defaultdict(dict)
    presence: dict[str, dict[tuple[int, int], str]] = defaultdict(dict)
    present_sheets: set[str] = set()
    stats = {
        "grid_ranges_confirmed": 0,
        "coordinates_covered": 0,
        "cell_data_returned": 0,
        "omitted_cell_data_reconstructed": 0,
    }
    expected: dict[tuple[str, int, int], tuple[str, int, int, int, int]] = {}
    for requested in requested_ranges:
        sheet, start_row, start_column, end_row, end_column = _parse_requested_range(requested)
        key = (sheet, start_row, start_column)
        if key in expected:
            raise ValueComparisonError("The importer contract contains duplicate range origins.")
        expected[key] = (sheet, start_row, start_column, end_row, end_column)

    sheets_payload = response.get("sheets")
    if not isinstance(sheets_payload, list):
        raise ValueComparisonError("Google Sheets returned an incomplete range response.")
    returned_grids: dict[tuple[str, int, int], dict[str, Any]] = {}
    for sheet in sheets_payload:
        if not isinstance(sheet, dict):
            raise ValueComparisonError("Google Sheets returned malformed sheet data.")
        properties = sheet.get("properties", {})
        title = properties.get("title") if isinstance(properties, dict) else None
        if not isinstance(title, str):
            raise ValueComparisonError("Google Sheets returned malformed sheet identity.")
        if title in present_sheets:
            raise ValueComparisonError("Google Sheets returned duplicate sheet data.")
        present_sheets.add(title)
        grids = sheet.get("data", [])
        if not isinstance(grids, list):
            raise ValueComparisonError("Google Sheets returned malformed grid ranges.")
        for grid in grids:
            if not isinstance(grid, dict):
                raise ValueComparisonError("Google Sheets returned malformed grid data.")
            start_row = _response_grid_index(grid.get("startRow")) + 1
            start_column = _response_grid_index(grid.get("startColumn")) + 1
            key = (title, start_row, start_column)
            if key not in expected or key in returned_grids:
                raise ValueComparisonError("Google Sheets returned unexpected grid ranges.")
            returned_grids[key] = grid

    missing_origins = set(expected) - set(returned_grids)
    if missing_origins:
        raise ValueComparisonError("Google Sheets omitted a requested grid range.")

    for key, bounds in expected.items():
        sheet, start_row, start_column, end_row, end_column = bounds
        grid = returned_grids[key]
        height = end_row - start_row + 1
        width = end_column - start_column + 1
        row_metadata = grid.get("rowMetadata")
        column_metadata = grid.get("columnMetadata")
        # Dimension metadata is optional and is not needed to map CellData in a
        # requested GridRange. When supplied, accept the API's empty representation
        # or require a complete, well-formed array; partial metadata is still rejected.
        for metadata, expected_length, label in (
            (row_metadata, height, "row"),
            (column_metadata, width, "column"),
        ):
            if metadata is None or metadata == []:
                continue
            if not isinstance(metadata, list):
                raise ValueComparisonError(
                    f"Google Sheets returned malformed {label}-range metadata."
                )
            if len(metadata) != expected_length:
                raise ValueComparisonError(
                    f"Google Sheets returned truncated {label}-range metadata."
                )
            if any(not isinstance(item, dict) for item in metadata):
                raise ValueComparisonError("Google Sheets returned malformed range metadata.")
        row_data = grid.get("rowData", [])
        if not isinstance(row_data, list) or len(row_data) > height:
            raise ValueComparisonError("Google Sheets returned malformed or oversized row data.")
        for row_offset in range(height):
            row = row_data[row_offset] if row_offset < len(row_data) else None
            if row is not None and not isinstance(row, dict):
                raise ValueComparisonError("Google Sheets returned malformed row data.")
            row_values = row.get("values", []) if isinstance(row, dict) else []
            if not isinstance(row_values, list) or len(row_values) > width:
                raise ValueComparisonError("Google Sheets returned malformed or oversized cells.")
            for column_offset in range(width):
                row_number = start_row + row_offset
                column_number = start_column + column_offset
                if column_offset >= len(row_values):
                    cell: dict[str, Any] = {}
                    cell_state = "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE"
                    stats["omitted_cell_data_reconstructed"] += 1
                else:
                    raw_cell = row_values[column_offset]
                    if not isinstance(raw_cell, dict):
                        raise ValueComparisonError("Google Sheets returned malformed cell data.")
                    cell = raw_cell
                    stats["cell_data_returned"] += 1
                    if not cell:
                        cell_state = "EXPLICIT_EMPTY_CELL_DATA"
                    elif "userEnteredValue" in cell or "effectiveValue" in cell:
                        cell_state = "CELL_VALUE_DATA_PRESENT"
                    else:
                        cell_state = "CELL_METADATA_ONLY"
                for cell_field in ("userEnteredValue", "effectiveValue", "effectiveFormat"):
                    if cell_field in cell and not isinstance(cell[cell_field], dict):
                        raise ValueComparisonError("Google Sheets returned malformed cell fields.")
                position = (row_number, column_number)
                values[sheet][position] = cell
                formats[sheet][position] = _live_number_format(cell)
                presence[sheet][position] = cell_state
        stats["grid_ranges_confirmed"] += 1
        stats["coordinates_covered"] += height * width
    return values, formats, present_sheets, presence, stats


def _live_formula(cell: dict[str, Any]) -> str | None:
    entered = cell.get("userEnteredValue", {})
    if not isinstance(entered, dict):
        return None
    formula = entered.get("formulaValue")
    return formula.strip().removeprefix("=").strip() if isinstance(formula, str) else None


def _live_number_format(cell: dict[str, Any]) -> str | None:
    effective = cell.get("effectiveFormat", {})
    number_format = effective.get("numberFormat", {}) if isinstance(effective, dict) else {}
    value = number_format.get("type") if isinstance(number_format, dict) else None
    return value if isinstance(value, str) else None


def _read_live_projection(
    session: Any,
    *,
    request_url: str,
    groups: list[list[tuple[str, str, int]]],
    fields: str,
    expected_file_id: str,
    progress: dict[str, int] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    on_request: Callable[[], None] | None = None,
) -> tuple[
    dict[str, dict[tuple[int, int], dict[str, Any]]],
    dict[str, dict[tuple[int, int], str | None]],
    set[str],
    dict[str, dict[tuple[int, int], str]],
]:
    grid_values: dict[str, dict[tuple[int, int], dict[str, Any]]] = defaultdict(dict)
    grid_formats: dict[str, dict[tuple[int, int], str | None]] = defaultdict(dict)
    grid_presence: dict[str, dict[tuple[int, int], str]] = defaultdict(dict)
    present_sheets: set[str] = set()
    state = progress if progress is not None else {}
    state.update(
        {
            "chunks_total": len(groups),
            "chunks_attempted": 0,
            "chunks_completed": 0,
            "ranges_total": sum(len(group) for group in groups),
            "ranges_completed": 0,
            "requested_cells_total": sum(item[2] for group in groups for item in group),
            "requested_cells_completed": 0,
            "cells_returned": 0,
            "grid_ranges_confirmed": 0,
            "coordinates_covered": 0,
            "omitted_cell_data_reconstructed": 0,
            "api_requests": 0,
        }
    )
    for index, group in enumerate(groups):
        # Production comparisons pace every HTTP attempt through a shared callback,
        # including metadata calls and retries across both sweeps. Keep this fallback for
        # direct/test callers that do not supply that callback.
        if index and on_request is None:
            sleeper(REQUEST_SPACING_SECONDS)
        params: list[tuple[str, str]] = [("includeGridData", "true"), ("fields", fields)]
        params.extend(("ranges", item[1]) for item in group)
        try:
            state["chunks_attempted"] = index + 1

            def count_request() -> None:
                state["api_requests"] += 1
                if on_request is not None:
                    on_request()

            response = _get_with_retry(
                session, request_url, params=params, on_request=count_request
            )
            if response.status_code != 200:
                raise ValueComparisonError(
                    f"Google Sheets values returned HTTP {response.status_code}."
                )
            body = response.json(parse_float=Decimal, parse_int=Decimal)
            if not isinstance(body, dict) or body.get("spreadsheetId") != expected_file_id:
                raise ValueComparisonError(
                    "Google Sheets returned a different spreadsheet identity."
                )
            values, formats, batch_sheets, presence, coverage = _cell_grid_index(body, group)
        except ValueComparisonError as error:
            state["failed_chunk"] = index + 1
            raise ProjectionReadError(str(error), dict(state)) from None
        except (TypeError, ValueError) as error:
            state["failed_chunk"] = index + 1
            raise ProjectionReadError(
                "Google Sheets returned invalid cell data.", dict(state)
            ) from error
        present_sheets.update(batch_sheets)
        for sheet, sheet_values in values.items():
            grid_values[sheet].update(sheet_values)
            grid_formats[sheet].update(formats[sheet])
            grid_presence[sheet].update(presence[sheet])
        state["chunks_completed"] = index + 1
        state["ranges_completed"] += len(group)
        state["requested_cells_completed"] += sum(item[2] for item in group)
        state["cells_returned"] += coverage["cell_data_returned"]
        state["grid_ranges_confirmed"] += coverage["grid_ranges_confirmed"]
        state["coordinates_covered"] += coverage["coordinates_covered"]
        state["omitted_cell_data_reconstructed"] += coverage["omitted_cell_data_reconstructed"]
    return grid_values, grid_formats, present_sheets, grid_presence


def _value_hash(normalized: NormalizedCellValue) -> str:
    encoded = json.dumps(
        normalized.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _comparison_status(
    *,
    source_stable: bool,
    live_values_stable: bool,
    live_formulas_stable: bool = True,
    live_cell_evidence_stable: bool = True,
) -> str:
    if not source_stable:
        return "SOURCE_CHANGED_DURING_COMPARISON"
    if not live_values_stable:
        return "LIVE_VALUES_CHANGED_DURING_COMPARISON"
    if not live_formulas_stable:
        return "LIVE_FORMULAS_CHANGED_DURING_COMPARISON"
    if not live_cell_evidence_stable:
        return "LIVE_CELL_EVIDENCE_CHANGED_DURING_COMPARISON"
    return "COMPARED"


def _snapshot_metadata_fence(
    manifest: dict[str, Any], metadata: dict[str, Any]
) -> tuple[bool, str]:
    """Match the frozen source version, using a semantic fence when Sheets has no revision ID.

    Native Google spreadsheets do not consistently expose Drive ``headRevisionId``.
    In that case the modification timestamp is only one part of the fence: the caller
    must also prove that two bounded importer-value/formula reads are identical.
    """

    expected_modified = manifest.get("source_modified_at")
    live_modified = metadata.get("modifiedTime")
    if not isinstance(expected_modified, str) or not expected_modified.strip():
        return False, "SNAPSHOT_MODIFICATION_TIME_MISSING"
    if not isinstance(live_modified, str) or not live_modified.strip():
        return False, "LIVE_MODIFICATION_TIME_MISSING"
    if expected_modified != live_modified:
        return False, "MODIFICATION_TIME_CHANGED"

    expected_revision = manifest.get("source_revision")
    live_revision = metadata.get("headRevisionId")
    if expected_revision is None and live_revision is None:
        revision_protocol = "NO_DRIVE_REVISION_SEMANTIC_FENCE"
    elif (
        isinstance(expected_revision, str)
        and expected_revision
        and expected_revision == live_revision
    ):
        revision_protocol = "DRIVE_REVISION_AND_SEMANTIC_FENCE"
    else:
        return False, "REVISION_METADATA_MISMATCH"

    expected_checksum = manifest.get("source_checksum")
    if expected_checksum is not None and expected_checksum != metadata.get("md5Checksum"):
        return False, "SOURCE_CHECKSUM_MISMATCH"
    if metadata.get("mimeType") != GOOGLE_SHEET_MIME:
        return False, "SOURCE_MIME_TYPE_CHANGED"
    return True, revision_protocol


def _same_source_metadata(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Require exact source identity/metadata equality across the comparison window."""

    fields = ("id", "mimeType", "modifiedTime", "headRevisionId", "md5Checksum")
    return all(before.get(field) == after.get(field) for field in fields)


def _formula_is_dynamic(formula: str) -> bool:
    return bool(
        re.search(
            r"\b(GOOGLEFINANCE|IMPORTRANGE|NOW|TODAY|RAND|RANDBETWEEN|OFFSET|INDIRECT)\s*\(",
            formula,
            flags=re.IGNORECASE,
        )
    )


_SHARED_FORMULA_CELL_REF = re.compile(
    r"(?<![A-Z0-9_.])"
    r"(?P<sheet>(?:'(?:[^']|'')+'|(?:\[[^\]]+\])?[A-Z_][A-Z0-9_.]*)!)?"
    r"(?P<column_absolute>\$?)(?P<column>[A-Z]{1,3})"
    r"(?P<row_absolute>\$?)(?P<row>[1-9][0-9]*)"
    r"(?![A-Z0-9_.]|\s*\()",
    re.IGNORECASE,
)
_SHARED_FORMULA_WHOLE_ROW_OR_COLUMN = re.compile(
    r"(?<![A-Z0-9_.])(?:\$?[A-Z]{1,3}:\$?[A-Z]{1,3}|\$?[1-9][0-9]*:\$?[1-9][0-9]*)(?![A-Z0-9_.])",
    re.IGNORECASE,
)


def _translate_shared_formula(formula: str, source_address: str, target_address: str) -> str | None:
    """Expand one OOXML shared-formula follower using Excel relative-reference rules.

    This deliberately supports only A1 cell references. Whole-row/whole-column ranges and
    unsupported reference shapes fail closed so they remain visible for formula review.
    String literals and quoted sheet names are retained verbatim.
    """
    source_row, source_column = _cell_position(source_address)
    target_row, target_column = _cell_position(target_address)
    row_offset = target_row - source_row
    column_offset = target_column - source_column
    result: list[str] = []
    index = 0
    in_string = False
    while index < len(formula):
        if formula[index] == '"':
            result.append(formula[index])
            index += 1
            if in_string and index < len(formula) and formula[index] == '"':
                result.append(formula[index])
                index += 1
                continue
            in_string = not in_string
            continue
        if in_string:
            result.append(formula[index])
            index += 1
            continue
        if formula[index] == "'":
            # A quoted sheet name is not a string literal. Keep it intact, including escaped
            # apostrophes; the cell reference following ! is translated separately.
            end = index + 1
            while end < len(formula):
                if formula[end] == "'":
                    if end + 1 < len(formula) and formula[end + 1] == "'":
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            result.append(formula[index:end])
            index = end
            continue
        match = _SHARED_FORMULA_CELL_REF.match(formula, index)
        if match is None:
            result.append(formula[index])
            index += 1
            continue
        column = _column_number(match.group("column").upper())
        row = int(match.group("row"))
        if not match.group("column_absolute"):
            column += column_offset
        if not match.group("row_absolute"):
            row += row_offset
        if not (1 <= column <= 16_384 and 1 <= row <= 1_048_576):
            return None
        if not match.group("column_absolute") and not match.group("row_absolute"):
            ref = f"{_column_name(column)}{row}"
        else:
            ref = (
                f"{match.group('column_absolute')}{_column_name(column)}"
                f"{match.group('row_absolute')}{row}"
            )
        result.append(f"{match.group('sheet') or ''}{ref}")
        index = match.end()
    translated = "".join(result)
    if in_string or _SHARED_FORMULA_WHOLE_ROW_OR_COLUMN.search(translated):
        return None
    return translated


def _source_formula_map(workbook: Workbook) -> dict[tuple[str, str], tuple[str | None, str]]:
    """Resolve OOXML shared formula followers for comparison without evaluating formulas."""
    anchors: dict[tuple[str, str], tuple[str, str, str | None]] = {}
    for sheet, cells in workbook.sheets.items():
        for address, cell in cells.items():
            if (
                cell.formula_type == "shared"
                and cell.formula_shared_index is not None
                and cell.formula
            ):
                anchors[(sheet, cell.formula_shared_index)] = (
                    address,
                    cell.formula,
                    cell.formula_shared_ref,
                )

    result: dict[tuple[str, str], tuple[str | None, str]] = {}
    for sheet, cells in workbook.sheets.items():
        for address, cell in cells.items():
            if cell.formula_type != "shared":
                result[(sheet, address)] = (cell.formula, "DIRECT")
                continue
            if cell.formula:
                result[(sheet, address)] = (cell.formula, "SHARED_ANCHOR")
                continue
            if cell.formula_shared_index is None:
                result[(sheet, address)] = (None, "SHARED_FORMULA_UNRESOLVED")
                continue
            anchor = anchors.get((sheet, cell.formula_shared_index))
            if anchor is None:
                result[(sheet, address)] = (None, "SHARED_FORMULA_UNRESOLVED")
                continue
            anchor_range = anchor[2]
            range_match = (
                re.fullmatch(
                    r"\$?([A-Z]+)\$?([1-9][0-9]*):\$?([A-Z]+)\$?([1-9][0-9]*)",
                    anchor_range or "",
                    re.IGNORECASE,
                )
                if anchor_range is not None
                else None
            )
            if range_match is None:
                result[(sheet, address)] = (None, "SHARED_FORMULA_UNRESOLVED")
                continue
            first_column = _column_number(range_match.group(1).upper())
            first_row = int(range_match.group(2))
            last_column = _column_number(range_match.group(3).upper())
            last_row = int(range_match.group(4))
            target_row, target_column = _cell_position(address)
            if not (
                min(first_row, last_row) <= target_row <= max(first_row, last_row)
                and min(first_column, last_column)
                <= target_column
                <= max(first_column, last_column)
            ):
                result[(sheet, address)] = (None, "SHARED_FORMULA_UNRESOLVED")
                continue
            translated = _translate_shared_formula(anchor[1], anchor[0], address)
            result[(sheet, address)] = (
                translated,
                "SHARED_TRANSLATED" if translated is not None else "SHARED_FORMULA_UNRESOLVED",
            )
    return result


def _formula_text(formula: str | None) -> str | None:
    """Normalize only the XLSX/Sheets formula wrapper, never formula syntax."""
    if formula is None:
        return None
    return formula.strip().removeprefix("=").strip()


def _formula_relation(source_formula: str | None, live_formula: str | None) -> str:
    if source_formula is None and live_formula is None:
        return "NO_FORMULA"
    if source_formula is None:
        return "LIVE_FORMULA_ONLY"
    if live_formula is None:
        return "SNAPSHOT_FORMULA_ONLY"
    return "EXACT_TEXT_MATCH" if source_formula == live_formula else "TEXT_DIFFERENCE_UNRESOLVED"


def _value_relation(
    source: NormalizedCellValue,
    live: NormalizedCellValue,
    *,
    live_source_type: str | None = None,
) -> str:
    if source.state != live.state:
        if {source.state, live.state} <= {"BLANK", "MISSING"}:
            return "ABSENCE_REPRESENTATION_DIFFERENCE"
        return "STATE_DIFFERENCE"
    value_differs = source.value != live.value
    type_differs = source.source_type != (live_source_type or live.source_type)
    if value_differs and type_differs:
        return "VALUE_AND_TYPE_DIFFERENCE"
    if value_differs:
        return "VALUE_DIFFERENCE"
    if type_differs:
        return "TYPE_DIFFERENCE"
    return "EXACT_TYPED_VALUE_MATCH"


def _comparison_type(source_type: str | None) -> str | None:
    # XLSX and Sheets use different names for the same string storage type.
    return "text" if source_type == "string" else source_type


def _registry_name_is_present(workbook: Workbook, ticker: str) -> bool:
    for address, cell in workbook.sheets.get("Universe Registry", {}).items():
        row, column = _cell_position(address)
        if column != 1 or row < 5 or (cell.value or "").strip().upper() != ticker:
            continue
        name = workbook.sheets.get("Universe Registry", {}).get(f"B{row}")
        return name is not None and bool((name.value or "").strip())
    return False


def _company_name_fallback_is_present(workbook: Workbook, ticker: str) -> bool:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        return False
    for _, row in workbook.rows("Compounder Quality", 5):
        ticker_cell = row.get("A")
        name_cell = row.get("B")
        if (
            ticker_cell is not None
            and name_cell is not None
            and (ticker_cell.value or "").strip().upper() == normalized_ticker
            and bool((name_cell.value or "").strip())
        ):
            return True
    return False


def _importer_cell_is_consumed(workbook: Workbook, definition: Any) -> bool:
    """Apply narrow, documented gates from the existing legacy import adapter."""
    row, column = _cell_position(definition.address)
    if definition.sheet == "Universe Registry":
        ticker_cell = workbook.sheets.get("Universe Registry", {}).get(f"A{row}")
        ticker = (ticker_cell.value or "").strip().upper() if ticker_cell else ""
        if not ticker:
            return False
        if column != 2:
            return True
        source_cell = workbook.sheets.get("Universe Registry", {}).get(definition.address)
        source_is_missing = source_cell is None or (
            source_cell.value is None and source_cell.kind != "e"
        )
        return not (source_is_missing and _company_name_fallback_is_present(workbook, ticker))
    if definition.sheet == "10Y Durability" and definition.address[:1] == "B":
        # Company names are only read from the Compounder Quality tab as a fallback.
        return False
    if definition.sheet == "Compounder Quality" and definition.address[:1] == "B":
        row, _ = _cell_position(definition.address)
        ticker_cell = workbook.sheets.get("Compounder Quality", {}).get(f"A{row}")
        ticker = (ticker_cell.value or "").strip().upper() if ticker_cell else ""
        return bool(ticker) and not _registry_name_is_present(workbook, ticker)
    if definition.sheet == "Price Feed":
        row_class = workbook.sheets.get("Price Feed", {}).get(f"A{row}")
        key_cell = workbook.sheets.get("Price Feed", {}).get(f"C{row}")
        row_kind = (row_class.value or "").strip().upper() if row_class else ""
        key = (key_cell.value or "").strip().upper() if key_cell else ""
        if column == 1:
            # The adapter only supports two explicit auxiliary listing keys.
            return key in {"SPYY", "TSM-ADR"}
        if column == 3:
            return row_kind == "AUX" and key in {"SPYY", "TSM-ADR"}
        return row_kind == "AUX" and key in {"SPYY", "TSM-ADR"}
    return True


def _importer_semantic_relation(
    workbook: Workbook,
    definition: Any,
    source: NormalizedCellValue,
    live: NormalizedCellValue,
    *,
    source_formula: str | None,
    live_formula: str | None,
    source_format: str | None,
    live_format: str | None,
    live_source_type: str | None,
) -> str:
    """Describe impact after the current importer transformation, without hiding raw drift."""
    if not _importer_cell_is_consumed(workbook, definition):
        return "NOT_CONSUMED_BY_CURRENT_IMPORT"
    target_field, _transformation = importer_field_semantics(definition)
    if (
        target_field.startswith("RankingEntry.legacy_")
        and source.state in {"FORMULA_CACHE_EMPTY", "BLANK", "MISSING"}
        and live.state in {"FORMULA_CACHE_EMPTY", "BLANK", "MISSING"}
    ):
        # The importer persists an explicit INPUTS_UNAVAILABLE/NOT_ELIGIBLE status for
        # missing cached rank positions; it does not invent a ranking value.
        return "EXPLICIT_UNAVAILABLE_RANK"
    if source.state in {"FORMULA_ERROR", "CELL_ERROR", "FORMULA_CACHE_EMPTY"} or live.state in {
        "FORMULA_ERROR",
        "CELL_ERROR",
        "FORMULA_CACHE_EMPTY",
    }:
        return "IMPORTER_VALUE_UNAVAILABLE_OR_ERROR"
    if source.state in {"BLANK", "MISSING"} and live.state in {"BLANK", "MISSING"}:
        return "EQUIVALENT_ABSENCE"

    if target_field == "ScoreAssessment.evidence_completeness":
        source_present = source.state == "VALUE" and bool(source.value)
        live_present = live.state == "VALUE" and bool(live.value)
        return (
            "EQUIVALENT_PRESENCE_ONLY"
            if source_present == live_present
            else "IMPORTER_PRESENCE_DIFFERENCE"
        )

    type_differs = source.state == live.state == "VALUE" and source.source_type != _comparison_type(
        live_source_type
    )
    value_differs = source.state != live.state or source.value != live.value
    if type_differs and value_differs:
        return "IMPORTER_VALUE_AND_TYPE_DIFFERENCE"
    if type_differs:
        return "IMPORTER_SOURCE_TYPE_DIFFERENCE"
    if source.payload() != live.payload():
        return "IMPORTER_VALUE_DIFFERENCE"
    if source_formula != live_formula:
        return "CURRENT_VALUE_MATCH_FORMULA_TEXT_DIFFERENCE_UNRESOLVED"
    if source_format != live_format:
        return "EQUIVALENT_VALUE_FORMAT_ONLY"
    return "EQUIVALENT_EXACT_VALUE"


def _json_exact(value: Any) -> Any:
    """Convert API Decimal values to exact decimal text for private JSON evidence."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _json_exact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_exact(item) for item in value]
    return value


def _classification(
    source: NormalizedCellValue,
    live: NormalizedCellValue,
    *,
    mode: SemanticMode,
    source_formula: str | None,
    live_formula: str | None,
    source_has_formula: bool,
    live_has_formula: bool,
    source_format: str | None,
    live_format: str | None,
    live_source_type: str | None = None,
    formula_relation: str | None = None,
) -> str:
    if source.state in {"FORMULA_ERROR", "CELL_ERROR"} or live.state in {
        "FORMULA_ERROR",
        "CELL_ERROR",
    }:
        return "FORMULA_ERROR"
    resolved_formula_relation = formula_relation or _formula_relation(
        _formula_text(source_formula), _formula_text(live_formula)
    )
    if source_has_formula != live_has_formula or resolved_formula_relation in {
        "TEXT_DIFFERENCE_UNRESOLVED",
        "LIVE_FORMULA_ONLY",
        "SNAPSHOT_FORMULA_ONLY",
        "SHARED_FORMULA_EXPANSION_UNSUPPORTED",
    }:
        return "FORMULA_DEFINITION_MISMATCH"
    if source.payload() == live.payload():
        if live_source_type is not None and source.source_type != live_source_type:
            return "VALUE_TYPE_MISMATCH"
        if mode == "excel_date":
            source_date = source_format == "DATE_TIME"
            live_date = live_format in {"DATE", "DATE_TIME", "DATE_TIME_SECONDS"}
            if source_format is not None and live_format is not None and source_date != live_date:
                return "DATE_FORMATTING_MISMATCH"
        elif (
            mode in {"decimal", "percent_decimal"}
            and source_format is not None
            and live_format is not None
            and source_format != live_format
        ):
            if "CURRENCY" in {source_format, live_format}:
                return "CURRENCY_FORMATTING_MISMATCH"
            if "PERCENT" in {source_format, live_format}:
                return "PERCENT_FORMATTING_MISMATCH"
            return "NUMERIC_FORMATTING_MISMATCH"
        return "MATCH"
    if source.state == "FORMULA_CACHE_EMPTY" and live.state == "VALUE":
        return "EMPTY_XLSX_CACHE_LIVE_VALUE"
    if mode == "excel_date":
        return "DATE_INTERPRETATION_MISMATCH"
    if mode == "currency":
        return "CURRENCY_IDENTITY_MISMATCH"
    if source.source_type != (live_source_type or live.source_type):
        return "VALUE_TYPE_MISMATCH"
    if (
        mode in {"decimal", "percent_decimal"}
        and source_format != live_format
        and "CURRENCY" in {source_format, live_format}
    ):
        return "CURRENCY_FORMATTING_MISMATCH"
    if (
        mode in {"decimal", "percent_decimal"}
        and source_format != live_format
        and "PERCENT" in {source_format, live_format}
    ):
        return "PERCENT_FORMATTING_MISMATCH"
    if source_formula is not None and source_formula == live_formula:
        return (
            "LIVE_CALCULATION_CHANGED_AFTER_EXPORT_CANDIDATE"
            if _formula_is_dynamic(source_formula)
            else "STALE_XLSX_CACHE_CANDIDATE"
        )
    return "OTHER_VALUE_MISMATCH"


def compare_semantic_values(
    workbook: Workbook,
    live_values: dict[str, dict[tuple[int, int], dict[str, Any]]],
    *,
    number_formats: dict[str, dict[tuple[int, int], str | None]],
    cell_presence: dict[str, dict[tuple[int, int], str]] | None = None,
    definitions: Sequence[Any] | None = None,
    include_source_value_cells: bool = False,
) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    source_projection: list[dict[str, object]] = []
    live_projection: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    differences_by_class: Counter[str] = Counter()
    source_formula_projection: list[dict[str, str]] = []
    live_formula_projection: list[dict[str, str]] = []
    live_cell_evidence_projection: list[dict[str, Any]] = []
    value_relations: Counter[str] = Counter()
    formula_relations: Counter[str] = Counter()
    number_format_relations: Counter[str] = Counter()
    importer_relations: Counter[str] = Counter()
    source_formula_map = _source_formula_map(workbook)
    canonical_source_cells: list[dict[str, Any]] = []
    selected_definitions = (
        definitions if definitions is not None else importer_value_cells(workbook)
    )
    expected_importer_cell_count = sum(
        _importer_cell_is_consumed(workbook, definition) for definition in selected_definitions
    )
    for definition in selected_definitions:
        row, column = _cell_position(definition.address)
        source_cell = workbook.sheets.get(definition.sheet, {}).get(definition.address)
        if source_cell is None:
            from portfolio_api.legacy_import import Cell

            source_cell = Cell()
        live_cell = live_values.get(definition.sheet, {}).get((row, column), {})
        live_cell_present = (row, column) in live_values.get(definition.sheet, {})
        presence_state = (cell_presence or {}).get(definition.sheet, {}).get((row, column))
        if presence_state is None:
            presence_state = (
                "CELL_VALUE_DATA_PRESENT" if live_cell_present else "UNVERIFIED_MISSING_COORDINATE"
            )
        known_presence_states = {
            "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE",
            "EXPLICIT_EMPTY_CELL_DATA",
            "CELL_VALUE_DATA_PRESENT",
            "CELL_METADATA_ONLY",
        }
        coordinate_covered = presence_state in known_presence_states
        api_cell_present = presence_state in {
            "EXPLICIT_EMPTY_CELL_DATA",
            "CELL_VALUE_DATA_PRESENT",
            "CELL_METADATA_ONLY",
        }
        live_effective = live_cell.get("effectiveValue")
        if not isinstance(live_effective, dict):
            live_effective = None
        has_formula = _live_formula(live_cell) is not None
        entered_value = live_cell.get("userEnteredValue")
        live_format = number_formats.get(definition.sheet, {}).get((row, column))
        source_normalized = normalize_source_cell(
            source_cell, definition.mode, date_system=workbook.date_system
        )
        live_normalized, live_source_type, _ = live_cell_normalization(
            live_effective,
            mode=definition.mode,
            has_formula=has_formula,
            number_format_type=live_format,
        )
        entered_empty_string = (
            isinstance(entered_value, dict)
            and entered_value.get("stringValue") == ""
            and not has_formula
        )
        if entered_empty_string and live_effective is None:
            live_normalized = NormalizedCellValue("EMPTY_STRING", "", "empty-string")
        elif coordinate_covered and not has_formula and not live_effective and not entered_value:
            # Sparse GridData omissions are a blank only when their enclosing requested
            # range was confirmed and its dimensions were complete. The presence state
            # remains separately fingerprinted and recorded for audit.
            live_normalized = NormalizedCellValue("BLANK", "", "blank")
        live_formula_raw = _live_formula(live_cell)
        live_formula = _formula_text(live_formula_raw)
        source_formula_raw = source_cell.formula
        source_formula_value, source_formula_resolution = source_formula_map.get(
            (definition.sheet, definition.address), (source_formula_raw, "DIRECT")
        )
        source_formula = _formula_text(source_formula_value)
        value_relation = _value_relation(
            source_normalized,
            live_normalized,
            live_source_type=_comparison_type(live_source_type),
        )
        formula_relation = (
            "SHARED_FORMULA_EXPANSION_UNSUPPORTED"
            if source_formula_resolution == "SHARED_FORMULA_UNRESOLVED"
            else _formula_relation(source_formula, live_formula)
        )
        number_format_relation = (
            "EXACT_FORMAT_MATCH"
            if source_cell.number_format_type == live_format
            else "DISPLAY_FORMAT_DIFFERENCE"
        )
        importer_relation = _importer_semantic_relation(
            workbook,
            definition,
            source_normalized,
            live_normalized,
            source_formula=source_formula,
            live_formula=live_formula,
            source_format=source_cell.number_format_type,
            live_format=live_format,
            live_source_type=_comparison_type(live_source_type),
        )
        value_relations[value_relation] += 1
        formula_relations[formula_relation] += 1
        number_format_relations[number_format_relation] += 1
        importer_relations[importer_relation] += 1
        if source_formula is not None:
            source_formula_projection.append(
                {
                    "sheet": definition.sheet,
                    "cell": definition.address,
                    "formula_sha256": hashlib.sha256(source_formula.encode()).hexdigest(),
                }
            )
        if live_formula is not None:
            live_formula_projection.append(
                {
                    "sheet": definition.sheet,
                    "cell": definition.address,
                    "formula_sha256": hashlib.sha256(live_formula.encode()).hexdigest(),
                }
            )
        classification = _classification(
            source_normalized,
            live_normalized,
            mode=definition.mode,
            source_formula=source_formula,
            live_formula=live_formula,
            source_has_formula=source_cell.formula is not None,
            live_has_formula=has_formula,
            source_format=source_cell.number_format_type,
            live_format=live_format,
            live_source_type=_comparison_type(live_source_type),
            formula_relation=formula_relation,
        )
        target_field, transformation = importer_field_semantics(definition)
        source_role = importer_source_role(definition, source_cell)
        importer_consumed = _importer_cell_is_consumed(workbook, definition)
        if importer_consumed:
            live_cell_evidence_projection.append(
                {
                    "sheet": definition.sheet,
                    "cell": definition.address,
                    "cell_data_state": presence_state,
                    "user_entered_value": _json_exact(entered_value),
                    "effective_value": _json_exact(live_effective),
                    "number_format_type": live_format,
                }
            )
        importer_formula_unresolved = (
            formula_relation
            not in {
                "NO_FORMULA",
                "EXACT_TEXT_MATCH",
            }
            and importer_consumed
            and importer_relation != ("EXPLICIT_UNAVAILABLE_RANK")
        )
        counts[definition.domain] += 1
        source_projection.append(
            {
                "domain": definition.domain,
                "sheet": definition.sheet,
                "cell": definition.address,
                "target_field": target_field,
                "transformation": transformation,
                "source_role": source_role,
                "formula_present": source_cell.formula is not None,
                **source_normalized.payload(),
            }
        )
        live_projection.append(
            {
                "domain": definition.domain,
                "sheet": definition.sheet,
                "cell": definition.address,
                "target_field": target_field,
                "transformation": transformation,
                "source_role": importer_source_role(definition, formula_present=has_formula),
                "formula_present": has_formula,
                **live_normalized.payload(),
                "source_type": _comparison_type(live_source_type),
                "cell_data_state": presence_state,
            }
        )
        if importer_consumed and include_source_value_cells:
            entered_value = live_cell.get("userEnteredValue")
            effective_format = live_cell.get("effectiveFormat")
            number_format = (
                effective_format.get("numberFormat") if isinstance(effective_format, dict) else None
            )
            canonical_source_cells.append(
                {
                    "domain": definition.domain,
                    "sheet": definition.sheet,
                    "cell": definition.address,
                    "target_field": target_field,
                    "transformation": transformation,
                    "mode": definition.mode,
                    "source_role": source_role,
                    "value_authority": importer_source_value_policy(definition)[0],
                    "formula_policy": importer_source_value_policy(definition)[1],
                    "api_cell_present": api_cell_present,
                    "api_coordinate_covered": coordinate_covered,
                    "cell_data_state": presence_state,
                    "empty_value_policy": importer_empty_value_policy(
                        workbook, definition, live_values=live_values
                    ),
                    "xlsx": {
                        "state": source_normalized.state,
                        "normalized_value": source_normalized.value,
                        "source_type": source_normalized.source_type,
                        "value_text": source_cell.value,
                        "cell_type": source_cell.kind,
                        "formula_text": source_cell.formula,
                        "expanded_formula_text": source_formula,
                        "formula_resolution": source_formula_resolution,
                        "formula_storage_type": source_cell.formula_type,
                        "formula_shared_index": source_cell.formula_shared_index,
                        "formula_shared_ref": source_cell.formula_shared_ref,
                        "number_format_type": source_cell.number_format_type,
                        "number_format_code": source_cell.number_format_code,
                    },
                    "sheets": {
                        "user_entered_value": _json_exact(entered_value),
                        "effective_value": _json_exact(live_effective),
                        "formula_text": (
                            entered_value.get("formulaValue")
                            if isinstance(entered_value, dict)
                            and isinstance(entered_value.get("formulaValue"), str)
                            else None
                        ),
                        "effective_number_format_type": live_format,
                        "effective_number_format_pattern": (
                            number_format.get("pattern")
                            if isinstance(number_format, dict)
                            and isinstance(number_format.get("pattern"), str)
                            else None
                        ),
                    },
                    "normalized": {
                        "authoritative_live": live_normalized.payload(),
                        "live_source_type": _comparison_type(live_source_type),
                    },
                    "diagnostics": {
                        "classification": classification,
                        "value_relation": value_relation,
                        "formula_relation": formula_relation,
                        "number_format_relation": number_format_relation,
                        "importer_semantic_relation": importer_relation,
                    },
                }
            )
        if classification == "MATCH":
            continue
        differences_by_class[classification] += 1
        differences.append(
            {
                "domain": definition.domain,
                "sheet": definition.sheet,
                "cell": definition.address,
                "target_field": target_field,
                "transformation": transformation,
                "source_role": source_role,
                "classification": classification,
                "value_relation": value_relation,
                "formula_relation": formula_relation,
                "number_format_relation": number_format_relation,
                "importer_semantic_relation": importer_relation,
                "canonical_value_changed": importer_relation
                in {
                    "IMPORTER_VALUE_DIFFERENCE",
                    "IMPORTER_VALUE_AND_TYPE_DIFFERENCE",
                    "IMPORTER_SOURCE_TYPE_DIFFERENCE",
                    "IMPORTER_PRESENCE_DIFFERENCE",
                },
                "source_fidelity_review_required": importer_relation
                in {
                    "IMPORTER_VALUE_DIFFERENCE",
                    "IMPORTER_VALUE_AND_TYPE_DIFFERENCE",
                    "IMPORTER_SOURCE_TYPE_DIFFERENCE",
                    "IMPORTER_PRESENCE_DIFFERENCE",
                    "IMPORTER_VALUE_UNAVAILABLE_OR_ERROR",
                    "CURRENT_VALUE_MATCH_FORMULA_TEXT_DIFFERENCE_UNRESOLVED",
                }
                or importer_formula_unresolved,
                "formula_semantics_review_required": importer_formula_unresolved,
                "source_state": source_normalized.state,
                "live_state": live_normalized.state,
                "source_type": source_normalized.source_type,
                "live_type": live_source_type,
                "source_number_format": source_cell.number_format_type,
                "live_number_format": live_format,
                "source_value_sha256": _value_hash(source_normalized),
                "live_value_sha256": _value_hash(live_normalized),
                "source_formula_sha256": hashlib.sha256(source_formula.encode()).hexdigest()
                if source_formula is not None
                else None,
                "live_formula_sha256": hashlib.sha256(live_formula.encode()).hexdigest()
                if live_formula is not None
                else None,
                "source_evidence": {
                    "value_text": source_cell.value,
                    "cell_type": source_cell.kind,
                    "formula_text": source_cell.formula,
                    "formula_text_for_comparison": source_formula,
                    "formula_resolution": source_formula_resolution,
                    "formula_storage_type": source_cell.formula_type,
                    "formula_shared_index": source_cell.formula_shared_index,
                    "formula_shared_ref": source_cell.formula_shared_ref,
                    "number_format_type": source_cell.number_format_type,
                    "number_format_code": source_cell.number_format_code,
                },
                "live_evidence": {
                    "user_entered_value": _json_exact(live_cell.get("userEnteredValue")),
                    "effective_value": _json_exact(live_cell.get("effectiveValue")),
                    "formula_text_for_comparison": live_formula,
                    "number_format_type": live_format,
                },
            }
        )

    def digest(projection: Sequence[Mapping[str, object]]) -> str:
        serialized = json.dumps(
            {
                "version": SEMANTIC_FINGERPRINT_VERSION,
                "values": projection,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    return {
        "cells_compared": sum(counts.values()),
        "cells_by_domain": dict(sorted(counts.items())),
        "differences_by_class": dict(sorted(differences_by_class.items())),
        "value_relations": dict(sorted(value_relations.items())),
        "formula_relations": dict(sorted(formula_relations.items())),
        "number_format_relations": dict(sorted(number_format_relations.items())),
        "importer_semantic_relations": dict(sorted(importer_relations.items())),
        "semantic_fingerprint_version": SEMANTIC_FINGERPRINT_VERSION,
        "snapshot_semantic_sha256": digest(source_projection),
        "live_semantic_sha256": digest(live_projection),
        "live_cell_evidence_sha256": digest(live_cell_evidence_projection),
        "snapshot_formula_definitions_sha256": digest(source_formula_projection),
        "live_formula_definitions_sha256": digest(live_formula_projection),
        "required_live_cells_missing": sum(
            not item["api_coordinate_covered"] for item in canonical_source_cells
        ),
        "expected_importer_cell_count": expected_importer_cell_count,
        "canonical_source_cells": canonical_source_cells,
        "differences": differences,
        "exception_ledger_version": EXCEPTION_LEDGER_VERSION,
    }


def _write_private_report(
    store: SnapshotStore,
    run_id: str,
    report: dict[str, Any],
    *,
    comparison_started_at: datetime | None = None,
    comparison_attempt_id: str | None = None,
    comparison_completed_at: datetime | None = None,
) -> None:
    directory = store.root / "value-comparisons"
    directory.mkdir(mode=0o700, exist_ok=True)
    with suppress(OSError):
        directory.chmod(0o700)
    path = directory / f"{run_id}-{uuid.uuid4().hex}.json"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        private_report = dict(report)
        exception_records = private_report.pop("differences", [])
        private_report.setdefault("report_version", COMPARISON_REPORT_VERSION)
        private_report.setdefault("comparison_contract_version", COMPARISON_CONTRACT_VERSION)
        private_report.setdefault(
            "comparison_started_at_utc",
            (comparison_started_at or datetime.now(UTC)).isoformat(),
        )
        if comparison_attempt_id is not None:
            private_report["comparison_attempt_id"] = comparison_attempt_id
        if private_report.get("status") != "COMPARISON_ATTEMPT_STARTED":
            private_report.setdefault(
                "comparison_completed_at_utc",
                (comparison_completed_at or datetime.now(UTC)).isoformat(),
            )
        private_report["exception_ledger"] = {
            "version": EXCEPTION_LEDGER_VERSION,
            "record_count": len(exception_records),
            "records": exception_records,
        }
        json.dump(private_report, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")


def _read_snapshot(store: SnapshotStore, run_id: str) -> tuple[dict[str, Any], bytes]:
    manifest = store.manifest(run_id)
    if manifest.get("profile") != PORTFOLIO_PROFILE.key:
        raise ValueComparisonError("The selected run is not a portfolio workbook snapshot.")
    if manifest.get("status") not in {
        "ACQUIRED",
        "ACQUIRED_REVIEW_REQUIRED",
        "SCHEMA_BASELINE_ACCEPTED",
    }:
        raise ValueComparisonError("The selected source run is not an acquired workbook snapshot.")
    if manifest.get("semantic_fingerprint_version") != SEMANTIC_FINGERPRINT_VERSION:
        raise ValueComparisonError(
            "The snapshot predates importer semantic fingerprints; reacquire it."
        )
    digest = manifest.get("artifact_sha256")
    relative = manifest.get("blob_path")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueComparisonError("The source manifest is missing its artifact hash.")
    if not isinstance(relative, str):
        raise ValueComparisonError("The source manifest is missing its private artifact path.")
    relative_path = Path(relative)
    expected = Path("blobs") / "sha256" / digest / "workbook.xlsx"
    if relative_path.is_absolute() or ".." in relative_path.parts or relative_path != expected:
        raise ValueComparisonError("The source manifest artifact path is invalid.")
    path = store.root / relative_path
    if not path.is_file() or path.is_symlink():
        raise ValueComparisonError("The frozen source artifact is unavailable.")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueComparisonError("The frozen source artifact failed its SHA-256 check.")
    return manifest, payload


def compare_snapshot(
    *,
    run_id: str,
    store: SnapshotStore,
    settings: Settings,
    scope: ValidationScope = "canonical-bootstrap",
) -> dict[str, Any]:
    comparison_started_at = datetime.now(UTC)
    if re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        raise ValueComparisonError("Use the exact 32-character workbook acquisition run ID.")
    comparison_attempt_id = uuid.uuid4().hex
    _write_private_report(
        store,
        run_id,
        {
            "report_version": COMPARISON_REPORT_VERSION,
            "comparison_contract_version": COMPARISON_CONTRACT_VERSION,
            "run_id": run_id,
            "scope": scope,
            "status": "COMPARISON_ATTEMPT_STARTED",
            "consistency_result": "IN_PROGRESS",
        },
        comparison_started_at=comparison_started_at,
        comparison_attempt_id=comparison_attempt_id,
    )
    manifest, payload = _read_snapshot(store, run_id)
    drive_reader, file_id = _google_source(PORTFOLIO_PROFILE, settings)
    del drive_reader  # The comparison uses the same configured file with read-only Sheets scope.
    identity = hashlib.sha256(f"google-drive:{file_id}".encode()).hexdigest()
    if manifest.get("source_identity_sha256") != identity:
        raise ValueComparisonError(
            "The configured Google workbook does not match the frozen snapshot identity."
        )
    if manifest.get("source_mime_type") != GOOGLE_SHEET_MIME:
        raise ValueComparisonError(
            "Live cell comparison is supported only for a native Google spreadsheet."
        )
    expected_revision = manifest.get("source_revision")
    expected_modified = manifest.get("source_modified_at")
    if expected_revision is not None and not isinstance(expected_revision, str):
        raise ValueComparisonError("The frozen snapshot contains invalid Drive revision metadata.")
    if not isinstance(expected_modified, str) or not expected_modified.strip():
        raise ValueComparisonError("The frozen snapshot lacks a stable modification time.")

    workbook = Workbook.read_bytes(
        payload,
        lambda name: (
            name
            in {
                "Universe Registry",
                "Current Holdings",
                "Target Architecture",
                "10Y Durability",
                "Compounder Quality",
                "Price Feed",
                "Model Contract",
                "Model Revision History",
                "Estimate History",
                "Candidate Ranking",
            }
            or name.startswith(("P-", "W-", "C-"))
        ),
        source_name=PORTFOLIO_PROFILE.expected_filename,
    )
    expected_semantic = manifest.get("semantic_sha256")
    from portfolio_api.workbook_semantics import semantic_fingerprint

    actual_semantic, _ = semantic_fingerprint(workbook)
    if expected_semantic != actual_semantic:
        raise ValueComparisonError("The frozen artifact semantic fingerprint failed verification.")
    plan = _validation_plan(workbook, scope)
    definitions = plan["definitions"]
    groups = plan["groups"]
    metrics = plan["metrics"]
    if metrics["work_budget_exceeded"]:
        report = {
            "report_version": COMPARISON_REPORT_VERSION,
            "run_id": run_id,
            "scope": scope,
            "status": "BLOCKED_VALIDATION_BUDGET_EXCEEDED",
            "consistency_result": "NOT_STARTED",
            "request_count": 0,
            "progress": {"chunks_completed": 0, "chunks_total": metrics["chunks_per_pass"]},
            "cells_compared": 0,
            "mismatch_classes": {},
            **metrics,
        }
        _write_private_report(
            store,
            run_id,
            report,
            comparison_started_at=comparison_started_at,
            comparison_attempt_id=comparison_attempt_id,
        )
        return report

    from portfolio_api.workbook_sources import load_google_sheets_readonly_session

    credential_path = settings.google_sheets_service_account_file
    if credential_path is None:
        raise WorkbookSourceError(
            "CREDENTIAL_FILE_NOT_CONFIGURED",
            "Set GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE to a private service-account key file.",
        )
    session = load_google_sheets_readonly_session(credential_path)
    request_counts = {"metadata": 0, "values": 0}
    last_request_started_at: float | None = None

    def request_counter(kind: Literal["metadata", "values"]) -> Callable[[], None]:
        def count_request() -> None:
            nonlocal last_request_started_at
            now = time.monotonic()
            if last_request_started_at is not None:
                delay = REQUEST_SPACING_SECONDS - (now - last_request_started_at)
                if delay > 0:
                    time.sleep(delay)
            last_request_started_at = time.monotonic()
            request_counts[kind] += 1

        return count_request

    count_metadata_request = request_counter("metadata")
    count_value_request = request_counter("values")
    try:
        before = _metadata(session, file_id, on_request=count_metadata_request)
    except ValueComparisonError as error:
        report = {
            "report_version": COMPARISON_REPORT_VERSION,
            "run_id": run_id,
            "scope": scope,
            "status": "SOURCE_METADATA_READ_FAILED",
            "consistency_result": "INCOMPLETE_NO_ACCEPTANCE",
            "request_count": sum(request_counts.values()),
            "progress": {
                "metadata_requests": request_counts["metadata"],
                "first_pass": None,
                "second_pass": None,
            },
            "required_cells": metrics["required_cells"],
            "ranges": metrics["ranges"],
            "chunks_per_pass": metrics["chunks_per_pass"],
            "compared_cells": 0,
            "mismatch_classes": {},
            "error": str(error),
            **metrics,
        }
        _write_private_report(
            store,
            run_id,
            report,
            comparison_started_at=comparison_started_at,
            comparison_attempt_id=comparison_attempt_id,
        )
        return {
            "status": report["status"],
            "run_id": run_id,
            "scope": scope,
            "required_cells": metrics["required_cells"],
            "ranges": metrics["ranges"],
            "chunks_per_pass": metrics["chunks_per_pass"],
            "compared_cells": 0,
            "mismatch_classes": {},
            "request_count": report["request_count"],
            "progress": report["progress"],
            "error": report["error"],
            "consistency_result": report["consistency_result"],
            **metrics,
        }
    if before.get("mimeType") != GOOGLE_SHEET_MIME:
        raise ValueComparisonError(
            "The configured source is no longer a native Google spreadsheet."
        )
    metadata_matches_snapshot, consistency_protocol = _snapshot_metadata_fence(manifest, before)
    if not metadata_matches_snapshot:
        blocked = {
            "report_version": COMPARISON_REPORT_VERSION,
            "comparison_contract_version": COMPARISON_CONTRACT_VERSION,
            "status": "SOURCE_ADVANCED_REACQUIRE_REQUIRED",
            "run_id": run_id,
            "scope": scope,
            "source_identity_sha256": identity,
            "snapshot_source_revision": expected_revision,
            "snapshot_source_modified_at": expected_modified,
            "live_source_revision": before.get("headRevisionId"),
            "live_source_modified_at": before.get("modifiedTime"),
            "consistency_protocol": consistency_protocol,
            "source_revision_matches": (
                expected_revision == before.get("headRevisionId")
                if expected_revision is not None
                else None
            ),
            "source_modified_at_matches": expected_modified == before.get("modifiedTime"),
            "source_metadata_matches_snapshot": False,
            "cells_compared": 0,
            "compared_cells": 0,
            "mismatch_classes": {},
            "consistency_result": "SOURCE_METADATA_MISMATCH",
            "request_count": sum(request_counts.values()),
            "progress": {"chunks_completed": 0, "chunks_total": metrics["chunks_per_pass"]},
            **metrics,
        }
        _write_private_report(
            store,
            run_id,
            blocked,
            comparison_started_at=comparison_started_at,
            comparison_attempt_id=comparison_attempt_id,
        )
        return blocked

    request_url = f"{SHEETS_API}/{quote(file_id, safe='')}"
    fields = (
        "spreadsheetId,sheets(properties(title),data(startRow,startColumn,rowMetadata,"
        "columnMetadata,"
        "rowData(values(userEnteredValue,effectiveValue,effectiveFormat(numberFormat(type,pattern))))))"
    )
    first_progress: dict[str, int] = {}
    try:
        grid_values, grid_formats, present_sheets, grid_presence = _read_live_projection(
            session,
            request_url=request_url,
            groups=groups,
            fields=fields,
            expected_file_id=file_id,
            progress=first_progress,
            on_request=count_value_request,
        )
    except ProjectionReadError as error:
        report = {
            "report_version": COMPARISON_REPORT_VERSION,
            "run_id": run_id,
            "scope": scope,
            "status": "LIVE_REQUEST_FAILED",
            "consistency_result": "INCOMPLETE_NO_ACCEPTANCE",
            "request_count": sum(request_counts.values()),
            "progress": {"first_pass": error.progress, "second_pass": None},
            "cells_compared": 0,
            "mismatch_classes": {},
            "error": str(error),
            **metrics,
        }
        _write_private_report(
            store,
            run_id,
            report,
            comparison_started_at=comparison_started_at,
            comparison_attempt_id=comparison_attempt_id,
        )
        return report

    required_sheets = {item.sheet for item in definitions}
    missing_sheets = sorted(required_sheets - present_sheets)
    if missing_sheets:
        report = {
            "report_version": COMPARISON_REPORT_VERSION,
            "run_id": run_id,
            "scope": scope,
            "status": "LIVE_REQUIRED_SHEETS_MISSING",
            "consistency_result": "INCOMPLETE_NO_ACCEPTANCE",
            "request_count": sum(request_counts.values()),
            "progress": {"first_pass": first_progress, "second_pass": None},
            "required_cells": metrics["required_cells"],
            "ranges": metrics["ranges"],
            "chunks_per_pass": metrics["chunks_per_pass"],
            "cells_compared": 0,
            "compared_cells": 0,
            "mismatch_classes": {},
            "missing_required_sheets": missing_sheets,
            **metrics,
        }
        _write_private_report(
            store,
            run_id,
            report,
            comparison_started_at=comparison_started_at,
            comparison_attempt_id=comparison_attempt_id,
        )
        return report
    comparison = compare_semantic_values(
        workbook,
        grid_values,
        number_formats=grid_formats,
        cell_presence=grid_presence,
        definitions=definitions,
        include_source_value_cells=True,
    )
    second_progress: dict[str, int] = {}
    try:
        (
            verification_values,
            verification_formats,
            verification_sheets,
            verification_presence,
        ) = _read_live_projection(
            session,
            request_url=request_url,
            groups=groups,
            fields=fields,
            expected_file_id=file_id,
            progress=second_progress,
            on_request=count_value_request,
        )
    except ProjectionReadError as error:
        report = {
            "report_version": COMPARISON_REPORT_VERSION,
            "run_id": run_id,
            "scope": scope,
            "status": "LIVE_REQUEST_FAILED",
            "consistency_result": "INCOMPLETE_NO_ACCEPTANCE",
            "request_count": sum(request_counts.values()),
            "progress": {"first_pass": first_progress, "second_pass": error.progress},
            "cells_compared": comparison["cells_compared"],
            "compared_cells": comparison["cells_compared"],
            "mismatch_classes": comparison["differences_by_class"],
            "error": str(error),
            **metrics,
        }
        _write_private_report(
            store,
            run_id,
            report,
            comparison_started_at=comparison_started_at,
            comparison_attempt_id=comparison_attempt_id,
        )
        return report
    missing_sheets.extend(sorted(required_sheets - verification_sheets))
    verification = compare_semantic_values(
        workbook,
        verification_values,
        number_formats=verification_formats,
        cell_presence=verification_presence,
        definitions=definitions,
        include_source_value_cells=True,
    )
    live_values_stable = comparison["live_semantic_sha256"] == verification["live_semantic_sha256"]
    live_formulas_stable = (
        comparison["live_formula_definitions_sha256"]
        == verification["live_formula_definitions_sha256"]
    )
    first_cell_evidence = comparison.get("live_cell_evidence_sha256")
    second_cell_evidence = verification.get("live_cell_evidence_sha256")
    live_cell_evidence_stable = (
        isinstance(first_cell_evidence, str)
        and isinstance(second_cell_evidence, str)
        and first_cell_evidence == second_cell_evidence
    )
    try:
        after = _metadata(session, file_id, on_request=count_metadata_request)
    except ValueComparisonError as error:
        report = {
            "report_version": COMPARISON_REPORT_VERSION,
            "run_id": run_id,
            "scope": scope,
            "status": "SOURCE_METADATA_RECHECK_FAILED",
            "consistency_result": "INCOMPLETE_NO_ACCEPTANCE",
            "request_count": sum(request_counts.values()),
            "progress": {"first_pass": first_progress, "second_pass": second_progress},
            "required_cells": metrics["required_cells"],
            "ranges": metrics["ranges"],
            "chunks_per_pass": metrics["chunks_per_pass"],
            "compared_cells": comparison["cells_compared"],
            "mismatch_classes": comparison["differences_by_class"],
            "live_values_stable_across_reads": live_values_stable,
            "live_formula_definitions_stable_across_reads": live_formulas_stable,
            "error": str(error),
            **metrics,
        }
        _write_private_report(
            store,
            run_id,
            report,
            comparison_started_at=comparison_started_at,
            comparison_attempt_id=comparison_attempt_id,
        )
        return {
            "status": report["status"],
            "run_id": run_id,
            "scope": scope,
            "required_cells": metrics["required_cells"],
            "ranges": metrics["ranges"],
            "chunks_per_pass": metrics["chunks_per_pass"],
            "compared_cells": comparison["cells_compared"],
            "mismatch_classes": comparison["differences_by_class"],
            "request_count": report["request_count"],
            "progress": report["progress"],
            "error": report["error"],
            "consistency_result": report["consistency_result"],
            **metrics,
        }
    same_source_version = _same_source_metadata(before, after)
    comparison_completed_at = datetime.now(UTC)
    status = _comparison_status(
        source_stable=same_source_version,
        live_values_stable=live_values_stable,
        live_formulas_stable=live_formulas_stable,
        live_cell_evidence_stable=live_cell_evidence_stable,
    )
    if missing_sheets and status == "COMPARED":
        status = "LIVE_REQUIRED_SHEETS_MISSING"
    uncovered_required_importer_coordinates = max(
        int(comparison.get("required_live_cells_missing", 0)),
        int(verification.get("required_live_cells_missing", 0)),
    )
    if uncovered_required_importer_coordinates and status == "COMPARED":
        status = "LIVE_REQUIRED_IMPORTER_CELLS_MISSING"
    bundle_source_cells = verification.pop("canonical_source_cells", [])
    comparison.pop("canonical_source_cells", None)
    bundle_summary: dict[str, Any] = (
        {"status": "NOT_CAPTURED_NON_CANONICAL_SCOPE"}
        if scope != "canonical-bootstrap"
        else {"status": "NOT_CAPTURED_CONSISTENCY_FAILED"}
    )
    if scope == "canonical-bootstrap" and status == "COMPARED":
        if not bundle_source_cells:
            bundle_summary = {"status": "BLOCKED_SOURCE_CELL_EVIDENCE_UNAVAILABLE"}
        else:
            try:
                from portfolio_api.workbook_source_bundle import (
                    SourceValueBundleError,
                    capture_source_value_bundle,
                )

                bundle_summary = capture_source_value_bundle(
                    store,
                    manifest=manifest,
                    source_cells=bundle_source_cells,
                    comparison={
                        "consistency_result": status,
                        "scope": scope,
                        "comparison_contract_version": COMPARISON_CONTRACT_VERSION,
                        "comparison_attempt_id": comparison_attempt_id,
                        "live_cell_evidence_sha256": verification["live_cell_evidence_sha256"],
                        "expected_importer_cell_count": verification[
                            "expected_importer_cell_count"
                        ],
                        "consistency_checks": {
                            "snapshot_metadata_matched_before_capture": metadata_matches_snapshot,
                            "source_metadata_unchanged_before_and_after": same_source_version,
                            "live_values_stable_across_two_reads": live_values_stable,
                            "live_formula_definitions_stable_across_two_reads": (
                                live_formulas_stable
                            ),
                            "live_source_cell_evidence_stable_across_two_reads": (
                                live_cell_evidence_stable
                            ),
                            "required_importer_coordinates_covered_in_both_reads": (
                                uncovered_required_importer_coordinates == 0
                            ),
                        },
                    },
                    comparison_started_at_utc=comparison_started_at.isoformat(),
                    comparison_completed_at_utc=comparison_completed_at.isoformat(),
                    consistency_protocol=consistency_protocol,
                )
            except SourceValueBundleError as error:
                bundle_summary = {
                    "status": "BLOCKED_CAPTURE",
                    "reason": str(error),
                }
    report = {
        "report_version": COMPARISON_REPORT_VERSION,
        "comparison_contract_version": COMPARISON_CONTRACT_VERSION,
        "run_id": run_id,
        "scope": scope,
        "source_identity_sha256": identity,
        "snapshot_artifact_sha256": manifest["artifact_sha256"],
        "snapshot_semantic_sha256": manifest["semantic_sha256"],
        "snapshot_semantic_fingerprint_version": SEMANTIC_FINGERPRINT_VERSION,
        "snapshot_source_revision": expected_revision,
        "snapshot_source_modified_at": expected_modified,
        "consistency_protocol": consistency_protocol,
        "comparison_started_at_utc": comparison_started_at.isoformat(),
        "comparison_completed_at_utc": comparison_completed_at.isoformat(),
        "source_revision_matches_snapshot": (
            expected_revision == before.get("headRevisionId")
            if expected_revision is not None
            else None
        ),
        "source_modified_at_matches_snapshot": expected_modified == before.get("modifiedTime"),
        "source_metadata_matches_snapshot": True,
        "live_source_stable_during_comparison": same_source_version,
        "request_count": sum(request_counts.values()),
        "consistency_result": status,
        "progress": {"first_pass": first_progress, "second_pass": second_progress},
        "missing_required_sheets": sorted(set(missing_sheets)),
        "live_values_stable_across_reads": live_values_stable,
        "live_formula_definitions_stable_across_reads": live_formulas_stable,
        "live_source_cell_evidence_stable_across_reads": live_cell_evidence_stable,
        "live_cell_evidence_sha256": verification["live_cell_evidence_sha256"],
        "uncovered_required_importer_coordinates": uncovered_required_importer_coordinates,
        # Kept for existing sanitized diagnostics; this counts uncovered coordinates,
        # not empty CellData slots inside confirmed ranges.
        "required_live_cells_missing": uncovered_required_importer_coordinates,
        "canonical_source_bundle": bundle_summary,
        "verification_live_semantic_sha256": verification["live_semantic_sha256"],
        "source_fidelity_review_required_count": sum(
            int(item["source_fidelity_review_required"])
            for item in comparison.get("differences", [])
        ),
        "canonical_value_changed_count": sum(
            int(item["canonical_value_changed"]) for item in comparison.get("differences", [])
        ),
        **comparison,
        "status": status,
        "interpretation": (
            (
                "Drive revision metadata and modification time matched the frozen manifest; "
                if expected_revision is not None
                else "Drive revision metadata was unavailable. Exact file identity and "
                "modification time matched the frozen manifest, and two bounded importer-value "
                "and formula-definition reads were stable; this is a semantic consistency "
                "fence, not a Drive transaction token. "
            )
            + "The source metadata remained stable across both sweeps. A formula-result "
            "difference is evidence of an export/live mismatch, not proof of its cause."
            if status == "COMPARED"
            else "The source metadata, importer values, or formula definitions changed during "
            "the bounded comparison; this diagnostic cannot support source-value acceptance."
        ),
    }
    _write_private_report(
        store,
        run_id,
        report,
        comparison_started_at=comparison_started_at,
        comparison_attempt_id=comparison_attempt_id,
        comparison_completed_at=comparison_completed_at,
    )
    return {
        "status": report["status"],
        "run_id": run_id,
        "scope": scope,
        "comparison_contract_version": COMPARISON_CONTRACT_VERSION,
        "required_cells": metrics["required_cells"],
        "optional_model_research_cells_excluded": metrics["optional_model_research_cells_excluded"],
        "ranges": metrics["ranges"],
        "chunks_per_pass": metrics["chunks_per_pass"],
        "source_revision_matches_snapshot": (
            expected_revision == before.get("headRevisionId")
            if expected_revision is not None
            else None
        ),
        "source_modified_at_matches_snapshot": expected_modified == before.get("modifiedTime"),
        "source_metadata_matches_snapshot": True,
        "consistency_protocol": consistency_protocol,
        "source_stable_during_comparison": same_source_version,
        "cells_compared": comparison["cells_compared"],
        "compared_cells": comparison["cells_compared"],
        "mismatch_classes": comparison["differences_by_class"],
        "value_relations": comparison.get("value_relations", {}),
        "formula_relations": comparison.get("formula_relations", {}),
        "number_format_relations": comparison.get("number_format_relations", {}),
        "importer_semantic_relations": comparison.get("importer_semantic_relations", {}),
        "source_fidelity_review_required_count": report["source_fidelity_review_required_count"],
        "canonical_value_changed_count": report["canonical_value_changed_count"],
        "request_count": sum(request_counts.values()),
        "live_values_stable_across_reads": live_values_stable,
        "live_formula_definitions_stable_across_reads": live_formulas_stable,
        "live_source_cell_evidence_stable_across_reads": live_cell_evidence_stable,
        "uncovered_required_importer_coordinates": uncovered_required_importer_coordinates,
        "required_live_cells_missing": uncovered_required_importer_coordinates,
        "canonical_source_bundle": bundle_summary,
        "progress": {"first_pass": first_progress, "second_pass": second_progress},
        "requested_cells_per_pass": metrics["requested_cells_per_pass"],
        "estimated_total_requests": metrics["estimated_total_requests"],
        "maximum_http_attempts_including_retries": metrics[
            "maximum_http_attempts_including_retries"
        ],
        "work_budget_limits": metrics["work_budget_limits"],
        "work_budget_exceeded": metrics["work_budget_exceeded"],
        "consistency_result": status,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="Frozen portfolio acquisition run ID")
    parser.add_argument("--store", type=Path, required=True, help="Private workbook snapshot store")
    parser.add_argument(
        "--scope",
        choices=("canonical-bootstrap", "optional-model-research", "all-importers"),
        default="canonical-bootstrap",
        help=(
            "Compare initial-bootstrap inputs (default), optional model/research inputs, "
            "or all importer inputs."
        ),
    )
    parser.add_argument(
        "--confirm-read-only-live-comparison",
        action="store_true",
        help="Authorize bounded Google Drive metadata and Sheets read-only requests",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.confirm_read_only_live_comparison:
        print("Pass --confirm-read-only-live-comparison to continue.", file=sys.stderr)
        return 2
    try:
        settings = Settings()
        store = SnapshotStore(args.store)
        result = compare_snapshot(
            run_id=args.run_id,
            store=store,
            settings=settings,
            scope=args.scope,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "COMPARED" and not result.get("mismatch_classes") else 1
    except (ValueComparisonError, WorkbookSourceError) as error:
        print(f"SOURCE_VALUE_COMPARISON_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
