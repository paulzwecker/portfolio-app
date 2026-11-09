"""Research citations must not suppress a filing before the citation was known."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_research_queue import create_active_company

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    CandidatePipelineEvidence,
    CandidatePipelineGateAssessment,
    CandidatePipelineRevision,
    HoldingSnapshot,
    InvestmentThesisClaim,
    InvestmentThesisEvidence,
    InvestmentThesisRevision,
    Lifecycle,
    Portfolio,
    ResearchEvidence,
    ResearchRevision,
    RiskAssessmentEvidence,
    RiskAssessmentFinding,
    RiskAssessmentRevision,
    SourceDocument,
)
from portfolio_api.research_queue import complete_research_queue_task, get_research_queue


def _document(session: Session, company_id: UUID, cutoff: datetime) -> SourceDocument:
    doc = SourceDocument(
        company_id=company_id,
        provider_id="fixture",
        source_name="Issuer",
        external_identifier=str(uuid4()),
        document_type="10-Q",
        title="Quarterly report",
        canonical_url="https://issuer.example/report",
        published_at=cutoff.date(),
        recorded_at=cutoff - timedelta(hours=1),
        data_quality="PASS",
        actor="IMPORT",
    )
    session.add(doc)
    session.flush()
    return doc


def _add_citations(
    session: Session,
    kind: str,
    company_id: UUID,
    documents: list[SourceDocument],
    effective: datetime,
    recorded: datetime,
    *,
    risk_scope: str = "COMPANY",
    risk_times: dict[str, datetime] | None = None,
) -> None:
    if kind == "research":
        revision = ResearchRevision(
            company_id=company_id,
            stream_key="research",
            revision_number=1,
            contract_version="1.0",
            external_revision_id=str(uuid4()),
            author_id="analyst",
            source_id="fixture",
            source_reference="https://issuer.example",
            observed_at=effective,
            recorded_at=recorded,
            status="PUBLISHED",
            rationale="Review the filings.",
            content_fingerprint="a" * 64,
        )
        session.add(revision)
        session.flush()
        session.add_all(
            ResearchEvidence(
                revision_id=revision.id, source_document_id=doc.id, source_name="Issuer"
            )
            for doc in documents
        )
    elif kind == "thesis":
        thesis = InvestmentThesisRevision(
            company_id=company_id,
            stream_key="thesis",
            revision_number=1,
            contract_version="1.0",
            external_revision_id=str(uuid4()),
            author_id="analyst",
            source_id="fixture",
            source_reference="https://issuer.example",
            observed_at=effective,
            recorded_at=recorded,
            status="PUBLISHED",
            thesis_statement="A thesis.",
            confidence="MEDIUM",
            rationale="Review evidence.",
            content_fingerprint="b" * 64,
        )
        session.add(thesis)
        session.flush()
        claim = InvestmentThesisClaim(
            revision_id=thesis.id,
            claim_key="risk",
            claim_type="PRINCIPAL_RISK",
            status="ACTIVE",
            statement="A risk.",
            confidence="MEDIUM",
        )
        session.add(claim)
        session.flush()
        session.add_all(
            InvestmentThesisEvidence(
                claim_id=claim.id,
                relationship="CONTEXT",
                source_document_id=doc.id,
                source_name="Issuer",
            )
            for doc in documents
        )
    elif kind == "candidate":
        candidate = CandidatePipelineRevision(
            company_id=company_id,
            revision_number=1,
            submission_id=uuid4(),
            stage="DISCOVERY",
            unresolved_questions=[],
            actor="LOCAL_USER",
            author_id="analyst",
            rationale="Review",
            effective_at=effective,
            recorded_at=recorded,
            content_fingerprint="c" * 64,
        )
        session.add(candidate)
        session.flush()
        gate = CandidatePipelineGateAssessment(
            revision_id=candidate.id, gate="DISCOVERY", outcome="INCOMPLETE"
        )
        session.add(gate)
        session.flush()
        session.add_all(
            CandidatePipelineEvidence(
                gate_assessment_id=gate.id,
                evidence_type="SOURCE_DOCUMENT",
                relationship="CONTEXT",
                source_document_id=doc.id,
            )
            for doc in documents
        )
    else:
        portfolio = Portfolio(name="Risk fixture", base_currency="EUR", is_demo=False)
        session.add(portfolio)
        session.flush()
        snapshot = HoldingSnapshot(
            portfolio_id=portfolio.id,
            completeness="COMPLETE",
            effective_at=effective,
            recorded_at=recorded,
            actor="IMPORT",
            reason="Fixture",
            source="test",
        )
        session.add(snapshot)
        session.flush()
        times = risk_times or {}
        risk = RiskAssessmentRevision(
            portfolio_id=portfolio.id,
            stream_key="risk",
            revision_number=1,
            contract_version="1.0",
            external_revision_id=str(uuid4()),
            author_id="analyst",
            source_id="fixture",
            source_reference="https://issuer.example",
            authored_at=times.get("authored_at", effective),
            published_at=times.get("published_at", effective),
            recorded_at=times.get("recorded_at", recorded),
            reviewer="reviewer",
            reviewer_note="ok",
            accepted_at=times.get("accepted_at", recorded),
            baseline_status_at_accept="CURRENT",
            baseline_stale_acknowledged=False,
            portfolio_state_contract_version="1.0",
            portfolio_state_fingerprint="sha256:" + "d" * 64,
            holdings_snapshot_id=snapshot.id,
            valuation_as_of=effective,
            coverage_status="COMPLETE",
            summary="Risk",
            rationale="Review",
            content_fingerprint="d" * 64,
        )
        session.add(risk)
        session.flush()
        finding = RiskAssessmentFinding(
            revision_id=risk.id,
            finding_key="risk",
            scope=risk_scope,
            company_id=company_id if risk_scope == "COMPANY" else None,
            category="BUSINESS",
            title="Risk",
            description="Fixture",
            severity="HIGH",
            confidence="MEDIUM",
            status="ACTIVE",
            change_direction="NEW",
            rationale="Review",
        )
        session.add(finding)
        session.flush()
        session.add_all(
            RiskAssessmentEvidence(
                finding_id=finding.id, source_document_id=doc.id, source_name="Issuer"
            )
            for doc in documents
        )
    session.flush()


def _task_sources(session: Session, cutoff: datetime) -> set[str]:
    return {
        source.source_record_id
        for item in get_research_queue(session, as_of=cutoff).tasks
        if item.task_type == "MATERIAL_EVIDENCE"
        for source in item.sources
    }


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["research", "thesis", "candidate", "risk"])
@pytest.mark.parametrize("late", ["effective", "recorded"])
def test_citation_requires_parent_knowledge_and_matching_company(
    postgres_engine: Engine,
    kind: str,
    late: str,
) -> None:
    first_company = create_active_company(postgres_engine, "Citation issuer", Lifecycle.WATCHLIST)
    other_company = create_active_company(postgres_engine, "Other issuer", Lifecycle.WATCHLIST)
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    before, after = cutoff - timedelta(seconds=1), cutoff + timedelta(days=1)
    effective = after if late == "effective" else before
    recorded = after if late == "recorded" else before
    with Session(postgres_engine) as session, session.begin():
        doc = _document(session, first_company, cutoff)
        other = _document(session, other_company, cutoff)
        _add_citations(session, kind, first_company, [doc, other], effective, recorded)
        historical = _task_sources(session, cutoff)
        assert str(doc.id) in historical and str(other.id) in historical
        current = _task_sources(session, after)
        assert str(doc.id) not in current
        assert str(other.id) in current  # A different issuer's citation cannot suppress it.


@pytest.mark.integration
def test_portfolio_risk_can_cite_another_company_source(postgres_engine: Engine) -> None:
    company_id = create_active_company(postgres_engine, "Portfolio source", Lifecycle.WATCHLIST)
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    with Session(postgres_engine) as session, session.begin():
        doc = _document(session, company_id, cutoff)
        _add_citations(session, "risk", company_id, [doc], cutoff, cutoff, risk_scope="PORTFOLIO")
        assert str(doc.id) not in _task_sources(session, cutoff)


@pytest.mark.integration
@pytest.mark.parametrize(
    "late_field", ["authored_at", "published_at", "accepted_at", "recorded_at"]
)
def test_risk_citation_requires_each_parent_time(
    postgres_engine: Engine,
    late_field: str,
) -> None:
    company_id = create_active_company(postgres_engine, "Risk time issuer", Lifecycle.WATCHLIST)
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    after = cutoff + timedelta(days=1)
    with Session(postgres_engine) as session, session.begin():
        doc = _document(session, company_id, cutoff)
        _add_citations(
            session, "risk", company_id, [doc], cutoff, cutoff, risk_times={late_field: after}
        )
        assert str(doc.id) in _task_sources(session, cutoff)
        assert str(doc.id) not in _task_sources(session, after)


@pytest.mark.integration
def test_later_citation_preserves_prior_completion_identity(postgres_engine: Engine) -> None:
    company_id = create_active_company(postgres_engine, "Completed filing", Lifecycle.WATCHLIST)
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    after = cutoff + timedelta(days=1)
    with Session(postgres_engine) as session, session.begin():
        doc = _document(session, company_id, cutoff)
        _add_citations(session, "research", company_id, [doc], after, after)
        task = next(
            item
            for item in get_research_queue(session, as_of=cutoff).tasks
            if item.task_type == "MATERIAL_EVIDENCE"
            and item.sources[0].source_record_id == str(doc.id)
        )
        value = s.ResearchQueueCompletionCreate(
            condition_fingerprint=task.condition_fingerprint,
            completed_by="reviewer",
            completion_note="Checked the source.",
        )
        completed, result = complete_research_queue_task(session, task.task_id, value, as_of=cutoff)
        assert result == "COMPLETED" and completed.status == "COMPLETE"
        assert str(doc.id) not in _task_sources(session, after)
        prior = next(
            item
            for item in get_research_queue(
                session,
                as_of=cutoff,
                include_complete=True,
            ).tasks
            if item.task_id == task.task_id
        )
        assert (
            prior.status == "COMPLETE" and prior.condition_fingerprint == task.condition_fingerprint
        )
        _, replay = complete_research_queue_task(session, task.task_id, value, as_of=after)
        assert replay == "ALREADY_COMPLETED"


@pytest.mark.integration
def test_earlier_citation_remains_known_after_later_revision_omits_it(
    postgres_engine: Engine,
) -> None:
    company_id = create_active_company(postgres_engine, "Citation history", Lifecycle.WATCHLIST)
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    later = cutoff + timedelta(days=1)
    with Session(postgres_engine) as session, session.begin():
        doc = _document(session, company_id, cutoff)
        _add_citations(session, "research", company_id, [doc], cutoff, cutoff)
        session.add(
            ResearchRevision(
                company_id=company_id,
                stream_key="research",
                revision_number=2,
                contract_version="1.0",
                external_revision_id=str(uuid4()),
                author_id="analyst",
                source_id="fixture",
                source_reference="https://issuer.example",
                observed_at=later,
                recorded_at=later,
                status="WITHDRAWN",
                rationale="Withdrawn later.",
                content_fingerprint="e" * 64,
            )
        )
        session.flush()
        assert str(doc.id) not in _task_sources(session, cutoff)
        assert str(doc.id) not in _task_sources(session, later)
