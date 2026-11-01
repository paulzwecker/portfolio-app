"""Live-source comparison normalizes exact types without exposing source values."""

import hashlib
import io
import json
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from zipfile import ZipFile

import pytest

from portfolio_api import workbook_value_validation as validation
from portfolio_api.legacy_import import Cell, Workbook
from portfolio_api.settings import Settings
from portfolio_api.workbook_semantics import (
    ImporterValueCell,
    importer_empty_value_policy,
    importer_value_cells,
    live_cell_normalization,
    normalize_source_cell,
)
from portfolio_api.workbook_sources import SnapshotStore
from portfolio_api.workbook_value_validation import (
    _cell_position,
    _classification,
    _comparison_status,
    _group_ranges,
    _importer_cell_is_consumed,
    _ranges_for_workbook,
    _snapshot_metadata_fence,
    compare_semantic_values,
)


def test_live_number_value_uses_decimal_precision_without_float_conversion() -> None:
    exact = Decimal("123456789012345.1234567890123456789")
    normalized, source_type, _scale = live_cell_normalization(
        {"numberValue": exact}, mode="decimal", has_formula=False
    )

    assert normalized.value == "123456789012345.1234567890123456789"
    assert source_type == "number"


def test_same_source_cell_and_live_value_produce_matching_semantics() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell("Synthetic Company", "inlineStr"),
                "C5": Cell("Watchlist", "inlineStr"),
                "D5": Cell("0", "n"),
                "F5": Cell("0.125", "n"),
                "J5": Cell("1", "n"),
                "L5": Cell("2", "n"),
                "M5": Cell("3", "n"),
            }
        },
    )
    live_values: dict[str, dict[tuple[int, int], dict[str, object]]] = {"Universe Registry": {}}
    live_formats: dict[str, dict[tuple[int, int], str | None]] = {"Universe Registry": {}}
    for definition in importer_value_cells(workbook):
        if definition.sheet != "Universe Registry":
            continue
        row, column = _cell_position(definition.address)
        cell = workbook.cell(definition.sheet, definition.address)
        if cell.kind == "inlineStr":
            effective: dict[str, object] = {"stringValue": cell.value}
        elif cell.value is not None:
            effective = {"numberValue": Decimal(cell.value)}
        else:
            effective = {}
        live_values[definition.sheet][(row, column)] = {"effectiveValue": effective}
        live_formats[definition.sheet][(row, column)] = None

    result = compare_semantic_values(workbook, live_values, number_formats=live_formats)

    assert result["differences_by_class"] == {}
    # The empty XLSX source states are fingerprinted separately from confirmed API blanks.
    assert result["snapshot_semantic_sha256"] != result["live_semantic_sha256"]


@pytest.mark.parametrize("address", ["D116", "F116"])
def test_membership_cells_on_unkeyed_registry_rows_are_not_imported(address: str) -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Universe Registry": {address: Cell(None, None, 'IF(TRUE,1,"")')}},
    )
    definition = ImporterValueCell(
        "Universe Registry", address, "identity_lifecycle_and_cached_ranks", "decimal"
    )

    assert _importer_cell_is_consumed(workbook, definition) is False


def test_unkeyed_membership_formula_does_not_create_importer_unavailability() -> None:
    formula = 'IF(TRUE,1,"")'
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Universe Registry": {"D116": Cell(None, None, formula)}},
    )
    definition = ImporterValueCell(
        "Universe Registry", "D116", "identity_lifecycle_and_cached_ranks", "decimal"
    )

    result = compare_semantic_values(
        workbook,
        {"Universe Registry": {(116, 4): {"userEnteredValue": {"formulaValue": formula}}}},
        number_formats={},
        definitions=[definition],
    )

    assert result["importer_semantic_relations"] == {"NOT_CONSUMED_BY_CURRENT_IMPORT": 1}
    if result["differences"]:
        assert result["differences"][0]["source_fidelity_review_required"] is False


@pytest.mark.parametrize("address", ["D5", "F5"])
def test_membership_cells_are_imported_when_registry_key_exists(address: str) -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Universe Registry": {"A5": Cell("SYN", "inlineStr"), address: Cell("0.1", "n")}},
    )
    definition = ImporterValueCell(
        "Universe Registry", address, "identity_lifecycle_and_cached_ranks", "decimal"
    )

    assert _importer_cell_is_consumed(workbook, definition) is True


def test_same_revision_formula_result_mismatch_is_a_candidate_not_asserted_cause() -> None:
    source = normalize_source_cell(Cell("1", "n", "A1*2"), "decimal")
    live, _source_type, _scale = live_cell_normalization(
        {"numberValue": Decimal("2")}, mode="decimal", has_formula=True
    )

    classification = _classification(
        source,
        live,
        mode="decimal",
        source_formula="A1*2",
        live_formula="A1*2",
        source_has_formula=True,
        live_has_formula=True,
        source_format="NUMBER",
        live_format="NUMBER",
    )

    assert classification == "STALE_XLSX_CACHE_CANDIDATE"


def test_dynamic_formula_mismatch_is_classified_as_live_recalculation_candidate() -> None:
    source = normalize_source_cell(Cell("1", "n", 'GOOGLEFINANCE("SYN")'), "decimal")
    live, _source_type, _scale = live_cell_normalization(
        {"numberValue": Decimal("2")}, mode="decimal", has_formula=True
    )

    classification = _classification(
        source,
        live,
        mode="decimal",
        source_formula='GOOGLEFINANCE("SYN")',
        live_formula='GOOGLEFINANCE("SYN")',
        source_has_formula=True,
        live_has_formula=True,
        source_format="NUMBER",
        live_format="NUMBER",
    )

    assert classification == "LIVE_CALCULATION_CHANGED_AFTER_EXPORT_CANDIDATE"


def test_date_formatting_and_formula_errors_are_separate_from_numeric_values() -> None:
    date_value = normalize_source_cell(
        Cell("45000", "n", number_format_type="DATE_TIME"), "excel_date", date_system="1900"
    )
    live_date, _, _ = live_cell_normalization(
        {"numberValue": Decimal("45000")},
        mode="excel_date",
        has_formula=False,
        number_format_type="DATE",
    )
    error = normalize_source_cell(Cell("#N/A", "e", "=NA()"), "decimal")
    live_error, _, _ = live_cell_normalization(
        {"errorValue": {"type": "N_A"}}, mode="decimal", has_formula=True
    )

    assert date_value.value == live_date.value
    assert (
        _classification(
            date_value,
            live_date,
            mode="excel_date",
            source_formula=None,
            live_formula=None,
            source_has_formula=False,
            live_has_formula=False,
            source_format="DATE_TIME",
            live_format="DATE",
        )
        == "MATCH"
    )
    assert (
        _classification(
            error,
            live_error,
            mode="decimal",
            source_formula="NA()",
            live_formula="NA()",
            source_has_formula=True,
            live_has_formula=True,
            source_format=None,
            live_format=None,
        )
        == "FORMULA_ERROR"
    )


