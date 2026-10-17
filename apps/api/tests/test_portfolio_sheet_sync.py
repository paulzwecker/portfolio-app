from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import Actor, Lifecycle
from portfolio_api.portfolio_sheet_sync import (
    PORTFOLIO_STATE_COLUMNS,
    PORTFOLIO_STATE_CONTRACT_VERSION,
    PORTFOLIO_STATE_MARKER,
    PORTFOLIO_STATE_TAB,
    GoogleSheetsPortfolioPublisher,
    PortfolioSheetPublishError,
    build_portfolio_state_rows,
)

SPREADSHEET_ID = "sheet-id"
PORTFOLIO_ID = UUID("1f327894-68cd-4c50-908f-19332739e48d")
COMPANY_ID = UUID("e829571f-b7f1-4e4a-a42d-00547c1f878b")
SECURITY_ID = UUID("ce1cb567-1991-4863-9f72-ade79402c974")
LISTING_ID = UUID("8cd71301-c02e-4e81-90e1-c5f3d95a3c4d")
SNAPSHOT_ID = UUID("ceff3219-5711-46d3-a0fc-04ff1005f560")
TARGET_ID = UUID("9bc3b49b-5517-43cb-8572-1b79a174e782")
OBSERVED = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)


def _overview() -> s.PortfolioOverview:
    portfolio = s.PortfolioRead.model_construct(
        id=PORTFOLIO_ID,
        name="Primary portfolio",
        base_currency="EUR",
        created_at=OBSERVED,
        is_demo=False,
    )
    snapshot = s.SnapshotRead.model_construct(
        id=SNAPSHOT_ID,
        portfolio_id=PORTFOLIO_ID,
        effective_at=datetime(2026, 10, 3, tzinfo=UTC),
        recorded_at=datetime(2026, 10, 3, 1, tzinfo=UTC),
        completeness="COMPLETE",
        source="legacy workbook import",
        actor=Actor.IMPORT,
        reason="accepted holdings state",
        positions=[],
        cash_positions=[],
    )
    target = s.TargetRead.model_construct(
        id=TARGET_ID,
        portfolio_id=PORTFOLIO_ID,
        effective_at=datetime(2026, 10, 1, tzinfo=UTC),
        recorded_at=datetime(2026, 10, 3, 1, tzinfo=UTC),
        accepted_at=datetime(2026, 10, 3, 1, tzinfo=UTC),
        status="ACCEPTED",
        actor=Actor.LOCAL_USER,
        reason="approved targets",
        source="target review",
        allocations=[],
        invested_weight=Decimal("0.6"),
        strategic_cash_weight=Decimal("0.4"),
    )
    company = s.CompanyRead.model_construct(
        id=COMPANY_ID,
        name="Example Holdings",
        reporting_currency="USD",
        created_at=OBSERVED,
        is_demo=False,
        lifecycle=Lifecycle.PORTFOLIO,
        lifecycle_event_id=None,
    )
    position = s.HoldingContext.model_construct(
        listing_id=LISTING_ID,
        security_id=SECURITY_ID,
        ticker="EXMP",
        venue="NASDAQ",
        currency="USD",
        security_name="Example Holdings Class A",
        quantity=Decimal("10.5"),
        latest_price=Decimal("100.25"),
        price_date=datetime(2026, 10, 14, tzinfo=UTC),
        price_observed_at=OBSERVED,
        price_currency="USD",
        portfolio_weight=None,
        fx_rate=Decimal("0.92"),
        fx_effective_at=OBSERVED,
        valuation_sync_status="NON_SYNCHRONOUS",
        price_freshness="FRESH",
        native_market_value=Decimal("1052.625"),
        base_market_value=Decimal("968.415"),
        valuation_status="VALUED",
    )
    zero_target = s.CompanyPortfolioContext.model_construct(
        company=company,
        positions=[position],
        target_weight=Decimal("0"),
        current_market_value=Decimal("968.415"),
        current_market_currency="EUR",
        current_weight=None,
        allocation_gap=None,
        allocation_status="PORTFOLIO_TOTAL_UNAVAILABLE",
    )
    missing_target_company = s.CompanyRead.model_construct(
        id=UUID("a889e3bb-c02d-41ec-bd69-612d34366c05"),
        name="Missing Target Co",
        reporting_currency=None,
        created_at=OBSERVED,
        is_demo=False,
        lifecycle=Lifecycle.WATCHLIST,
        lifecycle_event_id=None,
    )
    missing_target = s.CompanyPortfolioContext.model_construct(
        company=missing_target_company,
        positions=[],
        target_weight=None,
        current_market_value=None,
        current_market_currency=None,
        current_weight=None,
        allocation_gap=None,
        allocation_status="PORTFOLIO_TOTAL_UNAVAILABLE",
    )
    cash = s.CashValuation.model_construct(
        currency="USD",
        balance=Decimal("500"),
        base_market_value=None,
        portfolio_weight=None,
        fx_rate=None,
        fx_effective_at=None,
        valuation_status="FX_UNAVAILABLE",
    )
    return s.PortfolioOverview.model_construct(
        portfolio=portfolio,
        snapshot=snapshot,
        target_revision=target,
        companies=[zero_target, missing_target],
        standalone_positions=[],
        valuation_status="INCOMPLETE_FX_COVERAGE",
        valuation_mode="CURRENT_MARK_TO_MARKET",
        valuation_as_of=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        market_data_through=OBSERVED,
        fx_data_through=None,
        holdings_age_days=12,
        holdings_freshness="STALE",
        base_market_value=None,
        valuation_currency="EUR",
        cash_valuations=[cash],
        valuation_gaps=[s.ValuationGap(identity="cash:USD", reason="FX_UNAVAILABLE")],
    )


