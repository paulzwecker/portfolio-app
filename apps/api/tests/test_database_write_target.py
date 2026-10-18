from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import make_url

from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import (
    ConfirmationProvider,
    DatabaseWriteTargetError,
    DatabaseWriteTargetGuard,
    LiveDatabaseIdentity,
    NeonControlPlaneClient,
    NeonTargetMetadata,
    WriteOperationKind,
    _interactive_confirmation,
    _RejectRedirects,
    _statement_may_write,
    validate_database_write_target,
)
from portfolio_api.settings import Settings

PROJECT_ID = "prj_example_only"
PRIMARY_BRANCH_ID = "br_example_primary"
REHEARSAL_BRANCH_ID = "br_example_rehearsal"
ENDPOINT_ID = "ep_example_direct"
HOST = "ep-example-direct.example.neon.tech"
DATABASE = "portfolio_app"
REMOTE_URL = (
    f"postgresql+psycopg://writer:synthetic-password@{HOST}:5432/{DATABASE}?sslmode=verify-full"
)


def remote_settings(
    environment: str = "production",
    *,
    app_env: str | None = None,
    production_authorized: bool = True,
    rehearsal_authorized: bool = True,
    url: str = REMOTE_URL,
) -> Settings:
    return Settings(
        database_url=SecretStr(url),
        app_env=app_env or ("preview" if environment == "rehearsal" else environment),
        database_target_environment=environment,
        database_target_database=DATABASE,
        database_production_writes_authorized=production_authorized,
        database_rehearsal_writes_authorized=rehearsal_authorized,
        neon_api_key=SecretStr("synthetic-neon-api-key-not-a-credential"),
        neon_project_id=PROJECT_ID,
        neon_branch_id=(PRIMARY_BRANCH_ID if environment == "production" else REHEARSAL_BRANCH_ID),
        neon_endpoint_id=ENDPOINT_ID,
        api_access_token=SecretStr("synthetic-api-token-0123456789012345")
        if (app_env or environment) in {"production", "rehearsal"}
        else None,
    )


def remote_identity(
    url: str = REMOTE_URL,
    *,
    host: str | None = None,
    hostaddr: str | None = "203.0.113.20",
    database: str = DATABASE,
    superuser: bool = False,
    can_connect: bool = True,
    can_use_schema: bool = True,
    can_create_schema: bool = True,
    missing_tables: tuple[str, ...] = (),
    missing_privileges: tuple[str, ...] = (),
    missing_owned_objects: tuple[str, ...] = (),
) -> LiveDatabaseIdentity:
    parsed = make_url(url)
    resolved_host = host or str(parsed.host)
    return LiveDatabaseIdentity(
        url_host=str(parsed.host),
        driver_host=resolved_host,
        driver_hostaddr=hostaddr,
        url_port=int(parsed.port or 5432),
        driver_port=int(parsed.port or 5432),
        url_database=str(parsed.database),
        driver_database=database,
        server_database=database,
        server_user="synthetic-role",
        server_address=hostaddr,
        server_port=int(parsed.port or 5432),
        server_version_num=180000,
        current_schema="public",
        role_is_superuser=superuser,
        can_connect=can_connect,
        can_use_schema=can_use_schema,
        can_create_schema=can_create_schema,
        missing_tables=missing_tables,
        missing_privileges=missing_privileges,
        missing_owned_objects=missing_owned_objects,
    )


def neon_target(
    *,
    environment: str = "production",
    host: str = HOST,
    branch_id: str | None = None,
    primary_branch_id: str = PRIMARY_BRANCH_ID,
    branch_is_primary: bool | None = None,
    parent_id: str | None = None,
    endpoint_branch_id: str | None = None,
    endpoint_type: str = "read_write",
    endpoint_state: str = "active",
    branch_state: str = "ready",
    project_id: str = PROJECT_ID,
    endpoint_id: str = ENDPOINT_ID,
) -> NeonTargetMetadata:
    actual_branch_id = branch_id or (
        PRIMARY_BRANCH_ID if environment == "production" else REHEARSAL_BRANCH_ID
    )
    is_primary = (
        actual_branch_id == primary_branch_id if branch_is_primary is None else branch_is_primary
    )
    return NeonTargetMetadata(
        project_id=project_id,
        branch_id=actual_branch_id,
        branch_project_id=project_id,
        branch_is_primary=is_primary,
        primary_branch_id=primary_branch_id,
        branch_parent_id=parent_id or (None if is_primary else primary_branch_id),
        branch_state=branch_state,
        endpoint_id=endpoint_id,
        endpoint_project_id=project_id,
        endpoint_branch_id=endpoint_branch_id or actual_branch_id,
        endpoint_host=host,
        endpoint_type=endpoint_type,
        endpoint_state=endpoint_state,
    )


