from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Actor,
    Company,
    Lifecycle,
    LifecycleEvent,
    ResearchAssessment,
    ResearchQueueCompletion,
    ResearchRevision,
    SourceDocument,
)
from portfolio_api.domain.services import DomainError, transition_lifecycle
from portfolio_api.main import create_app
from portfolio_api.research_queue import complete_research_queue_task, get_research_queue
from portfolio_api.settings import Settings


def create_active_company(engine: Engine, name: str, lifecycle: Lifecycle) -> UUID:
    with Session(engine) as session, session.begin():
        company = Company(name=name, reporting_currency="USD", is_demo=False)
        session.add(company)
        session.flush()
        transition_lifecycle(
            session,
            company.id,
            s.LifecycleChange(
                actor=Actor.LOCAL_USER,
                reason="Added for research queue verification",
                source="test_research_queue",
                effective_at=datetime.now(UTC),
                new_state=lifecycle,
                expected_event_id=None,
            ),
        )
        return company.id


def add_filing(engine: Engine, company_id: UUID, title: str) -> UUID:
    with Session(engine) as session, session.begin():
        document = SourceDocument(
            company_id=company_id,
            provider_id="test-primary-source",
            source_name="Test issuer source",
            source_jurisdiction="US",
            external_identifier=f"test-{uuid4()}",
            document_type="10-Q",
            title=title,
            canonical_url=f"https://issuer.example/{uuid4()}",
            published_at=datetime.now(UTC).date(),
            data_quality="PASS",
        )
        session.add(document)
        session.flush()
        return document.id


def add_research_update(engine: Engine, company_id: UUID) -> UUID:
    with Session(engine) as session, session.begin():
        revision_id = uuid4()
        fingerprint = hashlib.sha256(str(revision_id).encode()).hexdigest()
        revision = ResearchRevision(
            id=revision_id,
            company_id=company_id,
            stream_key="quarterly-outlook",
            revision_number=1,
            contract_version="1.0.0",
            external_revision_id=f"queue-test-{revision_id}",
            author_id="research-agent",
            source_id="test-primary-source",
            source_reference="https://issuer.example/research",
            observed_at=datetime.now(UTC),
            status="PUBLISHED",
            rationale="A canonical research publication was added for queue verification.",
            content_fingerprint=fingerprint,
        )
        session.add(revision)
        session.flush()
        session.add(
            ResearchAssessment(
                revision_id=revision.id,
                assessment_type="BUSINESS_OUTLOOK",
                status="UNAVAILABLE",
                status_reason="No structured outlook is available in this fixture.",
                narrative=None,
                confidence="UNASSESSED",
            )
        )
        return revision.id


