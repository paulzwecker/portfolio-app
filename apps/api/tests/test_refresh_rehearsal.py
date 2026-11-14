"""Queue-to-provider-to-API proof against an isolated recorded-response database."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from browser_portfolio_data import prepare_portfolio_data
from browser_real_sec_data import SecRecording, prepare_real_sec_data
from browser_refresh_data import RefreshRehearsal
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from portfolio_api.cloud_cron import main as cloud_cycle


def _recording_manifest(directory: Path) -> Path:
    """Small fictional bytes test the private-bundle guard, never live source evidence."""
    at = datetime.now(UTC) - timedelta(hours=1)
    issuer = {
        "company_id": "00000000-0000-0000-0000-000000000001",
        "name": "Fixture Inc.",
        "facts_name": "FIXTURE INC.",
        "cik": "0000000001",
        "ticker": "FIX",
        "venue": "NYSE",
        "currency": "USD",
    }
    payloads = {
        "submissions.json": (
            {
                "cik": "0000000001",
                "name": "Fixture Inc.",
                "tickers": ["FIX"],
                "exchanges": ["NYSE"],
                "filings": {"files": []},
            },
            "https://data.sec.gov/submissions/CIK0000000001.json",
        ),
        "companyfacts.json": (
            {"cik": 1, "entityName": "FIXTURE INC.", "facts": {}},
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json",
        ),
    }
    records = []
    for filename, (payload, url) in payloads.items():
        raw = json.dumps(payload).encode()
        (directory / filename).write_bytes(raw)
        records.append(
            {
                "file": filename,
                "source_url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "captured_at": at.isoformat(),
                "capture_timestamp_basis": "fictional guard fixture",
                "bytes": len(raw),
            }
        )
    path = directory / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "version": "sec-real-recording-v1",
                "scope": "Fictional loader test",
                "issuer": issuer,
                "records": records,
                "request_count": 2,
                "captured_at": at.isoformat(),
                "production_writes": 0,
                "expected": {},
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "fault", ["hash", "path", "future", "issuer", "venue", "extra_url", "missing_history"]
)
def test_private_sec_recording_fails_closed(tmp_path: Path, fault: str) -> None:
    path = _recording_manifest(tmp_path)
    data = json.loads(path.read_bytes())
    if fault == "hash":
        data["records"][0]["sha256"] = "0" * 64
    elif fault == "path":
        data["records"][0]["file"] = "../submissions.json"
    elif fault == "future":
        data["captured_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    elif fault == "issuer":
        data["issuer"]["cik"] = "0000000002"
    elif fault == "venue":
        data["issuer"]["venue"] = "NASDAQ"
    elif fault == "extra_url":
        data["records"][0]["source_url"] = "https://untrusted.invalid/submissions.json"
    else:
        source = json.loads((tmp_path / "submissions.json").read_bytes())
        source["filings"]["files"] = [{"name": "CIK0000000001-submissions-001.json"}]
        raw = json.dumps(source).encode()
        (tmp_path / "submissions.json").write_bytes(raw)
        data["records"][0].update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        SecRecording(path)


def test_private_sec_recording_reads_only_exact_hash_bound_sources(tmp_path: Path) -> None:
    recording = SecRecording(_recording_manifest(tmp_path))
    assert len(recording.payloads) == 2
    assert recording.manifest.issuer.name == "Fixture Inc."
    assert recording.metadata()["provider_fixture"] == "recorded-real-sec-v1"


@pytest.mark.integration
@pytest.mark.source_data
def test_real_sec_recording_manual_scheduled_api_reconciliation(postgres_engine: Engine) -> None:
    configured = os.environ.get("BROWSER_SEC_RECORDING_MANIFEST")
    if not configured:
        pytest.skip("Opt-in private official SEC recording is not configured")
    recording = SecRecording(Path(configured))
    settings = fixture_settings()
    metadata = prepare_real_sec_data(postgres_engine, recording)
    refresh = RefreshRehearsal(postgres_engine, settings, metadata, recording=recording)
    app = fixture_application(postgres_engine, refresh.settings, metadata, refresh=refresh)
    with refresh.running(), TestClient(app) as client:
        baseline = refresh.protected_state()
        for name in ("SEC_FUNDAMENTALS", "SEC_FILINGS"):
            response = client.post(
                "/v1/operations/job-requests",
                json={
                    "job_name": name,
                    "scope_kind": "COMPANY",
                    "company_id": metadata["company_id"],
                },
            )
            assert response.status_code == 202, response.text
            job_id = response.json()["id"]
            client.post("/__test/refresh-control", json={"paused": False})
            for _ in range(300):
                receipt = client.get(f"/v1/operations/job-requests/{job_id}").json()
                if receipt["status"] not in {"QUEUED", "RUNNING"}:
                    break
                Event().wait(0.1)
            # Preserve the real provider coverage/quality warnings in both domains.
            assert receipt["status"] == "PARTIAL", (receipt, refresh.errors)
            if name == "SEC_FUNDAMENTALS":
                assert "UNMAPPED_STANDARD_CONCEPTS" in json.dumps(receipt)
            client.post("/__test/refresh-control", json={"paused": True})
        before = refresh.readback()
        counts = before["counts"]
        assert isinstance(counts, dict)
        assert counts["reported_fundamental_observations"] == 1596
        assert counts["source_documents"] == 310
        assert before["provider_request_count"] == 3
        annual = client.get(
            f"/v1/companies/{metadata['company_id']}/financial-statements?period_type=ANNUAL&period_limit=10"
        ).json()
        assert len(annual["periods"]) == 10
        revenue = next(
            row
            for row in annual["rows"]
            if row["metric"] == "REVENUE" and row["source_kind"] == "REPORTED_ACTUAL"
        )
        for end, value in [
            ("2025-12-31", "3134459000"),
            ("2024-12-31", "2856128000"),
            ("2023-12-31", "2528920000"),
        ]:
            cell = next(cell for cell in revenue["cells"] if cell["period_end"] == end)
            assert cell["status"] == "AVAILABLE"
            assert Decimal(cell["value"]) == Decimal(value)
            period = next(period for period in annual["periods"] if period["period_end"] == end)
            assert period["fiscal_year"] == int(end[:4])
        quarterly = client.get(
            f"/v1/companies/{metadata['company_id']}/financial-statements?period_type=QUARTERLY&period_limit=10"
        ).json()
        quarter_revenue = next(
            row
            for row in quarterly["rows"]
            if row["metric"] == "REVENUE" and row["source_kind"] == "REPORTED_ACTUAL"
        )
        quarter = next(
            cell for cell in quarter_revenue["cells"] if cell["period_end"] == "2026-09-30"
        )
        assert Decimal(quarter["value"]) == Decimal("892000000")
        with postgres_engine.connect() as connection:
            from sqlalchemy import text

            dates: list[datetime] = list(
                connection.execute(text("SELECT DISTINCT retrieved_at FROM external_raw_payloads"))
                .scalars()
                .all()
            )
            assert set(dates) == set(recording.captured.values())
        scheduled = client.post(
            "/__test/refresh-control", json={"paused": True, "scheduled_days_later": 3}
        ).json()
        assert scheduled["counts"]["reported_fundamental_observations"] == 1596
        assert scheduled["counts"]["source_documents"] == 310
        assert scheduled["protected_state_sha256"] == baseline
        repeated = client.post(
            "/__test/refresh-control", json={"paused": True, "scheduled_days_later": 3}
        ).json()
        assert repeated["provider_request_count"] == scheduled["provider_request_count"]
        assert repeated["counts"] == scheduled["counts"]
        assert not repeated["worker_errors"]
        assert (
            client.post("/__test/refresh-control", json={"response": "updated"}).status_code == 422
        )
        with pytest.raises(AssertionError):
            refresh.download("https://data.sec.gov/submissions/CIK0000000002.json", "unused")


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