def validate(
    settings: Settings,
    identity: LiveDatabaseIdentity,
    target: NeonTargetMetadata | None,
    *,
    operation_kind: WriteOperationKind = "application",
    confirmation_provider: ConfirmationProvider | None = None,
) -> dict[str, Any]:
    assert settings.database_url is not None
    return validate_database_write_target(
        settings=settings,
        url=make_url(settings.database_url.get_secret_value()),
        identity=identity,
        operation="test_write_operation",
        operation_kind=operation_kind,
        neon_target=target,
        confirmation_provider=confirmation_provider,
    )


def install_resolved_dns(monkeypatch: pytest.MonkeyPatch, address: str = "203.0.113.20") -> None:
    monkeypatch.setattr(
        "portfolio_api.database_write_target.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, (address, 5432))],
    )


def test_verified_production_identity_is_approved_and_audit_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_resolved_dns(monkeypatch)
    audit = validate(remote_settings(), remote_identity(), neon_target())

    assert audit["event"] == "database_write_target_approved"
    assert audit["environment"] == "production"
    assert audit["provider"] == "neon"
    assert audit["project_id"] == PROJECT_ID
    assert audit["branch_id"] == PRIMARY_BRANCH_ID
    assert audit["endpoint_id"] == ENDPOINT_ID
    assert "url" not in audit and "host" not in audit and "password" not in audit
    assert REMOTE_URL not in str(audit)
    assert "synthetic-password" not in str(audit)


def test_unconfigured_environment_is_rejected() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://writer:fake@db.example.test/portfolio")
    )
    assert settings.database_url is not None
    identity = remote_identity(
        "postgresql+psycopg://writer:fake@db.example.test/portfolio",
        hostaddr="203.0.113.20",
        database="portfolio",
    )
    with pytest.raises(DatabaseWriteTargetError, match="target_environment_required"):
        validate_database_write_target(
            settings=settings,
            url=make_url(settings.database_url.get_secret_value()),
            identity=identity,
            operation="test_import",
            operation_kind="import",
            neon_target=None,
        )


@pytest.mark.parametrize(
    ("settings_changes", "identity_changes", "target_changes", "code"),
    [
        (
            {"app_env": "production", "database_target_environment": "rehearsal"},
            {},
            {},
            "application_target_environment_mismatch",
        ),
        ({}, {"database": "other_db"}, {}, "live_connection_target_mismatch"),
        ({}, {"host": "ep-other.example.neon.tech"}, {}, "live_connection_target_mismatch"),
        ({}, {"superuser": True}, {}, "superuser_write_role_rejected"),
        ({}, {"can_connect": False}, {}, "insufficient_database_privileges"),
        ({}, {"can_use_schema": False}, {}, "insufficient_database_privileges"),
        ({}, {"missing_tables": ("companies",)}, {}, "application_schema_incomplete"),
        ({}, {"missing_privileges": ("companies:INSERT",)}, {}, "insufficient_table_privileges"),
        ({}, {}, {"project_id": "prj_other"}, "neon_configured_identity_mismatch"),
        ({}, {}, {"branch_id": "br_other"}, "neon_configured_identity_mismatch"),
        ({}, {}, {"endpoint_id": "ep_other"}, "neon_configured_identity_mismatch"),
        ({}, {}, {"endpoint_branch_id": "br_other"}, "endpoint_branch_mismatch"),
        ({}, {}, {"host": "ep-other.example.neon.tech"}, "endpoint_host_mismatch"),
        ({}, {}, {"endpoint_type": "read_only"}, "endpoint_not_writable"),
        ({}, {}, {"endpoint_state": "disabled"}, "endpoint_not_writable"),
        ({}, {}, {"branch_state": "creating"}, "branch_not_ready"),
        ({}, {}, {"branch_is_primary": False}, "neon_primary_branch_ambiguous"),
        (
            {"database_production_writes_authorized": False},
            {},
            {},
            "production_write_not_authorized",
        ),
    ],
)
def test_production_rejection_paths(
    monkeypatch: pytest.MonkeyPatch,
    settings_changes: dict[str, Any],
    identity_changes: dict[str, Any],
    target_changes: dict[str, Any],
    code: str,
) -> None:
    install_resolved_dns(monkeypatch)
    settings = remote_settings().model_copy(update=settings_changes)
    identity = remote_identity(**identity_changes)
    target = neon_target(**target_changes)
    with pytest.raises(DatabaseWriteTargetError, match=code):
        validate(settings, identity, target)


