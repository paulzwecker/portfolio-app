"""Explicit, read-only acquisition of private workbook snapshots.

This module never imports workbook contents into PostgreSQL. It retrieves a caller-selected
Google Drive file or operator-supplied XLSX, validates the package and source contract, stores
the unchanged bytes in a private content-addressed cache, and writes an immutable run manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import stat
import sys
import tempfile
import time
import uuid
import zlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DRIVE_FILES_API = "https://www.googleapis.com/drive/v3/files"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_WORKBOOK_BYTES = 32 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = {"m": SHEET_NS, "r": REL_NS, "p": PKG_REL_NS}


@dataclass(frozen=True)
class WorkbookProfile:
    key: str
    contract_version: str
    expected_filename: str
    required_sheets: tuple[str, ...]
    required_model_prefixes: tuple[str, ...]
    header_rows: tuple[tuple[str, int], ...]
    contract_cells: tuple[tuple[str, tuple[str, ...]], ...] = ()


PORTFOLIO_PROFILE = WorkbookProfile(
    key="portfolio",
    contract_version="portfolio-workbook-contract-v1",
    expected_filename="Portfolio_Watchlist.xlsx",
    required_sheets=(
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
    ),
    required_model_prefixes=("P-", "W-"),
    header_rows=(
        ("Universe Registry", 4),
        ("Current Holdings", 4),
        ("Target Architecture", 4),
        ("10Y Durability", 4),
        ("Compounder Quality", 4),
        ("Price Feed", 4),
        ("Model Revision History", 3),
        ("Estimate History", 1),
        ("Candidate Ranking", 1),
    ),
    contract_cells=(("Model Contract", tuple(f"A{row}" for row in range(5, 23))),),
)

MARKET_DATA_PROFILE = WorkbookProfile(
    key="market_data",
    contract_version="market-data-workbook-contract-v1",
    expected_filename="Market Data.xlsx",
    required_sheets=(
        "Listings",
        "Daily Prices",
        "Corporate Actions",
        "Price Regime",
        "Data QA",
    ),
    required_model_prefixes=(),
    header_rows=(
        ("Listings", 4),
        ("Daily Prices", 3),
        ("Corporate Actions", 3),
        ("Price Regime", 3),
        ("Data QA", 3),
    ),
)

PROFILES = {profile.key: profile for profile in (PORTFOLIO_PROFILE, MARKET_DATA_PROFILE)}
DRIVE_ID_ENVIRONMENT = {
    "portfolio": "GOOGLE_DRIVE_PORTFOLIO_WORKBOOK_FILE_ID",
    "market_data": "GOOGLE_DRIVE_MARKET_DATA_WORKBOOK_FILE_ID",
}


class WorkbookSourceError(Exception):
    """Safe, user-facing source-acquisition failure without provider response bodies."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics


class HttpResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def json(self) -> Any: ...

    def iter_content(self, chunk_size: int = ...) -> Iterator[bytes]: ...


@dataclass(frozen=True)
class AcquiredBytes:
    data: bytes
    method: str
    source_revision: str | None
    source_modified_at: str | None
    source_checksum: str | None
    source_mime_type: str | None


