from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
