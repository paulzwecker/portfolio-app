"""Reviewed template and replay tests for the generalized Sheets DCF exporter."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from portfolio_api.financial_model_package import PackageCell, PackageError, _package_cell
from portfolio_api.financial_model_package_exporter import (
    CONTRACT_VERSION,
    DcfModelPackage,
    DcfModelPackageExporter,
    DcfModelPackageStore,
    _a1_coordinates,
    _qualified_ranges,
    build_dcf_model_package,
    validate_dcf_model_package,
)
from portfolio_api.financial_model_package_templates import (
    DCF_MODEL_TEMPLATES,
    get_dcf_model_template,
)
from portfolio_api.legacy_import import Workbook
from portfolio_api.model_input_migration import DEFAULT_WORKBOOK
from portfolio_api.settings import Settings
from portfolio_api.workbook_sources import GOOGLE_SHEET_MIME

pytestmark = pytest.mark.source_data

SYNTHETIC_SPREADSHEET_ID = "synthetic-dcf-model-spreadsheet-v2"


class _Response:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, content: bytes):
        self.content = content


class _DecimalJsonEncoder(json.JSONEncoder):
    def default(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return f"__EXACT_DECIMAL__{format(value, 'f')}__"
        return super().default(value)


def _wire(value: Any) -> bytes:
    encoded = json.dumps(value, cls=_DecimalJsonEncoder, separators=(",", ":"))
    encoded = re.sub(r'"__EXACT_DECIMAL__(-?[0-9]+(?:\.[0-9]+)?)__"', r"\1", encoded)
    return encoded.encode()


def _fixture_source_cells(model_key: str) -> dict[str, PackageCell]:
    workbook = Workbook.read(DEFAULT_WORKBOOK, lambda name: name == model_key)
    template = get_dcf_model_template(model_key)
    result: dict[str, PackageCell] = {}
    for qualified in _qualified_ranges(template):
        for _row, _column, address in _a1_coordinates(qualified):
            source = workbook.cell(model_key, address)
            entered: dict[str, Any] | None = None
            effective: dict[str, Any] | None = None
            if source.formula is not None:
                entered = {"formulaValue": source.formula}
            elif source.value is not None:
                if source.kind == "b":
                    entered = {"boolValue": source.value.casefold() == "true"}
                else:
                    try:
                        entered = {"numberValue": Decimal(source.value)}
                    except Exception:
                        entered = {"stringValue": source.value}
            if source.value is not None:
                if source.kind == "b":
                    effective = {"boolValue": source.value.casefold() == "true"}
                else:
                    try:
                        effective = {"numberValue": Decimal(source.value)}
                    except Exception:
                        effective = {"stringValue": source.value}
            raw: dict[str, Any] = {}
            if entered is not None:
                raw["userEnteredValue"] = entered
            if effective is not None:
                raw["effectiveValue"] = effective
            if source.number_format_type or source.number_format_code:
                raw["effectiveFormat"] = {
                    "numberFormat": {
                        key: value
                        for key, value in (
                            ("type", source.number_format_type),
                            ("pattern", source.number_format_code),
                        )
                        if value is not None
                    }
                }
            transport = (
                "CELL_VALUE_DATA_PRESENT"
                if entered is not None or effective is not None
                else "EXPLICIT_EMPTY_CELL_DATA"
            )
            result[address] = _package_cell(raw, transport)
    return result


def _fixture_package(model_key: str) -> tuple[DcfModelPackage, str]:
    template = get_dcf_model_template(model_key)
    cells = _fixture_source_cells(model_key)
    package = build_dcf_model_package(
        template,
        source_metadata={
            "source_identity_sha256": hashlib.sha256(SYNTHETIC_SPREADSHEET_ID.encode()).hexdigest(),
            "modified_time": "2026-10-01T12:00:00Z",
            "head_revision_id": "synthetic-drive-revision",
            "checksum": None,
        },
        structure={"sheet_id": 17, "time_zone": "America/Los_Angeles"},
        source_cells=cells,
        captured_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
    )
    payload = json.dumps(
        package.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return package, hashlib.sha256(payload).hexdigest()


class _FakeSheetsSession:
    def __init__(self, package: DcfModelPackage):
        self.package = package
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.mutate_address: str | None = None
        self.mutate_after_first_range = False

    def get(self, url: str, *, params: dict[str, str], **_kwargs: Any) -> _Response:
        self.calls.append((url, params))
        if "/drive/v3/files/" in url:
            return _Response(
                _wire(
                    {
                        "id": SYNTHETIC_SPREADSHEET_ID,
                        "mimeType": GOOGLE_SHEET_MIME,
                        "modifiedTime": self.package.source.modified_time,
                        "headRevisionId": self.package.source.drive_revision_id,
                    }
                )
            )
        if "ranges" not in params:
            return _Response(
                _wire(
                    {
                        "spreadsheetId": SYNTHETIC_SPREADSHEET_ID,
                        "properties": {"timeZone": self.package.source.spreadsheet_time_zone},
                        "sheets": [
                            {
                                "properties": {
                                    "sheetId": self.package.source.sheet_id,
                                    "title": self.package.source.sheet_title,
                                    "gridProperties": {"rowCount": 220, "columnCount": 42},
                                }
                            }
                        ],
                    }
                )
            )
        a1_range = params["ranges"]
        coordinates = _a1_coordinates(a1_range)
        rows: list[dict[str, Any]] = []
        first_row, first_column = coordinates[0][:2]
        last_row, last_column = coordinates[-1][:2]
        for row in range(first_row, last_row + 1):
            row_values: list[dict[str, Any]] = []
            for column in range(first_column, last_column + 1):
                address = next(
                    item[2] for item in coordinates if item[0] == row and item[1] == column
                )
                row_values.append(_raw_cell(self.package.source_cells[address]))
            rows.append({"values": row_values})
        body = {
            "spreadsheetId": SYNTHETIC_SPREADSHEET_ID,
            "sheets": [
                {
                    "properties": {"title": self.package.source.sheet_title},
                    "data": [
                        {
                            "startRow": first_row - 1,
                            "startColumn": first_column - 1,
                            "rowData": rows,
                        }
                    ],
                }
            ],
        }
        response = _Response(_wire(body))
        if (
            self.mutate_after_first_range
            and len([call for call in self.calls if "ranges" in call[1]]) == 1
        ):
            assert self.mutate_address is not None
            cell = self.package.source_cells[self.mutate_address]
            assert cell.effective_value is not None
            changed = cell.model_copy(
                update={
                    "effective_value": cell.effective_value.model_copy(
                        update={
                            "value": format(Decimal(cell.effective_value.value) + Decimal("1"), "f")
                        }
                    )
                }
            )
            cells = dict(self.package.source_cells)
            cells[self.mutate_address] = changed
            self.package = self.package.model_copy(update={"source_cells": cells})
        return response


def _raw_cell(cell: PackageCell) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if cell.user_entered_value is not None:
        value = cell.user_entered_value
        key = {
            "NUMBER": "numberValue",
            "STRING": "stringValue",
            "BOOLEAN": "boolValue",
            "FORMULA": "formulaValue",
        }.get(value.kind)
        if key is not None:
            cell_value: Any = Decimal(value.value) if value.kind == "NUMBER" else value.value
            raw["userEnteredValue"] = {key: cell_value}
    if cell.effective_value is not None:
        value = cell.effective_value
        key = {"NUMBER": "numberValue", "STRING": "stringValue", "BOOLEAN": "boolValue"}.get(
            value.kind
        )
        if key is not None:
            cell_value = Decimal(value.value) if value.kind == "NUMBER" else value.value
            raw["effectiveValue"] = {key: cell_value}
        elif value.kind == "ERROR":
            raw["effectiveValue"] = {
                "errorValue": {"type": value.value, "message": value.detail or "fixture error"}
            }
    if cell.number_format_type is not None or cell.number_format_pattern is not None:
        raw["effectiveFormat"] = {
            "numberFormat": {
                key: value
                for key, value in (
                    ("type", cell.number_format_type),
                    ("pattern", cell.number_format_pattern),
                )
                if value is not None
            }
        }
    return raw


@pytest.mark.parametrize("model_key", ("P-GOOGL", "P-CPRT", "P-AMZN"))
def test_three_reviewed_dcf_templates_build_and_replay_identically(model_key: str) -> None:
    package, payload_hash = _fixture_package(model_key)
    validated = validate_dcf_model_package(
        package, payload_hash, validated_at=datetime(2026, 10, 2, tzinfo=UTC)
    )

    assert package.contract_version == CONTRACT_VERSION
    assert package.identity.source_model_key == model_key
    assert package.revision.acceptance_state == "PROPOSAL_NOT_ACCEPTED"
    assert package.identity.listing_currency == package.identity.model_currency == "USD"
    assert package.identity.return_comparability == "NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR"
    assert package.input_cell_map["base.base_revenue"] == "B17"
    assert package.input_cell_map["scenarios.BASE.probability"] == "AO5"
    assert package.input_cell_map["scenarios.BASE.years"] == "J16:N22"
    if model_key == "P-GOOGL":
        assert package.input_cell_map["scenarios.BASE.year10_ufcf_growth"] == "J24:N24"
    elif model_key == "P-CPRT":
        assert package.input_cell_map["scenarios.BASE.year10_ufcf_growth"] == "C210"
    else:
        assert package.input_cell_map["scenarios.BASE.tail_ufcf_growth"] == "C206:C210"
        assert package.identity.return_methodology_code == "UFCF_ENTERPRISE_HMODEL_IRR"
    assert validated.parity_report["status"] == "PARITY_PASS"
    assert validated.parity_report["projection_reconciliation"]["compared"] == 30
    assert validated.parity_report["projection_reconciliation"]["passed"] == 30
    assert validated.parity_report["output_reconciliation"]["compared"] == 22
    assert validated.parity_report["output_reconciliation"]["passed"] == 22


def test_supported_templates_are_explicitly_distinct_and_unknown_layouts_fail() -> None:
    googl = get_dcf_model_template("P-GOOGL")
    cprt = get_dcf_model_template("P-CPRT")
    amzn = get_dcf_model_template("P-AMZN")

    assert googl.template_id != cprt.template_id != amzn.template_id
    assert "E24:S24" in googl.ranges
    assert "B210:D210" in cprt.ranges
    assert "B206:D210" in amzn.ranges
    with pytest.raises(ValueError, match="No reviewed direct-Sheets DCF template"):
        get_dcf_model_template("P-UNKNOWN")


def test_live_exporter_captures_and_replays_three_layouts_without_xlsx_fallback(
    tmp_path: Path,
) -> None:
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path / "service-account.json",
    )
    for model_key in DCF_MODEL_TEMPLATES:
        fixture_package, fixture_hash = _fixture_package(model_key)
        transport = _FakeSheetsSession(fixture_package)
        store = DcfModelPackageStore(tmp_path / model_key)
        exporter = DcfModelPackageExporter(
            settings,
            store,
            transport,
            sleeper=lambda _delay: None,
            clock=lambda: datetime(2026, 10, 3, tzinfo=UTC),
        )
        dry_run = exporter.capture(model_key, dry_run=True)
        assert dry_run.stored_run is None
        assert list(store.store.run_root.glob("*.json")) == []
        calls_before_store = len(transport.calls)
        result = exporter.capture(model_key)

        assert result.source_stable is True
        assert result.validation.parity_report["status"] == "PARITY_PASS"
        assert result.stored_run is not None
        replay = store.load(result.stored_run.run_id, result.payload_sha256)
        assert replay.payload_sha256 == result.payload_sha256
        assert replay.package == result.package
        assert result.payload_sha256 == fixture_hash
        assert len(transport.calls) - calls_before_store == result.request_count


def test_unknown_model_capture_fails_before_any_provider_request(tmp_path: Path) -> None:
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path / "service-account.json",
    )
    fixture_package, _ = _fixture_package("P-GOOGL")
    transport = _FakeSheetsSession(fixture_package)
    exporter = DcfModelPackageExporter(
        settings,
        DcfModelPackageStore(tmp_path / "store"),
        transport,
        sleeper=lambda _delay: None,
    )
    with pytest.raises(PackageError, match="No reviewed template"):
        exporter.capture("P-UNKNOWN")
    assert transport.calls == []


def test_capture_rejects_source_change_between_double_reads(tmp_path: Path) -> None:
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path / "service-account.json",
    )
    fixture_package, _ = _fixture_package("P-CPRT")
    transport = _FakeSheetsSession(fixture_package)
    transport.mutate_address = "B4"
    transport.mutate_after_first_range = True
    exporter = DcfModelPackageExporter(
        settings,
        DcfModelPackageStore(tmp_path / "store"),
        transport,
        sleeper=lambda _delay: None,
    )
    with pytest.raises(PackageError, match="changed during capture"):
        exporter.capture("P-CPRT")


def test_package_identity_tampering_is_detected_on_validation() -> None:
    package, payload_hash = _fixture_package("P-AMZN")
    changed_identity = package.identity.model_copy(update={"model_currency": "EUR"})
    changed = package.model_copy(update={"identity": changed_identity})
    changed_hash = hashlib.sha256(
        json.dumps(changed.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises((PackageError, ValueError)):
        validate_dcf_model_package(changed, changed_hash)
    assert payload_hash != changed_hash
