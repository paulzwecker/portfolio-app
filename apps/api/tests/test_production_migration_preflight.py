from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from alembic.config import Config
from alembic.util.exc import CommandError
from pydantic import SecretStr

from portfolio_api.production_migration_preflight import (
    PRODUCTION_BASE_REVISION,
    RELEASE_HEAD,
    ProductionMigrationPreflightError,
    _checkout_sha,
    initial_bootstrap_confirmation,
    migration_confirmation,
    migration_required,
    run_fresh_bootstrap_preflight,
    run_fresh_bootstrap_schema_check,
    run_migration_preflight,
    run_readonly_schema_check,
    validate_fresh_bootstrap_read_settings,
    validate_recovery_window,
)
from portfolio_api.settings import Settings


def fresh_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": SecretStr(
            "postgresql+psycopg://reader:synthetic-password@"
            "ep-new-primary.example.neon.tech:5432/newdb?sslmode=verify-full"
        ),
        "app_env": "development",
        "database_target_environment": "production",
        "database_target_database": "newdb",
        "database_production_writes_authorized": False,
        "database_rehearsal_writes_authorized": False,
        "database_local_writes_authorized": False,
        "database_local_test_writes_authorized": False,
        "neon_api_key": SecretStr("synthetic-neon-key"),
        "neon_project_id": "prj_new_example",
        "neon_branch_id": "br_new_primary",
        "neon_endpoint_id": "ep_new_direct",
        "cloud_ingestion_enabled": False,
        "recurring_operations_enabled": False,
        "manual_operations_enabled": False,
        "workbook_sync_enabled": False,
        "google_sheets_poll_seconds": 0,
        "fmp_consensus_ingestion_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_fresh_bootstrap_settings_accept_a_configured_new_primary() -> None:
    validate_fresh_bootstrap_read_settings(fresh_settings())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"database_target_database": "another_database"}, "production_direct_tls_target_invalid"),
        ({"database_production_writes_authorized": True}, "all_database_write_authorizations"),
        ({"recurring_operations_enabled": True}, "background_operations_must_be_disabled"),
        ({"neon_endpoint_id": None}, "verified_neon_production_identity_required"),
        (
            {
                "database_url": SecretStr(
                    "postgresql+psycopg://reader:synthetic-password@"
                    "ep-new-primary-pooler.example.neon.tech:5432/newdb?sslmode=verify-full"
                )
            },
            "production_direct_tls_target_invalid",
        ),
    ],
)
def test_fresh_bootstrap_settings_reject_unsafe_targets(
    overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ProductionMigrationPreflightError, match=message):
        validate_fresh_bootstrap_read_settings(fresh_settings(**overrides))


def test_fresh_bootstrap_confirmation_binds_target_and_full_chain() -> None:
    assert initial_bootstrap_confirmation(
        project_id="prj_new_example",
        branch_id="br_new_primary",
        endpoint_id="ep_new_direct",
        database="newdb",
        target=RELEASE_HEAD,
    ) == (f"INITIALIZE prj_new_example/br_new_primary/ep_new_direct/newdb/base->{RELEASE_HEAD}")


