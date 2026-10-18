"""Build a sanitized, counts-only report for a proposed cloud data bootstrap.

The command reads aggregate inventory snapshots only. It never opens a database,
loads environment settings, or accepts row-level values, identifiers, or URLs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DOMAIN_CLASSES = {
    "companies": "A",
    "securities": "A",
    "listings": "A",
    "holdings": "A",
    "target_allocations": "A",
    "price_observations": "B",
    "fx_observations": "B",
    "reported_fundamental_observations": "B",
    "model_output_snapshots": "A",
    "score_assessments": "A",
    "current_derived_analytics": "C",
    "historical_ranking_runs": "D",
    "accepted_native_model_revisions": "D",
    "accepted_research_and_thesis_revisions": "D",
    "source_evidence_and_provenance": "D",
    "provider_payloads_and_ingestion_history": "D",
}
ROOT_FIELDS = {"schema_version", "role", "basis", "verified", "domains"}
DOMAIN_FIELDS = {"count", "precision", "recovery_class"}
PRECISIONS = {"exact", "approximate", "unknown"}
BASES = {
    "source": {"operator_reported_aggregate"},
    "target": {"operator_reported_no_meaningful_canonical_data"},
}


def _normalize_inventory(document: Any, expected_role: str) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != ROOT_FIELDS:
        raise ValueError("Inventory input has unsupported fields or an invalid shape.")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["role"] != expected_role
    ):
        raise ValueError("Inventory schema version or role is invalid.")
    basis = document["basis"]
    if not isinstance(basis, str) or basis not in BASES[expected_role]:
        raise ValueError("Inventory evidence basis is not recognized.")
    if type(document["verified"]) is not bool:
        raise ValueError("Inventory verification status must be boolean.")
    domains = document["domains"]
    if not isinstance(domains, dict) or set(domains) != set(DOMAIN_CLASSES):
        raise ValueError("Inventory must contain the complete allowlisted domain set.")

    normalized: dict[str, Any] = {
        "schema_version": 1,
        "role": expected_role,
        "basis": document["basis"],
        "verified": document["verified"],
        "domains": {},
    }
    for name, entry in domains.items():
        if not isinstance(entry, dict) or set(entry) != DOMAIN_FIELDS:
            raise ValueError(
                "Inventory domain entries may contain counts and classifications only."
            )
        count = entry["count"]
        precision = entry["precision"]
        if not isinstance(precision, str) or precision not in PRECISIONS:
            raise ValueError("Inventory count precision is invalid.")
        if count is None:
            if precision != "unknown":
                raise ValueError("A missing inventory count must use unknown precision.")
        elif type(count) is not int or count < 0 or precision == "unknown":
            raise ValueError(
                "Inventory counts must be non-negative integers or explicitly unknown."
            )
        if entry["recovery_class"] != DOMAIN_CLASSES[name]:
            raise ValueError("Inventory recovery classification does not match the approved map.")
        normalized["domains"][name] = {
            "count": count,
            "precision": precision,
            "recovery_class": DOMAIN_CLASSES[name],
        }
    return normalized


def load_inventory(path: Path, expected_role: str) -> dict[str, Any]:
    """Load a strict count-only inventory snapshot without echoing unsafe input."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Inventory input is unreadable or is not valid JSON.") from None
    return _normalize_inventory(document, expected_role)


def build_gap_report(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Compare sanitized counts and retain uncertainty in the result."""
    source = _normalize_inventory(source, "source")
    target = _normalize_inventory(target, "target")

    rows: list[dict[str, Any]] = []
    for name, recovery_class in DOMAIN_CLASSES.items():
        source_entry = source["domains"][name]
        target_entry = target["domains"][name]
        source_count = source_entry["count"]
        target_count = target_entry["count"]
        if source_count is None:
            difference = None
            status = "SOURCE_COUNT_UNKNOWN"
        elif target_count is None:
            difference = None
            status = "TARGET_COUNT_UNKNOWN"
        else:
            difference = source_count - target_count
            status = (
                "REPORTED_GAP"
                if difference > 0
                else ("TARGET_EXCEEDS_SOURCE" if difference < 0 else "NO_REPORTED_GAP")
            )
        precision = (
            "unknown"
            if difference is None
            else "approximate"
            if "approximate" in {source_entry["precision"], target_entry["precision"]}
            else "reported"
        )
        rows.append(
            {
                "domain": name,
                "recovery_class": recovery_class,
                "source_count": source_count,
                "source_precision": source_entry["precision"],
                "target_count": target_count,
                "target_precision": target_entry["precision"],
                "reported_difference": difference,
                "difference_precision": precision,
                "source_verified": source["verified"],
                "target_verified": target["verified"],
                "status": status
                if source["verified"] and target["verified"]
                else f"UNVERIFIED_{status}",
            }
        )
    return {
        "schema_version": 1,
        "report_type": "aggregate_recovery_gap",
        "status": "VERIFIED_COUNTS"
        if source["verified"] and target["verified"]
        else "PROVISIONAL_COUNTS_ONLY",
        "source_basis": source["basis"],
        "target_basis": target["basis"],
        "database_accessed": False,
        "row_level_data_included": False,
        "domains": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Counts-only source JSON")
    parser.add_argument("--target", type=Path, required=True, help="Counts-only target JSON")
    parser.add_argument("--output", type=Path, help="Optional path for the counts-only JSON report")
    arguments = parser.parse_args(argv)
    try:
        if arguments.output is not None and arguments.output.resolve() in {
            arguments.source.resolve(),
            arguments.target.resolve(),
        }:
            raise ValueError("Report output must not overwrite either inventory input.")
        report = build_gap_report(
            load_inventory(arguments.source, "source"),
            load_inventory(arguments.target, "target"),
        )
        rendered = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        if arguments.output is None:
            print(rendered, end="")
        else:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(rendered, encoding="utf-8")
            print("Wrote sanitized aggregate recovery-gap report.")
    except (OSError, ValueError) as error:
        print(f"Recovery-gap report failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
