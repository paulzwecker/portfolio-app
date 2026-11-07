"""Bounded same-day retry using immutable source scopes and persisted attempts."""

import json
from datetime import UTC, datetime, time, timedelta, tzinfo
from typing import Self
from urllib.error import URLError
from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import market_scope as market_scope
from test_cloud_market_refresh import source_payload

from portfolio_api.domain.models import ExternalIngestionAttempt, ExternalIngestionRun
from portfolio_api.market_data_startup import (
    ADVISORY_LOCK_KEY,
    ADVISORY_LOCK_NAMESPACE,
    run_cloud_incremental_refresh,
    run_startup_refresh,
)
from portfolio_api.settings import Settings
from portfolio_api.yahoo_finance import YahooFinanceProvider, YahooListingCrosswalk


@pytest.fixture
def cycle_clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    at = [datetime.combine(datetime.now(UTC).date() - timedelta(days=1), time(12), UTC)]

    class ClockDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(at[0].timestamp(), tz)

    monkeypatch.setattr("portfolio_api.external_ingestion.datetime", ClockDatetime)
    return at


@pytest.fixture
def retry_provider(
    monkeypatch: pytest.MonkeyPatch,
    cycle_clock: list[datetime],
) -> tuple[list[str], dict[str, bool]]:
    calls: list[str] = []
    state = {"fx_down": True, "wrong_market_identity": False}

    def transport(url: str) -> bytes:
        symbol = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        calls.append(symbol)
        if state["fx_down"] and symbol == "EUR=X":
            raise URLError("Synthetic retryable outage")
        payload = source_payload(symbol, cycle_clock[0])
        if state["wrong_market_identity"] and symbol == "SYNTH":
            data = json.loads(payload)
            data["chart"]["result"][0]["meta"]["symbol"] = "OTHER"
            return json.dumps(data).encode()
        return payload

    def provider(crosswalk: YahooListingCrosswalk) -> YahooFinanceProvider:
        return YahooFinanceProvider(crosswalk, transport=transport, retries=0)

    monkeypatch.setattr("portfolio_api.external_ingestion.YahooFinanceProvider", provider)
    return calls, state


def refresh(engine: Engine, at: datetime) -> dict[str, object]:
    with Session(engine) as session:
        return run_cloud_incremental_refresh(
            session,
            Settings(_env_file=None, database_url=None, database_target_environment="development"),
            at,
        )


@pytest.mark.integration
def test_same_day_retry_waits_for_cooldown_then_only_refetches_failed_fx(
    postgres_engine: Engine,
    market_scope: object,
    cycle_clock: list[datetime],
    retry_provider: tuple[list[str], dict[str, bool]],
) -> None:
    calls, state = retry_provider
    first = refresh(postgres_engine, cycle_clock[0])
    assert first["status"] == "FAILED"
    assert len(calls) == 2
    cycle_clock[0] += timedelta(minutes=14, seconds=59)
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "FAILED"
    assert len(calls) == 2
    state["fx_down"] = False
    cycle_clock[0] += timedelta(seconds=1)
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "COMPLETE"
    assert calls.count("SYNTH") == 1
    assert calls.count("EUR=X") == 2
    with Session(postgres_engine) as session:
        runs = session.scalars(select(ExternalIngestionRun)).all()
        assert len(runs) == 3
        assert {run.domain: run.attempt_count for run in runs} == {
            "MARKET_DATA": 1,
            "CORPORATE_ACTIONS": 1,
            "FX": 2,
        }
        fx = next(run for run in runs if run.domain == "FX")
        attempts = session.scalars(
            select(ExternalIngestionAttempt)
            .where(
                ExternalIngestionAttempt.run_id == fx.id,
            )
            .order_by(ExternalIngestionAttempt.attempt_number)
        ).all()
        assert [attempt.attempt_number for attempt in attempts] == [1, 2]
        assert [attempt.status for attempt in attempts] == ["FAILED", "SUCCEEDED"]
        assert fx.request_scope["required_fx_pairs"] == [["USD", "EUR"]]
    cycle_clock[0] += timedelta(hours=1)
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "COMPLETE"
    assert len(calls) == 3


