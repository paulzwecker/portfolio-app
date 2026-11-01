from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from portfolio_api import workbook_value_overlay as overlay
from portfolio_api.legacy_import import Cell, Workbook, build_plan_from_workbooks
from portfolio_api.workbook_sources import SnapshotStore

RUN_ID = "1" * 32
ARTIFACT_SHA = "a" * 64
SEMANTIC_SHA = "b" * 64
IDENTITY_SHA = "c" * 64
FORMULA = "A1*2"


def _fixture() -> tuple[dict[str, Any], Workbook, dict[str, Any]]:
    workbook = Workbook(
        Path("Portfolio_Watchlist.xlsx"),
        ARTIFACT_SHA,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "D5": Cell("1.0000000000000000001", None, FORMULA),
            }
        },
    )
    formula_sha = hashlib.sha256(FORMULA.encode()).hexdigest()
    manifest = {
        "run_id": RUN_ID,
        "profile": "portfolio",
        "contract_version": "portfolio-workbook-contract-v1",
        "expected_filename": "Portfolio_Watchlist.xlsx",
        "status": "ACQUIRED_REVIEW_REQUIRED",
        "artifact_sha256": ARTIFACT_SHA,
        "semantic_fingerprint_version": "portfolio-import-values-v2",
        "semantic_sha256": SEMANTIC_SHA,
        "source_identity_sha256": IDENTITY_SHA,
        "source_modified_at": "2026-10-31T08:00:00Z",
        "source_revision": None,
    }
    report = {
        "report_version": 5,
        "comparison_contract_version": overlay.COMPARISON_CONTRACT_VERSION,
        "run_id": RUN_ID,
        "scope": "canonical-bootstrap",
        "status": "COMPARED",
        "consistency_result": "COMPARED",
        "source_metadata_matches_snapshot": True,
        "source_modified_at_matches_snapshot": True,
        "source_revision_matches_snapshot": None,
        "live_source_stable_during_comparison": True,
        "live_values_stable_across_reads": True,
        "live_formula_definitions_stable_across_reads": True,
        "missing_required_sheets": [],
        "snapshot_artifact_sha256": ARTIFACT_SHA,
        "snapshot_semantic_sha256": overlay._canonical_bootstrap_source_fingerprint(workbook),
        "snapshot_semantic_fingerprint_version": "portfolio-import-values-v2",
        "source_identity_sha256": IDENTITY_SHA,
        "snapshot_source_modified_at": manifest["source_modified_at"],
        "snapshot_source_revision": None,
        "comparison_started_at_utc": "2026-10-31T09:00:00+00:00",
        "comparison_completed_at_utc": "2026-10-31T09:02:00+00:00",
        "canonical_value_changed_count": 1,
        "exception_ledger": {
            "records": [
                {
                    "sheet": "Universe Registry",
                    "cell": "D5",
                    "target_field": "legacy_rank_population.current_weight_input",
                    "transformation": (
                        "exact Decimal membership input only; not canonical current weight"
                    ),
                    "source_role": "spreadsheet_derived_value",
                    "classification": "STALE_XLSX_CACHE_CANDIDATE",
                    "importer_semantic_relation": "IMPORTER_VALUE_DIFFERENCE",
                    "canonical_value_changed": True,
                    "source_state": "VALUE",
                    "live_state": "VALUE",
                    "source_type": "number",
                    "live_type": "number",
                    "source_formula_sha256": formula_sha,
                    "live_formula_sha256": formula_sha,
                    "source_evidence": {
                        "value_text": "1.0000000000000000001",
                        "formula_text": FORMULA,
                    },
                    "live_evidence": {
                        "effective_value": {"numberValue": "0"},
                        "formula_text_for_comparison": FORMULA,
                    },
                }
            ]
        },
    }
    return manifest, workbook, report


def _refresh_scoped_fingerprint(workbook: Workbook, report: dict[str, Any]) -> None:
    """Keep synthetic report evidence bound to an intentionally changed fixture."""
    report["snapshot_semantic_sha256"] = overlay._canonical_bootstrap_source_fingerprint(workbook)


