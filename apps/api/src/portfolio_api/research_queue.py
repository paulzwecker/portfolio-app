"""Deterministic research-review needs composed from canonical histories.

Queue items are derived from source state. Only analyst completions are persisted;
an upstream revision never changes as a side effect of completing a queue item.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    CandidatePipelineEvidence,
    CandidatePipelineGateAssessment,
    CandidatePipelineRevision,
    Company,
    ConsensusEstimateObservation,
    CurrentLifecycle,
    FinancialModel,
    FinancialModelMigrationAssessment,
    FinancialModelOutput,
    FinancialModelRevision,
    FinancialModelRevisionEvidence,
    InvestmentThesisClaim,
    InvestmentThesisEvidence,
    InvestmentThesisRevision,
    Lifecycle,
    LifecycleEvent,
    RankingDefinition,
    RankingEntry,
    RankingRun,
    RankingType,
    ReportedFundamentalObservation,
    ResearchAssessment,
    ResearchEvidence,
    ResearchForecast,
    ResearchQueueCompletion,
    ResearchQueueTaskType,
    ResearchRevision,
    ResearchTrigger,
    RiskAssessmentEvidence,
    RiskAssessmentFinding,
    RiskAssessmentRevision,
    ScoreAssessment,
    ScoreDefinition,
    ScoreDimension,
    SourceDocument,
    ThesisClaimStatus,
    ThesisRevisionStatus,
    ThesisWatchClassification,
)
from portfolio_api.domain.services import DomainError

THESIS_REVIEW_DAYS = 365
SOURCE_DOCUMENT_LOOKBACK_DAYS = 30
ACTIVE_LIFECYCLES = {Lifecycle.PORTFOLIO, Lifecycle.WATCHLIST, Lifecycle.CANDIDATE}
LIFECYCLE_ORDER = {
    Lifecycle.PORTFOLIO: 1,
    Lifecycle.WATCHLIST: 2,
    Lifecycle.CANDIDATE: 3,
}
TASK_ORDER = {
    ResearchQueueTaskType.MODEL_INTEGRITY: 1,
    ResearchQueueTaskType.STRUCTURAL_RISK: 2,
    ResearchQueueTaskType.MODEL_REUNDERWRITE: 3,
    ResearchQueueTaskType.THESIS_QUESTION: 4,
    ResearchQueueTaskType.THESIS_REVIEW: 5,
    ResearchQueueTaskType.RESEARCH_TRIGGER: 6,
    ResearchQueueTaskType.MATERIAL_EVIDENCE: 7,
    ResearchQueueTaskType.WATCHLIST_READINESS: 8,
    ResearchQueueTaskType.CANDIDATE_STAGE: 9,
}


def get_research_queue(
    session: Session,
    *,
    lifecycle: Lifecycle | None = None,
    search: str | None = None,
    include_complete: bool = False,
    as_of: datetime | None = None,
) -> s.ResearchQueueRead:
    cutoff = (as_of or datetime.now(UTC)).astimezone(UTC)
    task_candidates, company_by_id = _derive_tasks(session, cutoff)
    ids = {task.task_id for task in task_candidates}
    completions = (
        list(
            session.scalars(
                select(ResearchQueueCompletion).where(
                    ResearchQueueCompletion.task_id.in_(ids),
                    ResearchQueueCompletion.completed_at <= cutoff,
                )
            )
        )
        if ids
        else []
    )
    completion_by_identity = {
        (item.task_id, item.condition_fingerprint): item for item in completions
    }
    current: list[s.ResearchQueueTask] = []
    for task in task_candidates:
        completion = completion_by_identity.get((task.task_id, task.condition_fingerprint))
        item = task.model_copy(
            update={
                "status": "COMPLETE" if completion is not None else "OPEN",
                "completed_by": completion.completed_by if completion is not None else None,
                "completed_at": completion.completed_at if completion is not None else None,
                "completion_note": (completion.completion_note if completion is not None else None),
                "trigger_classification": (
                    ThesisWatchClassification(completion.trigger_classification)
                    if completion is not None and completion.trigger_classification is not None
                    else None
                ),
            }
        )
        company = company_by_id[item.company.id]
        if lifecycle is not None and company.lifecycle != lifecycle:
            continue
        if search and search.casefold() not in (
            f"{company.name} {item.title} {item.reason}".casefold()
        ):
            continue
        if include_complete or item.status == "OPEN":
            current.append(item)
    current.sort(key=_task_sort_key)
    counts = s.ResearchQueueCounts(
        open=sum(item.status == "OPEN" for item in current),
        complete=sum(item.status == "COMPLETE" for item in current),
        portfolio=sum(item.company.lifecycle == Lifecycle.PORTFOLIO for item in current),
        watchlist=sum(item.company.lifecycle == Lifecycle.WATCHLIST for item in current),
        candidate=sum(item.company.lifecycle == Lifecycle.CANDIDATE for item in current),
    )
    return s.ResearchQueueRead(as_of=cutoff, tasks=current, counts=counts)


def complete_research_queue_task(
    session: Session,
    task_id: str,
    value: s.ResearchQueueCompletionCreate,
    *,
    as_of: datetime | None = None,
) -> tuple[s.ResearchQueueTask, Literal["COMPLETED", "ALREADY_COMPLETED"]]:
    cutoff = (as_of or datetime.now(UTC)).astimezone(UTC)
    existing = session.scalar(
        select(ResearchQueueCompletion).where(
            ResearchQueueCompletion.task_id == task_id,
            ResearchQueueCompletion.condition_fingerprint == value.condition_fingerprint,
        )
    )
    if existing is not None:
        if existing.trigger_classification != (
            value.trigger_classification.value if value.trigger_classification else None
        ):
            raise DomainError(
                "This review condition was already completed with a different trigger "
                "classification",
                409,
            )
        snapshot = s.ResearchQueueTask.model_validate(existing.task_snapshot)
        return _completed_task(snapshot, existing), "ALREADY_COMPLETED"

    tasks, _companies = _derive_tasks(session, cutoff)
    task = next(
        (
            item
            for item in tasks
            if item.task_id == task_id and item.condition_fingerprint == value.condition_fingerprint
        ),
        None,
    )
    if task is None:
        raise DomainError(
            "This research condition has changed or is no longer current. Refresh the queue "
            "before completing it.",
            409,
        )
    if (
        value.trigger_classification is not None
        and task.task_type != ResearchQueueTaskType.RESEARCH_TRIGGER
    ):
        raise DomainError("A Thesis Watch classification applies only to trigger reviews", 422)
    task_snapshot = task.model_dump(mode="json")
    session.add(
        ResearchQueueCompletion(
            company_id=task.company.id,
            task_id=task.task_id,
            condition_fingerprint=task.condition_fingerprint,
            task_type=task.task_type.value,
            task_snapshot=task_snapshot,
            completed_by=value.completed_by,
            completion_note=value.completion_note,
            trigger_classification=(
                value.trigger_classification.value if value.trigger_classification else None
            ),
            completed_at=cutoff,
        )
    )
    session.flush()
    return task.model_copy(
        update={
            "status": "COMPLETE",
            "completed_by": value.completed_by,
            "completed_at": cutoff,
            "completion_note": value.completion_note,
            "trigger_classification": (
                value.trigger_classification if value.trigger_classification else None
            ),
        }
    ), "COMPLETED"


def research_queue_history(
    session: Session, *, limit: int = 100
) -> list[s.ResearchQueueCompletionRead]:
    rows = list(
        session.scalars(
            select(ResearchQueueCompletion)
            .order_by(ResearchQueueCompletion.completed_at.desc(), ResearchQueueCompletion.id)
            .limit(limit)
        )
    )
    results: list[s.ResearchQueueCompletionRead] = []
    for row in rows:
        task = s.ResearchQueueTask.model_validate(row.task_snapshot).model_copy(
            update={
                "status": "COMPLETE",
                "completed_by": row.completed_by,
                "completed_at": row.completed_at,
                "completion_note": row.completion_note,
                "trigger_classification": (
                    ThesisWatchClassification(row.trigger_classification)
                    if row.trigger_classification is not None
                    else None
                ),
            }
        )
        results.append(
            s.ResearchQueueCompletionRead(
                id=row.id,
                task=task,
                completed_by=row.completed_by,
                completion_note=row.completion_note,
                trigger_classification=row.trigger_classification,
                completed_at=row.completed_at,
            )
        )
    return results


def _derive_tasks(
    session: Session, cutoff: datetime
) -> tuple[list[s.ResearchQueueTask], dict[UUID, s.CompanyRead]]:
    rows = session.execute(
        select(Company, LifecycleEvent)
        .join(CurrentLifecycle, CurrentLifecycle.company_id == Company.id)
        .join(LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id)
        .where(LifecycleEvent.new_state.in_([item.value for item in ACTIVE_LIFECYCLES]))
        .order_by(Company.name, Company.id)
    ).all()
    companies = {
        company.id: s.CompanyRead(
            id=company.id,
            name=company.name,
            reporting_currency=company.reporting_currency,
            created_at=company.created_at,
            is_demo=company.is_demo,
            lifecycle=Lifecycle(event.new_state),
            lifecycle_event_id=event.id,
        )
        for company, event in rows
    }
    lifecycle_events = {company.id: event for company, event in rows}
    lifecycle_by_id = {company.id: Lifecycle(event.new_state) for company, event in rows}
    if not companies:
        return [], companies

    company_ids = list(companies)
    candidate_revisions = list(
        session.scalars(
            select(CandidatePipelineRevision)
            .where(CandidatePipelineRevision.company_id.in_(company_ids))
            .order_by(
                CandidatePipelineRevision.company_id,
                CandidatePipelineRevision.revision_number.desc(),
            )
        )
    )
    latest_candidate: dict[UUID, CandidatePipelineRevision] = {}
    for candidate_row in candidate_revisions:
        latest_candidate.setdefault(candidate_row.company_id, candidate_row)
    candidate_revision_ids = [revision.id for revision in latest_candidate.values()]
    candidate_gates = (
        list(
            session.scalars(
                select(CandidatePipelineGateAssessment).where(
                    CandidatePipelineGateAssessment.revision_id.in_(candidate_revision_ids)
                )
            )
        )
        if candidate_revision_ids
        else []
    )
    gates_by_revision: dict[UUID, dict[str, CandidatePipelineGateAssessment]] = {}
    for candidate_gate_row in candidate_gates:
        gates_by_revision.setdefault(candidate_gate_row.revision_id, {})[
            candidate_gate_row.gate
        ] = candidate_gate_row

    thesis_rows = list(
        session.scalars(
            select(InvestmentThesisRevision)
            .where(InvestmentThesisRevision.company_id.in_(company_ids))
            .order_by(
                InvestmentThesisRevision.company_id,
                InvestmentThesisRevision.stream_key,
                InvestmentThesisRevision.revision_number.desc(),
            )
        )
    )
    thesis_current: dict[tuple[UUID, str], InvestmentThesisRevision] = {}
    for thesis_revision in thesis_rows:
        thesis_current.setdefault(
            (thesis_revision.company_id, thesis_revision.stream_key), thesis_revision
        )
    current_theses = list(thesis_current.values())
    claims = (
        list(
            session.scalars(
                select(InvestmentThesisClaim).where(
                    InvestmentThesisClaim.revision_id.in_([item.id for item in current_theses]),
                    InvestmentThesisClaim.claim_type == "UNRESOLVED_QUESTION",
                )
            )
        )
        if current_theses
        else []
    )

    active_models = list(
        session.scalars(
            select(FinancialModel).where(
                FinancialModel.company_id.in_(company_ids),
                FinancialModel.current_revision_id.is_not(None),
            )
        )
    )
    current_model_revisions = (
        list(
            session.scalars(
                select(FinancialModelRevision).where(
                    FinancialModelRevision.id.in_(
                        [
                            model.current_revision_id
                            for model in active_models
                            if model.current_revision_id is not None
                        ]
                    )
                )
            )
        )
        if active_models
        else []
    )
    revision_by_id = {item.id: item for item in current_model_revisions}
    current_outputs = (
        list(
            session.scalars(
                select(FinancialModelOutput).where(
                    FinancialModelOutput.revision_id.in_(list(revision_by_id))
                )
            )
        )
        if revision_by_id
        else []
    )
    output_by_revision = {item.revision_id: item for item in current_outputs}
    migrations = (
        list(
            session.scalars(
                select(FinancialModelMigrationAssessment)
                .where(
                    FinancialModelMigrationAssessment.model_id.in_(
                        [financial_model.id for financial_model in active_models]
                    )
                )
                .order_by(
                    FinancialModelMigrationAssessment.model_id,
                    FinancialModelMigrationAssessment.recorded_at.desc(),
                )
            )
        )
        if active_models
        else []
    )
    latest_migration: dict[UUID, FinancialModelMigrationAssessment] = {}
    for migration_row in migrations:
        latest_migration.setdefault(migration_row.model_id, migration_row)

    model_evidence = (
        list(
            session.scalars(
                select(FinancialModelRevisionEvidence).where(
                    FinancialModelRevisionEvidence.revision_id.in_(revision_by_id)
                )
            )
        )
        if revision_by_id
        else []
    )
    linked_research_ids = {item.research_revision_id for item in model_evidence}
    linked_thesis_ids = {item.thesis_revision_id for item in model_evidence}

    research_rows = list(
        session.scalars(
            select(ResearchRevision)
            .where(ResearchRevision.company_id.in_(company_ids))
            .order_by(
                ResearchRevision.company_id,
                ResearchRevision.stream_key,
                ResearchRevision.revision_number.desc(),
            )
        )
    )
    research_current: dict[tuple[UUID, str], ResearchRevision] = {}
    for research_revision in research_rows:
        research_current.setdefault(
            (research_revision.company_id, research_revision.stream_key), research_revision
        )

    score_rows = list(
        session.execute(
            select(ScoreAssessment, ScoreDefinition.dimension)
            .join(ScoreDefinition, ScoreDefinition.id == ScoreAssessment.score_definition_id)
            .where(
                ScoreAssessment.company_id.in_(company_ids),
                ScoreDefinition.status == "ACTIVE",
            )
            .order_by(ScoreAssessment.recorded_at.desc(), ScoreAssessment.id)
        )
    )
    current_scores: dict[tuple[UUID, ScoreDimension], ScoreAssessment] = {}
    for score_assessment, dimension in score_rows:
        current_scores.setdefault(
            (score_assessment.company_id, ScoreDimension(dimension)), score_assessment
        )

    watchlist_rank = _latest_rank_entries(session, RankingType.WATCHLIST, cutoff)
    research_rank = _latest_rank_entries(session, RankingType.RESEARCH, cutoff)

    risk_revisions = list(
        session.scalars(
            select(RiskAssessmentRevision).order_by(
                RiskAssessmentRevision.portfolio_id,
                RiskAssessmentRevision.stream_key,
                RiskAssessmentRevision.revision_number.desc(),
            )
        )
    )
    risk_current: dict[tuple[UUID, str], RiskAssessmentRevision] = {}
    for risk_row in risk_revisions:
        risk_current.setdefault((risk_row.portfolio_id, risk_row.stream_key), risk_row)
    risk_current_ids = [item.id for item in risk_current.values()]
    risk_findings = (
        list(
            session.scalars(
                select(RiskAssessmentFinding).where(
                    RiskAssessmentFinding.revision_id.in_(risk_current_ids),
                    RiskAssessmentFinding.scope == "COMPANY",
                    RiskAssessmentFinding.company_id.in_(company_ids),
                    RiskAssessmentFinding.status == "UNDER_REVIEW",
                    RiskAssessmentFinding.severity.in_(["HIGH", "CRITICAL"]),
                )
            )
        )
        if risk_current_ids
        else []
    )
    risk_revision_by_id = {item.id: item for item in risk_current.values()}

    docs = list(
        session.scalars(
            select(SourceDocument).where(
                SourceDocument.company_id.in_(company_ids),
                SourceDocument.document_type != "OTHER",
                SourceDocument.data_quality == "PASS",
            )
        )
    )
    superseded_document_ids = set(
        session.scalars(
            select(SourceDocument.supersedes_document_id).where(
                SourceDocument.supersedes_document_id.is_not(None)
            )
        ).all()
    )
    superseded_observation_ids = {
        str(item)
        for item in session.scalars(
            select(ReportedFundamentalObservation.supersedes_observation_id).where(
                ReportedFundamentalObservation.supersedes_observation_id.is_not(None)
            )
        ).all()
    }
    superseded_observation_ids.update(
        str(item)
        for item in session.scalars(
            select(ConsensusEstimateObservation.supersedes_observation_id).where(
                ConsensusEstimateObservation.supersedes_observation_id.is_not(None)
            )
        ).all()
    )
    docs = [item for item in docs if item.id not in superseded_document_ids]
    referenced_document_ids: set[UUID] = set()
    for evidence_model in (
        InvestmentThesisEvidence,
        ResearchEvidence,
        CandidatePipelineEvidence,
        RiskAssessmentEvidence,
    ):
        referenced_document_ids.update(
            session.scalars(
                select(evidence_model.source_document_id).where(
                    evidence_model.source_document_id.is_not(None),
                    evidence_model.source_document_id.in_([document.id for document in docs]),
                )
            )
        )

    research_evidence = (
        list(
            session.scalars(
                select(ResearchEvidence).where(
                    ResearchEvidence.revision_id.in_(
                        [item.id for item in research_current.values()]
                    )
                )
            )
        )
        if research_current
        else []
    )
    candidate_evidence = (
        list(
            session.scalars(
                select(CandidatePipelineEvidence).where(
                    CandidatePipelineEvidence.research_revision_id.is_not(None),
                    CandidatePipelineEvidence.research_revision_id.in_(
                        [item.id for item in research_current.values()]
                    ),
                )
            )
        )
        if research_current
        else []
    )
    linked_research_ids.update(item.revision_id for item in research_evidence)
    linked_research_ids.update(item.research_revision_id for item in candidate_evidence)

    tasks: dict[tuple[str, str], s.ResearchQueueTask] = {}

    def add(
        company_id: UUID,
        task_type: ResearchQueueTaskType,
        source_key: str,
        condition: object,
        *,
        title: str,
        reason: str,
        trigger_rule: str,
        judgment_required: bool,
        owner_workflow: Literal["LOCAL_ANALYST", "RESEARCH_AGENT", "DATA_REVIEW"],
        sources: list[s.ResearchQueueSource],
        due_at: datetime | None = None,
        rank_position: int | None = None,
    ) -> None:
        company = companies[company_id]
        task_id = _digest(f"{task_type.value}|{company_id}|{source_key}")
        fingerprint = _digest(condition)
        if not sources:
            lifecycle_event = lifecycle_events[company_id]
            sources = [
                s.ResearchQueueSource(
                    source_type="LIFECYCLE",
                    source_record_id=str(lifecycle_event.id),
                    title=f"Lifecycle set to {lifecycle_by_id[company_id].value}",
                    effective_at=lifecycle_event.effective_at,
                    recorded_at=lifecycle_event.recorded_at,
                )
            ]
        effective_times = [source.effective_at for source in sources if source.effective_at]
        recorded_times = [source.recorded_at for source in sources if source.recorded_at]
        published_dates = [source.published_at for source in sources if source.published_at]
        task = s.ResearchQueueTask(
            task_id=task_id,
            condition_fingerprint=fingerprint,
            company=company,
            task_type=task_type,
            title=title,
            reason=reason,
            lifecycle_priority=LIFECYCLE_ORDER[lifecycle_by_id[company_id]],
            research_rank_position=rank_position,
            trigger_rule=trigger_rule,
            judgment_required=judgment_required,
            owner_workflow=owner_workflow,
            source_effective_at=max(effective_times) if effective_times else None,
            source_published_at=max(published_dates) if published_dates else None,
            source_recorded_at=max(recorded_times) if recorded_times else None,
            due_at=due_at,
            sources=sources,
        )
        tasks[(task_id, fingerprint)] = task

    # Candidate gates have no historical legacy source, so no stage is inferred.
    for company_id, company in companies.items():
        if company.lifecycle != Lifecycle.CANDIDATE:
            continue
        candidate_revision = latest_candidate.get(company_id)
        if candidate_revision is None:
            reason = (
                "No Candidate research-pipeline revision has been recorded. Start with Discovery."
            )
            source = s.ResearchQueueSource(
                source_type="LIFECYCLE",
                source_record_id=str(lifecycle_events[company_id].id),
                title="Candidate lifecycle event",
                effective_at=lifecycle_events[company_id].effective_at,
                recorded_at=lifecycle_events[company_id].recorded_at,
            )
            condition: object = {"lifecycle_event_id": lifecycle_events[company_id].id}
            stage = "Discovery"
        else:
            candidate_gate = gates_by_revision.get(candidate_revision.id, {}).get(
                candidate_revision.stage
            )
            outcome = candidate_gate.outcome if candidate_gate is not None else "NOT_ASSESSED"
            stage = candidate_revision.stage.replace("_", " ").title()
            questions = list(candidate_revision.unresolved_questions or [])
            if candidate_revision.stage == "RESOLUTION" and candidate_revision.disposition:
                reason = (
                    f"Research recorded a {candidate_revision.disposition} recommendation. "
                    "Review it and make any lifecycle change through the separate lifecycle "
                    "workflow."
                )
                stage = "Recommendation"
            else:
                reason = candidate_revision.next_action or (
                    f"The current {stage} gate is {outcome}. Record the next evidence-based step."
                )
                if outcome != "PASS" and not candidate_revision.next_action:
                    reason = (
                        f"The current {stage} gate is {outcome}. "
                        "Complete or resolve the gate with evidence."
                    )
            if questions:
                reason += " Unresolved questions: " + "; ".join(questions[:3])
            source = s.ResearchQueueSource(
                source_type="CANDIDATE_PIPELINE_REVISION",
                source_record_id=str(candidate_revision.id),
                title=f"Candidate research revision {candidate_revision.revision_number}",
                effective_at=candidate_revision.effective_at,
                recorded_at=candidate_revision.recorded_at,
            )
            condition = {
                "revision_id": candidate_revision.id,
                "content_fingerprint": candidate_revision.content_fingerprint,
                "current_gate": outcome,
            }
        rank = research_rank.get(company_id)
        title = (
            "Complete Candidate deep dive"
            if stage == "Deep Dive"
            else (
                "Review Candidate research recommendation"
                if stage == "Recommendation"
                else f"Advance Candidate research: {stage}"
            )
        )
        add(
            company_id,
            ResearchQueueTaskType.CANDIDATE_STAGE,
            f"candidate-pipeline:{company_id}",
            condition,
            title=title,
            reason=reason,
            trigger_rule="Current Candidate pipeline has no terminal recommendation.",
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=[source],
            rank_position=rank.position if rank is not None else None,
        )

    theses_by_company: dict[UUID, list[InvestmentThesisRevision]] = {}
    for thesis_revision in current_theses:
        theses_by_company.setdefault(thesis_revision.company_id, []).append(thesis_revision)
    for company_id, company in companies.items():
        if company.lifecycle == Lifecycle.CANDIDATE:
            continue
        current_published = [
            thesis_revision
            for thesis_revision in theses_by_company.get(company_id, [])
            if thesis_revision.status == ThesisRevisionStatus.PUBLISHED.value
        ]
        if not current_published:
            latest_revision = max(
                theses_by_company.get(company_id, []),
                key=lambda item: item.recorded_at,
                default=None,
            )
            thesis_sources = (
                [
                    s.ResearchQueueSource(
                        source_type="INVESTMENT_THESIS_REVISION",
                        source_record_id=str(latest_revision.id),
                        title=f"Thesis {latest_revision.status.lower()}",
                        effective_at=latest_revision.observed_at,
                        recorded_at=latest_revision.recorded_at,
                    )
                ]
                if latest_revision
                else []
            )
            add(
                company_id,
                ResearchQueueTaskType.THESIS_REVIEW,
                f"thesis-current:{company_id}",
                {
                    "lifecycle_event_id": lifecycle_events[company_id].id,
                    "latest_thesis_revision": latest_revision.id if latest_revision else None,
                    "status": latest_revision.status if latest_revision else "MISSING",
                },
                title="Create or restore the investment thesis",
                reason=(
                    "There is no current published thesis revision. Record the current view, "
                    "key claims, uncertainty, and source evidence."
                ),
                trigger_rule="No current published investment-thesis revision exists.",
                judgment_required=True,
                owner_workflow="LOCAL_ANALYST",
                sources=thesis_sources,
            )
        else:
            latest_thesis = max(current_published, key=lambda item: item.recorded_at)
            due_at = latest_thesis.recorded_at + timedelta(days=THESIS_REVIEW_DAYS)
            if cutoff >= due_at:
                add(
                    company_id,
                    ResearchQueueTaskType.THESIS_REVIEW,
                    f"thesis-current:{company_id}",
                    {"latest_published_revision_id": latest_thesis.id},
                    title="Review the investment thesis",
                    reason=(
                        f"The latest published thesis has been recorded for at least "
                        f"{THESIS_REVIEW_DAYS} days. Confirm or revise the thesis and its evidence."
                    ),
                    trigger_rule=(
                        f"No published thesis revision recorded in {THESIS_REVIEW_DAYS} days."
                    ),
                    judgment_required=True,
                    owner_workflow="LOCAL_ANALYST",
                    sources=[
                        s.ResearchQueueSource(
                            source_type="INVESTMENT_THESIS_REVISION",
                            source_record_id=str(latest_thesis.id),
                            title=f"Published thesis revision {latest_thesis.revision_number}",
                            source_url=latest_thesis.source_reference,
                            effective_at=latest_thesis.observed_at,
                            recorded_at=latest_thesis.recorded_at,
                        )
                    ],
                    due_at=due_at,
                )

    for claim in claims:
        if claim.status in {ThesisClaimStatus.RESOLVED.value, ThesisClaimStatus.INVALIDATED.value}:
            continue
        thesis_revision_for_claim = next(
            (item for item in current_theses if item.id == claim.revision_id), None
        )
        if (
            thesis_revision_for_claim is None
            or thesis_revision_for_claim.status != ThesisRevisionStatus.PUBLISHED.value
        ):
            continue
        company_id = thesis_revision_for_claim.company_id
        add(
            company_id,
            ResearchQueueTaskType.THESIS_QUESTION,
            f"thesis-question:{thesis_revision_for_claim.stream_key}:{claim.claim_key}",
            {
                "thesis_revision_id": thesis_revision_for_claim.id,
                "claim_id": claim.id,
                "status": claim.status,
            },
            title="Resolve an open thesis question",
            reason=claim.statement,
            trigger_rule="The latest published thesis contains an unresolved question.",
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=[
                s.ResearchQueueSource(
                    source_type="THESIS_CLAIM",
                    source_record_id=str(claim.id),
                    title=claim.claim_key,
                    source_url=thesis_revision_for_claim.source_reference,
                    effective_at=thesis_revision_for_claim.observed_at,
                    recorded_at=thesis_revision_for_claim.recorded_at,
                )
            ],
        )

    # Recent primary publications without a canonical research citation are review needs.
    recent_cutoff = cutoff.date() - timedelta(days=SOURCE_DOCUMENT_LOOKBACK_DAYS)
    for document in docs:
        published = document.published_at or document.filed_at
        if (
            published is None
            or published < recent_cutoff
            or published > cutoff.date()
            or document.id in referenced_document_ids
        ):
            continue
        add(
            document.company_id,
            ResearchQueueTaskType.MATERIAL_EVIDENCE,
            f"source-document:{document.id}",
            {
                "source_document_id": document.id,
                "document_type": document.document_type,
                "published_at": published,
                "canonical_url": document.canonical_url,
            },
            title="Review a new primary source",
            reason=(
                f"{document.document_type} '{document.title}' is not linked to a canonical "
                "research, thesis, Candidate-gate, or risk assessment."
            ),
            trigger_rule=(
                "Unreferenced PASS-quality source published within "
                f"{SOURCE_DOCUMENT_LOOKBACK_DAYS} days."
            ),
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=[
                s.ResearchQueueSource(
                    source_type="SOURCE_DOCUMENT",
                    source_record_id=str(document.id),
                    title=document.title,
                    source_url=document.canonical_url,
                    published_at=published,
                    recorded_at=document.recorded_at,
                )
            ],
        )

    # Latest published agent research not yet linked into a Candidate gate or model revision.
    for research_revision in research_current.values():
        if (
            research_revision.company_id not in companies
            or research_revision.status != "PUBLISHED"
            or research_revision.id in linked_research_ids
        ):
            continue
        has_content = session.scalar(
            select(ResearchForecast.id)
            .where(ResearchForecast.revision_id == research_revision.id)
            .limit(1)
        ) or session.scalar(
            select(ResearchAssessment.id)
            .where(ResearchAssessment.revision_id == research_revision.id)
            .limit(1)
        )
        if not has_content:
            continue
        add(
            research_revision.company_id,
            ResearchQueueTaskType.MATERIAL_EVIDENCE,
            f"research-revision:{research_revision.id}",
            {
                "research_revision_id": research_revision.id,
                "content_fingerprint": research_revision.content_fingerprint,
            },
            title="Review a published research update",
            reason=(
                f"The latest '{research_revision.stream_key}' research revision "
                "has not been cited by "
                "a current Candidate gate or accepted model revision."
            ),
            trigger_rule=(
                "Latest published research revision has not been linked to downstream review."
            ),
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=[
                s.ResearchQueueSource(
                    source_type="RESEARCH_REVISION",
                    source_record_id=str(research_revision.id),
                    title=(
                        f"{research_revision.stream_key} revision "
                        f"{research_revision.revision_number}"
                    ),
                    source_url=research_revision.source_reference,
                    effective_at=research_revision.observed_at,
                    recorded_at=research_revision.recorded_at,
                )
            ],
        )

    # When accepted research arrives after underwriting, put an explicit model review in queue.
    for financial_model in active_models:
        model_revision_id = financial_model.current_revision_id
        if model_revision_id is None:
            continue
        current_revision = revision_by_id.get(model_revision_id)
        if current_revision is None:
            continue
        relevant_sources: list[s.ResearchQueueSource] = []
        source_ids: list[str] = []
        for thesis_revision in current_theses:
            if thesis_revision.company_id != financial_model.company_id:
                continue
            if (
                thesis_revision.recorded_at <= current_revision.recorded_at
                or thesis_revision.id in linked_thesis_ids
            ):
                continue
            relevant_sources.append(
                s.ResearchQueueSource(
                    source_type="INVESTMENT_THESIS_REVISION",
                    source_record_id=str(thesis_revision.id),
                    title=(
                        f"{thesis_revision.stream_key} revision {thesis_revision.revision_number}"
                    ),
                    source_url=thesis_revision.source_reference,
                    effective_at=thesis_revision.observed_at,
                    recorded_at=thesis_revision.recorded_at,
                )
            )
            source_ids.append(str(thesis_revision.id))
        for research_revision in research_current.values():
            if research_revision.company_id != financial_model.company_id:
                continue
            if (
                research_revision.recorded_at <= current_revision.recorded_at
                or research_revision.id in linked_research_ids
            ):
                continue
            relevant_sources.append(
                s.ResearchQueueSource(
                    source_type="RESEARCH_REVISION",
                    source_record_id=str(research_revision.id),
                    title=(
                        f"{research_revision.stream_key} revision "
                        f"{research_revision.revision_number}"
                    ),
                    source_url=research_revision.source_reference,
                    effective_at=research_revision.observed_at,
                    recorded_at=research_revision.recorded_at,
                )
            )
            source_ids.append(str(research_revision.id))
        is_due = cutoff >= current_revision.recorded_at + timedelta(days=THESIS_REVIEW_DAYS)
        if not relevant_sources and not is_due:
            continue
        if not relevant_sources:
            relevant_sources.append(
                s.ResearchQueueSource(
                    source_type="FINANCIAL_MODEL_REVISION",
                    source_record_id=str(current_revision.id),
                    title=f"Accepted model revision {current_revision.revision_number}",
                    effective_at=current_revision.effective_at,
                    recorded_at=current_revision.recorded_at,
                )
            )
        add(
            financial_model.company_id,
            ResearchQueueTaskType.MODEL_REUNDERWRITE,
            f"model-reunderwrite:{financial_model.id}",
            {
                "model_id": financial_model.id,
                "model_revision_id": current_revision.id,
                "unreviewed_research_ids": sorted(source_ids),
                "periodic_review_due": is_due,
            },
            title="Re-underwrite the accepted financial model",
            reason=(
                "New accepted research or thesis evidence postdates the current model revision. "
                "Review whether deterministic model assumptions still represent the current view."
                if source_ids
                else (
                    "The current model revision has been recorded for at least "
                    f"{THESIS_REVIEW_DAYS} days."
                )
            ),
            trigger_rule=(
                "A published research/thesis revision recorded after the current model and not "
                "cited by that model revision; or the documented annual review interval."
            ),
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=relevant_sources,
            due_at=(current_revision.recorded_at + timedelta(days=THESIS_REVIEW_DAYS))
            if is_due
            else None,
        )

    # Latest mapping/output states are actionable source/model-integrity blockers.
    for financial_model in active_models:
        model_revision_id = financial_model.current_revision_id
        if model_revision_id is None:
            continue
        model_revision = revision_by_id.get(model_revision_id)
        if model_revision is None:
            continue
        migration_assessment = latest_migration.get(financial_model.id)
        output = output_by_revision.get(model_revision.id)
        problems: list[str] = []
        integrity_sources: list[s.ResearchQueueSource] = []
        if migration_assessment is not None and migration_assessment.status != "PARITY_PASS":
            problems.append(f"Latest migration/parity state is {migration_assessment.status}.")
            integrity_sources.append(
                s.ResearchQueueSource(
                    source_type="MODEL_MIGRATION_ASSESSMENT",
                    source_record_id=str(migration_assessment.id),
                    title=f"Model mapping state: {migration_assessment.status}",
                    recorded_at=migration_assessment.recorded_at,
                )
            )
        if output is None:
            problems.append("The current accepted revision has no normalized output record.")
        elif output.status != "COMPLETE":
            problems.append(
                f"The current normalized output is {output.status}; "
                f"price state is {output.price_status}."
            )
            integrity_sources.append(
                s.ResearchQueueSource(
                    source_type="FINANCIAL_MODEL_OUTPUT",
                    source_record_id=str(output.id),
                    title=f"Model output {output.status} / {output.price_status}",
                    effective_at=output.price_effective_at,
                    recorded_at=model_revision.recorded_at,
                )
            )
        if not problems:
            continue
        if not integrity_sources:
            integrity_sources.append(
                s.ResearchQueueSource(
                    source_type="FINANCIAL_MODEL_REVISION",
                    source_record_id=str(model_revision.id),
                    title=f"Accepted model revision {model_revision.revision_number}",
                    effective_at=model_revision.effective_at,
                    recorded_at=model_revision.recorded_at,
                )
            )
        add(
            financial_model.company_id,
            ResearchQueueTaskType.MODEL_INTEGRITY,
            f"model-integrity:{financial_model.id}",
            {
                "model_id": financial_model.id,
                "revision_id": model_revision.id,
                "assessment_id": (migration_assessment.id if migration_assessment else None),
                "assessment_status": (
                    migration_assessment.status if migration_assessment else None
                ),
                "output_id": output.id if output else None,
                "output_status": output.status if output else None,
                "price_status": output.price_status if output else None,
            },
            title="Review a model source or output check",
            reason=" ".join(problems),
            trigger_rule=(
                "Current model migration state is not parity-pass or output is incomplete/missing."
            ),
            judgment_required=False,
            owner_workflow="DATA_REVIEW",
            sources=integrity_sources,
        )

    for finding in risk_findings:
        risk_revision = risk_revision_by_id.get(finding.revision_id)
        if risk_revision is None or finding.company_id is None:
            continue
        add(
            finding.company_id,
            ResearchQueueTaskType.STRUCTURAL_RISK,
            f"risk-finding:{finding.finding_key}",
            {
                "risk_revision_id": risk_revision.id,
                "finding_id": finding.id,
                "finding_key": finding.finding_key,
                "status": finding.status,
                "severity": finding.severity,
            },
            title=f"Reassess {finding.severity.lower()} structural risk",
            reason=finding.title + ": " + finding.description,
            trigger_rule=(
                "Latest accepted risk assessment retains an UNDER_REVIEW HIGH/CRITICAL "
                "company finding."
            ),
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=[
                s.ResearchQueueSource(
                    source_type="RISK_ASSESSMENT_FINDING",
                    source_record_id=str(finding.id),
                    title=finding.title,
                    effective_at=risk_revision.authored_at,
                    recorded_at=risk_revision.recorded_at,
                )
            ],
        )

    # Readiness review is a human checkpoint over the current canonical input set,
    # not an automatic rank or a lifecycle/target decision.
    for company_id, company in companies.items():
        if company.lifecycle != Lifecycle.WATCHLIST:
            continue
        rank = watchlist_rank.get(company_id)
        scores = [
            current_scores.get((company_id, ScoreDimension.DURABILITY_10Y)),
            current_scores.get((company_id, ScoreDimension.COMPOUNDER_QUALITY)),
        ]
        model_rows = [
            financial_model
            for financial_model in active_models
            if financial_model.company_id == company_id
        ]
        score_missing = [
            name
            for name, score in zip(("10Y Durability", "Compounder Quality"), scores, strict=True)
            if score is None or score.status != "ASSESSED" or score.score is None
        ]
        model_missing = not model_rows or any(
            financial_model.current_revision_id is None
            or output_by_revision.get(financial_model.current_revision_id) is None
            or output_by_revision[financial_model.current_revision_id].status != "COMPLETE"
            for financial_model in model_rows
        )
        reasons = []
        if score_missing:
            reasons.append(
                "Missing or unavailable current score assessments: "
                + ", ".join(score_missing)
                + "."
            )
        if model_missing:
            reasons.append(
                "A complete current native model output is not available for every "
                "accepted native model."
            )
        if rank is None:
            reasons.append(
                "No canonical Watchlist Rank entry is available for the current research inputs."
            )
        elif rank.status != "RANKED":
            reasons.append(f"Watchlist Rank is {rank.status}: {rank.reason}")
        if not reasons:
            reasons.append(
                "Available canonical inputs have not yet received an explicit human assessment "
                "of research completeness and portfolio readiness."
            )
        input_ids = [str(item.id) for item in scores if item is not None]
        input_ids.extend(
            str(financial_model.current_revision_id)
            for financial_model in model_rows
            if financial_model.current_revision_id
        )
        input_ids.extend(str(item.id) for item in theses_by_company.get(company_id, []))
        input_ids.extend(
            str(item.id) for item in research_current.values() if item.company_id == company_id
        )
        source_rows: list[s.ResearchQueueSource] = []
        for score in scores:
            if score is not None:
                source_rows.append(
                    s.ResearchQueueSource(
                        source_type="SCORE_ASSESSMENT",
                        source_record_id=str(score.id),
                        title=f"Score assessment {score.status}",
                        effective_at=score.effective_at,
                        recorded_at=score.recorded_at,
                    )
                )
        for financial_model in model_rows:
            model_revision_id = financial_model.current_revision_id
            model_revision = (
                revision_by_id.get(model_revision_id) if model_revision_id is not None else None
            )
            output = (
                output_by_revision.get(model_revision_id) if model_revision_id is not None else None
            )
            if model_revision is not None:
                source_rows.append(
                    s.ResearchQueueSource(
                        source_type="FINANCIAL_MODEL_REVISION",
                        source_record_id=str(model_revision.id),
                        title=(
                            f"{financial_model.model_name} revision "
                            f"{model_revision.revision_number}"
                        ),
                        effective_at=model_revision.effective_at,
                        recorded_at=model_revision.recorded_at,
                    )
                )
            if output is not None:
                source_rows.append(
                    s.ResearchQueueSource(
                        source_type="FINANCIAL_MODEL_OUTPUT",
                        source_record_id=str(output.id),
                        title=f"Model output {output.status} / {output.price_status}",
                        effective_at=output.price_effective_at,
                        recorded_at=model_revision.recorded_at if model_revision else None,
                    )
                )
        source_rows.extend(
            s.ResearchQueueSource(
                source_type="INVESTMENT_THESIS_REVISION",
                source_record_id=str(item.id),
                title=f"Thesis revision {item.revision_number}",
                source_url=item.source_reference,
                effective_at=item.observed_at,
                recorded_at=item.recorded_at,
            )
            for item in theses_by_company.get(company_id, [])
        )
        source_rows.extend(
            s.ResearchQueueSource(
                source_type="RESEARCH_REVISION",
                source_record_id=str(item.id),
                title=f"{item.stream_key} revision {item.revision_number}",
                source_url=item.source_reference,
                effective_at=item.observed_at,
                recorded_at=item.recorded_at,
            )
            for item in research_current.values()
            if item.company_id == company_id
        )
        if rank is not None:
            source_rows.append(
                s.ResearchQueueSource(
                    source_type="WATCHLIST_RANK_ENTRY",
                    source_record_id=str(rank.id),
                    title=f"Watchlist Rank {rank.status}",
                    recorded_at=None,
                )
            )
        add(
            company_id,
            ResearchQueueTaskType.WATCHLIST_READINESS,
            f"watchlist-readiness:{company_id}",
            {
                "lifecycle_event_id": lifecycle_events[company_id].id,
                "input_ids": sorted(input_ids),
                "rank_status": rank.status if rank else None,
                "rank_reason": rank.reason if rank else None,
                "rank_snapshot": rank.input_snapshot if rank else None,
                "missing_scores": score_missing,
                "model_missing": model_missing,
            },
            title="Assess Watchlist research readiness",
            reason=" ".join(reasons),
            trigger_rule="One readiness review per unchanged canonical input fingerprint.",
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=source_rows,
            rank_position=None,
        )

    # Persisted evidence events become queue work only after an explicit trigger refresh.
    # A recent unlinked filing already has the 7H MATERIAL_EVIDENCE task; reuse that card.
    trigger_rows = list(
        session.scalars(
            select(ResearchTrigger)
            .where(
                ResearchTrigger.detected_at <= cutoff,
                ResearchTrigger.source_recorded_at <= cutoff,
                ResearchTrigger.company_id.in_(company_ids),
            )
            .order_by(
                ResearchTrigger.event_key,
                ResearchTrigger.version.desc(),
                ResearchTrigger.detected_at.desc(),
            )
        )
    )
    latest_triggers: dict[str, ResearchTrigger] = {}
    for trigger in trigger_rows:
        latest_triggers.setdefault(trigger.event_key, trigger)
    for trigger in latest_triggers.values():
        if trigger.company_id not in companies:
            continue
        if trigger.source_record_id in superseded_observation_ids or trigger.source_record_id in {
            str(item) for item in superseded_document_ids
        }:
            continue
        existing_filing_task = next(
            (
                task
                for task in tasks.values()
                if task.task_type == ResearchQueueTaskType.MATERIAL_EVIDENCE
                and any(
                    source.source_type == "SOURCE_DOCUMENT"
                    and source.source_record_id == trigger.source_record_id
                    for source in task.sources
                )
            ),
            None,
        )
        if trigger.source_domain == "source_document" and existing_filing_task is not None:
            continue
        add(
            trigger.company_id,
            ResearchQueueTaskType.RESEARCH_TRIGGER,
            f"research-trigger:{trigger.id}",
            {"trigger_id": trigger.id, "fingerprint": trigger.fingerprint},
            title=trigger.title,
            reason=trigger.reason,
            trigger_rule=(
                f"Canonical {trigger.trigger_type.replace('_', ' ').lower()} event; "
                "review the linked source and record an explicit completion."
            ),
            judgment_required=True,
            owner_workflow="LOCAL_ANALYST",
            sources=[
                s.ResearchQueueSource(
                    source_type="RESEARCH_TRIGGER",
                    source_record_id=str(trigger.id),
                    title=trigger.title,
                    source_url=trigger.source_reference,
                    effective_at=trigger.effective_at,
                    recorded_at=trigger.source_recorded_at,
                )
            ],
        )

    return list(tasks.values()), companies


def _latest_rank_entries(
    session: Session, ranking_type: RankingType, cutoff: datetime
) -> dict[UUID, RankingEntry]:
    latest_run = session.scalar(
        select(RankingRun)
        .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
        .where(
            RankingDefinition.ranking_type == ranking_type.value,
            RankingDefinition.status == "ACTIVE",
            RankingRun.as_of <= cutoff,
            RankingRun.recorded_at <= cutoff,
        )
        .order_by(RankingRun.as_of.desc(), RankingRun.recorded_at.desc())
        .limit(1)
    )
    if latest_run is None:
        return {}
    return {
        item.company_id: item
        for item in session.scalars(
            select(RankingEntry).where(RankingEntry.run_id == latest_run.id)
        )
    }


def _completed_task(
    task: s.ResearchQueueTask, completion: ResearchQueueCompletion
) -> s.ResearchQueueTask:
    return task.model_copy(
        update={
            "status": "COMPLETE",
            "completed_by": completion.completed_by,
            "completed_at": completion.completed_at,
            "completion_note": completion.completion_note,
            "trigger_classification": (
                ThesisWatchClassification(completion.trigger_classification)
                if completion.trigger_classification is not None
                else None
            ),
        }
    )


def _task_sort_key(task: s.ResearchQueueTask) -> tuple[Any, ...]:
    rank_position = (
        task.research_rank_position if task.company.lifecycle == Lifecycle.CANDIDATE else None
    )
    return (
        task.lifecycle_priority,
        TASK_ORDER[task.task_type],
        rank_position is None,
        rank_position or 0,
        task.due_at or task.source_effective_at or datetime.max.replace(tzinfo=UTC),
        task.company.name.casefold(),
        task.task_id,
    )


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
