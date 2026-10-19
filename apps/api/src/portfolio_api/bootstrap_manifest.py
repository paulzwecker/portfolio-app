"""Validate metadata for an authoritative-input cloud baseline.

This command validates only a manifest. It never opens source artifacts, imports
application settings, contacts a database, or contacts an external provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,79}$")
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")

_DOMAINS = {
    "company_identities",
    "security_listings",
    "portfolio_state",
    "investment_assessments",
    "market_observations",
    "fx_observations",
    "financial_statements",
    "consensus_estimates",
    "model_outputs",
    "native_model_inputs",
    "research_contracts",
    "ranking_history",
    "source_provenance",
    "operations_history",
    "derived_analytics",
}
_SOURCE_KINDS = {
    "workbook_snapshot",
    "sheet_snapshot",
    "provider_snapshot",
    "accepted_archive",
    "deterministic_pipeline",
    "operator_decision",
}
_DECIMAL_SEMANTICS = {"exact_decimal_strings", "not_applicable"}
_MISSING_SEMANTICS = {"null_absent_distinct_from_zero", "not_applicable"}
_HISTORY_DISPOSITIONS = {
    "current_snapshot_only",
    "preserve_authoritative_history",
    "recompute_as_new",
    "omit_history_approved",
}
_DECIMAL_DOMAINS = {
    "portfolio_state",
    "investment_assessments",
    "market_observations",
    "fx_observations",
    "financial_statements",
    "consensus_estimates",
    "model_outputs",
    "native_model_inputs",
    "derived_analytics",
}
_REQUIRED_KEYS = {
    "source_id",
    "domain",
    "source_kind",
    "source_version",
    "artifact_sha256",
    "identity_map_sha256",
    "recorded_at",
    "effective_at",
    "expected_records",
    "decimal_semantics",
    "missing_value_semantics",
    "history_disposition",
    "methodology_sha256",
    "approval_ref",
    "depends_on",
}


class BootstrapManifestError(ValueError):
    """The manifest does not satisfy the metadata-only bootstrap contract."""


@dataclass(frozen=True)
class ArtifactCheck:
    """A sanitized result for one source artifact or identity map."""

    source_id: str
    artifact_kind: Literal["source", "identity_map"]
    status: Literal["verified", "not_required"]


def _fail(field: str, reason: str) -> NoReturn:
    raise BootstrapManifestError(f"Invalid bootstrap manifest field '{field}': {reason}.")


def _validate_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        _fail(field, "expected a short lowercase identifier")
    return value


def _validate_hash(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail(field, "expected a lowercase SHA-256 digest")
    return value


def _validate_timestamp(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        _fail(field, "expected an RFC 3339 timestamp with an explicit offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(field, "expected an RFC 3339 timestamp with an explicit offset")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(field, "expected an RFC 3339 timestamp with an explicit offset")
    return value


def _validate_version(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        _fail(field, "expected a version token without paths, URLs, or credentials")
    return value


def _validate_entry(value: object, index: int) -> dict[str, Any]:
    field = f"sources[{index}]"
    if not isinstance(value, dict):
        _fail(field, "expected an object")
    entry = cast(dict[str, Any], value)
    if set(entry) != _REQUIRED_KEYS:
        _fail(field, "required metadata fields must be present and unknown fields are forbidden")

    source_id = _validate_identifier(entry["source_id"], f"{field}.source_id")
    domain = entry["domain"]
    if not isinstance(domain, str) or domain not in _DOMAINS:
        _fail(f"{field}.domain", "unsupported domain")
    source_kind = entry["source_kind"]
    if not isinstance(source_kind, str) or source_kind not in _SOURCE_KINDS:
        _fail(f"{field}.source_kind", "unsupported source kind")
    _validate_version(entry["source_version"], f"{field}.source_version")

    disposition = entry["history_disposition"]
    if not isinstance(disposition, str) or disposition not in _HISTORY_DISPOSITIONS:
        _fail(f"{field}.history_disposition", "unsupported history disposition")
    decision_source = source_kind == "operator_decision"
    _validate_hash(entry["artifact_sha256"], f"{field}.artifact_sha256", optional=decision_source)
    _validate_hash(
        entry["identity_map_sha256"], f"{field}.identity_map_sha256", optional=decision_source
    )
    _validate_timestamp(entry["recorded_at"], f"{field}.recorded_at")
    _validate_timestamp(entry["effective_at"], f"{field}.effective_at", optional=True)

    expected_records = entry["expected_records"]
    if expected_records is not None and (
        not isinstance(expected_records, int)
        or isinstance(expected_records, bool)
        or expected_records < 0
    ):
        _fail(f"{field}.expected_records", "expected a non-negative count or null for unknown")

    decimal_semantics = entry["decimal_semantics"]
    if not isinstance(decimal_semantics, str) or decimal_semantics not in _DECIMAL_SEMANTICS:
        _fail(f"{field}.decimal_semantics", "unsupported decimal semantics")
    if domain in _DECIMAL_DOMAINS and decimal_semantics != "exact_decimal_strings":
        _fail(f"{field}.decimal_semantics", "this domain requires exact decimal semantics")
    missing_semantics = entry["missing_value_semantics"]
    if not isinstance(missing_semantics, str) or missing_semantics not in _MISSING_SEMANTICS:
        _fail(f"{field}.missing_value_semantics", "unsupported missing-value semantics")
    if domain in _DECIMAL_DOMAINS and missing_semantics != "null_absent_distinct_from_zero":
        _fail(
            f"{field}.missing_value_semantics",
            "this domain must distinguish missing values from explicit zero",
        )

    methodology_hash = _validate_hash(
        entry["methodology_sha256"], f"{field}.methodology_sha256", optional=True
    )
    if disposition == "recompute_as_new" and methodology_hash is None:
        _fail(f"{field}.methodology_sha256", "recomputed outputs require a pinned methodology")
    if disposition == "recompute_as_new" and domain not in {
        "derived_analytics",
        "model_outputs",
    }:
        _fail(f"{field}.history_disposition", "only outputs can be marked for recomputation")
    approval_ref = entry["approval_ref"]
    if approval_ref is not None and (
        not isinstance(approval_ref, str) or not _IDENTIFIER.fullmatch(approval_ref)
    ):
        _fail(f"{field}.approval_ref", "expected a short approval reference")
    if disposition == "omit_history_approved" and approval_ref is None:
        _fail(f"{field}.approval_ref", "approved omissions require an approval reference")
    if decision_source and disposition != "omit_history_approved":
        _fail(
            f"{field}.history_disposition",
            "operator decisions are only valid for approved omissions",
        )

    dependencies = entry["depends_on"]
    if not isinstance(dependencies, list) or any(
        not isinstance(item, str) or not _IDENTIFIER.fullmatch(item) for item in dependencies
    ):
        _fail(f"{field}.depends_on", "expected a list of source identifiers")
    if len(dependencies) != len(set(dependencies)):
        _fail(f"{field}.depends_on", "duplicate dependencies are forbidden")
    if source_id in dependencies:
        _fail(f"{field}.depends_on", "a source cannot depend on itself")

    return {**entry, "source_id": source_id, "domain": domain, "depends_on": dependencies}


def _topological_order(sources: list[dict[str, Any]]) -> list[str]:
    by_id = {source["source_id"]: source for source in sources}
    if len(by_id) != len(sources):
        _fail("sources", "source identifiers must be unique")
    for source in sources:
        for dependency in source["depends_on"]:
            if dependency not in by_id:
                _fail(f"sources.{source['source_id']}.depends_on", "references an unknown source")

    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(source_id: str) -> None:
        if source_id in visiting:
            _fail("sources.depends_on", "dependency cycle detected")
        if source_id in visited:
            return
        visiting.add(source_id)
        for dependency in by_id[source_id]["depends_on"]:
            visit(dependency)
        visiting.remove(source_id)
        visited.add(source_id)
        ordered.append(source_id)

    for source in sources:
        visit(source["source_id"])
    return ordered


def validate_manifest(value: object) -> list[str]:
    """Validate the closed manifest contract and return safe source execution order."""
    if not isinstance(value, dict) or set(value) != {"format_version", "baseline_id", "sources"}:
        _fail("root", "expected only format_version, baseline_id, and sources")
    manifest = cast(dict[str, Any], value)
    if (
        not isinstance(manifest["format_version"], int)
        or isinstance(manifest["format_version"], bool)
        or manifest["format_version"] != 1
    ):
        _fail("format_version", "only version 1 is supported")
    _validate_identifier(manifest["baseline_id"], "baseline_id")
    raw_sources = manifest["sources"]
    if not isinstance(raw_sources, list) or not raw_sources:
        _fail("sources", "at least one source or approved omission is required")
    sources = [_validate_entry(source, index) for index, source in enumerate(raw_sources)]
    return _topological_order(sources)


def _artifact_digest(
    root: Path,
    filename: str,
    source_id: str,
    kind: Literal["source", "identity_map"],
) -> str:
    candidate = root / filename
    try:
        if candidate.is_symlink():
            raise OSError
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise OSError
        digest = hashlib.sha256()
        with resolved.open("rb") as source_file:
            for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, RuntimeError, ValueError):
        raise BootstrapManifestError(
            f"Input verification failed for source '{source_id}' ({kind}): "
            "the expected file is missing, unsafe, or unreadable."
        ) from None


def verify_source_artifacts(value: object, input_root: Path) -> list[ArtifactCheck]:
    """Verify frozen input bytes against the manifest without opening a DB/provider.

    Artifact paths are derived only from validated source IDs. The input root is an
    explicit operator-selected directory; path names and file contents are never
    included in verification results or errors.
    """
    dependency_order = validate_manifest(value)
    try:
        root = input_root.resolve(strict=True)
        if not root.is_dir():
            raise OSError
    except (OSError, RuntimeError):
        raise BootstrapManifestError(
            "Input verification failed: select an existing input directory."
        ) from None

    manifest = cast(dict[str, Any], value)
    source_by_id = {
        cast(dict[str, Any], source)["source_id"]: cast(dict[str, Any], source)
        for source in cast(list[object], manifest["sources"])
    }
    checks: list[ArtifactCheck] = []
    for source_id in dependency_order:
        source = source_by_id[source_id]
        for field, kind, suffix in (
            ("artifact_sha256", "source", ".artifact"),
            ("identity_map_sha256", "identity_map", ".identity-map.artifact"),
        ):
            artifact_kind = cast(Literal["source", "identity_map"], kind)
            expected = source[field]
            if expected is None:
                checks.append(
                    ArtifactCheck(
                        source_id=source_id,
                        artifact_kind=artifact_kind,
                        status="not_required",
                    )
                )
                continue
            actual = _artifact_digest(root, f"{source_id}{suffix}", source_id, artifact_kind)
            if actual != expected:
                raise BootstrapManifestError(
                    f"Input verification failed for source '{source_id}' ({artifact_kind}): "
                    "SHA-256 does not match the manifest."
                )
            checks.append(
                ArtifactCheck(
                    source_id=source_id,
                    artifact_kind=artifact_kind,
                    status="verified",
                )
            )
    return checks


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object keys are forbidden")
        result[key] = value
    return result


def load_manifest(path: Path) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise BootstrapManifestError("Could not read a valid JSON manifest file.") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate metadata without DB access")
    validate_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser = subparsers.add_parser(
        "verify-inputs", help="verify frozen input bytes without DB or provider access"
    )
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--input-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "validate":
            order = validate_manifest(manifest)
            checks: list[ArtifactCheck] = []
        else:
            checks = verify_source_artifacts(manifest, args.input_root)
            order = validate_manifest(manifest)
    except BootstrapManifestError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.command == "verify-inputs":
        verified = sum(check.status == "verified" for check in checks)
        not_required = sum(check.status == "not_required" for check in checks)
        print(
            "Bootstrap input artifacts verified: "
            f"verified={verified}; not_required={not_required}; "
            f"sources={len(order)}; no database or provider accessed."
        )
    else:
        print(f"Bootstrap input manifest valid: sources={len(order)}; no database accessed.")
    print(f"Dependency order: {' -> '.join(order)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
