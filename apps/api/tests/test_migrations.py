"""Integration tests never fall back to the application database.

TEST_DATABASE_URL must explicitly identify a dedicated database ending in _test.
Each run creates and removes only its own randomly named schema in that database.
"""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from portfolio_api.database import Base
from portfolio_api.domain import models  # noqa: F401
from portfolio_api.health import check_readiness
from portfolio_api.migrations import alembic_config, expected_heads
from portfolio_api.settings import Settings


@pytest.mark.integration
def test_postgresql_migration_roundtrip() -> None:
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip(
            "Set TEST_DATABASE_URL to an explicit dedicated PostgreSQL database ending _test"
        )
    # Reuse application URL validation, including rejection of alternative database engines.
    Settings(database_url=SecretStr(raw_url))
    url = make_url(raw_url)
    if not url.database or not url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must use a dedicated database whose name ends in _test")

    schema = f"test_{uuid4().hex}"
    engine = create_engine(
        url,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        hide_parameters=True,
    )
    config = alembic_config()
    created_schema = False
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.commit()
            created_schema = True
            connection.execute(
                text("SELECT set_config('search_path', :schema, false)"), {"schema": schema}
            )
            connection.commit()
            config.attributes["connection"] = connection

            assert MigrationContext.configure(connection).get_current_heads() == ()
            connection.commit()
            command.upgrade(config, "head")
            assert (
                set(MigrationContext.configure(connection).get_current_heads()) == expected_heads()
            )
            assert set(inspect(connection).get_table_names(schema=schema)) == set(
                Base.metadata.tables
            ) | {"alembic_version"}
            connection.commit()

            # A separate pool with the same isolated search path checks real readiness.
            health_engine = create_engine(
                url,
                connect_args={
                    "connect_timeout": 3,
                    "options": f"-c search_path={schema} -c statement_timeout=3000",
                },
                hide_parameters=True,
            )
            try:
                assert check_readiness(health_engine, expected_heads()).status == "ok"
                command.downgrade(config, "base")
                assert MigrationContext.configure(connection).get_current_heads() == ()
                connection.commit()
                assert check_readiness(health_engine, expected_heads()).schema_status == "outdated"
                command.upgrade(config, "head")
                assert check_readiness(health_engine, expected_heads()).status == "ok"
            finally:
                health_engine.dispose()
    finally:
        if created_schema:
            with engine.begin() as cleanup:
                # The identifier is generated locally above, never provided by a caller.
                cleanup.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