def test_fresh_bootstrap_preflight_accepts_only_verified_empty_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = fresh_settings()
    engine = Mock()
    confirmation = initial_bootstrap_confirmation(
        project_id="prj_new_example",
        branch_id="br_new_primary",
        endpoint_id="ep_new_direct",
        database="newdb",
        target=RELEASE_HEAD,
    )
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("INITIAL_BOOTSTRAP_CONFIRMATION", confirmation)
    with (
        patch(
            "portfolio_api.production_migration_preflight._checkout_sha",
            return_value="a" * 40,
        ) as checkout,
        patch("portfolio_api.production_migration_preflight.Settings", return_value=settings),
        patch(
            "portfolio_api.production_migration_preflight.validate_fresh_bootstrap_read_settings"
        ),
        patch(
            "portfolio_api.production_migration_preflight.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ),
        patch(
            "portfolio_api.production_migration_preflight.verify_database_read_target"
        ) as read_guard,
        patch(
            "portfolio_api.production_migration_preflight._current_schema", return_value="public"
        ),
        patch("portfolio_api.production_migration_preflight._current_heads", return_value=set()),
        patch("portfolio_api.production_migration_preflight._user_relations", return_value=()),
        patch(
            "portfolio_api.production_migration_preflight._database_inventory",
            return_value=({}, "empty-inventory-hash", 0),
        ),
        patch("portfolio_api.production_migration_preflight._verify_recovery") as recovery,
    ):
        result = run_fresh_bootstrap_preflight()

    checkout.assert_called_once_with(allow_codex_branch=True)
    read_guard.assert_called_once_with(engine, required_tables=())
    recovery.assert_not_called()
    engine.dispose.assert_called_once()
    assert result["migration_required"] == "true"
    assert result["empty_database_verified"] == "true"
    assert result["recovery_required"] == "false"
    assert result["write_authorization"] == "disabled"


@pytest.mark.parametrize(
    ("heads", "relations", "inventory", "rows", "message"),
    [
        ({"6c2eaf0b8147"}, (), {}, 0, "already_has_migration_state"),
        (set(), ("public.companies",), {"companies": 0}, 0, "contains_relations"),
        (set(), (), {"reference_data": 1}, 1, "contains_tables"),
    ],
)
def test_fresh_bootstrap_preflight_rejects_initialized_or_data_bearing_targets(
    monkeypatch: pytest.MonkeyPatch,
    heads: set[str],
    relations: tuple[str, ...],
    inventory: dict[str, int],
    rows: int,
    message: str,
) -> None:
    settings = fresh_settings()
    engine = Mock()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(
        "INITIAL_BOOTSTRAP_CONFIRMATION",
        initial_bootstrap_confirmation(
            project_id="prj_new_example",
            branch_id="br_new_primary",
            endpoint_id="ep_new_direct",
            database="newdb",
            target=RELEASE_HEAD,
        ),
    )
    with (
        patch("portfolio_api.production_migration_preflight._checkout_sha", return_value="a" * 40),
        patch("portfolio_api.production_migration_preflight.Settings", return_value=settings),
        patch(
            "portfolio_api.production_migration_preflight.validate_fresh_bootstrap_read_settings"
        ),
        patch(
            "portfolio_api.production_migration_preflight.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ),
        patch("portfolio_api.production_migration_preflight.verify_database_read_target"),
        patch(
            "portfolio_api.production_migration_preflight._current_schema", return_value="public"
        ),
        patch("portfolio_api.production_migration_preflight._current_heads", return_value=heads),
        patch(
            "portfolio_api.production_migration_preflight._user_relations", return_value=relations
        ),
        patch(
            "portfolio_api.production_migration_preflight._database_inventory",
            return_value=(inventory, "inventory-hash", rows),
        ),
        pytest.raises(ProductionMigrationPreflightError, match=message),
    ):
        run_fresh_bootstrap_preflight()
    engine.dispose.assert_called_once()


def test_fresh_bootstrap_preflight_requires_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = fresh_settings()
    engine = Mock()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("INITIAL_BOOTSTRAP_CONFIRMATION", "INITIALIZE wrong-target")
    with (
        patch("portfolio_api.production_migration_preflight._checkout_sha", return_value="a" * 40),
        patch("portfolio_api.production_migration_preflight.Settings", return_value=settings),
        patch(
            "portfolio_api.production_migration_preflight.validate_fresh_bootstrap_read_settings"
        ),
        patch(
            "portfolio_api.production_migration_preflight.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ),
        patch("portfolio_api.production_migration_preflight.verify_database_read_target"),
        patch(
            "portfolio_api.production_migration_preflight._current_schema", return_value="public"
        ),
        patch("portfolio_api.production_migration_preflight._current_heads", return_value=set()),
        patch("portfolio_api.production_migration_preflight._user_relations", return_value=()),
        patch(
            "portfolio_api.production_migration_preflight._database_inventory",
            return_value=({}, "inventory-hash", 0),
        ),
        pytest.raises(
            ProductionMigrationPreflightError,
            match="exact_initial_bootstrap_confirmation_mismatch",
        ),
    ):
        run_fresh_bootstrap_preflight()
    engine.dispose.assert_called_once()


def test_fresh_bootstrap_schema_check_uses_verified_readonly_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    engine = Mock()
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine.connect.return_value = connection_context
    settings = fresh_settings()
    monkeypatch.setenv("APP_ENV", "development")
    with (
        patch(
            "portfolio_api.production_migration_preflight._checkout_sha",
            return_value="a" * 40,
        ) as checkout,
        patch("portfolio_api.production_migration_preflight.Settings", return_value=settings),
        patch(
            "portfolio_api.production_migration_preflight.validate_fresh_bootstrap_read_settings"
        ),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ),
        patch(
            "portfolio_api.production_migration_preflight.verify_database_read_target"
        ) as read_guard,
        patch(
            "portfolio_api.production_migration_preflight._current_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight._check_mapped_alembic_metadata"
        ) as metadata_check,
    ):
        result = run_fresh_bootstrap_schema_check()

    checkout.assert_called_once_with(allow_codex_branch=True)
    read_guard.assert_called_once_with(engine)
    metadata_check.assert_called_once_with(connection)
    connection.rollback.assert_called_once()
    engine.dispose.assert_called_once()
    assert result["alembic_head"] == RELEASE_HEAD
    assert result["metadata_check"] == "no_drift"
    assert result["connection"] == "read_only"


def test_preflight_requires_the_exact_clean_main_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXPECTED_CHECKOUT_SHA", "a" * 40)
    with patch(
        "portfolio_api.production_migration_preflight.subprocess.check_output",
        side_effect=["a" * 40, "main", ""],
    ) as check_output:
        assert _checkout_sha() == "a" * 40
    assert [call.args[0] for call in check_output.call_args_list] == [
        ["git", "rev-parse", "HEAD"],
        ["git", "branch", "--show-current"],
        ["git", "status", "--porcelain", "--untracked-files=all"],
    ]


@pytest.mark.parametrize(
    ("branch", "status", "message"),
    [
        ("feature", "", "checkout_must_be_main"),
        ("main", " M render.yaml", "checkout_must_be_clean"),
    ],
)
def test_preflight_rejects_non_main_or_dirty_checkout(
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    status: str,
    message: str,
) -> None:
    monkeypatch.setenv("EXPECTED_CHECKOUT_SHA", "a" * 40)
    with (
        patch(
            "portfolio_api.production_migration_preflight.subprocess.check_output",
            side_effect=["a" * 40, branch, status],
        ),
        pytest.raises(ProductionMigrationPreflightError, match=message),
    ):
        _checkout_sha()


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
    with pytest.raises(ProductionMigrationPreflightError):
        migration_required(current, repository)


def test_migration_confirmation_binds_exact_target_and_revision_range() -> None:
    assert migration_confirmation(
        project_id="blue-pond-96398788",
        branch_id="br-square-butterfly-bacw0rn5",
        endpoint_id="ep-floral-cake-bae16liy",
        database="neondb",
        current=PRODUCTION_BASE_REVISION,
        target=RELEASE_HEAD,
    ) == (
        "MIGRATE blue-pond-96398788/br-square-butterfly-bacw0rn5/"
        "ep-floral-cake-bae16liy/neondb/9f2a6d4c81b7->b59f16c8a203"
    )


def test_recovery_point_must_be_recent_and_persist_long_enough() -> None:
    now = datetime(2026, 11, 3, 12, tzinfo=UTC)
    validate_recovery_window(
        created_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=2),
        now=now,
    )
    with pytest.raises(ProductionMigrationPreflightError, match="within_four_hours"):
        validate_recovery_window(created_at=now - timedelta(hours=5), expires_at=None, now=now)
    with pytest.raises(ProductionMigrationPreflightError, match="expires_too_soon"):
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
            project_id="blue-pond-96398788",
            branch_id="br-square-butterfly-bacw0rn5",
            endpoint_id="ep-floral-cake-bae16liy",
            database="neondb",
            current=PRODUCTION_BASE_REVISION,
            target=RELEASE_HEAD,
        ),
    )

    with (
        patch("portfolio_api.production_migration_preflight._checkout_sha", return_value="a" * 40),
        patch("portfolio_api.production_migration_preflight.Settings", return_value=settings),
        patch("portfolio_api.production_migration_preflight.validate_read_settings") as validate,
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ) as create_engine,
        patch(
            "portfolio_api.production_migration_preflight.verify_database_read_target"
        ) as read_guard,
        patch(
            "portfolio_api.production_migration_preflight._current_heads",
            return_value={PRODUCTION_BASE_REVISION},
        ),
        patch(
            "portfolio_api.production_migration_preflight._database_inventory",
            return_value=(
                {
                    "alembic_version": 1,
                    "ranking_definitions": 11,
                    "return_methodology_definitions": 4,
                    "score_definitions": 4,
                },
                "inventory-hash",
                20,
            ),
        ),
        patch("portfolio_api.production_migration_preflight._verify_recovery") as verify_recovery,
    ):
        result = run_migration_preflight()

    validate.assert_called_once_with(settings)
    create_engine.assert_called_once_with(settings, read_only=True)
    read_guard.assert_called_once()
    verify_recovery.assert_called_once_with(
        settings,
        {PRODUCTION_BASE_REVISION},
        {
            "alembic_version": 1,
            "ranking_definitions": 11,
            "return_methodology_definitions": 4,
            "score_definitions": 4,
        },
    )
    engine.dispose.assert_called_once()
    assert result["read_target_guard"] == "passed"
    assert result["write_authorization"] == "disabled"
    assert result["recovery_required"] == "true"
    assert result["recovery_verified"] == "verified"


