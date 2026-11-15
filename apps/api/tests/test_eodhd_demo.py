"""Synthetic data only: never publish EODHD source responses in Git."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from portfolio_api.eodhd_demo import (
    EODHD_DEMO_PROVIDER_ID,
    EODHD_GENERAL_SCHEMA_VERSION,
    EodhdDemoMapping,
    EodhdDemoNormalizer,
    EodhdDemoProvider,
    _default_transport,
    fetch_demo_metadata,
    validate_eodhd_demo_metadata,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationResult,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.yahoo_finance import YahooListingFacts

MAPPING = EodhdDemoMapping(
    listing_id=UUID("11111111-1111-4111-8111-111111111111"),
    security_id=UUID("22222222-2222-4222-8222-222222222222"),
    company_id=UUID("33333333-3333-4333-8333-333333333333"),
)
CAPTURED = datetime(2026, 11, 15, 12, tzinfo=UTC)


def metadata(**changes: Any) -> RawProviderRecord:
    payload = json.dumps(
        {
            "Code": "AMZN",
            "PrimaryTicker": "AMZN.US",
            "Name": "Amazon.com Inc",
            "Exchange": "NASDAQ",
            "CurrencyCode": "USD",
            "Type": "Common Stock",
            "CIK": "0001018724",
            "IsDelisted": False,
            **changes,
        }
    ).encode()
    return RawProviderRecord(
        domain=ExternalDataDomain.COMPANY_REFERENCE,
        provider_id=EODHD_DEMO_PROVIDER_ID,
        provider_schema_version=EODHD_GENERAL_SCHEMA_VERSION,
        source_record_id="AMZN.US:GENERAL",
        media_type="application/json",
        retrieved_at=CAPTURED,
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


def query(**changes: Any) -> ProviderQuery:
    return ProviderQuery.model_validate(
        {
            "domain": ExternalDataDomain.MARKET_DATA,
            "subjects": (
                CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=MAPPING.listing_id),
            ),
            "start_date": date(2026, 11, 12),
            "end_date": date(2026, 11, 13),
            "requested_at": CAPTURED,
            **changes,
        }
    )


def record(rows: object) -> RawProviderRecord:
    provider = EodhdDemoProvider(
        MAPPING, metadata(), transport=lambda _: json.dumps(rows).encode(), clock=lambda: CAPTURED
    )
    return asyncio.run(provider.fetch(query()))[0]


def normalize(rows: object) -> NormalizationResult[YahooListingFacts]:
    return EodhdDemoNormalizer(MAPPING, metadata(), query()).normalize(record(rows))


def test_native_close_does_not_fabricate_split_adjustment_or_volume() -> None:
    result = normalize(
        [{"date": "2026-11-13", "close": 101.25, "adjusted_close": 98.5, "volume": 1000}]
    )
    assert result.disposition == NormalizationDisposition.ACCEPTED
    assert result.observation is not None
    fact = result.observation.prices[0]
    assert fact.provider_close == Decimal("101.25")
    assert fact.split_adjusted_close is None
    assert fact.total_return_close == Decimal("98.5")
    assert fact.volume is None
    assert fact.adjustment_basis == "UNADJUSTED_NATIVE_CLOSE"
    assert fact.currency == "USD"
    assert fact.source_price_multiplier == Decimal(1)
    assert fact.market_date == datetime(2026, 11, 13, tzinfo=UTC)
    assert fact.observed_at == CAPTURED
    assert result.issues[0].code == "INDICATIVE_DEMO_PRICE"
    assert result.observation.returned_exchange == "NASDAQ"


@pytest.mark.parametrize(
    "change",
    [
        {"Exchange": "NYSE"},
        {"CurrencyCode": "EUR"},
        {"Type": "ADR"},
        {"CIK": "0000000001"},
        {"IsDelisted": True},
        {"PrimaryTicker": "AMZN.F"},
        {"Name": "Different issuer"},
    ],
)
def test_exact_provider_identity_is_required(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="identity|listing"):
        validate_eodhd_demo_metadata(metadata(**change), MAPPING)


@pytest.mark.parametrize(
    "changes",
    [
        {"start_date": None},
        {"start_date": date(2025, 1, 1)},
        {"end_date": date(2026, 11, 15)},
        {"domain": ExternalDataDomain.FX},
        {"subjects": (CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=UUID(int=4)),)},
    ],
)
def test_query_rejected_before_transport(changes: dict[str, Any]) -> None:
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        return b"[]"

    provider = EodhdDemoProvider(MAPPING, metadata(), transport=transport)
    with pytest.raises(ValueError, match="exact listing"):
        asyncio.run(provider.fetch(query(**changes)))
    assert calls == []


def test_transport_is_one_fixed_demo_request_and_retains_exact_bytes() -> None:
    calls: list[str] = []
    payload = b'[ { "date": "2026-11-13", "close": 101.2500 } ]'

    def transport(url: str) -> bytes:
        calls.append(url)
        return payload

    provider = EodhdDemoProvider(MAPPING, metadata(), transport=transport, clock=lambda: CAPTURED)
    records = asyncio.run(provider.fetch(query()))
    assert len(calls) == len(records) == 1
    assert "api_token=demo" in calls[0]
    assert "/AMZN.US?" in calls[0]
    assert records[0].payload == payload
    assert records[0].provider_id == "EODHD_DEMO"
    assert records[0].retrieved_at == CAPTURED


def test_metadata_capture_retains_exact_bytes_without_implicit_price_request() -> None:
    calls: list[str] = []
    payload = metadata().payload
    assert payload is not None

    def transport(url: str) -> bytes:
        calls.append(url)
        return payload

    captured = fetch_demo_metadata(transport=transport, clock=lambda: CAPTURED)
    assert len(calls) == 1
    assert "filter=General" in calls[0] and "api_token=demo" in calls[0]
    assert captured.payload == payload
    assert captured.payload_sha256 == hashlib.sha256(payload).hexdigest()
    validate_eodhd_demo_metadata(captured, MAPPING)


@pytest.mark.parametrize("close", [0, -1, True, "NaN", "Infinity", "broken"])
def test_invalid_price_rejected(close: object) -> None:
    result = normalize([{"date": "2026-11-13", "close": close}])
    assert result.disposition == NormalizationDisposition.REJECTED
    assert result.observation is None


@pytest.mark.parametrize("bad_date", ["2026-11-11", "2026-11-14", "not-a-date"])
def test_out_of_scope_or_invalid_session_rejected(bad_date: str) -> None:
    assert (
        normalize([{"date": bad_date, "close": 100}]).disposition
        == NormalizationDisposition.REJECTED
    )


def test_duplicate_session_rejected_and_missing_observations_preserved() -> None:
    assert (
        normalize([{"date": "2026-11-13", "close": 100}] * 2).disposition
        == NormalizationDisposition.REJECTED
    )
    result = normalize(
        [{"date": "2026-11-12", "close": None}, {"date": "2026-11-13", "close": 100}]
    )
    assert result.observation is not None
    assert len(result.observation.prices) == 1
    assert result.observation.missing_close_count == 1
    assert "MISSING_CLOSE" in {issue.code for issue in result.issues}
    empty = normalize([])
    assert empty.observation is not None and not empty.observation.prices
    assert "MISSING_CLOSE" in {issue.code for issue in empty.issues}


def test_other_provider_or_scope_cannot_be_normalized() -> None:
    original = record([{"date": "2026-11-13", "close": 100}])
    normalizer = EodhdDemoNormalizer(MAPPING, metadata(), query())
    for changed in [
        original.model_copy(update={"provider_id": "YAHOO_FINANCE"}),
        original.model_copy(update={"source_record_id": "other-listing"}),
    ]:
        assert normalizer.normalize(changed).disposition == NormalizationDisposition.REJECTED


@pytest.mark.parametrize(
    "url",
    [
        "https://other.example/api/eod/AMZN.US?api_token=demo",
        "https://eodhd.com/api/eod/MSFT.US?api_token=demo",
        "https://eodhd.com/api/eod/AMZN.US?api_token=paid-key",
        "http://eodhd.com/api/eod/AMZN.US?api_token=demo",
    ],
)
def test_default_transport_rejects_nonallowlisted_urls_before_network(url: str) -> None:
    with pytest.raises(ValueError, match="fixed-symbol demo"):
        _default_transport(url)
