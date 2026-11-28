"""Portfolio earnings reviews from immutable publications and saved model comparisons."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    AgentModelRevisionProposal,
    Company,
    DcfScenarioAssumptions,
    DcfYearAssumption,
    FinancialModel,
    FinancialModelRevision,
    HoldingPosition,
    HoldingSnapshot,
    Listing,
    Portfolio,
    ResearchEvidence,
    ResearchRevision,
    Security,
    SourceDocument,
)
from portfolio_api.domain.services import DomainError

DOCUMENT_TYPES = ("10-K", "10-Q", "20-F", "ANNUAL_REPORT", "EARNINGS_RELEASE")
HURDLE = Decimal("0.15")


class Review(s.Contract):
    listing_id: UUID
    company_id: UUID | None
    listing: str
    company: str
    revision_number: int | None
    title: str
    url: str | None = None
    period: str | None = None
    published_at: date | None = None
    outcome: str = "Awaiting assessment"
    rationale: str | None = None
    passage: str | None = None
    comparison: str | None = None
    proposal_id: UUID | None = None
    decision_note: str | None = None
    reviewed_at: datetime | None = None
    irr_before: Decimal | None = None
    irr_after: Decimal | None = None
    impact_bps: Decimal | None = None
    crosses_hurdle: bool = False
    price_status: str | None = None
    comparison_price_date: date | None = None


class Inbox(s.Contract):
    portfolio_id: UUID
    snapshot_id: UUID | None
    effective_at: datetime | None
    listing_count: int
    modeled_count: int
    rows: list[Review]


def validate_assessment(
    session: Session, company_id: UUID, review: s.EarningsAssessment, security_id: UUID | None
) -> None:
    row = session.execute(
        select(FinancialModel, Listing, DcfYearAssumption)
        .select_from(FinancialModel)
        .join(Listing, Listing.id == FinancialModel.valuation_listing_id)
        .join(
            DcfScenarioAssumptions,
            DcfScenarioAssumptions.revision_id == FinancialModel.current_revision_id,
        )
        .join(DcfYearAssumption, DcfYearAssumption.scenario_id == DcfScenarioAssumptions.id)
        .where(
            FinancialModel.company_id == company_id,
            Listing.id == review.listing_id,
            FinancialModel.current_revision_id == review.base_revision_id,
            DcfScenarioAssumptions.scenario == "BASE",
            DcfYearAssumption.forecast_year == 1,
        )
    ).one_or_none()
    if row is None or (security_id is not None and row[1].security_id != security_id):
        raise DomainError(
            "Earnings assessment requires the current revision of the held listing's DCF", 409
        )
    if getattr(row[2], review.driver) != review.accepted_base_year_one:
        raise DomainError("Reviewed assumption differs from the accepted base year one", 409)


def add_impact(row: Review, proposal: AgentModelRevisionProposal) -> None:
    row.proposal_id = proposal.id
    row.outcome = proposal.status
    row.decision_note = proposal.decision_note
    row.reviewed_at = proposal.reviewed_at
    row.rationale = proposal.rationale
    if not proposal.preview_data:
        return
    preview = s.ModelRevisionProposalPreviewRead.model_validate(proposal.preview_data)
    old, new = preview.current_outputs or {}, preview.proposed_outputs or {}
    row.price_status = str(new.get("price_status") or "Unavailable")
    if (
        preview.status != "READY"
        or row.price_status != "FRESH"
        or old.get("price_status") != "FRESH"
        or not old.get("price_observation_id")
        or old.get("price_observation_id") != new.get("price_observation_id")
    ):
        return
    before, after = old.get("expected_cash_flow_irr"), new.get("expected_cash_flow_irr")
    if before is None or after is None:
        return
    effective_at = new.get("price_effective_at")
    if isinstance(effective_at, str) and effective_at == old.get("price_effective_at"):
        row.comparison_price_date = datetime.fromisoformat(effective_at).date()
    row.irr_before, row.irr_after = Decimal(str(before)), Decimal(str(after))
    row.impact_bps = (row.irr_after - row.irr_before) * 10000
    row.crosses_hurdle = (row.irr_before >= HURDLE) != (row.irr_after >= HURDLE)


def earnings_inbox(session: Session, portfolio_id: UUID) -> Inbox:
    if session.get(Portfolio, portfolio_id) is None:
        raise DomainError("Portfolio not found", 404)
    snapshot = session.scalar(
        select(HoldingSnapshot)
        .where(
            HoldingSnapshot.portfolio_id == portfolio_id, HoldingSnapshot.completeness == "COMPLETE"
        )
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.id)
        .limit(1)
    )
    inbox = Inbox(
        portfolio_id=portfolio_id,
        snapshot_id=snapshot.id if snapshot else None,
        effective_at=snapshot.effective_at if snapshot else None,
        listing_count=0,
        modeled_count=0,
        rows=[],
    )
    if snapshot is None:
        return inbox
    holdings = session.execute(
        select(Listing, Company, FinancialModelRevision)
        .select_from(HoldingPosition)
        .join(Listing, Listing.id == HoldingPosition.listing_id)
        .join(Security, Security.id == Listing.security_id)
        .outerjoin(Company, Company.id == Security.company_id)
        .outerjoin(
            FinancialModel,
            (FinancialModel.valuation_listing_id == Listing.id)
            & (FinancialModel.model_type == "UFCF_DCF_10Y_FADE"),
        )
        .outerjoin(
            FinancialModelRevision, FinancialModelRevision.id == FinancialModel.current_revision_id
        )
        .where(HoldingPosition.snapshot_id == snapshot.id, HoldingPosition.quantity > 0)
    ).all()
    inbox.listing_count = len(holdings)
    companies = {company.id for _, company, _ in holdings if company is not None}
    documents = session.scalars(
        select(SourceDocument)
        .where(
            SourceDocument.company_id.in_(companies),
            SourceDocument.document_type.in_(DOCUMENT_TYPES),
            SourceDocument.data_quality == "PASS",
        )
        .order_by(SourceDocument.recorded_at, SourceDocument.id)
    ).all()
    research = session.execute(
        select(ResearchRevision, ResearchEvidence)
        .join(ResearchEvidence, ResearchEvidence.revision_id == ResearchRevision.id)
        .where(
            ResearchRevision.company_id.in_(companies),
            ResearchRevision.status == "PUBLISHED",
            ResearchEvidence.source_url == ResearchRevision.source_reference,
        )
        .order_by(ResearchRevision.revision_number.desc(), ResearchEvidence.id)
    ).all()
    proposals = session.scalars(
        select(AgentModelRevisionProposal).where(
            AgentModelRevisionProposal.valuation_listing_id.in_(
                [listing.id for listing, _, _ in holdings]
            ),
            AgentModelRevisionProposal.model_type == "UFCF_DCF_10Y_FADE",
        )
    ).all()
    superseded = set(
        session.scalars(
            select(ResearchRevision.supersedes_revision_id).where(
                ResearchRevision.company_id.in_(companies),
                ResearchRevision.supersedes_revision_id.is_not(None),
            )
        )
    )
    for listing, company, revision in holdings:
        inbox.modeled_count += int(revision is not None)
        base = Review(
            listing_id=listing.id,
            company_id=company.id if company else None,
            listing=f"{listing.venue}:{listing.ticker}",
            company=company.name if company else listing.ticker,
            revision_number=revision.revision_number if revision else None,
            title="No earnings publication recorded",
        )
        if company is None:
            inbox.rows.append(base)
            continue
        publications = {
            doc.canonical_url: base.model_copy(
                update=dict(
                    title=doc.title,
                    url=doc.canonical_url,
                    period=doc.reporting_period
                    or (str(doc.period_end) if doc.period_end else None),
                    published_at=doc.published_at or doc.filed_at,
                )
            )
            for doc in documents
            if doc.company_id == company.id
            and (not doc.security_id or doc.security_id == listing.security_id)
        }
        assessments: dict[UUID, Review] = {}
        for packet, evidence in research:
            if packet.company_id != company.id or (
                packet.security_id and packet.security_id != listing.security_id
            ):
                continue
            assessment = (
                s.EarningsAssessment.model_validate(packet.earnings_review)
                if packet.earnings_review
                else None
            )
            url = packet.source_reference
            if assessment and (assessment.listing_id != listing.id or not evidence.excerpt):
                continue
            if (
                not assessment
                and url not in publications
                and "earnings release" not in evidence.source_name.lower()
            ):
                continue
            if packet.id in assessments or packet.id in superseded:
                continue
            pub = publications.setdefault(
                url,
                base.model_copy(
                    update=dict(
                        title=evidence.source_name, url=url, published_at=evidence.published_at
                    )
                ),
            )
            row = pub.model_copy()
            row.passage = evidence.excerpt
            row.rationale = packet.rationale
            if assessment:
                row.period = assessment.period
                row.outcome = assessment.conclusion
                row.comparison = (
                    f"Base year 1 {assessment.driver.replace('_', ' ')} "
                    f"{assessment.accepted_base_year_one:.2%} · {assessment.comparable_period}"
                )
            assessments[packet.id] = row
        detailed = []
        linked: set[UUID] = set()
        for proposal in proposals:
            if proposal.valuation_listing_id != listing.id:
                continue
            ids = {
                e.get("reference_id")
                for e in proposal.supporting_evidence
                if e.get("evidence_type") == "RESEARCH_REVISION"
            }
            matched = [
                (key, row)
                for key, row in assessments.items()
                if str(key) in ids and row.url == proposal.source_reference
            ]
            if not matched and proposal.source_reference not in publications:
                continue
            row = (
                matched[0][1] if matched else publications[proposal.source_reference]
            ).model_copy()
            linked.update(key for key, _ in matched)
            add_impact(row, proposal)
            detailed.append(row)
        detailed.extend(row for key, row in assessments.items() if key not in linked)
        reviewed_urls = {row.url for row in detailed}
        detailed.extend(row for url, row in publications.items() if url not in reviewed_urls)
        inbox.rows.extend(detailed or [base])
    inbox.rows.sort(
        key=lambda r: (
            r.outcome in {"ACCEPTED", "REJECTED"},
            not r.crosses_hurdle,
            r.impact_bps is None,
            -abs(r.impact_bps or Decimal(0)),
            r.url is None,
            -(r.published_at or date.min).toordinal(),
            r.listing,
            r.title,
            str(r.proposal_id or ""),
        )
    )
    return inbox
