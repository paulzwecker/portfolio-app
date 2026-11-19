"""Bounded, read-only canonical company context for research agents."""

from datetime import UTC, date, datetime, time
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api import company_observations as observations
from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    FinancialModel,
    FinancialModelRevision,
    InvestmentThesisRevision,
    Lifecycle,
    LifecycleEvent,
    Listing,
    Portfolio,
    ResearchRevision,
    Security,
    now,
)
from portfolio_api.investment_thesis import thesis_revision_read
from portfolio_api.research_forecasts import research_revision_read

# The response is a working context, not an exhaustive historical export.
MAX_OBSERVATIONS = 80
MAX_GUIDANCE = 40
MAX_DEFINITIONS = 80
MAX_CONSENSUS_PERIODS = 24
MAX_STREAMS = 8
MAX_MODELS = 8
MAX_DRIVERS = 90


class AgentContextCoverage(s.Contract):
    status: Literal["AVAILABLE", "PARTIAL", "NO_DATA", "AMBIGUOUS", "UNSUPPORTED"]
    reason: str | None = None
    latest_recorded_at: datetime | None = None
    truncated: bool = False


class AgentContextNativeModel(s.Contract):
    model_id: UUID
    model_name: str
    model_type: str
    valuation_listing_id: UUID
    model_currency: str
    accepted_revision: s.FinancialModelRevisionSummary
    driver_projections: list[observations.FinancialModelDriverProjectionRead]
    drivers_truncated: bool
    revision_history_href: str


class CompanyAgentContextV1(s.Contract):
    contract_type: Literal["CompanyAgentContextV1"] = "CompanyAgentContextV1"
    contract_version: Literal["1.0.0"] = "1.0.0"
    generated_at: datetime
    as_of: date
    known_at: datetime
    identity: AgentContextCoverage
    company: s.CompanyRead
    securities: list[s.SecurityRead]
    listings: list[s.ListingRead]
    portfolio_status: AgentContextCoverage
    portfolio_id: UUID | None
    portfolio_snapshot_id: UUID | None
    portfolio_target_revision_id: UUID | None
    portfolio_holdings_authority: s.HoldingsAuthorityRead | None
    portfolio: s.CompanyPortfolioContext | None
    metrics_status: AgentContextCoverage
    metric_definitions: list[observations.CompanyMetricDefinitionRead]
    metric_observations: list[observations.CompanyMetricObservationRead]
    guidance_status: AgentContextCoverage
    guidance_observations: list[observations.CompanyGuidanceObservationRead]
    consensus_status: AgentContextCoverage
    consensus_continuity_status: str
    consensus_provider_id: str | None
    consensus_periods: list[s.ConsensusEstimatePeriodRead]
    research_status: AgentContextCoverage
    current_research: list[s.ResearchRevisionRead]
    thesis_status: AgentContextCoverage
    current_theses: list[s.InvestmentThesisRevisionRead]
    native_models_status: AgentContextCoverage
    native_models: list[AgentContextNativeModel]
    imported_outputs_status: AgentContextCoverage
    imported_model_outputs: s.CompanyModelOutputsCurrentRead | None
    resource_links: dict[str, str]


def _coverage(
    count: int,
    *,
    truncated: bool = False,
    latest: datetime | None = None,
    reason: str | None = None,
) -> AgentContextCoverage:
    return AgentContextCoverage(
        status="PARTIAL" if truncated else "AVAILABLE" if count else "NO_DATA",
        reason=reason,
        latest_recorded_at=latest,
        truncated=truncated,
    )


