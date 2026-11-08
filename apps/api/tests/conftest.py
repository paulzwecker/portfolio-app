"""Explicit test database only; every integration test gets its own migrated schema."""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from portfolio_api.domain import models  # noqa: F401
from portfolio_api.migrations import alembic_config


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    unclassified = sorted(
        {
            item.nodeid.split("[", 1)[0]
            for item in items
            if isinstance(item, pytest.Function)
            and "postgres_engine" in item.fixturenames
            and item.get_closest_marker("integration") is None
            and item.get_closest_marker("source_data") is None
        }
    )
    if unclassified:
        raise pytest.UsageError(
            "PostgreSQL tests require @pytest.mark.integration for CI coverage:\n"
            + "\n".join(unclassified)
        )


@pytest.fixture
def postgres_engine(request: pytest.FixtureRequest) -> Iterator[Engine]:
    if (
        request.node.get_closest_marker("integration") is None
        and request.node.get_closest_marker("source_data") is None
    ):
        pytest.fail(
            "PostgreSQL tests require @pytest.mark.integration for CI coverage", pytrace=False
        )
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending _test")
    url = make_url(raw)
    if (
        url.drivername != "postgresql+psycopg"
        or not url.database
        or not url.database.endswith("_test")
    ):
        pytest.fail("Integration requires an explicit postgresql+psycopg database ending _test")
    schema = f"test_{uuid4().hex}"
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
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
