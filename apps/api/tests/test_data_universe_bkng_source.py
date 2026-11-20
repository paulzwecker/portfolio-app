"""Booking Holdings Q3 2026 primary SEC 10-Q source verification, offline."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from portfolio_api.data_universe_public_evidence import (
    BKNG_Q3_2026_CIK,
    BKNG_Q3_2026_URL,
    extract_booking_q3_2026,
    verify_booking_q3_2026_pack,
    verify_official_source,
    verify_source_html,
)
from portfolio_api.data_universe_shadow import EvidencePackV1

HERE = Path(__file__).parent / "fixtures"
FILING = (HERE / "data_universe_bkng_q3_2026_excerpt.html").read_bytes()


def _pack() -> EvidencePackV1:
    return EvidencePackV1.model_validate_json(
        (HERE / "data_universe_bkng_q3_2026.json").read_text(encoding="utf-8")
    )


def test_booking_exact_q3_operating_values_keep_rounded_reporting_units() -> None:
    assert extract_booking_q3_2026(FILING) == {
        "bkng.room_nights": 345,
        "bkng.flight_tickets": 21,
        "bkng.gross_bookings": 54461,
    }
    report = verify_source_html(_pack(), FILING)
    assert report["status"] == "SOURCE_MATCHED"
    assert report["profile"] == "BKNG_Q3_2026_SEC_10Q"
    assert report["issuer_cik"] == BKNG_Q3_2026_CIK == "0001075531"
    assert report["source_reference"] == BKNG_Q3_2026_URL
    assert len(report["facts_checked"]) == 3
    assert len(report["source_sha256"]) == 64


@pytest.mark.parametrize(
    "modified",
    [
        FILING.replace(b">345<", b">346<"),
        FILING.replace(b">21<", b">22<"),
        FILING.replace(b"54,461", b"54,462"),
        FILING.replace(b"54,461", b"154,461"),
        FILING.replace(b"September 30, 2026", b"December 31, 2026"),
        FILING.replace(b"FORM 10-Q", b"FORM 10-K"),
        FILING.replace(b"Booking Holdings Inc.", b"Other Company Inc."),
        FILING.replace(b"<th>2026</th><th>2025</th>", b"<th>2025</th><th>2026</th>"),
        FILING.replace(b"Three Months Ended", b"Nine Months Ended"),
        FILING + FILING,
    ],
)
def test_booking_changed_filing_cannot_be_promoted(modified: bytes) -> None:
    with pytest.raises(ValueError):
        verify_booking_q3_2026_pack(_pack(), modified)


def test_booking_rounded_reported_facts_cannot_be_silently_upgraded_to_exact() -> None:
    pack = _pack()
    pack.kpi_observations[0].value_qualifier = "EQ"
    with pytest.raises(ValueError, match="evidence mismatch"):
        verify_booking_q3_2026_pack(pack, FILING)
    pack = _pack()
    pack.kpi_observations[2].value = 54500
    with pytest.raises(ValueError, match="evidence mismatch"):
        verify_booking_q3_2026_pack(pack, FILING)
    pack = _pack()
    pack.kpi_observations[1].scale = 1
    with pytest.raises(ValueError, match="evidence mismatch"):
        verify_booking_q3_2026_pack(pack, FILING)
    pack = _pack()
    pack.guidance_observations.append(
        pack.guidance_observations[0] if pack.guidance_observations else
        # Reject extra unverifiable guidance regardless of its value.
        __import__("portfolio_api.company_observation_proposals", fromlist=["GuidanceObservationItem"]).GuidanceObservationItem.model_validate({
            "metric_key": "bkng.room_nights",
            "period_type": "QUARTER", "period_start": "2026-10-01",
            "period_end": "2026-12-31", "unit": "room_nights", "scale": "1000000",
            "currency": None, "basis": "COMPANY_GUIDANCE", "scope_json": {},
            "source_type": "SEC_10Q", "source_reference": BKNG_Q3_2026_URL,
            "external_guidance_id": "invented", "lower_value": "1",
            "upper_value": "3"
        })
    )
    with pytest.raises(ValueError, match="Unsupported Booking"):
        verify_booking_q3_2026_pack(pack, FILING)


def test_sec_live_read_needs_operator_contact_and_makes_no_request_without_one() -> None:
    with (
        patch.dict("os.environ", {"SEC_USER_AGENT": ""}),
        patch("portfolio_api.data_universe_public_evidence.build_opener") as opener,
        pytest.raises(ValueError, match="SEC_USER_AGENT"),
    ):
        verify_official_source(_pack())
    opener.assert_not_called()


def test_source_registry_rejects_unknown_issuer() -> None:
    pack = _pack()
    pack.issuer_ticker = "OTHER"
    with pytest.raises(ValueError, match="approved"):
        verify_source_html(pack, FILING)