def test_pooler_and_non_verified_tls_are_rejected_before_use() -> None:
    pooler_url = REMOTE_URL.replace(HOST, "ep-example-pooler.example.neon.tech")
    with pytest.raises(ValidationError, match="direct PostgreSQL endpoint"):
        remote_settings(url=pooler_url)

    tls_settings = remote_settings(url=REMOTE_URL.replace("verify-full", "require"))
    tls_identity = remote_identity(REMOTE_URL.replace("verify-full", "require"))
    with pytest.raises(DatabaseWriteTargetError, match="tls_hostname_verification_required"):
        validate(tls_settings, tls_identity, neon_target())


def test_resolved_address_and_port_mismatches_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_resolved_dns(monkeypatch, address="203.0.113.21")
    with pytest.raises(DatabaseWriteTargetError, match="resolved_endpoint_mismatch"):
        validate(remote_settings(), remote_identity(), neon_target())

    pooler_url = REMOTE_URL.replace(":5432/", ":6432/")
    settings = remote_settings(url=pooler_url)
    identity = remote_identity(pooler_url, hostaddr="203.0.113.20")
    with pytest.raises(DatabaseWriteTargetError, match="pooled_endpoint_not_supported"):
        validate(settings, identity, neon_target())


def test_rehearsal_requires_a_nonprimary_direct_child_and_explicit_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_resolved_dns(monkeypatch)
    settings = remote_settings("rehearsal")
    target = neon_target(environment="rehearsal")
    assert validate(settings, remote_identity(), target)["environment"] == "rehearsal"

    with pytest.raises(DatabaseWriteTargetError, match="nonproduction_primary_branch_rejected"):
        validate(
            settings,
            remote_identity(),
            neon_target(
                environment="rehearsal",
                primary_branch_id=REHEARSAL_BRANCH_ID,
                branch_is_primary=True,
            ),
        )
    with pytest.raises(DatabaseWriteTargetError, match="rehearsal_branch_not_isolated"):
        validate(
            settings,
            remote_identity(),
            neon_target(environment="rehearsal", parent_id="br_other_parent"),
        )
    with pytest.raises(DatabaseWriteTargetError, match="rehearsal_write_not_authorized"):
        validate(
            remote_settings("rehearsal", rehearsal_authorized=False), remote_identity(), target
        )


def test_production_bootstrap_requires_authorization_and_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_resolved_dns(monkeypatch)
    settings = remote_settings(production_authorized=False)
    with pytest.raises(DatabaseWriteTargetError, match="production_write_not_authorized"):
        validate(settings, remote_identity(), neon_target(), operation_kind="bootstrap")

    settings = remote_settings()
    with pytest.raises(
        DatabaseWriteTargetError, match="production_bootstrap_confirmation_required"
    ):
        validate(settings, remote_identity(), neon_target(), operation_kind="bootstrap")
    with pytest.raises(
        DatabaseWriteTargetError, match="production_bootstrap_confirmation_mismatch"
    ):
        validate(
            settings,
            remote_identity(),
            neon_target(),
            operation_kind="bootstrap",
            confirmation_provider=lambda _expected: "yes",
        )
    audit = validate(
        settings,
        remote_identity(),
        neon_target(),
        operation_kind="bootstrap",
        confirmation_provider=lambda expected: expected,
    )
    assert audit["operation_kind"] == "bootstrap"