def test_currency_identity_and_currency_format_mismatches_are_explicit() -> None:
    source_currency = normalize_source_cell(Cell("EUR", "inlineStr"), "currency")
    live_currency, _, _ = live_cell_normalization(
        {"stringValue": "USD"}, mode="currency", has_formula=False
    )
    source_amount = normalize_source_cell(
        Cell("123.45", "n", number_format_type="CURRENCY"), "decimal"
    )
    live_amount, _, _ = live_cell_normalization(
        {"numberValue": Decimal("123.45")},
        mode="decimal",
        has_formula=False,
        number_format_type="NUMBER",
    )

    assert (
        _classification(
            source_currency,
            live_currency,
            mode="currency",
            source_formula=None,
            live_formula=None,
            source_has_formula=False,
            live_has_formula=False,
            source_format="TEXT",
            live_format="TEXT",
        )
        == "CURRENCY_IDENTITY_MISMATCH"
    )
    assert (
        _classification(
            source_amount,
            live_amount,
            mode="decimal",
            source_formula=None,
            live_formula=None,
            source_has_formula=False,
            live_has_formula=False,
            source_format="CURRENCY",
            live_format="NUMBER",
        )
        == "CURRENCY_FORMATTING_MISMATCH"
    )


def test_xlsx_and_google_sheets_date_epochs_are_not_silently_conflated() -> None:
    source = normalize_source_cell(Cell("1", "n"), "excel_date", date_system="1900")
    live, _, _ = live_cell_normalization(
        {"numberValue": Decimal("1")},
        mode="excel_date",
        has_formula=False,
        number_format_type="DATE",
    )

    assert source.value == "1900-01-01"
    assert live.value == "1899-12-31"
    assert (
        _classification(
            source,
            live,
            mode="excel_date",
            source_formula=None,
            live_formula=None,
            source_has_formula=False,
            live_has_formula=False,
            source_format="DATE_TIME",
            live_format="DATE",
        )
        == "DATE_INTERPRETATION_MISMATCH"
    )


def test_exact_source_type_mismatch_is_not_misclassified_as_a_stale_formula_cache() -> None:
    source = normalize_source_cell(Cell("1", "n", "=A1"), "decimal")
    live, _, _ = live_cell_normalization({"stringValue": "1"}, mode="decimal", has_formula=True)

    assert (
        _classification(
            source,
            live,
            mode="decimal",
            source_formula="A1",
            live_formula="A1",
            source_has_formula=True,
            live_has_formula=True,
            source_format="NUMBER",
            live_format="NUMBER",
        )
        == "VALUE_TYPE_MISMATCH"
    )


def test_comparison_preserves_formula_value_axes_and_exact_private_evidence() -> None:
    exact_value = Decimal("123456789012345.1234567890123456789")
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "D5": Cell(str(exact_value), "n", " =A1*2 ", "0.00", "NUMBER"),
            }
        },
    )
    definition = ImporterValueCell(
        "Universe Registry", "D5", "identity_lifecycle_and_cached_ranks", "decimal"
    )

    result = compare_semantic_values(
        workbook,
        {
            "Universe Registry": {
                (5, 4): {
                    "userEnteredValue": {"formulaValue": "=A1*3"},
                    "effectiveValue": {"numberValue": exact_value},
                }
            }
        },
        number_formats={"Universe Registry": {(5, 4): "NUMBER"}},
        definitions=[definition],
    )

    difference = result["differences"][0]
    assert difference["classification"] == "FORMULA_DEFINITION_MISMATCH"
    assert difference["value_relation"] == "EXACT_TYPED_VALUE_MATCH"
    assert difference["formula_relation"] == "TEXT_DIFFERENCE_UNRESOLVED"
    assert (
        difference["importer_semantic_relation"]
        == "CURRENT_VALUE_MATCH_FORMULA_TEXT_DIFFERENCE_UNRESOLVED"
    )
    assert difference["source_fidelity_review_required"] is True
    assert difference["source_evidence"]["value_text"] == str(exact_value)
    assert difference["source_evidence"]["formula_text"] == " =A1*2 "
    assert difference["source_evidence"]["formula_text_for_comparison"] == "A1*2"
    assert difference["live_evidence"]["effective_value"]["numberValue"] == str(exact_value)
    assert difference["live_evidence"]["user_entered_value"]["formulaValue"] == "=A1*3"


def test_formula_wrapper_whitespace_is_normalized_but_formula_logic_is_not() -> None:
    assert (
        validation._formula_relation(
            validation._formula_text(" =A1*2 "), validation._formula_text("A1*2")
        )
        == "EXACT_TEXT_MATCH"
    )
    assert validation._formula_relation("A1*2", "SUM(A1,A1)") == "TEXT_DIFFERENCE_UNRESOLVED"


def test_shared_formula_translation_applies_absolute_and_relative_reference_rules() -> None:
    translated = validation._translate_shared_formula(
        "IF(A1=$B$2,\"A1\",'Price Feed'!C3)", "B1", "C2"
    )
    assert translated == "IF(B2=$B$2,\"A1\",'Price Feed'!D4)"
    assert validation._translate_shared_formula("SUM(A:A)", "B1", "B2") is None


def test_workbook_reader_preserves_ooxml_shared_formula_metadata() -> None:
    workbook_xml = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Universe Registry" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels_xml = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
        "</Relationships>"
    )
    sheet_xml = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="D1"><f t="shared" si="0" ref="D1:D2">C1*2</f>'
        '<v>2</v></c></row><row r="2"><c r="D2"><f t="shared" si="0"/><v>4</v>'
        "</c></row></sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    workbook = Workbook.read_bytes(buffer.getvalue(), lambda _name: True)
    cells = workbook.sheets["Universe Registry"]
    assert cells["D1"].formula_type == "shared"
    assert cells["D1"].formula_shared_index == "0"
    assert cells["D1"].formula_shared_ref == "D1:D2"
    assert cells["D2"].formula == ""
    assert validation._source_formula_map(workbook)[("Universe Registry", "D2")] == (
        "C2*2",
        "SHARED_TRANSLATED",
    )


def test_shared_formula_expansion_matches_live_formula_without_value_only_inference() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "D1": Cell(
                    "2",
                    "n",
                    "C1*2",
                    formula_type="shared",
                    formula_shared_index="0",
                    formula_shared_ref="D1:D2",
                ),
                "D2": Cell(
                    "4",
                    "n",
                    "",
                    formula_type="shared",
                    formula_shared_index="0",
                    formula_shared_ref="D1:D2",
                ),
            }
        },
    )
    definition = ImporterValueCell(
        "Universe Registry", "D2", "identity_lifecycle_and_cached_ranks", "decimal"
    )
    result = compare_semantic_values(
        workbook,
        {
            "Universe Registry": {
                (2, 4): {
                    "userEnteredValue": {"formulaValue": "=C2*2"},
                    "effectiveValue": {"numberValue": Decimal("4")},
                }
            }
        },
        number_formats={"Universe Registry": {(2, 4): "NUMBER"}},
        definitions=[definition],
    )

    assert result["differences"] == []
    assert result["formula_relations"] == {"EXACT_TEXT_MATCH": 1}


