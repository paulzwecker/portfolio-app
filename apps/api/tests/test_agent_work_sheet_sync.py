from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from portfolio_api import agent_work_sheet_sync as sync
from portfolio_api.domain import schemas as s
from portfolio_api.portfolio_sheet_sync import PortfolioSheetPublishError
from portfolio_api.settings import Settings

SPREADSHEET_ID = "test-spreadsheet-id-1234567890"
OBSERVED = datetime(2026, 10, 16, 9, tzinfo=UTC)
DELIVERY_ID = UUID("c3a7bead-0b35-4bd8-a89d-70f66a0f0458")
WORK_FINGERPRINT = "b" * 64


class Response:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSheetsSession:
    def __init__(self, target_values: list[list[object]] | None = None) -> None:
        self.target_values = target_values
        self.writes: list[tuple[str, dict[str, object]]] = []
        self.mismatch_readback = False

    def get(self, url: str, **_: object) -> Response:
        if "?fields=spreadsheetId" in url:
            sheets: list[dict[str, object]] = (
                [
                    {
                        "properties": {
                            "sheetId": 73,
                            "title": sync.AGENT_WORK_FEED_TAB,
                            "gridProperties": {
                                "rowCount": sync.MAX_AGENT_WORK_ROWS,
                                "columnCount": len(sync.AGENT_WORK_FEED_COLUMNS),
                            },
                        }
                    }
                ]
                if self.target_values is not None
                else []
            )
            return Response(
                {
                    "spreadsheetId": SPREADSHEET_ID,
                    "properties": {"title": "Portfolio/Watchlist"},
                    "sheets": sheets,
                }
            )
        if "/values/" in url:
            values = self.target_values or []
            if self.mismatch_readback and values:
                values = [row.copy() for row in values]
                values[-1][-1] = "changed"
            return Response({"values": values})
        return Response({})

    def post(self, url: str, json: dict[str, object] | None = None, **_: object) -> Response:
        body = json or {}
        self.writes.append((url, body))
        requests = body.get("requests", [])
        if not isinstance(requests, list):
            return Response({})
        for request in requests:
            if not isinstance(request, dict):
                continue
            added = request.get("addSheet")
            if isinstance(added, dict):
                self.target_values = []
                properties = added.get("properties")
                assert isinstance(properties, dict)
                assert properties.get("title") == sync.AGENT_WORK_FEED_TAB
                return Response({"replies": [{"addSheet": {"properties": {"sheetId": 73}}}]})
        if self.target_values is None:
            self.target_values = []
        for request in requests:
            if not isinstance(request, dict):
                continue
            update = request.get("updateCells")
            if not isinstance(update, dict) or not isinstance(update.get("rows"), list):
                continue
            start = update.get("start")
            assert isinstance(start, dict)
            row_index = start.get("rowIndex")
            assert isinstance(row_index, int)
            written = [
                [
                    cell.get("userEnteredValue", {}).get("stringValue", "")
                    for cell in row.get("values", [])
                ]
                for row in update["rows"]
            ]
            while len(self.target_values) < row_index:
                self.target_values.append([])
            for index, row in enumerate(written):
                target_index = row_index + index
                if target_index < len(self.target_values):
                    self.target_values[target_index] = row
                else:
                    self.target_values.append(row)
        return Response({"replies": []})


def _contract() -> s.ResearchAgentWorkContractV1:
    item = s.ResearchAgentWorkItemRead(
        delivery_id=DELIVERY_ID,
        work_type="DATA_DOMAIN",
        work_key="sec_edgar:SOURCE_DOCUMENTS",
        work_fingerprint=WORK_FINGERPRINT,
        delivery_channel="GOOGLE_SHEETS",
        delivered_at=OBSERVED,
        current_status="DELIVERED",
        current_reason=None,
        payload={"domain": "SOURCE_DOCUMENTS", "freshness": "STALE"},
    )
    return s.ResearchAgentWorkContractV1(
        agent_role="DATA_UNIVERSE_STEWARD",
        as_of=OBSERVED,
        status="AVAILABLE",
        status_reason=None,
        items=[item],
    )


def _publisher(session: FakeSheetsSession) -> sync.GoogleSheetsAgentWorkPublisher:
    publisher = sync.GoogleSheetsAgentWorkPublisher.__new__(sync.GoogleSheetsAgentWorkPublisher)
    publisher.spreadsheet_id = SPREADSHEET_ID
    publisher.timeout = 3
    publisher.session = session
    return publisher


