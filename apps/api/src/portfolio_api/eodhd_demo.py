"""Bounded EODHD demo history for the reviewed Amazon common-stock example.

This is a private evaluation source, not permission to activate a production feed.
Native closes and split/dividend-adjusted closes retain their distinct meanings.
No split-only series or confirmed corporate transactions are inferred.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from portfolio_api.external_data import (
    CanonicalSubjectKind,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    ProviderTransportError,
    RawProviderRecord,
    parse_retry_after_seconds,
)
from portfolio_api.yahoo_finance import YahooListingFacts, YahooPriceFact

EODHD_DEMO_PROVIDER_ID = "EODHD_DEMO"
EODHD_DEMO_SCHEMA_VERSION = "eodhd-eod-v1"
EODHD_GENERAL_SCHEMA_VERSION = "eodhd-general-v1.1"
EODHD_DEMO_SYMBOL = "AMZN.US"
EODHD_ADJUSTMENT_BASIS = "UNADJUSTED_NATIVE_CLOSE"
EODHD_METADATA_URL = (
    "https://eodhd.com/api/v1.1/fundamentals/AMZN.US?api_token=demo&filter=General&fmt=json"
)


class EodhdDemoMapping(BaseModel):
    """Exact local rehearsal identity; constructing it does not approve production."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    listing_id: UUID
    security_id: UUID
    company_id: UUID
    ticker: Literal["AMZN"] = "AMZN"
    venue: Literal["NASDAQ"] = "NASDAQ"
    currency: Literal["USD"] = "USD"
    security_type: Literal["COMMON_STOCK"] = "COMMON_STOCK"
    provider_symbol: Literal["AMZN.US"] = "AMZN.US"
    cik: Literal["0001018724"] = "0001018724"


def validate_eodhd_demo_metadata(record: RawProviderRecord, mapping: EodhdDemoMapping) -> None:
    """Match the actual General response, not the provider's broad US suffix."""

    if (
        record.provider_id != EODHD_DEMO_PROVIDER_ID
        or record.provider_schema_version != EODHD_GENERAL_SCHEMA_VERSION
        or record.domain != ExternalDataDomain.COMPANY_REFERENCE
        or record.source_record_id != f"{EODHD_DEMO_SYMBOL}:GENERAL"
        or record.payload is None
    ):
        raise ValueError("Exact EODHD demo metadata evidence is required")
    metadata = json.loads(record.payload)
    expected = {
        "Code": mapping.ticker,
        "PrimaryTicker": mapping.provider_symbol,
        "Exchange": mapping.venue,
        "CurrencyCode": mapping.currency,
        "Type": "Common Stock",
        "CIK": mapping.cik,
        "IsDelisted": False,
    }
    if not isinstance(metadata, dict) or any(metadata.get(k) != v for k, v in expected.items()):
        raise ValueError("EODHD metadata conflicts with the exact reviewed listing")
    if metadata["IsDelisted"] is not False:
        raise ValueError("EODHD listing must be explicitly active")
    if str(metadata.get("Name", "")).casefold().replace(" ", "").rstrip(".") != "amazon.cominc":
        raise ValueError("EODHD registrant identity does not match Amazon")


def _window(query: ProviderQuery, mapping: EodhdDemoMapping) -> tuple[date, date]:
    if (
        query.domain != ExternalDataDomain.MARKET_DATA
        or len(query.subjects) != 1
        or query.subjects[0].kind != CanonicalSubjectKind.LISTING
        or query.subjects[0].id != mapping.listing_id
        or query.start_date is None
        or query.end_date is None
        or (query.end_date - query.start_date).days > 365
        or query.end_date >= query.requested_at.astimezone(UTC).date()
    ):
        raise ValueError("Demo requires one exact listing and at most 366 completed calendar days")
    return query.start_date, query.end_date


def eodhd_demo_url(start: date, end: date) -> str:
    return f"https://eodhd.com/api/eod/{EODHD_DEMO_SYMBOL}?" + urlencode(
        {"api_token": "demo", "from": start, "to": end, "period": "d", "order": "a", "fmt": "json"}
    )


