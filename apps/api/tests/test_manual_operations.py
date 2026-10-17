from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    CurrentLifecycle,
    LifecycleEvent,
    OperationalJobAttempt,
    OperationalJobRequest,
)
from portfolio_api.domain.schemas import OperationalJobRequestCreate
from portfolio_api.manual_operations import create_job_request, retry_job_request
from portfolio_api.recurring_operations import process_manual_job_requests
from portfolio_api.settings import Settings


def _company_in_state(session: Session, state: str = "PORTFOLIO") -> Company:
    company = Company(name="Manual refresh fixture", reporting_currency="USD")
    session.add(company)
    session.flush()
    event = LifecycleEvent(
        company_id=company.id,
        sequence=1,
        previous_state=None,
        new_state=state,
        effective_at=datetime.now(UTC),
        recorded_at=datetime.now(UTC),
        actor="IMPORT",
        reason="Test fixture",
        source="test:manual-refresh",
    )
    session.add(event)
    session.flush()
    session.add(CurrentLifecycle(company_id=company.id, event_id=event.id))
    session.flush()
    return company


def test_requests_are_scoped_deduplicated_and_company_lifecycle_is_checked(
    postgres_engine: Engine,
) -> None:
    now_at = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        company = _company_in_state(session)
        request, duplicate = create_job_request(
            session,
            OperationalJobRequestCreate(
                job_name="COMPANY_REFRESH", scope_kind="COMPANY", company_id=company.id
            ),
            now_at=now_at,
        )
        repeated, deduplicated = create_job_request(
            session,
            OperationalJobRequestCreate(
                job_name="COMPANY_REFRESH", scope_kind="COMPANY", company_id=company.id
            ),
            now_at=now_at + timedelta(seconds=1),
        )
        assert not duplicate
        assert deduplicated
        assert repeated.id == request.id
        assert request.affected_domains == [
            "MARKET_DATA",
            "CORPORATE_ACTIONS",
            "FX",
            "REPORTED_FUNDAMENTALS",
            "SOURCE_DOCUMENTS",
            "RESEARCH_TRIGGERS",
            "RESEARCH_QUEUE",
        ]
        assert request.scope_detail["company_name"] == company.name
        with pytest.raises(ValueError, match="Portfolio and Watchlist"):
            create_job_request(
                session,
                OperationalJobRequestCreate(
                    job_name="COMPANY_REFRESH",
                    scope_kind="COMPANY",
                    company_id=_company_in_state(session, "CANDIDATE").id,
                ),
                now_at=now_at,
            )