def test_unexpandable_shared_formula_is_an_explicit_formula_blocker() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A2": Cell("SYN", "inlineStr"),
                "D2": Cell(
                    "4",
                    "n",
                    "",
                    formula_type="shared",
                    formula_shared_index="missing-anchor",
                ),
            }
        },
    )
    definition = ImporterValueCell(
        "Universe Registry", "D2", "identity_lifecycle_and_cached_ranks", "decimal"
    )
    result = compare_semantic_values(
        workbook,
        {"Universe Registry": {(2, 4): {"effectiveValue": {"numberValue": Decimal("4")}}}},
        number_formats={},
        definitions=[definition],
    )
    assert result["differences"][0]["formula_relation"] == ("SHARED_FORMULA_EXPANSION_UNSUPPORTED")
    assert result["differences"][0]["source_fidelity_review_required"] is True


def test_score_evidence_completeness_compares_presence_without_coercing_payload() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"10Y Durability": {"A5": Cell("SYN", "inlineStr"), "C5": Cell("17", "inlineStr")}},
    )
    definition = ImporterValueCell("10Y Durability", "C5", "quality_assessments", "text")
    result = compare_semantic_values(
        workbook,
        {"10Y Durability": {(5, 3): {"effectiveValue": {"numberValue": Decimal("17")}}}},
        number_formats={},
        definitions=[definition],
    )

    difference = result["differences"][0]
    assert difference["value_relation"] == "TYPE_DIFFERENCE"
    assert difference["importer_semantic_relation"] == "EQUIVALENT_PRESENCE_ONLY"
    assert difference["canonical_value_changed"] is False
    assert difference["source_fidelity_review_required"] is False


def test_company_name_crosscheck_is_not_consumed_when_registry_name_exists() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell("Canonical", "inlineStr"),
            },
            "Compounder Quality": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell("Other", "inlineStr"),
            },
        },
    )
    definition = ImporterValueCell("Compounder Quality", "B5", "quality_assessments", "text")
    result = compare_semantic_values(
        workbook,
        {"Compounder Quality": {(5, 2): {"effectiveValue": {"stringValue": "Changed"}}}},
        number_formats={},
        definitions=[definition],
    )

    assert result["differences"][0]["importer_semantic_relation"] == (
        "NOT_CONSUMED_BY_CURRENT_IMPORT"
    )
    assert result["differences"][0]["canonical_value_changed"] is False


def test_blank_registry_name_uses_exact_compounder_fallback_without_blocking() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell(None, "n", 'IF(A5="","",A5)'),
            },
            "Compounder Quality": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell("Canonical name", "inlineStr"),
            },
        },
    )
    definition = ImporterValueCell(
        "Universe Registry", "B5", "identity_lifecycle_and_cached_ranks", "text"
    )
    result = compare_semantic_values(
        workbook,
        {
            "Universe Registry": {
                (5, 2): {
                    "userEnteredValue": {"formulaValue": 'IF(A5="","",A5)'},
                }
            }
        },
        number_formats={},
        definitions=[definition],
    )
    assert result["differences"][0]["importer_semantic_relation"] == (
        "NOT_CONSUMED_BY_CURRENT_IMPORT"
    )
    assert result["differences"][0]["source_fidelity_review_required"] is False


@pytest.mark.parametrize(
    "row_class,listing_key,expected_relation",
    [
        ("OTHER", "TSM-ADR", "NOT_CONSUMED_BY_CURRENT_IMPORT"),
        ("AUX", "TSM-ADR", "IMPORTER_VALUE_DIFFERENCE"),
        ("AUX", "UNSUPPORTED", "NOT_CONSUMED_BY_CURRENT_IMPORT"),
    ],
)
def test_price_feed_identity_is_scoped_to_supported_auxiliary_rows(
    row_class: str, listing_key: str, expected_relation: str
) -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Price Feed": {
                "A5": Cell(row_class, "inlineStr"),
                "C5": Cell(listing_key, "inlineStr"),
                "D5": Cell("XETR:OLD", "inlineStr"),
            }
        },
    )
    definition = ImporterValueCell("Price Feed", "D5", "listing_identity_crosswalk", "text")
    result = compare_semantic_values(
        workbook,
        {"Price Feed": {(5, 4): {"effectiveValue": {"stringValue": "XETR:NEW"}}}},
        number_formats={},
        definitions=[definition],
    )

    assert result["differences"][0]["importer_semantic_relation"] == expected_relation
    assert result["differences"][0]["canonical_value_changed"] == (
        expected_relation == "IMPORTER_VALUE_DIFFERENCE"
    )


def test_unavailable_price_feed_class_for_unsupported_key_is_not_imported() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Price Feed": {
                "A5": Cell(None, "str", 'IF(C5="","","STOCK")'),
                "C5": Cell("UNSUPPORTED", "inlineStr"),
            }
        },
    )
    definition = ImporterValueCell("Price Feed", "A5", "listing_identity_crosswalk", "text")
    result = compare_semantic_values(
        workbook,
        {"Price Feed": {(5, 1): {"effectiveValue": {}}}},
        number_formats={},
        definitions=[definition],
    )
    assert result["differences"][0]["importer_semantic_relation"] == (
        "NOT_CONSUMED_BY_CURRENT_IMPORT"
    )


def test_missing_legacy_rank_is_preserved_as_explicit_unavailable_status() -> None:
    formula = 'IF(A5="","",1)'
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "L5": Cell(None, "n", formula),
            }
        },
    )
    definition = ImporterValueCell(
        "Universe Registry", "L5", "identity_lifecycle_and_cached_ranks", "decimal"
    )
    result = compare_semantic_values(
        workbook,
        {
            "Universe Registry": {
                (5, 12): {"userEnteredValue": {"formulaValue": formula}, "effectiveValue": {}}
            }
        },
        number_formats={},
        definitions=[definition],
    )
    difference = result["differences"][0]
    assert difference["importer_semantic_relation"] == "EXPLICIT_UNAVAILABLE_RANK"
    assert difference["canonical_value_changed"] is False
    assert difference["source_fidelity_review_required"] is False


