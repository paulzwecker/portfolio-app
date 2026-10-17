"""Versioned investment-thesis publications and source-linked claims."""

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
    InvestmentThesisClaim,
    InvestmentThesisEvidence,
    InvestmentThesisRevision,
    ReportedFundamentalObservation,
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


def _contract_fingerprint(value: s.InvestmentThesisRevisionPublishContract) -> str:
    canonical = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def publish_investment_thesis_revision(
    session: Session, value: s.InvestmentThesisRevisionPublishContract
) -> tuple[InvestmentThesisRevision, Literal["PUBLISHED", "ALREADY_PUBLISHED"]]:
    """Append a complete thesis snapshot using the company's current stream revision as base."""
    company = session.scalar(
        select(Company).where(Company.id == value.company_id).with_for_update()
    )
    if company is None:
        raise DomainError("Investment-thesis company identity was not found", 404)

    if value.security_id is not None:
        security = session.scalar(select(Security).where(Security.id == value.security_id))
        if security is None or security.company_id != value.company_id:
            raise DomainError("Security identity does not belong to the thesis company")

    validate_trigger_references(
        session,
        company_id=value.company_id,
        observed_at=value.observed_at,
        references=value.trigger_references,
    )

    fingerprint = _contract_fingerprint(value)
    duplicate = session.scalar(
        select(InvestmentThesisRevision).where(
            InvestmentThesisRevision.company_id == value.company_id,
            InvestmentThesisRevision.stream_key == value.stream_key,
            InvestmentThesisRevision.external_revision_id == value.external_revision_id,
        )
    )
    if duplicate is not None:
        if duplicate.content_fingerprint != fingerprint:
            raise DomainError(
                "External thesis revision ID was already used for different content", 409
            )
        return duplicate, "ALREADY_PUBLISHED"

    previous = session.scalar(
        select(InvestmentThesisRevision)
        .where(
            InvestmentThesisRevision.company_id == value.company_id,
            InvestmentThesisRevision.stream_key == value.stream_key,
        )
        .order_by(InvestmentThesisRevision.revision_number.desc())
        .limit(1)
        .with_for_update()
    )
    expected_base = previous.id if previous is not None else None
    if value.supersedes_revision_id != expected_base:
        raise DomainError(
            "Thesis stream changed; reload its current revision before publishing", 409
        )
    if previous is not None and value.observed_at < previous.observed_at:
        raise DomainError("Thesis stream revisions cannot be backdated", 409)

    canonical_documents: dict[UUID, SourceDocument] = {}
    canonical_facts: dict[UUID, ReportedFundamentalObservation] = {}
    for claim_input in value.claims:
        for evidence in claim_input.evidence:
            if evidence.source_document_id is not None:
                document = session.scalar(
                    select(SourceDocument).where(SourceDocument.id == evidence.source_document_id)
                )
                if document is None or document.company_id != value.company_id:
                    raise DomainError(
                        "Evidence source document does not belong to the thesis company"
                    )
                if (
                    document.security_id is not None
                    and value.security_id is not None
                    and document.security_id != value.security_id
                ):
                    raise DomainError("Evidence source document refers to a different security")
                canonical_documents[document.id] = document
            if evidence.reported_fundamental_observation_id is not None:
                fact = session.scalar(
                    select(ReportedFundamentalObservation).where(
                        ReportedFundamentalObservation.id
                        == evidence.reported_fundamental_observation_id
                    )
                )
                if fact is None or fact.company_id != value.company_id:
                    raise DomainError(
                        "Evidence financial observation does not belong to the thesis company"
                    )
                if (
                    fact.security_id is not None
                    and value.security_id is not None
                    and fact.security_id != value.security_id
                ):
                    raise DomainError(
                        "Evidence financial observation refers to a different security"
                    )
                canonical_facts[fact.id] = fact

    revision = InvestmentThesisRevision(
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
        thesis_statement=value.thesis_statement,
        confidence=value.confidence.value,
        rationale=value.rationale,
        uncertainty=value.uncertainty,
        content_fingerprint=fingerprint,
    )
    session.add(revision)
    session.flush()

    persist_trigger_references(
        session,
        revision_id=revision.id,
        revision_type="THESIS",
        references=value.trigger_references,
        recorded_at=revision.recorded_at,
    )

    for claim_input in value.claims:
        claim_row = InvestmentThesisClaim(
            revision_id=revision.id,
            claim_key=claim_input.claim_key,
            claim_type=claim_input.claim_type.value,
            status=claim_input.status.value,
            statement=claim_input.statement,
            confidence=claim_input.confidence.value,
            uncertainty=claim_input.uncertainty,
        )
        session.add(claim_row)
        session.flush()
        evidence_rows = []
        for evidence in claim_input.evidence:
            source_name = evidence.source_name
            if evidence.source_document_id is not None:
                source_name = (
                    source_name or canonical_documents[evidence.source_document_id].source_name
                )
            elif evidence.reported_fundamental_observation_id is not None:
                source_name = (
                    source_name
                    or canonical_facts[evidence.reported_fundamental_observation_id].provider_id
                )
            evidence_rows.append(
                InvestmentThesisEvidence(
                    claim_id=claim_row.id,
                    relationship=evidence.relationship.value,
                    source_document_id=evidence.source_document_id,
                    reported_fundamental_observation_id=(
                        evidence.reported_fundamental_observation_id
                    ),
                    source_name=source_name,
                    external_identifier=evidence.external_identifier,
                    source_url=(
                        str(evidence.source_url) if evidence.source_url is not None else None
                    ),
                    published_at=evidence.published_at,
                    excerpt=evidence.excerpt,
                    note=evidence.note,
                )
            )
        session.add_all(evidence_rows)
    session.flush()
    return revision, "PUBLISHED"


