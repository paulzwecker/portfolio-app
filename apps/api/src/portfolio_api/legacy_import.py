"""Deterministic, explicit import of implemented domains from the legacy workbooks.

The importer reads cached OOXML cell values only. It never evaluates workbook formulas and
does not migrate valuation/model inputs, prices, FX, or market history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    Actor,
    CashPosition,
    Company,
    CurrentLifecycle,
    HoldingPosition,
    HoldingSnapshot,
    LegacyImportBatch,
    Lifecycle,
    LifecycleEvent,
    Listing,
    Portfolio,
    RankingDefinition,
    RankingEntry,
    RankingEntryStatus,
    RankingRun,
    RankingRunStatus,
    RankingType,
    ScoreAssessment,
    ScoreAssessmentStatus,
    ScoreDefinition,
    ScoreDimension,
    Security,
    TargetAllocation,
    TargetRevision,
    now,
)
from portfolio_api.settings import Settings

MAIN_BOOK = "Portfolio_Watchlist.xlsx"
MARKET_BOOK = "Market Data.xlsx"
NAMESPACE = UUID("7f861169-24c4-4af3-bf50-70bb4b0b8911")
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": SHEET_NS, "r": REL_NS, "p": PKG_REL_NS}


@dataclass(frozen=True)
class Cell:
    value: str | None = None
    kind: str | None = None
    formula: str | None = None


@dataclass
class Workbook:
    path: Path
    sha256: str
    sheets: dict[str, dict[str, Cell]]

    @classmethod
    def read(cls, path: Path, include: Callable[[str], bool]) -> Workbook:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            archive = ZipFile(path)
        except (BadZipFile, OSError) as error:
            raise ValueError(f"Cannot read workbook {path}: {error}") from error
        with archive:
            if "xl/workbook.xml" not in archive.namelist():
                raise ValueError(f"Not an OOXML workbook: {path}")
            strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                strings = [
                    "".join(node.text or "" for node in item.findall(".//m:t", NS))
                    for item in root.findall("m:si", NS)
                ]
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {item.attrib["Id"]: item.attrib["Target"] for item in rels}
            sheets: dict[str, dict[str, Cell]] = {}
            sheet_nodes = workbook.find("m:sheets", NS)
            for sheet in sheet_nodes if sheet_nodes is not None else []:
                name = sheet.attrib["name"]
                if not include(name):
                    continue
                relationship = sheet.attrib[f"{{{REL_NS}}}id"]
                target = targets[relationship]
                xml_path = posixpath.normpath(
                    target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
                )
                root = ET.fromstring(archive.read(xml_path))
                cells: dict[str, Cell] = {}
                for node in root.findall(".//m:sheetData/m:row/m:c", NS):
                    value_node = node.find("m:v", NS)
                    inline = node.find("m:is", NS)
                    formula = node.find("m:f", NS)
                    value = value_node.text if value_node is not None else None
                    kind = node.attrib.get("t")
                    if kind == "s" and value is not None:
                        value = strings[int(value)]
                    elif kind == "inlineStr" and inline is not None:
                        value = "".join(
                            text_node.text or "" for text_node in inline.findall(".//m:t", NS)
                        )
                    cells[node.attrib["r"]] = Cell(
                        value=value,
                        kind=kind,
                        formula=(formula.text or "") if formula is not None else None,
                    )
                sheets[name] = cells
        return cls(path=path, sha256=digest, sheets=sheets)

    def cell(self, sheet: str, address: str) -> Cell:
        return self.sheets.get(sheet, {}).get(address, Cell())

    def rows(self, sheet: str, first_row: int = 1) -> list[tuple[int, dict[str, Cell]]]:
        rows: dict[int, dict[str, Cell]] = {}
        for address, cell in self.sheets.get(sheet, {}).items():
            match = re.fullmatch(r"([A-Z]+)(\d+)", address)
            if match is None:
                continue
            row = int(match.group(2))
            if row < first_row:
                continue
            rows.setdefault(row, {})[match.group(1)] = cell
        return sorted(rows.items())


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    source: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "source": self.source,
            "message": self.message,
        }


@dataclass(frozen=True)
class CompanyRow:
    ticker: str
    name: str
    research_bucket: str | None
    current_weight: Decimal | None
    target_weight: Decimal | None
    lifecycle: Lifecycle | None
    source: str


@dataclass(frozen=True)
class ListingRow:
    listing_key: str
    canonical_ticker: str
    security_key: str
    underlying_security_key: str | None
    name: str
    ticker: str
    venue: str
    currency: str
    security_type: str
    share_class: str | None
    source: str


@dataclass(frozen=True)
class PositionRow:
    canonical_ticker: str
    listing_key: str
    listing_ticker: str
    venue: str
    quantity: Decimal | None
    source: str


@dataclass(frozen=True)
class CashRow:
    currency: str
    balance: Decimal | None
    source: str


@dataclass(frozen=True)
class ScoreRow:
    ticker: str
    dimension: ScoreDimension
    score: Decimal | None
    status: ScoreAssessmentStatus
    rationale: str
    source: str
    issue: str | None = None
    source_priority: int = 0


@dataclass(frozen=True)
class RankRow:
    ticker: str
    ranking_type: RankingType
    position: int | None
    status: RankingEntryStatus
    reason: str
    source: str


@dataclass
class ImportPlan:
    portfolio_workbook: Workbook
    market_workbook: Workbook
    observed_at: datetime
    source_digest: str
    companies: list[CompanyRow] = field(default_factory=list)
    listings: list[ListingRow] = field(default_factory=list)
    positions: list[PositionRow] = field(default_factory=list)
    cash: list[CashRow] = field(default_factory=list)
    scores: list[ScoreRow] = field(default_factory=list)
    rankings: dict[RankingType, list[RankRow]] = field(default_factory=dict)
    targets: dict[str, Decimal] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    source_position_count: int = 0
    source_target_count: int = 0
    source_rank_count: dict[str, int] = field(default_factory=dict)
    source_score_count: dict[str, int] = field(default_factory=dict)
    target_snapshot_total: Decimal | None = None
    base_currency: str | None = None
    holdings_partial: bool = False
    target_importable: bool = True

    @property
    def batch_id(self) -> UUID:
        return uuid5(NAMESPACE, f"batch:{self.source_digest}")

    def issue(self, code: str, severity: str, source: str, message: str) -> None:
        self.issues.append(Issue(code, severity, source, message))

    def source_ref(self, workbook: Workbook, sheet: str, cell: str) -> str:
        return f"{workbook.path.name}:{sheet}!{cell}#sha256:{workbook.sha256}"

    def report(self, applied: bool = False) -> dict[str, Any]:
        return {
            "status": "APPLIED" if applied else "DRY_RUN",
            "observed_at": self.observed_at.isoformat(),
            "effective_time_policy": (
                "The workbook has no documented observation timestamp. This timestamp records "
                "when the importer observed the workbook; it is not asserted as the original "
                "effective date of its values."
            ),
            "source_digest": self.source_digest,
            "sources": {
                self.portfolio_workbook.path.name: self.portfolio_workbook.sha256,
                self.market_workbook.path.name: self.market_workbook.sha256,
            },
            "counts": {
                "company_rows": len(self.companies),
                "listing_mappings": len(self.listings),
                "source_holding_positions": self.source_position_count,
                "migratable_holding_positions": len(self.positions),
                "native_cash_rows": len(self.cash),
                "target_allocations": len(self.targets),
                "score_assessments": len(self.scores),
                "ranking_entries": sum(len(entries) for entries in self.rankings.values()),
                "ranked_positions": sum(
                    item.status == RankingEntryStatus.RANKED
                    for entries in self.rankings.values()
                    for item in entries
                ),
                "by_score_dimension": self.source_score_count,
                "by_ranking_type": self.source_rank_count,
            },
            "score_coverage": {
                dimension.value: {
                    "assessment_rows_imported": sum(
                        item.dimension == dimension for item in self.scores
                    ),
                    "assessed": sum(
                        item.dimension == dimension
                        and item.status == ScoreAssessmentStatus.ASSESSED
                        for item in self.scores
                    ),
                    "invalid_null": sum(
                        item.dimension == dimension and item.status == ScoreAssessmentStatus.INVALID
                        for item in self.scores
                    ),
                    "no_assessment_in_snapshot": max(
                        0,
                        len(self.companies)
                        - sum(item.dimension == dimension for item in self.scores),
                    ),
                    "missing_semantics": (
                        "No assessment record is emitted for an absent/blank workbook value; "
                        "this report records the coverage gap without fabricating a score event."
                    ),
                }
                for dimension in ScoreDimension
            },
            "ranking_coverage": {
                ranking_type.value: {
                    status.value.lower(): sum(
                        item.status == status for item in self.rankings.get(ranking_type, [])
                    )
                    for status in RankingEntryStatus
                }
                for ranking_type in RankingType
            },
            "holdings": {
                "completeness": "PARTIAL" if self.holdings_partial else "COMPLETE",
                "base_currency": self.base_currency,
                "source_position_rows": self.source_position_count,
                "imported_position_rows": len(self.positions),
                "cash_rows": len(self.cash),
            },
            "targets": {
                "source_company_allocations": self.source_target_count,
                "imported_company_allocations": len(self.targets),
                "importable": self.target_importable,
                "company_weight_total": str(sum(self.targets.values(), Decimal(0))),
                "workbook_reported_total": (
                    str(self.target_snapshot_total)
                    if self.target_snapshot_total is not None
                    else None
                ),
            },
            "unresolved_issue_count": sum(issue.severity == "ERROR" for issue in self.issues),
            "issues": [issue.as_dict() for issue in self.issues],
        }


def _value(row: dict[str, Cell], column: str) -> str | None:
    cell = row.get(column, Cell())
    if cell.value is None:
        return None
    value = cell.value.strip()
    return value or None


def _decimal(value: str | None, source: str, plan: ImportPlan) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(value)
    except InvalidOperation:
        plan.issue("INVALID_DECIMAL", "ERROR", source, f"Could not parse numeric value {value!r}.")
        return None
    if not result.is_finite():
        plan.issue("INVALID_DECIMAL", "ERROR", source, f"Non-finite numeric value {value!r}.")
        return None
    return result


def _ticker_key(value: str) -> str:
    return value.strip().upper()


def _lifecycle(
    ticker: str,
    bucket: str | None,
    current: Decimal | None,
    target: Decimal | None,
    source: str,
    plan: ImportPlan,
) -> Lifecycle | None:
    active = (current is not None and current > 0) or (target is not None and target > 0)
    normalized = (bucket or "").strip().casefold()
    if active:
        if normalized not in {"", "portfolio"}:
            plan.issue(
                "PORTFOLIO_MEMBERSHIP_OVERRIDES_RESEARCH_BUCKET",
                "WARNING",
                source,
                f"{ticker} has a positive current/target weight and workbook code P; Portfolio "
                f"membership takes precedence over Research Bucket {bucket!r}, matching the "
                "Universe Registry lifecycle formula.",
            )
        return Lifecycle.PORTFOLIO
    if current is None or target is None:
        plan.issue(
            "LIFECYCLE_SOURCE_INCOMPLETE",
            "ERROR",
            source,
            f"{ticker} has a blank cached current/target weight; its non-portfolio "
            "lifecycle was not inferred.",
        )
        return None
    if normalized == "watchlist":
        return Lifecycle.WATCHLIST
    if normalized in {"candidate - high", "candidate - low"}:
        return Lifecycle.CANDIDATE
    if normalized == "drop":
        return Lifecycle.DROP
    if normalized in {"", "portfolio"}:
        plan.issue(
            "LIFECYCLE_SOURCE_INCOMPLETE",
            "ERROR" if current is None or target is None else "WARNING",
            source,
            f"{ticker} has no positive portfolio allocation or explicit non-portfolio bucket; "
            "missing weights remain null.",
        )
        return None
    plan.issue(
        "LIFECYCLE_UNMAPPED",
        "ERROR",
        source,
        f"{ticker} has unsupported Research Bucket {bucket!r}; lifecycle was not imported.",
    )
    return None


def _load_companies(plan: ImportPlan) -> dict[str, CompanyRow]:
    workbook = plan.portfolio_workbook
    companies: dict[str, CompanyRow] = {}
    for row_number, row in workbook.rows("Universe Registry", 5):
        ticker_value = _value(row, "A")
        if ticker_value is None:
            continue
        ticker = _ticker_key(ticker_value)
        source = plan.source_ref(workbook, "Universe Registry", f"A{row_number}:I{row_number}")
        name = _value(row, "B")
        if name is None:
            compounder_name = next(
                (
                    _value(score_row, "B")
                    for _, score_row in workbook.rows("Compounder Quality", 5)
                    if _ticker_key(_value(score_row, "A") or "") == ticker
                    and _value(score_row, "B") is not None
                ),
                None,
            )
            listing_name = next(
                (
                    _value(listing_row, "B")
                    for _, listing_row in plan.market_workbook.rows("Listings", 5)
                    if _ticker_key(_value(listing_row, "A") or "") == ticker
                    and _value(listing_row, "B") is not None
                ),
                None,
            )
            name = compounder_name or listing_name
            if name is None:
                plan.issue(
                    "COMPANY_NAME_MISSING",
                    "ERROR",
                    source,
                    f"{ticker} has no cached name in Universe Registry, Compounder Quality, "
                    "or Listings.",
                )
                continue
            name_source = (
                f"Compounder Quality!B exact ticker match for {ticker}"
                if compounder_name
                else f"Market Data Listings!B exact ticker match for {ticker}"
            )
            plan.issue(
                "COMPANY_NAME_FALLBACK",
                "WARNING",
                source,
                f"Universe Registry name cache was blank; exact-ticker name {name!r} "
                f"was read from {name_source}.",
            )
        if ticker in companies:
            plan.issue("DUPLICATE_COMPANY_KEY", "ERROR", source, f"Duplicate company key {ticker}.")
            continue
        current = _decimal(_value(row, "D"), source, plan)
        target = _decimal(_value(row, "F"), source, plan)
        if current is None or target is None:
            plan.issue(
                "ALLOCATION_MEMBERSHIP_UNRESOLVED",
                "WARNING",
                source,
                f"{ticker} has a blank cached current/target weight; blank was not "
                "converted to zero.",
            )
        bucket = _value(row, "C")
        lifecycle = _lifecycle(ticker, bucket, current, target, source, plan)
        companies[ticker] = CompanyRow(ticker, name, bucket, current, target, lifecycle, source)
    plan.companies = list(companies.values())
    return companies


def _security_type(basis: str | None) -> str | None:
    normalized = (basis or "").casefold()
    if "adr" in normalized or "depositary receipt" in normalized:
        return "ADR"
    if "preferred" in normalized:
        return "PREFERRED"
    if any(
        word in normalized
        for word in (
            "ordinary",
            "common stock",
            "local stock",
            "same currency",
            "class a",
            "class b",
        )
    ):
        return "COMMON_STOCK"
    return None


def _share_class(basis: str | None) -> str | None:
    match = re.search(r"\bclass\s+([A-Z0-9]+)\b", basis or "", re.IGNORECASE)
    return match.group(1).upper() if match else None


def _load_listings(plan: ImportPlan, companies: dict[str, CompanyRow]) -> dict[str, ListingRow]:
    workbook = plan.market_workbook
    listings: dict[str, ListingRow] = {}
    venue_identity: dict[tuple[str, str], str] = {}
    for row_number, row in workbook.rows("Listings", 5):
        raw_key = _value(row, "A")
        if raw_key is None:
            continue
        key = _ticker_key(raw_key)
        source = plan.source_ref(workbook, "Listings", f"A{row_number}:K{row_number}")
        status = (_value(row, "K") or "").upper()
        if status != "READY":
            plan.issue(
                "LISTING_MAPPING_UNRESOLVED",
                "ERROR",
                source,
                f"{key} listing status is {status or 'blank'}; no venue/ticker/currency "
                "mapping imported.",
            )
            continue
        symbol = _value(row, "C")
        venue = _value(row, "D")
        currency = _value(row, "E")
        name = _value(row, "B")
        kind = _security_type(_value(row, "G"))
        match = re.fullmatch(r"([^:]+):(.+)", symbol or "")
        if (
            match is None
            or venue is None
            or currency is None
            or not re.fullmatch(r"[A-Z]{3}", currency)
            or name is None
            or kind is None
        ):
            plan.issue(
                "LISTING_FIELDS_INCOMPLETE",
                "ERROR",
                source,
                f"{key} lacks a supported exact symbol, venue, quote currency, company name, or "
                "instrument basis.",
            )
            continue
        market_venue, listing_ticker = match.groups()
        if market_venue.casefold() != venue.casefold():
            plan.issue(
                "LISTING_VENUE_CONFLICT",
                "ERROR",
                source,
                f"Market Symbol venue {market_venue!r} disagrees with Exchange {venue!r}.",
            )
            continue
        if key not in companies:
            plan.issue(
                "LISTING_COMPANY_UNRESOLVED",
                "ERROR",
                source,
                f"Listing key {key} has no importable Universe Registry company.",
            )
            continue
        unique = (venue.upper(), listing_ticker.upper())
        existing = venue_identity.get(unique)
        if existing is not None and existing != key:
            plan.issue(
                "DUPLICATE_LISTING_IDENTITY",
                "ERROR",
                source,
                f"{venue}:{listing_ticker} maps to both {existing} and {key}.",
            )
            continue
        if key in listings:
            plan.issue(
                "DUPLICATE_LISTING_KEY", "ERROR", source, f"Duplicate listing mapping for {key}."
            )
            continue
        venue_identity[unique] = key
        listings[key] = ListingRow(
            listing_key=key,
            canonical_ticker=key,
            security_key=key,
            underlying_security_key=None,
            name=name,
            ticker=listing_ticker,
            venue=venue,
            currency=currency,
            security_type=kind,
            share_class=_share_class(_value(row, "G")),
            source=source,
        )
    # The Market Data Listings table intentionally omits fund coverage. The legacy Price Feed
    # row carries the exact ETR listing identity and quote currency for the current SPYY ETF.
    for row_number, row in plan.portfolio_workbook.rows("Price Feed", 5):
        if (_value(row, "A") or "").upper() != "AUX":
            continue
        key_value = _value(row, "C")
        if key_value is None:
            continue
        key = _ticker_key(key_value)
        if key not in {"SPYY", "TSM-ADR"}:
            continue
        symbol = _value(row, "D")
        currency = _value(row, "H")
        name = _value(row, "B")
        match = re.fullmatch(r"([^:]+):(.+)", symbol or "")
        if (
            match is None
            or currency is None
            or name is None
            or not re.fullmatch(r"[A-Z]{3}", currency)
        ):
            plan.issue(
                "AUX_LISTING_UNRESOLVED",
                "ERROR",
                f"Price Feed!A{row_number}:H{row_number}",
                f"{key} auxiliary fund row lacks an exact listing symbol or quote currency.",
            )
            continue
        venue, ticker = match.groups()
        if key == "SPYY":
            canonical_ticker = "SPYY"
            security_key = "ETF:SPYY"
            underlying_security_key = None
            kind = "ETF"
        else:
            canonical_ticker = "TSM"
            security_key = "TSM-ADR"
            underlying_security_key = "TSM"
            kind = "ADR"
        source = plan.source_ref(
            plan.portfolio_workbook, "Price Feed", f"B{row_number}:H{row_number}"
        )
        venue_identity_key = (venue.upper(), ticker.upper())
        existing_key = venue_identity.get(venue_identity_key)
        if existing_key is not None:
            plan.issue(
                "DUPLICATE_LISTING_IDENTITY",
                "ERROR",
                source,
                f"{venue}:{ticker} is already mapped as {existing_key}; the auxiliary "
                "row was not imported.",
            )
            continue
        listings[key] = ListingRow(
            listing_key=key,
            canonical_ticker=canonical_ticker,
            security_key=security_key,
            underlying_security_key=underlying_security_key,
            name=name,
            ticker=ticker,
            venue=venue,
            currency=currency,
            security_type=kind,
            share_class=None,
            source=source,
        )
        venue_identity[venue_identity_key] = key
    plan.listings = list(listings.values())
    return listings


def _load_holdings(
    plan: ImportPlan,
    companies: dict[str, CompanyRow],
    listings: dict[str, ListingRow],
) -> None:
    workbook = plan.portfolio_workbook
    total_currency = (
        _value(workbook.rows("Current Holdings")[3][1], "L")
        if len(workbook.rows("Current Holdings")) > 3
        else None
    )
    if total_currency:
        match = re.search(r"\b([A-Z]{3})\s*$", total_currency)
        plan.base_currency = match.group(1) if match else None
    if plan.base_currency is None:
        plan.issue(
            "PORTFOLIO_CURRENCY_UNRESOLVED",
            "ERROR",
            plan.source_ref(workbook, "Current Holdings", "L4"),
            "Could not resolve the portfolio base currency from the explicit EUR summary label.",
        )
    positions: list[PositionRow] = []
    cash: list[CashRow] = []

    def holding_listing(canonical_ticker: str, source_listing: str | None) -> ListingRow | None:
        if source_listing is not None:
            source_key = _ticker_key(source_listing)
            direct = listings.get(source_key)
            if direct is not None and direct.canonical_ticker == canonical_ticker:
                return direct
            matches = [
                listing
                for listing in listings.values()
                if listing.canonical_ticker == canonical_ticker
                and _ticker_key(listing.ticker) == source_key
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return None
        direct = listings.get(canonical_ticker)
        return (
            direct if direct is not None and direct.canonical_ticker == canonical_ticker else None
        )

    for row_number, row in workbook.rows("Current Holdings", 5):
        kind = (_value(row, "A") or "").strip().casefold()
        canonical = _value(row, "B")
        if kind == "stock":
            if canonical is None:
                plan.holdings_partial = True
                plan.issue(
                    "HOLDING_IDENTITY_MISSING",
                    "ERROR",
                    f"Current Holdings!A{row_number}:E{row_number}",
                    "Stock row has no canonical portfolio ticker.",
                )
                continue
            ticker = _ticker_key(canonical)
            source = plan.source_ref(workbook, "Current Holdings", f"A{row_number}:G{row_number}")
            quantity = _decimal(_value(row, "E"), source, plan)
            if quantity is None:
                plan.holdings_partial = True
            listing = holding_listing(ticker, _value(row, "D"))
            if ticker not in companies or listing is None:
                plan.holdings_partial = True
                plan.issue(
                    "HOLDING_LISTING_UNRESOLVED",
                    "ERROR",
                    source,
                    f"{ticker} holding has no fully mapped company and listing; position "
                    "was not invented.",
                )
                continue
            positions.append(
                PositionRow(
                    ticker, listing.listing_key, listing.ticker, listing.venue, quantity, source
                )
            )
        elif kind == "etf":
            plan.source_position_count += 1
            source = plan.source_ref(workbook, "Current Holdings", f"A{row_number}:G{row_number}")
            ticker = _ticker_key(canonical or "")
            listing = holding_listing(ticker, _value(row, "D"))
            if listing is None or listing.security_type != "ETF":
                plan.holdings_partial = True
                plan.issue(
                    "ETF_LISTING_UNRESOLVED",
                    "ERROR",
                    source,
                    f"{canonical or 'ETF'} has no exact exchange/venue mapping; no listing "
                    "was fabricated.",
                )
                continue
            quantity = _decimal(_value(row, "E"), source, plan)
            if quantity is None:
                plan.holdings_partial = True
            positions.append(
                PositionRow(
                    ticker, listing.listing_key, listing.ticker, listing.venue, quantity, source
                )
            )
        elif kind == "cash component":
            source = plan.source_ref(workbook, "Current Holdings", f"A{row_number}:G{row_number}")
            currency = _value(row, "G")
            if currency is None or not re.fullmatch(r"[A-Z]{3}", currency):
                plan.holdings_partial = True
                plan.issue(
                    "CASH_CURRENCY_UNRESOLVED",
                    "ERROR",
                    source,
                    "Native cash row has no supported ISO currency.",
                )
                continue
            balance = _decimal(_value(row, "E"), source, plan)
            if balance is None:
                plan.holdings_partial = True
            cash.append(CashRow(currency, balance, source))
    plan.source_position_count += sum(
        (_value(row, "A") or "").strip().casefold() == "stock"
        for _, row in workbook.rows("Current Holdings", 5)
    )
    if len({position.canonical_ticker for position in positions}) != len(positions):
        plan.holdings_partial = True
        plan.issue(
            "DUPLICATE_HOLDING",
            "ERROR",
            "Current Holdings!B5:E26",
            "A stock ticker appears more than once.",
        )
    if len({item.currency for item in cash}) != len(cash):
        plan.holdings_partial = True
        plan.issue(
            "DUPLICATE_CASH_CURRENCY",
            "ERROR",
            "Current Holdings!A28:G29",
            "Native cash currency appears more than once.",
        )
    plan.positions = positions
    plan.cash = cash


def _load_targets(plan: ImportPlan, companies: dict[str, CompanyRow]) -> None:
    workbook = plan.portfolio_workbook
    reported = _decimal(
        workbook.cell("Target Architecture", "P3").value,
        "Target Architecture!P3",
        plan,
    )
    plan.target_snapshot_total = reported
    targets: dict[str, Decimal] = {}
    reserve: Decimal | None = None
    for row_number, row in workbook.rows("Target Architecture", 5):
        raw_ticker = _value(row, "A")
        if raw_ticker is None:
            continue
        raw_weight = _value(row, "D")
        if raw_weight is None:
            plan.issue(
                "TARGET_VALUE_MISSING",
                "ERROR",
                f"Target Architecture!A{row_number}:D{row_number}",
                f"{raw_ticker} has a blank target; it remains null and is not converted to zero.",
            )
            plan.target_importable = False
            continue
        weight = _decimal(raw_weight, f"Target Architecture!D{row_number}", plan)
        if weight is None or not Decimal(0) <= weight <= Decimal(1):
            plan.issue(
                "TARGET_VALUE_INVALID",
                "ERROR",
                f"Target Architecture!D{row_number}",
                f"{raw_ticker} target is outside [0,1].",
            )
            plan.target_importable = False
            continue
        key = _ticker_key(raw_ticker)
        if key == "RESERVE":
            reserve = weight
            plan.issue(
                "RESERVE_TARGET_NOT_MODELED",
                "WARNING" if weight == 0 else "ERROR",
                f"Target Architecture!A{row_number}:D{row_number}",
                "The workbook combines cash and ETF reserve in RESERVE; the application "
                "only stores "
                "company targets. Zero is recorded in this report; a positive reserve "
                "blocks target import.",
            )
            if weight != 0:
                plan.target_importable = False
            continue
        if key not in companies:
            plan.issue(
                "TARGET_COMPANY_UNRESOLVED",
                "ERROR",
                f"Target Architecture!A{row_number}:D{row_number}",
                f"Target {key} has no importable company identity.",
            )
            plan.target_importable = False
            continue
        if key in targets:
            plan.issue(
                "DUPLICATE_TARGET",
                "ERROR",
                f"Target Architecture!A{row_number}:D{row_number}",
                f"Duplicate target for {key}.",
            )
            plan.target_importable = False
            continue
        targets[key] = weight
    plan.source_target_count = len(targets) + (1 if reserve is not None else 0)
    company_total = sum(targets.values(), Decimal(0))
    if company_total > 1:
        plan.issue(
            "TARGET_TOTAL_EXCEEDS_ONE",
            "ERROR",
            "Target Architecture!D5:D100",
            f"Company target weights sum to {company_total}; no normalization is applied.",
        )
        plan.target_importable = False
    if reported is not None and company_total + (reserve or Decimal(0)) != reported:
        plan.issue(
            "TARGET_TOTAL_RECONCILIATION",
            "ERROR",
            "Target Architecture!P3",
            "Imported company targets plus explicit reserve total "
            f"{company_total + (reserve or Decimal(0))}, "
            f"but workbook reports {reported}; no values were adjusted.",
        )
        plan.target_importable = False
    plan.targets = targets


def _score_value(
    cell: Cell,
    dimension: ScoreDimension,
    minimum: Decimal,
    maximum: Decimal,
    ticker: str,
    source: str,
    rationale: str,
    plan: ImportPlan,
    source_priority: int = 0,
) -> ScoreRow | None:
    if cell.value is None or not cell.value.strip():
        if cell.kind == "e":
            message = f"Workbook error value {cell.value!r} was retained as INVALID/null."
            plan.issue("SCORE_CELL_ERROR", "ERROR", source, message)
            return ScoreRow(
                ticker,
                dimension,
                None,
                ScoreAssessmentStatus.INVALID,
                rationale,
                source,
                message,
                source_priority,
            )
        return None
    try:
        value = Decimal(cell.value.strip())
    except InvalidOperation:
        message = f"Non-numeric source value {cell.value!r} was retained as INVALID/null."
        plan.issue("SCORE_VALUE_INVALID", "ERROR", source, message)
        return ScoreRow(
            ticker,
            dimension,
            None,
            ScoreAssessmentStatus.INVALID,
            rationale,
            source,
            message,
            source_priority,
        )
    if not value.is_finite() or not minimum <= value <= maximum:
        message = (
            f"Source score {cell.value!r} is outside the active {dimension.value} scale "
            f"{minimum}–{maximum}; value was not clamped."
        )
        plan.issue("SCORE_RANGE_INVALID", "ERROR", source, message)
        return ScoreRow(
            ticker,
            dimension,
            None,
            ScoreAssessmentStatus.INVALID,
            rationale,
            source,
            message,
            source_priority,
        )
    return ScoreRow(
        ticker,
        dimension,
        value,
        ScoreAssessmentStatus.ASSESSED,
        rationale,
        source,
        source_priority=source_priority,
    )


def _load_scores(plan: ImportPlan, companies: dict[str, CompanyRow]) -> None:
    workbook = plan.portfolio_workbook
    score_rows: list[ScoreRow] = []
    canon_sheets = [
        ("10Y Durability", ScoreDimension.DURABILITY_10Y, "G", "K", "L"),
        ("Compounder Quality", ScoreDimension.COMPOUNDER_QUALITY, "G", "K", "L"),
    ]
    for sheet, dimension, score_column, rationale_column, source_column in canon_sheets:
        for row_number, row in workbook.rows(sheet, 5):
            raw_ticker = _value(row, "A")
            if raw_ticker is None:
                continue
            ticker = _ticker_key(raw_ticker)
            if ticker not in companies:
                plan.issue(
                    "SCORE_COMPANY_UNRESOLVED",
                    "ERROR",
                    f"{sheet}!A{row_number}",
                    f"Score row has no importable company identity for {ticker}.",
                )
                continue
            source = plan.source_ref(workbook, sheet, f"{score_column}{row_number}")
            rationale = (
                _value(row, rationale_column)
                or "No score-specific rationale is stored on this legacy score row."
            )
            source_urls: list[str] = []
            for source_url_column in ("L", "M") if sheet == "10Y Durability" else (source_column,):
                source_url = _value(row, source_url_column)
                if source_url is not None:
                    source_urls.append(source_url)
            if source_urls:
                source = f"{source}; source URL: {'; '.join(source_urls)}"
            components = (
                ("B", "C", "D", "E", "F") if sheet == "10Y Durability" else ("C", "D", "E", "F")
            )
            source_priority = sum(_value(row, column) is not None for column in components)
            source_priority += 2 if _value(row, rationale_column) is not None else 0
            source_priority += len(source_urls)
            # The active definitions are the authority for each range. Their values are stable
            # across environments and duplicated here only to validate a dry-run without DB IO.
            minimum = Decimal("0")
            maximum = Decimal("5")
            score = _score_value(
                workbook.cell(sheet, f"{score_column}{row_number}"),
                dimension,
                minimum,
                maximum,
                ticker,
                source,
                rationale,
                plan,
                source_priority,
            )
            if score is not None:
                score_rows.append(score)
    for sheet, _cells in workbook.sheets.items():
        if not sheet.startswith(("P-", "W-", "C-")):
            continue
        ticker = _ticker_key(sheet[2:])
        if ticker not in companies:
            continue
        for dimension, label_cell, value_cell, lower_bound in (
            (ScoreDimension.EXECUTION, "A7", "B7", Decimal(1)),
            (ScoreDimension.RISK, "A8", "B8", Decimal(1)),
        ):
            if _value({"label": workbook.cell(sheet, label_cell)}, "label") is None:
                continue
            label = _value({"label": workbook.cell(sheet, label_cell)}, "label")
            if label != (
                "Execution Score" if dimension == ScoreDimension.EXECUTION else "Risk Score"
            ):
                continue
            source = plan.source_ref(workbook, sheet, value_cell)
            rationale = (
                f"The workbook stores {dimension.value} numerically at "
                f"{sheet}!{value_cell} but has "
                "no dimension-specific rationale adjacent to that field."
            )
            score = _score_value(
                workbook.cell(sheet, value_cell),
                dimension,
                lower_bound,
                Decimal(5),
                ticker,
                source,
                rationale,
                plan,
            )
            if score is not None:
                score_rows.append(score)
    grouped: dict[tuple[str, ScoreDimension], list[ScoreRow]] = {}
    for item in score_rows:
        grouped.setdefault((item.ticker, item.dimension), []).append(item)
    unique: list[ScoreRow] = []
    for (ticker, dimension), candidates in grouped.items():
        ordered = sorted(candidates, key=lambda item: item.source_priority, reverse=True)
        chosen = ordered[0]
        distinct = {(item.score, item.status) for item in candidates}
        if len(distinct) > 1 and (
            len(ordered) > 1 and ordered[0].source_priority == ordered[1].source_priority
        ):
            plan.issue(
                "DUPLICATE_SCORE_CONFLICT",
                "ERROR",
                "; ".join(item.source for item in candidates),
                f"{ticker} has equally complete but conflicting {dimension.value} rows; "
                "no value was selected.",
            )
            continue
        if len(candidates) > 1:
            plan.issue(
                "DUPLICATE_SCORE_ROW_RESOLVED_BY_DETAIL",
                "WARNING",
                "; ".join(item.source for item in candidates),
                f"{ticker} {dimension.value} uses the row with the most complete "
                "component evidence, "
                "rationale, and source references; summary-only duplicates were not "
                "treated as history.",
            )
        unique.append(chosen)
    plan.scores = unique
    for dimension in ScoreDimension:
        plan.source_score_count[dimension.value] = sum(
            item.dimension == dimension for item in unique
        )


def _rank_value(value: str | None, source: str, plan: ImportPlan) -> int | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        plan.issue(
            "RANK_VALUE_INVALID",
            "ERROR",
            source,
            f"Cached rank {value!r} is not numeric; it remains unavailable.",
        )
        return None
    if not number.is_finite() or number <= 0 or number != number.to_integral_value():
        plan.issue(
            "RANK_VALUE_INVALID",
            "ERROR",
            source,
            f"Cached rank {value!r} is not a positive integer; it remains unavailable.",
        )
        return None
    return int(number)


def _load_rankings(plan: ImportPlan, companies: dict[str, CompanyRow]) -> None:
    workbook = plan.portfolio_workbook
    registry = {
        _ticker_key(_value(row, "A") or ""): (row_number, row)
        for row_number, row in workbook.rows("Universe Registry", 5)
        if _value(row, "A") is not None
    }
    rank_columns = {
        RankingType.PORTFOLIO: "L",
        RankingType.WATCHLIST: "M",
        RankingType.RESEARCH: "J",
    }
    for ranking_type in RankingType:
        entries: list[RankRow] = []
        col = rank_columns[ranking_type]
        ranked_source_count = 0
        for ticker, company in companies.items():
            source_row = registry.get(ticker)
            if source_row is None:
                continue
            row_number, row = source_row
            cell_value = _value(row, col)
            source = plan.source_ref(workbook, "Universe Registry", f"{col}{row_number}")
            bucket = (company.research_bucket or "").casefold()
            if ranking_type == RankingType.PORTFOLIO:
                member: bool | None = (
                    True
                    if (company.current_weight is not None and company.current_weight > 0)
                    or (company.target_weight is not None and company.target_weight > 0)
                    else False
                    if company.current_weight is not None and company.target_weight is not None
                    else None
                )
            elif ranking_type == RankingType.WATCHLIST:
                member = (
                    None
                    if company.lifecycle is None and bucket == "watchlist"
                    else company.lifecycle == Lifecycle.WATCHLIST
                )
            else:
                candidate_bucket = bucket in {"candidate - high", "candidate - low"}
                member = (
                    None
                    if company.lifecycle is None and candidate_bucket
                    else company.lifecycle == Lifecycle.CANDIDATE and candidate_bucket
                )
            if member is None:
                if cell_value is not None:
                    _rank_value(cell_value, source, plan)
                entries.append(
                    RankRow(
                        ticker,
                        ranking_type,
                        None,
                        RankingEntryStatus.INPUTS_UNAVAILABLE,
                        "The workbook cached current/target membership inputs are incomplete; "
                        "a cached rank, if any, is not assigned without resolved eligibility.",
                        source,
                    )
                )
            elif member:
                rank = _rank_value(cell_value, source, plan)
                if rank is None:
                    reason = "The workbook has no usable cached position for this eligible company."
                    status = RankingEntryStatus.INPUTS_UNAVAILABLE
                else:
                    ranked_source_count += 1
                    status = RankingEntryStatus.RANKED
                    reason = (
                        "Cached legacy workbook rank imported as observed; the application "
                        "did not calculate it."
                    )
                entries.append(RankRow(ticker, ranking_type, rank, status, reason, source))
            else:
                if cell_value is not None:
                    _rank_value(cell_value, source, plan)
                entries.append(
                    RankRow(
                        ticker,
                        ranking_type,
                        None,
                        RankingEntryStatus.NOT_ELIGIBLE,
                        "The company is outside the workbook-defined population for this "
                        "ranking type.",
                        source,
                    )
                )
        position_groups: dict[int, list[int]] = {}
        for index, item in enumerate(entries):
            if item.status == RankingEntryStatus.RANKED and item.position is not None:
                position_groups.setdefault(item.position, []).append(index)
        duplicate_indexes = {
            index for indexes in position_groups.values() if len(indexes) > 1 for index in indexes
        }
        for rank, indexes in position_groups.items():
            if len(indexes) < 2:
                continue
            duplicate_rows = [entries[index] for index in indexes]
            plan.issue(
                "DUPLICATE_RANK_POSITION",
                "ERROR",
                "; ".join(item.source for item in duplicate_rows),
                f"{ranking_type.value} cached position {rank} is shared by "
                f"{', '.join(item.ticker for item in duplicate_rows)}. The workbook's "
                "documented tie-break requires a unique ordinal; none of these cells "
                "was reassigned.",
            )
        entries = [
            RankRow(
                item.ticker,
                item.ranking_type,
                None,
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "The cached rank position is duplicated in the source and cannot be "
                "mapped to this domain's unique ordinal position without changing it.",
                item.source,
            )
            if index in duplicate_indexes
            else item
            for index, item in enumerate(entries)
        ]
        ranked_source_count -= len(duplicate_indexes)
        plan.rankings[ranking_type] = entries
        plan.source_rank_count[ranking_type.value] = ranked_source_count


def build_plan(
    portfolio_path: Path,
    market_path: Path,
    observed_at: datetime | None = None,
) -> ImportPlan:
    timestamp = (observed_at or now()).astimezone(UTC)
    if timestamp > now():
        raise ValueError("The import observation timestamp cannot be in the future.")
    portfolio_book = Workbook.read(
        portfolio_path,
        lambda name: (
            name
            in {
                "Universe Registry",
                "Current Holdings",
                "Target Architecture",
                "10Y Durability",
                "Compounder Quality",
            }
            or name == "Price Feed"
            or name.startswith(("P-", "W-", "C-"))
        ),
    )
    market_book = Workbook.read(market_path, lambda name: name == "Listings")
    digest = hashlib.sha256(
        f"{portfolio_book.sha256}:{market_book.sha256}".encode("ascii")
    ).hexdigest()
    plan = ImportPlan(portfolio_book, market_book, timestamp, digest)
    companies = _load_companies(plan)
    listings = _load_listings(plan, companies)
    _load_holdings(plan, companies, listings)
    _load_targets(plan, companies)
    _load_scores(plan, companies)
    _load_rankings(plan, companies)
    return plan


def _stable_id(kind: str, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{kind}:{key}")


def _delete_demo_data(session: Session) -> None:
    """Remove only explicitly marked demo rows and their explicitly seeded history."""
    demo_companies = select(Company.id).where(Company.is_demo.is_(True))
    demo_portfolios = select(Portfolio.id).where(Portfolio.is_demo.is_(True))
    demo_runs = select(RankingRun.id).where(RankingRun.source == "development-seed-v1")
    demo_snapshots = select(HoldingSnapshot.id).where(
        HoldingSnapshot.portfolio_id.in_(demo_portfolios)
    )
    demo_revisions = select(TargetRevision.id).where(
        TargetRevision.portfolio_id.in_(demo_portfolios)
    )
    session.execute(delete(RankingEntry).where(RankingEntry.run_id.in_(demo_runs)))
    session.execute(delete(RankingRun).where(RankingRun.source == "development-seed-v1"))
    session.execute(delete(ScoreAssessment).where(ScoreAssessment.company_id.in_(demo_companies)))
    session.execute(delete(CurrentLifecycle).where(CurrentLifecycle.company_id.in_(demo_companies)))
    session.execute(delete(LifecycleEvent).where(LifecycleEvent.company_id.in_(demo_companies)))
    session.execute(delete(HoldingPosition).where(HoldingPosition.snapshot_id.in_(demo_snapshots)))
    session.execute(delete(CashPosition).where(CashPosition.snapshot_id.in_(demo_snapshots)))
    session.execute(
        delete(HoldingSnapshot).where(HoldingSnapshot.portfolio_id.in_(demo_portfolios))
    )
    session.execute(
        delete(TargetAllocation).where(TargetAllocation.revision_id.in_(demo_revisions))
    )
    session.execute(delete(TargetRevision).where(TargetRevision.portfolio_id.in_(demo_portfolios)))
    session.execute(
        delete(Listing).where(
            Listing.security_id.in_(
                select(Security.id).where(Security.company_id.in_(demo_companies))
            )
        )
    )
    session.execute(delete(Security).where(Security.company_id.in_(demo_companies)))
    session.execute(delete(Company).where(Company.id.in_(demo_companies)))
    session.execute(delete(Portfolio).where(Portfolio.is_demo.is_(True)))


def _assert_safe_database(session: Session, plan: ImportPlan, replace_demo: bool) -> None:
    existing_batch = session.scalar(
        select(LegacyImportBatch).where(LegacyImportBatch.source_digest == plan.source_digest)
    )
    if existing_batch is not None:
        raise AlreadyImported(existing_batch)
    if replace_demo:
        non_demo_portfolios = session.scalar(
            select(Portfolio.id).where(Portfolio.is_demo.is_(False)).limit(1)
        )
        if non_demo_portfolios is not None:
            raise ValueError(
                "--replace-demo refuses a database that also contains a non-demo portfolio."
            )
        # Protect authored data attached to demo companies; the opt-in seed alone is removable.
        demo_ids = select(Company.id).where(Company.is_demo.is_(True))
        non_demo_company = session.scalar(
            select(Company.id).where(Company.is_demo.is_(False)).limit(1)
        )
        if non_demo_company is not None:
            raise ValueError(
                "--replace-demo refuses a database that contains real company identities."
            )
        non_demo_demo_security = session.scalar(
            select(Security.id)
            .where(Security.company_id.in_(demo_ids), Security.is_demo.is_(False))
            .limit(1)
        )
        if non_demo_demo_security is not None:
            raise ValueError("--replace-demo found a non-demo security attached to a demo company.")
        non_demo_demo_listing = session.scalar(
            select(Listing.id)
            .where(
                Listing.security_id.in_(
                    select(Security.id).where(Security.company_id.in_(demo_ids))
                ),
                Listing.is_demo.is_(False),
            )
            .limit(1)
        )
        if non_demo_demo_listing is not None:
            raise ValueError("--replace-demo found a non-demo listing attached to demo data.")
        unexpected_score = session.scalar(
            select(ScoreAssessment.id)
            .where(
                ScoreAssessment.company_id.in_(demo_ids),
                ScoreAssessment.source != "development-seed-v1",
            )
            .limit(1)
        )
        if unexpected_score is not None:
            raise ValueError(
                "--replace-demo found authored score history attached to a demo company."
            )
        unexpected_lifecycle = session.scalar(
            select(LifecycleEvent.id)
            .where(
                LifecycleEvent.company_id.in_(demo_ids),
                LifecycleEvent.source != "development-seed-v1",
            )
            .limit(1)
        )
        if unexpected_lifecycle is not None:
            raise ValueError(
                "--replace-demo found lifecycle history not owned by the development seed."
            )
        unexpected_ranking = session.scalar(
            select(RankingRun.id).where(RankingRun.source != "development-seed-v1").limit(1)
        )
        if unexpected_ranking is not None:
            raise ValueError(
                "--replace-demo found non-seed ranking history; refusing to remove it."
            )
        unexpected_snapshot = session.scalar(
            select(HoldingSnapshot.id)
            .where(
                HoldingSnapshot.portfolio_id.in_(
                    select(Portfolio.id).where(Portfolio.is_demo.is_(True))
                ),
                HoldingSnapshot.source != "development-seed-v1",
            )
            .limit(1)
        )
        if unexpected_snapshot is not None:
            raise ValueError(
                "--replace-demo found a non-seed holdings snapshot; refusing to remove it."
            )
        unexpected_target = session.scalar(
            select(TargetRevision.id)
            .where(
                TargetRevision.portfolio_id.in_(
                    select(Portfolio.id).where(Portfolio.is_demo.is_(True))
                ),
                TargetRevision.source != "development-seed-v1",
            )
            .limit(1)
        )
        if unexpected_target is not None:
            raise ValueError(
                "--replace-demo found a non-seed target revision; refusing to remove it."
            )
        unexpected_import = session.scalar(select(LegacyImportBatch.id).limit(1))
        if unexpected_import is not None:
            raise ValueError(
                "--replace-demo found an earlier workbook import batch; refusing to "
                "remove imported history."
            )
    elif (
        session.scalar(select(Portfolio.id).limit(1)) is not None
        or session.scalar(select(Company.id).limit(1)) is not None
    ):
        raise ValueError(
            "Existing application data was found. Use a clean database or pass "
            "--replace-demo for a demo-only database."
        )


class AlreadyImported(Exception):
    def __init__(self, batch: LegacyImportBatch) -> None:
        super().__init__("This workbook pair was already imported")
        self.batch = batch


def _latest_lifecycle(session: Session, company_id: UUID) -> LifecycleEvent | None:
    current = session.get(CurrentLifecycle, company_id)
    return session.get(LifecycleEvent, current.event_id) if current else None


def _import_identity(session: Session, plan: ImportPlan) -> dict[str, UUID]:
    company_ids: dict[str, UUID] = {}
    for company_row in plan.companies:
        identifier = _stable_id("company", company_row.ticker)
        existing = session.get(Company, identifier)
        if existing is not None:
            if existing.is_demo or (existing.name, existing.reporting_currency) != (
                company_row.name,
                None,
            ):
                raise ValueError(
                    f"Company mapping conflict for {company_row.ticker}; refusing to "
                    "overwrite identity."
                )
        else:
            session.add(
                Company(
                    id=identifier,
                    name=company_row.name,
                    reporting_currency=None,
                    is_demo=False,
                    created_at=plan.observed_at,
                )
            )
        company_ids[company_row.ticker] = identifier
    session.flush()

    security_ids: dict[str, UUID] = {}
    listing_ids: dict[str, UUID] = {}
    for listing_row in plan.listings:
        company_id = (
            None
            if listing_row.security_type == "ETF"
            else company_ids[listing_row.canonical_ticker]
        )
        security_id = security_ids.get(listing_row.security_key)
        if security_id is None:
            security_id = _stable_id("security", listing_row.security_key)
            underlying_id = (
                security_ids.get(listing_row.underlying_security_key)
                if listing_row.underlying_security_key is not None
                else None
            )
            if listing_row.underlying_security_key is not None and underlying_id is None:
                raise ValueError(
                    f"Underlying security mapping {listing_row.underlying_security_key} for "
                    f"{listing_row.security_key} must be imported first."
                )
            existing_security = session.get(Security, security_id)
            security_identity = (
                company_id,
                listing_row.name,
                listing_row.security_type,
                listing_row.share_class,
                underlying_id,
            )
            if existing_security is not None:
                if (
                    existing_security.is_demo
                    or (
                        existing_security.company_id,
                        existing_security.name,
                        existing_security.security_type,
                        existing_security.share_class,
                        existing_security.underlying_security_id,
                    )
                    != security_identity
                ):
                    raise ValueError(
                        f"Security mapping conflict for {listing_row.security_key}; refusing "
                        "to overwrite identity."
                    )
            else:
                session.add(
                    Security(
                        id=security_id,
                        company_id=company_id,
                        name=listing_row.name,
                        security_type=listing_row.security_type,
                        share_class=listing_row.share_class,
                        underlying_security_id=underlying_id,
                        is_demo=False,
                        created_at=plan.observed_at,
                    )
                )
            security_ids[listing_row.security_key] = security_id
        listing_id = _stable_id("listing", f"{listing_row.venue}:{listing_row.ticker}")
        existing_listing = session.get(Listing, listing_id)
        listing_identity = (
            security_id,
            listing_row.venue,
            listing_row.ticker,
            listing_row.currency,
        )
        if existing_listing is not None:
            if (
                existing_listing.is_demo
                or (
                    existing_listing.security_id,
                    existing_listing.venue,
                    existing_listing.ticker,
                    existing_listing.currency,
                )
                != listing_identity
            ):
                raise ValueError(
                    f"Listing mapping conflict for {listing_row.venue}:"
                    f"{listing_row.ticker}; refusing "
                    "to overwrite identity."
                )
        else:
            collision = session.scalar(
                select(Listing.id).where(
                    Listing.venue == listing_row.venue,
                    Listing.ticker == listing_row.ticker,
                )
            )
            if collision is not None:
                raise ValueError(
                    f"Venue/ticker {listing_row.venue}:{listing_row.ticker} is already mapped "
                    "to another listing."
                )
            session.add(
                Listing(
                    id=listing_id,
                    security_id=security_id,
                    venue=listing_row.venue,
                    ticker=listing_row.ticker,
                    currency=listing_row.currency,
                    is_demo=False,
                    created_at=plan.observed_at,
                )
            )
        listing_ids[listing_row.listing_key] = listing_id
    session.flush()
    return {
        **{f"company:{key}": value for key, value in company_ids.items()},
        **{f"security:{key}": value for key, value in security_ids.items()},
        **{f"listing:{key}": value for key, value in listing_ids.items()},
    }


def _import_lifecycle(session: Session, plan: ImportPlan, company_ids: dict[str, UUID]) -> int:
    inserted = 0
    recorded = now()
    for row in plan.companies:
        if row.lifecycle is None:
            continue
        company_id = company_ids[row.ticker]
        previous = _latest_lifecycle(session, company_id)
        if previous is not None and previous.new_state == row.lifecycle:
            continue
        if previous is not None and plan.observed_at < previous.effective_at:
            plan.issue(
                "LIFECYCLE_BACKDATED",
                "ERROR",
                row.source,
                f"{row.ticker} import observation predates current lifecycle; no "
                "transition was added.",
            )
            continue
        event_id = _stable_id(
            "lifecycle", f"{plan.source_digest}:{row.ticker}:{row.lifecycle.value}"
        )
        event = LifecycleEvent(
            id=event_id,
            company_id=company_id,
            sequence=(previous.sequence + 1) if previous else 1,
            previous_state=previous.new_state if previous else None,
            new_state=row.lifecycle.value,
            effective_at=plan.observed_at,
            recorded_at=recorded,
            actor=Actor.IMPORT.value,
            reason=(
                "Imported the current workbook lifecycle observation. Positive current/target "
                "membership maps to PORTFOLIO only when Research Bucket is blank/Portfolio; "
                "explicit Watchlist, Candidate, or Drop buckets are retained."
            ),
            source=row.source,
        )
        session.add(event)
        session.flush()
        current = session.get(CurrentLifecycle, company_id)
        if current is None:
            session.add(CurrentLifecycle(company_id=company_id, event_id=event.id))
        else:
            current.event_id = event.id
        inserted += 1
    session.flush()
    return inserted


def _portfolio(session: Session, plan: ImportPlan) -> Portfolio:
    identifier = _stable_id("portfolio", "legacy-default")
    portfolio = session.get(Portfolio, identifier)
    currency = plan.base_currency
    if currency is None:
        raise ValueError("Portfolio base currency is unresolved; cannot create a portfolio.")
    name = "Imported Legacy Portfolio"
    if portfolio is not None:
        if portfolio.is_demo or (portfolio.name, portfolio.base_currency) != (name, currency):
            raise ValueError(
                "Portfolio identity conflicts with the existing database; refusing to overwrite."
            )
        return portfolio
    other = session.scalar(select(Portfolio.id).limit(1))
    if other is not None:
        raise ValueError("A different portfolio already exists; importer will not replace it.")
    portfolio = Portfolio(
        id=identifier,
        name=name,
        base_currency=currency,
        is_demo=False,
        created_at=plan.observed_at,
    )
    session.add(portfolio)
    session.flush()
    return portfolio


def _current_snapshot(session: Session, portfolio_id: UUID) -> HoldingSnapshot | None:
    return session.scalar(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.portfolio_id == portfolio_id)
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )


def _import_holdings(
    session: Session,
    plan: ImportPlan,
    ids: dict[str, UUID],
    portfolio: Portfolio,
) -> tuple[int, int]:
    desired_positions = {
        ids[f"listing:{item.listing_key}"]: item.quantity for item in plan.positions
    }
    desired_cash = {item.currency: item.balance for item in plan.cash}
    latest = _current_snapshot(session, portfolio.id)
    if latest is not None:
        stored_positions = {
            item.listing_id: item.quantity
            for item in session.scalars(
                select(HoldingPosition).where(HoldingPosition.snapshot_id == latest.id)
            )
        }
        stored_cash = {
            item.currency: item.balance
            for item in session.scalars(
                select(CashPosition).where(CashPosition.snapshot_id == latest.id)
            )
        }
        desired_completeness = "PARTIAL" if plan.holdings_partial else "COMPLETE"
        if (
            stored_positions == desired_positions
            and stored_cash == desired_cash
            and latest.completeness == desired_completeness
        ):
            return 0, len(desired_positions) + len(desired_cash)
        if plan.observed_at < latest.effective_at:
            plan.issue(
                "HOLDINGS_BACKDATED",
                "ERROR",
                "Current Holdings!A4:J29",
                "Import observation predates the latest stored holdings snapshot; no "
                "snapshot was added.",
            )
            return 0, 0
    elif plan.observed_at < portfolio.created_at:
        plan.issue(
            "HOLDINGS_BACKDATED",
            "ERROR",
            "Current Holdings!A4:J29",
            "Import observation predates the portfolio; no snapshot was added.",
        )
        return 0, 0
    source = plan.source_ref(plan.portfolio_workbook, "Current Holdings", "A4:J29")
    unresolved = [
        issue.message
        for issue in plan.issues
        if issue.code in {"ETF_LISTING_UNRESOLVED", "HOLDING_LISTING_UNRESOLVED"}
    ]
    reason = "Current workbook holdings imported as observed at import time."
    if unresolved:
        reason += (
            " Partial because unresolved instruments were excluded: " + "; ".join(unresolved)[:700]
        )
    snapshot = HoldingSnapshot(
        id=_stable_id("holdings", f"{plan.source_digest}:{portfolio.id}"),
        portfolio_id=portfolio.id,
        completeness="PARTIAL" if plan.holdings_partial else "COMPLETE",
        effective_at=plan.observed_at,
        recorded_at=now(),
        actor=Actor.IMPORT.value,
        reason=reason[:1000],
        source=source,
    )
    session.add(snapshot)
    session.flush()
    session.info["new_snapshot_ids"] = {snapshot.id}
    try:
        for position in plan.positions:
            session.add(
                HoldingPosition(
                    id=_stable_id("holding-position", f"{snapshot.id}:{position.canonical_ticker}"),
                    snapshot_id=snapshot.id,
                    listing_id=ids[f"listing:{position.listing_key}"],
                    quantity=position.quantity,
                )
            )
        for cash in plan.cash:
            session.add(
                CashPosition(
                    id=_stable_id("holding-cash", f"{snapshot.id}:{cash.currency}"),
                    snapshot_id=snapshot.id,
                    currency=cash.currency,
                    balance=cash.balance,
                )
            )
        session.flush()
    finally:
        session.info.pop("new_snapshot_ids", None)
    return 1, len(plan.positions) + len(plan.cash)


def _import_targets(
    session: Session,
    plan: ImportPlan,
    company_ids: dict[str, UUID],
    portfolio: Portfolio,
) -> int:
    if not plan.target_importable:
        return 0
    latest = session.scalar(
        select(TargetRevision)
        .where(TargetRevision.portfolio_id == portfolio.id, TargetRevision.status == "ACCEPTED")
        .order_by(TargetRevision.effective_at.desc(), TargetRevision.accepted_at.desc())
        .limit(1)
    )
    if latest is not None:
        prior = {
            item.company_id: item.weight
            for item in session.scalars(
                select(TargetAllocation).where(TargetAllocation.revision_id == latest.id)
            )
        }
        desired = {company_ids[key]: weight for key, weight in plan.targets.items()}
        if prior == desired:
            return 0
        if plan.observed_at < latest.effective_at:
            plan.issue(
                "TARGET_BACKDATED",
                "ERROR",
                "Target Architecture!A4:D100",
                "Import observation predates the latest accepted target; no revision was added.",
            )
            return 0
    revision_id = _stable_id("target-revision", f"{plan.source_digest}:{portfolio.id}")
    revision = TargetRevision(
        id=revision_id,
        portfolio_id=portfolio.id,
        effective_at=plan.observed_at,
        recorded_at=now(),
        actor=Actor.IMPORT.value,
        reason=(
            "Accepted company target allocations imported exactly as listed in "
            "Target Architecture. "
            "Zero weights are preserved; the RESERVE row is not a company target."
        ),
        source=plan.source_ref(plan.portfolio_workbook, "Target Architecture", "A4:D100"),
        status="DRAFT",
        accepted_at=None,
    )
    session.add(revision)
    session.flush()
    session.add_all(
        TargetAllocation(
            id=_stable_id("target-allocation", f"{revision.id}:{ticker}"),
            revision_id=revision.id,
            company_id=company_ids[ticker],
            weight=weight,
        )
        for ticker, weight in plan.targets.items()
    )
    session.flush()
    revision.status = "ACCEPTED"
    revision.accepted_at = now()
    session.flush()
    return 1


def _import_scores(
    session: Session,
    plan: ImportPlan,
    company_ids: dict[str, UUID],
) -> int:
    definitions = {
        ScoreDimension(item.dimension): item
        for item in session.scalars(
            select(ScoreDefinition).where(ScoreDefinition.status == "ACTIVE")
        )
    }
    inserted = 0
    for item in plan.scores:
        definition = definitions.get(item.dimension)
        if definition is None:
            plan.issue(
                "SCORE_DEFINITION_MISSING",
                "ERROR",
                item.source,
                f"No active definition for {item.dimension.value}.",
            )
            continue
        if (
            item.score is not None
            and not definition.minimum_score <= item.score <= definition.maximum_score
        ):
            plan.issue(
                "SCORE_RANGE_INVALID",
                "ERROR",
                item.source,
                f"{item.score} exceeds the active definition scale; no score was imported.",
            )
            continue
        company_id = company_ids[item.ticker]
        previous = session.scalar(
            select(ScoreAssessment)
            .where(
                ScoreAssessment.company_id == company_id,
                ScoreAssessment.score_definition_id == definition.id,
            )
            .order_by(
                ScoreAssessment.effective_at.desc(),
                ScoreAssessment.recorded_at.desc(),
                ScoreAssessment.id.desc(),
            )
            .limit(1)
        )
        if previous is not None:
            if (
                previous.status == item.status.value
                and previous.score == item.score
                and previous.rationale == item.rationale
            ):
                continue
            if plan.observed_at < previous.effective_at:
                plan.issue(
                    "SCORE_BACKDATED",
                    "ERROR",
                    item.source,
                    f"{item.ticker} score import predates the latest assessment; no "
                    "correction was added.",
                )
                continue
        record = ScoreAssessment(
            id=_stable_id("score", f"{plan.source_digest}:{item.ticker}:{item.dimension.value}"),
            company_id=company_id,
            score_definition_id=definition.id,
            score=item.score,
            status=item.status.value,
            effective_at=plan.observed_at,
            recorded_at=now(),
            rationale=(
                item.rationale
                if item.issue is None
                else f"{item.rationale} Source data-quality issue: {item.issue}"
            )[:4000],
            actor=Actor.IMPORT.value,
            source=item.source,
            superseded_assessment_id=previous.id if previous is not None else None,
        )
        session.add(record)
        inserted += 1
    session.flush()
    return inserted


def _import_rankings(
    session: Session,
    plan: ImportPlan,
    company_ids: dict[str, UUID],
) -> tuple[int, int]:
    definitions = {
        RankingType(item.ranking_type): item
        for item in session.scalars(
            select(RankingDefinition).where(RankingDefinition.status == "ACTIVE")
        )
    }
    run_count = 0
    entry_count = 0
    for ranking_type, rows in plan.rankings.items():
        definition = definitions.get(ranking_type)
        if definition is None:
            plan.issue(
                "RANKING_DEFINITION_MISSING",
                "ERROR",
                "ranking_definitions",
                f"No active {ranking_type.value} definition.",
            )
            continue
        ranked_count = sum(item.status == RankingEntryStatus.RANKED for item in rows)
        unavailable_count = sum(
            item.status == RankingEntryStatus.INPUTS_UNAVAILABLE for item in rows
        )
        status = (
            RankingRunStatus.UNAVAILABLE
            if ranked_count == 0
            else RankingRunStatus.PARTIAL
            if unavailable_count > 0
            else RankingRunStatus.COMPLETE
        )
        prior = session.scalar(
            select(RankingRun)
            .where(RankingRun.definition_id == definition.id)
            .order_by(RankingRun.as_of.desc(), RankingRun.recorded_at.desc(), RankingRun.id.desc())
            .limit(1)
        )
        recorded_at = now()
        if prior is not None and recorded_at <= prior.recorded_at:
            recorded_at = prior.recorded_at + timedelta(microseconds=1)
        run_id = _stable_id("ranking-run", f"{plan.source_digest}:{ranking_type.value}")
        run = RankingRun(
            id=run_id,
            definition_id=definition.id,
            as_of=plan.observed_at,
            recorded_at=recorded_at,
            status=status.value,
            actor=Actor.IMPORT.value,
            reason=(
                "Cached legacy workbook positions were imported verbatim where available. "
                "This run is a source observation and is not a recalculation by the application."
            ),
            source=plan.source_ref(plan.portfolio_workbook, "Universe Registry", "J4:M223"),
        )
        session.add(run)
        session.flush()
        for item in rows:
            session.add(
                RankingEntry(
                    id=_stable_id("ranking-entry", f"{run.id}:{item.ticker}"),
                    run_id=run.id,
                    company_id=company_ids[item.ticker],
                    position=item.position,
                    status=item.status.value,
                    reason=item.reason,
                )
            )
            entry_count += 1
        run_count += 1
    session.flush()
    return run_count, entry_count


def _record_batch(session: Session, plan: ImportPlan, report: dict[str, Any]) -> None:
    session.add(
        LegacyImportBatch(
            id=plan.batch_id,
            source_digest=plan.source_digest,
            portfolio_workbook_sha256=plan.portfolio_workbook.sha256,
            market_data_sha256=plan.market_workbook.sha256,
            observed_at=plan.observed_at,
            recorded_at=now(),
            status="APPLIED",
            report=report,
        )
    )
    session.flush()


def _reconcile(
    session: Session,
    plan: ImportPlan,
    ids: dict[str, UUID],
    company_ids: dict[str, UUID],
    portfolio: Portfolio,
) -> dict[str, Any]:
    """Compare the just-imported canonical projection with the parsed workbook observations."""
    domains: dict[str, dict[str, Any]] = {}

    def record(name: str, expected: int, matched: int, mismatches: list[str] | None = None) -> None:
        mismatches = mismatches or []
        domains[name] = {
            "status": "MATCHED" if not mismatches and expected == matched else "MISMATCH",
            "expected": expected,
            "matched": matched,
            "mismatches": mismatches[:50],
        }

    company_mismatches: list[str] = []
    matched_companies = 0
    for company_row in plan.companies:
        company_record = session.get(Company, company_ids[company_row.ticker])
        if company_record is not None and (
            company_record.name,
            company_record.reporting_currency,
        ) == (company_row.name, None):
            matched_companies += 1
        else:
            company_mismatches.append(
                f"Company identity differs or is absent for {company_row.ticker}."
            )
    record("companies", len(plan.companies), matched_companies, company_mismatches)

    listing_mismatches: list[str] = []
    matched_listings = 0
    for listing_row in plan.listings:
        listing_record = session.get(Listing, ids[f"listing:{listing_row.listing_key}"])
        security_record = session.get(Security, ids[f"security:{listing_row.security_key}"])
        expected_company = (
            None
            if listing_row.security_type == "ETF"
            else company_ids[listing_row.canonical_ticker]
        )
        expected_underlying = (
            ids[f"security:{listing_row.underlying_security_key}"]
            if listing_row.underlying_security_key is not None
            else None
        )
        if (
            listing_record is not None
            and security_record is not None
            and (
                listing_record.venue,
                listing_record.ticker,
                listing_record.currency,
            )
            == (listing_row.venue, listing_row.ticker, listing_row.currency)
            and (
                security_record.company_id,
                security_record.name,
                security_record.security_type,
                security_record.share_class,
                security_record.underlying_security_id,
            )
            == (
                expected_company,
                listing_row.name,
                listing_row.security_type,
                listing_row.share_class,
                expected_underlying,
            )
        ):
            matched_listings += 1
        else:
            listing_mismatches.append(
                f"Listing identity or currency differs for {listing_row.venue}:"
                f"{listing_row.ticker}."
            )
    record("securities_and_listings", len(plan.listings), matched_listings, listing_mismatches)

    lifecycle_mismatches: list[str] = []
    lifecycle_expected = sum(item.lifecycle is not None for item in plan.companies)
    lifecycle_matched = 0
    for lifecycle_row in plan.companies:
        if lifecycle_row.lifecycle is None:
            continue
        lifecycle_event = _latest_lifecycle(session, company_ids[lifecycle_row.ticker])
        if (
            lifecycle_event is not None
            and lifecycle_event.new_state == lifecycle_row.lifecycle.value
        ):
            lifecycle_matched += 1
        else:
            lifecycle_mismatches.append(
                f"Current lifecycle differs or is absent for {lifecycle_row.ticker}."
            )
    record("lifecycle", lifecycle_expected, lifecycle_matched, lifecycle_mismatches)
    domains["lifecycle"]["unresolved_source_rows"] = len(plan.companies) - lifecycle_expected

    latest = _current_snapshot(session, portfolio.id)
    holding_mismatches: list[str] = []
    holding_matched = 0
    if latest is not None:
        stored_positions = {
            item.listing_id: item.quantity
            for item in session.scalars(
                select(HoldingPosition).where(HoldingPosition.snapshot_id == latest.id)
            )
        }
        expected_positions = {
            ids[f"listing:{item.listing_key}"]: item.quantity for item in plan.positions
        }
        stored_cash = {
            item.currency: item.balance
            for item in session.scalars(
                select(CashPosition).where(CashPosition.snapshot_id == latest.id)
            )
        }
        expected_cash = {item.currency: item.balance for item in plan.cash}
        expected_completeness = "PARTIAL" if plan.holdings_partial else "COMPLETE"
        if (
            stored_positions == expected_positions
            and stored_cash == expected_cash
            and latest.completeness == expected_completeness
        ):
            holding_matched = len(expected_positions) + len(expected_cash)
        else:
            holding_mismatches.append(
                "Latest snapshot quantities, currencies, cash, or completeness differ "
                "from the import observation."
            )
    else:
        holding_mismatches.append("No holdings snapshot is present.")
    record("holdings", len(plan.positions) + len(plan.cash), holding_matched, holding_mismatches)

    if plan.target_importable:
        target_revision = session.scalar(
            select(TargetRevision)
            .where(TargetRevision.portfolio_id == portfolio.id, TargetRevision.status == "ACCEPTED")
            .order_by(TargetRevision.effective_at.desc(), TargetRevision.accepted_at.desc())
            .limit(1)
        )
        actual = (
            {
                allocation.company_id: allocation.weight
                for allocation in session.scalars(
                    select(TargetAllocation).where(
                        TargetAllocation.revision_id == target_revision.id
                    )
                )
            }
            if target_revision is not None
            else {}
        )
        expected_targets = {company_ids[ticker]: weight for ticker, weight in plan.targets.items()}
        target_matched = (
            len(expected_targets)
            if target_revision is not None and actual == expected_targets
            else 0
        )
        record(
            "strategic_targets",
            len(expected_targets),
            target_matched,
            []
            if target_matched == len(expected_targets)
            else ["Latest accepted target revision differs from workbook allocations."],
        )
    else:
        domains["strategic_targets"] = {
            "status": "BLOCKED_BY_SOURCE_ISSUES",
            "expected": len(plan.targets),
            "matched": 0,
            "mismatches": [],
        }

    definitions = {
        ScoreDimension(definition_row.dimension): definition_row
        for definition_row in session.scalars(
            select(ScoreDefinition).where(ScoreDefinition.status == "ACTIVE")
        )
    }
    score_mismatches: list[str] = []
    score_unmatched_by_dimension = {item.value: 0 for item in ScoreDimension}
    score_matched = 0
    for score_row in plan.scores:
        definition = definitions.get(score_row.dimension)
        if definition is None:
            score_mismatches.append(f"No active definition for {score_row.dimension.value}.")
            continue
        score_assessment = session.scalar(
            select(ScoreAssessment)
            .where(
                ScoreAssessment.company_id == company_ids[score_row.ticker],
                ScoreAssessment.score_definition_id == definition.id,
            )
            .order_by(
                ScoreAssessment.effective_at.desc(),
                ScoreAssessment.recorded_at.desc(),
                ScoreAssessment.id.desc(),
            )
            .limit(1)
        )
        if score_assessment is not None and (
            score_assessment.score,
            score_assessment.status,
        ) == (
            score_row.score,
            score_row.status.value,
        ):
            score_matched += 1
        else:
            score_unmatched_by_dimension[score_row.dimension.value] += 1
            score_mismatches.append(
                f"Latest {score_row.dimension.value} assessment differs or is absent for "
                f"{score_row.ticker}; expected ({score_row.score}, {score_row.status.value}), "
                f"found ({score_assessment.score if score_assessment else None}, "
                f"{score_assessment.status if score_assessment else None})."
            )
    record("scores", len(plan.scores), score_matched, score_mismatches)
    domains["scores"]["coverage"] = plan.report()["score_coverage"]
    domains["scores"]["unmatched_by_dimension"] = score_unmatched_by_dimension

    rank_mismatches: list[str] = []
    rank_expected = sum(len(entries) for entries in plan.rankings.values())
    rank_matched = 0
    for ranking_type, ranking_entries in plan.rankings.items():
        run_id = _stable_id("ranking-run", f"{plan.source_digest}:{ranking_type.value}")
        run = session.get(RankingRun, run_id)
        if run is None:
            rank_mismatches.append(f"No imported {ranking_type.value} run is present.")
            continue
        stored_rank_entries = {
            entry.company_id: (entry.position, entry.status)
            for entry in session.scalars(select(RankingEntry).where(RankingEntry.run_id == run.id))
        }
        expected_rank_entries = {
            company_ids[rank_entry.ticker]: (rank_entry.position, rank_entry.status.value)
            for rank_entry in ranking_entries
        }
        if stored_rank_entries == expected_rank_entries:
            rank_matched += len(expected_rank_entries)
        else:
            rank_mismatches.append(
                f"Imported {ranking_type.value} run differs from cached workbook rank entries."
            )
    record("ranking_runs", rank_expected, rank_matched, rank_mismatches)
    domains["ranking_runs"]["coverage"] = plan.report()["ranking_coverage"]

    mismatches = sum(
        max(0, int(item.get("expected", 0)) - int(item.get("matched", 0)))
        for item in domains.values()
        if item["status"] == "MISMATCH"
    )
    unresolved = sum(issue.severity == "ERROR" for issue in plan.issues)
    return {
        "status": "RECONCILED_WITH_SOURCE_GAPS"
        if mismatches == 0 and unresolved
        else "MATCHED"
        if mismatches == 0
        else "MISMATCH",
        "mismatch_count": mismatches,
        "unresolved_source_issue_count": unresolved,
        "domains": domains,
    }


def apply_plan(session: Session, plan: ImportPlan, replace_demo: bool = False) -> dict[str, Any]:
    _assert_safe_database(session, plan, replace_demo)
    if replace_demo:
        _delete_demo_data(session)
    ids = _import_identity(session, plan)
    company_ids = {
        key.removeprefix("company:"): value
        for key, value in ids.items()
        if key.startswith("company:")
    }
    lifecycle_count = _import_lifecycle(session, plan, company_ids)
    portfolio = _portfolio(session, plan)
    snapshot_count, position_and_cash_count = _import_holdings(session, plan, ids, portfolio)
    target_count = _import_targets(session, plan, company_ids, portfolio)
    score_count = _import_scores(session, plan, company_ids)
    rank_run_count, rank_entry_count = _import_rankings(session, plan, company_ids)
    report = plan.report(applied=True)
    report["applied_records"] = {
        "companies": len(company_ids),
        "securities": sum(key.startswith("security:") for key in ids),
        "listings": sum(key.startswith("listing:") for key in ids),
        "lifecycle_events": lifecycle_count,
        "holding_snapshots": snapshot_count,
        "positions_and_cash_rows": position_and_cash_count,
        "accepted_target_revisions": target_count,
        "score_assessments": score_count,
        "ranking_runs": rank_run_count,
        "ranking_entries": rank_entry_count,
    }
    report["reconciliation"] = _reconcile(session, plan, ids, company_ids, portfolio)
    _record_batch(session, plan, report)
    return report


def run_cli(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--portfolio-workbook", type=Path, default=repo / "reference" / "workbook" / MAIN_BOOK
    )
    parser.add_argument(
        "--market-data-workbook", type=Path, default=repo / "reference" / "workbook" / MARKET_BOOK
    )
    parser.add_argument(
        "--observed-at",
        type=datetime.fromisoformat,
        help="Optional timezone-aware import observation time (ISO-8601). Defaults to current UTC.",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply the dry-run plan in one database transaction."
    )
    parser.add_argument(
        "--replace-demo",
        action="store_true",
        help="With --apply, remove only explicitly marked seed data before importing.",
    )
    parser.add_argument(
        "--report", type=Path, help="Write the JSON plan/reconciliation report to this path."
    )
    args = parser.parse_args(argv)
    if args.replace_demo and not args.apply:
        parser.error("--replace-demo requires --apply")
    if args.observed_at is not None and (
        args.observed_at.tzinfo is None or args.observed_at.utcoffset() is None
    ):
        parser.error("--observed-at must include a timezone offset")
    try:
        plan = build_plan(args.portfolio_workbook, args.market_data_workbook, args.observed_at)
        report: dict[str, Any] = plan.report()
        engine = create_database_engine(Settings())
        if args.apply:
            if engine is None:
                raise ValueError("DATABASE_URL is required to apply an import.")
            try:
                with Session(engine) as session, session.begin():
                    report = apply_plan(session, plan, replace_demo=args.replace_demo)
            except AlreadyImported as existing:
                report = existing.batch.report
                report["status"] = "ALREADY_APPLIED"
            finally:
                engine.dispose()
        else:
            if engine is not None:
                try:
                    with Session(engine) as session:
                        found = session.scalar(
                            select(LegacyImportBatch).where(
                                LegacyImportBatch.source_digest == plan.source_digest
                            )
                        )
                        if found is not None:
                            report["already_applied"] = True
                        report["database_preflight"] = {
                            "portfolio_count": int(
                                session.scalar(select(func.count()).select_from(Portfolio)) or 0
                            ),
                            "demo_portfolio_count": int(
                                session.scalar(
                                    select(func.count())
                                    .select_from(Portfolio)
                                    .where(Portfolio.is_demo.is_(True))
                                )
                                or 0
                            ),
                            "real_portfolio_count": int(
                                session.scalar(
                                    select(func.count())
                                    .select_from(Portfolio)
                                    .where(Portfolio.is_demo.is_(False))
                                )
                                or 0
                            ),
                        }
                finally:
                    engine.dispose()
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        print(rendered)
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered + "\n", encoding="utf-8")
        return 0
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        print(f"Workbook import failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