def test_blank_missing_are_equivalent_absence_but_zero_remains_a_value() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Target Architecture": {"D5": Cell("", "inlineStr")}},
    )
    definition = ImporterValueCell("Target Architecture", "D5", "strategic_targets", "decimal")
    absence = compare_semantic_values(
        workbook,
        {},
        number_formats={},
        definitions=[definition],
    )
    zero = compare_semantic_values(
        workbook,
        {"Target Architecture": {(5, 4): {"effectiveValue": {"numberValue": Decimal("0")}}}},
        number_formats={},
        definitions=[definition],
    )

    assert absence["differences"][0]["value_relation"] == "ABSENCE_REPRESENTATION_DIFFERENCE"
    assert absence["differences"][0]["importer_semantic_relation"] == "EQUIVALENT_ABSENCE"
    assert zero["differences"][0]["importer_semantic_relation"] == "IMPORTER_VALUE_DIFFERENCE"
    assert zero["differences"][0]["canonical_value_changed"] is True


def test_confirmed_sparse_grid_preserves_omitted_and_empty_value_states() -> None:
    response = {
        "sheets": [
            {
                "properties": {"title": "Data"},
                "data": [
                    {
                        "startRow": 0,
                        "startColumn": 0,
                        "rowMetadata": [{}, {}, {}, {}],
                        "columnMetadata": [{}, {}, {}],
                        "rowData": [
                            {
                                "values": [
                                    {
                                        "userEnteredValue": {"numberValue": 0},
                                        "effectiveValue": {"numberValue": 0},
                                    }
                                ]
                            },
                            {
                                "values": [
                                    {},
                                    {},
                                    {
                                        "userEnteredValue": {"formulaValue": '=IF(TRUE,"",1)'},
                                        "effectiveValue": {"stringValue": ""},
                                    },
                                ]
                            },
                        ],
                    }
                ],
            }
        ]
    }

    values, _formats, sheets, presence, stats = validation._cell_grid_index(
        response, [("Data", "'Data'!A1:C4", 12)]
    )

    assert sheets == {"Data"}
    assert values["Data"][(1, 1)]["effectiveValue"]["numberValue"] == 0
    assert presence["Data"][(1, 2)] == "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE"
    assert presence["Data"][(2, 1)] == "EXPLICIT_EMPTY_CELL_DATA"
    assert presence["Data"][(2, 3)] == "CELL_VALUE_DATA_PRESENT"
    assert stats["grid_ranges_confirmed"] == 1
    assert stats["coordinates_covered"] == 12
    assert stats["cell_data_returned"] == 4
    assert stats["omitted_cell_data_reconstructed"] == 8


def test_grid_accepts_omitted_default_zero_origin_and_empty_dimension_metadata() -> None:
    response = {
        "sheets": [
            {
                "properties": {"title": "Data"},
                "data": [{"rowData": [{"values": [{"effectiveValue": {"numberValue": 0}}]}]}],
            }
        ]
    }

    values, _formats, sheets, presence, stats = validation._cell_grid_index(
        response, [("Data", "'Data'!A1:B3", 6)]
    )

    assert sheets == {"Data"}
    assert values["Data"][(1, 1)]["effectiveValue"]["numberValue"] == 0
    assert presence["Data"][(1, 2)] == "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE"
    assert presence["Data"][(3, 2)] == "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE"
    assert stats["coordinates_covered"] == 6


def test_omitted_zero_origin_does_not_match_nonzero_requested_origin() -> None:
    response = {
        "sheets": [
            {"properties": {"title": "Data"}, "data": [{"rowData": []}]},
        ]
    }

    with pytest.raises(validation.ValueComparisonError, match="unexpected grid ranges"):
        validation._cell_grid_index(response, [("Data", "'Data'!A4:A5", 2)])


@pytest.mark.parametrize(
    "response, message",
    [
        ({"sheets": [{"properties": {"title": "Data"}, "data": []}]}, "omitted a requested"),
        (
            {
                "sheets": [
                    {
                        "properties": {"title": "Data"},
                        "data": [
                            {
                                "startRow": 0,
                                "startColumn": 0,
                                "rowMetadata": [{}],
                                "columnMetadata": [{}],
                                "rowData": [],
                            }
                        ],
                    }
                ]
            },
            "truncated row-range metadata",
        ),
        (
            {
                "sheets": [
                    {
                        "properties": {"title": "Data"},
                        "data": [
                            {
                                "startRow": 0,
                                "startColumn": 0,
                                "rowMetadata": [{}],
                                "columnMetadata": [{}, {}],
                                "rowData": [],
                            }
                        ],
                    }
                ]
            },
            "truncated column-range metadata",
        ),
        (
            {
                "sheets": [
                    {
                        "properties": {"title": "Data"},
                        "data": [
                            {
                                "startRow": 0,
                                "startColumn": 0,
                                "rowMetadata": [{}],
                                "columnMetadata": [{}],
                                "rowData": [{"values": [{}, {}]}],
                            }
                        ],
                    }
                ]
            },
            "oversized cells",
        ),
    ],
)
def test_grid_response_must_cover_requested_range_before_reconstructing_absence(
    response: dict[str, Any], message: str
) -> None:
    requested = (
        ("Data", "'Data'!A1:A2", 2)
        if "row-range" in message
        else ("Data", "'Data'!A1:B1", 2)
        if "column-range" in message
        else ("Data", "'Data'!A1:A1", 1)
    )
    with pytest.raises(validation.ValueComparisonError, match=message):
        if "column-range" in message:
            requested = ("Data", "'Data'!A1:C1", 3)
        validation._cell_grid_index(response, [requested])


def test_duplicate_or_missing_grid_coordinates_fail_closed() -> None:
    grid = {
        "startRow": 0,
        "startColumn": 0,
        "rowMetadata": [{}],
        "columnMetadata": [{}],
        "rowData": [],
    }
    duplicate = {
        "sheets": [
            {"properties": {"title": "Data"}, "data": [grid, grid]},
        ]
    }
    missing_start = {
        "sheets": [
            {
                "properties": {"title": "Data"},
                "data": [{"rowMetadata": [{}], "columnMetadata": [{}], "rowData": []}],
            }
        ]
    }
    with pytest.raises(validation.ValueComparisonError, match="unexpected grid ranges"):
        validation._cell_grid_index(duplicate, [("Data", "'Data'!A1:A1", 1)])
    with pytest.raises(validation.ValueComparisonError, match="unexpected grid ranges"):
        validation._cell_grid_index(missing_start, [("Data", "'Data'!A4:A4", 1)])


