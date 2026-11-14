"""Queue-to-provider-to-API proof against an isolated recorded-response database."""

from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from browser_portfolio_data import prepare_portfolio_data
from browser_refresh_data import RefreshRehearsal
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from portfolio_api.cloud_cron import main as cloud_cycle


@pytest.mark.integration
def test_recorded_refresh_persists_and_scheduled_cycle_updates_existing_api(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    settings = fixture_settings()
    metadata = prepare_portfolio_data(postgres_engine, tmp_path, "unpriced", settings)
    refresh = RefreshRehearsal(postgres_engine, settings, metadata)
    app = fixture_application(postgres_engine, refresh.settings, metadata, refresh=refresh)
    with refresh.running(), TestClient(app) as client:
        baseline = refresh.protected_state()
        rejected = client.post(
            "/v1/operations/job-requests",
            json={
                "job_name": "REFRESH_ALL",
                "scope_kind": "ACTIVE_UNIVERSE",
            },
        )
        assert rejected.status_code == 405
        response = client.post(
            "/v1/operations/job-requests",
            json={
                "job_name": "SEC_FUNDAMENTALS",
                "scope_kind": "COMPANY",
                "company_id": metadata["company_id"],
            },
        )
        assert response.status_code == 202, response.text
        job = response.json()
        assert job["status"] == "QUEUED"
        assert not refresh.calls
        assert client.get(f"/v1/operations/job-requests/{job['id']}").json()["id"] == job["id"]
        client.post("/__test/refresh-control", json={"paused": False})
        for _ in range(80):
            receipt = client.get(f"/v1/operations/job-requests/{job['id']}").json()
            if receipt["status"] not in {"QUEUED", "RUNNING"}:
                break
            Event().wait(0.1)
        assert receipt["status"] == "SUCCEEDED", (receipt, refresh.errors)
        assert len(refresh.calls) == 1
        initial = client.get(f"/v1/companies/{metadata['company_id']}/financial-statements").json()
        assert any(row["metric"] == "REVENUE" for row in initial["rows"])
        result = client.post(
            "/__test/refresh-control",
            json={
                "paused": True,
                "response": "updated",
                "scheduled_days_later": 3,
            },
        )
        assert result.status_code == 200, result.text
        first = result.json()
        assert first["counts"]["source_documents"] == 2
        assert first["counts"]["reported_fundamental_observations"] > 2
        assert first["protected_state_sha256"] == baseline
        updated = client.get(f"/v1/companies/{metadata['company_id']}/financial-statements").json()
        assert updated != initial
        repeated = client.post(
            "/__test/refresh-control",
            json={
                "paused": True,
                "response": "updated",
                "scheduled_days_later": 3,
            },
        ).json()
        assert repeated["provider_request_count"] == first["provider_request_count"]
        assert repeated["counts"] == first["counts"]
        assert not repeated["worker_errors"]

        outage = client.post(
            "/__test/refresh-control",
            json={
                "paused": True,
                "response": "outage",
                "scheduled_days_later": 4,
            },
        ).json()
        assert (
            outage["counts"]["reported_fundamental_observations"]
            == first["counts"]["reported_fundamental_observations"]
        )
        assert all(job["operation_status"] == "FAILED" for job in outage["last_cycle"]["jobs"])
        partial = client.post(
            "/__test/refresh-control",
            json={
                "paused": True,
                "response": "partial",
                "scheduled_days_later": 5,
            },
        ).json()
        assert partial["last_cycle"]["jobs"][0]["operation_status"] == "PARTIAL"
        assert partial["protected_state_sha256"] == baseline


@pytest.mark.integration
def test_sec_cloud_command_runs_recorded_provider_through_database(
    postgres_engine: Engine,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = fixture_settings()
    metadata = prepare_portfolio_data(postgres_engine, tmp_path, "unpriced", settings)
    refresh = RefreshRehearsal(postgres_engine, settings, metadata)
    baseline = refresh.protected_state()
    enabled = refresh.settings.model_copy(
        update={
            "recurring_operations_enabled": True,
            "cloud_ingestion_enabled": True,
        }
    )
    with (
        refresh.running(),
        patch("portfolio_api.cloud_cron.Settings", return_value=enabled),
        patch("portfolio_api.cloud_cron.create_database_engine", return_value=postgres_engine),
        patch(
            "portfolio_api.cloud_cron.run_startup_refresh", side_effect=AssertionError("No Yahoo")
        ),
    ):
        assert cloud_cycle(["--scope", "sec-data"]) == 0
        first = refresh.readback()
        counts = first["counts"]
        assert isinstance(counts, dict)
        assert counts["reported_fundamental_observations"] == 2
        assert counts["source_documents"] == 2
        assert first["provider_request_count"] == 2
        assert cloud_cycle(["--scope", "sec-data"]) == 0
        assert refresh.readback()["provider_request_count"] == 2
        assert refresh.protected_state() == baseline
    assert '"scope": "sec-data"' in capsys.readouterr().out
