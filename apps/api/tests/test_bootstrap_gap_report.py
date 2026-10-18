from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from portfolio_api.bootstrap_gap_report import (
    DOMAIN_CLASSES,
    build_gap_report,
    load_inventory,
    main,
)


def _inventory(role: str, *, verified: bool, counts: Mapping[str, int | None]) -> dict[str, Any]:
    basis = (
        "operator_reported_aggregate"
        if role == "source"
        else "operator_reported_no_meaningful_canonical_data"
    )
    domains = {}
    for name, recovery_class in DOMAIN_CLASSES.items():
        count = counts.get(name, 0 if role == "target" else None)
        domains[name] = {
            "count": count,
            "precision": (
                "unknown"
                if count is None
                else "approximate"
                if name
                in {"price_observations", "fx_observations", "reported_fundamental_observations"}
                else "exact"
            ),
            "recovery_class": recovery_class,
        }
    return {
        "schema_version": 1,
        "role": role,
        "basis": basis,
        "verified": verified,
        "domains": domains,
    }


def test_report_marks_operator_supplied_counts_provisional_and_counts_only() -> None:
    source_counts = {
        "companies": 219,
        "securities": 110,
        "holdings": 22,
        "target_allocations": 16,
        "price_observations": 305_000,
        "fx_observations": 26_000,
        "reported_fundamental_observations": 27_000,
        "model_output_snapshots": 344,
        "score_assessments": 506,
    }
    source = _inventory("source", verified=False, counts=source_counts)
    target = _inventory("target", verified=False, counts={})

    report = build_gap_report(source, target)
    rows = {row["domain"]: row for row in report["domains"]}

    assert report["status"] == "PROVISIONAL_COUNTS_ONLY"
    assert report["database_accessed"] is False
    assert report["row_level_data_included"] is False
    assert rows["companies"]["reported_difference"] == 219
    assert rows["price_observations"]["reported_difference"] == 305_000
    assert rows["price_observations"]["difference_precision"] == "approximate"
    assert rows["accepted_native_model_revisions"]["status"] == "UNVERIFIED_SOURCE_COUNT_UNKNOWN"
    assert rows["accepted_research_and_thesis_revisions"]["recovery_class"] == "D"


def test_inventory_parser_rejects_row_level_or_secret_fields(tmp_path: Path) -> None:
    inventory = _inventory("source", verified=False, counts={})
    inventory["domains"]["companies"]["company_name"] = "Private Issuer"
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ValueError, match="counts and classifications only"):
        load_inventory(path, "source")


def test_inventory_parser_rejects_non_integer_counts_and_unknown_domains(tmp_path: Path) -> None:
    inventory = _inventory("source", verified=False, counts={})
    inventory["domains"]["companies"]["count"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ValueError, match="non-negative integers"):
        load_inventory(path, "source")

    inventory["domains"]["companies"]["count"] = 1
    inventory["unexpected"] = {"database_url": "secret"}
    path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported fields"):
        load_inventory(path, "source")

    inventory.pop("unexpected")
    inventory["domains"]["companies"]["precision"] = []
    path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(ValueError, match="precision is invalid"):
        load_inventory(path, "source")


def test_cli_writes_only_allowlisted_aggregate_fields(tmp_path: Path, capsys: Any) -> None:
    source_path = tmp_path / "source.json"
    target_path = tmp_path / "target.json"
    output_path = tmp_path / "report.json"
    source_path.write_text(
        json.dumps(_inventory("source", verified=False, counts={"companies": 219})),
        encoding="utf-8",
    )
    target_path.write_text(
        json.dumps(_inventory("target", verified=False, counts={})),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--source",
                str(source_path),
                "--target",
                str(target_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Private Issuer" not in output_path.read_text(encoding="utf-8")
    assert "database_url" not in output_path.read_text(encoding="utf-8")
    assert capsys.readouterr().out == "Wrote sanitized aggregate recovery-gap report.\n"
    assert report["domains"][0].keys() == {
        "domain",
        "recovery_class",
        "source_count",
        "source_precision",
        "target_count",
        "target_precision",
        "reported_difference",
        "difference_precision",
        "source_verified",
        "target_verified",
        "status",
    }


def test_report_rejects_unvalidated_direct_inputs() -> None:
    source = _inventory("source", verified=False, counts={})
    target = _inventory("target", verified=False, counts={})
    source["basis"] = "postgresql://private-user:private-password@example.invalid/db"

    with pytest.raises(ValueError, match="evidence basis"):
        build_gap_report(source, target)


def test_cli_refuses_to_overwrite_an_inventory_input(tmp_path: Path, capsys: Any) -> None:
    source_path = tmp_path / "source.json"
    target_path = tmp_path / "target.json"
    source_path.write_text(
        json.dumps(_inventory("source", verified=False, counts={})), encoding="utf-8"
    )
    target_path.write_text(
        json.dumps(_inventory("target", verified=False, counts={})), encoding="utf-8"
    )

    assert (
        main(
            [
                "--source",
                str(source_path),
                "--target",
                str(target_path),
                "--output",
                str(source_path),
            ]
        )
        == 2
    )
    assert "must not overwrite" in capsys.readouterr().err
