"""Deterministic source-value semantics are independent of XLSX package bytes."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from portfolio_api.consensus_estimates import _excel_date
from portfolio_api.domain.models import ScoreAssessmentStatus, ScoreDimension
from portfolio_api.legacy_import import (
    Cell,
    ImportPlan,
    Workbook,
    _classify_number_format,
    _load_targets,
    _score_value,
)
from portfolio_api.workbook_semantics import (
    importer_field_semantics,
    importer_source_role,
    importer_value_cells,
    normalize_source_cell,
    semantic_fingerprint,
    semantic_projection,
)


def test_missing_zero_and_formula_cache_empty_are_distinct() -> None:
    missing = normalize_source_cell(Cell(), "decimal")
    explicit_zero = normalize_source_cell(Cell("0", "n"), "decimal")
    empty_formula = normalize_source_cell(Cell(None, "n", "SUM(A1:A2)"), "decimal")

    assert missing.state == "MISSING"
    assert explicit_zero.state == "VALUE"
    assert explicit_zero.value == "0"
    assert empty_formula.state == "FORMULA_CACHE_EMPTY"
    assert (
        len(
            {
                missing.payload().__repr__(),
                explicit_zero.payload().__repr__(),
                empty_formula.payload().__repr__(),
            }
        )
        == 3
    )


def test_importer_cell_discovery_keeps_formula_only_rows_and_skips_blank_rows() -> None:
    workbook = Workbook(
        Path("rows.xlsx"),
        "a" * 64,
        {
            "Universe Registry": {
                "D5": Cell(None, "n", "=SUM(A1:A4)"),
                "A6": Cell(),
                "Z1000": Cell("unrelated", "inlineStr"),
            }
        },
    )

    selected = {
        item.address for item in importer_value_cells(workbook) if item.sheet == "Universe Registry"
    }

    assert selected == {f"{column}5" for column in ("A", "B", "C", "D", "F", "J", "L", "M")}


def test_decimal_values_are_normalized_without_float_or_context_rounding() -> None:
    precise = "0.123456789012345678901234567890123456789"
    normalized = normalize_source_cell(Cell(precise, "n"), "decimal")
    rounded_neighbor = normalize_source_cell(
        Cell("0.123456789012345678901234567890123456788", "n"), "decimal"
    )

    assert normalized.value == precise
    assert normalized != rounded_neighbor


def test_numeric_text_boolean_and_currency_identity_remain_explicit() -> None:
    number = normalize_source_cell(Cell("100", "n"), "decimal")
    numeric_text = normalize_source_cell(Cell("100", "str"), "decimal")
    boolean = normalize_source_cell(Cell("1", "b"), "decimal")
    usd = normalize_source_cell(Cell("USD", "inlineStr"), "currency")
    eur = normalize_source_cell(Cell("EUR", "inlineStr"), "currency")

    assert number.value == numeric_text.value == "100"
    assert number.source_type == "number"
    assert numeric_text.source_type == "text"
    assert boolean.state == "INVALID_SOURCE_TYPE"
    assert usd.value == "USD" and eur.value == "EUR"
    assert usd != eur


def test_currency_values_keep_listing_basis_without_conversion() -> None:
    workbook = Workbook(
        Path("currency.xlsx"),
        "e" * 64,
        {"Price Feed": {"A5": Cell("AUX", "inlineStr"), "C5": Cell("SPYY", "inlineStr")}},
    )
    currency = next(
        item
        for item in importer_value_cells(workbook)
        if item.sheet == "Price Feed" and item.address == "H5"
    )

    assert importer_field_semantics(currency) == (
        "Listing.quote_currency",
        "ISO currency identity; no conversion",
    )
    assert importer_source_role(currency, Cell("EUR", "inlineStr")) == (
        "legacy_listing_identity_crosswalk"
    )


def test_number_format_classifier_does_not_call_accounting_numbers_currency() -> None:
    assert _classify_number_format("#,##0.00;[Red](#,##0.00)") == "NUMBER"
    assert _classify_number_format("[$€-407] #,##0.00") == "CURRENCY"


def test_excel_date_system_is_applied_to_date_serials() -> None:
    serial_one = Cell("1", "n", number_format_type="DATE_TIME")

    assert normalize_source_cell(serial_one, "excel_date", date_system="1900").value == "1900-01-01"
    assert normalize_source_cell(serial_one, "excel_date", date_system="1904").value == "1904-01-02"
    assert normalize_source_cell(Cell("1", "n"), "excel_date").state == "VALUE"
    assert normalize_source_cell(Cell("date", "str"), "excel_date").state == "INVALID_DATE_TYPE"
    assert normalize_source_cell(Cell("60", "n"), "excel_date").state == "INVALID_DATE_SERIAL"
    assert normalize_source_cell(Cell("1.5", "n"), "excel_date").state == "INVALID_DATE_SERIAL"
    assert _excel_date("1", "1900").isoformat() == "1900-01-01"
    assert _excel_date("1", "1904").isoformat() == "1904-01-02"


def test_formula_empty_score_cache_is_invalid_null_not_a_missing_neutral_score() -> None:
    workbook = Workbook(Path("source.xlsx"), "e" * 64, {})
    plan = ImportPlan(
        workbook,
        workbook,
        datetime(2026, 10, 25, tzinfo=UTC),
        "source-digest",
    )

    score = _score_value(
        Cell(None, "n", "=AVERAGE(B1:F1)"),
        ScoreDimension.DURABILITY_10Y,
        Decimal(0),
        Decimal(5),
        "SYN",
        "source!G5",
        "Synthetic rationale",
        plan,
    )

    assert score is not None
    assert score.score is None
    assert score.status == ScoreAssessmentStatus.INVALID
    assert any(issue.code == "SCORE_FORMULA_CACHE_EMPTY" for issue in plan.issues)


def test_missing_target_control_total_blocks_target_import() -> None:
    workbook = Workbook(Path("source.xlsx"), "f" * 64, {})
    plan = ImportPlan(
        workbook,
        workbook,
        datetime(2026, 10, 25, tzinfo=UTC),
        "source-digest",
    )

    _load_targets(plan, {})

    assert plan.target_snapshot_total is None
    assert plan.target_importable is False
    assert any(issue.code == "TARGET_TOTAL_MISSING" for issue in plan.issues)


def test_semantic_fingerprint_ignores_binary_digest_but_keeps_imported_values() -> None:
    sheets = {
        "Universe Registry": {
            "A5": Cell("SYN", "inlineStr"),
            "B5": Cell("Synthetic Co", "inlineStr"),
            "C5": Cell("Watchlist", "inlineStr"),
            "D5": Cell("0", "n"),
            "F5": Cell("0", "n"),
            "J5": Cell(None),
            "L5": Cell(None),
            "M5": Cell(None),
        }
    }
    first = Workbook(Path("first.xlsx"), "a" * 64, sheets)
    repacked = Workbook(Path("repacked.xlsx"), "b" * 64, sheets)
    changed_zero_to_missing = Workbook(
        Path("changed.xlsx"),
        "c" * 64,
        {"Universe Registry": {**sheets["Universe Registry"], "D5": Cell()}},
    )

    first_fingerprint, _ = semantic_fingerprint(first)
    repacked_fingerprint, _ = semantic_fingerprint(repacked)
    changed_fingerprint, _ = semantic_fingerprint(changed_zero_to_missing)

    assert first.sha256 != repacked.sha256
    assert first_fingerprint == repacked_fingerprint
    assert first_fingerprint != changed_fingerprint


def test_same_cached_value_tracks_formula_versus_literal_origin() -> None:
    formula = Workbook(
        Path("formula.xlsx"),
        "1" * 64,
        {"Universe Registry": {"A5": Cell("SYN", "inlineStr"), "D5": Cell("0.2", "n", "=1/5")}},
    )
    literal = Workbook(
        Path("literal.xlsx"),
        "2" * 64,
        {"Universe Registry": {"A5": Cell("SYN", "inlineStr"), "D5": Cell("0.2", "n")}},
    )

    formula_digest, _ = semantic_fingerprint(formula)
    literal_digest, _ = semantic_fingerprint(literal)

    assert formula_digest != literal_digest


def test_semantic_diagnostics_only_count_importer_scoped_formula_errors() -> None:
    workbook = Workbook(
        Path("scoped.xlsx"),
        "d" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "D5": Cell("#DIV/0!", "e", "=1/0"),
                "J5": Cell(None, "n", "=RANK(A5,A:A)"),
                "Z100": Cell("#N/A", "e", "=NA()"),
            },
            "Unrelated Notes": {"A1": Cell("#N/A", "e", "=NA()")},
        },
    )

    _, diagnostics = semantic_fingerprint(workbook)

    assert diagnostics["by_domain"]["identity_lifecycle_and_cached_ranks"]["FORMULA_ERROR"] == 1
    assert (
        diagnostics["by_domain"]["identity_lifecycle_and_cached_ranks"]["FORMULA_CACHE_EMPTY"] == 1
    )
    issues = diagnostics["formula_cache_issues"]["identity_lifecycle_and_cached_ranks"]
    assert [item["cell"] for item in issues] == ["D5", "J5"]
    assert issues[0]["target_field"] == "legacy_rank_population.current_weight_input"
    assert issues[0]["source_role"] == "spreadsheet_derived_value"
    assert issues[0]["state"] == "FORMULA_ERROR"
    assert issues[1]["target_field"] == "RankingEntry.legacy_research_position"
    assert issues[1]["state"] == "FORMULA_CACHE_EMPTY"
    assert "Unrelated Notes" not in diagnostics["by_domain"]


def test_semantic_projection_documents_literal_derived_and_published_roles() -> None:
    workbook = Workbook(
        Path("roles.xlsx"),
        "f" * 64,
        {
            "Universe Registry": {
                "A5": Cell("SYN", "inlineStr"),
                "B5": Cell("Synthetic Co", "inlineStr"),
                "D5": Cell("0.2", "n", "=SUM(G5:G6)"),
            },
            "P-SYN": {
                "BA4": Cell("10", "n", "=DCF()"),
                "C20": Cell("Model Currency", "inlineStr"),
                "D20": Cell("USD", "inlineStr"),
            },
        },
    )

    projection, _ = semantic_projection(workbook)
    by_cell = {(item["sheet"], item["cell"]): item for item in projection}

    assert by_cell[("Universe Registry", "A5")]["source_role"] == "literal_workbook_input"
    assert by_cell[("Universe Registry", "D5")]["source_role"] == "spreadsheet_derived_value"
    assert by_cell[("Universe Registry", "D5")]["formula_present"] is True
    assert by_cell[("P-SYN", "BA4")]["source_role"] == "published_financial_model_output"
    assert by_cell[("P-SYN", "C20")]["target_field"] == ("ModelOutputSnapshot.model_currency")
    assert by_cell[("P-SYN", "D20")]["source_role"] == "published_model_currency_metadata"
