"""Bounded primary-source verification for the first real-data steward pilot.

This is deliberately one explicit issuer release profile, not a generic
crawler. A failed/changed document is never treated as confirmed evidence.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

if TYPE_CHECKING:
    from portfolio_api.data_universe_shadow import EvidencePackV1

UBER_Q3_2026_URL = (
    "https://investor.uber.com/news-events/news/press-release-details/2026/"
    "Uber-Announces-Results-for-Third-Quarter-2026/default.aspx"
)
MAX_ISSUER_BYTES = 2_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class _ReleaseHTML(HTMLParser):
    """Capture visible text and table cells without interpreting HTML as instructions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._depth = 0
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._hidden += 1
            return
        if self._hidden:
            return
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._table = []
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg") and self._hidden:
            self._hidden -= 1
            return
        if self._hidden:
            return
        if self._depth == 1 and tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append(_normalize("".join(self._cell)))
            self._cell = None
        elif self._depth == 1 and tag == "tr":
            if self._table is not None and self._row is not None:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            if self._depth == 1 and self._table is not None:
                self.tables.append(self._table)
                self._table = None
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self.visible.append(data)
            if self._cell is not None:
                self._cell.append(data)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _million_values(row: list[str]) -> tuple[int, int]:
    # Only two unambiguous four-plus-digit values, excluding percent columns.
    values = [
        int(token.replace(",", ""))
        for cell in row[1:]
        for token in re.findall(r"(?<!\d)\d{1,3}(?:,\d{3})+(?!\d)", cell)
    ]
    if len(values) != 2:
        raise ValueError("Issuer table does not identify exact prior/current millions")
    return values[0], values[1]


def extract_uber_q3_2026(html: bytes) -> tuple[int, int, Decimal, Decimal]:
    """Extract only the Q3 operating table and separately labeled Q4 outlook."""
    if not html or len(html) > MAX_ISSUER_BYTES:
        raise ValueError("Issuer HTML exceeds the verified source byte budget")
    parser = _ReleaseHTML()
    parser.feed(html.decode("utf-8", errors="strict"))
    text = _normalize(" ".join(parser.visible))
    if (
        "Uber Announces Results for Third Quarter 2026" not in text
        or not re.search(r"November\s+0?4,\s+2026\b", text)
        or "Financial and Operational Highlights for Third Quarter 2026" not in text
        or not re.search(r"In millions, except percentages", text, re.I)
    ):
        raise ValueError("Issuer, release date or table units could not be established")

    candidates: list[tuple[int, int]] = []
    for table in parser.tables:
        year_headers = [cell for row in table[:6] for cell in row if cell in ("2025", "2026")]
        if "2025" not in year_headers or "2026" not in year_headers:
            continue
        trips = [row for row in table if row and row[0] == "Trips"]
        bookings = [row for row in table if row and row[0] == "Gross Bookings"]
        if trips and bookings:
            if year_headers.index("2025") >= year_headers.index("2026"):
                raise ValueError("Issuer operating table fiscal-year columns reversed")
            if len(trips) != 1 or len(bookings) != 1:
                raise ValueError("Duplicate company operating rows in issuer table")
            old_trips, current_trips = _million_values(trips[0])
            old_bookings, current_bookings = _million_values(bookings[0])
            if old_trips <= 0 or old_bookings <= 0:
                raise ValueError("Issuer table lacks an identifiable prior-year column")
            candidates.append((current_trips, current_bookings))
    if len(candidates) != 1:
        raise ValueError("Issuer operating table missing or ambiguous")

    start = text.find("Outlook for Q4 2026")
    end = text.find("Financial and Operational Highlights for Third Quarter 2026", start)
    if start < 0 or end <= start:
        raise ValueError("Issuer Q4 outlook section could not be isolated")
    outlook = text[start:end]
    ranges = re.findall(
        r"Gross Bookings of \$\s*(\d+(?:\.\d+)?)\s*billion\s+to\s+"
        r"\$\s*(\d+(?:\.\d+)?)\s*billion",
        outlook,
        re.I,
    )
    if len(ranges) != 1:
        raise ValueError("Issuer Gross Bookings guidance missing or ambiguous")
    return (
        candidates[0][0],
        candidates[0][1],
        Decimal(ranges[0][0]) * 1000,
        Decimal(ranges[0][1]) * 1000,
    )


