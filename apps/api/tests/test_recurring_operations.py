from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    ExternalIngestionAttempt,
    ExternalIngestionRun,
    RecurringOperationRun,
)
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import PROVIDERS
from portfolio_api.recurring_operations import (
    FAILURE_BACKOFF_INITIAL,
    LOCK_KEY,
    LOCK_NAMESPACE,
    SEC_GOOGLE_API_HOSTS,
    _classified_status,
    _run_fmp_consensus,
    _run_one_job,
    _run_sec_domain,
    _run_sheets_discovery,
    configure_external_operations_no_proxy,
    main,
    operation_due,
    run_recurring_cycle,
)
from portfolio_api.settings import Settings


def test_recurring_worker_adds_sec_google_exclusions_only_for_known_local_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "portfolio_api.networking.urllib.request.getproxies",
        lambda: {"https": "http://127.0.0.1:9"},
    )
    environment = {"NO_PROXY": "localhost,internal.example"}
    assert configure_external_operations_no_proxy(environment)
    assert all(host in environment["NO_PROXY"] for host in SEC_GOOGLE_API_HOSTS)
    assert environment["no_proxy"] == environment["NO_PROXY"]


def test_recurring_worker_preserves_other_proxy_configurations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "portfolio_api.networking.urllib.request.getproxies",
        lambda: {"https": "http://proxy.example:8080"},
    )
    environment = {"NO_PROXY": "localhost"}
    assert not configure_external_operations_no_proxy(environment)
    assert environment == {"NO_PROXY": "localhost"}


def test_disabled_worker_stays_alive_until_parent_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StopAfterOneWait:
        def set(self) -> None:
            return None

        def is_set(self) -> bool:
            return False

        def wait(self, _timeout: int) -> bool:
            return True

    monkeypatch.setattr(
        "portfolio_api.recurring_operations.Settings",
        lambda: Settings(_env_file=None, recurring_operations_enabled=False),
    )
    monkeypatch.setattr("portfolio_api.recurring_operations.Event", StopAfterOneWait)
    monkeypatch.setattr("portfolio_api.recurring_operations.signal.signal", lambda *_args: None)
    monkeypatch.setattr(
        "portfolio_api.recurring_operations.configure_external_operations_no_proxy",
        lambda: False,
    )
    assert main(["--interval-seconds", "10"]) == 0


def test_repeated_scheduler_checks_respect_next_attempt(postgres_engine: Engine) -> None:
    now_at = datetime.now(UTC)
    settings = Settings(_env_file=None)
    with Session(postgres_engine) as session:
        run = RecurringOperationRun(
            job_name="RESEARCH_TRIGGER_SCAN",
            status="SUCCEEDED",
            started_at=now_at - timedelta(hours=1),
            finished_at=now_at - timedelta(hours=1),
            next_attempt_at=now_at + timedelta(hours=1),
            result={"created": 1},
        )
        session.add(run)
        session.commit()
        assert not operation_due(session, "RESEARCH_TRIGGER_SCAN", now_at, 3600, settings)
        assert operation_due(
            session,
            "RESEARCH_TRIGGER_SCAN",
            now_at + timedelta(hours=2),
            3600,
            settings,
        )


def test_interrupted_job_is_marked_and_retried_after_backoff(postgres_engine: Engine) -> None:
    now_at = datetime.now(UTC)
    settings = Settings(_env_file=None)
    with Session(postgres_engine) as session:
        run = RecurringOperationRun(
            job_name="SEC_FILINGS",
            status="RUNNING",
            started_at=now_at - timedelta(hours=3),
            result={},
        )
        session.add(run)
        session.commit()
        assert not operation_due(session, "SEC_FILINGS", now_at, 86400, settings)
        session.refresh(run)
        assert run.status == "FAILED"
        assert run.failure_code == "WORKER_INTERRUPTED"
        assert run.next_attempt_at is not None
        assert run.next_attempt_at >= now_at + FAILURE_BACKOFF_INITIAL - timedelta(seconds=2)
        assert not operation_due(
            session,
            "SEC_FILINGS",
            now_at + timedelta(minutes=5),
            86400,
            settings,
        )
        assert operation_due(
            session,
            "SEC_FILINGS",
            now_at + timedelta(minutes=20),
            86400,
            settings,
        )


def test_sec_missing_configuration_is_rechecked_as_soon_as_it_is_fixed(
    postgres_engine: Engine,
) -> None:
    now_at = datetime.now(UTC)
    with Session(postgres_engine) as session:
        session.add(
            RecurringOperationRun(
                job_name="SEC_FUNDAMENTALS",
                status="BLOCKED",
                started_at=now_at - timedelta(minutes=2),
                finished_at=now_at - timedelta(minutes=2),
                next_attempt_at=now_at + timedelta(hours=6),
                failure_code="SEC_USER_AGENT_MISSING",
                result={},
            )
        )
        session.commit()
        assert operation_due(
            session,
            "SEC_FUNDAMENTALS",
            now_at,
            86400,
            Settings(_env_file=None, sec_user_agent="Portfolio Research App contact@example.com"),
        )


