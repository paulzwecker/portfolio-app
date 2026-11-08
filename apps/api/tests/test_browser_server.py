import json
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from browser_portfolio_data import PortfolioDataState, prepare_portfolio_data
from browser_server import (
    fixture_application,
    fixture_read_engine,
    fixture_settings,
    local_test_url,
    main,
    verify_local_identity,
)
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.orm import Session

from portfolio_api.database_write_target import DatabaseReadOnlyError
from portfolio_api.domain import queries


@pytest.mark.parametrize(
    "url",
    [
        None,
        "malformed-private-value",
        "sqlite://",
        "postgresql+psycopg://role:private@127.0.0.1/neondb",
        "postgresql+psycopg://role:private@remote.example/portfolio_test",
        "postgresql+psycopg://role:private@localhost/portfolio_test?host=remote.example",
        "postgresql+psycopg://role:private@localhost/portfolio_test?service=other",
    ],
)
def test_browser_fixture_target_rejection_is_sanitized(url: str | None) -> None:
    with pytest.raises(SystemExit) as result:
        local_test_url(url)
    assert "private" not in str(result.value)
    assert "remote.example" not in str(result.value)


@pytest.mark.parametrize("identity", [("other_test", "127.0.0.1"), ("portfolio_test", "10.0.0.2")])
def test_browser_fixture_verifies_live_identity_before_schema_creation(
    identity: tuple[str, str],
) -> None:
    connection = Mock()
    connection.execute.return_value.one.return_value = identity
    with pytest.raises(SystemExit, match="identity did not match"):
        verify_local_identity(
            cast(Connection, connection), make_url("postgresql+psycopg://localhost/portfolio_test")
        )


def test_browser_fixture_settings_ignore_operator_credentials_and_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "APP_ENV": "production",
        "DATABASE_URL": "private-invalid-value",
        "NEON_API_KEY": "private",
        "API_ACCESS_TOKEN": "private",
        "GOOGLE_SHEETS_SPREADSHEET_ID": "private",
        "RECURRING_OPERATIONS_ENABLED": "true",
        "MANUAL_OPERATIONS_ENABLED": "true",
        "DATABASE_PRODUCTION_WRITES_AUTHORIZED": "true",
    }.items():
        monkeypatch.setenv(key, value)
    settings = fixture_settings()
    assert settings.app_env == "development"
    assert settings.database_url is settings.neon_api_key is settings.api_access_token is None
    assert settings.google_sheets_spreadsheet_id is None
    assert not settings.recurring_operations_enabled
    assert not settings.manual_operations_enabled
    assert not settings.database_production_writes_authorized


def test_browser_reader_rejects_an_unowned_schema() -> None:
    with pytest.raises(SystemExit, match="test-owned schema"):
        fixture_read_engine(
            make_url("postgresql+psycopg://localhost/portfolio_test"), "public", fixture_settings()
        )


