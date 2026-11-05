"""Minimal, versioned Google Sheets-to-canonical portfolio bootstrap.

Only company identities, held listing identities, holdings/cash, and target weights
are read. The capture is an observed consistent state guarded by source metadata and
two complete value sweeps; Google Sheets does not provide a transaction snapshot.
"""

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
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from portfolio_api import legacy_import
from portfolio_api.bootstrap_preflight import (
    BootstrapPreflightError,
    verify_database_preflight,
    verify_database_read_only_preflight,
)
from portfolio_api.canonical_bootstrap import resolve_approved_snapshot
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import DatabaseWriteTargetError
from portfolio_api.domain.models import (
    CanonicalBootstrapRun,
    CashPosition,
    Company,
    CurrentLifecycle,
    HoldingPosition,
    HoldingSnapshot,
    LegacyImportBatch,
    LifecycleEvent,
    Listing,
    Portfolio,
    RankingEntry,
    RankingRun,
    ScoreAssessment,
    Security,
    TargetAllocation,
    TargetRevision,
    now,
)
from portfolio_api.settings import Settings
from portfolio_api.workbook_sources import (
    DRIVE_FILES_API,
    GOOGLE_SHEET_MIME,
    MARKET_DATA_PROFILE,
    SnapshotStore,
    WorkbookSourceError,
    _assert_private_location,
    load_google_sheets_readonly_session,
)
from portfolio_api.workbook_value_validation import (
    ValueComparisonError,
    _cell_grid_index,
    _column_name,
)

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
SOURCE_CONTRACT_VERSION = "canonical-portfolio-sheets-minimal-v1"
IMPORT_VERSION = "canonical-sheets-minimal-v1"
MAX_ROWS_PER_SHEET = 5_000
MAX_CAPTURE_CELLS = 40_000
MAX_CAPTURE_RANGES = 12
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
REQUEST_SPACING_SECONDS = 0.12
RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,39}$")
_GRID_FIELDS = (
    "spreadsheetId,sheets(properties(title),data(startRow,startColumn,"
    "rowData(values(userEnteredValue,effectiveValue,"
    "effectiveFormat(numberFormat(type,pattern))))))"
)
_STRUCTURE_FIELDS = (
    "spreadsheetId,properties(timeZone),sheets(properties(sheetId,title,"
    "gridProperties(rowCount,columnCount)))"
)
_DRIVE_FIELDS = "id,mimeType,modifiedTime,headRevisionId,md5Checksum,size"


