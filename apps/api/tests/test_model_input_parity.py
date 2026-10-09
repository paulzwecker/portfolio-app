"""Fixture-only verification of the reviewed native model migration mappings."""

from __future__ import annotations

from datetime import UTC, datetime

from portfolio_api.legacy_import import Workbook
from portfolio_api.model_input_migration import (
    DEFAULT_WORKBOOK,
    EXPECTED_MODEL_KEYS,
    PARITY_PROVEN_MODEL_KEYS,
    build_native_model_parity_report,
)


def source_workbook() -> Workbook:
    return Workbook.read(DEFAULT_WORKBOOK, lambda name: name in EXPECTED_MODEL_KEYS)


def test_parity_receipt_is_read_only_and_identifies_complete_portfolio_coverage() -> None:
    report = build_native_model_parity_report(
        source_workbook(), assessed_at=datetime(2026, 10, 6, tzinfo=UTC)
    )

    assert report["mode"] == "PARITY_ONLY"
    assert report["canonical_application_state"] == "NOT_QUERIED"
    assert report["input_sets_imported"] == 0
    assert report["parity_pass_model_keys"] == list(PARITY_PROVEN_MODEL_KEYS)
    assert report["expected_irr_canonical_comparability_counts"] == {
        "NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR": 16
    }

    models = {row["model_key"]: row for row in report["models"]}
    expected_listings = {
        "P-GOOGL": ("GOOGL", "NASDAQ", "USD"),
        "P-ISRG": ("ISRG", "NASDAQ", "USD"),
        "P-MA": ("MA", "NYSE", "USD"),
        "P-CPRT": ("CPRT", "NASDAQ", "USD"),
        "P-UBER": ("UBER", "NYSE", "USD"),
    }
    for model_key, expected in expected_listings.items():
        listing = models[model_key]["listing_requirement"]
        assert (listing["ticker"], listing["venue"], listing["currency"]) == expected

    assert (
        models["P-CPRT"]["input_mapping"]["source_cells"]["scenarios.BASE.year10_ufcf_growth"]
        == "C210"
    )
    assert (
        models["P-UBER"]["input_mapping"]["source_cells"]["scenarios.BEAR.year10_ufcf_growth"]
        == "B210"
    )
    assert models["P-AMD"]["projection_reconciliation"]["passed"] == 30
    assert "SHARE_BASIS_MISMATCH" in models["P-AMD"]["blocking_categories"]
    assert "METHODOLOGY_MISMATCH" in models["P-AMZN"]["blocking_categories"]
    assert "METHODOLOGY_MISMATCH" in models["P-HIMS"]["blocking_categories"]
    assert "METHODOLOGY_MISMATCH" in models["P-MSFT"]["blocking_categories"]
    assert "INVALID_SOURCE_ASSUMPTION" in models["P-MSCI"]["blocking_categories"]
    assert "MISSING_SOURCE_DATA" in models["P-MORN"]["blocking_categories"]


def test_return_parity_and_shareholder_irr_comparability_are_separate() -> None:
    report = build_native_model_parity_report(
        source_workbook(), assessed_at=datetime(2026, 10, 6, tzinfo=UTC)
    )
    models = {row["model_key"]: row for row in report["models"]}

    for model_key in PARITY_PROVEN_MODEL_KEYS:
        item = models[model_key]
        assert item["status"] == "PARITY_PASS"
        assert item["expected_irr"]["native_method_return_parity"] == "PARITY_PASS"
        assert (
            item["expected_irr"]["canonical_shareholder_irr_comparability"]
            == "NOT_COMPARABLE_TO_CANONICAL_SHAREHOLDER_IRR"
        )
        assert item["expected_irr"]["reinterpreted_as_canonical_shareholder_irr"] is False
        assert item["source_price_for_parity"]["effective_at"] is None
        assert item["source_price_for_parity"]["use"] == "PARITY_ONLY_NOT_STORED_AS_MARKET_DATA"
        assert item["apply_status"] == "NOT_APPLIED"

    nvo = models["P-NVO"]
    assert nvo["listing_requirement"] == {
        "ticker": "NOVO-B",
        "venue": "CPH",
        "currency": "DKK",
        "security_type": "COMMON_STOCK",
    }
    assert nvo["source_price_for_parity"]["effective_at"] is None
    assert nvo["application_identity_validation"] == "NOT_CHECKED_PARITY_ONLY"