def eodhd_demo_record_id(mapping: EodhdDemoMapping, start: date, end: date) -> str:
    return f"{mapping.listing_id}:{mapping.provider_symbol}:{start}:{end}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _default_transport(url: str) -> bytes:
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    allowed_history = False
    if (
        parts.scheme == "https"
        and parts.netloc == "eodhd.com"
        and parts.path == f"/api/eod/{EODHD_DEMO_SYMBOL}"
        and set(query) == {"api_token", "from", "to", "period", "order", "fmt"}
    ):
        with suppress(ValueError, IndexError):
            allowed_history = url == eodhd_demo_url(
                date.fromisoformat(query["from"][0]), date.fromisoformat(query["to"][0])
            )
    if url != EODHD_METADATA_URL and not allowed_history:
        raise ValueError("Only documented fixed-symbol demo requests are permitted")
    request = urllib.request.Request(
        url, headers={"User-Agent": "PortfolioResearch private evaluation/1.0"}
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=25) as response:
            payload = response.read(4_000_001)
            if len(payload) > 4_000_000:
                raise ValueError("Demo response exceeds the bounded size")
            return bytes(payload)
    except urllib.error.HTTPError as error:
        raise ProviderTransportError(
            EODHD_DEMO_PROVIDER_ID,
            "PROVIDER_HTTP_ERROR",
            f"EODHD demo returned HTTP {error.code}; no alternate token or endpoint was used.",
            retryable=error.code == 429 or error.code >= 500,
            retry_after_seconds=parse_retry_after_seconds(error.headers.get("Retry-After")),
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderTransportError(
            EODHD_DEMO_PROVIDER_ID,
            "PROVIDER_UNAVAILABLE",
            "EODHD demo request failed; no alternate endpoint was used.",
            retryable=True,
        ) from None


def fetch_demo_metadata(
    *,
    transport: Callable[[str], bytes] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RawProviderRecord:
    """One documented metadata request; returned evidence must be retained by the runner."""

    payload = (transport or _default_transport)(EODHD_METADATA_URL)
    return RawProviderRecord(
        domain=ExternalDataDomain.COMPANY_REFERENCE,
        provider_id=EODHD_DEMO_PROVIDER_ID,
        provider_schema_version=EODHD_GENERAL_SCHEMA_VERSION,
        source_record_id=f"{EODHD_DEMO_SYMBOL}:GENERAL",
        source_url=EODHD_METADATA_URL,
        media_type="application/json",
        retrieved_at=clock(),
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


class EodhdDemoProvider:
    """One bounded request; transport is explicit and cannot silently use a paid key."""

    provider_id = EODHD_DEMO_PROVIDER_ID

    def __init__(
        self,
        mapping: EodhdDemoMapping,
        metadata: RawProviderRecord,
        *,
        transport: Callable[[str], bytes] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        validate_eodhd_demo_metadata(metadata, mapping)
        self.mapping = mapping
        self.metadata = metadata
        self.transport = transport or _default_transport
        self.clock = clock

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        start, end = _window(query, self.mapping)
        url = eodhd_demo_url(start, end)
        payload = await asyncio.to_thread(self.transport, url)
        return (
            RawProviderRecord(
                domain=query.domain,
                provider_id=self.provider_id,
                provider_schema_version=EODHD_DEMO_SCHEMA_VERSION,
                source_record_id=eodhd_demo_record_id(self.mapping, start, end),
                source_url=url,
                media_type="application/json",
                retrieved_at=self.clock(),
                payload=payload,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
            ),
        )


class EodhdDemoNormalizer:
    domain = ExternalDataDomain.MARKET_DATA
    version = "eodhd-demo-native-close-v1"

    def __init__(
        self, mapping: EodhdDemoMapping, metadata: RawProviderRecord, query: ProviderQuery
    ) -> None:
        validate_eodhd_demo_metadata(metadata, mapping)
        self.mapping = mapping
        self.metadata = metadata
        self.start, self.end = _window(query, mapping)

    def normalize(self, record: RawProviderRecord) -> NormalizationResult[YahooListingFacts]:
        try:
            facts, issues = self._normalize(record)
        except (ValueError, TypeError, KeyError, InvalidOperation) as error:
            return NormalizationResult(
                disposition=NormalizationDisposition.REJECTED,
                observation=None,
                issues=(
                    NormalizationIssue(
                        code="INVALID_EODHD_DEMO", message=str(error), severity="ERROR"
                    ),
                ),
            )
        return NormalizationResult(
            disposition=NormalizationDisposition.ACCEPTED, observation=facts, issues=issues
        )

    def _normalize(
        self, record: RawProviderRecord
    ) -> tuple[YahooListingFacts, tuple[NormalizationIssue, ...]]:
        if (
            record.provider_id != EODHD_DEMO_PROVIDER_ID
            or record.provider_schema_version != EODHD_DEMO_SCHEMA_VERSION
            or record.domain != self.domain
            or record.source_record_id != eodhd_demo_record_id(self.mapping, self.start, self.end)
            or str(record.source_url) != eodhd_demo_url(self.start, self.end)
            or record.payload is None
            or self.end >= record.retrieved_at.astimezone(UTC).date()
        ):
            raise ValueError(
                "Price response does not match the reviewed provider, listing and window"
            )
        rows = json.loads(record.payload, parse_float=Decimal)
        if not isinstance(rows, list) or len(rows) > 366:
            raise ValueError("Expected a bounded daily-price array")
        prices: list[YahooPriceFact] = []
        seen: set[date] = set()
        missing = 0
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid price row")
            session = date.fromisoformat(row["date"])
            if not self.start <= session <= self.end or session.weekday() > 4 or session in seen:
                raise ValueError("Out-of-window, duplicate or non-weekday price session")
            seen.add(session)
            if row.get("close") is None:
                missing += 1
                continue
            close = _positive_decimal(row["close"])
            adjusted = (
                _positive_decimal(row["adjusted_close"])
                if row.get("adjusted_close") is not None
                else None
            )
            # Match canonical value identity across overlapping request windows.
            # Original response bytes remain independently retained with each batch.
            value_digest = hashlib.sha256(
                json.dumps(
                    {
                        "close": format(close.normalize(), "f"),
                        "total_return_close": format(adjusted.normalize(), "f")
                        if adjusted is not None
                        else None,
                        "currency": self.mapping.currency,
                        "adjustment_basis": EODHD_ADJUSTMENT_BASIS,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            # Volume is split-adjusted at source; do not present it as native traded volume.
            prices.append(
                YahooPriceFact(
                    market_date=datetime.combine(session, time.min, UTC),
                    observed_at=record.retrieved_at,
                    provider_close=close,
                    split_adjusted_close=None,
                    total_return_close=adjusted,
                    volume=None,
                    currency=self.mapping.currency,
                    provider_currency=self.mapping.currency,
                    source_price_multiplier=Decimal(1),
                    provider_symbol=self.mapping.provider_symbol,
                    price_kind="DAILY_CLOSE",
                    adjustment_basis=EODHD_ADJUSTMENT_BASIS,
                    source_ref=f"eodhd-demo:{self.mapping.listing_id}:{session}:{value_digest}",
                )
            )
        issues = [
            NormalizationIssue(
                code="INDICATIVE_DEMO_PRICE",
                message=(
                    "Private EODHD evaluation: indicative provider close, not an official exchange "
                    "close; split-only prices unavailable."
                ),
                severity="WARNING",
            )
        ]
        if missing or not prices:
            issues.append(
                NormalizationIssue(
                    code="MISSING_CLOSE",
                    message=(
                        f"{missing} supplied sessions have no close; "
                        f"{len(prices)} usable observations."
                    ),
                    severity="WARNING",
                )
            )
        return YahooListingFacts(
            listing_id=self.mapping.listing_id,
            provider_symbol=self.mapping.provider_symbol,
            prices=tuple(sorted(prices, key=lambda item: item.market_date)),
            current_quote=None,
            corporate_actions=(),
            missing_close_count=missing,
            in_progress_bar_count=0,
            duplicate_session_bar_count=0,
            returned_exchange=self.mapping.venue,
        ), tuple(issues)


def _positive_decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Price must be numeric")
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise ValueError("Price must be finite and positive")
    return result
