"""Shared manual and scheduled release discovery and reviewer-controlled publication."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from portfolio_api import earnings_release_agent as agent
from portfolio_api import earnings_release_source as source
from portfolio_api.domain import models as m
from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.earnings_inbox import earnings_inbox
from portfolio_api.earnings_review_packet import bind_assessment
from portfolio_api.holding_earnings_publication import PublishInput, review_batch
from portfolio_api.model_revision_proposals import _inputs_read, submit_model_revision_proposal
from portfolio_api.sec_identity import reviewed_cik
from portfolio_api.settings import Settings


class Draft(s.Contract):
    id: UUID
    listing: str
    revision: int
    accession: str
    source_url: str
    assessment: dict[str, object]
    replacement: Decimal | None


class DraftDecision(s.Contract):
    snapshot_id: UUID
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class CheckResult(s.Contract):
    listing: str
    message: str


def held_model(db: Session, portfolio: UUID, listing_id: UUID) -> s.FinancialModelRead:
    inbox = earnings_inbox(db, portfolio)
    if not any(
        r.listing_id == listing_id and r.revision_number and r.listing in source.ISSUERS
        for r in inbox.rows
    ):
        raise services.DomainError("Listing is outside the five modeled holdings", 409)
    model = db.scalars(
        select(m.FinancialModel).where(
            m.FinancialModel.valuation_listing_id == listing_id,
            m.FinancialModel.model_type == "UFCF_DCF_10Y_FADE",
        )
    ).one()
    return queries.financial_model(db, model.id)


def pending(db: Session, portfolio: UUID) -> list[Draft]:
    inbox = earnings_inbox(db, portfolio)
    ids = {r.listing_id for r in inbox.rows if r.revision_number and r.listing in source.ISSUERS}
    rows = db.scalars(
        select(m.EarningsReleaseDraft)
        .join(
            m.FinancialModel,
            m.FinancialModel.current_revision_id == m.EarningsReleaseDraft.base_revision_id,
        )
        .where(
            m.EarningsReleaseDraft.listing_id.in_(ids),
            m.EarningsReleaseDraft.publication_id.is_(None),
        )
        .order_by(m.EarningsReleaseDraft.accession)
    ).all()
    return [
        Draft(
            id=r.id,
            listing=str(r.assessment["listing"]),
            revision=int(str(r.assessment["revision_number"])),
            accession=r.accession,
            source_url=str(r.assessment["source_reference"]),
            assessment=r.assessment,
            replacement=r.replacement,
        )
        for r in rows
    ]


def check_release(
    db: Session, settings: Settings, portfolio: UUID, listing_id: UUID
) -> CheckResult:
    model = held_model(db, portfolio, listing_id)
    listing = f"{model.valuation_listing.venue}:{model.valuation_listing.ticker}"
    if not settings.sec_user_agent:
        raise services.DomainError("SEC contact user agent is missing", 503)
    mappings = db.scalars(
        select(m.CompanyProviderIdentifier).where(
            m.CompanyProviderIdentifier.company_id == model.company_id,
            m.CompanyProviderIdentifier.provider_id == "sec_edgar",
            m.CompanyProviderIdentifier.identifier_type == "SEC_CIK",
        )
    ).all()
    if any(reviewed_cik(mapping) != source.ISSUERS[listing].cik for mapping in mappings):
        raise services.DomainError("Issuer mapping conflicts with reviewed release scope", 409)
    prior = db.scalars(
        select(m.ResearchRevision)
        .where(
            m.ResearchRevision.company_id == model.company_id,
            m.ResearchRevision.status == "PUBLISHED",
            m.ResearchRevision.earnings_review.is_not(None),
        )
        .order_by(m.ResearchRevision.recorded_at.desc())
    ).all()
    reviews = [
        r for r in prior if r.earnings_review and r.earnings_review["listing_id"] == str(listing_id)
    ]
    if not reviews:
        raise services.DomainError("Reviewed launch assessment is missing", 409)
    known = set(
        db.scalars(
            select(m.EarningsReleaseDraft.accession).where(
                m.EarningsReleaseDraft.listing_id == listing_id,
                or_(
                    m.EarningsReleaseDraft.publication_id.is_not(None),
                    m.EarningsReleaseDraft.base_revision_id == model.current_revision_id,
                ),
            )
        )
    )
    filings = source.announcements(
        listing,
        settings.sec_user_agent,
        baseline_reviewed=any(
            r.source_reference == source.BASELINE_SOURCES[listing] for r in reviews
        ),
    )
    year = next(
        y
        for sc in model.current_revision.scenarios
        if sc.scenario == "BASE"
        for y in sc.years
        if y.forecast_year == 1
    )
    assumptions = {
        key: str(getattr(year, key))
        for key in ("revenue_growth", "ebit_margin", "capex_to_revenue")
    }
    for filing in filings:
        if filing.accession in known:
            continue
        url, body = source.release_text(filing, settings.sec_user_agent)
        if any(r.source_reference == url for r in reviews):
            continue
        result = agent.assess(
            settings, listing, body, assumptions, reviews[0].rationale, filing.filed
        )
        data = dict(
            listing=listing,
            revision_number=model.current_revision.revision_number,
            contract_type="ResearchRevisionContractV1",
            contract_version="1.2.0",
            author_id="earnings-release-agent",
            source_id="sec_edgar",
            source_reference=url,
            observed_at=datetime.now(UTC).isoformat(),
            rationale=result.rationale,
            uncertainty=result.uncertainty,
            assessments=[
                dict(
                    assessment_type="BUSINESS_OUTLOOK",
                    status="AVAILABLE",
                    narrative=result.rationale,
                )
            ],
            evidence=[
                dict(
                    source_name=listing + " earnings release",
                    source_url=url,
                    external_identifier=filing.accession,
                    published_at=str(filing.filed),
                    excerpt=result.passage,
                )
            ],
            earnings_review=dict(
                period=result.period,
                period_end=str(result.period_end),
                driver=result.driver,
                conclusion=result.conclusion,
                comparable_period=result.comparable_period,
                accepted_base_year_one=assumptions[result.driver],
            ),
        )
        bind_assessment(model, data)
        if result.replacement is not None:
            s.DcfYearAssumptionInput.model_validate(
                {
                    **year.model_dump(exclude={"id", "scenario_id"}),
                    result.driver: result.replacement,
                }
            )
        services.portfolio(db, portfolio, lock=True)
        current = db.scalar(
            select(m.FinancialModel.current_revision_id)
            .where(m.FinancialModel.id == model.id)
            .with_for_update()
        )
        if (
            current != model.current_revision_id
            or held_model(db, portfolio, listing_id).id != model.id
        ):
            raise services.DomainError("Holding or accepted revision changed. Check again.", 409)
        if (
            db.scalar(
                select(m.EarningsReleaseDraft.id).where(
                    m.EarningsReleaseDraft.listing_id == listing_id,
                    m.EarningsReleaseDraft.accession == filing.accession,
                    or_(
                        m.EarningsReleaseDraft.publication_id.is_not(None),
                        m.EarningsReleaseDraft.base_revision_id == current,
                    ),
                )
            )
            is None
        ):
            db.add(
                m.EarningsReleaseDraft(
                    listing_id=listing_id,
                    base_revision_id=current,
                    accession=filing.accession,
                    assessment=data,
                    replacement=result.replacement,
                )
            )
            db.flush()
        return CheckResult(listing=listing, message="Release draft ready")
    return CheckResult(listing=listing, message="No unreviewed release found")


def publish_draft(
    db: Session, portfolio: UUID, draft_id: UUID, snapshot: UUID, digest: str
) -> UUID:
    services.portfolio(db, portfolio, lock=True)
    draft = db.scalar(
        select(m.EarningsReleaseDraft)
        .where(m.EarningsReleaseDraft.id == draft_id)
        .with_for_update()
    )
    if draft is None:
        raise services.DomainError("Draft not found", 404)
    model = held_model(db, portfolio, draft.listing_id)
    if draft.publication_id:
        return draft.publication_id
    if model.current_revision_id != draft.base_revision_id:
        raise services.DomainError("Accepted model changed. Check for releases again.", 409)
    receipt = review_batch(
        db,
        portfolio,
        PublishInput(snapshot_id=snapshot, assessments=[draft.assessment], digest=digest),
    )
    draft.publication_id = receipt.revision_ids[0]
    if draft.replacement is not None:
        inputs = _inputs_read(model)
        assert isinstance(inputs, s.DcfCalculationInput)
        year = next(
            y
            for sc in inputs.scenarios
            if sc.scenario == "BASE"
            for y in sc.years
            if y.forecast_year == 1
        )
        setattr(year, receipt.items[0].driver, draft.replacement)
        proposal = s.FinancialModelRevisionProposalV1.model_validate(
            dict(
                contract_type="FinancialModelRevisionProposalV1",
                contract_version="1.0.0",
                external_revision_id=str(draft.id),
                model_id=model.id,
                company_id=model.company_id,
                valuation_listing_id=draft.listing_id,
                model_currency=model.model_currency,
                base_revision_id=draft.base_revision_id,
                base_revision_number=model.current_revision.revision_number,
                methodology_version=model.current_revision.methodology_version,
                authored_at=draft.assessment["observed_at"],
                effective_at=draft.assessment["observed_at"],
                source_reference=draft.assessment["source_reference"],
                rationale=draft.assessment["rationale"],
                supporting_evidence=[
                    dict(
                        evidence_type="RESEARCH_REVISION",
                        relationship="SUPPORTS",
                        reference_id=draft.publication_id,
                        note="Reviewed earnings exhibit",
                    )
                ],
                method=dict(methodology=model.model_type, inputs=inputs.model_dump(mode="json")),
            )
        )
        draft.proposal_id = submit_model_revision_proposal(
            db, proposal, producer_id="earnings-release-agent"
        ).proposal.id
    db.flush()
    return draft.publication_id