def test_refresh_all_records_dependency_steps_and_never_recomputes_decisions(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(postgres_engine) as session, session.begin():
        request, _ = create_job_request(
            session,
            OperationalJobRequestCreate(job_name="REFRESH_ALL"),
        )
        request_id = request.id
    called: list[str] = []

    def fake_step(
        _engine: Engine,
        _settings: Settings,
        _request: OperationalJobRequest,
        step_name: str,
        _now: datetime,
    ) -> dict[str, object]:
        called.append(step_name)
        return {"status": "SUCCEEDED", "updated": 1}

    monkeypatch.setattr("portfolio_api.recurring_operations._run_manual_step", fake_step)
    result = process_manual_job_requests(
        postgres_engine, Settings.model_construct(), now_at=datetime.now(UTC)
    )
    assert result["status"] == "SUCCEEDED"
    assert called == [
        "MARKET_AND_FX",
        "SEC_FUNDAMENTALS",
        "SEC_FILINGS",
        "SHEETS_DISCOVERY",
        "RESEARCH_REFRESH",
        "AGENT_WORK_FEED",
    ]
    assert "DECISION_RECOMPUTE" not in called
    with Session(postgres_engine) as session:
        stored_request = session.get(OperationalJobRequest, request_id)
        assert stored_request is not None and stored_request.status == "SUCCEEDED"
        attempts = list(
            session.scalars(
                select(OperationalJobAttempt)
                .where(OperationalJobAttempt.request_id == request_id)
                .order_by(OperationalJobAttempt.started_at)
            )
        )
        assert [attempt.step_name for attempt in attempts] == called
        assert all(attempt.finished_at is not None for attempt in attempts)
    assert (
        process_manual_job_requests(
            postgres_engine, Settings.model_construct(), now_at=datetime.now(UTC)
        )["status"]
        == "IDLE"
    )


def test_partial_refresh_all_retains_step_errors_and_can_be_retried(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(postgres_engine) as session, session.begin():
        request, _ = create_job_request(
            session,
            OperationalJobRequestCreate(job_name="REFRESH_ALL"),
        )
        original_id = request.id

    def partial_step(
        _engine: Engine,
        _settings: Settings,
        _request: OperationalJobRequest,
        step_name: str,
        _now: datetime,
    ) -> dict[str, object]:
        if step_name == "SEC_FILINGS":
            return {"status": "PARTIAL", "failure_code": "PARTIAL_COVERAGE"}
        return {"status": "SUCCEEDED"}

    monkeypatch.setattr("portfolio_api.recurring_operations._run_manual_step", partial_step)
    result = process_manual_job_requests(
        postgres_engine, Settings.model_construct(), now_at=datetime.now(UTC)
    )
    assert result["status"] == "PARTIAL"
    with Session(postgres_engine) as session, session.begin():
        original = session.get(OperationalJobRequest, original_id)
        assert original is not None and original.status == "PARTIAL"
        retried = retry_job_request(session, original_id)
        assert retried.retry_of_id == original_id
        assert retried.status == "QUEUED"


def test_company_scoped_request_api_is_local_domain_contract(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio_api.main import create_app

    with Session(postgres_engine) as session, session.begin():
        company = _company_in_state(session, "WATCHLIST")
        company_id = company.id
    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine", lambda _settings: postgres_engine
    )
    with TestClient(create_app(Settings(database_url=None))) as client:
        response = client.post(
            "/v1/operations/job-requests",
            json={
                "job_name": "COMPANY_REFRESH",
                "scope_kind": "COMPANY",
                "company_id": str(company_id),
            },
        )
        assert response.status_code == 202
        assert response.json()["company_id"] == str(company_id)
        assert response.json()["status"] == "QUEUED"
        request_id = response.json()["id"]
        assert client.get(f"/v1/operations/job-requests/{request_id}").status_code == 200
        invalid = client.post(
            "/v1/operations/job-requests",
            json={
                "job_name": "SHEETS_DISCOVERY",
                "scope_kind": "COMPANY",
                "company_id": str(company_id),
            },
        )
        assert invalid.status_code == 422


def test_api_rejects_refresh_when_background_worker_is_disabled(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio_api.main import create_app

    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine", lambda _settings: postgres_engine
    )
    with TestClient(
        create_app(Settings(database_url=None, recurring_operations_enabled=False))
    ) as client:
        response = client.post(
            "/v1/operations/job-requests",
            json={"job_name": "MARKET_DATA", "scope_kind": "ACTIVE_UNIVERSE"},
        )

    assert response.status_code == 503
    assert "worker is disabled" in response.json()["detail"]


def test_second_worker_cannot_claim_a_request_while_first_is_processing(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(postgres_engine) as session, session.begin():
        create_job_request(session, OperationalJobRequestCreate(job_name="RESEARCH_REFRESH"))
    entered = Event()
    release = Event()

    def slow_step(
        _engine: Engine,
        _settings: Settings,
        _request: OperationalJobRequest,
        _step_name: str,
        _now: datetime,
    ) -> dict[str, object]:
        entered.set()
        release.wait(timeout=5)
        return {"status": "SUCCEEDED"}

    monkeypatch.setattr("portfolio_api.recurring_operations._run_manual_step", slow_step)
    first_result: list[dict[str, object]] = []
    thread = Thread(
        target=lambda: first_result.append(
            process_manual_job_requests(
                postgres_engine, Settings.model_construct(), now_at=datetime.now(UTC)
            )
        )
    )
    thread.start()
    assert entered.wait(timeout=5)
    second = process_manual_job_requests(
        postgres_engine, Settings.model_construct(), now_at=datetime.now(UTC)
    )
    release.set()
    thread.join(timeout=5)
    assert second["status"] == "IDLE"
    assert first_result and first_result[0]["status"] == "SUCCEEDED"