def test_partial_provider_outcome_stays_explicit() -> None:
    assert _classified_status({"status": "PARTIAL"}) == "PARTIAL"
    assert _classified_status({"status": "BLOCKED"}) == "BLOCKED"


def test_missing_sec_contact_blocks_without_provider_calls() -> None:
    settings = Settings(_env_file=None, sec_user_agent=None)
    result = _run_sec_domain(
        cast(Engine, None),
        settings,
        ExternalDataDomain.REPORTED_FUNDAMENTALS,
        datetime.now(UTC),
    )
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "SEC_USER_AGENT_MISSING"


def test_sec_job_requests_only_the_selected_canonical_domain(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[ExternalDataDomain]] = []

    def fake_run_scheduled(
        _session: Session, _settings: Settings, **kwargs: Any
    ) -> dict[str, object]:
        calls.append(cast(list[ExternalDataDomain], kwargs["domains"]))
        return {"status": "COMPLETE", "domains": []}

    monkeypatch.setattr("portfolio_api.recurring_operations.run_scheduled", fake_run_scheduled)
    result = _run_sec_domain(
        postgres_engine,
        Settings(_env_file=None, sec_user_agent="App contact@example.com"),
        ExternalDataDomain.SOURCE_DOCUMENTS,
        datetime.now(UTC),
    )
    assert result["status"] == "COMPLETE"
    assert calls == [[ExternalDataDomain.SOURCE_DOCUMENTS]]


