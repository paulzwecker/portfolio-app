"""Contract and replay checks for the P-GOOGL native model package."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    Listing,
    ReturnMethodologyDefinition,
    Security,
)
from portfolio_api.financial_model_package import (
    EXPECTED_PACKAGE_CELLS,
    P_GOOGL_RANGES,
    PACKAGE_MODEL_KEY,
    PACKAGE_VERSION,
    FinancialModelPackage,
    FinancialModelPackageStore,
    PackageCell,
    PackageError,
    PGooglSheetsExporter,
    _mapped_model,
    _package_cell,
    _package_from_cells,
    _range_coordinates,
    _strict_json,
    accept_financial_model_package,
    validate_financial_model_package,
)
from portfolio_api.legacy_import import Workbook
from portfolio_api.model_input_migration import DEFAULT_WORKBOOK
from portfolio_api.settings import Settings
from portfolio_api.workbook_sources import GOOGLE_SHEET_MIME

pytestmark = pytest.mark.source_data

SYNTHETIC_SPREADSHEET_ID = "synthetic-financial-model-spreadsheet-0001"


def _fixture_package() -> tuple[FinancialModelPackage, str]:
    workbook = Workbook.read(DEFAULT_WORKBOOK, lambda name: name == PACKAGE_MODEL_KEY)
    cells: dict[str, PackageCell] = {}
    for address in EXPECTED_PACKAGE_CELLS:
        source = workbook.sheets[PACKAGE_MODEL_KEY][address]
        entered: dict[str, Any] | None = None
        effective: dict[str, Any] | None = None
        if source.formula is not None:
            entered = {"formulaValue": source.formula}
        elif source.value is not None:
            if address in {"B12", "B15"}:
                entered = {"stringValue": source.value}
            else:
                entered = {"numberValue": Decimal(source.value)}
        if source.value is not None:
            if address in {"B12", "B15"}:
                effective = {"stringValue": source.value}
            else:
                effective = {"numberValue": Decimal(source.value)}
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
        if "userEnteredValue" in raw or "effectiveValue" in raw:
            transport_state = "CELL_VALUE_DATA_PRESENT"
        elif raw:
            transport_state = "CELL_METADATA_ONLY"
        else:
            transport_state = "EXPLICIT_EMPTY_CELL_DATA"
        cells[address] = _package_cell(raw, transport_state)
    metadata = {
        "source_identity_sha256": hashlib.sha256(SYNTHETIC_SPREADSHEET_ID.encode()).hexdigest(),
        "modified_time": "2026-10-01T12:00:00Z",
        "head_revision_id": "synthetic-revision",
        "checksum": None,
    }
    structure = {"sheet_id": 42, "time_zone": "America/Los_Angeles"}
    package = _package_from_cells(
        source_metadata=metadata,
        structure=structure,
        source_cells=cells,
        captured_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
    )
    payload_hash = hashlib.sha256(
        _strict_json(package.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()
    return package, payload_hash


class _Response:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, payload: bytes):
        self.content = payload

    def close(self) -> None:
        return None


class _DecimalJsonEncoder(json.JSONEncoder):
    def default(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return f"__EXACT_DECIMAL__{format(value, 'f')}__"
        return super().default(value)


def _wire_json(value: Any) -> bytes:
    encoded = json.dumps(value, cls=_DecimalJsonEncoder, separators=(",", ":"))
    encoded = re.sub(r'"__EXACT_DECIMAL__(-?[0-9]+(?:\.[0-9]+)?)__"', r"\1", encoded)
    return encoded.encode("utf-8")


def _raw_cell(cell: PackageCell) -> dict[str, Any]:
    def scalar(item: Any) -> dict[str, Any] | None:
        if item is None:
            return None
        if item.kind == "NUMBER":
            return {"numberValue": Decimal(item.value)}
        if item.kind == "STRING":
            return {"stringValue": item.value}
        if item.kind == "BOOLEAN":
            return {"boolValue": item.value}
        if item.kind == "FORMULA":
            return {"formulaValue": item.value}
        return None

    raw: dict[str, Any] = {}
    entered = scalar(cell.user_entered_value)
    effective = scalar(cell.effective_value)
    if cell.user_entered_value is not None and cell.user_entered_value.kind == "ERROR":
        entered = None
    if cell.effective_value is not None and cell.effective_value.kind == "ERROR":
        effective = {
            "errorValue": {
                "type": cell.effective_value.value,
                "message": cell.effective_value.detail or "synthetic error",
            }
        }
    if entered is not None:
        raw["userEnteredValue"] = entered
    if effective is not None:
        raw["effectiveValue"] = effective
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


class _FakeSheetsSession:
    def __init__(self, package: Any):
        self.package = package
        self.mutate_after_first_price = False
        self.mutate_probability_on_first_read = False
        self._probability_read_count = 0
        self.fail_range: str | None = None
        self.flaky_range: str | None = None
        self.flaky_failures_left = 0
        self.omit_range: str | None = None
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, *, params: dict[str, str], **_kwargs: Any) -> _Response:
        self.calls.append((url, params))
        if "/drive/v3/files/" in url:
            body = {
                "id": SYNTHETIC_SPREADSHEET_ID,
                "mimeType": GOOGLE_SHEET_MIME,
                "modifiedTime": self.package.source.modified_time,
                "headRevisionId": self.package.source.drive_revision_id,
            }
            return _Response(_wire_json(body))
        if "ranges" not in params:
            body = {
                "spreadsheetId": SYNTHETIC_SPREADSHEET_ID,
                "properties": {"timeZone": self.package.source.spreadsheet_time_zone},
                "sheets": [
                    {
                        "properties": {
                            "sheetId": self.package.source.sheet_id,
                            "title": PACKAGE_MODEL_KEY,
                            "gridProperties": {"rowCount": 220, "columnCount": 42},
                        }
                    }
                ],
            }
            return _Response(_wire_json(body))
        a1_range = params["ranges"]
        if a1_range == self.flaky_range and self.flaky_failures_left > 0:
            self.flaky_failures_left -= 1
            response = _Response(b'{"error":"synthetic transient failure"}')
            response.status_code = 503
            return response
        if a1_range == self.fail_range:
            response = _Response(b'{"error":"synthetic failure"}')
            response.status_code = 503
            return response
        if a1_range == self.omit_range:
            return _Response(
                _wire_json(
                    {
                        "spreadsheetId": SYNTHETIC_SPREADSHEET_ID,
                        "sheets": [{"properties": {"title": PACKAGE_MODEL_KEY}, "data": []}],
                    }
                )
            )
        coordinates = _range_coordinates(a1_range)
        first_row, first_col = coordinates[0][0], coordinates[0][1]
        last_row, last_col = coordinates[-1][0], coordinates[-1][1]
        rows: list[dict[str, Any]] = []
        for row_number in range(first_row, last_row + 1):
            values: list[dict[str, Any]] = []
            for column_number in range(first_col, last_col + 1):
                address = coordinates[
                    (row_number - first_row) * (last_col - first_col + 1)
                    + (column_number - first_col)
                ][2]
                values.append(_raw_cell(self.package.source_cells[address]))
            rows.append({"values": values})
        body = {
            "spreadsheetId": SYNTHETIC_SPREADSHEET_ID,
            "sheets": [
                {
                    "properties": {"title": PACKAGE_MODEL_KEY},
                    "data": [
                        {
                            "startRow": first_row - 1,
                            "startColumn": first_col - 1,
                            "rowData": rows,
                        }
                    ],
                }
            ],
        }
        response = _Response(_wire_json(body))
        if a1_range == "'P-GOOGL'!AO4:AO6":
            self._probability_read_count += 1
            if self._probability_read_count == 1 and self.mutate_probability_on_first_read:
                address = "AO4"
                original = self.package.source_cells[address]
                assert original.effective_value is not None
                changed_value = format(
                    Decimal(original.effective_value.value) + Decimal("0.01"), "f"
                )
                changed = original.model_copy(
                    update={
                        "effective_value": original.effective_value.model_copy(
                            update={"value": changed_value}
                        )
                    }
                )
                cells = dict(self.package.source_cells)
                cells[address] = changed
                self.package = self.package.model_copy(update={"source_cells": cells})
        if a1_range == P_GOOGL_RANGES[0] and self.mutate_after_first_price:
            self.mutate_after_first_price = False
            original = self.package.source_cells["B4"]
            changed = original.model_copy(
                update={
                    "effective_value": original.effective_value.model_copy(
                        update={"value": format(Decimal(original.effective_value.value) + 1, "f")}
                    )
                }
            )
            cells = dict(self.package.source_cells)
            cells["B4"] = changed
            self.package = self.package.model_copy(update={"source_cells": cells})
        return response


def test_package_replays_through_approved_p_googl_parity_fixture() -> None:
    package, payload_hash = _fixture_package()
    validated = validate_financial_model_package(
        package, payload_hash, validated_at=datetime(2026, 10, 1, tzinfo=UTC)
    )

    assert package.contract_version == PACKAGE_VERSION
    assert package.identity.return_methodology_code == "UFCF_ENTERPRISE_IRR"
    assert package.identity.return_perspective == "ENTERPRISE"
    assert package.revision.acceptance_state == "PROPOSAL_NOT_ACCEPTED"
    assert package.revision.source_effective_at is None
    assert validated.parity_report["status"] == "PARITY_PASS"
    assert validated.parity_report["projection_reconciliation"]["compared"] == 30
    assert validated.parity_report["projection_reconciliation"]["passed"] == 30
    assert validated.parity_report["output_reconciliation"]["compared"] == 22
    assert validated.parity_report["output_reconciliation"]["passed"] == 22


def test_package_store_roundtrip_is_content_addressed_and_deterministic(tmp_path: Path) -> None:
    package, payload_hash = _fixture_package()
    store = FinancialModelPackageStore(tmp_path / "private")
    first = store.capture(package, captured_at=datetime(2026, 10, 1, tzinfo=UTC), request_count=38)
    replay = store.load(first.run_id, payload_hash)
    second = store.capture(package, captured_at=datetime(2026, 10, 2, tzinfo=UTC), request_count=38)

    assert replay.payload_sha256 == payload_hash
    assert replay.package.model_dump(mode="json") == package.model_dump(mode="json")
    assert second.payload_sha256 == first.payload_sha256
    assert second.run_id != first.run_id


def test_package_cells_keep_blank_zero_formula_empty_and_error_distinct() -> None:
    blank = _package_cell({}, "EXPLICIT_EMPTY_CELL_DATA")
    empty = _package_cell(
        {"userEnteredValue": {"stringValue": ""}, "effectiveValue": {"stringValue": ""}},
        "CELL_VALUE_DATA_PRESENT",
    )
    formula_empty = _package_cell(
        {"userEnteredValue": {"formulaValue": '=IF(TRUE,"","x")'}},
        "CELL_VALUE_DATA_PRESENT",
    )
    zero = _package_cell(
        {
            "userEnteredValue": {"numberValue": Decimal("0.000")},
            "effectiveValue": {"numberValue": 0},
        },
        "CELL_VALUE_DATA_PRESENT",
    )
    error = _package_cell(
        {
            "userEnteredValue": {"formulaValue": "=NA()"},
            "effectiveValue": {"errorValue": {"type": "N_A", "message": "unavailable"}},
        },
        "CELL_VALUE_DATA_PRESENT",
    )

    assert blank.state == "BLANK"
    assert empty.state == "EMPTY_STRING"
    assert formula_empty.state == "FORMULA_EMPTY_RESULT"
    assert zero.state == "NUMBER_ZERO"
    assert zero.effective_value is not None
    assert zero.effective_value.value == "0"
    assert error.state == "ERROR"


def test_exporter_captures_two_stable_reads_and_replays_from_private_store(tmp_path: Path) -> None:
    package, payload_hash = _fixture_package()
    session = _FakeSheetsSession(package)
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path.parent / "service-account.json",
    )
    store = FinancialModelPackageStore(tmp_path / "store")
    run = PGooglSheetsExporter(
        settings,
        store,
        session,
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 10, 1, tzinfo=UTC),
    ).capture()

    assert run.payload_sha256 == payload_hash
    assert store.load(run.run_id).package == run.package
    assert run.manifest["request_count"] == 38
    assert run.manifest["logical_request_count"] == 38
    assert len(session.calls) == 38


def test_capture_manifest_distinguishes_http_attempts_from_logical_reads(tmp_path: Path) -> None:
    package, _payload_hash = _fixture_package()
    session = _FakeSheetsSession(package)
    session.flaky_range = P_GOOGL_RANGES[0]
    session.flaky_failures_left = 1
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path.parent / "service-account.json",
    )
    run = PGooglSheetsExporter(
        settings,
        FinancialModelPackageStore(tmp_path / "store"),
        session,
        sleeper=lambda _delay: None,
    ).capture()

    assert run.manifest["logical_request_count"] == 38
    assert run.manifest["request_count"] == 39
    assert len(session.calls) == 39


def test_exporter_fails_closed_on_source_change_failed_request_and_missing_range(
    tmp_path: Path,
) -> None:
    package, _payload_hash = _fixture_package()
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path.parent / "service-account.json",
    )

    changed = _FakeSheetsSession(package)
    changed.mutate_after_first_price = True
    with pytest.raises(PackageError, match="changed during capture"):
        PGooglSheetsExporter(
            settings,
            FinancialModelPackageStore(tmp_path / "changed"),
            changed,
            sleeper=lambda _delay: None,
        ).capture()

    failed = _FakeSheetsSession(package)
    failed.fail_range = P_GOOGL_RANGES[1]
    with pytest.raises(PackageError, match="HTTP 503"):
        PGooglSheetsExporter(
            settings,
            FinancialModelPackageStore(tmp_path / "failed"),
            failed,
            sleeper=lambda _delay: None,
        ).capture()

    missing = _FakeSheetsSession(package)
    missing.omit_range = P_GOOGL_RANGES[1]
    with pytest.raises(PackageError, match="omitted a requested grid range"):
        PGooglSheetsExporter(
            settings,
            FinancialModelPackageStore(tmp_path / "missing"),
            missing,
            sleeper=lambda _delay: None,
        ).capture()


def test_probability_diagnostic_writes_exact_evidence_privately_and_returns_only_summary(
    tmp_path: Path,
) -> None:
    package, _payload_hash = _fixture_package()
    session = _FakeSheetsSession(package)
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path.parent / "service-account.json",
    )
    store = FinancialModelPackageStore(tmp_path / "private-store")
    summary = PGooglSheetsExporter(
        settings,
        store,
        session,
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 10, 1, 12, tzinfo=UTC),
    ).diagnose_probabilities()

    reports = list(store.report_root.glob("probability-diagnostic-*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert summary["source_stable"] is True
    assert summary["sum_equals_one_exactly"] is True
    assert report["scenario_mapping"] == {"BEAR": "AO4", "BASE": "AO5", "BULL": "AO6"}
    assert Decimal(report["stable_exact_sum"]) == Decimal(1)
    assert report["normalization_applied"] is False
    assert report["first_read"] == report["second_read"]
    assert len(session.calls) == 6
    assert set(summary) == {
        "status",
        "source_stable",
        "sum_equals_one_exactly",
        "all_values_match_parity_fixture",
        "all_formulas_match_parity_fixture",
        "private_report_written",
    }


def test_probability_diagnostic_fails_closed_when_values_change_between_reads(
    tmp_path: Path,
) -> None:
    package, _payload_hash = _fixture_package()
    session = _FakeSheetsSession(package)
    session.mutate_probability_on_first_read = True
    settings = Settings(
        google_sheets_spreadsheet_id=SYNTHETIC_SPREADSHEET_ID,
        google_sheets_service_account_file=tmp_path.parent / "service-account.json",
    )
    store = FinancialModelPackageStore(tmp_path / "private-store")
    summary = PGooglSheetsExporter(
        settings,
        store,
        session,
        sleeper=lambda _delay: None,
        clock=lambda: datetime(2026, 10, 1, 12, tzinfo=UTC),
    ).diagnose_probabilities()

    report = json.loads(next(store.report_root.glob("probability-diagnostic-*.json")).read_text())
    assert summary["source_stable"] is False
    assert report["status"] == "SOURCE_CHANGED"
    assert report["stable_exact_sum"] is None
    assert report["stable_delta_from_one"] is None


def _package_with_probabilities(
    package: FinancialModelPackage,
    probabilities: tuple[Decimal | None, Decimal | None, Decimal | None],
    *,
    percent_format: bool = False,
) -> FinancialModelPackage:
    source_cells = dict(package.source_cells)
    for address, value in zip(("AO4", "AO5", "AO6"), probabilities, strict=True):
        cell = source_cells[address]
        if value is None:
            source_cells[address] = cell.model_copy(
                update={"effective_value": None, "state": "BLANK"}
            )
            continue
        assert cell.effective_value is not None
        decimal_text = format(value, "f")
        source_cells[address] = cell.model_copy(
            update={
                "effective_value": cell.effective_value.model_copy(update={"value": decimal_text}),
                "number_format_type": "PERCENT" if percent_format else cell.number_format_type,
                "number_format_pattern": "0.00%" if percent_format else cell.number_format_pattern,
            }
        )
    return package.model_copy(update={"source_cells": source_cells})


def _rebuild_package_with_source_cells(
    package: FinancialModelPackage, source_cells: dict[str, PackageCell]
) -> FinancialModelPackage:
    return _package_from_cells(
        source_metadata={
            "source_identity_sha256": package.source.source_identity_sha256,
            "modified_time": package.source.modified_time,
            "head_revision_id": package.source.drive_revision_id,
            "checksum": package.source.drive_checksum,
        },
        structure={
            "sheet_id": package.source.sheet_id,
            "time_zone": package.source.spreadsheet_time_zone,
        },
        source_cells=source_cells,
        captured_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
    )


def _effective_probability(package: FinancialModelPackage, address: str) -> Decimal:
    value = package.source_cells[address].effective_value
    assert value is not None and value.kind == "NUMBER"
    return Decimal(value.value)


def test_native_scenario_probability_contract_keeps_exact_sum_and_bear_base_bull_order() -> None:
    package, payload_hash = _fixture_package()
    mapped = _mapped_model(package, payload_hash, datetime(2026, 10, 1, tzinfo=UTC))

    assert [scenario.scenario.value for scenario in mapped.values.scenarios] == [
        "BEAR",
        "BASE",
        "BULL",
    ]
    assert [scenario.probability for scenario in mapped.values.scenarios] == [
        _effective_probability(package, address) for address in ("AO4", "AO5", "AO6")
    ]
    assert sum((scenario.probability for scenario in mapped.values.scenarios), Decimal(0)) == 1


@pytest.mark.parametrize(
    "percent_format",
    [
        False,
        True,
    ],
)
def test_probability_mapping_does_not_apply_display_percent_conversion(
    percent_format: bool,
) -> None:
    package, payload_hash = _fixture_package()
    probabilities = (
        _effective_probability(package, "AO4"),
        _effective_probability(package, "AO5"),
        _effective_probability(package, "AO6"),
    )
    package = _package_with_probabilities(package, probabilities, percent_format=percent_format)

    mapped = _mapped_model(package, payload_hash, datetime(2026, 10, 1, tzinfo=UTC))

    assert [scenario.probability for scenario in mapped.values.scenarios] == list(probabilities)


def test_probability_contract_rejects_material_sum_deviation() -> None:
    package, payload_hash = _fixture_package()
    package = _package_with_probabilities(
        package, (Decimal("0.2"), Decimal("0.5"), Decimal("0.31"))
    )

    with pytest.raises(PackageError, match="serialization bound"):
        _mapped_model(package, payload_hash, datetime(2026, 10, 1, tzinfo=UTC))


def test_probability_contract_rejects_missing_probability_without_coercing_to_zero() -> None:
    package, payload_hash = _fixture_package()
    package = _package_with_probabilities(package, (Decimal("0.2"), None, Decimal("0.3")))

    with pytest.raises((PackageError, ValueError)):
        _mapped_model(package, payload_hash, datetime(2026, 10, 1, tzinfo=UTC))


def test_probability_contract_does_not_infer_percent_units_from_display_format() -> None:
    package, payload_hash = _fixture_package()
    package = _package_with_probabilities(
        package,
        (Decimal("20"), Decimal("50"), Decimal("30")),
        percent_format=True,
    )

    with pytest.raises(PackageError, match="fractions from zero through one"):
        _mapped_model(package, payload_hash, datetime(2026, 10, 1, tzinfo=UTC))


def test_probability_contract_rejects_negative_values_and_unexpected_units() -> None:
    package, payload_hash = _fixture_package()
    negative = _package_with_probabilities(
        package, (Decimal("-0.01"), Decimal("0.71"), Decimal("0.3"))
    )
    with pytest.raises(PackageError, match="fractions from zero through one"):
        _mapped_model(negative, payload_hash, datetime(2026, 10, 1, tzinfo=UTC))

    source_cells = dict(package.source_cells)
    source_cells["AO4"] = source_cells["AO4"].model_copy(
        update={"number_format_type": "NUMBER", "number_format_pattern": "0.00"}
    )
    untyped = package.model_copy(update={"source_cells": source_cells})
    with pytest.raises(PackageError, match="declared percent display format"):
        _mapped_model(untyped, payload_hash, datetime(2026, 10, 1, tzinfo=UTC))


@pytest.mark.parametrize(
    "residual",
    [Decimal("0.00000000000000002"), Decimal("-0.00000000000000002")],
)
def test_tiny_serialization_residual_is_closed_on_base_and_preserved_for_replay(
    tmp_path: Path, residual: Decimal
) -> None:
    package, _payload_hash = _fixture_package()
    raw = tuple(_effective_probability(package, address) for address in ("AO4", "AO5", "AO6"))
    adjusted_source = _package_with_probabilities(package, (raw[0], raw[1] - residual, raw[2]))
    source_cells = dict(adjusted_source.source_cells)

    first = _rebuild_package_with_source_cells(package, source_cells)
    replay = _rebuild_package_with_source_cells(package, source_cells)
    evidence = first.probability_normalization
    assert evidence is not None
    assert evidence.method == "BASE_RESIDUAL_V1"
    assert evidence.adjusted_scenario == "BASE"
    assert evidence.residual_to_one == residual
    assert evidence.base_adjustment == residual
    assert evidence.original_probabilities.base == raw[1] - residual
    assert evidence.normalized_probabilities.base == raw[1]
    assert first.source_cells["AO5"].effective_value is not None
    assert first.source_cells["AO5"].effective_value.value == format(raw[1] - residual, "f")
    assert first.inputs.scenarios[1].probability == raw[1]
    assert sum((row.probability for row in first.inputs.scenarios), Decimal(0)) == Decimal(1)
    assert first.model_dump(mode="json") == replay.model_dump(mode="json")
    assert first.revision.input_sha256 == replay.revision.input_sha256

    payload_hash = hashlib.sha256(
        _strict_json(first.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()
    store = FinancialModelPackageStore(tmp_path / "store")
    captured = store.capture(
        first,
        captured_at=datetime(2026, 10, 1, tzinfo=UTC),
        request_count=0,
        logical_request_count=0,
    )
    replayed = store.load(captured.run_id, payload_hash)
    assert replayed.package == first
    validated = validate_financial_model_package(replayed.package, payload_hash)
    assert validated.mapped_model.values.scenarios[1].probability == raw[1]
    assert validated.parity_report["probability_input_comparison"]["normalization_applied"]
    assert validated.parity_report["status"] == "PARITY_PASS"
    assert validated.parity_report["projection_reconciliation"]["passed"] == 30
    assert validated.parity_report["output_reconciliation"]["passed"] == 22


def test_live_probability_drift_is_reported_as_a_new_source_revision_not_hidden_by_closure() -> (
    None
):
    package, _payload_hash = _fixture_package()
    raw = tuple(_effective_probability(package, address) for address in ("AO4", "AO5", "AO6"))
    drift = Decimal("0.00000000001")
    changed = _package_with_probabilities(package, (raw[0] + drift, raw[1] - drift, raw[2]))
    proposed = _rebuild_package_with_source_cells(package, dict(changed.source_cells))
    payload_hash = hashlib.sha256(
        _strict_json(proposed.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()

    validated = validate_financial_model_package(proposed, payload_hash)

    assert proposed.probability_normalization is None
    assert proposed.revision.input_sha256 != package.revision.input_sha256
    comparison = validated.parity_report["probability_input_comparison"]
    assert comparison["status"] == "PROPOSED_SOURCE_REVISION"
    assert validated.parity_report["status"] == "PARITY_PASS"
    assert comparison["scenarios"]["BEAR"]["formula_matches_parity_fixture"] is True
    assert comparison["scenarios"]["BASE"]["formula_matches_parity_fixture"] is True
    assert comparison["scenarios"]["BEAR"]["status"] == "SOURCE_INPUT_DIFFERS_FROM_PARITY_FIXTURE"
    assert comparison["scenarios"]["BASE"]["status"] == "SOURCE_INPUT_DIFFERS_FROM_PARITY_FIXTURE"
    assert comparison["scenarios"]["BULL"]["status"] == "EXACT_MATCH"


def _add_exact_company(session: Session) -> Company:
    company = Company(name="Alphabet", reporting_currency="USD", is_demo=False)
    session.add(company)
    session.flush()
    security = Security(
        company_id=company.id,
        name="Alphabet common stock",
        security_type="COMMON_STOCK",
        is_demo=False,
    )
    session.add(security)
    session.flush()
    session.add(
        Listing(
            security_id=security.id,
            ticker="GOOGL",
            venue="NASDAQ",
            currency="USD",
            is_demo=False,
        )
    )
    session.flush()
    return company


@pytest.mark.integration
def test_import_is_idempotent_and_preserves_package_revision_provenance(
    postgres_engine: Engine,
) -> None:
    package, payload_hash = _fixture_package()
    accepted_at = datetime(2026, 10, 1, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        _add_exact_company(session)
        first = accept_financial_model_package(
            session, package, payload_hash, accepted_at=accepted_at
        )
        replay = accept_financial_model_package(
            session, package, payload_hash, accepted_at=accepted_at
        )
        assert first["status"] == "ACCEPTED"
        assert replay["status"] == "ALREADY_ACCEPTED"
        assert first["source_revision_id"] == package.revision.external_revision_id
        assert first["methodology_version"] == "ufcf-dcf-fade-v1"
        assert first["effective_at"] == accepted_at.isoformat()
        revision_count = session.scalar(select(func.count()).select_from(FinancialModelRevision))
        model_count = session.scalar(select(func.count()).select_from(FinancialModel))
        assert revision_count == 1
        assert model_count == 1
        revision = session.get(FinancialModelRevision, UUID(first["revision_id"]))
        assert revision is not None
        assert revision.source is not None
        assert payload_hash in revision.source
        output = session.scalar(
            select(FinancialModelOutput).where(FinancialModelOutput.revision_id == revision.id)
        )
        assert output is not None
        methodology = session.get(ReturnMethodologyDefinition, output.return_methodology_id)
        assert methodology is not None
        assert methodology.code == "UFCF_ENTERPRISE_IRR"


@pytest.mark.integration
def test_import_transaction_rollback_leaves_no_model_revision(postgres_engine: Engine) -> None:
    package, payload_hash = _fixture_package()
    with (
        pytest.raises(RuntimeError, match="synthetic rollback"),
        Session(postgres_engine) as session,
        session.begin(),
    ):
        _add_exact_company(session)
        accepted = accept_financial_model_package(
            session,
            package,
            payload_hash,
            accepted_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
        assert accepted["status"] == "ACCEPTED"
        raise RuntimeError("synthetic rollback")
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(FinancialModel)) == 0
        assert session.scalar(select(func.count()).select_from(FinancialModelRevision)) == 0


@pytest.mark.integration
def test_package_with_base_revision_cannot_create_a_missing_canonical_model(
    postgres_engine: Engine,
) -> None:
    from portfolio_api.financial_model_package import preview_financial_model_package_import

    package, _payload_hash = _fixture_package()
    package = package.model_copy(
        update={"revision": package.revision.model_copy(update={"base_revision_id": uuid4()})}
    )
    payload_hash = hashlib.sha256(
        _strict_json(package.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()
    with Session(postgres_engine) as session, session.begin():
        _add_exact_company(session)
        result = preview_financial_model_package_import(session, package, payload_hash)
    assert result["status"] == "BLOCKED_BASE_MODEL_MISSING"


@pytest.mark.integration
def test_model_identity_preview_is_read_only_and_reports_exact_scope(
    postgres_engine: Engine,
) -> None:
    from portfolio_api.domain.models import (
        CurrentLifecycle,
        ModelIdentityBootstrapReceipt,
        Portfolio,
    )
    from portfolio_api.model_identity_bootstrap import preview_model_identity_bootstrap

    package, payload_hash = _fixture_package()
    with Session(postgres_engine) as session, session.begin():
        result = preview_model_identity_bootstrap(session, package, payload_hash)
        assert result["status"] == "READY_TO_CREATE"
        assert result["read_only"] is True
        assert result["canonical_identity"] == {
            "company_name": "Alphabet",
            "canonical_ticker": "GOOGL",
            "company_reporting_currency": None,
            "security_name": "Alphabet",
            "security_type": "COMMON_STOCK",
            "share_class": None,
            "listing_venue": "NASDAQ",
            "listing_ticker": "GOOGL",
            "listing_currency": "USD",
            "model_currency": "USD",
        }
        assert result["records"] == {
            "companies": 1,
            "securities": 1,
            "listings": 1,
            "receipts": 1,
            "lifecycle_events": 0,
            "portfolios": 0,
            "holdings": 0,
            "cash_positions": 0,
            "target_revisions": 0,
            "financial_model_revisions": 0,
        }
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0
        assert session.scalar(select(func.count()).select_from(Security)) == 0
        assert session.scalar(select(func.count()).select_from(Listing)) == 0
        assert session.scalar(select(func.count()).select_from(ModelIdentityBootstrapReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(CurrentLifecycle)) == 0
        assert session.scalar(select(func.count()).select_from(Portfolio)) == 0


@pytest.mark.integration
def test_model_identity_preview_reports_receipt_migration_as_apply_dependency(
    postgres_engine: Engine,
) -> None:
    from sqlalchemy import text

    from portfolio_api.model_identity_bootstrap import preview_model_identity_bootstrap

    package, payload_hash = _fixture_package()
    with postgres_engine.begin() as connection:
        connection.execute(text("DROP TABLE model_identity_bootstrap_receipts"))
    with Session(postgres_engine) as session:
        result = preview_model_identity_bootstrap(session, package, payload_hash)

    assert result["status"] == "READY_TO_CREATE"
    assert result["receipt_schema_available"] is False
    assert result["apply_available"] is False
    records = result["records"]
    changes = result["changes"]
    assert isinstance(records, dict) and records["receipts"] == 1
    assert isinstance(changes, dict) and changes["receipt"] == "CREATE_REQUIRES_MIGRATION"
    from portfolio_api.model_identity_bootstrap import (
        ModelIdentityBootstrapError,
        apply_model_identity_bootstrap,
    )

    with (
        Session(postgres_engine) as session,
        session.begin(),
        pytest.raises(ModelIdentityBootstrapError, match="receipt migration"),
    ):
        apply_model_identity_bootstrap(
            session,
            package,
            payload_hash,
            observed_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
        )


@pytest.mark.integration
def test_model_identity_bootstrap_is_idempotent_and_enables_package_preview(
    postgres_engine: Engine,
) -> None:
    from portfolio_api.domain.models import (
        CurrentLifecycle,
        HoldingSnapshot,
        ModelIdentityBootstrapReceipt,
        Portfolio,
    )
    from portfolio_api.financial_model_package import preview_financial_model_package_import
    from portfolio_api.model_identity_bootstrap import (
        P_GOOGL_IDENTITY_MAPPING,
        apply_model_identity_bootstrap,
    )

    package, payload_hash = _fixture_package()
    captured_at = datetime(2026, 10, 1, 12, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        first = apply_model_identity_bootstrap(
            session, package, payload_hash, observed_at=captured_at
        )
        replay = apply_model_identity_bootstrap(
            session, package, payload_hash, observed_at=captured_at
        )
        package_preview = preview_financial_model_package_import(session, package, payload_hash)

        assert first["status"] == "APPLIED"
        assert replay["status"] == "ALREADY_APPLIED"
        assert first["canonical_ids"] == {
            "company_id": str(P_GOOGL_IDENTITY_MAPPING.company_id),
            "security_id": str(P_GOOGL_IDENTITY_MAPPING.security_id),
            "listing_id": str(P_GOOGL_IDENTITY_MAPPING.listing_id),
        }
        assert package_preview["status"] == "READY_FOR_EXPLICIT_ACCEPTANCE"
        assert session.scalar(select(func.count()).select_from(Company)) == 1
        assert session.scalar(select(func.count()).select_from(Security)) == 1
        assert session.scalar(select(func.count()).select_from(Listing)) == 1
        assert session.scalar(select(func.count()).select_from(ModelIdentityBootstrapReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(CurrentLifecycle)) == 0
        assert session.scalar(select(func.count()).select_from(Portfolio)) == 0
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == 0
        assert session.scalar(select(func.count()).select_from(FinancialModelRevision)) == 0


@pytest.mark.integration
def test_model_identity_bootstrap_conflicts_on_deterministic_id_mismatch(
    postgres_engine: Engine,
) -> None:
    from portfolio_api.model_identity_bootstrap import (
        P_GOOGL_IDENTITY_MAPPING,
        ModelIdentityConflict,
        preview_model_identity_bootstrap,
    )

    package, payload_hash = _fixture_package()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            Company(
                id=P_GOOGL_IDENTITY_MAPPING.company_id,
                name="Unrelated issuer",
                is_demo=False,
            )
        )
    with Session(postgres_engine) as session:
        with pytest.raises(ModelIdentityConflict, match="different identity"):
            preview_model_identity_bootstrap(session, package, payload_hash)
        assert session.scalar(select(func.count()).select_from(Security)) == 0
        assert session.scalar(select(func.count()).select_from(Listing)) == 0


@pytest.mark.integration
def test_model_identity_bootstrap_rolls_back_identity_and_receipt_together(
    postgres_engine: Engine,
) -> None:
    from portfolio_api.domain.models import ModelIdentityBootstrapReceipt
    from portfolio_api.model_identity_bootstrap import apply_model_identity_bootstrap

    package, payload_hash = _fixture_package()
    with (
        pytest.raises(RuntimeError, match="synthetic rollback"),
        Session(postgres_engine) as session,
        session.begin(),
    ):
        apply_model_identity_bootstrap(
            session,
            package,
            payload_hash,
            observed_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
        )
        raise RuntimeError("synthetic rollback")
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0
        assert session.scalar(select(func.count()).select_from(Security)) == 0
        assert session.scalar(select(func.count()).select_from(Listing)) == 0
        assert session.scalar(select(func.count()).select_from(ModelIdentityBootstrapReceipt)) == 0


@pytest.mark.integration
def test_model_identity_receipt_is_append_only(postgres_engine: Engine) -> None:
    from portfolio_api.domain.models import ModelIdentityBootstrapReceipt
    from portfolio_api.model_identity_bootstrap import apply_model_identity_bootstrap

    package, payload_hash = _fixture_package()
    with Session(postgres_engine) as session, session.begin():
        apply_model_identity_bootstrap(
            session,
            package,
            payload_hash,
            observed_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
        )
    with Session(postgres_engine) as session:
        receipt = session.scalar(select(ModelIdentityBootstrapReceipt))
        assert receipt is not None
        receipt.status = "REWRITTEN"
        with pytest.raises(ValueError, match="Historical observations are append-only"):
            session.flush()
        session.rollback()
    with Session(postgres_engine) as session:
        receipt = session.scalar(select(ModelIdentityBootstrapReceipt))
        assert receipt is not None
        assert receipt.status == "APPLIED"


def test_model_identity_mapping_rejects_an_unrelated_package_company() -> None:
    from portfolio_api.model_identity_bootstrap import (
        ModelIdentityBootstrapError,
        _validated_input,
    )

    package, payload_hash = _fixture_package()
    unrelated_identity = package.identity.model_copy(update={"company_name": "Unrelated issuer"})
    unrelated_package = package.model_copy(update={"identity": unrelated_identity})
    unrelated_hash = hashlib.sha256(
        _strict_json(unrelated_package.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ModelIdentityBootstrapError, match="explicit P-GOOGL canonical mapping"):
        _validated_input(unrelated_package, unrelated_hash)


def test_model_identity_read_only_preview_accepts_only_known_schema_heads() -> None:
    from portfolio_api.model_identity_bootstrap import (
        ModelIdentityBootstrapError,
        validate_identity_preview_heads,
    )

    validate_identity_preview_heads({"6c2eaf0b8147"})
    validate_identity_preview_heads({"3e5c8a1d7b42"})
    with pytest.raises(ModelIdentityBootstrapError, match="reviewed canonical schema revisions"):
        validate_identity_preview_heads({"unknown_head"})
    with pytest.raises(ModelIdentityBootstrapError, match="reviewed canonical schema revisions"):
        validate_identity_preview_heads({"6c2eaf0b8147", "3e5c8a1d7b42"})