class Response:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSheetsSession:
    def __init__(
        self,
        *,
        target_values: list[list[object]] | None = None,
        write_status: int = 200,
        corrupt_readback: bool = False,
    ) -> None:
        self.sheet_id = 44
        self.title = "Portfolio/Watchlist"
        self.other_sheets = {
            "Portfolio": 7,
            "Current Holdings": 8,
            "Application Model Sync Inbox": 9,
        }
        self.target_values = target_values
        self.write_status = write_status
        self.corrupt_readback = corrupt_readback
        self.write_requests: list[dict[str, object]] = []
        self.last_table: list[list[str]] | None = None
        self.get_calls: list[str] = []

    def get(self, url: str, **_: object) -> Response:
        self.get_calls.append(url)
        if "?fields=spreadsheetId" in url:
            sheets = [
                {"properties": {"sheetId": sheet_id, "title": title}}
                for title, sheet_id in self.other_sheets.items()
            ]
            if self.target_values is not None:
                sheets.append(
                    {"properties": {"sheetId": self.sheet_id, "title": PORTFOLIO_STATE_TAB}}
                )
            return Response(
                {
                    "spreadsheetId": SPREADSHEET_ID,
                    "properties": {"title": self.title},
                    "sheets": sheets,
                }
            )
        if "/values/" in url:
            values = self.target_values or []
            if self.corrupt_readback and self.last_table is not None:
                values = [row.copy() for row in values]
                if values:
                    values[0][1] = "unexpected"
            return Response({"values": values})
        return Response({})

    def post(self, url: str, json: dict[str, object] | None = None, **_: object) -> Response:
        body = json or {}
        self.write_requests.append(body)
        if self.write_status >= 400:
            return Response({}, self.write_status)
        requests = body.get("requests", [])
        if isinstance(requests, list):
            for request in requests:
                add_sheet = request.get("addSheet") if isinstance(request, dict) else None
                if isinstance(add_sheet, dict):
                    self.target_values = []
                    return Response(
                        {"replies": [{"addSheet": {"properties": {"sheetId": self.sheet_id}}}]}
                    )
            for request in requests:
                if not isinstance(request, dict):
                    continue
                update = request.get("updateCells")
                if isinstance(update, dict) and isinstance(update.get("rows"), list):
                    new_table: list[list[str]] = []
                    for row in update["rows"]:
                        values = row.get("values", []) if isinstance(row, dict) else []
                        new_table.append(
                            [
                                cell.get("userEnteredValue", {}).get("stringValue", "")
                                for cell in values
                            ]
                        )
                    self.last_table = new_table
                    self.target_values = cast(list[list[object]], new_table)
        return Response({"replies": []})


