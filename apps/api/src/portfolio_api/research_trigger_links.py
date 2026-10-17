"""Typed, append-only provenance between deterministic triggers and publications."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    ResearchTrigger,
    ResearchTriggerPublicationLink,
    ThesisWatchClassification,
)


def validate_trigger_references(
    session: Session,
    *,
    company_id: UUID,
    observed_at: datetime,
    references: list[s.ResearchTriggerReferenceInput],
) -> dict[UUID, ResearchTrigger]:
    from portfolio_api.domain.services import DomainError

    if not references:
        return {}
    trigger_ids = [item.trigger_id for item in references]
    rows = list(session.scalars(select(ResearchTrigger).where(ResearchTrigger.id.in_(trigger_ids))))
    by_id = {row.id: row for row in rows}
    for reference in references:
        trigger = by_id.get(reference.trigger_id)
        if trigger is None:
            raise DomainError("Referenced research trigger does not exist", 404)
        if trigger.company_id != company_id:
            raise DomainError("Research trigger belongs to a different company")
        if trigger.detected_at > observed_at:
            raise DomainError("Research observation predates the application trigger context", 409)
        if reference.classification not in set(ThesisWatchClassification):
            raise DomainError("Unsupported Thesis Watch classification")
    return by_id


def persist_trigger_references(
    session: Session,
    *,
    revision_id: UUID,
    revision_type: str,
    references: list[s.ResearchTriggerReferenceInput],
    recorded_at: datetime,
) -> None:
    if revision_type not in {"RESEARCH", "THESIS"}:
        raise ValueError("Unsupported trigger publication revision type")
    for reference in references:
        session.add(
            ResearchTriggerPublicationLink(
                trigger_id=reference.trigger_id,
                research_revision_id=revision_id if revision_type == "RESEARCH" else None,
                thesis_revision_id=revision_id if revision_type == "THESIS" else None,
                classification=reference.classification.value,
                classification_rationale=reference.classification_rationale,
                recorded_at=recorded_at,
            )
        )
    session.flush()


def _reference_read(
    link: ResearchTriggerPublicationLink, trigger: ResearchTrigger
) -> s.ResearchTriggerReferenceRead:
    return s.ResearchTriggerReferenceRead(
        trigger_id=trigger.id,
        event_key=trigger.event_key,
        trigger_type=trigger.trigger_type,
        title=trigger.title,
        classification=ThesisWatchClassification(link.classification),
        classification_rationale=link.classification_rationale,
        source_reference=trigger.source_reference,
        effective_at=trigger.effective_at,
        source_observed_at=trigger.source_observed_at,
        source_recorded_at=trigger.source_recorded_at,
        detected_at=trigger.detected_at,
    )


def references_for_revision(
    session: Session, *, revision_id: UUID, revision_type: str
) -> list[s.ResearchTriggerReferenceRead]:
    if revision_type == "RESEARCH":
        statement = select(ResearchTriggerPublicationLink).where(
            ResearchTriggerPublicationLink.research_revision_id == revision_id
        )
    elif revision_type == "THESIS":
        statement = select(ResearchTriggerPublicationLink).where(
            ResearchTriggerPublicationLink.thesis_revision_id == revision_id
        )
    else:
        raise ValueError("Unsupported trigger publication revision type")
    links = session.scalars(statement.order_by(ResearchTriggerPublicationLink.recorded_at)).all()
    result = []
    for link in links:
        trigger = session.get(ResearchTrigger, link.trigger_id)
        if trigger is not None:
            result.append(_reference_read(link, trigger))
    return result


def publications_for_trigger(
    session: Session, trigger_id: UUID
) -> list[s.ResearchTriggerPublicationRead]:
    links = session.scalars(
        select(ResearchTriggerPublicationLink)
        .where(ResearchTriggerPublicationLink.trigger_id == trigger_id)
        .order_by(ResearchTriggerPublicationLink.recorded_at, ResearchTriggerPublicationLink.id)
    ).all()
    return [
        s.ResearchTriggerPublicationRead(
            revision_type="RESEARCH" if link.research_revision_id else "THESIS",
            revision_id=link.research_revision_id or link.thesis_revision_id,
            classification=ThesisWatchClassification(link.classification),
            classification_rationale=link.classification_rationale,
            recorded_at=link.recorded_at,
        )
        for link in links
    ]
