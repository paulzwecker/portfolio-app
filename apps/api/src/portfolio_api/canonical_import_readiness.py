"""Readiness evidence for provider imports that require a canonical portfolio baseline."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain.models import CanonicalBootstrapRun


def canonical_import_readiness(
    session: Session, *, run_prepared_at: datetime | None = None
) -> dict[str, Any]:
    """Report whether the newest canonical import is reconciled and predates a run."""

    run = session.scalar(
        select(CanonicalBootstrapRun)
        .order_by(CanonicalBootstrapRun.recorded_at.desc(), CanonicalBootstrapRun.id.desc())
        .limit(1)
    )
    if run is None:
        return {
            "ready": False,
            "status": "MISSING",
            "run_id": None,
            "bootstrap_status": None,
            "reconciliation_status": None,
            "source_gap_count": None,
            "recorded_at": None,
        }
    report = run.report if isinstance(run.report, dict) else {}
    reconciliation = report.get("reconciliation")
    reconciliation_status = (
        reconciliation.get("status") if isinstance(reconciliation, dict) else None
    )
    source_gaps = report.get("source_gaps")
    source_gap_count = len(source_gaps) if isinstance(source_gaps, list) else None
    reconciliation_ready = (
        run.status in {"APPLIED", "APPLIED_WITH_GAPS"} and reconciliation_status == "MATCHED"
    )
    baseline_predates_run = run_prepared_at is None or run.recorded_at <= run_prepared_at
    ready = reconciliation_ready and baseline_predates_run
    return {
        "ready": ready,
        "status": (
            "RECONCILED"
            if ready
            else "BASELINE_AFTER_RUN"
            if reconciliation_ready and not baseline_predates_run
            else "REVIEW_REQUIRED"
        ),
        "run_id": str(run.id),
        "bootstrap_status": run.status,
        "reconciliation_status": reconciliation_status,
        "source_gap_count": source_gap_count,
        "recorded_at": run.recorded_at.isoformat(),
    }