def test_candidate_preserves_exact_decimal_and_explicit_zero() -> None:
    manifest, workbook, report = _fixture()
    candidate = overlay._build_candidate(
        manifest,
        workbook,
        report,
        "d" * 64,
        "2026-10-31T09:03:00+00:00",
    )

    assert candidate["status"] == "REVIEW_REQUIRED"
    assert len(candidate["cells"]) == 1
    assert candidate["cells"][0]["source_value"] == "1.0000000000000000001"
    assert candidate["cells"][0]["live_value"] == "0"
    assert candidate["comparison"]["live_source_observation_time"] == "bounded-comparison-window"


def test_candidate_rejects_comparison_without_recorded_time() -> None:
    manifest, workbook, report = _fixture()
    report.pop("comparison_started_at_utc")

    with pytest.raises(overlay.ValueOverlayError, match="start timestamp"):
        overlay._build_candidate(
            manifest,
            workbook,
            report,
            "d" * 64,
            "2026-10-31T09:03:00+00:00",
        )


def test_candidate_rejects_scope_fingerprint_that_differs_from_frozen_source() -> None:
    manifest, workbook, report = _fixture()
    report["snapshot_semantic_sha256"] = "f" * 64

    with pytest.raises(overlay.ValueOverlayError, match="canonical-bootstrap values"):
        overlay._build_candidate(
            manifest,
            workbook,
            report,
            "d" * 64,
            "2026-10-31T09:03:00+00:00",
        )


def _write_comparison(
    store: SnapshotStore,
    name: str,
    *,
    completed_at: str,
    status: str = "COMPARED",
    contract_version: str = overlay.COMPARISON_CONTRACT_VERSION,
    scope: str = "canonical-bootstrap",
    include_scope: bool = True,
    include_start: bool = False,
) -> str:
    report = {
        "run_id": RUN_ID,
        "comparison_contract_version": contract_version,
        "status": status,
        "comparison_started_at_utc": completed_at,
        "comparison_completed_at_utc": completed_at,
    }
    if include_scope:
        report["scope"] = scope
    if include_start:
        attempt_id = hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
        report["comparison_attempt_id"] = attempt_id
        start = {
            "run_id": RUN_ID,
            "scope": scope,
            "comparison_contract_version": contract_version,
            "comparison_attempt_id": attempt_id,
            "comparison_started_at_utc": completed_at,
            "status": "COMPARISON_ATTEMPT_STARTED",
        }
        start_path = store.root / "value-comparisons" / f"{RUN_ID}-{name}-started.json"
        start_path.parent.mkdir(parents=True, exist_ok=True)
        start_path.write_bytes(overlay._canonical_bytes(start))
    path = store.root / "value-comparisons" / f"{RUN_ID}-{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = overlay._canonical_bytes(report)
    path.write_bytes(raw)
    return overlay._sha256(raw)


