"""Isolated verification of real public issuer facts; tests do not make live requests."""

import copy
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

import pytest

from portfolio_api.data_universe_public_evidence import (
    UBER_Q3_2026_URL,
    extract_uber_q3_2026,
    verify_official_uber_release,
    verify_uber_q3_2026_pack,
)
from portfolio_api.data_universe_shadow import EvidencePackV1

FIXTURE = Path(__file__).parent / "fixtures" / "data_universe_uber_q3_2026.json"

# Synthetic structure only; the full issuer page is not redistributed in Git.
ISSUER_HTML = (
    Path(__file__).parent / "fixtures" / "data_universe_uber_q3_2026_excerpt.html"
).read_bytes()


def _pack() -> EvidencePackV1:
    return EvidencePackV1.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_uber_q3_exact_public_facts_and_source_hash() -> None:
    assert tuple(str(value) for value in extract_uber_q3_2026(ISSUER_HTML)) == (
        "4061",
        "59819",
        "63250.00",
        "65250.00",
    )
    report = verify_uber_q3_2026_pack(_pack(), ISSUER_HTML)
    assert report["status"] == "SOURCE_MATCHED"
    assert report["profile"] == "UBER_Q3_2026_IR"
    assert report["source_reference"] == UBER_Q3_2026_URL
    assert len(report["source_sha256"]) == 64
    assert len(report["facts_checked"]) == 3


@pytest.mark.parametrize(
    "modified",
    [
        ISSUER_HTML.replace(b"4,061", b"4,062"),
        ISSUER_HTML.replace(b"59,819", b"59,820"),
        ISSUER_HTML.replace(b"$65.25", b"$65.30"),
        ISSUER_HTML.replace(b"November 04, 2026", b"November 05, 2026"),
        ISSUER_HTML.replace(b"(In millions", b"(In thousands"),
        ISSUER_HTML.replace(b"2025</th><th>2026", b"2026</th><th>2025"),
        ISSUER_HTML + ISSUER_HTML,
    ],
)
def test_changed_or_ambiguous_source_never_verifies(modified: bytes) -> None:
    with pytest.raises(ValueError):
        verify_uber_q3_2026_pack(_pack(), modified)


def test_changed_pack_scale_basis_identity_and_publication_time_fail() -> None:
    cases = []
    pack = _pack()
    pack.kpi_observations[0].scale = Decimal("1000")
    cases.append(pack)
    pack = _pack()
    pack.kpi_observations[0].basis = "ADJUSTED"
    cases.append(pack)
    pack = _pack()
    pack.kpi_observations[0].reported_at = datetime(2026, 11, 4, 13, tzinfo=UTC)
    cases.append(pack)
    pack = _pack()
    pack.guidance_observations[0].upper_value = Decimal("65500")
    cases.append(pack)
    pack = _pack()
    pack.source_reference = "https://example.com/redirected"
    cases.append(pack)
    pack = _pack()
    pack.guidance_observations[0].period_end = date(2027, 3, 31)
    cases.append(pack)
    for case in cases:
        with pytest.raises(ValueError):
            verify_uber_q3_2026_pack(case, ISSUER_HTML)


def test_public_source_fetch_uses_fixed_https_no_credentials_or_redirects() -> None:
    class Headers:
        def get_content_type(self) -> str:
            return "text/html"

    class Response:
        status = 200
        headers = Headers()

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            assert limit > len(ISSUER_HTML)
            return ISSUER_HTML

    class Opener:
        def open(self, request: Request, timeout: int) -> Response:
            assert request.full_url == UBER_Q3_2026_URL
            assert request.get_method() == "GET"
            assert timeout == 15
            return Response()

    with patch(
        "portfolio_api.data_universe_public_evidence.build_opener",
        return_value=Opener(),
    ) as opener:
        verified = verify_official_uber_release(_pack())
    assert verified["status"] == "SOURCE_MATCHED"
    assert opener.call_count == 1

    not_issuer = copy.deepcopy(_pack())
    not_issuer.source_reference = "https://example.com"
    with (
        pytest.raises(ValueError, match="approved Uber"),
        patch("portfolio_api.data_universe_public_evidence.build_opener") as blocked,
    ):
        verify_official_uber_release(not_issuer)
    blocked.assert_not_called()


def test_source_size_limit_fails_closed() -> None:
    from portfolio_api.data_universe_public_evidence import MAX_ISSUER_BYTES

    with pytest.raises(ValueError, match="byte budget"):
        verify_uber_q3_2026_pack(_pack(), b"x" * (MAX_ISSUER_BYTES + 1))
