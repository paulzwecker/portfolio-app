"""Read-only market diagnostics expose the worker's actual retry budget and history."""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_recovery import cycle_clock as cycle_clock
from test_cloud_market_recovery import refresh
from test_cloud_market_recovery import retry_provider as retry_provider
from test_cloud_market_refresh import market_scope as market_scope
from test_cloud_market_refresh import table_counts

from portfolio_api.domain import queries
from portfolio_api.domain.models import ExternalIngestionRun
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


def read_status(engine: Engine) -> dict[str, Any]:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=engine),
        TestClient(
            create_app(Settings(_env_file=None, database_url=None, api_access_token=None))
        ) as client,
    ):
        response = client.get("/v1/recurring-operations/status")
        assert response.status_code == 200
        return dict(response.json()["market_data"])


@pytest.mark.integration
def test_read_only_diagnostics_follow_cooldown_and_preserve_recovered_attempts(
    postgres_engine: Engine,
    market_scope: object,
    cycle_clock: list[datetime],
    retry_provider: tuple[list[str], dict[str, bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("portfolio_api.domain.queries.now", lambda: cycle_clock[0])
    calls, state = retry_provider
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "FAILED"
    counts = table_counts(postgres_engine)
    first = read_status(postgres_engine)
    assert first["state"] == "PARTIAL"
    assert {run["domain"] for run in first["runs"]} == {"MARKET_DATA", "FX", "CORPORATE_ACTIONS"}
    fx = next(run for run in first["runs"] if run["domain"] == "FX")
    assert fx["retry_state"] == "COOLDOWN"
    assert fx["attempt_count"] == 1 and fx["max_attempts"] == 3
    assert fx["request_scope"]["required_fx_pairs"] == [["USD", "EUR"]]
    assert len(fx["request_scope"]["crosswalk_sha256"]) == 64
    assert fx["attempts"][0]["retryable"] is True
    assert fx["report"]["domain_report"]["provider_fetch_failures"]
    cycle_clock[0] += timedelta(minutes=15)
    eligible = read_status(postgres_engine)
    eligible_fx = next(run for run in eligible["runs"] if run["domain"] == "FX")
    assert eligible_fx["retry_state"] == "ELIGIBLE"
    assert eligible_fx["retry_eligible_at"] == fx["retry_eligible_at"]
    assert table_counts(postgres_engine) == counts
    assert len(calls) == 2
    state["fx_down"] = False
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "COMPLETE"
    recovered = read_status(postgres_engine)
    fx = next(run for run in recovered["runs"] if run["domain"] == "FX")
    assert recovered["state"] == "AVAILABLE"
    assert fx["retry_state"] == "NONE" and fx["retry_eligible_at"] is None
    assert [attempt["status"] for attempt in fx["attempts"]] == ["FAILED", "SUCCEEDED"]
    assert fx["last_successful_at"] is not None


@pytest.mark.integration
@pytest.mark.parametrize("problem", ["exhausted", "identity", "previous_day", "running"])
def test_diagnostics_never_offer_an_unsupported_automatic_retry(
    postgres_engine: Engine,
    market_scope: object,
    cycle_clock: list[datetime],
    retry_provider: tuple[list[str], dict[str, bool]],
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    monkeypatch.setattr("portfolio_api.domain.queries.now", lambda: cycle_clock[0])
    _calls, state = retry_provider
    if problem == "identity":
        state.update(fx_down=False, wrong_market_identity=True)
    refresh(postgres_engine, cycle_clock[0])
    if problem == "exhausted":
        for _ in range(2):
            cycle_clock[0] += timedelta(minutes=15)
            refresh(postgres_engine, cycle_clock[0])
    elif problem == "previous_day":
        cycle_clock[0] += timedelta(days=1)
    elif problem == "running":
        with Session(postgres_engine) as session, session.begin():
            running = session.scalars(
                select(ExternalIngestionRun).where(ExternalIngestionRun.domain == "FX")
            ).one()
            running.status = "RUNNING"
            running.finished_at = None
    with Session(postgres_engine) as session:
        report = queries.market_refresh_status(session)
    run = next(
        item
        for item in report.runs
        if item.domain == ("MARKET_DATA" if problem == "identity" else "FX")
    )
    assert (
        run.retry_state
        == {
            "exhausted": "EXHAUSTED",
            "identity": "REVIEW_REQUIRED",
            "previous_day": "REVIEW_REQUIRED",
            "running": "RUNNING",
        }[problem]
    )
    assert run.retry_eligible_at is None
