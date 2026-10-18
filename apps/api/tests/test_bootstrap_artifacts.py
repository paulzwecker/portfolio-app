"""Synthetic tests for private bootstrap input artifact verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from portfolio_api.bootstrap_manifest import (
    ArtifactCheck,
    BootstrapManifestError,
    main,
    verify_source_artifacts,
)


def _entry(
    source_id: str, domain: str, *, depends_on: list[str] | None = None
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "domain": domain,
        "source_kind": "workbook_snapshot",
        "source_version": "synthetic-v1",
        "artifact_sha256": "0" * 64,
        "identity_map_sha256": "1" * 64,
        "recorded_at": "2026-10-18T12:00:00Z",
        "effective_at": None,
        "expected_records": 2,
        "decimal_semantics": (
            "exact_decimal_strings" if domain == "portfolio_state" else "not_applicable"
        ),
        "missing_value_semantics": (
            "null_absent_distinct_from_zero" if domain == "portfolio_state" else "not_applicable"
        ),
        "history_disposition": "current_snapshot_only",
        "methodology_sha256": None,
        "approval_ref": None,
        "depends_on": depends_on or [],
    }


def _manifest() -> dict[str, object]:
    return {
        "format_version": 1,
        "baseline_id": "synthetic-baseline",
        "sources": [
            _entry("company-identities", "company_identities"),
            _entry("portfolio-state", "portfolio_state", depends_on=["company-identities"]),
        ],
    }


def _write_artifacts(root: Path, manifest: dict[str, object]) -> None:
    sources = manifest["sources"]
    assert isinstance(sources, list)
    for source in sources:
        assert isinstance(source, dict)
        source_id = source["source_id"]
        assert isinstance(source_id, str)
        for field, suffix, content in (
            ("artifact_sha256", ".artifact", f"synthetic source {source_id}".encode()),
            (
                "identity_map_sha256",
                ".identity-map.artifact",
                f"synthetic map {source_id}".encode(),
            ),
        ):
            if source[field] is None:
                continue
            (root / f"{source_id}{suffix}").write_bytes(content)
            source[field] = hashlib.sha256(content).hexdigest()


def test_verify_inputs_checks_bytes_in_dependency_order(tmp_path: Path) -> None:
    manifest = _manifest()
    _write_artifacts(tmp_path, manifest)

    checks = verify_source_artifacts(manifest, tmp_path)

    assert checks == [
        ArtifactCheck("company-identities", "source", "verified"),
        ArtifactCheck("company-identities", "identity_map", "verified"),
        ArtifactCheck("portfolio-state", "source", "verified"),
        ArtifactCheck("portfolio-state", "identity_map", "verified"),
    ]


def test_verify_inputs_rejects_missing_artifact_without_printing_private_path(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    _write_artifacts(tmp_path, manifest)
    (tmp_path / "company-identities.artifact").unlink()

    with pytest.raises(BootstrapManifestError, match="missing, unsafe, or unreadable") as error:
        verify_source_artifacts(manifest, tmp_path)

    assert str(tmp_path) not in str(error.value)


def test_verify_inputs_rejects_hash_mismatch_without_echoing_hash_or_path(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    _write_artifacts(tmp_path, manifest)
    sources = manifest["sources"]
    assert isinstance(sources, list)
    sources[0]["artifact_sha256"] = "f" * 64

    with pytest.raises(BootstrapManifestError, match="SHA-256 does not match") as error:
        verify_source_artifacts(manifest, tmp_path)

    assert str(tmp_path) not in str(error.value)
    assert "f" * 64 not in str(error.value)


def test_verify_inputs_rejects_symlinked_artifact(tmp_path: Path) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    outside_artifact = tmp_path / "outside.artifact"
    outside_artifact.write_bytes(b"synthetic source company-identities")
    manifest = _manifest()
    _write_artifacts(input_root, manifest)
    artifact = input_root / "company-identities.artifact"
    artifact.unlink()
    artifact.symlink_to(outside_artifact)

    with pytest.raises(BootstrapManifestError, match="missing, unsafe, or unreadable"):
        verify_source_artifacts(manifest, input_root)


def test_approved_omission_does_not_require_source_artifacts(tmp_path: Path) -> None:
    source = _entry("omitted-history", "operations_history")
    source.update(
        {
            "source_kind": "operator_decision",
            "artifact_sha256": None,
            "identity_map_sha256": None,
            "history_disposition": "omit_history_approved",
            "approval_ref": "reviewed-omission",
        }
    )
    manifest: dict[str, object] = {
        "format_version": 1,
        "baseline_id": "synthetic-baseline",
        "sources": [source],
    }

    assert verify_source_artifacts(manifest, tmp_path) == [
        ArtifactCheck("omitted-history", "source", "not_required"),
        ArtifactCheck("omitted-history", "identity_map", "not_required"),
    ]


def test_verify_inputs_cli_reports_summary_without_paths_hashes_or_contents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_root = tmp_path / "private-inputs"
    input_root.mkdir()
    manifest = _manifest()
    _write_artifacts(input_root, manifest)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        main(
            [
                "verify-inputs",
                "--manifest",
                str(manifest_path),
                "--input-root",
                str(input_root),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "verified=4; not_required=0; sources=2" in output
    assert "company-identities -> portfolio-state" in output
    assert str(tmp_path) not in output
    assert "synthetic source" not in output
    assert "0" * 64 not in output
