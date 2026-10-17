"""Versioned external research forecasts and qualitative assessments."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    ResearchAssessment,
    ResearchEvidence,
    ResearchForecast,
    ResearchRevision,
    Security,
    SourceDocument,
    now,
)
from portfolio_api.domain.services import DomainError
from portfolio_api.research_trigger_links import (
    persist_trigger_references,
    references_for_revision,
    validate_trigger_references,
)


def _contract_fingerprint(value: s.ResearchRevisionPublishContract) -> str:
    canonical = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def publish_research_revision(
    session: Session, value: s.ResearchRevisionPublishContract
) -> tuple[ResearchRevision, Literal["PUBLISHED", "ALREADY_PUBLISHED"]]:
    """Append a source-linked research packet with optimistic supersession semantics."""
    issuer = session.scalar(select(Company).where(Company.id == value.company_id).with_for_update())
    if issuer is None:
        raise DomainError("Research contract company identity was not found", 404)

    if value.security_id is not None:
        security = session.scalar(select(Security).where(Security.id == value.security_id))
        if security is None or security.company_id != value.company_id:
            raise DomainError("Security identity does not belong to the contract company")

    validate_trigger_references(
        session,
        company_id=value.company_id,
        observed_at=value.observed_at,
        references=value.trigger_references,
    )

    fingerprint = _contract_fingerprint(value)
    duplicate = session.scalar(
        select(ResearchRevision).where(
            ResearchRevision.company_id == value.company_id,
            ResearchRevision.stream_key == value.stream_key,
            ResearchRevision.external_revision_id == value.external_revision_id,
        )
    )
    if duplicate is not None:
        if duplicate.content_fingerprint != fingerprint:
            raise DomainError(
                "External research revision ID was already used for different content", 409
            )
        return duplicate, "ALREADY_PUBLISHED"

    previous = session.scalar(
        select(ResearchRevision)
        .where(
            ResearchRevision.company_id == value.company_id,
            ResearchRevision.stream_key == value.stream_key,
        )
        .order_by(ResearchRevision.revision_number.desc())
        .limit(1)
        .with_for_update()
    )
    expected_base = previous.id if previous is not None else None
    if value.supersedes_revision_id != expected_base:
        raise DomainError(
            "Research stream changed; reload its current revision before publishing", 409
        )
    if previous is not None and value.observed_at < previous.observed_at:
        raise DomainError("Research stream revisions cannot be backdated", 409)

    for item in value.evidence:
        if item.source_document_id is not None:
            document = session.scalar(
                select(SourceDocument).where(SourceDocument.id == item.source_document_id)
            )
            if document is None or document.company_id != value.company_id:
                raise DomainError(
                    "Evidence source document does not belong to the contract company"
                )

    revision = ResearchRevision(
        company_id=value.company_id,
        security_id=value.security_id,
        stream_key=value.stream_key,
        revision_number=1 if previous is None else previous.revision_number + 1,
        contract_version=value.contract_version,
        external_revision_id=value.external_revision_id,
        supersedes_revision_id=expected_base,
        author_id=value.author_id,
        source_id=value.source_id,
        source_reference=value.source_reference,
        observed_at=value.observed_at,
        recorded_at=now(),
        status=value.status.value,
        rationale=value.rationale,
        uncertainty=value.uncertainty,
        content_fingerprint=fingerprint,
    )
    session.add(revision)
    session.flush()

    persist_trigger_references(
        session,
        revision_id=revision.id,
        revision_type="RESEARCH",
        references=value.trigger_references,
        recorded_at=revision.recorded_at,
    )

    session.add_all(
        ResearchForecast(
            revision_id=revision.id,
            metric=item.metric.value,
            period_type=item.period_type.value,
            fiscal_year=item.fiscal_year,
            fiscal_period=item.fiscal_period,
            period_end=item.period_end,
            scenario=item.scenario.value,
            value=item.value,
            currency=item.currency,
            unit=item.unit,
            availability_status=item.availability_status.value,
            availability_reason=item.availability_reason,
            confidence=item.confidence.value,
            rationale=item.rationale,
            uncertainty=item.uncertainty,
        )
        for item in value.forecasts
    )
    session.add_all(
        ResearchAssessment(
            revision_id=revision.id,
            assessment_type=item.assessment_type.value,
            status=item.status.value,
            status_reason=item.status_reason,
            narrative=item.narrative,
            confidence=item.confidence.value,
            uncertainty=item.uncertainty,
        )
        for item in value.assessments
    )
    session.add_all(
        ResearchEvidence(
            revision_id=revision.id,
            source_document_id=item.source_document_id,
            source_name=item.source_name,
            external_identifier=item.external_identifier,
            source_url=str(item.source_url) if item.source_url is not None else None,
            published_at=item.published_at,
            excerpt=item.excerpt,
            note=item.note,
        )
        for item in value.evidence
    )
    session.flush()
    return revision, "PUBLISHED"


def research_revision_read(session: Session, revision: ResearchRevision) -> s.ResearchRevisionRead:
    forecasts = session.scalars(
        select(ResearchForecast)
        .where(ResearchForecast.revision_id == revision.id)
        .order_by(
            ResearchForecast.fiscal_year,
            ResearchForecast.fiscal_period,
            ResearchForecast.metric,
            ResearchForecast.scenario,
        )
    ).all()
    assessments = session.scalars(
        select(ResearchAssessment)
        .where(ResearchAssessment.revision_id == revision.id)
        .order_by(ResearchAssessment.assessment_type)
    ).all()
    evidence = session.scalars(
        select(ResearchEvidence)
        .where(ResearchEvidence.revision_id == revision.id)
        .order_by(ResearchEvidence.source_name, ResearchEvidence.external_identifier)
    ).all()
    document_ids = {item.source_document_id for item in evidence if item.source_document_id}
    documents = (
        {
            item.id: item.title
            for item in session.scalars(
                select(SourceDocument).where(SourceDocument.id.in_(document_ids))
            )
        }
        if document_ids
        else {}
    )
    return s.ResearchRevisionRead(
        id=revision.id,
        company_id=revision.company_id,
        security_id=revision.security_id,
        stream_key=revision.stream_key,
        revision_number=revision.revision_number,
        contract_version=revision.contract_version,
        external_revision_id=revision.external_revision_id,
        supersedes_revision_id=revision.supersedes_revision_id,
        author_id=revision.author_id,
        source_id=revision.source_id,
        source_reference=revision.source_reference,
        observed_at=revision.observed_at,
        recorded_at=revision.recorded_at,
        status=revision.status,
        rationale=revision.rationale,
        uncertainty=revision.uncertainty,
        content_fingerprint=revision.content_fingerprint,
        forecasts=[s.ResearchForecastRead.model_validate(item) for item in forecasts],
        assessments=[s.ResearchAssessmentRead.model_validate(item) for item in assessments],
        evidence=[
            s.ResearchEvidenceRead(
                id=item.id,
                source_document_id=item.source_document_id,
                source_document_title=(
                    documents.get(item.source_document_id)
                    if item.source_document_id is not None
                    else None
                ),
                source_name=item.source_name,
                external_identifier=item.external_identifier,
                source_url=item.source_url,
                published_at=item.published_at,
                excerpt=item.excerpt,
                note=item.note,
            )
            for item in evidence
        ],
        trigger_references=references_for_revision(
            session, revision_id=revision.id, revision_type="RESEARCH"
        ),
    )


def company_research(
    session: Session,
    company_id: UUID,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyResearchRead:
    if session.get(Company, company_id) is None:
        raise DomainError("Company not found", 404)
    statement = select(ResearchRevision).where(ResearchRevision.company_id == company_id)
    if as_of is not None:
        observed_cutoff = datetime.combine(as_of, time.max, UTC)
        statement = statement.where(ResearchRevision.observed_at <= observed_cutoff)
    if known_at is not None:
        if known_at.tzinfo is None or known_at.utcoffset() is None:
            raise DomainError("known_at must include a timezone offset")
        statement = statement.where(ResearchRevision.recorded_at <= known_at.astimezone(UTC))
    revisions = list(
        session.scalars(
            statement.order_by(
                ResearchRevision.stream_key,
                ResearchRevision.revision_number.desc(),
            )
        )
    )
    grouped: dict[str, list[s.ResearchRevisionRead]] = {}
    for item in revisions:
        grouped.setdefault(item.stream_key, []).append(research_revision_read(session, item))
    streams = [
        s.ResearchStreamRead(
            stream_key=stream_key,
            current_revision=history[0],
            history=history,
        )
        for stream_key, history in sorted(grouped.items())
    ]
    return s.CompanyResearchRead(
        company_id=company_id,
        as_of=as_of,
        known_at=known_at,
        streams=streams,
    )
