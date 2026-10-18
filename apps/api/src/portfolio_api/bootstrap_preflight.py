"""Run a read-only, target-verified preflight for a cloud bootstrap.

This command verifies frozen inputs, the explicitly selected database target, and
the current Alembic revision. It does not import data or call external providers.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NoReturn

from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Engine

from portfolio_api.bootstrap_manifest import (
    BootstrapManifestError,
    load_manifest,
    validate_manifest,
    verify_source_artifacts,
)
from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    verify_database_write_target,
)
from portfolio_api.migrations import expected_heads
from portfolio_api.settings import Settings

_SAFE_REVISION = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class BootstrapPreflightError(RuntimeError):
    """A sanitized preflight failure that does not include connection details."""


def validate_target_selection(configured: str | None, requested: str) -> None:
    """Require the CLI's explicit target to agree with runtime configuration."""
    if configured is None:
        raise BootstrapPreflightError(
            "DATABASE_TARGET_ENVIRONMENT must be explicitly configured before preflight."
        )
    if configured != requested:
        raise BootstrapPreflightError(
            "The requested target environment does not match DATABASE_TARGET_ENVIRONMENT."
        )


def validate_alembic_heads(current: set[str], expected: set[str]) -> None:
    """Require the database to be at the exact repository migration head."""
    if not expected:
        raise BootstrapPreflightError("The repository does not define an Alembic head.")
    if current == expected:
        return

    def safe_revisions(revisions: set[str]) -> str:
        if not revisions:
            return "<none>"
        return ",".join(
            sorted(
                revision if _SAFE_REVISION.fullmatch(revision) else "<unknown>"
                for revision in revisions
            )
        )

    raise BootstrapPreflightError(
        "Alembic revision mismatch: "
        f"expected [{safe_revisions(expected)}], found [{safe_revisions(current)}]. "
        "Apply the reviewed migrations, then rerun preflight."
    )


def verify_database_preflight(
    engine: Engine,
    *,
    configured_target_environment: str | None,
    requested_target_environment: str,
) -> set[str]:
    """Verify explicit target authorization and schema revision without writes."""
    validate_target_selection(configured_target_environment, requested_target_environment)
    # This invokes the shared guard on its live PostgreSQL connection, including
    # Neon control-plane identity, explicit authorization, privileges, and (for
    # production bootstrap) interactive target confirmation.
    verify_database_write_target(engine)

    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
            connection.rollback()
    except Exception:
        raise BootstrapPreflightError(
            "Could not read the current Alembic revision. Verify that the target schema is "
            "available and rerun preflight."
        ) from None

    expected = expected_heads()
    validate_alembic_heads(current, expected)
    return current


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument(
        "--target-environment",
        choices=("development", "rehearsal", "production"),
        required=True,
        help="must match DATABASE_TARGET_ENVIRONMENT exactly",
    )
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        checks = verify_source_artifacts(manifest, args.input_root)
        order = validate_manifest(manifest)
    except BootstrapManifestError as error:
        _fail(str(error))

    try:
        settings = Settings()
    except Exception:
        _fail(
            "Runtime settings are invalid or incomplete. Review DATABASE_URL and the explicit "
            "database target settings; values are not printed."
        )
    if settings.database_url is None:
        _fail("DATABASE_URL is required for the target preflight.")

    from portfolio_api.database import create_database_engine

    engine = create_database_engine(
        settings,
        write_operation="cloud_bootstrap.preflight",
        write_operation_kind="bootstrap",
    )
    if engine is None:
        _fail("DATABASE_URL is required for the target preflight.")
    try:
        verify_database_preflight(
            engine,
            configured_target_environment=settings.database_target_environment,
            requested_target_environment=args.target_environment,
        )
    except (BootstrapPreflightError, DatabaseWriteTargetError) as error:
        _fail(str(error))
    except Exception:
        _fail("Bootstrap preflight failed. No database writes or provider calls were made.")
    finally:
        engine.dispose()

    verified = sum(check.status == "verified" for check in checks)
    not_required = sum(check.status == "not_required" for check in checks)
    print(
        "Bootstrap preflight passed: "
        f"target={args.target_environment}; alembic=current; sources={len(order)}; "
        f"artifacts_verified={verified}; artifacts_not_required={not_required}; "
        "no writes or provider calls."
    )
    print(f"Dependency order: {' -> '.join(order)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
