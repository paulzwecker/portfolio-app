"""Research workflows must use lifecycle evidence known at their cutoff."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_research_triggers import _reported_fact

from portfolio_api.attention import attention_feed
from portfolio_api.domain.models import (
    Company,
    CurrentLifecycle,
    InvestmentThesisClaim,
    InvestmentThesisEvidence,
    InvestmentThesisRevision,
    LifecycleEvent,
    ReportedFundamentalBatch,
    SourceDocument,
)
from portfolio_api.research_queue import get_research_queue
from portfolio_api.research_triggers import (
    _company_read,
    _current_lifecycle,
    _fundamental_correction_candidates,
    _thesis_evidence_candidates,
)


def _company(session: Session, cutoff: datetime, *, created_at: datetime | None = None) -> Company:
    company = Company(
        name=f"Lifecycle {uuid4()}", created_at=created_at or cutoff - timedelta(days=10)
    )
    session.add(company)
    session.flush()
    session.add(
        SourceDocument(
            company_id=company.id,
            provider_id="fixture",
            source_name="Issuer",
            external_identifier=str(uuid4()),
            document_type="10-Q",
            title="Recent filing",
            canonical_url="https://issuer.example/filing",
            published_at=cutoff.date(),
            recorded_at=cutoff - timedelta(hours=1),
            data_quality="PASS",
            actor="IMPORT",
        )
    )
    return company


def _event(
    session: Session,
    company: Company,
    sequence: int,
    state: str,
    effective: datetime,
    recorded: datetime,
    previous: str | None,
) -> LifecycleEvent:
    event = LifecycleEvent(
        company_id=company.id,
        sequence=sequence,
        previous_state=previous,
        new_state=state,
        effective_at=effective,
        recorded_at=recorded,
        actor="LOCAL_USER",
        reason="Fixture",
    )
    session.add(event)
    session.flush()
    return event


def _states(session: Session, company: Company, cutoff: datetime) -> tuple[set[str], set[str]]:
    queue = get_research_queue(session, as_of=cutoff)
    queue_states = {
        task.company.lifecycle.value
        for task in queue.tasks
        if task.company.id == company.id and task.company.lifecycle is not None
    }
    feed = attention_feed(session, as_of=cutoff, company_id=company.id, event_type="NEW_FILING")
    feed_states = {event.lifecycle.value for event in feed.events if event.lifecycle is not None}
    return queue_states, feed_states


@pytest.mark.integration
@pytest.mark.parametrize("late", ["effective", "recorded"])
def test_later_drop_does_not_hide_earlier_research(
    postgres_engine: Engine,
    late: str,
) -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        company = _company(session, cutoff)
        previous = _event(
            session,
            company,
            1,
            "WATCHLIST",
            cutoff - timedelta(days=2),
            cutoff - timedelta(days=2),
            None,
        )
        next_time = cutoff + timedelta(days=1)
        later = _event(
            session,
            company,
            2,
            "DROP",
            next_time if late == "effective" else cutoff - timedelta(hours=1),
            next_time if late == "recorded" else cutoff - timedelta(hours=1),
            "WATCHLIST",
        )
        session.add(CurrentLifecycle(company_id=company.id, event_id=later.id))
        session.flush()
        assert _states(session, company, cutoff) == ({"WATCHLIST"}, {"WATCHLIST"})
        assert _current_lifecycle(session, company.id, cutoff) == ("WATCHLIST", previous.id)
        assert _states(session, company, next_time) == (set(), set())


@pytest.mark.integration
def test_equal_timestamps_choose_latest_sequence_before_filtering(
    postgres_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        company = _company(session, cutoff)
        _event(session, company, 1, "WATCHLIST", cutoff, cutoff, None)
        second = _event(session, company, 2, "CANDIDATE", cutoff, cutoff, "WATCHLIST")
        session.add(CurrentLifecycle(company_id=company.id, event_id=second.id))
        session.flush()
        assert _states(session, company, cutoff) == ({"CANDIDATE"}, {"CANDIDATE"})
        assert _current_lifecycle(session, company.id, cutoff) == ("CANDIDATE", second.id)


@pytest.mark.integration
def test_reentry_does_not_invent_an_earlier_active_state(postgres_engine: Engine) -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    later = cutoff + timedelta(days=1)
    with Session(postgres_engine) as session, session.begin():
        company = _company(session, cutoff)
        _event(
            session,
            company,
            1,
            "DROP",
            cutoff - timedelta(days=2),
            cutoff - timedelta(days=2),
            None,
        )
        reentry = _event(session, company, 2, "WATCHLIST", later, later, "DROP")
        session.add(CurrentLifecycle(company_id=company.id, event_id=reentry.id))
        session.flush()
        assert _states(session, company, cutoff) == (set(), set())
        assert _states(session, company, later) == ({"WATCHLIST"}, {"WATCHLIST"})


@pytest.mark.integration
def test_later_company_or_first_event_is_not_invented_in_the_past(
    postgres_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        later_company = _company(session, cutoff, created_at=cutoff + timedelta(days=1))
        later_company_event = _event(session, later_company, 1, "WATCHLIST", cutoff, cutoff, None)
        session.add(CurrentLifecycle(company_id=later_company.id, event_id=later_company_event.id))
        later_lifecycle = _company(session, cutoff)
        future_event = _event(
            session, later_lifecycle, 1, "WATCHLIST", cutoff + timedelta(days=1), cutoff, None
        )
        session.add(CurrentLifecycle(company_id=later_lifecycle.id, event_id=future_event.id))
        session.flush()
        assert _states(session, later_company, cutoff) == (set(), set())
        assert _company_read(session, later_company.id, cutoff) is None
        assert _states(session, later_lifecycle, cutoff) == (set(), set())
        assert _current_lifecycle(session, later_lifecycle.id, cutoff) == (None, None)


@pytest.mark.integration
def test_historical_trigger_detectors_use_known_lifecycle_and_thesis_revision(
    postgres_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    later = cutoff + timedelta(days=1)
    with Session(postgres_engine) as session, session.begin():
        company = _company(session, cutoff)
        _event(
            session,
            company,
            1,
            "WATCHLIST",
            cutoff - timedelta(days=3),
            cutoff - timedelta(days=3),
            None,
        )
        drop = _event(
            session, company, 2, "DROP", later, cutoff - timedelta(minutes=1), "WATCHLIST"
        )
        session.add(CurrentLifecycle(company_id=company.id, event_id=drop.id))
        batch = ReportedFundamentalBatch(
            provider_id="sec_company_facts",
            provider_schema_version="fixture",
            normalizer_version="fixture",
            domain="REPORTED_FUNDAMENTALS",
            source_digest="a" * 64,
            query_scope={},
            observed_at=cutoff - timedelta(hours=1),
            recorded_at=cutoff - timedelta(hours=1),
            provider_summary={},
            reconciliation={},
        )
        session.add(batch)
        session.flush()
        fact = _reported_fact(
            session,
            company.id,
            batch.id,
            now=cutoff,
            accession="0000000001-26-000001",
            value="100",
            context="POTENTIAL_RESTATEMENT",
            recorded_at=cutoff - timedelta(minutes=1),
        )
        session.add(fact)
        thesis = InvestmentThesisRevision(
            company_id=company.id,
            stream_key="thesis",
            revision_number=1,
            contract_version="1.0",
            external_revision_id="known",
            author_id="analyst",
            source_id="fixture",
            source_reference="https://issuer.example",
            observed_at=cutoff - timedelta(hours=2),
            recorded_at=cutoff - timedelta(hours=1),
            status="PUBLISHED",
            thesis_statement="Thesis",
            confidence="MEDIUM",
            rationale="Review",
            content_fingerprint="a" * 64,
        )
        session.add(thesis)
        session.flush()
        claim = InvestmentThesisClaim(
            revision_id=thesis.id,
            claim_key="risk",
            claim_type="PRINCIPAL_RISK",
            status="ACTIVE",
            statement="Risk",
            confidence="MEDIUM",
        )
        session.add(claim)
        session.flush()
        session.add(
            InvestmentThesisEvidence(
                claim_id=claim.id,
                relationship="CONTEXT",
                source_name="Issuer",
                source_url="https://issuer.example/evidence",
            )
        )
        session.add(
            InvestmentThesisRevision(
                company_id=company.id,
                stream_key="thesis",
                revision_number=2,
                contract_version="1.0",
                external_revision_id="future-observed",
                author_id="analyst",
                source_id="fixture",
                source_reference="https://issuer.example",
                observed_at=later,
                recorded_at=cutoff - timedelta(minutes=1),
                status="PUBLISHED",
                thesis_statement="New",
                confidence="MEDIUM",
                rationale="Review",
                content_fingerprint="b" * 64,
            )
        )
        session.flush()
        window_start = cutoff - timedelta(days=30)
        facts = _fundamental_correction_candidates(
            session, as_of=cutoff, cutoff=window_start, company_id=company.id
        )
        theses = _thesis_evidence_candidates(
            session, as_of=cutoff, cutoff=window_start, company_id=company.id
        )
        assert len(facts) == 1 and facts[0].source_record_id == str(fact.id)
        assert len(theses) == 1 and "Risk" in theses[0].reason
        assert not _fundamental_correction_candidates(
            session, as_of=later, cutoff=window_start, company_id=company.id
        )
        assert not _thesis_evidence_candidates(
            session, as_of=later, cutoff=window_start, company_id=company.id
        )
