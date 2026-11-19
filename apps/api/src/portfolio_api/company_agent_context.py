"""Bounded canonical context for API-first company research agents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from portfolio_api.company_observations import (
    CompanyGuidanceObservationRead,
    CompanyMetricDefinitionRead,
    CompanyMetricObservationRead,
    company_guidance_history,
    company_metric_history,
    metric_definitions,
)
from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.investment_thesis import company_investment_thesis
from portfolio_api.research_forecasts import company_research


class CompanyAgentContextRead(s.Contract):
    """Current accepted company state assembled for an external research agent."""

    contract_type: Literal["CompanyAgentContextV1"] = "CompanyAgentContextV1"
    contract_version: Literal["1.0.0"] = "1.0.0"
    context_as_of: datetime
    company: s.CompanyDetail
    metric_definitions: list[CompanyMetricDefinitionRead]
    metric_observations: list[CompanyMetricObservationRead]
    active_guidance: list[CompanyGuidanceObservationRead]
    consensus: s.CompanyConsensusEstimatesRead
    research: s.CompanyResearchRead
    thesis: s.CompanyInvestmentThesisRead
    models: list[s.ResearchTriggerModelContextRead]
    companion_resources: dict[str, str]


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


def current_company_agent_context(
    session: Session,
    company_id: UUID,
    *,
    metric_limit: int = 250,
    guidance_limit: int = 100,
) -> CompanyAgentContextRead:
    """Assemble bounded current canonical state without scraping workbook geometry."""

    cutoff = datetime.now(UTC)
    models = [_model_context(model) for model in q.company_financial_models(session, company_id)]
    models.extend(
        _model_context(model) for model in q.company_extended_financial_models(session, company_id)
    )
    return CompanyAgentContextRead(
        context_as_of=cutoff,
        company=q.detail(session, company_id),
        metric_definitions=metric_definitions(session, company_id),
        metric_observations=company_metric_history(
            session,
            company_id,
            known_at=cutoff,
            limit=metric_limit,
        ),
        active_guidance=company_guidance_history(
            session,
            company_id,
            known_at=cutoff,
            current_only=True,
            limit=guidance_limit,
        ),
        consensus=q.company_consensus_estimates(
            session,
            company_id,
            known_at=cutoff,
            effective_cutoff=cutoff,
        ),
        research=company_research(session, company_id, known_at=cutoff),
        thesis=company_investment_thesis(session, company_id, known_at=cutoff),
        models=models,
        companion_resources={
            "market_data": f"/v1/companies/{company_id}/market-data",
            "financial_statements": f"/v1/companies/{company_id}/financial-statements",
            "source_documents": f"/v1/companies/{company_id}/source-documents",
            "risk_assessments": f"/v1/companies/{company_id}/risk-assessments",
            "research_queue": f"/v1/research-queue?company_id={company_id}",
        },
    )