def test_migration_preflight_requires_recovery_when_application_data_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    settings = object()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(
        "MIGRATION_CONFIRMATION",
        migration_confirmation(
            project_id="blue-pond-96398788",
            branch_id="br-square-butterfly-bacw0rn5",
            endpoint_id="ep-floral-cake-bae16liy",
            database="neondb",
            current=PRODUCTION_BASE_REVISION,
            target=RELEASE_HEAD,
        ),
    )

    with (
        patch("portfolio_api.production_migration_preflight._checkout_sha", return_value="a" * 40),
        patch("portfolio_api.production_migration_preflight.Settings", return_value=settings),
        patch("portfolio_api.production_migration_preflight.validate_read_settings"),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ),
        patch("portfolio_api.production_migration_preflight.verify_database_read_target"),
        patch(
            "portfolio_api.production_migration_preflight._current_heads",
            return_value={PRODUCTION_BASE_REVISION},
        ),
        patch(
            "portfolio_api.production_migration_preflight._database_inventory",
            return_value=({"companies": 1}, "inventory-hash", 1),
        ),
        patch("portfolio_api.production_migration_preflight._verify_recovery") as verify_recovery,
    ):
        result = run_migration_preflight()

    verify_recovery.assert_called_once_with(settings, {PRODUCTION_BASE_REVISION}, {"companies": 1})
    assert result["recovery_required"] == "true"
    assert result["recovery_verified"] == "verified"


