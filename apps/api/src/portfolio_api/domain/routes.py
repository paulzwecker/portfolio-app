"""Domain-oriented REST operations; session dependency commits each operation atomically."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from portfolio_api import candidate_pipeline as candidate_research
from portfolio_api.agent_work_sheet_sync import publish_agent_work_feed
from portfolio_api.attention import attention_feed
from portfolio_api.decision_evaluation import company_decision_evaluation
from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as operations
from portfolio_api.domain.models import (
    ForecastAccuracyMetric,
    ForecastAccuracySourceType,
    FundamentalPeriodType,
    Lifecycle,
    OperationalJobRequest,
    Portfolio,
    RankingType,
    ResearchPeriodType,
    ResearchTriggerType,
    ReturnMethodologyDefinition,
    ScoreDimension,
    SourceDocumentType,
)
from portfolio_api.execution_pace import create_execution_pace_run
from portfolio_api.expected_return_attribution import company_expected_return_attribution
from portfolio_api.financial_statements import company_financial_statements
from portfolio_api.forecast_accuracy import company_forecast_accuracy
from portfolio_api.google_sheets_sync import (
    accept_sync_candidate,
    google_sheets_status,
    list_sync_candidates,
    list_sync_runs,
    preview_sync_candidate,
    reject_sync_candidate,
    run_sync_check,
    test_google_sheets_connection,
)
from portfolio_api.investment_thesis import (
    company_investment_thesis,
    publish_investment_thesis_revision,
    thesis_revision_read,
)
from portfolio_api.manual_operations import (
    create_job_request,
    job_request_read,
    list_job_requests,
    retry_job_request,
)
from portfolio_api.model_migration_status import company_model_migration_status
from portfolio_api.portfolio_sheet_sync import (
    PortfolioSheetPublishError,
    publish_portfolio_state,
)
from portfolio_api.recurring_operations import recurring_operations_status
from portfolio_api.reported_fundamentals import METRIC_DEFINITIONS
from portfolio_api.research_agent_operations import (
    ResearchAgentOperationError,
    deliver_agent_work,
    list_agent_events,
    proposal_status,
    record_agent_acknowledgment,
    record_delivery_failure,
    record_portfolio_sheet_delivery,
    record_sheet_agent_work_deliveries,
    record_sheet_delivery_failure,
    record_thesis_sheet_deliveries,
    run_acknowledgment_inbox_check,
    work_event_read,
)
from portfolio_api.research_forecasts import (
    company_research,
    publish_research_revision,
    research_revision_read,
)
from portfolio_api.research_queue import (
    complete_research_queue_task,
    get_research_queue,
    research_queue_history,
)
from portfolio_api.research_sheet_sync import (
    accept_research_candidate,
    check_research_sync_connection,
    list_research_sync_candidates,
    list_research_sync_runs,
    preview_research_candidate,
    reject_research_candidate,
    research_sync_status,
    run_research_sync_check,
)
from portfolio_api.research_triggers import (
    list_research_triggers,
    normalize_trigger_cutoff,
    refresh_research_triggers,
    research_trigger_context,
)
from portfolio_api.return_semantics import methodology_payload
from portfolio_api.risk_assessments import (
    accept_risk_candidate,
    company_risk_assessments,
    list_risk_sync_candidates,
    list_risk_sync_runs,
    portfolio_risk_assessments,
    preview_risk_candidate,
    reject_risk_candidate,
    risk_sync_status,
    run_risk_sync_check,
    test_risk_sync_connection,
)
from portfolio_api.settings import Settings
from portfolio_api.source_documents import create_company_source_document
from portfolio_api.temporal_alignment import company_temporal_alignment
from portfolio_api.thesis_watch_sheet_sync import publish_thesis_watch_feed

router = APIRouter(prefix="/v1", tags=["Portfolio research"])


def session_for(request: Request) -> Iterator[Session]:
    engine = cast(Engine | None, request.app.state.database_engine)
    if engine is None:
        raise HTTPException(503, "Database is unavailable; configure the local environment")
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except operations.DomainError as error:
            session.rollback()
            raise HTTPException(error.status, error.detail) from None
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                409, "The operation conflicts with existing identity or historical records"
            ) from None
        except SQLAlchemyError:
            session.rollback()
            raise HTTPException(503, "Database is unavailable or migrations are required") from None


Db = Annotated[Session, Depends(session_for, scope="function")]


@router.get(
    "/google-sheets-research-sync/status",
    response_model=s.GoogleSheetsResearchSyncStatusRead,
)
def get_google_sheets_research_sync_status(db: Db) -> s.GoogleSheetsResearchSyncStatusRead:
    return research_sync_status(db, Settings())


@router.post(
    "/google-sheets-research-sync/connection-test",
    response_model=s.GoogleSheetsResearchConnectionTestRead,
)
def post_google_sheets_research_connection_test() -> s.GoogleSheetsResearchConnectionTestRead:
    return check_research_sync_connection(Settings())


@router.post(
    "/google-sheets-research-sync/check",
    response_model=s.GoogleSheetsResearchSyncCheckRead,
)
def post_google_sheets_research_sync_check(db: Db) -> s.GoogleSheetsResearchSyncCheckRead:
    return run_research_sync_check(db, Settings())


@router.get(
    "/google-sheets-research-sync/runs",
    response_model=list[s.GoogleSheetsResearchSyncRunRead],
)
def get_google_sheets_research_sync_runs(
    db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> list[s.GoogleSheetsResearchSyncRunRead]:
    return list_research_sync_runs(db, limit)


@router.get(
    "/google-sheets-research-sync/candidates",
    response_model=list[s.GoogleSheetsResearchCandidateRead],
)
def get_google_sheets_research_sync_candidates(
    db: Db,
    status: Annotated[
        str | None,
        Query(pattern="^(PENDING|READY|CONFLICT|INVALID|ACCEPTED|REJECTED)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[s.GoogleSheetsResearchCandidateRead]:
    return list_research_sync_candidates(db, status, limit)


@router.post(
    "/google-sheets-research-sync/candidates/{candidate_id}/preview",
    response_model=s.GoogleSheetsResearchCandidateRead,
)
def post_google_sheets_research_candidate_preview(
    candidate_id: UUID, db: Db
) -> s.GoogleSheetsResearchCandidateRead:
    return preview_research_candidate(db, candidate_id)


@router.post(
    "/google-sheets-research-sync/candidates/{candidate_id}/accept",
    response_model=s.GoogleSheetsResearchCandidateRead,
)
def post_google_sheets_research_candidate_accept(
    candidate_id: UUID, value: s.GoogleSheetsResearchSyncReviewRequest, db: Db
) -> s.GoogleSheetsResearchCandidateRead:
    return accept_research_candidate(db, candidate_id, value.reviewer, value.reviewer_note)


@router.post(
    "/google-sheets-research-sync/candidates/{candidate_id}/reject",
    response_model=s.GoogleSheetsResearchCandidateRead,
)
def post_google_sheets_research_candidate_reject(
    candidate_id: UUID, value: s.GoogleSheetsResearchSyncRejectRequest, db: Db
) -> s.GoogleSheetsResearchCandidateRead:
    return reject_research_candidate(db, candidate_id, value.reviewer, value.reviewer_note)


@router.get("/google-sheets-sync/status", response_model=s.GoogleSheetsSyncStatusRead)
def get_google_sheets_sync_status(db: Db) -> s.GoogleSheetsSyncStatusRead:
    return google_sheets_status(db, Settings())


@router.post(
    "/google-sheets-sync/connection-test",
    response_model=s.GoogleSheetsConnectionTestRead,
)
def post_google_sheets_connection_test() -> s.GoogleSheetsConnectionTestRead:
    return test_google_sheets_connection(Settings())


@router.post("/google-sheets-sync/check", response_model=s.GoogleSheetsSyncCheckRead)
def post_google_sheets_sync_check(db: Db) -> s.GoogleSheetsSyncCheckRead:
    return run_sync_check(db, Settings())


@router.get("/google-sheets-risk-sync/status", response_model=s.GoogleSheetsRiskSyncStatusRead)
def get_google_sheets_risk_sync_status(db: Db) -> s.GoogleSheetsRiskSyncStatusRead:
    return risk_sync_status(db, Settings())


@router.post(
    "/google-sheets-risk-sync/connection-test",
    response_model=s.GoogleSheetsConnectionTestRead,
)
def post_google_sheets_risk_connection_test() -> s.GoogleSheetsConnectionTestRead:
    return test_risk_sync_connection(Settings())


@router.post("/google-sheets-risk-sync/check", response_model=s.GoogleSheetsRiskSyncCheckRead)
def post_google_sheets_risk_sync_check(db: Db) -> s.GoogleSheetsRiskSyncCheckRead:
    return run_risk_sync_check(db, Settings())


@router.get("/google-sheets-risk-sync/runs", response_model=list[s.GoogleSheetsRiskSyncRunRead])
def get_google_sheets_risk_sync_runs(
    db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> list[s.GoogleSheetsRiskSyncRunRead]:
    return list_risk_sync_runs(db, limit)


@router.get(
    "/google-sheets-risk-sync/candidates",
    response_model=list[s.GoogleSheetsRiskCandidateRead],
)
def get_google_sheets_risk_sync_candidates(
    db: Db,
    status: Annotated[
        str | None,
        Query(pattern="^(PENDING|READY|STALE_BASELINE|CONFLICT|INVALID|ACCEPTED|REJECTED)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[s.GoogleSheetsRiskCandidateRead]:
    return list_risk_sync_candidates(db, status, limit)


@router.post(
    "/google-sheets-risk-sync/candidates/{candidate_id}/preview",
    response_model=s.GoogleSheetsRiskCandidateRead,
)
def post_google_sheets_risk_candidate_preview(
    candidate_id: UUID, db: Db
) -> s.GoogleSheetsRiskCandidateRead:
    return preview_risk_candidate(db, candidate_id)


@router.post(
    "/google-sheets-risk-sync/candidates/{candidate_id}/accept",
    response_model=s.GoogleSheetsRiskCandidateRead,
)
def post_google_sheets_risk_candidate_accept(
    candidate_id: UUID, value: s.GoogleSheetsRiskSyncReviewRequest, db: Db
) -> s.GoogleSheetsRiskCandidateRead:
    return accept_risk_candidate(
        db,
        candidate_id,
        value.reviewer,
        value.reviewer_note,
        value.acknowledge_stale_baseline,
    )


@router.post(
    "/google-sheets-risk-sync/candidates/{candidate_id}/reject",
    response_model=s.GoogleSheetsRiskCandidateRead,
)
def post_google_sheets_risk_candidate_reject(
    candidate_id: UUID, value: s.GoogleSheetsRiskSyncRejectRequest, db: Db
) -> s.GoogleSheetsRiskCandidateRead:
    return reject_risk_candidate(db, candidate_id, value.reviewer, value.reviewer_note)


@router.post(
    "/google-sheets-sync/portfolio-state/publish",
    response_model=s.GoogleSheetsPortfolioStatePublishRead,
)
def post_google_sheets_portfolio_state_publish(
    value: s.GoogleSheetsPortfolioStatePublishRequest, db: Db
) -> s.GoogleSheetsPortfolioStatePublishRead | JSONResponse:
    try:
        result = publish_portfolio_state(db, value.portfolio_id, Settings())
        response = s.GoogleSheetsPortfolioStatePublishRead.model_validate(result.__dict__)
        record_portfolio_sheet_delivery(db, response)
        return response
    except PortfolioSheetPublishError as error:
        record_sheet_delivery_failure(
            db,
            role="MODEL_ALLOCATION_STEWARD",
            work_type="PORTFOLIO_STATE",
            work_key=str(value.portfolio_id),
            attempt_id=str(uuid4()),
            reason=f"{error.code}: {error}",
            fingerprint_source={"portfolio_id": str(value.portfolio_id)},
        )
        return JSONResponse(
            status_code=error.status,
            content={"detail": f"{error.code}: {error}"},
        )


@router.post(
    "/google-sheets-sync/thesis-watch/publish",
    response_model=s.GoogleSheetsThesisWatchPublishRead,
)
def post_google_sheets_thesis_watch_publish(
    value: s.GoogleSheetsThesisWatchPublishRequest, db: Db
) -> s.GoogleSheetsThesisWatchPublishRead | JSONResponse:
    try:
        result = publish_thesis_watch_feed(db, Settings(), limit=value.limit, offset=value.offset)
        record_thesis_sheet_deliveries(db, result)
        return result
    except PortfolioSheetPublishError as error:
        record_sheet_delivery_failure(
            db,
            role="PORTFOLIO_THESIS_SENTINEL",
            work_type="TRIGGER",
            work_key=f"THESIS_WATCH_FEED:{value.offset}:{value.limit}",
            attempt_id=str(uuid4()),
            reason=f"{error.code}: {error}",
            fingerprint_source={"offset": value.offset, "limit": value.limit},
        )
        return JSONResponse(
            status_code=error.status,
            content={"detail": f"{error.code}: {error}"},
        )


@router.get("/google-sheets-sync/runs", response_model=list[s.GoogleSheetsSyncRunRead])
def get_google_sheets_sync_runs(
    db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> list[s.GoogleSheetsSyncRunRead]:
    return list_sync_runs(db, limit)


@router.get(
    "/google-sheets-sync/candidates",
    response_model=list[s.GoogleSheetsSyncCandidateRead],
)
def get_google_sheets_sync_candidates(
    db: Db,
    status: Annotated[
        str | None,
        Query(pattern="^(PENDING|READY|CONFLICT|INVALID|NO_CHANGES|ACCEPTED|REJECTED)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[s.GoogleSheetsSyncCandidateRead]:
    return list_sync_candidates(db, status, limit)


@router.post(
    "/google-sheets-sync/candidates/{candidate_id}/preview",
    response_model=s.GoogleSheetsSyncCandidateRead,
)
def post_google_sheets_candidate_preview(
    candidate_id: UUID, db: Db
) -> s.GoogleSheetsSyncCandidateRead:
    return preview_sync_candidate(db, candidate_id)


@router.post(
    "/google-sheets-sync/candidates/{candidate_id}/accept",
    response_model=s.GoogleSheetsSyncCandidateRead,
)
def post_google_sheets_candidate_accept(
    candidate_id: UUID, value: s.GoogleSheetsSyncReviewRequest, db: Db
) -> s.GoogleSheetsSyncCandidateRead:
    return accept_sync_candidate(db, candidate_id, value.reviewer, value.decision_note)


@router.post(
    "/google-sheets-sync/candidates/{candidate_id}/reject",
    response_model=s.GoogleSheetsSyncCandidateRead,
)
def post_google_sheets_candidate_reject(
    candidate_id: UUID, value: s.GoogleSheetsSyncRejectRequest, db: Db
) -> s.GoogleSheetsSyncCandidateRead:
    return reject_sync_candidate(db, candidate_id, value.reviewer, value.decision_note)


@router.get("/return-methodologies", response_model=s.ReturnMethodologiesRead)
def get_return_methodologies(db: Db) -> s.ReturnMethodologiesRead:
    definitions = list(
        db.scalars(
            select(ReturnMethodologyDefinition).order_by(
                ReturnMethodologyDefinition.code, ReturnMethodologyDefinition.version
            )
        )
    )
    payload = methodology_payload()
    return s.ReturnMethodologiesRead(
        definitions=[s.ReturnMethodologyRead.model_validate(row) for row in definitions],
        rules=[
            s.ReturnComparabilityRuleRead.model_validate(item)
            for item in cast(list[dict[str, str]], payload["rules"])
        ],
        currency_policy=str(payload["currency_policy"]),
    )


@router.get("/attention", response_model=s.AttentionFeedRead)
def get_attention_feed(
    db: Db,
    company_id: UUID | None = None,
    event_type: Annotated[
        str | None,
        Query(
            pattern="^(MODEL_REVISION|MODEL_OUTPUT_IMPORT|EXPECTED_IRR_CHANGE|CONSENSUS_REVISION|NEW_FILING|PRICE_MOVE|RANK_CHANGE|EXECUTION_PACE_CHANGE|DATA_QUALITY|RISK_ASSESSMENT)$"
        ),
    ] = None,
    lifecycle: Lifecycle | None = None,
    severity: Annotated[str | None, Query(pattern="^(HIGH|MEDIUM|LOW)$")] = None,
    status: Annotated[str | None, Query(pattern="^(REVIEW|INFORMATIONAL)$")] = None,
    lookback_days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> s.AttentionFeedRead:
    return attention_feed(
        db,
        company_id=company_id,
        event_type=event_type,
        lifecycle=lifecycle,
        severity=severity,
        status=status,
        lookback_days=lookback_days,
        limit=limit,
    )


def _validate_market_cutoffs(as_of: date | datetime | None, known_at: datetime | None) -> None:
    for name, value in (("as_of", as_of), ("known_at", known_at)):
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(422, f"{name} must include a timezone offset")


@router.get("/universe", response_model=list[s.CompanyRead])
def get_universe(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> list[s.CompanyRead]:
    return q.universe(db, lifecycle, search)


@router.get("/universe/score-summary", response_model=list[s.UniverseScoreSummary])
def get_universe_score_summary(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> list[s.UniverseScoreSummary]:
    return q.universe_score_summary(db, lifecycle, search)


@router.get("/universe/ranking-summary", response_model=list[s.UniverseRankingSummary])
def get_universe_ranking_summary(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> list[s.UniverseRankingSummary]:
    return q.universe_ranking_summary(db, lifecycle, search)


@router.get(
    "/candidate-pipeline",
    response_model=list[s.CandidatePipelineQueueEntry],
)
def get_candidate_pipeline(
    db: Db, search: Annotated[str | None, Query(max_length=200)] = None
) -> list[s.CandidatePipelineQueueEntry]:
    return candidate_research.candidate_pipeline_queue(db, search)


@router.get(
    "/companies/{company_id}/candidate-pipeline",
    response_model=s.CompanyCandidatePipelineRead,
)
def get_company_candidate_pipeline(company_id: UUID, db: Db) -> s.CompanyCandidatePipelineRead:
    try:
        return candidate_research.company_candidate_pipeline(db, company_id)
    except operations.DomainError as error:
        raise HTTPException(error.status, error.detail) from None


@router.post(
    "/companies/{company_id}/candidate-pipeline-revisions",
    response_model=s.CandidatePipelinePublicationResult,
    status_code=201,
)
def post_candidate_pipeline_revision(
    company_id: UUID,
    value: s.CandidatePipelineRevisionCreate,
    db: Db,
    response: Response,
) -> s.CandidatePipelinePublicationResult:
    try:
        revision, result = candidate_research.record_candidate_pipeline_revision(
            db, company_id, value
        )
        if result == "ALREADY_RECORDED":
            response.status_code = 200
        return s.CandidatePipelinePublicationResult(
            result=result,
            revision=candidate_research.revision_read(db, company_id, revision.id),
        )
    except operations.DomainError as error:
        raise HTTPException(error.status, error.detail) from None


@router.get("/research-queue", response_model=s.ResearchQueueRead)
def get_research_review_queue(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    include_complete: bool = False,
) -> s.ResearchQueueRead:
    return get_research_queue(
        db, lifecycle=lifecycle, search=search, include_complete=include_complete
    )


@router.get("/research-triggers", response_model=s.ResearchTriggerReadResult)
def get_research_triggers(
    db: Db,
    as_of: datetime | None = None,
    company_id: UUID | None = None,
    trigger_type: ResearchTriggerType | None = None,
    processing_state: Annotated[
        str | None, Query(pattern="^(OPEN|REVIEWED|SUPERSEDED|STALE)$")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0, le=5000)] = 0,
) -> s.ResearchTriggerReadResult:
    try:
        cutoff = normalize_trigger_cutoff(as_of)
        return list_research_triggers(
            db,
            as_of=cutoff,
            company_id=company_id,
            trigger_type=trigger_type,
            processing_state=processing_state,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.get(
    "/research-triggers/{trigger_id}/context",
    response_model=s.ResearchTriggerContextRead,
)
def get_research_trigger_context(trigger_id: UUID, db: Db) -> s.ResearchTriggerContextRead:
    try:
        return research_trigger_context(db, trigger_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from None


@router.post("/research-triggers/refresh", response_model=s.ResearchTriggerRefreshResult)
def post_research_triggers_refresh(
    db: Db,
    as_of: datetime | None = None,
    company_id: UUID | None = None,
    lookback_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> s.ResearchTriggerRefreshResult:
    try:
        cutoff = normalize_trigger_cutoff(as_of)
        return refresh_research_triggers(
            db,
            as_of=cutoff,
            lookback_days=lookback_days,
            company_id=company_id,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.get("/research-queue/history", response_model=list[s.ResearchQueueCompletionRead])
def get_research_review_history(
    db: Db, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[s.ResearchQueueCompletionRead]:
    return research_queue_history(db, limit=limit)


@router.post(
    "/research-agent-operations/{agent_role}/work",
    response_model=s.ResearchAgentWorkContractV1,
)
def post_research_agent_work(
    agent_role: s.ResearchAgentRoleValue,
    value: s.ResearchAgentWorkRequest,
    db: Db,
) -> s.ResearchAgentWorkContractV1:
    try:
        return deliver_agent_work(db, agent_role, value)
    except ResearchAgentOperationError as error:
        raise HTTPException(error.status, error.detail) from None


@router.post(
    "/google-sheets-agent-operations/{agent_role}/work/publish",
    response_model=s.GoogleSheetsAgentWorkPublishRead,
)
def post_google_sheets_agent_work_publish(
    agent_role: s.ResearchAgentRoleValue,
    value: s.GoogleSheetsAgentWorkPublishRequest,
    db: Db,
) -> s.GoogleSheetsAgentWorkPublishRead | JSONResponse:
    work_request = s.ResearchAgentWorkRequest(
        as_of=value.as_of,
        limit=value.limit,
        offset=value.offset,
        portfolio_id=value.portfolio_id,
    )
    try:
        work = deliver_agent_work(db, agent_role, work_request, channel="GOOGLE_SHEETS")
        result = publish_agent_work_feed(db, work, Settings())
        if result.read_back_verified:
            record_sheet_agent_work_deliveries(db, work, result.published_at)
        return result
    except PortfolioSheetPublishError as error:
        for item in work.items:
            record_delivery_failure(
                db,
                role=work.agent_role,
                work_type=item.work_type,
                work_key=item.work_key,
                fingerprint=item.work_fingerprint,
                attempt_id=str(uuid4()),
                channel="GOOGLE_SHEETS",
                reason=f"{error.code}: {error}",
            )
        return JSONResponse(
            status_code=error.status,
            content={"detail": f"{error.code}: {error}"},
        )
    except ResearchAgentOperationError as error:
        raise HTTPException(error.status, error.detail) from None


@router.post(
    "/research-agent-operations/acknowledgments",
    response_model=s.ResearchAgentAcknowledgmentResult,
)
def post_research_agent_acknowledgment(
    value: s.ResearchAgentAcknowledgmentContractV1, db: Db
) -> s.ResearchAgentAcknowledgmentResult:
    try:
        return record_agent_acknowledgment(db, value)
    except ResearchAgentOperationError as error:
        raise HTTPException(error.status, error.detail) from None


@router.post(
    "/research-agent-operations/delivery-failures",
    response_model=s.ResearchAgentDeliveryFailureResult,
)
def post_research_agent_delivery_failure(
    value: s.ResearchAgentDeliveryFailure, db: Db
) -> s.ResearchAgentDeliveryFailureResult:
    try:
        event, result = record_delivery_failure(
            db,
            role=value.agent_role,
            work_type=value.work_type,
            work_key=value.work_key,
            fingerprint=value.work_fingerprint,
            attempt_id=value.attempt_id,
            channel=value.channel,
            reason=value.reason,
            observed_at=value.observed_at,
        )
        return s.ResearchAgentDeliveryFailureResult(result=result, event=work_event_read(event))
    except ResearchAgentOperationError as error:
        raise HTTPException(error.status, error.detail) from None


@router.get(
    "/research-agent-operations/events",
    response_model=list[s.ResearchAgentWorkEventRead],
)
def get_research_agent_events(
    db: Db,
    agent_role: str | None = None,
    work_key: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[s.ResearchAgentWorkEventRead]:
    try:
        return list_agent_events(db, role=agent_role, work_key=work_key, limit=limit)
    except ResearchAgentOperationError as error:
        raise HTTPException(error.status, error.detail) from None


@router.get(
    "/research-agent-operations/proposals/{proposal_domain}/{candidate_id}",
    response_model=s.ResearchAgentProposalStatusRead,
)
def get_research_agent_proposal_status(
    proposal_domain: s.ResearchAgentProposalDomain,
    candidate_id: UUID,
    db: Db,
) -> s.ResearchAgentProposalStatusRead:
    try:
        return proposal_status(db, proposal_domain, candidate_id)
    except ResearchAgentOperationError as error:
        raise HTTPException(error.status, error.detail) from None


@router.post(
    "/google-sheets-agent-operations/check",
    response_model=s.ResearchAgentAcknowledgmentSyncRead,
)
def post_google_sheets_agent_acknowledgment_check(
    db: Db,
) -> s.ResearchAgentAcknowledgmentSyncRead:
    return run_acknowledgment_inbox_check(db, Settings())


@router.post(
    "/research-queue/{task_id}/complete",
    response_model=s.ResearchQueueCompletionResult,
)
def post_research_queue_completion(
    task_id: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    value: s.ResearchQueueCompletionCreate,
    db: Db,
) -> s.ResearchQueueCompletionResult:
    try:
        task, result = complete_research_queue_task(db, task_id, value)
        return s.ResearchQueueCompletionResult(result=result, task=task)
    except operations.DomainError as error:
        raise HTTPException(error.status, error.detail) from None


@router.get(
    "/universe/execution-pace-summary",
    response_model=list[s.UniverseExecutionPaceSummary],
)
def get_universe_execution_pace_summary(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> list[s.UniverseExecutionPaceSummary]:
    return q.universe_execution_pace_summary(db, lifecycle, search)


@router.get("/universe/market-summary", response_model=list[s.UniverseMarketSummary])
def get_universe_market_summary(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> list[s.UniverseMarketSummary]:
    _validate_market_cutoffs(as_of, known_at)
    return q.universe_market_summary(db, lifecycle, search, as_of, known_at)


@router.get("/market-data/status", response_model=s.MarketRefreshStatusRead)
def get_market_refresh_status(db: Db) -> s.MarketRefreshStatusRead:
    return q.market_refresh_status(db)


@router.get(
    "/recurring-operations/status",
    response_model=s.RecurringOperationsStatusRead,
)
def get_recurring_operations_status(request: Request, db: Db) -> s.RecurringOperationsStatusRead:
    settings = cast(Settings, request.app.state.settings)
    return recurring_operations_status(db, settings)


@router.get("/operations/job-requests", response_model=list[s.OperationalJobRequestRead])
def get_operational_job_requests(
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[s.OperationalJobRequestRead]:
    return list_job_requests(db, limit)


@router.get("/operations/job-requests/{request_id}", response_model=s.OperationalJobRequestRead)
def get_operational_job_request(request_id: UUID, db: Db) -> s.OperationalJobRequestRead:
    request = db.get(OperationalJobRequest, request_id)
    if request is None:
        raise HTTPException(404, "Operational job request was not found.")
    return job_request_read(db, request)


@router.post(
    "/operations/job-requests",
    response_model=s.OperationalJobRequestRead,
    status_code=202,
)
def post_operational_job_request(
    request: Request,
    value: s.OperationalJobRequestCreate,
    db: Db,
) -> s.OperationalJobRequestRead:
    settings = cast(Settings, request.app.state.settings)
    if not settings.recurring_operations_enabled:
        raise HTTPException(
            503,
            "The background operations worker is disabled; no refresh request was queued.",
        )
    try:
        job_request, deduplicated = create_job_request(db, value)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return job_request_read(db, job_request, deduplicated=deduplicated)


@router.post(
    "/operations/job-requests/{request_id}/retry",
    response_model=s.OperationalJobRequestRead,
    status_code=202,
)
def post_operational_job_request_retry(
    request: Request,
    request_id: UUID,
    db: Db,
) -> s.OperationalJobRequestRead:
    settings = cast(Settings, request.app.state.settings)
    if not settings.recurring_operations_enabled:
        raise HTTPException(
            503,
            "The background operations worker is disabled; no retry was queued.",
        )
    try:
        job_request = retry_job_request(db, request_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return job_request_read(db, job_request)


@router.get(
    "/universe/estimate-momentum-summary",
    response_model=list[s.UniverseEstimateMomentumRead],
)
def get_universe_estimate_momentum_summary(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> list[s.UniverseEstimateMomentumRead]:
    _validate_market_cutoffs(as_of, known_at)
    return q.universe_estimate_momentum(db, lifecycle, search, as_of, known_at)


@router.get("/universe/model-output-summary", response_model=list[s.UniverseModelOutputSummary])
def get_universe_model_output_summary(
    db: Db,
    lifecycle: Lifecycle | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> list[s.UniverseModelOutputSummary]:
    return q.universe_model_output_summary(db, lifecycle, search)


@router.get("/score-definitions", response_model=list[s.ScoreDefinitionRead])
def get_score_definitions(
    db: Db, dimension: ScoreDimension | None = None
) -> list[s.ScoreDefinitionRead]:
    return q.score_definitions(db, dimension)


@router.get("/ranking-definitions", response_model=list[s.RankingDefinitionRead])
def get_ranking_definitions(
    db: Db, ranking_type: RankingType | None = None
) -> list[s.RankingDefinitionRead]:
    return q.ranking_definitions(db, ranking_type)


@router.get("/ranking-runs", response_model=list[s.RankingRunRead])
def get_ranking_runs(db: Db, ranking_type: RankingType | None = None) -> list[s.RankingRunRead]:
    return q.ranking_runs(db, ranking_type)


@router.post("/ranking-runs", response_model=s.RankingRunRead, status_code=201)
def post_ranking_run(value: s.RankingRunCreate, db: Db) -> s.RankingRunRead:
    run = operations.create_ranking_run(db, value)
    return q.ranking_run_read(db, run)


@router.get("/ranking-runs/{run_id}", response_model=s.RankingRunDetailRead)
def get_ranking_run(run_id: UUID, db: Db) -> s.RankingRunDetailRead:
    return q.ranking_run_detail(db, run_id)


@router.get("/execution-pace-runs", response_model=list[s.ExecutionPaceRunRead])
def get_execution_pace_runs(db: Db) -> list[s.ExecutionPaceRunRead]:
    return q.execution_pace_runs(db)


@router.post(
    "/execution-pace-runs",
    response_model=s.ExecutionPaceRunRead,
    status_code=201,
)
def post_execution_pace_run(value: s.ExecutionPaceRunCreate, db: Db) -> s.ExecutionPaceRunRead:
    try:
        run = create_execution_pace_run(db, value)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return q.execution_pace_run_read(db, run)


@router.get("/execution-pace-runs/{run_id}", response_model=s.ExecutionPaceRunDetailRead)
def get_execution_pace_run(run_id: UUID, db: Db) -> s.ExecutionPaceRunDetailRead:
    return q.execution_pace_run_detail(db, run_id)


@router.get(
    "/companies/{company_id}/execution-pace",
    response_model=s.CompanyExecutionPaceRead,
)
def get_company_execution_pace(company_id: UUID, db: Db) -> s.CompanyExecutionPaceRead:
    return q.company_execution_pace(db, company_id)


@router.get("/companies/{company_id}/rankings", response_model=s.CompanyRankingsRead)
def get_company_rankings(
    company_id: UUID, db: Db, ranking_type: RankingType | None = None
) -> s.CompanyRankingsRead:
    return q.company_rankings(db, company_id, ranking_type)


@router.get("/companies/{company_id}/scores/current", response_model=list[s.ScoreCurrentRead])
def get_current_scores(company_id: UUID, db: Db) -> list[s.ScoreCurrentRead]:
    return q.current_scores(db, company_id)


@router.get("/companies/{company_id}/scores/history", response_model=list[s.ScoreHistoryEntry])
def get_score_history(company_id: UUID, db: Db) -> list[s.ScoreHistoryEntry]:
    return q.score_history(db, company_id)


@router.post(
    "/companies/{company_id}/score-assessments",
    response_model=s.ScoreHistoryEntry,
    status_code=201,
)
def post_score_assessment(
    company_id: UUID, value: s.ScoreAssessmentCreate, db: Db
) -> s.ScoreHistoryEntry:
    assessment = operations.create_score_assessment(db, company_id, value)
    return q.score_history_entry(db, assessment)


@router.post("/companies", response_model=s.CompanyRead, status_code=201)
def post_company(value: s.CompanyCreate, db: Db) -> s.CompanyRead:
    return q.company_read(db, operations.create_company(db, value))


@router.get("/companies/{company_id}", response_model=s.CompanyDetail)
def get_company(company_id: UUID, db: Db) -> s.CompanyDetail:
    return q.detail(db, company_id)


@router.get("/companies/{company_id}/research", response_model=s.CompanyResearchRead)
def get_company_research(
    company_id: UUID,
    db: Db,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyResearchRead:
    _validate_market_cutoffs(as_of, known_at)
    if as_of is not None and known_at is not None:
        cutoff = datetime.combine(as_of, time.max, UTC)
        if known_at.astimezone(UTC) > cutoff:
            raise HTTPException(422, "known_at cannot be later than the as_of cutoff")
    return company_research(db, company_id, as_of, known_at)


@router.post("/research-revisions", response_model=s.ResearchPublicationResult, status_code=201)
def post_research_revision(
    value: s.ResearchRevisionPublishContract,
    db: Db,
    response: Response,
) -> s.ResearchPublicationResult:
    revision, result = publish_research_revision(db, value)
    if result == "ALREADY_PUBLISHED":
        response.status_code = 200
    return s.ResearchPublicationResult(
        result=result,
        revision=research_revision_read(db, revision),
    )


@router.get("/companies/{company_id}/thesis", response_model=s.CompanyInvestmentThesisRead)
def get_company_investment_thesis(
    company_id: UUID,
    db: Db,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyInvestmentThesisRead:
    _validate_market_cutoffs(as_of, known_at)
    if as_of is not None and known_at is not None:
        cutoff = datetime.combine(as_of, time.max, UTC)
        if known_at.astimezone(UTC) > cutoff:
            raise HTTPException(422, "known_at cannot be later than the as_of cutoff")
    return company_investment_thesis(db, company_id, as_of, known_at)


@router.get(
    "/companies/{company_id}/risk-assessments",
    response_model=s.CompanyRiskAssessmentsRead,
)
def get_company_risk_assessments(
    company_id: UUID, db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> s.CompanyRiskAssessmentsRead:
    return company_risk_assessments(db, company_id, limit)


@router.get(
    "/portfolios/{portfolio_id}/risk-assessments",
    response_model=s.PortfolioRiskAssessmentsRead,
)
def get_portfolio_risk_assessments(
    portfolio_id: UUID, db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> s.PortfolioRiskAssessmentsRead:
    return portfolio_risk_assessments(db, portfolio_id, limit)


@router.post(
    "/investment-thesis-revisions",
    response_model=s.InvestmentThesisPublicationResult,
    status_code=201,
)
def post_investment_thesis_revision(
    value: s.InvestmentThesisRevisionPublishContract,
    db: Db,
    response: Response,
) -> s.InvestmentThesisPublicationResult:
    revision, result = publish_investment_thesis_revision(db, value)
    if result == "ALREADY_PUBLISHED":
        response.status_code = 200
    return s.InvestmentThesisPublicationResult(
        result=result,
        revision=thesis_revision_read(db, revision),
    )


@router.get("/companies/{company_id}/market-data", response_model=list[s.ListingMarketData])
def get_company_market_data(
    company_id: UUID,
    db: Db,
    history_limit: Annotated[int, Query(ge=0, le=252)] = 90,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> list[s.ListingMarketData]:
    _validate_market_cutoffs(as_of, known_at)
    return q.company_market_data(db, company_id, history_limit, as_of, known_at)


@router.get(
    "/reported-fundamental-definitions",
    response_model=list[s.ReportedFundamentalDefinitionRead],
)
def get_reported_fundamental_definitions() -> list[s.ReportedFundamentalDefinitionRead]:
    definitions = [
        s.ReportedFundamentalDefinitionRead(
            metric=item.metric.value,
            statement=item.statement,
            display_name=item.display_name,
            canonical_unit=item.canonical_unit,
            evidence_type="REPORTED_FACT",
            description=item.description,
        )
        for item in METRIC_DEFINITIONS
    ]
    definitions.append(
        s.ReportedFundamentalDefinitionRead(
            metric="FREE_CASH_FLOW",
            statement=None,
            display_name="Free cash flow",
            canonical_unit="currency",
            evidence_type="DERIVED_ANALYTIC",
            description=(
                "Not stored as a reported fact. Free cash flow remains a derived analytic "
                "because source definitions differ."
            ),
        )
    )
    return definitions


@router.get(
    "/companies/{company_id}/financial-statements",
    response_model=s.CompanyFinancialStatementsRead,
)
def get_company_financial_statements(
    company_id: UUID,
    db: Db,
    period_type: Literal["ANNUAL", "QUARTERLY"] = "ANNUAL",
    period_limit: Annotated[int, Query(ge=1, le=40)] = 10,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyFinancialStatementsRead:
    _validate_market_cutoffs(as_of, known_at)
    return company_financial_statements(
        db,
        company_id,
        period_type=period_type,
        period_limit=period_limit,
        as_of=as_of,
        known_at=known_at,
    )


@router.get(
    "/companies/{company_id}/reported-fundamentals",
    response_model=s.CompanyReportedFundamentalsRead,
)
def get_company_reported_fundamentals(
    company_id: UUID,
    db: Db,
    period_type: FundamentalPeriodType | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyReportedFundamentalsRead:
    _validate_market_cutoffs(as_of, known_at)
    return q.company_reported_fundamentals(db, company_id, period_type, as_of, known_at)


@router.get(
    "/companies/{company_id}/source-documents",
    response_model=s.CompanySourceDocumentsRead,
)
def get_company_source_documents(
    company_id: UUID,
    db: Db,
    document_type: SourceDocumentType | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> s.CompanySourceDocumentsRead:
    _validate_market_cutoffs(as_of, known_at)
    return q.company_source_documents(db, company_id, document_type, as_of, known_at, limit)


@router.post(
    "/companies/{company_id}/source-documents",
    response_model=s.SourceDocumentRead,
    status_code=201,
)
def post_company_source_document(
    company_id: UUID, value: s.SourceDocumentCreate, db: Db
) -> s.SourceDocumentRead:
    document = create_company_source_document(db, company_id, value)
    return s.SourceDocumentRead.model_validate(document)


@router.get(
    "/companies/{company_id}/consensus-estimates",
    response_model=s.CompanyConsensusEstimatesRead,
)
def get_company_consensus_estimates(
    company_id: UUID,
    db: Db,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyConsensusEstimatesRead:
    _validate_market_cutoffs(as_of, known_at)
    return q.company_consensus_estimates(db, company_id, as_of, known_at)


@router.get(
    "/companies/{company_id}/estimate-momentum",
    response_model=s.CompanyEstimateMomentumRead,
)
def get_company_estimate_momentum(
    company_id: UUID,
    db: Db,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyEstimateMomentumRead:
    _validate_market_cutoffs(as_of, known_at)
    return q.company_estimate_momentum(db, company_id, as_of, known_at)


@router.get(
    "/companies/{company_id}/temporal-alignment",
    response_model=s.CompanyTemporalAlignmentRead,
)
def get_company_temporal_alignment(
    company_id: UUID,
    db: Db,
    fiscal_year: Annotated[int, Query(ge=1800, le=2200)],
    as_of: date,
    known_at: datetime | None = None,
    outcome_known_at: datetime | None = None,
    horizon_days: Annotated[int, Query(ge=1, le=3650)] = 365,
) -> s.CompanyTemporalAlignmentRead:
    for name, value in (("known_at", known_at), ("outcome_known_at", outcome_known_at)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(422, f"{name} must include a timezone offset")
    forecast_cutoff = datetime.combine(as_of, time.max, UTC)
    if known_at is not None and known_at.astimezone(UTC) > forecast_cutoff:
        raise HTTPException(422, "known_at cannot be later than the as_of cutoff")
    return company_temporal_alignment(
        db,
        company_id,
        fiscal_year=fiscal_year,
        as_of=as_of,
        known_at=known_at,
        outcome_known_at=outcome_known_at,
        horizon_days=horizon_days,
    )


@router.get(
    "/companies/{company_id}/forecast-accuracy",
    response_model=s.CompanyForecastAccuracyRead,
)
def get_company_forecast_accuracy(
    company_id: UUID,
    db: Db,
    metric: ForecastAccuracyMetric | None = None,
    source: ForecastAccuracySourceType | None = None,
    period_type: ResearchPeriodType | None = None,
    fiscal_year: Annotated[int | None, Query(ge=1800, le=2200)] = None,
    fiscal_period: Annotated[str | None, Query(max_length=8)] = None,
    outcome_known_at: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> s.CompanyForecastAccuracyRead:
    if outcome_known_at is not None and (
        outcome_known_at.tzinfo is None or outcome_known_at.utcoffset() is None
    ):
        raise HTTPException(422, "outcome_known_at must include a timezone offset")
    try:
        return company_forecast_accuracy(
            db,
            company_id,
            metric=metric,
            source=source,
            period_type=period_type.value if period_type else None,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            outcome_known_at=outcome_known_at,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.get(
    "/companies/{company_id}/decision-evaluation",
    response_model=s.CompanyDecisionEvaluationRead,
)
def get_company_decision_evaluation(
    company_id: UUID,
    db: Db,
    outcome_known_at: datetime | None = None,
    horizons_days: Annotated[list[int] | None, Query(max_length=3)] = None,
) -> s.CompanyDecisionEvaluationRead:
    if outcome_known_at is not None and (
        outcome_known_at.tzinfo is None or outcome_known_at.utcoffset() is None
    ):
        raise HTTPException(422, "outcome_known_at must include a timezone offset")
    try:
        return company_decision_evaluation(
            db,
            company_id,
            outcome_known_at=outcome_known_at,
            horizons_days=horizons_days,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.get(
    "/companies/{company_id}/model-outputs/current",
    response_model=s.CompanyModelOutputsCurrentRead,
)
def get_current_model_outputs(company_id: UUID, db: Db) -> s.CompanyModelOutputsCurrentRead:
    return q.company_model_outputs_current(db, company_id)


@router.get(
    "/companies/{company_id}/model-outputs/history",
    response_model=list[s.ModelOutputSnapshotRead],
)
def get_model_output_history(
    company_id: UUID,
    db: Db,
    model_key: Annotated[str | None, Query(max_length=120)] = None,
) -> list[s.ModelOutputSnapshotRead]:
    return q.company_model_outputs_history(db, company_id, model_key)


@router.get(
    "/companies/{company_id}/expected-return-history",
    response_model=s.CompanyExpectedReturnHistoryRead,
)
def get_company_expected_return_history(
    company_id: UUID,
    db: Db,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyExpectedReturnHistoryRead:
    _validate_market_cutoffs(as_of, known_at)
    return q.company_expected_return_history(db, company_id, as_of, known_at)


@router.get(
    "/companies/{company_id}/expected-return-attribution",
    response_model=s.CompanyExpectedReturnAttributionRead,
)
def get_company_expected_return_attribution(
    company_id: UUID,
    db: Db,
    prior_point_id: Annotated[str, Query(min_length=1, max_length=100)],
    current_point_id: Annotated[str, Query(min_length=1, max_length=100)],
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyExpectedReturnAttributionRead:
    _validate_market_cutoffs(as_of, known_at)
    return company_expected_return_attribution(
        db, company_id, prior_point_id, current_point_id, as_of, known_at
    )


@router.get(
    "/companies/{company_id}/model-migration-status",
    response_model=s.CompanyFinancialModelMigrationRead,
)
def get_company_model_migration_status(
    company_id: UUID, db: Db
) -> s.CompanyFinancialModelMigrationRead:
    try:
        return company_model_migration_status(db, company_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from None


@router.get(
    "/companies/{company_id}/financial-models",
    response_model=list[s.FinancialModelRead],
)
def get_company_financial_models(company_id: UUID, db: Db) -> list[s.FinancialModelRead]:
    return q.company_financial_models(db, company_id)


@router.get(
    "/companies/{company_id}/canonical-financial-models",
    response_model=list[s.ExtendedFinancialModelRead],
)
def get_company_extended_financial_models(
    company_id: UUID, db: Db
) -> list[s.ExtendedFinancialModelRead]:
    return q.company_extended_financial_models(db, company_id)


@router.post(
    "/companies/{company_id}/financial-models",
    response_model=s.FinancialModelRead,
    status_code=201,
)
def post_company_financial_model(
    company_id: UUID, value: s.FinancialModelCreate, db: Db
) -> s.FinancialModelRead:
    model = operations.create_financial_model(db, company_id, value)
    return q.financial_model(db, model.id)


@router.post(
    "/companies/{company_id}/canonical-financial-models/owner-cash-flow",
    response_model=s.ExtendedFinancialModelRead,
    status_code=201,
)
def post_owner_cash_flow_model(
    company_id: UUID, value: s.OwnerCashFlowModelCreate, db: Db
) -> s.ExtendedFinancialModelRead:
    model = operations.create_owner_cash_flow_model(db, company_id, value)
    return q.extended_financial_model(db, model.id)


@router.post(
    "/companies/{company_id}/canonical-financial-models/residual-income",
    response_model=s.ExtendedFinancialModelRead,
    status_code=201,
)
def post_residual_income_model(
    company_id: UUID, value: s.ResidualIncomeModelCreate, db: Db
) -> s.ExtendedFinancialModelRead:
    model = operations.create_residual_income_model(db, company_id, value)
    return q.extended_financial_model(db, model.id)


@router.post(
    "/companies/{company_id}/canonical-financial-models/owner-cash-flow/preview",
    response_model=s.OwnerCashFlowCalculationPreviewRead,
)
def post_owner_cash_flow_initial_preview(
    company_id: UUID, value: s.OwnerCashFlowInitialPreviewCreate, db: Db
) -> s.OwnerCashFlowCalculationPreviewRead:
    return operations.preview_owner_cash_flow_initial(db, company_id, value)


@router.post(
    "/companies/{company_id}/canonical-financial-models/residual-income/preview",
    response_model=s.ResidualIncomeCalculationPreviewRead,
)
def post_residual_income_initial_preview(
    company_id: UUID, value: s.ResidualIncomeInitialPreviewCreate, db: Db
) -> s.ResidualIncomeCalculationPreviewRead:
    return operations.preview_residual_income_initial(db, company_id, value)


@router.get(
    "/canonical-financial-models/{model_id}",
    response_model=s.ExtendedFinancialModelRead,
)
def get_extended_financial_model(model_id: UUID, db: Db) -> s.ExtendedFinancialModelRead:
    return q.extended_financial_model(db, model_id)


@router.get(
    "/canonical-financial-models/{model_id}/contract",
    response_model=s.AdditionalModelPortableContractV2,
)
def get_additional_model_contract(model_id: UUID, db: Db) -> s.AdditionalModelPortableContractV2:
    return operations.export_additional_model_contract(db, model_id)


@router.post(
    "/canonical-financial-models/{model_id}/contract/preview",
    response_model=s.AdditionalModelContractPreviewRead,
)
def post_additional_model_contract_preview(
    model_id: UUID, value: s.AdditionalModelPortableContractV2, db: Db
) -> s.AdditionalModelContractPreviewRead:
    return operations.preview_additional_model_contract(db, model_id, value)


@router.post(
    "/canonical-financial-models/{model_id}/contract/import",
    response_model=s.AdditionalModelContractImportRead,
)
def post_additional_model_contract_import(
    model_id: UUID, value: s.AdditionalModelPortableContractV2, db: Db
) -> s.AdditionalModelContractImportRead:
    return operations.import_additional_model_contract(db, model_id, value)


@router.get(
    "/canonical-financial-models/{model_id}/revisions/{revision_id}",
    response_model=s.OwnerCashFlowRevisionRead | s.ResidualIncomeRevisionRead,
)
def get_extended_financial_model_revision(
    model_id: UUID, revision_id: UUID, db: Db
) -> s.OwnerCashFlowRevisionRead | s.ResidualIncomeRevisionRead:
    return q.extended_financial_model_revision(db, model_id, revision_id)


@router.post(
    "/canonical-financial-models/{model_id}/owner-cash-flow/revisions",
    response_model=s.OwnerCashFlowRevisionRead,
    status_code=201,
)
def post_owner_cash_flow_revision(
    model_id: UUID, value: s.OwnerCashFlowRevisionCreate, db: Db
) -> s.OwnerCashFlowRevisionRead:
    revision = operations.append_owner_cash_flow_revision(db, model_id, value)
    return q.extended_financial_model_revision(db, model_id, revision.id)  # type: ignore[return-value]


@router.post(
    "/canonical-financial-models/{model_id}/residual-income/revisions",
    response_model=s.ResidualIncomeRevisionRead,
    status_code=201,
)
def post_residual_income_revision(
    model_id: UUID, value: s.ResidualIncomeRevisionCreate, db: Db
) -> s.ResidualIncomeRevisionRead:
    revision = operations.append_residual_income_revision(db, model_id, value)
    return q.extended_financial_model_revision(db, model_id, revision.id)  # type: ignore[return-value]


@router.post(
    "/canonical-financial-models/{model_id}/owner-cash-flow/revisions/preview",
    response_model=s.OwnerCashFlowCalculationPreviewRead,
)
def post_owner_cash_flow_revision_preview(
    model_id: UUID, value: s.OwnerCashFlowRevisionPreviewCreate, db: Db
) -> s.OwnerCashFlowCalculationPreviewRead:
    return operations.preview_owner_cash_flow_revision(db, model_id, value)


@router.post(
    "/canonical-financial-models/{model_id}/residual-income/revisions/preview",
    response_model=s.ResidualIncomeCalculationPreviewRead,
)
def post_residual_income_revision_preview(
    model_id: UUID, value: s.ResidualIncomeRevisionPreviewCreate, db: Db
) -> s.ResidualIncomeCalculationPreviewRead:
    return operations.preview_residual_income_revision(db, model_id, value)


@router.post(
    "/companies/{company_id}/financial-models/preview",
    response_model=s.FinancialModelCalculationPreviewRead,
)
def post_financial_model_initial_calculation_preview(
    company_id: UUID, value: s.FinancialModelInitialCalculationPreviewCreate, db: Db
) -> s.FinancialModelCalculationPreviewRead:
    return operations.preview_financial_model_initial_calculation(db, company_id, value)


@router.get("/financial-models/{model_id}", response_model=s.FinancialModelRead)
def get_financial_model(model_id: UUID, db: Db) -> s.FinancialModelRead:
    return q.financial_model(db, model_id)


@router.get(
    "/financial-models/{model_id}/contract",
    response_model=s.FinancialModelContractV1,
)
def get_financial_model_contract(model_id: UUID, db: Db) -> s.FinancialModelContractV1:
    return operations.export_financial_model_contract(db, model_id)


@router.post(
    "/financial-models/{model_id}/contract/preview",
    response_model=s.FinancialModelContractPreviewRead,
)
def post_financial_model_contract_preview(
    model_id: UUID, value: s.FinancialModelContractV1, db: Db
) -> s.FinancialModelContractPreviewRead:
    return operations.preview_financial_model_contract(db, model_id, value)


@router.post(
    "/financial-models/{model_id}/contract/import",
    response_model=s.FinancialModelContractImportRead,
)
def post_financial_model_contract_import(
    model_id: UUID, value: s.FinancialModelContractV1, db: Db
) -> s.FinancialModelContractImportRead:
    return operations.import_financial_model_contract(db, model_id, value)


@router.get(
    "/financial-models/{model_id}/revisions",
    response_model=list[s.FinancialModelRevisionSummary],
)
def get_financial_model_history(model_id: UUID, db: Db) -> list[s.FinancialModelRevisionSummary]:
    return q.financial_model_revision_history(db, model_id)


@router.get(
    "/financial-models/{model_id}/revisions/{revision_id}",
    response_model=s.FinancialModelRevisionRead,
)
def get_financial_model_revision(
    model_id: UUID, revision_id: UUID, db: Db
) -> s.FinancialModelRevisionRead:
    return q.financial_model_revision(db, model_id, revision_id)


@router.post(
    "/financial-models/{model_id}/revisions",
    response_model=s.FinancialModelRevisionRead,
    status_code=201,
)
def post_financial_model_revision(
    model_id: UUID, value: s.FinancialModelRevisionCreate, db: Db
) -> s.FinancialModelRevisionRead:
    revision = operations.append_financial_model_revision(db, model_id, value)
    return q.financial_model_revision(db, model_id, revision.id)


@router.post(
    "/financial-models/{model_id}/revisions/preview",
    response_model=s.FinancialModelCalculationPreviewRead,
)
def post_financial_model_revision_calculation_preview(
    model_id: UUID, value: s.FinancialModelRevisionCalculationPreviewCreate, db: Db
) -> s.FinancialModelCalculationPreviewRead:
    return operations.preview_financial_model_revision_calculation(db, model_id, value)


@router.get("/listings/{listing_id}/market-data", response_model=s.ListingMarketData)
def get_listing_market_data(
    listing_id: UUID,
    db: Db,
    history_limit: Annotated[int, Query(ge=0, le=252)] = 90,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.ListingMarketData:
    _validate_market_cutoffs(as_of, known_at)
    return q.listing_market_data_by_id(db, listing_id, history_limit, as_of, known_at)


@router.get("/listings/{listing_id}/corporate-actions", response_model=list[s.CorporateActionRead])
def get_listing_corporate_actions(
    listing_id: UUID,
    db: Db,
    as_of: date | None = None,
    known_at: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[s.CorporateActionRead]:
    _validate_market_cutoffs(as_of, known_at)
    return q.listing_corporate_actions(db, listing_id, as_of=as_of, known_at=known_at, limit=limit)


@router.get("/fx-observations", response_model=list[s.FxObservationRead])
def get_fx_observations(
    db: Db,
    base_currency: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
    quote_currency: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
) -> list[s.FxObservationRead]:
    _validate_market_cutoffs(as_of, known_at)
    return q.fx_observations(db, base_currency, quote_currency, as_of, known_at)


@router.post("/fx-observations", response_model=s.FxObservationRead, status_code=201)
def post_fx_observation(value: s.FxObservationCreate, db: Db) -> s.FxObservationRead:
    return s.FxObservationRead.model_validate(operations.record_fx_observation(db, value))


@router.post("/companies/{company_id}/securities", response_model=s.SecurityRead, status_code=201)
def post_security(company_id: UUID, value: s.SecurityCreate, db: Db) -> s.SecurityRead:
    return s.SecurityRead.model_validate(operations.create_security(db, company_id, value))


@router.post("/securities/{security_id}/listings", response_model=s.ListingRead, status_code=201)
def post_listing(security_id: UUID, value: s.ListingCreate, db: Db) -> s.ListingRead:
    return s.ListingRead.model_validate(operations.create_listing(db, security_id, value))


@router.post(
    "/companies/{company_id}/lifecycle-transitions",
    response_model=s.LifecycleEventRead,
    status_code=201,
)
def post_transition(company_id: UUID, value: s.LifecycleChange, db: Db) -> s.LifecycleEventRead:
    return s.LifecycleEventRead.model_validate(
        operations.transition_lifecycle(db, company_id, value)
    )


@router.get("/portfolios", response_model=list[s.PortfolioRead])
def get_portfolios(db: Db) -> list[s.PortfolioRead]:
    return [
        s.PortfolioRead.model_validate(p)
        for p in db.scalars(select(Portfolio).order_by(Portfolio.created_at))
    ]


@router.post("/portfolios", response_model=s.PortfolioRead, status_code=201)
def post_portfolio(value: s.PortfolioCreate, db: Db) -> s.PortfolioRead:
    return s.PortfolioRead.model_validate(operations.create_portfolio(db, value))


@router.get("/portfolios/{portfolio_id}/overview", response_model=s.PortfolioOverview)
def get_overview(
    portfolio_id: UUID,
    db: Db,
    as_of: Annotated[
        datetime | None, Query(description="Historical valuation and knowledge cutoff")
    ] = None,
) -> s.PortfolioOverview:
    _validate_market_cutoffs(as_of, None)
    return q.overview(db, portfolio_id, as_of)


@router.get("/portfolios/{portfolio_id}/holding-snapshots", response_model=list[s.SnapshotRead])
def get_snapshots(portfolio_id: UUID, db: Db) -> list[s.SnapshotRead]:
    from portfolio_api.domain.models import HoldingSnapshot

    operations.portfolio(db, portfolio_id)
    return [
        q.snapshot_read(db, h)
        for h in db.scalars(
            select(HoldingSnapshot)
            .where(
                HoldingSnapshot.portfolio_id == portfolio_id,
            )
            .order_by(HoldingSnapshot.effective_at.desc())
        )
    ]


@router.post(
    "/portfolios/{portfolio_id}/holding-snapshots", response_model=s.SnapshotRead, status_code=201
)
def post_snapshot(portfolio_id: UUID, value: s.SnapshotCreate, db: Db) -> s.SnapshotRead:
    return q.snapshot_read(db, operations.record_holdings(db, portfolio_id, value))


@router.get("/portfolios/{portfolio_id}/target-revisions", response_model=list[s.TargetRead])
def get_targets(portfolio_id: UUID, db: Db) -> list[s.TargetRead]:
    from portfolio_api.domain.models import TargetRevision

    operations.portfolio(db, portfolio_id)
    return [
        q.target_read(db, t)
        for t in db.scalars(
            select(TargetRevision)
            .where(
                TargetRevision.portfolio_id == portfolio_id,
            )
            .order_by(TargetRevision.recorded_at.desc())
        )
    ]


@router.post(
    "/portfolios/{portfolio_id}/target-revisions", response_model=s.TargetRead, status_code=201
)
def post_targets(portfolio_id: UUID, value: s.TargetCreate, db: Db) -> s.TargetRead:
    return q.target_read(db, operations.create_targets(db, portfolio_id, value))


@router.post(
    "/portfolios/{portfolio_id}/target-revisions/{revision_id}/accept", response_model=s.TargetRead
)
def post_accept(portfolio_id: UUID, revision_id: UUID, db: Db) -> s.TargetRead:
    return q.target_read(db, operations.accept_targets(db, portfolio_id, revision_id))
