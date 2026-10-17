"""Append-only capture of deterministic research triggers from canonical histories."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from portfolio_api.attention import attention_feed
from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateObservation,
    CurrentLifecycle,
    FinancialModelRevision,
    InvestmentThesisClaim,
    InvestmentThesisEvidence,
    InvestmentThesisRevision,
    Lifecycle,
    LifecycleEvent,
    Listing,
    ReportedFundamentalObservation,
    ResearchQueueCompletion,
    ResearchQueueTaskType,
    ResearchTrigger,
    ResearchTriggerType,
    RiskAssessmentRevision,
    Security,
    SourceDocument,
)
from portfolio_api.investment_thesis import company_investment_thesis
from portfolio_api.research_forecasts import company_research
from portfolio_api.research_trigger_links import publications_for_trigger

TRIGGER_EVENT_TYPES = {
    "NEW_FILING": ResearchTriggerType.NEW_FILING,
    "MODEL_REVISION": ResearchTriggerType.MODEL_REVISION,
    "EXPECTED_IRR_CHANGE": ResearchTriggerType.EXPECTED_IRR_CHANGE,
    "CONSENSUS_REVISION": ResearchTriggerType.CONSENSUS_REVISION,
    "RISK_ASSESSMENT": ResearchTriggerType.RISK_ASSESSMENT,
}
CORRECTION_CONTEXTS = {"POTENTIAL_RESTATEMENT", "AMENDED_FILING"}
THESIS_TRIGGER_CLAIMS = {"PRINCIPAL_RISK", "THESIS_BREAKER", "CATALYST"}
ACTIVE_LIFECYCLES = {
    Lifecycle.PORTFOLIO.value,
    Lifecycle.WATCHLIST.value,
    Lifecycle.CANDIDATE.value,
}


@dataclass(frozen=True)
class TriggerCandidate:
    company_id: UUID
    event_key: str
    trigger_type: ResearchTriggerType
    title: str
    reason: str
    source_domain: str
    source_record_id: str
    source_reference: str | None
    effective_at: datetime | None
    source_observed_at: datetime | None
    source_recorded_at: datetime
    source_snapshot: dict[str, object]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _snapshot_fingerprint(candidate: TriggerCandidate) -> str:
    return _digest(
        {
            "trigger_type": candidate.trigger_type.value,
            "title": candidate.title,
            "reason": candidate.reason,
            "source_domain": candidate.source_domain,
            "source_record_id": candidate.source_record_id,
            "source_reference": candidate.source_reference,
            "effective_at": candidate.effective_at,
            "source_observed_at": candidate.source_observed_at,
            "source_recorded_at": candidate.source_recorded_at,
            "source_snapshot": candidate.source_snapshot,
        }
    )


def _upsert_candidate(
    session: Session, candidate: TriggerCandidate, detected_at: datetime
) -> tuple[ResearchTrigger, bool]:
    fingerprint = _snapshot_fingerprint(candidate)
    existing = session.scalar(
        select(ResearchTrigger).where(
            ResearchTrigger.event_key == candidate.event_key,
            ResearchTrigger.fingerprint == fingerprint,
        )
    )
    if existing is not None:
        return existing, False
    next_version = (
        session.scalar(
            select(func.max(ResearchTrigger.version)).where(
                ResearchTrigger.event_key == candidate.event_key
            )
        )
        or 0
    ) + 1
    row = ResearchTrigger(
        company_id=candidate.company_id,
        event_key=candidate.event_key,
        version=next_version,
        fingerprint=fingerprint,
        trigger_type=candidate.trigger_type.value,
        title=candidate.title,
        reason=candidate.reason,
        source_domain=candidate.source_domain,
        source_record_id=candidate.source_record_id,
        source_reference=candidate.source_reference,
        effective_at=candidate.effective_at,
        source_observed_at=candidate.source_observed_at,
        source_recorded_at=_aware(candidate.source_recorded_at),
        detected_at=detected_at,
        source_snapshot=json.loads(json.dumps(candidate.source_snapshot, default=str)),
    )
    session.add(row)
    session.flush()
    return row, True


def _event_candidates(
    session: Session,
    *,
    as_of: datetime,
    lookback_days: int,
    company_id: UUID | None,
) -> list[TriggerCandidate]:
    feed = attention_feed(
        session,
        as_of=as_of,
        lookback_days=lookback_days,
        company_id=company_id,
        limit=100_000,
    )
    if feed.total > len(feed.events):
        feed = attention_feed(
            session,
            as_of=as_of,
            lookback_days=lookback_days,
            company_id=company_id,
            limit=feed.total,
        )

    def event_uuid(event_id: str | None, *, composite: bool = False) -> UUID | None:
        if not event_id:
            return None
        value = event_id.split(":", 1)[0] if composite else event_id
        try:
            return UUID(value)
        except ValueError:
            return None

    by_domain: dict[str, set[UUID]] = {
        "financial_model_revision": set(),
        "consensus_estimate_observation": set(),
        "source_document": set(),
        "risk_assessment": set(),
    }
    event_source_ids: dict[str, tuple[str, UUID]] = {}
    for item in feed.events:
        if item.source_domain not in by_domain:
            continue
        source_uuid = event_uuid(
            item.source_id,
            composite=item.source_domain == "risk_assessment",
        )
        if source_uuid is not None:
            by_domain[item.source_domain].add(source_uuid)
            event_source_ids[item.id] = (item.source_domain, source_uuid)
    observed_by_identity: dict[tuple[str, UUID], datetime] = {}
    if by_domain["financial_model_revision"]:
        observed_by_identity.update(
            {
                ("financial_model_revision", row.id): _aware(row.proposal_authored_at)
                for row in session.scalars(
                    select(FinancialModelRevision).where(
                        FinancialModelRevision.id.in_(by_domain["financial_model_revision"]),
                        FinancialModelRevision.proposal_authored_at.is_not(None),
                    )
                )
                if row.proposal_authored_at is not None
            }
        )
    if by_domain["consensus_estimate_observation"]:
        observed_by_identity.update(
            {
                ("consensus_estimate_observation", row.id): _aware(row.observed_at)
                for row in session.scalars(
                    select(ConsensusEstimateObservation).where(
                        ConsensusEstimateObservation.id.in_(
                            by_domain["consensus_estimate_observation"]
                        ),
                        ConsensusEstimateObservation.observed_at.is_not(None),
                    )
                )
                if row.observed_at is not None
            }
        )
    if by_domain["source_document"]:
        observed_by_identity.update(
            {
                ("source_document", row.id): _aware(row.retrieved_at)
                for row in session.scalars(
                    select(SourceDocument).where(
                        SourceDocument.id.in_(by_domain["source_document"]),
                        SourceDocument.retrieved_at.is_not(None),
                    )
                )
                if row.retrieved_at is not None
            }
        )
    if by_domain["risk_assessment"]:
        observed_by_identity.update(
            {
                ("risk_assessment", row.id): _aware(row.authored_at)
                for row in session.scalars(
                    select(RiskAssessmentRevision).where(
                        RiskAssessmentRevision.id.in_(by_domain["risk_assessment"])
                    )
                )
            }
        )
    candidates: list[TriggerCandidate] = []
    for item in feed.events:
        trigger_type = TRIGGER_EVENT_TYPES.get(item.event_type)
        if (
            trigger_type is None
            or item.company_id is None
            or item.source_id is None
            or item.recorded_at is None
        ):
            continue
        recorded_at = _aware(item.recorded_at)
        if recorded_at > as_of:
            continue
        source_observed_at = (
            observed_by_identity.get(event_source_ids[item.id])
            if item.id in event_source_ids
            else None
        )
        if source_observed_at is not None and source_observed_at > as_of:
            continue
        candidates.append(
            TriggerCandidate(
                company_id=item.company_id,
                event_key=item.id,
                trigger_type=trigger_type,
                title=item.title,
                reason=item.explanation,
                source_domain=item.source_domain,
                source_record_id=item.source_id,
                source_reference=item.source_reference,
                effective_at=_aware(item.effective_at) if item.effective_at else None,
                source_observed_at=source_observed_at,
                source_recorded_at=recorded_at,
                source_snapshot={
                    "event_type": item.event_type,
                    "severity": item.severity,
                    "status": item.status,
                    "prior_value": item.prior_value,
                    "current_value": item.current_value,
                    "unit": item.unit,
                    "time_precision": item.time_precision,
                },
            )
        )
    return candidates


def _fundamental_correction_candidates(
    session: Session,
    *,
    as_of: datetime,
    cutoff: datetime,
    company_id: UUID | None,
) -> list[TriggerCandidate]:
    query = (
        select(ReportedFundamentalObservation)
        .join(
            CurrentLifecycle,
            CurrentLifecycle.company_id == ReportedFundamentalObservation.company_id,
        )
        .join(LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id)
        .where(
            LifecycleEvent.new_state.in_(ACTIVE_LIFECYCLES),
            ReportedFundamentalObservation.revision_context.in_(CORRECTION_CONTEXTS),
            ReportedFundamentalObservation.recorded_at <= as_of,
        )
    )
    if company_id is not None:
        query = query.where(ReportedFundamentalObservation.company_id == company_id)
    candidates: list[TriggerCandidate] = []
    for observation in session.scalars(query).all():
        if _aware(observation.observed_at) > as_of:
            continue
        available_at = observation.filed_at or observation.observed_at
        if available_at is None:
            continue
        available_at = _aware(available_at)
        if not cutoff <= available_at <= as_of:
            continue
        period = observation.fiscal_period or observation.period_end.date().isoformat()
        evidence_id = observation.accession_number or observation.source_record_id
        candidates.append(
            TriggerCandidate(
                company_id=observation.company_id,
                event_key=f"reported_fundamental_observation:{observation.id}",
                trigger_type=ResearchTriggerType.REPORTED_FACT_CORRECTION,
                title=f"Reported {observation.metric} correction for {period}",
                reason=(
                    f"The source observation is marked {observation.revision_context} "
                    f"({observation.data_quality}). Review the source before relying on it; "
                    "this status does not establish that the issuer formally restated the fact."
                ),
                source_domain="reported_fundamental_observation",
                source_record_id=str(observation.id),
                source_reference=observation.source_url,
                effective_at=_aware(observation.filed_at) if observation.filed_at else None,
                source_observed_at=_aware(observation.observed_at),
                source_recorded_at=_aware(observation.recorded_at),
                source_snapshot={
                    "metric": observation.metric,
                    "period_type": observation.period_type,
                    "period_start": observation.period_start,
                    "period_end": observation.period_end,
                    "fiscal_year": observation.fiscal_year,
                    "fiscal_period": observation.fiscal_period,
                    "value": str(observation.value),
                    "currency": observation.currency,
                    "unit": observation.unit,
                    "revision_context": observation.revision_context,
                    "data_quality": observation.data_quality,
                    "quality_reason": observation.quality_reason,
                    "accession_number": observation.accession_number,
                    "source_record_id": observation.source_record_id,
                    "supersedes_observation_id": observation.supersedes_observation_id,
                    "evidence_id": evidence_id,
                },
            )
        )
    return candidates


def _thesis_evidence_candidates(
    session: Session,
    *,
    as_of: datetime,
    cutoff: datetime,
    company_id: UUID | None,
) -> list[TriggerCandidate]:
    revision_query = (
        select(InvestmentThesisRevision)
        .join(CurrentLifecycle, CurrentLifecycle.company_id == InvestmentThesisRevision.company_id)
        .join(LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id)
        .where(
            LifecycleEvent.new_state.in_(ACTIVE_LIFECYCLES),
            InvestmentThesisRevision.recorded_at <= as_of,
        )
        .order_by(
            InvestmentThesisRevision.company_id,
            InvestmentThesisRevision.stream_key,
            InvestmentThesisRevision.revision_number.desc(),
        )
    )
    if company_id is not None:
        revision_query = revision_query.where(InvestmentThesisRevision.company_id == company_id)
    current_revisions: dict[tuple[UUID, str], InvestmentThesisRevision] = {}
    for revision in session.scalars(revision_query).all():
        current_revisions.setdefault((revision.company_id, revision.stream_key), revision)
    published = [
        item
        for item in current_revisions.values()
        if item.status == "PUBLISHED"
        and cutoff <= _aware(item.recorded_at) <= as_of
        and _aware(item.observed_at) <= as_of
    ]
    revision_by_id = {item.id: item for item in published}
    if not revision_by_id:
        return []
    claims = session.scalars(
        select(InvestmentThesisClaim).where(
            InvestmentThesisClaim.revision_id.in_(revision_by_id),
            InvestmentThesisClaim.claim_type.in_(THESIS_TRIGGER_CLAIMS),
            InvestmentThesisClaim.status.in_(("ACTIVE", "UNDER_REVIEW")),
        )
    ).all()
    claim_by_id = {item.id: item for item in claims}
    if not claim_by_id:
        return []
    evidence_rows = session.scalars(
        select(InvestmentThesisEvidence).where(InvestmentThesisEvidence.claim_id.in_(claim_by_id))
    ).all()
    documents = (
        {
            item.id: item
            for item in session.scalars(
                select(SourceDocument).where(
                    SourceDocument.id.in_(
                        [
                            item.source_document_id
                            for item in evidence_rows
                            if item.source_document_id
                        ]
                    ),
                    SourceDocument.recorded_at <= as_of,
                )
            ).all()
        }
        if evidence_rows
        else {}
    )
    facts = (
        {
            item.id: item
            for item in session.scalars(
                select(ReportedFundamentalObservation).where(
                    ReportedFundamentalObservation.id.in_(
                        [
                            item.reported_fundamental_observation_id
                            for item in evidence_rows
                            if item.reported_fundamental_observation_id
                        ]
                    ),
                    ReportedFundamentalObservation.recorded_at <= as_of,
                )
            ).all()
        }
        if evidence_rows
        else {}
    )
    candidates: list[TriggerCandidate] = []
    for evidence in evidence_rows:
        claim = claim_by_id.get(evidence.claim_id)
        thesis_revision = revision_by_id.get(claim.revision_id) if claim else None
        if claim is None or thesis_revision is None:
            continue
        document = (
            documents.get(evidence.source_document_id)
            if evidence.source_document_id is not None
            else None
        )
        fact = (
            facts.get(evidence.reported_fundamental_observation_id)
            if evidence.reported_fundamental_observation_id is not None
            else None
        )
        if evidence.source_document_id and document is None:
            continue
        if evidence.reported_fundamental_observation_id and fact is None:
            continue
        source_reference = (
            document.canonical_url if document else fact.source_url if fact else evidence.source_url
        )
        source_record_id = str(
            evidence.source_document_id
            or evidence.reported_fundamental_observation_id
            or evidence.id
        )
        candidates.append(
            TriggerCandidate(
                company_id=thesis_revision.company_id,
                event_key=f"investment_thesis_evidence:{evidence.id}",
                trigger_type=ResearchTriggerType.THESIS_EVIDENCE_LINKED,
                title=f"New evidence linked to thesis {claim.claim_type.lower().replace('_', ' ')}",
                reason=(
                    f"A published thesis revision linked evidence as {evidence.relationship} to "
                    f"'{claim.statement}'. The evidence relationship is a researcher judgment; "
                    "it does not restate the source as a canonical fact."
                ),
                source_domain=(
                    "source_document"
                    if document
                    else "reported_fundamental_observation"
                    if fact
                    else "investment_thesis_evidence"
                ),
                source_record_id=source_record_id,
                source_reference=source_reference,
                effective_at=_aware(thesis_revision.observed_at),
                source_observed_at=_aware(thesis_revision.observed_at),
                source_recorded_at=_aware(thesis_revision.recorded_at),
                source_snapshot={
                    "evidence_id": evidence.id,
                    "claim_id": claim.id,
                    "claim_key": claim.claim_key,
                    "claim_type": claim.claim_type,
                    "claim_statement": claim.statement,
                    "relationship": evidence.relationship,
                    "source_name": evidence.source_name,
                    "source_document_id": evidence.source_document_id,
                    "reported_fundamental_observation_id": (
                        evidence.reported_fundamental_observation_id
                    ),
                    "external_identifier": evidence.external_identifier,
                    "source_url": source_reference,
                    "published_at": evidence.published_at,
                    "thesis_revision_id": thesis_revision.id,
                    "thesis_revision_number": thesis_revision.revision_number,
                    "thesis_observed_at": thesis_revision.observed_at,
                },
            )
        )
    return candidates


def _current_lifecycle(
    session: Session, company_id: UUID, as_of: datetime
) -> tuple[str | None, UUID | None]:
    row = session.execute(
        select(LifecycleEvent.new_state, LifecycleEvent.id)
        .where(
            LifecycleEvent.company_id == company_id,
            LifecycleEvent.effective_at <= as_of,
            LifecycleEvent.recorded_at <= as_of,
        )
        .order_by(LifecycleEvent.effective_at.desc(), LifecycleEvent.recorded_at.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else (None, None)


def _company_read(session: Session, company_id: UUID, as_of: datetime) -> s.CompanyRead | None:
    company = session.get(Company, company_id)
    if company is None:
        return None
    lifecycle, event_id = _current_lifecycle(session, company_id, as_of)
    return s.CompanyRead(
        id=company.id,
        name=company.name,
        reporting_currency=company.reporting_currency,
        created_at=company.created_at,
        is_demo=company.is_demo,
        lifecycle=Lifecycle(lifecycle) if lifecycle else None,
        lifecycle_event_id=event_id,
    )


def _processing_state(
    row: ResearchTrigger,
    *,
    latest_version: int,
    completion_by_identity: dict[tuple[str, str], ResearchQueueCompletion],
    superseded_source_ids: set[str],
) -> str:
    if row.source_record_id in superseded_source_ids:
        return "SUPERSEDED"
    if row.version < latest_version:
        return "SUPERSEDED"
    if row.queue_task_id and row.queue_condition_fingerprint:
        identity = (row.queue_task_id, row.queue_condition_fingerprint)
        if identity in completion_by_identity:
            return "REVIEWED"
        return "OPEN"
    return "STALE"


def _superseded_source_ids(session: Session, cutoff: datetime) -> set[str]:
    """Return only corrections that had been recorded by the requested as-of time."""
    superseded = {
        str(item)
        for item in session.scalars(
            select(SourceDocument.supersedes_document_id).where(
                SourceDocument.supersedes_document_id.is_not(None),
                SourceDocument.recorded_at <= cutoff,
                or_(SourceDocument.retrieved_at.is_(None), SourceDocument.retrieved_at <= cutoff),
            )
        ).all()
    }
    superseded.update(
        str(item)
        for item in session.scalars(
            select(ReportedFundamentalObservation.supersedes_observation_id).where(
                ReportedFundamentalObservation.supersedes_observation_id.is_not(None),
                ReportedFundamentalObservation.recorded_at <= cutoff,
                or_(
                    ReportedFundamentalObservation.observed_at.is_(None),
                    ReportedFundamentalObservation.observed_at <= cutoff,
                ),
            )
        ).all()
    )
    superseded.update(
        str(item)
        for item in session.scalars(
            select(ConsensusEstimateObservation.supersedes_observation_id).where(
                ConsensusEstimateObservation.supersedes_observation_id.is_not(None),
                ConsensusEstimateObservation.recorded_at <= cutoff,
                or_(
                    ConsensusEstimateObservation.observed_at.is_(None),
                    ConsensusEstimateObservation.observed_at <= cutoff,
                ),
            )
        ).all()
    )
    return superseded


def list_research_triggers(
    session: Session,
    *,
    as_of: datetime | None = None,
    company_id: UUID | None = None,
    trigger_type: ResearchTriggerType | None = None,
    processing_state: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> s.ResearchTriggerReadResult:
    cutoff = _aware(as_of or datetime.now(UTC))
    query = select(ResearchTrigger).where(
        ResearchTrigger.detected_at <= cutoff,
        ResearchTrigger.source_recorded_at <= cutoff,
    )
    if company_id is not None:
        query = query.where(ResearchTrigger.company_id == company_id)
    if trigger_type is not None:
        query = query.where(ResearchTrigger.trigger_type == trigger_type.value)
    ordered_query = query.order_by(ResearchTrigger.detected_at.desc(), ResearchTrigger.event_key)
    # Filtered pages must be sliced after deriving state; limiting first can hide OPEN
    # triggers behind newer completed/superseded events.
    rows = list(
        session.scalars(
            ordered_query
            if processing_state is not None
            else ordered_query.offset(offset).limit(limit)
        )
    )
    all_keys = {item.event_key for item in rows}
    latest_versions = (
        dict(
            session.execute(
                select(ResearchTrigger.event_key, func.max(ResearchTrigger.version))
                .where(
                    ResearchTrigger.event_key.in_(all_keys),
                    ResearchTrigger.detected_at <= cutoff,
                    ResearchTrigger.source_recorded_at <= cutoff,
                )
                .group_by(ResearchTrigger.event_key)
            ).all()
        )
        if all_keys
        else {}
    )
    completions = (
        list(
            session.scalars(
                select(ResearchQueueCompletion).where(
                    ResearchQueueCompletion.completed_at <= cutoff,
                    ResearchQueueCompletion.task_id.in_(
                        [item.queue_task_id for item in rows if item.queue_task_id]
                    ),
                )
            )
        )
        if any(item.queue_task_id for item in rows)
        else []
    )
    completion_by_identity = {
        (item.task_id, item.condition_fingerprint): item for item in completions
    }
    superseded_source_ids = _superseded_source_ids(session, cutoff)
    result: list[s.ResearchTriggerRead] = []
    for row in rows:
        company = _company_read(session, row.company_id, cutoff)
        if company is None:
            continue
        state = _processing_state(
            row,
            latest_version=latest_versions.get(row.event_key, row.version),
            completion_by_identity=completion_by_identity,
            superseded_source_ids=superseded_source_ids,
        )
        if processing_state is not None and state != processing_state:
            continue
        result.append(
            s.ResearchTriggerRead(
                id=row.id,
                company=company,
                event_key=row.event_key,
                version=row.version,
                fingerprint=row.fingerprint,
                trigger_type=ResearchTriggerType(row.trigger_type),
                title=row.title,
                reason=row.reason,
                source_domain=row.source_domain,
                source_record_id=row.source_record_id,
                source_reference=row.source_reference,
                effective_at=row.effective_at,
                source_observed_at=row.source_observed_at,
                source_recorded_at=row.source_recorded_at,
                detected_at=row.detected_at,
                source_snapshot=row.source_snapshot,
                queue_task_id=row.queue_task_id,
                queue_condition_fingerprint=row.queue_condition_fingerprint,
                processing_state=state,
            )
        )
    if processing_state is not None:
        result = result[offset : offset + limit]
    return s.ResearchTriggerReadResult(as_of=cutoff, triggers=result)


def _model_context(
    model: s.FinancialModelRead | s.ExtendedFinancialModelRead,
) -> s.ResearchTriggerModelContextRead:
    revision = model.current_revision
    return s.ResearchTriggerModelContextRead(
        model_id=model.id,
        model_type=model.model_type,
        model_name=model.model_name,
        valuation_listing=model.valuation_listing,
        model_currency=model.model_currency,
        current_revision_id=model.current_revision_id,
        revision_number=revision.revision_number,
        methodology_version=revision.methodology_version,
        actor=revision.actor,
        source=revision.source,
        rationale=revision.rationale,
        effective_at=revision.effective_at,
        recorded_at=revision.recorded_at,
        outputs=revision.outputs,
        supporting_evidence=revision.supporting_evidence,
    )


def research_trigger_context(session: Session, trigger_id: UUID) -> s.ResearchTriggerContextRead:
    """Return one trigger with bounded current canonical context for external research."""
    cutoff = datetime.now(UTC)
    row = session.get(ResearchTrigger, trigger_id)
    if row is None or row.detected_at > cutoff or row.source_recorded_at > cutoff:
        raise ValueError("Research trigger was not found")
    company = _company_read(session, row.company_id, cutoff)
    if company is None:
        raise ValueError("Research trigger company was not found")
    latest_version = (
        session.scalar(
            select(func.max(ResearchTrigger.version)).where(
                ResearchTrigger.event_key == row.event_key,
                ResearchTrigger.detected_at <= cutoff,
                ResearchTrigger.source_recorded_at <= cutoff,
            )
        )
        or row.version
    )
    completion = None
    if row.queue_task_id and row.queue_condition_fingerprint:
        completion = session.scalar(
            select(ResearchQueueCompletion).where(
                ResearchQueueCompletion.task_id == row.queue_task_id,
                ResearchQueueCompletion.condition_fingerprint == row.queue_condition_fingerprint,
                ResearchQueueCompletion.completed_at <= cutoff,
            )
        )
    state = _processing_state(
        row,
        latest_version=latest_version,
        completion_by_identity=(
            {
                (completion.task_id, completion.condition_fingerprint): completion,
            }
            if completion is not None
            else {}
        ),
        superseded_source_ids=_superseded_source_ids(session, cutoff),
    )
    trigger = s.ResearchTriggerRead(
        id=row.id,
        company=company,
        event_key=row.event_key,
        version=row.version,
        fingerprint=row.fingerprint,
        trigger_type=ResearchTriggerType(row.trigger_type),
        title=row.title,
        reason=row.reason,
        source_domain=row.source_domain,
        source_record_id=row.source_record_id,
        source_reference=row.source_reference,
        effective_at=row.effective_at,
        source_observed_at=row.source_observed_at,
        source_recorded_at=row.source_recorded_at,
        detected_at=row.detected_at,
        source_snapshot=row.source_snapshot,
        queue_task_id=row.queue_task_id,
        queue_condition_fingerprint=row.queue_condition_fingerprint,
        processing_state=state,
    )
    securities = list(
        session.scalars(
            select(Security)
            .where(Security.company_id == row.company_id)
            .order_by(Security.name, Security.id)
        )
    )
    listings = list(
        session.scalars(
            select(Listing)
            .join(Security, Security.id == Listing.security_id)
            .where(Security.company_id == row.company_id)
            .order_by(Listing.venue, Listing.ticker, Listing.id)
        )
    )
    model_context = [
        _model_context(model) for model in q.company_financial_models(session, row.company_id)
    ]
    model_context.extend(
        _model_context(model)
        for model in q.company_extended_financial_models(session, row.company_id)
    )
    return s.ResearchTriggerContextRead(
        context_as_of=cutoff,
        trigger=trigger,
        securities=[s.SecurityRead.model_validate(item) for item in securities],
        listings=[s.ListingRead.model_validate(item) for item in listings],
        research=company_research(session, row.company_id),
        thesis=company_investment_thesis(session, row.company_id),
        models=model_context,
        accepted_publications=publications_for_trigger(session, row.id),
    )


def _link_to_queue(session: Session, rows: list[ResearchTrigger], as_of: datetime) -> None:
    if not rows:
        return
    from portfolio_api.research_queue import get_research_queue

    queue = get_research_queue(session, include_complete=True, as_of=as_of)
    for row in rows:
        if row.queue_task_id and row.queue_condition_fingerprint:
            continue
        matched = None
        for task in queue.tasks:
            if any(
                source.source_record_id == row.source_record_id
                and (
                    (
                        row.source_domain == "source_document"
                        and source.source_type == "SOURCE_DOCUMENT"
                    )
                    or (
                        row.source_domain == "investment_thesis_evidence"
                        and source.source_record_id == str(row.source_snapshot.get("evidence_id"))
                    )
                )
                for source in task.sources
            ):
                matched = task
                break
            if task.task_type == ResearchQueueTaskType.RESEARCH_TRIGGER and any(
                source.source_type == "RESEARCH_TRIGGER" and source.source_record_id == str(row.id)
                for source in task.sources
            ):
                matched = task
                break
        if matched is not None:
            row.queue_task_id = matched.task_id
            row.queue_condition_fingerprint = matched.condition_fingerprint


def refresh_research_triggers(
    session: Session,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    company_id: UUID | None = None,
) -> s.ResearchTriggerRefreshResult:
    cutoff = _aware(as_of or datetime.now(UTC))
    detected_at = datetime.now(UTC)
    capture_cutoff = max(cutoff, detected_at)
    start = cutoff - timedelta(days=lookback_days)
    candidates = _event_candidates(
        session, as_of=cutoff, lookback_days=lookback_days, company_id=company_id
    )
    candidates.extend(
        _fundamental_correction_candidates(
            session, as_of=cutoff, cutoff=start, company_id=company_id
        )
    )
    candidates.extend(
        _thesis_evidence_candidates(session, as_of=cutoff, cutoff=start, company_id=company_id)
    )
    # Stable ordering keeps version assignment reproducible across identical source scans.
    candidates.sort(key=lambda item: (item.event_key, _snapshot_fingerprint(item)))
    inserted = 0
    rows: list[ResearchTrigger] = []
    for candidate in candidates:
        row, created = _upsert_candidate(session, candidate, detected_at)
        rows.append(row)
        inserted += int(created)
    session.flush()
    _link_to_queue(session, rows, capture_cutoff)
    session.flush()
    result = list_research_triggers(
        session,
        as_of=capture_cutoff,
        company_id=company_id,
        limit=max(100, len(rows)),
    )
    return s.ResearchTriggerRefreshResult(
        as_of=capture_cutoff,
        lookback_days=lookback_days,
        examined=len(candidates),
        created=inserted,
        replayed=len(candidates) - inserted,
        triggers=result.triggers,
    )


def normalize_trigger_cutoff(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("as_of must include a timezone offset")
    return _aware(value) if value is not None else None