@pytest.mark.integration
def test_persistent_outage_exhausts_three_domain_attempts_and_remains_idempotent(
    postgres_engine: Engine,
    market_scope: object,
    cycle_clock: list[datetime],
    retry_provider: tuple[list[str], dict[str, bool]],
) -> None:
    calls, _state = retry_provider
    for _ in range(5):
        assert refresh(postgres_engine, cycle_clock[0])["status"] == "FAILED"
        cycle_clock[0] += timedelta(minutes=15)
    assert calls.count("SYNTH") == 1
    assert calls.count("EUR=X") == 3
    with Session(postgres_engine) as session:
        fx = session.scalars(
            select(ExternalIngestionRun).where(
                ExternalIngestionRun.domain == "FX",
            )
        ).one()
        assert fx.attempt_count == fx.max_attempts == 3
        attempts = session.scalars(
            select(ExternalIngestionAttempt).where(
                ExternalIngestionAttempt.run_id == fx.id,
            )
        ).all()
        assert sorted(attempt.attempt_number for attempt in attempts) == [1, 2, 3]


@pytest.mark.integration
def test_nonretryable_identity_failure_is_not_automatically_replayed(
    postgres_engine: Engine,
    market_scope: object,
    cycle_clock: list[datetime],
    retry_provider: tuple[list[str], dict[str, bool]],
) -> None:
    calls, state = retry_provider
    state.update(fx_down=False, wrong_market_identity=True)
    first = refresh(postgres_engine, cycle_clock[0])
    cycle_clock[0] += timedelta(hours=1)
    assert refresh(postgres_engine, cycle_clock[0])["status"] == first["status"]
    assert len(calls) == 2
    with Session(postgres_engine) as session:
        attempts = session.scalars(select(ExternalIngestionAttempt)).all()
        assert all(attempt.attempt_number == 1 for attempt in attempts)


@pytest.mark.integration
def test_overlapping_worker_cannot_consume_a_retry_attempt(
    postgres_engine: Engine,
    market_scope: object,
    cycle_clock: list[datetime],
    retry_provider: tuple[list[str], dict[str, bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, _state = retry_provider
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "FAILED"
    cycle_clock[0] += timedelta(minutes=15)
    monkeypatch.setattr(
        "portfolio_api.market_data_startup.create_database_engine",
        lambda *_a, **_k: postgres_engine,
    )
    with postgres_engine.connect() as active:
        assert active.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :key)"),
            {"namespace": ADVISORY_LOCK_NAMESPACE, "key": ADVISORY_LOCK_KEY},
        ).scalar_one()
        active.commit()
        try:
            result = run_startup_refresh(
                Settings(
                    _env_file=None, database_url=None, database_target_environment="development"
                ),
                cloud_incremental=True,
                allow_local_proxy_bypass=False,
            )
            assert result["status"] == "SKIPPED"
        finally:
            active.execute(
                text("SELECT pg_advisory_unlock(:namespace, :key)"),
                {"namespace": ADVISORY_LOCK_NAMESPACE, "key": ADVISORY_LOCK_KEY},
            )
            active.commit()
    assert len(calls) == 2
    with Session(postgres_engine) as session:
        fx = session.scalars(
            select(ExternalIngestionRun).where(
                ExternalIngestionRun.domain == "FX",
            )
        ).one()
        assert fx.attempt_count == 1


@pytest.mark.integration
def test_interrupted_retry_claim_recovers_with_preserved_attempt_history(
    postgres_engine: Engine,
    market_scope: object,
    cycle_clock: list[datetime],
    retry_provider: tuple[list[str], dict[str, bool]],
) -> None:
    calls, state = retry_provider
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "FAILED"
    with Session(postgres_engine) as session, session.begin():
        fx = session.scalars(
            select(ExternalIngestionRun).where(
                ExternalIngestionRun.domain == "FX",
            )
        ).one()
        fx.status = "RUNNING"
        fx.last_attempt_started_at = cycle_clock[0] + timedelta(minutes=15)
        fx.finished_at = None
    cycle_clock[0] += timedelta(hours=5)
    assert refresh(postgres_engine, cycle_clock[0])["status"] == "FAILED"
    assert len(calls) == 2
    cycle_clock[0] += timedelta(minutes=15)
    state["fx_down"] = False
    recovered = refresh(postgres_engine, cycle_clock[0])
    with Session(postgres_engine) as session:
        states = [
            (run.domain, run.status, run.attempt_count, run.failure_code)
            for run in session.scalars(select(ExternalIngestionRun))
        ]
    assert recovered["status"] == "COMPLETE", states
    assert len(calls) == 3
    with Session(postgres_engine) as session:
        fx = session.scalars(
            select(ExternalIngestionRun).where(
                ExternalIngestionRun.domain == "FX",
            )
        ).one()
        assert fx.attempt_count == 2
        attempts = session.scalars(
            select(ExternalIngestionAttempt).where(
                ExternalIngestionAttempt.run_id == fx.id,
            )
        ).all()
        assert sorted(attempt.attempt_number for attempt in attempts) == [1, 2]
