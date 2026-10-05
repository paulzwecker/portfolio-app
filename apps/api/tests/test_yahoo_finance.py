"""Offline regression tests for the Yahoo transport boundary and market normalizer."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.yahoo_finance import (
    FX_SYMBOLS,
    YahooChartNormalizer,
    YahooFinanceProvider,
    YahooFxNormalizer,
    YahooListingCrosswalk,
    YahooListingMapping,
    load_yahoo_crosswalk,
    yahoo_mapping_for_listing,
)

LISTING_ID = UUID("10101010-1010-4010-8010-101010101010")
RETRIEVED_AT = datetime(2026, 10, 5, 18, tzinfo=UTC)


def mapping(**changes: Any) -> YahooListingMapping:
    values = {
        "venue": "NASDAQ",
        "ticker": "EXAMPLE",
        "currency": "USD",
        "security_type": "COMMON_STOCK",
        "provider_symbol": "EXAMPLE",
        "provider_exchange_code": "NMS",
        "provider_exchange_name": "NasdaqGS",
        "provider_instrument_type": "EQUITY",
        "mapping_basis": "TEST_FIXTURE",
        "verification_status": "VERIFIED",
    }
    return YahooListingMapping.model_validate({**values, **changes})


def chart_payload(
    *, currency: str = "USD", symbol: str = "EXAMPLE", exchange: str = "NMS"
) -> bytes:
    timestamps = [
        int(datetime(2026, 10, 2, 13, 30, tzinfo=UTC).timestamp()),
        int(datetime(2026, 10, 5, 13, 30, tzinfo=UTC).timestamp()),
    ]
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": symbol,
                        "currency": currency,
                        "exchangeName": exchange,
                        "fullExchangeName": "NasdaqGS",
                        "instrumentType": "EQUITY",
                        "exchangeTimezoneName": "America/New_York",
                        "regularMarketPrice": 201.25,
                        "regularMarketTime": int(
                            datetime(2026, 10, 5, 19, 45, tzinfo=UTC).timestamp()
                        ),
                        "regularMarketVolume": 1000,
                    },
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [{"close": [200.5, 201.0], "volume": [500, 600]}],
                        "adjclose": [{"adjclose": [190.25, 191.0]}],
                    },
                    "events": {
                        "dividends": {
                            str(int(datetime(2026, 9, 15, 13, 30, tzinfo=UTC).timestamp())): {
                                "amount": 0.25,
                                "date": int(datetime(2026, 9, 15, 13, 30, tzinfo=UTC).timestamp()),
                            }
                        },
                        "splits": {
                            str(int(datetime(2025, 6, 16, 13, 30, tzinfo=UTC).timestamp())): {
                                "numerator": 2,
                                "denominator": 1,
                                "splitRatio": "2:1",
                            }
                        },
                    },
                }
            ],
            "error": None,
        }
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def raw_record(
    payload: bytes, *, domain: ExternalDataDomain, source_record_id: str
) -> RawProviderRecord:
    return RawProviderRecord(
        domain=domain,
        provider_id="YAHOO_FINANCE",
        provider_schema_version="yahoo-chart-v8",
        source_record_id=source_record_id,
        source_url="https://query1.finance.yahoo.com/v8/finance/chart/EXAMPLE",
        media_type="application/json",
        retrieved_at=RETRIEVED_AT,
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_provider_crosswalk_requires_exact_listing_identity() -> None:
    first = mapping()
    second = mapping(venue="NYSE", provider_symbol="EXAMPLE.NY")
    crosswalk = YahooListingCrosswalk(
        provider_id="YAHOO_FINANCE",
        provider_schema_version="yahoo-chart-v8",
        verified_at=RETRIEVED_AT,
        mappings=(first, second),
    )

    assert (
        yahoo_mapping_for_listing(
            crosswalk,
            venue="NYSE",
            ticker="EXAMPLE",
            currency="USD",
            security_type="COMMON_STOCK",
        )
        == second
    )
    assert (
        yahoo_mapping_for_listing(
            crosswalk,
            venue="NASDAQ",
            ticker="EXAMPLE",
            currency="EUR",
            security_type="COMMON_STOCK",
        )
        is None
    )


def test_checked_in_crosswalk_covers_exact_held_listing_identities() -> None:
    from portfolio_api.market_data_ingestion import CROSSWALK_PATH

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

    assert len(crosswalk.mappings) == 84
    assert {item.currency for item in crosswalk.mappings} - {"EUR"} <= {
        base for base, quote in FX_SYMBOLS if quote == "EUR"
    }
    assert held_tsm is not None and held_tsm.provider_symbol == "TSM"
    assert held_spyy is not None and held_spyy.provider_symbol == "SPYY.DE"


def test_raw_batch_identity_can_be_reprocessed_under_a_new_normalizer_version() -> None:
    from portfolio_api.market_data_ingestion import _batch_id

    raw_digest = "a" * 64

    assert _batch_id(raw_digest, "yahoo-chart-normalizer-v1") == _batch_id(
        raw_digest, "yahoo-chart-normalizer-v1"
    )
    assert _batch_id(raw_digest, "yahoo-chart-normalizer-v1") != _batch_id(
        raw_digest, "yahoo-chart-normalizer-v2"
    )


def test_yahoo_normalizer_keeps_price_bases_dividends_and_splits_distinct() -> None:
    record = raw_record(
        chart_payload(),
        domain=ExternalDataDomain.MARKET_DATA,
        source_record_id=f"LISTING:{LISTING_ID}",
    )
    normalizer = YahooChartNormalizer(
        {f"LISTING:{LISTING_ID}": (LISTING_ID, mapping())},
        requested_start=date(2026, 10, 1),
        requested_end=date(2026, 10, 5),
    )

    result = normalizer.normalize(record)

    assert result.disposition == NormalizationDisposition.ACCEPTED
    facts = result.observation
    assert facts is not None
    assert len(facts.prices) == 2
    assert facts.prices[0].provider_close == Decimal("200.5")
    assert facts.prices[0].split_adjusted_close == Decimal("200.5")
    assert facts.prices[0].total_return_close == Decimal("190.25")
    assert facts.prices[0].currency == "USD"
    assert facts.current_quote is not None
    assert facts.current_quote.provider_close == Decimal("201.25")
    assert facts.current_quote.observed_at == datetime(2026, 10, 5, 19, 45, tzinfo=UTC)
    dividend, split = facts.corporate_actions
    assert dividend.action_type == "DIVIDEND"
    assert dividend.cash_amount == Decimal("0.25")
    assert dividend.cash_currency == "USD"
    assert split.action_type == "STOCK_SPLIT"
    assert split.ratio_before == Decimal(1)
    assert split.ratio_after == Decimal(2)


def test_provider_unit_multiplier_preserves_gbx_and_normalizes_to_gbp() -> None:
    listing_mapping = mapping(
        venue="LON",
        ticker="JDG",
        currency="GBP",
        provider_currency="GBp",
        unit_multiplier=Decimal("0.01"),
        security_type="COMMON_STOCK",
        provider_symbol="JDG.L",
        provider_exchange_code="LSE",
        provider_exchange_name="LSE",
    )
    record = raw_record(
        chart_payload(currency="GBp", symbol="JDG.L", exchange="LSE"),
        domain=ExternalDataDomain.MARKET_DATA,
        source_record_id=f"LISTING:{LISTING_ID}",
    )
    result = YahooChartNormalizer(
        {f"LISTING:{LISTING_ID}": (LISTING_ID, listing_mapping)}
    ).normalize(record)

    assert result.observation is not None
    fact = result.observation.prices[0]
    assert fact.provider_close == Decimal("200.5")
    assert fact.provider_currency == "GBp"
    assert fact.source_price_multiplier == Decimal("0.01")
    assert fact.split_adjusted_close == Decimal("2.005")
    dividend = result.observation.corporate_actions[0]
    assert dividend.provider_cash_amount == Decimal("0.25")
    assert dividend.provider_cash_currency == "GBp"
    assert dividend.cash_amount == Decimal("0.0025")
    assert dividend.cash_currency == "GBP"


def test_yahoo_normalizer_rejects_currency_or_exchange_identity_drift() -> None:
    wrong_currency = raw_record(
        chart_payload(currency="CAD"),
        domain=ExternalDataDomain.MARKET_DATA,
        source_record_id=f"LISTING:{LISTING_ID}",
    )
    wrong_exchange = raw_record(
        chart_payload(exchange="NYQ"),
        domain=ExternalDataDomain.MARKET_DATA,
        source_record_id=f"LISTING:{LISTING_ID}",
    )
    normalizer = YahooChartNormalizer({f"LISTING:{LISTING_ID}": (LISTING_ID, mapping())})

    assert normalizer.normalize(wrong_currency).issues[0].code == "LISTING_CURRENCY_MISMATCH"
    assert normalizer.normalize(wrong_exchange).issues[0].code == "LISTING_EXCHANGE_MISMATCH"


def test_missing_close_is_skipped_without_a_zero_price() -> None:
    payload = json.loads(chart_payload())
    payload["chart"]["result"][0]["indicators"]["quote"][0]["close"][1] = None
    raw = raw_record(
        json.dumps(payload).encode(),
        domain=ExternalDataDomain.MARKET_DATA,
        source_record_id=f"LISTING:{LISTING_ID}",
    )
    result = YahooChartNormalizer({f"LISTING:{LISTING_ID}": (LISTING_ID, mapping())}).normalize(raw)

    assert result.observation is not None
    assert len(result.observation.prices) == 1
    assert result.observation.prices[0].provider_close > 0
    assert result.observation.missing_close_count == 1
    assert result.issues[0].code == "PRICE_ROWS_WITHOUT_CLOSE"


def test_identical_bars_for_the_same_exchange_session_are_collapsed() -> None:
    payload = json.loads(chart_payload())
    timestamp = int(datetime(2026, 10, 5, 17, tzinfo=UTC).timestamp())
    payload["chart"]["result"][0]["timestamp"].append(timestamp)
    payload["chart"]["result"][0]["indicators"]["quote"][0]["close"].append(201.0)
    payload["chart"]["result"][0]["indicators"]["quote"][0]["volume"].append(700)
    payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"].append(191.0)
    record = raw_record(
        json.dumps(payload).encode(),
        domain=ExternalDataDomain.MARKET_DATA,
        source_record_id=f"LISTING:{LISTING_ID}",
    )

    result = YahooChartNormalizer({f"LISTING:{LISTING_ID}": (LISTING_ID, mapping())}).normalize(
        record
    )

    assert result.disposition == NormalizationDisposition.ACCEPTED
    assert result.observation is not None
    assert len(result.observation.prices) == 2
    assert result.observation.duplicate_session_bar_count == 1
    assert result.observation.prices[1].volume is None
    assert result.issues[0].code == "DUPLICATE_SESSION_BARS_COLLAPSED"


def test_conflicting_bars_for_one_exchange_session_are_rejected() -> None:
    payload = json.loads(chart_payload())
    timestamp = int(datetime(2026, 10, 5, 17, tzinfo=UTC).timestamp())
    payload["chart"]["result"][0]["timestamp"].append(timestamp)
    payload["chart"]["result"][0]["indicators"]["quote"][0]["close"].append(202.0)
    payload["chart"]["result"][0]["indicators"]["quote"][0]["volume"].append(601)
    payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"].append(192.0)
    record = raw_record(
        json.dumps(payload).encode(),
        domain=ExternalDataDomain.MARKET_DATA,
        source_record_id=f"LISTING:{LISTING_ID}",
    )

    result = YahooChartNormalizer({f"LISTING:{LISTING_ID}": (LISTING_ID, mapping())}).normalize(
        record
    )

    assert result.disposition == NormalizationDisposition.REJECTED
    assert result.issues[0].code == "DUPLICATE_LISTING_SESSION_CONFLICT"


def test_yahoo_fx_pair_is_explicit_and_uses_quote_currency_units() -> None:
    assert FX_SYMBOLS[("USD", "EUR")] == "EUR=X"
    assert FX_SYMBOLS[("AUD", "EUR")] == "AUDEUR=X"
    assert FX_SYMBOLS[("CAD", "EUR")] == "CADEUR=X"
    assert FX_SYMBOLS[("CHF", "EUR")] == "CHFEUR=X"
    assert FX_SYMBOLS[("GBP", "EUR")] == "GBPEUR=X"
    assert FX_SYMBOLS[("JPY", "EUR")] == "JPYEUR=X"
    assert FX_SYMBOLS[("SEK", "EUR")] == "SEKEUR=X"
    assert FX_SYMBOLS[("TWD", "EUR")] == "TWDEUR=X"
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "EUR=X",
                        "currency": "EUR",
                        "exchangeName": "CCY",
                        "instrumentType": "CURRENCY",
                        "regularMarketPrice": 0.9,
                        "regularMarketTime": int(datetime(2026, 10, 5, 18, tzinfo=UTC).timestamp()),
                    },
                    "timestamp": [int(datetime(2026, 10, 2, tzinfo=UTC).timestamp())],
                    "indicators": {
                        "quote": [{"close": [0.91], "volume": [None]}],
                        "adjclose": [{"adjclose": [0.91]}],
                    },
                }
            ],
            "error": None,
        }
    }
    record = raw_record(
        json.dumps(payload).encode(),
        domain=ExternalDataDomain.FX,
        source_record_id="FX:USD/EUR",
    )

    result = YahooFxNormalizer().normalize(record)

    assert result.disposition == NormalizationDisposition.ACCEPTED
    facts = result.observation
    assert facts is not None
    assert facts.base_currency == "USD"
    assert facts.quote_currency == "EUR"
    assert facts.observations[0].rate == Decimal("0.91")
    assert facts.observations[0].effective_at.date() == date(2026, 10, 2)
    assert facts.observations[-1].is_current_quote
    assert facts.observations[-1].rate == Decimal("0.9")


def test_provider_fetch_uses_bound_listing_and_inclusive_dates() -> None:
    requested_urls: list[str] = []

    def transport(url: str) -> bytes:
        requested_urls.append(url)
        return chart_payload()

    crosswalk = YahooListingCrosswalk(
        provider_id="YAHOO_FINANCE",
        provider_schema_version="yahoo-chart-v8",
        verified_at=RETRIEVED_AT,
        mappings=(mapping(),),
    )
    provider = YahooFinanceProvider(crosswalk, transport=transport, retries=0)
    provider.bind_listing_ids({LISTING_ID: mapping()})
    query = ProviderQuery(
        domain=ExternalDataDomain.MARKET_DATA,
        subjects=[CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=LISTING_ID)],
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 5),
        requested_at=RETRIEVED_AT,
    )

    records = asyncio.run(provider.fetch(query))

    assert len(records) == 1
    assert records[0].source_record_id == f"LISTING:{LISTING_ID}"
    assert "EXAMPLE" in requested_urls[0]
    assert "period1=" in requested_urls[0] and "period2=" in requested_urls[0]
