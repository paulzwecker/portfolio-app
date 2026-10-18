"""Regression checks for the private, reviewed Yahoo listing crosswalk."""

import pytest

from portfolio_api.market_data_ingestion import CROSSWALK_PATH
from portfolio_api.yahoo_finance import FX_SYMBOLS, load_yahoo_crosswalk, yahoo_mapping_for_listing

pytestmark = pytest.mark.source_data


def test_checked_in_crosswalk_covers_exact_held_listing_identities() -> None:
    crosswalk = load_yahoo_crosswalk(CROSSWALK_PATH)
    held_tsm = yahoo_mapping_for_listing(
        crosswalk,
        venue="NYSE",
        ticker="TSM",
        currency="USD",
        security_type="ADR",
    )
    held_spyy = yahoo_mapping_for_listing(
        crosswalk,
        venue="ETR",
        ticker="SPYY",
        currency="EUR",
        security_type="ETF",
    )

    assert len(crosswalk.mappings) == 94
    assert {item.currency for item in crosswalk.mappings} - {"EUR"} <= {
        base for base, quote in FX_SYMBOLS if quote == "EUR"
    }
    assert held_tsm is not None and held_tsm.provider_symbol == "TSM"
    assert held_spyy is not None and held_spyy.provider_symbol == "SPYY.DE"


def test_reviewed_watchlist_listing_gap_crosswalk_is_primary_source_linked() -> None:
    crosswalk = load_yahoo_crosswalk(CROSSWALK_PATH)
    expected = {
        ("SWX", "ACLN", "CHF", "ACLN.SW"),
        ("STO", "BONEX", "SEK", "BONEX.ST"),
        ("PAR", "EXENS", "EUR", "EXENS.PA"),
        ("NYSE", "FN", "USD", "FN"),
        ("STO", "IVSO", "SEK", "IVSO.ST"),
        ("OSL", "MEDI", "NOK", "MEDI.OL"),
        ("NASDAQ", "META", "USD", "META"),
        ("NASDAQ", "NVMI", "USD", "NVMI"),
        ("ETR", "RHM", "EUR", "RHM.DE"),
        ("ETR", "V1NC", "EUR", "V1NC.DE"),
    }
    resolved = {
        (item.venue, item.ticker, item.currency, item.provider_symbol): item
        for item in crosswalk.mappings
        if item.identity_status == "READY_FOR_CANONICAL_IMPORT"
    }

    assert expected <= resolved.keys()
    for identity in expected:
        item = resolved[identity]
        assert item.verification_status == "VERIFIED"
        assert item.canonical_company_id is not None
        assert item.canonical_security_id is not None
        assert item.canonical_listing_id is not None
        assert item.identity_source_ref is not None
        assert item.identity_source_ref.startswith("https://")
