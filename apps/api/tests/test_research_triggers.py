from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.attention import attention_feed
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Actor,
    Company,
    InvestmentThesisClaim,
    InvestmentThesisEvidence,
    InvestmentThesisRevision,
    Lifecycle,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
    ResearchQueueCompletion,
    ResearchTrigger,
    ResearchTriggerType,
    SourceDocument,
    SourceDocumentBatch,
)
from portfolio_api.domain.services import DomainError, transition_lifecycle
from portfolio_api.research_agent_operations import deliver_agent_work, record_agent_acknowledgment
from portfolio_api.research_queue import complete_research_queue_task, get_research_queue
from portfolio_api.research_triggers import (
    TriggerCandidate,
    _processing_state,
    _snapshot_fingerprint,
    _superseded_source_ids,
    _thesis_evidence_candidates,
    list_research_triggers,
    normalize_trigger_cutoff,
    refresh_research_triggers,
    research_trigger_context,
)
from portfolio_api.source_document_provenance import (
    SEC_ISSUER_WARNING,
    SOURCE_MISMATCH_WARNING,
    SOURCE_UNAVAILABLE_WARNING,
)


def test_trigger_identity_fingerprint_is_stable_and_revision_sensitive() -> None:
    now = datetime(2026, 10, 15, 9, tzinfo=UTC)
    base = TriggerCandidate(
        company_id=uuid4(),
        event_key="source_document:filing-1",
        trigger_type=ResearchTriggerType.NEW_FILING,
        title="New 10-Q filing",
        reason="Review this source.",
        source_domain="source_document",
        source_record_id="filing-1",
        source_reference="https://issuer.example/filing-1",
        effective_at=None,
        source_observed_at=None,
        source_recorded_at=now,
        source_snapshot={"time_precision": "UNKNOWN"},
    )
    replay = TriggerCandidate(**base.__dict__)
    corrected = TriggerCandidate(**{**base.__dict__, "reason": "Review the corrected source."})

    assert _snapshot_fingerprint(base) == _snapshot_fingerprint(replay)
    assert _snapshot_fingerprint(base) != _snapshot_fingerprint(corrected)


def test_processing_state_uses_queue_completion_and_explicit_supersession() -> None:
    row = ResearchTrigger(
        event_key="source_document:filing-1",
        version=1,
        source_record_id="filing-1",
        queue_task_id="a" * 64,
        queue_condition_fingerprint="b" * 64,
    )
    unlinked = ResearchTrigger(
        event_key="source_document:unlinked-filing",
        version=1,
        source_record_id="unlinked-filing",
    )
    assert (
        _processing_state(
            row,
            latest_version=1,
            completion_by_identity={},
            superseded_source_ids=set(),
        )
        == "OPEN"
    )
    assert (
        _processing_state(
            row,
            latest_version=1,
            completion_by_identity={("a" * 64, "b" * 64): cast(ResearchQueueCompletion, object())},
            superseded_source_ids=set(),
        )
        == "REVIEWED"
    )
    assert (
        _processing_state(
            row,
            latest_version=2,
            completion_by_identity={},
            superseded_source_ids=set(),
        )
        == "SUPERSEDED"
    )
    assert (
        _processing_state(
            row,
            latest_version=1,
            completion_by_identity={},
            superseded_source_ids={"filing-1"},
        )
        == "SUPERSEDED"
    )
    assert (
        _processing_state(
            unlinked,
            latest_version=1,
            completion_by_identity={},
            superseded_source_ids=set(),
        )
        == "STALE"
    )


def test_as_of_cutoff_requires_timezone_information() -> None:
    cutoff = datetime(2026, 10, 15, 9, tzinfo=UTC)
    assert normalize_trigger_cutoff(cutoff) == cutoff
    with pytest.raises(ValueError, match="timezone offset"):
        normalize_trigger_cutoff(datetime(2026, 10, 15, 9))


def _active_company(session: Session, name: str) -> UUID:
    company = Company(name=name, reporting_currency="USD", is_demo=False)
    session.add(company)
    session.flush()
    transition_lifecycle(
        session,
        company.id,
        s.LifecycleChange(
            actor=Actor.LOCAL_USER,
            reason="Added for research trigger verification",
            source="test_research_triggers",
            effective_at=datetime.now(UTC),
            new_state=Lifecycle.WATCHLIST,
            expected_event_id=None,
        ),
    )
    return company.id


