"""Live browser fixture server: migrate/seed only a test-owned PostgreSQL schema."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Timer
from typing import Any, cast
from uuid import UUID, uuid4

import uvicorn
from alembic import command
from browser_ledger_ownership import prepare_ledger_ownership
from browser_portfolio_data import PortfolioDataState, prepare_portfolio_data
from browser_sec_data import prepare_sec_data
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Insert
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from test_cloud_market_refresh import table_counts

from portfolio_api.database_write_target import (
    DatabaseReadOnlyError,
    _statement_may_write,
    install_database_read_only_guard,
)
from portfolio_api.domain import queries
from portfolio_api.domain.routes import ledger_write_session_for
from portfolio_api.domain.seed import seed
from portfolio_api.main import create_app
from portfolio_api.migrations import alembic_config, expected_heads
from portfolio_api.settings import Settings


def local_test_url(raw: str | None) -> URL:
    if not raw:
        raise SystemExit("Set TEST_DATABASE_URL to a dedicated database ending _test")
    try:
        url = make_url(raw)
    except Exception:
        raise SystemExit("TEST_DATABASE_URL is malformed") from None
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not url.database
        or not url.database.endswith("_test")
        or {"host", "hostaddr", "service", "servicefile", "dbname", "database", "port"}
        & url.query.keys()
    ):
        raise SystemExit(
            "Browser fixtures require a loopback PostgreSQL _test database without target overrides"
        )
    return url


def verify_local_identity(connection: Connection, url: URL) -> None:
    database, address = connection.execute(
        text("SELECT current_database(), host(inet_server_addr())")
    ).one()
    if (
        database != url.database
        or not isinstance(address, str)
        or not ipaddress.ip_address(address).is_loopback
    ):
        raise SystemExit("Browser fixture database identity did not match its local test target")


def fixture_settings() -> Settings:
    return Settings(
        _env_file=None,
        _env_prefix="PORTFOLIO_BROWSER_FIXTURE_",
        app_env="development",
        database_url=None,
        database_target_environment="development",
        database_production_writes_authorized=False,
        database_rehearsal_writes_authorized=False,
        recurring_operations_enabled=False,
        cloud_ingestion_enabled=False,
        manual_operations_enabled=False,
        google_sheets_poll_seconds=0,
    )


def fixture_read_engine(url: URL, schema: str, settings: Settings) -> Engine:
    local_test_url(url.render_as_string(hide_password=False))
    if not re.fullmatch(r"test_(?:browser_)?[a-f0-9]{32}", schema):
        raise SystemExit("Read-only browser access requires a test-owned schema")
    reader = create_engine(
        url,
        pool_size=2,
        max_overflow=2,
        connect_args={
            "connect_timeout": 3,
            "options": (
                f"-c search_path={schema} -c statement_timeout=5000 "
                "-c default_transaction_read_only=on"
            ),
        },
        hide_parameters=True,
    )
    install_database_read_only_guard(reader, settings)
    return reader


def protected_state(engine: Engine, portfolio_id: str, *, ledger_receipts: bool = False) -> str:
    with Session(engine) as session:
        overview = queries.overview(session, UUID(portfolio_id))
        value = {
            "snapshot": overview.snapshot.model_dump(mode="json") if overview.snapshot else None,
            "targets": overview.target_revision.model_dump(mode="json")
            if overview.target_revision
            else None,
            "counts": {
                key: count
                for key, count in table_counts(engine).items()
                if not ledger_receipts
                or key not in {"portfolio_ledger_candidates", "portfolio_ledger_reviews"}
            },
        }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fixture_ledger_writer(url: URL, schema: str) -> Engine:
    local_test_url(url.render_as_string(hide_password=False))
    if not re.fullmatch(r"test_(?:browser_)?[a-f0-9]{32}", schema):
        raise SystemExit("Ledger browser writes require an isolated test-owned schema")
    writer = create_engine(
        url,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": f"-c search_path={schema} -c statement_timeout=5000",
        },
    )
    with writer.connect() as connection:
        verify_local_identity(connection, url)

    def restrict(
        _connection: Any, _cursor: Any, statement: str, _parameters: Any, context: Any, _many: bool
    ) -> None:
        if not _statement_may_write(statement, context):
            return
        compiled = getattr(context, "compiled", None)
        command = getattr(compiled, "statement", None)
        if (
            not isinstance(command, Insert)
            or command.table.schema not in {None, schema}
            or command.table.name
            not in {
                "portfolio_ledger_candidates",
                "portfolio_ledger_reviews",
            }
        ):
            raise DatabaseReadOnlyError(
                "fixture_ledger_scope", "Fixture writes are restricted to new ledger receipts"
            )

    event.listen(writer, "before_cursor_execute", restrict)
    return writer


def fixture_application(
    engine: Engine,
    settings: Settings,
    metadata: dict[str, object] | None = None,
    *,
    ledger_writer: Engine | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.database_engine = engine
        application.state.migration_heads = expected_heads()
        yield

    application = create_app(settings)
    application.router.lifespan_context = lifespan
    if ledger_writer is not None:
        if metadata is None or metadata.get("ledger_receipts_only") is not True:
            raise ValueError("Ledger fixture writes require explicit test-only metadata")
        writer_app = create_app(settings)
        writer_app.state.database_engine = ledger_writer

        def write_session() -> Iterator[Session]:
            yield from ledger_write_session_for(Request({"type": "http", "app": writer_app}))

        application.dependency_overrides[ledger_write_session_for] = write_session
    if metadata is not None:

        @application.middleware("http")
        async def read_only_fixture(
            request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
            ledger_preview = (
                request.method == "POST"
                and request.url.path == f"/v1/portfolios/{metadata['portfolio_id']}/ledger/preview"
            )
            ledger_review = (
                ledger_writer is not None
                and request.method == "POST"
                and re.fullmatch(
                    rf"/v1/portfolios/{metadata['portfolio_id']}/ledger/candidates(?:/[a-f0-9-]{{36}}/review)?",
                    request.url.path,
                )
                is not None
            )
            if request.method not in {"GET", "HEAD"} and not ledger_preview and not ledger_review:
                return JSONResponse(
                    {"detail": "This fixture supports read-only inspection."}, status_code=405
                )
            return await call_next(request)

        @application.get("/__test/fixture")
        def fixture_identity() -> dict[str, object]:
            return {
                **metadata,
                "test_only": "portfolio-data-v1",
                "protected_state_sha256": protected_state(
                    engine, str(metadata["portfolio_id"]), ledger_receipts=ledger_writer is not None
                ),
            }

    return application


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "demo",
            "unpriced",
            "fx-outage",
            "valued",
            "ledger-review",
            "ledger-owned",
            "sec-covered",
            "sec-outage",
            "sec-unmapped",
            "sec-refresh-partial",
            "sec-refresh-outage",
        ),
        default="demo",
    )
    parser.add_argument("--lifetime-seconds", type=int, default=None)
    args = parser.parse_args(argv)
    if args.lifetime_seconds is not None and not 1 <= args.lifetime_seconds <= 600:
        parser.error("Fixture lifetime must be between 1 and 600 seconds")
    url = local_test_url(os.environ.get("TEST_DATABASE_URL"))
    settings = fixture_settings()
    schema = f"test_browser_{uuid4().hex}"
    admin = create_engine(url, connect_args={"connect_timeout": 3}, hide_parameters=True)
    with admin.begin() as connection:
        verify_local_identity(connection, url)
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        connect_args={
            "connect_timeout": 3,
            "options": f"-c search_path={schema} -c statement_timeout=5000",
        },
        hide_parameters=True,
    )
    reader: Engine | None = None
    ledger_writer: Engine | None = None
    try:
        with engine.begin() as connection:
            config = alembic_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        metadata = None
        if args.scenario == "demo":
            with Session(engine) as session, session.begin():
                seed(session)
        else:
            with TemporaryDirectory(prefix="portfolio-browser-") as directory:
                metadata = prepare_portfolio_data(
                    engine,
                    Path(directory),
                    "unpriced"
                    if args.scenario.startswith("sec-")
                    or args.scenario in {"ledger-review", "ledger-owned"}
                    else cast(PortfolioDataState, args.scenario),
                    settings,
                )
                if args.scenario.startswith("sec-"):
                    prepare_sec_data(engine, metadata, args.scenario)
            if args.scenario == "ledger-owned":
                prepare_ledger_ownership(engine, metadata)
            metadata["schema"] = schema
            reader = fixture_read_engine(url, schema, settings)
        if args.scenario == "ledger-review":
            assert metadata is not None
            metadata["ledger_receipts_only"] = True
            ledger_writer = fixture_ledger_writer(url, schema)
        application = fixture_application(
            reader or engine, settings, metadata, ledger_writer=ledger_writer
        )
        port = int(os.environ.get("BROWSER_API_PORT", "8000"))
        server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port))
        lifetime = args.lifetime_seconds or (120 if metadata is not None else None)
        print("Isolated fictional browser fixtures ready.")
        if lifetime:
            print(f"Fixture lifetime {lifetime} seconds. Normal shutdown removes its test schema.")
        deadline = Timer(lifetime, setattr, (server, "should_exit", True)) if lifetime else None
        if deadline is not None:
            deadline.daemon = True
            deadline.start()
        try:
            server.run()
        finally:
            if deadline is not None:
                deadline.cancel()
    finally:
        if ledger_writer is not None:
            ledger_writer.dispose()
        if reader is not None:
            reader.dispose()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
        print("Removed the test-owned browser schema.")


if __name__ == "__main__":
    main()
