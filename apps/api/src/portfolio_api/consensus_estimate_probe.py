"""One-symbol, read-only Alpha Vantage estimates probe.

This experimental transport is deliberately not registered with production
ingestion and has no normalizer or persistence path. It exists to inspect the
provider-native response after an operator has reviewed the applicable license.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import AnyHttpUrl, TypeAdapter

from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    ProviderTransportError,
    RawProviderRecord,
)

ALPHA_VANTAGE_PROBE_ID = "alpha_vantage_estimates_probe"
ALPHA_VANTAGE_ENDPOINT = "https://www.alphavantage.co/query"


class AlphaVantageEstimatesProbeProvider:
    """Fetch one documented estimates response without normalizing or saving it."""

    provider_id = ALPHA_VANTAGE_PROBE_ID

    def __init__(self, api_key: str, provider_symbols: dict[UUID, str]) -> None:
        if not api_key.strip():
            raise ValueError("ALPHA_VANTAGE_API_KEY is required for the read-only probe")
        if any(not symbol.strip() for symbol in provider_symbols.values()):
            raise ValueError("Provider symbols must be explicit and nonblank")
        self._api_key = api_key
        self._symbols = provider_symbols

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        if query.domain != ExternalDataDomain.CONSENSUS_ESTIMATES:
            raise ValueError("Alpha Vantage probe only supports consensus estimates")
        if len(query.subjects) != 1:
            raise ValueError("The read-only probe is limited to one subject per request")
        subject = query.subjects[0]
        if subject.kind != CanonicalSubjectKind.COMPANY or subject.id not in self._symbols:
            raise ValueError("Probe requires one company with an explicit provider-symbol mapping")
        symbol = self._symbols[subject.id]
        return (await asyncio.to_thread(self._fetch_one, symbol),)

    def _fetch_one(self, symbol: str) -> RawProviderRecord:
        parameters = {"function": "EARNINGS_ESTIMATES", "symbol": symbol, "apikey": self._api_key}
        request_url = f"{ALPHA_VANTAGE_ENDPOINT}?{urllib.parse.urlencode(parameters)}"
        request = urllib.request.Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "portfolio-estimate-source-probe/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                retrieved_at = datetime.now(UTC)
                content_type = response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as error:
            raise ProviderTransportError(
                ALPHA_VANTAGE_PROBE_ID,
                "RATE_LIMITED" if error.code == 429 else f"HTTP_{error.code}",
                f"Alpha Vantage probe returned HTTP {error.code}; request details were omitted",
                retryable=error.code == 429 or 500 <= error.code <= 599,
            ) from None
        except (TimeoutError, urllib.error.URLError, ConnectionError) as error:
            raise ProviderTransportError(
                ALPHA_VANTAGE_PROBE_ID,
                "NETWORK_ERROR",
                f"Alpha Vantage probe failed with {type(error).__name__}; "
                "request details were omitted",
                retryable=True,
            ) from None

        try:
            response_body = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ProviderTransportError(
                ALPHA_VANTAGE_PROBE_ID,
                "INVALID_RESPONSE",
                "Alpha Vantage probe did not return valid JSON",
                retryable=False,
            ) from None
        if not isinstance(response_body, dict):
            raise ProviderTransportError(
                ALPHA_VANTAGE_PROBE_ID,
                "INVALID_RESPONSE",
                "Alpha Vantage estimates response was not a JSON object",
                retryable=False,
            )
        if any(key in response_body for key in ("Error Message", "Note", "Information")):
            raise ProviderTransportError(
                ALPHA_VANTAGE_PROBE_ID,
                "PROVIDER_MESSAGE",
                "Alpha Vantage returned an error, entitlement, or rate-limit message",
                retryable=False,
            )
        response_symbol = response_body.get("symbol")
        if (
            response_symbol is not None
            and str(response_symbol).strip().casefold() != symbol.casefold()
        ):
            raise ProviderTransportError(
                ALPHA_VANTAGE_PROBE_ID,
                "IDENTITY_MISMATCH",
                "Alpha Vantage response symbol did not match the explicit probe mapping",
                retryable=False,
            )

        safe_parameters = {"function": "EARNINGS_ESTIMATES", "symbol": symbol}
        safe_url = f"{ALPHA_VANTAGE_ENDPOINT}?{urllib.parse.urlencode(safe_parameters)}"
        safe_source_url = TypeAdapter(AnyHttpUrl).validate_python(safe_url)
        return RawProviderRecord(
            domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
            provider_id=ALPHA_VANTAGE_PROBE_ID,
            provider_schema_version=None,
            source_record_id=f"{symbol}:EARNINGS_ESTIMATES",
            source_url=safe_source_url,
            media_type=content_type.split(";", maxsplit=1)[0],
            retrieved_at=retrieved_at,
            payload=payload,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
        )


def _main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch one Alpha Vantage estimates payload to stdout; never writes to the database."
        )
    )
    parser.add_argument("--company-id", required=True, type=UUID)
    parser.add_argument("--provider-symbol", required=True)
    args = parser.parse_args()
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    provider = AlphaVantageEstimatesProbeProvider(api_key, {args.company_id: args.provider_symbol})
    query = ProviderQuery(
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
        subjects=(CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=args.company_id),),
        requested_at=datetime.now(UTC),
    )
    record = asyncio.run(provider.fetch(query))[0]
    payload = json.loads(record.payload or b"{}")
    returned_symbol = payload.get("symbol") if isinstance(payload, dict) else None
    print(
        json.dumps(
            {
                "provider_id": record.provider_id,
                "source_record_id": record.source_record_id,
                "source_url": str(record.source_url),
                "retrieved_at": record.retrieved_at.isoformat(),
                "payload_sha256": record.payload_sha256,
                "response_symbol": returned_symbol,
                "response_symbol_matches": (
                    str(returned_symbol).strip().casefold() == args.provider_symbol.casefold()
                    if returned_symbol is not None
                    else None
                ),
                "raw_response": payload,
                "canonical_imported": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
