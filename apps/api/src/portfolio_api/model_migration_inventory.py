"""Build a read-only inventory of legacy financial-model tabs.

This module classifies source tabs and migration readiness only. It never reads a
database, writes model assumptions, or evaluates spreadsheet formulas.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from portfolio_api.legacy_import import Workbook
from portfolio_api.model_outputs import (
    _expected_contract_labels,
    _explicit_currency,
    _quality,
    _read_output_values,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_WORKBOOK = REPOSITORY_ROOT / "reference" / "workbook" / "Portfolio_Watchlist.xlsx"
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "docs" / "reconciliation" / "model-migration-inventory-2026-10-05.json"
)
INVENTORY_DATE = "2026-10-05"

READY_FIXTURES = {
    "P-GOOGL": "UFCF_DCF_10Y_FADE",
    "W-TOST": "OWNER_CASH_FLOW_10Y",
    "W-HDFC": "RESIDUAL_INCOME_10Y_FADE",
}
IDENTITY_CANDIDATES = {
    "P-MELI-SOTP": "MELI",
    "P-SPGI-CIQ": "SPGI",
}
SPECIALIZATIONS = {
    "W-AFRM": "CREDIT_AND_FUNDING_CAPITAL",
    "W-ARES": "ALTERNATIVE_ASSET_MANAGER",
    "W-BAM": "ALTERNATIVE_ASSET_MANAGER",
    "W-CSU": "ACQUISITION_REINVESTMENT",
    "W-HOOD": "BROKERAGE_FINANCIAL_PLATFORM",
    "W-IBKR": "BROKERAGE_FINANCIAL_PLATFORM",
    "W-JDG": "ACQUISITION_REINVESTMENT",
    "W-KNSL": "INSURANCE_UNDERWRITING",
    "W-NU": "BANK",
    "W-PLMR": "SPECIALTY_INSURANCE",
}
UNSUPPORTED_SPECIALIZATIONS = {
    "ACQUISITION_REINVESTMENT",
    "ALTERNATIVE_ASSET_MANAGER",
    "BANK",
    "BROKERAGE_FINANCIAL_PLATFORM",
    "CREDIT_AND_FUNDING_CAPITAL",
    "INSURANCE_UNDERWRITING",
    "SPECIALTY_INSURANCE",
}
MANUAL_CURRENCY_EVIDENCE = {
    "W-JDG": ("GBP", "A1", "Explicit title text: GBP m unless per share."),
    "W-PLEJD": ("SEK", "D3", "Explicit unit text: SEK/share."),
    "W-TSM": ("TWD", "A2", "Explicit model statement: Home-currency TWD model."),
}
UNIT_CURRENCY_CODES = (
    "USD",
    "EUR",
    "SEK",
    "DKK",
    "INR",
    "JPY",
    "TWD",
    "CAD",
    "AUD",
    "NOK",
    "CHF",
    "GBP",
    "SGD",
    "HKD",
    "BRL",
    "ZAR",
    "CNY",
    "KRW",
    "NZD",
    "PLN",
    "MXN",
)

MODEL_TAB_PREFIXES = ("P-", "W-")
METHOD_FAMILY_BY_TITLE = {
    "UFCF_DCF_10Y_FADE": ("secular growth fade",),
    "RESIDUAL_INCOME_10Y_FADE": ("residual income",),
    "SOTP_OR_HYBRID": ("sum-of-the-parts", "sotp"),
    "OWNER_CASH_FLOW_OR_EARNINGS": ("owner",),
}


def _value(cells: dict[str, Any], address: str) -> str | None:
    cell = cells.get(address)
    if cell is None or cell.value is None:
        return None
    result = cell.value.strip()
    return result or None


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _lifecycle(registry_row: dict[str, str | None] | None) -> tuple[str, str]:
    if registry_row is None:
        return "UNRESOLVED", "No exact registry ticker matches the model-tab suffix."

    current = _parse_decimal(registry_row.get("D"))
    target = _parse_decimal(registry_row.get("F"))
    if (current is not None and current > 0) or (target is not None and target > 0):
        return "PORTFOLIO", "Positive cached current or target weight in Universe Registry."
    if current is None or target is None:
        return "UNRESOLVED", "Blank cached current/target weight prevents lifecycle resolution."

    bucket = (registry_row.get("C") or "").strip().casefold()
    if bucket == "watchlist":
        return "WATCHLIST", "Explicit Research Bucket after non-portfolio membership check."
    if bucket in {"candidate - high", "candidate - low"}:
        return "CANDIDATE", "Explicit candidate Research Bucket."
    if bucket == "drop":
        return "DROP", "Explicit Drop Research Bucket."
    return "UNRESOLVED", "No positive allocation or recognized Research Bucket."


def _source_contract_status(raw_status: str | None) -> str:
    normalized = (raw_status or "").strip().upper()
    if normalized == "PASS":
        return "PASS"
    if normalized.startswith("NOT MAPPED"):
        return "NOT_MAPPED"
    return "NO_CONTRACT" if not normalized else "DATA_CHECK"


def _methodology_family(model_key: str, title: str) -> str:
    normalized = title.casefold()
    if model_key in {"P-SPGI", "P-MELI-SOTP", "P-SPGI-CIQ"}:
        return "SOTP_OR_HYBRID"
    for family in (
        "RESIDUAL_INCOME_10Y_FADE",
        "UFCF_DCF_10Y_FADE",
        "SOTP_OR_HYBRID",
        "OWNER_CASH_FLOW_OR_EARNINGS",
    ):
        if any(term in normalized for term in METHOD_FAMILY_BY_TITLE[family]):
            return family
    return "OTHER_METHOD_UNCLASSIFIED"


def _currency(cells: dict[str, Any], model_key: str) -> dict[str, Any]:
    contract_currency, label_cell = _explicit_currency(cells)
    contract_status = "DOCUMENTED" if contract_currency else "UNKNOWN"
    if contract_currency:
        return {
            "model_currency": contract_currency,
            "currency_evidence": f"{model_key}!{label_cell} label and adjacent ISO code",
            "currency_evidence_type": "CONTRACT_CURRENCY_LABEL",
            "contract_currency_status": contract_status,
        }

    unit_pattern = re.compile(r"\b(" + "|".join(UNIT_CURRENCY_CODES) + r")\b", re.IGNORECASE)
    unit_codes: set[str] = set()
    unit_cells: list[str] = []
    for address, cell in cells.items():
        if not address.startswith("C") or not cell.value:
            continue
        match = re.fullmatch(r"C\d+", address)
        if match is None:
            continue
        found = {value.upper() for value in unit_pattern.findall(cell.value)}
        if found:
            unit_codes.update(found)
            unit_cells.append(address)
    if len(unit_codes) == 1:
        unit_currency = next(iter(unit_codes))
        return {
            "model_currency": unit_currency,
            "currency_evidence": (
                f"{model_key}!{','.join(unit_cells[:5])}: unique ISO currency in Unit/Basis column"
            ),
            "currency_evidence_type": "UNIQUE_UNIT_BASIS_CURRENCY",
            "contract_currency_status": contract_status,
        }

    manual = MANUAL_CURRENCY_EVIDENCE.get(model_key)
    if manual is not None:
        currency, cell, evidence = manual
        return {
            "model_currency": currency,
            "currency_evidence": f"{model_key}!{cell}: {evidence}",
            "currency_evidence_type": "EXPLICIT_MODEL_CURRENCY_STATEMENT",
            "contract_currency_status": contract_status,
        }

    return {
        "model_currency": None,
        "currency_evidence": (
            f"{model_key}: multiple Unit/Basis currencies {','.join(sorted(unit_codes))}"
            if unit_codes
            else None
        ),
        "currency_evidence_type": (
            "MULTIPLE_UNIT_CURRENCIES_UNRESOLVED" if unit_codes else "NO_EXPLICIT_CURRENCY_EVIDENCE"
        ),
        "contract_currency_status": contract_status,
    }


def _output_state(
    *,
    model_key: str,
    cells: dict[str, Any],
    source_status: str,
    suffix_ticker: str,
    expected_labels: dict[int, str],
) -> dict[str, Any]:
    if source_status != "PASS":
        return {
            "current_output_status": source_status,
            "output_quality": "UNAVAILABLE",
            "published_numeric_fields": [],
        }

    contract_ticker = (_value(cells, "BA3") or "").upper()
    if not contract_ticker or contract_ticker != suffix_ticker:
        return {
            "current_output_status": "DATA_CHECK",
            "output_quality": "UNAVAILABLE",
            "published_numeric_fields": [],
        }

    outputs, field_issues = _read_output_values(
        cells=cells,
        coordinate=lambda row_number: f"BA{row_number}",
        source=model_key,
        validate_contract_labels=True,
        expected_labels=expected_labels,
    )
    label_issues = [issue for issue in field_issues if issue["field"] == "contract_labels"]
    if label_issues:
        return {
            "current_output_status": "DATA_CHECK",
            "output_quality": "UNAVAILABLE",
            "published_numeric_fields": [],
        }
    return {
        "current_output_status": "PUBLISHED",
        "output_quality": _quality(outputs, field_issues, available=True),
        "published_numeric_fields": sorted(
            name for name, value in outputs.items() if value is not None
        ),
    }


def _tab_identity(
    model_key: str,
    suffix_ticker: str,
    registry: dict[str, dict[str, str | None]],
) -> dict[str, Any]:
    source_row = registry.get(suffix_ticker)
    if source_row is not None:
        return {
            "identity_status": "MAPPED_BY_EXACT_TAB_SUFFIX",
            "canonical_ticker": suffix_ticker,
            "company_name": source_row.get("B") or None,
            "identity_candidate_ticker": None,
        }
    candidate_ticker = IDENTITY_CANDIDATES.get(model_key)
    candidate_row = registry.get(candidate_ticker or "")
    return {
        "identity_status": "UNRESOLVED",
        "canonical_ticker": None,
        "company_name": None,
        "identity_candidate_ticker": candidate_ticker,
        "identity_candidate_name": candidate_row.get("B") if candidate_row else None,
    }


def _native_support(model_key: str, family: str, specialization: str | None) -> str:
    if model_key in READY_FIXTURES:
        return "PARITY_PROVEN_FOR_TAB"
    if (
        family
        in {
            "UFCF_DCF_10Y_FADE",
            "OWNER_CASH_FLOW_OR_EARNINGS",
            "RESIDUAL_INCOME_10Y_FADE",
        }
        and specialization not in UNSUPPORTED_SPECIALIZATIONS
    ):
        return "NATIVE_FAMILY_EXISTS_TAB_PARITY_REQUIRED"
    if family == "SOTP_OR_HYBRID" or specialization in UNSUPPORTED_SPECIALIZATIONS:
        return "NOT_SUPPORTED_NATIVELY"
    return "METHODOLOGY_NOT_CLASSIFIED"


def _migration_status(
    *,
    model_key: str,
    lifecycle: str,
    identity_status: str,
    current_output_status: str,
    family: str,
    specialization: str | None,
) -> str:
    if lifecycle == "DROP":
        return "LEGACY_ONLY"
    if current_output_status == "DATA_CHECK":
        return "DATA_CHECK"
    if identity_status == "UNRESOLVED":
        return "NEEDS_MAPPING"
    if model_key in READY_FIXTURES:
        return "READY_FOR_NATIVE_IMPORT"
    if family == "SOTP_OR_HYBRID" or specialization in UNSUPPORTED_SPECIALIZATIONS:
        return "UNSUPPORTED_METHOD"
    return "NEEDS_MAPPING"


def _blockers(
    *,
    model_key: str,
    lifecycle: str,
    identity_status: str,
    current_output_status: str,
    family: str,
    specialization: str | None,
    contract_currency_status: str,
) -> list[str]:
    values: list[str] = []
    if identity_status == "UNRESOLVED":
        values.append("CANONICAL_COMPANY_IDENTITY_UNRESOLVED")
    if current_output_status == "DATA_CHECK":
        values.append("PUBLISHED_TICKER_OR_CONTRACT_LAYOUT_MISMATCH")
    elif current_output_status in {"NOT_MAPPED", "NO_CONTRACT"}:
        values.append("NO_PUBLISHED_NORMALIZED_OUTPUT_CONTRACT")
    if contract_currency_status == "UNKNOWN":
        values.append("CONTRACT_MODEL_CURRENCY_UNKNOWN")
    if lifecycle == "UNRESOLVED":
        values.append("LIFECYCLE_UNRESOLVED")
    if (
        model_key not in READY_FIXTURES
        and family
        in {
            "UFCF_DCF_10Y_FADE",
            "OWNER_CASH_FLOW_OR_EARNINGS",
            "RESIDUAL_INCOME_10Y_FADE",
        }
        and specialization not in UNSUPPORTED_SPECIALIZATIONS
    ):
        values.append("TAB_SPECIFIC_ASSUMPTION_MAPPING_AND_PARITY_NOT_PROVEN")
    if family == "SOTP_OR_HYBRID" or specialization in UNSUPPORTED_SPECIALIZATIONS:
        values.append("NO_SUPPORTED_NATIVE_METHOD_FOR_THIS_VARIANT")
    if lifecycle == "DROP":
        values.append("DROPPED_LIFECYCLE_DEFERRED_FROM_ACTIVE_MIGRATION")
    return values


def _recommended_batch(
    *,
    model_key: str,
    lifecycle: str,
    family: str,
    migration_status: str,
    identity_status: str,
) -> str:
    if migration_status == "READY_FOR_NATIVE_IMPORT":
        return "B0_PARITY_BACKED_ACTIVE_IMPORT"
    if lifecycle == "DROP":
        return "DEFER_DROPPED_MODELS"
    if migration_status == "DATA_CHECK":
        return "B0_SOURCE_DATA_REMEDIATION"
    if identity_status == "UNRESOLVED":
        return "B0_IDENTITY_RESOLUTION"
    if lifecycle == "UNRESOLVED":
        return "B0_LIFECYCLE_RESOLUTION"
    if model_key == "P-SPGI":
        return "B3_PORTFOLIO_SOTP_METHOD_PROOF"
    if model_key == "P-NVO":
        return "B1B_PORTFOLIO_LISTING_CURRENCY_RECONCILIATION"
    if migration_status == "UNSUPPORTED_METHOD":
        return "B5_NEW_METHOD_PILOTS"
    if not model_key.startswith("P-") and family == "OWNER_CASH_FLOW_OR_EARNINGS":
        return "B4_WATCHLIST_OWNER_CASH_FLOW_MAPPING"
    if lifecycle == "PORTFOLIO" and family == "UFCF_DCF_10Y_FADE":
        return "B1_PORTFOLIO_DCF_COHORT"
    if lifecycle == "PORTFOLIO" and family == "OWNER_CASH_FLOW_OR_EARNINGS":
        return "B2_PORTFOLIO_OWNER_CASH_FLOW_VARIANTS"
    return "B6_WATCHLIST_METHOD_DISCOVERY"


MODEL_NOTES = {
    "P-MELI-SOTP": (
        "The tab title points to MercadoLibre, but the source tab suffix has no exact registry "
        "identity. Do not attach it to MELI until its role and ownership are confirmed."
    ),
    "P-NVO": (
        "The model is explicitly in DKK and states it uses the Copenhagen B share. Confirm the "
        "exact application listing and matching price before importing price-dependent outputs; "
        "do not substitute the USD ADR without an evidenced share ratio and FX path."
    ),
    "P-SPGI": (
        "The tab combines a RemainCo DCF with a linked Capital IQ Pro SOTP. The listed SPGI "
        "identity and output contract are present, but the sum-of-parts bridge needs its own "
        "methodology and component mapping."
    ),
    "P-SPGI-CIQ": (
        "The standalone Capital IQ Pro component tab has no exact company identity or published "
        "contract. Treat it as a possible SPGI component only after its accounting and ownership "
        "relationship is confirmed."
    ),
    "W-PLEJD": (
        "The registry cache does not resolve lifecycle because allocation caches are blank; the "
        "tab says Watchlist, but BA3 contains 272.75 instead of PLEJD. Resolve both before use."
    ),
    "W-TSM": (
        "The source explicitly uses a TWD local-ordinary-share model. Preserve the TPE ordinary "
        "listing identity; do not compare with the held USD ADR without a documented ratio and FX."
    ),
}


def build_inventory(workbook_path: Path = DEFAULT_WORKBOOK) -> dict[str, Any]:
    """Return a deterministic source-grounded inventory; no database is consulted."""
    workbook = Workbook.read(
        workbook_path,
        lambda name: (
            name in {"Universe Registry", "Model Contract"} or name.startswith(MODEL_TAB_PREFIXES)
        ),
    )
    registry: dict[str, dict[str, str | None]] = {}
    for _row_number, registry_cells in workbook.rows("Universe Registry", 5):
        ticker = _value(registry_cells, "A")
        if not ticker:
            continue
        registry[ticker.upper()] = {
            column: _value(registry_cells, column) for column in registry_cells
        }

    expected_labels = _expected_contract_labels(workbook)
    # Import's contract-label checker consumes the exact source contract block.
    models: list[dict[str, Any]] = []
    for model_key, cells in sorted(workbook.sheets.items()):
        if not model_key.startswith(MODEL_TAB_PREFIXES):
            continue
        suffix_ticker = model_key[2:].strip().upper()
        title = _value(cells, "A1") or ""
        raw_status = _value(cells, "BA20")
        source_status = _source_contract_status(raw_status)
        identity = _tab_identity(model_key, suffix_ticker, registry)
        lifecycle, lifecycle_evidence = _lifecycle(registry.get(identity["canonical_ticker"] or ""))
        output_state = _output_state(
            model_key=model_key,
            cells=cells,
            source_status=source_status,
            suffix_ticker=suffix_ticker,
            expected_labels=expected_labels,
        )
        currency = _currency(cells, model_key)
        family = _methodology_family(model_key, title)
        specialization = SPECIALIZATIONS.get(model_key)
        native_support = _native_support(model_key, family, specialization)
        migration_status = _migration_status(
            model_key=model_key,
            lifecycle=lifecycle,
            identity_status=identity["identity_status"],
            current_output_status=output_state["current_output_status"],
            family=family,
            specialization=specialization,
        )
        if model_key in READY_FIXTURES:
            assumption_mapping = "VERIFIED_BY_REPRESENTATIVE_PARITY_FIXTURE"
        elif native_support == "NATIVE_FAMILY_EXISTS_TAB_PARITY_REQUIRED":
            assumption_mapping = "NOT_YET_VERIFIED_FOR_THIS_TAB"
        elif native_support == "NOT_SUPPORTED_NATIVELY":
            assumption_mapping = "NO_NATIVE_INPUT_SCHEMA_FOR_THIS_VARIANT"
        else:
            assumption_mapping = "METHODOLOGY_AND_INPUTS_REQUIRE_REVIEW"

        blockers = _blockers(
            model_key=model_key,
            lifecycle=lifecycle,
            identity_status=identity["identity_status"],
            current_output_status=output_state["current_output_status"],
            family=family,
            specialization=specialization,
            contract_currency_status=currency["contract_currency_status"],
        )
        if migration_status == "READY_FOR_NATIVE_IMPORT":
            blockers = [
                "SOURCE_EFFECTIVE_DATE_UNKNOWN",
                *(
                    ["CONTRACT_CURRENCY_UNKNOWN_BUT_INPUT_UNIT_IS_EXPLICIT"]
                    if currency["contract_currency_status"] == "UNKNOWN"
                    else []
                ),
            ]

        tab_prefix_hint = "PORTFOLIO" if model_key.startswith("P-") else "WATCHLIST"
        prefix_lifecycle_note = None
        if lifecycle == "PORTFOLIO" and tab_prefix_hint == "WATCHLIST":
            prefix_lifecycle_note = (
                "The model tab retains a W- name although Universe Registry resolves current "
                "lifecycle as PORTFOLIO; registry membership is authoritative."
            )

        model_entry = {
            "model_tab": model_key,
            "source_title": title,
            "tab_prefix_lifecycle_hint": tab_prefix_hint,
            **identity,
            "lifecycle": lifecycle,
            "lifecycle_evidence": lifecycle_evidence,
            "prefix_lifecycle_note": prefix_lifecycle_note,
            "methodology_family": family,
            "methodology_variant": specialization,
            "methodology_evidence": "Model-tab title; not a full formula audit.",
            "assessment_notes": MODEL_NOTES.get(model_key),
            "native_method_support": native_support,
            "assumption_mapping_status": assumption_mapping,
            "source_contract_status_raw": raw_status,
            "source_contract_status": source_status,
            "current_output_status": output_state["current_output_status"],
            "output_quality": output_state["output_quality"],
            "published_numeric_fields": output_state["published_numeric_fields"],
            **currency,
            "migration_status": migration_status,
            "recommended_batch": _recommended_batch(
                model_key=model_key,
                lifecycle=lifecycle,
                family=family,
                migration_status=migration_status,
                identity_status=identity["identity_status"],
            ),
            "blockers": blockers,
        }
        models.append(model_entry)

    lifecycle_counts = Counter(model["lifecycle"] for model in models)
    methodology_counts = Counter(model["methodology_family"] for model in models)
    source_contract_counts = Counter(model["source_contract_status"] for model in models)
    output_status_counts = Counter(model["current_output_status"] for model in models)
    currency_counts = Counter(model["contract_currency_status"] for model in models)
    source_currency_counts = Counter(
        "DOCUMENTED" if model["model_currency"] else "UNKNOWN" for model in models
    )
    migration_counts = Counter(model["migration_status"] for model in models)
    lifecycle_by_methodology: dict[str, dict[str, int]] = {}
    for family in sorted(methodology_counts):
        lifecycle_by_methodology[family] = dict(
            sorted(
                Counter(
                    model["lifecycle"] for model in models if model["methodology_family"] == family
                ).items()
            )
        )

    def tabs(predicate: Any) -> list[str]:
        return sorted(model["model_tab"] for model in models if predicate(model))

    migration_batches = [
        {
            "batch_id": "B0_PARITY_BACKED_ACTIVE_IMPORT",
            "sequence": 0,
            "model_tabs": tabs(
                lambda model: model["migration_status"] == "READY_FOR_NATIVE_IMPORT"
            ),
            "objective": (
                "Import only the two active tabs with existing tab-specific native parity fixtures."
            ),
            "entry_gates": [
                "Preserve source workbook hash and import provenance.",
                "Set effective time to the explicit application acceptance time; retain the "
                "original source effective date as unknown.",
                "Do not reinterpret the legacy expected-return field as canonical "
                "shareholder-cash-flow IRR.",
            ],
        },
        {
            "batch_id": "B0_IDENTITY_RESOLUTION",
            "sequence": 0,
            "model_tabs": tabs(lambda model: model["identity_status"] == "UNRESOLVED"),
            "objective": (
                "Resolve two SOTP/component tabs to exact canonical company or model-component "
                "identity before attaching them."
            ),
            "entry_gates": ["No ticker-prefix or company-name guess may create a canonical link."],
        },
        {
            "batch_id": "B0_LIFECYCLE_RESOLUTION",
            "sequence": 0,
            "model_tabs": tabs(lambda model: model["lifecycle"] == "UNRESOLVED"),
            "objective": (
                "Resolve blank registry allocation caches or source identity before applying "
                "lifecycle priority."
            ),
            "entry_gates": ["Do not infer Watchlist from a W- tab name or stale page label."],
        },
        {
            "batch_id": "B0_SOURCE_DATA_REMEDIATION",
            "sequence": 0,
            "model_tabs": tabs(lambda model: model["migration_status"] == "DATA_CHECK"),
            "objective": (
                "Correct the published ticker/contract mismatch and reconcile the source before "
                "any import."
            ),
            "entry_gates": [
                "Rebuild and validate the normalized output contract after source repair."
            ],
        },
        {
            "batch_id": "B1_PORTFOLIO_DCF_COHORT",
            "sequence": 1,
            "model_tabs": tabs(
                lambda model: (
                    model["lifecycle"] == "PORTFOLIO"
                    and model["methodology_family"] == "UFCF_DCF_10Y_FADE"
                    and model["model_tab"] not in {"P-GOOGL", "P-NVO"}
                )
            ),
            "objective": (
                "Validate tab-specific assumptions against the existing DCF engine, then import "
                "the active portfolio cohort in small reviewed groups."
            ),
            "entry_gates": [
                "Compare source formulas and all required inputs with the P-GOOGL canonical "
                "schema.",
                "Reconcile scenario fair values, output fields, listing basis and currency before "
                "each accepted revision.",
            ],
        },
        {
            "batch_id": "B1B_PORTFOLIO_LISTING_CURRENCY_RECONCILIATION",
            "sequence": 1,
            "model_tabs": ["P-NVO"],
            "objective": "Confirm the exact Copenhagen B listing and DKK-per-share basis for NVO.",
            "entry_gates": [
                "Do not substitute the USD ADR without a sourced ADR ratio and dated FX treatment.",
                "Require a comparable listing-specific quote before accepting price-dependent "
                "outputs.",
            ],
        },
        {
            "batch_id": "B2_PORTFOLIO_OWNER_CASH_FLOW_VARIANTS",
            "sequence": 2,
            "model_tabs": tabs(
                lambda model: (
                    model["lifecycle"] == "PORTFOLIO"
                    and model["methodology_family"] == "OWNER_CASH_FLOW_OR_EARNINGS"
                )
            ),
            "objective": (
                "Map active portfolio owner-cash methods, preserving listing-specific economics "
                "and explicit reinvestment/SBC treatments."
            ),
            "entry_gates": [
                "Do not treat title similarity as proof that P-CPRT, P-MORN, P-UBER, DLO, RDDT "
                "and TSM share Toast assumptions or cash-flow semantics."
            ],
        },
        {
            "batch_id": "B3_PORTFOLIO_SOTP_METHOD_PROOF",
            "sequence": 3,
            "model_tabs": ["P-SPGI"],
            "objective": (
                "Prototype the S&P Global RemainCo plus linked Capital IQ Pro SOTP while "
                "preserving each component and ownership bridge."
            ),
            "entry_gates": [
                "Document component identity, non-controlling stakes, net debt, currency and "
                "share basis before native parity work."
            ],
        },
        {
            "batch_id": "B4_WATCHLIST_OWNER_CASH_FLOW_MAPPING",
            "sequence": 4,
            "model_tabs": tabs(
                lambda model: (
                    model["lifecycle"] == "WATCHLIST"
                    and model["methodology_family"] == "OWNER_CASH_FLOW_OR_EARNINGS"
                    and model["methodology_variant"] not in UNSUPPORTED_SPECIALIZATIONS
                    and model["migration_status"] != "READY_FOR_NATIVE_IMPORT"
                )
            ),
            "objective": (
                "After Portfolio work, migrate only the reviewed operating-company owner-cash "
                "cohort; group by confirmed input layout and currency evidence."
            ),
            "entry_gates": [
                "Use small batches and parity fixtures; exclude financial, credit, insurance and "
                "acquisition-reinvestment variants."
            ],
        },
        {
            "batch_id": "B5_NEW_METHOD_PILOTS",
            "sequence": 5,
            "model_tabs": tabs(
                lambda model: (
                    model["migration_status"] == "UNSUPPORTED_METHOD"
                    and model["model_tab"] != "P-SPGI"
                )
            ),
            "objective": (
                "Select one active representative at a time for financial/credit, insurance, "
                "alternative-asset and acquisition-reinvestment methods."
            ),
            "entry_gates": [
                "Do not generalize from HDFC residual-income parity to all financial-company tabs."
            ],
        },
        {
            "batch_id": "B6_WATCHLIST_METHOD_DISCOVERY",
            "sequence": 6,
            "model_tabs": tabs(
                lambda model: (
                    model["lifecycle"] == "WATCHLIST"
                    and model["methodology_family"] == "OTHER_METHOD_UNCLASSIFIED"
                    and model["migration_status"] == "NEEDS_MAPPING"
                )
            ),
            "objective": (
                "Review the remaining specialized Watchlist tabs and map only after methodology "
                "and identity are explicit."
            ),
            "entry_gates": ["No new native method is justified by an output-contract PASS alone."],
        },
        {
            "batch_id": "DEFER_DROPPED_MODELS",
            "sequence": 99,
            "model_tabs": tabs(lambda model: model["lifecycle"] == "DROP"),
            "objective": (
                "Retain as auditable legacy evidence; do not prioritize native input migration "
                "while lifecycle remains DROP."
            ),
            "entry_gates": [
                "A later explicit lifecycle change is required before reconsidering migration "
                "priority."
            ],
        },
    ]

    return {
        "schema_version": "1.0.0",
        "inventory_date": INVENTORY_DATE,
        "scope": "Assessment only; no model assumptions or outputs are imported.",
        "source": {
            "path": workbook_path.relative_to(REPOSITORY_ROOT).as_posix()
            if workbook_path.is_relative_to(REPOSITORY_ROOT)
            else workbook_path.name,
            "sha256": workbook.sha256,
            "effective_date": None,
            "effective_date_note": (
                "The workbook does not record a trustworthy snapshot effective date."
            ),
        },
        "summary": {
            "model_tabs": len(models),
            "tracked_universe_companies": len(registry),
            "native_model_input_sets_imported_in_this_milestone": 0,
            "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
            "methodology_counts": dict(sorted(methodology_counts.items())),
            "lifecycle_by_methodology": lifecycle_by_methodology,
            "current_output_status_counts": dict(sorted(output_status_counts.items())),
            "source_contract_status_counts": dict(sorted(source_contract_counts.items())),
            "contract_currency_status_counts": dict(sorted(currency_counts.items())),
            "source_model_currency_status_counts": dict(sorted(source_currency_counts.items())),
            "migration_status_counts": dict(sorted(migration_counts.items())),
            "active_ready_tabs": sorted(
                model["model_tab"]
                for model in models
                if model["migration_status"] == "READY_FOR_NATIVE_IMPORT"
                and model["lifecycle"] in {"PORTFOLIO", "WATCHLIST"}
            ),
            "identity_unresolved_tabs": sorted(
                model["model_tab"] for model in models if model["identity_status"] == "UNRESOLVED"
            ),
            "lifecycle_unresolved_tabs": sorted(
                model["model_tab"] for model in models if model["lifecycle"] == "UNRESOLVED"
            ),
            "data_check_tabs": sorted(
                model["model_tab"]
                for model in models
                if model["current_output_status"] == "DATA_CHECK"
            ),
            "expected_return_semantics": {
                "canonical_definition": (
                    "Probability-weighted explicit shareholder cash flows; scenario IRRs are "
                    "not averaged, dividends are explicit, and terminal proceeds are separate."
                ),
                "legacy_contract_warning": (
                    "The legacy Expected Cash-Flow IRR label is method-specific. P-GOOGL uses "
                    "probability-weighted enterprise UFCF and terminal value against implied "
                    "enterprise cost; owner-cash-flow tabs use their own owner-cash convention; "
                    "financial-company tabs may solve an implied equity return. Preserve each "
                    "published legacy value and do not relabel or recalculate it as canonical "
                    "shareholder-cash-flow IRR without a method-specific bridge."
                ),
                "parity_policy": "Legacy output history remains immutable and method-tagged.",
            },
        },
        "classification_notes": [
            "Methodology family is a first-pass classification from the model-tab title and "
            "selected explicit workbook labels, not formula parity acceptance.",
            "The source's PASS/NOT MAPPED labels concern normalized outputs; they do not "
            "establish safe assumption import.",
            "P-/W- prefixes are naming hints only. Lifecycle is derived from the Universe "
            "Registry rules and cached membership inputs.",
            "Only P-GOOGL, W-TOST, and W-HDFC have tab-specific native input/output parity "
            "fixtures. Dropped W-HDFC remains outside active migration priority.",
            "No tab is classified NOT_RELEVANT; dropped/archived tabs are marked LEGACY_ONLY "
            "and retained as evidence.",
        ],
        "recommended_batches": migration_batches,
        "models": models,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory legacy financial-model tabs without importing them."
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    inventory = build_inventory(args.workbook)
    rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote read-only model migration inventory: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
