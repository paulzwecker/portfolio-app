from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import ExternalIngestionAttempt, ExternalIngestionRun
from portfolio_api.external_data import ExternalDataDomain, ProviderTransportError
from portfolio_api.external_ingestion import (
    DAILY_DOMAINS,
    MAX_RETRY_DELAY_SECONDS,
    RunClaim,
    _domain_status_for_yahoo,
    _execute_cycle,
    _selected_domains,
    active_company_states,
    classify_transport_error,
    freshness_status,
    parse_fx_pair,
    retry_delay_seconds,
    status_report,
)


def test_retry_policy_is_bounded_and_honors_provider_retry_after() -> None:
    assert retry_delay_seconds(1) == 1
    assert retry_delay_seconds(2) == 2
    assert retry_delay_seconds(3, 7) == 7
    assert retry_delay_seconds(3, 300) == MAX_RETRY_DELAY_SECONDS
    with pytest.raises(ValueError, match="positive"):
        retry_delay_seconds(0)


def test_transport_failure_record_is_sanitized_and_retryable() -> None:
    error = ProviderTransportError(
        "fmp_estimates",
        "RATE_LIMITED",
        "HTTP 429; request details omitted",
        retryable=True,
        retry_after_seconds=5,
    )
    code, message, retryable, retry_after = classify_transport_error(error)
    assert (code, message, retryable, retry_after) == (
        "RATE_LIMITED",
        "HTTP 429; request details omitted",
        True,
        5,
    )
    assert "apikey" not in message.lower()


def test_freshness_tracks_success_age_and_missing_history() -> None:
    current = datetime(2026, 10, 6, 12, tzinfo=UTC)
    fresh, age = freshness_status(
        current - timedelta(hours=24),
        now_at=current,
        max_age=timedelta(hours=72),
        has_run=True,
    )
    assert fresh == "FRESH"
    assert age == 24 * 3600
    stale, _ = freshness_status(
        current - timedelta(hours=80),
        now_at=current,
        max_age=timedelta(hours=72),
        has_run=True,
    )
    assert stale == "STALE"
    assert freshness_status(None, now_at=current, max_age=timedelta(hours=72), has_run=False) == (
        "UNKNOWN",
        None,
    )
    assert freshness_status(None, now_at=current, max_age=timedelta(hours=72), has_run=True) == (
        "STALE",
        None,
    )


def test_daily_worker_covers_each_prioritized_provider_domain() -> None:
    assert [domain.value for domain in DAILY_DOMAINS] == [
        "REPORTED_FUNDAMENTALS",
        "SOURCE_DOCUMENTS",
        "CONSENSUS_ESTIMATES",
        "FX",
        "MARKET_DATA",
        "CORPORATE_ACTIONS",
    ]


def test_company_ingestion_scope_uses_explicit_lifecycle_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio_id = uuid4()
    watchlist_id = uuid4()
    session = Mock()
    session.execute.return_value.all.return_value = [
        (portfolio_id, "PORTFOLIO"),
        (watchlist_id, "WATCHLIST"),
    ]
    monkeypatch.setattr(
        "portfolio_api.external_ingestion.active_market_listings",
        lambda _session: pytest.fail("Holdings must not assign company lifecycle."),
    )

    assert active_company_states(cast(Session, session)) == {
        portfolio_id: "PORTFOLIO",
        watchlist_id: "WATCHLIST",
    }


def test_yahoo_retryable_subject_failure_is_persisted_on_domain_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = ExternalDataDomain.MARKET_DATA
    outcome = _domain_status_for_yahoo(
        domain,
        {
            "selected_listing_count": 2,
            "verified_listing_mapping_count": 2,
            "market_data_batches": [{"accepted_subjects": 1, "daily_price_rows": 5}],
            "provider_fetch_failures": [{"code": "RATE_LIMITED", "retryable": True}],
        },
        {"persistence": {"inserted_totals": {}}},
    )
    assert outcome.status == "PARTIAL"
    assert outcome.retryable is True

    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        attempt_count=0,
        last_attempt_started_at=None,
        status="RUNNING",
        finished_at=None,
        failure_code=None,
        failure_message=None,
        report={},
        last_successful_at=None,
    )

    class MemorySession:
        attempts: list[ExternalIngestionAttempt] = []

        def get(self, model: object, _identifier: object) -> object:
            assert model is ExternalIngestionRun
            return run

        def add(self, value: ExternalIngestionAttempt) -> None:
            self.attempts.append(value)

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

    session = MemorySession()
    claim = RunClaim(run_id, "yahoo_chart", domain, True, "RUNNING", {})
    _execute_cycle(cast(Session, session), [claim], lambda: {domain: outcome})

    assert run.status == "PARTIAL"
    assert len(session.attempts) == 1
    assert session.attempts[0].retryable is True
    assert session.attempts[0].failure_code == "PARTIAL_COVERAGE"


def test_targeted_yahoo_domain_scope_keeps_fx_backfill_separate() -> None:
    assert _selected_domains([ExternalDataDomain.FX]) == {ExternalDataDomain.FX}
    assert _selected_domains([ExternalDataDomain.MARKET_DATA]) == {
        ExternalDataDomain.MARKET_DATA,
        ExternalDataDomain.CORPORATE_ACTIONS,
    }
    assert parse_fx_pair("twd/eur") == ("TWD", "EUR")
    with pytest.raises(ValueError, match="reviewed Yahoo FX mapping"):
        parse_fx_pair("ABC/XYZ")


def test_operational_run_status_and_attempt_are_durable_and_append_only(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    run_id = uuid4()
    attempt_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        run = ExternalIngestionRun(
            id=run_id,
            provider_id="fmp_estimates",
            domain="CONSENSUS_ESTIMATES",
            idempotency_key=f"fixture:{run_id}",
            replay_of_run_id=None,
            status="PARTIAL",
            requested_at=now,
            created_at=now,
            started_at=now,
            finished_at=now,
            last_successful_at=now,
            attempt_count=2,
            max_attempts=3,
            failure_code="PARTIAL_COVERAGE",
            failure_message="One active company has no mapping.",
            request_scope={"company_ids": []},
            report={"status": "PARTIAL", "normalized_estimate_count": 5},
        )
        session.add(run)
        session.add(
            ExternalIngestionAttempt(
                id=attempt_id,
                run_id=run_id,
                attempt_number=2,
                status="PARTIAL",
                started_at=now - timedelta(seconds=2),
                finished_at=now,
                retryable=False,
                failure_code="PARTIAL_COVERAGE",
                failure_message="One active company has no mapping.",
                report={"normalized_estimate_count": 5},
            )
        )

    with Session(postgres_engine) as session:
        report = status_report(session, now_at=now + timedelta(hours=1))
        consensus = next(
            item for item in report["domains"] if item["domain"] == "CONSENSUS_ESTIMATES"
        )
        assert consensus["latest_run"]["status"] == "PARTIAL"
        assert consensus["freshness"] == "FRESH"
        assert report["recent_failures"][0]["failure_code"] == "PARTIAL_COVERAGE"

    with Session(postgres_engine) as session:
        attempt = session.get(ExternalIngestionAttempt, attempt_id)
        assert attempt is not None
        attempt.failure_code = "EDITED"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
