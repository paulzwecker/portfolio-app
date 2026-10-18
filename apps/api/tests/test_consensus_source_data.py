"""Regression checks that reconcile consensus history with the private source workbook."""

import pytest

from portfolio_api.consensus_estimates import (
    FMP_PROVIDER_ID,
    LEGACY_PROVIDER_ID,
    NORMALIZER_VERSION,
    legacy_estimate_import_plan,
)

pytestmark = pytest.mark.source_data


def test_legacy_history_reconciliation_only_imports_supported_snapshot_fields() -> None:
    report, observations = legacy_estimate_import_plan()
    facts = [item for item in observations if "value" in item]

    assert report["source_sha256"]
    assert report["company_rows"] == 79
    assert report["resolved_company_count"] == 79
    assert report["snapshot_date"] == "2026-09-12"
    assert len(facts) == 67
    assert {item["status"] for item in facts} == {"DATA_CHECK"}
    assert {item["metric"] for item in facts} == {"REVENUE", "EPS"}
    assert {item["horizon"] for item in facts} == {"FY+1", "FY+2"}
    assert all(item["snapshot_date"] == "2026-09-12" for item in facts)
    assert report["limitations"]
    assert NORMALIZER_VERSION == "consensus-estimates-v1"
    assert LEGACY_PROVIDER_ID != FMP_PROVIDER_ID