def test_work_feed_is_allowlisted_append_only_and_exact_replay_is_idempotent() -> None:
    session = FakeSheetsSession()
    publisher = _publisher(session)

    first = publisher.publish_work(_contract())
    assert first.status == "PUBLISHED"
    assert first.tab == sync.AGENT_WORK_FEED_TAB
    assert first.added_count == 1
    assert first.read_back_verified
    assert session.target_values is not None
    assert session.target_values[0][1] == sync.AGENT_WORK_FEED_MARKER
    assert session.target_values[7] == list(sync.AGENT_WORK_FEED_COLUMNS)
    assert session.target_values[8][0] == str(DELIVERY_ID)
    payload_json = session.target_values[8][-1]
    assert isinstance(payload_json, str)
    assert '"freshness":"STALE"' in payload_json
    written_sheet_ids: list[int] = []
    for _url, body in session.writes:
        requests = body.get("requests", [])
        assert isinstance(requests, list)
        for request in requests:
            assert isinstance(request, dict)
            update = request.get("updateCells")
            if not isinstance(update, dict):
                continue
            start = update.get("start")
            if not isinstance(start, dict):
                continue
            sheet_id = start.get("sheetId")
            if isinstance(sheet_id, int):
                written_sheet_ids.append(sheet_id)
    assert written_sheet_ids and set(written_sheet_ids) == {73}

    replay = publisher.publish_work(_contract())
    assert replay.status == "UNCHANGED"
    assert replay.content_fingerprint == first.content_fingerprint
    assert len(session.writes) == 2


def test_new_work_appends_without_modifying_prior_delivery_rows() -> None:
    session = FakeSheetsSession()
    publisher = _publisher(session)
    first = publisher.publish_work(_contract())
    assert session.target_values is not None
    previous_row = session.target_values[8].copy()

    item = (
        _contract()
        .items[0]
        .model_copy(
            update={
                "delivery_id": UUID("b13c0ac6-46e5-41c3-b88d-2be8b1a8a6ef"),
                "work_key": "sec_edgar:REPORTED_FUNDAMENTALS",
            }
        )
    )
    second_contract = _contract().model_copy(update={"items": [item]})
    second = publisher.publish_work(second_contract)

    assert second.status == "PUBLISHED"
    assert second.row_count == 2
    assert second.added_count == 1
    assert session.target_values[8] == previous_row
    assert session.target_values[9][0] == str(item.delivery_id)
    assert first.content_fingerprint != second.content_fingerprint


def test_unowned_tab_is_never_written() -> None:
    session = FakeSheetsSession([["someone else's work", "preserve"]])

    with pytest.raises(PortfolioSheetPublishError) as failure:
        _publisher(session).publish_work(_contract())

    assert failure.value.code == "TARGET_TAB_NOT_OWNED"
    assert session.writes == []


def test_modified_history_or_failed_readback_is_not_reported_as_success() -> None:
    session = FakeSheetsSession()
    publisher = _publisher(session)
    publisher.publish_work(_contract())
    assert session.target_values is not None
    session.target_values[8][-1] = "tampered"

    with pytest.raises(PortfolioSheetPublishError) as tampered:
        publisher.publish_work(_contract())
    assert tampered.value.code == "TARGET_CONTENT_MISMATCH"

    readback_session = FakeSheetsSession()
    readback_publisher = _publisher(readback_session)
    readback_session.mismatch_readback = True
    with pytest.raises(PortfolioSheetPublishError) as mismatch:
        readback_publisher.publish_work(_contract())
    assert mismatch.value.code == "READBACK_MISMATCH"


def test_oversized_payload_is_rejected_before_any_sheet_write() -> None:
    contract = _contract()
    item = contract.items[0].model_copy(update={"payload": {"large": "x" * 45_000}})
    contract = contract.model_copy(update={"items": [item]})
    session = FakeSheetsSession()

    with pytest.raises(PortfolioSheetPublishError) as failure:
        _publisher(session).publish_work(contract)

    assert failure.value.code == "WORK_ITEM_TOO_LARGE"
    assert session.writes == []


def test_empty_work_does_not_create_a_publisher_or_write_any_tab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ShouldNotPublish:
        def __init__(self, _: Settings) -> None:
            raise AssertionError("Empty work should not contact Google")

    monkeypatch.setattr(sync, "GoogleSheetsAgentWorkPublisher", ShouldNotPublish)
    contract = s.ResearchAgentWorkContractV1(
        agent_role="PORTFOLIO_THESIS_SENTINEL",
        as_of=OBSERVED,
        status="NO_WORK",
        status_reason="No open work.",
        items=[],
    )
    result = sync.publish_agent_work_feed(cast(Session, object()), contract, Settings())

    assert result.status == "NO_WORK"
    assert not result.read_back_verified
    assert result.work_item_count == 0
