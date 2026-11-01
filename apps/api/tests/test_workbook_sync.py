"""Synthetic PostgreSQL coverage for frozen, reviewed workbook synchronization."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_canonical_bootstrap import _prepared_inputs, synthetic_workbooks

from portfolio_api import canonical_bootstrap, legacy_import, model_outputs, workbook_sync
from portfolio_api.domain.models import (
    Actor,
    CanonicalBootstrapRun,
    CashPosition,
    Company,
    HoldingPosition,
    HoldingSnapshot,
    LegacyImportBatch,
    OperationalJobRequest,
    WorkbookSyncArtifact,
    WorkbookSyncPreview,
    WorkbookSyncRun,
    WorkbookSyncSchemaApproval,
)
from portfolio_api.recurring_operations import _manual_job_steps
from portfolio_api.workbook_sources import (
    PORTFOLIO_PROFILE,
    _portfolio_semantic_manifest,
    inspect_workbook,
)


def _use_empty_model_output_contract_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def build_import(
        _session: Session,
        path: Path,
        observed_at: datetime,
        *,
        source_name: str | None = None,
    ) -> model_outputs.ImportPlan:
        workbook = legacy_import.Workbook(
            path=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            sheets={},
            source_name=source_name,
        )
        return model_outputs.ImportPlan(
            workbook=workbook,
            observed_at=observed_at,
            source_digest=hashlib.sha256(b"empty synthetic model-output projection").hexdigest(),
            batch_id=uuid4(),
            summary={"field_reconciliation": {"mismatches": 0}},
        )

    monkeypatch.setattr(model_outputs, "build_import", build_import)


def _manifest(payload: bytes, *, source_revision: str = "synthetic-revision-1") -> dict[str, Any]:
    inventory = inspect_workbook(payload, PORTFOLIO_PROFILE)
    semantic = _portfolio_semantic_manifest(payload)
    return {
        "manifest_version": 1,
        "profile": PORTFOLIO_PROFILE.key,
        "contract_version": PORTFOLIO_PROFILE.contract_version,
        "source_identity_sha256": hashlib.sha256(b"google-drive:synthetic-only").hexdigest(),
        "source_revision": source_revision,
        "source_modified_at": "2026-10-20T10:00:00+00:00",
        "source_checksum": None,
        "source_mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "schema_fingerprint": inventory.schema_fingerprint,
        "header_fingerprint": inventory.header_fingerprint,
        "semantic_fingerprint_version": semantic["fingerprint_version"],
        "semantic_sha256": semantic["sha256"],
        "semantic_summary": semantic,
        "acquired_at": datetime.now(UTC).isoformat(),
        "acquisition_method": "synthetic_test_fixture",
        "inventory": {"sheet_count": len(inventory.sheet_names)},
    }


def test_missing_workbook_rows_are_reported_without_delete_semantics() -> None:
    prior = {
        "scores": [
            {"ticker": "SYN", "dimension": "RISK"},
            {"ticker": "SYN", "dimension": "DURABILITY"},
        ],
        "targets": [["SYN"]],
        "research_priority_inputs": [{"ticker": "SYN"}],
        "model_output_snapshots": [
            {"company_id": "company-id", "model_key": "ufcf", "snapshot_key": "FY2027"}
        ],
    }
    current: dict[str, object] = {
        "scores": [],
        "targets": [],
        "research_priority_inputs": [],
        "model_output_snapshots": [],
    }

    warnings = workbook_sync._removed_source_row_warnings(prior, current)

    assert {item["domain"] for item in warnings} == set(prior)
    assert all(item["code"] == "SOURCE_ROWS_ABSENT_NOT_DELETED" for item in warnings)
    assert all("No company" in str(item["message"]) for item in warnings)
    assert workbook_sync._source_row_identities("scores", prior["scores"]) == {
        ("SYN", "RISK"),
        ("SYN", "DURABILITY"),
    }


def test_workbook_sync_and_decision_recompute_are_separate_from_refresh_all() -> None:
    refresh_all = _manual_job_steps(
        cast(OperationalJobRequest, SimpleNamespace(job_name="REFRESH_ALL"))
    )
    workbook_sync_steps = _manual_job_steps(
        cast(OperationalJobRequest, SimpleNamespace(job_name="WORKBOOK_SYNC"))
    )
    decision_steps = _manual_job_steps(
        cast(OperationalJobRequest, SimpleNamespace(job_name="DECISION_RECOMPUTE"))
    )

    assert "WORKBOOK_SYNC" not in {step for step, _domains in refresh_all}
    assert "DECISION_RECOMPUTE" not in {step for step, _domains in refresh_all}
    assert workbook_sync_steps == [
        ("WORKBOOK_SYNC", ["WORKBOOK_SOURCE", "WORKBOOK_IMPORT_PREVIEW"])
    ]
    assert decision_steps == [
        (
            "DECISION_RECOMPUTE",
            ["PORTFOLIO_RANK", "WATCHLIST_RANK", "RESEARCH_RANK", "EXECUTION_PACE"],
        )
    ]


@pytest.mark.integration
def test_manual_workbook_request_can_be_queued_without_recurring_scheduler(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from portfolio_api.domain.models import OperationalJobRequest
    from portfolio_api.main import create_app
    from portfolio_api.settings import Settings

    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine",
        lambda _settings, **_kwargs: postgres_engine,
    )
    with TestClient(
        create_app(
            Settings(
                database_url=None,
                recurring_operations_enabled=False,
                manual_operations_enabled=True,
                workbook_sync_enabled=True,
            )
        )
    ) as client:
        response = client.post(
            "/v1/operations/job-requests",
            json={"job_name": "WORKBOOK_SYNC", "scope_kind": "ACTIVE_UNIVERSE"},
        )

    assert response.status_code == 202
    request_id = response.json()["id"]
    with Session(postgres_engine) as session:
        request = session.get(OperationalJobRequest, request_id)
        assert request is not None
        assert request.job_name == "WORKBOOK_SYNC"
        assert request.status == "QUEUED"


@pytest.mark.integration
def test_one_shot_runner_creates_and_runs_only_the_allowlisted_request(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from portfolio_api import manual_job_runner
    from portfolio_api.settings import Settings

    settings = Settings(
        database_url=SecretStr(postgres_engine.url.render_as_string(hide_password=False)),
        recurring_operations_enabled=False,
        manual_operations_enabled=True,
        workbook_sync_enabled=True,
    )
    monkeypatch.setattr(manual_job_runner, "Settings", lambda: settings)
    monkeypatch.setattr(
        manual_job_runner,
        "create_database_engine",
        lambda _settings, **_kwargs: postgres_engine,
    )
    monkeypatch.setattr(manual_job_runner, "verify_database_write_target", lambda _engine: None)
    processed: list[str] = []

    def process_exact_request(
        engine: Engine,
        _settings: Settings,
        *,
        request_id: Any,
    ) -> dict[str, object]:
        with Session(engine) as session:
            request = session.get(OperationalJobRequest, request_id)
            assert request is not None
            assert request.job_name == "WORKBOOK_SYNC"
            assert request.scope_kind == "ACTIVE_UNIVERSE"
            processed.append(str(request.id))
        return {"status": "SUCCEEDED", "steps": []}

    monkeypatch.setattr(manual_job_runner, "process_manual_job_requests", process_exact_request)
    exit_code = manual_job_runner.main(
        ["--job-name", "WORKBOOK_SYNC", "--scope-kind", "ACTIVE_UNIVERSE", "--confirm-run"]
    )

    assert exit_code == 0
    assert len(processed) == 1
    output = capsys.readouterr().out
    assert processed[0] in output
    assert "workbook" not in output.casefold()


@pytest.mark.integration
def test_schema_review_freezes_exact_artifact_before_parsing_and_replay_is_idempotent(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _ = synthetic_workbooks()
    manifest = _manifest(payload)
    monkeypatch.setattr(
        workbook_sync,
        "_preview",
        lambda *_args, **_kwargs: pytest.fail("schema-review artifacts must not be parsed"),
    )

    with Session(postgres_engine) as session, session.begin():
        first = workbook_sync.stage_frozen_snapshot(session, payload=payload, manifest=manifest)
        replay = workbook_sync.stage_frozen_snapshot(session, payload=payload, manifest=manifest)
        assert first.status == "SCHEMA_REVIEW_REQUIRED"
        assert replay.id == first.id
        assert session.scalar(select(func.count()).select_from(WorkbookSyncArtifact)) == 1
        artifact = session.get(WorkbookSyncArtifact, hashlib.sha256(payload).hexdigest())
        assert artifact is not None and bytes(artifact.payload) == payload

    with Session(postgres_engine) as session:
        artifact = session.get(WorkbookSyncArtifact, hashlib.sha256(payload).hexdigest())
        assert artifact is not None
        artifact.payload = b"mutated"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()


@pytest.mark.integration
def test_synthetic_bootstrap_sync_approval_apply_and_replay_are_auditable(
    postgres_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_empty_model_output_contract_fixture(monkeypatch)
    portfolio_bytes, market_bytes = synthetic_workbooks()
    _store, portfolio_snapshot, market_snapshot, plan = _prepared_inputs(
        tmp_path, portfolio_bytes=portfolio_bytes, market_bytes=market_bytes
    )
    with Session(postgres_engine) as session, session.begin():
        bootstrap = canonical_bootstrap.apply_canonical_bootstrap(
            session,
            portfolio_snapshot=portfolio_snapshot,
            market_snapshot=market_snapshot,
            plan=plan,
            provider_plan=None,
            observed_at=plan.observed_at,
            resume=True,
        )
        assert bootstrap["status"] == "APPLIED"

    manifest = _manifest(portfolio_bytes)
    with Session(postgres_engine) as session, session.begin():
        run = workbook_sync.stage_frozen_snapshot(
            session, payload=portfolio_bytes, manifest=manifest
        )
        assert run.status == "SCHEMA_REVIEW_REQUIRED"
        run = workbook_sync.approve_schema(
            session,
            run.id,
            expected_artifact_sha256=hashlib.sha256(portfolio_bytes).hexdigest(),
            reviewer="synthetic-reviewer",
            rationale="Synthetic contract fixture only.",
        )
        assert run.status == "PREVIEWED", run.preview_report
        assert run.preview_report["blocking_issues"] == []
        run_id = run.id

    with Session(postgres_engine) as session, session.begin():
        applied = workbook_sync.apply_run(
            session,
            run_id,
            expected_artifact_sha256=hashlib.sha256(portfolio_bytes).hexdigest(),
            reviewer="synthetic-reviewer",
        )
        assert applied["status"] == "APPLIED"

    with Session(postgres_engine) as session, session.begin():
        replay = workbook_sync.apply_run(
            session,
            run_id,
            expected_artifact_sha256=hashlib.sha256(portfolio_bytes).hexdigest(),
            reviewer="synthetic-reviewer",
        )
        assert replay["status"] == "ALREADY_APPLIED"
        applied_run = session.get(WorkbookSyncRun, run_id)
        assert applied_run is not None and applied_run.status == "APPLIED"
        assert session.scalar(select(func.count()).select_from(WorkbookSyncArtifact)) == 1
        assert session.scalar(select(func.count()).select_from(WorkbookSyncSchemaApproval)) == 1
        assert session.scalar(select(func.count()).select_from(WorkbookSyncPreview)) == 1
        assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 1
        assert session.scalar(select(func.count()).select_from(LegacyImportBatch)) == 2
        assert session.scalar(select(func.count()).select_from(Company)) == 2
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == 1


@pytest.mark.integration
def test_schema_approved_preview_is_rebuilt_when_source_state_changes(
    postgres_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_empty_model_output_contract_fixture(monkeypatch)
    portfolio_bytes, _market_bytes = synthetic_workbooks()
    _store, portfolio_snapshot, market_snapshot, plan = _prepared_inputs(
        tmp_path, portfolio_bytes=portfolio_bytes, market_bytes=synthetic_workbooks()[1]
    )
    with Session(postgres_engine) as session, session.begin():
        canonical_bootstrap.apply_canonical_bootstrap(
            session,
            portfolio_snapshot=portfolio_snapshot,
            market_snapshot=market_snapshot,
            plan=plan,
            provider_plan=None,
            observed_at=plan.observed_at,
            resume=True,
        )

    manifest = _manifest(portfolio_bytes)
    with Session(postgres_engine) as session, session.begin():
        run = workbook_sync.stage_frozen_snapshot(
            session, payload=portfolio_bytes, manifest=manifest
        )
        run = workbook_sync.approve_schema(
            session,
            run.id,
            expected_artifact_sha256=hashlib.sha256(portfolio_bytes).hexdigest(),
            reviewer="synthetic-reviewer",
            rationale="Synthetic contract fixture only.",
        )
        assert run.status == "PREVIEWED"
        run_id = run.id
        prior_preview_count = session.scalar(select(func.count()).select_from(WorkbookSyncPreview))
        assert prior_preview_count is not None

    # Simulate a new application-owned holdings confirmation. Sync must retain the
    # conflict and require a fresh preview rather than overwriting that decision.
    with Session(postgres_engine) as session, session.begin():
        snapshot = session.scalar(select(HoldingSnapshot).limit(1))
        assert snapshot is not None
        portfolio_id = snapshot.portfolio_id
        positions: list[HoldingPosition] = list(
            session.scalars(
                select(HoldingPosition).where(HoldingPosition.snapshot_id == snapshot.id)
            )
        )
        cash_positions: list[CashPosition] = list(
            session.scalars(select(CashPosition).where(CashPosition.snapshot_id == snapshot.id))
        )
        confirmed = HoldingSnapshot(
            id=uuid4(),
            portfolio_id=portfolio_id,
            completeness=snapshot.completeness,
            effective_at=datetime.now(UTC) + timedelta(minutes=1),
            recorded_at=datetime.now(UTC),
            actor=Actor.LOCAL_USER.value,
            reason="Synthetic operator confirmation marker.",
            source="test:operator-confirmation",
        )
        session.add(confirmed)
        session.flush()
        session.info["new_snapshot_ids"] = {confirmed.id}
        session.add_all(
            HoldingPosition(
                id=uuid4(),
                snapshot_id=confirmed.id,
                listing_id=position.listing_id,
                quantity=(position.quantity or Decimal(0)) + Decimal("1"),
            )
            for position in positions
        )
        session.add_all(
            CashPosition(
                id=uuid4(),
                snapshot_id=confirmed.id,
                currency=cash.currency,
                balance=cash.balance,
            )
            for cash in cash_positions
        )
        session.flush()
        session.info.pop("new_snapshot_ids", None)
        with pytest.raises(workbook_sync.WorkbookSyncError, match="changed after preview"):
            workbook_sync.apply_run(
                session,
                run_id,
                expected_artifact_sha256=hashlib.sha256(portfolio_bytes).hexdigest(),
                reviewer="synthetic-reviewer",
            )
        refreshed = workbook_sync.refresh_preview(
            session,
            run_id,
            expected_artifact_sha256=hashlib.sha256(portfolio_bytes).hexdigest(),
        )
        assert refreshed.status == "BLOCKED"
        blocking_issues = refreshed.preview_report.get("blocking_issues", [])
        assert isinstance(blocking_issues, list)
        assert any(
            isinstance(issue, dict)
            and issue.get("code") == "HOLDINGS_APPLICATION_DECISION_CONFLICT"
            for issue in blocking_issues
        )
        assert session.scalar(select(func.count()).select_from(WorkbookSyncPreview)) == (
            prior_preview_count + 1
        )
