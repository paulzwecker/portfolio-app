"""Read-only production release preflight and separately gated migration preflight.

This module never applies a migration or deploys a service. The only mutating
command remains the existing guarded `npm run db:migrate` path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    NeonControlPlaneClient,
    verify_database_read_target,
    verify_database_write_target,
)
from portfolio_api.domain import models as _models  # noqa: F401 -- register mapped tables
from portfolio_api.migrations import expected_heads
from portfolio_api.settings import Settings

PROJECT_ID = "delicate-heart-04560404"
PRIMARY_BRANCH_ID = "br-morning-truth-b96361yh"
PRIMARY_ENDPOINT_ID = "ep-snowy-term-b9gr75j6"
DATABASE_NAME = "neondb"
PRODUCTION_BASE_REVISION = "6c2eaf0b8147"
RELEASE_HEAD = "9f2a6d4c81b7"
CORE_READ_TABLES = ("companies",)
MIGRATION_CONFIRMATION_PREFIX = "MIGRATE"


class ReleasePreflightError(RuntimeError):
    """Sanitized release validation error with no provider response body."""


def migration_required(current_heads: set[str], repository_heads: set[str]) -> bool:
    if repository_heads != {RELEASE_HEAD}:
        raise ReleasePreflightError("repository_migration_head_unexpected")
    if current_heads == {RELEASE_HEAD}:
        return False
    if current_heads == {PRODUCTION_BASE_REVISION}:
        return True
    raise ReleasePreflightError("production_schema_head_requires_new_review")


def migration_confirmation(
    *, project_id: str, branch_id: str, endpoint_id: str, database: str, current: str, target: str
) -> str:
    return (
        f"{MIGRATION_CONFIRMATION_PREFIX} {project_id}/{branch_id}/{endpoint_id}/"
        f"{database}/{current}->{target}"
    )


def validate_recovery_window(
    *, created_at: datetime, expires_at: datetime | None, now: datetime
) -> None:
    if created_at.tzinfo is None or now.tzinfo is None:
        raise ReleasePreflightError("recovery_timestamps_must_be_timezone_aware")
    if created_at < now - timedelta(hours=4) or created_at > now + timedelta(minutes=5):
        raise ReleasePreflightError("recovery_point_must_be_created_within_four_hours")
    if expires_at is not None and (
        expires_at.tzinfo is None or expires_at <= now + timedelta(hours=24)
    ):
        raise ReleasePreflightError("recovery_point_expires_too_soon")


def validate_read_settings(settings: Settings) -> None:
    if settings.database_url is None:
        raise ReleasePreflightError("production_readonly_database_url_missing")
    if settings.app_env != "development":
        raise ReleasePreflightError("release_preflight_must_run_in_isolated_tooling_mode")
    if settings.database_target_environment != "production":
        raise ReleasePreflightError("production_database_target_environment_mismatch")
    if settings.database_target_database != DATABASE_NAME:
        raise ReleasePreflightError("production_database_name_mismatch")
    if settings.database_production_writes_authorized:
        raise ReleasePreflightError("production_write_authorization_must_be_disabled_in_preflight")
    if (
        any(
            (
                settings.cloud_ingestion_enabled,
                settings.recurring_operations_enabled,
                settings.manual_operations_enabled,
                settings.workbook_sync_enabled,
                settings.fmp_consensus_ingestion_enabled,
            )
        )
        or settings.google_sheets_poll_seconds != 0
    ):
        raise ReleasePreflightError("background_operations_must_be_disabled")
    if (
        settings.neon_project_id != PROJECT_ID
        or settings.neon_branch_id != PRIMARY_BRANCH_ID
        or settings.neon_endpoint_id != PRIMARY_ENDPOINT_ID
        or settings.neon_api_key is None
    ):
        raise ReleasePreflightError("verified_neon_production_identity_required")
    url = make_url(settings.database_url.get_secret_value())
    if (
        url.database != DATABASE_NAME
        or url.host is None
        or "-pooler." in url.host
        or url.query.get("sslmode") != "verify-full"
    ):
        raise ReleasePreflightError("production_direct_tls_target_invalid")


def _current_heads(engine: Engine) -> set[str]:
    try:
        with engine.connect() as connection:
            heads = set(MigrationContext.configure(connection).get_current_heads())
            connection.rollback()
            return heads
    except SQLAlchemyError:
        raise ReleasePreflightError("production_alembic_revision_unavailable") from None


def _database_inventory(engine: Engine) -> tuple[dict[str, int], str, int]:
    try:
        names = inspect(engine).get_table_names(schema="public")
        counts: dict[str, int] = {}
        with engine.connect() as connection:
            for name in sorted(names):
                table = '"' + name.replace('"', '""') + '"'
                statement = text(f"SELECT count(*) FROM public.{table}")
                counts[name] = int(connection.execute(statement).scalar_one())
            connection.rollback()
        canonical = json.dumps(counts, sort_keys=True, separators=(",", ":")).encode()
        return counts, hashlib.sha256(canonical).hexdigest(), sum(counts.values())
    except SQLAlchemyError:
        raise ReleasePreflightError("database_inventory_read_failed") from None


def _branch_timestamps(
    settings: Settings, branch_id: str
) -> tuple[datetime | None, datetime | None]:
    assert settings.neon_api_key is not None
    client = NeonControlPlaneClient(settings.neon_api_key.get_secret_value())
    try:
        payload = client._get_json(f"/projects/{PROJECT_ID}/branches/{branch_id}")
    except DatabaseWriteTargetError as error:
        raise ReleasePreflightError(f"neon_recovery_metadata_unavailable:{error.code}") from None
    branch = payload.get("branch", payload)
    if not isinstance(branch, Mapping):
        raise ReleasePreflightError("neon_recovery_metadata_invalid")
    created = _parse_datetime(branch.get("created_at"))
    expires = _parse_datetime(branch.get("expires_at"))
    return created, expires


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReleasePreflightError("neon_branch_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ReleasePreflightError("neon_branch_timestamp_invalid") from None
    if parsed.tzinfo is None:
        raise ReleasePreflightError("neon_branch_timestamp_invalid")
    return parsed


def _read_settings_for_recovery(
    primary: Settings, url: str, branch: str, endpoint: str
) -> Settings:
    return Settings(
        _env_file=None,
        app_env="development",
        database_url=url,
        database_target_environment="rehearsal",
        database_target_database=DATABASE_NAME,
        database_production_writes_authorized=False,
        neon_api_key=primary.neon_api_key,
        neon_project_id=PROJECT_ID,
        neon_branch_id=branch,
        neon_endpoint_id=endpoint,
    )


def _verify_recovery(
    primary: Settings, prod_head: set[str], prod_inventory: dict[str, int]
) -> None:
    recovery_url = os.environ.get("RECOVERY_DATABASE_URL")
    recovery_branch = os.environ.get("RECOVERY_BRANCH_ID")
    recovery_endpoint = os.environ.get("RECOVERY_ENDPOINT_ID")
    if not all((recovery_url, recovery_branch, recovery_endpoint)):
        raise ReleasePreflightError("fresh_recovery_point_configuration_required")
    created_at, expires_at = _branch_timestamps(primary, str(recovery_branch))
    now = datetime.now(UTC)
    if created_at is None:
        raise ReleasePreflightError("recovery_branch_creation_time_missing")
    validate_recovery_window(created_at=created_at, expires_at=expires_at, now=now)

    recovery = _read_settings_for_recovery(
        primary, str(recovery_url), str(recovery_branch), str(recovery_endpoint)
    )
    recovery_url_obj = make_url(str(recovery_url))
    if recovery_url_obj.query.get("sslmode") != "verify-full" or "-pooler." in (
        recovery_url_obj.host or ""
    ):
        raise ReleasePreflightError("recovery_direct_tls_target_invalid")
    engine = create_database_engine(recovery, read_only=True)
    if engine is None:
        raise ReleasePreflightError("recovery_database_url_missing")
    try:
        verify_database_read_target(engine, required_tables=CORE_READ_TABLES)
        recovery_head = _current_heads(engine)
        recovery_inventory, _, _ = _database_inventory(engine)
        if recovery_head != prod_head:
            raise ReleasePreflightError("recovery_schema_differs_from_production")
        if recovery_inventory != prod_inventory:
            raise ReleasePreflightError("recovery_data_inventory_differs_from_production")
    finally:
        engine.dispose()


def _release_sha() -> str:
    value = os.environ.get("RELEASE_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ReleasePreflightError("release_sha_invalid")
    try:
        checkout_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        raise ReleasePreflightError("release_checkout_identity_unavailable") from None
    if checkout_sha != value:
        raise ReleasePreflightError("release_checkout_sha_mismatch")
    return value


def _write_github_outputs(values: dict[str, str]) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")


def run_readonly_preflight() -> dict[str, str]:
    release_sha = _release_sha()
    if os.environ.get("APP_ENV") != "development":
        raise ReleasePreflightError("release_preflight_app_env_must_be_development")
    settings = Settings(_env_file=None)
    validate_read_settings(settings)
    engine = create_database_engine(settings, read_only=True)
    if engine is None:
        raise ReleasePreflightError("production_readonly_database_url_missing")
    try:
        verify_database_read_target(engine, required_tables=CORE_READ_TABLES)
        current = _current_heads(engine)
        required_migration = migration_required(current, expected_heads())
        inventory, fingerprint, total_rows = _database_inventory(engine)
        if required_migration:
            _verify_recovery(settings, current, inventory)
        if settings.database_url is None:
            raise ReleasePreflightError("production_readonly_database_url_missing")
        url = make_url(settings.database_url.get_secret_value())
        result = {
            "release_sha": release_sha,
            "database_name": DATABASE_NAME,
            "database_host": str(url.host),
            "production_head": next(iter(current)),
            "repository_head": RELEASE_HEAD,
            "migration_required": str(required_migration).lower(),
            "public_table_count": str(len(inventory)),
            "public_row_count": str(total_rows),
            "inventory_fingerprint": fingerprint,
            "recovery_verified": str(required_migration).lower(),
        }
    finally:
        engine.dispose()
    _write_github_outputs(result)
    return result


def run_migration_preflight() -> dict[str, str]:
    release_sha = _release_sha()
    settings = Settings(_env_file=None)
    if not settings.database_production_writes_authorized:
        raise ReleasePreflightError("production_migration_authorization_missing")
    validate_read_settings_for_migration(settings)
    engine = create_database_engine(
        settings,
        write_operation="production_release_migration_preflight",
        write_operation_kind="schema_migration",
    )
    if engine is None:
        raise ReleasePreflightError("production_migration_database_url_missing")
    try:
        verify_database_write_target(engine)
        current = _current_heads(engine)
        if current != {PRODUCTION_BASE_REVISION}:
            raise ReleasePreflightError("production_schema_changed_since_review")
        inventory, _, _ = _database_inventory(engine)
        _verify_recovery(settings, current, inventory)
        expected = migration_confirmation(
            project_id=PROJECT_ID,
            branch_id=PRIMARY_BRANCH_ID,
            endpoint_id=PRIMARY_ENDPOINT_ID,
            database=DATABASE_NAME,
            current=PRODUCTION_BASE_REVISION,
            target=RELEASE_HEAD,
        )
        supplied = os.environ.get("MIGRATION_CONFIRMATION", "")
        if supplied != expected:
            raise ReleasePreflightError("exact_migration_confirmation_mismatch")
        result = {
            "release_sha": release_sha,
            "production_head": PRODUCTION_BASE_REVISION,
            "repository_head": RELEASE_HEAD,
            "write_target_guard": "passed",
            "authorization": "job_scoped",
        }
    finally:
        engine.dispose()
    _write_github_outputs(result)
    return result


def validate_read_settings_for_migration(settings: Settings) -> None:
    if (
        settings.database_target_environment != "production"
        or settings.database_target_database != DATABASE_NAME
        or settings.neon_project_id != PROJECT_ID
        or settings.neon_branch_id != PRIMARY_BRANCH_ID
        or settings.neon_endpoint_id != PRIMARY_ENDPOINT_ID
        or settings.neon_api_key is None
    ):
        raise ReleasePreflightError("verified_neon_production_identity_required")
    if (
        any(
            (
                settings.cloud_ingestion_enabled,
                settings.recurring_operations_enabled,
                settings.manual_operations_enabled,
                settings.workbook_sync_enabled,
                settings.fmp_consensus_ingestion_enabled,
            )
        )
        or settings.google_sheets_poll_seconds != 0
    ):
        raise ReleasePreflightError("background_operations_must_be_disabled")
    if settings.database_url is None:
        raise ReleasePreflightError("production_migration_database_url_missing")
    url = make_url(settings.database_url.get_secret_value())
    if url.query.get("sslmode") != "verify-full" or "-pooler." in (url.host or ""):
        raise ReleasePreflightError("production_direct_tls_target_invalid")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("readonly", "migration-preflight"))
    args = parser.parse_args(argv)
    try:
        result = run_readonly_preflight() if args.mode == "readonly" else run_migration_preflight()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (DatabaseWriteTargetError, ReleasePreflightError, SQLAlchemyError, ValueError) as error:
        code = error.code if isinstance(error, DatabaseWriteTargetError) else str(error)
        safe_code = re.sub(r"[^A-Za-z0-9_:.-]", "_", code)[:160]
        print(f"production_release_preflight_blocked:{safe_code or 'unknown'}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