@pytest.mark.integration
def test_queue_generation_completion_reopening_and_historical_traceability(
    postgres_engine: Engine,
) -> None:
    company_id = create_active_company(postgres_engine, "Queue issuer", Lifecycle.WATCHLIST)
    first_document_id = add_filing(postgres_engine, company_id, "Quarterly results")
    cutoff = datetime.now(UTC)

    with Session(postgres_engine) as session:
        first_queue = get_research_queue(session, as_of=cutoff)
        duplicate_queue = get_research_queue(session, as_of=cutoff)
        assert first_queue == duplicate_queue
        identities = {(task.task_id, task.condition_fingerprint) for task in first_queue.tasks}
        assert len(identities) == len(first_queue.tasks)
        assert session.scalar(select(func.count()).select_from(ResearchQueueCompletion)) == 0

    company_tasks = [task for task in first_queue.tasks if task.company.id == company_id]
    readiness = next(task for task in company_tasks if task.task_type == "WATCHLIST_READINESS")
    missing_thesis = next(task for task in company_tasks if task.task_type == "THESIS_REVIEW")
    filing_task = next(
        task
        for task in company_tasks
        if task.task_type == "MATERIAL_EVIDENCE"
        and task.sources[0].source_record_id == str(first_document_id)
    )
    assert readiness.judgment_required is True
    assert "No canonical Watchlist Rank entry" in readiness.reason
    assert missing_thesis.trigger_rule == "No current published investment-thesis revision exists."
    assert filing_task.sources[0].source_url is not None

    readiness_completion = {
        "condition_fingerprint": readiness.condition_fingerprint,
        "completed_by": "researcher",
        "completion_note": "Reviewed the available Watchlist context.",
    }

    completion = {
        "condition_fingerprint": filing_task.condition_fingerprint,
        "completed_by": "researcher",
        "completion_note": "Reviewed the filing and linked the relevant evidence in the thesis.",
    }
    # An uncompleted publication expires from the review window and must reject a stale write.
    with (
        Session(postgres_engine) as session,
        session.begin(),
        pytest.raises(DomainError, match="changed or is no longer current"),
    ):
        complete_research_queue_task(
            session,
            filing_task.task_id,
            s.ResearchQueueCompletionCreate.model_validate(completion),
            as_of=cutoff + timedelta(days=SOURCE_WINDOW_DAYS + 1),
        )

    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        completed = client.post(
            f"/v1/research-queue/{filing_task.task_id}/complete", json=completion
        )
        assert completed.status_code == 200
        assert completed.json()["result"] == "COMPLETED"
        replay = client.post(f"/v1/research-queue/{filing_task.task_id}/complete", json=completion)
        assert replay.status_code == 200
        assert replay.json()["result"] == "ALREADY_COMPLETED"
        readiness_response = client.post(
            f"/v1/research-queue/{readiness.task_id}/complete",
            json=readiness_completion,
        )
        assert readiness_response.status_code == 200
        assert readiness_response.json()["result"] == "COMPLETED"
        open_queue = client.get("/v1/research-queue")
        assert open_queue.status_code == 200
        assert filing_task.task_id not in {item["task_id"] for item in open_queue.json()["tasks"]}
        with_complete = client.get("/v1/research-queue?include_complete=true")
        current_completion = next(
            item for item in with_complete.json()["tasks"] if item["task_id"] == filing_task.task_id
        )
        assert current_completion["status"] == "COMPLETE"

    second_document_id = add_filing(postgres_engine, company_id, "New quarterly results")
    add_research_update(postgres_engine, company_id)
    with Session(postgres_engine) as session, session.begin():
        replay_after_change, replay_result = complete_research_queue_task(
            session,
            filing_task.task_id,
            s.ResearchQueueCompletionCreate.model_validate(completion),
        )
        assert replay_result == "ALREADY_COMPLETED"
        assert replay_after_change.status == "COMPLETE"
    with Session(postgres_engine) as session:
        refreshed = get_research_queue(session)
        new_filing_task = next(
            task
            for task in refreshed.tasks
            if task.company.id == company_id
            and task.task_type == "MATERIAL_EVIDENCE"
            and task.sources[0].source_record_id == str(second_document_id)
        )
        assert new_filing_task.task_id != filing_task.task_id
        assert new_filing_task.status == "OPEN"
        reopened_readiness = next(
            task
            for task in refreshed.tasks
            if task.company.id == company_id and task.task_type == "WATCHLIST_READINESS"
        )
        assert reopened_readiness.task_id == readiness.task_id
        assert reopened_readiness.condition_fingerprint != readiness.condition_fingerprint
        assert reopened_readiness.status == "OPEN"
        history = client_history(postgres_engine)
        assert len(history) == 2
        prior = next(item for item in history if item.task.task_id == filing_task.task_id)
        assert prior.task.task_id == filing_task.task_id
        assert prior.task.sources[0].source_record_id == str(first_document_id)
        assert prior.completion_note == completion["completion_note"]


@pytest.mark.integration
def test_candidate_gate_condition_changes_reject_stale_completion(postgres_engine: Engine) -> None:
    company_id = create_active_company(
        postgres_engine, "Candidate queue issuer", Lifecycle.CANDIDATE
    )
    with Session(postgres_engine) as session:
        candidate_task = next(
            task
            for task in get_research_queue(session).tasks
            if task.company.id == company_id and task.task_type == "CANDIDATE_STAGE"
        )
    assert "Start with Discovery" in candidate_task.reason

    # A changed lifecycle event invalidates the Candidate condition without changing the old item.
    with Session(postgres_engine) as session, session.begin():
        event = session.scalar(
            select(LifecycleEvent).where(LifecycleEvent.company_id == company_id)
        )
        assert event is not None
        transition_lifecycle(
            session,
            company_id,
            s.LifecycleChange(
                actor=Actor.LOCAL_USER,
                reason="Reviewed candidate and moved to Watchlist",
                source="test_research_queue",
                effective_at=datetime.now(UTC),
                new_state=Lifecycle.WATCHLIST,
                expected_event_id=event.id,
            ),
        )
    with (
        Session(postgres_engine) as session,
        session.begin(),
        pytest.raises(DomainError, match="changed or is no longer current"),
    ):
        complete_research_queue_task(
            session,
            candidate_task.task_id,
            s.ResearchQueueCompletionCreate(
                condition_fingerprint=candidate_task.condition_fingerprint,
                completed_by="researcher",
            ),
        )


SOURCE_WINDOW_DAYS = 30


def client_history(engine: Engine) -> list[s.ResearchQueueCompletionRead]:
    from portfolio_api.research_queue import research_queue_history

    with Session(engine) as session:
        return research_queue_history(session)
