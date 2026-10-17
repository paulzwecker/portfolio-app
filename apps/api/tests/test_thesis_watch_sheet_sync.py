from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api import thesis_watch_sheet_sync as sync
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import Lifecycle, ResearchTriggerType
from portfolio_api.portfolio_sheet_sync import PortfolioSheetPublishError
from portfolio_api.settings import Settings

SPREADSHEET_ID = "test-spreadsheet-id-1234567890"
COMPANY_ID = UUID("e829571f-b7f1-4e4a-a42d-00547c1f878b")
TRIGGER_ID = UUID("19d4a906-4c82-4a4d-a94e-fb4e3714e9ae")
OBSERVED = datetime(2026, 10, 15, 9, tzinfo=UTC)


class Response:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSheetsSession:
    def __init__(self, target_values: list[list[object]] | None = None) -> None:
        self.target_values = target_values
        self.writes: list[dict[str, object]] = []
        self.last_table: list[list[str]] | None = None

    def get(self, url: str, **_: object) -> Response:
        if "?fields=spreadsheetId" in url:
            sheets: list[dict[str, object]] = (
                [
                    {
                        "properties": {
                            "sheetId": 82,
                            "title": sync.THESIS_WATCH_TAB,
                            "gridProperties": {"rowCount": 5000, "columnCount": 18},
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
            return Response({"values": self.target_values or []})
        return Response({})

    def post(self, url: str, json: dict[str, object] | None = None, **_: object) -> Response:
        body = json or {}
        self.writes.append(body)
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
                assert properties.get("title") == sync.THESIS_WATCH_TAB
                return Response({"replies": [{"addSheet": {"properties": {"sheetId": 82}}}]})
        if self.target_values is None:
            self.target_values = []
        table = self.target_values
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
            while len(table) < row_index:
                table.append([])
            for index, row in enumerate(written):
                target_index = row_index + index
                if target_index < len(table):
                    table[target_index] = row
                else:
                    table.append(row)
        self.last_table = cast(list[list[str]], table)
        return Response({"replies": []})


def _company() -> s.CompanyRead:
    return s.CompanyRead.model_construct(
        id=COMPANY_ID,
        name="Example Corp",
        reporting_currency="USD",
        created_at=OBSERVED,
        is_demo=False,
        lifecycle=Lifecycle.WATCHLIST,
        lifecycle_event_id=None,
    )


def _trigger(reason: str = "A new filing needs review") -> s.ResearchTriggerRead:
    return s.ResearchTriggerRead.model_construct(
        id=TRIGGER_ID,
        company=_company(),
        event_key="source_document:filing-1",
        version=1,
        fingerprint="a" * 64,
        trigger_type=ResearchTriggerType.NEW_FILING,
        title="New filing: 10-Q",
        reason=reason,
        source_domain="source_document",
        source_record_id="filing-1",
        source_reference="https://example.com/filing",
        effective_at=OBSERVED,
        source_observed_at=OBSERVED,
        source_recorded_at=OBSERVED,
        detected_at=OBSERVED,
        source_snapshot={"document_type": "10-Q"},
        queue_task_id=None,
        queue_condition_fingerprint=None,
        processing_state="OPEN",
    )


def _context(trigger: s.ResearchTriggerRead) -> s.ResearchTriggerContextRead:
    return s.ResearchTriggerContextRead.model_construct(
        context_as_of=OBSERVED,
        trigger=trigger,
        securities=[],
        listings=[],
        research=s.CompanyResearchRead.model_construct(
            company_id=COMPANY_ID, as_of=None, known_at=None, streams=[]
        ),
        thesis=s.CompanyInvestmentThesisRead.model_construct(
            company_id=COMPANY_ID, as_of=None, known_at=None, streams=[]
        ),
        models=[],
        accepted_publications=[],
    )


def _publisher(session: FakeSheetsSession) -> sync.GoogleSheetsThesisWatchPublisher:
    publisher = sync.GoogleSheetsThesisWatchPublisher.__new__(sync.GoogleSheetsThesisWatchPublisher)
    publisher.spreadsheet_id = SPREADSHEET_ID
    publisher.timeout = 3
    publisher.session = session
    return publisher


def _db() -> Session:
    return cast(Session, object())


def _patch_context(
    monkeypatch: pytest.MonkeyPatch, *, reason: str = "A new filing needs review"
) -> None:
    trigger = _trigger(reason)
    result = s.ResearchTriggerReadResult.model_construct(as_of=OBSERVED, triggers=[trigger])
    monkeypatch.setattr(sync, "list_research_triggers", lambda *args, **kwargs: result)
    monkeypatch.setattr(sync, "research_trigger_context", lambda *args, **kwargs: _context(trigger))


def test_feed_is_allowlisted_append_only_and_exact_replay_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_context(monkeypatch)
    session = FakeSheetsSession()
    publisher = _publisher(session)

    first = publisher.publish_triggers(_db())
    assert first.status == "PUBLISHED"
    assert first.tab == sync.THESIS_WATCH_TAB
    assert first.added_count == 1
    assert first.read_back_verified
    assert session.last_table is not None
    assert session.last_table[0][1] == sync.THESIS_WATCH_MARKER
    assert session.last_table[7] == list(sync.THESIS_WATCH_COLUMNS)
    assert session.last_table[8][0] == str(TRIGGER_ID)
    assert "Example Corp" in session.last_table[8][-1]

    replay = publisher.publish_triggers(_db())
    assert replay.status == "UNCHANGED"
    assert replay.content_fingerprint == first.content_fingerprint
    assert len(session.writes) == 2  # create tab and first data write only


def test_changed_context_appends_a_revision_and_keeps_the_prior_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_context(monkeypatch)
    session = FakeSheetsSession()
    publisher = _publisher(session)
    first = publisher.publish_triggers(_db())
    first_row = session.last_table[8].copy() if session.last_table else []

    _patch_context(monkeypatch, reason="The filing received a new accepted interpretation")
    second = publisher.publish_triggers(_db())

    assert second.status == "PUBLISHED"
    assert second.added_count == 1
    assert second.row_count == 2
    assert session.last_table is not None
    assert session.last_table[8] == first_row
    assert session.last_table[9][0] == first_row[0]
    assert session.last_table[9][16] != first_row[16]
    assert first.content_fingerprint != second.content_fingerprint


def test_unowned_tab_is_never_written(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_context(monkeypatch)
    session = FakeSheetsSession([["someone else's research", "preserve"]])

    with pytest.raises(PortfolioSheetPublishError) as failure:
        _publisher(session).publish_triggers(_db())

    assert failure.value.code == "TARGET_TAB_NOT_OWNED"
    assert session.writes == []


def test_oversized_context_fails_before_any_workbook_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trigger = _trigger()
    trigger.source_snapshot = {"source_excerpt": "x" * 45_000}
    result = s.ResearchTriggerReadResult.model_construct(as_of=OBSERVED, triggers=[trigger])
    context = _context(trigger)
    monkeypatch.setattr(sync, "list_research_triggers", lambda *args, **kwargs: result)
    monkeypatch.setattr(sync, "research_trigger_context", lambda *args, **kwargs: context)
    session = FakeSheetsSession()

    with pytest.raises(PortfolioSheetPublishError) as failure:
        _publisher(session).publish_triggers(_db())

    assert failure.value.code == "CONTEXT_TOO_LARGE"
    assert session.writes == []


@pytest.mark.integration
def test_publish_service_serializes_with_a_postgres_transaction_lock(
    postgres_engine: Engine,
) -> None:
    class Publisher:
        spreadsheet_id = SPREADSHEET_ID

        def publish_triggers(
            self, session: Session, *, limit: int, offset: int
        ) -> s.GoogleSheetsThesisWatchPublishRead:
            assert limit == 50
            assert offset == 100
            return s.GoogleSheetsThesisWatchPublishRead(
                status="UNCHANGED",
                spreadsheet_id=SPREADSHEET_ID,
                spreadsheet_title="Portfolio/Watchlist",
                tab=sync.THESIS_WATCH_TAB,
                contract_version=sync.THESIS_WATCH_CONTRACT_VERSION,
                content_fingerprint="sha256:" + "a" * 64,
                published_at=OBSERVED,
                row_count=0,
                added_count=0,
                trigger_ids=[],
                read_back_verified=True,
                message="No new rows.",
            )

    with Session(postgres_engine) as session, session.begin():
        result = sync.publish_thesis_watch_feed(
            session,
            Settings(google_sheets_spreadsheet_id=SPREADSHEET_ID),
            limit=50,
            offset=100,
            publisher=cast(sync.GoogleSheetsThesisWatchPublisher, Publisher()),
        )
        assert result.status == "UNCHANGED"
