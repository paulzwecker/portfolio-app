"""Import reviewed model outputs and parity-backed native inputs from one frozen snapshot.

This command deliberately composes the existing model-output and native-input importers.
It does not calculate legacy workbook formulas, create ranking/execution history, or treat
published outputs as native model calculations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import portfolio_api.model_input_migration as model_input_migration
import portfolio_api.model_outputs as model_outputs
from portfolio_api.bootstrap_preflight import (
    BootstrapPreflightError,
    verify_database_preflight,
    verify_database_read_only_preflight,
)
from portfolio_api.canonical_bootstrap import (
    ApprovedWorkbookSnapshot,
    CanonicalBootstrapError,
    resolve_approved_snapshot,
)
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import DatabaseWriteTargetError
from portfolio_api.domain.models import (
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    ModelOutputImportBatch,
    ModelOutputSnapshot,
)
from portfolio_api.model_migration_inventory import (
    DEFAULT_OUTPUT as MODEL_MIGRATION_INVENTORY_PATH,
)
from portfolio_api.settings import Settings
from portfolio_api.workbook_sources import PORTFOLIO_PROFILE, SnapshotStore, WorkbookSourceError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")


class ModelAnalyticsBootstrapError(ValueError):
    """Safe, operator-facing bootstrap validation failure."""


def _native_source_sha256() -> str:
    try:
        inventory = json.loads(MODEL_MIGRATION_INVENTORY_PATH.read_text(encoding="utf-8"))
        digest = inventory["source"]["sha256"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        raise ModelAnalyticsBootstrapError(
            "The reviewed native-model migration inventory is missing or invalid."
        ) from None
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ModelAnalyticsBootstrapError(
            "The reviewed native-model migration inventory has no valid source hash."
        )
    return digest


def _state_counts(session: Session) -> dict[str, int]:
    """Small canonical-state inventory used to show before/after import effects."""
    return {
        "native_models": int(session.scalar(select(func.count()).select_from(FinancialModel)) or 0),
        "native_revisions": int(
            session.scalar(select(func.count()).select_from(FinancialModelRevision)) or 0
        ),
        "native_current_outputs": int(
            session.scalar(select(func.count()).select_from(FinancialModelOutput)) or 0
        ),
        "published_output_snapshots": int(
            session.scalar(select(func.count()).select_from(ModelOutputSnapshot)) or 0
        ),
        "published_output_import_batches": int(
            session.scalar(select(func.count()).select_from(ModelOutputImportBatch)) or 0
        ),
    }


def build_bootstrap_report(
    session: Session,
    snapshot: ApprovedWorkbookSnapshot,
    *,
    observed_at: datetime,
    apply: bool,
) -> dict[str, Any]:
    """Build a preview or run the existing importers against one approved snapshot."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ModelAnalyticsBootstrapError("The import timestamp must include a timezone offset.")
    observed = observed_at.astimezone(UTC)
    before = _state_counts(session)

    output_plan = model_outputs.build_import(session, snapshot.path, observed)
    output_report = (
        model_outputs.apply_import(session, output_plan)
        if apply
        else output_plan.report(status="PREVIEW")
    )
    if output_report.get("status") == "RECONCILIATION_FAILED":
        raise ModelAnalyticsBootstrapError(
            "Published model-output reconciliation failed; the import must be rolled back."
        )

    expected_native_sha = _native_source_sha256()
    if snapshot.sha256 != expected_native_sha:
        native_report: dict[str, Any] = {
            "status": "BLOCKED_SOURCE_HASH_MISMATCH",
            "accepted_revisions_created": 0,
            "expected_inventory_sha256": expected_native_sha,
            "approved_snapshot_sha256": snapshot.sha256,
            "reason": (
                "Native assumptions are mapped and parity-reviewed only for the exact source "
                "workbook digest pinned by the migration inventory. This snapshot remains "
                "eligible for published-output import, but not native-input acceptance."
            ),
        }
    else:
        workbook = model_input_migration.load_source_workbook(snapshot.path)
        native_report = model_input_migration.import_native_model_inputs(
            session,
            workbook,
            accepted_at=observed,
            apply=apply,
        )

    after = _state_counts(session) if apply else before
    return {
        "report_version": "1.0.0",
        "mode": "APPLIED" if apply else "PREVIEW",
        "source": {
            "snapshot_run_id": snapshot.run_id,
            "profile": snapshot.profile,
            "expected_filename": snapshot.expected_filename,
            "sha256": snapshot.sha256,
            "schema_fingerprint": snapshot.schema_fingerprint,
            "acquired_at": snapshot.acquired_at.isoformat(),
            "effective_date_policy": (
                "The workbook has no generally trustworthy effective date. Imported historical "
                "output snapshots retain only valid source revision dates; current published "
                "outputs use observed_at. Native model revisions use application acceptance "
                "time unless a separately reviewed source effective time exists."
            ),
        },
        "observed_at": observed.isoformat(),
        "canonical_state_before": before,
        "canonical_state_after": after,
        "published_model_outputs": output_report,
        "native_model_inputs": native_report,
        "derived_analytics": {
            "native_current_outputs": (
                "CALCULATED_FOR_NEWLY_ACCEPTED_REVISIONS_ONLY" if apply else "NOT_RUN"
            ),
            "native_current_outputs_detail": (
                "Only revisions newly accepted by the existing importer are recalculated. The "
                "deterministic engine preserves unavailable/stale exact-listing inputs in its "
                "output status. Already accepted revisions are not rewritten or recalculated."
                if apply
                else "Preview does not recalculate or persist current native outputs."
            ),
            "ranking_runs": "NOT_CREATED",
            "execution_pace_runs": "NOT_CREATED",
            "reason": (
                "This bootstrap does not create immutable decision history. Rank and execution "
                "previews remain separate and require their current canonical prerequisites."
            ),
        },
    }


