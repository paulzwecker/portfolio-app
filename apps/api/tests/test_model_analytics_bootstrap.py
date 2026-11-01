"""Focused orchestration tests for the reviewed model/analytics bootstrap."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from portfolio_api import model_analytics_bootstrap as bootstrap
from portfolio_api.canonical_bootstrap import ApprovedWorkbookSnapshot, CanonicalBootstrapError


def _snapshot(path: Path, digest: str = "a" * 64) -> ApprovedWorkbookSnapshot:
    return ApprovedWorkbookSnapshot(
        run_id="b" * 32,
        profile="portfolio",
        expected_filename="Portfolio_Watchlist.xlsx",
        sha256=digest,
        path=path,
        acquired_at=datetime(2026, 10, 1, tzinfo=UTC),
        schema_fingerprint="c" * 64,
    )


def _output_plan() -> SimpleNamespace:
    return SimpleNamespace(
        report=lambda *, status="DRY_RUN": {
            "status": status,
            "candidate_snapshot_count": 2,
            "contract_status_counts": {"PASS": 2},
        }
    )


def test_preview_keeps_published_outputs_separate_from_native_calculations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = Mock()
    snapshot = _snapshot(tmp_path / "workbook.xlsx")
    plan = _output_plan()
    output_builder = Mock(return_value=plan)
    output_apply = Mock()
    native_import = Mock(return_value={"mode": "DRY_RUN", "input_sets_imported": 0})
    monkeypatch.setattr(
        bootstrap,
        "model_outputs",
        SimpleNamespace(build_import=output_builder, apply_import=output_apply),
    )
    monkeypatch.setattr(bootstrap, "_native_source_sha256", lambda: snapshot.sha256)
    monkeypatch.setattr(
        bootstrap,
        "model_input_migration",
        SimpleNamespace(
            load_source_workbook=lambda path: SimpleNamespace(sha256=snapshot.sha256),
            import_native_model_inputs=native_import,
        ),
    )
    monkeypatch.setattr(bootstrap, "_state_counts", lambda _: {"native_models": 0})

    report = bootstrap.build_bootstrap_report(
        session,
        snapshot,
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
        apply=False,
    )

    output_builder.assert_called_once_with(
        session, snapshot.path, datetime(2026, 10, 2, tzinfo=UTC)
    )
    output_apply.assert_not_called()
    native_import.assert_called_once()
    assert report["published_model_outputs"]["status"] == "PREVIEW"
    assert report["native_model_inputs"]["mode"] == "DRY_RUN"
    assert report["derived_analytics"]["ranking_runs"] == "NOT_CREATED"
    assert report["derived_analytics"]["execution_pace_runs"] == "NOT_CREATED"
    assert report["canonical_state_before"] == report["canonical_state_after"]


def test_native_import_is_blocked_when_snapshot_differs_from_parity_inventory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = Mock()
    snapshot = _snapshot(tmp_path / "workbook.xlsx", digest="a" * 64)
    monkeypatch.setattr(
        bootstrap,
        "model_outputs",
        SimpleNamespace(build_import=Mock(return_value=_output_plan())),
    )
    monkeypatch.setattr(bootstrap, "_native_source_sha256", lambda: "d" * 64)
    native_import = Mock()
    monkeypatch.setattr(
        bootstrap,
        "model_input_migration",
        SimpleNamespace(import_native_model_inputs=native_import),
    )
    monkeypatch.setattr(bootstrap, "_state_counts", lambda _: {"native_models": 0})

    report = bootstrap.build_bootstrap_report(
        session,
        snapshot,
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
        apply=False,
    )

    assert report["native_model_inputs"]["status"] == "BLOCKED_SOURCE_HASH_MISMATCH"
    assert report["native_model_inputs"]["accepted_revisions_created"] == 0
    native_import.assert_not_called()
    assert report["published_model_outputs"]["candidate_snapshot_count"] == 2


def test_apply_invokes_both_existing_importers_and_records_new_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = Mock()
    snapshot = _snapshot(tmp_path / "workbook.xlsx")
    plan = _output_plan()
    monkeypatch.setattr(
        bootstrap,
        "model_outputs",
        SimpleNamespace(
            build_import=Mock(return_value=plan),
            apply_import=Mock(return_value={"status": "APPLIED", "persisted_snapshots_added": 2}),
        ),
    )
    monkeypatch.setattr(bootstrap, "_native_source_sha256", lambda: snapshot.sha256)
    native_import = Mock(return_value={"mode": "APPLIED", "input_sets_imported": 1})
    monkeypatch.setattr(
        bootstrap,
        "model_input_migration",
        SimpleNamespace(
            load_source_workbook=lambda path: SimpleNamespace(sha256=snapshot.sha256),
            import_native_model_inputs=native_import,
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "_state_counts",
        Mock(side_effect=[{"native_models": 0}, {"native_models": 1}]),
    )

    report = bootstrap.build_bootstrap_report(
        session,
        snapshot,
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
        apply=True,
    )

    assert report["published_model_outputs"]["status"] == "APPLIED"
    assert report["native_model_inputs"]["input_sets_imported"] == 1
    assert report["canonical_state_before"] == {"native_models": 0}
    assert report["canonical_state_after"] == {"native_models": 1}
    native_import.assert_called_once()
    assert native_import.call_args.kwargs["apply"] is True


def test_apply_requires_an_explicit_cli_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    create_engine = Mock(side_effect=AssertionError("must stop before database access"))
    monkeypatch.setattr(bootstrap, "create_database_engine", create_engine)

    with pytest.raises(SystemExit) as error:
        bootstrap.main(
            [
                "apply",
                "--store",
                "C:/private/snapshots",
                "--portfolio-run",
                "b" * 32,
                "--portfolio-sha256",
                "a" * 64,
                "--target-environment",
                "production",
            ]
        )

    assert error.value.code == 2
    create_engine.assert_not_called()


def test_unapproved_snapshot_fails_before_target_connection_and_redacts_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = "b" * 32
    monkeypatch.setattr(bootstrap, "SnapshotStore", lambda root: SimpleNamespace(root=root))
    monkeypatch.setattr(
        bootstrap,
        "resolve_approved_snapshot",
        Mock(side_effect=CanonicalBootstrapError(f"Snapshot {run_id} is not approved.")),
    )
    create_engine = Mock(side_effect=AssertionError("database must not be accessed"))
    monkeypatch.setattr(bootstrap, "create_database_engine", create_engine)

    result = bootstrap.main(
        [
            "preview",
            "--store",
            str(tmp_path),
            "--portfolio-run",
            run_id,
            "--portfolio-sha256",
            "a" * 64,
            "--target-environment",
            "production",
        ]
    )

    assert result == 2
    create_engine.assert_not_called()
    assert run_id not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command", "expected_read_only", "preflight_name"),
    [
        ("preview", True, "verify_database_read_only_preflight"),
        ("apply", False, "verify_database_preflight"),
    ],
)
def test_cli_uses_matching_target_preflight_before_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    expected_read_only: bool,
    preflight_name: str,
) -> None:
    snapshot = _snapshot(tmp_path / "workbook.xlsx")
    settings = SimpleNamespace(database_url=object(), database_target_environment="production")
    engine = Mock()
    session = Mock()
    session.begin.return_value = nullcontext()
    preflight = Mock()
    monkeypatch.setattr(bootstrap, "SnapshotStore", lambda root: SimpleNamespace(root=root))
    monkeypatch.setattr(bootstrap, "resolve_approved_snapshot", Mock(return_value=snapshot))
    monkeypatch.setattr(bootstrap, "Settings", lambda: settings)
    engine_factory = Mock(return_value=engine)
    monkeypatch.setattr(bootstrap, "create_database_engine", engine_factory)
    monkeypatch.setattr(bootstrap, preflight_name, preflight)
    monkeypatch.setattr(bootstrap, "Session", lambda _: nullcontext(session))
    monkeypatch.setattr(
        bootstrap,
        "build_bootstrap_report",
        lambda *args, **kwargs: {
            "published_model_outputs": {"status": "PREVIEW", "candidate_snapshot_count": 0},
            "native_model_inputs": {"mode": "DRY_RUN", "input_sets_imported": 0},
        },
    )
    monkeypatch.setattr(bootstrap, "_write_private_report", lambda *_: "private-report.json")
    argv = [
        command,
        "--store",
        str(tmp_path),
        "--portfolio-run",
        snapshot.run_id,
        "--portfolio-sha256",
        snapshot.sha256,
        "--target-environment",
        "production",
    ]
    if command == "apply":
        argv.append("--confirm-apply")

    assert bootstrap.main(argv) == 0
    engine_factory.assert_called_once_with(
        settings,
        write_operation="model_analytics_bootstrap",
        write_operation_kind="bootstrap",
        read_only=expected_read_only,
    )
    preflight.assert_called_once_with(
        engine,
        configured_target_environment="production",
        requested_target_environment="production",
    )
    engine.dispose.assert_called_once()
    assert '"status"' in capsys.readouterr().out


def test_failed_output_reconciliation_stops_before_native_input_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = Mock()
    snapshot = _snapshot(tmp_path / "workbook.xlsx")
    monkeypatch.setattr(
        bootstrap,
        "model_outputs",
        SimpleNamespace(
            build_import=Mock(return_value=_output_plan()),
            apply_import=Mock(return_value={"status": "RECONCILIATION_FAILED"}),
        ),
    )
    monkeypatch.setattr(bootstrap, "_native_source_sha256", lambda: snapshot.sha256)
    native_import = Mock()
    monkeypatch.setattr(
        bootstrap,
        "model_input_migration",
        SimpleNamespace(import_native_model_inputs=native_import),
    )
    monkeypatch.setattr(bootstrap, "_state_counts", lambda _: {"native_models": 0})

    with pytest.raises(bootstrap.ModelAnalyticsBootstrapError, match="reconciliation failed"):
        bootstrap.build_bootstrap_report(
            session,
            snapshot,
            observed_at=datetime(2026, 10, 2, tzinfo=UTC),
            apply=True,
        )

    native_import.assert_not_called()
