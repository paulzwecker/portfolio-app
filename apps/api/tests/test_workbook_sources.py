"""Private workbook acquisition tests use only generated XLSX bytes and mocked Drive responses."""

from __future__ import annotations

import hashlib
import io
import json
import os
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO, cast
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from portfolio_api.workbook_sources import (
    DRIVE_FILES_API,
    GOOGLE_SHEET_MIME,
    MARKET_DATA_PROFILE,
    PORTFOLIO_PROFILE,
    XLSX_MIME,
    AcquiredBytes,
    GoogleDriveWorkbookReader,
    SnapshotStore,
    WorkbookSourceError,
    _read_operator_file,
    acquire_snapshot,
    inspect_workbook,
    load_google_drive_reader,
)


def _worksheet_xml(cells: dict[str, tuple[str, str]]) -> str:
    rows: dict[int, list[str]] = {}
    for address, (cell_type, value) in cells.items():
        row_number = int("".join(character for character in address if character.isdigit()))
        if cell_type == "formula":
            node = f'<c r="{address}"><f>{escape(value)}</f><v>2</v></c>'
        elif cell_type == "shared":
            node = f'<c r="{address}" t="s"><v>{escape(value)}</v></c>'
        else:
            node = f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        rows.setdefault(row_number, []).append(node)
    row_xml = "".join(
        f'<row r="{row}">{"".join(row_cells)}</row>' for row, row_cells in sorted(rows.items())
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<dimension ref="A1:Z20"/><sheetData>'
        f"{row_xml}</sheetData></worksheet>"
    )


def _xlsx(
    names: tuple[str, ...],
    *,
    extra_name: str | None = None,
    header: str = "Synthetic header",
    formula: bool = True,
    date1904: bool = False,
    defined_name: str | None = None,
    defined_name_ref: str = "'Universe Registry'!$A$1",
    data_marker: str = "Synthetic body value",
    empty_sheets: tuple[str, ...] = (),
    invalid_shared_string: bool = False,
) -> bytes:
    all_names = (*names, *((extra_name,) if extra_name else ()))
    sheet_nodes = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(all_names, start=1)
    )
    defined_names = (
        f'<definedNames><definedName name="{escape(defined_name)}">'
        f"{escape(defined_name_ref)}</definedName></definedNames>"
        if defined_name
        else ""
    )
    date_attribute = ' date1904="1"' if date1904 else ""
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<workbookPr{date_attribute}/><sheets>{sheet_nodes}</sheets>{defined_names}</workbook>"
    )
    relation_nodes = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index, _name in enumerate(all_names, start=1)
    )
    relationships_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{relation_nodes}</Relationships>"
    )
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships_xml)
        for index, name in enumerate(all_names, start=1):
            cells = {} if name in empty_sheets else {"A4": ("inline", header)}
            if name == "Model Contract":
                cells["A5"] = ("inline", "Contract v1")
            if formula and name.startswith("P-"):
                cells["B2"] = ("formula", "1+1")
            if name in {"P-DEMO", "Listings"}:
                cells["C7"] = ("inline", data_marker)
            if invalid_shared_string:
                cells["D9"] = ("shared", "9")
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(cells))
        if invalid_shared_string:
            archive.writestr(
                "xl/sharedStrings.xml",
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<si><t>Only one shared string</t></si></sst>",
            )
    return output.getvalue()


def _complete_profile_xlsx(
    *, extra_name: str | None = "Operator Notes", header: str = "Synthetic header"
) -> bytes:
    return _xlsx(
        PORTFOLIO_PROFILE.required_sheets + ("P-DEMO", "W-DEMO"),
        extra_name=extra_name,
        header=header,
        date1904=True,
        defined_name="synthetic_name",
    )


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        payload: dict[str, Any] | None = None,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.body = body
        self.headers = headers or {}

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def iter_content(self, chunk_size: int = 65_536) -> Iterator[bytes]:
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        return self.responses.popleft()