def _source_document(
    session: Session,
    company_id: UUID,
    *,
    now: datetime,
    title: str,
    published_at: date | None,
    recorded_at: datetime,
    supersedes_document_id: UUID | None = None,
    provider_id: str = "test-primary-source",
) -> SourceDocument:
    row = SourceDocument(
        company_id=company_id,
        provider_id=provider_id,
        source_name="Test issuer source",
        source_jurisdiction="US",
        external_identifier=f"test-{uuid4()}",
        document_type="10-Q",
        title=title,
        reporting_period="FY2026 Q3",
        published_at=published_at,
        filed_at=published_at,
        canonical_url=f"https://issuer.example/{uuid4()}",
        recorded_at=recorded_at,
        supersedes_document_id=supersedes_document_id,
        actor=Actor.IMPORT,
    )
    session.add(row)
    session.flush()
    return row


def _reported_fact(
    session: Session,
    company_id: UUID,
    batch_id: UUID,
    *,
    now: datetime,
    accession: str,
    value: str,
    context: str,
    recorded_at: datetime,
    supersedes_id: UUID | None = None,
) -> ReportedFundamentalObservation:
    return ReportedFundamentalObservation(
        company_id=company_id,
        batch_id=batch_id,
        provider_id="sec_company_facts",
        provider_entity_id="0000000001",
        source_priority=10,
        metric="REVENUE",
        statement="INCOME_STATEMENT",
        period_type="ANNUAL",
        period_start=datetime(2025, 1, 1, tzinfo=UTC),
        period_end=datetime(2025, 12, 31, tzinfo=UTC),
        fiscal_year=2025,
        fiscal_period="FY",
        filed_at=now - timedelta(days=1),
        observed_at=now - timedelta(hours=1),
        recorded_at=recorded_at,
        value=Decimal(value),
        currency="USD",
        unit="USD",
        source_taxonomy="us-gaap",
        source_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        source_unit="USD",
        accession_number=accession,
        form="10-K/A",
        frame="CY2025",
        source_record_id=f"{accession}:revenue",
        source_url=f"https://www.sec.gov/Archives/{accession}",
        source_ref=f"SEC accession {accession}",
        observation_fingerprint=("a" if context == "POTENTIAL_RESTATEMENT" else "b") * 64,
        mapping_priority=0,
        revision_context=context,
        data_quality="DATA_CHECK" if context == "POTENTIAL_RESTATEMENT" else "PASS",
        quality_reason="Changed value requires source review."
        if context == "POTENTIAL_RESTATEMENT"
        else None,
        supersedes_observation_id=supersedes_id,
    )