def test_production_bootstrap_confirmation_requires_an_interactive_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NonInteractiveInput:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("portfolio_api.database_write_target.sys.stdin", NonInteractiveInput())
    with pytest.raises(
        DatabaseWriteTargetError, match="production_bootstrap_confirmation_required"
    ):
        _interactive_confirmation("BOOTSTRAP synthetic-target")


def test_seed_is_rejected_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    install_resolved_dns(monkeypatch)
    with pytest.raises(DatabaseWriteTargetError, match="seed_environment_rejected"):
        validate(
            remote_settings(),
            remote_identity(),
            neon_target(),
            operation_kind="seed",
        )


def test_local_test_database_needs_no_neon_configuration() -> None:
    url = make_url("postgresql+psycopg://test_role:fake@127.0.0.1:5432/portfolio_test")
    settings = Settings(
        database_url=SecretStr(url.render_as_string(hide_password=False)),
        database_target_environment="development",
        database_target_database="portfolio_test",
        database_local_test_writes_authorized=True,
    )
    identity = LiveDatabaseIdentity(
        url_host="127.0.0.1",
        driver_host="127.0.0.1",
        driver_hostaddr="127.0.0.1",
        url_port=5432,
        driver_port=5432,
        url_database="portfolio_test",
        driver_database="portfolio_test",
        server_database="portfolio_test",
        server_user="test_role",
        server_address="127.0.0.1",
        server_port=5432,
        server_version_num=180000,
        current_schema="public",
        role_is_superuser=True,
        can_connect=True,
        can_use_schema=True,
        can_create_schema=True,
    )

    audit = validate_database_write_target(
        settings=settings,
        url=url,
        identity=identity,
        operation="local_test_write",
        operation_kind="ingestion",
        neon_target=None,
    )

    assert audit["provider"] == "local_postgresql"
    assert audit["environment"] == "development"

    unauthorized = settings.model_copy(update={"database_local_test_writes_authorized": False})
    with pytest.raises(DatabaseWriteTargetError, match="local_test_write_not_authorized"):
        validate_database_write_target(
            settings=unauthorized,
            url=url,
            identity=identity,
            operation="local_test_write",
            operation_kind="ingestion",
            neon_target=None,
        )


def test_ci_integration_target_is_explicit_local_postgresql_without_neon_credentials() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "image: postgres:18" in workflow
    assert (
        "TEST_DATABASE_URL: postgresql+psycopg://portfolio_app:ci-password@127.0.0.1:5432/"
        "portfolio_app_test" in workflow
    )
    assert "DATABASE_TARGET_ENVIRONMENT: development" in workflow
    assert "DATABASE_TARGET_DATABASE: portfolio_app_test" in workflow
    assert 'DATABASE_LOCAL_TEST_WRITES_AUTHORIZED: "true"' in workflow
    assert "NEON_API_KEY:" not in workflow


def test_shared_engine_factory_installs_operation_specific_guard() -> None:
    raw_url = "postgresql+psycopg://test_role:synthetic@127.0.0.1:5432/portfolio_test"
    settings = Settings(
        database_url=SecretStr(raw_url),
        database_target_environment="development",
        database_target_database="portfolio_test",
        database_local_test_writes_authorized=True,
    )
    engine = create_database_engine(
        settings,
        write_operation="factory_regression_test",
        write_operation_kind="import",
    )
    assert engine is not None
    try:
        guard = engine._portfolio_database_write_target_guard  # type: ignore[attr-defined]
        assert isinstance(guard, DatabaseWriteTargetGuard)
        assert guard.operation == "factory_regression_test"
        assert guard.operation_kind == "import"
    finally:
        engine.dispose()