def test_latest_failed_comparison_blocks_use_of_older_success(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    _write_comparison(store, "older", completed_at="2026-10-31T09:02:00Z", status="COMPARED")
    _write_comparison(store, "newer", completed_at="2026-10-31T09:04:00Z", status="SOURCE_ADVANCED")

    with pytest.raises(overlay.ValueOverlayError, match="latest comparison did not complete"):
        overlay._comparison_report(store, RUN_ID)


def test_newer_comparison_supersedes_a_candidate_report_hash(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    older_sha = _write_comparison(store, "older", completed_at="2026-10-31T09:02:00Z")
    _write_comparison(store, "newer", completed_at="2026-10-31T09:04:00Z")

    with pytest.raises(overlay.ValueOverlayError, match="newer comparison superseded"):
        overlay._comparison_report(store, RUN_ID, older_sha)


def test_newer_comparison_for_another_scope_blocks_old_canonical_result(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    _write_comparison(store, "older", completed_at="2026-10-31T09:02:00Z")
    _write_comparison(
        store,
        "newer",
        completed_at="2026-10-31T09:04:00Z",
        scope="all-importers",
    )

    with pytest.raises(overlay.ValueOverlayError, match="canonical-bootstrap scope"):
        overlay._comparison_report(store, RUN_ID)


def test_legacy_v5_missing_scope_uses_matching_durable_attempt_start(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    _write_comparison(
        store,
        "scope-omitted",
        completed_at="2026-10-31T09:04:00Z",
        include_scope=False,
        include_start=True,
    )

    report, _report_sha = overlay._comparison_report(store, RUN_ID)

    start_path = store.root / "value-comparisons" / f"{RUN_ID}-scope-omitted-started.json"
    assert report["_scope_verification"]["basis"] == "paired_attempt_start_record"
    assert report["_scope_verification"]["scope"] == "canonical-bootstrap"
    assert report["_scope_verification"]["start_report_sha256"] == overlay._sha256(
        start_path.read_bytes()
    )


def test_legacy_v5_missing_scope_without_durable_start_fails_closed(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    _write_comparison(
        store,
        "scope-omitted",
        completed_at="2026-10-31T09:04:00Z",
        include_scope=False,
    )

    with pytest.raises(overlay.ValueOverlayError, match="canonical-bootstrap scope"):
        overlay._comparison_report(store, RUN_ID)


def test_legacy_v5_missing_scope_rejects_noncanonical_paired_start(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    _write_comparison(
        store,
        "scope-omitted",
        completed_at="2026-10-31T09:04:00Z",
        scope="all-importers",
        include_scope=False,
        include_start=True,
    )

    with pytest.raises(overlay.ValueOverlayError, match="canonical-bootstrap scope"):
        overlay._comparison_report(store, RUN_ID)


def test_pre_v5_comparison_without_timestamps_is_historical_only(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    old_report = {
        "run_id": RUN_ID,
        "scope": "canonical-bootstrap",
        "comparison_contract_version": "portfolio-live-value-comparison-v3",
        "status": "COMPARED",
    }
    path = store.root / "value-comparisons" / f"{RUN_ID}-legacy.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(overlay._canonical_bytes(old_report))
    old_v2 = {
        "run_id": RUN_ID,
        "report_version": 2,
        "status": "COMPARED",
    }
    (store.root / "value-comparisons" / f"{RUN_ID}-older-v2.json").write_bytes(
        overlay._canonical_bytes(old_v2)
    )
    current_sha = _write_comparison(store, "current", completed_at="2026-10-31T09:04:00Z")

    report, report_sha = overlay._comparison_report(store, RUN_ID)

    assert report["comparison_contract_version"] == overlay.COMPARISON_CONTRACT_VERSION
    assert report_sha == current_sha


def test_private_analysis_ledger_does_not_masquerade_as_comparison_attempt(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    ledger = {
        "snapshot_run_id": RUN_ID,
        "source_report_version": 3,
        "source_comparison_contract_version": "portfolio-live-value-comparison-v3",
        "ledger_version": 1,
        "record_count": 0,
        "records": [],
    }
    ledger_path = store.root / "value-comparisons" / f"{RUN_ID}-analysis-ledger.json"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_bytes(overlay._canonical_bytes(ledger))
    current_sha = _write_comparison(store, "current", completed_at="2026-10-31T09:04:00Z")

    report, report_sha = overlay._comparison_report(store, RUN_ID)

    assert report["status"] == "COMPARED"
    assert report_sha == current_sha


def test_unreadable_report_for_snapshot_fails_closed(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    path = store.root / "value-comparisons" / f"{RUN_ID}-corrupt.json"
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(overlay.ValueOverlayError, match="unreadable"):
        overlay._comparison_report(store, RUN_ID)


def test_interrupted_newer_comparison_attempt_blocks_older_success(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    _write_comparison(store, "older", completed_at="2026-10-31T09:02:00Z")
    attempt_id = "e" * 32
    started = {
        "run_id": RUN_ID,
        "scope": "canonical-bootstrap",
        "comparison_contract_version": overlay.COMPARISON_CONTRACT_VERSION,
        "comparison_attempt_id": attempt_id,
        "comparison_started_at_utc": "2026-10-31T09:04:00Z",
        "status": "COMPARISON_ATTEMPT_STARTED",
    }
    path = store.root / "value-comparisons" / f"{RUN_ID}-interrupted.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(overlay._canonical_bytes(started))

    with pytest.raises(overlay.ValueOverlayError, match="attempt did not complete"):
        overlay._comparison_report(store, RUN_ID)


@pytest.mark.parametrize(
    "change",
    [
        lambda record: record.update(classification="FORMULA_DEFINITION_MISMATCH"),
        lambda record: record.update(target_field="Company.name"),
        lambda record: record["live_evidence"].update(formula_text_for_comparison="A1*3"),
        lambda record: record["live_evidence"].update(effective_value={"stringValue": "0"}),
    ],
)
def test_candidate_fails_closed_for_unverified_cell_evidence(
    change: Callable[[dict[str, Any]], None],
) -> None:
    manifest, workbook, report = _fixture()
    change(report["exception_ledger"]["records"][0])

    with pytest.raises(overlay.ValueOverlayError):
        overlay._build_candidate(
            manifest,
            workbook,
            report,
            "d" * 64,
            "2026-10-31T09:03:00+00:00",
        )


def test_candidate_rejects_duplicate_or_unlisted_differences() -> None:
    manifest, workbook, report = _fixture()
    report["exception_ledger"]["records"].append(dict(report["exception_ledger"]["records"][0]))
    report["canonical_value_changed_count"] = 2

    with pytest.raises(overlay.ValueOverlayError, match="duplicate"):
        overlay._build_candidate(
            manifest,
            workbook,
            report,
            "d" * 64,
            "2026-10-31T09:03:00+00:00",
        )


def test_candidate_rejects_unresolved_formula_on_importer_consumed_value() -> None:
    manifest, workbook, report = _fixture()
    workbook.sheets["Price Feed"] = {
        "A5": Cell("AUX", "str", 'IF(TRUE,"AUX","OTHER")'),
        "C5": Cell("SPYY", "inlineStr"),
    }
    _refresh_scoped_fingerprint(workbook, report)
    report["exception_ledger"]["records"].append(
        {
            "sheet": "Price Feed",
            "cell": "A5",
            "target_field": "ListingMapping.row_class",
            "canonical_value_changed": False,
            "importer_semantic_relation": "CURRENT_VALUE_MATCH_FORMULA_TEXT_DIFFERENCE_UNRESOLVED",
        }
    )

    with pytest.raises(overlay.ValueOverlayError, match="formula difference remains unresolved"):
        overlay._build_candidate(
            manifest,
            workbook,
            report,
            "d" * 64,
            "2026-10-31T09:03:00+00:00",
        )


def test_unresolved_formula_on_unsupported_feed_row_does_not_block_overlay() -> None:
    manifest, workbook, report = _fixture()
    workbook.sheets["Price Feed"] = {
        "A5": Cell("AUX", "str", 'IF(TRUE,"AUX","OTHER")'),
        "C5": Cell("UNSUPPORTED", "inlineStr"),
    }
    _refresh_scoped_fingerprint(workbook, report)
    report["exception_ledger"]["records"].append(
        {
            "sheet": "Price Feed",
            "cell": "A5",
            "target_field": "ListingMapping.row_class",
            "canonical_value_changed": False,
            "importer_semantic_relation": "CURRENT_VALUE_MATCH_FORMULA_TEXT_DIFFERENCE_UNRESOLVED",
        }
    )

    candidate = overlay._build_candidate(
        manifest,
        workbook,
        report,
        "d" * 64,
        "2026-10-31T09:03:00+00:00",
    )

    assert len(candidate["cells"]) == 1


def test_only_a_reviewed_hash_bound_overlay_changes_import_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    candidate = {
        "format_version": overlay.CANDIDATE_FORMAT_VERSION,
        "status": "REVIEW_REQUIRED",
        "snapshot": {
            "acquisition_run_id": RUN_ID,
            "artifact_sha256": ARTIFACT_SHA,
            "semantic_sha256": SEMANTIC_SHA,
        },
        "comparison": {
            "comparison_started_at_utc": "2026-10-31T09:00:00+00:00",
            "comparison_completed_at_utc": "2026-10-31T09:02:00+00:00",
        },
        "validation": {"validated_at_utc": "2026-10-31T09:03:00+00:00"},
        "cells": [
            {
                "sheet": "Universe Registry",
                "cell": "D5",
                "target_field": "legacy_rank_population.current_weight_input",
                "source_value": "1.0000000000000000001",
                "source_formula": FORMULA,
                "live_value": "0",
            }
        ],
    }
    candidate_sha = overlay._sha256(overlay._canonical_bytes(candidate))
    approved = {
        "format_version": overlay.OVERLAY_FORMAT_VERSION,
        "status": "APPROVED",
        "candidate_sha256": candidate_sha,
        "candidate": candidate,
        "approval": {
            "reviewed_by": "reviewer",
            "reviewed_at_utc": "2026-10-31T09:04:00+00:00",
            "review_note": "Reviewed source comparison and exact field scope.",
            "confirmation": overlay.APPROVAL_CONFIRMATION,
        },
    }
    artifact = store.root / "value-overlays" / "approved" / "approved.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(overlay._canonical_bytes(approved))
    artifact_sha = overlay._sha256(artifact.read_bytes())
    workbook = Workbook(
        Path("Portfolio_Watchlist.xlsx"),
        ARTIFACT_SHA,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "D5": Cell("1.0000000000000000001", None, FORMULA),
            }
        },
    )
    monkeypatch.setattr(overlay, "_validate_candidate", lambda *_args: workbook)

    summary = overlay.apply_approved_overlay(
        store,
        path=artifact,
        expected_sha256=artifact_sha,
        acquisition_run_id=RUN_ID,
        artifact_sha256=ARTIFACT_SHA,
        semantic_sha256=SEMANTIC_SHA,
        workbook=workbook,
    )

    assert workbook.cell("Universe Registry", "D5").value == "0"
    assert workbook.cell("Universe Registry", "D5").value_before_overlay == (
        "1.0000000000000000001"
    )
    assert workbook.value_overlay_sha256 == artifact_sha
    assert summary["cell_count"] == 1


def test_overlay_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    path = store.root / "value-overlays" / "approved.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": "APPROVED"}), encoding="utf-8")
    workbook = Workbook(Path("frozen.xlsx"), ARTIFACT_SHA, {})

    with pytest.raises(overlay.ValueOverlayError, match="SHA-256"):
        overlay.apply_approved_overlay(
            store,
            path=path,
            expected_sha256="e" * 64,
            acquisition_run_id=RUN_ID,
            artifact_sha256=ARTIFACT_SHA,
            semantic_sha256=SEMANTIC_SHA,
            workbook=workbook,
        )


def test_replaying_identical_overlay_approval_returns_the_same_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SnapshotStore(tmp_path / "private-store")
    candidate = {
        "format_version": overlay.CANDIDATE_FORMAT_VERSION,
        "status": "REVIEW_REQUIRED",
        "snapshot": {"acquisition_run_id": RUN_ID},
    }
    candidate_bytes = overlay._canonical_bytes(candidate)
    candidate_sha = overlay._sha256(candidate_bytes)
    candidate_path = store.root / "value-overlays" / f"{RUN_ID}-candidate-{candidate_sha}.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(candidate_bytes)
    monkeypatch.setattr(
        overlay,
        "_validate_candidate",
        lambda *_args: Workbook(Path("frozen.xlsx"), ARTIFACT_SHA, {}),
    )

    first_path, first_sha, _ = overlay.approve_candidate(
        store,
        RUN_ID,
        candidate_sha,
        reviewed_by="reviewer",
        review_note="Review note.",
        confirm_overlay_values=True,
    )
    replay_path, replay_sha, _ = overlay.approve_candidate(
        store,
        RUN_ID,
        candidate_sha,
        reviewed_by="reviewer",
        review_note="Review note.",
        confirm_overlay_values=True,
    )

    assert replay_path == first_path
    assert replay_sha == first_sha


def test_overlay_changes_import_digest_and_source_provenance() -> None:
    portfolio = Workbook(Path("Portfolio_Watchlist.xlsx"), ARTIFACT_SHA, {})
    market = Workbook(Path("Market Data.xlsx"), SEMANTIC_SHA, {})
    observed_at = datetime(2026, 10, 31, 9, 5, tzinfo=UTC)
    cached_plan = build_plan_from_workbooks(portfolio, market, observed_at)
    base_digest = hashlib.sha256(f"{ARTIFACT_SHA}:{SEMANTIC_SHA}".encode()).hexdigest()
    assert cached_plan.source_digest == base_digest

    portfolio.value_overlay_sha256 = "d" * 64
    overlay_plan = build_plan_from_workbooks(portfolio, market, observed_at)

    assert overlay_plan.source_digest != cached_plan.source_digest
    assert "value-overlay-sha256:" + "d" * 64 in overlay_plan.source_ref(
        portfolio, "Universe Registry", "A5"
    )
