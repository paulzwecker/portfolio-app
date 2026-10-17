"""Manual, allowlisted publication of canonical portfolio state to Google Sheets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.settings import REPOSITORY_PATH, Settings

SHEETS_WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
PORTFOLIO_STATE_TAB = "Application Portfolio State"
PORTFOLIO_STATE_MARKER = "PORTFOLIO_RESEARCH_APPLICATION_STATE"
PORTFOLIO_STATE_CONTRACT_VERSION = "1.0.0"
MAX_STATE_ROWS = 5000

PORTFOLIO_STATE_COLUMNS = (
    "record_type",
    "portfolio_id",
    "portfolio_name",
    "portfolio_currency",
    "holdings_snapshot_id",
    "holdings_effective_at",
    "holdings_recorded_at",
    "holdings_completeness",
    "holdings_source",
    "holdings_actor",
    "holdings_reason",
    "holdings_freshness",
    "holdings_age_days",
    "valuation_mode",
    "valuation_as_of",
    "valuation_status",
    "portfolio_market_value",
    "valuation_currency",
    "market_data_through",
    "fx_data_through",
    "target_revision_id",
    "target_effective_at",
    "target_recorded_at",
    "target_accepted_at",
    "target_source",
    "target_actor",
    "target_reason",
    "company_id",
    "company_name",
    "lifecycle",
    "security_id",
    "security_name",
    "listing_id",
    "ticker",
    "venue",
    "listing_currency",
    "quantity",
    "cash_currency",
    "cash_balance",
    "price",
    "price_market_date",
    "price_observed_at",
    "price_currency",
    "price_freshness",
    "valuation_sync_status",
    "fx_rate",
    "fx_effective_at",
    "native_market_value",
    "base_market_value",
    "current_weight",
    "target_weight",
    "target_state",
    "allocation_gap",
    "availability_status",
)


class PortfolioSheetPublishError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SheetConnection:
    title: str
    sheet_ids: dict[str, int]
    sheet_dimensions: dict[str, tuple[int, int]]


@dataclass(frozen=True)
class PublishedPortfolioState:
    status: str
    spreadsheet_id: str
    spreadsheet_title: str
    tab: str
    portfolio_id: UUID
    contract_version: str
    content_fingerprint: str
    published_at: datetime
    valuation_as_of: datetime | None
    valuation_status: str
    row_count: int
    read_back_verified: bool
    message: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _date(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _empty_row(record_type: str) -> dict[str, object]:
    return {column: None for column in PORTFOLIO_STATE_COLUMNS} | {"record_type": record_type}


def build_portfolio_state_rows(overview: s.PortfolioOverview) -> list[dict[str, object]]:
    """Flatten the canonical API result without recalculating any portfolio values."""
    portfolio = overview.portfolio
    snapshot = overview.snapshot
    target = overview.target_revision
    common: dict[str, object] = {
        "portfolio_id": str(portfolio.id),
        "portfolio_name": portfolio.name,
        "portfolio_currency": portfolio.base_currency,
        "holdings_snapshot_id": str(snapshot.id) if snapshot else None,
        "holdings_effective_at": _date(snapshot.effective_at) if snapshot else None,
        "holdings_recorded_at": _date(snapshot.recorded_at) if snapshot else None,
        "holdings_completeness": snapshot.completeness if snapshot else "NO_SNAPSHOT",
        "holdings_source": snapshot.source if snapshot else None,
        "holdings_actor": snapshot.actor if snapshot else None,
        "holdings_reason": snapshot.reason if snapshot else None,
        "holdings_freshness": overview.holdings_freshness,
        "holdings_age_days": overview.holdings_age_days,
        "valuation_mode": overview.valuation_mode,
        "valuation_as_of": _date(overview.valuation_as_of),
        "valuation_status": overview.valuation_status,
        "portfolio_market_value": overview.base_market_value,
        "valuation_currency": overview.valuation_currency,
        "market_data_through": _date(overview.market_data_through),
        "fx_data_through": _date(overview.fx_data_through),
        "target_revision_id": str(target.id) if target else None,
        "target_effective_at": _date(target.effective_at) if target else None,
        "target_recorded_at": _date(target.recorded_at) if target else None,
        "target_accepted_at": _date(target.accepted_at) if target else None,
        "target_source": target.source if target else None,
        "target_actor": target.actor if target else None,
        "target_reason": target.reason if target else None,
    }
    rows: list[dict[str, object]] = [_empty_row("PORTFOLIO") | common]

    for company_context in overview.companies:
        company = company_context.company
        allocation = (
            _empty_row("COMPANY_ALLOCATION")
            | common
            | {
                "company_id": str(company.id),
                "company_name": company.name,
                "lifecycle": company.lifecycle,
                "base_market_value": company_context.current_market_value,
                "current_weight": company_context.current_weight,
                "target_weight": company_context.target_weight,
                "target_state": "AUTHORED"
                if company_context.target_weight is not None
                else "MISSING",
                "allocation_gap": company_context.allocation_gap,
                "availability_status": company_context.allocation_status,
            }
        )
        rows.append(allocation)
        for position in company_context.positions:
            rows.append(
                _empty_row("POSITION")
                | common
                | {
                    "company_id": str(company.id),
                    "company_name": company.name,
                    "lifecycle": company.lifecycle,
                    "security_id": str(position.security_id),
                    "security_name": position.security_name,
                    "listing_id": str(position.listing_id),
                    "ticker": position.ticker,
                    "venue": position.venue,
                    "listing_currency": position.currency,
                    "quantity": position.quantity,
                    "price": position.latest_price,
                    "price_market_date": _date(position.price_date),
                    "price_observed_at": _date(position.price_observed_at),
                    "price_currency": position.price_currency,
                    "price_freshness": position.price_freshness,
                    "valuation_sync_status": position.valuation_sync_status,
                    "fx_rate": position.fx_rate,
                    "fx_effective_at": _date(position.fx_effective_at),
                    "native_market_value": position.native_market_value,
                    "base_market_value": position.base_market_value,
                    "current_weight": position.portfolio_weight,
                    "availability_status": position.valuation_status,
                }
            )

    for position in overview.standalone_positions:
        rows.append(
            _empty_row("POSITION")
            | common
            | {
                "security_id": str(position.security_id),
                "security_name": position.security_name,
                "listing_id": str(position.listing_id),
                "ticker": position.ticker,
                "venue": position.venue,
                "listing_currency": position.currency,
                "quantity": position.quantity,
                "price": position.latest_price,
                "price_market_date": _date(position.price_date),
                "price_observed_at": _date(position.price_observed_at),
                "price_currency": position.price_currency,
                "price_freshness": position.price_freshness,
                "valuation_sync_status": position.valuation_sync_status,
                "fx_rate": position.fx_rate,
                "fx_effective_at": _date(position.fx_effective_at),
                "native_market_value": position.native_market_value,
                "base_market_value": position.base_market_value,
                "current_weight": position.portfolio_weight,
                "availability_status": position.valuation_status,
            }
        )

    for cash in overview.cash_valuations:
        rows.append(
            _empty_row("CASH")
            | common
            | {
                "cash_currency": cash.currency,
                "cash_balance": cash.balance,
                "fx_rate": cash.fx_rate,
                "fx_effective_at": _date(cash.fx_effective_at),
                "base_market_value": cash.base_market_value,
                "current_weight": cash.portfolio_weight,
                "availability_status": cash.valuation_status,
            }
        )
    return rows


def _cells(values: list[str | None]) -> list[dict[str, object]]:
    return [{"userEnteredValue": {"stringValue": value or ""}} for value in values]


def _column_name(index: int) -> str:
    result = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_table(
    overview: s.PortfolioOverview,
    published_at: datetime,
) -> tuple[list[list[str | None]], str, int]:
    rows = build_portfolio_state_rows(overview)
    manifest: list[list[str | None]] = [
        ["contract_marker", PORTFOLIO_STATE_MARKER],
        ["contract_version", PORTFOLIO_STATE_CONTRACT_VERSION],
        ["content_fingerprint", ""],
        ["published_at", published_at.astimezone(UTC).isoformat()],
        ["valuation_as_of", _date(overview.valuation_as_of)],
        ["record_count", str(len(rows))],
    ]
    table: list[list[str | None]] = manifest + [[None] * len(PORTFOLIO_STATE_COLUMNS)]
    table.append(list(PORTFOLIO_STATE_COLUMNS))
    for row in rows:
        table.append(
            [
                None if row[column] is None else str(row[column])
                for column in PORTFOLIO_STATE_COLUMNS
            ]
        )
    # The request-time cutoff changes on every read. Source observation times and freshness are
    # fingerprinted; the cutoff is kept in the contract as the time of the last publication.
    valuation_column = PORTFOLIO_STATE_COLUMNS.index("valuation_as_of")
    valuation_mode_column = PORTFOLIO_STATE_COLUMNS.index("valuation_mode")
    holdings_age_column = PORTFOLIO_STATE_COLUMNS.index("holdings_age_days")
    holdings_freshness_column = PORTFOLIO_STATE_COLUMNS.index("holdings_freshness")
    fingerprint_rows = [list(row) for row in table]
    fingerprint_rows[3][1] = None
    fingerprint_rows[4][1] = None
    for fingerprint_row in fingerprint_rows[8:]:
        fingerprint_row[valuation_column] = None
        fingerprint_row[valuation_mode_column] = None
        fingerprint_row[holdings_age_column] = None
        fingerprint_row[holdings_freshness_column] = None
    fingerprint = "sha256:" + _sha256(
        _canonical_json(
            {
                "contract_version": PORTFOLIO_STATE_CONTRACT_VERSION,
                "columns": PORTFOLIO_STATE_COLUMNS,
                "rows": fingerprint_rows,
            }
        )
    )
    table[2][1] = fingerprint
    return table, fingerprint, len(rows)


def portfolio_state_fingerprint(overview: s.PortfolioOverview) -> str:
    """Return the published portfolio-state fingerprint for an API overview."""
    published_at = overview.valuation_as_of or datetime.now(UTC)
    return _sheet_table(overview, published_at)[1]


class GoogleSheetsPortfolioPublisher:
    """Google Sheets writer base used by fixed, allowlisted application publishers."""

    def __init__(self, settings: Settings, session: Any | None = None) -> None:
        if not settings.google_sheets_spreadsheet_id:
            raise PortfolioSheetPublishError(
                "NOT_CONFIGURED", "Set GOOGLE_SHEETS_SPREADSHEET_ID", status=503
            )
        credential_path = settings.google_sheets_service_account_file
        if credential_path is None:
            raise PortfolioSheetPublishError(
                "CREDENTIALS_NOT_CONFIGURED",
                "Set GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE for application-owned Sheets publication",
                status=503,
            )
        credential_path = credential_path.expanduser().resolve()
        if credential_path.is_relative_to(REPOSITORY_PATH.resolve()):
            raise PortfolioSheetPublishError(
                "CREDENTIALS_IN_REPOSITORY",
                "Keep the Google credential outside the repository",
                status=503,
            )
        if not credential_path.is_file():
            raise PortfolioSheetPublishError(
                "CREDENTIAL_FILE_MISSING",
                "The configured Google service-account file is missing",
                status=503,
            )
        self.spreadsheet_id = settings.google_sheets_spreadsheet_id
        self.timeout = settings.google_sheets_request_timeout_seconds
        if session is None:
            try:
                from google.auth.transport.requests import AuthorizedSession
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    str(credential_path), scopes=[SHEETS_WRITE_SCOPE]
                )  # type: ignore[no-untyped-call]
                session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
            except Exception as error:
                raise PortfolioSheetPublishError(
                    "CREDENTIAL_INVALID",
                    "The Google service-account credential could not load",
                    status=503,
                ) from error
        self.session = session

    def _request(
        self, method: str, url: str, body: dict[str, object] | None = None
    ) -> dict[str, Any]:
        try:
            response = getattr(self.session, method)(url, json=body, timeout=(5, self.timeout))
        except Exception as error:
            raise PortfolioSheetPublishError(
                "NETWORK_ERROR", f"Google Sheets request failed ({type(error).__name__})"
            ) from error
        if response.status_code >= 400:
            if response.status_code in {401, 403}:
                raise PortfolioSheetPublishError(
                    "WORKBOOK_WRITE_FORBIDDEN",
                    "Google rejected the writer credential or workbook permission. "
                    "Share the configured workbook with the service account as an "
                    "Editor to publish.",
                    status=403,
                )
            if response.status_code == 404:
                raise PortfolioSheetPublishError(
                    "WORKBOOK_NOT_FOUND",
                    "The configured workbook was not found or is not shared with "
                    "the service account",
                    status=404,
                )
            if response.status_code == 429:
                raise PortfolioSheetPublishError(
                    "RATE_LIMITED",
                    "Google Sheets API rate limit reached; retry after a short delay",
                    status=429,
                )
            raise PortfolioSheetPublishError(
                "GOOGLE_API_ERROR", f"Google Sheets API returned HTTP {response.status_code}"
            )
        try:
            result = response.json()
        except (TypeError, ValueError) as error:
            raise PortfolioSheetPublishError(
                "INVALID_RESPONSE", "Google Sheets returned invalid JSON"
            ) from error
        if not isinstance(result, dict):
            raise PortfolioSheetPublishError(
                "INVALID_RESPONSE", "Google Sheets returned an invalid response"
            )
        return result

    def _url(self, suffix: str = "") -> str:
        return f"{SHEETS_API}/{quote(self.spreadsheet_id, safe='')}{suffix}"

    def connection(self) -> SheetConnection:
        result = self._request(
            "get",
            self._url(
                "?fields=spreadsheetId,properties(title),"
                "sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))"
            ),
        )
        if result.get("spreadsheetId") != self.spreadsheet_id:
            raise PortfolioSheetPublishError(
                "SPREADSHEET_MISMATCH", "Google returned a different workbook", status=502
            )
        properties = result.get("properties")
        title = properties.get("title") if isinstance(properties, dict) else None
        sheet_ids: dict[str, int] = {}
        sheet_dimensions: dict[str, tuple[int, int]] = {}
        for sheet in result.get("sheets", []):
            props = sheet.get("properties") if isinstance(sheet, dict) else None
            if (
                isinstance(props, dict)
                and isinstance(props.get("title"), str)
                and isinstance(props.get("sheetId"), int)
            ):
                sheet_ids[props["title"]] = props["sheetId"]
                grid = props.get("gridProperties")
                if isinstance(grid, dict):
                    rows = grid.get("rowCount")
                    columns = grid.get("columnCount")
                    if isinstance(rows, int) and isinstance(columns, int):
                        sheet_dimensions[props["title"]] = (rows, columns)
        if not isinstance(title, str):
            raise PortfolioSheetPublishError(
                "INVALID_RESPONSE", "Google returned no workbook title"
            )
        return SheetConnection(title, sheet_ids, sheet_dimensions)

    def _add_owned_tab(self) -> int:
        result = self._request(
            "post",
            self._url(":batchUpdate"),
            {
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": PORTFOLIO_STATE_TAB,
                                "gridProperties": {
                                    "rowCount": MAX_STATE_ROWS,
                                    "columnCount": len(PORTFOLIO_STATE_COLUMNS),
                                },
                            }
                        }
                    }
                ]
            },
        )
        replies = result.get("replies")
        if isinstance(replies, list) and replies:
            added = replies[0].get("addSheet") if isinstance(replies[0], dict) else None
            properties = added.get("properties") if isinstance(added, dict) else None
            sheet_id = properties.get("sheetId") if isinstance(properties, dict) else None
            if isinstance(sheet_id, int):
                return sheet_id
        raise PortfolioSheetPublishError(
            "INVALID_RESPONSE", "Google did not return the new application-owned tab identity"
        )

    def _read_owned_area(self, row_count: int, column_count: int) -> list[list[object]]:
        last_row = min(MAX_STATE_ROWS, max(1, row_count))
        last_column = _column_name(min(len(PORTFOLIO_STATE_COLUMNS), max(1, column_count)) - 1)
        cell_range = quote(f"'{PORTFOLIO_STATE_TAB}'!A1:{last_column}{last_row}", safe="!:$'")
        result = self._request(
            "get",
            self._url(
                f"/values/{cell_range}?majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
            ),
        )
        values = result.get("values", [])
        if not isinstance(values, list):
            raise PortfolioSheetPublishError(
                "INVALID_RESPONSE", "Google returned invalid portfolio tab values"
            )
        return values

    @staticmethod
    def _padded(row: object, width: int) -> list[str | None]:
        if not isinstance(row, list):
            return [None] * width
        values: list[str | None] = []
        for value in row[:width]:
            values.append(None if value is None or value == "" else str(value))
        return values + [None] * (width - len(values))

    @classmethod
    def _matches_published_table(
        cls,
        expected: list[list[str | None]],
        actual: list[list[object]],
    ) -> bool:
        width = len(PORTFOLIO_STATE_COLUMNS)
        if len(actual) < len(expected):
            return False
        expected_rows = [cls._padded(row, width) for row in expected]
        actual_rows = [cls._padded(row, width) for row in actual[: len(expected)]]
        valuation_column = PORTFOLIO_STATE_COLUMNS.index("valuation_as_of")
        for rows in (expected_rows, actual_rows):
            rows[3][1] = None
            rows[4][1] = None
            for data_row in rows[8:]:
                data_row[valuation_column] = None
        unexpected_tail = any(
            any(value is not None for value in cls._padded(row, width))
            for row in actual[len(expected) :]
        )
        return actual_rows == expected_rows and not unexpected_tail

    def _write_table(
        self, sheet_id: int, table: list[list[str | None]], previous_row_count: int
    ) -> None:
        if len(table) > MAX_STATE_ROWS:
            raise PortfolioSheetPublishError(
                "STATE_TOO_LARGE",
                "Portfolio state exceeds the application tab row limit",
                status=413,
            )
        requests: list[dict[str, object]] = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "rowCount": max(1000, len(table)),
                            "columnCount": len(PORTFOLIO_STATE_COLUMNS),
                        },
                    },
                    "fields": "gridProperties.rowCount,gridProperties.columnCount",
                }
            },
            {
                "updateCells": {
                    "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                    "rows": [{"values": _cells(row)} for row in table],
                    "fields": "userEnteredValue",
                }
            },
        ]
        if previous_row_count > len(table):
            requests.append(
                {
                    "updateCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": len(table),
                            "endRowIndex": previous_row_count,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(PORTFOLIO_STATE_COLUMNS),
                        },
                        "fields": "userEnteredValue",
                    }
                }
            )
        try:
            self._request("post", self._url(":batchUpdate"), {"requests": requests})
        except PortfolioSheetPublishError as error:
            raise PortfolioSheetPublishError(
                "PUBLISH_FAILED",
                "Google rejected the portfolio-state batch write; the existing application "
                f"tab remains unchanged: {error}",
                status=error.status,
            ) from error

    def publish(self, overview: s.PortfolioOverview) -> PublishedPortfolioState:
        connection = self.connection()
        sheet_id = connection.sheet_ids.get(PORTFOLIO_STATE_TAB)
        created_tab = False
        if sheet_id is None:
            sheet_id = self._add_owned_tab()
            created_tab = True
            existing_values: list[list[object]] = []
        else:
            sheet_rows, sheet_columns = connection.sheet_dimensions.get(
                PORTFOLIO_STATE_TAB, (1000, 26)
            )
            existing_values = self._read_owned_area(sheet_rows, sheet_columns)
            nonempty = any(
                cell not in (None, "")
                for row in existing_values
                if isinstance(row, list)
                for cell in row
            )
            first_row = existing_values[0] if existing_values and existing_values[0] else []
            marker = first_row[1] if len(first_row) > 1 else None
            old_fingerprint = (
                existing_values[2][1]
                if len(existing_values) > 2 and len(existing_values[2]) > 1
                else None
            )
            if nonempty and (
                (not first_row or first_row[0] != "contract_marker")
                or marker != PORTFOLIO_STATE_MARKER
            ):
                raise PortfolioSheetPublishError(
                    "TARGET_TAB_NOT_OWNED",
                    f"The existing '{PORTFOLIO_STATE_TAB}' tab has content but is not "
                    "marked as application-owned; no workbook content was changed.",
                    status=409,
                )
            # A marker-only tab is permitted after a prior partial setup, but never overwrite
            # unrelated cells outside the fixed application-owned table columns.
            version_key = (
                existing_values[1][0] if len(existing_values) > 1 and existing_values[1] else None
            )
            version_value = (
                existing_values[1][1]
                if len(existing_values) > 1 and len(existing_values[1]) > 1
                else None
            )
            if marker == PORTFOLIO_STATE_MARKER and (
                version_key != "contract_version"
                or version_value != PORTFOLIO_STATE_CONTRACT_VERSION
            ):
                raise PortfolioSheetPublishError(
                    "TARGET_TAB_NOT_OWNED",
                    "The target tab ownership marker is malformed; no workbook content "
                    "was changed.",
                    status=409,
                )

        now = datetime.now(UTC)
        table, fingerprint, record_count = _sheet_table(overview, now)
        if not created_tab and old_fingerprint == fingerprint:
            if not self._matches_published_table(table, existing_values):
                raise PortfolioSheetPublishError(
                    "TARGET_CONTENT_MISMATCH",
                    "The application-owned tab no longer matches its published fingerprint; "
                    "no cells were changed. Republish after reviewing the tab contents.",
                    status=409,
                )
            published_value = (
                existing_values[3][1]
                if len(existing_values) > 3 and len(existing_values[3]) > 1
                else None
            )
            valuation_value = (
                existing_values[4][1]
                if len(existing_values) > 4 and len(existing_values[4]) > 1
                else None
            )
            return PublishedPortfolioState(
                status="UNCHANGED",
                spreadsheet_id=self.spreadsheet_id,
                spreadsheet_title=connection.title,
                tab=PORTFOLIO_STATE_TAB,
                portfolio_id=overview.portfolio.id,
                contract_version=PORTFOLIO_STATE_CONTRACT_VERSION,
                content_fingerprint=fingerprint,
                published_at=datetime.fromisoformat(str(published_value))
                if published_value
                else now,
                valuation_as_of=datetime.fromisoformat(str(valuation_value))
                if valuation_value
                else None,
                valuation_status=overview.valuation_status,
                row_count=record_count,
                read_back_verified=True,
                message="Canonical portfolio state is unchanged; no Sheet cells were written.",
            )

        previous_row_count = 0
        previous_count = (
            existing_values[5][1]
            if len(existing_values) > 5 and len(existing_values[5]) > 1
            else None
        )
        if isinstance(previous_count, (int, str)) and str(previous_count).isdigit():
            previous_row_count = 8 + int(previous_count)
        self._write_table(sheet_id, table, previous_row_count)
        last_column = _column_name(len(PORTFOLIO_STATE_COLUMNS) - 1)
        cell_range = quote(f"'{PORTFOLIO_STATE_TAB}'!A1:{last_column}{len(table)}", safe="!:$'")
        result = self._request(
            "get",
            self._url(
                f"/values/{cell_range}?majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
            ),
        )
        readback = result.get("values")
        if not isinstance(readback, list):
            raise PortfolioSheetPublishError(
                "READBACK_FAILED",
                "Portfolio state was written, but Google returned no read-back values",
            )
        expected = [[value or "" for value in row] for row in table]
        actual = [self._padded(row, len(PORTFOLIO_STATE_COLUMNS)) for row in readback]
        normalized_expected = [self._padded(row, len(PORTFOLIO_STATE_COLUMNS)) for row in expected]
        if actual != normalized_expected:
            raise PortfolioSheetPublishError(
                "READBACK_MISMATCH",
                "Portfolio state was written but its read-back did not match "
                "the published contract",
            )
        return PublishedPortfolioState(
            status="PUBLISHED",
            spreadsheet_id=self.spreadsheet_id,
            spreadsheet_title=connection.title,
            tab=PORTFOLIO_STATE_TAB,
            portfolio_id=overview.portfolio.id,
            contract_version=PORTFOLIO_STATE_CONTRACT_VERSION,
            content_fingerprint=fingerprint,
            published_at=now,
            valuation_as_of=overview.valuation_as_of,
            valuation_status=overview.valuation_status,
            row_count=record_count,
            read_back_verified=True,
            message="Canonical portfolio state was published and verified by read-back.",
        )


def publish_portfolio_state(
    session: Session,
    portfolio_id: UUID,
    settings: Settings,
    publisher: GoogleSheetsPortfolioPublisher | None = None,
) -> PublishedPortfolioState:
    overview = q.overview(session, portfolio_id)
    writer = publisher or GoogleSheetsPortfolioPublisher(settings)
    return writer.publish(overview)