def test_migration_preflight_requires_recovery_even_for_empty_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    monkeypatch.setenv("APP_ENV", "development")
    for variable in ("RECOVERY_DATABASE_URL", "RECOVERY_BRANCH_ID", "RECOVERY_ENDPOINT_ID"):
        monkeypatch.delenv(variable, raising=False)
    with (
        patch("portfolio_api.production_migration_preflight._checkout_sha", return_value="a" * 40),
        patch("portfolio_api.production_migration_preflight.Settings", return_value=object()),
        patch("portfolio_api.production_migration_preflight.validate_read_settings"),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ),
        patch("portfolio_api.production_migration_preflight.verify_database_read_target"),
        patch(
            "portfolio_api.production_migration_preflight._current_heads",
            return_value={PRODUCTION_BASE_REVISION},
        ),
        patch(
            "portfolio_api.production_migration_preflight._database_inventory",
            return_value=({}, "inventory-hash", 0),
        ),
        pytest.raises(
            ProductionMigrationPreflightError,
            match="fresh_recovery_point_configuration_required",
        ),
    ):
        run_migration_preflight()
    engine.dispose.assert_called_once()


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
        patch("portfolio_api.production_migration_preflight._checkout_sha", return_value="a" * 40),
        patch("portfolio_api.production_migration_preflight.Settings", return_value=settings),
        patch("portfolio_api.production_migration_preflight.validate_read_settings"),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ) as create_engine,
        patch("portfolio_api.production_migration_preflight.verify_database_read_target"),
        patch(
            "portfolio_api.production_migration_preflight._current_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.alembic_command.check",
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
        patch("portfolio_api.production_migration_preflight._checkout_sha", return_value="a" * 40),
        patch("portfolio_api.production_migration_preflight.Settings", return_value=object()),
        patch("portfolio_api.production_migration_preflight.validate_read_settings"),
        patch(
            "portfolio_api.production_migration_preflight.create_database_engine",
            return_value=engine,
        ),
        patch("portfolio_api.production_migration_preflight.verify_database_read_target"),
        patch(
            "portfolio_api.production_migration_preflight._current_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.expected_heads",
            return_value={RELEASE_HEAD},
        ),
        patch(
            "portfolio_api.production_migration_preflight.alembic_command.check",
            side_effect=CommandError("private SQL details"),
        ),
        pytest.raises(
            ProductionMigrationPreflightError, match="alembic_metadata_drift_detected"
        ) as exc,
    ):
        run_readonly_schema_check()
    assert "private SQL details" not in str(exc.value)
    engine.dispose.assert_called_once()


def test_current_release_plan_rejects_retired_target_and_previous_confirmation() -> None:
    from portfolio_api.production_migration_preflight import validate_read_settings

    current = fresh_settings(
        database_url=SecretStr(
            "postgresql+psycopg://reader:synthetic@ep-floral-cake-bae16liy.example.neon.tech/neondb?sslmode=verify-full"
        ),
        database_target_database="neondb",
        neon_project_id="blue-pond-96398788",
        neon_branch_id="br-square-butterfly-bacw0rn5",
        neon_endpoint_id="ep-floral-cake-bae16liy",
    )
    validate_read_settings(current)
    retired = current.model_copy(update={"neon_project_id": "delicate-heart-04560404"})
    with pytest.raises(
        ProductionMigrationPreflightError, match="verified_neon_production_identity_required"
    ):
        validate_read_settings(retired)
    assert PRODUCTION_BASE_REVISION == "9f2a6d4c81b7"
    assert RELEASE_HEAD == "b59f16c8a203"
    with pytest.raises(ProductionMigrationPreflightError, match="requires_new_review"):
        migration_required({"6c2eaf0b8147"}, {RELEASE_HEAD})