def _drive_metadata(
    file_id: str,
    mime_type: str = GOOGLE_SHEET_MIME,
    md5_checksum: str | None = None,
) -> FakeResponse:
    return FakeResponse(
        payload={
            "id": file_id,
            "mimeType": mime_type,
            "headRevisionId": "synthetic-revision-7",
            "modifiedTime": "2026-10-19T12:00:00Z",
            **({"md5Checksum": md5_checksum} if md5_checksum is not None else {}),
            "size": "1234",
        }
    )


def test_generated_portfolio_workbook_validates_and_preserves_original_bytes(
    tmp_path: Path,
) -> None:
    data = _complete_profile_xlsx()
    inventory = inspect_workbook(data, PORTFOLIO_PROFILE)
    store = SnapshotStore(tmp_path / "private-snapshots")
    manifest = acquire_snapshot(
        store=store,
        profile=PORTFOLIO_PROFILE,
        source_identity="test-drive-source-id-never-written-plain",
        fetch=lambda: AcquiredBytes(
            data=data,
            method="operator_supplied_xlsx",
            source_revision=None,
            source_modified_at=None,
            source_checksum=None,
            source_mime_type=XLSX_MIME,
        ),
    )

    stored = store.root / manifest["blob_path"]
    manifest_path = store.run_root / f"{manifest['run_id']}.json"
    serialized_manifest = manifest_path.read_text(encoding="utf-8")
    assert stored.read_bytes() == data
    assert manifest["status"] == "ACQUIRED_REVIEW_REQUIRED"
    assert manifest["schema_state"] == "UNBASELINED"
    assert manifest["review_required"] is True
    assert manifest["import_triggered"] is False
    assert manifest["artifact_sha256"] == hashlib.sha256(data).hexdigest()
    assert manifest["schema_fingerprint"] == inventory.schema_fingerprint
    assert manifest["inventory"]["date_system"] == "1904"
    assert "P-DEMO" in manifest["inventory"]["sheet_names"]
    model_tab = next(
        item for item in manifest["inventory"]["sheet_metrics"] if item["name"] == "P-DEMO"
    )
    assert model_tab["formula_cell_count"] == 1
    assert "synthetic_name" in serialized_manifest
    assert "test-drive-source-id-never-written-plain" not in serialized_manifest


def test_schema_acceptance_requires_the_reviewed_hash_and_keeps_acquisition_immutable(
    tmp_path: Path,
) -> None:
    data = _complete_profile_xlsx()
    digest = hashlib.sha256(data).hexdigest()
    store = SnapshotStore(tmp_path / "private-snapshots")
    acquired = acquire_snapshot(
        store=store,
        profile=PORTFOLIO_PROFILE,
        source_identity="operator-supplied:portfolio",
        fetch=lambda: AcquiredBytes(data, "operator_supplied_xlsx", None, None, None, XLSX_MIME),
    )
    original_manifest_path = store.run_root / f"{acquired['run_id']}.json"
    original_manifest = original_manifest_path.read_bytes()

    with pytest.raises(WorkbookSourceError, match="does not match"):
        store.accept_schema_baseline(acquired["run_id"], "0" * 64)

    accepted = store.accept_schema_baseline(acquired["run_id"], digest)
    assert accepted["status"] == "SCHEMA_BASELINE_ACCEPTED"
    assert accepted["parent_run_id"] == acquired["run_id"]
    assert accepted["import_triggered"] is False
    assert original_manifest_path.read_bytes() == original_manifest