@dataclass(frozen=True)
class WorkbookInventory:
    sheet_names: tuple[str, ...]
    hidden_sheet_names: tuple[str, ...]
    defined_names: tuple[tuple[str, str, str], ...]
    sheet_metrics: tuple[dict[str, Any], ...]
    date_system: str
    header_fingerprint: str
    schema_fingerprint: str
    unclassified_sheets: tuple[str, ...]


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Acquisition timestamps must include a timezone")
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _size_limit_message(max_bytes: int = MAX_WORKBOOK_BYTES) -> str:
    size_mib = max_bytes // (1024 * 1024)
    return f"The workbook exceeds the {size_mib} MiB acquisition limit."


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _assert_private_location(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    repository = REPOSITORY_ROOT.resolve()
    if _is_within(resolved, repository) or _is_within(repository, resolved):
        raise WorkbookSourceError(
            "REPOSITORY_PATH_FORBIDDEN",
            f"Keep the {label} outside the repository checkout.",
        )
    return resolved


def _xml_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//m:t", XML_NS))


def inspect_workbook(data: bytes, profile: WorkbookProfile) -> WorkbookInventory:
    """Validate an XLSX package and compute a data-free structural schema fingerprint."""
    if not data:
        raise WorkbookSourceError("EMPTY_WORKBOOK", "The acquired workbook is empty.")
    if len(data) > MAX_WORKBOOK_BYTES:
        raise WorkbookSourceError(
            "WORKBOOK_TOO_LARGE",
            _size_limit_message(),
        )

    try:
        archive = ZipFile(io.BytesIO(data))
    except (BadZipFile, OSError, ValueError) as error:
        raise WorkbookSourceError(
            "INVALID_XLSX", "The acquired file is not a valid XLSX package."
        ) from error

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise WorkbookSourceError(
                "XLSX_PACKAGE_TOO_COMPLEX", "The XLSX package has too many parts."
            )
        filenames = [item.filename for item in infos]
        if len(filenames) != len(set(filenames)):
            raise WorkbookSourceError(
                "DUPLICATE_XLSX_PART", "The XLSX package contains duplicate parts."
            )
        if any(item.flag_bits & 0x1 for item in infos):
            raise WorkbookSourceError(
                "ENCRYPTED_XLSX", "Encrypted workbook packages are unsupported."
            )
        if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
            raise WorkbookSourceError(
                "XLSX_PACKAGE_TOO_LARGE", "The uncompressed XLSX package exceeds its limit."
            )
        if "xl/vbaProject.bin" in filenames:
            raise WorkbookSourceError(
                "MACRO_ENABLED_WORKBOOK", "Macro-enabled workbooks are unsupported."
            )
        if "xl/workbook.xml" not in filenames or "xl/_rels/workbook.xml.rels" not in filenames:
            raise WorkbookSourceError(
                "INVALID_XLSX", "The XLSX package is missing workbook metadata."
            )
        try:
            corrupt_part = archive.testzip()
        except (BadZipFile, EOFError, OSError, RuntimeError, zlib.error) as error:
            raise WorkbookSourceError(
                "INVALID_XLSX_ARCHIVE", "The XLSX archive is incomplete or unreadable."
            ) from error
        if corrupt_part is not None:
            raise WorkbookSourceError("CORRUPT_XLSX_PART", "The XLSX package failed its CRC check.")

        try:
            workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (ET.ParseError, BadZipFile, EOFError, OSError, zlib.error) as error:
            raise WorkbookSourceError(
                "INVALID_XLSX_XML", "The workbook metadata is malformed."
            ) from error

        relationships = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships_xml.findall("p:Relationship", XML_NS)
            if "Id" in item.attrib and "Target" in item.attrib
        }
        sheet_nodes = workbook_xml.findall("m:sheets/m:sheet", XML_NS)
        if not sheet_nodes:
            raise WorkbookSourceError("NO_WORKSHEETS", "The XLSX package contains no worksheets.")

        sheet_names: list[str] = []
        hidden_sheet_names: list[str] = []
        sheet_parts: list[tuple[str, str]] = []
        for node in sheet_nodes:
            name = node.attrib.get("name", "")
            relation_id = node.attrib.get(f"{{{REL_NS}}}id")
            target = relationships.get(relation_id or "")
            if not name or target is None:
                raise WorkbookSourceError(
                    "INVALID_SHEET_RELATIONSHIP", "A worksheet relationship is invalid."
                )
            target_path = (
                posixpath.normpath(target.lstrip("/"))
                if target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", target))
            )
            if target_path.startswith("../") or target_path not in filenames:
                raise WorkbookSourceError(
                    "INVALID_SHEET_RELATIONSHIP", "A worksheet part is missing or unsafe."
                )
            if name in sheet_names:
                raise WorkbookSourceError(
                    "DUPLICATE_SHEET_NAME", "The workbook has duplicate worksheet names."
                )
            sheet_names.append(name)
            sheet_parts.append((name, target_path))
            if node.attrib.get("state", "visible") != "visible":
                hidden_sheet_names.append(name)

        missing = sorted(set(profile.required_sheets) - set(sheet_names))
        prefix_counts = {
            prefix: sum(name.startswith(prefix) for name in sheet_names)
            for prefix in profile.required_model_prefixes
        }
        missing_prefixes = sorted(prefix for prefix, count in prefix_counts.items() if count == 0)
        if missing or missing_prefixes:
            diagnostics = tuple(
                [
                    *(f"missing required sheet: {name}" for name in missing),
                    *(
                        f"missing required model-tab prefix: {prefix}"
                        for prefix in missing_prefixes
                    ),
                ]
            )
            raise WorkbookSourceError(
                "WORKBOOK_CONTRACT_INCOMPLETE",
                "Required workbook tabs are missing.",
                diagnostics=diagnostics,
            )

        defined_names: list[tuple[str, str, str]] = []
        defined_names_node = workbook_xml.find("m:definedNames", XML_NS)
        if defined_names_node is not None:
            for node in defined_names_node.findall("m:definedName", XML_NS):
                name = node.attrib.get("name", "")
                if name:
                    scope = node.attrib.get("localSheetId", "global")
                    definition_hash = _canonical_digest(node.text or "")
                    defined_names.append((name, scope, definition_hash))

        header_rows = dict(profile.header_rows)
        contract_cells = {sheet: set(cells) for sheet, cells in profile.contract_cells}
        headers_by_sheet: dict[str, list[tuple[str, str, str, bool]]] = {}
        sheet_metrics: list[dict[str, Any]] = []
        shared_string_indexes: set[int] = set()
        header_shared_string_indexes: set[int] = set()
        pending_headers: dict[str, list[tuple[str, str, str | None, bool]]] = {}

        for sheet_name, part_path in sheet_parts:
            try:
                with archive.open(part_path) as worksheet:
                    dimension: str | None = None
                    formula_count = 0
                    cell_count = 0
                    selected: list[tuple[str, str, str | None, bool]] = []
                    for _event, element in ET.iterparse(worksheet, events=("end",)):
                        if element.tag == f"{{{SHEET_NS}}}dimension":
                            dimension = element.attrib.get("ref")
                        elif element.tag == f"{{{SHEET_NS}}}c":
                            cell_count += 1
                            formula = element.find("m:f", XML_NS)
                            has_formula = formula is not None
                            if has_formula:
                                formula_count += 1
                            address = element.attrib.get("r", "")
                            row_match = re.search(r"([0-9]+)$", address)
                            cell_type = element.attrib.get("t", "n")
                            value_node = element.find("m:v", XML_NS)
                            raw_value = value_node.text if value_node is not None else None
                            if cell_type == "s" and raw_value is not None:
                                try:
                                    shared_index = int(raw_value)
                                    if shared_index < 0:
                                        raise ValueError
                                    shared_string_indexes.add(shared_index)
                                except ValueError as error:
                                    raise WorkbookSourceError(
                                        "INVALID_SHARED_STRING_INDEX",
                                        "The XLSX package has an invalid shared-string index.",
                                    ) from error
                            selected_rows = (
                                {header_rows[sheet_name]} if sheet_name in header_rows else set()
                            )
                            selected_cells = contract_cells.get(sheet_name, set())
                            if row_match is not None and (
                                int(row_match.group(1)) in selected_rows
                                or address in selected_cells
                            ):
                                inline_node = element.find("m:is", XML_NS)
                                if cell_type == "s" and raw_value is not None:
                                    header_shared_string_indexes.add(int(raw_value))
                                if cell_type == "inlineStr" and inline_node is not None:
                                    raw_value = _xml_text(inline_node)
                                    cell_type = "inlineStr"
                                selected.append((address, cell_type, raw_value, has_formula))
                            element.clear()
                        elif element.tag == f"{{{SHEET_NS}}}row":
                            element.clear()
                    pending_headers[sheet_name] = selected
                    sheet_metrics.append(
                        {
                            "name": sheet_name,
                            "state": next(
                                (
                                    item.attrib.get("state", "visible")
                                    for item in sheet_nodes
                                    if item.attrib.get("name") == sheet_name
                                ),
                                "visible",
                            ),
                            "dimension": dimension,
                            "cell_count": cell_count,
                            "formula_cell_count": formula_count,
                        }
                    )
            except (ET.ParseError, BadZipFile, EOFError, OSError, zlib.error) as error:
                raise WorkbookSourceError(
                    "INVALID_WORKSHEET_XML", "A worksheet part is malformed."
                ) from error

        empty_required = sorted(
            name
            for name in profile.required_sheets
            if next(
                (int(metric["cell_count"]) for metric in sheet_metrics if metric["name"] == name),
                0,
            )
            == 0
        )
        empty_required_prefixes = sorted(
            prefix
            for prefix in profile.required_model_prefixes
            if not any(
                metric["name"].startswith(prefix) and metric["cell_count"] > 0
                for metric in sheet_metrics
            )
        )
        if empty_required or empty_required_prefixes:
            diagnostics = tuple(
                [
                    *(f"required sheet is empty: {name}" for name in empty_required),
                    *(
                        f"required model-tab prefix has no populated sheet: {prefix}"
                        for prefix in empty_required_prefixes
                    ),
                ]
            )
            raise WorkbookSourceError(
                "WORKBOOK_CONTRACT_INCOMPLETE",
                "Required workbook tabs are empty.",
                diagnostics=diagnostics,
            )

        shared_strings: dict[int, str] = {}
        shared_string_count = 0
        if "xl/sharedStrings.xml" in filenames:
            try:
                shared_index = 0
                shared_root: ET.Element | None = None
                with archive.open("xl/sharedStrings.xml") as shared_xml:
                    for event, element in ET.iterparse(shared_xml, events=("start", "end")):
                        if event == "start" and shared_root is None:
                            shared_root = element
                        elif event == "end" and element.tag == f"{{{SHEET_NS}}}si":
                            if shared_index in header_shared_string_indexes:
                                shared_strings[shared_index] = _xml_text(element)
                            shared_index += 1
                            element.clear()
                            if shared_root is not None:
                                shared_root.clear()
                shared_string_count = shared_index
            except (ET.ParseError, BadZipFile, EOFError, OSError, zlib.error) as error:
                raise WorkbookSourceError(
                    "INVALID_SHARED_STRINGS", "The XLSX shared-string table is malformed."
                ) from error
        if any(index >= shared_string_count for index in shared_string_indexes):
            raise WorkbookSourceError(
                "INVALID_SHARED_STRING_INDEX",
                "A worksheet references a missing shared-string entry.",
            )

        for sheet_name, cells in pending_headers.items():
            resolved: list[tuple[str, str, str, bool]] = []
            for address, cell_type, raw_value, has_formula in cells:
                value = raw_value or ""
                if cell_type == "s" and raw_value is not None:
                    try:
                        index = int(raw_value)
                        value = shared_strings[index]
                    except (ValueError, KeyError) as error:
                        raise WorkbookSourceError(
                            "INVALID_SHARED_STRING_INDEX",
                            "The XLSX package contains an invalid shared-string index.",
                        ) from error
                resolved.append(
                    (address, cell_type, value if not has_formula else "<formula>", has_formula)
                )
            headers_by_sheet[sheet_name] = resolved

        workbook_properties = workbook_xml.find("m:workbookPr", XML_NS)
        date_system = (
            "1904"
            if workbook_properties is not None
            and workbook_properties.attrib.get("date1904", "0").casefold() in {"1", "true"}
            else "1900"
        )

    ordered_names = tuple(sheet_names)
    ordered_defined_names = tuple(sorted(defined_names))
    header_fingerprint = _canonical_digest(
        {name: sorted(values) for name, values in sorted(headers_by_sheet.items())}
    )
    schema_fingerprint = _canonical_digest(
        {
            "profile": profile.key,
            "contract_version": profile.contract_version,
            "sheet_names": ordered_names,
            "hidden_sheet_names": tuple(hidden_sheet_names),
            "defined_names": ordered_defined_names,
            "header_fingerprint": header_fingerprint,
            "date_system": date_system,
        }
    )
    classified = set(profile.required_sheets)
    unclassified_sheets = tuple(
        name
        for name in ordered_names
        if name not in classified and not name.startswith(("P-", "W-", "C-"))
    )
    return WorkbookInventory(
        sheet_names=ordered_names,
        hidden_sheet_names=tuple(hidden_sheet_names),
        defined_names=ordered_defined_names,
        sheet_metrics=tuple(sheet_metrics),
        date_system=date_system,
        header_fingerprint=header_fingerprint,
        schema_fingerprint=schema_fingerprint,
        unclassified_sheets=unclassified_sheets,
    )