def _publisher(session: FakeSheetsSession) -> GoogleSheetsPortfolioPublisher:
    publisher = GoogleSheetsPortfolioPublisher.__new__(GoogleSheetsPortfolioPublisher)
    publisher.spreadsheet_id = SPREADSHEET_ID
    publisher.timeout = 3
    publisher.session = session
    return publisher


def test_export_preserves_exact_identity_timestamps_and_missing_vs_zero() -> None:
    rows = build_portfolio_state_rows(_overview())
    portfolio = rows[0]
    assert portfolio["holdings_snapshot_id"] == str(SNAPSHOT_ID)
    assert portfolio["target_revision_id"] == str(TARGET_ID)
    assert portfolio["holdings_effective_at"] == "2026-10-03T00:00:00+00:00"
    assert portfolio["market_data_through"] == OBSERVED.isoformat()
    company_rows = [row for row in rows if row["record_type"] == "COMPANY_ALLOCATION"]
    assert company_rows[0]["target_weight"] == Decimal("0")
    assert company_rows[0]["target_state"] == "AUTHORED"
    assert company_rows[1]["target_weight"] is None
    assert company_rows[1]["target_state"] == "MISSING"
    position = next(row for row in rows if row["record_type"] == "POSITION")
    assert position["listing_id"] == str(LISTING_ID)
    assert position["security_id"] == str(SECURITY_ID)
    assert position["quantity"] == Decimal("10.5")
    assert position["price_observed_at"] == OBSERVED.isoformat()
    cash = next(row for row in rows if row["record_type"] == "CASH")
    assert cash["cash_currency"] == "USD"
    assert cash["cash_balance"] == Decimal("500")
    assert cash["availability_status"] == "FX_UNAVAILABLE"
    assert portfolio["valuation_status"] == "INCOMPLETE_FX_COVERAGE"
    assert portfolio["portfolio_market_value"] is None


def test_publication_is_allowlisted_idempotent_and_read_back_verified() -> None:
    session = FakeSheetsSession()
    publisher = _publisher(session)
    first = publisher.publish(_overview())
    assert first.status == "PUBLISHED"
    assert first.read_back_verified
    assert first.tab == PORTFOLIO_STATE_TAB
    assert first.contract_version == PORTFOLIO_STATE_CONTRACT_VERSION
    assert first.row_count == len(build_portfolio_state_rows(_overview()))
    assert session.last_table is not None
    assert session.last_table[0] == ["contract_marker", PORTFOLIO_STATE_MARKER]
    assert session.last_table[1] == ["contract_version", PORTFOLIO_STATE_CONTRACT_VERSION]
    assert session.last_table[7] == list(PORTFOLIO_STATE_COLUMNS)
    state_writes: list[dict[str, object]] = []
    for request in session.write_requests:
        requests = request.get("requests")
        if isinstance(requests, list) and any(
            isinstance(item, dict) and "updateCells" in item for item in requests
        ):
            state_writes.append(request)
    raw_requests = state_writes[0].get("requests")
    assert isinstance(raw_requests, list)
    update_cells = next(
        item for item in raw_requests if isinstance(item, dict) and "updateCells" in item
    )
    update = update_cells.get("updateCells") if isinstance(update_cells, dict) else None
    assert isinstance(update, dict)
    start = update.get("start")
    assert isinstance(start, dict)
    assert start.get("sheetId") == 44
    for request in session.write_requests:
        body_requests = request.get("requests")
        if isinstance(body_requests, list):
            for item in body_requests:
                if not isinstance(item, dict):
                    continue
                if "updateSheetProperties" in item:
                    properties = item["updateSheetProperties"].get("properties")
                    assert properties["sheetId"] == 44
                if "updateCells" in item:
                    update = item["updateCells"]
                    location = update.get("start") or update.get("range")
                    assert location["sheetId"] == 44
        if isinstance(body_requests, list) and body_requests:
            first_request = body_requests[0]
            if isinstance(first_request, dict) and "addSheet" in first_request:
                add_sheet = first_request.get("addSheet")
                properties = add_sheet.get("properties") if isinstance(add_sheet, dict) else None
                assert isinstance(properties, dict)
                assert properties.get("title") == PORTFOLIO_STATE_TAB

    second = publisher.publish(_overview())
    assert second.status == "UNCHANGED"
    assert second.content_fingerprint == first.content_fingerprint
    assert len(session.write_requests) == 2


