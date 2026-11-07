from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from portfolio_api.canonical_import_readiness import canonical_import_readiness


class StubSession:
    def __init__(self, result: Any) -> None:
        self.result = result

    def scalar(self, _statement: object) -> Any:
        return self.result


RECORDED_AT = datetime(2026, 10, 20, 12, tzinfo=UTC)


def test_missing_canonical_import_is_not_ready() -> None:
    result = canonical_import_readiness(cast(Session, StubSession(None)))

    assert result == {
        "ready": False,
        "status": "MISSING",
        "run_id": None,
        "bootstrap_status": None,
        "reconciliation_status": None,
        "source_gap_count": None,
        "recorded_at": None,
    }


@pytest.mark.parametrize("bootstrap_status", ["APPLIED", "APPLIED_WITH_GAPS"])
def test_reconciled_canonical_import_is_ready_and_reports_source_gaps(
    bootstrap_status: str,
) -> None:
    run = SimpleNamespace(
        id="synthetic-run",
        status=bootstrap_status,
        recorded_at=RECORDED_AT,
        report={"reconciliation": {"status": "MATCHED"}, "source_gaps": [{}, {}]},
    )

    result = canonical_import_readiness(cast(Session, StubSession(run)))

    assert result["ready"] is True
    assert result["status"] == "RECONCILED"
    assert result["source_gap_count"] == 2


def test_import_recorded_after_prepared_run_is_not_a_valid_baseline() -> None:
    run = SimpleNamespace(
        id="synthetic-run",
        status="APPLIED",
        recorded_at=RECORDED_AT,
        report={"reconciliation": {"status": "MATCHED"}, "source_gaps": []},
    )

    result = canonical_import_readiness(
        cast(Session, StubSession(run)),
        run_prepared_at=RECORDED_AT - timedelta(seconds=1),
    )

    assert result["ready"] is False
    assert result["status"] == "BASELINE_AFTER_RUN"


@pytest.mark.parametrize(
    ("bootstrap_status", "reconciliation_status"),
    [("FAILED", "MATCHED"), ("APPLIED", "MISMATCH"), ("APPLIED", None)],
)
def test_unapplied_or_unreconciled_import_is_not_ready(
    bootstrap_status: str, reconciliation_status: str | None
) -> None:
    run = SimpleNamespace(
        id="synthetic-run",
        status=bootstrap_status,
        recorded_at=RECORDED_AT,
        report={"reconciliation": {"status": reconciliation_status}},
    )

    result = canonical_import_readiness(cast(Session, StubSession(run)))

    assert result["ready"] is False
    assert result["status"] == "REVIEW_REQUIRED"


def minimal_receipts() -> tuple[SimpleNamespace, SimpleNamespace]:
    portfolio_hash, market_hash = "e" * 64, "f" * 64
    source_digest = sha256(
        f"canonical-sheets-minimal-v1:{portfolio_hash}:{market_hash}".encode("ascii")
    ).hexdigest()
    legacy = {
        "status": "APPLIED",
        "source_digest": source_digest,
        "reconciliation": {
            "status": "MATCHED",
            "mismatch_count": 0,
            "unresolved_source_issue_count": 0,
            "domains": {
                name: {"status": "MATCHED", "expected": 1, "matched": 1, "mismatches": []}
                for name in (
                    "companies",
                    "securities_and_listings",
                    "lifecycle",
                    "holdings",
                    "strategic_targets",
                    "scores",
                    "ranking_runs",
                )
            },
        },
    }
    report = {
        "status": "APPLIED_WITH_GAPS",
        "import_version": "canonical-sheets-minimal-v1",
        "source_contract_version": "canonical-portfolio-sheets-minimal-v1",
        "input_sha256": "a" * 64,
        "portfolio_source_run_id": "c" * 32,
        "market_source_run_id": "d" * 32,
        "portfolio_source_sha256": portfolio_hash,
        "market_source_sha256": market_hash,
        "legacy_import": legacy,
        "warnings": [{"code": "OPTIONAL_LISTING_MISSING"}],
    }
    return (
        SimpleNamespace(
            id="minimal-run",
            status="APPLIED_WITH_GAPS",
            recorded_at=RECORDED_AT,
            import_version="canonical-sheets-minimal-v1",
            input_digest="a" * 64,
            source_digest=source_digest,
            portfolio_snapshot_run_id="c" * 32,
            market_snapshot_run_id="d" * 32,
            report=report,
        ),
        SimpleNamespace(
            status="APPLIED",
            report=deepcopy(legacy),
            portfolio_workbook_sha256=portfolio_hash,
            market_data_sha256=market_hash,
        ),
    )