def company_agent_context(
    session: Session,
    company_id: UUID,
    portfolio_id: UUID | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    data_universe_only: bool = False,
) -> CompanyAgentContextV1:
    """Compose accepted domains; do not infer data or mutate canonical state."""
    requested_at = now()
    day = as_of or (known_at.astimezone(UTC).date() if known_at else requested_at.date())
    # No implicit knowledge from after the requested as-of day.
    as_of_end = datetime.combine(day, time.max, UTC)
    cutoff = min(known_at.astimezone(UTC) if known_at else requested_at, as_of_end, requested_at)
    day = min(day, cutoff.date())

    company = services.company(session, company_id)
    if company.created_at > cutoff:
        raise services.DomainError("Company did not exist at the requested cutoff", 404)

    security_rows = list(
        session.scalars(
            select(Security)
            .where(Security.company_id == company_id, Security.created_at <= cutoff)
            .order_by(Security.name, Security.id)
        )
    )
    listing_rows = list(
        session.scalars(
            select(Listing)
            .where(
                Listing.security_id.in_([row.id for row in security_rows]),
                Listing.created_at <= cutoff,
            )
            .order_by(Listing.ticker, Listing.venue, Listing.id)
        )
    )
    company_read = q.company_read(session, company)
    if as_of is not None or known_at is not None:
        lifecycle = session.scalar(
            select(LifecycleEvent)
            .where(
                LifecycleEvent.company_id == company_id,
                LifecycleEvent.effective_at <= cutoff,
                LifecycleEvent.recorded_at <= cutoff,
            )
            .order_by(LifecycleEvent.sequence.desc())
            .limit(1)
        )
        company_read = company_read.model_copy(
            update={
                "lifecycle": Lifecycle(lifecycle.new_state) if lifecycle else None,
                "lifecycle_event_id": lifecycle.id if lifecycle else None,
            }
        )

    portfolios: list[UUID] = []
    if not data_universe_only:
        portfolios = list(
            session.scalars(
                select(Portfolio.id)
                .where(Portfolio.created_at <= cutoff)
                .order_by(Portfolio.created_at, Portfolio.id)
                .limit(2)
            )
        )

    selected_portfolio_id = None if data_universe_only else portfolio_id
    portfolio_status = AgentContextCoverage(
        status="UNSUPPORTED" if data_universe_only else "NO_DATA",
        reason=(
            "Outside Data & Universe read scope" if data_universe_only else "No portfolio exists"
        ),
    )
    portfolio_view: s.CompanyPortfolioContext | None = None
    snapshot_id: UUID | None = None
    target_revision_id: UUID | None = None
    holdings_authority: s.HoldingsAuthorityRead | None = None
    if selected_portfolio_id is None and len(portfolios) == 1:
        selected_portfolio_id = portfolios[0]
    elif selected_portfolio_id is None and len(portfolios) > 1:
        portfolio_status = AgentContextCoverage(
            status="AMBIGUOUS", reason="Supply portfolio_id when multiple portfolios exist"
        )
    if selected_portfolio_id is not None:
        portfolio = session.get(Portfolio, selected_portfolio_id)
        if portfolio is None or portfolio.created_at > cutoff:
            raise services.DomainError("Portfolio was not found at the requested cutoff", 404)
        view = q.overview(session, selected_portfolio_id, as_of=cutoff)
        portfolio_view = next(
            (item for item in view.companies if item.company.id == company_id), None
        )
        if portfolio_view is not None and (as_of is not None or known_at is not None):
            portfolio_view = portfolio_view.model_copy(update={"company": company_read})
        snapshot_id = view.snapshot.id if view.snapshot else None
        target_revision_id = view.target_revision.id if view.target_revision else None
        holdings_authority = view.holdings_authority
        portfolio_status = AgentContextCoverage(
            status="AVAILABLE" if portfolio_view else "NO_DATA",
            reason=None if portfolio_view else "Company has no accepted holding or target",
            latest_recorded_at=view.snapshot.recorded_at if view.snapshot else None,
        )

    definitions = [
        item
        for item in observations.metric_definitions(session, company_id)
        if item.created_at <= cutoff
    ]
    actuals = observations.company_metric_history(
        session, company_id, as_of=day, known_at=cutoff, limit=MAX_OBSERVATIONS + 1
    )
    # Guidance targets may end in the future; visibility follows issue/recording time.
    guidance = observations.company_guidance_history(
        session, company_id, known_at=cutoff, current_only=True, limit=MAX_GUIDANCE + 1
    )
    metrics_truncated = len(definitions) > MAX_DEFINITIONS or len(actuals) > MAX_OBSERVATIONS
    guidance_truncated = len(guidance) > MAX_GUIDANCE
    definitions = definitions[:MAX_DEFINITIONS]
    actuals = actuals[:MAX_OBSERVATIONS]
    guidance = guidance[:MAX_GUIDANCE]

    consensus = q.company_consensus_estimates(session, company_id, as_of=day, known_at=cutoff)
    selected = next((p for p in consensus.providers if p.selected), None)
    consensus_periods = selected.periods if selected else []
    consensus_periods.sort(key=lambda item: item.period_end or date.min, reverse=True)
    consensus_truncated = len(consensus_periods) > MAX_CONSENSUS_PERIODS
    # Full provider revision history is accessible through the linked domain API.
    consensus_periods = [
        item.model_copy(update={"history": []})
        for item in consensus_periods[:MAX_CONSENSUS_PERIODS]
    ]

    research_rows: list[ResearchRevision] = []
    if not data_universe_only:
        research_rows = list(
            session.scalars(
                select(ResearchRevision)
                .where(
                    ResearchRevision.company_id == company_id,
                    ResearchRevision.observed_at <= cutoff,
                    ResearchRevision.recorded_at <= cutoff,
                )
                .distinct(ResearchRevision.stream_key)
                .order_by(ResearchRevision.stream_key, ResearchRevision.revision_number.desc())
                .limit(MAX_STREAMS + 1)
            )
        )

    research_truncated = len(research_rows) > MAX_STREAMS
    current_research: list[s.ResearchRevisionRead] = []
    for row in research_rows[:MAX_STREAMS]:
        current = research_revision_read(session, row)
        if (
            len(current.forecasts) > 30
            or len(current.assessments) > 20
            or len(current.evidence) > 20
            or len(current.trigger_references) > 20
        ):
            research_truncated = True
        current_research.append(
            current.model_copy(
                update={
                    "forecasts": current.forecasts[:30],
                    "assessments": current.assessments[:20],
                    "evidence": current.evidence[:20],
                    "trigger_references": current.trigger_references[:20],
                }
            )
        )

    thesis_rows: list[InvestmentThesisRevision] = []
    if not data_universe_only:
        thesis_rows = list(
            session.scalars(
                select(InvestmentThesisRevision)
                .where(
                    InvestmentThesisRevision.company_id == company_id,
                    InvestmentThesisRevision.observed_at <= cutoff,
                    InvestmentThesisRevision.recorded_at <= cutoff,
                )
                .distinct(InvestmentThesisRevision.stream_key)
                .order_by(
                    InvestmentThesisRevision.stream_key,
                    InvestmentThesisRevision.revision_number.desc(),
                )
                .limit(MAX_STREAMS + 1)
            )
        )

    thesis_truncated = len(thesis_rows) > MAX_STREAMS
    current_theses: list[s.InvestmentThesisRevisionRead] = []
    for thesis_row in thesis_rows[:MAX_STREAMS]:
        thesis_current = thesis_revision_read(session, thesis_row)
        if len(thesis_current.claims) > 20 or len(thesis_current.trigger_references) > 20:
            thesis_truncated = True
        claims = []
        for claim in thesis_current.claims[:20]:
            if len(claim.evidence) > 10:
                thesis_truncated = True
            claims.append(claim.model_copy(update={"evidence": claim.evidence[:10]}))
        current_theses.append(
            thesis_current.model_copy(
                update={
                    "claims": claims,
                    "trigger_references": thesis_current.trigger_references[:20],
                }
            )
        )

    model_rows: list[FinancialModel] = []
    if not data_universe_only:
        model_rows = list(
            session.scalars(
                select(FinancialModel)
                .where(
                    FinancialModel.company_id == company_id,
                    FinancialModel.created_at <= cutoff,
                    FinancialModel.current_revision_id.is_not(None),
                )
                .order_by(FinancialModel.model_name, FinancialModel.id)
                .limit(MAX_MODELS + 1)
            )
        )

    models_truncated = len(model_rows) > MAX_MODELS
    models: list[AgentContextNativeModel] = []
    for model in model_rows[:MAX_MODELS]:
        revision = session.scalar(
            select(FinancialModelRevision)
            .where(
                FinancialModelRevision.model_id == model.id,
                FinancialModelRevision.effective_at <= cutoff,
                FinancialModelRevision.recorded_at <= cutoff,
            )
            .order_by(FinancialModelRevision.revision_number.desc())
            .limit(1)
        )
        if revision is None:
            continue
        summary = q._financial_model_revision_summary(session, revision)
        if len(summary.supporting_evidence) > 20:
            models_truncated = True
            summary = summary.model_copy(
                update={"supporting_evidence": summary.supporting_evidence[:20]}
            )
        drivers = [
            item
            for item in observations.model_driver_projections(session, model.id, revision.id)
            if item.recorded_at <= cutoff
        ]
        if len(drivers) > MAX_DRIVERS:
            models_truncated = True
        models.append(
            AgentContextNativeModel(
                model_id=model.id,
                model_name=model.model_name,
                model_type=model.model_type,
                valuation_listing_id=model.valuation_listing_id,
                model_currency=model.model_currency,
                accepted_revision=summary,
                driver_projections=drivers[:MAX_DRIVERS],
                drivers_truncated=len(drivers) > MAX_DRIVERS,
                revision_history_href=f"/v1/financial-models/{model.id}/revisions",
            )
        )

    imported_outputs: s.CompanyModelOutputsCurrentRead | None = None
    if data_universe_only:
        imported_status = AgentContextCoverage(
            status="UNSUPPORTED", reason="Outside Data & Universe read scope"
        )
    elif as_of is not None or known_at is not None:
        imported_status = AgentContextCoverage(
            status="UNSUPPORTED",
            reason="Imported current snapshots have no verified point-in-time context read",
        )
    else:
        imported_outputs = q.company_model_outputs_current(session, company_id)
        imported_truncated = len(imported_outputs.models) > MAX_MODELS
        if imported_truncated:
            imported_outputs = imported_outputs.model_copy(
                update={
                    "models": imported_outputs.models[:MAX_MODELS],
                }
            )
        imported_status = _coverage(
            len(imported_outputs.models),
            truncated=imported_truncated
            or (bool(imported_outputs.models) and imported_outputs.status != "AVAILABLE"),
            reason=(None if imported_outputs.status == "AVAILABLE" else imported_outputs.status),
        )

    root = f"/v1/companies/{company_id}"
    restricted = AgentContextCoverage(
        status="UNSUPPORTED", reason="Outside Data & Universe read scope"
    )
    return CompanyAgentContextV1(
        generated_at=requested_at,
        as_of=day,
        known_at=cutoff,
        identity=_coverage(len(security_rows) + len(listing_rows) + 1),
        company=company_read,
        securities=[s.SecurityRead.model_validate(item) for item in security_rows],
        listings=[s.ListingRead.model_validate(item) for item in listing_rows],
        portfolio_status=portfolio_status,
        portfolio_id=selected_portfolio_id,
        portfolio_snapshot_id=snapshot_id,
        portfolio_target_revision_id=target_revision_id,
        portfolio_holdings_authority=holdings_authority,
        portfolio=portfolio_view,
        metrics_status=_coverage(
            len(actuals),
            truncated=metrics_truncated,
            latest=max((item.recorded_at for item in actuals), default=None),
            reason=None if definitions else "No registered operating metrics",
        ),
        metric_definitions=definitions,
        metric_observations=actuals,
        guidance_status=_coverage(
            len(guidance),
            truncated=guidance_truncated,
            latest=max((item.recorded_at for item in guidance), default=None),
        ),
        guidance_observations=guidance,
        consensus_status=_coverage(
            len(consensus_periods),
            truncated=consensus_truncated,
            latest=max(
                (
                    item.current_observation.recorded_at
                    for item in consensus_periods
                    if item.current_observation is not None
                ),
                default=None,
            ),
            reason=None if selected else consensus.continuity_status,
        ),
        consensus_continuity_status=consensus.continuity_status,
        consensus_provider_id=consensus.selected_provider_id,
        consensus_periods=consensus_periods,
        research_status=(
            restricted
            if data_universe_only
            else _coverage(
                len(current_research),
                truncated=research_truncated,
                latest=max((item.recorded_at for item in current_research), default=None),
            )
        ),
        current_research=current_research,
        thesis_status=(
            restricted
            if data_universe_only
            else _coverage(
                len(current_theses),
                truncated=thesis_truncated,
                latest=max((item.recorded_at for item in current_theses), default=None),
            )
        ),
        current_theses=current_theses,
        native_models_status=(
            restricted
            if data_universe_only
            else _coverage(
                len(models),
                truncated=models_truncated,
                latest=max((item.accepted_revision.recorded_at for item in models), default=None),
            )
        ),
        native_models=models,
        imported_outputs_status=imported_status,
        imported_model_outputs=imported_outputs,
        resource_links={}
        if data_universe_only
        else {
            "company": root,
            "financial_statements": f"{root}/financial-statements",
            "reported_fundamentals": f"{root}/reported-fundamentals",
            "filings": f"{root}/source-documents",
            "market_history": f"{root}/market-data",
            "metric_history": f"{root}/metric-observations",
            "guidance_history": f"{root}/guidance-observations",
            "consensus_history": f"{root}/consensus-estimates",
            "research_history": f"{root}/research",
            "thesis_history": f"{root}/thesis",
            "model_outputs": f"{root}/model-outputs/history",
        },
    )
