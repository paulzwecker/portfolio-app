"""Synthetic contract tests for immutable native-Sheets source-value bundles."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from portfolio_api.legacy_import import Cell, Workbook
from portfolio_api.workbook_semantics import (
    SEMANTIC_FINGERPRINT_VERSION,
    ImporterValueCell,
    importer_empty_value_policy,
    importer_field_semantics,
    importer_source_value_policy,
    importer_value_cells,
)
from portfolio_api.workbook_source_bundle import (
    SOURCE_AUTHORITY_CONTRACT_VERSION,
    SOURCE_VALUE_BUNDLE_VERSION,
    SourceValueBundleError,
    apply_approved_source_value_bundle,
    approve_source_value_bundle,
    capture_source_value_bundle,
    inspect_source_value_bundle,
)
from portfolio_api.workbook_sources import GOOGLE_SHEET_MIME, PORTFOLIO_PROFILE, SnapshotStore

RUN_ID = "a" * 32
ARTIFACT = "b" * 64
SEMANTIC = "c" * 64
SCHEMA = "d" * 64
SOURCE_IDENTITY = "e" * 64
CAPTURED_AT = "2026-10-31T10:00:00Z"


def _store(tmp_path_factory: pytest.TempPathFactory) -> SnapshotStore:
    return SnapshotStore(tmp_path_factory.mktemp("d1") / "s")


def _workbook() -> Workbook:
    return Workbook(
        Path("Portfolio_Watchlist.xlsx"),
        ARTIFACT,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell("Synthetic Company", "inlineStr"),
                "C5": Cell("Watchlist", "inlineStr"),
                "D5": Cell("0", "n"),
                "F5": Cell("0.1250000000000000001", "n"),
                "J5": Cell("1", "n"),
                "L5": Cell("2", "n"),
                "M5": Cell("3", "n"),
            },
            "Current Holdings": {"L4": Cell("EUR", "inlineStr")},
            "Target Architecture": {"P3": Cell("0.1250000000000000001", "n")},
            "Price Feed": {
                "A5": Cell("AUX", "inlineStr"),
                "B5": Cell("Synthetic Fund", "inlineStr"),
                "C5": Cell("SPYY", "inlineStr"),
                "D5": Cell("XETR:SPYY", "str", 'CONCATENATE("XETR:","SPYY")'),
                "H5": Cell("EUR", "inlineStr"),
            },
        },
    )


def _manifest() -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "profile": PORTFOLIO_PROFILE.key,
        "contract_version": PORTFOLIO_PROFILE.contract_version,
        "semantic_fingerprint_version": SEMANTIC_FINGERPRINT_VERSION,
        "expected_filename": PORTFOLIO_PROFILE.expected_filename,
        "source_mime_type": GOOGLE_SHEET_MIME,
        "artifact_sha256": ARTIFACT,
        "semantic_sha256": SEMANTIC,
        "schema_fingerprint": SCHEMA,
        "source_identity_sha256": SOURCE_IDENTITY,
        "source_revision": None,
        "source_modified_at": "2026-10-31T09:59:00Z",
        "source_checksum": None,
    }


def _source_cells(
    workbook: Workbook,
    *,
    overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
    missing: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    overrides = overrides or {}
    missing = missing or set()
    result: list[dict[str, Any]] = []
    for definition in importer_value_cells(workbook):
        row = workbook.cell(definition.sheet, definition.address)
        if row.kind in {"inlineStr", "str"}:
            effective: dict[str, Any] = {"stringValue": row.value or ""}
            normalized_state = "EMPTY_STRING" if row.value == "" else "VALUE"
            source_type = "empty-string" if normalized_state == "EMPTY_STRING" else "text"
        elif row.value is None:
            effective = {}
            normalized_state = "BLANK"
            source_type = "blank"
        else:
            effective = {"numberValue": format(Decimal(row.value), "f")}
            normalized_state = "VALUE"
            source_type = "number"
        formula = f"={row.formula}" if row.formula else None
        if formula and normalized_state == "EMPTY_STRING":
            normalized_state = "FORMULA_EMPTY_STRING"
            source_type = "formula-empty-string"
        missing_coordinate = (definition.sheet, definition.address) in missing
        if missing_coordinate:
            cell_data_state = "UNVERIFIED_MISSING_COORDINATE"
        elif row.value is None and not row.formula:
            cell_data_state = "EXPLICIT_EMPTY_CELL_DATA"
        else:
            cell_data_state = "CELL_VALUE_DATA_PRESENT"
        item = {
            "domain": definition.domain,
            "sheet": definition.sheet,
            "cell": definition.address,
            "target_field": importer_field_semantics(definition)[0],
            "transformation": importer_field_semantics(definition)[1],
            "mode": definition.mode,
            "source_role": "synthetic",
            "value_authority": importer_source_value_policy(definition)[0],
            "formula_policy": importer_source_value_policy(definition)[1],
            "api_cell_present": not missing_coordinate
            and cell_data_state != "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE",
            "api_coordinate_covered": not missing_coordinate,
            "cell_data_state": cell_data_state,
            "empty_value_policy": importer_empty_value_policy(workbook, definition),
            "xlsx": {
                "state": normalized_state,
                "normalized_value": row.value,
                "source_type": source_type,
                "value_text": row.value,
                "cell_type": row.kind,
                "formula_text": row.formula,
            },
            "sheets": {
                "user_entered_value": {"formulaValue": formula} if formula else effective,
                "effective_value": effective,
                "formula_text": formula,
                "effective_number_format_type": row.number_format_type,
                "effective_number_format_pattern": None,
            },
            "normalized": {
                "authoritative_live": {
                    "state": normalized_state,
                    "value": row.value if normalized_state == "VALUE" else "",
                    "source_type": source_type,
                },
                "live_source_type": source_type,
            },
            "diagnostics": {
                "classification": "MATCH",
                "value_relation": "EXACT_TYPED_VALUE_MATCH",
                "formula_relation": "NO_FORMULA",
                "number_format_relation": "EXACT_FORMAT_MATCH",
            },
        }
        item.update(overrides.get((definition.sheet, definition.address), {}))
        result.append(item)
    return result


def _comparison(*, checks: dict[str, bool] | None = None) -> dict[str, Any]:
    return {
        "consistency_result": "COMPARED",
        "scope": "canonical-bootstrap",
        "comparison_contract_version": "synthetic-comparison-v1",
        "comparison_attempt_id": "f" * 32,
        "expected_importer_cell_count": len(_source_cells(_workbook())),
        "consistency_checks": checks
        or {
            "snapshot_metadata_matched_before_capture": True,
            "source_metadata_unchanged_before_and_after": True,
            "live_values_stable_across_two_reads": True,
            "live_formula_definitions_stable_across_two_reads": True,
            "live_source_cell_evidence_stable_across_two_reads": True,
            "required_importer_coordinates_covered_in_both_reads": True,
        },
    }


def _capture(
    store: SnapshotStore, *, source_cells: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return capture_source_value_bundle(
        store,
        manifest=_manifest(),
        source_cells=source_cells or _source_cells(_workbook()),
        comparison=_comparison(),
        comparison_started_at_utc="2026-10-31T09:58:00Z",
        comparison_completed_at_utc=CAPTURED_AT,
        consistency_protocol="NO_DRIVE_REVISION_SEMANTIC_FENCE",
    )


def _write_manifest(store: SnapshotStore) -> None:
    store._write_manifest(_manifest())


def test_bundle_capture_preserves_exact_decimals_blanks_zero_and_replays_by_hash(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    cells = _source_cells(_workbook())
    blank = next(
        item for item in cells if (item["sheet"], item["cell"]) == ("Model Contract", "A5")
    )
    blank["cell_data_state"] = "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE"
    blank["api_cell_present"] = False
    blank["sheets"]["effective_value"] = None
    blank["sheets"]["user_entered_value"] = None
    blank["normalized"]["authoritative_live"] = {
        "state": "BLANK",
        "value": "",
        "source_type": "blank",
    }
    result = _capture(store, source_cells=cells)
    repeated = _capture(store, source_cells=cells)

    assert result["contract_version"] == SOURCE_VALUE_BUNDLE_VERSION
    assert result["bundle_sha256"] == repeated["bundle_sha256"]
    bundle = json.loads((store.root / result["relative_path"]).read_text(encoding="utf-8"))
    values = {(item["sheet"], item["cell"]): item for item in bundle["cells"]}
    assert values[("Universe Registry", "D5")]["sheets"]["effective_value"]["numberValue"] == "0"
    assert (
        values[("Universe Registry", "F5")]["sheets"]["effective_value"]["numberValue"]
        == "0.1250000000000000001"
    )
    assert values[("Model Contract", "A5")]["normalized"]["authoritative_live"]["state"] == "BLANK"
    assert values[("Model Contract", "A5")]["api_coordinate_covered"] is True
    assert values[("Model Contract", "A5")]["api_cell_present"] is False
    assert bundle["consistency"]["transactional_snapshot_guaranteed"] is False
    assert bundle["source_authority_contract_version"] == SOURCE_AUTHORITY_CONTRACT_VERSION


def test_price_feed_formula_policy_is_field_specific_and_has_no_excel_equivalence_claim() -> None:
    definition = next(
        item
        for item in importer_value_cells(_workbook())
        if (item.sheet, item.address) == ("Price Feed", "D5")
    )

    authority, policy = importer_source_value_policy(definition)

    assert authority == "google_sheets.effective_value"
    assert "Listing.exchange_and_ticker" in policy
    assert "no_excel_formula_equivalence_assertion" in policy


def test_price_feed_formula_change_requires_separate_explicit_policy_review(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    cells = _source_cells(
        _workbook(),
        overrides={
            ("Price Feed", "D5"): {
                "diagnostics": {
                    "classification": "FORMULA_DEFINITION_MISMATCH",
                    "value_relation": "EXACT_TYPED_VALUE_MATCH",
                    "formula_relation": "TEXT_DIFFERENCE_UNRESOLVED",
                    "number_format_relation": "EXACT_FORMAT_MATCH",
                }
            }
        },
    )
    result = _capture(store, source_cells=cells)
    with pytest.raises(SourceValueBundleError, match="Price Feed field-level formula policy"):
        approve_source_value_bundle(
            store,
            run_id=RUN_ID,
            bundle_sha256=result["bundle_sha256"],
            reviewed_by="synthetic reviewer",
            review_note="Reviewed the complete synthetic fixture source evidence.",
            confirm_sheets_values_authoritative=True,
            confirm_xlsx_value_differences=False,
            confirm_formula_definition_differences=True,
            confirm_price_feed_formula_policy=False,
        )


def test_missing_required_cell_or_unstable_capture_fails_without_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    cells = _source_cells(_workbook())
    cells[0]["api_cell_present"] = False
    cells[0]["api_coordinate_covered"] = False
    cells[0]["cell_data_state"] = "UNVERIFIED_MISSING_COORDINATE"

    with pytest.raises(SourceValueBundleError, match="required importer coordinate"):
        _capture(store, source_cells=cells)

    checks = _comparison()["consistency_checks"]
    checks["live_values_stable_across_two_reads"] = False
    with pytest.raises(SourceValueBundleError, match="consistency fence"):
        capture_source_value_bundle(
            store,
            manifest=_manifest(),
            source_cells=_source_cells(_workbook()),
            comparison=_comparison(checks=checks),
            comparison_started_at_utc="2026-10-31T09:58:00Z",
            comparison_completed_at_utc=CAPTURED_AT,
            consistency_protocol="NO_DRIVE_REVISION_SEMANTIC_FENCE",
        )

    assert not (store.root / "source-value-bundles").exists()


def test_live_type_mismatch_is_captured_as_blocked_and_cannot_be_approved(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    cells = _source_cells(
        _workbook(),
        overrides={
            ("Universe Registry", "D5"): {
                "sheets": {
                    "effective_value": {"stringValue": "0"},
                    "formula_text": None,
                },
                "normalized": {
                    "authoritative_live": {"state": "VALUE", "value": "0", "source_type": "text"},
                    "live_source_type": "text",
                },
            }
        },
    )
    result = _capture(store, source_cells=cells)
    assert result["status"] == "CAPTURED_BLOCKED"
    with pytest.raises(SourceValueBundleError, match="clean, complete"):
        approve_source_value_bundle(
            store,
            run_id=RUN_ID,
            bundle_sha256=result["bundle_sha256"],
            reviewed_by="synthetic reviewer",
            review_note="This fixture deliberately contains a type mismatch.",
            confirm_sheets_values_authoritative=True,
            confirm_xlsx_value_differences=True,
            confirm_formula_definition_differences=True,
            confirm_price_feed_formula_policy=True,
        )


def test_entered_literal_without_effective_value_never_falls_back_to_xlsx_cache(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    cells = _source_cells(
        _workbook(),
        overrides={
            ("Universe Registry", "D5"): {
                "sheets": {
                    "user_entered_value": {"numberValue": "0"},
                    "effective_value": {},
                    "formula_text": None,
                }
            }
        },
    )

    result = _capture(store, source_cells=cells)

    assert result["status"] == "CAPTURED_BLOCKED"
    assert result["blocking_issue_count"] == 1


def test_required_nonempty_blank_is_captured_as_explicit_blocker(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    cells = _source_cells(_workbook())
    control = next(
        item for item in cells if (item["sheet"], item["cell"]) == ("Target Architecture", "P3")
    )
    control["sheets"]["user_entered_value"] = None
    control["sheets"]["effective_value"] = None
    control["normalized"]["authoritative_live"] = {
        "state": "BLANK",
        "value": "",
        "source_type": "blank",
    }
    control["normalized"]["live_source_type"] = "blank"
    control["cell_data_state"] = "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE"
    control["api_cell_present"] = False

    result = _capture(store, source_cells=cells)
    summary = inspect_source_value_bundle(store, RUN_ID, result["bundle_sha256"])

    assert result["status"] == "CAPTURED_BLOCKED"
    assert result["required_nonempty_value_issue_count"] == 1
    assert summary["required_nonempty_value_issue_count"] == 1
    with pytest.raises(SourceValueBundleError, match="clean, complete"):
        approve_source_value_bundle(
            store,
            run_id=RUN_ID,
            bundle_sha256=result["bundle_sha256"],
            reviewed_by="synthetic reviewer",
            review_note="The required control total is deliberately absent.",
            confirm_sheets_values_authoritative=True,
            confirm_xlsx_value_differences=False,
            confirm_formula_definition_differences=False,
            confirm_price_feed_formula_policy=False,
        )


def test_formula_empty_peer_does_not_make_score_identity_required() -> None:
    workbook = Workbook(
        Path("Portfolio_Watchlist.xlsx"),
        ARTIFACT,
        {"10Y Durability": {"A5": Cell("", "str", 'IF(TRUE, "", "score")')}},
    )
    definition = ImporterValueCell("10Y Durability", "A5", "quality_assessments", "ticker")
    live_values = {
        "10Y Durability": {
            (5, 7): {
                "userEnteredValue": {"formulaValue": '=IF(TRUE, "", 4)'},
                "effectiveValue": {"stringValue": ""},
            }
        }
    }

    assert (
        importer_empty_value_policy(workbook, definition, live_values=live_values) == "ALLOW_EMPTY"
    )


@pytest.mark.parametrize(
    "normalized_state,formula,expected_state",
    [
        ("EMPTY_STRING", None, "EMPTY_STRING"),
        ("FORMULA_EMPTY_STRING", '=IF(TRUE,"",1)', "FORMULA_EMPTY_STRING"),
    ],
)
def test_empty_string_state_replays_without_collapsing_to_blank(
    tmp_path_factory: pytest.TempPathFactory,
    normalized_state: str,
    formula: str | None,
    expected_state: str,
) -> None:
    store = _store(tmp_path_factory)
    workbook = _workbook()
    cells = _source_cells(workbook)
    record = next(
        item for item in cells if (item["sheet"], item["cell"]) == ("Model Contract", "A5")
    )
    record["sheets"]["user_entered_value"] = (
        {"formulaValue": formula} if formula else {"stringValue": ""}
    )
    record["sheets"]["effective_value"] = {"stringValue": ""}
    record["sheets"]["formula_text"] = formula
    record["normalized"]["authoritative_live"] = {
        "state": normalized_state,
        "value": "",
        "source_type": "formula-empty-string" if formula else "empty-string",
    }
    record["normalized"]["live_source_type"] = "string"
    record["cell_data_state"] = "CELL_VALUE_DATA_PRESENT"
    record["api_cell_present"] = True
    result = _capture(store, source_cells=cells)
    _write_manifest(store)
    _, approval_sha256, _receipt = approve_source_value_bundle(
        store,
        run_id=RUN_ID,
        bundle_sha256=result["bundle_sha256"],
        reviewed_by="synthetic reviewer",
        review_note="Reviewed explicit empty-string semantics in the source contract.",
        confirm_sheets_values_authoritative=True,
        confirm_xlsx_value_differences=False,
        confirm_formula_definition_differences=False,
        confirm_price_feed_formula_policy=False,
    )

    apply_approved_source_value_bundle(
        store,
        run_id=RUN_ID,
        bundle_sha256=result["bundle_sha256"],
        approval_sha256=approval_sha256,
        workbook=workbook,
        expected_artifact_sha256=ARTIFACT,
        expected_schema_fingerprint=SCHEMA,
        expected_semantic_sha256=SEMANTIC,
        expected_source_identity_sha256=SOURCE_IDENTITY,
        expected_source_revision=None,
        expected_source_modified_at="2026-10-31T09:59:00Z",
        expected_source_checksum=None,
    )

    replayed = workbook.cell("Model Contract", "A5")
    assert replayed.value == ""
    assert replayed.kind == "str"
    assert ("FORMULA_EMPTY_STRING" if replayed.formula else "EMPTY_STRING") == expected_state


def test_approved_bundle_replays_exact_live_values_against_frozen_identity(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    workbook = _workbook()
    result = _capture(store)
    _write_manifest(store)
    _, approval_sha256, _receipt = approve_source_value_bundle(
        store,
        run_id=RUN_ID,
        bundle_sha256=result["bundle_sha256"],
        reviewed_by="synthetic reviewer",
        review_note="Reviewed exact live values, source fields, and formula policy.",
        confirm_sheets_values_authoritative=True,
        confirm_xlsx_value_differences=False,
        confirm_formula_definition_differences=False,
        confirm_price_feed_formula_policy=False,
    )
    before = inspect_source_value_bundle(store, RUN_ID, result["bundle_sha256"])

    applied = apply_approved_source_value_bundle(
        store,
        run_id=RUN_ID,
        bundle_sha256=result["bundle_sha256"],
        approval_sha256=approval_sha256,
        workbook=workbook,
        expected_artifact_sha256=ARTIFACT,
        expected_schema_fingerprint=SCHEMA,
        expected_semantic_sha256=SEMANTIC,
        expected_source_identity_sha256=SOURCE_IDENTITY,
        expected_source_revision=None,
        expected_source_modified_at="2026-10-31T09:59:00Z",
        expected_source_checksum=None,
    )

    assert applied["bundle_sha256"] == result["bundle_sha256"]
    assert workbook.cell("Universe Registry", "D5").value == "0"
    assert workbook.cell("Target Architecture", "P3").value == "0.1250000000000000001"
    assert workbook.source_value_bundle_sha256 == result["bundle_sha256"]
    assert inspect_source_value_bundle(store, RUN_ID, result["bundle_sha256"]) == before


def test_approval_is_bound_to_source_schema_metadata_and_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    store = _store(tmp_path_factory)
    result = _capture(store)
    _write_manifest(store)
    _, approval_sha256, _receipt = approve_source_value_bundle(
        store,
        run_id=RUN_ID,
        bundle_sha256=result["bundle_sha256"],
        reviewed_by="synthetic reviewer",
        review_note="Reviewed exact live values, source fields, and formula policy.",
        confirm_sheets_values_authoritative=True,
        confirm_xlsx_value_differences=False,
        confirm_formula_definition_differences=False,
        confirm_price_feed_formula_policy=False,
    )
    with pytest.raises(SourceValueBundleError, match="does not match"):
        apply_approved_source_value_bundle(
            store,
            run_id=RUN_ID,
            bundle_sha256=result["bundle_sha256"],
            approval_sha256=approval_sha256,
            workbook=_workbook(),
            expected_artifact_sha256=ARTIFACT,
            expected_schema_fingerprint="0" * 64,
            expected_semantic_sha256=SEMANTIC,
            expected_source_identity_sha256=SOURCE_IDENTITY,
            expected_source_revision=None,
            expected_source_modified_at="2026-10-31T09:59:00Z",
            expected_source_checksum=None,
        )
