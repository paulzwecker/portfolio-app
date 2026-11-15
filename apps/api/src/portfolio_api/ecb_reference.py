"""Bounded official ECB reference rates, retaining the original per-EUR response.

Reference dates are encoded at UTC midnight, not asserted publication instants.
Retrieval is the observation time; reciprocal conversion is explicitly disclosed.
These informational reference rates are not trade-execution quotes.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from pydantic import AnyHttpUrl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from portfolio_api.domain.models import FxObservation
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    ProviderTransportError,
    RawProviderRecord,
    parse_retry_after_seconds,
)
from portfolio_api.yahoo_finance import YahooFxFact, YahooFxFacts

ECB_PROVIDER_ID = "ECB_REFERENCE"
ECB_SCHEMA_VERSION = "ecb-exr-sdmx-csv-v1"
ECB_PAIRS = frozenset({("USD", "EUR"), ("DKK", "EUR")})
MAX_WINDOW_DAYS = 366
MAX_RESPONSE_BYTES = 2_000_000
Transport = Callable[[str], bytes]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _default_transport(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PortfolioResearch ECB reference rates/1.0", "Accept": "text/csv"},
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=60) as response:
            body = bytes(response.read(MAX_RESPONSE_BYTES + 1))
    except urllib.error.HTTPError as error:
        raise ProviderTransportError(
            ECB_PROVIDER_ID,
            f"HTTP_{error.code}",
            f"ECB returned HTTP {error.code}.",
            retryable=error.code == 429 or error.code >= 500,
            retry_after_seconds=parse_retry_after_seconds(error.headers.get("Retry-After")),
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderTransportError(
            ECB_PROVIDER_ID, "NETWORK_ERROR", "ECB request failed.", retryable=True
        ) from None
    if len(body) > MAX_RESPONSE_BYTES:
        raise ProviderTransportError(
            ECB_PROVIDER_ID,
            "RESPONSE_TOO_LARGE",
            "ECB response exceeded the bound.",
            retryable=False,
        )
    return body


class EcbReferenceProvider:
    provider_id = ECB_PROVIDER_ID

    def __init__(self, *, transport: Transport = _default_transport) -> None:
        self._transport = transport

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        if (
            query.domain != ExternalDataDomain.FX
            or query.start_date is None
            or query.end_date is None
        ):
            raise ValueError("ECB requires an explicit FX date window")
        if (query.end_date - query.start_date).days >= MAX_WINDOW_DAYS:
            raise ValueError("ECB requests are bounded to 366 inclusive dates")
        if query.end_date > query.requested_at.date():
            raise ValueError("ECB requests cannot include future reference dates")
        pairs = {(subject.base_currency, subject.quote_currency) for subject in query.subjects}
        if (
            len(pairs) != len(query.subjects)
            or not pairs.issubset(ECB_PAIRS)
            or any(subject.kind != CanonicalSubjectKind.CURRENCY_PAIR for subject in query.subjects)
        ):
            raise ValueError("ECB supports only exact, distinct USD/EUR and DKK/EUR subjects")
        records = []
        for base, quote in sorted(pairs):
            query_string = urllib.parse.urlencode(
                {"startPeriod": query.start_date, "endPeriod": query.end_date, "format": "csvdata"}
            )
            url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{base}.EUR.SP00.A?{query_string}"
            body = await asyncio.to_thread(self._transport, url)
            records.append(
                RawProviderRecord(
                    domain=ExternalDataDomain.FX,
                    provider_id=self.provider_id,
                    provider_schema_version=ECB_SCHEMA_VERSION,
                    source_record_id=f"FX:{base}/{quote}",
                    source_url=AnyHttpUrl(url),
                    media_type="text/csv",
                    retrieved_at=datetime.now(UTC),
                    payload=body,
                    payload_sha256=hashlib.sha256(body).hexdigest(),
                )
            )
        return records


def _rejected(code: str, message: str) -> NormalizationResult[YahooFxFacts]:
    return NormalizationResult(
        disposition=NormalizationDisposition.REJECTED,
        observation=None,
        issues=(NormalizationIssue(code=code, message=message, severity="ERROR"),),
    )


class EcbFxNormalizer:
    """Reuse the existing FX observation shape; provider payloads stay separate."""

    domain = ExternalDataDomain.FX
    version = "ecb-reference-fx-v1"

    def __init__(self, *, start_date: date, end_date: date) -> None:
        self.start_date = start_date
        self.end_date = end_date

    def normalize(self, record: RawProviderRecord) -> NormalizationResult[YahooFxFacts]:
        if (
            record.provider_id != ECB_PROVIDER_ID
            or record.domain != ExternalDataDomain.FX
            or record.provider_schema_version != ECB_SCHEMA_VERSION
            or record.payload is None
        ):
            return _rejected("PROVIDER_DOMAIN_MISMATCH", "Raw record is not supported ECB FX data.")
        if not (record.source_record_id or "").startswith("FX:"):
            return _rejected("FX_IDENTITY_MISSING", "ECB response has no exact currency pair.")
        pair = (record.source_record_id or "").removeprefix("FX:").split("/")
        if len(pair) != 2 or tuple(pair) not in ECB_PAIRS:
            return _rejected("FX_PAIR_UNSUPPORTED", "ECB currency-pair identity is not reviewed.")
        base, quote = pair
        series = f"EXR.D.{base}.EUR.SP00.A"
        rows: dict[date, Decimal] = {}
        excluded = 0
        try:
            reader = csv.DictReader(io.StringIO(record.payload.decode("utf-8-sig")))
            required = {
                "KEY",
                "FREQ",
                "CURRENCY",
                "CURRENCY_DENOM",
                "EXR_TYPE",
                "EXR_SUFFIX",
                "TIME_PERIOD",
                "OBS_VALUE",
                "OBS_STATUS",
                "UNIT",
                "UNIT_MULT",
            }
            if not required.issubset(reader.fieldnames or []):
                return _rejected(
                    "ECB_SCHEMA_INVALID", "ECB CSV is missing required identity fields."
                )
            for row in reader:
                expected = {
                    "KEY": series,
                    "FREQ": "D",
                    "CURRENCY": base,
                    "CURRENCY_DENOM": "EUR",
                    "EXR_TYPE": "SP00",
                    "EXR_SUFFIX": "A",
                    "UNIT": base,
                    "UNIT_MULT": "0",
                }
                if any(row.get(key) != value for key, value in expected.items()):
                    return _rejected(
                        "ECB_SERIES_MISMATCH", "ECB returned a different series or unit."
                    )
                day = date.fromisoformat(row["TIME_PERIOD"])
                if not self.start_date <= day <= self.end_date or day > record.retrieved_at.date():
                    return _rejected(
                        "ECB_DATE_OUTSIDE_SCOPE", "ECB reference date is outside the window."
                    )
                if row["OBS_STATUS"] != "A" or not row["OBS_VALUE"]:
                    excluded += 1
                    continue
                rate = Decimal(row["OBS_VALUE"])
                if not rate.is_finite() or rate <= 0:
                    excluded += 1
                    continue
                if day in rows and rows[day] != rate:
                    return _rejected(
                        "DUPLICATE_FX_SESSION_CONFLICT", "ECB rates conflict for one date."
                    )
                rows[day] = rate
        except (UnicodeError, ValueError, InvalidOperation, csv.Error, TypeError):
            return _rejected(
                "ECB_PAYLOAD_INVALID", "ECB CSV contains invalid date or numeric data."
            )
        if not rows:
            return _rejected("FX_SERIES_EMPTY", "ECB returned no eligible reference rates.")
        observations = []
        for day, raw_rate in sorted(rows.items()):
            try:
                with localcontext() as context:
                    context.prec = 40
                    rate = (Decimal(1) / raw_rate).quantize(Decimal("0.00000000000001"))
                if rate <= 0 or rate >= Decimal("100000000000000"):
                    raise InvalidOperation
            except InvalidOperation:
                return _rejected(
                    "ECB_RATE_OUT_OF_RANGE", "ECB reciprocal exceeds canonical precision."
                )
            fingerprint = hashlib.sha256(str(raw_rate.normalize()).encode()).hexdigest()
            source_ref = f"ECB:{series}:{day}:{fingerprint}"
            observations.append(
                YahooFxFact(
                    base,
                    quote,
                    series,
                    "EUR",
                    base,
                    True,
                    datetime.combine(day, datetime.min.time(), UTC),
                    record.retrieved_at,
                    rate,
                    source_ref,
                )
            )
        issues = (
            (
                NormalizationIssue(
                    code="ECB_OBSERVATIONS_UNAVAILABLE",
                    message=f"Excluded {excluded} unavailable or invalid ECB observations.",
                    severity="WARNING",
                ),
            )
            if excluded
            else ()
        )
        return NormalizationResult(
            disposition=NormalizationDisposition.ACCEPTED,
            observation=YahooFxFacts(base, quote, series, tuple(observations)),
            issues=issues,
        )


async def build_ecb_fx_report(
    session: Session,
    *,
    start_date: date | None,
    end_date: date,
    lookback_days: int = 365,
    fx_pairs: set[tuple[str, str]] | None = None,
    provider: EcbReferenceProvider | None = None,
) -> dict[str, Any]:
    from portfolio_api.market_data_ingestion import (
        fx_provider_batch_plan,
        portfolio_fx_requirements,
    )

    pairs = fx_pairs if fx_pairs is not None else portfolio_fx_requirements(session)[1]
    source = provider or EcbReferenceProvider()
    plans = []
    failures = []
    for base, quote in sorted(pairs & ECB_PAIRS):
        latest = session.scalar(
            select(func.max(FxObservation.effective_at)).where(
                FxObservation.provider == ECB_PROVIDER_ID,
                FxObservation.base_currency == base,
                FxObservation.quote_currency == quote,
            )
        )
        start = start_date or (
            latest.date() - timedelta(days=3)
            if latest
            else end_date - timedelta(days=min(max(lookback_days, 1), 365) - 1)
        )
        if start > end_date:
            continue
        query = ProviderQuery(
            domain=ExternalDataDomain.FX,
            subjects=(
                CanonicalSubjectRef(
                    kind=CanonicalSubjectKind.CURRENCY_PAIR,
                    base_currency=base,
                    quote_currency=quote,
                ),
            ),
            start_date=start,
            end_date=end_date,
            requested_at=datetime.now(UTC),
        )
        try:
            records = list(await source.fetch(query))
        except ProviderTransportError as error:
            failures.append(
                {
                    "source_record_id": f"FX:{base}/{quote}",
                    "code": error.code,
                    "message": str(error),
                    "retryable": error.retryable,
                    "retry_after_seconds": error.retry_after_seconds,
                }
            )
            continue
        plan = fx_provider_batch_plan(
            query,
            records,
            EcbFxNormalizer(start_date=start, end_date=end_date),
            provider_id=ECB_PROVIDER_ID,
            provider_schema_version=ECB_SCHEMA_VERSION,
            provider_label="European Central Bank",
            reason_suffix=(
                "; reciprocal of original currency units per EUR, rounded to 14 decimals. "
                "Reference date encoded at UTC midnight; observation time is retrieval. "
                "Informational reference rate, not a transaction quote."
            ),
        )
        if plan:
            plans.append(plan)
    return {
        "provider_id": ECB_PROVIDER_ID,
        "status": "PREVIEW",
        "plans": plans,
        "required_fx_pairs": [f"{base}/{quote}" for base, quote in sorted(pairs)],
        "unmapped_fx_pairs": [f"{base}/{quote}" for base, quote in sorted(pairs - ECB_PAIRS)],
        "fx_fetch_failures": failures,
        "fx_batches": [plan["report"] for plan in plans],
        "market_data_batches": [],
        "provider_fetch_failures": [],
        "unresolved_listings": [],
    }