def test_manifest_run_ids_are_create_once_and_cannot_overwrite_existing_records(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(tmp_path / "private-snapshots")
    manifest = {"run_id": "a" * 32, "status": "FIRST"}
    original_path = store._write_manifest(manifest)
    original_bytes = original_path.read_bytes()

    with pytest.raises(WorkbookSourceError, match="run identifier already exists"):
        store._write_manifest({"run_id": "a" * 32, "status": "REPLACEMENT"})

    assert original_path.read_bytes() == original_bytes


def test_schema_review_gate_requires_a_matching_digest_and_keeps_manifests_immutable(
    tmp_path: Path,
) -> None:
    data = _complete_profile_xlsx()
    digest = hashlib.sha256(data).hexdigest()
    store = SnapshotStore(tmp_path / "private-snapshots")
    source = "google-drive:synthetic-drive-id-01"

    first = acquire_snapshot(
        store=store,
        profile=PORTFOLIO_PROFILE,
        source_identity=source,
        fetch=lambda: AcquiredBytes(
            data, "google_drive_xlsx_export", "rev-1", None, None, GOOGLE_SHEET_MIME
        ),
    )
    accepted = store.accept_schema_baseline(first["run_id"], digest)
    assert first["status"] == "ACQUIRED_REVIEW_REQUIRED"
    assert accepted["status"] == "SCHEMA_BASELINE_ACCEPTED"
    assert accepted["schema_baseline_accepted"] is True
    assert accepted["previous_accepted_run_id"] is None
    assert first["run_id"] != accepted["run_id"]
    assert len(list(store.run_root.glob("*.json"))) == 2

    changed_schema = _complete_profile_xlsx(extra_name="New Workbook Tab")
    drifted = acquire_snapshot(
        store=store,
        profile=PORTFOLIO_PROFILE,
        source_identity=source,
        fetch=lambda: AcquiredBytes(
            changed_schema, "google_drive_xlsx_export", "rev-2", None, None, GOOGLE_SHEET_MIME
        ),
    )
    assert drifted["schema_state"] == "DRIFTED"
    assert drifted["status"] == "ACQUIRED_REVIEW_REQUIRED"
    assert drifted["schema_baseline_accepted"] is False

    changed_hash = hashlib.sha256(changed_schema).hexdigest()
    drift_accepted = store.accept_schema_baseline(drifted["run_id"], changed_hash)
    assert drift_accepted["status"] == "SCHEMA_BASELINE_ACCEPTED"
    assert drift_accepted["schema_state"] == "DRIFTED"
    assert drift_accepted["previous_accepted_run_id"] == accepted["run_id"]
    assert len(list(store.run_root.glob("*.json"))) == 4
    assert len(list(store.blob_root.glob("*/workbook.xlsx"))) == 2


def test_changed_content_with_same_schema_is_versioned_and_deduplicated(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-snapshots")
    source = "operator-supplied:market-data"
    baseline_data = _xlsx(MARKET_DATA_PROFILE.required_sheets)
    baseline = acquire_snapshot(
        store=store,
        profile=MARKET_DATA_PROFILE,
        source_identity=source,
        fetch=lambda: AcquiredBytes(
            baseline_data, "operator_supplied_xlsx", None, None, None, XLSX_MIME
        ),
    )
    baseline_hash = hashlib.sha256(baseline_data).hexdigest()
    accepted_baseline = store.accept_schema_baseline(baseline["run_id"], baseline_hash)
    changed_data = _xlsx(
        MARKET_DATA_PROFILE.required_sheets,
        data_marker="Changed synthetic data value",
    )
    changed = acquire_snapshot(
        store=store,
        profile=MARKET_DATA_PROFILE,
        source_identity=source,
        fetch=lambda: AcquiredBytes(
            changed_data, "operator_supplied_xlsx", None, None, None, XLSX_MIME
        ),
    )
    replay = acquire_snapshot(
        store=store,
        profile=MARKET_DATA_PROFILE,
        source_identity=source,
        fetch=lambda: AcquiredBytes(
            changed_data, "operator_supplied_xlsx", None, None, None, XLSX_MIME
        ),
    )
    assert baseline["status"] == "ACQUIRED_REVIEW_REQUIRED"
    assert accepted_baseline["status"] == "SCHEMA_BASELINE_ACCEPTED"
    assert changed["schema_state"] == "UNCHANGED"
    assert changed["content_state"] == "CHANGED"
    assert changed["review_required"] is False
    assert changed["status"] == "ACQUIRED"
    assert replay["schema_state"] == "UNCHANGED"
    assert replay["content_state"] == "UNCHANGED"
    assert replay["status"] == "ACQUIRED"
    assert replay["blob_path"] == changed["blob_path"]
    assert len(list(store.blob_root.glob("*/workbook.xlsx"))) == 2


def test_wrong_hash_incomplete_and_corrupt_workbooks_fail_closed_without_blob(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(tmp_path / "private-snapshots")
    valid = _complete_profile_xlsx()
    mismatch = acquire_snapshot(
        store=store,
        profile=PORTFOLIO_PROFILE,
        source_identity="operator-supplied:portfolio",
        fetch=lambda: AcquiredBytes(valid, "operator_supplied_xlsx", None, None, None, XLSX_MIME),
        expected_sha256="0" * 64,
    )
    incomplete_data = _xlsx(
        tuple(name for name in PORTFOLIO_PROFILE.required_sheets if name != "Price Feed")
        + ("P-DEMO", "W-DEMO")
    )
    incomplete = acquire_snapshot(
        store=store,
        profile=PORTFOLIO_PROFILE,
        source_identity="operator-supplied:incomplete",
        fetch=lambda: AcquiredBytes(
            incomplete_data, "operator_supplied_xlsx", None, None, None, XLSX_MIME
        ),
    )
    corrupt = acquire_snapshot(
        store=store,
        profile=MARKET_DATA_PROFILE,
        source_identity="operator-supplied:corrupt",
        fetch=lambda: AcquiredBytes(
            b"not an xlsx", "operator_supplied_xlsx", None, None, None, XLSX_MIME
        ),
    )

    assert mismatch["error_code"] == "EXPECTED_SHA256_MISMATCH"
    assert incomplete["error_code"] == "WORKBOOK_CONTRACT_INCOMPLETE"
    assert "missing required sheet: Price Feed" in incomplete["diagnostics"]
    assert corrupt["error_code"] == "INVALID_XLSX"
    assert mismatch["import_triggered"] is False
    assert not list(store.blob_root.glob("*/workbook.xlsx"))
    assert len(list(store.run_root.glob("*.json"))) == 3


def test_present_but_empty_required_tab_is_an_incomplete_workbook() -> None:
    data = _xlsx(
        MARKET_DATA_PROFILE.required_sheets,
        empty_sheets=("Daily Prices",),
    )
    with pytest.raises(WorkbookSourceError) as error:
        inspect_workbook(data, MARKET_DATA_PROFILE)
    assert error.value.code == "WORKBOOK_CONTRACT_INCOMPLETE"
    assert error.value.diagnostics == ("required sheet is empty: Daily Prices",)


def test_shared_string_references_are_validated_across_all_rows() -> None:
    data = _xlsx(
        MARKET_DATA_PROFILE.required_sheets,
        invalid_shared_string=True,
    )
    with pytest.raises(WorkbookSourceError) as error:
        inspect_workbook(data, MARKET_DATA_PROFILE)
    assert error.value.code == "INVALID_SHARED_STRING_INDEX"
    assert "missing shared-string entry" in error.value.message


def test_defined_name_target_changes_are_detected_without_storing_the_reference() -> None:
    original = inspect_workbook(
        _xlsx(
            PORTFOLIO_PROFILE.required_sheets + ("P-DEMO", "W-DEMO"),
            defined_name="SyntheticRange",
            defined_name_ref="'Universe Registry'!$A$1",
        ),
        PORTFOLIO_PROFILE,
    )
    changed = inspect_workbook(
        _xlsx(
            PORTFOLIO_PROFILE.required_sheets + ("P-DEMO", "W-DEMO"),
            defined_name="SyntheticRange",
            defined_name_ref="'Universe Registry'!$B$1",
        ),
        PORTFOLIO_PROFILE,
    )
    assert original.schema_fingerprint != changed.schema_fingerprint
    assert original.defined_names[0][:2] == ("SyntheticRange", "global")
    assert original.defined_names[0][2] != changed.defined_names[0][2]


def test_drive_api_exports_native_sheet_and_records_only_safe_metadata() -> None:
    file_id = "synthetic-drive-file-1234"
    data = _complete_profile_xlsx()
    session = FakeSession(
        [_drive_metadata(file_id), FakeResponse(body=data), _drive_metadata(file_id)]
    )
    reader = GoogleDriveWorkbookReader(session, sleeper=lambda _delay: None)
    result = reader.acquire(file_id)

    assert result.data == data
    assert result.method == "google_drive_xlsx_export"
    assert result.source_revision == "synthetic-revision-7"
    assert result.source_modified_at == "2026-10-19T12:00:00Z"
    assert len(session.calls) == 3
    assert session.calls[0][0] == f"{DRIVE_FILES_API}/{file_id}"
    assert (
        session.calls[0][1]["params"]["fields"]
        == "id,mimeType,modifiedTime,headRevisionId,md5Checksum,size"
    )
    assert session.calls[1][0].endswith(f"/files/{file_id}/export")
    assert session.calls[1][1]["params"] == {"mimeType": XLSX_MIME}
    assert session.calls[2][0] == f"{DRIVE_FILES_API}/{file_id}"


def test_drive_api_downloads_uploaded_xlsx_and_retries_transient_failures() -> None:
    file_id = "synthetic-drive-file-5678"
    data = _xlsx(MARKET_DATA_PROFILE.required_sheets)
    delays: list[float] = []
    session = FakeSession(
        [
            FakeResponse(503, headers={"Retry-After": "1"}),
            _drive_metadata(
                file_id, XLSX_MIME, hashlib.md5(data, usedforsecurity=False).hexdigest()
            ),
            FakeResponse(body=data),
            _drive_metadata(
                file_id, XLSX_MIME, hashlib.md5(data, usedforsecurity=False).hexdigest()
            ),
        ]
    )
    reader = GoogleDriveWorkbookReader(session, sleeper=delays.append)
    result = reader.acquire(file_id)

    assert result.data == data
    assert result.method == "google_drive_xlsx_download"
    assert delays == [1.0]
    assert len(session.calls) == 4
    assert session.calls[2][1]["params"]["alt"] == "media"


def test_drive_identity_permission_retry_limit_and_response_body_are_sanitized() -> None:
    file_id = "synthetic-drive-file-9000"
    wrong_identity = FakeSession(
        [FakeResponse(payload={"id": "different-file-id", "mimeType": XLSX_MIME})]
    )
    with pytest.raises(WorkbookSourceError, match="different file identity"):
        GoogleDriveWorkbookReader(wrong_identity, sleeper=lambda _delay: None).acquire(file_id)

    denied = FakeSession([FakeResponse(403)])
    with pytest.raises(WorkbookSourceError, match="denied access") as error:
        GoogleDriveWorkbookReader(denied, sleeper=lambda _delay: None).acquire(file_id)
    assert "drive-file-9000" not in str(error.value)
    assert len(denied.calls) == 1

    exhausted = FakeSession([FakeResponse(429), FakeResponse(503), FakeResponse(503)])
    with pytest.raises(WorkbookSourceError, match="bounded retries"):
        GoogleDriveWorkbookReader(exhausted, sleeper=lambda _delay: None).acquire(file_id)
    assert len(exhausted.calls) == 3


def test_drive_download_size_limit_is_bounded() -> None:
    file_id = "synthetic-drive-file-3456"
    session = FakeSession([_drive_metadata(file_id), FakeResponse(body=b"123456")])
    reader = GoogleDriveWorkbookReader(session, max_bytes=5, sleeper=lambda _delay: None)
    with pytest.raises(WorkbookSourceError, match="acquisition limit"):
        reader.acquire(file_id)


def test_drive_file_change_during_transfer_is_rejected() -> None:
    file_id = "synthetic-drive-file-6789"
    data = _xlsx(MARKET_DATA_PROFILE.required_sheets)
    changed_metadata = _drive_metadata(file_id)
    assert changed_metadata._payload is not None
    changed_metadata._payload["modifiedTime"] = "2026-10-19T12:01:00Z"
    session = FakeSession([_drive_metadata(file_id), FakeResponse(body=data), changed_metadata])
    with pytest.raises(WorkbookSourceError, match="changed during acquisition"):
        GoogleDriveWorkbookReader(session, sleeper=lambda _delay: None).acquire(file_id)


def test_snapshot_store_and_local_source_reject_repository_paths(tmp_path: Path) -> None:
    with pytest.raises(WorkbookSourceError, match="outside the repository"):
        SnapshotStore(Path(__file__).resolve().parents[3] / ".private-workbook-snapshots")

    inventory = inspect_workbook(_xlsx(MARKET_DATA_PROFILE.required_sheets), MARKET_DATA_PROFILE)
    assert inventory.date_system == "1900"
    assert inventory.defined_names == ()
    assert inventory.hidden_sheet_names == ()


def test_operator_source_rejects_file_changes_during_bounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "Market Data.xlsx"
    source_path.write_bytes(_xlsx(MARKET_DATA_PROFILE.required_sheets))
    original_open = Path.open

    class ChangingStream:
        def __init__(self, stream: BinaryIO) -> None:
            self.stream = stream

        def __enter__(self) -> ChangingStream:
            self.stream.__enter__()
            return self

        def __exit__(self, *args: Any) -> bool | None:
            return self.stream.__exit__(*args)

        def fileno(self) -> int:
            return self.stream.fileno()

        def read(self, limit: int) -> bytes:
            result = self.stream.read(limit)
            source_path.write_bytes(result + b"changed")
            return result

    def open_with_change(path: Path, *args: Any, **kwargs: Any) -> Any:
        stream = original_open(path, *args, **kwargs)
        if path == source_path and args and args[0] == "rb":
            return ChangingStream(cast(BinaryIO, stream))
        return stream

    monkeypatch.setattr(Path, "open", open_with_change)
    with pytest.raises(WorkbookSourceError) as error:
        _read_operator_file(source_path)
    assert error.value.code == "SOURCE_FILE_CHANGED_DURING_ACQUISITION"


@pytest.mark.skipif(os.name == "nt", reason="POSIX credential mode bits only")
def test_google_credential_file_must_not_be_group_or_world_readable(tmp_path: Path) -> None:
    credential_path = tmp_path / "synthetic-service-account.json"
    credential_path.write_text('{"type":"synthetic"}', encoding="utf-8")
    credential_path.chmod(0o644)
    with pytest.raises(WorkbookSourceError, match="Restrict the Google credential file"):
        load_google_drive_reader(credential_path)


def test_drive_rejects_urls_and_non_workbook_file_types() -> None:
    reader = GoogleDriveWorkbookReader(FakeSession([]), sleeper=lambda _delay: None)
    with pytest.raises(WorkbookSourceError, match="file ID, not a URL"):
        reader.acquire("https://drive.google.com/spreadsheets/d/synthetic-id")

    file_id = "synthetic-drive-file-1111"
    unsupported = FakeSession(
        [FakeResponse(payload={"id": file_id, "mimeType": "application/pdf"})]
    )
    with pytest.raises(WorkbookSourceError, match="must be a Google spreadsheet"):
        GoogleDriveWorkbookReader(unsupported, sleeper=lambda _delay: None).acquire(file_id)


def test_cli_confirmation_is_required_before_any_acquisition(tmp_path: Path, capsys: Any) -> None:
    from portfolio_api.workbook_sources import main

    result = main(["acquire", "portfolio", "--store", str(tmp_path / "private")])
    captured = capsys.readouterr()
    assert result == 2
    assert "ACQUISITION_CONFIRMATION_REQUIRED" in captured.err
    assert not list((tmp_path / "private" / "runs").glob("*.json"))


def test_confirmed_operator_file_cli_only_acquires_a_private_snapshot(
    tmp_path: Path, capsys: Any
) -> None:
    from portfolio_api.workbook_sources import main

    source_path = tmp_path / "Portfolio_Watchlist.xlsx"
    data = _complete_profile_xlsx()
    source_path.write_bytes(data)
    store_path = tmp_path / "private-store"
    result = main(
        [
            "acquire",
            "portfolio",
            "--store",
            str(store_path),
            "--from-file",
            str(source_path),
            "--confirm-source-acquisition",
        ]
    )
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert result == 2
    assert summary["status"] == "ACQUIRED_REVIEW_REQUIRED"
    assert summary["import_triggered"] is False
    assert "Synthetic body value" not in captured.out
    assert "artifact_sha256" not in captured.out
    assert len(list((store_path / "runs").glob("*.json"))) == 1
    assert len(list((store_path / "blobs" / "sha256").glob("*/workbook.xlsx"))) == 1