@pytest.mark.integration
@pytest.mark.parametrize("fails", [False, True])
def test_fixture_main_cleans_its_schema_on_normal_and_failed_server_exit(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    server = Mock()
    if fails:
        server.run.side_effect = RuntimeError("Synthetic fixture server failure")
    monkeypatch.setattr("browser_server.uvicorn.Server", lambda _config: server)
    with postgres_engine.connect() as connection:
        before = set(
            connection.scalars(
                text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'test_browser_%'")
            )
        )
    if fails:
        with pytest.raises(RuntimeError, match="Synthetic fixture server failure"):
            main(["--scenario", "valued", "--lifetime-seconds", "30"])
    else:
        main(["--scenario", "valued", "--lifetime-seconds", "30"])
    with postgres_engine.connect() as connection:
        after = set(
            connection.scalars(
                text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'test_browser_%'")
            )
        )
    assert after == before


@pytest.mark.integration
@pytest.mark.parametrize("state", ["unpriced", "fx-outage", "valued"])
def test_actual_browser_fixture_import_and_read_only_application(
    postgres_engine: Engine,
    tmp_path: Path,
    state: PortfolioDataState,
) -> None:
    settings = fixture_settings()
    with postgres_engine.connect() as connection:
        verify_local_identity(connection, postgres_engine.url)
        schema = str(connection.scalar(text("SELECT current_schema()")))
    metadata = prepare_portfolio_data(postgres_engine, tmp_path, state, settings)
    with Session(postgres_engine) as session:
        from uuid import UUID

        overview = queries.overview(session, UUID(str(metadata["portfolio_id"])))
        assert overview.base_market_value == (Decimal("391.75") if state == "valued" else None)
        assert overview.snapshot is not None and len(overview.snapshot.positions) == 2
        assert len(overview.snapshot.cash_positions) == 2
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with reader.connect() as connection:
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
        with TestClient(fixture_application(reader, settings, metadata)) as client:
            initial = client.get("/__test/fixture").json()
            assert client.get("/health/ready").status_code == 200
            assert (
                client.get(f"/v1/portfolios/{metadata['portfolio_id']}/overview").status_code == 200
            )
            assert client.get("/v1/recurring-operations/status").status_code == 200
            assert client.post("/v1/ranking-runs", json={}).status_code == 405
            ledger_path = f"/v1/portfolios/{metadata['portfolio_id']}/ledger"
            anchor = client.get(f"{ledger_path}/anchor").json()
            account_id = "11111111-1111-4111-8111-111111111111"
            at = datetime.now(UTC).isoformat()
            positions = anchor["snapshot"]["positions"]
            cash = anchor["snapshot"]["cash_positions"]
            opening = {
                "account_id": account_id,
                "name": "Synthetic unallocated opening",
                "kind": "UNALLOCATED_OPENING",
                "broker_name": None,
                "evidence": {"source_sha256": "d" * 64, "source_record_id": "opening"},
                "positions": positions,
                "cash": cash,
            }
            packet = {
                "contract_version": "portfolio-ledger-preview-v1",
                "anchor_snapshot_id": anchor["snapshot"]["id"],
                "anchor_sha256": anchor["anchor_sha256"],
                "as_of": at,
                "accounts": [opening],
                "activity": [],
                "ending_statement": {
                    "effective_at": at,
                    "accounts": [
                        {
                            "account_id": account_id,
                            "evidence": {"source_sha256": "e" * 64, "source_record_id": "ending"},
                            "positions": positions,
                            "cash": cash,
                        }
                    ],
                },
            }
            result = client.post(f"{ledger_path}/preview", json=packet)
            assert result.status_code == 200 and result.json()["status"] == "ENDING_RECONCILED"
            assert client.delete(f"{ledger_path}/preview").status_code == 405
            assert (
                client.post(
                    "/v1/portfolios/11111111-1111-4111-8111-111111111111/ledger/preview",
                    json=packet,
                ).status_code
                == 405
            )
            assert (
                client.post(
                    f"/v1/portfolios/{metadata['portfolio_id']}/holding-snapshots", json={}
                ).status_code
                == 405
            )
            assert (
                client.get("/__test/fixture").json()["protected_state_sha256"]
                == initial["protected_state_sha256"]
            )
        with reader.begin() as connection, pytest.raises(DatabaseReadOnlyError):
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
            connection.execute(text("UPDATE portfolios SET name = 'forbidden'"))
    finally:
        reader.dispose()


@pytest.mark.parametrize(
    "difference",
    [
        None,
        "database",
        "address",
        "port",
        "binding",
        "image",
        "stopped",
        "ci",
        "container",
        "malformed",
        "timeout",
    ],
)
def test_ci_docker_identity_requires_exact_service_and_published_loopback_port(
    monkeypatch: pytest.MonkeyPatch, difference: str | None
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("MIGRATION_PG_TOOLS_CONTAINER", "a" * 12)
    metadata = {
        "image": "postgres:18",
        "running": True,
        "ports": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]},
        "networks": {"isolated-ci-network": {"IPAddress": "172.19.0.2", "GlobalIPv6Address": ""}},
    }
    database, address = "portfolio_test", "172.19.0.2"
    if difference == "database":
        database = "neondb"
    if difference == "address":
        address = "172.19.0.3"
    if difference == "port":
        metadata["ports"] = {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5433"}]}
    if difference == "binding":
        metadata["ports"] = {"5432/tcp": [{"HostIp": "192.0.2.10", "HostPort": "5432"}]}
    if difference == "image":
        metadata["image"] = "postgres:17"
    if difference == "stopped":
        metadata["running"] = False
    if difference == "ci":
        monkeypatch.setenv("GITHUB_ACTIONS", "false")
    if difference == "container":
        monkeypatch.setenv("MIGRATION_PG_TOOLS_CONTAINER", "unverified-name")
    inspect = Mock(
        return_value=Mock(stdout="malformed" if difference == "malformed" else json.dumps(metadata))
    )
    if difference == "timeout":
        inspect.side_effect = subprocess.TimeoutExpired("docker", 5)
    monkeypatch.setattr("browser_server.subprocess.run", inspect)
    connection = Mock()
    connection.execute.return_value.one.return_value = (database, address)
    url = make_url("postgresql+psycopg://localhost:5432/portfolio_test")
    if difference:
        with pytest.raises(SystemExit, match="identity did not match"):
            verify_local_identity(cast(Connection, connection), url)
    else:
        verify_local_identity(cast(Connection, connection), url)
        command = inspect.call_args.args[0]
        assert command[:2] == ["docker", "inspect"] and command[-1] == "a" * 12
        assert ".Config.Env" not in command[3]
        assert inspect.call_args.kwargs["timeout"] == 5


def test_ci_container_metadata_never_authorizes_a_remote_or_overridden_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("MIGRATION_PG_TOOLS_CONTAINER", "a" * 12)
    inspect = Mock()
    monkeypatch.setattr("browser_server.subprocess.run", inspect)
    for raw in (
        "postgresql+psycopg://remote.example/portfolio_test",
        "postgresql+psycopg://localhost/portfolio_test?host=remote.example",
        "postgresql+psycopg://localhost/neondb",
    ):
        with pytest.raises(SystemExit, match="loopback"):
            verify_local_identity(cast(Connection, Mock()), make_url(raw))
    inspect.assert_not_called()