def test_empty_string_and_formula_empty_string_are_distinct_from_verified_blank() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Universe Registry": {"A5": Cell("SYN", "inlineStr"), "B5": Cell("", "str")}},
    )
    definition = ImporterValueCell(
        "Universe Registry", "B5", "identity_lifecycle_and_cached_ranks", "text"
    )
    positions = {"Universe Registry": {(5, 2): "OMITTED_CELL_DATA_IN_CONFIRMED_RANGE"}}
    omitted = compare_semantic_values(
        workbook,
        {},
        number_formats={},
        definitions=[definition],
        cell_presence=positions,
        include_source_value_cells=True,
    )
    literal_empty = compare_semantic_values(
        workbook,
        {"Universe Registry": {(5, 2): {"userEnteredValue": {"stringValue": ""}}}},
        number_formats={},
        definitions=[definition],
        cell_presence={"Universe Registry": {(5, 2): "CELL_VALUE_DATA_PRESENT"}},
        include_source_value_cells=True,
    )
    formula_empty = compare_semantic_values(
        workbook,
        {
            "Universe Registry": {
                (5, 2): {
                    "userEnteredValue": {"formulaValue": '=IF(TRUE,"",1)'},
                    "effectiveValue": {"stringValue": ""},
                }
            }
        },
        number_formats={},
        definitions=[definition],
        cell_presence={"Universe Registry": {(5, 2): "CELL_VALUE_DATA_PRESENT"}},
        include_source_value_cells=True,
    )

    assert (
        omitted["canonical_source_cells"][0]["normalized"]["authoritative_live"]["state"] == "BLANK"
    )
    assert (
        literal_empty["canonical_source_cells"][0]["normalized"]["authoritative_live"]["state"]
        == "EMPTY_STRING"
    )
    assert (
        formula_empty["canonical_source_cells"][0]["normalized"]["authoritative_live"]["state"]
        == "FORMULA_EMPTY_STRING"
    )


def test_contextual_empty_policy_uses_live_peer_values_and_keeps_zero_present() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Target Architecture": {"A5": Cell("SYN", "inlineStr"), "D5": Cell("", "str")}},
    )
    definition = ImporterValueCell("Target Architecture", "A5", "strategic_targets", "ticker")
    live_values: dict[str, dict[tuple[int, int], dict[str, Any]]] = {
        "Target Architecture": {
            (5, 1): {
                "userEnteredValue": {"stringValue": "SYN"},
                "effectiveValue": {"stringValue": "SYN"},
            },
            (5, 4): {
                "userEnteredValue": {"numberValue": Decimal("0")},
                "effectiveValue": {"numberValue": Decimal("0")},
            },
        }
    }

    assert importer_empty_value_policy(workbook, definition) == "CANONICAL_IMPORTER_VALIDATES"
    assert (
        importer_empty_value_policy(workbook, definition, live_values=live_values)
        == "REQUIRED_NONEMPTY"
    )


def test_numeric_value_and_storage_type_differences_are_both_reported() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Target Architecture": {"D5": Cell("0.15", "inlineStr")}},
    )
    definition = ImporterValueCell("Target Architecture", "D5", "strategic_targets", "decimal")
    result = compare_semantic_values(
        workbook,
        {"Target Architecture": {(5, 4): {"effectiveValue": {"numberValue": Decimal("0.2")}}}},
        number_formats={},
        definitions=[definition],
    )

    difference = result["differences"][0]
    assert difference["value_relation"] == "VALUE_AND_TYPE_DIFFERENCE"
    assert difference["importer_semantic_relation"] == "IMPORTER_VALUE_AND_TYPE_DIFFERENCE"
    assert difference["canonical_value_changed"] is True


@pytest.mark.parametrize(
    "source_format,live_format", [("CURRENCY", "NUMBER"), ("PERCENT", "NUMBER")]
)
def test_number_format_differences_do_not_rescale_exact_decimal_values(
    source_format: str, live_format: str
) -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Target Architecture": {"D5": Cell("0.15", "n", number_format_type=source_format)}},
    )
    definition = ImporterValueCell("Target Architecture", "D5", "strategic_targets", "decimal")
    result = compare_semantic_values(
        workbook,
        {"Target Architecture": {(5, 4): {"effectiveValue": {"numberValue": Decimal("0.15")}}}},
        number_formats={"Target Architecture": {(5, 4): live_format}},
        definitions=[definition],
    )

    difference = result["differences"][0]
    assert difference["classification"] in {
        "CURRENCY_FORMATTING_MISMATCH",
        "PERCENT_FORMATTING_MISMATCH",
    }
    assert difference["value_relation"] == "EXACT_TYPED_VALUE_MATCH"
    assert difference["importer_semantic_relation"] == "EQUIVALENT_VALUE_FORMAT_ONLY"
    assert difference["canonical_value_changed"] is False


def test_same_formula_with_different_cached_value_remains_a_stale_cache_candidate() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "D5": Cell("1", "n", "A1*2"),
            }
        },
    )
    definition = ImporterValueCell(
        "Universe Registry", "D5", "identity_lifecycle_and_cached_ranks", "decimal"
    )
    result = compare_semantic_values(
        workbook,
        {
            "Universe Registry": {
                (5, 4): {
                    "userEnteredValue": {"formulaValue": "=A1*2"},
                    "effectiveValue": {"numberValue": Decimal("2")},
                }
            }
        },
        number_formats={},
        definitions=[definition],
    )

    difference = result["differences"][0]
    assert difference["classification"] == "STALE_XLSX_CACHE_CANDIDATE"
    assert difference["formula_relation"] == "EXACT_TEXT_MATCH"
    assert difference["value_relation"] == "VALUE_DIFFERENCE"
    assert difference["canonical_value_changed"] is True


def test_private_report_writes_versioned_exception_ledger(tmp_path: Path) -> None:
    store = cast(Any, SimpleNamespace(root=tmp_path))
    validation._write_private_report(
        store,
        "synthetic-run",
        {
            "run_id": "synthetic-run",
            "scope": "canonical-bootstrap",
            "status": "COMPARED",
            "differences": [
                {
                    "cell": "D5",
                    "source_evidence": {"value_text": "0.1234567890123456789"},
                    "live_evidence": {"effective_value": {"numberValue": "0.1234567890123456789"}},
                }
            ],
        },
    )

    reports = list((tmp_path / "value-comparisons").glob("synthetic-run-*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["report_version"] == validation.COMPARISON_REPORT_VERSION
    assert report["comparison_contract_version"] == validation.COMPARISON_CONTRACT_VERSION
    assert report["exception_ledger"]["version"] == validation.EXCEPTION_LEDGER_VERSION
    assert report["exception_ledger"]["record_count"] == 1
    assert report["scope"] == "canonical-bootstrap"
    assert report["exception_ledger"]["records"][0]["source_evidence"]["value_text"] == (
        "0.1234567890123456789"
    )
    assert report["comparison_started_at_utc"]
    assert report["comparison_completed_at_utc"]
    assert "differences" not in report


def test_started_comparison_attempt_is_durable_and_uncompleted(tmp_path: Path) -> None:
    store = cast(Any, SimpleNamespace(root=tmp_path))
    validation._write_private_report(
        store,
        "synthetic-run",
        {
            "run_id": "synthetic-run",
            "scope": "canonical-bootstrap",
            "status": "COMPARISON_ATTEMPT_STARTED",
        },
        comparison_attempt_id="a" * 32,
    )

    path = next((tmp_path / "value-comparisons").glob("synthetic-run-*.json"))
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["comparison_attempt_id"] == "a" * 32
    assert report["comparison_started_at_utc"]
    assert "comparison_completed_at_utc" not in report


def test_bounded_live_ranges_exclude_unrelated_formula_cells() -> None:
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "D5": Cell("0.1", "n"),
                "Z1000": Cell("99", "n", "SUM(A1:A9)"),
            }
        },
    )

    ranges = _ranges_for_workbook(workbook)

    assert all("Z1000" not in cell_range for _, cell_range, _ in ranges)
    assert sum(area for _, _, area in ranges) < 100