def test_local_non_test_database_requires_explicit_name_and_authorization() -> None:
    raw_url = "postgresql+psycopg://writer:fake@localhost:5432/portfolio_dev"
    url = make_url(raw_url)
    identity = remote_identity(
        raw_url,
        host="localhost",
        hostaddr="127.0.0.1",
        database="portfolio_dev",
    )
    denied = Settings(
        database_url=SecretStr(raw_url),
        database_target_environment="development",
        database_target_database="portfolio_dev",
    )
    with pytest.raises(DatabaseWriteTargetError, match="local_development_write_not_authorized"):
        validate_database_write_target(
            settings=denied,
            url=url,
            identity=identity,
            operation="local_dev_write",
            operation_kind="application",
            neon_target=None,
        )
    allowed = denied.model_copy(update={"database_local_writes_authorized": True})
    assert (
        validate_database_write_target(
            settings=allowed,
            url=url,
            identity=identity,
            operation="local_dev_write",
            operation_kind="application",
            neon_target=None,
        )["environment"]
        == "development"
    )


def test_statement_classifier_covers_sqlalchemy_and_raw_sql_writes() -> None:
    class Context:
        isinsert = False
        isupdate = False
        isdelete = False
        isddl = False

    context = Context()
    assert _statement_may_write("INSERT INTO companies VALUES (1)", context)
    assert _statement_may_write("WITH changed AS (DELETE FROM companies) SELECT 1", context)
    assert _statement_may_write("SELECT pg_try_advisory_lock(1, 2)", context)
    assert _statement_may_write("SELECT pg_notify('channel', 'payload')", context)
    assert _statement_may_write("SELECT lo_import('/tmp/input')", context)
    assert _statement_may_write("SELECT 1; DROP TABLE companies", context)
    assert _statement_may_write("VACUUM ANALYZE companies", context)
    assert _statement_may_write("EXPLAIN ANALYZE UPDATE companies SET name='x'", context)
    assert not _statement_may_write("SELECT * FROM companies", context)
    context.isinsert = True
    assert _statement_may_write("SELECT 1", context)


def test_preflight_never_marks_a_connection_as_verified_for_a_later_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_url = "postgresql+psycopg://role:fake@127.0.0.1/portfolio_test"
    settings = Settings(database_url=SecretStr(raw_url))
    url = make_url(raw_url)

    monkeypatch.setattr(
        "portfolio_api.database_write_target._read_live_identity",
        lambda *_args: remote_identity(raw_url, hostaddr="127.0.0.1", database="portfolio_test"),
    )
    monkeypatch.setattr(
        "portfolio_api.database_write_target.validate_database_write_target",
        lambda **_kwargs: {"environment": "development"},
    )
    guard = DatabaseWriteTargetGuard(
        settings,
        operation="preflight_test",
        operation_kind="application",
        audit_sink=lambda _: None,
    )
    connection = SimpleNamespace(info={}, engine=SimpleNamespace(url=url))

    guard.verify_connection(connection, phase="preflight")  # type: ignore[arg-type]
    assert "portfolio_database_write_target_guard" not in connection.info
    guard.verify_connection(connection, phase="before_write")  # type: ignore[arg-type]
    assert connection.info["portfolio_database_write_target_guard"] == guard._guard_id


def test_neon_redirect_handler_refuses_redirects() -> None:
    handler = _RejectRedirects()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://attacker.test/") is None


@pytest.mark.parametrize(
    ("settings_changes", "identity_changes", "operation_kind", "code"),
    [
        (
            {"database_target_database": "other_database"},
            {},
            "application",
            "database_name_mismatch",
        ),
        ({}, {"can_create_schema": False}, "schema_migration", "insufficient_database_privileges"),
        (
            {},
            {"missing_owned_objects": ("companies",)},
            "schema_migration",
            "insufficient_schema_ownership",
        ),
    ],
)
def test_additional_target_and_schema_privilege_rejections(
    monkeypatch: pytest.MonkeyPatch,
    settings_changes: dict[str, Any],
    identity_changes: dict[str, Any],
    operation_kind: WriteOperationKind,
    code: str,
) -> None:
    install_resolved_dns(monkeypatch)
    settings = remote_settings().model_copy(update=settings_changes)
    with pytest.raises(DatabaseWriteTargetError, match=code):
        validate(
            settings,
            remote_identity(**identity_changes),
            neon_target(),
            operation_kind=operation_kind,
        )