def _write_private_report(store: SnapshotStore, report: dict[str, Any]) -> str:
    reports = store.root / "model-analytics-bootstrap-runs"
    if reports.is_symlink():
        raise ModelAnalyticsBootstrapError("The private report directory cannot be symlinked.")
    reports.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        reports.resolve(strict=True).relative_to(store.root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        raise ModelAnalyticsBootstrapError("The private report directory is unsafe.") from None
    with os.scandir(reports) as entries:
        if any(entry.is_symlink() for entry in entries):
            raise ModelAnalyticsBootstrapError("The private report directory is unsafe.")
    report_path = reports / f"{uuid.uuid4().hex}.json"
    with os.fdopen(
        os.open(
            report_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        ),
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        reports.chmod(0o700)
    return str((Path("model-analytics-bootstrap-runs") / report_path.name).as_posix())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "apply"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--store", type=Path, required=True)
        subparser.add_argument("--portfolio-run", required=True)
        subparser.add_argument("--portfolio-sha256", required=True)
        subparser.add_argument(
            "--target-environment",
            choices=("development", "rehearsal", "production"),
            required=True,
        )
        subparser.add_argument("--observed-at", type=datetime.fromisoformat)
        if command == "apply":
            subparser.add_argument(
                "--confirm-apply",
                action="store_true",
                help="Confirm an import; the configured database write guard still applies.",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    apply = args.command == "apply"
    if apply and not args.confirm_apply:
        parser.error("apply requires --confirm-apply; database target authorization still applies")
    if not _RUN_ID.fullmatch(args.portfolio_run):
        parser.error("--portfolio-run must be a 32-character lowercase snapshot run ID")
    if not _SHA256.fullmatch(args.portfolio_sha256):
        parser.error("--portfolio-sha256 must be a 64-character lowercase SHA-256")

    engine = None
    try:
        store = SnapshotStore(args.store)
        snapshot = resolve_approved_snapshot(
            store,
            args.portfolio_run,
            expected_profile=PORTFOLIO_PROFILE.key,
            expected_contract_version=PORTFOLIO_PROFILE.contract_version,
            expected_filename=PORTFOLIO_PROFILE.expected_filename,
        )
        if snapshot.sha256 != args.portfolio_sha256:
            raise ModelAnalyticsBootstrapError(
                "The selected approved snapshot does not match --portfolio-sha256."
            )

        settings = Settings()
        if settings.database_url is None:
            raise ModelAnalyticsBootstrapError("DATABASE_URL is required for target verification.")
        engine = create_database_engine(
            settings,
            write_operation="model_analytics_bootstrap",
            write_operation_kind="bootstrap",
            read_only=not apply,
        )
        if engine is None:
            raise ModelAnalyticsBootstrapError("DATABASE_URL is required for target verification.")
        if apply:
            verify_database_preflight(
                engine,
                configured_target_environment=settings.database_target_environment,
                requested_target_environment=args.target_environment,
            )
        else:
            verify_database_read_only_preflight(
                engine,
                configured_target_environment=settings.database_target_environment,
                requested_target_environment=args.target_environment,
            )

        observed_at = args.observed_at or datetime.now(UTC)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ModelAnalyticsBootstrapError("--observed-at must include a timezone offset.")
        if observed_at.astimezone(UTC) > datetime.now(UTC):
            raise ModelAnalyticsBootstrapError("--observed-at cannot be in the future.")

        with Session(engine) as session:
            if apply:
                with session.begin():
                    report = build_bootstrap_report(
                        session, snapshot, observed_at=observed_at, apply=True
                    )
            else:
                report = build_bootstrap_report(
                    session, snapshot, observed_at=observed_at, apply=False
                )
        report_path = _write_private_report(store, report)
        output_summary = report["published_model_outputs"]
        native_summary = report["native_model_inputs"]
        print(
            json.dumps(
                {
                    "status": "APPLIED" if apply else "PREVIEW_COMPLETE",
                    "snapshot_run_id": snapshot.run_id,
                    "snapshot_sha256": snapshot.sha256,
                    "published_output_candidates": output_summary.get(
                        "candidate_snapshot_count", 0
                    ),
                    "published_output_status": output_summary.get("status"),
                    "native_input_status": native_summary.get("status", native_summary.get("mode")),
                    "native_models_imported": native_summary.get("input_sets_imported", 0),
                    "report": report_path,
                    "ranking_and_execution_runs": "NOT_CREATED",
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        BootstrapPreflightError,
        CanonicalBootstrapError,
        DatabaseWriteTargetError,
        ModelAnalyticsBootstrapError,
        WorkbookSourceError,
        OSError,
        ValueError,
    ) as error:
        if isinstance(error, CanonicalBootstrapError):
            message = (
                "The selected snapshot is unavailable, stale, or not schema-approved; "
                "verify its private manifest and reviewed digest."
            )
        elif isinstance(
            error,
            (
                BootstrapPreflightError,
                DatabaseWriteTargetError,
                ModelAnalyticsBootstrapError,
                WorkbookSourceError,
            ),
        ):
            message = str(error)
        else:
            message = "Bootstrap validation or reconciliation failed; no transaction was committed."
        print(f"Model analytics bootstrap failed: {message}", file=sys.stderr)
        return 2
    except Exception:
        message = (
            "Model analytics apply failed; the guarded transaction was rolled back."
            if apply
            else "Model analytics preview failed before any database mutation."
        )
        print(message, file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