def thesis_revision_read(
    session: Session, revision: InvestmentThesisRevision
) -> s.InvestmentThesisRevisionRead:
    claims = session.scalars(
        select(InvestmentThesisClaim)
        .where(InvestmentThesisClaim.revision_id == revision.id)
        .order_by(InvestmentThesisClaim.claim_type, InvestmentThesisClaim.claim_key)
    ).all()
    claim_reads: list[s.InvestmentThesisClaimRead] = []
    for claim in claims:
        evidence_rows = session.scalars(
            select(InvestmentThesisEvidence)
            .where(InvestmentThesisEvidence.claim_id == claim.id)
            .order_by(InvestmentThesisEvidence.id)
        ).all()
        evidence_reads: list[s.InvestmentThesisEvidenceRead] = []
        for evidence in evidence_rows:
            document = (
                session.get(SourceDocument, evidence.source_document_id)
                if evidence.source_document_id is not None
                else None
            )
            fact = (
                session.get(
                    ReportedFundamentalObservation,
                    evidence.reported_fundamental_observation_id,
                )
                if evidence.reported_fundamental_observation_id is not None
                else None
            )
            evidence_reads.append(
                s.InvestmentThesisEvidenceRead(
                    id=evidence.id,
                    relationship=evidence.relationship,
                    source_document_id=evidence.source_document_id,
                    source_document_title=document.title if document is not None else None,
                    source_document_type=(document.document_type if document is not None else None),
                    source_document_url=document.canonical_url if document is not None else None,
                    reported_fundamental_observation_id=(
                        evidence.reported_fundamental_observation_id
                    ),
                    reported_fundamental=(
                        s.InvestmentThesisFactRead.model_validate(fact)
                        if fact is not None
                        else None
                    ),
                    source_name=evidence.source_name,
                    external_identifier=evidence.external_identifier,
                    source_url=evidence.source_url,
                    published_at=evidence.published_at
                    or (
                        document.filed_at or document.published_at
                        if document is not None
                        else fact.filed_at.date()
                        if fact is not None and fact.filed_at is not None
                        else None
                    ),
                    excerpt=evidence.excerpt,
                    note=evidence.note,
                )
            )
        claim_reads.append(
            s.InvestmentThesisClaimRead(
                id=claim.id,
                claim_key=claim.claim_key,
                claim_type=claim.claim_type,
                status=claim.status,
                statement=claim.statement,
                confidence=claim.confidence,
                uncertainty=claim.uncertainty,
                evidence=evidence_reads,
            )
        )
    return s.InvestmentThesisRevisionRead(
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
        thesis_statement=revision.thesis_statement,
        confidence=revision.confidence,
        rationale=revision.rationale,
        uncertainty=revision.uncertainty,
        content_fingerprint=revision.content_fingerprint,
        claims=claim_reads,
        trigger_references=references_for_revision(
            session, revision_id=revision.id, revision_type="THESIS"
        ),
    )


def company_investment_thesis(
    session: Session,
    company_id: UUID,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyInvestmentThesisRead:
    if session.get(Company, company_id) is None:
        raise DomainError("Company not found", 404)
    statement = select(InvestmentThesisRevision).where(
        InvestmentThesisRevision.company_id == company_id
    )
    if as_of is not None:
        observed_cutoff = datetime.combine(as_of, time.max, UTC)
        statement = statement.where(InvestmentThesisRevision.observed_at <= observed_cutoff)
    if known_at is not None:
        if known_at.tzinfo is None or known_at.utcoffset() is None:
            raise DomainError("known_at must include a timezone offset")
        statement = statement.where(
            InvestmentThesisRevision.recorded_at <= known_at.astimezone(UTC)
        )
    revisions = list(
        session.scalars(
            statement.order_by(
                InvestmentThesisRevision.stream_key,
                InvestmentThesisRevision.revision_number.desc(),
            )
        )
    )
    grouped: dict[str, list[s.InvestmentThesisRevisionRead]] = {}
    for revision in revisions:
        grouped.setdefault(revision.stream_key, []).append(thesis_revision_read(session, revision))
    streams = [
        s.InvestmentThesisStreamRead(
            stream_key=stream_key,
            current_revision=history[0],
            history=history,
        )
        for stream_key, history in sorted(grouped.items())
    ]
    return s.CompanyInvestmentThesisRead(
        company_id=company_id,
        as_of=as_of,
        known_at=known_at,
        streams=streams,
    )
