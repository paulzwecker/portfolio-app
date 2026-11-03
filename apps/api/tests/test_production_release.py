from datetime import UTC, datetime, timedelta

import pytest

from portfolio_api.production_release import (
    PRODUCTION_BASE_REVISION,
    RELEASE_HEAD,
    ReleasePreflightError,
    migration_confirmation,
    migration_required,
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
