"""Canonical, review-gated values captured from a native Google Sheets workbook."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from portfolio_api.legacy_import import Cell, Workbook
from portfolio_api.workbook_semantics import (
    SEMANTIC_FINGERPRINT_VERSION,
    ImporterValueCell,
    SemanticMode,
    importer_empty_value_policy,
    importer_field_semantics,
    importer_source_value_policy,
    importer_value_cells,
)
from portfolio_api.workbook_sources import (
    GOOGLE_SHEET_MIME,
    PORTFOLIO_PROFILE,
    SnapshotStore,
    WorkbookSourceError,
)
from portfolio_api.workbook_value_validation import _cell_position, _importer_cell_is_consumed

SOURCE_VALUE_BUNDLE_VERSION = "native-google-sheets-source-values-v2"
SOURCE_VALUE_APPROVAL_VERSION = "native-google-sheets-source-approval-v2"
SOURCE_AUTHORITY_CONTRACT_VERSION = "portfolio-import-source-authority-v2"
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_VALUE_TYPES = {
    "text": "stringValue",
    "ticker": "stringValue",
    "currency": "stringValue",
    "label": "stringValue",
    "timestamp": "stringValue",
    "decimal": "numberValue",
    "percent_decimal": "numberValue",
    "excel_date": "numberValue",
}


class SourceValueBundleError(ValueError):
    """Sanitized failure for capture, approval, or application of a source-value bundle."""


def _canonical_bytes(value: Any) -> bytes:
    def exact(item: Any) -> Any:
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise SourceValueBundleError("A non-finite numeric source value is unsupported.")
            return format(item, "f")
        if isinstance(item, float):
            raise SourceValueBundleError("Binary floating-point source values are forbidden.")
        if isinstance(item, dict):
            return {str(key): exact(nested) for key, nested in item.items()}
        if isinstance(item, (list, tuple)):
            return [exact(nested) for nested in item]
        return item

    return json.dumps(
        exact(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _private_file(root: Path, path: Path, label: str) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        probe = path
        while probe != resolved_root and probe != probe.parent:
            if probe.is_symlink():
                raise OSError
            probe = probe.parent
        if probe != resolved_root or path.is_symlink() or not path.is_file():
            raise OSError
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
        return resolved
    except (OSError, RuntimeError, ValueError):
        raise SourceValueBundleError(f"The private {label} is missing or unsafe.") from None


def _write_immutable(root: Path, target: Path, payload: bytes, *, label: str) -> Path:
    try:
        parent = target.parent
        while parent != root and parent != parent.parent:
            if parent.is_symlink():
                raise OSError
            parent = parent.parent
        if parent != root or target.is_symlink():
            raise OSError
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with suppress(OSError):
            target.parent.chmod(0o700)
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        with suppress(OSError):
            target.chmod(0o600)
        return target
    except FileExistsError:
        try:
            existing = _private_file(root, target, label).read_bytes()
        except (OSError, SourceValueBundleError):
            raise SourceValueBundleError(
                f"The existing immutable {label} cannot be verified."
            ) from None
        if existing != payload:
            raise SourceValueBundleError(
                f"An immutable {label} already exists with other content."
            ) from None
        return target
    except OSError:
        raise SourceValueBundleError(f"The private {label} could not be written.") from None


def _bundle_path(store: SnapshotStore, run_id: str, bundle_sha256: str) -> Path:
    if not _RUN_ID.fullmatch(run_id) or not _SHA256.fullmatch(bundle_sha256):
        raise SourceValueBundleError("The source bundle identity is invalid.")
    return store.root / "source-value-bundles" / run_id / f"{bundle_sha256}.json"


def _read_bundle(
    store: SnapshotStore, run_id: str, bundle_sha256: str
) -> tuple[Path, dict[str, Any]]:
    path = _private_file(
        store.root,
        _bundle_path(store, run_id, bundle_sha256),
        "source-value bundle",
    )
    raw = path.read_bytes()
    if _sha256(raw) != bundle_sha256:
        raise SourceValueBundleError("The source-value bundle failed its content hash check.")
    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError:
        raise SourceValueBundleError("The source-value bundle is not valid JSON.") from None
    if not isinstance(bundle, dict):
        raise SourceValueBundleError("The source-value bundle contract is invalid.")
    if (
        bundle.get("contract_version") != SOURCE_VALUE_BUNDLE_VERSION
        or bundle.get("source_acquisition_run_id") != run_id
        or bundle.get("scope") != "canonical-bootstrap"
        or bundle.get("source_mime_type") != GOOGLE_SHEET_MIME
        or bundle.get("source_authority_contract_version") != SOURCE_AUTHORITY_CONTRACT_VERSION
        or bundle.get("source_profile") != PORTFOLIO_PROFILE.key
        or bundle.get("source_contract_version") != PORTFOLIO_PROFILE.contract_version
        or bundle.get("source_semantic_fingerprint_version") != SEMANTIC_FINGERPRINT_VERSION
    ):
        raise SourceValueBundleError("The source-value bundle uses an unsupported contract.")
    return path, bundle


def _approval_directory(store: SnapshotStore) -> Path:
    directory = store.root / "source-value-approvals"
    if directory.is_symlink():
        raise SourceValueBundleError("The private source approval directory is unsafe.")
    return directory


def _read_approval(
    store: SnapshotStore,
    run_id: str,
    bundle_sha256: str,
    approval_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    if not _SHA256.fullmatch(approval_sha256):
        raise SourceValueBundleError("The source-value approval identity is invalid.")
    directory = _approval_directory(store)
    matches: list[tuple[Path, dict[str, Any]]] = []
    for candidate in directory.glob(f"{bundle_sha256}-*.json"):
        path = _private_file(store.root, candidate, "source-value approval")
        raw = path.read_bytes()
        if _sha256(raw) != approval_sha256:
            continue
        try:
            receipt = json.loads(raw)
        except json.JSONDecodeError:
            raise SourceValueBundleError("The source-value approval is not valid JSON.") from None
        if isinstance(receipt, dict):
            matches.append((path, receipt))
    if len(matches) != 1:
        raise SourceValueBundleError("The exact source-value approval was not found.")
    path, receipt = matches[0]
    if (
        receipt.get("contract_version") != SOURCE_VALUE_APPROVAL_VERSION
        or receipt.get("source_acquisition_run_id") != run_id
        or receipt.get("source_value_bundle_sha256") != bundle_sha256
        or receipt.get("status") != "APPROVED_FOR_CANONICAL_IMPORT"
        or receipt.get("confirmation", {}).get("sheets_values_authoritative") is not True
        or receipt.get("confirmation", {}).get("schema_acceptance_included") is not False
        or receipt.get("confirmation", {}).get("investment_decisions_inferred") is not False
    ):
        raise SourceValueBundleError("The source-value approval does not match this bundle.")
    _bundle_path, bundle = _read_bundle(store, run_id, bundle_sha256)
    quality = bundle.get("quality")
    confirmation = receipt.get("confirmation")
    if not isinstance(quality, dict) or not isinstance(confirmation, dict):
        raise SourceValueBundleError("The source-value approval evidence is incomplete.")
    if (
        receipt.get("source_artifact_sha256") != bundle.get("source_artifact_sha256")
        or receipt.get("source_schema_fingerprint") != bundle.get("source_schema_fingerprint")
        or receipt.get("source_semantic_sha256") != bundle.get("source_semantic_sha256")
        or receipt.get("source_identity_sha256") != bundle.get("source_identity_sha256")
        or receipt.get("source_revision") != bundle.get("source_revision")
        or receipt.get("source_modified_at") != bundle.get("source_modified_at")
        or receipt.get("source_checksum") != bundle.get("source_checksum")
        or (
            quality.get("xlsx_value_difference_count", 0)
            and confirmation.get("xlsx_value_differences_reviewed") is not True
        )
        or (
            quality.get("formula_definition_difference_count", 0)
            and confirmation.get(
                "formula_definition_differences_reviewed_without_equivalence_claim"
            )
            is not True
        )
        or (
            quality.get("price_feed_formula_definition_difference_count", 0)
            and confirmation.get("price_feed_formula_policy_reviewed_without_equivalence_claim")
            is not True
        )
    ):
        raise SourceValueBundleError("The source-value approval does not cover this evidence.")
    return path, receipt


def _source_type_mismatch(record: dict[str, Any]) -> str | None:
    mode = record.get("mode")
    if mode not in _EXPECTED_VALUE_TYPES:
        return "UNSUPPORTED_IMPORTER_VALUE_MODE"
    sheets = record.get("sheets", {})
    effective = sheets.get("effective_value")
    formula = sheets.get("formula_text")
    entered = sheets.get("user_entered_value")
    normalized_state = record.get("normalized", {}).get("authoritative_live", {}).get("state")
    if not isinstance(effective, dict) or not effective:
        if formula:
            return "LIVE_FORMULA_VALUE_UNAVAILABLE"
        if isinstance(entered, dict):
            variants = [
                key
                for key in ("numberValue", "stringValue", "boolValue", "formulaValue")
                if key in entered
            ]
            if len(variants) > 1:
                return "LIVE_ENTERED_VALUE_INVALID"
            if variants:
                if variants[0] == "stringValue" and entered.get("stringValue") == "":
                    if normalized_state != "EMPTY_STRING":
                        return "LIVE_EMPTY_STRING_STATE_MISMATCH"
                else:
                    return "LIVE_EFFECTIVE_VALUE_UNAVAILABLE"
        if normalized_state == "MISSING":
            return "LIVE_VALUE_MISSING_WITHIN_CONFIRMED_RANGE"
        if normalized_state in {"EMPTY_STRING", "FORMULA_EMPTY_STRING"}:
            return "LIVE_EMPTY_STRING_STATE_MISMATCH"
        return None
    variants = [
        key for key in ("numberValue", "stringValue", "boolValue", "errorValue") if key in effective
    ]
    if len(variants) != 1:
        return "LIVE_EFFECTIVE_VALUE_INVALID"
    if variants[0] == "errorValue":
        return "LIVE_EFFECTIVE_VALUE_ERROR"
    if normalized_state not in {"VALUE", "BLANK", "EMPTY_STRING", "FORMULA_EMPTY_STRING"}:
        return "LIVE_EFFECTIVE_VALUE_INVALID_FOR_IMPORTER_FIELD"
    if normalized_state in {"EMPTY_STRING", "FORMULA_EMPTY_STRING"}:
        if variants[0] == "stringValue" and effective.get("stringValue") == "":
            return None
        return "LIVE_EMPTY_STRING_STATE_MISMATCH"
    if normalized_state == "BLANK":
        return "LIVE_BLANK_STATE_HAS_EFFECTIVE_VALUE"
    expected = _EXPECTED_VALUE_TYPES[mode]
    if variants[0] != expected:
        return "LIVE_EFFECTIVE_VALUE_TYPE_MISMATCH"
    if variants[0] == "numberValue":
        value = effective["numberValue"]
        if not isinstance(value, str) or not value:
            return "LIVE_NUMERIC_VALUE_NOT_EXACT_TEXT"
        try:
            decimal_value = Decimal(value)
        except InvalidOperation:
            return "LIVE_NUMERIC_VALUE_INVALID"
        if not decimal_value.is_finite():
            return "LIVE_NUMERIC_VALUE_INVALID"
    elif not isinstance(effective.get("stringValue"), str):
        return "LIVE_STRING_VALUE_INVALID"
    elif effective.get("stringValue") == "" and normalized_state not in {
        "EMPTY_STRING",
        "FORMULA_EMPTY_STRING",
    }:
        return "LIVE_EMPTY_STRING_STATE_MISMATCH"
    return None


def _live_values_for_policy(
    records: list[dict[str, Any]],
) -> dict[str, dict[tuple[int, int], dict[str, Any]]]:
    """Build sibling-cell context from captured Sheets values, never XLSX caches."""
    result: dict[str, dict[tuple[int, int], dict[str, Any]]] = {}
    for record in records:
        sheet = record.get("sheet")
        address = record.get("cell")
        if not isinstance(sheet, str) or not isinstance(address, str):
            raise SourceValueBundleError("A source value has an invalid cell identity.")
        try:
            position = _cell_position(address)
        except ValueError:
            raise SourceValueBundleError("A source value has an invalid cell identity.") from None
        evidence = record.get("sheets")
        if not isinstance(evidence, dict):
            raise SourceValueBundleError("A source value has incomplete Sheets evidence.")
        result.setdefault(sheet, {})[position] = {
            "userEnteredValue": evidence.get("user_entered_value"),
            "effectiveValue": evidence.get("effective_value"),
        }
    return result


def capture_source_value_bundle(
    store: SnapshotStore,
    *,
    manifest: dict[str, Any],
    source_cells: list[dict[str, Any]],
    comparison: dict[str, Any],
    comparison_started_at_utc: str,
    comparison_completed_at_utc: str,
    consistency_protocol: str,
) -> dict[str, Any]:
    """Persist all consumed canonical-bootstrap values from the stable second Sheets read."""
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise SourceValueBundleError("The frozen source acquisition identity is invalid.")
    if manifest.get("source_mime_type") != GOOGLE_SHEET_MIME:
        raise SourceValueBundleError(
            "Canonical source bundles require a native Google spreadsheet."
        )
    consistency_checks = comparison.get("consistency_checks")
    if (
        comparison.get("consistency_result") != "COMPARED"
        or not isinstance(consistency_checks, dict)
        or any(
            consistency_checks.get(key) is not True
            for key in (
                "snapshot_metadata_matched_before_capture",
                "source_metadata_unchanged_before_and_after",
                "live_values_stable_across_two_reads",
                "live_formula_definitions_stable_across_two_reads",
                "live_source_cell_evidence_stable_across_two_reads",
                "required_importer_coordinates_covered_in_both_reads",
            )
        )
    ):
        raise SourceValueBundleError("The source comparison did not pass its consistency fence.")
    if comparison.get("scope") != "canonical-bootstrap":
        raise SourceValueBundleError("Only canonical-bootstrap values can form this bundle.")
    artifact_sha256 = manifest.get("artifact_sha256")
    semantic_sha256 = manifest.get("semantic_sha256")
    source_identity_sha256 = manifest.get("source_identity_sha256")
    schema_fingerprint = manifest.get("schema_fingerprint")
    if not all(
        isinstance(item, str) and _SHA256.fullmatch(item)
        for item in (artifact_sha256, semantic_sha256, source_identity_sha256, schema_fingerprint)
    ):
        raise SourceValueBundleError("The frozen source acquisition metadata is incomplete.")
    if (
        manifest.get("profile") != PORTFOLIO_PROFILE.key
        or manifest.get("contract_version") != PORTFOLIO_PROFILE.contract_version
        or manifest.get("semantic_fingerprint_version") != SEMANTIC_FINGERPRINT_VERSION
    ):
        raise SourceValueBundleError("The source acquisition uses an unsupported contract.")
    cells = list(source_cells)
    if not cells or any(item.get("api_coordinate_covered") is not True for item in cells):
        raise SourceValueBundleError(
            "A required importer coordinate is not covered by a confirmed Sheets range."
        )
    expected_cell_count = comparison.get("expected_importer_cell_count")
    if (
        not isinstance(expected_cell_count, int)
        or isinstance(expected_cell_count, bool)
        or expected_cell_count <= 0
        or len(cells) != expected_cell_count
    ):
        raise SourceValueBundleError(
            "The source bundle does not cover the complete importer scope."
        )
    if not isinstance(consistency_protocol, str) or not consistency_protocol.strip():
        raise SourceValueBundleError("The source consistency protocol is missing.")
    keys = [(item.get("sheet"), item.get("cell")) for item in cells]
    if len(keys) != len(set(keys)):
        raise SourceValueBundleError(
            "The canonical source bundle contains duplicate importer cells."
        )

    blocking: list[dict[str, str]] = []
    required_empty: list[dict[str, str]] = []
    classifications: dict[str, int] = {}
    cell_data_states: dict[str, int] = {}
    normalized_empty_states: dict[str, int] = {}
    empty_policy_counts: dict[str, int] = {}
    empty_state_by_sheet_field: dict[tuple[str, str, str, str, str], int] = {}
    formula_differences = 0
    xlsx_value_differences = 0
    price_feed_formula_differences = 0
    live_policy_values = _live_values_for_policy(cells)
    for item in cells:
        cell_state = str(item.get("cell_data_state", "UNKNOWN"))
        if cell_state not in {
            "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE",
            "EXPLICIT_EMPTY_CELL_DATA",
            "CELL_VALUE_DATA_PRESENT",
            "CELL_METADATA_ONLY",
        }:
            blocking.append(
                {
                    "sheet": str(item.get("sheet")),
                    "cell": str(item.get("cell")),
                    "reason": "INVALID_CELL_PRESENCE_STATE",
                }
            )
        expected_api_cell_present = cell_state in {
            "EXPLICIT_EMPTY_CELL_DATA",
            "CELL_VALUE_DATA_PRESENT",
            "CELL_METADATA_ONLY",
        }
        if item.get("api_cell_present") is not expected_api_cell_present:
            blocking.append(
                {
                    "sheet": str(item.get("sheet")),
                    "cell": str(item.get("cell")),
                    "reason": "CELL_PRESENCE_METADATA_MISMATCH",
                }
            )
        cell_data_states[cell_state] = cell_data_states.get(cell_state, 0) + 1
        empty_policy = str(item.get("empty_value_policy", "UNKNOWN"))
        empty_policy_counts[empty_policy] = empty_policy_counts.get(empty_policy, 0) + 1
        definition = ImporterValueCell(
            str(item.get("sheet")),
            str(item.get("cell")),
            str(item.get("domain")),
            cast(SemanticMode, item.get("mode")),
        )
        expected_empty_policy = importer_empty_value_policy(
            None, definition, live_values=live_policy_values
        )
        if empty_policy != expected_empty_policy:
            blocking.append(
                {
                    "sheet": str(item.get("sheet")),
                    "cell": str(item.get("cell")),
                    "reason": "IMPORTER_EMPTY_POLICY_MISMATCH",
                }
            )
        diagnostic = item.get("diagnostics", {})
        classification = str(diagnostic.get("classification", "UNKNOWN"))
        classifications[classification] = classifications.get(classification, 0) + 1
        if diagnostic.get("formula_relation") not in {"NO_FORMULA", "EXACT_TEXT_MATCH"}:
            formula_differences += 1
            if item.get("sheet") == "Price Feed":
                price_feed_formula_differences += 1
        if diagnostic.get("value_relation") != "EXACT_TYPED_VALUE_MATCH":
            xlsx_value_differences += 1
        reason = _source_type_mismatch(item)
        if reason:
            blocking.append(
                {"sheet": str(item.get("sheet")), "cell": str(item.get("cell")), "reason": reason}
            )
        if cell_state == "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE":
            sheets_evidence = item.get("sheets", {})
            if (
                not isinstance(sheets_evidence, dict)
                or sheets_evidence.get("user_entered_value") is not None
                or sheets_evidence.get("effective_value") is not None
            ):
                blocking.append(
                    {
                        "sheet": str(item.get("sheet")),
                        "cell": str(item.get("cell")),
                        "reason": "OMITTED_CELL_HAS_VALUE_EVIDENCE",
                    }
                )
        normalized_state = item.get("normalized", {}).get("authoritative_live", {}).get("state")
        if normalized_state in {"BLANK", "EMPTY_STRING", "FORMULA_EMPTY_STRING", "MISSING"}:
            state = str(normalized_state)
            normalized_empty_states[state] = normalized_empty_states.get(state, 0) + 1
            aggregate_key = (
                str(item.get("sheet")),
                str(item.get("target_field")),
                str(item.get("mode")),
                empty_policy,
                state,
            )
            empty_state_by_sheet_field[aggregate_key] = (
                empty_state_by_sheet_field.get(aggregate_key, 0) + 1
            )
        if empty_policy == "REQUIRED_NONEMPTY" and normalized_state in {
            "BLANK",
            "MISSING",
            "EMPTY_STRING",
            "FORMULA_EMPTY_STRING",
        }:
            required_empty.append(
                {
                    "sheet": str(item.get("sheet")),
                    "cell": str(item.get("cell")),
                    "target_field": str(item.get("target_field")),
                    "reason": "REQUIRED_IMPORTER_VALUE_EMPTY",
                }
            )
    if any(item.get("api_coordinate_covered") is not True for item in cells):
        raise SourceValueBundleError(
            "A required importer coordinate is not covered by a confirmed Sheets range."
        )
    payload: dict[str, Any] = {
        "contract_version": SOURCE_VALUE_BUNDLE_VERSION,
        "source_authority_contract_version": SOURCE_AUTHORITY_CONTRACT_VERSION,
        "status": "CAPTURED_REVIEW_REQUIRED"
        if not blocking and not required_empty
        else "CAPTURED_BLOCKED",
        "scope": "canonical-bootstrap",
        "source_acquisition_run_id": run_id,
        "source_profile": manifest.get("profile"),
        "source_contract_version": manifest.get("contract_version"),
        "source_filename": manifest.get("expected_filename"),
        "source_mime_type": manifest.get("source_mime_type"),
        "source_identity_sha256": source_identity_sha256,
        "source_revision": manifest.get("source_revision"),
        "source_modified_at": manifest.get("source_modified_at"),
        "source_checksum": manifest.get("source_checksum"),
        "source_artifact_sha256": artifact_sha256,
        "source_schema_fingerprint": schema_fingerprint,
        "source_semantic_fingerprint_version": manifest.get("semantic_fingerprint_version"),
        "source_semantic_sha256": semantic_sha256,
        "source_date_system": "Google Sheets serial-date semantics",
        "captured_at_utc": comparison_completed_at_utc,
        "consistency": {
            "protocol": consistency_protocol,
            "comparison_contract_version": comparison.get("comparison_contract_version"),
            "comparison_attempt_id": comparison.get("comparison_attempt_id"),
            "live_cell_evidence_sha256": comparison.get("live_cell_evidence_sha256"),
            "comparison_started_at_utc": comparison_started_at_utc,
            "comparison_completed_at_utc": comparison_completed_at_utc,
            "source_metadata_matched_before_capture": consistency_checks[
                "snapshot_metadata_matched_before_capture"
            ],
            "source_metadata_unchanged_before_and_after": consistency_checks[
                "source_metadata_unchanged_before_and_after"
            ],
            "live_values_stable_across_two_reads": consistency_checks[
                "live_values_stable_across_two_reads"
            ],
            "live_formula_definitions_stable_across_two_reads": consistency_checks[
                "live_formula_definitions_stable_across_two_reads"
            ],
            "live_source_cell_evidence_stable_across_two_reads": consistency_checks[
                "live_source_cell_evidence_stable_across_two_reads"
            ],
            "required_importer_coordinates_covered_in_both_reads": consistency_checks[
                "required_importer_coordinates_covered_in_both_reads"
            ],
            "transactional_snapshot_guaranteed": False,
            "interpretation": (
                "Observed consistent importer-scoped source state; Google Sheets does not "
                "provide a transaction token for this bounded multi-request capture."
            ),
        },
        "field_contract": {
            "authority": "Sheets API effectiveValue for every listed importer-consumed field",
            "literal_cells": (
                "Preserve userEnteredValue and effectiveValue as distinct typed evidence."
            ),
            "formula_cells": (
                "Preserve XLSX and live formulas independently; import the live effectiveValue; "
                "make no Excel formula equivalence assertion."
            ),
            "price_feed_row_class": (
                "ListingMapping row filter uses the captured Sheets effectiveValue; formula "
                "text is preserved as source evidence and never interpreted as Excel semantics."
            ),
            "missing_values": (
                "Missing requested ranges block capture. Omitted CellData is a verified blank "
                "only inside a confirmed, dimension-checked GridData range. Empty strings and "
                "formula results of empty strings remain distinct; zero remains zero."
            ),
            "empty_value_policy": (
                "Required nonempty fields with blank, empty-string, or formula-empty-string "
                "values block approval. Other empty values remain explicit source states and "
                "are subject to the existing canonical importer validation."
            ),
            "numeric_values": (
                "Exact decimal text; no float conversion or rescaling beyond importer mode."
            ),
            "units_and_currencies": "Preserved source values; no currency conversion is performed.",
        },
        "quality": {
            "importer_cell_count": len(cells),
            "uncovered_api_coordinates": sum(
                item.get("api_coordinate_covered") is not True for item in cells
            ),
            "required_nonempty_value_issue_count": len(required_empty),
            "required_nonempty_value_issues": required_empty,
            "cell_data_state_counts": dict(sorted(cell_data_states.items())),
            "normalized_empty_state_counts": dict(sorted(normalized_empty_states.items())),
            "empty_value_policy_counts": dict(sorted(empty_policy_counts.items())),
            "empty_state_counts_by_sheet_field_type_policy": [
                {
                    "sheet": key[0],
                    "target_field": key[1],
                    "mode": key[2],
                    "policy": key[3],
                    "state": key[4],
                    "count": count,
                }
                for key, count in sorted(empty_state_by_sheet_field.items())
            ],
            "xlsx_value_difference_count": xlsx_value_differences,
            "formula_definition_difference_count": formula_differences,
            "price_feed_formula_definition_difference_count": price_feed_formula_differences,
            "classification_counts": dict(sorted(classifications.items())),
            "blocking_issue_count": len(blocking) + len(required_empty),
            "blocking_issues": blocking + required_empty,
        },
        "cells": cells,
    }
    raw = _canonical_bytes(payload)
    digest = _sha256(raw)
    path = _bundle_path(store, run_id, digest)
    _write_immutable(store.root, path, raw, label="source-value bundle")
    return {
        "status": payload["status"],
        "contract_version": SOURCE_VALUE_BUNDLE_VERSION,
        "bundle_sha256": digest,
        "relative_path": str(path.relative_to(store.root)),
        "importer_cell_count": len(cells),
        "xlsx_value_difference_count": xlsx_value_differences,
        "formula_definition_difference_count": formula_differences,
        "price_feed_formula_definition_difference_count": price_feed_formula_differences,
        "blocking_issue_count": len(blocking) + len(required_empty),
        "required_nonempty_value_issue_count": len(required_empty),
        "cell_data_state_counts": dict(sorted(cell_data_states.items())),
        "normalized_empty_state_counts": dict(sorted(normalized_empty_states.items())),
        "empty_value_policy_counts": dict(sorted(empty_policy_counts.items())),
        "empty_state_counts_by_sheet_field_type_policy": [
            {
                "sheet": key[0],
                "target_field": key[1],
                "mode": key[2],
                "policy": key[3],
                "state": key[4],
                "count": count,
            }
            for key, count in sorted(empty_state_by_sheet_field.items())
        ],
    }


def inspect_source_value_bundle(
    store: SnapshotStore, run_id: str, bundle_sha256: str
) -> dict[str, Any]:
    path, bundle = _read_bundle(store, run_id, bundle_sha256)
    quality = bundle.get("quality", {})
    return {
        "status": bundle.get("status"),
        "contract_version": bundle.get("contract_version"),
        "bundle_sha256": bundle_sha256,
        "relative_path": str(path.relative_to(store.root)),
        "source_acquisition_run_id": run_id,
        "captured_at_utc": bundle.get("captured_at_utc"),
        "scope": bundle.get("scope"),
        "consistency_protocol": bundle.get("consistency", {}).get("protocol"),
        "transactional_snapshot_guaranteed": False,
        "importer_cell_count": quality.get("importer_cell_count"),
        "xlsx_value_difference_count": quality.get("xlsx_value_difference_count"),
        "formula_definition_difference_count": quality.get("formula_definition_difference_count"),
        "price_feed_formula_definition_difference_count": quality.get(
            "price_feed_formula_definition_difference_count"
        ),
        "blocking_issue_count": quality.get("blocking_issue_count"),
        "uncovered_api_coordinates": quality.get("uncovered_api_coordinates"),
        "required_nonempty_value_issue_count": quality.get("required_nonempty_value_issue_count"),
        "cell_data_state_counts": quality.get("cell_data_state_counts", {}),
        "normalized_empty_state_counts": quality.get("normalized_empty_state_counts", {}),
        "empty_value_policy_counts": quality.get("empty_value_policy_counts", {}),
        "empty_state_counts_by_sheet_field_type_policy": quality.get(
            "empty_state_counts_by_sheet_field_type_policy", []
        ),
        "classification_counts": quality.get("classification_counts", {}),
    }


def approve_source_value_bundle(
    store: SnapshotStore,
    *,
    run_id: str,
    bundle_sha256: str,
    reviewed_by: str,
    review_note: str,
    confirm_sheets_values_authoritative: bool,
    confirm_xlsx_value_differences: bool,
    confirm_formula_definition_differences: bool,
    confirm_price_feed_formula_policy: bool,
) -> tuple[Path, str, dict[str, Any]]:
    bundle_path, bundle = _read_bundle(store, run_id, bundle_sha256)
    quality = bundle.get("quality")
    if bundle.get("status") != "CAPTURED_REVIEW_REQUIRED" or not isinstance(quality, dict):
        raise SourceValueBundleError(
            "A clean, complete source-value bundle is required for approval."
        )
    if quality.get("blocking_issue_count") != 0 or quality.get("uncovered_api_coordinates") != 0:
        raise SourceValueBundleError(
            "The source-value bundle contains blocking value-quality issues."
        )
    if not confirm_sheets_values_authoritative:
        raise SourceValueBundleError(
            "Explicit confirmation of Sheets-authoritative values is required."
        )
    if quality.get("xlsx_value_difference_count", 0) and not confirm_xlsx_value_differences:
        raise SourceValueBundleError("Explicit review of XLSX/live value differences is required.")
    if (
        quality.get("formula_definition_difference_count", 0)
        and not confirm_formula_definition_differences
    ):
        raise SourceValueBundleError(
            "Explicit review of formula-definition differences is required; "
            "no equivalence is inferred."
        )
    if (
        quality.get("price_feed_formula_definition_difference_count", 0)
        and not confirm_price_feed_formula_policy
    ):
        raise SourceValueBundleError(
            "Explicit review of the Price Feed field-level formula policy is required."
        )
    reviewer = reviewed_by.strip()
    note = review_note.strip()
    if not reviewer or len(reviewer) > 200 or len(note) < 12 or len(note) > 2000:
        raise SourceValueBundleError("A reviewer and a substantive review note are required.")
    try:
        source_manifest = store.manifest(run_id)
    except WorkbookSourceError as error:
        raise SourceValueBundleError("The source acquisition manifest is unavailable.") from error
    if (
        source_manifest.get("artifact_sha256") != bundle.get("source_artifact_sha256")
        or source_manifest.get("schema_fingerprint") != bundle.get("source_schema_fingerprint")
        or source_manifest.get("semantic_sha256") != bundle.get("source_semantic_sha256")
        or source_manifest.get("source_identity_sha256") != bundle.get("source_identity_sha256")
        or source_manifest.get("source_mime_type") != GOOGLE_SHEET_MIME
        or source_manifest.get("profile") != PORTFOLIO_PROFILE.key
        or source_manifest.get("contract_version") != PORTFOLIO_PROFILE.contract_version
        or source_manifest.get("source_revision") != bundle.get("source_revision")
        or source_manifest.get("source_modified_at") != bundle.get("source_modified_at")
        or source_manifest.get("source_checksum") != bundle.get("source_checksum")
    ):
        raise SourceValueBundleError(
            "The source bundle no longer matches its acquisition manifest."
        )
    receipt = {
        "contract_version": SOURCE_VALUE_APPROVAL_VERSION,
        "status": "APPROVED_FOR_CANONICAL_IMPORT",
        "source_acquisition_run_id": run_id,
        "source_value_bundle_sha256": bundle_sha256,
        "source_artifact_sha256": bundle.get("source_artifact_sha256"),
        "source_schema_fingerprint": bundle.get("source_schema_fingerprint"),
        "source_semantic_sha256": bundle.get("source_semantic_sha256"),
        "source_identity_sha256": bundle.get("source_identity_sha256"),
        "source_revision": bundle.get("source_revision"),
        "source_modified_at": bundle.get("source_modified_at"),
        "source_checksum": bundle.get("source_checksum"),
        "reviewed_by": reviewer,
        "review_note": note,
        "reviewed_at_utc": _utc_now(),
        "confirmation": {
            "sheets_values_authoritative": True,
            "xlsx_value_differences_reviewed": confirm_xlsx_value_differences,
            "formula_definition_differences_reviewed_without_equivalence_claim": (
                confirm_formula_definition_differences
            ),
            "price_feed_formula_policy_reviewed_without_equivalence_claim": (
                confirm_price_feed_formula_policy
            ),
            "schema_acceptance_included": False,
            "investment_decisions_inferred": False,
        },
        "bundle_relative_path": str(bundle_path.relative_to(store.root)),
    }
    payload = _canonical_bytes(receipt)
    digest = _sha256(payload)
    target = _approval_directory(store) / f"{bundle_sha256}-{digest}.json"
    path = _write_immutable(store.root, target, payload, label="source-value approval")
    return path, digest, receipt


def _expected_import_cells(workbook: Workbook) -> dict[tuple[str, str], Any]:
    return {
        (definition.sheet, definition.address): definition
        for definition in importer_value_cells(workbook)
        if _importer_cell_is_consumed(workbook, definition)
    }


def _live_cell_from_record(record: dict[str, Any], source_cell: Cell) -> Cell:
    effective = record.get("sheets", {}).get("effective_value")
    formula = record.get("sheets", {}).get("formula_text")
    if not isinstance(effective, dict) or not effective:
        entered = record.get("sheets", {}).get("user_entered_value")
        if isinstance(entered, dict) and entered.get("stringValue") == "" and not formula:
            return Cell(
                value="",
                kind="str",
                formula=None,
                number_format_code=source_cell.number_format_code,
                number_format_type=source_cell.number_format_type,
            )
        if formula or (
            isinstance(entered, dict) and any(value not in (None, "") for value in entered.values())
        ):
            raise SourceValueBundleError(
                "A live entered value has no effective result; XLSX fallback is forbidden."
            )
        return Cell(
            value=None,
            kind=None,
            formula=None,
            number_format_code=source_cell.number_format_code,
            number_format_type=source_cell.number_format_type,
        )
    variant = next(iter(effective))
    value = effective[variant]
    if variant == "numberValue":
        if not isinstance(value, str) or not value:
            raise SourceValueBundleError(
                "A live numeric value is not stored as exact decimal text."
            )
        return Cell(
            value=value,
            kind="n",
            formula=formula.removeprefix("=") if isinstance(formula, str) else None,
            number_format_code=source_cell.number_format_code,
            number_format_type=source_cell.number_format_type,
        )
    if variant == "stringValue" and isinstance(value, str):
        return Cell(
            value=value,
            kind="str",
            formula=formula.removeprefix("=") if isinstance(formula, str) else None,
            number_format_code=source_cell.number_format_code,
            number_format_type=source_cell.number_format_type,
        )
    raise SourceValueBundleError("A live value has an unsupported or invalid type.")


def apply_approved_source_value_bundle(
    store: SnapshotStore,
    *,
    run_id: str,
    bundle_sha256: str,
    approval_sha256: str,
    workbook: Workbook,
    expected_artifact_sha256: str,
    expected_schema_fingerprint: str,
    expected_semantic_sha256: str,
    expected_source_identity_sha256: str,
    expected_source_revision: str | None,
    expected_source_modified_at: str | None,
    expected_source_checksum: str | None,
) -> dict[str, Any]:
    bundle_path, bundle = _read_bundle(store, run_id, bundle_sha256)
    approval_path, approval = _read_approval(store, run_id, bundle_sha256, approval_sha256)
    if (
        bundle.get("source_artifact_sha256") != expected_artifact_sha256
        or bundle.get("source_schema_fingerprint") != expected_schema_fingerprint
        or workbook.sha256 != expected_artifact_sha256
        or bundle.get("source_semantic_sha256") != expected_semantic_sha256
        or bundle.get("source_identity_sha256") != expected_source_identity_sha256
        or bundle.get("source_revision") != expected_source_revision
        or bundle.get("source_modified_at") != expected_source_modified_at
        or bundle.get("source_checksum") != expected_source_checksum
        or approval.get("source_artifact_sha256") != expected_artifact_sha256
        or approval.get("source_schema_fingerprint") != expected_schema_fingerprint
        or approval.get("source_semantic_sha256") != expected_semantic_sha256
        or approval.get("source_identity_sha256") != expected_source_identity_sha256
        or approval.get("source_revision") != expected_source_revision
        or approval.get("source_modified_at") != expected_source_modified_at
        or approval.get("source_checksum") != expected_source_checksum
    ):
        raise SourceValueBundleError(
            "The approved source bundle does not match the frozen workbook."
        )
    if bundle.get("status") != "CAPTURED_REVIEW_REQUIRED":
        raise SourceValueBundleError("The source bundle is blocked from canonical import.")
    consistency = bundle.get("consistency")
    if (
        not isinstance(consistency, dict)
        or consistency.get("transactional_snapshot_guaranteed") is not False
        or any(
            consistency.get(key) is not True
            for key in (
                "source_metadata_matched_before_capture",
                "source_metadata_unchanged_before_and_after",
                "live_values_stable_across_two_reads",
                "live_formula_definitions_stable_across_two_reads",
                "live_source_cell_evidence_stable_across_two_reads",
                "required_importer_coordinates_covered_in_both_reads",
            )
        )
    ):
        raise SourceValueBundleError("The source bundle consistency statement is invalid.")
    expected = _expected_import_cells(workbook)
    records = bundle.get("cells")
    if not isinstance(records, list):
        raise SourceValueBundleError("The source bundle cell contract is invalid.")
    actual: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise SourceValueBundleError("The source bundle contains an invalid cell record.")
        sheet_name = record.get("sheet")
        address = record.get("cell")
        if not isinstance(sheet_name, str) or not isinstance(address, str):
            raise SourceValueBundleError("The source bundle has an invalid cell identity.")
        key = (sheet_name, address)
        if key in actual:
            raise SourceValueBundleError(
                "The source bundle has duplicate or invalid cell identities."
            )
        actual[key] = record
    if set(actual) != set(expected):
        raise SourceValueBundleError(
            "The source bundle does not cover the exact importer cell set."
        )
    live_policy_values = _live_values_for_policy(records)
    for key, definition in expected.items():
        record = actual[key]
        if (
            record.get("domain") != definition.domain
            or record.get("mode") != definition.mode
            or record.get("target_field") != importer_field_semantics(definition)[0]
            or record.get("transformation") != importer_field_semantics(definition)[1]
            or (record.get("value_authority"), record.get("formula_policy"))
            != importer_source_value_policy(definition)
            or record.get("api_coordinate_covered") is not True
            or record.get("empty_value_policy")
            != importer_empty_value_policy(workbook, definition, live_values=live_policy_values)
            or (
                record.get("empty_value_policy") == "REQUIRED_NONEMPTY"
                and record.get("normalized", {}).get("authoritative_live", {}).get("state")
                in {"BLANK", "MISSING", "EMPTY_STRING", "FORMULA_EMPTY_STRING"}
            )
            or _source_type_mismatch(record) is not None
        ):
            raise SourceValueBundleError(
                "A source bundle field failed its importer contract check."
            )
    for (sheet, address), record in actual.items():
        source_cell = workbook.sheets.get(sheet, {}).get(address, Cell())
        workbook.sheets.setdefault(sheet, {})[address] = _live_cell_from_record(record, source_cell)
    workbook.source_value_bundle_sha256 = bundle_sha256
    workbook.source_value_bundle_approval_sha256 = approval_sha256
    workbook.source_value_bundle_observed_at = bundle.get("captured_at_utc")
    workbook.source_value_bundle_contract = bundle.get("contract_version")
    return {
        "bundle_sha256": bundle_sha256,
        "approval_sha256": approval_sha256,
        "bundle_relative_path": str(bundle_path.relative_to(store.root)),
        "approval_relative_path": str(approval_path.relative_to(store.root)),
        "contract_version": bundle.get("contract_version"),
        "captured_at_utc": bundle.get("captured_at_utc"),
        "importer_cell_count": len(records),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_command = commands.add_parser("inspect")
    approve_command = commands.add_parser("approve")
    for command in (inspect_command, approve_command):
        command.add_argument("--store", type=Path, required=True)
        command.add_argument("--portfolio-run", required=True)
        command.add_argument("--bundle-sha256", required=True)
    approve_command.add_argument("--reviewed-by", required=True)
    approve_command.add_argument("--review-note", required=True)
    approve_command.add_argument("--confirm-sheets-values-authoritative", action="store_true")
    approve_command.add_argument("--confirm-xlsx-value-differences", action="store_true")
    approve_command.add_argument("--confirm-formula-definition-differences", action="store_true")
    approve_command.add_argument("--confirm-price-feed-formula-policy", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = SnapshotStore(args.store)
        if args.command == "inspect":
            result = inspect_source_value_bundle(store, args.portfolio_run, args.bundle_sha256)
        else:
            path, digest, receipt = approve_source_value_bundle(
                store,
                run_id=args.portfolio_run,
                bundle_sha256=args.bundle_sha256,
                reviewed_by=args.reviewed_by,
                review_note=args.review_note,
                confirm_sheets_values_authoritative=args.confirm_sheets_values_authoritative,
                confirm_xlsx_value_differences=args.confirm_xlsx_value_differences,
                confirm_formula_definition_differences=(
                    args.confirm_formula_definition_differences
                ),
                confirm_price_feed_formula_policy=args.confirm_price_feed_formula_policy,
            )
            result = {
                "status": receipt["status"],
                "approval_sha256": digest,
                "relative_path": str(path.relative_to(store.root)),
                "contract_version": receipt["contract_version"],
                "reviewed_at_utc": receipt["reviewed_at_utc"],
            }
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, SourceValueBundleError, WorkbookSourceError, ValueError) as error:
        print(
            json.dumps({"status": "BLOCKED", "message": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
