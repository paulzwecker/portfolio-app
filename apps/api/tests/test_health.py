from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError

from portfolio_api.health import check_readiness
from portfolio_api.main import create_app
from portfolio_api.migrations import expected_heads
from portfolio_api.settings import Settings


def test_liveness_does_not_require_database() -> None:
    with TestClient(create_app(Settings(database_url=None))) as client:
        assert client.get("/health/live").json() == {"status": "ok"}


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