class MinimalSession:
    def __init__(self, run: SimpleNamespace, batch: SimpleNamespace | None) -> None:
        self.rows = iter([run, batch])

    def scalar(self, _statement: object) -> Any:
        return next(self.rows)


@pytest.mark.parametrize("status", ["APPLIED", "APPLIED_WITH_GAPS"])
def test_known_minimal_receipt_reuses_linked_reconciliation_without_mutation(status: str) -> None:
    run, batch = minimal_receipts()
    run.status = run.report["status"] = status
    original = deepcopy(run.report)
    result = canonical_import_readiness(cast(Session, MinimalSession(run, batch)))
    assert result["ready"] is True
    assert result["reconciliation_status"] == "MATCHED"
    assert result["source_gap_count"] == 1
    assert run.report == original
    assert (
        canonical_import_readiness(
            cast(Session, MinimalSession(run, batch)),
            run_prepared_at=RECORDED_AT - timedelta(seconds=1),
        )["status"]
        == "BASELINE_AFTER_RUN"
    )


@pytest.mark.parametrize(
    "field",
    [
        "import_version",
        "source_contract_version",
        "input_sha256",
        "portfolio_source_run_id",
        "market_source_run_id",
        "portfolio_source_sha256",
        "market_source_sha256",
        "status",
    ],
)
def test_minimal_receipt_contract_or_hash_mismatch_is_blocked(field: str) -> None:
    run, batch = minimal_receipts()
    run.report[field] = "unexpected"
    assert canonical_import_readiness(cast(Session, MinimalSession(run, batch)))["ready"] is False


@pytest.mark.parametrize(
    "problem",
    [
        "missing_batch",
        "unapplied_batch",
        "different_report",
        "source_digest",
        "missing_reconciliation",
        "mismatch",
        "unresolved",
        "false_zero",
        "missing_domains",
        "domain_mismatch",
        "domain_count_mismatch",
        "domain_errors",
        "domain_false_count",
        "missing_core_domain",
        "root_reconciliation",
        "batch_portfolio_hash",
        "batch_market_hash",
        "derived_digest",
    ],
)
def test_minimal_receipt_requires_complete_matching_immutable_evidence(problem: str) -> None:
    batch: SimpleNamespace | None
    run, batch = minimal_receipts()
    legacy = run.report["legacy_import"]
    if problem == "missing_batch":
        batch = None
    elif problem == "unapplied_batch":
        batch.status = "FAILED"
    elif problem == "different_report":
        batch.report["extra"] = "changed"
    elif problem == "source_digest":
        legacy["source_digest"] = "e" * 64
    elif problem == "missing_reconciliation":
        legacy.pop("reconciliation")
    elif problem == "mismatch":
        legacy["reconciliation"]["status"] = "MISMATCH"
    elif problem == "unresolved":
        legacy["reconciliation"]["unresolved_source_issue_count"] = 1
    elif problem == "false_zero":
        legacy["reconciliation"]["mismatch_count"] = False
    elif problem == "missing_domains":
        legacy["reconciliation"]["domains"] = {}
    elif problem == "domain_mismatch":
        legacy["reconciliation"]["domains"]["holdings"]["status"] = "MISMATCH"
    elif problem == "domain_count_mismatch":
        legacy["reconciliation"]["domains"]["holdings"]["matched"] = 0
    elif problem == "domain_errors":
        legacy["reconciliation"]["domains"]["holdings"]["mismatches"] = ["Quantity differs"]
    elif problem == "domain_false_count":
        legacy["reconciliation"]["domains"]["holdings"]["expected"] = True
    elif problem == "missing_core_domain":
        legacy["reconciliation"]["domains"].pop("holdings")
    elif problem == "root_reconciliation":
        run.report["reconciliation"] = {"status": "MISMATCH"}
    elif problem == "batch_portfolio_hash":
        batch.portfolio_workbook_sha256 = "a" * 64
    elif problem == "batch_market_hash":
        batch.market_data_sha256 = "b" * 64
    elif problem == "derived_digest":
        run.source_digest = legacy["source_digest"] = "c" * 64
    if batch is not None and problem not in {"different_report", "unapplied_batch"}:
        batch.report = deepcopy(legacy)
    assert canonical_import_readiness(cast(Session, MinimalSession(run, batch)))["ready"] is False