def _safe_metadata(response: HttpResponse) -> dict[str, Any]:
    try:
        value = response.json()
    except (TypeError, ValueError) as error:
        raise WorkbookSourceError(
            "INVALID_DRIVE_RESPONSE", "Google Drive returned invalid metadata."
        ) from error
    if not isinstance(value, dict):
        raise WorkbookSourceError(
            "INVALID_DRIVE_RESPONSE", "Google Drive returned invalid metadata."
        )
    return value


class GoogleDriveWorkbookReader:
    """Fetch one explicitly configured Drive file, never listing or searching Drive."""

    def __init__(
        self,
        session: Any,
        *,
        timeout_seconds: float = 30,
        max_bytes: int = MAX_WORKBOOK_BYTES,
        retries: int = MAX_RETRIES,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if retries < 1 or retries > MAX_RETRIES:
            raise ValueError(f"retries must be between 1 and {MAX_RETRIES}")
        self.session = session
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.retries = retries
        self.sleeper = sleeper

    def _pause(self, attempt: int, response: HttpResponse | None = None) -> None:
        retry_after = None
        if response is not None:
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
                min(5.0, max(0.0, float(retry_after)))
                if retry_after is not None
                else min(2.0, 0.25 * 2 ** (attempt - 1))
            )
        except ValueError:
            delay = min(2.0, 0.25 * 2 ** (attempt - 1))
        self.sleeper(delay)

    def _get_json(self, url: str, params: Mapping[str, str]) -> dict[str, Any]:
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(
                    url, params=params, timeout=(5, self.timeout_seconds), stream=False
                )
            except Exception as error:
                if attempt == self.retries:
                    raise WorkbookSourceError(
                        "DRIVE_NETWORK_ERROR",
                        "Google Drive could not be reached after bounded retries.",
                    ) from error
                self._pause(attempt)
                continue
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == self.retries:
                    raise WorkbookSourceError(
                        "DRIVE_RETRY_LIMIT",
                        "Google Drive remained temporarily unavailable after bounded retries.",
                    )
                self._pause(attempt, response)
                continue
            if response.status_code in {401, 403}:
                raise WorkbookSourceError(
                    "DRIVE_ACCESS_DENIED",
                    "Google Drive denied access to the configured read-only source.",
                )
            if response.status_code == 404:
                raise WorkbookSourceError(
                    "DRIVE_FILE_NOT_FOUND", "The configured Google Drive workbook was not found."
                )
            if response.status_code != 200:
                raise WorkbookSourceError(
                    "DRIVE_HTTP_ERROR", f"Google Drive returned HTTP {response.status_code}."
                )
            return _safe_metadata(response)
        raise WorkbookSourceError("DRIVE_RETRY_LIMIT", "Google Drive metadata retrieval failed.")

    def _get_bytes(self, url: str, params: Mapping[str, str]) -> bytes:
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(
                    url, params=params, timeout=(5, self.timeout_seconds), stream=True
                )
            except Exception as error:
                if attempt == self.retries:
                    raise WorkbookSourceError(
                        "DRIVE_NETWORK_ERROR",
                        "Google Drive could not be reached after bounded retries.",
                    ) from error
                self._pause(attempt)
                continue
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == self.retries:
                    raise WorkbookSourceError(
                        "DRIVE_RETRY_LIMIT",
                        "Google Drive remained temporarily unavailable after bounded retries.",
                    )
                self._pause(attempt, response)
                continue
            if response.status_code in {401, 403}:
                raise WorkbookSourceError(
                    "DRIVE_ACCESS_DENIED",
                    "Google Drive denied access to the configured read-only source.",
                )
            if response.status_code == 404:
                raise WorkbookSourceError(
                    "DRIVE_FILE_NOT_FOUND", "The configured Google Drive workbook was not found."
                )
            if response.status_code != 200:
                raise WorkbookSourceError(
                    "DRIVE_HTTP_ERROR", f"Google Drive returned HTTP {response.status_code}."
                )
            try:
                chunks: list[bytes] = []
                total_bytes = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > self.max_bytes:
                        raise WorkbookSourceError(
                            "WORKBOOK_TOO_LARGE",
                            _size_limit_message(self.max_bytes),
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
            except WorkbookSourceError:
                raise
            except Exception as error:
                if attempt == self.retries:
                    raise WorkbookSourceError(
                        "DRIVE_TRANSFER_INCOMPLETE",
                        "Google Drive transfer failed after bounded retries.",
                    ) from error
                self._pause(attempt, response)
        raise WorkbookSourceError("DRIVE_RETRY_LIMIT", "Google Drive workbook retrieval failed.")

    def acquire(self, file_id: str) -> AcquiredBytes:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", file_id):
            raise WorkbookSourceError(
                "INVALID_DRIVE_FILE_ID", "Configure a Google Drive file ID, not a URL."
            )
        encoded_id = quote(file_id, safe="")
        metadata = self._get_json(
            f"{DRIVE_FILES_API}/{encoded_id}",
            {
                "fields": "id,mimeType,modifiedTime,headRevisionId,md5Checksum,size",
                "supportsAllDrives": "true",
            },
        )
        if metadata.get("id") != file_id:
            raise WorkbookSourceError(
                "DRIVE_IDENTITY_MISMATCH", "Google Drive resolved a different file identity."
            )
        mime_type = metadata.get("mimeType")
        if mime_type not in {GOOGLE_SHEET_MIME, XLSX_MIME}:
            raise WorkbookSourceError(
                "UNSUPPORTED_DRIVE_FILE_TYPE",
                "The configured Drive file must be a Google spreadsheet or an XLSX workbook.",
            )
        modified_at = metadata.get("modifiedTime")
        if not isinstance(modified_at, str) or not modified_at:
            raise WorkbookSourceError(
                "DRIVE_REVISION_UNAVAILABLE",
                "Google Drive did not provide a stable modification timestamp.",
            )
        if mime_type == GOOGLE_SHEET_MIME:
            method = "google_drive_xlsx_export"
            data = self._get_bytes(
                f"{DRIVE_FILES_API}/{encoded_id}/export",
                {"mimeType": XLSX_MIME},
            )
        elif mime_type == XLSX_MIME:
            method = "google_drive_xlsx_download"
            if isinstance(metadata.get("size"), (str, int)):
                try:
                    remote_size = int(metadata["size"])
                except ValueError:
                    remote_size = 0
                if remote_size > self.max_bytes:
                    raise WorkbookSourceError(
                        "WORKBOOK_TOO_LARGE",
                        _size_limit_message(self.max_bytes),
                    )
            data = self._get_bytes(
                f"{DRIVE_FILES_API}/{encoded_id}",
                {"alt": "media", "supportsAllDrives": "true"},
            )
            expected_md5 = metadata.get("md5Checksum")
            if isinstance(expected_md5, str) and expected_md5:
                actual_md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
                if actual_md5.casefold() != expected_md5.casefold():
                    raise WorkbookSourceError(
                        "DRIVE_CHECKSUM_MISMATCH",
                        "The downloaded XLSX does not match Google Drive's file checksum.",
                    )
        else:
            raise WorkbookSourceError(
                "UNSUPPORTED_DRIVE_FILE_TYPE",
                "The configured Drive file must be a Google spreadsheet or an XLSX workbook.",
            )
        after_download = self._get_json(
            f"{DRIVE_FILES_API}/{encoded_id}",
            {
                "fields": "id,mimeType,modifiedTime,headRevisionId,md5Checksum,size",
                "supportsAllDrives": "true",
            },
        )
        identity_fields = ("id", "mimeType", "modifiedTime", "headRevisionId", "md5Checksum")
        if any(metadata.get(field) != after_download.get(field) for field in identity_fields):
            raise WorkbookSourceError(
                "DRIVE_SOURCE_CHANGED_DURING_ACQUISITION",
                "The Google Drive workbook changed during acquisition; retry after it is stable.",
            )
        return AcquiredBytes(
            data=data,
            method=method,
            source_revision=(
                metadata.get("headRevisionId")
                if isinstance(metadata.get("headRevisionId"), str)
                else None
            ),
            source_modified_at=(
                metadata.get("modifiedTime")
                if isinstance(metadata.get("modifiedTime"), str)
                else None
            ),
            source_checksum=(
                metadata.get("md5Checksum")
                if isinstance(metadata.get("md5Checksum"), str)
                else None
            ),
            source_mime_type=mime_type if isinstance(mime_type, str) else None,
        )


def load_google_drive_reader(
    credential_path: Path,
) -> GoogleDriveWorkbookReader:
    """Build a Drive reader using a dedicated, repository-external service-account file."""
    resolved_path = _assert_private_location(credential_path, label="Google credential")
    if not resolved_path.is_file():
        raise WorkbookSourceError(
            "CREDENTIAL_FILE_MISSING", "The configured Google credential file is missing."
        )
    if os.name != "nt" and stat.S_IMODE(resolved_path.stat().st_mode) & 0o077:
        raise WorkbookSourceError(
            "CREDENTIAL_FILE_PERMISSIONS",
            "Restrict the Google credential file to its owner before acquisition.",
        )
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            str(resolved_path), scopes=[DRIVE_READONLY_SCOPE]
        )  # type: ignore[no-untyped-call]
        session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
    except Exception as error:
        raise WorkbookSourceError(
            "CREDENTIAL_INVALID", "The Google service-account credential could not be loaded."
        ) from error
    return GoogleDriveWorkbookReader(session)


