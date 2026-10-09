"""Checks the checked-in assessment against its exact source workbook snapshot."""

import json
from typing import Any

import pytest

from portfolio_api.model_migration_inventory import DEFAULT_OUTPUT, build_inventory


@pytest.fixture(scope="module")
def inventory() -> dict[str, Any]:
    return build_inventory()


def test_inventory_matches_all_model_tabs_in_source_snapshot(
    inventory: dict[str, Any],
) -> None:
    checked_in = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

    assert checked_in == inventory
    summary = inventory["summary"]
    models = inventory["models"]
    assert summary["model_tabs"] == 116
    assert summary["tracked_universe_companies"] == 219
    assert len({model["model_tab"] for model in models}) == 116


def test_inventory_keeps_output_publication_separate_from_import_readiness(
    inventory: dict[str, Any],
) -> None:
    models = {model["model_tab"]: model for model in inventory["models"]}

    assert inventory["summary"]["source_contract_status_counts"] == {
        "NOT_MAPPED": 11,
        "NO_CONTRACT": 8,
        "PASS": 97,
    }
    assert inventory["summary"]["current_output_status_counts"] == {
        "DATA_CHECK": 1,
        "NOT_MAPPED": 11,
        "NO_CONTRACT": 8,
        "PUBLISHED": 96,
    }
    assert models["W-PLEJD"]["source_contract_status"] == "PASS"
    assert models["W-PLEJD"]["current_output_status"] == "DATA_CHECK"
    assert models["W-PLEJD"]["migration_status"] == "DATA_CHECK"
    assert models["P-GOOGL"]["current_output_status"] == "PUBLISHED"
    assert models["P-GOOGL"]["migration_status"] == "READY_FOR_NATIVE_IMPORT"


def test_only_active_tabs_with_representative_parity_are_ready(
    inventory: dict[str, Any],
) -> None:
    models = {model["model_tab"]: model for model in inventory["models"]}

    assert inventory["summary"]["active_ready_tabs"] == [
        "P-CPRT",
        "P-GOOGL",
        "P-ISRG",
        "P-MA",
        "P-UBER",
        "W-TOST",
    ]
    assert models["P-CPRT"]["methodology_family"] == "UFCF_DCF_10Y_FADE"
    assert models["P-UBER"]["methodology_family"] == "UFCF_DCF_10Y_FADE"
    assert models["P-MORN"]["methodology_family"] == "UFCF_DCF_10Y_FADE"
    assert models["P-MORN"]["migration_status"] == "NEEDS_MAPPING"
    assert "Formula audit" in models["P-CPRT"]["methodology_evidence"]
    assert models["W-TOST"]["lifecycle"] == "WATCHLIST"
    assert models["W-TOST"]["assumption_mapping_status"] == (
        "VERIFIED_BY_REPRESENTATIVE_PARITY_FIXTURE"
    )
    assert models["W-TOST"]["model_currency"] == "USD"
    assert models["W-TOST"]["contract_currency_status"] == "UNKNOWN"
    assert models["W-HDFC"]["native_method_support"] == "PARITY_PROVEN_FOR_TAB"
    assert models["W-HDFC"]["lifecycle"] == "DROP"
    assert models["W-HDFC"]["migration_status"] == "LEGACY_ONLY"
    assert models["W-JDG"]["model_currency"] == "GBP"
    assert models["W-KXS"]["model_currency"] is None
    assert models["W-KXS"]["currency_evidence_type"] == "MULTIPLE_UNIT_CURRENCIES_UNRESOLVED"


def test_lifecycle_currency_identity_and_return_semantics_gaps_are_explicit(
    inventory: dict[str, Any],
) -> None:
    summary = inventory["summary"]
    models = {model["model_tab"]: model for model in inventory["models"]}

    assert summary["lifecycle_counts"] == {
        "DROP": 19,
        "PORTFOLIO": 21,
        "UNRESOLVED": 5,
        "WATCHLIST": 71,
    }
    assert summary["contract_currency_status_counts"] == {"DOCUMENTED": 54, "UNKNOWN": 62}
    assert summary["source_model_currency_status_counts"] == {
        "DOCUMENTED": 106,
        "UNKNOWN": 10,
    }
    assert summary["identity_unresolved_tabs"] == ["P-MELI-SOTP", "P-SPGI-CIQ"]
    assert summary["lifecycle_unresolved_tabs"] == [
        "P-MELI-SOTP",
        "P-SPGI-CIQ",
        "W-ARENIT",
        "W-ENGCON-B",
        "W-PLEJD",
    ]
    assert models["P-NVO"]["model_currency"] == "DKK"
    assert "Copenhagen B share" in models["P-NVO"]["assessment_notes"]

    semantics = summary["expected_return_semantics"]
    assert "shareholder" in semantics["canonical_definition"]
    assert "enterprise UFCF" in semantics["legacy_contract_warning"]
    assert "do not relabel" in semantics["legacy_contract_warning"]


def test_recommended_batches_put_active_portfolio_methods_ahead_of_bulk_watchlist(
    inventory: dict[str, Any],
) -> None:
    batches = {batch["batch_id"]: batch for batch in inventory["recommended_batches"]}

    assert batches["B0_PARITY_BACKED_ACTIVE_IMPORT"]["model_tabs"] == [
        "P-CPRT",
        "P-GOOGL",
        "P-ISRG",
        "P-MA",
        "P-UBER",
        "W-TOST",
    ]
    assert batches["B1_PORTFOLIO_DCF_COHORT"]["model_tabs"] == [
        "P-ADYEN",
        "P-AMD",
        "P-AMZN",
        "P-ASML",
        "P-BKNG",
        "P-CELH",
        "P-HIMS",
        "P-MELI",
        "P-MORN",
        "P-MSCI",
        "P-MSFT",
    ]
    assert batches["B2_PORTFOLIO_OWNER_CASH_FLOW_VARIANTS"]["model_tabs"] == [
        "W-DLO",
        "W-RDDT",
        "W-TSM",
    ]
    assert "P-SPGI" in batches["B3_PORTFOLIO_SOTP_METHOD_PROOF"]["model_tabs"]
    assert len(batches["B4_WATCHLIST_OWNER_CASH_FLOW_MAPPING"]["model_tabs"]) == 53
    assert len(batches["DEFER_DROPPED_MODELS"]["model_tabs"]) == 19
