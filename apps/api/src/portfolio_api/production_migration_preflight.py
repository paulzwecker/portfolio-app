"""Read-only target, recovery, and schema preflight for operator-run migrations.

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

from alembic import command as alembic_command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.util.exc import CommandError
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    NeonControlPlaneClient,
    verify_database_read_target,
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
INITIAL_BOOTSTRAP_CONFIRMATION_PREFIX = "INITIALIZE"


class ProductionMigrationPreflightError(RuntimeError):
    """Sanitized release validation error with no provider response body."""


def migration_required(current_heads: set[str], repository_heads: set[str]) -> bool:
    if repository_heads != {RELEASE_HEAD}:
        raise ProductionMigrationPreflightError("repository_migration_head_unexpected")
    if current_heads == {RELEASE_HEAD}:
        return False
    if current_heads == {PRODUCTION_BASE_REVISION}:
        return True
    raise ProductionMigrationPreflightError("production_schema_head_requires_new_review")


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
        raise ProductionMigrationPreflightError("recovery_timestamps_must_be_timezone_aware")
    if created_at < now - timedelta(hours=4) or created_at > now + timedelta(minutes=5):
        raise ProductionMigrationPreflightError("recovery_point_must_be_created_within_four_hours")
    if expires_at is not None and (
        expires_at.tzinfo is None or expires_at <= now + timedelta(hours=24)
    ):
        raise ProductionMigrationPreflightError("recovery_point_expires_too_soon")


def validate_read_settings(settings: Settings) -> None:
    _validate_common_production_read_settings(settings)
    if (
        settings.neon_project_id != PROJECT_ID
        or settings.neon_branch_id != PRIMARY_BRANCH_ID
        or settings.neon_endpoint_id != PRIMARY_ENDPOINT_ID
    ):
        raise ProductionMigrationPreflightError("verified_neon_production_identity_required")


def validate_fresh_bootstrap_read_settings(settings: Settings) -> None:
    """Validate a configured production primary for an empty-database bootstrap."""
    _validate_common_production_read_settings(settings)
    if not all((settings.neon_project_id, settings.neon_branch_id, settings.neon_endpoint_id)):
        raise ProductionMigrationPreflightError("verified_neon_production_identity_required")


def _validate_common_production_read_settings(settings: Settings) -> None:
    if settings.database_url is None:
        raise ProductionMigrationPreflightError("production_readonly_database_url_missing")
    if settings.app_env != "development":
        raise ProductionMigrationPreflightError(
            "production_migration_preflight_must_run_in_isolated_tooling_mode"
        )
    if settings.database_target_environment != "production":
        raise ProductionMigrationPreflightError("production_database_target_environment_mismatch")
    if not settings.database_target_database:
        raise ProductionMigrationPreflightError("production_database_name_missing")
    if any(
        (
            settings.database_local_test_writes_authorized,
            settings.database_local_writes_authorized,
            settings.database_rehearsal_writes_authorized,
            settings.database_production_writes_authorized,
        )
    ):
        raise ProductionMigrationPreflightError(
            "all_database_write_authorizations_must_be_disabled_in_preflight"
        )
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
        raise ProductionMigrationPreflightError("background_operations_must_be_disabled")
    if settings.neon_api_key is None:
        raise ProductionMigrationPreflightError("verified_neon_production_identity_required")
    url = make_url(settings.database_url.get_secret_value())
    if (
        url.database != settings.database_target_database
        or url.host is None
        or "-pooler." in url.host
        or url.query.get("sslmode") != "verify-full"
    ):
        raise ProductionMigrationPreflightError("production_direct_tls_target_invalid")


def _current_heads(engine: Engine) -> set[str]:
    try:
        with engine.connect() as connection:
            heads = set(MigrationContext.configure(connection).get_current_heads())
            connection.rollback()
            return heads
    except SQLAlchemyError:
        raise ProductionMigrationPreflightError("production_alembic_revision_unavailable") from None


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
        raise ProductionMigrationPreflightError("database_inventory_read_failed") from None


def _user_relations(engine: Engine) -> tuple[str, ...]:
    """Return user-schema relations that would make a target non-empty."""
    try:
        with engine.connect() as connection:
            rows: list[Any] = list(
                connection.execute(
                    text(
                        """SELECT n.nspname || '.' || c.relname
                       FROM pg_catalog.pg_class AS c
                       JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                       WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                         AND n.nspname !~ '^pg_'
                         AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                       ORDER BY n.nspname, c.relname"""
                    )
                ).scalars()
            )
            relations = tuple(str(value) for value in rows)
            connection.rollback()
            return relations
    except SQLAlchemyError:
        raise ProductionMigrationPreflightError("database_relation_inventory_read_failed") from None


def _current_schema(engine: Engine) -> str:
    try:
        with engine.connect() as connection:
            schema = connection.execute(text("SELECT current_schema()")).scalar_one_or_none()
            connection.rollback()
            return str(schema or "")
    except SQLAlchemyError:
        raise ProductionMigrationPreflightError("database_schema_identity_read_failed") from None


def _branch_timestamps(
    settings: Settings, branch_id: str
) -> tuple[datetime | None, datetime | None]:
    assert settings.neon_api_key is not None
    client = NeonControlPlaneClient(settings.neon_api_key.get_secret_value())
    try:
        payload = client._get_json(f"/projects/{PROJECT_ID}/branches/{branch_id}")
    except DatabaseWriteTargetError as error:
        raise ProductionMigrationPreflightError(
            f"neon_recovery_metadata_unavailable:{error.code}"
        ) from None
    branch = payload.get("branch", payload)
    if not isinstance(branch, Mapping):
        raise ProductionMigrationPreflightError("neon_recovery_metadata_invalid")
    created = _parse_datetime(branch.get("created_at"))
    expires = _parse_datetime(branch.get("expires_at"))
    return created, expires


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProductionMigrationPreflightError("neon_branch_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ProductionMigrationPreflightError("neon_branch_timestamp_invalid") from None
    if parsed.tzinfo is None:
        raise ProductionMigrationPreflightError("neon_branch_timestamp_invalid")
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
        raise ProductionMigrationPreflightError("fresh_recovery_point_configuration_required")
    created_at, expires_at = _branch_timestamps(primary, str(recovery_branch))
    now = datetime.now(UTC)
    if created_at is None:
        raise ProductionMigrationPreflightError("recovery_branch_creation_time_missing")
    validate_recovery_window(created_at=created_at, expires_at=expires_at, now=now)

    recovery = _read_settings_for_recovery(
        primary, str(recovery_url), str(recovery_branch), str(recovery_endpoint)
    )
    recovery_url_obj = make_url(str(recovery_url))
    if recovery_url_obj.query.get("sslmode") != "verify-full" or "-pooler." in (
        recovery_url_obj.host or ""
    ):
        raise ProductionMigrationPreflightError("recovery_direct_tls_target_invalid")
    engine = create_database_engine(recovery, read_only=True)
    if engine is None:
        raise ProductionMigrationPreflightError("recovery_database_url_missing")
    try:
        verify_database_read_target(engine, required_tables=CORE_READ_TABLES)
        recovery_head = _current_heads(engine)
        recovery_inventory, _, _ = _database_inventory(engine)
        if recovery_head != prod_head:
            raise ProductionMigrationPreflightError("recovery_schema_differs_from_production")
        if recovery_inventory != prod_inventory:
            raise ProductionMigrationPreflightError(
                "recovery_data_inventory_differs_from_production"
            )
    finally:
        engine.dispose()


def _checkout_sha(*, allow_codex_branch: bool = False) -> str:
    value = os.environ.get("EXPECTED_CHECKOUT_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ProductionMigrationPreflightError("checkout_sha_invalid")
    repository_root = Path(__file__).resolve().parents[4]
    try:
        checkout_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=repository_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repository_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        raise ProductionMigrationPreflightError("checkout_identity_unavailable") from None
    if checkout_sha != value:
        raise ProductionMigrationPreflightError("checkout_sha_mismatch")
    if branch != "main" and not (allow_codex_branch and branch.startswith("codex/")):
        raise ProductionMigrationPreflightError("checkout_must_be_main")
    if status:
        raise ProductionMigrationPreflightError("checkout_must_be_clean")
    return value


def initial_bootstrap_confirmation(
    *, project_id: str, branch_id: str, endpoint_id: str, database: str, target: str
) -> str:
    """Bind the empty-target review to one Neon primary and full migration range."""
    return (
        f"{INITIAL_BOOTSTRAP_CONFIRMATION_PREFIX} {project_id}/{branch_id}/{endpoint_id}/"
        f"{database}/base->{target}"
    )


def run_fresh_bootstrap_preflight() -> dict[str, str]:
    """Read-only proof that an exact Neon primary is empty before its first migration."""
    checkout_sha = _checkout_sha(allow_codex_branch=True)
    if os.environ.get("APP_ENV") != "development":
        raise ProductionMigrationPreflightError(
            "production_migration_preflight_app_env_must_be_development"
        )
    settings = Settings(_env_file=None)
    validate_fresh_bootstrap_read_settings(settings)
    if expected_heads() != {RELEASE_HEAD}:
        raise ProductionMigrationPreflightError("repository_migration_head_unexpected")
    engine = create_database_engine(settings, read_only=True)
    if engine is None:
        raise ProductionMigrationPreflightError("production_readonly_database_url_missing")
    try:
        verify_database_read_target(engine, required_tables=())
        if _current_schema(engine) != "public":
            raise ProductionMigrationPreflightError("fresh_bootstrap_default_schema_must_be_public")
        current = _current_heads(engine)
        if current:
            raise ProductionMigrationPreflightError(
                "fresh_bootstrap_target_already_has_migration_state"
            )
        relations = _user_relations(engine)
        if relations:
            raise ProductionMigrationPreflightError("fresh_bootstrap_target_contains_relations")
        inventory, fingerprint, total_rows = _database_inventory(engine)
        if inventory or total_rows:
            raise ProductionMigrationPreflightError("fresh_bootstrap_target_contains_tables")
        database = settings.database_target_database
        project_id = settings.neon_project_id
        branch_id = settings.neon_branch_id
        endpoint_id = settings.neon_endpoint_id
        if not all((database, project_id, branch_id, endpoint_id)):
            raise ProductionMigrationPreflightError("verified_neon_production_identity_required")
        expected_confirmation = initial_bootstrap_confirmation(
            project_id=str(project_id),
            branch_id=str(branch_id),
            endpoint_id=str(endpoint_id),
            database=str(database),
            target=RELEASE_HEAD,
        )
        if os.environ.get("INITIAL_BOOTSTRAP_CONFIRMATION", "") != expected_confirmation:
            raise ProductionMigrationPreflightError("exact_initial_bootstrap_confirmation_mismatch")
        return {
            "checkout_sha": checkout_sha,
            "database_name": str(database),
            "neon_project_id": str(project_id),
            "neon_primary_branch_id": str(branch_id),
            "neon_endpoint_id": str(endpoint_id),
            "current_head": "base",
            "repository_head": RELEASE_HEAD,
            "migration_required": "true",
            "empty_database_verified": "true",
            "public_table_count": str(len(inventory)),
            "public_row_count": str(total_rows),
            "user_relation_count": str(len(relations)),
            "inventory_fingerprint": fingerprint,
            "recovery_required": "false",
            "write_authorization": "disabled",
        }
    finally:
        engine.dispose()


def run_fresh_bootstrap_schema_check() -> dict[str, str]:
    """Read-only verification after the complete fresh-database upgrade."""
    checkout_sha = _checkout_sha(allow_codex_branch=True)
    if os.environ.get("APP_ENV") != "development":
        raise ProductionMigrationPreflightError(
            "production_migration_preflight_app_env_must_be_development"
        )
    settings = Settings(_env_file=None)
    validate_fresh_bootstrap_read_settings(settings)
    engine = create_database_engine(settings, read_only=True)
    if engine is None:
        raise ProductionMigrationPreflightError("production_readonly_database_url_missing")
    try:
        verify_database_read_target(engine)
        current = _current_heads(engine)
        if current != expected_heads() or current != {RELEASE_HEAD}:
            raise ProductionMigrationPreflightError("fresh_bootstrap_schema_not_at_release_head")
        with engine.connect() as connection:
            try:
                _check_mapped_alembic_metadata(connection)
            finally:
                connection.rollback()
        return {
            "checkout_sha": checkout_sha,
            "database_name": str(settings.database_target_database),
            "alembic_head": RELEASE_HEAD,
            "metadata_check": "no_drift",
            "connection": "read_only",
        }
    finally:
        engine.dispose()


def run_readonly_preflight() -> dict[str, str]:
    checkout_sha = _checkout_sha()
    if os.environ.get("APP_ENV") != "development":
        raise ProductionMigrationPreflightError(
            "production_migration_preflight_app_env_must_be_development"
        )
    settings = Settings(_env_file=None)
    validate_read_settings(settings)
    engine = create_database_engine(settings, read_only=True)
    if engine is None:
        raise ProductionMigrationPreflightError("production_readonly_database_url_missing")
    try:
        verify_database_read_target(engine, required_tables=CORE_READ_TABLES)
        current = _current_heads(engine)
        required_migration = migration_required(current, expected_heads())
        inventory, fingerprint, total_rows = _database_inventory(engine)
        # Every schema migration requires a freshly verified pre-migration state,
        # including the initial migration while only reference rows exist.
        needs_recovery = required_migration
        if needs_recovery:
            _verify_recovery(settings, current, inventory)
        if settings.database_url is None:
            raise ProductionMigrationPreflightError("production_readonly_database_url_missing")
        url = make_url(settings.database_url.get_secret_value())
        result = {
            "checkout_sha": checkout_sha,
            "database_name": DATABASE_NAME,
            "database_host": str(url.host),
            "production_head": next(iter(current)),
            "repository_head": RELEASE_HEAD,
            "migration_required": str(required_migration).lower(),
            "recovery_required": str(needs_recovery).lower(),
            "public_table_count": str(len(inventory)),
            "public_row_count": str(total_rows),
            "inventory_fingerprint": fingerprint,
            "recovery_verified": (
                "verified" if needs_recovery else ("not_required_schema_current")
            ),
        }
    finally:
        engine.dispose()
    return result


def run_readonly_schema_check() -> dict[str, str]:
    """Compare mapped metadata to the release schema through a read-only engine."""
    checkout_sha = _checkout_sha()
    if os.environ.get("APP_ENV") != "development":
        raise ProductionMigrationPreflightError(
            "production_migration_preflight_app_env_must_be_development"
        )
    settings = Settings(_env_file=None)
    validate_read_settings(settings)
    engine = create_database_engine(settings, read_only=True)
    if engine is None:
        raise ProductionMigrationPreflightError("production_readonly_database_url_missing")
    try:
        verify_database_read_target(engine, required_tables=CORE_READ_TABLES)
        current = _current_heads(engine)
        if current != expected_heads():
            raise ProductionMigrationPreflightError("production_schema_not_at_release_head")
        with engine.connect() as connection:
            try:
                _check_mapped_alembic_metadata(connection)
            finally:
                connection.rollback()
        result = {
            "checkout_sha": checkout_sha,
            "alembic_head": next(iter(current)),
            "metadata_check": "no_drift",
            "connection": "read_only",
        }
    finally:
        engine.dispose()
    return result


def run_migration_preflight() -> dict[str, str]:
    checkout_sha = _checkout_sha()
    if os.environ.get("APP_ENV") != "development":
        raise ProductionMigrationPreflightError(
            "production_migration_preflight_app_env_must_be_development"
        )
    settings = Settings(_env_file=None)
    validate_read_settings(settings)
    engine = create_database_engine(settings, read_only=True)
    if engine is None:
        raise ProductionMigrationPreflightError("production_readonly_database_url_missing")
    try:
        verify_database_read_target(engine, required_tables=CORE_READ_TABLES)
        current = _current_heads(engine)
        if current != {PRODUCTION_BASE_REVISION}:
            raise ProductionMigrationPreflightError("production_schema_changed_since_review")
        inventory, _, _ = _database_inventory(engine)
        _verify_recovery(settings, current, inventory)
        recovery_status = "verified"
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
            raise ProductionMigrationPreflightError("exact_migration_confirmation_mismatch")
        result = {
            "checkout_sha": checkout_sha,
            "production_head": PRODUCTION_BASE_REVISION,
            "repository_head": RELEASE_HEAD,
            "read_target_guard": "passed",
            "write_authorization": "disabled",
            "recovery_required": "true",
            "recovery_verified": recovery_status,
        }
    finally:
        engine.dispose()
    return result


def _check_mapped_alembic_metadata(connection: Connection) -> None:
    """Run Alembic autogenerate comparison on the supplied read-only connection."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = connection
    try:
        alembic_command.check(config)
    except CommandError:
        raise ProductionMigrationPreflightError("alembic_metadata_drift_detected") from None
    except SQLAlchemyError:
        raise ProductionMigrationPreflightError("alembic_metadata_check_database_error") from None
    except Exception:
        raise ProductionMigrationPreflightError("alembic_metadata_check_failed") from None
    finally:
        config.attributes.pop("connection", None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "readonly",
            "migration-preflight",
            "schema-check",
            "fresh-bootstrap-preflight",
            "fresh-bootstrap-schema-check",
        ),
    )
    args = parser.parse_args(argv)
    try:
        if args.mode == "readonly":
            result = run_readonly_preflight()
        elif args.mode == "migration-preflight":
            result = run_migration_preflight()
        elif args.mode == "fresh-bootstrap-preflight":
            result = run_fresh_bootstrap_preflight()
        elif args.mode == "fresh-bootstrap-schema-check":
            result = run_fresh_bootstrap_schema_check()
        else:
            result = run_readonly_schema_check()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (
        DatabaseWriteTargetError,
        ProductionMigrationPreflightError,
        SQLAlchemyError,
        ValueError,
    ) as error:
        code = error.code if isinstance(error, DatabaseWriteTargetError) else str(error)
        safe_code = re.sub(r"[^A-Za-z0-9_:.-]", "_", code)[:160]
        print(f"production_migration_preflight_blocked:{safe_code or 'unknown'}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
