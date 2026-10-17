"""Append-only, bounded trigger/context handoff for the external Thesis Watch agent."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.portfolio_sheet_sync import (
    MAX_STATE_ROWS,
    GoogleSheetsPortfolioPublisher,
    PortfolioSheetPublishError,
    _column_name,
)
from portfolio_api.research_triggers import list_research_triggers, research_trigger_context
from portfolio_api.settings import Settings

THESIS_WATCH_TAB = "Application Thesis Watch Feed"
THESIS_WATCH_MARKER = "PORTFOLIO_RESEARCH_THESIS_WATCH_FEED"
THESIS_WATCH_CONTRACT_VERSION = "1.0.0"
THESIS_WATCH_COLUMNS = (
    "trigger_id",
    "event_key",
    "trigger_version",
    "company_id",
    "company_name",
    "lifecycle",
    "trigger_type",
    "title",
    "reason",
    "source_domain",
    "source_record_id",
    "source_reference",
    "effective_at",
    "source_observed_at",
    "source_recorded_at",
    "detected_at",
    "context_fingerprint",
    "context_json",
)
MAX_CONTEXT_CELL_CHARS = 40_000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _context_payload(context: s.ResearchTriggerContextRead) -> dict[str, object]:
    """Keep the handoff to the current accepted context, not unbounded revision history."""
    payload = context.model_dump(mode="json")
    payload.pop("context_as_of", None)  # publication time is in the sheet manifest
    for key in ("research", "thesis"):
        domain = payload.get(key)
        if isinstance(domain, dict) and isinstance(domain.get("streams"), list):
            domain["streams"] = [
                {
                    "stream_key": stream.get("stream_key"),
                    "current_revision": stream.get("current_revision"),
                }
                for stream in domain["streams"]
                if isinstance(stream, dict)
            ]
    return payload


def _trigger_row(
    trigger: s.ResearchTriggerRead, context: s.ResearchTriggerContextRead
) -> list[str]:
    context_json = _canonical(_context_payload(context))
    if len(context_json) > MAX_CONTEXT_CELL_CHARS:
        raise PortfolioSheetPublishError(
            "CONTEXT_TOO_LARGE",
            f"Thesis Watch context for trigger {trigger.id} exceeds the safe Sheets cell limit; "
            "no workbook cells were changed.",
            status=413,
        )
    return [
        str(trigger.id),
        trigger.event_key,
        str(trigger.version),
        str(trigger.company.id),
        trigger.company.name,
        trigger.company.lifecycle or "",
        trigger.trigger_type.value,
        trigger.title,
        trigger.reason,
        trigger.source_domain,
        trigger.source_record_id,
        trigger.source_reference or "",
        _cell(trigger.effective_at),
        _cell(trigger.source_observed_at),
        _cell(trigger.source_recorded_at),
        _cell(trigger.detected_at),
        "sha256:" + _sha256(context_json),
        context_json,
    ]


def _manifest(now: datetime, fingerprint: str, count: int) -> list[list[str]]:
    return [
        ["contract_marker", THESIS_WATCH_MARKER],
        ["contract_version", THESIS_WATCH_CONTRACT_VERSION],
        ["content_fingerprint", fingerprint],
        ["published_at", now.astimezone(UTC).isoformat()],
        ["record_count", str(count)],
    ]


def _feed_fingerprint(rows: list[list[str]]) -> str:
    return "sha256:" + _sha256(_canonical([list(THESIS_WATCH_COLUMNS), *rows]))


class GoogleSheetsThesisWatchPublisher(GoogleSheetsPortfolioPublisher):
    """Writer fixed to the application-owned Thesis Watch feed tab."""

    def _add_thesis_watch_tab(self) -> int:
        result = self._request(
            "post",
            self._url(":batchUpdate"),
            {
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": THESIS_WATCH_TAB,
                                "gridProperties": {
                                    "rowCount": MAX_STATE_ROWS,
                                    "columnCount": len(THESIS_WATCH_COLUMNS),
                                },
                            }
                        }
                    }
                ]
            },
        )
        replies = result.get("replies")
        added = replies[0].get("addSheet") if isinstance(replies, list) and replies else None
        properties = added.get("properties") if isinstance(added, dict) else None
        sheet_id = properties.get("sheetId") if isinstance(properties, dict) else None
        if not isinstance(sheet_id, int):
            raise PortfolioSheetPublishError(
                "INVALID_RESPONSE", "Google did not return the Thesis Watch tab identity"
            )
        return sheet_id

    def _read_thesis_watch_area(self, row_count: int) -> list[list[object]]:
        last_column = _column_name(len(THESIS_WATCH_COLUMNS) - 1)
        cell_range = quote(
            f"'{THESIS_WATCH_TAB}'!A1:{last_column}{min(MAX_STATE_ROWS, max(1, row_count))}",
            safe="!:$'",
        )
        result = self._request(
            "get",
            self._url(
                f"/values/{cell_range}?majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
            ),
        )
        values = result.get("values", [])
        if not isinstance(values, list):
            raise PortfolioSheetPublishError(
                "INVALID_RESPONSE", "Google returned invalid Thesis Watch tab values"
            )
        return values

    @staticmethod
    def _normalize_rows(values: list[list[object]], width: int) -> list[list[str]]:
        result: list[list[str]] = []
        for row in values:
            if not isinstance(row, list):
                result.append([""] * width)
                continue
            result.append([_cell(value) for value in row[:width]] + [""] * max(0, width - len(row)))
        return result

    def publish_triggers(
        self,
        session: Session,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> s.GoogleSheetsThesisWatchPublishRead:
        trigger_page = list_research_triggers(
            session, processing_state="OPEN", limit=limit, offset=offset
        )
        new_rows = [
            _trigger_row(trigger, research_trigger_context(session, trigger.id))
            for trigger in trigger_page.triggers
        ]
        now = datetime.now(UTC)
        connection = self.connection()
        sheet_id = connection.sheet_ids.get(THESIS_WATCH_TAB)
        created_tab = sheet_id is None
        old_values: list[list[object]] = []
        old_rows: list[list[str]] = []
        old_fingerprint = ""
        valid_existing_feed = False
        if created_tab:
            sheet_id = self._add_thesis_watch_tab()
        else:
            assert sheet_id is not None
            dimensions = connection.sheet_dimensions.get(
                THESIS_WATCH_TAB, (MAX_STATE_ROWS, len(THESIS_WATCH_COLUMNS))
            )
            old_values = self._read_thesis_watch_area(dimensions[0])
            old_normalized = self._normalize_rows(old_values, len(THESIS_WATCH_COLUMNS))
            nonempty = any(value for row in old_normalized for value in row)
            if nonempty:
                marker = old_normalized[0][1] if len(old_normalized) > 0 else ""
                version = old_normalized[1][1] if len(old_normalized) > 1 else ""
                if (
                    len(old_normalized) < 8
                    or old_normalized[0][0] != "contract_marker"
                    or marker != THESIS_WATCH_MARKER
                    or old_normalized[1][0] != "contract_version"
                    or version != THESIS_WATCH_CONTRACT_VERSION
                    or old_normalized[7] != list(THESIS_WATCH_COLUMNS)
                ):
                    raise PortfolioSheetPublishError(
                        "TARGET_TAB_NOT_OWNED",
                        f"The existing '{THESIS_WATCH_TAB}' tab is not a valid application-owned "
                        "feed; no workbook content was changed.",
                        status=409,
                    )
                try:
                    declared_count = int(old_normalized[4][1])
                except (IndexError, ValueError):
                    declared_count = -1
                old_rows = old_normalized[8:]
                if declared_count != len(old_rows) or any(
                    len(row) != len(THESIS_WATCH_COLUMNS) or not row[0] for row in old_rows
                ):
                    raise PortfolioSheetPublishError(
                        "TARGET_CONTENT_MISMATCH",
                        "The application-owned Thesis Watch feed has an incomplete or altered "
                        "append history; no cells were changed.",
                        status=409,
                    )
                old_fingerprint = _feed_fingerprint(old_rows)
                if old_normalized[2][1] != old_fingerprint:
                    raise PortfolioSheetPublishError(
                        "TARGET_CONTENT_MISMATCH",
                        "The application-owned Thesis Watch feed fingerprint does not match its "
                        "contents; no cells were changed.",
                        status=409,
                    )
                valid_existing_feed = True

        existing = {(row[0], row[16]) for row in old_rows}
        additions = [row for row in new_rows if (row[0], row[16]) not in existing]
        if not additions and valid_existing_feed:
            published_at = datetime.fromisoformat(old_normalized[3][1])
            return s.GoogleSheetsThesisWatchPublishRead(
                status="UNCHANGED",
                spreadsheet_id=self.spreadsheet_id,
                spreadsheet_title=connection.title,
                tab=THESIS_WATCH_TAB,
                contract_version=THESIS_WATCH_CONTRACT_VERSION,
                content_fingerprint=old_fingerprint,
                published_at=published_at,
                row_count=len(old_rows),
                added_count=0,
                trigger_ids=[row[0] for row in new_rows],
                read_back_verified=True,
                message=(
                    "No new trigger context was added; existing Thesis Watch rows were preserved."
                ),
            )

        combined = old_rows + additions
        if len(combined) + 8 > MAX_STATE_ROWS:
            raise PortfolioSheetPublishError(
                "FEED_TOO_LARGE",
                "The append-only Thesis Watch feed reached its row limit",
                status=413,
            )
        fingerprint = _feed_fingerprint(combined)
        manifest = _manifest(now, fingerprint, len(combined))
        manifest_rows = [row + [""] * (len(THESIS_WATCH_COLUMNS) - len(row)) for row in manifest]
        header = [list(THESIS_WATCH_COLUMNS)]
        table = manifest_rows + [[""] * len(THESIS_WATCH_COLUMNS)] * 2 + header + combined
        assert sheet_id is not None
        requests: list[dict[str, object]] = []
        if created_tab:
            requests.append(
                {
                    "updateCells": {
                        "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                        "rows": [
                            {
                                "values": [
                                    {"userEnteredValue": {"stringValue": value}} for value in row
                                ]
                            }
                            for row in table
                        ],
                        "fields": "userEnteredValue",
                    }
                }
            )
        else:
            requests.extend(
                [
                    {
                        "updateCells": {
                            "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                            "rows": [
                                {
                                    "values": [
                                        {"userEnteredValue": {"stringValue": value}}
                                        for value in row
                                    ]
                                }
                                for row in manifest_rows
                            ],
                            "fields": "userEnteredValue",
                        }
                    },
                    {
                        "updateCells": {
                            "start": {
                                "sheetId": sheet_id,
                                "rowIndex": len(old_rows) + 8,
                                "columnIndex": 0,
                            },
                            "rows": [
                                {
                                    "values": [
                                        {"userEnteredValue": {"stringValue": value}}
                                        for value in row
                                    ]
                                }
                                for row in additions
                            ],
                            "fields": "userEnteredValue",
                        }
                    },
                ]
            )
        self._request("post", self._url(":batchUpdate"), {"requests": requests})
        last_column = _column_name(len(THESIS_WATCH_COLUMNS) - 1)
        cell_range = quote(f"'{THESIS_WATCH_TAB}'!A1:{last_column}{len(table)}", safe="!:$'")
        readback = self._request(
            "get",
            self._url(
                f"/values/{cell_range}?majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
            ),
        ).get("values")
        if (
            not isinstance(readback, list)
            or self._normalize_rows(readback, len(THESIS_WATCH_COLUMNS)) != table
        ):
            raise PortfolioSheetPublishError(
                "READBACK_MISMATCH", "Thesis Watch feed write did not match its read-back"
            )
        return s.GoogleSheetsThesisWatchPublishRead(
            status="PUBLISHED",
            spreadsheet_id=self.spreadsheet_id,
            spreadsheet_title=connection.title,
            tab=THESIS_WATCH_TAB,
            contract_version=THESIS_WATCH_CONTRACT_VERSION,
            content_fingerprint=fingerprint,
            published_at=now,
            row_count=len(combined),
            added_count=len(additions),
            trigger_ids=[row[0] for row in additions],
            read_back_verified=True,
            message=(
                f"Published {len(additions)} new trigger context row(s); "
                "earlier rows remain intact."
            ),
        )


def publish_thesis_watch_feed(
    session: Session,
    settings: Settings,
    *,
    limit: int = 50,
    offset: int = 0,
    publisher: GoogleSheetsThesisWatchPublisher | None = None,
) -> s.GoogleSheetsThesisWatchPublishRead:
    writer = publisher or GoogleSheetsThesisWatchPublisher(settings)
    # Serialize app instances publishing to the same workbook. A retry then reads the
    # prior completed append and returns UNCHANGED instead of racing on the same rows.
    key_bytes = hashlib.sha256(f"thesis-watch-feed:{writer.spreadsheet_id}".encode()).digest()[:8]
    lock_key = int.from_bytes(key_bytes, byteorder="big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    return writer.publish_triggers(session, limit=limit, offset=offset)
