"""Resolve and retain typed links from model revisions to published research."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    FinancialModelRevisionEvidence,
    InvestmentThesisClaim,
    InvestmentThesisRevision,
    ResearchForecast,
    ResearchRevision,
)
from portfolio_api.research_trigger_links import references_for_revision


def _check_revision_identity(
    *,
    company_id: UUID,
    security_id: UUID,
    record_company_id: UUID,
    record_security_id: UUID | None,
    status: str,
    label: str,
) -> None:
    if status != "PUBLISHED":
        raise ValueError(f"{label} must reference a published research revision")
    if record_company_id != company_id:
        raise ValueError(f"{label} belongs to a different company")
    if record_security_id is not None and record_security_id != security_id:
        raise ValueError(f"{label} belongs to a different security/listing basis")


def resolve_model_evidence_reference(
    session: Session,
    *,
    company_id: UUID,
    security_id: UUID,
    reference: s.FinancialModelEvidenceReference,
) -> tuple[dict[str, object], s.FinancialModelEvidenceRead]:
    """Validate a canonical evidence identity and return its storage/read models."""
    record_id = reference.reference_id
    evidence_type = reference.evidence_type
    foreign_key_name: str
    author_id: str | None
    source_reference: str | None
    observed_at: datetime | None
    recorded_at: datetime
    trigger_references: list[s.ResearchTriggerReferenceRead] = []
    if evidence_type == "RESEARCH_REVISION":
        research_revision = session.get(ResearchRevision, record_id)
        if research_revision is None:
            raise ValueError("Referenced research revision does not exist")
        _check_revision_identity(
            company_id=company_id,
            security_id=security_id,
            record_company_id=research_revision.company_id,
            record_security_id=research_revision.security_id,
            status=research_revision.status,
            label="Research revision",
        )
        foreign_key_name = "research_revision_id"
        summary = research_revision.rationale
        evidence_status = research_revision.status
        author_id = research_revision.author_id
        source_reference = research_revision.source_reference
        observed_at = research_revision.observed_at
        recorded_at = research_revision.recorded_at
        trigger_references = references_for_revision(
            session, revision_id=research_revision.id, revision_type="RESEARCH"
        )
    elif evidence_type == "RESEARCH_FORECAST":
        forecast = session.get(ResearchForecast, record_id)
        if forecast is None:
            raise ValueError("Referenced research forecast does not exist")
        research_revision = session.get(ResearchRevision, forecast.revision_id)
        if research_revision is None:
            raise ValueError("Research forecast has no source revision")
        _check_revision_identity(
            company_id=company_id,
            security_id=security_id,
            record_company_id=research_revision.company_id,
            record_security_id=research_revision.security_id,
            status=research_revision.status,
            label="Research forecast",
        )
        foreign_key_name = "research_forecast_id"
        period = (
            f"FY{forecast.fiscal_year}"
            if forecast.fiscal_period == "FY"
            else (f"{forecast.fiscal_period} FY{forecast.fiscal_year}")
        )
        value = "unavailable" if forecast.value is None else str(forecast.value)
        currency = f" {forecast.currency}" if forecast.currency else ""
        summary = (
            f"{forecast.metric} {period} {forecast.scenario}: {value}{currency} "
            f"({forecast.availability_status})"
        )
        evidence_status = forecast.availability_status
        author_id = research_revision.author_id
        source_reference = research_revision.source_reference
        observed_at = research_revision.observed_at
        recorded_at = research_revision.recorded_at
        trigger_references = references_for_revision(
            session, revision_id=research_revision.id, revision_type="RESEARCH"
        )
    elif evidence_type == "THESIS_REVISION":
        thesis_revision = session.get(InvestmentThesisRevision, record_id)
        if thesis_revision is None:
            raise ValueError("Referenced investment-thesis revision does not exist")
        _check_revision_identity(
            company_id=company_id,
            security_id=security_id,
            record_company_id=thesis_revision.company_id,
            record_security_id=thesis_revision.security_id,
            status=thesis_revision.status,
            label="Investment-thesis revision",
        )
        foreign_key_name = "thesis_revision_id"
        summary = thesis_revision.thesis_statement or thesis_revision.rationale
        evidence_status = thesis_revision.status
        author_id = thesis_revision.author_id
        source_reference = thesis_revision.source_reference
        observed_at = thesis_revision.observed_at
        recorded_at = thesis_revision.recorded_at
        trigger_references = references_for_revision(
            session, revision_id=thesis_revision.id, revision_type="THESIS"
        )
    else:
        claim = session.get(InvestmentThesisClaim, record_id)
        if claim is None:
            raise ValueError("Referenced investment-thesis claim does not exist")
        thesis_revision = session.get(InvestmentThesisRevision, claim.revision_id)
        if thesis_revision is None:
            raise ValueError("Investment-thesis claim has no source revision")
        _check_revision_identity(
            company_id=company_id,
            security_id=security_id,
            record_company_id=thesis_revision.company_id,
            record_security_id=thesis_revision.security_id,
            status=thesis_revision.status,
            label="Investment-thesis claim",
        )
        foreign_key_name = "thesis_claim_id"
        summary = f"{claim.claim_type}: {claim.statement}"
        evidence_status = claim.status
        author_id = thesis_revision.author_id
        source_reference = thesis_revision.source_reference
        observed_at = thesis_revision.observed_at
        recorded_at = thesis_revision.recorded_at
        trigger_references = references_for_revision(
            session, revision_id=thesis_revision.id, revision_type="THESIS"
        )

    values: dict[str, object] = {
        "evidence_type": evidence_type,
        "relationship": reference.relationship,
        "note": reference.note,
        "research_revision_id": None,
        "research_forecast_id": None,
        "thesis_revision_id": None,
        "thesis_claim_id": None,
    }
    values[foreign_key_name] = record_id
    read = s.FinancialModelEvidenceRead(
        evidence_type=evidence_type,
        reference_id=record_id,
        relationship=reference.relationship,
        note=reference.note,
        summary=summary,
        evidence_status=evidence_status,
        author_id=author_id,
        source_reference=source_reference,
        observed_at=observed_at,
        recorded_at=recorded_at,
        resolution_status="VERIFIED",
        resolution_issue=None,
        trigger_references=trigger_references,
    )
    return values, read


def persist_model_revision_evidence(
    session: Session,
    *,
    revision_id: UUID,
    company_id: UUID,
    security_id: UUID,
    references: list[s.FinancialModelEvidenceReference],
) -> None:
    for reference in references:
        values, _ = resolve_model_evidence_reference(
            session,
            company_id=company_id,
            security_id=security_id,
            reference=reference,
        )
        session.add(FinancialModelRevisionEvidence(revision_id=revision_id, **values))
    session.flush()


def unresolved_model_evidence_read(
    reference: s.FinancialModelEvidenceReference,
    *,
    recorded_at: datetime,
    issue: str,
) -> s.FinancialModelEvidenceRead:
    return s.FinancialModelEvidenceRead(
        evidence_type=reference.evidence_type,
        reference_id=reference.reference_id,
        relationship=reference.relationship,
        note=reference.note,
        summary=None,
        evidence_status="UNRESOLVED",
        author_id=None,
        source_reference=None,
        observed_at=None,
        recorded_at=recorded_at,
        resolution_status="UNRESOLVED",
        resolution_issue=issue,
    )


def stored_evidence_reference(
    row: FinancialModelRevisionEvidence,
) -> s.FinancialModelEvidenceReference:
    reference_ids = {
        "RESEARCH_REVISION": row.research_revision_id,
        "RESEARCH_FORECAST": row.research_forecast_id,
        "THESIS_REVISION": row.thesis_revision_id,
        "THESIS_CLAIM": row.thesis_claim_id,
    }
    reference_id = reference_ids[row.evidence_type]
    if reference_id is None:
        raise ValueError("Stored model evidence reference is incomplete")
    return s.FinancialModelEvidenceReference(
        evidence_type=row.evidence_type,
        reference_id=reference_id,
        relationship=row.relationship,
        note=row.note,
    )
