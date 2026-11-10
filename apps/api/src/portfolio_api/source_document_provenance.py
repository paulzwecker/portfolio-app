"""Conservative source-document attribution warnings for research workflows."""

from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from portfolio_api.domain.models import ResearchTrigger, SourceDocument

SEC_ISSUER_WARNING = (
    "SEC issuer attribution is unverified. Confirm the company against the original source "
    "before relying on this filing."
)
SOURCE_UNAVAILABLE_WARNING = (
    "The cited source document is unavailable at this time. Verify its issuer and evidence "
    "before relying on it."
)
SOURCE_MISMATCH_WARNING = (
    "The cited source document is recorded under a different company. Verify its issuer and "
    "evidence before relying on it."
)


def document_warning(document: SourceDocument) -> str | None:
    return SEC_ISSUER_WARNING if document.provider_id == "sec_edgar" else None


def append_source_warning(text: str, warning: str | None) -> str:
    if warning is None or warning in text:
        return text
    return f"{text} {warning}"


def trigger_document_warnings(
    session: Session, rows: Sequence[ResearchTrigger], cutoff: datetime
) -> dict[UUID, str]:
    """Project warnings without rewriting historical trigger records or their fingerprints."""
    source_ids: dict[UUID, UUID] = {}
    for row in rows:
        if row.source_domain != "source_document":
            continue
        with suppress(ValueError, TypeError, AttributeError):
            source_ids[row.id] = UUID(row.source_record_id)
    docs = (
        {
            doc.id: doc
            for doc in session.scalars(
                select(SourceDocument).where(
                    SourceDocument.id.in_(source_ids.values()),
                    SourceDocument.recorded_at <= cutoff,
                    or_(
                        SourceDocument.retrieved_at.is_(None), SourceDocument.retrieved_at <= cutoff
                    ),
                )
            )
        }
        if source_ids
        else {}
    )
    warnings: dict[UUID, str] = {}
    for row in rows:
        if row.source_domain != "source_document":
            continue
        source_id = source_ids.get(row.id)
        doc = docs.get(source_id) if source_id else None
        if doc is None:
            warnings[row.id] = SOURCE_UNAVAILABLE_WARNING
        elif doc.company_id != row.company_id:
            warnings[row.id] = SOURCE_MISMATCH_WARNING
        elif warning := document_warning(doc):
            warnings[row.id] = warning
    return warnings