class SheetsPortfolioError(ValueError):
    """Sanitized source-capture or minimal-bootstrap error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CapturedSource:
    run_id: str
    sha256: str
    semantic_sha256: str
    manifest: dict[str, Any]
    bundle: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class MinimalPlan:
    plan: legacy_import.ImportPlan
    source: CapturedSource
    market_run_id: str
    market_sha256: str
    market_schema_sha256: str
    input_sha256: str
    projection: dict[str, Any]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise SheetsPortfolioError("NONFINITE_SOURCE_VALUE", "A source value is non-finite.")
        return {"decimal": str(value)}
    if isinstance(value, dict):
        if set(value) == {"numberValue"}:
            number = value["numberValue"]
            if isinstance(number, int) and not isinstance(number, bool):
                return {"numberValue": {"decimal": str(number)}}
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise SheetsPortfolioError(
        "SOURCE_VALUE_TYPE_UNSUPPORTED", "A source value has an unsupported type."
    )


def _private_json(path: Path, payload: bytes, expected_sha256: str) -> None:
    """Create an immutable private file, accepting only an identical prior blob."""
    if path.is_symlink():
        raise SheetsPortfolioError("SNAPSHOT_SYMLINK_FORBIDDEN", "A snapshot path is symlinked.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.parent.chmod(0o700)
    if path.exists():
        if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != expected_sha256:
            raise SheetsPortfolioError(
                "SNAPSHOT_BLOB_CONFLICT", "An existing snapshot blob failed integrity validation."
            )
        return
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != expected_sha256:
            raise SheetsPortfolioError(
                "SNAPSHOT_BLOB_CONFLICT", "A concurrent snapshot failed integrity validation."
            ) from None
    except OSError:
        raise SheetsPortfolioError(
            "SNAPSHOT_WRITE_FAILED", "The private Sheets snapshot could not be stored."
        ) from None
    with suppress(OSError):
        path.chmod(0o600)


def _write_run_manifest(run_root: Path, manifest: dict[str, Any]) -> Path:
    if run_root.is_symlink():
        raise SheetsPortfolioError(
            "SNAPSHOT_SYMLINK_FORBIDDEN", "A run manifest path is symlinked."
        )
    run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        run_root.chmod(0o700)
    path = run_root / f"{manifest['run_id']}.json"
    payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise SheetsPortfolioError(
            "SNAPSHOT_MANIFEST_WRITE_FAILED", "The immutable source manifest could not be written."
        ) from None
    return path


def _manifest_sha256(manifest: Mapping[str, Any]) -> str:
    values = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return _sha256(_canonical_json(values))


def _quoted_range(
    sheet: str, start_column: str, start_row: int, end_column: str, end_row: int
) -> tuple[str, str, int]:
    quoted_sheet = "'" + sheet.replace("'", "''") + "'"
    a1 = f"{quoted_sheet}!{start_column}{start_row}:{end_column}{end_row}"
    width = _column_number(end_column) - _column_number(start_column) + 1
    return sheet, a1, width * (end_row - start_row + 1)


def _column_number(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character.upper()) - 64
    return result


def _contract_ranges(
    structure: dict[str, Any],
) -> tuple[list[tuple[str, str, int]], dict[str, dict[str, int]]]:
    sheets = structure.get("sheets")
    if not isinstance(sheets, list):
        raise SheetsPortfolioError(
            "SHEET_STRUCTURE_INVALID", "Google did not return workbook sheet metadata."
        )
    by_title: dict[str, dict[str, int]] = {}
    for sheet in sheets:
        properties = sheet.get("properties") if isinstance(sheet, dict) else None
        grid = properties.get("gridProperties") if isinstance(properties, dict) else None
        title = properties.get("title") if isinstance(properties, dict) else None
        if not isinstance(title, str) or not isinstance(grid, dict):
            raise SheetsPortfolioError(
                "SHEET_STRUCTURE_INVALID", "Google returned malformed worksheet metadata."
            )
        rows, columns = grid.get("rowCount"), grid.get("columnCount")
        if (
            isinstance(rows, bool)
            or isinstance(columns, bool)
            or not isinstance(rows, int)
            or not isinstance(columns, int)
        ):
            raise SheetsPortfolioError(
                "SHEET_STRUCTURE_INVALID", "Google returned invalid worksheet dimensions."
            )
        if title in by_title:
            raise SheetsPortfolioError(
                "SHEET_STRUCTURE_INVALID", "Google returned duplicate worksheet names."
            )
        by_title[title] = {"row_count": rows, "column_count": columns}

    required_columns = {
        "Universe Registry": 2,
        "Current Holdings": 12,
        "Target Architecture": 16,
        "Price Feed": 8,
    }
    for title, minimum_columns in required_columns.items():
        dimensions = by_title.get(title)
        if (
            dimensions is None
            or dimensions["row_count"] < 5
            or dimensions["column_count"] < minimum_columns
        ):
            raise SheetsPortfolioError(
                "WORKBOOK_CONTRACT_INCOMPLETE",
                "A required portfolio worksheet or column is missing.",
            )
        if dimensions["row_count"] > MAX_ROWS_PER_SHEET:
            raise SheetsPortfolioError(
                "CAPTURE_ROW_LIMIT_EXCEEDED",
                "A required worksheet exceeds the bounded source-capture row limit.",
            )

    ranges = [
        _quoted_range("Universe Registry", "A", 4, "B", by_title["Universe Registry"]["row_count"]),
        _quoted_range("Current Holdings", "A", 4, "B", by_title["Current Holdings"]["row_count"]),
        _quoted_range("Current Holdings", "D", 4, "E", by_title["Current Holdings"]["row_count"]),
        _quoted_range("Current Holdings", "G", 4, "G", by_title["Current Holdings"]["row_count"]),
        _quoted_range("Current Holdings", "L", 4, "L", 4),
        _quoted_range(
            "Target Architecture", "A", 4, "A", by_title["Target Architecture"]["row_count"]
        ),
        _quoted_range(
            "Target Architecture", "D", 4, "D", by_title["Target Architecture"]["row_count"]
        ),
        _quoted_range("Target Architecture", "P", 3, "P", 3),
        _quoted_range("Price Feed", "A", 5, "D", by_title["Price Feed"]["row_count"]),
        _quoted_range("Price Feed", "H", 5, "H", by_title["Price Feed"]["row_count"]),
    ]
    if len(ranges) > MAX_CAPTURE_RANGES or sum(item[2] for item in ranges) > MAX_CAPTURE_CELLS:
        raise SheetsPortfolioError(
            "CAPTURE_CELL_LIMIT_EXCEEDED",
            "The complete minimal import scope exceeds the bounded source-capture cell limit.",
        )
    return ranges, by_title


class SheetsPortfolioReader:
    """Direct read-only Sheets/Drive reader with one whole-capture consistency fence."""

    def __init__(
        self,
        settings: Settings,
        session: Any | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        spreadsheet_id = settings.google_sheets_spreadsheet_id
        credential_path = settings.google_sheets_service_account_file
        if not spreadsheet_id or not credential_path:
            raise SheetsPortfolioError(
                "NOT_CONFIGURED",
                "Set GOOGLE_SHEETS_SPREADSHEET_ID and GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE.",
            )
        if (
            settings.google_drive_portfolio_workbook_file_id
            and settings.google_drive_portfolio_workbook_file_id != spreadsheet_id
        ):
            raise SheetsPortfolioError(
                "PORTFOLIO_SOURCE_ID_CONFLICT",
                "The configured portfolio Drive and Sheets identities differ.",
            )
        self.spreadsheet_id = spreadsheet_id
        self.timeout = settings.google_sheets_request_timeout_seconds
        self.session = session or load_google_sheets_readonly_session(credential_path)
        self.sleeper = sleeper
        self.clock = clock
        self._last_request_at: float | None = None
        self.request_attempt_count = 0

    def _get_json(self, url: str, params: Mapping[str, str]) -> dict[str, Any]:
        for attempt in range(1, MAX_RETRIES + 1):
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                if elapsed < REQUEST_SPACING_SECONDS:
                    self.sleeper(REQUEST_SPACING_SECONDS - elapsed)
            try:
                self.request_attempt_count += 1
                response = self.session.get(
                    url, params=params, timeout=(5, self.timeout), stream=True
                )
            except Exception as error:
                raise SheetsPortfolioError(
                    "GOOGLE_NETWORK_ERROR",
                    f"A read-only Google request failed ({type(error).__name__}).",
                ) from None
            self._last_request_at = time.monotonic()
            status = getattr(response, "status_code", 0)
            if status in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                headers = getattr(response, "headers", {})
                retry_after = headers.get("Retry-After") if isinstance(headers, Mapping) else None
                try:
                    delay = (
                        min(5.0, max(REQUEST_SPACING_SECONDS, float(retry_after)))
                        if retry_after
                        else min(2.0, 0.25 * 2 ** (attempt - 1))
                    )
                except (TypeError, ValueError):
                    delay = min(2.0, 0.25 * 2 ** (attempt - 1))
                self.sleeper(delay)
                continue
            if not isinstance(status, int) or status >= 400:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                safe_status = status if isinstance(status, int) else "unknown"
                raise SheetsPortfolioError(
                    "GOOGLE_API_ERROR",
                    f"Google returned HTTP {safe_status} for a read-only request.",
                )
            try:
                body = self._bounded_response_body(response)
            except SheetsPortfolioError:
                raise
            except Exception:
                raise SheetsPortfolioError(
                    "GOOGLE_RESPONSE_INVALID", "A bounded Google response could not be read."
                ) from None
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
            try:
                parsed = json.loads(body.decode("utf-8"), parse_float=Decimal, parse_int=int)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise SheetsPortfolioError(
                    "GOOGLE_RESPONSE_INVALID", "Google returned malformed JSON."
                ) from None
            if not isinstance(parsed, dict):
                raise SheetsPortfolioError(
                    "GOOGLE_RESPONSE_INVALID", "Google returned a malformed JSON object."
                )
            return parsed
        raise SheetsPortfolioError("GOOGLE_RETRY_LIMIT", "Google request retry limit was reached.")

    @staticmethod
    def _bounded_response_body(response: Any) -> bytes:
        chunks = getattr(response, "iter_content", None)
        if callable(chunks):
            content = bytearray()
            for chunk in chunks(chunk_size=64 * 1024):
                if not isinstance(chunk, bytes):
                    raise SheetsPortfolioError(
                        "GOOGLE_RESPONSE_INVALID", "Google returned an invalid response chunk."
                    )
                if not chunk:
                    continue
                if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise SheetsPortfolioError(
                        "GOOGLE_RESPONSE_OVERSIZED",
                        "A Google response exceeded the bounded byte limit.",
                    )
                content.extend(chunk)
            body = bytes(content)
        else:
            fallback_body = getattr(response, "content", None)
            if not isinstance(fallback_body, bytes):
                raise SheetsPortfolioError(
                    "GOOGLE_RESPONSE_INVALID", "Google returned an invalid response body."
                )
            body = fallback_body
        if not body or len(body) > MAX_RESPONSE_BYTES:
            raise SheetsPortfolioError(
                "GOOGLE_RESPONSE_INVALID", "A bounded Google response was empty or oversized."
            )
        return body

    def _drive_metadata(self) -> dict[str, Any]:
        url = f"{DRIVE_FILES_API}/{quote(self.spreadsheet_id, safe='')}"
        metadata = self._get_json(url, {"fields": _DRIVE_FIELDS})
        if (
            metadata.get("id") != self.spreadsheet_id
            or metadata.get("mimeType") != GOOGLE_SHEET_MIME
        ):
            raise SheetsPortfolioError(
                "PORTFOLIO_SOURCE_IDENTITY_MISMATCH",
                "The configured source is not the exact native Google spreadsheet.",
            )
        modified = metadata.get("modifiedTime")
        if not isinstance(modified, str) or not modified:
            raise SheetsPortfolioError(
                "SOURCE_METADATA_INCOMPLETE", "Drive did not return a source modification time."
            )
        identity = {
            "source_identity_sha256": _sha256(self.spreadsheet_id.encode("utf-8")),
            "mime_type": metadata["mimeType"],
            "modified_time": modified,
            "head_revision_id": metadata.get("headRevisionId"),
            "checksum": metadata.get("md5Checksum"),
            "size": metadata.get("size"),
        }
        return identity

    def _structure(self) -> dict[str, Any]:
        url = f"{SHEETS_API}/{quote(self.spreadsheet_id, safe='')}"
        structure = self._get_json(url, {"fields": _STRUCTURE_FIELDS})
        if structure.get("spreadsheetId") != self.spreadsheet_id:
            raise SheetsPortfolioError(
                "PORTFOLIO_SOURCE_IDENTITY_MISMATCH",
                "Sheets returned a different spreadsheet identity.",
            )
        ranges, dimensions = _contract_ranges(structure)
        manifest = {
            "time_zone": (structure.get("properties") or {}).get("timeZone"),
            "sheets": [
                {
                    "sheet_id": item["properties"].get("sheetId"),
                    "title": item["properties"].get("title"),
                    **dimensions[item["properties"]["title"]],
                }
                for item in structure["sheets"]
                if item["properties"]["title"] in dimensions
            ],
        }
        manifest["structure_sha256"] = _sha256(_canonical_json(manifest))
        return {"manifest": manifest, "ranges": ranges, "dimensions": dimensions}

    def _sweep(
        self, ranges: list[tuple[str, str, int]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        cells: dict[tuple[str, int, int], dict[str, Any]] = {}
        stats: Counter[str] = Counter()
        for item in ranges:
            sheet, a1_range, expected_area = item
            result = self._get_json(
                f"{SHEETS_API}/{quote(self.spreadsheet_id, safe='')}",
                {"ranges": a1_range, "includeGridData": "true", "fields": _GRID_FIELDS},
            )
            if result.get("spreadsheetId") != self.spreadsheet_id:
                raise SheetsPortfolioError(
                    "PORTFOLIO_SOURCE_IDENTITY_MISMATCH",
                    "Sheets returned a different spreadsheet identity during value capture.",
                )
            try:
                values, formats, present_sheets, presence, cell_stats = _cell_grid_index(
                    result, [item]
                )
            except ValueComparisonError as error:
                raise SheetsPortfolioError(
                    "SHEETS_RANGE_INCOMPLETE",
                    f"Requested Sheets range {a1_range} failed GridData validation: {error}",
                ) from None
            if sheet not in present_sheets or cell_stats["coordinates_covered"] != expected_area:
                raise SheetsPortfolioError(
                    "SHEETS_RANGE_INCOMPLETE",
                    f"Requested Sheets range {a1_range} did not cover its declared dimensions.",
                )
            for (row, column), raw_cell in values[sheet].items():
                cell = {
                    "sheet": sheet,
                    "row": row,
                    "column": _column_name(column),
                    "cell_state": presence[sheet][(row, column)],
                    "user_entered_value": _json_value(raw_cell.get("userEnteredValue")),
                    "effective_value": _json_value(raw_cell.get("effectiveValue")),
                    "effective_number_format_type": formats[sheet][(row, column)],
                    "effective_number_format_pattern": _json_value(
                        (raw_cell.get("effectiveFormat") or {})
                        .get("numberFormat", {})
                        .get("pattern")
                        if isinstance(raw_cell.get("effectiveFormat"), dict)
                        and isinstance(
                            (raw_cell.get("effectiveFormat") or {}).get("numberFormat"), dict
                        )
                        else None
                    ),
                }
                key = (sheet, row, column)
                if key in cells:
                    raise SheetsPortfolioError(
                        "SHEETS_RANGE_DUPLICATE",
                        "The source contract requested a duplicate cell range.",
                    )
                cells[key] = cell
            stats.update(cell_stats)
        ordered = sorted(
            cells.values(),
            key=lambda item: (item["sheet"], item["row"], _column_number(item["column"])),
        )
        return ordered, dict(stats)

    def capture(self, store: SnapshotStore) -> CapturedSource:
        root = _assert_private_location(store.root, label="native Sheets snapshot store")
        source_root = root / "native-sheets-portfolio-v1"
        for directory in (
            source_root,
            source_root / "blobs",
            source_root / "blobs" / "sha256",
            source_root / "runs",
        ):
            if directory.is_symlink():
                raise SheetsPortfolioError(
                    "SNAPSHOT_SYMLINK_FORBIDDEN",
                    "The native Sheets snapshot store cannot contain a symlink.",
                )
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                directory.chmod(0o700)

        drive_before = self._drive_metadata()
        structure_before = self._structure()
        first_cells, first_stats = self._sweep(structure_before["ranges"])
        second_cells, second_stats = self._sweep(structure_before["ranges"])
        structure_after = self._structure()
        drive_after = self._drive_metadata()
        if (
            drive_before != drive_after
            or structure_before["manifest"] != structure_after["manifest"]
        ):
            raise SheetsPortfolioError(
                "SOURCE_CHANGED_DURING_CAPTURE",
                "Google source identity, revision metadata, or worksheet structure changed "
                "during capture.",
            )
        if first_cells != second_cells:
            raise SheetsPortfolioError(
                "SOURCE_CHANGED_DURING_CAPTURE",
                "Importer-relevant Sheets values changed between complete reads.",
            )

        bundle = {
            "bundle_version": SOURCE_CONTRACT_VERSION,
            "source_identity_sha256": drive_before["source_identity_sha256"],
            "source_metadata": drive_before,
            "structure": structure_before["manifest"],
            "ranges": [
                {"sheet": sheet, "a1_range": address, "area": area}
                for sheet, address, area in structure_before["ranges"]
            ],
            "cells": first_cells,
            "capture_semantics": "observed-consistent-state-not-transactional-snapshot",
        }
        payload = _canonical_json(bundle) + b"\n"
        digest = _sha256(payload)
        captured_time = self.clock()
        if captured_time.tzinfo is None or captured_time.utcoffset() is None:
            raise SheetsPortfolioError(
                "CAPTURE_TIME_INVALID", "The source capture clock must be timezone-aware."
            )
        captured_time = captured_time.astimezone(UTC)
        if captured_time > datetime.now(UTC):
            raise SheetsPortfolioError(
                "CAPTURE_TIME_INVALID", "The source capture time cannot be in the future."
            )
        captured_at = captured_time.isoformat().replace("+00:00", "Z")
        run_id = uuid.uuid4().hex
        blob_path = source_root / "blobs" / "sha256" / f"{digest}.json"
        _private_json(blob_path, payload, digest)
        manifest = {
            "manifest_version": 1,
            "run_id": run_id,
            "profile": "native-sheets-minimal-portfolio",
            "contract_version": SOURCE_CONTRACT_VERSION,
            "status": "CAPTURED_REVIEW_REQUIRED",
            "source_identity_sha256": drive_before["source_identity_sha256"],
            "source_modified_at": drive_before["modified_time"],
            "source_revision": drive_before["head_revision_id"],
            "source_checksum": drive_before["checksum"],
            "captured_at": captured_at,
            "captured_state_is_transactional": False,
            "consistency_protocol": (
                "drive-metadata-and-sheet-structure-before-and-after-plus-two-complete-"
                "effective-value-sweeps"
            ),
            "ranges": len(structure_before["ranges"]),
            "captured_cells": len(first_cells),
            "sweep_one": first_stats,
            "sweep_two": second_stats,
            "artifact_sha256": digest,
            "semantic_sha256": digest,
            "artifact_path": str(blob_path.relative_to(root)),
            "required_schema_review": True,
            "import_triggered": False,
        }
        manifest["manifest_sha256"] = _manifest_sha256(manifest)
        _write_run_manifest(source_root / "runs", manifest)
        return CapturedSource(run_id, digest, digest, manifest, bundle, blob_path)


def _column_address(column: str, row: int) -> str:
    return f"{column}{row}"


def _workbook_source_ref(workbook: legacy_import.Workbook, sheet: str, cell: str) -> str:
    source_name = workbook.source_name or workbook.path.name
    return f"{source_name}:{sheet}!{cell}#sha256:{workbook.sha256}"


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


def _bundle_cell_map(bundle: dict[str, Any]) -> dict[tuple[str, int, str], dict[str, Any]]:
    result: dict[tuple[str, int, str], dict[str, Any]] = {}
    cells = bundle.get("cells")
    if not isinstance(cells, list):
        raise SheetsPortfolioError(
            "SNAPSHOT_INVALID", "The native Sheets snapshot has no cell records."
        )
    for item in cells:
        if not isinstance(item, dict):
            raise SheetsPortfolioError(
                "SNAPSHOT_INVALID", "The native Sheets snapshot contains an invalid cell record."
            )
        key = (item.get("sheet"), item.get("row"), item.get("column"))
        if (
            not isinstance(key[0], str)
            or isinstance(key[1], bool)
            or not isinstance(key[1], int)
            or not isinstance(key[2], str)
            or key in result
        ):
            raise SheetsPortfolioError(
                "SNAPSHOT_INVALID",
                "The native Sheets snapshot contains duplicate or malformed coordinates.",
            )
        result[(str(key[0]), int(key[1]), str(key[2]))] = item
    return result


def _effective(cell: dict[str, Any] | None) -> tuple[str, str | None, str | None]:
    if cell is None:
        return "UNVERIFIED_MISSING", None, None
    value = cell.get("effective_value")
    if not isinstance(value, dict):
        entered = cell.get("user_entered_value")
        formula = isinstance(entered, dict) and isinstance(entered.get("formulaValue"), str)
        return ("FORMULA_EMPTY_RESULT" if formula else "BLANK"), None, None
    if (
        set(value) == {"numberValue"}
        and isinstance(value.get("numberValue"), dict)
        and set(value["numberValue"]) == {"decimal"}
        and isinstance(value["numberValue"].get("decimal"), str)
    ):
        decimal_text = value["numberValue"]["decimal"]
        return ("NUMBER_ZERO" if Decimal(decimal_text) == 0 else "NUMBER"), decimal_text, "number"
    if set(value) == {"stringValue"} and isinstance(value.get("stringValue"), str):
        text = value["stringValue"]
        return ("EMPTY_STRING" if text == "" else "STRING"), text, "string"
    if set(value) == {"boolValue"} and isinstance(value.get("boolValue"), bool):
        return "BOOLEAN", "TRUE" if value["boolValue"] else "FALSE", "boolean"
    if set(value) == {"errorValue"} and isinstance(value.get("errorValue"), dict):
        error_type = value["errorValue"].get("type")
        return "ERROR", str(error_type or "UNKNOWN"), "error"
    raise SheetsPortfolioError(
        "SNAPSHOT_CELL_TYPE_INVALID", "The snapshot contains an unsupported effective cell value."
    )


def _load_source_snapshot(
    store: SnapshotStore, run_id: str, expected_sha256: str
) -> CapturedSource:
    if not RUN_ID_PATTERN.fullmatch(run_id) or not SHA256_PATTERN.fullmatch(expected_sha256):
        raise SheetsPortfolioError(
            "SNAPSHOT_ID_INVALID", "Use a valid snapshot run ID and lowercase SHA-256."
        )
    source_root = store.root / "native-sheets-portfolio-v1"
    for directory in (
        source_root,
        source_root / "runs",
        source_root / "blobs",
        source_root / "blobs" / "sha256",
    ):
        if directory.is_symlink() or not directory.is_dir():
            raise SheetsPortfolioError(
                "SNAPSHOT_PATH_INVALID",
                "The selected snapshot store path is not a private directory.",
            )
    manifest_path = source_root / "runs" / f"{run_id}.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SheetsPortfolioError(
            "SNAPSHOT_NOT_FOUND", "The selected direct Sheets snapshot was not found."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SheetsPortfolioError(
            "SNAPSHOT_MANIFEST_INVALID", "The selected snapshot manifest is unreadable."
        ) from None
    if (
        not isinstance(manifest, dict)
        or manifest.get("contract_version") != SOURCE_CONTRACT_VERSION
        or manifest.get("status") != "CAPTURED_REVIEW_REQUIRED"
        or manifest.get("manifest_sha256") != _manifest_sha256(manifest)
    ):
        raise SheetsPortfolioError(
            "SNAPSHOT_MANIFEST_INVALID",
            "The selected snapshot uses an unsupported or incomplete contract.",
        )
    if manifest.get("artifact_sha256") != expected_sha256 or manifest.get("run_id") != run_id:
        raise SheetsPortfolioError(
            "SNAPSHOT_HASH_MISMATCH", "The selected snapshot does not match its reviewed hash."
        )
    relative_path = manifest.get("artifact_path")
    expected_path = (
        Path("native-sheets-portfolio-v1") / "blobs" / "sha256" / f"{expected_sha256}.json"
    )
    if relative_path != str(expected_path):
        raise SheetsPortfolioError(
            "SNAPSHOT_PATH_INVALID", "The selected source blob path is invalid."
        )
    path = store.root / expected_path
    if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != expected_sha256:
        raise SheetsPortfolioError(
            "SNAPSHOT_HASH_MISMATCH", "The selected source blob failed its integrity check."
        )
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SheetsPortfolioError(
            "SNAPSHOT_INVALID", "The selected source blob is not valid JSON."
        ) from None
    if not isinstance(bundle, dict) or bundle.get("bundle_version") != SOURCE_CONTRACT_VERSION:
        raise SheetsPortfolioError(
            "SNAPSHOT_INVALID", "The selected source bundle contract is invalid."
        )
    source = CapturedSource(
        run_id, expected_sha256, str(manifest["semantic_sha256"]), manifest, bundle, path
    )
    source_metadata = bundle.get("source_metadata")
    if (
        manifest.get("semantic_sha256") != expected_sha256
        or bundle.get("source_identity_sha256") != manifest.get("source_identity_sha256")
        or not isinstance(source_metadata, dict)
        or source_metadata.get("source_identity_sha256") != manifest.get("source_identity_sha256")
        or source_metadata.get("modified_time") != manifest.get("source_modified_at")
        or source_metadata.get("head_revision_id") != manifest.get("source_revision")
        or source_metadata.get("checksum") != manifest.get("source_checksum")
        or bundle.get("capture_semantics") != "observed-consistent-state-not-transactional-snapshot"
    ):
        raise SheetsPortfolioError(
            "SNAPSHOT_PROVENANCE_MISMATCH",
            "The source manifest and captured bundle provenance do not agree.",
        )
    _validate_snapshot_coverage(source)
    return source


def _validate_snapshot_coverage(source: CapturedSource) -> None:
    structure = source.bundle.get("structure")
    if not isinstance(structure, dict) or not isinstance(structure.get("sheets"), list):
        raise SheetsPortfolioError(
            "SNAPSHOT_STRUCTURE_INVALID", "The source snapshot has no valid worksheet structure."
        )
    adapted = {
        "sheets": [
            {
                "properties": {
                    "title": item.get("title"),
                    "sheetId": item.get("sheet_id"),
                    "gridProperties": {
                        "rowCount": item.get("row_count"),
                        "columnCount": item.get("column_count"),
                    },
                }
            }
            for item in structure["sheets"]
            if isinstance(item, dict)
        ]
    }
    expected_ranges, _dimensions = _contract_ranges(adapted)
    expected_range_payload = [
        {"sheet": sheet, "a1_range": a1_range, "area": area}
        for sheet, a1_range, area in expected_ranges
    ]
    if source.bundle.get("ranges") != expected_range_payload:
        raise SheetsPortfolioError(
            "SNAPSHOT_RANGE_CONTRACT_MISMATCH",
            "The source snapshot ranges do not match the declared contract.",
        )
    expected_coordinates: set[tuple[str, int, str]] = set()
    for sheet, address, _area in expected_ranges:
        match = re.fullmatch(r"'((?:[^']|'')+)'!([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)", address)
        if match is None:
            raise SheetsPortfolioError(
                "SNAPSHOT_RANGE_CONTRACT_MISMATCH", "The source snapshot contains an invalid range."
            )
        start_column, start_row = _column_number(match.group(2)), int(match.group(3))
        end_column, end_row = _column_number(match.group(4)), int(match.group(5))
        for row in range(start_row, end_row + 1):
            for column in range(start_column, end_column + 1):
                expected_coordinates.add((sheet, row, _column_name(column)))
    actual_cells = _bundle_cell_map(source.bundle)
    if set(actual_cells) != expected_coordinates:
        raise SheetsPortfolioError(
            "SNAPSHOT_CELL_COVERAGE_INVALID",
            "The source snapshot is missing or contains unexpected importer coordinates.",
        )
    if source.bundle.get("source_identity_sha256") != source.manifest.get("source_identity_sha256"):
        raise SheetsPortfolioError(
            "SNAPSHOT_SOURCE_IDENTITY_MISMATCH",
            "The source bundle identity does not match its manifest.",
        )
    structure_fingerprint = structure.get("structure_sha256")
    structure_values = {key: value for key, value in structure.items() if key != "structure_sha256"}
    if structure_fingerprint != _sha256(_canonical_json(structure_values)):
        raise SheetsPortfolioError(
            "SNAPSHOT_STRUCTURE_HASH_MISMATCH",
            "The captured worksheet structure failed its integrity check.",
        )


def _captured_workbook(source: CapturedSource) -> legacy_import.Workbook:
    cells: dict[str, dict[str, legacy_import.Cell]] = defaultdict(dict)
    for item in source.bundle["cells"]:
        state, value, kind = _effective(item)
        entered = item.get("user_entered_value")
        formula = entered.get("formulaValue") if isinstance(entered, dict) else None
        formula = formula.strip().removeprefix("=").strip() if isinstance(formula, str) else None
        cell_kind = {"number": "n", "string": "str", "boolean": "b", "error": "e"}.get(kind or "")
        if state in {"BLANK", "FORMULA_EMPTY_RESULT", "UNVERIFIED_MISSING"}:
            value_text = None
        else:
            value_text = value
        address = _column_address(item["column"], item["row"])
        cells[item["sheet"]][address] = legacy_import.Cell(
            value=value_text,
            kind=cell_kind,
            formula=formula,
            number_format_type=item.get("effective_number_format_type"),
            number_format_code=item.get("effective_number_format_pattern"),
        )
    return legacy_import.Workbook(
        path=source.path,
        sha256=source.sha256,
        sheets=dict(cells),
        source_name=f"Google Sheets source snapshot {source.run_id}",
    )


def _cell_value(workbook: legacy_import.Workbook, sheet: str, address: str) -> str | None:
    cell = workbook.cell(sheet, address)
    if cell.value is None:
        return None
    value = cell.value.strip()
    return value or None


def _header_value(workbook: legacy_import.Workbook, sheet: str, address: str) -> str | None:
    return _cell_value(workbook, sheet, address)


def _text_value_cell(workbook: legacy_import.Workbook, sheet: str, address: str) -> bool:
    cell = workbook.cell(sheet, address)
    return cell.value is None or cell.kind in {"str", "inlineStr", "s"}


def _validate_headers(workbook: legacy_import.Workbook) -> None:
    expected = {
        ("Universe Registry", "A4"): "ticker",
        ("Universe Registry", "B4"): "company",
        ("Current Holdings", "A4"): "type",
        ("Current Holdings", "B4"): "portfolio ticker",
        ("Current Holdings", "D4"): "price feed ticker",
        ("Current Holdings", "E4"): "shares / native cash",
        ("Current Holdings", "G4"): "currency",
        ("Target Architecture", "A4"): "ticker",
        ("Target Architecture", "D4"): "target weight (edit here)",
    }
    for (sheet, address), expected_value in expected.items():
        actual = _header_value(workbook, sheet, address)
        if actual is None or _normalize_text(actual) != expected_value:
            raise SheetsPortfolioError(
                "WORKBOOK_HEADER_CONTRACT_MISMATCH",
                "A required importer header differs from the minimal Sheets contract.",
            )


@dataclass(frozen=True)
class _MarketListing:
    listing_row: legacy_import.ListingRow
    market_symbol: str
    listing_ticker: str
    canonical_ticker: str
    status: str
    row_number: int


def _read_market_listings(
    workbook: legacy_import.Workbook,
) -> tuple[dict[str, list[_MarketListing]], list[dict[str, Any]]]:
    by_company: dict[str, list[_MarketListing]] = defaultdict(list)
    exceptions: list[dict[str, Any]] = []
    seen_venue_tickers: dict[tuple[str, str], str] = {}
    for row_number, row in workbook.rows("Listings", 5):
        raw_key = legacy_import._value(row, "A")
        if raw_key is None:
            continue
        key = legacy_import._ticker_key(raw_key)
        status = (legacy_import._value(row, "K") or "").upper()
        source = _workbook_source_ref(workbook, "Listings", f"A{row_number}:K{row_number}")
        if any(
            not _text_value_cell(workbook, "Listings", f"{column}{row_number}")
            for column in ("A", "B", "C", "D", "E", "G", "K")
        ):
            exceptions.append({"kind": "LISTING_FIELD_TYPE_INVALID", "key": key, "source": source})
            continue
        if any(
            workbook.cell("Listings", f"{column}{row_number}").formula
            for column in ("A", "B", "C", "D", "E", "G", "K")
        ):
            exceptions.append(
                {"kind": "LISTING_IDENTITY_FORMULA_UNSUPPORTED", "key": key, "source": source}
            )
            continue
        if status != "READY":
            exceptions.append({"kind": "LISTING_NOT_READY", "key": key, "source": source})
            continue
        values = {column: legacy_import._value(row, column) for column in ("B", "C", "D", "E", "G")}
        if any(value is None for value in values.values()) or not TICKER_PATTERN.fullmatch(key):
            exceptions.append({"kind": "LISTING_FIELDS_INCOMPLETE", "key": key, "source": source})
            continue
        name = values["B"]
        market_symbol = values["C"]
        venue = values["D"]
        currency = values["E"]
        basis = values["G"]
        if (
            name is None
            or market_symbol is None
            or venue is None
            or currency is None
            or basis is None
        ):
            continue
        match = re.fullmatch(r"([^:]+):(.+)", market_symbol.strip())
        kind = legacy_import._security_type(basis)
        if (
            match is None
            or match.group(1).strip().casefold() != venue.strip().casefold()
            or not re.fullmatch(r"[A-Z]{3}", currency)
            or kind is None
        ):
            exceptions.append({"kind": "LISTING_IDENTITY_INVALID", "key": key, "source": source})
            continue
        if kind == "ADR":
            exceptions.append(
                {"kind": "ADR_REQUIRES_EXPLICIT_AUX_MAPPING", "key": key, "source": source}
            )
            continue
        listing_ticker = match.group(2).strip()
        identity = (venue.upper(), listing_ticker.upper())
        prior = seen_venue_tickers.get(identity)
        if prior is not None and prior != key:
            exceptions.append({"kind": "DUPLICATE_VENUE_TICKER", "key": key, "source": source})
            continue
        seen_venue_tickers[identity] = key
        listing = legacy_import.ListingRow(
            listing_key=key,
            canonical_ticker=key,
            security_key=key,
            underlying_security_key=None,
            name=name.strip(),
            ticker=listing_ticker,
            venue=venue.strip(),
            currency=currency,
            security_type=kind,
            share_class=legacy_import._share_class(basis),
            source=source,
        )
        by_company[key].append(
            _MarketListing(listing, market_symbol.strip(), listing_ticker, key, status, row_number)
        )
    return by_company, exceptions


def _normalize_listing_symbol(value: str) -> str:
    value = value.strip().upper()
    if ":" in value:
        venue, ticker = value.split(":", 1)
        return f"{venue.strip()}:{ticker.strip()}"
    return value


def _resolve_aux_listing(
    portfolio: legacy_import.Workbook,
    *,
    source_ticker: str,
    source_listing: str,
    holding_kind: str,
    market_by_company: dict[str, list[_MarketListing]],
) -> tuple[legacy_import.ListingRow | None, list[legacy_import.ListingRow], str | None]:
    matches: list[legacy_import.ListingRow] = []
    underlying: list[legacy_import.ListingRow] = []
    for row_number, row in portfolio.rows("Price Feed", 5):
        if (legacy_import._value(row, "A") or "").upper() != "AUX":
            continue
        aux_key = legacy_import._ticker_key(legacy_import._value(row, "C") or "")
        if aux_key not in {"SPYY", "TSM-ADR"}:
            continue
        source = _workbook_source_ref(portfolio, "Price Feed", f"A{row_number}:H{row_number}")
        identity_columns = ("A", "B", "C", "D", "H")
        if any(
            not _text_value_cell(portfolio, "Price Feed", f"{column}{row_number}")
            or portfolio.cell("Price Feed", f"{column}{row_number}").formula is not None
            for column in identity_columns
        ):
            continue
        name = legacy_import._value(row, "B")
        market_symbol = legacy_import._value(row, "D")
        currency = legacy_import._value(row, "H")
        if name is None or market_symbol is None or currency is None:
            continue
        if not re.fullmatch(r"[A-Z]{3}", currency):
            continue
        source_match = _normalize_listing_symbol(source_listing)
        allowed_source_ids = {aux_key, _normalize_listing_symbol(market_symbol)}
        if source_match not in allowed_source_ids:
            continue
        if aux_key == "SPYY":
            if holding_kind != "etf" or source_ticker != "SPYY":
                continue
            market_match = re.fullmatch(r"([^:]+):(.+)", market_symbol.strip())
            if market_match is None:
                continue
            matches.append(
                legacy_import.ListingRow(
                    listing_key="SPYY",
                    canonical_ticker="SPYY",
                    security_key="ETF:SPYY",
                    underlying_security_key=None,
                    name=name.strip(),
                    ticker=market_match.group(2).strip(),
                    venue=market_match.group(1).strip(),
                    currency=currency,
                    security_type="ETF",
                    share_class=None,
                    source=source,
                )
            )
        else:
            if holding_kind != "stock" or source_ticker != "TSM":
                continue
            underlyings = market_by_company.get("TSM", [])
            if len(underlyings) != 1:
                continue
            underlying.append(underlyings[0].listing_row)
            market_match = re.fullmatch(r"([^:]+):(.+)", market_symbol.strip())
            if market_match is None:
                continue
            matches.append(
                legacy_import.ListingRow(
                    listing_key="TSM-ADR",
                    canonical_ticker="TSM",
                    security_key="TSM-ADR",
                    underlying_security_key="TSM",
                    name=name.strip(),
                    ticker=market_match.group(2).strip(),
                    venue=market_match.group(1).strip(),
                    currency=currency,
                    security_type="ADR",
                    share_class=None,
                    source=source,
                )
            )
    if len(matches) == 1:
        return matches[0], underlying, None
    return None, [], "AUX listing mapping is missing or ambiguous."


def _market_listing_for_holding(
    *,
    canonical_ticker: str,
    source_listing: str,
    holding_kind: str,
    market_by_company: dict[str, list[_MarketListing]],
) -> legacy_import.ListingRow | None:
    candidates = market_by_company.get(canonical_ticker, [])
    normalized_source = _normalize_listing_symbol(source_listing)
    matches = [
        item.listing_row
        for item in candidates
        if normalized_source
        in {
            _normalize_listing_symbol(item.market_symbol),
            _normalize_listing_symbol(item.listing_ticker),
        }
        and (holding_kind != "etf" or item.listing_row.security_type == "ETF")
    ]
    return matches[0] if len(matches) == 1 else None


def build_minimal_import_plan(
    store: SnapshotStore,
    sheets_run_id: str,
    sheets_sha256: str,
    market_run_id: str,
) -> MinimalPlan:
    """Replay one frozen Sheets source and one already accepted Market Data snapshot."""
    source = _load_source_snapshot(store, sheets_run_id, sheets_sha256)
    market_snapshot = resolve_approved_snapshot(
        store,
        market_run_id,
        expected_profile=MARKET_DATA_PROFILE.key,
        expected_contract_version=MARKET_DATA_PROFILE.contract_version,
        expected_filename=MARKET_DATA_PROFILE.expected_filename,
    )
    market_book = legacy_import.Workbook.read(
        market_snapshot.path,
        lambda name: name == "Listings",
        source_name=f"Market Data approved snapshot {market_run_id}",
    )
    portfolio_book = _captured_workbook(source)
    _validate_headers(portfolio_book)
    observed_at = datetime.fromisoformat(str(source.manifest["captured_at"]).replace("Z", "+00:00"))
    if observed_at.tzinfo is None or observed_at.utcoffset() is None or observed_at > now():
        raise SheetsPortfolioError(
            "SNAPSHOT_TIME_INVALID", "The frozen Sheets capture time is invalid."
        )
    source_digest = _sha256(
        f"{IMPORT_VERSION}:{source.sha256}:{market_snapshot.sha256}".encode("ascii")
    )
    plan = legacy_import.ImportPlan(
        portfolio_book,
        market_book,
        observed_at.astimezone(UTC),
        source_digest,
    )

    holding_rows: list[tuple[int, str, str | None, str | None]] = []
    critical_tickers: set[str] = set()
    held_tickers: set[str] = set()
    universe_rows = portfolio_book.rows("Universe Registry", 5)
    for row_number, row in portfolio_book.rows("Current Holdings", 5):
        kind = (legacy_import._value(row, "A") or "").strip().casefold()
        ticker_value = legacy_import._value(row, "B")
        source_listing = legacy_import._value(row, "D")
        if kind in {"stock", "etf"}:
            ticker = legacy_import._ticker_key(ticker_value or "")
            if ticker:
                held_tickers.add(ticker)
            if kind == "stock" and ticker:
                critical_tickers.add(ticker)
            holding_rows.append((row_number, kind, ticker_value, source_listing))
    target_rows = portfolio_book.rows("Target Architecture", 5)
    for _row_number, row in target_rows:
        target_ticker_value = legacy_import._value(row, "A")
        if (
            target_ticker_value is not None
            and legacy_import._ticker_key(target_ticker_value) != "RESERVE"
        ):
            critical_tickers.add(legacy_import._ticker_key(target_ticker_value))

    company_by_ticker: dict[str, legacy_import.CompanyRow] = {}
    duplicate_tickers: set[str] = set()
    optional_exclusions: list[dict[str, Any]] = []
    for row_number, row in universe_rows:
        raw_ticker = legacy_import._value(row, "A")
        name = legacy_import._value(row, "B")
        if raw_ticker is None and name is None:
            continue
        source_ref = _workbook_source_ref(
            portfolio_book, "Universe Registry", f"A{row_number}:B{row_number}"
        )
        if raw_ticker is None:
            optional_exclusions.append(
                {"code": "OPTIONAL_COMPANY_TICKER_MISSING", "source": source_ref}
            )
            plan.issue(
                "OPTIONAL_COMPANY_TICKER_MISSING",
                "WARNING",
                source_ref,
                "A non-importable optional universe row has no ticker.",
            )
            continue
        ticker = legacy_import._ticker_key(raw_ticker)
        if ticker in company_by_ticker or ticker in duplicate_tickers:
            duplicate_tickers.add(ticker)
            company_by_ticker.pop(ticker, None)
            severity = "ERROR" if ticker in critical_tickers else "WARNING"
            plan.issue(
                "DUPLICATE_COMPANY_KEY",
                severity,
                source_ref,
                "A normalized company ticker occurs more than once.",
            )
            optional_exclusions.append(
                {"code": "DUPLICATE_COMPANY_KEY", "ticker": ticker, "source": source_ref}
            )
            continue
        if not TICKER_PATTERN.fullmatch(ticker):
            severity = "ERROR" if ticker in critical_tickers else "WARNING"
            plan.issue(
                "COMPANY_TICKER_UNSUPPORTED",
                severity,
                source_ref,
                "A universe ticker is outside the supported identity format.",
            )
            optional_exclusions.append({"code": "COMPANY_TICKER_UNSUPPORTED", "source": source_ref})
            continue
        if name is None:
            severity = "ERROR" if ticker in critical_tickers else "WARNING"
            plan.issue(
                "COMPANY_NAME_MISSING",
                severity,
                source_ref,
                "A company name is missing; the company identity was not fabricated.",
            )
            optional_exclusions.append(
                {"code": "COMPANY_NAME_MISSING", "ticker": ticker, "source": source_ref}
            )
            continue
        if portfolio_book.cell("Universe Registry", f"A{row_number}").kind not in {
            "str",
            "inlineStr",
        } or portfolio_book.cell("Universe Registry", f"B{row_number}").kind not in {
            "str",
            "inlineStr",
        }:
            severity = "ERROR" if ticker in critical_tickers else "WARNING"
            plan.issue(
                "COMPANY_IDENTITY_TYPE_INVALID",
                severity,
                source_ref,
                "Company ticker and name must be text values.",
            )
            optional_exclusions.append(
                {"code": "COMPANY_IDENTITY_TYPE_INVALID", "ticker": ticker, "source": source_ref}
            )
            continue
        company_by_ticker[ticker] = legacy_import.CompanyRow(
            ticker=ticker,
            name=name.strip(),
            research_bucket=None,
            current_weight=None,
            target_weight=None,
            lifecycle=None,
            source=source_ref,
        )
    plan.companies = sorted(company_by_ticker.values(), key=lambda item: item.ticker)
    for ticker in sorted(critical_tickers):
        if ticker not in company_by_ticker and ticker not in {"SPYY"}:
            plan.issue(
                "REQUIRED_COMPANY_IDENTITY_UNRESOLVED",
                "ERROR",
                "Universe Registry!A:B",
                f"A held or targeted company {ticker} has no unique exact "
                "Universe Registry identity.",
            )

    market_by_company, market_exceptions = _read_market_listings(market_book)
    optional_universe_listing_gaps = [
        {
            "ticker": ticker,
            "status": "COMPANY_IDENTITY_RETAINED_LISTING_NOT_IMPORTED",
            "reason": "No READY listing row was present in the accepted Market Data snapshot.",
        }
        for ticker in sorted(company_by_ticker)
        if ticker not in critical_tickers
        and ticker not in held_tickers
        and not market_by_company.get(ticker)
    ]
    selected_listings: dict[str, legacy_import.ListingRow] = {}
    held_listing_map: list[dict[str, Any]] = []
    current_rows = {
        row_number: row for row_number, row in portfolio_book.rows("Current Holdings", 5)
    }
    invalid_holding_rows: set[int] = set()
    for row_number, kind, ticker_raw, listing_raw in holding_rows:
        ticker = legacy_import._ticker_key(ticker_raw or "")
        row = current_rows[row_number]
        source_ref = _workbook_source_ref(
            portfolio_book, "Current Holdings", f"A{row_number}:G{row_number}"
        )
        if any(
            not _text_value_cell(portfolio_book, "Current Holdings", f"{column}{row_number}")
            for column in ("A", "B", "D")
        ):
            plan.issue(
                "HOLDING_IDENTITY_TYPE_INVALID",
                "ERROR",
                source_ref,
                "Holding type, company ticker, and exact listing must be text values.",
            )
            invalid_holding_rows.add(row_number)
            plan.holdings_partial = True
            continue
        if not ticker or listing_raw is None:
            plan.issue(
                "HOLDING_LISTING_IDENTITY_MISSING",
                "ERROR",
                source_ref,
                "A held position lacks its exact source listing identity.",
            )
            invalid_holding_rows.add(row_number)
            plan.holdings_partial = True
            continue
        exact_listing: legacy_import.ListingRow | None
        supporting: list[legacy_import.ListingRow] = []
        aux_key = legacy_import._ticker_key(listing_raw)
        if aux_key in {"SPYY", "TSM-ADR"} or _normalize_listing_symbol(listing_raw) in {
            _normalize_listing_symbol(legacy_import._value(price_row, "D") or "")
            for _price_row_number, price_row in portfolio_book.rows("Price Feed", 5)
            if legacy_import._ticker_key(legacy_import._value(price_row, "C") or "")
            in {"SPYY", "TSM-ADR"}
        }:
            exact_listing, supporting, aux_issue = _resolve_aux_listing(
                portfolio_book,
                source_ticker=ticker,
                source_listing=listing_raw,
                holding_kind=kind,
                market_by_company=market_by_company,
            )
            if aux_issue:
                exact_listing = None
        else:
            exact_listing = _market_listing_for_holding(
                canonical_ticker=ticker,
                source_listing=listing_raw,
                holding_kind=kind,
                market_by_company=market_by_company,
            )
        if exact_listing is None:
            plan.issue(
                "HOLDING_LISTING_UNRESOLVED",
                "ERROR",
                source_ref,
                "The source holding does not map to one exact READY listing in the reviewed "
                "Market Data identity snapshot.",
            )
            invalid_holding_rows.add(row_number)
            plan.holdings_partial = True
            held_listing_map.append({"row": row_number, "status": "UNRESOLVED"})
            continue
        selected_listings[exact_listing.listing_key] = exact_listing
        for underlying in supporting:
            selected_listings[underlying.listing_key] = underlying
        held_listing_map.append(
            {
                "row": row_number,
                "status": "RESOLVED",
                "listing_key": exact_listing.listing_key,
                "mapping_source": "explicit Price Feed AUX"
                if exact_listing.security_type in {"ADR", "ETF"}
                else "exact Market Data symbol/ticker",
                "market_listing_source": exact_listing.source,
            }
        )
        # The existing importer consumes an exact listing key. This in-memory
        # adapter is only applied after a unique source-to-Market-Data match.
        portfolio_book.sheets.setdefault("Current Holdings", {})[f"D{row_number}"] = (
            legacy_import.Cell(exact_listing.listing_key, "str")
        )

    chosen_by_venue: dict[tuple[str, str], str] = {}
    for key, listing in selected_listings.items():
        venue_key = (listing.venue.upper(), listing.ticker.upper())
        prior = chosen_by_venue.get(venue_key)
        if prior is not None and prior != key:
            plan.issue(
                "DUPLICATE_LISTING_IDENTITY",
                "ERROR",
                listing.source,
                "Two source listings resolve to the same venue/ticker identity.",
            )
        chosen_by_venue[venue_key] = key
    plan.listings = sorted(
        selected_listings.values(),
        key=lambda item: (item.underlying_security_key is not None, item.listing_key),
    )

    # Enforce typed numeric values before the established parser turns string
    # representations into Decimal. Source blanks and explicit numeric zero remain distinct.
    for row_number, _kind, _ticker, _listing in holding_rows:
        address = f"E{row_number}"
        cell = portfolio_book.cell("Current Holdings", address)
        if cell.value is not None and cell.kind != "n":
            plan.issue(
                "HOLDING_QUANTITY_NOT_NUMERIC",
                "ERROR",
                _workbook_source_ref(portfolio_book, "Current Holdings", address),
                "Holding quantity/cash must be a numeric Sheets value.",
            )
            portfolio_book.sheets["Current Holdings"][address] = legacy_import.Cell()
            invalid_holding_rows.add(row_number)
            plan.holdings_partial = True
    for row_number, row in portfolio_book.rows("Current Holdings", 5):
        kind = (legacy_import._value(row, "A") or "").strip().casefold()
        if kind == "cash component" and not _text_value_cell(
            portfolio_book, "Current Holdings", f"G{row_number}"
        ):
            plan.issue(
                "CASH_CURRENCY_TYPE_INVALID",
                "ERROR",
                _workbook_source_ref(portfolio_book, "Current Holdings", f"G{row_number}"),
                "A cash currency must be a text ISO currency code.",
            )
            invalid_holding_rows.add(row_number)
            plan.holdings_partial = True
    for row_number in invalid_holding_rows:
        portfolio_book.sheets["Current Holdings"][f"A{row_number}"] = legacy_import.Cell(
            "unsupported", "str"
        )

    # Unsupported or aggregate source rows are recorded explicitly; only the
    # documented aggregate cash summary is an intentional non-imported row.
    for row_number, row in portfolio_book.rows("Current Holdings", 5):
        kind = (legacy_import._value(row, "A") or "").strip().casefold()
        populated = any(
            legacy_import._value(row, column) is not None for column in ("A", "B", "D", "E", "G")
        )
        if not populated:
            continue
        if kind == "cash":
            plan.issue(
                "AGGREGATE_CASH_EXCLUDED",
                "WARNING",
                _workbook_source_ref(
                    portfolio_book, "Current Holdings", f"A{row_number}:G{row_number}"
                ),
                "Aggregate cash summary is excluded; currency-specific cash components are "
                "imported.",
            )
            continue
        if kind not in {"stock", "etf", "cash component", "unsupported"}:
            plan.issue(
                "HOLDING_ROW_KIND_UNSUPPORTED",
                "ERROR",
                _workbook_source_ref(
                    portfolio_book, "Current Holdings", f"A{row_number}:G{row_number}"
                ),
                "A populated holdings row has an unsupported source row type.",
            )
            plan.holdings_partial = True

    # The legacy adapter locates L4 through its fourth row iterator result. The direct
    # source contract starts at row 4, so add empty in-memory rows solely to preserve
    # that adapter's fixed-cell lookup; these are not captured or imported source values.
    for row_number in range(1, 4):
        portfolio_book.sheets.setdefault("Current Holdings", {}).setdefault(
            f"A{row_number}", legacy_import.Cell()
        )
    plan.source_position_count = 0
    legacy_import._load_holdings(plan, company_by_ticker, selected_listings)
    plan.source_position_count = sum(kind in {"stock", "etf"} for _, kind, _, _ in holding_rows)

    # A type error in the portfolio base-currency summary or target control total
    # cannot be parsed as a valid domain currency/decimal.
    base_cell = portfolio_book.cell("Current Holdings", "L4")
    if base_cell.value is not None and base_cell.kind not in {"str", "inlineStr"}:
        plan.issue(
            "PORTFOLIO_CURRENCY_INVALID",
            "ERROR",
            _workbook_source_ref(portfolio_book, "Current Holdings", "L4"),
            "The portfolio base-currency label must be text.",
        )
        portfolio_book.sheets["Current Holdings"]["L4"] = legacy_import.Cell()
    p3 = portfolio_book.cell("Target Architecture", "P3")
    if p3.value is not None and p3.kind != "n":
        plan.issue(
            "TARGET_TOTAL_NOT_NUMERIC",
            "ERROR",
            _workbook_source_ref(portfolio_book, "Target Architecture", "P3"),
            "The target control total must be a numeric Sheets value.",
        )
        portfolio_book.sheets["Target Architecture"]["P3"] = legacy_import.Cell()
    for row_number, row in target_rows:
        target_ticker = legacy_import._value(row, "A")
        weight = legacy_import._value(row, "D")
        if target_ticker is not None and not _text_value_cell(
            portfolio_book, "Target Architecture", f"A{row_number}"
        ):
            plan.issue(
                "TARGET_IDENTITY_TYPE_INVALID",
                "ERROR",
                _workbook_source_ref(portfolio_book, "Target Architecture", f"A{row_number}"),
                "A target company identity must be a text value.",
            )
            portfolio_book.sheets["Target Architecture"][f"A{row_number}"] = legacy_import.Cell()
            plan.target_importable = False
            continue
        if target_ticker is None and weight is not None:
            plan.issue(
                "TARGET_IDENTITY_MISSING",
                "ERROR",
                _workbook_source_ref(
                    portfolio_book, "Target Architecture", f"A{row_number}:D{row_number}"
                ),
                "A populated target weight has no company identity.",
            )
            plan.target_importable = False
        elif (
            target_ticker is not None
            and weight is not None
            and portfolio_book.cell("Target Architecture", f"D{row_number}").kind != "n"
        ):
            plan.issue(
                "TARGET_VALUE_NOT_NUMERIC",
                "ERROR",
                _workbook_source_ref(portfolio_book, "Target Architecture", f"D{row_number}"),
                "Target weights must be numeric Sheets values.",
            )
            portfolio_book.sheets["Target Architecture"][f"D{row_number}"] = legacy_import.Cell()
            plan.target_importable = False
    legacy_import._load_targets(plan, company_by_ticker)

    # A source data row with an unresolved identity may not fall through to the
    # legacy importer’s same-ticker listing fallback.
    if invalid_holding_rows:
        plan.holdings_partial = True
    blocking = [issue for issue in plan.issues if issue.severity == "ERROR"]
    projection = {
        "source_company_row_count": sum(
            _cell_value(portfolio_book, "Universe Registry", f"A{row}") is not None
            or _cell_value(portfolio_book, "Universe Registry", f"B{row}") is not None
            for row in range(
                5,
                next(
                    item["row_count"]
                    for item in source.bundle["structure"]["sheets"]
                    if item["title"] == "Universe Registry"
                )
                + 1,
            )
        ),
        "valid_company_identities": len(plan.companies),
        "source_holding_rows": len(holding_rows),
        "positions": len(plan.positions),
        "cash_rows": len(plan.cash),
        "target_rows": len(target_rows),
        "company_targets": len(plan.targets),
        "selected_listing_mappings": len(plan.listings),
        "held_listing_mappings": held_listing_map,
        "optional_universe_exclusions": optional_exclusions,
        "optional_universe_listing_gaps": optional_universe_listing_gaps,
        "market_listing_exceptions": market_exceptions,
        "blocked": bool(blocking),
        "blocking_issue_count": len(blocking),
        "lifecycle_imported": 0,
        "score_assessments_imported": 0,
        "ranking_entries_imported": 0,
        "source_contract": SOURCE_CONTRACT_VERSION,
    }
    input_sha256 = _sha256(
        _canonical_json(
            {
                "import_version": IMPORT_VERSION,
                "sheets_snapshot_sha256": source.sha256,
                "market_run_id": market_snapshot.run_id,
                "market_snapshot_sha256": market_snapshot.sha256,
                "projection_sha256": _sha256(_canonical_json(projection)),
                "plan_source_digest": plan.source_digest,
            }
        )
    )
    return MinimalPlan(
        plan,
        source,
        market_snapshot.run_id,
        market_snapshot.sha256,
        market_snapshot.schema_fingerprint,
        input_sha256,
        projection,
    )


def _target_scope(settings: Settings, target_environment: str) -> dict[str, str | None]:
    if settings.database_url is None:
        raise SheetsPortfolioError(
            "DATABASE_URL_REQUIRED", "DATABASE_URL is required for target-scoped preview or apply."
        )
    try:
        url = make_url(settings.database_url.get_secret_value())
    except Exception:
        raise SheetsPortfolioError(
            "DATABASE_URL_INVALID", "The configured database target is invalid."
        ) from None
    if not url.host or not url.database:
        raise SheetsPortfolioError(
            "DATABASE_TARGET_INCOMPLETE",
            "The configured database target has no host or database name.",
        )
    return {
        "target_environment": target_environment,
        "database_name": url.database,
        "database_host_sha256": _sha256(url.host.casefold().encode("utf-8")),
        "neon_project_id": settings.neon_project_id,
        "neon_branch_id": settings.neon_branch_id,
        "neon_endpoint_id": settings.neon_endpoint_id,
    }


def _bound_input_sha256(
    minimal: MinimalPlan,
    settings: Settings,
    target_environment: str,
) -> tuple[str, dict[str, str | None]]:
    scope = _target_scope(settings, target_environment)
    value = _sha256(
        _canonical_json(
            {
                "import_version": IMPORT_VERSION,
                "source_input_sha256": minimal.input_sha256,
                "target_scope": scope,
            }
        )
    )
    return value, scope


def _listing_id_for_key(plan: legacy_import.ImportPlan, listing_key: str) -> UUID:
    listing = next((item for item in plan.listings if item.listing_key == listing_key), None)
    if listing is None:
        raise SheetsPortfolioError(
            "PLAN_LISTING_MISSING", "The holdings projection references an unplanned listing."
        )
    return legacy_import._stable_id("listing", f"{listing.venue}:{listing.ticker}")


def _database_diff(
    session: Session, plan: legacy_import.ImportPlan, input_sha256: str
) -> dict[str, Any]:
    company_changes: list[dict[str, str]] = []
    for company_row in plan.companies:
        identifier = legacy_import._stable_id("company", company_row.ticker)
        existing_company = session.get(Company, identifier)
        status = (
            "CREATE"
            if existing_company is None
            else "MATCH"
            if not existing_company.is_demo
            and existing_company.name == company_row.name
            and existing_company.reporting_currency is None
            else "CONFLICT"
        )
        company_changes.append({"key": company_row.ticker, "status": status})

    security_keys = {item.security_key for item in plan.listings}
    security_rows: dict[str, legacy_import.ListingRow] = {}
    for listing in plan.listings:
        security_rows.setdefault(listing.security_key, listing)
    security_ids = {key: legacy_import._stable_id("security", key) for key in security_keys}
    security_changes: list[dict[str, str]] = []
    for key, security_row in sorted(security_rows.items()):
        existing_security = session.get(Security, security_ids[key])
        company_id = (
            None
            if security_row.security_type == "ETF"
            else legacy_import._stable_id("company", security_row.canonical_ticker)
        )
        underlying_id = (
            security_ids.get(security_row.underlying_security_key)
            if security_row.underlying_security_key
            else None
        )
        expected_security = (
            company_id,
            security_row.name,
            security_row.security_type,
            security_row.share_class,
            underlying_id,
        )
        actual_security = (
            None
            if existing_security is None
            else (
                existing_security.company_id,
                existing_security.name,
                existing_security.security_type,
                existing_security.share_class,
                existing_security.underlying_security_id,
            )
        )
        status = (
            "CREATE"
            if existing_security is None
            else "MATCH"
            if not existing_security.is_demo and actual_security == expected_security
            else "CONFLICT"
        )
        security_changes.append({"key": key, "status": status})

    listing_changes: list[dict[str, str]] = []
    expected_listing_ids: dict[str, UUID] = {}
    for row in plan.listings:
        identifier = legacy_import._stable_id("listing", f"{row.venue}:{row.ticker}")
        expected_listing_ids[row.listing_key] = identifier
        existing_listing = session.get(Listing, identifier)
        security_id = security_ids[row.security_key]
        expected_listing = (security_id, row.venue, row.ticker, row.currency)
        actual_listing = (
            None
            if existing_listing is None
            else (
                existing_listing.security_id,
                existing_listing.venue,
                existing_listing.ticker,
                existing_listing.currency,
            )
        )
        collision = (
            session.execute(
                select(Listing.id).where(Listing.venue == row.venue, Listing.ticker == row.ticker)
            ).scalar_one_or_none()
            if existing_listing is None
            else None
        )
        status = (
            "CREATE"
            if existing_listing is None and collision is None
            else "MATCH"
            if existing_listing is not None
            and not existing_listing.is_demo
            and actual_listing == expected_listing
            else "CONFLICT"
        )
        listing_changes.append({"key": row.listing_key, "status": status})

    portfolio_id = legacy_import._stable_id("portfolio", "legacy-default")
    portfolio = session.get(Portfolio, portfolio_id)
    expected_portfolio = ("Imported Legacy Portfolio", plan.base_currency)
    portfolio_status = (
        "CREATE"
        if portfolio is None
        else "MATCH"
        if not portfolio.is_demo and (portfolio.name, portfolio.base_currency) == expected_portfolio
        else "CONFLICT"
    )
    existing_portfolio_count = int(session.scalar(select(func.count()).select_from(Portfolio)) or 0)
    company_count = int(session.scalar(select(func.count()).select_from(Company)) or 0)
    security_count = int(session.scalar(select(func.count()).select_from(Security)) or 0)
    listing_count = int(session.scalar(select(func.count()).select_from(Listing)) or 0)
    receipt = session.scalar(
        select(CanonicalBootstrapRun).where(CanonicalBootstrapRun.input_digest == input_sha256)
    )

    latest_snapshot = (
        legacy_import._current_snapshot(session, portfolio_id) if portfolio is not None else None
    )
    snapshot_status = "CREATE"
    if latest_snapshot is not None:
        stored_positions = {
            item.listing_id: item.quantity
            for item in session.scalars(
                select(HoldingPosition).where(HoldingPosition.snapshot_id == latest_snapshot.id)
            )
        }
        wanted_positions = {
            expected_listing_ids[item.listing_key]: item.quantity for item in plan.positions
        }
        stored_cash = {
            item.currency: item.balance
            for item in session.scalars(
                select(CashPosition).where(CashPosition.snapshot_id == latest_snapshot.id)
            )
        }
        wanted_cash = {item.currency: item.balance for item in plan.cash}
        completeness = "PARTIAL" if plan.holdings_partial else "COMPLETE"
        snapshot_status = (
            "MATCH"
            if stored_positions == wanted_positions
            and stored_cash == wanted_cash
            and latest_snapshot.completeness == completeness
            else "CHANGE"
        )

    target_status = "CREATE"
    if portfolio is not None:
        latest_target = session.scalar(
            select(TargetRevision)
            .where(TargetRevision.portfolio_id == portfolio_id, TargetRevision.status == "ACCEPTED")
            .order_by(TargetRevision.effective_at.desc(), TargetRevision.accepted_at.desc())
            .limit(1)
        )
        if latest_target is not None:
            stored_targets = {
                item.company_id: item.weight
                for item in session.scalars(
                    select(TargetAllocation).where(TargetAllocation.revision_id == latest_target.id)
                )
            }
            wanted_targets = {
                legacy_import._stable_id("company", ticker): weight
                for ticker, weight in plan.targets.items()
            }
            target_status = "MATCH" if stored_targets == wanted_targets else "CHANGE"

    canonical_tables = (
        Security,
        Listing,
        HoldingSnapshot,
        HoldingPosition,
        CashPosition,
        TargetRevision,
        TargetAllocation,
        LifecycleEvent,
        CurrentLifecycle,
        ScoreAssessment,
        RankingRun,
        RankingEntry,
        CanonicalBootstrapRun,
        LegacyImportBatch,
    )
    related_canonical_rows = any(
        int(session.scalar(select(func.count()).select_from(model)) or 0) > 0
        for model in canonical_tables
    )
    counts_match = (
        company_count == len(plan.companies)
        and security_count == len(security_rows)
        and listing_count == len(plan.listings)
        and existing_portfolio_count == (1 if portfolio is not None else 0)
    )
    projection_matches = (
        counts_match
        and all(
            item["status"] == "MATCH"
            for section in (company_changes, security_changes, listing_changes)
            for item in section
        )
        and all(
            status == "MATCH"
            for status in (
                portfolio_status,
                snapshot_status,
                target_status,
            )
        )
    )
    non_empty = (
        company_count > 0 or existing_portfolio_count > 0 or related_canonical_rows
    ) and receipt is None
    if receipt is not None:
        receipt_state = (
            "ALREADY_APPLIED" if projection_matches else "RECEIPT_RECONCILIATION_REQUIRED"
        )
    elif non_empty:
        receipt_state = "BLOCKED_NONEMPTY"
    else:
        receipt_state = "EMPTY"
    return {
        "status": receipt_state,
        "current_counts": {
            "companies": company_count,
            "securities": security_count,
            "listings": listing_count,
            "portfolios": existing_portfolio_count,
        },
        "proposed_changes": {
            "companies": company_changes,
            "securities": security_changes,
            "listings": listing_changes,
            "portfolio": {"status": portfolio_status},
            "holdings_snapshot": {
                "status": snapshot_status,
                "positions": len(plan.positions),
                "cash_rows": len(plan.cash),
            },
            "strategic_targets": {"status": target_status, "company_rows": len(plan.targets)},
        },
        "matching_canonical_receipt": receipt is not None,
        "receipt_projection_matches": projection_matches if receipt is not None else None,
        "planned_records": {
            "companies": len(plan.companies),
            "securities": len(security_rows),
            "listings": len(plan.listings),
            "holdings_positions": len(plan.positions),
            "cash_positions": len(plan.cash),
            "targets": len(plan.targets),
            "lifecycle_events": 0,
            "score_assessments": 0,
            "ranking_entries": 0,
        },
    }


def _minimal_report(
    minimal: MinimalPlan,
    *,
    target_environment: str,
    input_sha256: str,
    target_scope: dict[str, str | None],
) -> dict[str, Any]:
    plan = minimal.plan
    report = plan.report()
    report["bootstrap"] = {
        "import_version": IMPORT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "portfolio_source_run_id": minimal.source.run_id,
        "portfolio_source_sha256": minimal.source.sha256,
        "portfolio_source_semantic_sha256": minimal.source.semantic_sha256,
        "market_source_run_id": minimal.market_run_id,
        "market_source_sha256": minimal.market_sha256,
        "market_schema_sha256": minimal.market_schema_sha256,
        "input_sha256": input_sha256,
        "target_environment": target_environment,
        "target_scope": target_scope,
        "source_consistency": minimal.source.bundle["capture_semantics"],
        "lifecycle_scores_and_rankings": "EXCLUDED_FROM_MINIMAL_SCOPE",
        "provider_ingestion_or_recalculation": "NOT_PERFORMED",
    }
    report["projection"] = minimal.projection
    report["blocking_issues"] = [
        issue.as_dict() for issue in plan.issues if issue.severity == "ERROR"
    ]
    report["warnings"] = [issue.as_dict() for issue in plan.issues if issue.severity == "WARNING"]
    report["ready_to_apply"] = not report["blocking_issues"]
    return report


def _verify_target(
    engine: Engine, settings: Settings, target_environment: str, *, read_only: bool
) -> None:
    try:
        verifier = verify_database_read_only_preflight if read_only else verify_database_preflight
        verifier(
            engine,
            configured_target_environment=settings.database_target_environment,
            requested_target_environment=target_environment,
        )
    except (BootstrapPreflightError, DatabaseWriteTargetError):
        raise
    except Exception:
        raise SheetsPortfolioError(
            "DATABASE_PREFLIGHT_FAILED",
            "Database target and migration preflight did not complete; no import was attempted.",
        ) from None


def _write_report(store: SnapshotStore, report: dict[str, Any]) -> str:
    root = store.root / "sheets-portfolio-bootstrap-runs"
    if root.is_symlink():
        raise SheetsPortfolioError(
            "REPORT_PATH_INVALID", "The private report directory cannot be symlinked."
        )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        root.chmod(0o700)
    report_id = uuid.uuid4().hex
    path = root / f"{report_id}.json"
    payload = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise SheetsPortfolioError(
            "REPORT_WRITE_FAILED", "The private bootstrap report could not be written."
        ) from None
    return str(path.relative_to(store.root))


def preview_database(
    session: Session,
    minimal: MinimalPlan,
    *,
    target_environment: str,
    input_sha256: str,
    target_scope: dict[str, str | None],
) -> dict[str, Any]:
    report = _minimal_report(
        minimal,
        target_environment=target_environment,
        input_sha256=input_sha256,
        target_scope=target_scope,
    )
    report["database_diff"] = _database_diff(session, minimal.plan, input_sha256)
    if report["blocking_issues"]:
        report["status"] = "BLOCKED_SOURCE_VALIDATION"
    elif report["database_diff"]["status"] == "BLOCKED_NONEMPTY":
        report["status"] = "BLOCKED_NONEMPTY_TARGET"
    elif report["database_diff"]["status"] == "RECEIPT_RECONCILIATION_REQUIRED":
        report["status"] = "BLOCKED_RECEIPT_RECONCILIATION"
    elif report["database_diff"]["status"] == "ALREADY_APPLIED":
        report["status"] = "ALREADY_APPLIED"
    else:
        report["status"] = "READY_WITH_EXCLUSIONS" if report["warnings"] else "READY"
    report["preview_semantics"] = (
        "Read-only database diff; no DML, DDL, sequence changes, receipts, or provider calls."
    )
    return report


def _apply_in_transaction(
    session: Session,
    minimal: MinimalPlan,
    *,
    target_environment: str,
    input_sha256: str,
    target_scope: dict[str, str | None],
) -> dict[str, Any]:
    plan = minimal.plan
    if any(issue.severity == "ERROR" for issue in plan.issues):
        raise SheetsPortfolioError(
            "SOURCE_VALIDATION_BLOCKED",
            "The source projection has blocking identity or value issues.",
        )
    database_state = _database_diff(session, plan, input_sha256)
    if database_state["status"] == "BLOCKED_NONEMPTY":
        raise SheetsPortfolioError(
            "NONEMPTY_TARGET",
            "The canonical target contains data that is not owned by this exact bootstrap input.",
        )
    if database_state["status"] == "RECEIPT_RECONCILIATION_REQUIRED":
        raise SheetsPortfolioError(
            "RECEIPT_RECONCILIATION_REQUIRED",
            "The prior bootstrap receipt exists but canonical state no longer matches "
            "its projection.",
        )
    receipt_id = legacy_import._stable_id("canonical-bootstrap-run", input_sha256)
    prior_receipt = session.scalar(
        select(CanonicalBootstrapRun).where(CanonicalBootstrapRun.input_digest == input_sha256)
    )
    if prior_receipt is not None:
        return {
            "status": "ALREADY_APPLIED",
            "canonical_receipt": str(prior_receipt.id),
            "input_sha256": input_sha256,
            "reconciliation": (
                "No rows were written; the exact input and target receipt already exists."
            ),
        }
    prior_legacy = session.scalar(
        select(LegacyImportBatch).where(LegacyImportBatch.source_digest == plan.source_digest)
    )
    if prior_legacy is not None:
        raise SheetsPortfolioError(
            "LEGACY_RECEIPT_WITHOUT_CANONICAL_RECEIPT",
            "A matching legacy import receipt exists without this target-bound canonical "
            "receipt; review is required.",
        )
    try:
        legacy_report = legacy_import.apply_plan(session, plan)
    except legacy_import.AlreadyImported:
        raise SheetsPortfolioError(
            "SOURCE_ALREADY_IMPORTED",
            "The source projection already has a legacy receipt without a matching canonical "
            "receipt.",
        ) from None
    status = (
        "APPLIED_WITH_GAPS"
        if any(issue.severity == "WARNING" for issue in plan.issues)
        else "APPLIED"
    )
    report = {
        "status": status,
        "import_version": IMPORT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "portfolio_source_run_id": minimal.source.run_id,
        "portfolio_source_sha256": minimal.source.sha256,
        "market_source_run_id": minimal.market_run_id,
        "market_source_sha256": minimal.market_sha256,
        "input_sha256": input_sha256,
        "target_environment": target_environment,
        "target_scope": target_scope,
        "legacy_import": legacy_report,
        "excluded_lifecycle_scores_rankings": True,
        "warnings": [issue.as_dict() for issue in plan.issues if issue.severity == "WARNING"],
        "recorded_at": now().isoformat(),
    }
    session.add(
        CanonicalBootstrapRun(
            id=receipt_id,
            input_digest=input_sha256,
            source_digest=plan.source_digest,
            portfolio_snapshot_run_id=minimal.source.run_id,
            market_snapshot_run_id=minimal.market_run_id,
            provider_identifiers_sha256=None,
            import_version=IMPORT_VERSION,
            observed_at=plan.observed_at,
            recorded_at=now(),
            status="APPLIED_WITH_GAPS" if status == "APPLIED_WITH_GAPS" else "APPLIED",
            report=report,
        )
    )
    session.flush()
    report["canonical_receipt"] = str(receipt_id)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser(
        "capture", help="Capture a bounded read-only native Sheets source snapshot"
    )
    capture.add_argument("--store", type=Path, required=True)
    capture.add_argument("--confirm-read-only-source-capture", action="store_true", required=True)

    for name in ("preview", "apply"):
        subparser = commands.add_parser(name)
        subparser.add_argument("--store", type=Path, required=True)
        subparser.add_argument("--sheets-run", required=True)
        subparser.add_argument("--sheets-sha256", required=True)
        subparser.add_argument("--market-run", required=True)
        subparser.add_argument(
            "--target-environment",
            choices=("development", "rehearsal", "production"),
            required=True,
        )
        if name == "apply":
            subparser.add_argument("--expected-input-sha256", required=True)
            subparser.add_argument("--approve-input-sha256", required=True)
            subparser.add_argument(
                "--confirm-minimal-sheets-contract-reviewed", action="store_true", required=True
            )
    return parser


def _cli_failure(error: Exception, store: SnapshotStore | None = None) -> int:
    message = (
        str(error)
        if isinstance(
            error,
            (
                SheetsPortfolioError,
                BootstrapPreflightError,
                DatabaseWriteTargetError,
                WorkbookSourceError,
            ),
        )
        else "The operation failed validation; no source or database values are printed."
    )
    report_path = "unavailable"
    if store is not None:
        with suppress(Exception):
            report_path = _write_report(
                store,
                {
                    "status": "FAILED",
                    "error_code": getattr(error, "code", type(error).__name__),
                    "message": message,
                },
            )
    print(
        json.dumps({"status": "FAILED", "message": message, "report": report_path}, sort_keys=True),
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store: SnapshotStore | None = None
    engine: Engine | None = None
    try:
        store = SnapshotStore(args.store)
        settings = Settings()
        if args.command == "capture":
            captured = SheetsPortfolioReader(settings).capture(store)
            print(
                json.dumps(
                    {
                        "status": "CAPTURED_REVIEW_REQUIRED",
                        "run_id": captured.run_id,
                        "sha256": captured.sha256,
                        "ranges": captured.manifest["ranges"],
                        "captured_cells": captured.manifest["captured_cells"],
                        "consistency": captured.bundle["capture_semantics"],
                    },
                    sort_keys=True,
                )
            )
            return 0

        minimal = build_minimal_import_plan(
            store, args.sheets_run, args.sheets_sha256, args.market_run
        )
        input_sha256, target_scope = _bound_input_sha256(minimal, settings, args.target_environment)
        if args.command == "apply" and (
            args.expected_input_sha256 != input_sha256 or args.approve_input_sha256 != input_sha256
        ):
            raise SheetsPortfolioError(
                "EXPLICIT_APPROVAL_HASH_MISMATCH",
                "Both apply approval hashes must equal the newly computed exact "
                "source-and-target input hash.",
            )
        if settings.database_url is None:
            raise SheetsPortfolioError(
                "DATABASE_URL_REQUIRED",
                "DATABASE_URL is required for database target verification.",
            )
        engine = create_database_engine(
            settings,
            write_operation="canonical_portfolio_bootstrap",
            write_operation_kind="bootstrap",
            read_only=args.command == "preview",
        )
        if engine is None:
            raise SheetsPortfolioError(
                "DATABASE_URL_REQUIRED",
                "DATABASE_URL is required for database target verification.",
            )
        _verify_target(
            engine, settings, args.target_environment, read_only=args.command == "preview"
        )
        with Session(engine) as session:
            if args.command == "preview":
                report = preview_database(
                    session,
                    minimal,
                    target_environment=args.target_environment,
                    input_sha256=input_sha256,
                    target_scope=target_scope,
                )
            else:
                with session.begin():
                    report = _apply_in_transaction(
                        session,
                        minimal,
                        target_environment=args.target_environment,
                        input_sha256=input_sha256,
                        target_scope=target_scope,
                    )
        relative_report = _write_report(store, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "input_sha256": input_sha256,
                    "report": relative_report,
                },
                sort_keys=True,
            )
        )
        return (
            0
            if report["status"]
            in {"READY", "READY_WITH_EXCLUSIONS", "APPLIED", "APPLIED_WITH_GAPS", "ALREADY_APPLIED"}
            else 2
        )
    except (
        SheetsPortfolioError,
        BootstrapPreflightError,
        DatabaseWriteTargetError,
        WorkbookSourceError,
        ValueComparisonError,
        ValueError,
        OSError,
    ) as error:
        return _cli_failure(error, store)
    except Exception as error:
        return _cli_failure(error, store)
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
