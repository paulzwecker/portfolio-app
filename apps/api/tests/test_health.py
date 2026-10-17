from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError

from portfolio_api.health import check_readiness
from portfolio_api.main import create_app
from portfolio_api.migrations import expected_heads
from portfolio_api.settings import Settings


def test_liveness_does_not_require_database() -> None:
    with TestClient(create_app(Settings(database_url=None))) as client:
        assert client.get("/health/live").json() == {"status": "ok"}


def test_remote_api_requires_proxy_token_except_health_checks() -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(
            "postgresql+psycopg://portfolio_app:password@127.0.0.1/portfolio_app?sslmode=require"
        ),
        app_env="production",
        api_access_token=SecretStr("x" * 40),
    )
    with (
        patch("portfolio_api.main.create_database_engine", return_value=None),
        TestClient(create_app(settings)) as client,
    ):
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.get("/v1/not-a-real-route").status_code == 401
        assert (
            client.get(
                "/v1/not-a-real-route",
                headers={"X-API-Access-Token": "wrong"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/v1/not-a-real-route",
                headers={"X-API-Access-Token": "x" * 40},
            ).status_code
            == 404
        )


def test_remote_api_settings_fail_closed_without_token() -> None:
    with pytest.raises(ValidationError, match="API_ACCESS_TOKEN"):
        Settings(
            _env_file=None,
            database_url=SecretStr(
                "postgresql+psycopg://portfolio_app:password@127.0.0.1/portfolio_app?sslmode=require"
            ),
            app_env="preview",
            api_access_token=None,
        )


def test_remote_api_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="DATABASE_URL is required"):
        Settings(
            _env_file=None,
            app_env="production",
            api_access_token=SecretStr("x" * 40),
        )


def test_remote_api_requires_long_access_token() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(
            _env_file=None,
            database_url=SecretStr(
                "postgresql+psycopg://portfolio_app:password@127.0.0.1/portfolio_app?sslmode=require"
            ),
            app_env="production",
            api_access_token=SecretStr("too-short"),
        )


def test_remote_api_requires_tls_database_url() -> None:
    with pytest.raises(ValidationError, match="sslmode=require"):
        Settings(
            _env_file=None,
            database_url=SecretStr(
                "postgresql+psycopg://portfolio_app:password@localhost/portfolio_app"
            ),
            app_env="production",
            api_access_token=SecretStr("x" * 40),
        )


def test_remote_api_requires_database_host() -> None:
    with pytest.raises(ValidationError, match="direct PostgreSQL endpoint"):
        Settings(
            _env_file=None,
            database_url=SecretStr("postgresql+psycopg:///portfolio_app?sslmode=require"),
            app_env="production",
            api_access_token=SecretStr("x" * 40),
        )


def test_remote_api_rejects_neon_transaction_pooler_endpoint() -> None:
    with pytest.raises(ValidationError, match="direct PostgreSQL endpoint"):
        Settings(
            _env_file=None,
            database_url=SecretStr(
                "postgresql+psycopg://portfolio_app:password@ep-example-pooler.eu-central-1.aws.neon.tech/portfolio_app?sslmode=require"
            ),
            app_env="production",
            api_access_token=SecretStr("x" * 40),
        )


def test_missing_database_configuration_is_not_ready() -> None:
    with TestClient(create_app(Settings(database_url=None))) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["database"] == "unavailable"
    assert response.json()["schema"] == "unavailable"
    offset = datetime.fromisoformat(response.json()["checked_at"]).utcoffset()
    assert offset is not None and offset.total_seconds() == 0


def test_connection_failure_does_not_expose_credentials() -> None:
    engine = MagicMock(spec=Engine)
    engine.connect.side_effect = OperationalError(
        "postgresql://secret-user:secret-password@host/db", {}, Exception("driver secret")
    )
    result = check_readiness(engine, {"head"})
    assert result.status == "error"
    assert result.database == "unavailable"
    assert result.schema_status == "unavailable"
    assert "secret" not in result.model_dump_json()


def test_connected_database_with_old_schema_is_not_ready() -> None:
    engine = MagicMock(spec=Engine)
    with patch("portfolio_api.health.MigrationContext.configure") as configure:
        configure.return_value.get_current_heads.return_value = ("old",)
        result = check_readiness(engine, {"head"})
    assert result.status == "error"
    assert result.database == "connected"
    assert result.schema_status == "outdated"


def test_connected_database_without_migrations_is_not_ready() -> None:
    engine = MagicMock(spec=Engine)
    with patch("portfolio_api.health.MigrationContext.configure") as configure:
        configure.return_value.get_current_heads.return_value = ()
        result = check_readiness(engine, {"head"})
    assert result.status == "error"
    assert result.schema_status == "outdated"


def test_schema_query_failure_does_not_claim_current_schema() -> None:
    engine = MagicMock(spec=Engine)
    with patch("portfolio_api.health.MigrationContext.configure") as configure:
        configure.return_value.get_current_heads.side_effect = ProgrammingError(
            "statement", {}, Exception("private database information")
        )
        result = check_readiness(engine, {"head"})
    assert result.status == "error"
    assert result.database == "connected"
    assert result.schema_status == "unavailable"
    assert "private" not in result.model_dump_json()


def test_current_schema_is_ready_over_http() -> None:
    engine = MagicMock(spec=Engine)
    with (
        patch("portfolio_api.main.create_database_engine", return_value=engine),
        patch("portfolio_api.health.MigrationContext.configure") as configure,
    ):
        configure.return_value.get_current_heads.return_value = tuple(expected_heads())
        with TestClient(create_app(Settings(database_url=None))) as client:
            response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "connected"
    assert response.json()["schema"] == "current"
    engine.dispose.assert_called_once()
