"""Candidate research workflow, kept separate from investment lifecycle decisions."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    CandidateGateEvidenceType,
    CandidateGateOutcome,
    CandidatePipelineEvidence,
    CandidatePipelineGateAssessment,
    CandidatePipelineRevision,
    CandidateResearchDisposition,
    CandidateResearchStage,
    Company,
    CurrentLifecycle,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    InvestmentThesisClaim,
    InvestmentThesisRevision,
    Lifecycle,
    LifecycleEvent,
    ModelOutputSnapshot,
    ModelOutputSnapshotKind,
    RankingDefinition,
    RankingEntry,
    RankingRun,
    RankingType,
    ResearchPriorityInput,
    ResearchRevision,
    ScoreAssessment,
    ScoreAssessmentStatus,
    ScoreDefinition,
    ScoreDimension,
    SourceDocument,
)

GATE_STAGES = (
    CandidateResearchStage.DISCOVERY,
    CandidateResearchStage.INITIAL_SCREEN,
    CandidateResearchStage.QUALITY_DURABILITY,
    CandidateResearchStage.FUNDAMENTAL_COMPOUNDING,
    CandidateResearchStage.DEEP_DIVE,
)
STAGE_ORDER = (*GATE_STAGES, CandidateResearchStage.RESOLUTION)
FIFTEEN_PERCENT = Decimal("0.15")


def record_candidate_pipeline_revision(
    session: Session, company_id: UUID, value: s.CandidatePipelineRevisionCreate
) -> tuple[CandidatePipelineRevision, Literal["RECORDED", "ALREADY_RECORDED"]]:
    company = services.company(session, company_id, lock=True)
    lifecycle = _current_lifecycle(session, company.id)
    if lifecycle != Lifecycle.CANDIDATE:
        raise services.DomainError(
            "Candidate research updates require explicit CANDIDATE lifecycle. "
            "Lifecycle is unchanged.",
            409,
        )

    fingerprint = _fingerprint(value)
    existing = session.scalar(
        select(CandidatePipelineRevision).where(
            CandidatePipelineRevision.company_id == company_id,
            CandidatePipelineRevision.submission_id == value.submission_id,
        )
    )
    if existing is not None:
        if existing.content_fingerprint != fingerprint:
            raise services.DomainError(
                "This submission ID was already used with different Candidate pipeline content.",
                409,
            )
        return existing, "ALREADY_RECORDED"

    previous = session.scalar(
        select(CandidatePipelineRevision)
        .where(CandidatePipelineRevision.company_id == company_id)
        .order_by(CandidatePipelineRevision.revision_number.desc())
        .limit(1)
        .with_for_update()
    )
    actual_base = previous.id if previous else None
    if actual_base != value.expected_revision_id:
        raise services.DomainError(
            "Candidate research changed since it was read; reload before recording a revision.",
            409,
        )
    if previous is None:
        if value.stage != CandidateResearchStage.DISCOVERY:
            raise services.DomainError("Candidate research must begin at Discovery.")
        revision_number = 1
    else:
        revision_number = previous.revision_number + 1
        if value.effective_at < previous.effective_at:
            raise services.DomainError("Candidate research revisions cannot be backdated.")
        _validate_stage_transition(session, previous, value)

    _validate_evidence_ownership(session, company, value)
    _validate_gate_requirements(session, company, value)

    revision = CandidatePipelineRevision(
        company_id=company_id,
        revision_number=revision_number,
        base_revision_id=actual_base,
        submission_id=value.submission_id,
        stage=value.stage.value,
        disposition=value.disposition.value if value.disposition else None,
        next_action=value.next_action,
        unresolved_questions=list(value.unresolved_questions),
        actor=value.actor.value,
        author_id=value.author_id,
        source=value.source,
        rationale=value.rationale,
        effective_at=value.effective_at,
        content_fingerprint=fingerprint,
    )
    session.add(revision)
    session.flush()

    gates_by_stage: dict[CandidateResearchStage, CandidatePipelineGateAssessment] = {}
    for item in value.gates:
        gate = CandidatePipelineGateAssessment(
            revision_id=revision.id,
            gate=item.gate.value,
            outcome=item.outcome.value,
            rationale=item.rationale,
            normalized_per_share_basis_confirmed=item.normalized_per_share_basis_confirmed,
        )
        session.add(gate)
        session.flush()
        gates_by_stage[item.gate] = gate
        for evidence in item.evidence:
            session.add(_evidence_row(gate.id, evidence))
    session.flush()
    return revision, "RECORDED"


def candidate_pipeline_queue(
    session: Session, search: str | None = None
) -> list[s.CandidatePipelineQueueEntry]:
    statement = (
        select(Company, LifecycleEvent)
        .join(CurrentLifecycle, CurrentLifecycle.company_id == Company.id)
        .join(LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id)
        .where(LifecycleEvent.new_state == Lifecycle.CANDIDATE.value)
        .order_by(Company.name, Company.id)
    )
    if search:
        statement = statement.where(Company.name.ilike(f"%{search}%"))
    company_rows = session.execute(statement).all()
    if not company_rows:
        return []
    companies = [company for company, _lifecycle_event in company_rows]
    company_ids = [company.id for company in companies]

    revisions = session.scalars(
        select(CandidatePipelineRevision)
        .where(CandidatePipelineRevision.company_id.in_(company_ids))
        .order_by(
            CandidatePipelineRevision.company_id, CandidatePipelineRevision.revision_number.desc()
        )
    ).all()
    latest_revisions: dict[UUID, CandidatePipelineRevision] = {}
    for revision in revisions:
        latest_revisions.setdefault(revision.company_id, revision)

    revision_ids = [revision.id for revision in latest_revisions.values()]
    gate_rows = (
        session.scalars(
            select(CandidatePipelineGateAssessment).where(
                CandidatePipelineGateAssessment.revision_id.in_(revision_ids)
            )
        ).all()
        if revision_ids
        else []
    )
    gate_outcomes = {(gate.revision_id, gate.gate): gate.outcome for gate in gate_rows}

    priorities = session.scalars(
        select(ResearchPriorityInput)
        .where(ResearchPriorityInput.company_id.in_(company_ids))
        .order_by(
            ResearchPriorityInput.company_id,
            ResearchPriorityInput.recorded_at.desc(),
            ResearchPriorityInput.id,
        )
    ).all()
    latest_priorities: dict[UUID, ResearchPriorityInput] = {}
    for priority in priorities:
        latest_priorities.setdefault(priority.company_id, priority)

    rank_rows = _latest_research_rank_entries(session, company_ids)
    event_by_company = {company.id: event for company, event in company_rows}
    results: list[s.CandidatePipelineQueueEntry] = []
    for company in companies:
        event = event_by_company[company.id]
        company_read = s.CompanyRead(
            id=company.id,
            name=company.name,
            reporting_currency=company.reporting_currency,
            created_at=company.created_at,
            is_demo=company.is_demo,
            lifecycle=Lifecycle(event.new_state),
            lifecycle_event_id=event.id,
        )
        latest_revision = latest_revisions.get(company.id)
        summary = (
            _revision_summary(
                latest_revision,
                gate_outcomes.get(
                    (latest_revision.id, latest_revision.stage),
                    CandidateGateOutcome.NOT_ASSESSED.value,
                ),
            )
            if latest_revision
            else None
        )
        latest_priority = latest_priorities.get(company.id)
        rank = rank_rows.get(company.id)
        results.append(
            s.CandidatePipelineQueueEntry(
                company=company_read,
                status=_research_status(summary),
                stage=summary.stage if summary else None,
                disposition=summary.disposition if summary else None,
                candidate_tier=latest_priority.candidate_tier if latest_priority else None,
                priority_seed=latest_priority.priority_seed if latest_priority else None,
                priority_recorded_at=latest_priority.recorded_at if latest_priority else None,
                research_rank_position=rank.position if rank else None,
                research_rank_status=str(rank.status) if rank else None,
                research_rank_reason=rank.reason if rank else None,
                current_revision=summary,
            )
        )
    return sorted(
        results,
        key=lambda item: (
            item.research_rank_position is None,
            item.research_rank_position or 0,
            item.company.name.casefold(),
            str(item.company.id),
        ),
    )


def company_candidate_pipeline(
    session: Session, company_id: UUID
) -> s.CompanyCandidatePipelineRead:
    company = services.company(session, company_id)
    revision_rows = session.scalars(
        select(CandidatePipelineRevision)
        .where(CandidatePipelineRevision.company_id == company_id)
        .order_by(CandidatePipelineRevision.revision_number.desc())
    ).all()
    history = [_revision_read(session, row) for row in revision_rows]
    queue_entry = _queue_entry(session, company)
    return s.CompanyCandidatePipelineRead(
        company=q.company_read(session, company),
        lifecycle=_current_lifecycle(session, company_id),
        queue_entry=queue_entry,
        history=history,
        evidence_options=_evidence_options(session, company),
    )


def revision_read(
    session: Session, company_id: UUID, revision_id: UUID
) -> s.CandidatePipelineRevisionRead:
    row = session.scalar(
        select(CandidatePipelineRevision).where(
            CandidatePipelineRevision.company_id == company_id,
            CandidatePipelineRevision.id == revision_id,
        )
    )
    if row is None:
        raise services.DomainError("Candidate research revision was not found", 404)
    return _revision_read(session, row)


def _validate_stage_transition(
    session: Session,
    previous: CandidatePipelineRevision,
    value: s.CandidatePipelineRevisionCreate,
) -> None:
    previous_stage = CandidateResearchStage(previous.stage)
    old_index = STAGE_ORDER.index(previous_stage)
    new_index = STAGE_ORDER.index(value.stage)
    if new_index > old_index + 1:
        raise services.DomainError("Candidate research cannot skip a documented stage.")
    if new_index == old_index + 1:
        previous_gate = session.scalar(
            select(CandidatePipelineGateAssessment).where(
                CandidatePipelineGateAssessment.revision_id == previous.id,
                CandidatePipelineGateAssessment.gate == previous.stage,
            )
        )
        if previous_gate is None or previous_gate.outcome != CandidateGateOutcome.PASS.value:
            raise services.DomainError(
                f"The {previous_stage.value.replace('_', ' ').title()} gate must pass "
                "before advancing."
            )

    gate_by_stage = {item.gate: item for item in value.gates}
    if value.stage == CandidateResearchStage.RESOLUTION and value.disposition in {
        CandidateResearchDisposition.WATCHLIST,
        CandidateResearchDisposition.INCUBATE,
    }:
        required = [
            CandidateResearchStage.DISCOVERY,
            CandidateResearchStage.INITIAL_SCREEN,
            CandidateResearchStage.QUALITY_DURABILITY,
            CandidateResearchStage.FUNDAMENTAL_COMPOUNDING,
            CandidateResearchStage.DEEP_DIVE,
        ]
        if any(gate_by_stage[stage].outcome != CandidateGateOutcome.PASS for stage in required):
            raise services.DomainError(
                "Watchlist or Incubate recommendations require every research gate to pass."
            )
    if value.disposition == CandidateResearchDisposition.DROP and not any(
        gate.outcome == CandidateGateOutcome.FAIL for gate in value.gates
    ):
        raise services.DomainError(
            "A Drop recommendation requires at least one explicitly failed research gate."
        )


def _validate_gate_requirements(
    session: Session,
    company: Company,
    value: s.CandidatePipelineRevisionCreate,
) -> None:
    gate_by_stage = {item.gate: item for item in value.gates}
    quality_gate = gate_by_stage[CandidateResearchStage.QUALITY_DURABILITY]
    if quality_gate.outcome == CandidateGateOutcome.PASS:
        latest_score_ids: dict[ScoreDimension, UUID] = {}
        score_rows = session.execute(
            select(ScoreAssessment, ScoreDefinition.dimension)
            .join(ScoreDefinition, ScoreDefinition.id == ScoreAssessment.score_definition_id)
            .where(ScoreAssessment.company_id == company.id, ScoreDefinition.status == "ACTIVE")
            .order_by(ScoreAssessment.recorded_at.desc(), ScoreAssessment.id)
        ).all()
        for assessment, dimension in score_rows:
            parsed = ScoreDimension(dimension)
            latest_score_ids.setdefault(parsed, assessment.id)
        supplied = {
            evidence.reference_id
            for evidence in quality_gate.evidence
            if evidence.evidence_type == CandidateGateEvidenceType.SCORE_ASSESSMENT
        }
        for dimension in (ScoreDimension.DURABILITY_10Y, ScoreDimension.COMPOUNDER_QUALITY):
            assessment_id = latest_score_ids.get(dimension)
            score_assessment = (
                session.get(ScoreAssessment, assessment_id) if assessment_id else None
            )
            if (
                score_assessment is None
                or score_assessment.status != ScoreAssessmentStatus.ASSESSED.value
                or score_assessment.score is None
                or score_assessment.id not in supplied
            ):
                raise services.DomainError(
                    "A passed quality/durability gate must cite current assessed 10Y Durability "
                    "and Compounder Quality scores. No numeric score threshold is inferred."
                )

    compounding_gate = gate_by_stage[CandidateResearchStage.FUNDAMENTAL_COMPOUNDING]
    if compounding_gate.outcome == CandidateGateOutcome.PASS:
        supported_cagrs: list[Decimal] = []
        for evidence in compounding_gate.evidence:
            if evidence.evidence_type == CandidateGateEvidenceType.FINANCIAL_MODEL_OUTPUT:
                output = session.get(FinancialModelOutput, evidence.reference_id)
                if output is None or output.status != "COMPLETE":
                    continue
                revision = session.get(FinancialModelRevision, output.revision_id)
                model = session.get(FinancialModel, revision.model_id) if revision else None
                if (
                    model is not None
                    and model.current_revision_id == output.revision_id
                    and output.forward_fundamental_cagr is not None
                ):
                    supported_cagrs.append(output.forward_fundamental_cagr)
            elif evidence.evidence_type == CandidateGateEvidenceType.LEGACY_MODEL_OUTPUT:
                output_snapshot = session.get(ModelOutputSnapshot, evidence.reference_id)
                if (
                    output_snapshot is not None
                    and output_snapshot.snapshot_kind == ModelOutputSnapshotKind.CURRENT_CONTRACT
                    and output_snapshot.contract_status == "PASS"
                    and output_snapshot.output_quality == "COMPLETE"
                    and output_snapshot.model_currency is not None
                    and output_snapshot.return_methodology_status == "CLASSIFIED"
                    and output_snapshot.forward_fundamental_cagr is not None
                ):
                    supported_cagrs.append(output_snapshot.forward_fundamental_cagr)
        if not supported_cagrs or max(supported_cagrs) < FIFTEEN_PERCENT:
            raise services.DomainError(
                "A passed compounding gate requires a current complete normalized model output "
                "with Forward Fundamental CAGR of at least 15%. Missing or incompatible outputs "
                "remain incomplete; the API does not calculate CAGR."
            )


def _validate_evidence_ownership(
    session: Session, company: Company, value: s.CandidatePipelineRevisionCreate
) -> None:
    for gate in value.gates:
        seen: set[tuple[str, str]] = set()
        for evidence in gate.evidence:
            key = (
                evidence.evidence_type.value,
                str(evidence.reference_id or evidence.source_url),
            )
            if key in seen:
                raise services.DomainError("A gate cannot cite the same evidence twice.")
            seen.add(key)
            reference = evidence.reference_id
            evidence_type = evidence.evidence_type
            valid = False
            if evidence_type == CandidateGateEvidenceType.RESEARCH_REVISION and reference:
                research_revision = session.get(ResearchRevision, reference)
                valid = research_revision is not None and research_revision.company_id == company.id
            elif evidence_type == CandidateGateEvidenceType.THESIS_REVISION and reference:
                thesis_revision = session.get(InvestmentThesisRevision, reference)
                valid = thesis_revision is not None and thesis_revision.company_id == company.id
            elif evidence_type == CandidateGateEvidenceType.THESIS_CLAIM and reference:
                thesis_claim = session.get(InvestmentThesisClaim, reference)
                thesis_revision = (
                    session.get(InvestmentThesisRevision, thesis_claim.revision_id)
                    if thesis_claim
                    else None
                )
                valid = thesis_revision is not None and thesis_revision.company_id == company.id
            elif evidence_type == CandidateGateEvidenceType.SCORE_ASSESSMENT and reference:
                score_assessment = session.get(ScoreAssessment, reference)
                valid = score_assessment is not None and score_assessment.company_id == company.id
            elif evidence_type == CandidateGateEvidenceType.FINANCIAL_MODEL_OUTPUT and reference:
                output = session.get(FinancialModelOutput, reference)
                model_revision = (
                    session.get(FinancialModelRevision, output.revision_id) if output else None
                )
                model = (
                    session.get(FinancialModel, model_revision.model_id) if model_revision else None
                )
                valid = model is not None and model.company_id == company.id
            elif evidence_type == CandidateGateEvidenceType.LEGACY_MODEL_OUTPUT and reference:
                model_snapshot = session.get(ModelOutputSnapshot, reference)
                valid = model_snapshot is not None and model_snapshot.company_id == company.id
            elif evidence_type == CandidateGateEvidenceType.SOURCE_DOCUMENT and reference:
                source_document = session.get(SourceDocument, reference)
                valid = source_document is not None and source_document.company_id == company.id
            elif evidence_type == CandidateGateEvidenceType.SOURCE_URL:
                valid = evidence.source_url is not None
            if not valid:
                raise services.DomainError(
                    f"{evidence_type.value} evidence must resolve to the same canonical company.",
                    404,
                )


def _evidence_row(
    gate_assessment_id: UUID, item: s.CandidatePipelineEvidenceInput
) -> CandidatePipelineEvidence:
    columns: dict[str, UUID | str | None] = {
        "research_revision_id": None,
        "thesis_revision_id": None,
        "thesis_claim_id": None,
        "score_assessment_id": None,
        "financial_model_output_id": None,
        "model_output_snapshot_id": None,
        "source_document_id": None,
        "source_url": None,
    }
    column_by_type = {
        CandidateGateEvidenceType.RESEARCH_REVISION: "research_revision_id",
        CandidateGateEvidenceType.THESIS_REVISION: "thesis_revision_id",
        CandidateGateEvidenceType.THESIS_CLAIM: "thesis_claim_id",
        CandidateGateEvidenceType.SCORE_ASSESSMENT: "score_assessment_id",
        CandidateGateEvidenceType.FINANCIAL_MODEL_OUTPUT: "financial_model_output_id",
        CandidateGateEvidenceType.LEGACY_MODEL_OUTPUT: "model_output_snapshot_id",
        CandidateGateEvidenceType.SOURCE_DOCUMENT: "source_document_id",
    }
    if item.evidence_type == CandidateGateEvidenceType.SOURCE_URL:
        columns["source_url"] = str(item.source_url) if item.source_url else None
    else:
        column = column_by_type[item.evidence_type]
        columns[column] = item.reference_id
    return CandidatePipelineEvidence(
        gate_assessment_id=gate_assessment_id,
        evidence_type=item.evidence_type.value,
        relationship=item.relationship.value,
        note=item.note,
        **columns,
    )


def _revision_read(
    session: Session, row: CandidatePipelineRevision
) -> s.CandidatePipelineRevisionRead:
    gates = session.scalars(
        select(CandidatePipelineGateAssessment)
        .where(CandidatePipelineGateAssessment.revision_id == row.id)
        .order_by(CandidatePipelineGateAssessment.gate)
    ).all()
    gate_reads: list[s.CandidatePipelineGateRead] = []
    for gate in gates:
        evidence_rows = session.scalars(
            select(CandidatePipelineEvidence)
            .where(CandidatePipelineEvidence.gate_assessment_id == gate.id)
            .order_by(CandidatePipelineEvidence.id)
        ).all()
        evidence_reads = [_evidence_read(item) for item in evidence_rows]
        gate_reads.append(
            s.CandidatePipelineGateRead(
                id=gate.id,
                gate=CandidateResearchStage(gate.gate),
                outcome=CandidateGateOutcome(gate.outcome),
                rationale=gate.rationale,
                normalized_per_share_basis_confirmed=gate.normalized_per_share_basis_confirmed,
                evidence=evidence_reads,
            )
        )
    return s.CandidatePipelineRevisionRead(
        id=row.id,
        company_id=row.company_id,
        revision_number=row.revision_number,
        base_revision_id=row.base_revision_id,
        submission_id=row.submission_id,
        stage=CandidateResearchStage(row.stage),
        disposition=(CandidateResearchDisposition(row.disposition) if row.disposition else None),
        next_action=row.next_action,
        unresolved_questions=list(row.unresolved_questions),
        actor=row.actor,
        author_id=row.author_id,
        source=row.source,
        rationale=row.rationale,
        effective_at=row.effective_at,
        recorded_at=row.recorded_at,
        content_fingerprint=row.content_fingerprint,
        gates=gate_reads,
    )


def _evidence_read(row: CandidatePipelineEvidence) -> s.CandidatePipelineEvidenceRead:
    reference_columns = {
        CandidateGateEvidenceType.RESEARCH_REVISION: row.research_revision_id,
        CandidateGateEvidenceType.THESIS_REVISION: row.thesis_revision_id,
        CandidateGateEvidenceType.THESIS_CLAIM: row.thesis_claim_id,
        CandidateGateEvidenceType.SCORE_ASSESSMENT: row.score_assessment_id,
        CandidateGateEvidenceType.FINANCIAL_MODEL_OUTPUT: row.financial_model_output_id,
        CandidateGateEvidenceType.LEGACY_MODEL_OUTPUT: row.model_output_snapshot_id,
        CandidateGateEvidenceType.SOURCE_DOCUMENT: row.source_document_id,
    }
    evidence_type = CandidateGateEvidenceType(row.evidence_type)
    return s.CandidatePipelineEvidenceRead(
        id=row.id,
        evidence_type=evidence_type,
        reference_id=(
            None
            if evidence_type == CandidateGateEvidenceType.SOURCE_URL
            else reference_columns[evidence_type]
        ),
        source_url=row.source_url,
        relationship=row.relationship,
        note=row.note,
    )


def _queue_entry(session: Session, company: Company) -> s.CandidatePipelineQueueEntry:
    latest = session.scalar(
        select(CandidatePipelineRevision)
        .where(CandidatePipelineRevision.company_id == company.id)
        .order_by(CandidatePipelineRevision.revision_number.desc())
        .limit(1)
    )
    current_gate = (
        session.scalar(
            select(CandidatePipelineGateAssessment).where(
                CandidatePipelineGateAssessment.revision_id == latest.id,
                CandidatePipelineGateAssessment.gate == latest.stage,
            )
        )
        if latest and latest.stage != CandidateResearchStage.RESOLUTION.value
        else None
    )
    current_revision = (
        _revision_summary(
            latest,
            current_gate.outcome if current_gate else CandidateGateOutcome.NOT_ASSESSED.value,
        )
        if latest
        else None
    )
    rank = _latest_research_rank_entries(session, [company.id]).get(company.id)
    priority = session.scalar(
        select(ResearchPriorityInput)
        .where(ResearchPriorityInput.company_id == company.id)
        .order_by(ResearchPriorityInput.recorded_at.desc(), ResearchPriorityInput.id)
        .limit(1)
    )
    status = _research_status(current_revision)
    return s.CandidatePipelineQueueEntry(
        company=q.company_read(session, company),
        status=status,
        stage=current_revision.stage if current_revision else None,
        disposition=current_revision.disposition if current_revision else None,
        candidate_tier=priority.candidate_tier if priority else None,
        priority_seed=priority.priority_seed if priority else None,
        priority_recorded_at=priority.recorded_at if priority else None,
        research_rank_position=rank.position if rank else None,
        research_rank_status=str(rank.status) if rank else None,
        research_rank_reason=rank.reason if rank else None,
        current_revision=current_revision,
    )


def _revision_summary(
    row: CandidatePipelineRevision, current_gate_outcome: str
) -> s.CandidatePipelineRevisionSummaryRead:
    return s.CandidatePipelineRevisionSummaryRead(
        id=row.id,
        company_id=row.company_id,
        revision_number=row.revision_number,
        base_revision_id=row.base_revision_id,
        stage=CandidateResearchStage(row.stage),
        disposition=(CandidateResearchDisposition(row.disposition) if row.disposition else None),
        next_action=row.next_action,
        unresolved_questions=list(row.unresolved_questions),
        author_id=row.author_id,
        rationale=row.rationale,
        effective_at=row.effective_at,
        recorded_at=row.recorded_at,
        current_gate_outcome=CandidateGateOutcome(current_gate_outcome),
    )


def _evidence_options(
    session: Session, company: Company
) -> list[s.CandidatePipelineEvidenceOption]:
    options: list[s.CandidatePipelineEvidenceOption] = []

    research_rows = session.scalars(
        select(ResearchRevision)
        .where(ResearchRevision.company_id == company.id)
        .order_by(ResearchRevision.stream_key, ResearchRevision.revision_number.desc())
    ).all()
    latest_research: dict[str, int] = {}
    for row in research_rows:
        latest_research.setdefault(row.stream_key, row.revision_number)
    options.extend(
        s.CandidatePipelineEvidenceOption(
            evidence_type=CandidateGateEvidenceType.RESEARCH_REVISION,
            reference_id=row.id,
            label=f"Research r{row.revision_number} · {row.author_id} · {row.status}",
            current=(
                row.revision_number == latest_research[row.stream_key] and row.status == "PUBLISHED"
            ),
            availability_status=row.status,
        )
        for row in research_rows
    )

    thesis_rows = session.scalars(
        select(InvestmentThesisRevision)
        .where(InvestmentThesisRevision.company_id == company.id)
        .order_by(
            InvestmentThesisRevision.stream_key, InvestmentThesisRevision.revision_number.desc()
        )
    ).all()
    latest_thesis: dict[str, int] = {}
    for thesis_revision in thesis_rows:
        latest_thesis.setdefault(thesis_revision.stream_key, thesis_revision.revision_number)
    current_thesis_ids = {
        thesis_revision.id
        for thesis_revision in thesis_rows
        if thesis_revision.revision_number == latest_thesis[thesis_revision.stream_key]
        and thesis_revision.status == "PUBLISHED"
    }
    options.extend(
        s.CandidatePipelineEvidenceOption(
            evidence_type=CandidateGateEvidenceType.THESIS_REVISION,
            reference_id=thesis_revision.id,
            label=(
                f"Thesis r{thesis_revision.revision_number} · "
                f"{thesis_revision.author_id} · {thesis_revision.status}"
            ),
            current=thesis_revision.id in current_thesis_ids,
            availability_status=thesis_revision.status,
        )
        for thesis_revision in thesis_rows
    )
    claims = session.scalars(
        select(InvestmentThesisClaim)
        .join(
            InvestmentThesisRevision,
            InvestmentThesisRevision.id == InvestmentThesisClaim.revision_id,
        )
        .where(InvestmentThesisRevision.company_id == company.id)
        .order_by(InvestmentThesisClaim.claim_type, InvestmentThesisClaim.claim_key)
    ).all()
    for claim in claims:
        claim_revision = session.get(InvestmentThesisRevision, claim.revision_id)
        options.append(
            s.CandidatePipelineEvidenceOption(
                evidence_type=CandidateGateEvidenceType.THESIS_CLAIM,
                reference_id=claim.id,
                label=(
                    f"Thesis claim · {claim.claim_type.replace('_', ' ').title()} · "
                    f"{claim.statement[:120]}"
                ),
                current=claim_revision is not None and claim_revision.id in current_thesis_ids,
                availability_status=claim.status,
            )
        )

    score_rows = session.execute(
        select(ScoreAssessment, ScoreDefinition.dimension)
        .join(ScoreDefinition, ScoreDefinition.id == ScoreAssessment.score_definition_id)
        .where(ScoreAssessment.company_id == company.id, ScoreDefinition.status == "ACTIVE")
        .order_by(ScoreAssessment.recorded_at.desc(), ScoreAssessment.id)
    ).all()
    latest_scores: dict[ScoreDimension, UUID] = {}
    for assessment, dimension in score_rows:
        latest_scores.setdefault(ScoreDimension(dimension), assessment.id)
    for assessment, dimension in score_rows:
        parsed_dimension = ScoreDimension(dimension)
        score_value = str(assessment.score) if assessment.score is not None else "missing"
        options.append(
            s.CandidatePipelineEvidenceOption(
                evidence_type=CandidateGateEvidenceType.SCORE_ASSESSMENT,
                reference_id=assessment.id,
                label=(
                    f"{parsed_dimension.value.replace('_', ' ').title()} · "
                    f"{score_value} · {assessment.status}"
                ),
                current=latest_scores[parsed_dimension] == assessment.id,
                availability_status=assessment.status,
            )
        )

    native_outputs = session.execute(
        select(FinancialModelOutput, FinancialModelRevision, FinancialModel)
        .join(FinancialModelRevision, FinancialModelRevision.id == FinancialModelOutput.revision_id)
        .join(FinancialModel, FinancialModel.id == FinancialModelRevision.model_id)
        .where(FinancialModel.company_id == company.id)
        .order_by(FinancialModel.created_at, FinancialModelRevision.revision_number.desc())
    ).all()
    for output, model_revision, model in native_outputs:
        cagr = output.forward_fundamental_cagr
        options.append(
            s.CandidatePipelineEvidenceOption(
                evidence_type=CandidateGateEvidenceType.FINANCIAL_MODEL_OUTPUT,
                reference_id=output.id,
                label=(
                    f"{model.model_name} r{model_revision.revision_number} · "
                    "Forward Fundamental CAGR "
                    f"{cagr if cagr is not None else 'unavailable'}"
                ),
                current=model.current_revision_id == model_revision.id,
                availability_status=output.status,
                forward_fundamental_cagr=cagr,
            )
        )

    snapshots = session.scalars(
        select(ModelOutputSnapshot)
        .where(ModelOutputSnapshot.company_id == company.id)
        .order_by(ModelOutputSnapshot.model_key, ModelOutputSnapshot.recorded_at.desc())
    ).all()
    latest_snapshots: dict[str, UUID] = {}
    for model_snapshot in snapshots:
        if model_snapshot.snapshot_kind == ModelOutputSnapshotKind.CURRENT_CONTRACT:
            latest_snapshots.setdefault(model_snapshot.model_key, model_snapshot.id)
    for model_snapshot in snapshots:
        cagr = model_snapshot.forward_fundamental_cagr
        options.append(
            s.CandidatePipelineEvidenceOption(
                evidence_type=CandidateGateEvidenceType.LEGACY_MODEL_OUTPUT,
                reference_id=model_snapshot.id,
                label=(
                    f"{model_snapshot.model_key} · "
                    f"{model_snapshot.contract_status}/{model_snapshot.output_quality} · "
                    "Forward Fundamental CAGR "
                    f"{cagr if cagr is not None else 'unavailable'}"
                ),
                current=latest_snapshots.get(model_snapshot.model_key) == model_snapshot.id,
                availability_status=(
                    f"{model_snapshot.contract_status}/{model_snapshot.output_quality}"
                ),
                forward_fundamental_cagr=cagr,
            )
        )

    documents = session.scalars(
        select(SourceDocument)
        .where(SourceDocument.company_id == company.id)
        .order_by(
            SourceDocument.published_at.desc().nullslast(),
            SourceDocument.title,
        )
    ).all()
    options.extend(
        s.CandidatePipelineEvidenceOption(
            evidence_type=CandidateGateEvidenceType.SOURCE_DOCUMENT,
            reference_id=row.id,
            label=f"{row.document_type} · {row.title}",
            current=True,
            availability_status=row.data_quality,
        )
        for row in documents
    )
    return options


def _latest_research_rank_entries(
    session: Session, company_ids: list[UUID]
) -> dict[UUID, RankingEntry]:
    if not company_ids:
        return {}
    definition = session.scalar(
        select(RankingDefinition)
        .where(
            RankingDefinition.ranking_type == RankingType.RESEARCH,
            RankingDefinition.implementation_status == "READY",
            RankingDefinition.status == "ACTIVE",
        )
        .order_by(RankingDefinition.version.desc())
        .limit(1)
    )
    if definition is None:
        return {}
    run = session.scalar(
        select(RankingRun)
        .where(RankingRun.definition_id == definition.id)
        .order_by(RankingRun.recorded_at.desc(), RankingRun.id.desc())
        .limit(1)
    )
    if run is None:
        return {}
    entries = session.scalars(
        select(RankingEntry).where(
            RankingEntry.run_id == run.id,
            RankingEntry.company_id.in_(company_ids),
        )
    ).all()
    return {entry.company_id: entry for entry in entries}


def _current_lifecycle(session: Session, company_id: UUID) -> Lifecycle | None:
    pointer = session.get(CurrentLifecycle, company_id)
    event = session.get(LifecycleEvent, pointer.event_id) if pointer else None
    return Lifecycle(event.new_state) if event else None


def _research_status(
    revision: s.CandidatePipelineRevisionSummaryRead | None,
) -> str:
    if revision is None:
        return "NOT_STARTED"
    if revision.disposition is not None:
        return "COMPLETE"
    if revision.stage == CandidateResearchStage.RESOLUTION:
        return "BLOCKED"
    if revision.current_gate_outcome in {
        CandidateGateOutcome.INCOMPLETE,
        CandidateGateOutcome.FAIL,
        CandidateGateOutcome.DATA_CHECK,
    }:
        return "BLOCKED"
    return "IN_PROGRESS"


def _fingerprint(value: s.CandidatePipelineRevisionCreate) -> str:
    payload = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