@pytest.mark.integration
def test_filing_trigger_is_idempotent_temporally_honest_and_queue_linked(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Trigger filing issuer")
        document = _source_document(
            session,
            company_id,
            now=now,
            title="Quarterly report with unknown publication date",
            published_at=None,
            recorded_at=now - timedelta(hours=2),
        )
        first = refresh_research_triggers(session, as_of=now, lookback_days=30)
        replay = refresh_research_triggers(session, as_of=now, lookback_days=30)

        assert first.created == 1
        assert replay.created == 0
        assert replay.replayed == 1
        assert session.scalar(select(func.count()).select_from(ResearchTrigger)) == 1
        trigger = session.scalar(select(ResearchTrigger))
        assert trigger is not None
        assert trigger.source_record_id == str(document.id)
        assert trigger.effective_at is None
        assert trigger.source_recorded_at == document.recorded_at
        assert trigger.queue_task_id is not None
        queue_task = next(
            task
            for task in get_research_queue(session, as_of=first.as_of).tasks
            if task.task_id == trigger.queue_task_id
        )
        assert queue_task.task_type == "RESEARCH_TRIGGER"
        assert queue_task.sources[0].source_record_id == str(trigger.id)
        readiness_task = next(
            task
            for task in get_research_queue(session, as_of=first.as_of).tasks
            if task.company.id == company_id and task.task_type == "WATCHLIST_READINESS"
        )
        with pytest.raises(DomainError, match="applies only to trigger reviews"):
            complete_research_queue_task(
                session,
                readiness_task.task_id,
                s.ResearchQueueCompletionCreate(
                    condition_fingerprint=readiness_task.condition_fingerprint,
                    completed_by="reviewer",
                    trigger_classification="NOISE",
                ),
                as_of=first.as_of,
            )

        completed, result = complete_research_queue_task(
            session,
            queue_task.task_id,
            s.ResearchQueueCompletionCreate(
                condition_fingerprint=queue_task.condition_fingerprint,
                completed_by="reviewer",
                completion_note="Reviewed the source document.",
                trigger_classification="NOISE",
            ),
            as_of=first.as_of + timedelta(minutes=1),
        )
        assert result == "COMPLETED"
        assert completed.status == "COMPLETE"
        assert completed.trigger_classification == "NOISE"
        replayed, replay_result = complete_research_queue_task(
            session,
            queue_task.task_id,
            s.ResearchQueueCompletionCreate(
                condition_fingerprint=queue_task.condition_fingerprint,
                completed_by="reviewer",
                completion_note="Reviewed the source document.",
                trigger_classification="NOISE",
            ),
            as_of=first.as_of + timedelta(minutes=1),
        )
        assert replay_result == "ALREADY_COMPLETED"
        assert replayed.trigger_classification == "NOISE"
        with pytest.raises(DomainError, match="different trigger classification"):
            complete_research_queue_task(
                session,
                queue_task.task_id,
                s.ResearchQueueCompletionCreate(
                    condition_fingerprint=queue_task.condition_fingerprint,
                    completed_by="reviewer",
                    trigger_classification="INCREMENTAL",
                ),
                as_of=first.as_of + timedelta(minutes=1),
            )
        reviewed = list_research_triggers(
            session,
            as_of=first.as_of + timedelta(minutes=1),
            company_id=company_id,
        )
        assert reviewed.triggers[0].processing_state == "REVIEWED"


@pytest.mark.integration
def test_unverified_sec_filing_is_disclosed_across_existing_research_workflows(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "SEC disclosure issuer")
        sec = _source_document(
            session,
            company_id,
            now=now,
            title="SEC result",
            published_at=now.date(),
            recorded_at=now - timedelta(hours=2),
            provider_id="sec_edgar",
        )
        other = _source_document(
            session,
            company_id,
            now=now,
            title="Issuer result",
            published_at=now.date(),
            recorded_at=now - timedelta(hours=2),
        )
        session.flush()
        events = attention_feed(session, as_of=now, company_id=company_id).events
        sec_event = next(item for item in events if item.source_id == str(sec.id))
        other_event = next(item for item in events if item.source_id == str(other.id))
        assert SEC_ISSUER_WARNING in sec_event.explanation
        assert SEC_ISSUER_WARNING not in other_event.explanation

        first = refresh_research_triggers(session, as_of=now, lookback_days=30)
        trigger = session.scalar(
            select(ResearchTrigger).where(ResearchTrigger.source_record_id == str(sec.id))
        )
        assert trigger is not None
        assert SEC_ISSUER_WARNING not in trigger.reason  # Immutable fingerprint input.
        trigger_id, fingerprint = trigger.id, trigger.fingerprint
        listed = list_research_triggers(session, company_id=company_id, as_of=now)
        assert SEC_ISSUER_WARNING in next(
            item.reason for item in listed.triggers if item.id == trigger_id
        )
        assert SEC_ISSUER_WARNING in research_trigger_context(session, trigger_id).trigger.reason

        queue = get_research_queue(session, as_of=now)
        task = next(
            item
            for item in queue.tasks
            if item.task_type == "MATERIAL_EVIDENCE"
            and item.sources[0].source_record_id == str(sec.id)
        )
        other_task = next(
            item
            for item in queue.tasks
            if item.task_type == "MATERIAL_EVIDENCE"
            and item.sources[0].source_record_id == str(other.id)
        )
        assert SEC_ISSUER_WARNING in task.reason
        assert SEC_ISSUER_WARNING not in other_task.reason
        completed, result = complete_research_queue_task(
            session,
            task.task_id,
            s.ResearchQueueCompletionCreate(
                condition_fingerprint=task.condition_fingerprint,
                completed_by="reviewer",
                completion_note="Checked the original source.",
            ),
            as_of=now,
        )
        assert result == "COMPLETED" and completed.status == "COMPLETE"
        replay = refresh_research_triggers(session, as_of=now, lookback_days=30)
        assert first.created == 2 and replay.created == 0 and replay.replayed == 2
        assert trigger.id == trigger_id and trigger.fingerprint == fingerprint
        completed_again = next(
            item
            for item in get_research_queue(
                session,
                as_of=now,
                include_complete=True,
            ).tasks
            if item.task_id == task.task_id
        )
        assert completed_again.status == "COMPLETE"
        assert completed_again.condition_fingerprint == task.condition_fingerprint


@pytest.mark.integration
def test_old_thesis_and_missing_document_triggers_disclose_source_limits(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Trigger source issuer")
        other_company = _active_company(session, "Other issuer")
        sec = _source_document(
            session,
            company_id,
            now=now,
            title="Old SEC source",
            published_at=None,
            recorded_at=now - timedelta(hours=1),
            provider_id="sec_edgar",
        )
        wrong_company_doc = _source_document(
            session,
            other_company,
            now=now,
            title="Other source",
            published_at=None,
            recorded_at=now - timedelta(hours=1),
        )
        cases = [
            (str(sec.id), SEC_ISSUER_WARNING),
            (str(wrong_company_doc.id), SOURCE_MISMATCH_WARNING),
            ("not-a-uuid", SOURCE_UNAVAILABLE_WARNING),
            (str(uuid4()), SOURCE_UNAVAILABLE_WARNING),
        ]
        rows = []
        for index, (source_id, _) in enumerate(cases):
            row = ResearchTrigger(
                company_id=company_id,
                event_key=f"legacy-evidence-{index}",
                version=1,
                fingerprint=f"{index + 1:x}" * 64,
                trigger_type="THESIS_EVIDENCE_LINKED",
                title="Existing evidence",
                reason="Previously recorded reason.",
                source_domain="source_document",
                source_record_id=source_id,
                source_recorded_at=now - timedelta(minutes=1),
                detected_at=now - timedelta(minutes=1),
                source_snapshot={},
            )
            rows.append(row)
            session.add(row)
        session.flush()
        listed = {
            item.id: item
            for item in list_research_triggers(
                session,
                company_id=company_id,
                as_of=now,
            ).triggers
        }
        queue = get_research_queue(session, as_of=now)
        for row, (_, warning) in zip(rows, cases, strict=True):
            assert warning in listed[row.id].reason
            assert warning in research_trigger_context(session, row.id).trigger.reason
            task = next(
                item
                for item in queue.tasks
                if item.task_type == "RESEARCH_TRIGGER"
                and item.sources[0].source_record_id == str(row.id)
            )
            assert warning in task.reason
            assert row.reason == "Previously recorded reason."


@pytest.mark.integration
def test_later_filing_and_supersession_do_not_leak_into_historical_workflows(
    postgres_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Historical source issuer")
        original = _source_document(
            session,
            company_id,
            now=cutoff,
            title="Original filing",
            published_at=(cutoff - timedelta(days=2)).date(),
            recorded_at=cutoff - timedelta(days=1),
        )
        later = _source_document(
            session,
            company_id,
            now=cutoff,
            title="Later correction",
            published_at=(cutoff - timedelta(days=1)).date(),
            recorded_at=cutoff + timedelta(days=1),
            supersedes_document_id=original.id,
        )
        past_events = attention_feed(session, as_of=cutoff, company_id=company_id).events
        past_sources = {item.source_id for item in past_events}
        assert str(original.id) in past_sources and str(later.id) not in past_sources
        past_tasks = get_research_queue(session, as_of=cutoff).tasks
        past_task_sources = {
            source.source_record_id for item in past_tasks for source in item.sources
        }
        assert str(original.id) in past_task_sources and str(later.id) not in past_task_sources
        future = cutoff + timedelta(days=2)
        future_sources = {
            item.source_id
            for item in attention_feed(
                session,
                as_of=future,
                company_id=company_id,
            ).events
        }
        assert str(original.id) not in future_sources and str(later.id) in future_sources
        future_tasks = get_research_queue(session, as_of=future).tasks
        future_task_sources = {
            source.source_record_id for item in future_tasks for source in item.sources
        }
        assert str(original.id) not in future_task_sources and str(later.id) in future_task_sources


@pytest.mark.integration
def test_later_retrieval_is_not_visible_to_historical_filing_workflows(
    postgres_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Late observation issuer")
        batch = SourceDocumentBatch(
            provider_id="sec_edgar",
            normalizer_version="fixture",
            domain="SOURCE_DOCUMENTS",
            source_digest="a" * 64,
            query_scope={},
            observed_at=cutoff + timedelta(days=1),
            recorded_at=cutoff - timedelta(hours=1),
            provider_summary={},
            reconciliation={},
        )
        session.add(batch)
        session.flush()
        doc = SourceDocument(
            company_id=company_id,
            batch_id=batch.id,
            provider_id="sec_edgar",
            source_name="SEC",
            external_identifier="late-retrieval",
            document_type="10-Q",
            title="Later observed filing",
            canonical_url="https://www.sec.gov/example",
            published_at=(cutoff - timedelta(days=2)).date(),
            data_quality="PASS",
            recorded_at=cutoff - timedelta(hours=1),
            retrieved_at=cutoff + timedelta(days=1),
            actor="IMPORT",
        )
        session.add(doc)
        session.flush()
        trigger = ResearchTrigger(
            company_id=company_id,
            event_key="late-source-trigger",
            version=1,
            fingerprint="f" * 64,
            trigger_type="THESIS_EVIDENCE_LINKED",
            title="Existing source",
            reason="Previously recorded reason.",
            source_domain="source_document",
            source_record_id=str(doc.id),
            source_recorded_at=cutoff - timedelta(minutes=1),
            detected_at=cutoff - timedelta(minutes=1),
            source_snapshot={},
        )
        session.add(trigger)
        session.flush()
        assert str(doc.id) not in {
            item.source_id
            for item in attention_feed(
                session,
                as_of=cutoff,
                company_id=company_id,
            ).events
        }
        queue = get_research_queue(session, as_of=cutoff)
        assert not any(
            item.task_type == "MATERIAL_EVIDENCE"
            and any(source.source_record_id == str(doc.id) for source in item.sources)
            for item in queue.tasks
        )
        task = next(
            item
            for item in queue.tasks
            if item.task_type == "RESEARCH_TRIGGER"
            and item.sources[0].source_record_id == str(trigger.id)
        )
        assert SOURCE_UNAVAILABLE_WARNING in task.reason
        listed = list_research_triggers(session, company_id=company_id, as_of=cutoff)
        assert SOURCE_UNAVAILABLE_WARNING in next(
            item.reason for item in listed.triggers if item.id == trigger.id
        )
        thesis = InvestmentThesisRevision(
            company_id=company_id,
            stream_key="main",
            revision_number=1,
            contract_version="1.0.0",
            external_revision_id="late-evidence",
            author_id="analyst",
            source_id="fixture",
            source_reference="https://issuer.example",
            observed_at=cutoff - timedelta(hours=2),
            recorded_at=cutoff - timedelta(hours=1),
            status="PUBLISHED",
            thesis_statement="A research thesis.",
            confidence="MEDIUM",
            rationale="Review source evidence.",
            content_fingerprint="c" * 64,
        )
        session.add(thesis)
        session.flush()
        claim = InvestmentThesisClaim(
            revision_id=thesis.id,
            claim_key="risk",
            claim_type="PRINCIPAL_RISK",
            status="ACTIVE",
            statement="A research risk.",
            confidence="MEDIUM",
        )
        session.add(claim)
        session.flush()
        evidence = InvestmentThesisEvidence(
            claim_id=claim.id,
            relationship="CONTEXT",
            source_document_id=doc.id,
            source_name="SEC",
        )
        session.add(evidence)
        session.flush()
        assert (
            _thesis_evidence_candidates(
                session, as_of=cutoff, cutoff=cutoff - timedelta(days=30), company_id=company_id
            )
            == []
        )
        later = cutoff + timedelta(days=2)
        candidates = _thesis_evidence_candidates(
            session, as_of=later, cutoff=cutoff - timedelta(days=30), company_id=company_id
        )
        assert len(candidates) == 1 and candidates[0].source_record_id == str(doc.id)


@pytest.mark.integration
def test_sec_warning_changes_agent_delivery_identity_once_for_safety(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Agent warning issuer")
        doc = _source_document(
            session,
            company_id,
            now=now,
            title="Undated SEC filing",
            published_at=None,
            recorded_at=now - timedelta(hours=1),
            provider_id="sec_edgar",
        )
        refresh_research_triggers(session, as_of=now, company_id=company_id)
        request = s.ResearchAgentWorkRequest(as_of=now, limit=50)
        import portfolio_api.research_triggers as trigger_module

        original = trigger_module.trigger_document_warnings
        monkeypatch.setattr(trigger_module, "trigger_document_warnings", lambda *args: {})
        old = next(
            item
            for item in deliver_agent_work(
                session,
                "PORTFOLIO_THESIS_SENTINEL",
                request,
            ).items
            if item.work_type == "TRIGGER"
        )
        record_agent_acknowledgment(
            session,
            s.ResearchAgentAcknowledgmentContractV1(
                agent_role="PORTFOLIO_THESIS_SENTINEL",
                work_type="TRIGGER",
                work_key=old.work_key,
                work_fingerprint=old.work_fingerprint,
                external_update_id="old-completion",
                agent_run_id="old-run",
                actor_id="agent",
                status="COMPLETED",
                observed_at=datetime.now(UTC),
                delivery_channel="API",
            ),
        )
        monkeypatch.setattr(trigger_module, "trigger_document_warnings", original)
        new = next(
            item
            for item in deliver_agent_work(
                session,
                "PORTFOLIO_THESIS_SENTINEL",
                request,
            ).items
            if item.work_type == "TRIGGER"
        )
        assert new.work_key == old.work_key and new.work_fingerprint != old.work_fingerprint
        assert SEC_ISSUER_WARNING in str(new.payload)
        repeated = next(
            item
            for item in deliver_agent_work(
                session,
                "PORTFOLIO_THESIS_SENTINEL",
                request,
            ).items
            if item.work_type == "TRIGGER"
        )
        assert repeated.delivery_id == new.delivery_id
        assert str(doc.id) in str(new.payload)


@pytest.mark.integration
def test_open_trigger_offset_pages_after_derived_state_filter(postgres_engine: Engine) -> None:
    cutoff = datetime.now(UTC).replace(microsecond=0)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Trigger page issuer")
        rows = []
        for index in range(3):
            row = ResearchTrigger(
                company_id=company_id,
                event_key=f"source_document:page-{index}",
                version=1,
                fingerprint=f"{index + 1:x}" * 64,
                trigger_type=ResearchTriggerType.NEW_FILING,
                title=f"Filing {index}",
                reason="Review this source.",
                source_domain="source_document",
                source_record_id=f"page-{index}",
                source_reference=f"https://issuer.example/{index}",
                source_recorded_at=cutoff - timedelta(minutes=index),
                detected_at=cutoff - timedelta(minutes=index),
                source_snapshot={},
                queue_task_id=f"{index + 1:x}" * 64,
                queue_condition_fingerprint=f"{index + 4:x}" * 64,
            )
            session.add(row)
            rows.append(row)
        session.flush()
        page = list_research_triggers(
            session,
            as_of=cutoff,
            company_id=company_id,
            processing_state="OPEN",
            limit=1,
            offset=1,
        )
        assert len(page.triggers) == 1
        assert page.triggers[0].id == rows[1].id
        assert page.triggers[0].processing_state == "OPEN"


@pytest.mark.integration
def test_reported_fundamental_corrections_append_and_supersede_prior_trigger(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Trigger corrected fact issuer")
        batch = ReportedFundamentalBatch(
            provider_id="sec_company_facts",
            provider_schema_version="companyfacts-v1",
            normalizer_version="reported-facts-v1",
            domain="REPORTED_FUNDAMENTALS",
            source_digest="1" * 64,
            query_scope={"cik": "0000000001"},
            observed_at=now - timedelta(hours=1),
            recorded_at=now - timedelta(hours=1),
            provider_summary={"facts": 2},
            reconciliation={"issues": 0},
        )
        session.add(batch)
        session.flush()
        earlier = _reported_fact(
            session,
            company_id,
            batch.id,
            now=now,
            accession="0000000001-26-000001",
            value="100",
            context="POTENTIAL_RESTATEMENT",
            recorded_at=now - timedelta(minutes=40),
        )
        session.add(earlier)
        session.flush()
        first = refresh_research_triggers(session, as_of=now, lookback_days=30)
        assert first.created == 1
        first_id = first.triggers[0].id
        assert first.triggers[0].trigger_type == "REPORTED_FACT_CORRECTION"
        assert "does not establish" in first.triggers[0].reason

        later = _reported_fact(
            session,
            company_id,
            batch.id,
            now=now,
            accession="0000000001-26-000002",
            value="95",
            context="POTENTIAL_RESTATEMENT",
            recorded_at=now - timedelta(minutes=10),
            supersedes_id=earlier.id,
        )
        later.observation_fingerprint = "c" * 64
        session.add(later)
        session.flush()
        second = refresh_research_triggers(session, as_of=now, lookback_days=30)

        assert second.created == 1
        assert session.scalar(select(func.count()).select_from(ResearchTrigger)) == 2
        states = {str(item.id): item.processing_state for item in second.triggers}
        assert states[str(first_id)] == "SUPERSEDED"
        assert any(
            item.source_record_id == str(later.id) and item.processing_state == "OPEN"
            for item in second.triggers
        )


@pytest.mark.integration
def test_backfilled_future_record_is_excluded_from_historical_trigger_refresh(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    historical_cutoff = now - timedelta(days=2)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Trigger as-of issuer")
        document = _source_document(
            session,
            company_id,
            now=now,
            title="Backfilled filing",
            published_at=(historical_cutoff - timedelta(days=1)).date(),
            recorded_at=now - timedelta(hours=1),
        )
        historical = refresh_research_triggers(
            session,
            as_of=historical_cutoff,
            lookback_days=30,
        )
        assert historical.created == 0
        assert (
            session.scalar(
                select(ResearchTrigger).where(ResearchTrigger.source_record_id == str(document.id))
            )
            is None
        )

        current = refresh_research_triggers(session, as_of=now, lookback_days=30)
        assert current.created == 1
        past_read = list_research_triggers(
            session,
            as_of=historical_cutoff,
            company_id=company_id,
        )
        assert past_read.triggers == []


@pytest.mark.integration
def test_superseding_filing_keeps_history_and_removes_old_open_trigger(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    with Session(postgres_engine) as session, session.begin():
        company_id = _active_company(session, "Trigger superseding filing issuer")
        original = _source_document(
            session,
            company_id,
            now=now,
            title="Original quarterly filing",
            published_at=(now - timedelta(days=3)).date(),
            recorded_at=now - timedelta(days=3),
        )
        original_refresh = refresh_research_triggers(session, as_of=now, lookback_days=30)
        assert original_refresh.created == 1
        original_trigger_id = original_refresh.triggers[0].id

        amended = _source_document(
            session,
            company_id,
            now=now,
            title="Corrected quarterly filing",
            published_at=(now + timedelta(days=1)).date(),
            recorded_at=now + timedelta(days=1),
            supersedes_document_id=original.id,
        )
        historical = list_research_triggers(
            session,
            as_of=original_refresh.as_of + timedelta(minutes=1),
            company_id=company_id,
        )
        assert historical.triggers[0].processing_state == "OPEN"
        assert str(original.id) not in _superseded_source_ids(
            session, original_refresh.as_of + timedelta(minutes=1)
        )

        corrected = refresh_research_triggers(
            session, as_of=now + timedelta(days=2), lookback_days=30
        )
        assert corrected.created == 1
        assert session.scalar(select(func.count()).select_from(ResearchTrigger)) == 2
        old_trigger = next(item for item in corrected.triggers if item.id == original_trigger_id)
        new_trigger = next(
            item for item in corrected.triggers if item.source_record_id == str(amended.id)
        )
        assert old_trigger.processing_state == "SUPERSEDED"
        assert new_trigger.processing_state == "OPEN"
        queue = get_research_queue(session, as_of=corrected.as_of)
        assert not any(
            task.task_type == "RESEARCH_TRIGGER"
            and task.sources[0].source_record_id == str(original_trigger_id)
            for task in queue.tasks
        )
