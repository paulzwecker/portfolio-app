"""Retrieve Item 2.02 announcements and their earnings exhibits from EDGAR."""

import json
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from portfolio_api.source_documents import SEC_ARCHIVES_BASE, SEC_SUBMISSIONS_BASE, _NoSecRedirects


@dataclass(frozen=True)
class Issuer:
    cik: str
    baseline: str
    baseline_date: date


# Public issuer crosswalk and last reviewed release for the initial cohort.
ISSUERS = {
    "NASDAQ:BKNG": Issuer("0001075531", "0001075531-26-000044", date(2026, 11, 3)),
    "NASDAQ:GOOGL": Issuer("0001652044", "0001652044-26-000080", date(2026, 10, 28)),
    "NASDAQ:AMZN": Issuer("0001018724", "0001018724-26-000038", date(2026, 10, 29)),
    "NYSE:MA": Issuer("0001141391", "0001141391-26-000122", date(2026, 10, 29)),
    "NASDAQ:MSFT": Issuer("0000789019", "0001193125-26-436122", date(2026, 10, 28)),
}


BASELINE_SOURCES = {
    "NASDAQ:AMZN": (
        "https://ir.aboutamazon.com/news-release/news-release-details/2026/Ama"
        "zon-com-Announces-Third-Quarter-Results/"
    ),
    "NASDAQ:BKNG": (
        "https://www.bookingholdings.com/wp-content/uploads/2026/11/Q3-26-BKNG"
        "-Earnings-Release-Final.pdf"
    ),
    "NASDAQ:GOOGL": (
        "https://abc.xyz/investor/events/event-details/2026/2026-Q3-Earnings-C"
        "all-2026-Ujou16CTw9/default.aspx"
    ),
    "NYSE:MA": (
        "https://investor.mastercard.com/files/content_files/3Q26-Mastercard-Earnings-Release.pdf"
    ),
    "NASDAQ:MSFT": ("https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1"),
}


@dataclass(frozen=True)
class Filing:
    accession: str
    filed: date
    folder: str


def fetch(url: str, user_agent: str) -> bytes:
    request = Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    with build_opener(_NoSecRedirects()).open(request, timeout=12) as response:
        result: bytes = response.read(8_000_001)
    if len(result) > 8_000_000:
        raise ValueError("SEC response exceeds the release size limit")
    return result


def announcements(listing: str, user_agent: str, *, baseline_reviewed: bool) -> list[Filing]:
    issuer = ISSUERS[listing]
    payload = json.loads(fetch(f"{SEC_SUBMISSIONS_BASE}/CIK{issuer.cik}.json", user_agent))
    identities = {
        f"{exchange.upper()}:{ticker}"
        for ticker, exchange in zip(payload["tickers"], payload["exchanges"], strict=True)
    }
    if listing not in identities or int(payload["cik"]) != int(issuer.cik):
        raise ValueError("SEC submissions identity differs from held listing")
    recent = payload["filings"]["recent"]
    result = []
    for form, items, accession, filed in zip(
        recent["form"],
        recent["items"],
        recent["accessionNumber"],
        recent["filingDate"],
        strict=True,
    ):
        day = date.fromisoformat(filed)
        if day < issuer.baseline_date or (baseline_reviewed and accession == issuer.baseline):
            continue
        if form not in {"8-K", "8-K/A"} or "2.02" not in re.split(r"[,;\s]+", items):
            continue
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise ValueError("Invalid SEC accession")
        folder = f"{SEC_ARCHIVES_BASE}/{int(issuer.cik)}/{accession.replace('-', '')}/"
        result.append(Filing(accession, day, folder))
    return sorted(result, key=lambda item: (item.filed, item.accession))


class ExhibitIndex(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cells: list[str] = []
        self.href = ""
        self.cell = False
        self.files: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.cells = []
            self.href = ""
        elif tag == "td":
            self.cell = True
            self.cells.append("")
        elif tag == "a" and self.cell:
            self.href = dict(attrs).get("href") or ""

    def handle_data(self, data: str) -> None:
        if self.cell:
            self.cells[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self.cell = False
        elif tag == "tr" and len(self.cells) >= 4 and self.cells[3].strip().startswith("EX-99"):
            self.files.append((" ".join(self.cells[1:4]), self.href))


class ExhibitText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"style", "script", "ix:header", "head"}:
            self.hidden += 1
        if tag in {"p", "tr", "td", "div", "br", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script", "ix:header", "head"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "td", "div", "tr", "li"}:
            self.parts.append(" ")


def release_text(filing: Filing, user_agent: str) -> tuple[str, str]:
    index = ExhibitIndex()
    index.feed(fetch(f"{filing.folder}{filing.accession}-index.htm", user_agent).decode("utf-8"))
    candidates = [
        item for item in index.files if re.search(r"earnings|press.release|results", item[0], re.I)
    ]
    if not candidates and len(index.files) == 1:
        candidates = index.files
    if len(candidates) != 1:
        raise ValueError("Earnings exhibit could not be identified uniquely")
    href = candidates[0][1]
    prefix = urlsplit(filing.folder).path
    filename = href.removeprefix(prefix)
    if not re.fullmatch(r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]*\.html?", filename, re.I):
        raise ValueError("Unexpected earnings exhibit path")
    url = filing.folder + filename
    parser = ExhibitText()
    parser.feed(fetch(url, user_agent).decode("utf-8"))
    body = " ".join("".join(parser.parts).split())
    if not re.search(r"quarter|financial results|year ended", body, re.I):
        raise ValueError("Exhibit does not contain identifiable financial results")
    return url, body
