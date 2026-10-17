"""Manual publication of bounded agent work to one application-owned Sheets tab."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.portfolio_sheet_sync import (
    MAX_STATE_ROWS as _MAX_STATE_ROWS,
)
from portfolio_api.portfolio_sheet_sync import (
    GoogleSheetsPortfolioPublisher,
    PortfolioSheetPublishError,
    _column_name,
)
from portfolio_api.settings import Settings

AGENT_WORK_FEED_TAB = "Application Agent Work Feed"
AGENT_WORK_FEED_MARKER = "PORTFOLIO_RESEARCH_AGENT_WORK_FEED"
AGENT_WORK_FEED_CONTRACT_VERSION = "1.0.0"
AGENT_WORK_FEED_COLUMNS = (
    "delivery_id",
    "agent_role",
    "work_type",
    "work_key",
    "work_fingerprint",
    "delivery_channel",
    "delivered_at",
    "current_status",
    "current_reason",
    "work_item_json",
)
MAX_WORK_ITEM_CELL_CHARS = 40_000
MAX_AGENT_WORK_ROWS = _MAX_STATE_ROWS


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manifest(now: datetime, fingerprint: str, count: int) -> list[list[str]]:
    return [
        ["contract_marker", AGENT_WORK_FEED_MARKER],
        ["contract_version", AGENT_WORK_FEED_CONTRACT_VERSION],
        ["content_fingerprint", fingerprint],
        ["published_at", now.astimezone(UTC).isoformat()],
        ["record_count", str(count)],
    ]


def _feed_fingerprint(rows: list[list[str]]) -> str:
    return "sha256:" + _sha256(_canonical([list(AGENT_WORK_FEED_COLUMNS), *rows]))


def _work_rows(contract: s.ResearchAgentWorkContractV1) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in contract.items:
        payload = _canonical(item.model_dump(mode="json"))
        if len(payload) > MAX_WORK_ITEM_CELL_CHARS:
            raise PortfolioSheetPublishError(
                "WORK_ITEM_TOO_LARGE",
                f"Work item {item.work_key} exceeds the safe Sheets cell limit; "
                "no cells were changed.",
                status=413,
            )
        rows.append(
            [
                str(item.delivery_id),
                contract.agent_role,
                item.work_type,
                item.work_key,
                item.work_fingerprint,
                item.delivery_channel,
                item.delivered_at.astimezone(UTC).isoformat(),
                item.current_status,
                item.current_reason or "",
                payload,
            ]
        )
    return rows


class GoogleSheetsAgentWorkPublisher(GoogleSheetsPortfolioPublisher):
    """Append-only writer restricted to Application Agent Work Feed."""

    @staticmethod
    def _normalize_rows(values: list[list[object]], width: int) -> list[list[str]]:
        rows = [
            ["" if value is None else str(value) for value in row[:width]]
            + [""] * max(0, width - len(row))
            for row in values
            if isinstance(row, list)
        ]
        while rows and not any(rows[-1]):
            rows.pop()
        return rows

    def _add_work_tab(self) -> int:
        result = self._request(
            "post",
            self._url(":batchUpdate"),
            {
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": AGENT_WORK_FEED_TAB,
                                "gridProperties": {
                                    "rowCount": MAX_AGENT_WORK_ROWS,
                                    "columnCount": len(AGENT_WORK_FEED_COLUMNS),
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
                "INVALID_RESPONSE", "Google did not return the agent work tab identity"
            )
        return sheet_id

    def _read_work_area(self, row_count: int) -> list[list[object]]:
        last_column = _column_name(len(AGENT_WORK_FEED_COLUMNS) - 1)
        end_row = min(MAX_AGENT_WORK_ROWS, max(1, row_count))
        cell_range = quote(
            f"'{AGENT_WORK_FEED_TAB}'!A1:{last_column}{end_row}",
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
                "INVALID_RESPONSE", "Google returned invalid agent work feed values"
            )
        return values

    def _write_rows(
        self,
        sheet_id: int,
        manifest: list[list[str]],
        additions: list[list[str]],
        old_count: int,
        new_table: list[list[str]],
    ) -> None:
        manifest_rows = [row + [""] * (len(AGENT_WORK_FEED_COLUMNS) - len(row)) for row in manifest]
        requests: list[dict[str, object]] = []
        if old_count == 0:
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
                            for row in new_table
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
                                "rowIndex": old_count + 8,
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

    def publish_work(
        self, contract: s.ResearchAgentWorkContractV1
    ) -> s.GoogleSheetsAgentWorkPublishRead:
        now = datetime.now(UTC)
        new_rows = _work_rows(contract)
        connection = self.connection()
        sheet_id = connection.sheet_ids.get(AGENT_WORK_FEED_TAB)
        created_tab = sheet_id is None
        old_values: list[list[object]] = []
        old_rows: list[list[str]] = []
        if created_tab:
            sheet_id = self._add_work_tab()
        else:
            assert sheet_id is not None
            dimensions = connection.sheet_dimensions.get(
                AGENT_WORK_FEED_TAB, (MAX_AGENT_WORK_ROWS, len(AGENT_WORK_FEED_COLUMNS))
            )
            old_values = self._read_work_area(dimensions[0])
            old_rows = self._normalize_rows(old_values, len(AGENT_WORK_FEED_COLUMNS))
            if any(value for row in old_rows for value in row):
                if (
                    len(old_rows) < 8
                    or old_rows[0][0] != "contract_marker"
                    or old_rows[0][1] != AGENT_WORK_FEED_MARKER
                    or old_rows[1][0] != "contract_version"
                    or old_rows[1][1] != AGENT_WORK_FEED_CONTRACT_VERSION
                    or old_rows[7] != list(AGENT_WORK_FEED_COLUMNS)
                ):
                    raise PortfolioSheetPublishError(
                        "TARGET_TAB_NOT_OWNED",
                        f"The existing '{AGENT_WORK_FEED_TAB}' tab is not a valid "
                        "application-owned feed; no workbook content was changed.",
                        status=409,
                    )
                try:
                    declared_count = int(old_rows[4][1])
                except (IndexError, ValueError):
                    declared_count = -1
                old_rows = old_rows[8:]
                if declared_count != len(old_rows) or any(
                    len(row) != len(AGENT_WORK_FEED_COLUMNS) or not row[0] for row in old_rows
                ):
                    raise PortfolioSheetPublishError(
                        "TARGET_CONTENT_MISMATCH",
                        "The agent work feed has an incomplete append history; "
                        "no workbook cells were changed.",
                        status=409,
                    )
                if old_rows and old_values[2][1] != _feed_fingerprint(old_rows):
                    raise PortfolioSheetPublishError(
                        "TARGET_CONTENT_MISMATCH",
                        "The agent work feed fingerprint does not match its rows; "
                        "no workbook cells were changed.",
                        status=409,
                    )

        by_delivery_id = {row[0]: row for row in old_rows}
        additions: list[list[str]] = []
        for row in new_rows:
            existing = by_delivery_id.get(row[0])
            if existing is None:
                additions.append(row)
                by_delivery_id[row[0]] = row
            elif existing[1:6] != row[1:6]:
                raise PortfolioSheetPublishError(
                    "DELIVERY_ID_CONFLICT",
                    "An existing delivery ID was reused for different work identity; "
                    "no cells were changed.",
                    status=409,
                )

        combined = old_rows + additions
        if len(combined) + 8 > MAX_AGENT_WORK_ROWS:
            raise PortfolioSheetPublishError(
                "FEED_TOO_LARGE",
                "The append-only agent work feed reached its row limit",
                status=413,
            )
        fingerprint = _feed_fingerprint(combined)
        if not additions and not created_tab:
            published_at_raw = (
                old_values[3][1] if len(old_values) > 3 and len(old_values[3]) > 1 else None
            )
            if not isinstance(published_at_raw, str):
                raise PortfolioSheetPublishError(
                    "TARGET_CONTENT_MISMATCH",
                    "The agent work feed publication time is missing or invalid.",
                    status=409,
                )
            published_at = datetime.fromisoformat(published_at_raw)
            return s.GoogleSheetsAgentWorkPublishRead(
                status="UNCHANGED",
                agent_role=contract.agent_role,
                spreadsheet_id=self.spreadsheet_id,
                spreadsheet_title=connection.title,
                tab=AGENT_WORK_FEED_TAB,
                contract_version=AGENT_WORK_FEED_CONTRACT_VERSION,
                content_fingerprint=fingerprint,
                published_at=published_at,
                row_count=len(old_rows),
                added_count=0,
                work_item_count=len(contract.items),
                read_back_verified=True,
                status_reason=contract.status_reason,
                message="No new delivery was appended; the existing work history remains intact.",
            )

        manifest = _manifest(now, fingerprint, len(combined))
        table = (
            [row + [""] * (len(AGENT_WORK_FEED_COLUMNS) - len(row)) for row in manifest]
            + [[""] * len(AGENT_WORK_FEED_COLUMNS)] * 2
            + [list(AGENT_WORK_FEED_COLUMNS)]
            + combined
        )
        assert sheet_id is not None
        self._write_rows(sheet_id, manifest, additions, len(old_rows), table)
        last_column = _column_name(len(AGENT_WORK_FEED_COLUMNS) - 1)
        cell_range = quote(f"'{AGENT_WORK_FEED_TAB}'!A1:{last_column}{len(table)}", safe="!:$'")
        readback = self._request(
            "get",
            self._url(
                f"/values/{cell_range}?majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
            ),
        ).get("values")
        if (
            not isinstance(readback, list)
            or self._normalize_rows(readback, len(AGENT_WORK_FEED_COLUMNS)) != table
        ):
            raise PortfolioSheetPublishError(
                "READBACK_MISMATCH", "Agent work feed write did not match its read-back"
            )
        return s.GoogleSheetsAgentWorkPublishRead(
            status="PUBLISHED",
            agent_role=contract.agent_role,
            spreadsheet_id=self.spreadsheet_id,
            spreadsheet_title=connection.title,
            tab=AGENT_WORK_FEED_TAB,
            contract_version=AGENT_WORK_FEED_CONTRACT_VERSION,
            content_fingerprint=fingerprint,
            published_at=now,
            row_count=len(combined),
            added_count=len(additions),
            work_item_count=len(contract.items),
            read_back_verified=True,
            status_reason=contract.status_reason,
            message=(
                f"Published {len(additions)} new work item(s) and verified the feed by read-back."
            ),
        )


def publish_agent_work_feed(
    session: Session,
    contract: s.ResearchAgentWorkContractV1,
    settings: Settings,
    publisher: GoogleSheetsAgentWorkPublisher | None = None,
) -> s.GoogleSheetsAgentWorkPublishRead:
    if not contract.items:
        return s.GoogleSheetsAgentWorkPublishRead(
            status=contract.status if contract.status in {"NO_WORK", "BLOCKED"} else "NO_WORK",
            agent_role=contract.agent_role,
            spreadsheet_id=settings.google_sheets_spreadsheet_id,
            spreadsheet_title=None,
            tab=AGENT_WORK_FEED_TAB,
            contract_version=AGENT_WORK_FEED_CONTRACT_VERSION,
            content_fingerprint=None,
            published_at=datetime.now(UTC),
            row_count=0,
            added_count=0,
            work_item_count=0,
            read_back_verified=False,
            status_reason=contract.status_reason,
            message=contract.status_reason or "No open agent work is available for this page.",
        )
    writer = publisher or GoogleSheetsAgentWorkPublisher(settings)
    lock_key = int.from_bytes(
        hashlib.sha256(f"agent-work-feed:{writer.spreadsheet_id}".encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )
    # A database-scoped lock serializes concurrent app instances before they read/append.
    # The write remains restricted to this fixed application-owned tab.
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    return writer.publish_work(contract)