def test_duplicate_ranges_are_deduplicated_and_chunk_order_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validation, "MAX_RANGES_PER_REQUEST", 2)
    monkeypatch.setattr(validation, "MAX_CELLS_PER_REQUEST", 10)
    ranges = [
        ("Data", "'Data'!A7:A12", 6),
        ("Data", "'Data'!A1:A4", 4),
        ("Data", "'Data'!A7:A12", 6),
        ("Data", "'Data'!A14:A20", 7),
        ("Data", "'Data'!A22:A24", 3),
    ]

    groups = _group_ranges(ranges)

    assert groups == [
        [("Data", "'Data'!A1:A4", 4), ("Data", "'Data'!A7:A12", 6)],
        [("Data", "'Data'!A14:A20", 7), ("Data", "'Data'!A22:A24", 3)],
    ]


def test_google_range_retry_is_bounded_and_observable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, status_code: int, retry_after: str | None = None) -> None:
            self.status_code = status_code
            self.headers = {"Retry-After": retry_after} if retry_after is not None else {}

    class Session:
        def __init__(self) -> None:
            self.responses = iter([Response(429, "0"), Response(200)])
            self.calls = 0

        def get(self, *_args: Any, **_kwargs: Any) -> Response:
            self.calls += 1
            return next(self.responses)

    sleeps: list[float] = []
    requests: list[None] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    session = Session()

    def count_request() -> None:
        requests.append(None)

    response = validation._get_with_retry(
        session,
        "https://sheets.googleapis.com/v4/spreadsheets/synthetic",
        params={},
        on_request=count_request,
    )

    assert response.status_code == 200
    assert session.calls == 2
    assert len(requests) == 2
    assert sleeps == [validation.REQUEST_SPACING_SECONDS]


def test_large_bootstrap_workbook_is_planned_without_sparse_cell_rescanning() -> None:
    cells: dict[str, Cell] = {}
    for row in range(5, 605):
        for column, value in {
            "A": f"SYN{row}",
            "B": f"Synthetic {row}",
            "C": "Watchlist",
            "D": "0",
            "F": "0.1",
            "J": "1",
            "L": "2",
            "M": "3",
        }.items():
            kind = "inlineStr" if column in {"A", "B", "C"} else "n"
            cells[f"{column}{row}"] = Cell(value, kind)
    workbook = Workbook(Path("large.xlsx"), "a" * 64, {"Universe Registry": cells})

    plan = validation._validation_plan(workbook, "canonical-bootstrap")

    # Two fixed bootstrap controls are always compared in addition to populated rows.
    assert plan["metrics"]["required_cells"] == 600 * 8 + 2
    assert plan["metrics"]["ranges"] > 1_000
    assert plan["metrics"]["chunks_per_pass"] > 1
    assert plan["metrics"]["work_budget_exceeded"] == []


def test_bootstrap_scope_separates_optional_model_and_research_cells() -> None:
    workbook = Workbook(
        Path("scopes.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {"A5": Cell("SYN", "inlineStr")},
            "Model Contract": {"A5": Cell("Contract", "inlineStr")},
            "Estimate History": {"B2": Cell("SYN", "inlineStr")},
            "P-SYN": {"A7": Cell("Quality", "inlineStr"), "B7": Cell("4", "n")},
        },
    )

    required = validation._validation_plan(workbook, "canonical-bootstrap")
    optional = validation._validation_plan(workbook, "optional-model-research")
    complete = validation._validation_plan(workbook, "all-importers")

    required_domains = {item.domain for item in required["definitions"]}
    optional_domains = {item.domain for item in optional["definitions"]}
    assert required_domains <= validation.CANONICAL_BOOTSTRAP_DOMAINS
    assert optional_domains <= validation.OPTIONAL_MODEL_RESEARCH_DOMAINS
    assert required["metrics"]["optional_model_research_cells_excluded"] == len(
        optional["definitions"]
    )
    assert len(complete["definitions"]) == len(required["definitions"]) + len(
        optional["definitions"]
    )


def test_unclassified_importer_domain_blocks_instead_of_being_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = Workbook(Path("unknown-domain.xlsx"), "b" * 64, {})
    monkeypatch.setattr(
        validation,
        "importer_value_cells",
        lambda _workbook: [
            SimpleNamespace(sheet="Future", address="A1", domain="future_import_domain")
        ],
    )

    with pytest.raises(validation.ValueComparisonError, match="unclassified validation domain"):
        validation._validation_plan(workbook, "canonical-bootstrap")


def test_validation_plan_reports_budget_block_instead_of_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = Workbook(
        Path("over-budget.xlsx"),
        "b" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell("Synthetic", "inlineStr"),
            }
        },
    )
    monkeypatch.setattr(validation, "MAX_VALIDATION_CONTRACT_CELLS", 1)

    plan = validation._validation_plan(workbook, "canonical-bootstrap")

    # The importer contract also includes the fixed holdings-currency and target-total cells.
    assert plan["metrics"]["required_cells"] == 10
    assert plan["metrics"]["work_budget_exceeded"] == ["contract_cells"]


def test_over_budget_comparison_stops_before_any_live_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(
        monkeypatch,
        tmp_path,
        max_contract_cells=0,
    )

    assert result["status"] == "BLOCKED_VALIDATION_BUDGET_EXCEEDED"
    assert result["request_count"] == 0
    assert result["consistency_result"] == "NOT_STARTED"


def test_live_request_failure_reports_sanitized_chunk_progress() -> None:
    class ForbiddenResponse:
        status_code = 403
        headers: dict[str, str] = {}

    class Session:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, *_args: Any, **_kwargs: Any) -> ForbiddenResponse:
            self.calls += 1
            return ForbiddenResponse()

    session = Session()
    progress: dict[str, int] = {}
    with pytest.raises(validation.ProjectionReadError) as error:
        validation._read_live_projection(
            session,
            request_url="https://sheets.googleapis.com/v4/spreadsheets/synthetic",
            groups=[[("Data", "'Data'!A1:A2", 2)]],
            fields="spreadsheetId",
            expected_file_id="synthetic",
            progress=progress,
            sleeper=lambda _delay: None,
        )

    assert session.calls == 1
    assert error.value.progress["chunks_attempted"] == 1
    assert error.value.progress["chunks_completed"] == 0
    assert error.value.progress["api_requests"] == 1
    assert "403" in str(error.value)