class SnapshotStore:
    """Private, append-only manifests and content-addressed workbook blobs."""

    def __init__(self, root: Path) -> None:
        self.root = _assert_private_location(root, label="workbook snapshot store")
        self.blob_root = self.root / "blobs" / "sha256"
        self.run_root = self.root / "runs"
        for directory in (self.root, self.root / "blobs", self.blob_root, self.run_root):
            if directory.is_symlink():
                raise WorkbookSourceError(
                    "STORE_SYMLINK_FORBIDDEN",
                    "The snapshot store cannot contain symlinked directories.",
                )
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with suppress(OSError):
                directory.chmod(0o700)

    def _write_manifest(self, manifest: dict[str, Any]) -> Path:
        run_id = manifest["run_id"]
        target = self.run_root / f"{run_id}.json"
        payload = (
            json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".manifest-", dir=self.run_root)
        temporary = Path(temporary_name)
        try:
            with suppress(AttributeError, OSError):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Linking a fully-written temporary file gives us an atomic create-if-absent
                # operation on the same filesystem. A rename can replace an existing file on
                # POSIX if another writer wins the existence-check race.
                os.link(temporary, target)
            except FileExistsError as error:
                raise WorkbookSourceError(
                    "RUN_ID_COLLISION", "The acquisition run identifier already exists."
                ) from error
            with suppress(OSError):
                target.chmod(0o600)
            return target
        finally:
            if temporary.exists():
                temporary.unlink()

    def _store_blob(self, data: bytes, digest: str) -> str:
        target_directory = self.blob_root / digest
        target_file = target_directory / "workbook.xlsx"
        if target_directory.exists():
            if (
                target_directory.is_symlink()
                or not target_file.is_file()
                or target_file.is_symlink()
            ):
                raise WorkbookSourceError(
                    "CACHE_BLOB_INVALID", "A cached workbook blob is not a regular file."
                )
            existing_digest = _sha256_bytes(target_file.read_bytes())
            if existing_digest != digest:
                raise WorkbookSourceError(
                    "CACHE_BLOB_CORRUPTED", "A cached workbook failed its content-hash check."
                )
            return str(target_file.relative_to(self.root))

        temporary_directory = Path(tempfile.mkdtemp(prefix=".blob-", dir=self.blob_root))
        temporary_file = temporary_directory / "workbook.xlsx"
        try:
            try:
                temporary_directory.chmod(0o700)
                descriptor = os.open(temporary_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as error:
                raise WorkbookSourceError(
                    "CACHE_WRITE_FAILED", "The private workbook cache could not be written."
                ) from error
            try:
                os.rename(temporary_directory, target_directory)
            except OSError:
                if target_directory.is_symlink() or not target_directory.is_dir():
                    raise
                existing_file = target_directory / "workbook.xlsx"
                if (
                    existing_file.is_symlink()
                    or not existing_file.is_file()
                    or _sha256_bytes(existing_file.read_bytes()) != digest
                ):
                    raise WorkbookSourceError(
                        "CACHE_BLOB_CORRUPTED",
                        "A concurrent cached workbook failed its content-hash check.",
                    ) from None
            with suppress(OSError):
                target_directory.chmod(0o700)
                target_file.chmod(0o600)
            return str(target_file.relative_to(self.root))
        except WorkbookSourceError:
            raise
        except OSError as error:
            raise WorkbookSourceError(
                "CACHE_WRITE_FAILED", "The private workbook cache could not be written."
            ) from error
        finally:
            if temporary_directory.exists():
                shutil.rmtree(temporary_directory, ignore_errors=True)

    def _latest_accepted_manifest(
        self, profile_key: str, source_identity_sha256: str
    ) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for path in self.run_root.glob("*.json"):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(manifest, dict)
                and manifest.get("profile") == profile_key
                and manifest.get("source_identity_sha256") == source_identity_sha256
                and manifest.get("schema_baseline_accepted") is True
                and manifest.get("artifact_sha256")
            ):
                candidates.append(manifest)
        if not candidates:
            return None
        candidates.sort(key=lambda item: str(item.get("completed_at", "")))
        return candidates[-1]

    def manifest(self, run_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise WorkbookSourceError("INVALID_RUN_ID", "Use a 32-character acquisition run ID.")
        path = self.run_root / f"{run_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkbookSourceError(
                "RUN_MANIFEST_NOT_FOUND", "The acquisition run manifest was not found."
            ) from error
        if not isinstance(value, dict):
            raise WorkbookSourceError(
                "RUN_MANIFEST_INVALID", "The acquisition run manifest is invalid."
            )
        return value

    def accept_schema_baseline(self, run_id: str, expected_sha256: str) -> dict[str, Any]:
        """Append an immutable operator review event for one exact acquired snapshot."""
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise WorkbookSourceError(
                "INVALID_EXPECTED_SHA256", "The expected SHA-256 must contain 64 hex characters."
            )
        source_manifest = self.manifest(run_id)
        artifact_digest = source_manifest.get("artifact_sha256")
        if (
            not isinstance(artifact_digest, str)
            or artifact_digest.casefold() != expected_sha256.casefold()
        ):
            raise WorkbookSourceError(
                "EXPECTED_SHA256_MISMATCH",
                "The reviewed SHA-256 does not match the acquired workbook.",
            )
        if (
            source_manifest.get("status") != "ACQUIRED_REVIEW_REQUIRED"
            or source_manifest.get("review_required") is not True
            or source_manifest.get("schema_state") not in {"UNBASELINED", "DRIFTED"}
        ):
            raise WorkbookSourceError(
                "SCHEMA_REVIEW_NOT_REQUIRED",
                "Only an acquired unbaselined or drifted schema can be reviewed.",
            )
        blob_path = source_manifest.get("blob_path")
        if not isinstance(blob_path, str):
            raise WorkbookSourceError(
                "CACHE_BLOB_INVALID", "The reviewed snapshot has no cached workbook."
            )
        relative_blob_path = Path(blob_path)
        expected_blob_path = Path("blobs") / "sha256" / artifact_digest / "workbook.xlsx"
        if relative_blob_path.is_absolute() or ".." in relative_blob_path.parts:
            raise WorkbookSourceError(
                "CACHE_BLOB_INVALID", "The reviewed snapshot path is invalid."
            )
        if relative_blob_path != expected_blob_path:
            raise WorkbookSourceError(
                "CACHE_BLOB_INVALID", "The reviewed snapshot path is invalid."
            )
        blob_directory = self.root / relative_blob_path.parent
        cached_file = self.root / relative_blob_path
        if (
            not _is_within(cached_file.resolve(), self.root.resolve())
            or blob_directory.is_symlink()
            or cached_file.is_symlink()
            or not cached_file.is_file()
            or _sha256_bytes(cached_file.read_bytes()) != artifact_digest
        ):
            raise WorkbookSourceError(
                "CACHE_BLOB_CORRUPTED",
                "The reviewed workbook is missing or failed its content-hash check.",
            )

        source_identity_digest = source_manifest.get("source_identity_sha256")
        profile_key = source_manifest.get("profile")
        for path in self.run_root.glob("*.json"):
            candidate = self.manifest(path.stem)
            if (
                candidate.get("source_identity_sha256") == source_identity_digest
                and candidate.get("profile") == profile_key
                and candidate.get("run_id") != run_id
                and candidate.get("status") in {"ACQUIRED", "ACQUIRED_REVIEW_REQUIRED"}
                and candidate.get("artifact_sha256")
                and str(candidate.get("completed_at", ""))
                > str(source_manifest.get("completed_at", ""))
            ):
                raise WorkbookSourceError(
                    "STALE_SCHEMA_REVIEW",
                    "A newer workbook acquisition exists; review and accept the newest run.",
                )

        latest_accepted = self._latest_accepted_manifest(
            str(profile_key), str(source_identity_digest)
        )
        if latest_accepted is not None and str(latest_accepted.get("completed_at", "")) >= str(
            source_manifest.get("completed_at", "")
        ):
            raise WorkbookSourceError(
                "STALE_SCHEMA_REVIEW",
                "A newer schema baseline exists; acquire and review the current workbook.",
            )

        review: dict[str, Any] = {
            "manifest_version": 1,
            "run_id": uuid.uuid4().hex,
            "parent_run_id": run_id,
            "profile": profile_key,
            "contract_version": source_manifest.get("contract_version"),
            "expected_filename": source_manifest.get("expected_filename"),
            "source_identity_sha256": source_identity_digest,
            "acquisition_method": source_manifest.get("acquisition_method"),
            "acquired_at": source_manifest.get("acquired_at"),
            "reviewed_at": _utc_timestamp(),
            "completed_at": _utc_timestamp(),
            "source_revision": source_manifest.get("source_revision"),
            "source_modified_at": source_manifest.get("source_modified_at"),
            "source_checksum": source_manifest.get("source_checksum"),
            "source_mime_type": source_manifest.get("source_mime_type"),
            "artifact_sha256": artifact_digest,
            "artifact_bytes": source_manifest.get("artifact_bytes"),
            "blob_path": blob_path,
            "schema_fingerprint": source_manifest.get("schema_fingerprint"),
            "header_fingerprint": source_manifest.get("header_fingerprint"),
            "schema_state": source_manifest.get("schema_state"),
            "schema_baseline_accepted": True,
            "content_state": source_manifest.get("content_state"),
            "previous_accepted_run_id": latest_accepted.get("run_id") if latest_accepted else None,
            "review_required": False,
            "inventory": source_manifest.get("inventory"),
            "import_triggered": False,
            "review_action": "ACCEPT_SCHEMA_BASELINE",
            "status": "SCHEMA_BASELINE_ACCEPTED",
            "diagnostics": [],
        }
        self._write_manifest(review)
        return review


