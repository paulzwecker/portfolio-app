"""Synthetic exact-rate fixtures; no network requests or production data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from portfolio_api.ecb_reference import (
    ECB_PROVIDER_ID,
    ECB_SCHEMA_VERSION,
    EcbFxNormalizer,
    EcbReferenceProvider,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.market_data_ingestion import fx_provider_batch_plan

START = date(2026, 11, 9)
END = date(2026, 11, 10)
CAPTURED = datetime(2026, 11, 15, tzinfo=UTC)
HEADER = (
    "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,"
    "OBS_VALUE,OBS_STATUS,UNIT,UNIT_MULT\n"
)


def row(day: str = "2026-11-09", rate: str = "1.25", currency: str = "USD") -> str:
    return f"EXR.D.{currency}.EUR.SP00.A,D,{currency},EUR,SP00,A,{day},{rate},A,{currency},0\n"


def record(payload: str, currency: str = "USD") -> RawProviderRecord:
    body = payload.encode()
    return RawProviderRecord(
        domain=ExternalDataDomain.FX,
        provider_id=ECB_PROVIDER_ID,
        provider_schema_version=ECB_SCHEMA_VERSION,
        source_record_id=f"FX:{currency}/EUR",
        source_url="https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A",
        media_type="text/csv",
        retrieved_at=CAPTURED,
        payload=body,
        payload_sha256=hashlib.sha256(body).hexdigest(),
    )


def query(currency: str = "USD", **changes: object) -> ProviderQuery:
    return ProviderQuery.model_validate(
        {
            "domain": ExternalDataDomain.FX,
            "subjects": (
                CanonicalSubjectRef(
                    kind=CanonicalSubjectKind.CURRENCY_PAIR,
                    base_currency=currency,
                    quote_currency="EUR",
                ),
            ),
            "start_date": START,
            "end_date": END,
            "requested_at": CAPTURED,
            **changes,
        }
    )


def test_reciprocal_retains_reference_date_retrieval_provenance_and_identity() -> None:
    raw = record(HEADER + row() + row("2026-11-10", "1.28"))
    normalizer = EcbFxNormalizer(start_date=START, end_date=END)
    result = normalizer.normalize(raw)
    assert result.observation is not None
    first, second = result.observation.observations
    assert first.rate == Decimal("0.80000000000000")
    assert second.rate == Decimal("0.78125000000000")
    assert first.provider_base_currency == "EUR"
    assert first.provider_quote_currency == "USD"
    assert first.inverted and not first.is_current_quote
    assert first.effective_at == datetime(2026, 11, 9, tzinfo=UTC)
    assert first.observed_at == CAPTURED
    plan = fx_provider_batch_plan(
        query(),
        [raw],
        normalizer,
        provider_id=ECB_PROVIDER_ID,
        provider_schema_version=ECB_SCHEMA_VERSION,
        provider_label="European Central Bank",
    )
    assert plan is not None
    assert plan["records"][0].payload == raw.payload
    assert plan["batch"]["provider_id"] == ECB_PROVIDER_ID
    assert plan["batch"]["normalizer_version"] == normalizer.version
    assert plan["fx"][0]["provider"] == ECB_PROVIDER_ID
    assert "inverted" in plan["fx"][0]["reason"]
    assert plan["prices"] == plan["actions"] == []
    with pytest.raises(ValueError, match="mix provider"):
        fx_provider_batch_plan(query(), [raw], normalizer)


@pytest.mark.parametrize(
    "currency,rate,expected",
    [
        ("USD", "1.15", "0.86956521739130"),
        ("DKK", "7.45", "0.13422818791946"),
    ],
)
def test_explicit_pair_rate_direction(currency: str, rate: str, expected: str) -> None:
    result = EcbFxNormalizer(start_date=START, end_date=END).normalize(
        record(HEADER + row(rate=rate, currency=currency), currency)
    )
    assert result.observation is not None
    assert result.observation.observations[0].rate == Decimal(expected)


@pytest.mark.parametrize(
    "replacement",
    [
        ("D,USD,EUR", "M,USD,EUR"),
        ("D,USD,EUR", "D,USD,GBP"),
        ("SP00,A,2026", "SP01,A,2026"),
        (",USD,0", ",USD,3"),
        ("EXR.D.USD.EUR.SP00.A", "EXR.D.DKK.EUR.SP00.A"),
        ("2026-11-09", "2026-11-08"),
    ],
)
def test_identity_and_window_mismatch_fail_closed(replacement: tuple[str, str]) -> None:
    result = EcbFxNormalizer(start_date=START, end_date=END).normalize(
        record(HEADER + row().replace(*replacement))
    )
    assert result.disposition == NormalizationDisposition.REJECTED


@pytest.mark.parametrize("missing", ["", "0", "-1", "NaN", "Infinity"])
def test_unavailable_rates_do_not_become_zero_or_fill_dates(missing: str) -> None:
    result = EcbFxNormalizer(start_date=START, end_date=END).normalize(
        record(HEADER + row() + row("2026-11-10", missing))
    )
    assert result.observation is not None
    assert len(result.observation.observations) == 1
    assert result.issues[0].code == "ECB_OBSERVATIONS_UNAVAILABLE"


def test_non_normal_observations_and_conflicting_duplicates() -> None:
    normalizer = EcbFxNormalizer(start_date=START, end_date=END)
    provisional = normalizer.normalize(record(HEADER + row().replace(",A,USD,0", ",P,USD,0")))
    assert provisional.disposition == NormalizationDisposition.REJECTED
    duplicate = normalizer.normalize(record(HEADER + row() + row()))
    assert duplicate.observation is not None
    assert len(duplicate.observation.observations) == 1
    conflict = normalizer.normalize(record(HEADER + row() + row(rate="1.26")))
    assert conflict.issues[0].code == "DUPLICATE_FX_SESSION_CONFLICT"


def test_provider_freezes_exact_url_and_raw_bytes() -> None:
    urls = []
    body = (HEADER + row()).encode()

    def transport(url: str) -> bytes:
        urls.append(url)
        return body

    records = asyncio.run(EcbReferenceProvider(transport=transport).fetch(query()))
    assert len(urls) == len(records) == 1
    assert urls[0] == (
        "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?"
        "startPeriod=2026-11-09&endPeriod=2026-11-10&format=csvdata"
    )
    assert records[0].payload == body
    assert records[0].payload_sha256 == hashlib.sha256(body).hexdigest()


def test_provider_rejects_unbounded_or_unknown_scope_before_transport() -> None:
    def transport(url: str) -> bytes:
        raise AssertionError("Invalid request reached transport")

    provider = EcbReferenceProvider(transport=transport)
    for invalid in [
        query(start_date=None),
        query("GBP"),
        query(start_date=date(2025, 1, 1)),
        query(end_date=date(2026, 12, 1)),
    ]:
        with pytest.raises(ValueError):
            asyncio.run(provider.fetch(invalid))


@pytest.mark.source_data
def test_private_official_capture_and_incremental_reconcile_without_network() -> None:
    configured = os.environ.get("ECB_REAL_CAPTURE_DIR")
    if not configured:
        pytest.skip("Set ECB_REAL_CAPTURE_DIR to the private reviewed official capture directory")
    root = Path(configured)
    initial = [
        json.loads((root / "capture-manifest.json").read_text(encoding="utf-8-sig")),
        json.loads((root / "dkk-capture.json").read_text(encoding="utf-8-sig")),
    ]
    incremental = json.loads(
        (root / "incremental-capture-manifest.json").read_text(encoding="utf-8-sig")
    )
    expected = {"USD": ("1.1571", "1.1193", "1.1052"), "DKK": ("7.4672", "7.4753", "7.4756")}
    histories: dict[str, dict[date, Decimal]] = {}
    for captures, start, end, count in [
        (initial, date(2025, 11, 10), date(2026, 11, 9), 255),
        (incremental, date(2026, 11, 5), date(2026, 11, 14), 7),
    ]:
        for capture in captures:
            body = Path(capture["file"]).read_bytes()
            assert hashlib.sha256(body).hexdigest() == capture["sha256"]
            currency = capture["currency"]
            raw = RawProviderRecord(
                domain=ExternalDataDomain.FX,
                provider_id=ECB_PROVIDER_ID,
                provider_schema_version=ECB_SCHEMA_VERSION,
                source_record_id=f"FX:{currency}/EUR",
                source_url=capture["url"],
                media_type="text/csv",
                payload=body,
                payload_sha256=capture["sha256"],
                retrieved_at=datetime.fromisoformat(capture["retrieved_at"]),
            )
            result = EcbFxNormalizer(start_date=start, end_date=end).normalize(raw)
            assert result.observation is not None and not result.issues
            observations = result.observation.observations
            assert len(observations) == count
            assert all(item.observed_at == raw.retrieved_at for item in observations)
            if count == 255:
                assert observations[0].effective_at.date() == start
                assert observations[-1].effective_at.date() == end
                assert abs(observations[0].rate * Decimal(expected[currency][0]) - 1) < Decimal(
                    "1e-12"
                )
                assert abs(observations[-1].rate * Decimal(expected[currency][1]) - 1) < Decimal(
                    "1e-12"
                )
                histories[currency] = {item.effective_at.date(): item.rate for item in observations}
            else:
                assert observations[-1].effective_at.date() == date(2026, 11, 13)
                assert abs(observations[-1].rate * Decimal(expected[currency][2]) - 1) < Decimal(
                    "1e-12"
                )
                history = histories[currency]
                new_dates = 0
                for item in observations:
                    if item.effective_at.date() in history:
                        assert item.rate == history[item.effective_at.date()]
                    else:
                        new_dates += 1
                assert new_dates == 4
