"""Provider-boundary contract tests; no provider or network is required."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    RawProviderRecord,
    raw_batch_fingerprint,
    raw_record_fingerprint,
)

LISTING_ID = UUID("11111111-1111-4111-8111-111111111111")
RETRIEVED_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)


def raw_record(payload: bytes = b'{"close": 12.34}') -> RawProviderRecord:
    return RawProviderRecord(
        domain=ExternalDataDomain.MARKET_DATA,
        provider_id="example-feed",
        provider_schema_version="quotes-v2",
        source_record_id="daily-close:NASDAQ:EX:2026-10-02",
        source_url="https://data.example.test/quotes/EX",
        media_type="application/json",
        retrieved_at=RETRIEVED_AT,
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_provider_query_uses_canonical_listing_identity_and_date_window() -> None:
    query = ProviderQuery(
        domain=ExternalDataDomain.MARKET_DATA,
        subjects=[CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=LISTING_ID)],
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 5),
        requested_at=RETRIEVED_AT,
    )

    assert query.subjects[0].id == LISTING_ID
    assert query.domain == ExternalDataDomain.MARKET_DATA
    with pytest.raises(ValidationError, match="start_date"):
        ProviderQuery(
            domain=ExternalDataDomain.MARKET_DATA,
            subjects=[CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=LISTING_ID)],
            start_date=date(2026, 10, 6),
            end_date=date(2026, 10, 5),
            requested_at=RETRIEVED_AT,
        )


def test_raw_record_requires_an_exact_payload_digest_and_timezone() -> None:
    record = raw_record()
    assert record.payload is not None
    assert record.payload == b'{"close": 12.34}'
    assert record.payload_sha256 == hashlib.sha256(record.payload).hexdigest()

    with pytest.raises(ValidationError, match="does not match"):
        RawProviderRecord.model_validate({**record.model_dump(), "payload_sha256": "0" * 64})
    with pytest.raises(ValidationError, match="timezone-aware"):
        RawProviderRecord.model_validate(
            {**record.model_dump(), "retrieved_at": datetime(2026, 10, 5, 12)}
        )


def test_large_raw_payload_can_use_an_immutable_storage_reference() -> None:
    payload = raw_record()
    referenced = RawProviderRecord(
        domain=payload.domain,
        provider_id=payload.provider_id,
        provider_schema_version=payload.provider_schema_version,
        source_record_id="filing:0000000000-26-000001",
        source_url="https://filings.example.test/0000000000-26-000001.pdf",
        media_type="application/pdf",
        retrieved_at=RETRIEVED_AT,
        payload_ref="object://raw-data/sha256/" + payload.payload_sha256,
        payload_sha256=payload.payload_sha256,
    )
    assert referenced.payload is None
    assert referenced.payload_ref is not None
    with pytest.raises(ValidationError, match="exactly one"):
        RawProviderRecord(
            domain=payload.domain,
            provider_id=payload.provider_id,
            media_type=payload.media_type,
            retrieved_at=RETRIEVED_AT,
            payload=payload.payload,
            payload_ref="object://raw-data/example",
            payload_sha256=payload.payload_sha256,
        )


def test_raw_record_fingerprint_is_repeatable_and_changes_for_corrections() -> None:
    original = raw_record()
    replay = raw_record()
    correction = raw_record(b'{"close": 12.35}')

    assert raw_record_fingerprint(original) == raw_record_fingerprint(replay)
    assert raw_record_fingerprint(original) != raw_record_fingerprint(correction)
    assert len(raw_record_fingerprint(original)) == 64


def test_raw_batch_fingerprint_is_order_independent_and_excludes_retry_time() -> None:
    query = ProviderQuery(
        domain=ExternalDataDomain.MARKET_DATA,
        subjects=[CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=LISTING_ID)],
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 5),
        requested_at=RETRIEVED_AT,
    )
    retry = query.model_copy(update={"requested_at": datetime(2026, 10, 6, tzinfo=UTC)})
    first = raw_record()
    second = raw_record(b'{"close": 12.35}')

    assert raw_batch_fingerprint("example-feed", query, [first, second]) == (
        raw_batch_fingerprint("example-feed", retry, [second, first])
    )
    assert raw_batch_fingerprint("example-feed", query, [first]) != (
        raw_batch_fingerprint("example-feed", query, [second])
    )
    with pytest.raises(ValueError, match="match the batch provider"):
        raw_batch_fingerprint("other-feed", query, [first])


def test_normalization_requires_domain_observation_or_explicit_rejection() -> None:
    accepted = NormalizationResult[dict[str, str]](
        disposition=NormalizationDisposition.ACCEPTED,
        observation={"currency": "USD", "close": "12.34"},
    )
    rejected = NormalizationResult[dict[str, str]](
        disposition=NormalizationDisposition.REJECTED,
        observation=None,
        issues=[
            NormalizationIssue(
                code="UNKNOWN_LISTING",
                message="No exact canonical listing match was found.",
                severity="ERROR",
            )
        ],
    )

    assert accepted.observation == {"currency": "USD", "close": "12.34"}
    assert rejected.disposition == NormalizationDisposition.REJECTED
    with pytest.raises(ValidationError, match="requires an observation"):
        NormalizationResult[dict[str, str]](
            disposition=NormalizationDisposition.ACCEPTED,
            observation=None,
        )


def test_currency_pair_subject_is_explicit_and_not_an_entity_ticker() -> None:
    pair = CanonicalSubjectRef(
        kind=CanonicalSubjectKind.CURRENCY_PAIR,
        base_currency="EUR",
        quote_currency="USD",
    )
    assert pair.id is None
    with pytest.raises(ValidationError, match="distinct"):
        CanonicalSubjectRef(
            kind=CanonicalSubjectKind.CURRENCY_PAIR,
            base_currency="EUR",
            quote_currency="EUR",
        )
