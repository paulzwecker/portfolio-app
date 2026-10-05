"""Live browser fixture server: migrate/seed only a test-owned PostgreSQL schema."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import uvicorn
from alembic import command
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from portfolio_api.domain.seed import seed
from portfolio_api.main import create_app
from portfolio_api.migrations import alembic_config, expected_heads


def main() -> None:
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        raise SystemExit("Set TEST_DATABASE_URL to a dedicated database ending _test")
    url = make_url(raw)
    if (
        url.drivername != "postgresql+psycopg"
        or not url.database
        or not url.database.endswith("_test")
    ):
        raise SystemExit("Browser fixtures require postgresql+psycopg and a database ending _test")
    schema = f"test_browser_{uuid4().hex}"
    admin = create_engine(url, connect_args={"connect_timeout": 3}, hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        connect_args={
            "connect_timeout": 3,
            "options": f"-c search_path={schema} -c statement_timeout=5000",
        },
        hide_parameters=True,
    )
    try:
        with engine.begin() as connection:
            config = alembic_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with Session(engine) as session, session.begin():
            seed(session)

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncIterator[None]:
            application.state.database_engine = engine
            application.state.migration_heads = expected_heads()
            yield

        application = create_app()
        application.router.lifespan_context = lifespan
        print("Isolated fictional browser fixtures ready; Ctrl+C removes their schema.")
        port = int(os.environ.get("BROWSER_API_PORT", "8000"))
        uvicorn.run(application, host="127.0.0.1", port=port)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