def test_sec_retryable_partial_result_is_retried_before_daily_cadence(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    now_at = datetime.now(UTC)

    def fake_run_scheduled(
        session: Session, _settings: Settings, **_kwargs: Any
    ) -> dict[str, object]:
        run = ExternalIngestionRun(
            provider_id=PROVIDERS[ExternalDataDomain.REPORTED_FUNDAMENTALS],
            domain=ExternalDataDomain.REPORTED_FUNDAMENTALS.value,
            idempotency_key=f"sec-partial-{now_at.isoformat()}",
            status="PARTIAL",
            requested_at=now_at,
            created_at=now_at,
            started_at=now_at,
            finished_at=now_at,
            request_scope={},
            report={"status": "PARTIAL"},
        )
        session.add(run)
        session.flush()
        session.add(
            ExternalIngestionAttempt(
                run_id=run.id,
                attempt_number=1,
                status="PARTIAL",
                started_at=now_at,
                finished_at=now_at,
                retryable=True,
                failure_code="NETWORK_ERROR",
                report={},
            )
        )
        return {"status": "PARTIAL", "domains": []}

    monkeypatch.setattr("portfolio_api.recurring_operations.run_scheduled", fake_run_scheduled)
    result = _run_sec_domain(
        postgres_engine,
        Settings(_env_file=None, sec_user_agent="App contact@example.com"),
        ExternalDataDomain.REPORTED_FUNDAMENTALS,
        now_at,
    )
    assert result["status"] == "PARTIAL"
    assert result["retry_after_seconds"] == int(FAILURE_BACKOFF_INITIAL.total_seconds())


def test_sec_job_reuses_same_day_manual_partial_without_fetching_again(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    now_at = datetime.now(UTC)
    with Session(postgres_engine) as session:
        run = ExternalIngestionRun(
            provider_id=PROVIDERS[ExternalDataDomain.REPORTED_FUNDAMENTALS],
            domain=ExternalDataDomain.REPORTED_FUNDAMENTALS.value,
            idempotency_key="sec-manual-partial-reuse",
            status="PARTIAL",
            requested_at=now_at,
            created_at=now_at,
            started_at=now_at,
            finished_at=now_at,
            request_scope={},
            report={"status": "PARTIAL", "normalized_source_fact_count": 120},
        )
        session.add(run)
        session.flush()
        run_id = run.id
        session.add(
            ExternalIngestionAttempt(
                run_id=run.id,
                attempt_number=1,
                status="PARTIAL",
                started_at=now_at,
                finished_at=now_at,
                retryable=False,
                report={},
            )
        )
        session.commit()

    def fail_if_called(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise AssertionError("A completed same-day SEC scope should be reused")

    monkeypatch.setattr("portfolio_api.recurring_operations.run_scheduled", fail_if_called)
    result = _run_sec_domain(
        postgres_engine,
        Settings(_env_file=None, sec_user_agent="Portfolio Research App contact@example.com"),
        ExternalDataDomain.REPORTED_FUNDAMENTALS,
        now_at + timedelta(minutes=1),
    )
    assert result["status"] == "PARTIAL"
    assert result["external_run_id"] == str(run_id)
    assert result["idempotent_reuse"] is True


def test_retry_after_override_is_recorded_for_partial_job(postgres_engine: Engine) -> None:
    now_at = datetime.now(UTC)
    result = _run_one_job(
        postgres_engine,
        Settings(_env_file=None),
        "SEC_FUNDAMENTALS",
        86400,
        now_at,
        lambda: {"status": "PARTIAL", "retry_after_seconds": 900},
    )
    assert result["operation_status"] == "PARTIAL"
    with Session(postgres_engine) as session:
        run = session.get(RecurringOperationRun, result["run_id"])
        assert run is not None
        assert run.next_attempt_at is not None
        assert run.next_attempt_at < now_at + timedelta(hours=1)


def test_sec_retry_does_not_exceed_two_same_day_replays(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    now_at = datetime.now(UTC)
    provider_id = PROVIDERS[ExternalDataDomain.REPORTED_FUNDAMENTALS]
    with Session(postgres_engine) as session:
        original = ExternalIngestionRun(
            provider_id=provider_id,
            domain=ExternalDataDomain.REPORTED_FUNDAMENTALS.value,
            idempotency_key="sec-retry-cap-original",
            status="FAILED",
            requested_at=now_at,
            created_at=now_at,
            started_at=now_at,
            finished_at=now_at,
            request_scope={},
            report={"status": "FAILED"},
        )
        session.add(original)
        session.flush()
        parent_id = original.id
        latest_id = original.id
        for index in range(2):
            replay = ExternalIngestionRun(
                provider_id=provider_id,
                domain=ExternalDataDomain.REPORTED_FUNDAMENTALS.value,
                idempotency_key=f"sec-retry-cap-{index}",
                replay_of_run_id=parent_id,
                status="FAILED",
                requested_at=now_at,
                created_at=now_at + timedelta(seconds=index + 1),
                started_at=now_at,
                finished_at=now_at,
                request_scope={},
                report={"status": "FAILED"},
            )
            session.add(replay)
            session.flush()
            session.add(
                ExternalIngestionAttempt(
                    run_id=replay.id,
                    attempt_number=1,
                    status="FAILED",
                    started_at=now_at,
                    finished_at=now_at,
                    retryable=True,
                    report={},
                )
            )
            parent_id = replay.id
            latest_id = replay.id
        session.commit()

    calls: list[dict[str, Any]] = []

    def fake_run_scheduled(
        _session: Session, _settings: Settings, **kwargs: Any
    ) -> dict[str, object]:
        calls.append(kwargs)
        return {"status": "FAILED", "domains": []}

    monkeypatch.setattr("portfolio_api.recurring_operations.run_scheduled", fake_run_scheduled)
    result = _run_sec_domain(
        postgres_engine,
        Settings(_env_file=None, sec_user_agent="Portfolio Research App contact@example.com"),
        ExternalDataDomain.REPORTED_FUNDAMENTALS,
        now_at + timedelta(minutes=1),
    )
    assert len(calls) == 1
    assert calls[0]["replay_of_run_id"] is None
    assert "retry_after_seconds" not in result
    with Session(postgres_engine) as session:
        assert session.get(ExternalIngestionRun, latest_id) is not None


def test_fmp_requires_explicit_rights_and_credential_before_provider_calls() -> None:
    settings = Settings(
        _env_file=None,
        fmp_consensus_ingestion_enabled=True,
        fmp_api_key=None,
    )
    result = _run_fmp_consensus(cast(Engine, None), settings, datetime.now(UTC))
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "FMP_CREDENTIAL_MISSING"


def test_sheets_polling_can_be_disabled_explicitly() -> None:
    settings = Settings(_env_file=None, google_sheets_poll_seconds=0)
    result = _run_sheets_discovery(cast(Engine, None), settings)
    assert result == {
        "status": "SKIPPED",
        "reason": "Google Sheets polling is disabled.",
    }


def test_operation_replay_waits_for_cadence_and_retry_is_bounded(
    postgres_engine: Engine,
) -> None:
    settings = Settings(_env_file=None)
    call_count = 0

    def action() -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        return {"status": "SUCCEEDED", "new": 1}

    now_at = datetime.now(UTC)
    first = _run_one_job(
        postgres_engine,
        settings,
        "RESEARCH_TRIGGER_SCAN",
        3600,
        now_at,
        action,
    )
    second = _run_one_job(
        postgres_engine,
        settings,
        "RESEARCH_TRIGGER_SCAN",
        3600,
        now_at + timedelta(minutes=1),
        action,
    )
    third = _run_one_job(
        postgres_engine,
        settings,
        "RESEARCH_TRIGGER_SCAN",
        3600,
        now_at + timedelta(hours=2),
        action,
    )
    assert first["operation_status"] == "SUCCEEDED"
    assert second["status"] == "NOT_DUE"
    assert third["operation_status"] == "SUCCEEDED"
    assert call_count == 2


def test_concurrent_scheduler_cycle_is_skipped_by_postgres_lock(postgres_engine: Engine) -> None:
    settings = Settings(_env_file=None, recurring_operations_enabled=True)
    with postgres_engine.connect() as connection:
        acquired: bool = connection.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
            {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
        ).scalar_one()
        connection.commit()
        assert acquired
        try:
            result = run_recurring_cycle(settings, engine=postgres_engine)
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
            )
        assert result["status"] == "SKIPPED"
        assert "another recurring operations cycle" in str(result["reason"]).lower()
