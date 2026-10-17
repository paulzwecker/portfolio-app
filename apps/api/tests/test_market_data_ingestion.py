from typing import Any, cast
from uuid import uuid4

from sqlalchemy.orm import Session

from portfolio_api.market_data_ingestion import (
    active_companies_without_listing_for_scope,
    apply_provider_import,
)


def test_applied_market_refresh_reports_partial_when_provider_fetch_fails() -> None:
    report: dict[str, Any] = {
        "plans": [],
        "provider_fetch_failures": [{"source_record_id": "LISTING:test", "code": "NETWORK_ERROR"}],
        "market_data_batches": [],
        "fx_batches": [],
    }

    result = apply_provider_import(cast(Session, None), report)

    assert result["status"] == "PARTIAL"
    assert result["persistence"]["inserted_totals"]["price_observations"] == 0


def test_applied_market_refresh_reports_applied_when_clean_and_idempotent() -> None:
    report: dict[str, Any] = {"plans": [], "market_data_batches": [], "fx_batches": []}

    result = apply_provider_import(cast(Session, None), report)

    assert result["status"] == "APPLIED"
    assert result["persistence"]["inserted_totals"] == {
        "raw_payloads": 0,
        "price_observations": 0,
        "corporate_actions": 0,
        "fx_observations": 0,
    }


def test_scoped_listing_diagnostics_exclude_unrelated_active_companies() -> None:
    scoped_company_id = uuid4()
    unrelated_company_id = uuid4()
    active_companies = {
        scoped_company_id: ("Scoped issuer", "PORTFOLIO"),
        unrelated_company_id: ("Unmapped issuer", "WATCHLIST"),
    }

    scoped = active_companies_without_listing_for_scope(
        active_companies,
        {scoped_company_id},
        company_scope={scoped_company_id},
    )
    universe = active_companies_without_listing_for_scope(
        active_companies,
        {scoped_company_id},
    )

    assert scoped == []
    assert universe == [
        {
            "company_id": str(unrelated_company_id),
            "company": "Unmapped issuer",
            "lifecycle": "WATCHLIST",
        }
    ]
