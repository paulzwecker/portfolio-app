from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import uuid4

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


@pytest.mark.integration
def test_company_job_history_filters_before_limit_and_keeps_active_first(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio_api.main import create_app

    now_at = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        issuer = _company_in_state(session, "WATCHLIST")
        other = _company_in_state(session, "WATCHLIST")
        issuer_id, other_id = issuer.id, other.id
        active_ids = []
        for index in range(72):
            company = issuer if index < 37 else other
            active = index < 2
            request_id = uuid4()
            if active:
                active_ids.append(str(request_id))
            session.add(
                OperationalJobRequest(
                    id=request_id,
                    job_name="SEC_FILINGS" if index == 0 else "SEC_FUNDAMENTALS",
                    scope_kind="COMPANY",
                    company_id=company.id,
                    company_name=company.name,
                    requested_by="LOCAL_USER",
                    request_fingerprint=f"{index:064x}",
                    status="RUNNING" if index == 0 else "QUEUED" if active else "SUCCEEDED",
                    requested_at=now_at + timedelta(seconds=index),
                    attempt_count=0,
                    affected_domains=[],
                    scope_detail={},
                    result={"steps": []},
                )
            )
    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine", lambda *_args, **_kwargs: postgres_engine
    )
    with TestClient(
        create_app(Settings(database_url=None, recurring_operations_enabled=False))
    ) as client:
        response = client.get(f"/v1/companies/{issuer_id}/job-requests?limit=30")
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 30
        assert {row["id"] for row in rows[:2]} == set(active_ids)
        assert all(row["company_id"] == str(issuer_id) for row in rows)
        assert client.get(f"/v1/companies/{other_id}/job-requests?limit=101").status_code == 422
        assert client.get(f"/v1/companies/{uuid4()}/job-requests").status_code == 404
    with Session(postgres_engine) as session:
        assert len(list(session.scalars(select(OperationalJobRequest)))) == 72


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
def test_one_shot_request_does_not_claim_another_queued_job(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(postgres_engine) as session, session.begin():
        first, _ = create_job_request(
            session, OperationalJobRequestCreate(job_name="RESEARCH_REFRESH")
        )
        second, _ = create_job_request(
            session,
            OperationalJobRequestCreate(job_name="WORKBOOK_SYNC"),
            bypass_cooldown=True,
        )
        first_id, second_id = first.id, second.id

    called: list[str] = []

    def fake_step(
        _engine: Engine,
        _settings: Settings,
        request: OperationalJobRequest,
        step_name: str,
        _now: datetime,
    ) -> dict[str, object]:
        called.append(f"{request.id}:{step_name}")
        return {"status": "SUCCEEDED"}

    monkeypatch.setattr("portfolio_api.recurring_operations._run_manual_step", fake_step)
    result = process_manual_job_requests(
        postgres_engine,
        Settings.model_construct(workbook_sync_enabled=True),
        now_at=datetime.now(UTC),
        request_id=second_id,
    )

    assert result["status"] == "SUCCEEDED"
    assert called == [f"{second_id}:WORKBOOK_SYNC"]
    with Session(postgres_engine) as session:
        first_request = session.get(OperationalJobRequest, first_id)
        second_request = session.get(OperationalJobRequest, second_id)
        assert first_request is not None and first_request.status == "QUEUED"
        assert second_request is not None and second_request.status == "SUCCEEDED"


@pytest.mark.integration
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


@pytest.mark.integration
def test_company_scoped_request_api_is_local_domain_contract(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio_api.main import create_app

    with Session(postgres_engine) as session, session.begin():
        company = _company_in_state(session, "WATCHLIST")
        company_id = company.id
    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine",
        lambda _settings, **_kwargs: postgres_engine,
    )
    # This contract test exercises job-request creation. The operator's local
    # .env intentionally disables the recurring worker, so opt into the enabled
    # state explicitly rather than letting machine configuration change the test.
    with TestClient(
        create_app(Settings(database_url=None, recurring_operations_enabled=True))
    ) as client:
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


@pytest.mark.integration
def test_api_rejects_refresh_when_background_worker_is_disabled(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio_api.main import create_app

    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine",
        lambda _settings, **_kwargs: postgres_engine,
    )
    with TestClient(
        create_app(Settings(database_url=None, recurring_operations_enabled=False))
    ) as client:
        response = client.post(
            "/v1/operations/job-requests",
            json={"job_name": "MARKET_DATA", "scope_kind": "ACTIVE_UNIVERSE"},
        )

    assert response.status_code == 503
    assert "Manual operations are disabled" in response.json()["detail"]


@pytest.mark.integration
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
