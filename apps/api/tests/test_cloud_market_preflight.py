"""Preflight failures remain visible without changing portfolio or provider facts."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import market_scope as market_scope
from test_cloud_market_refresh import source_payload, table_counts

from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    install_database_write_target_guard,
)
from portfolio_api.domain import queries
from portfolio_api.domain.models import ExternalIngestionAttempt, ExternalIngestionRun
from portfolio_api.external_ingestion import (
    record_cloud_market_preflight,
    run_scheduled,
    status_report,
)
from portfolio_api.main import create_app
from portfolio_api.market_data_startup import _latest_run, run_startup_refresh
from portfolio_api.settings import Settings
from portfolio_api.yahoo_finance import YahooFinanceProvider, YahooListingCrosswalk


def test_preflight_diagnostic_cannot_be_replayed_as_a_provider_scope() -> None:
    with (
        patch("portfolio_api.external_ingestion._claim_run") as claim,
        pytest.raises(ValueError, match="fresh cloud scope check"),
    ):
        run_scheduled(
            cast(Session, None),
            Settings(_env_file=None, database_url=None),
            replay_scope={"scope": "cloud_market_preflight"},
        )
    claim.assert_not_called()


@pytest.mark.integration
def test_preflight_diagnostics_cannot_bypass_an_unverified_write_target(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_scope.write_text("invalid source", encoding="utf-8")
    settings = Settings(_env_file=None, database_url=None, database_target_environment=None)
    before = table_counts(postgres_engine)
    install_database_write_target_guard(
        postgres_engine,
        settings,
        operation="market_data_startup_ingestion",
        operation_kind="ingestion",
    )
    monkeypatch.setattr(
        "portfolio_api.market_data_startup.create_database_engine",
        lambda *_a, **_k: postgres_engine,
    )
    provider = Mock(side_effect=AssertionError("An unverified target must not fetch facts"))
    monkeypatch.setattr("portfolio_api.external_ingestion.YahooFinanceProvider", provider)
    with pytest.raises(DatabaseWriteTargetError, match="target_environment_required"):
        run_startup_refresh(settings, cloud_incremental=True, allow_local_proxy_bypass=False)
    provider.assert_not_called()
    assert table_counts(postgres_engine) == before


@pytest.mark.integration
@pytest.mark.parametrize(
    ("problem", "failure_code"),
    [
        ("mapping", "MARKET_SCOPE_REVIEW_REQUIRED"),
        ("budget", "MARKET_SCOPE_BUDGET_EXCEEDED"),
        ("invalid_source", "MARKET_SOURCE_INVALID"),
    ],
)
def test_cloud_preflight_records_only_operational_diagnostics(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
    failure_code: str,
) -> None:
    if problem == "budget":
        monkeypatch.setattr("portfolio_api.market_data_startup.CLOUD_MAX_SUBJECTS", 1)
    elif problem == "mapping":
        payload = json.loads(market_scope.read_text(encoding="utf-8"))
        payload["mappings"] = []
        market_scope.write_text(json.dumps(payload), encoding="utf-8")
    else:
        market_scope.write_text("invalid source", encoding="utf-8")
    provider = Mock(side_effect=AssertionError("Preflight must not fetch provider facts"))
    monkeypatch.setattr("portfolio_api.external_ingestion.YahooFinanceProvider", provider)
    monkeypatch.setattr(
        "portfolio_api.market_data_startup.create_database_engine",
        lambda *_a, **_k: postgres_engine,
    )
    before = table_counts(postgres_engine)
    result = run_startup_refresh(
        Settings(_env_file=None, database_url=None, database_target_environment="development"),
        cloud_incremental=True,
        allow_local_proxy_bypass=False,
    )
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == failure_code
    assert result["proxy_bypass_applied"] is False
    provider.assert_not_called()
    expected = {
        **before,
        "external_ingestion_runs": 1,
        "external_ingestion_attempts": 1,
    }
    assert table_counts(postgres_engine) == expected
    with Session(postgres_engine) as session:
        run = session.scalars(select(ExternalIngestionRun)).one()
        attempt = session.scalars(select(ExternalIngestionAttempt)).one()
        assert run.status == attempt.status == "BLOCKED"
        assert run.failure_code == attempt.failure_code == failure_code
        assert run.request_scope["scope"] == "cloud_market_preflight"
        assert run.report["phase"] == "PREFLIGHT"
        assert run.last_successful_at is None
        assert attempt.retryable is False
        assert run.attempt_count == attempt.attempt_number == 1
        if problem == "mapping":
            preview = run.report["preview"]
            assert isinstance(preview, dict) and preview["status"] == "BLOCKED"
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(
            create_app(Settings(_env_file=None, database_url=None, api_access_token=None))
        ) as client,
    ):
        response = client.get("/v1/recurring-operations/status")
        assert response.status_code == 200
        market = response.json()["market_data"]
        assert market["state"] == "UNAVAILABLE"
        assert market["last_successful_update"] is None
        assert market["market_run_id"] == str(run.id)
        assert failure_code in market["message"]
    assert table_counts(postgres_engine) == expected


@pytest.mark.integration
def test_repeated_blocks_preserve_previous_market_and_fx_success_in_operations(
    postgres_engine: Engine,
) -> None:
    current = datetime.now(UTC)
    previous_success = current - timedelta(hours=1)
    with Session(postgres_engine) as session, session.begin():
        for domain, at in (("MARKET_DATA", previous_success), ("FX", current - timedelta(hours=2))):
            run = ExternalIngestionRun(
                provider_id="YAHOO_FINANCE",
                domain=domain,
                idempotency_key=f"synthetic-history:{domain}",
                status="FAILED" if domain == "MARKET_DATA" else "COMPLETE",
                requested_at=at,
                created_at=at,
                started_at=at,
                finished_at=at,
                last_successful_at=at,
                attempt_count=2,
                request_scope={},
                report={},
            )
            session.add(run)
            session.flush()
            if domain == "FX":
                fx_run_id = run.id
    report: dict[str, object] = {
        "status": "BLOCKED",
        "phase": "PREFLIGHT",
        "failure_code": "MARKET_SCOPE_REVIEW_REQUIRED",
    }
    with Session(postgres_engine) as session:
        for seconds in range(45, 0, -1):
            result = record_cloud_market_preflight(
                session, report, current - timedelta(seconds=seconds)
            )
        last_run_id = result["run_id"]
        counts = table_counts(postgres_engine)
        repeat = record_cloud_market_preflight(session, report, current - timedelta(seconds=1))
        assert repeat["idempotent_reuse"] is True
        assert repeat["run_id"] == last_run_id
        assert counts == table_counts(postgres_engine)
        domain = next(
            item for item in status_report(session)["domains"] if item["domain"] == "MARKET_DATA"
        )
        assert domain["latest_run"]["status"] == "BLOCKED"
        assert datetime.fromisoformat(domain["last_successful_at"]) == previous_success
        assert domain["freshness"] == "FRESH"
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(
            create_app(Settings(_env_file=None, database_url=None, api_access_token=None))
        ) as client,
    ):
        response = client.get("/v1/recurring-operations/status")
        assert response.status_code == 200
        market = response.json()["market_data"]
        assert market["state"] == "PARTIAL"
        assert market["market_run_id"] == last_run_id
        assert market["fx_run_id"] == str(fx_run_id)
        assert datetime.fromisoformat(market["last_successful_update"]) == previous_success
        assert "MARKET_SCOPE_REVIEW_REQUIRED" in market["message"]
    assert counts == table_counts(postgres_engine)


@pytest.mark.integration
def test_scope_recovery_clears_active_block_without_refetching_or_advancing_freshness(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def transport(url: str) -> bytes:
        symbol = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        calls.append(symbol)
        return source_payload(symbol, datetime.now(UTC))

    def provider(crosswalk: YahooListingCrosswalk) -> YahooFinanceProvider:
        return YahooFinanceProvider(crosswalk, transport=transport, retries=0)

    monkeypatch.setattr("portfolio_api.external_ingestion.YahooFinanceProvider", provider)
    monkeypatch.setattr(
        "portfolio_api.market_data_startup.create_database_engine",
        lambda *_a, **_k: postgres_engine,
    )
    settings = Settings(
        _env_file=None, database_url=None, database_target_environment="development"
    )
    arguments = {"cloud_incremental": True, "allow_local_proxy_bypass": False}
    assert run_startup_refresh(settings, **arguments)["status"] == "COMPLETE"
    assert len(calls) == 2
    with Session(postgres_engine) as session:
        original = queries.market_refresh_status(session)
        assert original.state == "AVAILABLE"
    mapping = market_scope.read_bytes()
    market_scope.write_text("invalid source", encoding="utf-8")
    assert run_startup_refresh(settings, **arguments)["status"] == "BLOCKED"
    with Session(postgres_engine) as session:
        assert queries.market_refresh_status(session).state == "PARTIAL"
        counts = table_counts(postgres_engine)
    market_scope.write_bytes(mapping)
    assert run_startup_refresh(settings, **arguments)["status"] == "COMPLETE"
    assert len(calls) == 2
    assert counts == table_counts(postgres_engine)
    with Session(postgres_engine) as session:
        current = queries.market_refresh_status(session)
        assert current.state == "AVAILABLE"
        assert current.last_successful_update == original.last_successful_update
        assert current.market_run_id == original.market_run_id
        assert current.fx_run_id == original.fx_run_id
        assert current.message is None
        blocked = session.scalars(
            select(ExternalIngestionRun).where(ExternalIngestionRun.status == "BLOCKED")
        ).one()
        assert blocked.report["preflight_resolved_at"]
        assert blocked.failure_code == "MARKET_SOURCE_INVALID"
        attempt = session.scalars(
            select(ExternalIngestionAttempt).where(ExternalIngestionAttempt.run_id == blocked.id)
        ).one()
        assert attempt.status == "BLOCKED" and attempt.failure_code == "MARKET_SOURCE_INVALID"
        market = next(
            item for item in status_report(session)["domains"] if item["domain"] == "MARKET_DATA"
        )
        assert market["latest_run"]["run_id"] == str(original.market_run_id)


@pytest.mark.integration
def test_latest_status_follows_attempt_time_after_retrying_an_older_run(
    postgres_engine: Engine,
) -> None:
    current = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        for name, hours, status in (("retried", 3, "FAILED"), ("other_scope", 1, "COMPLETE")):
            created = current - timedelta(hours=hours)
            run = ExternalIngestionRun(
                provider_id="YAHOO_FINANCE",
                domain="MARKET_DATA",
                idempotency_key=f"synthetic-attempt-order:{name}",
                status=status,
                requested_at=created,
                created_at=created,
                started_at=created,
                last_attempt_started_at=current if name == "retried" else created,
                finished_at=current if name == "retried" else created,
                last_successful_at=created,
                attempt_count=2,
                request_scope={},
                report={},
            )
            session.add(run)
            session.flush()
            if name == "retried":
                retried_id = run.id
    with Session(postgres_engine) as session:
        market = queries.market_refresh_status(session)
        assert market.state == "PARTIAL"
        assert market.market_run_id == retried_id
        assert market.last_attempt_at == current
        latest = _latest_run(session, "MARKET_DATA")
        assert latest is not None and latest.id == retried_id
        external = next(
            item for item in status_report(session)["domains"] if item["domain"] == "MARKET_DATA"
        )
        assert external["latest_run"]["run_id"] == str(retried_id)
