"""Opt-in private SEC recordings for isolated browser replay; never fetch a URL."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import Actor, Company


class RecordedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    source_url: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    captured_at: datetime
    capture_timestamp_basis: str
    bytes: int = Field(gt=0, le=16 * 1024 * 1024)


class RecordedIssuer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    name: str
    facts_name: str
    cik: str = Field(pattern=r"^\d{10}$")
    ticker: str
    venue: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class RecordingManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    scope: str
    issuer: RecordedIssuer
    records: list[RecordedResponse] = Field(min_length=2, max_length=7)
    request_count: int
    captured_at: datetime
    production_writes: int
    expected: dict[str, Any]


class SecRecording:
    """Validate all bytes/identities before creating any disposable fixture state."""

    def __init__(self, path: Path) -> None:
        raw = path.read_bytes()
        self.manifest = RecordingManifest.model_validate_json(raw)
        manifest = self.manifest
        if (
            manifest.version != "sec-real-recording-v1"
            or manifest.production_writes != 0
            or manifest.request_count != len(manifest.records)
            or manifest.captured_at.tzinfo is None
            or manifest.captured_at > datetime.now(UTC)
        ):
            raise ValueError("Recording manifest scope or capture time is invalid")
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.payloads: dict[str, bytes] = {}
        self.captured: dict[str, datetime] = {}
        directory = path.parent.resolve()
        for record in manifest.records:
            candidate = directory / record.file
            if (
                Path(record.file).name != record.file
                or candidate.is_symlink()
                or candidate.resolve().parent != directory
                or record.source_url in self.payloads
                or record.captured_at.tzinfo is None
                or record.captured_at > manifest.captured_at
            ):
                raise ValueError("Recording path, URL or capture time is invalid")
            content = candidate.read_bytes()
            if len(content) != record.bytes or hashlib.sha256(content).hexdigest() != record.sha256:
                raise ValueError("Recorded SEC response failed its immutable byte check")
            self.payloads[record.source_url] = content
            self.captured[record.source_url] = record.captured_at

        issuer = manifest.issuer
        self.facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{issuer.cik}.json"
        self.submissions_url = f"https://data.sec.gov/submissions/CIK{issuer.cik}.json"
        if {self.facts_url, self.submissions_url} - self.payloads.keys():
            raise ValueError("Facts and submissions recordings are both required")
        facts = json.loads(self.payloads[self.facts_url])
        submissions = json.loads(self.payloads[self.submissions_url])
        if (
            str(facts.get("cik")).zfill(10) != issuer.cik
            or str(submissions.get("cik")).zfill(10) != issuer.cik
            or facts.get("entityName") != issuer.facts_name
            or submissions.get("name") != issuer.name
            or issuer.name.casefold() != issuer.facts_name.casefold()
            or issuer.ticker not in submissions.get("tickers", [])
        ):
            raise ValueError("Recorded SEC issuer identity does not match its reviewed manifest")
        tickers, exchanges = submissions.get("tickers", []), submissions.get("exchanges", [])
        if (
            len(tickers) != len(exchanges)
            or exchanges[tickers.index(issuer.ticker)] != issuer.venue
        ):
            raise ValueError("Recorded SEC listing venue does not match")
        files = submissions.get("filings", {}).get("files", [])
        if not isinstance(files, list) or len(files) > 5:
            raise ValueError("Recorded filing history exceeds the bounded review")
        allowed = {self.facts_url, self.submissions_url}
        for item in files:
            name = item.get("name") if isinstance(item, dict) else None
            if not isinstance(name, str) or not re.fullmatch(
                rf"CIK{issuer.cik}-submissions-\d{{3}}\.json", name
            ):
                raise ValueError("Recorded filing history index is invalid")
            allowed.add(f"https://data.sec.gov/submissions/{name}")
        if allowed != self.payloads.keys():
            raise ValueError("Every indexed SEC history page must be recorded, with no extra URLs")

    def metadata(self) -> dict[str, object]:
        return {
            "scenario": "sec-real-refresh",
            "provider_fixture": "recorded-real-sec-v1",
            "recorded_capture_at": self.manifest.captured_at.isoformat(),
            "recording_manifest_sha256": self.sha256,
            "issuer": self.manifest.issuer.model_dump(mode="json"),
            "expected": self.manifest.expected,
            "portfolio_context": (
                "Fictional quantities, cash and targets; official SEC observations."
            ),
        }


def prepare_real_sec_data(engine: Engine, recording: SecRecording) -> dict[str, object]:
    """Create the exact issuer before the protected baseline; no renamed accepted identity."""
    issuer = recording.manifest.issuer
    at = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        company = Company(
            id=issuer.company_id, name=issuer.name, reporting_currency=issuer.currency
        )
        session.add(company)
        session.flush()
        security = services.create_security(
            session, company.id, s.SecurityCreate(name=issuer.name, security_type="COMMON_STOCK")
        )
        listing = services.create_listing(
            session,
            security.id,
            s.ListingCreate(ticker=issuer.ticker, venue=issuer.venue, currency=issuer.currency),
        )
        portfolio = services.create_portfolio(
            session,
            s.PortfolioCreate(
                name="Isolated SEC replay — fictional allocation", base_currency="EUR"
            ),
        )
        snapshot = services.record_holdings(
            session,
            portfolio.id,
            s.SnapshotCreate(
                actor=Actor.IMPORT,
                reason="Fictional allocation for recorded official SEC replay",
                source="isolated-real-sec-replay-v1",
                effective_at=at - timedelta(days=1),
                completeness="COMPLETE",
                positions=[s.PositionInput(listing_id=listing.id, quantity=Decimal("2.5"))],
                cash_positions=[s.CashInput(currency="EUR", balance=Decimal("10"))],
            ),
        )
        target = services.create_targets(
            session,
            portfolio.id,
            s.TargetCreate(
                actor=Actor.IMPORT,
                reason="Fictional allocation, not an investment decision",
                source="isolated-real-sec-replay-v1",
                effective_at=at - timedelta(days=1),
                allocations=[s.AllocationInput(company_id=company.id, weight=Decimal("0.5"))],
            ),
        )
        services.accept_targets(session, portfolio.id, target.id)
        return {
            **recording.metadata(),
            "company_id": str(company.id),
            "portfolio_id": str(portfolio.id),
            "stock_listing_id": str(listing.id),
            "snapshot_id": str(snapshot.id),
            "target_revision_id": str(target.id),
        }
