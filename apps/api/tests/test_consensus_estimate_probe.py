import asyncio
import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import Message
from typing import Any
from uuid import UUID, uuid4

import pytest
from pytest import MonkeyPatch

from portfolio_api.consensus_estimate_probe import (
    ALPHA_VANTAGE_PROBE_ID,
    AlphaVantageEstimatesProbeProvider,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    ProviderTransportError,
)


async def _direct_to_thread(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return function(*args, **kwargs)


def _query(company_id: UUID) -> ProviderQuery:
    return ProviderQuery(
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
        subjects=(CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=company_id),),
        requested_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
    )


def test_probe_returns_raw_one_symbol_record_without_persisting_or_leaking_key(
    monkeypatch: MonkeyPatch,
) -> None:
    company_id = uuid4()
    requested_urls: list[str] = []
    payload = json.dumps({"symbol": "MSFT", "fixtureOnly": True}).encode()

    class Response:
        headers = Message()

        def __init__(self) -> None:
            self.headers["Content-Type"] = "application/json; charset=utf-8"

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self) -> bytes:
            return payload

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> Response:
        requested_urls.append(request.full_url)
        assert timeout == 30
        assert request.get_header("User-agent") == "portfolio-estimate-source-probe/1.0"
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "portfolio_api.consensus_estimate_probe.asyncio.to_thread", _direct_to_thread
    )
    provider = AlphaVantageEstimatesProbeProvider("probe-secret", {company_id: "MSFT"})

    records = asyncio.run(provider.fetch(_query(company_id)))

    assert len(records) == 1
    record = records[0]
    assert record.provider_id == ALPHA_VANTAGE_PROBE_ID
    assert record.source_record_id == "MSFT:EARNINGS_ESTIMATES"
    assert record.retrieved_at.tzinfo == UTC
    assert record.payload == payload
    assert record.payload_sha256
    assert "apikey=probe-secret" in requested_urls[0]
    assert "probe-secret" not in str(record.source_url)


def test_probe_rejects_wrong_symbol_and_provider_entitlement_messages(
    monkeypatch: MonkeyPatch,
) -> None:
    company_id = uuid4()

    class Response:
        headers = Message()

        def __init__(self, payload: bytes) -> None:
            self._payload = payload
            self.headers["Content-Type"] = "application/json"

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self) -> bytes:
            return self._payload

    payloads = [b'{"symbol":"OTHER"}', b'{"Information":"Claim an API key"}']
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(payloads.pop(0)),
    )
    monkeypatch.setattr(
        "portfolio_api.consensus_estimate_probe.asyncio.to_thread", _direct_to_thread
    )
    provider = AlphaVantageEstimatesProbeProvider("probe-secret", {company_id: "MSFT"})

    for code in ("IDENTITY_MISMATCH", "PROVIDER_MESSAGE"):
        with pytest.raises(ProviderTransportError) as captured:
            asyncio.run(provider.fetch(_query(company_id)))
        assert captured.value.code == code
        assert "probe-secret" not in str(captured.value)
