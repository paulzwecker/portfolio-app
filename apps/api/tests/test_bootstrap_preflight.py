from collections.abc import Mapping
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import Engine

from portfolio_api.bootstrap_preflight import (
    BootstrapPreflightError,
    validate_alembic_heads,
    validate_target_selection,
)


def test_preflight_requires_an_explicit_target_environment() -> None:
    with pytest.raises(BootstrapPreflightError, match="must be explicitly configured"):
        validate_target_selection(None, "rehearsal")


def test_preflight_requires_requested_and_configured_targets_to_match() -> None:
    with pytest.raises(BootstrapPreflightError, match="does not match"):
        validate_target_selection("development", "rehearsal")


def test_preflight_accepts_exact_alembic_heads() -> None:
    validate_alembic_heads({"head_one", "head_two"}, {"head_one", "head_two"})


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (set(), {"head_one"}),
        ({"old_head"}, {"head_one"}),
        ({"head_one", "unexpected"}, {"head_one"}),
    ],
)
def test_preflight_rejects_missing_or_incompatible_alembic_heads(
    current: set[str], expected: set[str]
) -> None:
    with pytest.raises(BootstrapPreflightError, match="Alembic revision mismatch"):
        validate_alembic_heads(current, expected)


def test_preflight_does_not_disclose_untrusted_revision_text() -> None:
    with pytest.raises(BootstrapPreflightError) as error:
        validate_alembic_heads({"password=secret"}, {"head_one"})

    assert "password=secret" not in str(error.value)
    assert "<unknown>" in str(error.value)


def test_preflight_target_mismatch_fails_before_guard_or_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portfolio_api import bootstrap_preflight

    guard = Mock()
    monkeypatch.setattr(bootstrap_preflight, "verify_database_write_target", guard)

    with pytest.raises(BootstrapPreflightError, match="does not match"):
        bootstrap_preflight.verify_database_preflight(
            Mock(),
            configured_target_environment="development",
            requested_target_environment="rehearsal",
        )

    guard.assert_not_called()


@pytest.mark.integration
def test_preflight_verifies_migrated_disposable_postgres(postgres_engine: Engine) -> None:
    from pydantic import SecretStr

    from portfolio_api.database_write_target import install_database_write_target_guard
    from portfolio_api.migrations import expected_heads
    from portfolio_api.settings import Settings

    target_database = postgres_engine.url.database
    assert target_database is not None and target_database.endswith("_test")
    settings = Settings(
        database_url=SecretStr(str(postgres_engine.url)),
        app_env="development",
        database_target_environment="development",
        database_target_database=target_database,
        database_local_test_writes_authorized=True,
    )
    audit_records: list[Mapping[str, Any]] = []
    install_database_write_target_guard(
        postgres_engine,
        settings,
        operation="cloud_bootstrap.preflight",
        operation_kind="bootstrap",
        audit_sink=audit_records.append,
    )

    from portfolio_api.bootstrap_preflight import verify_database_preflight

    current = verify_database_preflight(
        postgres_engine,
        configured_target_environment="development",
        requested_target_environment="development",
    )

    assert current == expected_heads()
    assert len(audit_records) == 1
    assert audit_records[0]["phase"] == "preflight"
    assert audit_records[0]["provider"] == "local_postgresql"