def test_replay_detects_manual_changes_inside_the_owned_tab() -> None:
    session = FakeSheetsSession()
    publisher = _publisher(session)
    published = publisher.publish(_overview())
    assert published.status == "PUBLISHED"
    assert session.target_values is not None
    session.target_values[8][1] = "changed outside the application"
    with pytest.raises(PortfolioSheetPublishError, match="no cells were changed") as failure:
        publisher.publish(_overview())
    assert failure.value.code == "TARGET_CONTENT_MISMATCH"
    assert len(session.write_requests) == 2


def test_existing_unowned_tab_is_never_modified() -> None:
    session = FakeSheetsSession(target_values=[["", "", "preserve me"]])
    with pytest.raises(
        PortfolioSheetPublishError, match="not marked as application-owned"
    ) as failure:
        _publisher(session).publish(_overview())
    assert failure.value.code == "TARGET_TAB_NOT_OWNED"
    assert session.write_requests == []


def test_writer_permission_failure_is_reported_without_readback_claim() -> None:
    session = FakeSheetsSession(
        target_values=[
            ["contract_marker", PORTFOLIO_STATE_MARKER],
            ["contract_version", PORTFOLIO_STATE_CONTRACT_VERSION],
        ],
        write_status=403,
    )
    with pytest.raises(PortfolioSheetPublishError) as failure:
        _publisher(session).publish(_overview())
    assert failure.value.code == "PUBLISH_FAILED"
    assert failure.value.status == 403
    assert "Editor" in str(failure.value)


def test_partial_publication_is_reported_when_readback_differs() -> None:
    session = FakeSheetsSession(corrupt_readback=True)
    with pytest.raises(PortfolioSheetPublishError, match="read-back did not match") as failure:
        _publisher(session).publish(_overview())
    assert failure.value.code == "READBACK_MISMATCH"
    assert session.last_table is not None


def test_contract_serializes_missing_values_as_blank_with_explicit_status() -> None:
    session = FakeSheetsSession()
    result = _publisher(session).publish(_overview())
    assert result.status == "PUBLISHED"
    assert session.last_table is not None
    columns = session.last_table[7]
    portfolio_row = next(row for row in session.last_table[8:] if row[0] == "PORTFOLIO")
    assert portfolio_row[columns.index("portfolio_market_value")] == ""
    assert portfolio_row[columns.index("valuation_status")] == "INCOMPLETE_FX_COVERAGE"
    cash_row = next(row for row in session.last_table[8:] if row[0] == "CASH")
    assert cash_row[columns.index("fx_rate")] == ""
    assert cash_row[columns.index("availability_status")] == "FX_UNAVAILABLE"
