"""Synthetic tests for the no-database bootstrap input manifest interface."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from portfolio_api.bootstrap_manifest import (
    BootstrapManifestError,
    main,
    validate_manifest,
)


def _entry(
    source_id: str,
    domain: str,
    *,
    dependencies: list[str] | None = None,
    decimal_semantics: str = "not_applicable",
    missing_value_semantics: str = "not_applicable",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "domain": domain,
        "source_kind": "workbook_snapshot",
        "source_version": "synthetic-v1",
        "artifact_sha256": "a" * 64,
        "identity_map_sha256": "b" * 64,
        "recorded_at": "2026-10-18T12:00:00Z",
        "effective_at": None,
        "expected_records": 2,
        "decimal_semantics": decimal_semantics,
        "missing_value_semantics": missing_value_semantics,
        "history_disposition": "current_snapshot_only",
        "methodology_sha256": None,
        "approval_ref": None,
        "depends_on": dependencies or [],
    }


def _manifest() -> dict[str, object]:
    return {
        "format_version": 1,
        "baseline_id": "synthetic-baseline",
        "sources": [
            _entry("company-identities", "company_identities"),
            _entry(
                "portfolio-state",
                "portfolio_state",
                dependencies=["company-identities"],
                decimal_semantics="exact_decimal_strings",
                missing_value_semantics="null_absent_distinct_from_zero",
            ),
        ],
    }


def test_manifest_validates_dependencies_and_exact_financial_semantics() -> None:
    assert validate_manifest(_manifest()) == ["company-identities", "portfolio-state"]


def test_manifest_rejects_missing_versus_zero_collapse() -> None:
    manifest = _manifest()
    sources = manifest["sources"]
    assert isinstance(sources, list)
    sources[1]["missing_value_semantics"] = "not_applicable"

    with pytest.raises(BootstrapManifestError, match="distinguish missing values"):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_sha256", "not-a-hash"),
        ("identity_map_sha256", None),
        ("recorded_at", "2026-10-18T12:00:00"),
    ],
)
def test_manifest_rejects_unverifiable_hashes_and_timestamps(field: str, value: object) -> None:
    entry = _entry("company-identities", "company_identities")
    entry[field] = value

    with pytest.raises(BootstrapManifestError):
        validate_manifest({"format_version": 1, "baseline_id": "synthetic", "sources": [entry]})


def test_manifest_rejects_recomputation_without_pinned_methodology() -> None:
    entry = _entry(
        "calculated-outputs",
        "derived_analytics",
        decimal_semantics="exact_decimal_strings",
        missing_value_semantics="null_absent_distinct_from_zero",
    )
    entry["history_disposition"] = "recompute_as_new"

    with pytest.raises(BootstrapManifestError, match="pinned methodology"):
        validate_manifest({"format_version": 1, "baseline_id": "synthetic", "sources": [entry]})


def test_manifest_rejects_recomputation_of_source_inputs() -> None:
    entry = _entry(
        "portfolio-state",
        "portfolio_state",
        decimal_semantics="exact_decimal_strings",
        missing_value_semantics="null_absent_distinct_from_zero",
    )
    entry["history_disposition"] = "recompute_as_new"
    entry["methodology_sha256"] = "c" * 64

    with pytest.raises(BootstrapManifestError, match="only outputs"):
        validate_manifest({"format_version": 1, "baseline_id": "synthetic", "sources": [entry]})


def test_manifest_requires_an_approval_reference_for_history_omissions() -> None:
    entry = _entry("old-history", "operations_history")
    entry["source_kind"] = "operator_decision"
    entry["artifact_sha256"] = None
    entry["identity_map_sha256"] = None
    entry["history_disposition"] = "omit_history_approved"

    with pytest.raises(BootstrapManifestError, match="approval reference"):
        validate_manifest({"format_version": 1, "baseline_id": "synthetic", "sources": [entry]})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_path", "private/workbook.xlsx"),
        ("database_url", "postgresql://user:pass@example/db"),
    ],
)
def test_manifest_is_closed_and_rejects_paths_and_credentials(field: str, value: str) -> None:
    entry = _entry("company-identities", "company_identities")
    entry[field] = value

    with pytest.raises(BootstrapManifestError, match="unknown fields are forbidden"):
        validate_manifest({"format_version": 1, "baseline_id": "synthetic", "sources": [entry]})


def test_manifest_rejects_dependency_cycles() -> None:
    manifest = _manifest()
    sources = manifest["sources"]
    assert isinstance(sources, list)
    sources[0]["depends_on"] = ["portfolio-state"]

    with pytest.raises(BootstrapManifestError, match="cycle"):
        validate_manifest(manifest)


def test_manifest_rejects_unknown_dependency() -> None:
    entry = _entry("portfolio-state", "portfolio_state", dependencies=["unknown-source"])
    entry["decimal_semantics"] = "exact_decimal_strings"
    entry["missing_value_semantics"] = "null_absent_distinct_from_zero"

    with pytest.raises(BootstrapManifestError, match="unknown source"):
        validate_manifest({"format_version": 1, "baseline_id": "synthetic", "sources": [entry]})


def test_manifest_version_must_be_an_integer() -> None:
    manifest = _manifest()
    manifest["format_version"] = 1.0

    with pytest.raises(BootstrapManifestError, match="version 1"):
        validate_manifest(manifest)


def test_manifest_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    from portfolio_api.bootstrap_manifest import load_manifest

    path = tmp_path / "synthetic-manifest.json"
    path.write_text('{"format_version":1,"format_version":1}', encoding="utf-8")
    with pytest.raises(BootstrapManifestError, match="valid JSON"):
        load_manifest(path)


def test_cli_validates_manifest_without_using_database_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from json import dumps

    path = tmp_path / "synthetic-manifest.json"
    path.write_text(dumps(_manifest()), encoding="utf-8")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://synthetic-user:synthetic-password@203.0.113.1:5432/unused",
    )

    assert main(["validate", "--manifest", str(path)]) == 0
    output = capsys.readouterr().out
    assert "no database accessed" in output
    assert "synthetic-password" not in output


def test_manifest_input_does_not_mutate_source_object() -> None:
    manifest = _manifest()
    original = deepcopy(manifest)
    validate_manifest(manifest)
    assert manifest == original
