"""Synthetic tests for the minimal native-Sheets canonical bootstrap path."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from portfolio_api import legacy_import
from portfolio_api.domain.models import (
    CanonicalBootstrapRun,
    CashPosition,
    Company,
    HoldingPosition,
    LegacyImportBatch,
    Listing,
    Portfolio,
    Security,
    TargetAllocation,
    TargetRevision,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings
from portfolio_api.sheets_portfolio_vertical_slice import (
    SheetsPortfolioError,
    SheetsPortfolioReader,
    _contract_ranges,
    _effective,
    _json_value,
    _load_source_snapshot,
    _manifest_sha256,
    _MarketListing,
    _resolve_aux_listing,
    _validate_headers,
    _validate_snapshot_coverage,
    build_minimal_import_plan,
    preview_database,
)
from portfolio_api.workbook_sources import SnapshotStore

SOURCE_ID = "s" * 30


def _column_number(value: str) -> int:
    result = 0
    for character in value:
        result = result * 26 + ord(character) - 64
    return result


def _column_name(value: int) -> str:
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _wire(value: Any) -> bytes:
    """Serialize Decimal values as exact JSON number tokens, like the Sheets API."""

    def replace_decimals(item: Any) -> Any:
        if isinstance(item, Decimal):
            return {"__exact_decimal_token__": format(item, "f")}
        if isinstance(item, dict):
            return {key: replace_decimals(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace_decimals(child) for child in item]
        return item

    rendered = json.dumps(replace_decimals(value), separators=(",", ":"))
    rendered = re.sub(
        r'\{"__exact_decimal_token__":"(-?[0-9]+(?:\.[0-9]+)?)"\}',
        r"\1",
        rendered,
    )
    return rendered.encode("utf-8")


class _Response:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self.status_code = status
        self.headers: dict[str, str] = {}
        self.body = _wire(payload)
        self.closed = False

    def iter_content(self, chunk_size: int = 65536) -> Iterator[bytes]:
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index : index + chunk_size]

    def close(self) -> None:
        self.closed = True


class _FakeGoogleSession:
    def __init__(
        self,
        *,
        mutate_cell: tuple[str, int, int] | None = None,
        mutate_metadata: bool = False,
        truncated_range: bool = False,
        error_status: int | None = None,
    ) -> None:
        self.mutate_cell = mutate_cell
        self.mutate_metadata = mutate_metadata
        self.truncated_range = truncated_range
        self.error_status = error_status
        self.metadata_calls = 0
        self.range_calls: dict[str, int] = {}
        self.responses: list[_Response] = []
        self.values: dict[tuple[str, int, int], dict[str, Any]] = {
            ("Universe Registry", 4, 1): self._text("Ticker"),
            ("Universe Registry", 4, 2): self._text("Company"),
            ("Universe Registry", 5, 1): self._text("SYN"),
            ("Universe Registry", 5, 2): self._text("Synthetic Corporation"),
            ("Current Holdings", 4, 1): self._text("Type"),
            ("Current Holdings", 4, 2): self._text("Portfolio Ticker"),
            ("Current Holdings", 4, 4): self._text("Price Feed Ticker"),
            ("Current Holdings", 4, 5): self._text("Shares / Native Cash"),
            ("Current Holdings", 4, 7): self._text("Currency"),
            ("Current Holdings", 5, 1): self._text("stock"),
            ("Current Holdings", 5, 2): self._text("SYN"),
            ("Current Holdings", 5, 4): self._text("XNYS:SYN"),
            ("Current Holdings", 5, 5): self._number(Decimal("3.1250000001")),
            ("Current Holdings", 6, 1): self._text("cash component"),
            ("Current Holdings", 6, 5): self._number(Decimal("250.2500000001")),
            ("Current Holdings", 6, 7): self._text("USD"),
            ("Current Holdings", 4, 12): self._text("Portfolio total EUR"),
            ("Target Architecture", 4, 1): self._text("Ticker"),
            ("Target Architecture", 4, 4): self._text("Target Weight (EDIT HERE)"),
            ("Target Architecture", 5, 1): self._text("SYN"),
            ("Target Architecture", 5, 4): self._number(Decimal("0.4")),
            ("Target Architecture", 3, 16): self._number(Decimal("0.4")),
        }

    @staticmethod
    def _text(value: str) -> dict[str, Any]:
        return {
            "userEnteredValue": {"stringValue": value},
            "effectiveValue": {"stringValue": value},
            "effectiveFormat": {"numberFormat": {"type": "TEXT", "pattern": "@"}},
        }

    @staticmethod
    def _number(value: Decimal) -> dict[str, Any]:
        return {
            "userEnteredValue": {"numberValue": value},
            "effectiveValue": {"numberValue": value},
            "effectiveFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}},
        }

    def _structure(self) -> dict[str, Any]:
        rows = {
            "Universe Registry": (6, 2),
            "Current Holdings": (7, 12),
            "Target Architecture": (6, 16),
            "Price Feed": (6, 8),
        }
        return {
            "spreadsheetId": SOURCE_ID,
            "properties": {"timeZone": "Europe/Berlin"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": index,
                        "title": title,
                        "gridProperties": {"rowCount": row_count, "columnCount": columns},
                    }
                }
                for index, (title, (row_count, columns)) in enumerate(rows.items(), start=1)
            ],
        }

    def _grid(self, a1_range: str) -> dict[str, Any]:
        match = re.fullmatch(r"'([^']+)'!([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)", a1_range)
        assert match is not None
        sheet, first_col, first_row, last_col, last_row = match.groups()
        start_col, end_col = _column_number(first_col), _column_number(last_col)
        start_row, end_row = int(first_row), int(last_row)
        calls = self.range_calls.get(a1_range, 0) + 1
        self.range_calls[a1_range] = calls
        row_data: list[dict[str, Any]] = []
        for row in range(start_row, end_row + 1):
            values = []
            for column in range(start_col, end_col + 1):
                key = (sheet, row, column)
                cell = dict(self.values.get(key, {}))
                if self.mutate_cell == key and calls >= 2:
                    cell = self._text("CHANGED")
                values.append(cell)
            while values and not values[-1]:
                values.pop()
            row_data.append({"values": values} if values else {})
        while row_data and not row_data[-1].get("values"):
            row_data.pop()
        grid_range: dict[str, Any] = {
            "startRow": start_row - 1,
            "rowData": row_data,
        }
        if start_col > 1:
            grid_range["startColumn"] = start_col - 1
        if self.truncated_range and calls == 1:
            grid_range["rowData"] = "malformed"
        return {
            "spreadsheetId": SOURCE_ID,
            "sheets": [{"properties": {"title": sheet}, "data": [grid_range]}],
        }

    def get(self, url: str, *, params: dict[str, str], timeout: Any, stream: bool) -> _Response:
        assert timeout
        assert stream is True
        if url.startswith("https://www.googleapis.com/drive/v3/files/"):
            self.metadata_calls += 1
            modified = "2026-10-31T10:00:00Z"
            if self.mutate_metadata and self.metadata_calls >= 2:
                modified = "2026-10-31T10:01:00Z"
            response = _Response(
                {
                    "id": SOURCE_ID,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "modifiedTime": modified,
                    "headRevisionId": "revision-1",
                    "size": "1234",
                },
                status=self.error_status or 200,
            )
        elif params.get("ranges") is not None:
            response = _Response(self._grid(params["ranges"]), status=self.error_status or 200)
        else:
            response = _Response(self._structure(), status=self.error_status or 200)
        self.responses.append(response)
        return response


def _reader(tmp_path: Path, session: _FakeGoogleSession) -> SheetsPortfolioReader:
    settings = Settings(
        google_sheets_spreadsheet_id=SOURCE_ID,
        google_sheets_service_account_file=tmp_path / "service-account.json",
    )
    return SheetsPortfolioReader(settings, session, sleeper=lambda _seconds: None)


def _store(tmp_path: Path) -> SnapshotStore:
    return SnapshotStore(tmp_path / "private-snapshot-store")


def _cell_xml(address: str, value: str) -> str:
    return f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'


def _synthetic_market_xlsx(*, shared_strings: bool = False) -> bytes:
    cells = {
        "A5": "SYN",
        "B5": "Synthetic Corporation",
        "C5": "XNYS:SYN",
        "D5": "XNYS",
        "E5": "USD",
        "G5": "Common Stock",
        "K5": "READY",
    }
    rows: dict[int, list[str]] = {}
    for index, (address, value) in enumerate(cells.items()):
        row = int(re.sub(r"[^0-9]", "", address))
        node = (
            f'<c r="{address}" t="s"><v>{index}</v></c>'
            if shared_strings
            else _cell_xml(address, value)
        )
        rows.setdefault(row, []).append(node)
    row_xml = "".join(
        f'<row r="{row}">{"".join(nodes)}</row>' for row, nodes in sorted(rows.items())
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{row_xml}"
        "</sheetData></worksheet>"
    )
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Listings" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        if shared_strings:
            strings = "".join(f"<si><t>{escape(value)}</t></si>" for value in cells.values())
            archive.writestr(
                "xl/sharedStrings.xml",
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"{strings}</sst>",
            )
    return output.getvalue()


def _stub_approved_market_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, shared_strings: bool = False
) -> str:
    market_path = tmp_path / "approved-market-data.xlsx"
    market_bytes = _synthetic_market_xlsx(shared_strings=shared_strings)
    market_path.write_bytes(market_bytes)
    market_run_id = "c" * 32
    market_sha = hashlib.sha256(market_bytes).hexdigest()
    monkeypatch.setattr(
        "portfolio_api.sheets_portfolio_vertical_slice.resolve_approved_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(
            run_id=market_run_id,
            sha256=market_sha,
            schema_fingerprint="f" * 64,
            path=market_path,
        ),
    )
    return market_run_id


def test_effective_values_keep_blank_zero_formula_empty_error_and_exact_decimal_distinct() -> None:
    assert _effective({"effective_value": None, "user_entered_value": None}) == (
        "BLANK",
        None,
        None,
    )
    assert _effective(
        {"effective_value": None, "user_entered_value": {"formulaValue": '=IF(TRUE,"",1)'}}
    ) == ("FORMULA_EMPTY_RESULT", None, None)
    assert _effective({"effective_value": {"stringValue": ""}}) == ("EMPTY_STRING", "", "string")
    assert _effective({"effective_value": {"numberValue": {"decimal": "0"}}}) == (
        "NUMBER_ZERO",
        "0",
        "number",
    )
    assert _effective(
        {"effective_value": {"numberValue": {"decimal": "0.123456789012345678901"}}}
    ) == ("NUMBER", "0.123456789012345678901", "number")
    integer_number = _json_value({"numberValue": 1200})
    assert integer_number == {"numberValue": {"decimal": "1200"}}
    assert _effective({"effective_value": integer_number}) == ("NUMBER", "1200", "number")
    zero_number = _json_value({"numberValue": 0})
    assert zero_number == {"numberValue": {"decimal": "0"}}
    assert _effective({"effective_value": zero_number}) == ("NUMBER_ZERO", "0", "number")
    assert _effective({"effective_value": {"errorValue": {"type": "DIVIDE_BY_ZERO"}}}) == (
        "ERROR",
        "DIVIDE_BY_ZERO",
        "error",
    )


def test_integer_json_number_values_do_not_coerce_booleans_to_numbers() -> None:
    boolean_number = _json_value({"numberValue": True})
    assert boolean_number == {"numberValue": True}
    with pytest.raises(SheetsPortfolioError) as error:
        _effective({"effective_value": boolean_number})
    assert error.value.code == "SNAPSHOT_CELL_TYPE_INVALID"


@pytest.mark.parametrize(
    ("source_ticker", "source_listing", "holding_kind", "aux_row", "market_by_company", "key"),
    [
        (
            "SPYY",
            "XETR:SPYY",
            "etf",
            {"A5": "AUX", "B5": "SPYY ETF", "C5": "SPYY", "D5": "XETR:SPYY", "H5": "EUR"},
            {},
            "SPYY",
        ),
        (
            "TSM",
            "NYSE:TSM",
            "stock",
            {
                "A5": "AUX",
                "B5": "TSM ADR",
                "C5": "TSM-ADR",
                "D5": "NYSE:TSM",
                "H5": "USD",
            },
            {
                "TSM": [
                    _MarketListing(
                        legacy_import.ListingRow(
                            listing_key="TSM",
                            canonical_ticker="TSM",
                            security_key="TSM",
                            underlying_security_key=None,
                            name="Taiwan Semiconductor",
                            ticker="2330",
                            venue="XTAI",
                            currency="TWD",
                            security_type="COMMON",
                            share_class="COMMON",
                            source="synthetic approved listing",
                        ),
                        "XTAI:2330",
                        "2330",
                        "TSM",
                        "READY",
                        5,
                    )
                ]
            },
            "TSM-ADR",
        ),
    ],
)
def test_explicit_aux_listing_mappings_keep_security_and_currency_basis(
    tmp_path: Path,
    source_ticker: str,
    source_listing: str,
    holding_kind: str,
    aux_row: dict[str, str],
    market_by_company: dict[str, list[_MarketListing]],
    key: str,
) -> None:
    source_cells = {address: legacy_import.Cell(value, "str") for address, value in aux_row.items()}
    portfolio = legacy_import.Workbook(
        path=tmp_path / "synthetic-source.json",
        sha256="a" * 64,
        sheets={"Price Feed": source_cells},
    )

    listing, supporting, issue = _resolve_aux_listing(
        portfolio,
        source_ticker=source_ticker,
        source_listing=source_listing,
        holding_kind=holding_kind,
        market_by_company=market_by_company,
    )

    assert issue is None
    assert listing is not None
    assert listing.listing_key == key
    assert listing.currency == ("EUR" if key == "SPYY" else "USD")
    assert [item.listing_key for item in supporting] == ([] if key == "SPYY" else ["TSM"])


def test_stable_capture_is_frozen_hashed_and_replayable(tmp_path: Path) -> None:
    session = _FakeGoogleSession()
    reader = _reader(tmp_path, session)
    store = _store(tmp_path)
    captured = reader.capture(store)
    replayed = _load_source_snapshot(store, captured.run_id, captured.sha256)

    assert captured.sha256 == hashlib.sha256(captured.path.read_bytes()).hexdigest()
    assert captured.semantic_sha256 == captured.sha256
    assert replayed.bundle == captured.bundle
    assert captured.manifest["captured_state_is_transactional"] is False
    assert captured.manifest["manifest_sha256"] == _manifest_sha256(captured.manifest)
    assert all(response.closed for response in session.responses)
    numeric = next(
        item
        for item in captured.bundle["cells"]
        if (item["sheet"], item["row"], item["column"]) == ("Current Holdings", 5, "E")
    )
    assert numeric["effective_value"] == {"numberValue": {"decimal": "3.1250000001"}}


@pytest.mark.parametrize(
    ("session_kwargs", "expected_code"),
    [
        ({"mutate_cell": ("Universe Registry", 5, 2)}, "SOURCE_CHANGED_DURING_CAPTURE"),
        ({"mutate_metadata": True}, "SOURCE_CHANGED_DURING_CAPTURE"),
        ({"truncated_range": True}, "SHEETS_RANGE_INCOMPLETE"),
        ({"error_status": 400}, "GOOGLE_API_ERROR"),
    ],
)
def test_capture_fails_closed_on_unstable_or_incomplete_source(
    tmp_path: Path, session_kwargs: dict[str, Any], expected_code: str
) -> None:
    session = _FakeGoogleSession(**session_kwargs)
    with pytest.raises(SheetsPortfolioError) as error:
        _reader(tmp_path, session).capture(_store(tmp_path))
    assert error.value.code == expected_code
    if session_kwargs.get("truncated_range"):
        assert "'Universe Registry'!A4:B6" in str(error.value)
    assert not list((_store(tmp_path).root / "native-sheets-portfolio-v1" / "runs").glob("*.json"))


def test_capture_enforces_range_and_cell_limits_before_api_value_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _FakeGoogleSession()
    reader = _reader(tmp_path, session)
    structure = session._structure()
    dimensions = structure["sheets"]
    dimensions[0]["properties"]["gridProperties"]["rowCount"] = 5_001
    with pytest.raises(SheetsPortfolioError, match="row limit") as error:
        _contract_ranges(structure)
    assert error.value.code == "CAPTURE_ROW_LIMIT_EXCEEDED"

    monkeypatch.setattr("portfolio_api.sheets_portfolio_vertical_slice.MAX_CAPTURE_CELLS", 5)
    with pytest.raises(SheetsPortfolioError) as error:
        reader.capture(_store(tmp_path))
    assert error.value.code == "CAPTURE_CELL_LIMIT_EXCEEDED"
    assert not session.range_calls


def test_response_body_byte_limit_is_enforced_during_streaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _FakeGoogleSession()
    reader = _reader(tmp_path, session)
    monkeypatch.setattr("portfolio_api.sheets_portfolio_vertical_slice.MAX_RESPONSE_BYTES", 5)
    with pytest.raises(SheetsPortfolioError) as error:
        reader._get_json("https://example.test", {})
    assert error.value.code == "GOOGLE_RESPONSE_OVERSIZED"


def test_snapshot_manifest_provenance_is_integrity_checked(tmp_path: Path) -> None:
    store = _store(tmp_path)
    captured = _reader(tmp_path, _FakeGoogleSession()).capture(store)
    manifest_path = store.root / "native-sheets-portfolio-v1" / "runs" / f"{captured.run_id}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_revision"] = "different-revision"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SheetsPortfolioError) as error:
        _load_source_snapshot(store, captured.run_id, captured.sha256)
    assert error.value.code == "SNAPSHOT_MANIFEST_INVALID"


def test_snapshot_replay_checks_structure_fingerprint(tmp_path: Path) -> None:
    store = _store(tmp_path)
    captured = _reader(tmp_path, _FakeGoogleSession()).capture(store)
    replayed = _load_source_snapshot(store, captured.run_id, captured.sha256)
    replayed.bundle["structure"]["time_zone"] = "UTC"

    with pytest.raises(SheetsPortfolioError) as error:
        _validate_snapshot_coverage(replayed)
    assert error.value.code == "SNAPSHOT_STRUCTURE_HASH_MISMATCH"


@pytest.mark.parametrize("shared_strings", [False, True])
def test_minimal_projection_reuses_existing_canonical_import_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shared_strings: bool
) -> None:
    store = _store(tmp_path)
    session = _FakeGoogleSession()
    session.values[("Universe Registry", 6, 1)] = session._text("OPT")
    session.values[("Universe Registry", 6, 2)] = session._text("Optional Research Company")
    captured = _reader(tmp_path, session).capture(store)
    market_run_id = _stub_approved_market_snapshot(
        tmp_path, monkeypatch, shared_strings=shared_strings
    )

    minimal = build_minimal_import_plan(store, captured.run_id, captured.sha256, market_run_id)
    assert not [issue for issue in minimal.plan.issues if issue.severity == "ERROR"]
    assert [(item.canonical_ticker, item.quantity) for item in minimal.plan.positions] == [
        ("SYN", Decimal("3.1250000001"))
    ]
    assert [(item.currency, item.balance) for item in minimal.plan.cash] == [
        ("USD", Decimal("250.2500000001"))
    ]
    assert minimal.plan.targets == {"SYN": Decimal("0.4")}
    assert [(item.venue, item.ticker, item.currency) for item in minimal.plan.listings] == [
        ("XNYS", "SYN", "USD")
    ]
    assert minimal.plan.companies[0].lifecycle is None
    assert [item.ticker for item in minimal.plan.companies] == ["OPT", "SYN"]
    assert minimal.projection["optional_universe_listing_gaps"] == [
        {
            "ticker": "OPT",
            "status": "COMPANY_IDENTITY_RETAINED_LISTING_NOT_IMPORTED",
            "reason": "No READY listing row was present in the accepted Market Data snapshot.",
        }
    ]


def test_incomplete_populated_holding_is_blocked_not_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    session = _FakeGoogleSession()
    session.values.pop(("Current Holdings", 5, 5))
    captured = _reader(tmp_path, session).capture(store)
    market_run_id = _stub_approved_market_snapshot(tmp_path, monkeypatch)

    minimal = build_minimal_import_plan(store, captured.run_id, captured.sha256, market_run_id)

    assert minimal.plan.positions == []
    assert minimal.plan.holdings_partial is True
    assert any(issue.code == "HOLDING_QUANTITY_MISSING" for issue in minimal.plan.issues)


def test_missing_declared_header_fails_before_projection() -> None:
    workbook = legacy_import.Workbook(
        path=Path("synthetic-source.json"),
        sha256="a" * 64,
        sheets={
            "Universe Registry": {
                "A4": legacy_import.Cell("Canonical Ticker", "str"),
                "B4": legacy_import.Cell("Company", "str"),
            },
            "Current Holdings": {
                "A4": legacy_import.Cell("Type", "str"),
                "B4": legacy_import.Cell("Portfolio Ticker", "str"),
                "D4": legacy_import.Cell("Price Feed Ticker", "str"),
                "E4": legacy_import.Cell("Shares / Native Cash", "str"),
                "G4": legacy_import.Cell("Currency", "str"),
            },
            "Target Architecture": {
                "A4": legacy_import.Cell("Ticker", "str"),
                "D4": legacy_import.Cell("Target Weight (Edit Here)", "str"),
            },
        },
    )

    with pytest.raises(SheetsPortfolioError) as error:
        _validate_headers(workbook)
    assert error.value.code == "WORKBOOK_HEADER_CONTRACT_MISMATCH"


@pytest.mark.integration
def test_minimal_apply_is_atomic_and_receipt_replay_is_read_only(
    postgres_engine: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    captured = _reader(tmp_path, _FakeGoogleSession()).capture(store)
    market_run_id = _stub_approved_market_snapshot(tmp_path, monkeypatch)
    minimal = build_minimal_import_plan(store, captured.run_id, captured.sha256, market_run_id)

    from portfolio_api.sheets_portfolio_vertical_slice import _apply_in_transaction, _target_scope

    settings = Settings(
        database_url="postgresql+psycopg://unused:unused@localhost/unused_test",
        database_target_environment="development",
        database_target_database="unused_test",
    )
    input_sha, scope = (
        "a" * 64,
        _target_scope(settings, "development"),
    )
    with Session(postgres_engine) as session:
        preview = preview_database(
            session,
            minimal,
            target_environment="development",
            input_sha256=input_sha,
            target_scope=scope,
        )
        assert preview["status"] == "READY"
        assert session.scalar(select(func.count()).select_from(Company)) == 0
        assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 0

    with (
        pytest.raises(RuntimeError, match="rollback test"),
        Session(postgres_engine) as session,
        session.begin(),
    ):
        _apply_in_transaction(
            session,
            minimal,
            target_environment="development",
            input_sha256=input_sha,
            target_scope=scope,
        )
        raise RuntimeError("rollback test")

    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0
        assert session.scalar(select(func.count()).select_from(Security)) == 0
        assert session.scalar(select(func.count()).select_from(Listing)) == 0
        assert session.scalar(select(func.count()).select_from(Portfolio)) == 0
        assert session.scalar(select(func.count()).select_from(HoldingPosition)) == 0
        assert session.scalar(select(func.count()).select_from(CashPosition)) == 0
        assert session.scalar(select(func.count()).select_from(TargetRevision)) == 0
        assert session.scalar(select(func.count()).select_from(TargetAllocation)) == 0
        assert session.scalar(select(func.count()).select_from(LegacyImportBatch)) == 0
        assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 0

    with Session(postgres_engine) as session, session.begin():
        applied = _apply_in_transaction(
            session,
            minimal,
            target_environment="development",
            input_sha256=input_sha,
            target_scope=scope,
        )
        assert applied["status"] == "APPLIED"

    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        universe = client.get("/v1/universe").json()
        assert len(universe) == 1
        assert universe[0]["name"] == "Synthetic Corporation"
        portfolios = client.get("/v1/portfolios").json()
        assert len(portfolios) == 1
        portfolio_id = portfolios[0]["id"]
        overview_response = client.get(f"/v1/portfolios/{portfolio_id}/overview")
        assert overview_response.status_code == 200
        overview = overview_response.json()
        assert overview["valuation_currency"] == "EUR"
        assert overview["snapshot"]["completeness"] == "COMPLETE"
        assert overview["valuation_status"] in {
            "INCOMPLETE_PRICE_COVERAGE",
            "INCOMPLETE_FX_COVERAGE",
        }
        assert Decimal(overview["snapshot"]["positions"][0]["quantity"]) == Decimal("3.1250000001")

    with Session(postgres_engine) as session:
        before = {
            Company: session.scalar(select(func.count()).select_from(Company)),
            Security: session.scalar(select(func.count()).select_from(Security)),
            Listing: session.scalar(select(func.count()).select_from(Listing)),
            Portfolio: session.scalar(select(func.count()).select_from(Portfolio)),
            HoldingPosition: session.scalar(select(func.count()).select_from(HoldingPosition)),
            CashPosition: session.scalar(select(func.count()).select_from(CashPosition)),
            TargetRevision: session.scalar(select(func.count()).select_from(TargetRevision)),
            TargetAllocation: session.scalar(select(func.count()).select_from(TargetAllocation)),
            LegacyImportBatch: session.scalar(select(func.count()).select_from(LegacyImportBatch)),
            CanonicalBootstrapRun: session.scalar(
                select(func.count()).select_from(CanonicalBootstrapRun)
            ),
        }
        assert all(value is not None and value > 0 for value in before.values())
        preview = preview_database(
            session,
            minimal,
            target_environment="development",
            input_sha256=input_sha,
            target_scope=scope,
        )
        assert preview["status"] == "ALREADY_APPLIED"
        after = {model: session.scalar(select(func.count()).select_from(model)) for model in before}
        assert after == before

    with Session(postgres_engine) as session, session.begin():
        replay = _apply_in_transaction(
            session,
            minimal,
            target_environment="development",
            input_sha256=input_sha,
            target_scope=scope,
        )
        assert replay["status"] == "ALREADY_APPLIED"
