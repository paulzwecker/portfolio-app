from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    install_database_write_target_guard,
)
from portfolio_api.settings import Settings


def _settings(engine: Engine, **overrides: object) -> Settings:
    raw_url = engine.url.render_as_string(hide_password=False)
    return Settings.model_validate(
        {
            "database_url": SecretStr(raw_url),
            "database_target_environment": "development",
            "database_target_database": engine.url.database,
            "database_local_test_writes_authorized": True,
            **overrides,
        }
    )


@pytest.mark.integration
def test_live_disposable_postgres_write_is_audited_and_uses_guarded_connection(
    postgres_engine: Engine,
) -> None:
    audit: list[Mapping[str, Any]] = []
    settings = _settings(postgres_engine)
    install_database_write_target_guard(
        postgres_engine,
        settings,
        operation="write_target_integration",
        operation_kind="application",
        audit_sink=audit.append,
    )
    table = f"write_guard_{uuid4().hex}"

    with postgres_engine.begin() as connection:
        connection.execute(text(f'CREATE TEMP TABLE "{table}" (value integer NOT NULL)'))
        connection.execute(text(f'INSERT INTO "{table}" (value) VALUES (17)'))
        assert connection.execute(text(f'SELECT value FROM "{table}"')).scalar_one() == 17

    assert len(audit) == 1
    assert audit[0]["event"] == "database_write_target_approved"
    assert audit[0]["provider"] == "local_postgresql"
    assert audit[0]["environment"] == "development"
    assert "password" not in str(audit[0])
    assert "127.0.0.1" not in str(audit[0])


@pytest.mark.integration
def test_incorrect_local_environment_is_rejected_before_postgres_write(
    postgres_engine: Engine,
) -> None:
    audit: list[Mapping[str, Any]] = []
    settings = _settings(
        postgres_engine,
        database_target_environment="rehearsal",
        database_target_database=postgres_engine.url.database,
    )
    install_database_write_target_guard(
        postgres_engine,
        settings,
        operation="reject_wrong_environment",
        operation_kind="application",
        audit_sink=audit.append,
    )
    table = f"write_guard_rejected_{uuid4().hex}"

    with postgres_engine.connect() as connection:
        with pytest.raises(DatabaseWriteTargetError, match="local_target_environment_mismatch"):
            connection.execute(text(f'CREATE TABLE "{table}" (value integer NOT NULL)'))
        assert (
            connection.execute(
                text("SELECT to_regclass(:table_name)"), {"table_name": table}
            ).scalar_one()
            is None
        )
        connection.rollback()

    assert audit == []


@pytest.mark.integration
def test_live_postgres_rejects_role_without_application_table_privileges(
    postgres_engine: Engine,
) -> None:
    role = f"write_guard_no_priv_{uuid4().hex}"
    schema: str
    with postgres_engine.begin() as connection:
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
        connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')

    try:
        audit: list[Mapping[str, Any]] = []
        with postgres_engine.connect() as connection:
            connection.exec_driver_sql(f'SET ROLE "{role}"')
            guard = install_database_write_target_guard(
                postgres_engine,
                _settings(postgres_engine),
                operation="reject_insufficient_table_privileges",
                operation_kind="application",
                audit_sink=audit.append,
            )
            with pytest.raises(DatabaseWriteTargetError, match="insufficient_table_privileges"):
                guard.verify_connection(connection)
            driver_connection = connection.connection.driver_connection
            assert driver_connection is not None
            cursor = driver_connection.cursor()
            cursor.execute("RESET ROLE")
            cursor.close()
            connection.rollback()
        assert audit == []
    finally:
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'REVOKE USAGE ON SCHEMA "{schema}" FROM "{role}"')
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')


@pytest.mark.integration
def test_live_postgres_migration_rejects_role_that_does_not_own_existing_objects(
    postgres_engine: Engine,
) -> None:
    role = f"write_guard_no_owner_{uuid4().hex}"
    schema: str
    with postgres_engine.begin() as connection:
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
        connection.exec_driver_sql(f'GRANT USAGE, CREATE ON SCHEMA "{schema}" TO "{role}"')

    try:
        audit: list[Mapping[str, Any]] = []
        with postgres_engine.connect() as connection:
            connection.exec_driver_sql(f'SET ROLE "{role}"')
            guard = install_database_write_target_guard(
                postgres_engine,
                _settings(postgres_engine),
                operation="reject_incomplete_migration_privileges",
                operation_kind="schema_migration",
                audit_sink=audit.append,
            )
            with pytest.raises(DatabaseWriteTargetError, match="insufficient_schema_ownership"):
                guard.verify_connection(connection)
            driver_connection = connection.connection.driver_connection
            assert driver_connection is not None
            cursor = driver_connection.cursor()
            cursor.execute("RESET ROLE")
            cursor.close()
            connection.rollback()
        assert audit == []
    finally:
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'REVOKE USAGE, CREATE ON SCHEMA "{schema}" FROM "{role}"')
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
