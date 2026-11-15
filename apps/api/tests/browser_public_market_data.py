"""Private recorded public-source rehearsal; never a production data fixture.

Only source bytes and timestamps in a reviewed, hash-bound private manifest are
replayed. Portfolio quantities are fictional. No network fallback is available.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event, Thread
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Table, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Insert, Update

from portfolio_api import ecb_reference, eodhd_demo
from portfolio_api.database import Base
from portfolio_api.database_write_target import DatabaseReadOnlyError, _statement_may_write
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import Actor, ExternalIngestionRun
from portfolio_api.external_data import ProviderQuery, RawProviderRecord
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.recurring_operations import process_manual_job_requests, run_recurring_cycle
from portfolio_api.settings import Settings

TABLES = frozenset(
    {
        "market_data_batches",
        "external_raw_payloads",
        "price_observations",
        "fx_observations",
        "external_ingestion_runs",
        "external_ingestion_attempts",
        "operational_job_requests",
        "operational_job_attempts",
        "recurring_operation_runs",
        "recurring_operations_worker_state",
    }
)
JOBS = frozenset({"MARKET_DATA", "FX", "MARKET_AND_FX"})


class PublicMarketControl(BaseModel):
    paused: bool = True
    phase: str = "initial"
    scheduled: bool = False


class PublicMarketReplay:
    def __init__(self, engine: Engine, settings: Settings, manifest_path: Path) -> None:
        self.manifest = json.loads(manifest_path.read_bytes())
        if self.manifest.get("version") != "private-public-market-v1":
            raise ValueError("A reviewed public market recording manifest is required")
        self.records: dict[str, tuple[bytes, datetime]] = {}
        for record in self.manifest["records"]:
            path = (manifest_path.parent / record["file"]).resolve()
            if not path.is_relative_to(manifest_path.parent.resolve()):
                raise ValueError("Recording paths must remain within the private bundle")
            raw = path.read_bytes()
            captured = datetime.fromisoformat(record["retrieved_at"])
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("Recording digest changed")
            if captured.tzinfo is None or captured > datetime.now(UTC):
                raise ValueError("Recording timestamp is invalid")
            if not record["url"].startswith(
                ("https://eodhd.com/api/", "https://data-api.ecb.europa.eu/service/data/EXR/")
            ):
                raise ValueError("Recording source is outside the reviewed providers")
            self.records[record["url"]] = raw, captured
        self.engine = engine
        self.settings = settings.model_copy(
            update={
                "manual_operations_enabled": True,
                "fx_provider": "ECB_REFERENCE",
                "market_data_provider": "EODHD_DEMO",
            }
        )
        self.phase = "initial"
        self.paused = True
        self.calls: list[str] = []
        self.errors: list[str] = []
        self.stopped = Event()
        self.at = datetime.now(UTC)
        self.last_cycle: dict[str, object] | None = None
        with Session(engine) as session, session.begin():
            company = services.create_company(
                session, s.CompanyCreate(name="Amazon", reporting_currency="USD")
            )
            security = services.create_security(
                session,
                company.id,
                s.SecurityCreate(name="Amazon common stock", security_type="COMMON_STOCK"),
            )
            listing = services.create_listing(
                session, security.id, s.ListingCreate(ticker="AMZN", venue="NASDAQ", currency="USD")
            )
            portfolio = services.create_portfolio(
                session,
                s.PortfolioCreate(
                    name="Isolated real sources — fictional quantities", base_currency="EUR"
                ),
            )
            snapshot = services.record_holdings(
                session,
                portfolio.id,
                s.SnapshotCreate(
                    actor=Actor.IMPORT,
                    reason="Fictional quantities; real privately recorded sources",
                    source="isolated-public-market-rehearsal",
                    effective_at=self.at - timedelta(days=1),
                    completeness="COMPLETE",
                    positions=[s.PositionInput(listing_id=listing.id, quantity=Decimal("2.5"))],
                    cash_positions=[
                        s.CashInput(currency="EUR", balance=Decimal("10")),
                        s.CashInput(currency="USD", balance=Decimal("5")),
                        s.CashInput(currency="DKK", balance=Decimal("1000")),
                    ],
                ),
            )
            target = services.create_targets(
                session,
                portfolio.id,
                s.TargetCreate(
                    actor=Actor.IMPORT,
                    reason="Fictional independent target",
                    source="isolated-public-market-rehearsal",
                    effective_at=self.at - timedelta(days=1),
                    allocations=[s.AllocationInput(company_id=company.id, weight=Decimal("1"))],
                ),
            )
            services.accept_targets(session, portfolio.id, target.id)
            self.metadata: dict[str, Any] = {
                "scenario": "public-market-refresh",
                "company_id": str(company.id),
                "listing_id": str(listing.id),
                "portfolio_id": str(portfolio.id),
                "snapshot_id": str(snapshot.id),
                "target_revision_id": str(target.id),
                "fixture_context": (
                    "Fictional quantities and targets; recorded official ECB and EODHD demo data"
                ),
                "expected": self.manifest["expected"],
            }

    def protected_state(self) -> str:
        with self.engine.connect() as connection:
            contents = {
                table.name: connection.scalar(
                    text(
                        f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), "
                        f"'[]'::jsonb)::text FROM \"{table.name}\" t"
                    )
                )
                for table in Base.metadata.sorted_tables
                if table.name not in TABLES
            }
        return hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()

    def readback(self) -> dict[str, Any]:
        with self.engine.connect() as connection:
            counts = {
                name: connection.scalar(text(f'SELECT count(*) FROM "{name}"'))
                for name in sorted(TABLES)
            }
        with Session(self.engine) as session:
            runs = [
                {"provider": row.provider_id, "status": row.status, "scope": row.request_scope}
                for row in session.scalars(select(ExternalIngestionRun))
            ]
        return {
            "provider_fixture": "recorded-real-public-market-v1",
            "counts": counts,
            "offline_transport_calls": len(self.calls),
            "worker_errors": self.errors,
            "protected_state_sha256": self.protected_state(),
            "last_cycle": self.last_cycle,
            "runs": runs,
            "phase": self.phase,
        }

    def download(self, url: str) -> bytes:
        if url not in self.records:
            raise AssertionError("No recording for the exact requested URL; network forbidden")
        self.calls.append(url)
        return self.records[url][0]

    def captured(self, records: list[RawProviderRecord]) -> list[RawProviderRecord]:
        return [
            record.model_copy(update={"retrieved_at": self.records[str(record.source_url)][1]})
            for record in records
        ]

    def run_recorded(self, session: Session, settings: Settings, **kwargs: Any) -> dict[str, Any]:
        # Freeze the two captured request windows explicitly; do not synthesize response rows.
        window = self.manifest["windows"][self.phase]
        kwargs.update(
            start_date=date.fromisoformat(window["start"]),
            end_date=date.fromisoformat(window["end"]),
        )
        return run_scheduled(session, settings, **kwargs)

    def install(self, application: FastAPI) -> None:
        @application.post("/__test/refresh-control")
        def control(value: PublicMarketControl) -> dict[str, Any]:
            if value.phase not in {"initial", "incremental"}:
                raise HTTPException(422, "Unknown recorded window")
            self.paused, self.phase = value.paused, value.phase
            if value.scheduled:
                if not self.paused:
                    raise HTTPException(422, "Pause the manual fixture worker for schedule proof")
                self.last_cycle = run_recurring_cycle(
                    self.settings.model_copy(update={"recurring_operations_enabled": True}),
                    engine=self.engine,
                    now_at=self.at + timedelta(days=3),
                    public_market_only=True,
                )
            return self.readback()

    def _work(self) -> None:
        while not self.stopped.wait(0.25):
            if not self.paused:
                try:
                    process_manual_job_requests(self.engine, self.settings, job_names=JOBS)
                except Exception as error:
                    self.errors.append(type(error).__name__)
                    self.paused = True

    @contextmanager
    def running(self) -> Iterator[None]:
        original_ecb = ecb_reference.EcbReferenceProvider.fetch
        original_eod = eodhd_demo.EodhdDemoProvider.fetch
        original_metadata = eodhd_demo.fetch_demo_metadata

        async def ecb(
            provider: ecb_reference.EcbReferenceProvider, query: ProviderQuery
        ) -> list[RawProviderRecord]:
            provider._transport = self.download
            return self.captured(list(await original_ecb(provider, query)))

        async def eod(
            provider: eodhd_demo.EodhdDemoProvider, query: ProviderQuery
        ) -> list[RawProviderRecord]:
            provider.transport = self.download
            return self.captured(list(await original_eod(provider, query)))

        def metadata() -> RawProviderRecord:
            return self.captured([original_metadata(transport=self.download)])[0]

        def restrict(
            _c: Any, _cursor: Any, statement: str, _p: Any, context: Any, _many: bool
        ) -> None:
            if not _statement_may_write(statement, context):
                return
            command = getattr(getattr(context, "compiled", None), "statement", None)
            if getattr(command, "text", None) in {
                "SELECT pg_advisory_xact_lock(:lock_id)",
                "SELECT pg_try_advisory_lock(:namespace, :lock_key)",
                "SELECT pg_advisory_unlock(:namespace, :lock_key)",
            }:
                return
            if (
                not isinstance(command, (Insert, Update))
                or not isinstance(command.table, Table)
                or command.table.name not in TABLES
            ):
                raise DatabaseReadOnlyError(
                    "fixture_refresh_scope", "Only market refresh writes allowed"
                )

        with ExitStack() as stack:
            stack.enter_context(patch.object(ecb_reference.EcbReferenceProvider, "fetch", ecb))
            stack.enter_context(patch.object(eodhd_demo.EodhdDemoProvider, "fetch", eod))
            stack.enter_context(patch.object(eodhd_demo, "fetch_demo_metadata", metadata))
            stack.enter_context(
                patch("portfolio_api.recurring_operations.run_scheduled", self.run_recorded)
            )
            stack.enter_context(patch("portfolio_api.external_ingestion.time.sleep"))
            event.listen(self.engine, "before_cursor_execute", restrict)
            worker = Thread(target=self._work, daemon=True)
            worker.start()
            try:
                yield
            finally:
                self.stopped.set()
                worker.join(timeout=15)
                event.remove(self.engine, "before_cursor_execute", restrict)