def verify_uber_q3_2026_pack(pack: EvidencePackV1, html: bytes) -> dict[str, Any]:
    """Fail closed if the reviewed proposal pack disagrees with public issuer text."""
    if (
        pack.issuer_ticker != "UBER"
        or pack.source_reference != UBER_Q3_2026_URL
        or pack.source_published_on != date(2026, 11, 4)
    ):
        raise ValueError("Unsupported issuer profile or source identity")
    definitions = {row.metric_key: row for row in pack.metric_definitions}
    actuals = {row.metric_key: row for row in pack.kpi_observations}
    if (
        len(definitions) != 2
        or set(definitions) != {"uber.trips", "uber.gross_bookings"}
        or len(actuals) != 2
        or set(actuals) != set(definitions)
        or len(pack.guidance_observations) != 1
    ):
        raise ValueError("Issuer pilot pack requires exactly two actuals and one guidance")
    trips, bookings, lower, upper = extract_uber_q3_2026(html)
    for metric, expected, unit, currency in (
        ("uber.trips", trips, "trips", None),
        ("uber.gross_bookings", bookings, "currency", "USD"),
    ):
        item = actuals[metric]
        definition = definitions[metric]
        if (
            item.value != Decimal(expected)
            or item.period_type != "QUARTER"
            or item.period_start != date(2026, 7, 1)
            or item.period_end != date(2026, 9, 30)
            or item.fiscal_year != 2026
            or item.fiscal_quarter != 3
            or item.unit != unit
            or item.scale != Decimal("1000000")
            or item.currency != currency
            or item.value_qualifier != "EQ"
            or item.basis != "REPORTED"
            or item.quality_status != "VERIFIED"
            or item.source_type != "EARNINGS_RELEASE"
            or item.scope_json
            or item.reported_at is not None
            or definition.category != "OPERATING"
            or definition.value_kind != ("CURRENCY" if currency else "COUNT")
            or definition.aggregation_semantics != "PERIOD_FLOW"
            or definition.default_basis != "REPORTED"
            or definition.scope_dimensions
            or not definition.actuals_allowed
            or definition.guidance_allowed != bool(currency)
            or definition.canonical_unit != unit
            or definition.canonical_scale != Decimal("1000000")
            or definition.default_period_type != "QUARTER"
            or definition.currency_policy != ("REQUIRED" if currency else "NONE")
        ):
            raise ValueError(f"Issuer fact or period/unit mismatch for {metric}")
    guidance = pack.guidance_observations[0]
    if (
        guidance.metric_key != "uber.gross_bookings"
        or guidance.lower_value != lower
        or guidance.upper_value != upper
        or guidance.midpoint_value is not None
        or guidance.period_type != "QUARTER"
        or guidance.period_start != date(2026, 10, 1)
        or guidance.period_end != date(2026, 12, 31)
        or guidance.fiscal_year != 2026
        or guidance.fiscal_quarter != 4
        or guidance.unit != "currency"
        or guidance.scale != Decimal("1000000")
        or guidance.currency != "USD"
        or guidance.basis != "COMPANY_GUIDANCE"
        or guidance.source_type != "EARNINGS_RELEASE"
        or guidance.scope_json
        or guidance.value_qualifier != "RANGE"
        or guidance.issued_at is not None
        or guidance.status != "ACTIVE"
    ):
        raise ValueError("Issuer Q4 guidance period, range or unit mismatch")
    if any(
        item.source_reference != UBER_Q3_2026_URL
        for item in (
            *pack.metric_definitions,
            *pack.kpi_observations,
            *pack.guidance_observations,
        )
    ):
        raise ValueError("Issuer pack includes facts from an unverified source")
    return {
        "status": "SOURCE_MATCHED",
        "profile": "UBER_Q3_2026_IR",
        "source_reference": UBER_Q3_2026_URL,
        "source_sha256": hashlib.sha256(html).hexdigest(),
        "checked_at": datetime.now(UTC).isoformat(),
        "facts_checked": [
            "uber.trips:2026Q3",
            "uber.gross_bookings:2026Q3",
            "uber.gross_bookings:2026Q4_GUIDANCE",
        ],
    }


def verify_official_uber_release(pack: EvidencePackV1) -> dict[str, Any]:
    """Exactly one bounded public issuer GET; no redirects, cookies or secrets."""
    if pack.issuer_ticker != "UBER" or pack.source_reference != UBER_Q3_2026_URL:
        raise ValueError("Live verification supports the approved Uber Q3 2026 URL only")
    req = Request(
        UBER_Q3_2026_URL,
        method="GET",
        headers={
            "Accept": "text/html",
            "User-Agent": "PortfolioResearch/1.0 (manual primary-source verification)",
        },
    )
    try:
        with build_opener(_NoRedirect).open(req, timeout=15) as response:
            if response.status != 200 or response.headers.get_content_type() != "text/html":
                raise ValueError("Issuer did not return a valid HTML release")
            raw = response.read(MAX_ISSUER_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError("Primary issuer GET unavailable; no evidence was verified") from error
    return verify_uber_q3_2026_pack(pack, raw)