def test_live_comparison_requires_stable_source_and_two_equal_value_reads() -> None:
    assert _comparison_status(source_stable=True, live_values_stable=True) == "COMPARED"
    assert _comparison_status(source_stable=True, live_values_stable=False) == (
        "LIVE_VALUES_CHANGED_DURING_COMPARISON"
    )
    assert _comparison_status(source_stable=False, live_values_stable=True) == (
        "SOURCE_CHANGED_DURING_COMPARISON"
    )
    assert (
        _comparison_status(
            source_stable=True,
            live_values_stable=True,
            live_cell_evidence_stable=False,
        )
        == "LIVE_CELL_EVIDENCE_CHANGED_DURING_COMPARISON"
    )


def test_native_sheet_without_drive_revision_uses_metadata_and_semantic_fence() -> None:
    manifest = {
        "source_modified_at": "2026-10-23T07:42:24.327Z",
        "source_revision": None,
        "source_checksum": None,
    }
    metadata: dict[str, Any] = {
        "id": "synthetic-file-id",
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "modifiedTime": "2026-10-23T07:42:24.327Z",
    }

    matched, protocol = _snapshot_metadata_fence(manifest, metadata)

    assert matched is True
    assert protocol == "NO_DRIVE_REVISION_SEMANTIC_FENCE"


