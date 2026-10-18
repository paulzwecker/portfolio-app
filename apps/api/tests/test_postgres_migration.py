"""Fail-closed migration-tool checks and disposable PostgreSQL 18 exercises."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Table, create_engine, text
from sqlalchemy.engine import URL, make_url

from portfolio_api.domain import models
from portfolio_api.migrations import alembic_config
from portfolio_api.postgres_migration import (
    DatabaseEndpoint,
    MigrationToolError,
    _canonical_json,
    _pg_restore,
    backup,
    cutover_preflight,
    endpoint_from_environment,
    reconcile,
    restore,
    schema_check,
    verify_backup,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_ENVIRONMENT_NAMES = (
    "MIGRATION_SOURCE_URL",
    "MIGRATION_SOURCE_SCHEMA",
    "MIGRATION_TARGET_URL",
    "MIGRATION_TARGET_SCHEMA",
    "MIGRATION_EXPECTED_TARGET_HOST",
    "MIGRATION_EXPECTED_TARGET_DATABASE",
    "MIGRATION_PRODUCTION_HOST",
    "MIGRATION_ALLOW_TEST_TARGET",
    "MIGRATION_PG_TOOLS_CONTAINER",
)


def _clear_migration_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in MIGRATION_ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)


def _set_target_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str,
    host: str = "127.0.0.1",
    database: str = "migration_test",
) -> None:
    monkeypatch.setenv("MIGRATION_TARGET_URL", url)
    monkeypatch.setenv("MIGRATION_EXPECTED_TARGET_HOST", host)
    monkeypatch.setenv("MIGRATION_EXPECTED_TARGET_DATABASE", database)
    monkeypatch.setenv("MIGRATION_PRODUCTION_HOST", "protected-production.invalid")


def test_source_does_not_fall_back_to_application_database(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_migration_environment(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://ignored-secret:never-print@127.0.0.1/production_name",
    )

    with pytest.raises(MigrationToolError, match="MIGRATION_SOURCE_URL") as error:
        endpoint_from_environment("source")

    assert "never-print" not in str(error.value)
    assert "production_name" not in str(error.value)


def test_invalid_source_and_ambiguous_target_fail_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_migration_environment(monkeypatch)
    monkeypatch.setenv(
        "MIGRATION_SOURCE_URL",
        "postgresql+psycopg://secret:never-print@remote.example/portfolio_app",
    )
    with pytest.raises(MigrationToolError, match="loopback") as error:
        endpoint_from_environment("source")
    assert "never-print" not in str(error.value)

    monkeypatch.setenv(
        "MIGRATION_TARGET_URL",
        "postgresql+psycopg://secret:never-print@127.0.0.1/migration_test",
    )
    with pytest.raises(MigrationToolError, match="MIGRATION_EXPECTED_TARGET_HOST"):
        endpoint_from_environment("target")


def test_target_requires_exact_isolated_endpoint_and_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_migration_environment(monkeypatch)
    _set_target_environment(
        monkeypatch,
        url="postgresql+psycopg://secret:never-print@127.0.0.1/migration_test",
        host="127.0.0.2",
    )
    with pytest.raises(MigrationToolError, match="expected host"):
        endpoint_from_environment("target")

    _set_target_environment(
        monkeypatch,
        url="postgresql+psycopg://secret:never-print@127.0.0.1/production_test",
        database="migration_test",
    )
    with pytest.raises(MigrationToolError, match="expected name"):
        endpoint_from_environment("target")


def test_production_and_default_database_targets_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_migration_environment(monkeypatch)
    _set_target_environment(
        monkeypatch,
        url="postgresql+psycopg://secret:never-print@production.neon.tech/neondb?sslmode=require",
        host="production.neon.tech",
        database="neondb",
    )
    monkeypatch.setenv("MIGRATION_PRODUCTION_HOST", "production.neon.tech")
    with pytest.raises(MigrationToolError, match="protected production"):
        endpoint_from_environment("target")

    _set_target_environment(
        monkeypatch,
        url="postgresql+psycopg://secret:never-print@branch.neon.tech/neondb?sslmode=require",
        host="branch.neon.tech",
        database="neondb",
    )
    with pytest.raises(MigrationToolError, match="end in _migration"):
        endpoint_from_environment("target")


def test_financial_decimal_fingerprints_preserve_exact_values() -> None:
    left = _canonical_json({"expected_irr": Decimal("0.150000000000000000")})
    right = _canonical_json({"expected_irr": Decimal("0.150000000000000001")})

    assert hashlib.sha256(left).digest() != hashlib.sha256(right).digest()


def test_interrupted_restore_stops_its_child_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class InterruptedProcess:
        returncode = None

        def __init__(self) -> None:
            self.terminated = False

        def communicate(self, timeout: int | None = None) -> tuple[bytes, bytes]:
            if not self.terminated:
                raise KeyboardInterrupt
            return b"", b""

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

    process = InterruptedProcess()
    endpoint = DatabaseEndpoint(
        role="target",
        url=URL.create(
            "postgresql+psycopg", username="test", host="127.0.0.1", database="restore_test"
        ),
        host="127.0.0.1",
        port=5432,
        database="restore_test",
        username="test",
        schema="public",
        test_target=True,
    )
    archive = tmp_path / "interrupted.dump"
    archive.write_bytes(b"synthetic archive")
    monkeypatch.setattr(
        "portfolio_api.postgres_migration._tool_prefix",
        lambda _endpoint, _tool: (["pg_restore"], None),
    )
    monkeypatch.setattr(
        "portfolio_api.postgres_migration.subprocess.Popen", lambda *_args, **_kwargs: process
    )

    with pytest.raises(MigrationToolError, match="Restore interrupted"):
        _pg_restore(endpoint, archive, restore=True)
    assert process.terminated is True


def test_ci_isolated_postgresql_configuration_has_no_migration_credentials() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    quality_job = workflow.split("  integration:", maxsplit=1)[0]
    integration_job = workflow.split("  integration:", maxsplit=1)[1]

    assert "image: postgres:18" in integration_job
    assert re.search(r"TEST_DATABASE_URL: .*_test", integration_job)
    assert "MIGRATION_PG_TOOLS_CONTAINER=$container_id" in integration_job
    assert "MIGRATION_SOURCE_URL" not in workflow
    assert "MIGRATION_TARGET_URL" not in workflow
    assert "NEON" not in workflow.upper()
    assert 'GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE: ""' in workflow
    assert "NEON_DATABASE_URL" not in workflow
    assert "DATABASE_URL" not in quality_job


@pytest.fixture
def migration_databases(monkeypatch: pytest.MonkeyPatch) -> Any:
    raw_url = os.environ.get("TEST_DATABASE_URL")
    tools_container = os.environ.get("MIGRATION_PG_TOOLS_CONTAINER", "")
    if not raw_url:
        pytest.fail(
            "Set TEST_DATABASE_URL to a dedicated local PostgreSQL 18 database ending _test"
        )
    admin_url = make_url(raw_url)
    if (
        admin_url.drivername != "postgresql+psycopg"
        or not admin_url.database
        or not admin_url.database.endswith("_test")
        or admin_url.host not in {"127.0.0.1", "localhost", "::1"}
    ):
        pytest.fail("Migration tests only create databases on a loopback _test PostgreSQL endpoint")
    if not os.environ.get("MIGRATION_PG_TOOLS_CONTAINER") and not shutil.which("pg_dump"):
        pytest.fail("Set MIGRATION_PG_TOOLS_CONTAINER or install PostgreSQL 18 client tools")

    names = [f"m14b1_{uuid4().hex[:12]}_{suffix}_test" for suffix in ("source", "target", "abort")]
    admin_engine = create_engine(
        admin_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        hide_parameters=True,
    )
    created: list[str] = []
    database_urls: dict[str, URL] = {}
    try:
        with admin_engine.connect() as connection:
            for index, name in enumerate(names):
                connection.execute(text(f'CREATE DATABASE "{name}"'))
                created.append(name)
                database_url = admin_url.set(database=name)
                database_urls[name] = database_url
                if index == 0:
                    engine = create_engine(database_url, hide_parameters=True)
                    try:
                        with engine.begin() as migration_connection:
                            config = alembic_config()
                            config.attributes["connection"] = migration_connection
                            command.upgrade(config, "head")
                    finally:
                        engine.dispose()

        source_name, target_name, abort_name = names
        source_url = database_urls[source_name].render_as_string(hide_password=False)
        target_url = database_urls[target_name].render_as_string(hide_password=False)
        _clear_migration_environment(monkeypatch)
        monkeypatch.setenv("MIGRATION_ALLOW_TEST_TARGET", "1")
        if tools_container:
            monkeypatch.setenv("MIGRATION_PG_TOOLS_CONTAINER", tools_container)
        monkeypatch.setenv("MIGRATION_SOURCE_URL", source_url)
        _set_target_environment(
            monkeypatch,
            url=target_url,
            host=database_urls[target_name].host or "127.0.0.1",
            database=target_name,
        )
        yield {
            "admin_engine": admin_engine,
            "admin_url": admin_url,
            "source": source_name,
            "target": target_name,
            "abort": abort_name,
            "source_url": database_urls[source_name],
            "target_url": database_urls[target_name],
            "abort_url": database_urls[abort_name],
        }
    finally:
        for name in reversed(created):
            with admin_engine.connect() as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin_engine.dispose()


def _table(model: Any) -> Table[Any]:
    return cast(Table[Any], model.__table__)


def _insert_synthetic_portfolio(url: URL) -> dict[str, Any]:
    engine = create_engine(url, hide_parameters=True)
    company_id = uuid4()
    security_id = uuid4()
    listing_id = uuid4()
    portfolio_id = uuid4()
    snapshot_id = uuid4()
    model_id = uuid4()
    revision_id = uuid4()
    observation_id = uuid4()
    output_id = uuid4()
    as_of = datetime(2025, 1, 31, 21, 0, tzinfo=UTC)

    try:
        with engine.begin() as connection:
            connection.execute(
                _table(models.Company)
                .insert()
                .values(
                    id=company_id,
                    name="Synthetic Migration Test Company",
                    reporting_currency="USD",
                )
            )
            connection.execute(
                _table(models.Security)
                .insert()
                .values(
                    id=security_id,
                    company_id=company_id,
                    name="Synthetic Common Stock",
                    security_type="COMMON_STOCK",
                )
            )
            connection.execute(
                _table(models.Listing)
                .insert()
                .values(
                    id=listing_id,
                    security_id=security_id,
                    venue="TEST",
                    ticker=f"T{company_id.hex[:5]}",
                    currency="USD",
                )
            )
            connection.execute(
                _table(models.PriceObservation)
                .insert()
                .values(
                    id=observation_id,
                    listing_id=listing_id,
                    market_date=as_of,
                    provider_close=Decimal("90.1234567891"),
                    split_adjusted_close=Decimal("90.1234567891"),
                    total_return_close=Decimal("91.2345678912"),
                    currency="USD",
                    provider="synthetic-test",
                    provider_symbol="TST",
                    adjustment_basis="Synthetic migration fixture",
                    data_quality="PASS",
                    source_ref=f"m14b1-test:{company_id}",
                )
            )
            connection.execute(
                _table(models.Portfolio)
                .insert()
                .values(
                    id=portfolio_id,
                    name="Synthetic Migration Test Portfolio",
                    base_currency="USD",
                )
            )
            connection.execute(
                _table(models.HoldingSnapshot)
                .insert()
                .values(
                    id=snapshot_id,
                    portfolio_id=portfolio_id,
                    effective_at=as_of,
                    actor="LOCAL_USER",
                    reason="Synthetic migration test snapshot",
                    completeness="COMPLETE",
                )
            )
            connection.execute(
                _table(models.HoldingPosition)
                .insert()
                .values(
                    id=uuid4(),
                    snapshot_id=snapshot_id,
                    listing_id=listing_id,
                    quantity=Decimal("1.2345678901"),
                )
            )
            connection.execute(
                _table(models.CashPosition)
                .insert()
                .values(
                    id=uuid4(),
                    snapshot_id=snapshot_id,
                    currency="USD",
                    balance=Decimal("1234.5600000001"),
                )
            )

            # This stable-identity/current-revision cycle is why the toolkit uses
            # a full-schema restore with constraints created after table data.
            connection.execute(
                _table(models.FinancialModel)
                .insert()
                .values(
                    id=model_id,
                    company_id=company_id,
                    valuation_listing_id=listing_id,
                    model_type="UFCF_DCF_10Y_FADE",
                    model_name="Synthetic DCF",
                    model_currency="USD",
                    current_revision_id=None,
                )
            )
            connection.execute(
                _table(models.FinancialModelRevision)
                .insert()
                .values(
                    id=revision_id,
                    model_id=model_id,
                    model_type="UFCF_DCF_10Y_FADE",
                    revision_number=1,
                    methodology_version="synthetic-test-v1",
                    actor="LOCAL_USER",
                    rationale="Synthetic migration test revision",
                    effective_at=as_of,
                )
            )
            connection.execute(
                _table(models.FinancialModel)
                .update()
                .where(_table(models.FinancialModel).c.id == model_id)
                .values(current_revision_id=revision_id)
            )
            connection.execute(
                _table(models.DcfModelAssumptions)
                .insert()
                .values(
                    id=uuid4(),
                    revision_id=revision_id,
                    base_revenue=Decimal("1234567890.123456789012345678"),
                    base_ebit_margin=Decimal("0.213456789012345678"),
                    base_tax_rate=Decimal("0.210000000000000000"),
                    base_da_to_revenue=Decimal("0.030000000000000000"),
                    base_capex_to_revenue=Decimal("0.040000000000000000"),
                    base_nwc_to_revenue=Decimal("0.010000000000000000"),
                    net_cash_debt=Decimal("-1234567.890123456789012345"),
                    diluted_shares=Decimal("98765432.123456789012345678"),
                )
            )
            methodology_id: UUID = connection.execute(
                text(
                    """
                    SELECT id FROM return_methodology_definitions
                     WHERE code = 'UFCF_ENTERPRISE_IRR' AND version = 1
                    """
                )
            ).scalar_one()
            connection.execute(
                _table(models.FinancialModelOutput)
                .insert()
                .values(
                    id=output_id,
                    return_methodology_id=methodology_id,
                    revision_id=revision_id,
                    status="COMPLETE",
                    model_currency="USD",
                    price_observation_id=observation_id,
                    current_price=Decimal("90.123456789100000000"),
                    price_effective_at=as_of,
                    price_status="FRESH",
                    bear_fv=Decimal("80.000000000000000000"),
                    base_fv=Decimal("100.000000000000000000"),
                    bull_fv=Decimal("120.000000000000000000"),
                    bear_probability=Decimal("0.200000000000000000"),
                    base_probability=Decimal("0.600000000000000000"),
                    bull_probability=Decimal("0.200000000000000000"),
                    weighted_fv=Decimal("100.000000000000000000"),
                    weighted_upside=Decimal("0.109580246000000000"),
                    expected_cash_flow_irr=Decimal("0.152340000000000000"),
                    hurdle=Decimal("0.120000000000000000"),
                    expected_excess=Decimal("0.032340000000000000"),
                    forward_fundamental_cagr=Decimal("0.098765432100000000"),
                )
            )
        return {
            "company_id": company_id,
            "listing_id": listing_id,
            "observation_id": observation_id,
            "model_id": model_id,
            "revision_id": revision_id,
            "output_id": output_id,
        }
    finally:
        engine.dispose()


@pytest.mark.integration
def test_postgres18_backup_restore_reconcile_and_atomic_failure(
    migration_databases: dict[str, Any], tmp_path: Path
) -> None:
    source_url = migration_databases["source_url"]
    target_url = migration_databases["target_url"]
    abort_url = migration_databases["abort_url"]

    synthetic_ids = _insert_synthetic_portfolio(source_url)
    source = endpoint_from_environment("source")
    target = endpoint_from_environment("target")
    archive = tmp_path / "synthetic-canonical.dump"
    source_engine = create_engine(source_url, hide_parameters=True)
    try:
        with source_engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE SEQUENCE public.m14b1_migration_sequence_test "
                    "START WITH 41 INCREMENT BY 5"
                )
            )
            connection.execute(
                text(
                    "CREATE SEQUENCE public.m14b1_owned_sequence_test START WITH 91 INCREMENT BY 2"
                )
            )
            connection.execute(
                text(
                    "ALTER SEQUENCE public.m14b1_owned_sequence_test "
                    "OWNED BY public.lifecycle_events.sequence"
                )
            )
            connection.execute(text("SELECT nextval('public.m14b1_migration_sequence_test')"))
            connection.execute(text("SELECT nextval('public.m14b1_owned_sequence_test')"))
    finally:
        source_engine.dispose()

    empty_schema_check = schema_check(source, target)
    assert empty_schema_check["status"] == "EMPTY_TARGET_COMPATIBLE_FOR_FULL_RESTORE"
    assert empty_schema_check["data_only_restore_compatible"] is False
    assert empty_schema_check["source"]["foreign_key_cycles"]
    assert empty_schema_check["source"]["alembic_heads"] == ["12a6f0d9c3e1"]

    backup_result = backup(archive, source)
    assert backup_result["status"] == "BACKUP_CREATED"
    manifest_text = Path(f"{archive}.manifest.json").read_text(encoding="utf-8")
    assert "never-print" not in manifest_text
    assert "Synthetic Migration Test Company" not in manifest_text
    assert "m14b1_migration_sequence_test" in manifest_text
    assert "m14b1_owned_sequence_test" in manifest_text
    assert verify_backup(archive)["status"] == "VALID"

    corrupted_archive = tmp_path / "corrupted.dump"
    shutil.copyfile(archive, corrupted_archive)
    shutil.copyfile(f"{archive}.manifest.json", f"{corrupted_archive}.manifest.json")
    with corrupted_archive.open("ab") as output:
        output.write(b"corruption")
    with pytest.raises(MigrationToolError, match="hash or size"):
        verify_backup(corrupted_archive)

    restore_result = restore(
        archive,
        target,
        confirmation=f"RESTORE {target.host}/{target.database}",
    )
    assert restore_result["status"] == "RESTORED_AND_RECONCILED"
    assert restore_result["target"]["alembic_heads"] == ["12a6f0d9c3e1"]
    target_engine = create_engine(target_url, hide_parameters=True)
    try:
        with target_engine.connect() as connection:
            sequence_states = {
                name: connection.execute(
                    text(f"SELECT last_value, is_called FROM public.{name}")
                ).one()
                for name in ("m14b1_migration_sequence_test", "m14b1_owned_sequence_test")
            }
            assert sequence_states == {
                "m14b1_migration_sequence_test": (41, True),
                "m14b1_owned_sequence_test": (91, True),
            }
            ownership = connection.execute(
                text(
                    """
                    SELECT owner.relname, owner_column.attname
                      FROM pg_class AS sequence
                      JOIN pg_namespace AS sequence_schema
                        ON sequence_schema.oid = sequence.relnamespace
                      JOIN pg_depend AS dependency
                        ON dependency.classid = 'pg_class'::regclass
                       AND dependency.objid = sequence.oid
                       AND dependency.refclassid = 'pg_class'::regclass
                       AND dependency.deptype = 'a'
                      JOIN pg_class AS owner ON owner.oid = dependency.refobjid
                      JOIN pg_attribute AS owner_column
                        ON owner_column.attrelid = owner.oid
                       AND owner_column.attnum = dependency.refobjsubid
                     WHERE sequence_schema.nspname = 'public'
                       AND sequence.relname = 'm14b1_owned_sequence_test'
                    """
                )
            ).one()
            assert ownership == ("lifecycle_events", "sequence")
    finally:
        target_engine.dispose()
    assert reconcile(source, target)["status"] == "MATCH"

    preflight = cutover_preflight(source, target, archive)
    assert preflight["status"] == "READY_FOR_SEPARATE_PRODUCTION_REVIEW"
    assert preflight["production_accessed"] is False
    assert preflight["production_modified"] is False

    target_engine = create_engine(target_url, hide_parameters=True)
    try:
        with target_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE financial_model_outputs
                       SET expected_cash_flow_irr = :irr
                     WHERE id = :output_id
                    """
                ),
                {
                    "irr": Decimal("0.152340000000000001"),
                    "output_id": synthetic_ids["output_id"],
                },
            )
    finally:
        target_engine.dispose()
    difference = reconcile(source, target)
    assert difference["status"] == "DIFFERENCES_FOUND"
    assert difference["tables"]["financial_model_outputs"]["changed_rows"] == 1
    assert difference["tables"]["financial_model_outputs"]["matches"] is False

    incompatible_engine = create_engine(target_url, hide_parameters=True)
    try:
        with incompatible_engine.begin() as connection:
            connection.execute(text("ALTER TABLE companies ADD COLUMN migration_test_extra text"))
        with pytest.raises(MigrationToolError, match="schema definitions"):
            schema_check(source, target)
        with incompatible_engine.begin() as connection:
            connection.execute(text("ALTER TABLE companies DROP COLUMN migration_test_extra"))
    finally:
        incompatible_engine.dispose()

    abort_target = DatabaseEndpoint(
        role="target",
        url=abort_url,
        host=abort_url.host or "127.0.0.1",
        port=abort_url.port or 5432,
        database=abort_url.database or "",
        username=abort_url.username or "postgres",
        schema="public",
        test_target=True,
    )
    _install_restore_failure_trigger(abort_url)
    with pytest.raises(MigrationToolError, match="transaction was rolled back"):
        _pg_restore(abort_target, archive, restore=True)
    abort_engine = create_engine(abort_url, hide_parameters=True)
    try:
        with abort_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT to_regclass('public.companies')")).scalar_one()
                is None
            )
            assert (
                connection.execute(
                    text("SELECT to_regclass('public.financial_models')")
                ).scalar_one()
                is None
            )
    finally:
        abort_engine.dispose()


def _install_restore_failure_trigger(url: URL) -> None:
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE FUNCTION public.m14b1_fail_company_insert()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                        RAISE EXCEPTION 'synthetic restore rollback test';
                    END;
                    $$
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE FUNCTION public.m14b1_install_company_insert_trigger()
                    RETURNS event_trigger LANGUAGE plpgsql AS $$
                    DECLARE command record;
                    BEGIN
                        FOR command IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
                            IF command.object_identity = 'public.companies' THEN
                                EXECUTE 'CREATE TRIGGER m14b1_fail_company_insert '
                                     || 'BEFORE INSERT ON public.companies '
                                     || 'FOR EACH ROW EXECUTE FUNCTION '
                                     || 'public.m14b1_fail_company_insert()';
                            END IF;
                        END LOOP;
                    END;
                    $$
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE EVENT TRIGGER m14b1_install_company_insert_trigger
                    ON ddl_command_end WHEN TAG IN ('CREATE TABLE')
                    EXECUTE FUNCTION public.m14b1_install_company_insert_trigger()
                    """
                )
            )
    finally:
        engine.dispose()
