"""Readiness evidence for provider imports that require a canonical portfolio baseline."""

import re
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain.models import CanonicalBootstrapRun, LegacyImportBatch


def _minimal_reconciliation(
    session: Session, run: CanonicalBootstrapRun, report: dict[str, Any]
) -> dict[str, Any] | None:
    """Recognize the atomic minimal-import receipt without rewriting its history."""
    if not (
        run.import_version == "canonical-sheets-minimal-v1"
        and report.get("import_version") == run.import_version
        and report.get("source_contract_version") == "canonical-portfolio-sheets-minimal-v1"
        and report.get("input_sha256") == run.input_digest
        and report.get("portfolio_source_run_id") == run.portfolio_snapshot_run_id
        and report.get("market_source_run_id") == run.market_snapshot_run_id
        and report.get("status") == run.status
        and "reconciliation" not in report
    ):
        return None
    portfolio_hash = report.get("portfolio_source_sha256")
    market_hash = report.get("market_source_sha256")
    if any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (portfolio_hash, market_hash)
    ):
        return None
    source_digest = sha256(
        f"{run.import_version}:{portfolio_hash}:{market_hash}".encode("ascii")
    ).hexdigest()
    if run.source_digest != source_digest:
        return None
    legacy = report.get("legacy_import")
    if not isinstance(legacy, dict) or legacy.get("source_digest") != run.source_digest:
        return None
    batch = session.scalar(
        select(LegacyImportBatch).where(LegacyImportBatch.source_digest == run.source_digest)
    )
    if (
        batch is None
        or batch.status != "APPLIED"
        or batch.portfolio_workbook_sha256 != portfolio_hash
        or batch.market_data_sha256 != market_hash
        or batch.report != legacy
    ):
        return None
    reconciliation = legacy.get("reconciliation")
    if not (
        legacy.get("status") == "APPLIED"
        and isinstance(reconciliation, dict)
        and type(reconciliation.get("mismatch_count")) is int
        and reconciliation.get("mismatch_count") == 0
        and type(reconciliation.get("unresolved_source_issue_count")) is int
        and reconciliation.get("unresolved_source_issue_count") == 0
    ):
        return None
    domains = reconciliation.get("domains")
    if (
        not isinstance(domains, dict)
        or not {
            "companies",
            "securities_and_listings",
            "lifecycle",
            "holdings",
            "strategic_targets",
            "scores",
            "ranking_runs",
        }.issubset(domains)
        or any(
            not isinstance(domain, dict)
            or domain.get("status") != "MATCHED"
            or type(domain.get("expected")) is not int
            or type(domain.get("matched")) is not int
            or domain["expected"] < 0
            or domain["expected"] != domain["matched"]
            or domain.get("mismatches") != []
            for domain in domains.values()
        )
    ):
        return None
    return reconciliation


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
    minimal = getattr(run, "import_version", None) == "canonical-sheets-minimal-v1"
    if minimal:
        reconciliation = _minimal_reconciliation(session, run, report)
    reconciliation_status = (
        reconciliation.get("status") if isinstance(reconciliation, dict) else None
    )
    source_gaps = report.get("warnings") if minimal else report.get("source_gaps")
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
