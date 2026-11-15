"""Opt-in real-source estimates through canonical PostgreSQL and read-only APIs."""

import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from browser_real_estimates import prepare_real_estimates, protected_estimate_state
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine


@pytest.mark.source_data
@pytest.mark.integration
def test_real_estimates_api_and_financials(postgres_engine: Engine) -> None:
    receipt = os.environ.get("BROWSER_CONSENSUS_RECEIPT")
    if not receipt:
        pytest.skip("Private real consensus capture is not configured")
    settings = fixture_settings()
    metadata = prepare_real_estimates(postgres_engine, settings, Path(receipt))
    before = protected_estimate_state(postgres_engine)
    with TestClient(fixture_application(postgres_engine, settings, metadata)) as client:
        root = f"/v1/companies/{metadata['company_id']}"
        response = client.get(f"{root}/consensus-estimates")
        assert response.status_code == 200, response.text
        provider = response.json()["providers"][0]
        assert provider["observation_count"] == 8
        assert provider["provider_id"] == "eodhd_demo_estimates"
        for sample in metadata["expected"]["samples"]:
            period = next(
                item
                for item in provider["periods"]
                if item["metric"] == sample["metric"]
                and item["period_type"] == sample["period_type"]
                and item["period_end"] == sample["period_end"]
            )
            observation = period["current_observation"]
            assert len(period["history"]) == 1  # Current capture is not historical revisions.
            assert observation["revision_context"] == "SNAPSHOT"
            for field in ["value", "low_value", "high_value"]:
                assert Decimal(observation[field]) == Decimal(sample[field])
            assert observation["analyst_count"] == sample["analyst_count"]
            assert observation["currency"] == "USD"
            assert observation["data_quality"] == sample["data_quality"]
        for kind in ["ANNUAL", "QUARTERLY"]:
            statements = client.get(f"{root}/financial-statements", params={"period_type": kind})
            assert statements.status_code == 200, statements.text
            rows = [
                item for item in statements.json()["rows"] if item["source_kind"] == "CONSENSUS"
            ]
            assert len(rows) == 2
            for row in rows:
                assert len(row["cells"]) == 2
                assert all(
                    cell["status"] == ("AVAILABLE" if row["metric"] == "REVENUE" else "DATA_CHECK")
                    for cell in row["cells"]
                )
        cutoff = datetime.fromisoformat(metadata["captured_at"]) - timedelta(seconds=1)
        earlier = client.get(f"{root}/consensus-estimates", params={"known_at": cutoff.isoformat()})
        assert earlier.status_code == 200
        assert not earlier.json()["providers"]
    assert protected_estimate_state(postgres_engine) == before
