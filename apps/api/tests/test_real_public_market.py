"""Opt-in private official-source database/API journey; no network fallback."""

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from browser_public_market_data import PublicMarketReplay
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from portfolio_api.recurring_operations import process_manual_job_requests


@pytest.mark.integration
@pytest.mark.source_data
def test_private_public_market_manual_incremental_scheduled_valuation(
    postgres_engine: Engine,
) -> None:
    path = os.environ.get("BROWSER_PUBLIC_MARKET_MANIFEST")
    if not path:
        pytest.skip("Private public-source recording not configured")
    replay = PublicMarketReplay(postgres_engine, fixture_settings(), Path(path))
    metadata = replay.metadata
    expected = metadata["expected"]
    app = fixture_application(postgres_engine, replay.settings, metadata, refresh=replay)
    with replay.running(), TestClient(app) as client:
        baseline = replay.protected_state()
        queued = client.post(
            "/v1/operations/job-requests",
            json={
                "job_name": "MARKET_AND_FX",
                "scope_kind": "ACTIVE_UNIVERSE",
            },
        )
        assert queued.status_code == 202, queued.text
        assert queued.json()["status"] == "QUEUED"
        job_id = queued.json()["id"]
        process_manual_job_requests(
            postgres_engine, replay.settings, job_names=frozenset({"MARKET_AND_FX"})
        )
        job = client.get(f"/v1/operations/job-requests/{job_id}").json()
        assert job["status"] in {"SUCCEEDED", "PARTIAL"}, job
        before = replay.readback()
        assert before["counts"]["price_observations"] == expected["initial_prices"]
        assert before["counts"]["fx_observations"] == expected["initial_fx"]
        assert before["offline_transport_calls"] == 4
        old = client.get(f"/v1/portfolios/{metadata['portfolio_id']}/overview").json()
        assert old["base_market_value"] is None  # Approved history alone is stale today.
        updated = client.post(
            "/__test/refresh-control",
            json={
                "paused": True,
                "phase": "incremental",
                "scheduled": True,
            },
        )
        assert updated.status_code == 200, updated.text
        final = updated.json()
        assert final["last_cycle"]["status"] in {"COMPLETE", "PARTIAL"}, final
        assert final["counts"]["price_observations"] == expected["final_prices"]
        assert final["counts"]["fx_observations"] == expected["final_fx"]
        assert final["offline_transport_calls"] == 8
        market = client.get(f"/v1/listings/{metadata['listing_id']}/market-data").json()
        assert market["native_freshness"] == "FRESH"
        assert len(market["native_history"]) > 1
        assert market["history"] == []
        assert market["latest"]["split_adjusted_close"] is None
        assert Decimal(market["latest"]["native_close"]) == Decimal(expected["price"])
        assert market["latest"]["provider"] == "EODHD_DEMO"
        assert market["latest"]["adjustment_basis"] == "UNADJUSTED_NATIVE_CLOSE"
        overview = client.get(f"/v1/portfolios/{metadata['portfolio_id']}/overview").json()
        assert Decimal(overview["base_market_value"]) == Decimal(expected["portfolio_eur"])
        assert overview["valuation_status"] == "VALUED"
        holding = overview["companies"][0]["positions"][0]
        assert Decimal(holding["base_market_value"]) == Decimal(expected["position_eur"])
        assert holding["valuation_price_basis"] == "UNADJUSTED_NATIVE_CLOSE"
        assert holding["price_provider"] == "EODHD_DEMO"
        historical = client.get(
            f"/v1/portfolios/{metadata['portfolio_id']}/overview",
            params={
                "as_of": datetime(2026, 11, 9, 23, tzinfo=UTC).isoformat(),
            },
        ).json()
        assert historical["base_market_value"] is None
        repeat = client.post(
            "/__test/refresh-control",
            json={
                "paused": True,
                "phase": "incremental",
                "scheduled": True,
            },
        ).json()
        assert repeat["counts"] == final["counts"]
        assert repeat["offline_transport_calls"] == final["offline_transport_calls"]
        assert replay.protected_state() == baseline
        assert replay.errors == []
        output = os.environ.get("PUBLIC_MARKET_READBACK_PATH")
        if output:
            Path(output).write_text(
                json.dumps(
                    {
                        "readback": repeat,
                        "overview": overview,
                        "market": market,
                        "production": False,
                        "fixture_quantities": True,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