def test_native_sheet_without_revision_can_pass_full_stable_live_comparison(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(monkeypatch, tmp_path)

    assert result["status"] == "COMPARED"
    assert result["consistency_protocol"] == "NO_DRIVE_REVISION_SEMANTIC_FENCE"
    assert result["source_revision_matches_snapshot"] is None
    assert result["source_metadata_matches_snapshot"] is True
    assert result["live_values_stable_across_reads"] is True
    assert result["live_formula_definitions_stable_across_reads"] is True
    assert result["live_source_cell_evidence_stable_across_reads"] is True
    assert result["scope"] == "canonical-bootstrap"
    assert result["required_cells"] == 1
    assert result["compared_cells"] == 1
    assert result["request_count"] == 4
    assert result["progress"]["first_pass"]["chunks_completed"] == 1
    assert result["progress"]["second_pass"]["chunks_completed"] == 1
    assert result["mismatch_classes"] == {}
    assert result["comparison_contract_version"] == validation.COMPARISON_CONTRACT_VERSION
    assert all(
        "rowMetadata" in fields and "columnMetadata" in fields
        for fields in result["requested_field_masks"]
    )
    assert "differences" not in result
    assert "exception_ledger" not in result


def test_one_rate_limiter_paces_metadata_and_both_complete_value_sweeps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(time, "sleep", sleeps.append)

    result = _run_mocked_comparison(monkeypatch, tmp_path)

    assert result["request_count"] == 4
    assert sleeps == [validation.REQUEST_SPACING_SECONDS] * 3


def test_initial_metadata_api_failure_returns_sanitized_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(monkeypatch, tmp_path, metadata_failure_at=1)

    assert result["status"] == "SOURCE_METADATA_READ_FAILED"
    assert result["request_count"] == 1
    assert result["progress"]["metadata_requests"] == 1
    assert result["consistency_result"] == "INCOMPLETE_NO_ACCEPTANCE"
    assert "canonical_source_bundle" not in result


def test_second_sweep_failure_keeps_first_sweep_comparison_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(monkeypatch, tmp_path, value_failure_at=2)

    assert result["status"] == "LIVE_REQUEST_FAILED"
    assert result["compared_cells"] == 1
    assert result["progress"]["first_pass"]["chunks_completed"] == 1
    assert result["progress"]["second_pass"]["failed_chunk"] == 1
    assert result["consistency_result"] == "INCOMPLETE_NO_ACCEPTANCE"
    assert "canonical_source_bundle" not in result


def test_final_metadata_api_failure_keeps_sweep_and_mismatch_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(monkeypatch, tmp_path, metadata_failure_at=2)

    assert result["status"] == "SOURCE_METADATA_RECHECK_FAILED"
    assert result["compared_cells"] == 1
    assert result["request_count"] == 4
    assert result["progress"]["first_pass"]["chunks_completed"] == 1
    assert result["progress"]["second_pass"]["chunks_completed"] == 1
    assert result["consistency_result"] == "INCOMPLETE_NO_ACCEPTANCE"


def test_concurrent_importer_value_change_blocks_live_comparison(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(
        monkeypatch,
        tmp_path,
        second_value_hash="f" * 64,
    )

    assert result["status"] == "LIVE_VALUES_CHANGED_DURING_COMPARISON"
    assert result["live_values_stable_across_reads"] is False
    assert result["canonical_source_bundle"]["status"] == "NOT_CAPTURED_CONSISTENCY_FAILED"


def test_concurrent_formula_definition_change_blocks_even_when_values_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(
        monkeypatch,
        tmp_path,
        second_formula_hash="f" * 64,
    )

    assert result["status"] == "LIVE_FORMULAS_CHANGED_DURING_COMPARISON"
    assert result["live_values_stable_across_reads"] is True
    assert result["live_formula_definitions_stable_across_reads"] is False
    assert result["canonical_source_bundle"]["status"] == "NOT_CAPTURED_CONSISTENCY_FAILED"


def test_changed_blank_presence_state_between_reads_blocks_source_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(
        monkeypatch,
        tmp_path,
        second_evidence_hash="9" * 64,
    )

    assert result["status"] == "LIVE_CELL_EVIDENCE_CHANGED_DURING_COMPARISON"
    assert result["live_source_cell_evidence_stable_across_reads"] is False
    assert result["canonical_source_bundle"]["status"] == "NOT_CAPTURED_CONSISTENCY_FAILED"


def test_missing_live_importer_cell_blocks_bundle_even_when_other_chunks_are_stable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(
        monkeypatch,
        tmp_path,
        second_missing_live_cells=1,
    )

    assert result["status"] == "LIVE_REQUIRED_IMPORTER_CELLS_MISSING"
    assert result["canonical_source_bundle"]["status"] == "NOT_CAPTURED_CONSISTENCY_FAILED"


def test_snapshot_without_modification_metadata_fails_closed() -> None:
    matched, protocol = _snapshot_metadata_fence(
        {"source_modified_at": None, "source_revision": None},
        {
            "id": "synthetic-file-id",
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "modifiedTime": None,
        },
    )

    assert matched is False
    assert protocol == "SNAPSHOT_MODIFICATION_TIME_MISSING"


def test_snapshot_revision_or_checksum_mismatch_fails_closed() -> None:
    metadata = {
        "id": "synthetic-file-id",
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "modifiedTime": "2026-10-23T07:42:24.327Z",
        "headRevisionId": "different-revision",
        "md5Checksum": "different-checksum",
    }

    revision_matches, revision_reason = _snapshot_metadata_fence(
        {
            "source_modified_at": "2026-10-23T07:42:24.327Z",
            "source_revision": "expected-revision",
            "source_checksum": "expected-checksum",
        },
        metadata,
    )
    checksum_matches, checksum_reason = _snapshot_metadata_fence(
        {
            "source_modified_at": "2026-10-23T07:42:24.327Z",
            "source_revision": "different-revision",
            "source_checksum": "expected-checksum",
        },
        metadata,
    )

    assert revision_matches is False
    assert revision_reason == "REVISION_METADATA_MISMATCH"
    assert checksum_matches is False
    assert checksum_reason == "SOURCE_CHECKSUM_MISMATCH"


def test_source_metadata_change_after_live_reads_blocks_comparison(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_mocked_comparison(
        monkeypatch,
        tmp_path,
        second_metadata={"modifiedTime": "2026-10-24T07:42:24.327Z"},
    )

    assert result["status"] == "SOURCE_CHANGED_DURING_COMPARISON"
    assert result["source_stable_during_comparison"] is False


def _run_mocked_comparison(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    second_value_hash: str | None = None,
    second_formula_hash: str | None = None,
    second_evidence_hash: str | None = None,
    second_missing_live_cells: int = 0,
    second_metadata: dict[str, object] | None = None,
    max_contract_cells: int | None = None,
    metadata_failure_at: int | None = None,
    value_failure_at: int | None = None,
) -> dict[str, Any]:
    file_id = "synthetic-file-id"
    modified_at = "2026-10-23T07:42:24.327Z"
    semantic_hash = "c" * 64
    workbook = Workbook(
        Path("frozen.xlsx"),
        "a" * 64,
        {"Universe Registry": {"A5": Cell("SYN", "inlineStr")}},
    )
    manifest = {
        "profile": "portfolio",
        "status": "ACQUIRED_REVIEW_REQUIRED",
        "semantic_fingerprint_version": "portfolio-import-values-v2",
        "semantic_sha256": semantic_hash,
        "artifact_sha256": "b" * 64,
        "blob_path": f"blobs/sha256/{'b' * 64}/workbook.xlsx",
        "source_identity_sha256": hashlib.sha256(f"google-drive:{file_id}".encode()).hexdigest(),
        "source_mime_type": "application/vnd.google-apps.spreadsheet",
        "source_revision": None,
        "source_modified_at": modified_at,
        "source_checksum": None,
    }
    metadata = {
        "id": file_id,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "modifiedTime": modified_at,
    }
    responses = [
        {
            "cells_compared": 1,
            "differences_by_class": {},
            "snapshot_semantic_sha256": semantic_hash,
            "live_semantic_sha256": "d" * 64,
            "snapshot_formula_definitions_sha256": "e" * 64,
            "live_formula_definitions_sha256": "e" * 64,
            "live_cell_evidence_sha256": "f" * 64,
        },
        {
            "cells_compared": 1,
            "differences_by_class": {},
            "snapshot_semantic_sha256": semantic_hash,
            "live_semantic_sha256": second_value_hash or "d" * 64,
            "snapshot_formula_definitions_sha256": "e" * 64,
            "live_formula_definitions_sha256": second_formula_hash or "e" * 64,
            "live_cell_evidence_sha256": second_evidence_hash or "f" * 64,
            "required_live_cells_missing": second_missing_live_cells,
        },
    ]

    if max_contract_cells is not None:
        monkeypatch.setattr(validation, "MAX_VALIDATION_CONTRACT_CELLS", max_contract_cells)

    monkeypatch.setattr(validation, "_read_snapshot", lambda _store, _run_id: (manifest, b"xlsx"))
    monkeypatch.setattr(validation, "_google_source", lambda _profile, _settings: (None, file_id))
    monkeypatch.setattr(
        Workbook,
        "read_bytes",
        classmethod(lambda _cls, _payload, _include, source_name=None: workbook),
    )
    monkeypatch.setattr(
        "portfolio_api.workbook_semantics.semantic_fingerprint",
        lambda _workbook: (semantic_hash, {}),
    )
    monkeypatch.setattr(
        validation,
        "importer_value_cells",
        lambda _workbook: [
            SimpleNamespace(
                sheet="Universe Registry",
                address="A5",
                domain="identity_lifecycle_and_cached_ranks",
            )
        ],
    )
    monkeypatch.setattr(
        validation,
        "_ranges_for_workbook",
        lambda _workbook, _definitions=None: [
            ("Universe Registry", "'Universe Registry'!A5:A5", 1)
        ],
    )
    monkeypatch.setattr(validation, "_group_ranges", lambda ranges: [ranges])
    value_reads = 0
    requested_field_masks: list[str] = []

    def read_live_projection(
        *_args: Any, **kwargs: Any
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        set[str],
        dict[str, dict[tuple[int, int], str]],
    ]:
        nonlocal value_reads
        value_reads += 1
        requested_field_masks.append(kwargs["fields"])
        kwargs["on_request"]()
        progress = kwargs["progress"]
        progress.update(
            {
                "chunks_total": 1,
                "chunks_attempted": 1,
                "chunks_completed": 1,
                "ranges_total": 1,
                "ranges_completed": 1,
                "requested_cells_total": 1,
                "requested_cells_completed": 1,
                "cells_returned": 1,
                "api_requests": 1,
            }
        )
        if value_failure_at == value_reads:
            progress["chunks_completed"] = 0
            progress["failed_chunk"] = 1
            raise validation.ProjectionReadError(
                "Google Sheets values returned HTTP 403.", dict(progress)
            )
        return (
            {},
            {},
            {"Universe Registry"},
            {"Universe Registry": {(5, 1): "CELL_VALUE_DATA_PRESENT"}},
        )

    monkeypatch.setattr(validation, "_read_live_projection", read_live_projection)
    monkeypatch.setattr(
        validation,
        "compare_semantic_values",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    final_metadata: dict[str, Any] = {**metadata, **(second_metadata or {})}
    metadata_reads: Any = iter([metadata, final_metadata])
    metadata_read_count = 0

    def read_metadata(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal metadata_read_count
        metadata_read_count += 1
        kwargs["on_request"]()
        if metadata_failure_at == metadata_read_count:
            raise validation.ValueComparisonError("Google Drive metadata returned HTTP 503.")
        return next(metadata_reads)

    monkeypatch.setattr(validation, "_metadata", read_metadata)
    monkeypatch.setattr(validation, "_write_private_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "portfolio_api.workbook_sources.load_google_sheets_readonly_session",
        lambda _path: object(),
    )

    settings = SimpleNamespace(google_sheets_service_account_file=tmp_path / "service-account.json")
    return validation.compare_snapshot(
        run_id="a" * 32,
        store=cast(SnapshotStore, object()),
        settings=cast(Settings, settings),
    ) | {"requested_field_masks": requested_field_masks}
