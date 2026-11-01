"""Importer-scoped semantic fingerprints for frozen portfolio workbook values.

This module deliberately excludes workbook formulas and values that no current
importer consumes. Formula *results* are represented as exact cached values; an
empty cache and an error remain distinct unavailable states.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any, Literal

SEMANTIC_FINGERPRINT_VERSION = "portfolio-import-values-v2"

SemanticMode = Literal[
    "text",
    "ticker",
    "currency",
    "decimal",
    "percent_decimal",
    "timestamp",
    "excel_date",
    "label",
]


@dataclass(frozen=True)
class ImporterValueCell:
    sheet: str
    address: str
    domain: str
    mode: SemanticMode


@dataclass(frozen=True)
class NormalizedCellValue:
    state: str
    value: str | None
    source_type: str
    decimal_scale: int | None = None

    def payload(self) -> dict[str, object]:
        return {
            "state": self.state,
            "value": self.value,
            "source_type": self.source_type,
        }


def _column_number(column: str) -> int:
    number = 0
    for character in column:
        number = number * 26 + ord(character.upper()) - 64
    return number


def column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _a1(address: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", address.upper())
    if match is None:
        raise ValueError("Invalid cell address in importer contract.")
    return match.group(1), int(match.group(2))


def _cell_present(cell: Any) -> bool:
    return cell.formula is not None or cell.value is not None


def _max_row(workbook: Any, sheet: str) -> int:
    addresses = workbook.sheets.get(sheet, {})
    return max((_a1(address)[1] for address in addresses), default=0)


def _append_table_cells(
    result: dict[tuple[str, str], ImporterValueCell],
    workbook: Any,
    *,
    sheet: str,
    domain: str,
    start_row: int,
    columns: tuple[tuple[str, SemanticMode], ...],
    anchor_column: str,
) -> None:
    selected_columns = {column for column, _ in columns}
    rows: dict[int, dict[str, Any]] = defaultdict(dict)
    for address, cell in workbook.sheets.get(sheet, {}).items():
        column, row_number = _a1(address)
        if row_number >= start_row and column in selected_columns:
            rows[row_number][address] = cell

    for row_number, row_cells in sorted(rows.items()):
        if not any(
            _cell_present(row_cells.get(f"{column}{row_number}", _BlankCell()))
            for column, _ in columns
        ):
            continue
        anchor = row_cells.get(f"{anchor_column}{row_number}", _BlankCell())
        # Preserve formula-only rows for validation, but skip arbitrary formatting rows.
        if (
            anchor.value is None
            and anchor.formula is None
            and not any(
                row_cells.get(f"{column}{row_number}", _BlankCell()).formula is not None
                for column, _ in columns
            )
        ):
            continue
        for column, mode in columns:
            address = f"{column}{row_number}"
            result[(sheet, address)] = ImporterValueCell(sheet, address, domain, mode)


class _BlankCell:
    value: str | None = None
    formula: str | None = None
    kind: str | None = None
    number_format_type: str | None = None
    number_format_code: str | None = None


def importer_value_cells(workbook: Any) -> list[ImporterValueCell]:
    """Return only fields read by the current portfolio import adapters."""
    result: dict[tuple[str, str], ImporterValueCell] = {}

    _append_table_cells(
        result,
        workbook,
        sheet="Universe Registry",
        domain="identity_lifecycle_and_cached_ranks",
        start_row=5,
        columns=(
            ("A", "ticker"),
            ("B", "text"),
            ("C", "text"),
            ("D", "decimal"),
            ("F", "decimal"),
            ("J", "decimal"),
            ("L", "decimal"),
            ("M", "decimal"),
        ),
        anchor_column="A",
    )
    _append_table_cells(
        result,
        workbook,
        sheet="Current Holdings",
        domain="holdings_and_cash",
        start_row=5,
        columns=(
            ("A", "text"),
            ("B", "ticker"),
            ("D", "ticker"),
            ("E", "decimal"),
            ("G", "currency"),
        ),
        anchor_column="A",
    )
    result[("Current Holdings", "L4")] = ImporterValueCell(
        "Current Holdings", "L4", "holdings_and_cash", "text"
    )
    _append_table_cells(
        result,
        workbook,
        sheet="Target Architecture",
        domain="strategic_targets",
        start_row=5,
        columns=(("A", "ticker"), ("D", "decimal")),
        anchor_column="A",
    )
    result[("Target Architecture", "P3")] = ImporterValueCell(
        "Target Architecture", "P3", "strategic_targets", "decimal"
    )

    _append_table_cells(
        result,
        workbook,
        sheet="10Y Durability",
        domain="quality_assessments",
        start_row=5,
        columns=tuple(
            (column, "decimal" if column == "G" else "text")
            for column in ("A", "B", "C", "D", "E", "F", "G", "K", "L", "M")
        ),
        anchor_column="A",
    )
    _append_table_cells(
        result,
        workbook,
        sheet="Compounder Quality",
        domain="quality_assessments",
        start_row=5,
        columns=tuple(
            (column, "decimal" if column == "G" else "text")
            for column in ("A", "B", "C", "D", "E", "F", "G", "K", "L", "M")
        ),
        anchor_column="A",
    )
    _append_table_cells(
        result,
        workbook,
        sheet="Price Feed",
        domain="listing_identity_crosswalk",
        start_row=5,
        columns=(("A", "text"), ("B", "text"), ("C", "ticker"), ("D", "text"), ("H", "currency")),
        anchor_column="A",
    )
    _append_table_cells(
        result,
        workbook,
        sheet="Candidate Ranking",
        domain="research_priority_inputs",
        start_row=2,
        columns=(("A", "decimal"), ("B", "ticker")),
        anchor_column="B",
    )
    result.update(
        {
            ("Model Contract", f"A{row}"): ImporterValueCell(
                "Model Contract", f"A{row}", "published_model_outputs", "label"
            )
            for row in range(5, 23)
        }
    )
    history_max = _max_row(workbook, "Model Revision History")
    for row in range(4, history_max + 1):
        cells = workbook.sheets.get("Model Revision History", {})
        anchor = cells.get(f"A{row}", _BlankCell())
        if anchor.value is None and anchor.formula is None:
            continue
        for column_number in range(1, 27):
            column = column_name(column_number)
            if column == "B":
                mode: SemanticMode = "timestamp"
            elif column == "C":
                mode = "ticker"
            elif column in {"M", "N", "O", "P", "Q", "R", "S", "T"}:
                mode = "percent_decimal" if column in {"M", "R", "S", "T"} else "decimal"
            else:
                mode = "text"
            address = f"{column}{row}"
            result[("Model Revision History", address)] = ImporterValueCell(
                "Model Revision History", address, "published_model_output_history", mode
            )

    _append_table_cells(
        result,
        workbook,
        sheet="Estimate History",
        domain="legacy_estimate_history",
        start_row=2,
        columns=(
            ("A", "excel_date"),
            ("B", "ticker"),
            ("D", "decimal"),
            ("E", "decimal"),
            ("F", "decimal"),
            ("G", "decimal"),
        ),
        anchor_column="B",
    )

    for sheet, cells in workbook.sheets.items():
        if not sheet.startswith(("P-", "W-", "C-")):
            continue
        score_cells: tuple[tuple[str, SemanticMode], ...] = (
            ("A7", "text"),
            ("B7", "decimal"),
            ("A8", "text"),
            ("B8", "decimal"),
        )
        for address, mode in score_cells:
            result[(sheet, address)] = ImporterValueCell(sheet, address, "investment_scores", mode)
        if sheet.startswith(("P-", "W-")):
            for row in range(3, 21):
                result[(sheet, f"AZ{row}")] = ImporterValueCell(
                    sheet, f"AZ{row}", "published_model_outputs", "label"
                )
                if row == 3:
                    output_mode: SemanticMode = "ticker"
                elif row in {19, 20}:
                    output_mode = "text"
                elif row in {7, 8, 9, 11, 12, 13, 14, 15}:
                    output_mode = "percent_decimal"
                else:
                    output_mode = "decimal"
                if row <= 15 or row >= 19:
                    result[(sheet, f"BA{row}")] = ImporterValueCell(
                        sheet, f"BA{row}", "published_model_outputs", output_mode
                    )

        # The current output importer searches labels anywhere on P/W model tabs for an
        # adjacent ISO currency code. Include only recognized pairs, not the full tab.
        if sheet.startswith(("P-", "W-")):
            for address, cell in cells.items():
                label = (cell.value or "").strip()
                if _currency_label(label):
                    column, row = _a1(address)
                    currency_cells: tuple[tuple[str, SemanticMode], ...] = (
                        (address, "text"),
                        *(
                            (
                                f"{column_name(_column_number(column) + offset)}{row}",
                                "currency",
                            )
                            for offset in (1, 2, 3)
                        ),
                    )
                    for pair_address, currency_mode in currency_cells:
                        result[(sheet, pair_address)] = ImporterValueCell(
                            sheet,
                            pair_address,
                            "published_model_output_currency",
                            currency_mode,
                        )

    return sorted(
        result.values(),
        key=lambda item: (item.sheet, _a1(item.address)[1], _column_number(_a1(item.address)[0])),
    )


def importer_field_semantics(definition: ImporterValueCell) -> tuple[str, str]:
    """Describe the canonical field and exact transformation for an imported cell."""
    column, row = _a1(definition.address)
    sheet = definition.sheet
    if sheet == "Universe Registry":
        fields = {
            "A": ("Company.canonical_ticker", "trim and uppercase canonical key"),
            "B": ("Company.name", "trim source name"),
            "C": ("CurrentLifecycle.source_bucket", "trim and case-fold lifecycle bucket"),
            "D": (
                "legacy_rank_population.current_weight_input",
                "exact Decimal membership input only; not canonical current weight",
            ),
            "F": (
                "legacy_rank_population.target_weight_input",
                "exact Decimal membership input only; canonical target comes from "
                "Target Architecture",
            ),
            "J": ("RankingEntry.legacy_research_position", "positive integer or unavailable"),
            "L": ("RankingEntry.legacy_portfolio_position", "positive integer or unavailable"),
            "M": ("RankingEntry.legacy_watchlist_position", "positive integer or unavailable"),
        }
        return fields.get(column, ("source_row", "retained only as importer input"))
    if sheet == "Current Holdings":
        if definition.address == "L4":
            return "Portfolio.base_currency", "parse explicit ISO suffix; no FX conversion"
        return {
            "A": ("HoldingSnapshot.row_kind", "trim and case-fold row discriminator"),
            "B": ("Company.canonical_ticker", "trim and uppercase canonical key"),
            "D": ("HoldingPosition.listing_identity", "resolve exact listing key or ticker"),
            "E": (
                "HoldingPosition.quantity_or_CashPosition.balance",
                "exact Decimal; blank remains missing, never zero",
            ),
            "G": ("CashPosition.currency", "ISO currency identity; no conversion"),
        }.get(column, ("source_row", "retained only as importer input"))
    if sheet == "Target Architecture":
        if definition.address == "P3":
            return "TargetRevision.source_control_total", "exact Decimal reconciliation control"
        return {
            "A": ("TargetAllocation.company_identity", "trim and uppercase canonical key"),
            "D": ("TargetAllocation.weight", "exact Decimal in [0,1]; no rescaling"),
        }.get(column, ("source_row", "retained only as importer input"))
    if sheet in {"10Y Durability", "Compounder Quality"}:
        dimension = "DURABILITY_10Y" if sheet == "10Y Durability" else "COMPOUNDER_QUALITY"
        if column == "A":
            return "ScoreAssessment.company_identity", "trim and uppercase canonical key"
        if column == "G":
            return f"ScoreAssessment.{dimension}.score", "exact Decimal; validated against 0–5"
        if column == "K":
            return "ScoreAssessment.rationale", "preserve source rationale"
        if column in {"L", "M"}:
            return "ScoreAssessment.provenance", "preserve source URL/reference"
        if column in {"C", "D", "E", "F"}:
            return "ScoreAssessment.evidence_completeness", "duplicate-source priority only"
        if column == "B":
            return "Company.name.cross_check", "exact-ticker name fallback/cross-check"
    if sheet == "Price Feed":
        return {
            "A": ("ListingMapping.row_class", "trim and case-fold auxiliary-row filter"),
            "B": ("Company.name", "trim source name"),
            "C": ("Company.canonical_ticker", "trim and uppercase canonical key"),
            "D": ("Listing.exchange_and_ticker", "split exact VENUE:TICKER identity"),
            "H": ("Listing.quote_currency", "ISO currency identity; no conversion"),
        }.get(column, ("source_row", "retained only as importer input"))
    if sheet == "Candidate Ranking":
        return {
            "A": ("ResearchPriorityInput.priority", "exact Decimal; validate canonical scale"),
            "B": ("ResearchPriorityInput.company_identity", "trim and uppercase canonical key"),
        }.get(column, ("source_row", "retained only as importer input"))
    if sheet == "Model Contract":
        return "ModelOutputContractV1.label", "normalized schema label used for validation"
    if sheet == "Model Revision History":
        fields = {
            "A": ("ModelOutputSnapshot.source_revision_id", "trim exact revision identity"),
            "B": (
                "ModelOutputSnapshot.effective_at",
                "parse timezone-aware timestamp; invalid remains unknown",
            ),
            "C": ("ModelOutputSnapshot.company_identity", "trim and uppercase exact source ticker"),
            "E": ("ModelOutputSnapshot.model_key", "trim exact model-tab identity"),
            "G": ("ModelOutputSnapshot.revision_source", "preserve source text"),
            "H": ("ModelOutputSnapshot.revision_type", "preserve source text"),
            "M": (
                "ModelOutputSnapshot.forward_fundamental_cagr",
                "exact Decimal; invalid remains null",
            ),
            "N": ("ModelOutputSnapshot.bear_fv", "exact Decimal; invalid remains null"),
            "O": ("ModelOutputSnapshot.base_fv", "exact Decimal; invalid remains null"),
            "P": ("ModelOutputSnapshot.bull_fv", "exact Decimal; invalid remains null"),
            "Q": ("ModelOutputSnapshot.weighted_fv", "exact Decimal; copied, never recomputed"),
            "R": (
                "ModelOutputSnapshot.expected_cash_flow_irr",
                "exact Decimal; copied, never recomputed",
            ),
            "S": ("ModelOutputSnapshot.hurdle", "exact Decimal; copied, never recomputed"),
            "T": ("ModelOutputSnapshot.expected_excess", "exact Decimal; copied, never recomputed"),
            "U": ("ModelOutputSnapshot.model_status", "preserve status text"),
            "W": ("ModelOutputSnapshot.rationale", "preserve source rationale"),
            "X": ("ModelOutputSnapshot.evidence", "preserve evidence reference"),
            "Y": ("ModelOutputSnapshot.source_actor", "preserve author lane"),
            "Z": ("ModelOutputSnapshot.notes", "preserve source notes"),
        }
        return fields.get(
            column,
            (
                "ModelOutputSnapshot.source_row_fingerprint_only",
                "included in immutable source fingerprint; no separate canonical field",
            ),
        )
    if sheet == "Estimate History":
        fields = {
            "A": (
                "LegacyEstimateObservation.snapshot_date",
                "exact date-only serial; invalid remains unavailable",
            ),
            "B": ("LegacyEstimateObservation.company_identity", "trim and uppercase source ticker"),
            "D": (
                "LegacyEstimateObservation.REVENUE.FY+1",
                "exact Decimal; no historical date inference",
            ),
            "E": (
                "LegacyEstimateObservation.REVENUE.FY+2",
                "exact Decimal; no historical date inference",
            ),
            "F": (
                "LegacyEstimateObservation.EPS.FY+1",
                "exact Decimal; no historical date inference",
            ),
            "G": (
                "LegacyEstimateObservation.EPS.FY+2",
                "exact Decimal; no historical date inference",
            ),
        }
        return fields.get(column, ("source_row", "retained only as importer input"))
    if sheet.startswith(("P-", "W-", "C-")):
        if definition.address in {"A7", "A8"}:
            return "ScoreAssessment.dimension", "must match explicit Execution/Risk label"
        if definition.address == "B7":
            return "ScoreAssessment.EXECUTION.score", "exact Decimal; validated against 1–5"
        if definition.address == "B8":
            return (
                "ScoreAssessment.RISK.score",
                "exact Decimal; validated against 1–5; higher means more risk",
            )
        if column == "AZ":
            return "ModelOutputContractV1.label", "normalized label used to validate output"
        if column == "BA":
            output_fields: dict[int, tuple[str, str]] = {
                3: (
                    "ModelOutputSnapshot.company_identity",
                    "trim and uppercase; must match tab suffix",
                ),
                4: ("ModelOutputSnapshot.bear_fv", "exact Decimal; published output only"),
                5: ("ModelOutputSnapshot.base_fv", "exact Decimal; published output only"),
                6: ("ModelOutputSnapshot.bull_fv", "exact Decimal; published output only"),
                7: (
                    "ModelOutputSnapshot.bear_probability",
                    "exact Decimal fraction; no percent rescaling",
                ),
                8: (
                    "ModelOutputSnapshot.base_probability",
                    "exact Decimal fraction; no percent rescaling",
                ),
                9: (
                    "ModelOutputSnapshot.bull_probability",
                    "exact Decimal fraction; no percent rescaling",
                ),
                10: ("ModelOutputSnapshot.weighted_fv", "exact Decimal; copied, never recomputed"),
                11: (
                    "ModelOutputSnapshot.weighted_upside",
                    "exact Decimal; copied, never recomputed",
                ),
                12: (
                    "ModelOutputSnapshot.expected_cash_flow_irr",
                    "exact Decimal; copied, never recomputed",
                ),
                13: ("ModelOutputSnapshot.hurdle", "exact Decimal; copied, never recomputed"),
                14: (
                    "ModelOutputSnapshot.expected_excess",
                    "exact Decimal; copied, never recomputed",
                ),
                15: (
                    "ModelOutputSnapshot.forward_fundamental_cagr",
                    "exact Decimal; copied, never recomputed",
                ),
                19: ("ModelOutputSnapshot.model_status", "preserve status text"),
                20: ("ModelOutputSnapshot.contract_status", "only explicit PASS publishes values"),
            }
            return output_fields.get(
                row, ("not_imported", "not consumed by current output importer")
            )
        if definition.domain == "published_model_output_currency":
            return (
                "ModelOutputSnapshot.model_currency",
                "ISO code in one of the next three scanned cells; no listing-currency inference",
            )
    return f"{definition.domain}.source_value", "exact normalized source value"


def importer_source_value_policy(definition: ImporterValueCell) -> tuple[str, str]:
    """Return the authority and formula policy for one explicitly imported source field.

    Native Sheets values are authoritative for declared importer fields. XLSX formulas,
    cached values and live formulas remain evidence; no cross-engine equivalence is inferred.
    Price Feed has an explicit row-filter/listing-identity policy because those values select
    exact auxiliary listing records.
    """
    target_field, _ = importer_field_semantics(definition)
    if definition.sheet == "Price Feed":
        return (
            "google_sheets.effective_value",
            "preserve_xlsx_and_sheets_formula; use_live_effective_value_for_"
            f"{target_field}; no_excel_formula_equivalence_assertion",
        )
    return (
        "google_sheets.effective_value",
        "preserve_xlsx_and_sheets_formula; use_live_effective_value; "
        "no_excel_formula_equivalence_assertion",
    )


def importer_empty_value_policy(
    workbook: Any,
    definition: ImporterValueCell,
    *,
    live_values: Mapping[str, Mapping[tuple[int, int], Mapping[str, Any]]] | None = None,
) -> str:
    """Describe how an empty live value is handled by the existing importer contract.

    This is deliberately narrower than full import validation. It identifies fields whose
    blank would otherwise silently omit a required source identity or amount; uncertain
    cases remain delegated to the canonical importer rather than being assigned a value.
    """
    target_field, _transformation = importer_field_semantics(definition)
    column, row_number = _a1(definition.address)

    def cell(address: str) -> Any | None:
        if live_values is not None:
            live_column, live_row = _a1(address)
            live_coordinate = live_values.get(definition.sheet, {}).get(
                (live_row, _column_number(live_column))
            )
            if not isinstance(live_coordinate, Mapping):
                return None
            entered = live_coordinate.get("userEnteredValue")
            effective = live_coordinate.get("effectiveValue")
            formula = (
                entered.get("formulaValue")
                if isinstance(entered, Mapping) and isinstance(entered.get("formulaValue"), str)
                else None
            )
            value: str | None = None
            if isinstance(effective, Mapping):
                if isinstance(effective.get("numberValue"), Decimal):
                    value = format(effective["numberValue"], "f")
                elif isinstance(effective.get("numberValue"), (str, int)):
                    value = str(effective["numberValue"])
                elif isinstance(effective.get("stringValue"), str):
                    value = effective["stringValue"]
            if value is None and isinstance(entered, Mapping):
                if isinstance(entered.get("numberValue"), (str, int, Decimal)):
                    value = str(entered["numberValue"])
                elif isinstance(entered.get("stringValue"), str):
                    value = entered["stringValue"]
            return SimpleNamespace(value=value, formula=formula)
        return workbook.sheets.get(definition.sheet, {}).get(address)

    def has_value(value: Any | None) -> bool:
        if value is None:
            return False
        raw = getattr(value, "value", None)
        # Row membership follows the effective value. A formula is provenance, not evidence
        # that the row is populated: a formula returning "" remains an empty source value.
        return raw is not None and (not isinstance(raw, str) or bool(raw.strip()))

    def text_value(value: Any | None) -> str:
        raw = getattr(value, "value", None)
        return raw.strip() if isinstance(raw, str) else ""

    # Cash rows have no company ticker. Resolve the row-specific contract before
    # applying the general Company identity rule below.
    if definition.sheet == "Current Holdings":
        row_kind = text_value(cell(f"A{row_number}")).casefold()
        if target_field == "Company.canonical_ticker":
            return "REQUIRED_NONEMPTY" if row_kind in {"stock", "etf"} else "ALLOW_EMPTY"
        if target_field == "HoldingPosition.quantity_or_CashPosition.balance":
            return (
                "REQUIRED_NONEMPTY"
                if row_kind in {"stock", "etf", "cash component"}
                else "CANONICAL_IMPORTER_VALIDATES"
            )
        if target_field == "CashPosition.currency":
            return "REQUIRED_NONEMPTY" if row_kind == "cash component" else "ALLOW_EMPTY"
        if target_field == "HoldingPosition.listing_identity":
            return "CANONICAL_IMPORTER_FALLBACK_OR_VALIDATION"

    if target_field in {
        "Company.canonical_ticker",
        "HoldingSnapshot.row_kind",
        "Portfolio.base_currency",
        "TargetRevision.source_control_total",
    }:
        return "REQUIRED_NONEMPTY"

    if target_field == "Company.name":
        if definition.sheet == "Price Feed":
            row_class = cell(f"A{row_number}")
            key = cell(f"C{row_number}")
            if text_value(row_class).upper() == "AUX" and text_value(key).upper() in {
                "SPYY",
                "TSM-ADR",
            }:
                return "REQUIRED_NONEMPTY"
        return "CANONICAL_IMPORTER_FALLBACK_OR_VALIDATION"

    if target_field == "CurrentLifecycle.source_bucket":
        return "PRESERVE_UNRESOLVED"

    if target_field in {
        "legacy_rank_population.current_weight_input",
        "legacy_rank_population.target_weight_input",
    } or target_field.startswith("RankingEntry.legacy_"):
        return "ALLOW_UNAVAILABLE"

    if definition.sheet == "Target Architecture":
        if target_field == "TargetAllocation.company_identity":
            weight_cell = cell(f"D{row_number}")
            return "REQUIRED_NONEMPTY" if has_value(weight_cell) else "CANONICAL_IMPORTER_VALIDATES"
        if target_field == "TargetAllocation.weight":
            identity_cell = cell(f"A{row_number}")
            return (
                "REQUIRED_NONEMPTY"
                if bool(text_value(identity_cell))
                else "CANONICAL_IMPORTER_VALIDATES"
            )

    if definition.sheet == "Price Feed":
        key_cell = cell(f"C{row_number}")
        row_class_cell = cell(f"A{row_number}")
        key = text_value(key_cell).upper()
        row_class = text_value(row_class_cell).upper()
        if (
            key in {"SPYY", "TSM-ADR"}
            and (column == "A" or row_class == "AUX")
            and target_field
            in {
                "ListingMapping.row_class",
                "Company.name",
                "Company.canonical_ticker",
                "Listing.exchange_and_ticker",
                "Listing.quote_currency",
            }
        ):
            return "REQUIRED_NONEMPTY"

    if target_field in {"TargetAllocation.company_identity", "TargetAllocation.weight"}:
        return "CANONICAL_IMPORTER_VALIDATES"

    if target_field == "ScoreAssessment.company_identity":
        relevant_columns = ("G", "K", "L", "M")
        if any(has_value(cell(f"{peer}{row_number}")) for peer in relevant_columns):
            return "REQUIRED_NONEMPTY"
        return "ALLOW_EMPTY"

    if target_field.startswith("ScoreAssessment."):
        return "ALLOW_EMPTY"

    if target_field.startswith("ResearchPriorityInput."):
        peer = "B" if column == "A" else "A"
        return (
            "REQUIRED_NONEMPTY"
            if has_value(cell(f"{peer}{row_number}"))
            else "CANONICAL_IMPORTER_VALIDATES"
        )

    # A newly introduced mapped field must not become implicitly optional. The bundle can
    # retain its empty source state, but the existing domain importer must validate it.
    return "CANONICAL_IMPORTER_VALIDATES"


_PUBLISHED_OUTPUT_FIELDS = {
    "bear_fv",
    "base_fv",
    "bull_fv",
    "bear_probability",
    "base_probability",
    "bull_probability",
    "weighted_fv",
    "weighted_upside",
    "expected_cash_flow_irr",
    "hurdle",
    "expected_excess",
    "forward_fundamental_cagr",
}


def importer_source_role(
    definition: ImporterValueCell, cell: Any | None = None, *, formula_present: bool | None = None
) -> str:
    """Classify the source role without treating formulas as accepted application state."""
    target_field, _ = importer_field_semantics(definition)
    field_name = target_field.rsplit(".", 1)[-1]
    if target_field.startswith("ModelOutputSnapshot.") and field_name in _PUBLISHED_OUTPUT_FIELDS:
        return "published_financial_model_output"
    if target_field == "ModelOutputContractV1.label":
        return "published_model_contract_metadata"
    if definition.domain == "published_model_output_currency":
        return "published_model_currency_metadata"
    if definition.domain == "published_model_output_history":
        return (
            "published_financial_model_output"
            if field_name in _PUBLISHED_OUTPUT_FIELDS
            else "published_model_history_metadata"
        )
    has_formula = (
        formula_present
        if formula_present is not None
        else cell is not None and cell.formula is not None
    )
    if has_formula:
        return "spreadsheet_derived_value"
    if definition.sheet == "Universe Registry" and definition.address[:1] in {"J", "L", "M"}:
        return "legacy_ranking_snapshot"
    if definition.sheet == "Universe Registry" and definition.address[:1] in {"D", "F"}:
        return "legacy_lifecycle_membership_input"
    if definition.sheet == "Candidate Ranking":
        return "workbook_research_priority_input"
    if definition.domain == "legacy_estimate_history":
        return "legacy_estimate_observation"
    if definition.sheet == "Price Feed":
        return "legacy_listing_identity_crosswalk"
    if definition.domain == "investment_scores":
        return "workbook_score_assessment"
    if definition.sheet == "Target Architecture":
        return "workbook_strategic_target_input"
    if definition.sheet == "Current Holdings":
        return "workbook_holding_or_cash_input"
    return "literal_workbook_input"


_CURRENCY_LABEL = re.compile(
    r"^(valuation currency|accounting\s*/\s*model currency|model\s*/\s*accounting currency|"
    r"model currency|accounting currency|home currency|valuation\s*/\s*accounting currency|"
    r"currency)$",
    re.IGNORECASE,
)


def _currency_label(value: str) -> bool:
    return bool(_CURRENCY_LABEL.fullmatch(value))


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("Non-finite source numbers are not valid semantic values.")
    if value == 0:
        return "0"
    exact = format(value, "f")
    if "." in exact:
        exact = exact.rstrip("0").rstrip(".")
    return exact


def _excel_serial_date(value: str, date_system: str) -> str | None:
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError, OverflowError):
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    serial = int(number)
    if date_system == "1904":
        if serial < 0:
            return None
        origin = date(1904, 1, 1)
    elif date_system == "google":
        # Google Sheets serial dates count from 1899-12-30 without Excel's
        # fictitious 1900-02-29 compatibility day.
        if serial < 0:
            return None
        origin = date(1899, 12, 30)
    else:
        # XLSX's 1900 system preserves Excel's leap-year bug. Serial 60 is the
        # nonexistent 1900-02-29 and must not be turned into a real date.
        if serial < 1 or serial == 60:
            return None
        origin = date(1899, 12, 31) if serial < 60 else date(1899, 12, 30)
    try:
        return (origin + timedelta(days=serial)).isoformat()
    except OverflowError:
        return None


def normalize_source_cell(
    cell: Any, mode: SemanticMode, *, date_system: str = "1900"
) -> NormalizedCellValue:
    """Normalize one frozen XLSX value using its importer field semantics, never floats."""
    raw = cell.value
    if cell.kind == "e":
        source_type = "error"
    elif cell.kind == "b":
        source_type = "boolean"
    elif cell.kind in {"s", "str", "inlineStr"}:
        source_type = "text"
    elif cell.kind in {None, "n"}:
        source_type = "number" if raw is not None else "blank"
    else:
        source_type = str(cell.kind)
    if cell.kind == "e":
        return NormalizedCellValue(
            "FORMULA_ERROR" if cell.formula is not None else "CELL_ERROR", raw, "error"
        )
    if cell.formula is not None and (raw is None or not raw.strip()):
        return NormalizedCellValue("FORMULA_CACHE_EMPTY", None, "formula-empty")
    if raw is None:
        return NormalizedCellValue("MISSING", None, source_type)
    value = raw.strip()
    if not value:
        return NormalizedCellValue("BLANK", "", source_type)
    if mode in {"decimal", "percent_decimal", "excel_date"} and cell.kind == "b":
        return NormalizedCellValue("INVALID_SOURCE_TYPE", None, source_type)
    if mode == "ticker":
        return NormalizedCellValue("VALUE", value.upper(), source_type)
    if mode == "currency":
        return NormalizedCellValue("VALUE", value.upper(), source_type)
    if mode == "excel_date":
        if source_type != "number":
            return NormalizedCellValue("INVALID_DATE_TYPE", None, source_type)
        parsed_date = _excel_serial_date(value, date_system)
        if parsed_date is None:
            return NormalizedCellValue(
                "INVALID_DATE_SERIAL",
                hashlib.sha256(value.encode("utf-8")).hexdigest(),
                source_type,
            )
        return NormalizedCellValue("VALUE", parsed_date, source_type)
    if mode == "label":
        normalized = re.sub(r"\s*/\s*share\b", "", value, flags=re.IGNORECASE)
        normalized = re.sub(
            r"\b(bear|base|bull)\s+prob\b", r"\1 probability", normalized, flags=re.I
        )
        normalized = re.sub(r"\bweighted\s+fv\b", "weighted fair value", normalized, flags=re.I)
        normalized = re.sub(r"[^a-z0-9]", "", normalized.casefold())
        aliases = {
            "expectedcfirr": "expectedcashflowirr",
            "fundamentalcagr": "forwardfundamentalcagr",
            "durability": "10ydurability",
        }
        return NormalizedCellValue("VALUE", aliases.get(normalized, normalized), source_type)
    if mode in {"decimal", "percent_decimal"}:
        numeric_raw = value
        if mode == "percent_decimal" and numeric_raw.endswith("%"):
            numeric_raw = numeric_raw[:-1].strip()
        try:
            number = Decimal(numeric_raw)
            if mode == "percent_decimal" and value.endswith("%"):
                number /= Decimal(100)
        except InvalidOperation:
            return NormalizedCellValue(
                "INVALID", hashlib.sha256(value.encode("utf-8")).hexdigest(), source_type
            )
        if not number.is_finite():
            return NormalizedCellValue(
                "INVALID", hashlib.sha256(value.encode("utf-8")).hexdigest(), source_type
            )
        exponent = number.as_tuple().exponent
        scale = max(-exponent, 0) if isinstance(exponent, int) else 0
        return NormalizedCellValue("VALUE", _decimal_text(number), source_type, scale)
    if mode == "timestamp":
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return NormalizedCellValue(
                "INVALID_TIMESTAMP",
                hashlib.sha256(value.encode("utf-8")).hexdigest(),
                source_type,
            )
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return NormalizedCellValue(
                "INVALID_TIMESTAMP",
                hashlib.sha256(value.encode("utf-8")).hexdigest(),
                source_type,
            )
        normalized_timestamp = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return NormalizedCellValue("VALUE", normalized_timestamp, "timestamp")
    return NormalizedCellValue("VALUE", value, "text")


def semantic_projection(workbook: Any) -> tuple[list[dict[str, object]], dict[str, Any]]:
    """Build the importer-field projection, with formula-cache health by owning domain."""
    cells = importer_value_cells(workbook)
    projection: list[dict[str, object]] = []
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    formula_refs: dict[str, list[dict[str, str]]] = defaultdict(list)
    for definition in cells:
        source_cell = workbook.sheets.get(definition.sheet, {}).get(
            definition.address, _BlankCell()
        )
        normalized = normalize_source_cell(
            source_cell,
            definition.mode,
            date_system=getattr(workbook, "date_system", "1900"),
        )
        target_field, transformation = importer_field_semantics(definition)
        source_role = importer_source_role(definition, source_cell)
        projection.append(
            {
                "domain": definition.domain,
                "sheet": definition.sheet,
                "cell": definition.address,
                "target_field": target_field,
                "transformation": transformation,
                "source_role": source_role,
                "formula_present": source_cell.formula is not None,
                **normalized.payload(),
            }
        )
        counters[definition.domain][normalized.state] += 1
        if source_cell.formula is not None:
            counters[definition.domain]["FORMULA"] += 1
            if normalized.state in {"FORMULA_CACHE_EMPTY", "FORMULA_ERROR"}:
                formula_refs[definition.domain].append(
                    {
                        "sheet": definition.sheet,
                        "cell": definition.address,
                        "target_field": target_field,
                        "transformation": transformation,
                        "source_role": source_role,
                        "state": normalized.state,
                    }
                )
    diagnostics = {
        "fingerprint_version": SEMANTIC_FINGERPRINT_VERSION,
        "cell_count": len(cells),
        "by_domain": {
            domain: dict(sorted(counts.items())) for domain, counts in sorted(counters.items())
        },
        "formula_cache_issues": {domain: refs for domain, refs in sorted(formula_refs.items())},
        "date_system": getattr(workbook, "date_system", "unknown"),
    }
    return projection, diagnostics


def semantic_fingerprint(workbook: Any) -> tuple[str, dict[str, Any]]:
    projection, diagnostics = semantic_projection(workbook)
    encoded = json.dumps(
        {"version": SEMANTIC_FINGERPRINT_VERSION, "values": projection},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), diagnostics


def _live_value_to_cell(value: dict[str, Any] | None) -> tuple[Any, str, str | None]:
    """Convert a Sheets effectiveValue object to a Cell-shaped exact value."""
    from portfolio_api.legacy_import import Cell

    if not value:
        return Cell(), "blank", None
    if "numberValue" in value:
        number = value["numberValue"]
        raw = format(number, "f") if isinstance(number, Decimal) else str(number)
        return Cell(raw, "n"), "number", raw
    if "stringValue" in value:
        raw = str(value["stringValue"])
        return Cell(raw, "str"), "string", raw
    if "boolValue" in value:
        raw = "1" if value["boolValue"] else "0"
        return Cell(raw, "b"), "boolean", raw
    if "errorValue" in value:
        error = value["errorValue"]
        code = str(error.get("type", "ERROR")) if isinstance(error, dict) else "ERROR"
        return Cell(code, "e"), "error", code
    return Cell(), "unknown", None


def live_cell_normalization(
    value: dict[str, Any] | None,
    *,
    mode: SemanticMode,
    has_formula: bool,
    number_format_type: str | None = None,
) -> tuple[NormalizedCellValue, str, int | None]:
    cell, source_type, raw = _live_value_to_cell(value)
    if has_formula:
        from portfolio_api.legacy_import import Cell

        cell = Cell(
            value=cell.value,
            kind=cell.kind,
            formula="live-formula",
            number_format_code=cell.number_format_code,
            number_format_type=cell.number_format_type,
        )
    if mode == "excel_date" and number_format_type not in {
        "DATE",
        "DATE_TIME",
        "DATE_TIME_SECONDS",
    }:
        return (
            NormalizedCellValue("INVALID_DATE_FORMAT", None, number_format_type or "unknown"),
            source_type,
            None,
        )
    normalized = normalize_source_cell(
        cell,
        mode,
        date_system="google" if mode == "excel_date" else "1900",
    )
    if source_type == "string" and raw == "":
        normalized = NormalizedCellValue(
            "FORMULA_EMPTY_STRING" if has_formula else "EMPTY_STRING",
            "",
            "formula-empty-string" if has_formula else "empty-string",
        )
    scale: int | None = None
    if raw is not None and source_type == "number":
        try:
            exponent = Decimal(raw).as_tuple().exponent
            scale = max(-exponent, 0) if isinstance(exponent, int) else 0
        except InvalidOperation:
            scale = None
    return normalized, source_type, scale
