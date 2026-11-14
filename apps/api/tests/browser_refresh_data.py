"""Recorded fictional SEC responses through the real queue, importer and database.

Only the isolated browser server imports this module. No provider network is used.
"""

import hashlib
import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import Any
from unittest.mock import patch
from urllib.error import URLError
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Table, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Insert, Update
from test_fundamentals_bootstrap import CIK

from portfolio_api.database import Base
from portfolio_api.database_write_target import DatabaseReadOnlyError, _statement_may_write
from portfolio_api.domain.models import ExternalIngestionRun
from portfolio_api.recurring_operations import process_manual_job_requests, run_recurring_cycle
from portfolio_api.reported_fundamentals import record_cik_mapping
from portfolio_api.settings import Settings

REFRESH_TABLES = frozenset(
    {
        "external_raw_payloads",
        "external_ingestion_runs",
        "external_ingestion_attempts",
        "reported_fundamental_batches",
        "reported_fundamental_observations",
        "source_document_batches",
        "source_documents",
        "operational_job_requests",
        "operational_job_attempts",
        "recurring_operation_runs",
        "recurring_operations_worker_state",
    }
)
SEC_JOBS = frozenset({"SEC_FUNDAMENTALS", "SEC_FILINGS"})


class FixtureControl(BaseModel):
    paused: bool = True
    response: str = "initial"
    scheduled_days_later: int | None = None


class RefreshRehearsal:
    def __init__(self, engine: Engine, settings: Settings, metadata: dict[str, object]) -> None:
        self.engine = engine
        self.settings = settings.model_copy(
            update={
                "manual_operations_enabled": True,
                "sec_user_agent": "Recorded fictional browser fixture test@example.invalid",
            }
        )
        self.metadata = metadata
        self.paused = True
        self.response = "initial"
        self.calls: list[str] = []
        self.errors: list[str] = []
        self.stopped = Event()
        self.at = datetime.now(UTC)
        self.last_cycle: dict[str, object] | None = None
        with Session(engine) as session, session.begin():
            record_cik_mapping(
                session,
                UUID(str(metadata["company_id"])),
                CIK,
                "Synthetic Holdings Inc.",
                "https://www.sec.gov/edgar/browse/?CIK=1",
            )

    def protected_state(self) -> str:
        """Hash contents, not just counts, of every table outside this refresh scope."""
        contents = {}
        with self.engine.connect() as connection:
            for table in Base.metadata.sorted_tables:
                if table.name not in REFRESH_TABLES:
                    contents[table.name] = connection.scalar(
                        text(
                            f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), "
                            f"'[]'::jsonb)::text FROM \"{table.name}\" t"
                        )
                    )
        return hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()

    def readback(self) -> dict[str, object]:
        with self.engine.connect() as connection:
            counts = {
                name: connection.scalar(text(f'SELECT count(*) FROM "{name}"'))
                for name in sorted(REFRESH_TABLES)
            }
        with Session(self.engine) as session:
            scopes = [run.request_scope for run in session.scalars(select(ExternalIngestionRun))]
        return {
            "provider_fixture": "recorded-fictional-sec-v1",
            "provider_request_count": len(self.calls),
            "provider_urls": self.calls,
            "counts": counts,
            "scopes": scopes,
            "worker_errors": self.errors,
            "protected_state_sha256": self.protected_state(),
            "last_cycle": self.last_cycle,
        }

    def download(self, url: str, _agent: str) -> bytes:
        if url not in {
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json",
            f"https://data.sec.gov/submissions/CIK{CIK}.json",
        }:
            raise AssertionError("Recorded fixture rejects an unexpected provider target")
        self.calls.append(url)
        if self.response == "outage":
            raise URLError("Recorded fixture: SEC temporarily unavailable")
        filename = f"facts-{self.response}.json" if "companyfacts" in url else "submissions.json"
        return (Path(__file__).parent / "recorded" / "sec-refresh" / filename).read_bytes()

    def install(self, application: FastAPI) -> None:
        @application.post("/__test/refresh-control")
        def control(value: FixtureControl) -> dict[str, object]:
            if value.response not in {"initial", "updated", "outage", "partial"}:
                raise HTTPException(422, "Unknown recorded response")
            if value.scheduled_days_later is not None and not 0 <= value.scheduled_days_later <= 7:
                raise HTTPException(422, "Fixture clock is bounded to seven days")
            self.paused, self.response = value.paused, value.response
            if value.scheduled_days_later is not None:
                if not value.paused:
                    raise HTTPException(422, "Pause the manual fixture worker for scheduled proof")
                at = self.at + timedelta(days=value.scheduled_days_later)
                with (
                    patch("portfolio_api.recurring_operations.datetime", wraps=datetime) as clock,
                    patch(
                        "portfolio_api.external_ingestion.datetime", wraps=datetime
                    ) as source_clock,
                ):
                    clock.now.return_value = source_clock.now.return_value = at
                    self.last_cycle = run_recurring_cycle(
                        self.settings.model_copy(update={"recurring_operations_enabled": True}),
                        engine=self.engine,
                        now_at=at,
                        sec_only=True,
                    )
            return self.readback()

    def _work(self) -> None:
        while not self.stopped.wait(0.25):
            if not self.paused:
                try:
                    process_manual_job_requests(self.engine, self.settings, job_names=SEC_JOBS)
                except Exception as error:
                    self.errors.append(type(error).__name__)
                    self.paused = True

    @contextmanager
    def running(self) -> Iterator[None]:
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
                or command.table.name not in REFRESH_TABLES
            ):
                raise DatabaseReadOnlyError(
                    "fixture_refresh_scope", "Only SEC refresh writes allowed"
                )

        with ExitStack() as stack:
            stack.enter_context(
                patch("portfolio_api.reported_fundamentals._download_sec_json", self.download)
            )
            stack.enter_context(
                patch("portfolio_api.source_documents._download_sec_json", self.download)
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
