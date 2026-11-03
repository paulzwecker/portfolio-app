from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from alembic.config import Config
from alembic.util.exc import CommandError

from portfolio_api.production_release import (
    PRODUCTION_BASE_REVISION,
    RELEASE_HEAD,
    ReleasePreflightError,
    migration_confirmation,
    migration_required,
    run_migration_preflight,
    run_readonly_schema_check,
    validate_recovery_window,
)


def test_release_from_verified_production_head_requires_migration() -> None:
    assert migration_required({PRODUCTION_BASE_REVISION}, {RELEASE_HEAD}) is True


def test_release_at_repository_head_skips_migration() -> None:
    assert migration_required({RELEASE_HEAD}, {RELEASE_HEAD}) is False


@pytest.mark.parametrize(
    "current, repository",
    [
        (set(), {RELEASE_HEAD}),
        ({"b16d4f8a2c91"}, {RELEASE_HEAD}),
        ({PRODUCTION_BASE_REVISION}, {"another-head"}),
        ({"unreviewed"}, {RELEASE_HEAD}),
    ],
)
def test_unreviewed_heads_fail_closed(current: set[str], repository: set[str]) -> None:
    with pytest.raises(ReleasePreflightError):
        migration_required(current, repository)


def test_migration_confirmation_binds_exact_target_and_revision_range() -> None:
    assert migration_confirmation(
        project_id="delicate-heart-04560404",
        branch_id="br-morning-truth-b96361yh",
        endpoint_id="ep-snowy-term-b9gr75j6",
        database="neondb",
        current=PRODUCTION_BASE_REVISION,
        target=RELEASE_HEAD,
    ) == (
        "MIGRATE delicate-heart-04560404/br-morning-truth-b96361yh/"
        "ep-snowy-term-b9gr75j6/neondb/6c2eaf0b8147->9f2a6d4c81b7"
    )


def test_recovery_point_must_be_recent_and_persist_long_enough() -> None:
    now = datetime(2026, 11, 3, 12, tzinfo=UTC)
    validate_recovery_window(
        created_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=2),
        now=now,
    )
    with pytest.raises(ReleasePreflightError, match="within_four_hours"):
        validate_recovery_window(created_at=now - timedelta(hours=5), expires_at=None, now=now)
    with pytest.raises(ReleasePreflightError, match="expires_too_soon"):
        validate_recovery_window(
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=12),
            now=now,
        )


def test_migration_preflight_uses_only_readonly_target_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    settings = object()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(
        "MIGRATION_CONFIRMATION",
        migration_confirmation(
            project_id="delicate-heart-04560404",
            branch_id="br-morning-truth-b96361yh",
            endpoint_id="ep-snowy-term-b9gr75j6",
            database="neondb",
            current=PRODUCTION_BASE_REVISION,
            target=RELEASE_HEAD,
        ),
    )

    with (
        patch("portfolio_api.production_release._release_sha", return_value="a" * 40),
        patch("portfolio_api.production_release.Settings", return_value=settings),
        patch("portfolio_api.production_release.validate_read_settings") as validate,
        patch(
            "portfolio_api.production_release.create_database_engine",
            return_value=engine,
        ) as create_engine,
        patch("portfolio_api.production_release.verify_database_read_target") as read_guard,
        patch(
            "portfolio_api.production_release._current_heads",
            return_value={PRODUCTION_BASE_REVISION},
        ),
        patch(
            "portfolio_api.production_release._database_inventory",
            return_value=({}, "inventory-hash", 0),
        ),
        patch("portfolio_api.production_release._verify_recovery") as verify_recovery,
    ):
        result = run_migration_preflight()

    validate.assert_called_once_with(settings)
    create_engine.assert_called_once_with(settings, read_only=True)
    read_guard.assert_called_once()
    verify_recovery.assert_called_once()
    engine.dispose.assert_called_once()
    assert result["read_target_guard"] == "passed"
    assert result["write_authorization"] == "disabled"


def test_schema_metadata_check_uses_verified_readonly_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    engine = Mock()
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine.connect.return_value = connection_context
    settings = object()
    monkeypatch.setenv("APP_ENV", "development")
    observed: dict[str, Any] = {}

    def capture_connection(config: Config) -> None:
        observed["connection"] = config.attributes.get("connection")

    with (
        patch("portfolio_api.production_release._release_sha", return_value="a" * 40),
        patch("portfolio_api.production_release.Settings", return_value=settings),
        patch("portfolio_api.production_release.validate_read_settings"),
        patch(
            "portfolio_api.production_release.create_database_engine",
            return_value=engine,
        ) as create_engine,
        patch("portfolio_api.production_release.verify_database_read_target"),
        patch(
            "portfolio_api.production_release._current_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_release.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_release.alembic_command.check",
            side_effect=capture_connection,
        ) as check,
    ):
        result = run_readonly_schema_check()

    create_engine.assert_called_once_with(settings, read_only=True)
    check.assert_called_once()
    assert observed["connection"] is connection
    assert "connection" not in check.call_args.args[0].attributes
    connection.rollback.assert_called_once()
    engine.dispose.assert_called_once()
    assert result["metadata_check"] == "no_drift"
    assert result["connection"] == "read_only"


def test_schema_metadata_drift_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    engine = Mock()
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine.connect.return_value = connection_context
    monkeypatch.setenv("APP_ENV", "development")
    with (
        patch("portfolio_api.production_release._release_sha", return_value="a" * 40),
        patch("portfolio_api.production_release.Settings", return_value=object()),
        patch("portfolio_api.production_release.validate_read_settings"),
        patch(
            "portfolio_api.production_release.create_database_engine",
            return_value=engine,
        ),
        patch("portfolio_api.production_release.verify_database_read_target"),
        patch(
            "portfolio_api.production_release._current_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_release.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_release.alembic_command.check",
            side_effect=CommandError("private SQL details"),
        ),
        pytest.raises(ReleasePreflightError, match="alembic_metadata_drift_detected") as exc,
    ):
        run_readonly_schema_check()
    assert "private SQL details" not in str(exc.value)
    engine.dispose.assert_called_once()