def acquire_snapshot(
    *,
    store: SnapshotStore,
    profile: WorkbookProfile,
    source_identity: str,
    fetch: Callable[[], AcquiredBytes],
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Acquire one snapshot; record success/failure without ever invoking an importer."""
    if expected_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise WorkbookSourceError(
            "INVALID_EXPECTED_SHA256", "The expected SHA-256 must contain 64 hex characters."
        )

    run_id = uuid.uuid4().hex
    started_at = _utc_timestamp()
    identity_digest = hashlib.sha256(source_identity.encode("utf-8")).hexdigest()
    fetched: AcquiredBytes | None = None
    acquired_at: str | None = None
    artifact_digest: str | None = None
    inventory: WorkbookInventory | None = None
    previous: dict[str, Any] | None = None
    try:
        fetched = fetch()
        acquired_at = _utc_timestamp()
        if len(fetched.data) > MAX_WORKBOOK_BYTES:
            raise WorkbookSourceError(
                "WORKBOOK_TOO_LARGE",
                _size_limit_message(),
            )
        artifact_digest = _sha256_bytes(fetched.data)
        if expected_sha256 is not None and artifact_digest.casefold() != expected_sha256.casefold():
            raise WorkbookSourceError(
                "EXPECTED_SHA256_MISMATCH",
                "The acquired workbook does not match the operator-reviewed SHA-256.",
            )
        inventory = inspect_workbook(fetched.data, profile)
        previous = store._latest_accepted_manifest(profile.key, identity_digest)
        schema_state = (
            "UNBASELINED"
            if previous is None
            else "UNCHANGED"
            if previous.get("schema_fingerprint") == inventory.schema_fingerprint
            else "DRIFTED"
        )
        content_state = (
            "FIRST_ACQUISITION"
            if previous is None
            else "UNCHANGED"
            if previous.get("artifact_sha256") == artifact_digest
            else "CHANGED"
        )
        schema_accepted = schema_state == "UNCHANGED"
        blob_path = store._store_blob(fetched.data, artifact_digest)
        manifest: dict[str, Any] = {
            "manifest_version": 1,
            "run_id": run_id,
            "profile": profile.key,
            "contract_version": profile.contract_version,
            "expected_filename": profile.expected_filename,
            "source_identity_sha256": identity_digest,
            "acquisition_method": fetched.method,
            "started_at": started_at,
            "acquired_at": acquired_at,
            "completed_at": _utc_timestamp(),
            "source_revision": fetched.source_revision,
            "source_modified_at": fetched.source_modified_at,
            "source_checksum": fetched.source_checksum,
            "source_mime_type": fetched.source_mime_type,
            "artifact_sha256": artifact_digest,
            "artifact_bytes": len(fetched.data),
            "blob_path": blob_path,
            "schema_fingerprint": inventory.schema_fingerprint,
            "header_fingerprint": inventory.header_fingerprint,
            "schema_state": schema_state,
            "schema_baseline_accepted": schema_accepted,
            "content_state": content_state,
            "previous_accepted_run_id": previous.get("run_id") if previous else None,
            "review_required": not schema_accepted,
            "inventory": {
                "date_system": inventory.date_system,
                "sheet_names": list(inventory.sheet_names),
                "hidden_sheet_names": list(inventory.hidden_sheet_names),
                "defined_names": [
                    {"name": name, "scope": scope, "definition_sha256": definition_hash}
                    for name, scope, definition_hash in inventory.defined_names
                ],
                "sheet_metrics": list(inventory.sheet_metrics),
                "unclassified_sheets": list(inventory.unclassified_sheets),
            },
            "import_triggered": False,
            "status": "ACQUIRED" if schema_accepted else "ACQUIRED_REVIEW_REQUIRED",
            "diagnostics": [],
        }
    except WorkbookSourceError as error:
        manifest = {
            "manifest_version": 1,
            "run_id": run_id,
            "profile": profile.key,
            "contract_version": profile.contract_version,
            "expected_filename": profile.expected_filename,
            "source_identity_sha256": identity_digest,
            "started_at": started_at,
            "acquired_at": acquired_at,
            "completed_at": _utc_timestamp(),
            "artifact_sha256": artifact_digest,
            "artifact_bytes": len(fetched.data) if fetched else None,
            "acquisition_method": fetched.method if fetched else None,
            "source_revision": fetched.source_revision if fetched else None,
            "source_modified_at": fetched.source_modified_at if fetched else None,
            "source_checksum": fetched.source_checksum if fetched else None,
            "source_mime_type": fetched.source_mime_type if fetched else None,
            "schema_fingerprint": inventory.schema_fingerprint if inventory else None,
            "schema_baseline_accepted": False,
            "review_required": True,
            "import_triggered": False,
            "status": "FAILED",
            "error_code": error.code,
            "diagnostics": list(error.diagnostics),
        }
    except Exception:
        # Unexpected exception strings can contain URLs, local paths or provider details.
        manifest = {
            "manifest_version": 1,
            "run_id": run_id,
            "profile": profile.key,
            "contract_version": profile.contract_version,
            "expected_filename": profile.expected_filename,
            "source_identity_sha256": identity_digest,
            "started_at": started_at,
            "acquired_at": acquired_at,
            "completed_at": _utc_timestamp(),
            "artifact_sha256": artifact_digest,
            "artifact_bytes": len(fetched.data) if fetched else None,
            "acquisition_method": fetched.method if fetched else None,
            "source_revision": fetched.source_revision if fetched else None,
            "source_modified_at": fetched.source_modified_at if fetched else None,
            "source_checksum": fetched.source_checksum if fetched else None,
            "source_mime_type": fetched.source_mime_type if fetched else None,
            "schema_baseline_accepted": False,
            "review_required": True,
            "import_triggered": False,
            "status": "FAILED",
            "error_code": "UNEXPECTED_ACQUISITION_ERROR",
            "diagnostics": [],
        }
    store._write_manifest(manifest)
    return manifest


def _read_operator_file(path: Path) -> AcquiredBytes:
    resolved = _assert_private_location(path, label="operator-supplied workbook")
    if resolved.suffix.casefold() != ".xlsx":
        raise WorkbookSourceError(
            "UNSUPPORTED_WORKBOOK_EXTENSION", "Supply an .xlsx workbook file."
        )
    if not resolved.is_file():
        raise WorkbookSourceError(
            "SOURCE_FILE_MISSING", "The operator-supplied workbook file is missing."
        )
    try:
        with resolved.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise WorkbookSourceError(
                    "SOURCE_FILE_UNREADABLE",
                    "The operator-supplied workbook is not a regular file.",
                )
            if before.st_size > MAX_WORKBOOK_BYTES:
                raise WorkbookSourceError(
                    "WORKBOOK_TOO_LARGE",
                    _size_limit_message(),
                )
            data = stream.read(MAX_WORKBOOK_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(data) > MAX_WORKBOOK_BYTES:
            raise WorkbookSourceError(
                "WORKBOOK_TOO_LARGE",
                _size_limit_message(),
            )
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or len(data) != before.st_size:
            raise WorkbookSourceError(
                "SOURCE_FILE_CHANGED_DURING_ACQUISITION",
                "The operator-supplied workbook changed during acquisition; "
                "retry from a stable snapshot.",
            )
    except WorkbookSourceError:
        raise
    except OSError as error:
        raise WorkbookSourceError(
            "SOURCE_FILE_UNREADABLE", "The operator-supplied workbook could not be read."
        ) from error
    return AcquiredBytes(
        data=data,
        method="operator_supplied_xlsx",
        source_revision=None,
        source_modified_at=None,
        source_checksum=None,
        source_mime_type=XLSX_MIME,
    )


def _google_source(profile: WorkbookProfile) -> tuple[GoogleDriveWorkbookReader, str]:
    id_env = DRIVE_ID_ENVIRONMENT[profile.key]
    file_id = os.environ.get(id_env, "").strip()
    if not file_id:
        raise WorkbookSourceError(
            "DRIVE_SOURCE_NOT_CONFIGURED", f"Set {id_env} for the selected source."
        )
    credential = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "").strip()
    if not credential:
        raise WorkbookSourceError(
            "CREDENTIAL_FILE_NOT_CONFIGURED",
            "Set GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE to a private service-account key file.",
        )
    return load_google_drive_reader(Path(credential)), file_id


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    acquire = commands.add_parser("acquire", help="Acquire one workbook without importing it")
    acquire.add_argument("profile", choices=sorted(PROFILES))
    acquire.add_argument(
        "--store", type=Path, required=True, help="Private path outside the repository"
    )
    acquire.add_argument(
        "--from-file", type=Path, help="Operator-supplied XLSX file; otherwise use Google Drive"
    )
    acquire.add_argument(
        "--expected-sha256", help="Require an exact operator-reviewed workbook digest"
    )
    acquire.add_argument(
        "--confirm-source-acquisition",
        action="store_true",
        help="Explicitly authorize retrieval and private storage of the selected workbook",
    )
    show = commands.add_parser("show", help="Display a private run manifest for operator review")
    show.add_argument("run_id")
    show.add_argument("--store", type=Path, required=True)
    accept_schema = commands.add_parser(
        "accept-schema", help="Append a review decision for a schema-changing snapshot"
    )
    accept_schema.add_argument("run_id")
    accept_schema.add_argument("--store", type=Path, required=True)
    accept_schema.add_argument("--expected-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        store = SnapshotStore(args.store)
        if args.command == "show":
            print(json.dumps(store.manifest(args.run_id), indent=2, sort_keys=True))
            return 0
        if args.command == "accept-schema":
            manifest = store.accept_schema_baseline(args.run_id, args.expected_sha256)
            print(
                json.dumps(
                    {
                        "run_id": manifest["run_id"],
                        "parent_run_id": manifest["parent_run_id"],
                        "profile": manifest["profile"],
                        "status": manifest["status"],
                        "import_triggered": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if not args.confirm_source_acquisition:
            raise WorkbookSourceError(
                "ACQUISITION_CONFIRMATION_REQUIRED",
                "Pass --confirm-source-acquisition to retrieve and store a workbook snapshot.",
            )
        profile = PROFILES[args.profile]
        if args.from_file is not None:
            source_identity = f"operator-supplied:{profile.key}"
            operator_path = args.from_file

            def fetch_operator_file() -> AcquiredBytes:
                return _read_operator_file(operator_path)

            fetch: Callable[[], AcquiredBytes] = fetch_operator_file
        else:
            reader, file_id = _google_source(profile)
            source_identity = f"google-drive:{file_id}"

            def fetch_google_drive_file() -> AcquiredBytes:
                return reader.acquire(file_id)

            fetch = fetch_google_drive_file
        manifest = acquire_snapshot(
            store=store,
            profile=profile,
            source_identity=source_identity,
            fetch=fetch,
            expected_sha256=args.expected_sha256,
        )
        summary = {
            "run_id": manifest["run_id"],
            "profile": manifest["profile"],
            "status": manifest["status"],
            "schema_state": manifest.get("schema_state"),
            "review_required": manifest["review_required"],
            "import_triggered": False,
        }
        print(json.dumps(summary, sort_keys=True))
        return 0 if manifest["status"] == "ACQUIRED" else 2
    except WorkbookSourceError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
