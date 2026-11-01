"""Review-gated, narrowly scoped live-value overlays for portfolio workbook imports.

Overlay candidates are derived from one timestamped, stable live comparison and the exact
frozen XLSX artifact. Candidate and approval artifacts belong only in the private snapshot
store; they contain source values and must never be committed or printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from portfolio_api.legacy_import import Workbook
from portfolio_api.workbook_semantics import (
    SEMANTIC_FINGERPRINT_VERSION,
    importer_field_semantics,
    importer_value_cells,
    semantic_fingerprint,
)
from portfolio_api.workbook_sources import (
    PORTFOLIO_PROFILE,
    SnapshotStore,
    WorkbookSourceError,
    inspect_workbook,
)
from portfolio_api.workbook_value_validation import (
    _importer_cell_is_consumed,
    _source_formula_map,
    _validation_plan,
    compare_semantic_values,
)

OVERLAY_FORMAT_VERSION = "portfolio-live-value-overlay-v1"
CANDIDATE_FORMAT_VERSION = "portfolio-live-value-overlay-candidate-v1"
APPROVAL_CONFIRMATION = "I_REVIEWED_THE_EXACT_OVERLAY_CANDIDATE"
COMPARISON_CONTRACT_VERSION = "portfolio-live-value-comparison-v5"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_ALLOWED_TARGET_FIELDS = frozenset(
    {
        "legacy_rank_population.current_weight_input",
        "ScoreAssessment.COMPOUNDER_QUALITY.score",
        "ScoreAssessment.DURABILITY_10Y.score",
        "ScoreAssessment.EXECUTION.score",
        "ScoreAssessment.RISK.score",
    }
)


class ValueOverlayError(ValueError):
    """Sanitized failure for candidate, approval, or application of a value overlay."""


def _verified_comparison_scope(
    report: dict[str, Any],
    *,
    paired_start: dict[str, Any] | None = None,
    paired_start_sha256: str | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Verify scope explicitly or from the same attempt's durable start record."""
    if "scope" in report:
        scope = report.get("scope")
        if paired_start is not None and paired_start.get("scope") != scope:
            return None, {"basis": "completed_and_start_scope_conflict"}
        return (
            scope if isinstance(scope, str) else None,
            {"basis": "explicit_report_scope", "scope": scope},
        )
    if (
        paired_start is None
        or paired_start.get("status") != "COMPARISON_ATTEMPT_STARTED"
        or paired_start.get("run_id") != report.get("run_id")
        or paired_start.get("comparison_contract_version")
        != report.get("comparison_contract_version")
        or paired_start.get("comparison_attempt_id") != report.get("comparison_attempt_id")
        or not isinstance(paired_start_sha256, str)
        or not _SHA256.fullmatch(paired_start_sha256)
    ):
        return None, {"basis": "scope_missing_or_matching_start_record_unavailable"}
    scope = paired_start.get("scope")
    if not isinstance(scope, str):
        return None, {"basis": "scope_missing_or_matching_start_record_unscoped"}
    return scope, {
        "basis": "paired_attempt_start_record",
        "scope": scope,
        "start_report_sha256": paired_start_sha256,
    }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueOverlayError(f"The comparison is missing its {field} timestamp.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueOverlayError(f"The comparison {field} timestamp is invalid.") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueOverlayError(f"The comparison {field} timestamp must include a timezone.")
    return result.astimezone(UTC)


def _private_path(root: Path, path: Path, *, label: str) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        probe = path
        while probe != resolved_root and probe != probe.parent:
            if probe.is_symlink():
                raise OSError
            probe = probe.parent
        if path.is_symlink() or not path.is_file():
            raise OSError
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        raise ValueOverlayError(
            f"The private {label} is missing or outside the snapshot store."
        ) from None
    return resolved_path


def _write_private_immutable(root: Path, target: Path, data: bytes) -> Path:
    try:
        parent = target.parent
        while parent != root and parent != parent.parent:
            if parent.is_symlink():
                raise OSError
            parent = parent.parent
        if parent != root:
            raise OSError
        if target.is_symlink():
            raise OSError
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with suppress(OSError):
            target.parent.chmod(0o700)
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        with suppress(OSError):
            target.chmod(0o600)
        return target
    except FileExistsError:
        try:
            existing = _private_path(root, target, label="overlay artifact").read_bytes()
        except (OSError, ValueOverlayError):
            raise ValueOverlayError(
                "The existing immutable overlay artifact cannot be verified."
            ) from None
        if existing != data:
            raise ValueOverlayError(
                "An immutable overlay artifact already exists with other content."
            ) from None
        return target
    except OSError:
        raise ValueOverlayError("The private overlay artifact could not be written.") from None


def _snapshot_workbook(store: SnapshotStore, run_id: str) -> tuple[dict[str, Any], Workbook]:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueOverlayError("Use the exact 32-character portfolio acquisition run ID.")
    try:
        manifest = store.manifest(run_id)
    except WorkbookSourceError as error:
        raise ValueOverlayError("The selected private portfolio snapshot was not found.") from error
    if (
        manifest.get("run_id") != run_id
        or manifest.get("profile") != PORTFOLIO_PROFILE.key
        or manifest.get("contract_version") != PORTFOLIO_PROFILE.contract_version
        or manifest.get("expected_filename") != PORTFOLIO_PROFILE.expected_filename
        or manifest.get("status") not in {"ACQUIRED_REVIEW_REQUIRED", "ACQUIRED"}
    ):
        raise ValueOverlayError("The selected run is not the expected frozen portfolio snapshot.")
    artifact_sha = manifest.get("artifact_sha256")
    semantic_sha = manifest.get("semantic_sha256")
    if not isinstance(artifact_sha, str) or not _SHA256.fullmatch(artifact_sha):
        raise ValueOverlayError("The frozen portfolio artifact hash is invalid.")
    if (
        manifest.get("semantic_fingerprint_version") != SEMANTIC_FINGERPRINT_VERSION
        or not isinstance(semantic_sha, str)
        or not _SHA256.fullmatch(semantic_sha)
    ):
        raise ValueOverlayError("The frozen portfolio semantic fingerprint is invalid.")
    blob_name = manifest.get("blob_path")
    if not isinstance(blob_name, str):
        raise ValueOverlayError("The frozen portfolio snapshot has no content-addressed artifact.")
    relative = Path(blob_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueOverlayError("The frozen portfolio blob path is unsafe.")
    try:
        blob = _private_path(store.root, store.root / relative, label="workbook snapshot")
        data = blob.read_bytes()
    except OSError:
        raise ValueOverlayError("The frozen portfolio artifact could not be read.") from None
    if _sha256(data) != artifact_sha:
        raise ValueOverlayError("The frozen portfolio artifact failed its SHA-256 check.")
    try:
        inventory = inspect_workbook(data, PORTFOLIO_PROFILE)
        workbook = Workbook.read_bytes(data, lambda _name: True)
        actual_semantic_sha, _diagnostics = semantic_fingerprint(workbook)
    except (OSError, ValueError, WorkbookSourceError):
        raise ValueOverlayError(
            "The frozen portfolio workbook failed its source contract."
        ) from None
    if inventory.schema_fingerprint != manifest.get("schema_fingerprint"):
        raise ValueOverlayError("The frozen portfolio schema fingerprint changed.")
    if actual_semantic_sha != semantic_sha:
        raise ValueOverlayError("The frozen portfolio semantic fingerprint changed.")
    return manifest, workbook


def _canonical_bootstrap_source_fingerprint(workbook: Workbook) -> str:
    definitions = _validation_plan(workbook, "canonical-bootstrap")["definitions"]
    fingerprint = compare_semantic_values(
        workbook,
        {},
        number_formats={},
        definitions=definitions,
    )["snapshot_semantic_sha256"]
    if not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint):
        raise ValueOverlayError("The frozen canonical-bootstrap source fingerprint is invalid.")
    return fingerprint


def _comparison_report(
    store: SnapshotStore, run_id: str, expected_sha256: str | None = None
) -> tuple[dict[str, Any], str]:
    directory = store.root / "value-comparisons"
    if directory.is_symlink() or not directory.is_dir():
        raise ValueOverlayError("The private live-comparison evidence directory is unavailable.")
    reports: list[tuple[dict[str, Any], str, datetime, datetime | None]] = []
    for path in directory.glob(f"{run_id}-*.json"):
        try:
            resolved = _private_path(store.root, path, label="comparison evidence")
            raw = resolved.read_bytes()
            digest = _sha256(raw)
            report = json.loads(raw)
            if not isinstance(report, dict):
                raise ValueOverlayError("A private comparison report for this snapshot is invalid.")
            if report.get("run_id") != run_id:
                if (
                    report.get("snapshot_run_id") == run_id
                    and "source_report_version" in report
                    and "source_comparison_contract_version" in report
                ):
                    # The private analysis ledger shares this directory but is not a
                    # comparator attempt and cannot authorize an overlay.
                    continue
                raise ValueOverlayError("A private comparison report for this snapshot is invalid.")
            contract_version = report.get("comparison_contract_version")
            version_match = re.fullmatch(
                r"portfolio-live-value-comparison-v(\d+)",
                contract_version if isinstance(contract_version, str) else "",
            )
            if version_match is None:
                report_version = report.get("report_version")
                if isinstance(report_version, int) and report_version < 5:
                    continue
                raise ValueOverlayError("A comparison report uses an unknown contract version.")
            if int(version_match.group(1)) < 5:
                # Older comparison contracts cannot authorize an overlay and predate the
                # timestamp fence. They are retained as historical evidence only.
                continue
            started = _parse_timestamp(report.get("comparison_started_at_utc"), "start")
            completed_value = report.get("comparison_completed_at_utc")
            completed = (
                _parse_timestamp(completed_value, "completion")
                if completed_value is not None
                else None
            )
            if completed is not None and completed < started:
                raise ValueOverlayError("The comparison timestamps are out of order.")
            reports.append((report, digest, started, completed))
        except (OSError, json.JSONDecodeError, ValueOverlayError) as error:
            raise ValueOverlayError(
                "A comparison report for this snapshot is unreadable or lacks a valid timestamp."
            ) from error
    if not reports:
        raise ValueOverlayError(
            "A timestamped, successful canonical-bootstrap comparison is required."
        )
    attempts: dict[str, list[tuple[dict[str, Any], str, datetime, datetime | None]]] = {}
    for item in reports:
        attempt_id = item[0].get("comparison_attempt_id")
        if attempt_id is None:
            attempt_id = f"report:{item[1]}"
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueOverlayError("The comparison attempt identity is invalid.")
        attempts.setdefault(attempt_id, []).append(item)
    latest_attempts: list[tuple[dict[str, Any], str, datetime, datetime | None]] = []
    for attempt_reports in attempts.values():
        starts = {item[2] for item in attempt_reports}
        if len(starts) != 1:
            raise ValueOverlayError("Comparison attempt timestamps are inconsistent.")
        completed_reports = [item for item in attempt_reports if item[3] is not None]
        if len(completed_reports) > 1:
            raise ValueOverlayError("A comparison attempt has multiple completion reports.")
        if completed_reports:
            latest_attempts.append(completed_reports[0])
        else:
            start_report = next(
                (
                    item
                    for item in attempt_reports
                    if item[0].get("status") == "COMPARISON_ATTEMPT_STARTED"
                ),
                None,
            )
            if start_report is None:
                raise ValueOverlayError("A comparison attempt has no completion timestamp.")
            latest_attempts.append(start_report)
    latest_attempts.sort(key=lambda item: item[2])
    if len(latest_attempts) > 1 and latest_attempts[-1][2] == latest_attempts[-2][2]:
        raise ValueOverlayError("The latest comparison attempt timestamp is ambiguous.")
    latest, latest_sha256, _started, completed = latest_attempts[-1]
    if completed is None:
        raise ValueOverlayError("The latest comparison attempt did not complete.")
    if latest.get("comparison_contract_version") != COMPARISON_CONTRACT_VERSION:
        raise ValueOverlayError("The latest comparison uses an unsupported contract version.")
    selected_attempt_id = latest.get("comparison_attempt_id")
    selected_attempt = (
        attempts.get(selected_attempt_id, []) if isinstance(selected_attempt_id, str) else []
    )
    start_records = [
        item for item in selected_attempt if item[0].get("status") == "COMPARISON_ATTEMPT_STARTED"
    ]
    if len(start_records) > 1:
        raise ValueOverlayError("The comparison attempt has multiple durable start records.")
    paired_start, paired_start_sha256 = (
        (start_records[0][0], start_records[0][1]) if start_records else (None, None)
    )
    scope, scope_verification = _verified_comparison_scope(
        latest,
        paired_start=paired_start,
        paired_start_sha256=paired_start_sha256,
    )
    if scope != "canonical-bootstrap":
        raise ValueOverlayError("The latest comparison did not validate canonical-bootstrap scope.")
    if latest.get("status") != "COMPARED":
        raise ValueOverlayError("The latest comparison did not complete successfully.")
    if expected_sha256 is not None and latest_sha256 != expected_sha256:
        raise ValueOverlayError("A newer comparison superseded the overlay candidate.")
    verified_report = dict(latest)
    verified_report["_scope_verification"] = scope_verification
    return verified_report, latest_sha256


def _validated_comparison(
    manifest: dict[str, Any], report: dict[str, Any]
) -> tuple[datetime, datetime]:
    if (
        report.get("report_version") != 5
        or report.get("consistency_result") != "COMPARED"
        or report.get("source_metadata_matches_snapshot") is not True
        or report.get("source_modified_at_matches_snapshot") is not True
        or report.get("live_source_stable_during_comparison") is not True
        or report.get("live_values_stable_across_reads") is not True
        or report.get("live_formula_definitions_stable_across_reads") is not True
        or report.get("missing_required_sheets")
    ):
        raise ValueOverlayError("The live comparison did not pass its complete consistency fence.")
    if (
        report.get("snapshot_artifact_sha256") != manifest.get("artifact_sha256")
        or report.get("snapshot_semantic_fingerprint_version")
        != manifest.get("semantic_fingerprint_version")
        or report.get("source_identity_sha256") != manifest.get("source_identity_sha256")
        or report.get("snapshot_source_modified_at") != manifest.get("source_modified_at")
        or report.get("snapshot_source_revision") != manifest.get("source_revision")
    ):
        raise ValueOverlayError("Live comparison metadata does not match the frozen snapshot.")
    expected_revision = manifest.get("source_revision")
    revision_match = report.get("source_revision_matches_snapshot")
    if (expected_revision is None and revision_match is not None) or (
        expected_revision is not None and revision_match is not True
    ):
        raise ValueOverlayError("The comparison revision fence is inconsistent with the snapshot.")
    started = _parse_timestamp(report.get("comparison_started_at_utc"), "start")
    completed = _parse_timestamp(report.get("comparison_completed_at_utc"), "completion")
    if completed < started:
        raise ValueOverlayError("The live comparison timestamps are out of order.")
    return started, completed


def _build_candidate(
    manifest: dict[str, Any],
    workbook: Workbook,
    report: dict[str, Any],
    report_sha256: str,
    validated_at_utc: str,
) -> dict[str, Any]:
    started, completed = _validated_comparison(manifest, report)
    scoped_semantic_sha256 = _canonical_bootstrap_source_fingerprint(workbook)
    if report.get("snapshot_semantic_sha256") != scoped_semantic_sha256:
        raise ValueOverlayError(
            "The comparison's canonical-bootstrap values do not match the frozen snapshot."
        )
    definitions = {(item.sheet, item.address): item for item in importer_value_cells(workbook)}
    formula_map = _source_formula_map(workbook)
    ledger = report.get("exception_ledger")
    records = ledger.get("records") if isinstance(ledger, dict) else None
    if not isinstance(records, list):
        raise ValueOverlayError(
            "The comparison does not retain the required private cell evidence."
        )
    unresolved_importer_formulas = []
    for item in records:
        if (
            not isinstance(item, dict)
            or item.get("importer_semantic_relation")
            != "CURRENT_VALUE_MATCH_FORMULA_TEXT_DIFFERENCE_UNRESOLVED"
        ):
            continue
        sheet = item.get("sheet")
        address = item.get("cell")
        definition = (
            definitions.get((sheet, address))
            if isinstance(sheet, str) and isinstance(address, str)
            else None
        )
        if definition is None:
            raise ValueOverlayError(
                "An unresolved formula could not be mapped to the current import contract."
            )
        if _importer_cell_is_consumed(workbook, definition):
            unresolved_importer_formulas.append(item)
    if unresolved_importer_formulas:
        raise ValueOverlayError(
            "An importer-consumed formula difference remains unresolved; no overlay is safe."
        )
    changed = [
        item
        for item in records
        if isinstance(item, dict) and item.get("canonical_value_changed") is True
    ]
    if report.get("canonical_value_changed_count") != len(changed):
        raise ValueOverlayError(
            "The comparison's changed-cell count does not match its evidence ledger."
        )
    if not changed:
        raise ValueOverlayError("The comparison has no importer-value differences to review.")

    cells: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in changed:
        sheet = record.get("sheet")
        address = record.get("cell")
        if not isinstance(sheet, str) or not isinstance(address, str):
            raise ValueOverlayError("The comparison contains an invalid source cell identity.")
        key = (sheet, address)
        if key in seen:
            raise ValueOverlayError("The comparison contains a duplicate or invalid source cell.")
        seen.add(key)
        definition = definitions.get(key)
        if definition is None:
            raise ValueOverlayError("A changed cell is outside the current importer contract.")
        target_field, transformation = importer_field_semantics(definition)
        if (
            target_field not in _ALLOWED_TARGET_FIELDS
            or record.get("target_field") != target_field
            or record.get("transformation") != transformation
            or record.get("source_role") != "spreadsheet_derived_value"
            or record.get("classification") != "STALE_XLSX_CACHE_CANDIDATE"
            or record.get("importer_semantic_relation") != "IMPORTER_VALUE_DIFFERENCE"
            or record.get("source_state") != "VALUE"
            or record.get("live_state") != "VALUE"
            or record.get("source_type") != record.get("live_type")
            or record.get("live_type") != "number"
        ):
            raise ValueOverlayError(
                "A changed cell does not satisfy the reviewed overlay contract."
            )
        source_cell = workbook.cell(sheet, address)
        source_evidence = record.get("source_evidence")
        live_evidence = record.get("live_evidence")
        if not isinstance(source_evidence, dict) or not isinstance(live_evidence, dict):
            raise ValueOverlayError("The comparison cell evidence is incomplete.")
        source_value = source_cell.value
        if (
            source_value is None
            or source_value != source_evidence.get("value_text")
            or source_cell.kind not in {None, "n"}
        ):
            raise ValueOverlayError("A cached source value differs from the frozen workbook.")
        effective_value = live_evidence.get("effective_value")
        live_value = (
            effective_value.get("numberValue") if isinstance(effective_value, dict) else None
        )
        if not isinstance(live_value, str):
            raise ValueOverlayError("The live comparison value is not exact decimal text.")
        try:
            source_decimal = Decimal(source_value)
            live_decimal = Decimal(live_value)
        except InvalidOperation as error:
            raise ValueOverlayError("A changed importer value is not a valid decimal.") from error
        if (
            not source_decimal.is_finite()
            or not live_decimal.is_finite()
            or source_decimal == live_decimal
        ):
            raise ValueOverlayError("A changed importer value failed exact decimal validation.")
        source_formula_raw, formula_resolution = formula_map.get(key, (None, "MISSING"))
        live_formula_raw = live_evidence.get("formula_text_for_comparison")
        source_formula = _normalize_formula(source_formula_raw)
        live_formula = _normalize_formula(live_formula_raw)
        if (
            formula_resolution not in {"DIRECT", "SHARED_ANCHOR", "SHARED_TRANSLATED"}
            or not isinstance(source_formula, str)
            or not source_formula
            or not isinstance(live_formula, str)
            or source_formula != live_formula
        ):
            raise ValueOverlayError(
                "The source and live formula definitions are not proven identical."
            )
        source_hash = _sha256(source_formula.encode("utf-8"))
        live_hash = _sha256(live_formula.encode("utf-8"))
        if (
            record.get("source_formula_sha256") != source_hash
            or record.get("live_formula_sha256") != live_hash
        ):
            raise ValueOverlayError("Formula evidence hashes do not match the frozen source.")
        cells.append(
            {
                "sheet": sheet,
                "cell": address,
                "target_field": target_field,
                "transformation": transformation,
                "source_role": record["source_role"],
                "source_value": source_value,
                "source_type": record["source_type"],
                "live_value": live_value,
                "live_type": record["live_type"],
                "source_formula": source_formula,
                "source_formula_raw": source_cell.formula,
                "source_formula_resolution": formula_resolution,
                "live_formula": live_formula,
                "formula_sha256": source_hash,
            }
        )

    cells.sort(key=lambda item: (item["sheet"], item["cell"]))
    snapshot = {
        "acquisition_run_id": manifest["run_id"],
        "artifact_sha256": manifest["artifact_sha256"],
        "semantic_fingerprint_version": manifest["semantic_fingerprint_version"],
        "semantic_sha256": manifest["semantic_sha256"],
        "source_identity_sha256": manifest["source_identity_sha256"],
        "source_modified_at": manifest["source_modified_at"],
        "source_revision": manifest.get("source_revision"),
        "canonical_bootstrap_semantic_sha256": scoped_semantic_sha256,
    }
    comparison = {
        "contract_version": report["comparison_contract_version"],
        "report_version": report["report_version"],
        "report_sha256": report_sha256,
        "scope": "canonical-bootstrap",
        "scope_verification": report.get("_scope_verification", {"basis": "explicit_report_scope"}),
        "consistency_result": report["consistency_result"],
        "source_revision_available": manifest.get("source_revision") is not None,
        "comparison_started_at_utc": started.isoformat(),
        "comparison_completed_at_utc": completed.isoformat(),
        "live_source_observation_time": "bounded-comparison-window",
    }
    evidence = {"snapshot": snapshot, "comparison": comparison, "cells": cells}
    return {
        "format_version": CANDIDATE_FORMAT_VERSION,
        "status": "REVIEW_REQUIRED",
        "evidence_fingerprint": _sha256(_canonical_bytes(evidence)),
        "snapshot": snapshot,
        "comparison": comparison,
        "validation": {"validated_at_utc": validated_at_utc},
        "cells": cells,
    }


def _normalize_formula(formula: Any) -> str | None:
    if not isinstance(formula, str):
        return None
    return formula.strip().removeprefix("=").strip()


def create_candidate(store: SnapshotStore, run_id: str) -> tuple[Path, str, dict[str, Any]]:
    manifest, workbook = _snapshot_workbook(store, run_id)
    report, report_sha = _comparison_report(store, run_id)
    validated_at = datetime.now(UTC).isoformat()
    candidate = _build_candidate(manifest, workbook, report, report_sha, validated_at)
    stable_key = candidate["evidence_fingerprint"]
    target = store.root / "value-overlays" / f"{run_id}-candidate-{stable_key}.json"
    if target.exists():
        existing_path = _private_path(store.root, target, label="overlay candidate")
        try:
            existing = json.loads(existing_path.read_bytes())
            prior_validated_at = existing.get("validation", {}).get("validated_at_utc")
            _parse_timestamp(prior_validated_at, "overlay validation")
            expected = _build_candidate(manifest, workbook, report, report_sha, prior_validated_at)
        except (AttributeError, json.JSONDecodeError, ValueError):
            raise ValueOverlayError(
                "The existing immutable overlay candidate is invalid."
            ) from None
        if existing != expected:
            raise ValueOverlayError("The existing immutable overlay candidate failed verification.")
        return existing_path, _sha256(existing_path.read_bytes()), existing
    candidate_path = _write_private_immutable(store.root, target, _canonical_bytes(candidate))
    digest = _sha256(candidate_path.read_bytes())
    return candidate_path, digest, candidate


def _load_candidate(
    store: SnapshotStore, run_id: str, expected_sha256: str
) -> tuple[Path, dict[str, Any]]:
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueOverlayError(
            "The candidate SHA-256 must be 64 lowercase hexadecimal characters."
        )
    directory = store.root / "value-overlays"
    if directory.is_symlink() or not directory.is_dir():
        raise ValueOverlayError("The private overlay candidate directory is unavailable.")
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in directory.glob(f"{run_id}-candidate-*.json"):
        resolved = _private_path(store.root, path, label="overlay candidate")
        raw = resolved.read_bytes()
        if _sha256(raw) != expected_sha256:
            continue
        try:
            candidate = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueOverlayError("The overlay candidate is not valid JSON.") from None
        if isinstance(candidate, dict):
            matches.append((resolved, candidate))
    if len(matches) != 1:
        raise ValueOverlayError("The exact private overlay candidate was not found.")
    return matches[0]


def _validate_candidate(store: SnapshotStore, run_id: str, candidate: dict[str, Any]) -> Workbook:
    if (
        candidate.get("format_version") != CANDIDATE_FORMAT_VERSION
        or candidate.get("status") != "REVIEW_REQUIRED"
        or not isinstance(candidate.get("snapshot"), dict)
        or candidate["snapshot"].get("acquisition_run_id") != run_id
    ):
        raise ValueOverlayError("The overlay candidate has an unsupported contract or snapshot.")
    manifest, workbook = _snapshot_workbook(store, run_id)
    report_sha = candidate.get("comparison", {}).get("report_sha256")
    if not isinstance(report_sha, str) or not _SHA256.fullmatch(report_sha):
        raise ValueOverlayError("The overlay candidate does not identify its private comparison.")
    report, exact_report_sha = _comparison_report(store, run_id, report_sha)
    validated_at = candidate.get("validation", {}).get("validated_at_utc")
    _parse_timestamp(validated_at, "overlay validation")
    expected = _build_candidate(manifest, workbook, report, exact_report_sha, validated_at)
    if expected != candidate:
        raise ValueOverlayError(
            "The candidate differs from its frozen workbook comparison evidence."
        )
    return workbook


def approve_candidate(
    store: SnapshotStore,
    run_id: str,
    candidate_sha256: str,
    *,
    reviewed_by: str,
    review_note: str,
    confirm_overlay_values: bool,
) -> tuple[Path, str, dict[str, Any]]:
    if not confirm_overlay_values:
        raise ValueOverlayError("Explicit --confirm-overlay-values review is required.")
    reviewer = reviewed_by.strip()
    note = review_note.strip()
    if not reviewer or len(reviewer) > 200 or not note or len(note) > 2000:
        raise ValueOverlayError("A reviewer identity and bounded review note are required.")
    candidate_path, candidate = _load_candidate(store, run_id, candidate_sha256)
    _validate_candidate(store, run_id, candidate)
    candidate_raw = candidate_path.read_bytes()
    approval = {
        "format_version": OVERLAY_FORMAT_VERSION,
        "status": "APPROVED",
        "candidate_sha256": _sha256(candidate_raw),
        "candidate": candidate,
        "approval": {
            "reviewed_by": reviewer,
            "reviewed_at_utc": datetime.now(UTC).isoformat(),
            "review_note": note,
            "confirmation": APPROVAL_CONFIRMATION,
        },
    }
    stable_name = f"{run_id}-approved-{candidate_sha256}.json"
    target = store.root / "value-overlays" / "approved" / stable_name
    if target.exists():
        existing_path = _private_path(store.root, target, label="approval artifact")
        try:
            existing = json.loads(existing_path.read_bytes())
        except json.JSONDecodeError:
            raise ValueOverlayError(
                "The existing immutable approval artifact is invalid."
            ) from None
        existing_approval = existing.get("approval", {}) if isinstance(existing, dict) else {}
        if not isinstance(existing, dict):
            raise ValueOverlayError("The existing immutable approval artifact is invalid.")
        if (
            existing.get("candidate_sha256") == candidate_sha256
            and existing_approval.get("reviewed_by") == reviewer
            and existing_approval.get("review_note") == note
            and existing_approval.get("confirmation") == APPROVAL_CONFIRMATION
        ):
            return existing_path, _sha256(existing_path.read_bytes()), existing
        raise ValueOverlayError("This candidate already has a different immutable approval record.")
    path = _write_private_immutable(store.root, target, _canonical_bytes(approval))
    return path, _sha256(path.read_bytes()), approval


def apply_approved_overlay(
    store: SnapshotStore,
    *,
    path: Path,
    expected_sha256: str,
    acquisition_run_id: str,
    artifact_sha256: str,
    semantic_sha256: str | None,
    workbook: Workbook,
) -> dict[str, Any]:
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueOverlayError(
            "The approved overlay SHA-256 must be 64 lowercase hexadecimal characters."
        )
    resolved = _private_path(store.root, path, label="approved overlay")
    raw = resolved.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise ValueOverlayError("The approved overlay failed its SHA-256 check.")
    try:
        approved = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueOverlayError("The approved overlay is not valid JSON.") from None
    if (
        not isinstance(approved, dict)
        or approved.get("format_version") != OVERLAY_FORMAT_VERSION
        or approved.get("status") != "APPROVED"
        or not isinstance(approved.get("candidate"), dict)
        or not isinstance(approved.get("approval"), dict)
    ):
        raise ValueOverlayError("Only an explicitly approved overlay can be applied.")
    candidate = approved["candidate"]
    approval = approved["approval"]
    snapshot = candidate.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueOverlayError("The approved overlay snapshot identity is invalid.")
    candidate_sha = approved.get("candidate_sha256")
    if not isinstance(candidate_sha, str) or not _SHA256.fullmatch(candidate_sha):
        raise ValueOverlayError("The approved overlay candidate identity is invalid.")
    if _sha256(_canonical_bytes(candidate)) != candidate_sha:
        raise ValueOverlayError("The approved candidate content no longer matches its identity.")
    if (
        snapshot.get("acquisition_run_id") != acquisition_run_id
        or snapshot.get("artifact_sha256") != artifact_sha256
        or snapshot.get("semantic_sha256") != semantic_sha256
    ):
        raise ValueOverlayError("The approved overlay belongs to a different frozen snapshot.")
    reviewer = approval.get("reviewed_by")
    note = approval.get("review_note")
    if (
        approved.get("approval", {}).get("confirmation") != APPROVAL_CONFIRMATION
        or not isinstance(reviewer, str)
        or not reviewer.strip()
        or not isinstance(note, str)
        or not note.strip()
    ):
        raise ValueOverlayError("The overlay approval record is incomplete.")
    _parse_timestamp(approval.get("reviewed_at_utc"), "approval")
    _validate_candidate(store, acquisition_run_id, candidate)
    source_formulas = _source_formula_map(workbook)
    for item in candidate["cells"]:
        sheet = item["sheet"]
        address = item["cell"]
        original = workbook.cell(sheet, address)
        if (
            original.value != item["source_value"]
            or original.kind not in {None, "n"}
            or _normalize_formula(source_formulas.get((sheet, address), (None, ""))[0])
            != item["source_formula"]
        ):
            raise ValueOverlayError(
                "The approved overlay no longer matches the parsed source cell."
            )
        workbook.sheets.setdefault(sheet, {})[address] = replace(
            original,
            value=item["live_value"],
            value_before_overlay=original.value,
        )
    workbook.value_overlay_sha256 = expected_sha256
    workbook.value_overlay_candidate_sha256 = candidate_sha
    workbook.value_overlay_reviewed_by = reviewer
    workbook.value_overlay_reviewed_at = approval["reviewed_at_utc"]
    workbook.value_overlay_comparison_completed_at = candidate["comparison"][
        "comparison_completed_at_utc"
    ]
    return {
        "status": "APPROVED",
        "sha256": expected_sha256,
        "candidate_sha256": candidate_sha,
        "reviewed_by": reviewer,
        "reviewed_at": approval["reviewed_at_utc"],
        "validated_at": candidate["validation"]["validated_at_utc"],
        "comparison_started_at": candidate["comparison"]["comparison_started_at_utc"],
        "comparison_completed_at": candidate["comparison"]["comparison_completed_at_utc"],
        "cell_count": len(candidate["cells"]),
        "target_field_counts": {
            key: sum(item["target_field"] == key for item in candidate["cells"])
            for key in sorted(_ALLOWED_TARGET_FIELDS)
            if any(item["target_field"] == key for item in candidate["cells"])
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    candidate = commands.add_parser("candidate")
    candidate.add_argument("--store", type=Path, required=True)
    candidate.add_argument("--portfolio-run", required=True)
    approval = commands.add_parser("approve")
    approval.add_argument("--store", type=Path, required=True)
    approval.add_argument("--portfolio-run", required=True)
    approval.add_argument("--candidate-sha256", required=True)
    approval.add_argument("--reviewed-by", required=True)
    approval.add_argument("--review-note", required=True)
    approval.add_argument("--confirm-overlay-values", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = SnapshotStore(args.store)
        if args.command == "candidate":
            path, digest, candidate = create_candidate(store, args.portfolio_run)
            summary = {
                "status": "REVIEW_REQUIRED",
                "candidate_sha256": digest,
                "artifact": path.name,
                "cell_count": len(candidate["cells"]),
                "target_field_counts": {
                    key: sum(item["target_field"] == key for item in candidate["cells"])
                    for key in sorted(_ALLOWED_TARGET_FIELDS)
                    if any(item["target_field"] == key for item in candidate["cells"])
                },
            }
        else:
            path, digest, approved = approve_candidate(
                store,
                args.portfolio_run,
                args.candidate_sha256,
                reviewed_by=args.reviewed_by,
                review_note=args.review_note,
                confirm_overlay_values=args.confirm_overlay_values,
            )
            summary = {
                "status": "APPROVED_LOCAL_OVERLAY",
                "overlay_sha256": digest,
                "artifact": path.name,
                "candidate_sha256": approved["candidate_sha256"],
                "cell_count": len(approved["candidate"]["cells"]),
            }
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (OSError, ValueOverlayError, WorkbookSourceError, ValueError) as error:
        print(
            json.dumps({"status": "BLOCKED", "message": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
