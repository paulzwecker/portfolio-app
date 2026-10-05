"""Yahoo Finance transport and normalization, isolated from canonical domains.

Yahoo symbols and response fields stop here. Callers provide exact listing or
currency-pair identities and receive provider-neutral raw records plus typed
canonical price, action, or FX facts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    RawProviderRecord,
)

YAHOO_PROVIDER_ID = "YAHOO_FINANCE"
YAHOO_SCHEMA_VERSION = "yahoo-chart-v8"
YAHOO_CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart"
FX_SYMBOLS: dict[tuple[str, str], str] = {
    ("AUD", "EUR"): "AUDEUR=X",
    ("CAD", "EUR"): "CADEUR=X",
    ("CHF", "EUR"): "CHFEUR=X",
    ("USD", "EUR"): "EUR=X",
    ("DKK", "EUR"): "DKKEUR=X",
    ("GBP", "EUR"): "GBPEUR=X",
    ("JPY", "EUR"): "JPYEUR=X",
    ("SEK", "EUR"): "SEKEUR=X",
    ("TWD", "EUR"): "TWDEUR=X",
}


class YahooListingMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    venue: str
    ticker: str
    currency: str
    provider_currency: str | None = None
    unit_multiplier: Decimal = Field(default=Decimal(1), gt=0, max_digits=12, decimal_places=6)
    security_type: str
    provider_symbol: str
    provider_exchange_code: str
    provider_exchange_name: str
    provider_instrument_type: str
    mapping_basis: str
    mapping_source_symbol: str | None = None
    canonical_company_id: UUID | None = None
    canonical_company_name: str | None = None
    canonical_security_id: UUID | None = None
    canonical_listing_id: UUID | None = None
    canonical_share_class: str | None = None
    identity_source_ref: str | None = None
    identity_status: str | None = None
    verification_status: str = Field(pattern=r"^VERIFIED$")


class YahooListingCrosswalk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str
    provider_schema_version: str
    verified_at: datetime
    mappings: tuple[YahooListingMapping, ...]


@dataclass(frozen=True)
class YahooPriceFact:
    market_date: datetime
    observed_at: datetime | None
    provider_close: Decimal
    split_adjusted_close: Decimal
    total_return_close: Decimal | None
    volume: Decimal | None
    currency: str
    provider_currency: str
    source_price_multiplier: Decimal
    provider_symbol: str
    price_kind: str
    adjustment_basis: str
    source_ref: str


@dataclass(frozen=True)
class YahooCorporateActionFact:
    source_action_id: str
    effective_date: datetime
    observed_at: datetime
    action_type: str
    ratio_before: Decimal | None
    ratio_after: Decimal | None
    cash_amount: Decimal | None
    cash_currency: str | None
    provider_cash_amount: Decimal | None
    provider_cash_currency: str | None
    source_url: str | None
    notes: str


@dataclass(frozen=True)
class YahooListingFacts:
    listing_id: UUID
    provider_symbol: str
    prices: tuple[YahooPriceFact, ...]
    current_quote: YahooPriceFact | None
    corporate_actions: tuple[YahooCorporateActionFact, ...]
    missing_close_count: int
    in_progress_bar_count: int
    duplicate_session_bar_count: int
    returned_exchange: str


@dataclass(frozen=True)
class YahooFxFact:
    base_currency: str
    quote_currency: str
    provider_symbol: str
    effective_at: datetime
    observed_at: datetime | None
    rate: Decimal
    source_ref: str
    is_current_quote: bool = False


@dataclass(frozen=True)
class YahooFxFacts:
    base_currency: str
    quote_currency: str
    provider_symbol: str
    observations: tuple[YahooFxFact, ...]


@dataclass(frozen=True)
class ProviderFetchFailure:
    source_record_id: str
    provider_symbol: str
    message: str


Transport = Callable[[str], bytes]


class DuplicateMarketSessionError(ValueError):
    """Yahoo returned conflicting bars for one canonical exchange session date."""


def load_yahoo_crosswalk(path: Path) -> YahooListingCrosswalk:
    return YahooListingCrosswalk.model_validate_json(path.read_text(encoding="utf-8"))


def yahoo_mapping_for_listing(
    crosswalk: YahooListingCrosswalk,
    *,
    venue: str,
    ticker: str,
    currency: str | None,
    security_type: str,
) -> YahooListingMapping | None:
    """Resolve using the full canonical listing key, never ticker alone."""

    matches = [
        mapping
        for mapping in crosswalk.mappings
        if mapping.venue.casefold() == venue.casefold()
        and mapping.ticker.casefold() == ticker.casefold()
        and mapping.currency.casefold() == (currency or "").casefold()
        and mapping.security_type.casefold() == security_type.casefold()
    ]
    return matches[0] if len(matches) == 1 else None


def _default_transport(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "portfolio-app market-data/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read()
        return bytes(body)


class YahooFinanceProvider:
    """Async transport adapter for exact listing and currency-pair queries."""

    provider_id = YAHOO_PROVIDER_ID

    def __init__(
        self,
        crosswalk: YahooListingCrosswalk,
        *,
        transport: Transport = _default_transport,
        concurrency: int = 5,
        retries: int = 3,
    ) -> None:
        self._crosswalk = crosswalk
        self._transport = transport
        self._concurrency = max(1, concurrency)
        self._retries = max(0, retries)
        self.failures: list[ProviderFetchFailure] = []
        self._id_mappings: dict[UUID, YahooListingMapping] = {}

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        self.failures = []
        semaphore = asyncio.Semaphore(self._concurrency)

        async def fetch_one(subject: CanonicalSubjectRef) -> RawProviderRecord | None:
            source_record_id, symbol = self._resolve(query.domain, subject)
            async with semaphore:
                try:
                    body, source_url = await asyncio.to_thread(
                        self._fetch_with_retries, symbol, query.start_date, query.end_date
                    )
                except Exception as error:  # per-subject provider gaps are reported, not fabricated
                    self.failures.append(
                        ProviderFetchFailure(
                            source_record_id=source_record_id,
                            provider_symbol=symbol,
                            message=f"{type(error).__name__}: {str(error)[:300]}",
                        )
                    )
                    return None
            return RawProviderRecord(
                domain=query.domain,
                provider_id=self.provider_id,
                provider_schema_version=YAHOO_SCHEMA_VERSION,
                source_record_id=source_record_id,
                source_url=source_url,
                media_type="application/json",
                retrieved_at=datetime.now(UTC),
                payload=body,
                payload_sha256=hashlib.sha256(body).hexdigest(),
            )

        results = await asyncio.gather(*(fetch_one(subject) for subject in query.subjects))
        return [record for record in results if record is not None]

    def _resolve(self, domain: ExternalDataDomain, subject: CanonicalSubjectRef) -> tuple[str, str]:
        if domain == ExternalDataDomain.MARKET_DATA:
            if subject.kind != CanonicalSubjectKind.LISTING or subject.id is None:
                raise ValueError("Market-price queries require canonical listing IDs")
            # The database caller binds exact listing IDs after validating the composite key.
            listing = self._id_mappings.get(subject.id)
            if listing is None:
                raise ValueError(f"No verified Yahoo mapping for listing {subject.id}")
            return f"LISTING:{subject.id}", listing.provider_symbol
        if domain == ExternalDataDomain.FX:
            if subject.kind != CanonicalSubjectKind.CURRENCY_PAIR:
                raise ValueError("FX queries require explicit currency-pair subjects")
            pair = (subject.base_currency or "", subject.quote_currency or "")
            symbol = FX_SYMBOLS.get(pair)
            if symbol is None:
                raise ValueError(f"No verified Yahoo FX mapping for {pair[0]}/{pair[1]}")
            return f"FX:{pair[0]}/{pair[1]}", symbol
        raise ValueError(f"Yahoo chart adapter does not support {domain.value}")

    def bind_listing_ids(self, listing_ids: Mapping[UUID, YahooListingMapping]) -> None:
        """Bind exact database identities to the checked-in crosswalk for one query."""

        self._id_mappings = dict(listing_ids)

    def _fetch_with_retries(
        self, symbol: str, start_date: date | None, end_date: date | None
    ) -> tuple[bytes, str]:
        params: dict[str, str] = {
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
        if start_date is None:
            params["range"] = "10y"
        else:
            params["period1"] = str(
                int(datetime.combine(start_date, day_time.min, UTC).timestamp())
            )
            end_exclusive = (end_date or datetime.now(UTC).date()) + timedelta(days=1)
            params["period2"] = str(
                int(datetime.combine(end_exclusive, day_time.min, UTC).timestamp())
            )
        encoded_symbol = urllib.parse.quote(symbol, safe=".=^-")
        url = f"{YAHOO_CHART_ENDPOINT}/{encoded_symbol}?{urllib.parse.urlencode(params)}"
        for attempt in range(self._retries + 1):
            try:
                return self._transport(url), url
            except urllib.error.HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                    raise
                time.sleep(0.4 * (2**attempt))
            except (TimeoutError, urllib.error.URLError):
                if attempt >= self._retries:
                    raise
                time.sleep(0.4 * (2**attempt))
        raise RuntimeError("Yahoo request exhausted retry policy")


class YahooChartNormalizer:
    """Versioned, identity-checking Yahoo chart normalizer for prices and actions."""

    domain = ExternalDataDomain.MARKET_DATA
    version = "yahoo-chart-normalizer-v4"

    def __init__(
        self,
        listing_ids: Mapping[str, tuple[UUID, YahooListingMapping]],
        *,
        requested_start: date | None = None,
        requested_end: date | None = None,
    ) -> None:
        self._listing_ids = dict(listing_ids)
        self._requested_start = requested_start
        self._requested_end = requested_end

    def normalize(self, record: RawProviderRecord) -> NormalizationResult[YahooListingFacts]:
        if (
            record.provider_id != YAHOO_PROVIDER_ID
            or record.domain != ExternalDataDomain.MARKET_DATA
        ):
            return _rejected("PROVIDER_DOMAIN_MISMATCH", "Raw record is not Yahoo market data.")
        if record.source_record_id is None:
            return _rejected(
                "SOURCE_RECORD_ID_MISSING", "Yahoo listing response has no canonical ID."
            )
        identity = self._listing_ids.get(record.source_record_id)
        if identity is None:
            return _rejected(
                "LISTING_MAPPING_MISSING", "No exact canonical listing mapping exists."
            )
        listing_id, mapping = identity
        return _normalize_listing_chart(
            record, listing_id, mapping, self._requested_start, self._requested_end
        )


class YahooFxNormalizer:
    """Versioned point-in-time conversion of explicit provider FX crosses."""

    domain = ExternalDataDomain.FX
    version = "yahoo-fx-normalizer-v1"

    def normalize(self, record: RawProviderRecord) -> NormalizationResult[YahooFxFacts]:
        if record.provider_id != YAHOO_PROVIDER_ID or record.domain != ExternalDataDomain.FX:
            return _rejected("PROVIDER_DOMAIN_MISMATCH", "Raw record is not Yahoo FX data.")
        if not record.source_record_id or not record.source_record_id.startswith("FX:"):
            return _rejected(
                "FX_IDENTITY_MISSING", "Yahoo FX response has no explicit currency pair."
            )
        try:
            base, quote = record.source_record_id[3:].split("/", maxsplit=1)
            symbol = FX_SYMBOLS[(base, quote)]
        except (ValueError, KeyError):
            return _rejected("FX_PAIR_UNSUPPORTED", "Yahoo FX cross is not explicitly mapped.")
        parsed = _read_chart(record)
        if isinstance(parsed, NormalizationResult):
            return parsed
        result, meta = parsed
        if str(meta.get("currency", "")).upper() != quote:
            return _rejected(
                "FX_QUOTE_CURRENCY_MISMATCH", "Yahoo FX quote currency did not match the pair."
            )
        if str(meta.get("instrumentType", "")).upper() != "CURRENCY":
            return _rejected(
                "FX_INSTRUMENT_TYPE_MISMATCH", "Yahoo response is not a currency pair."
            )
        returned_symbol = str(meta.get("symbol", ""))
        if returned_symbol.casefold() != symbol.casefold():
            return _rejected("FX_PROVIDER_SYMBOL_MISMATCH", "Yahoo returned a different FX symbol.")
        try:
            prices, _, quote_row, missing, _in_progress, _duplicates = _parse_prices(
                record, result, meta, currency=quote, price_symbol=symbol, fx=True
            )
        except DuplicateMarketSessionError as error:
            return _rejected("DUPLICATE_FX_SESSION_CONFLICT", str(error))
        except ValueError as error:
            return _rejected("FX_TIMEZONE_INVALID", str(error))
        observations = tuple(
            YahooFxFact(
                base_currency=base,
                quote_currency=quote,
                provider_symbol=symbol,
                effective_at=_fx_effective_at(price.market_date),
                observed_at=price.observed_at,
                rate=price.provider_close,
                source_ref=price.source_ref,
            )
            for price in prices
        )
        if quote_row is not None:
            observations += (
                YahooFxFact(
                    base_currency=base,
                    quote_currency=quote,
                    provider_symbol=symbol,
                    effective_at=quote_row.observed_at or _fx_effective_at(quote_row.market_date),
                    observed_at=quote_row.observed_at,
                    rate=quote_row.provider_close,
                    source_ref=quote_row.source_ref,
                    is_current_quote=True,
                ),
            )
        if not observations:
            return _rejected("FX_SERIES_EMPTY", f"Yahoo returned no valid {base}/{quote} rates.")
        if missing:
            issue = NormalizationIssue(
                code="FX_ROWS_WITHOUT_CLOSE",
                message=f"Skipped {missing} Yahoo FX sessions without a positive close.",
                severity="WARNING",
            )
            return NormalizationResult(
                disposition=NormalizationDisposition.ACCEPTED,
                observation=YahooFxFacts(base, quote, symbol, observations),
                issues=(issue,),
            )
        return NormalizationResult(
            disposition=NormalizationDisposition.ACCEPTED,
            observation=YahooFxFacts(base, quote, symbol, observations),
        )


def _normalize_listing_chart(
    record: RawProviderRecord,
    listing_id: UUID,
    mapping: YahooListingMapping,
    requested_start: date | None,
    requested_end: date | None,
) -> NormalizationResult[YahooListingFacts]:
    parsed = _read_chart(record)
    if isinstance(parsed, NormalizationResult):
        return parsed
    result, meta = parsed
    if str(meta.get("symbol", "")).casefold() != mapping.provider_symbol.casefold():
        return _rejected(
            "PROVIDER_SYMBOL_MISMATCH", "Yahoo returned a symbol other than the verified mapping."
        )
    provider_currency = mapping.provider_currency or mapping.currency
    if str(meta.get("currency", "")).upper() != provider_currency.upper():
        return _rejected(
            "LISTING_CURRENCY_MISMATCH",
            "Yahoo quote currency did not match the verified provider mapping.",
        )
    if str(meta.get("exchangeName", "")).upper() != mapping.provider_exchange_code.upper():
        return _rejected(
            "LISTING_EXCHANGE_MISMATCH", "Yahoo exchange did not match the verified listing."
        )
    if str(meta.get("instrumentType", "")).upper() != mapping.provider_instrument_type.upper():
        return _rejected(
            "LISTING_INSTRUMENT_MISMATCH",
            "Yahoo instrument type changed from its verified mapping.",
        )
    try:
        prices, timezone, current_quote, missing, in_progress, duplicates = _parse_prices(
            record,
            result,
            meta,
            currency=mapping.currency,
            price_symbol=mapping.provider_symbol,
            provider_currency=provider_currency,
            unit_multiplier=mapping.unit_multiplier,
            fx=False,
            requested_start=requested_start,
            requested_end=requested_end,
        )
    except DuplicateMarketSessionError as error:
        return _rejected("DUPLICATE_LISTING_SESSION_CONFLICT", str(error))
    except ValueError as error:
        return _rejected("EXCHANGE_TIMEZONE_INVALID", str(error))
    actions = _parse_actions(
        record,
        result,
        timezone,
        mapping.currency,
        provider_currency,
        mapping.unit_multiplier,
        mapping.provider_symbol,
    )
    if not prices and current_quote is None and not actions:
        return _rejected(
            "PRICE_HISTORY_EMPTY", "Yahoo returned no dated prices or corporate actions."
        )
    issues: list[NormalizationIssue] = []
    if missing:
        issues.append(
            NormalizationIssue(
                code="PRICE_ROWS_WITHOUT_CLOSE",
                message=f"Skipped {missing} Yahoo sessions without a positive close.",
                severity="WARNING",
            )
        )
    if duplicates:
        issues.append(
            NormalizationIssue(
                code="DUPLICATE_SESSION_BARS_COLLAPSED",
                message=(
                    f"Collapsed {duplicates} duplicate Yahoo session bars with identical "
                    "close and adjusted-close values; conflicting volume remains null."
                ),
                severity="WARNING",
            )
        )
    return NormalizationResult(
        disposition=NormalizationDisposition.ACCEPTED,
        observation=YahooListingFacts(
            listing_id=listing_id,
            provider_symbol=mapping.provider_symbol,
            prices=tuple(prices),
            current_quote=current_quote,
            corporate_actions=tuple(actions),
            missing_close_count=missing,
            in_progress_bar_count=in_progress,
            duplicate_session_bar_count=duplicates,
            returned_exchange=str(meta.get("fullExchangeName") or meta.get("exchangeName")),
        ),
        issues=tuple(issues),
    )


def _read_chart(
    record: RawProviderRecord,
) -> tuple[dict[str, Any], dict[str, Any]] | NormalizationResult[Any]:
    if record.payload is None:
        return _rejected("RAW_PAYLOAD_UNAVAILABLE", "Provider response bytes are unavailable.")
    try:
        body = json.loads(record.payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _rejected("PROVIDER_JSON_INVALID", "Yahoo response was not valid JSON.")
    chart = body.get("chart") if isinstance(body, dict) else None
    if not isinstance(chart, dict):
        return _rejected("PROVIDER_RESPONSE_INVALID", "Yahoo response has no chart envelope.")
    if chart.get("error"):
        return _rejected("PROVIDER_RETURNED_ERROR", f"Yahoo chart error: {chart['error']}")
    results = chart.get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return _rejected(
            "PROVIDER_RESULT_EMPTY", "Yahoo returned no chart result for this subject."
        )
    result = results[0]
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return _rejected("PROVIDER_METADATA_MISSING", "Yahoo result has no identity metadata.")
    return result, meta


def _parse_prices(
    record: RawProviderRecord,
    result: dict[str, Any],
    meta: dict[str, Any],
    *,
    currency: str,
    price_symbol: str,
    provider_currency: str | None = None,
    unit_multiplier: Decimal = Decimal(1),
    fx: bool,
    requested_start: date | None = None,
    requested_end: date | None = None,
) -> tuple[list[YahooPriceFact], ZoneInfo, YahooPriceFact | None, int, int, int]:
    if fx:
        timezone = ZoneInfo("UTC")
    else:
        zone_name = meta.get("exchangeTimezoneName")
        if not isinstance(zone_name, str):
            raise ValueError("Yahoo listing result has no exchange timezone")
        try:
            timezone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Yahoo listing result has an unknown exchange timezone") from error
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    quote = quotes[0] if quotes and isinstance(quotes[0], dict) else {}
    adjusted_rows = indicators.get("adjclose") or []
    adjusted = adjusted_rows[0].get("adjclose", []) if adjusted_rows else []
    timestamps = result.get("timestamp") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    prices_by_date: dict[datetime, tuple[YahooPriceFact, bool]] = {}
    missing = 0
    in_progress = 0
    duplicates = 0
    incomplete_day = _incomplete_session_day(record, meta, timezone)
    for index, raw_timestamp in enumerate(timestamps):
        if not isinstance(raw_timestamp, (int, float)):
            missing += 1
            continue
        instant = datetime.fromtimestamp(raw_timestamp, UTC)
        market_day = instant.astimezone(timezone).date()
        if market_day == incomplete_day:
            in_progress += 1
            continue
        if requested_start and market_day < requested_start:
            continue
        if requested_end and market_day > requested_end:
            continue
        provider_close = _positive_decimal(_at(closes, index))
        if provider_close is None:
            missing += 1
            continue
        close = provider_close * unit_multiplier
        provider_adjusted_close = _positive_decimal(_at(adjusted, index))
        adjusted_close = (
            provider_adjusted_close * unit_multiplier
            if provider_adjusted_close is not None
            else None
        )
        volume = _nonnegative_decimal(_at(volumes, index))
        market_date = datetime.combine(market_day, day_time.min, UTC)
        fact = YahooPriceFact(
            market_date=market_date,
            observed_at=None,
            provider_close=provider_close,
            split_adjusted_close=close,
            total_return_close=adjusted_close,
            volume=volume,
            currency=currency,
            provider_currency=provider_currency or currency,
            source_price_multiplier=unit_multiplier,
            provider_symbol=price_symbol,
            price_kind="DAILY_CLOSE",
            adjustment_basis=(
                f"Yahoo chart close ({provider_currency or currency} x {unit_multiplier} to "
                "canonical currency; split adjusted, dividend unadjusted); adjclose retained "
                "as Yahoo total-return-adjusted series"
            ),
            source_ref=_price_source_ref(
                record,
                price_symbol,
                "DAILY_CLOSE",
                market_date,
                provider_close,
                provider_adjusted_close,
                volume,
                unit_multiplier=unit_multiplier,
                provider_currency=provider_currency or currency,
            ),
        )
        existing = prices_by_date.get(market_date)
        if existing is None:
            prices_by_date[market_date] = (fact, False)
        elif (
            existing[0].provider_close,
            existing[0].split_adjusted_close,
            existing[0].total_return_close,
            existing[0].currency,
            existing[0].provider_currency,
        ) == (
            fact.provider_close,
            fact.split_adjusted_close,
            fact.total_return_close,
            fact.currency,
            fact.provider_currency,
        ):
            duplicates += 1
            # Duplicate rows can repeat one close while disagreeing on volume.
            # Keep the price and mark volume unavailable instead of choosing a bar.
            if existing[1] or existing[0].volume != fact.volume:
                without_volume = replace(
                    fact,
                    volume=None,
                    source_ref=_price_source_ref(
                        record,
                        price_symbol,
                        "DAILY_CLOSE",
                        market_date,
                        provider_close,
                        provider_adjusted_close,
                        None,
                        unit_multiplier=unit_multiplier,
                        provider_currency=provider_currency or currency,
                    ),
                )
                prices_by_date[market_date] = (without_volume, True)
        else:
            raise DuplicateMarketSessionError(
                "Yahoo returned different price facts for the same exchange session date."
            )
    current_quote = None
    provider_current_value = _positive_decimal(meta.get("regularMarketPrice"))
    current_timestamp = meta.get("regularMarketTime")
    if provider_current_value is not None and isinstance(current_timestamp, (int, float)):
        current_value = provider_current_value * unit_multiplier
        observed_at = datetime.fromtimestamp(current_timestamp, UTC)
        quote_day = observed_at.astimezone(timezone).date()
        current_date = datetime.combine(quote_day, day_time.min, UTC)
        current_volume = _nonnegative_decimal(meta.get("regularMarketVolume"))
        current_quote = YahooPriceFact(
            market_date=current_date,
            observed_at=observed_at,
            provider_close=provider_current_value,
            split_adjusted_close=current_value,
            total_return_close=None,
            volume=current_volume,
            currency=currency,
            provider_currency=provider_currency or currency,
            source_price_multiplier=unit_multiplier,
            provider_symbol=price_symbol,
            price_kind="CURRENT_QUOTE",
            adjustment_basis=(
                f"Yahoo regularMarketPrice ({provider_currency or currency} x {unit_multiplier} "
                "to canonical currency); provider-reported current/last price"
            ),
            source_ref=_price_source_ref(
                record,
                price_symbol,
                "CURRENT_QUOTE",
                current_date,
                provider_current_value,
                None,
                current_volume,
                observed_at,
                unit_multiplier=unit_multiplier,
                provider_currency=provider_currency or currency,
            ),
        )
    return (
        [fact for fact, _volume_ambiguous in prices_by_date.values()],
        timezone,
        current_quote,
        missing,
        in_progress,
        duplicates,
    )


def _incomplete_session_day(
    record: RawProviderRecord, meta: dict[str, Any], timezone: ZoneInfo
) -> date | None:
    periods = meta.get("currentTradingPeriod")
    regular = periods.get("regular") if isinstance(periods, dict) else None
    if not isinstance(regular, dict):
        return None
    starts_at = regular.get("start")
    ends_at = regular.get("end")
    if not isinstance(starts_at, (int, float)) or not isinstance(ends_at, (int, float)):
        return None
    retrieved = record.retrieved_at.astimezone(UTC).timestamp()
    if starts_at <= retrieved < ends_at:
        return datetime.fromtimestamp(starts_at, UTC).astimezone(timezone).date()
    return None


def _parse_actions(
    record: RawProviderRecord,
    result: dict[str, Any],
    timezone: ZoneInfo,
    currency: str,
    provider_currency: str,
    unit_multiplier: Decimal,
    symbol: str,
) -> list[YahooCorporateActionFact]:
    events = result.get("events") or {}
    actions: list[YahooCorporateActionFact] = []
    for provider_key, action_type in (("dividends", "DIVIDEND"), ("splits", "STOCK_SPLIT")):
        records = events.get(provider_key) or {}
        if not isinstance(records, dict):
            continue
        for timestamp_text, payload in records.items():
            if not isinstance(payload, dict):
                continue
            try:
                timestamp = int(timestamp_text)
                observed = record.retrieved_at.astimezone(UTC)
                event_day = datetime.fromtimestamp(timestamp, UTC).astimezone(timezone).date()
                effective = datetime.combine(event_day, day_time.min, UTC)
            except (ValueError, TypeError, OverflowError):
                continue
            ratio_before = ratio_after = cash_amount = cash_currency = None
            provider_cash_amount = None
            provider_cash_currency = None
            if action_type == "DIVIDEND":
                provider_cash_amount = _positive_decimal(payload.get("amount"))
                if provider_cash_amount is None:
                    continue
                cash_amount = provider_cash_amount * unit_multiplier
                cash_currency = currency
                provider_cash_currency = provider_currency
            else:
                ratio = payload.get("splitRatio")
                if isinstance(ratio, str) and ":" in ratio:
                    try:
                        shares_after, shares_before = ratio.split(":", maxsplit=1)
                        ratio_factor = Decimal(shares_after) / Decimal(shares_before)
                        ratio_before = Decimal(1)
                        ratio_after = ratio_factor
                    except (InvalidOperation, ZeroDivisionError):
                        continue
                    if ratio_before <= 0 or ratio_after is None or ratio_after <= 0:
                        continue
            content_digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16]
            action_id = (
                f"YAHOO_FINANCE:{symbol}:{action_type}:{event_day.isoformat()}:{content_digest}"
            )
            actions.append(
                YahooCorporateActionFact(
                    source_action_id=action_id,
                    effective_date=effective,
                    observed_at=observed,
                    action_type=action_type,
                    ratio_before=ratio_before,
                    ratio_after=ratio_after,
                    cash_amount=cash_amount,
                    cash_currency=cash_currency,
                    provider_cash_amount=provider_cash_amount,
                    provider_cash_currency=provider_cash_currency,
                    source_url=str(record.source_url) if record.source_url else None,
                    notes=f"Yahoo chart {provider_key} event; not independently issuer-verified",
                )
            )
    return actions


def _price_source_ref(
    record: RawProviderRecord,
    symbol: str,
    kind: str,
    market_date: datetime,
    close: Decimal,
    adjusted_close: Decimal | None,
    volume: Decimal | None,
    observed_at: datetime | None = None,
    *,
    unit_multiplier: Decimal = Decimal(1),
    provider_currency: str | None = None,
) -> str:
    values = {
        "adjusted_close": str(adjusted_close) if adjusted_close is not None else None,
        "close": str(close),
        "observed_at": observed_at.isoformat() if observed_at else None,
        "provider_currency": provider_currency,
        "unit_multiplier": str(unit_multiplier),
        "volume": str(volume) if volume is not None else None,
    }
    digest = hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"yahoo:{symbol}:{kind}:{market_date.date().isoformat()}:{digest}"


def _fx_effective_at(market_date: datetime) -> datetime:
    # The Yahoo daily bar identifies a calendar session, not an exact quote time.
    return datetime.combine(market_date.date(), day_time.min, UTC)


def _at(values: Any, index: int) -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else None


def _positive_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _nonnegative_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _rejected(code: str, message: str) -> NormalizationResult[Any]:
    return NormalizationResult(
        disposition=NormalizationDisposition.REJECTED,
        observation=None,
        issues=(NormalizationIssue(code=code, message=message, severity="ERROR"),),
    )
