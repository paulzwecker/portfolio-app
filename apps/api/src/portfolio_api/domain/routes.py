"""Domain-oriented REST operations; session dependency commits each operation atomically."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from portfolio_api.attention import attention_feed
from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as operations
from portfolio_api.domain.models import (
    FundamentalPeriodType,
    Lifecycle,
    Portfolio,
    RankingType,
    ScoreDimension,
    SourceDocumentType,
)
from portfolio_api.execution_pace import create_execution_pace_run
from portfolio_api.expected_return_attribution import company_expected_return_attribution
from portfolio_api.model_migration_status import company_model_migration_status
from portfolio_api.reported_fundamentals import METRIC_DEFINITIONS
from portfolio_api.source_documents import create_company_source_document
from portfolio_api.temporal_alignment import company_temporal_alignment

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


@router.get("/attention", response_model=s.AttentionFeedRead)
def get_attention_feed(
    db: Db,
    company_id: UUID | None = None,
    event_type: Annotated[
        str | None,
        Query(
            pattern="^(MODEL_REVISION|MODEL_OUTPUT_IMPORT|EXPECTED_IRR_CHANGE|CONSENSUS_REVISION|NEW_FILING|PRICE_MOVE|RANK_CHANGE|EXECUTION_PACE_CHANGE|DATA_QUALITY)$"
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
def get_overview(portfolio_id: UUID, db: Db) -> s.PortfolioOverview:
    return q.overview(db, portfolio_id)


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