def test_remote_write_requires_neon_metadata_and_complete_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_resolved_dns(monkeypatch)
    with pytest.raises(DatabaseWriteTargetError, match="neon_target_metadata_required"):
        validate(remote_settings(), remote_identity(), None)

    settings = remote_settings().model_copy(update={"neon_endpoint_id": None})
    with pytest.raises(DatabaseWriteTargetError, match="neon_target_configuration_incomplete"):
        validate(settings, remote_identity(), neon_target())


def test_remote_engine_guard_fails_without_neon_api_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = remote_settings().model_copy(update={"neon_api_key": None})
    monkeypatch.setattr(
        "portfolio_api.database_write_target._read_live_identity",
        lambda *_args: remote_identity(),
    )
    guard = DatabaseWriteTargetGuard(
        settings,
        operation="missing_neon_api_key",
        operation_kind="import",
        audit_sink=lambda _record: None,
    )
    connection = SimpleNamespace(info={}, engine=SimpleNamespace(url=make_url(REMOTE_URL)))

    with pytest.raises(DatabaseWriteTargetError, match="neon_target_configuration_incomplete"):
        guard.verify_connection(connection)  # type: ignore[arg-type]


def test_audit_sink_failure_blocks_approval() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://role:fake@127.0.0.1/portfolio_test"),
        database_target_environment="development",
        database_target_database="portfolio_test",
        database_local_test_writes_authorized=True,
    )

    def broken_audit_sink(_record: object) -> None:
        raise OSError("synthetic audit sink error")

    guard = DatabaseWriteTargetGuard(
        settings,
        operation="audit_failure_test",
        operation_kind="application",
        audit_sink=broken_audit_sink,
    )
    with pytest.raises(DatabaseWriteTargetError, match="write_audit_record_failed"):
        guard._emit_audit({"event": "synthetic"})


def test_invalid_unvalidated_target_environment_is_rejected() -> None:
    settings = remote_settings().model_copy(update={"database_target_environment": "unknown"})
    with pytest.raises(DatabaseWriteTargetError, match="target_environment_invalid"):
        validate(settings, remote_identity(), neon_target())


def test_production_cannot_write_to_a_local_postgresql_target() -> None:
    local_url = "postgresql+psycopg://writer:synthetic@127.0.0.1:5432/portfolio_app"
    settings = remote_settings().model_copy(
        update={
            "database_url": SecretStr(local_url),
            "database_target_database": DATABASE,
        }
    )
    with pytest.raises(DatabaseWriteTargetError, match="local_target_environment_mismatch"):
        validate_database_write_target(
            settings=settings,
            url=make_url(local_url),
            identity=remote_identity(local_url, hostaddr="127.0.0.1", database=DATABASE),
            operation="production_write",
            operation_kind="application",
            neon_target=None,
        )


def test_neon_api_client_resolves_authoritative_metadata_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = NeonControlPlaneClient("synthetic-key")
    responses = {
        f"/projects/{PROJECT_ID}/branches": {
            "branches": [
                {"id": PRIMARY_BRANCH_ID, "primary": True},
                {"id": REHEARSAL_BRANCH_ID, "primary": False},
            ]
        },
        f"/projects/{PROJECT_ID}/branches/{REHEARSAL_BRANCH_ID}": {
            "branch": {
                "id": REHEARSAL_BRANCH_ID,
                "project_id": PROJECT_ID,
                "primary": False,
                "parent_id": PRIMARY_BRANCH_ID,
                "current_state": "ready",
            }
        },
        f"/projects/{PROJECT_ID}/endpoints/{ENDPOINT_ID}": {
            "endpoint": {
                "id": ENDPOINT_ID,
                "project_id": PROJECT_ID,
                "branch_id": REHEARSAL_BRANCH_ID,
                "host": HOST,
                "type": "read_write",
                "current_state": "active",
            }
        },
    }
    monkeypatch.setattr(client, "_get_json", lambda resource: responses[resource])

    metadata = client.read_target(PROJECT_ID, REHEARSAL_BRANCH_ID, ENDPOINT_ID)

    assert metadata.primary_branch_id == PRIMARY_BRANCH_ID
    assert metadata.branch_id == REHEARSAL_BRANCH_ID
    assert metadata.endpoint_branch_id == REHEARSAL_BRANCH_ID
