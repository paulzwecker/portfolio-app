"""Exact decimal and timestamp contracts for explicit domain operations."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from portfolio_api.domain.models import (
    Actor,
    DcfScenario,
    FinancialModelType,
    FundamentalDataQuality,
    FundamentalMetric,
    FundamentalPeriodType,
    FundamentalRevisionContext,
    FundamentalStatement,
    Lifecycle,
    RankingDefinitionStatus,
    RankingEntryStatus,
    RankingImplementationStatus,
    RankingRunStatus,
    RankingType,
    ScoreAssessmentStatus,
    ScoreDefinitionStatus,
    ScoreDimension,
    ScoreDirectionality,
    SourceDocumentQuality,
    SourceDocumentType,
)


def exact(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError("Use a decimal string, not a floating point value")
    return value


def decimal_string(value: Decimal) -> str:
    return format(value, "f")


FixedDecimal = Annotated[
    Decimal, PlainSerializer(decimal_string, return_type=str, when_used="json")
]
Quantity = Annotated[
    FixedDecimal, BeforeValidator(exact), Field(ge=0, max_digits=28, decimal_places=10)
]
Weight = Annotated[
    FixedDecimal, BeforeValidator(exact), Field(ge=0, le=1, max_digits=18, decimal_places=12)
]
ScoreValue = Annotated[
    FixedDecimal, BeforeValidator(exact), Field(ge=0, le=5, max_digits=6, decimal_places=4)
]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Name = Annotated[str, Field(min_length=1, max_length=200)]


class Contract(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)


class CompanyCreate(Contract):
    name: Name
    reporting_currency: Currency | None = None


class CompanyRead(CompanyCreate):
    id: UUID
    created_at: datetime
    is_demo: bool
    lifecycle: Lifecycle | None
    lifecycle_event_id: UUID | None


class SecurityCreate(Contract):
    name: Name
    security_type: Literal["COMMON_STOCK", "ADR", "PREFERRED"]
    share_class: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    underlying_security_id: UUID | None = None


class SecurityRead(Contract):
    id: UUID
    company_id: UUID | None
    name: Name
    security_type: Literal["COMMON_STOCK", "ADR", "PREFERRED", "ETF"]
    share_class: Annotated[str, Field(min_length=1, max_length=80)] | None
    underlying_security_id: UUID | None
    is_demo: bool


class ListingCreate(Contract):
    venue: Annotated[str, Field(min_length=1, max_length=80)]
    ticker: Annotated[str, Field(min_length=1, max_length=40)]
    currency: Currency | None = None


class ListingRead(ListingCreate):
    id: UUID
    security_id: UUID
    identity_source_ref: str | None
    is_demo: bool


class AuditInput(Contract):
    actor: Actor
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def observed_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware effective timestamp")
        value = value.astimezone(UTC)
        if value > datetime.now(UTC):
            raise ValueError("Future-effective records are outside Milestone 1A")
        return value


class LifecycleChange(AuditInput):
    new_state: Lifecycle
    expected_event_id: UUID | None


class LifecycleEventRead(AuditInput):
    id: UUID
    company_id: UUID
    sequence: int
    previous_state: Lifecycle | None
    new_state: Lifecycle
    recorded_at: datetime


class PortfolioCreate(Contract):
    name: Name
    base_currency: Currency


class PortfolioRead(PortfolioCreate):
    id: UUID
    created_at: datetime
    is_demo: bool


class PositionInput(Contract):
    listing_id: UUID
    quantity: Quantity | None


class CashInput(Contract):
    currency: Currency
    balance: Quantity | None


class SnapshotCreate(AuditInput):
    completeness: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    positions: list[PositionInput] = Field(max_length=1000)
    cash_positions: list[CashInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def complete_observation(self) -> Self:
        if len({p.listing_id for p in self.positions}) != len(self.positions):
            raise ValueError("A listing can appear only once in a snapshot")
        if len({p.currency for p in self.cash_positions}) != len(self.cash_positions):
            raise ValueError("A cash currency can appear only once in a snapshot")
        if self.completeness == "UNAVAILABLE" and (self.positions or self.cash_positions):
            raise ValueError("Unavailable snapshots cannot claim observed positions")
        if self.completeness == "COMPLETE" and (
            any(p.quantity is None for p in self.positions)
            or any(p.balance is None for p in self.cash_positions)
        ):
            raise ValueError("Complete snapshots require observed quantities and cash balances")
        return self


class SnapshotRead(SnapshotCreate):
    cash_positions: list[CashInput] = Field(...)
    id: UUID
    portfolio_id: UUID
    recorded_at: datetime


class AllocationInput(Contract):
    company_id: UUID
    weight: Weight


class TargetCreate(AuditInput):
    allocations: list[AllocationInput] = Field(max_length=1000)

    @model_validator(mode="after")
    def invested_targets(self) -> Self:
        if len({a.company_id for a in self.allocations}) != len(self.allocations):
            raise ValueError("A company can have only one target per revision")
        if sum((a.weight for a in self.allocations), Decimal(0)) > 1:
            raise ValueError("Invested targets must sum to at most 1; residual is strategic cash")
        return self


class TargetRead(TargetCreate):
    id: UUID
    portfolio_id: UUID
    recorded_at: datetime
    status: Literal["DRAFT", "ACCEPTED"]
    accepted_at: datetime | None
    invested_weight: FixedDecimal
    strategic_cash_weight: FixedDecimal


class HoldingContext(Contract):
    listing_id: UUID
    security_id: UUID
    ticker: str
    venue: str
    currency: str | None
    security_name: str
    quantity: FixedDecimal | None
    latest_price: FixedDecimal | None
    price_date: datetime | None
    price_currency: Currency | None
    price_freshness: Literal["FRESH", "STALE", "QUALITY_CHECK", "NO_DATA"] = "NO_DATA"
    native_market_value: FixedDecimal | None
    base_market_value: FixedDecimal | None
    valuation_status: Literal[
        "VALUED", "PRICE_UNAVAILABLE", "FX_UNAVAILABLE", "QUANTITY_UNAVAILABLE"
    ] = "PRICE_UNAVAILABLE"


class CompanyPortfolioContext(Contract):
    company: CompanyRead
    positions: list[HoldingContext]
    target_weight: FixedDecimal | None
    current_market_value: FixedDecimal | None
    current_market_currency: Currency | None
    current_weight: FixedDecimal | None
    allocation_gap: FixedDecimal | None
    allocation_status: Literal[
        "VALUED", "PRICE_COVERAGE_INCOMPLETE", "FX_UNAVAILABLE", "PORTFOLIO_TOTAL_UNAVAILABLE"
    ] = "PORTFOLIO_TOTAL_UNAVAILABLE"


class CashValuation(Contract):
    currency: Currency
    balance: FixedDecimal | None
    base_market_value: FixedDecimal | None
    valuation_status: Literal["VALUED", "FX_UNAVAILABLE", "BALANCE_UNAVAILABLE"]


class ValuationGap(Contract):
    identity: str
    reason: str


class PortfolioOverview(Contract):
    portfolio: PortfolioRead
    snapshot: SnapshotRead | None
    target_revision: TargetRead | None
    companies: list[CompanyPortfolioContext]
    standalone_positions: list[HoldingContext]
    valuation_status: Literal[
        "VALUED",
        "NO_HOLDING_SNAPSHOT",
        "INCOMPLETE_HOLDINGS",
        "INCOMPLETE_PRICE_COVERAGE",
        "INCOMPLETE_FX_COVERAGE",
    ] = "NO_HOLDING_SNAPSHOT"
    base_market_value: FixedDecimal | None
    valuation_currency: Currency
    cash_valuations: list[CashValuation]
    valuation_gaps: list[ValuationGap]


class CompanyDetail(Contract):
    company: CompanyRead
    securities: list[SecurityRead]
    listings: list[ListingRead]
    lifecycle_history: list[LifecycleEventRead]
    portfolio: PortfolioRead | None
    portfolio_context: CompanyPortfolioContext | None
    holding_snapshot: SnapshotRead | None
    positions: list[HoldingContext]
    target_weight: FixedDecimal | None
    target_revision_id: UUID | None


class ModelOutputSnapshotRead(Contract):
    id: UUID
    company_id: UUID
    model_key: str
    snapshot_key: str
    snapshot_kind: Literal["CURRENT_CONTRACT", "LEGACY_REVISION"]
    contract_version: str | None
    contract_status: Literal["PASS", "NOT_MAPPED", "NO_CONTRACT", "DATA_CHECK", "HISTORICAL_ONLY"]
    output_quality: Literal["COMPLETE", "PARTIAL", "DATA_CHECK", "UNAVAILABLE"]
    model_currency: Currency | None
    currency_status: Literal["DOCUMENTED", "UNKNOWN"]
    currency_source_ref: str | None
    model_status: str | None
    effective_at: datetime | None
    recorded_at: datetime
    actor: Literal["IMPORT"]
    source: str
    source_revision_id: str | None
    revision_source: str | None
    revision_type: str | None
    source_actor: str | None
    rationale: str | None
    evidence: str | None
    notes: str | None
    field_issues: list[dict[str, str]]
    bear_fv: FixedDecimal | None
    base_fv: FixedDecimal | None
    bull_fv: FixedDecimal | None
    bear_probability: FixedDecimal | None
    base_probability: FixedDecimal | None
    bull_probability: FixedDecimal | None
    weighted_fv: FixedDecimal | None
    weighted_upside: FixedDecimal | None
    expected_cash_flow_irr: FixedDecimal | None
    hurdle: FixedDecimal | None
    expected_excess: FixedDecimal | None
    forward_fundamental_cagr: FixedDecimal | None


class ModelOutputCurrentModelRead(Contract):
    model_key: str
    status: Literal["PUBLISHED", "PARTIAL", "NOT_MAPPED", "NO_CONTRACT", "DATA_CHECK"]
    snapshot: ModelOutputSnapshotRead


class CompanyModelOutputsCurrentRead(Contract):
    company_id: UUID
    status: Literal["AVAILABLE", "PARTIAL", "NOT_MAPPED", "NO_CONTRACT", "DATA_CHECK", "NO_MODEL"]
    history_count: int
    models: list[ModelOutputCurrentModelRead]


class CompanyFinancialModelMigrationItemRead(Contract):
    model_key: str
    company_name: str
    canonical_ticker: str | None
    lifecycle: str
    methodology_family: str
    model_currency: Currency | None
    inventory_status: Literal[
        "READY_FOR_NATIVE_IMPORT",
        "NEEDS_MAPPING",
        "UNSUPPORTED_METHOD",
        "DATA_CHECK",
        "LEGACY_ONLY",
    ]
    representation_status: Literal[
        "NATIVE_EDITABLE",
        "NATIVE_WITH_PARITY_ISSUE",
        "IMPORTED_OUTPUT_ONLY",
        "UNSUPPORTED_LEGACY",
        "LEGACY_ONLY",
        "NOT_IMPORTED",
    ]
    output_snapshot_available: bool
    output_contract_status: str
    native_model_id: UUID | None
    native_revision_number: int | None
    parity_status: Literal["PARITY_PASS", "PARTIAL_MAPPING", "DATA_CHECK", "BLOCKED"] | None
    projections_compared: int | None
    projections_passed: int | None
    outputs_compared: int | None
    outputs_passed: int | None
    blockers: list[str]
    legacy_return_semantics: str | None


class CompanyFinancialModelMigrationRead(Contract):
    company_id: UUID
    inventory_available: bool
    models: list[CompanyFinancialModelMigrationItemRead]


class UniverseModelOutputSummary(Contract):
    company: CompanyRead
    outputs: CompanyModelOutputsCurrentRead


class PriceObservationRead(Contract):
    id: UUID
    listing_id: UUID
    price_kind: Literal["DAILY_CLOSE", "CURRENT_QUOTE"]
    market_date: datetime
    observed_at: datetime | None
    recorded_at: datetime
    provider_close: FixedDecimal | None
    split_adjusted_close: FixedDecimal | None
    total_return_close: FixedDecimal | None
    volume: FixedDecimal | None
    currency: Currency
    provider_currency: str | None
    source_price_multiplier: FixedDecimal
    provider: str
    provider_symbol: str
    adjustment_basis: str
    data_quality: Literal["PASS", "PASS_VERIFIED_FALLBACK", "UNSPECIFIED", "INVALID"]
    source_ref: str


class PriceRegimeRead(Contract):
    listing_id: UUID
    as_of: datetime
    provider_close: FixedDecimal | None
    split_adjusted_close: FixedDecimal | None
    dma_20: FixedDecimal | None
    dma_50: FixedDecimal | None
    dma_200: FixedDecimal | None
    high_52w: FixedDecimal | None
    drawdown_52w: FixedDecimal | None
    vs_dma_20: FixedDecimal | None
    vs_dma_50: FixedDecimal | None
    vs_dma_200: FixedDecimal | None
    return_1m: FixedDecimal | None
    return_3m: FixedDecimal | None
    return_6m: FixedDecimal | None
    realized_vol_20d: FixedDecimal | None
    trend_state: str | None
    correction_state: str | None
    regime: str | None
    data_quality: Literal["PASS", "DATA_CHECK", "UNSPECIFIED"]
    quality_reason: str | None
    methodology_version: str
    source_ref: str


class CorporateActionRead(Contract):
    id: UUID
    listing_id: UUID
    source_action_id: str
    provider: str
    effective_date: datetime
    observed_at: datetime | None
    action_type: str
    ratio_before: FixedDecimal | None
    ratio_after: FixedDecimal | None
    cash_amount: FixedDecimal | None
    cash_currency: Currency | None
    provider_cash_amount: FixedDecimal | None
    provider_cash_currency: str | None
    source_url: str | None
    verified: bool
    notes: str | None


class ListingMarketData(Contract):
    listing: ListingRead
    latest: PriceObservationRead | None
    freshness: Literal["FRESH", "STALE", "QUALITY_CHECK", "NO_DATA"]
    age_days: int | None
    price_regime: PriceRegimeRead | None
    history: list[PriceObservationRead]


class ReportedFundamentalObservationRead(Contract):
    id: UUID
    company_id: UUID
    security_id: UUID | None
    provider_id: str
    provider_entity_id: str
    source_priority: int
    metric: FundamentalMetric
    statement: FundamentalStatement
    period_type: FundamentalPeriodType
    period_start: datetime | None
    period_end: datetime
    fiscal_year: int | None
    fiscal_period: str | None
    filed_at: datetime | None
    observed_at: datetime
    recorded_at: datetime
    value: FixedDecimal
    currency: Currency | None
    unit: str
    source_taxonomy: str
    source_concept: str
    source_unit: str
    accession_number: str | None
    form: str | None
    frame: str | None
    source_record_id: str
    source_url: str
    source_ref: str
    revision_context: FundamentalRevisionContext
    data_quality: FundamentalDataQuality
    quality_reason: str | None
    supersedes_observation_id: UUID | None


class ReportedFundamentalPeriodRead(Contract):
    metric: FundamentalMetric
    statement: FundamentalStatement
    period_type: FundamentalPeriodType
    period_start: datetime | None
    period_end: datetime
    fiscal_year: int | None
    fiscal_period: str | None
    currency: Currency | None
    unit: str
    value: FixedDecimal | None
    selection_status: Literal["AVAILABLE", "CONFLICT", "DATA_CHECK"]
    selected_observation: ReportedFundamentalObservationRead | None
    observations: list[ReportedFundamentalObservationRead]


class ReportedFundamentalCoverageRead(Contract):
    metric: FundamentalMetric
    statement: FundamentalStatement
    observation_count: int
    latest_period_end: datetime | None
    status: Literal["AVAILABLE", "CONFLICT", "DATA_CHECK", "NOT_IMPORTED"]


class ReportedFundamentalDefinitionRead(Contract):
    metric: str
    statement: FundamentalStatement | None
    display_name: str
    canonical_unit: str
    evidence_type: Literal["REPORTED_FACT", "DERIVED_ANALYTIC"]
    description: str


class CompanyReportedFundamentalsRead(Contract):
    company_id: UUID
    provider_identity_status: Literal["MAPPED", "UNMAPPED", "AMBIGUOUS"]
    provider_ids: list[str]
    coverage: list[ReportedFundamentalCoverageRead]
    periods: list[ReportedFundamentalPeriodRead]
    as_of: date | None
    known_at: datetime | None
    latest_observed_at: datetime | None


class ConsensusEstimateObservationRead(Contract):
    id: UUID
    company_id: UUID
    listing_id: UUID | None
    provider_mapping_id: UUID
    provider_id: str
    metric: Literal["REVENUE", "EPS"]
    period_type: Literal["ANNUAL", "QUARTERLY"]
    forecast_period: str
    period_end: date | None
    value: FixedDecimal
    low_value: FixedDecimal | None
    high_value: FixedDecimal | None
    analyst_count: int | None
    currency: Currency | None
    unit: str
    snapshot_date: date
    observed_at: datetime | None
    recorded_at: datetime
    source_record_id: str
    source_ref: str
    revision_context: Literal["SNAPSHOT", "REVISED", "LEGACY_BASELINE"]
    data_quality: Literal["PASS", "DATA_CHECK", "INVALID"]
    quality_reason: str | None
    supersedes_observation_id: UUID | None


class ConsensusEstimatePeriodRead(Contract):
    metric: Literal["REVENUE", "EPS"]
    period_type: Literal["ANNUAL", "QUARTERLY"]
    forecast_period: str
    period_end: date | None
    currency: Currency | None
    unit: str
    current_observation: ConsensusEstimateObservationRead | None
    history: list[ConsensusEstimateObservationRead]


class ConsensusEstimateProviderRead(Contract):
    provider_id: str
    provider_symbol: str
    role: Literal["PRIMARY", "FALLBACK"]
    priority: int
    selected: bool
    mapping_status: Literal["SELECTED", "ALTERNATE", "AMBIGUOUS"]
    currency: Currency | None
    currency_evidence_source: str | None
    identity_evidence_source: str
    effective_from: datetime
    freshness: Literal["FRESH", "STALE", "DATA_CHECK", "NO_DATA"]
    latest_snapshot_date: date | None
    latest_observed_at: datetime | None
    observation_count: int
    missing_metrics: list[Literal["REVENUE", "EPS"]]
    periods: list[ConsensusEstimatePeriodRead]


class CompanyConsensusEstimatesRead(Contract):
    company_id: UUID
    continuity_status: Literal[
        "PRIMARY_SELECTED",
        "FALLBACK_SELECTED",
        "PRIMARY_NO_DATA",
        "NO_MAPPING",
        "AMBIGUOUS_FALLBACK",
    ]
    selected_provider_id: str | None
    as_of: date | None
    known_at: datetime | None
    providers: list[ConsensusEstimateProviderRead]


class SourceDocumentCreate(Contract):
    """Register an issuer-published source reference without uploading its content."""

    security_id: UUID | None = None
    provider_id: Literal["company_source"] = "company_source"
    source_name: Annotated[str, Field(min_length=1, max_length=200)]
    source_jurisdiction: Annotated[str, Field(max_length=80)] | None = None
    external_identifier: Annotated[str, Field(min_length=1, max_length=500)]
    document_type: SourceDocumentType
    title: Annotated[str, Field(min_length=1, max_length=500)]
    reporting_period: Annotated[str, Field(max_length=120)] | None = None
    fiscal_year: int | None = Field(default=None, ge=1800, le=2200)
    fiscal_period: Annotated[str, Field(max_length=40)] | None = None
    period_end: date | None = None
    published_at: date | None = None
    canonical_url: AnyHttpUrl
    is_amendment: bool = False
    amends_document_id: UUID | None = None
    supersedes_document_id: UUID | None = None
    data_quality: SourceDocumentQuality = SourceDocumentQuality.PASS
    quality_reason: Annotated[str, Field(max_length=1000)] | None = None
    actor: Actor = Actor.LOCAL_USER

    @field_validator("canonical_url")
    @classmethod
    def secure_source_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("Primary-source document links must use HTTPS")
        return value

    @model_validator(mode="after")
    def explicit_quality_and_amendment(self) -> Self:
        if self.published_at is None and self.data_quality != SourceDocumentQuality.DATA_CHECK:
            raise ValueError("Undated company-source references must be marked DATA_CHECK")
        if self.data_quality == SourceDocumentQuality.DATA_CHECK and not self.quality_reason:
            raise ValueError("DATA_CHECK source references require a quality reason")
        if self.is_amendment and self.amends_document_id is None and not self.quality_reason:
            raise ValueError("Unlinked amendments require an explicit quality reason")
        if (
            self.is_amendment
            and self.amends_document_id is None
            and self.data_quality != SourceDocumentQuality.DATA_CHECK
        ):
            raise ValueError("An unlinked amendment must be marked DATA_CHECK")
        return self


class SourceDocumentRead(Contract):
    id: UUID
    company_id: UUID
    security_id: UUID | None
    batch_id: UUID | None
    provider_id: str
    source_name: str
    source_jurisdiction: str | None
    external_identifier: str
    document_type: SourceDocumentType
    source_form: str | None
    title: str
    reporting_period: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    period_end: date | None
    filed_at: date | None
    published_at: date | None
    canonical_url: AnyHttpUrl
    retrieved_at: datetime | None
    recorded_at: datetime
    is_amendment: bool
    amends_document_id: UUID | None
    supersedes_document_id: UUID | None
    data_quality: SourceDocumentQuality
    quality_reason: str | None
    actor: Actor


class CompanySourceDocumentsRead(Contract):
    company_id: UUID
    sec_identity_status: Literal["MAPPED", "UNMAPPED", "AMBIGUOUS"]
    source_count: int
    as_of: date | None
    known_at: datetime | None
    documents: list[SourceDocumentRead]


class UniverseMarketSummary(Contract):
    company: CompanyRead
    market_data: list[ListingMarketData]


class FxObservationCreate(Contract):
    base_currency: Currency
    quote_currency: Currency
    rate: Annotated[
        FixedDecimal, BeforeValidator(exact), Field(gt=0, max_digits=28, decimal_places=14)
    ]
    effective_at: datetime
    provider: Annotated[str, Field(min_length=1, max_length=120)]
    source: Annotated[str, Field(min_length=1, max_length=1000)]
    actor: Actor
    reason: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("effective_at")
    @classmethod
    def observed_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware effective timestamp")
        value = value.astimezone(UTC)
        if value > datetime.now(UTC):
            raise ValueError("Future-effective FX observations are not supported")
        return value

    @model_validator(mode="after")
    def distinct_currencies(self) -> Self:
        if self.base_currency == self.quote_currency:
            raise ValueError("FX currencies must differ")
        return self


class FxObservationRead(Contract):
    id: UUID
    base_currency: Currency
    quote_currency: Currency
    rate: FixedDecimal
    data_quality: Literal["PASS", "DATA_CHECK", "INVALID"]
    effective_at: datetime
    observed_at: datetime | None
    recorded_at: datetime
    source_ref: str | None
    provider: str
    source: str
    actor: Actor
    reason: str


class ScoreDefinitionRead(Contract):
    id: UUID
    dimension: ScoreDimension
    version: int
    minimum_score: FixedDecimal
    maximum_score: FixedDecimal
    directionality: ScoreDirectionality
    units: str
    methodology: str
    effective_from: datetime
    status: ScoreDefinitionStatus
    recorded_at: datetime


class ScoreAssessmentCreate(Contract):
    dimension: ScoreDimension
    score: ScoreValue | None
    status: ScoreAssessmentStatus
    effective_at: datetime
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]
    actor: Actor
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    superseded_assessment_id: UUID | None = None

    @field_validator("effective_at")
    @classmethod
    def observed_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware effective timestamp")
        value = value.astimezone(UTC)
        if value > datetime.now(UTC):
            raise ValueError("Future-effective score assessments are not supported")
        return value

    @model_validator(mode="after")
    def score_matches_status(self) -> Self:
        if (self.status == ScoreAssessmentStatus.ASSESSED) != (self.score is not None):
            raise ValueError("ASSESSED requires a score; other statuses require a null score")
        return self


class ScoreAssessmentRead(Contract):
    id: UUID
    company_id: UUID
    score_definition_id: UUID
    score: FixedDecimal | None
    status: ScoreAssessmentStatus
    effective_at: datetime
    recorded_at: datetime
    rationale: str
    actor: Actor
    source: str | None
    superseded_assessment_id: UUID | None


class ScoreCurrentRead(Contract):
    definition: ScoreDefinitionRead
    assessment: ScoreAssessmentRead | None


class ScoreHistoryEntry(Contract):
    definition: ScoreDefinitionRead
    assessment: ScoreAssessmentRead


class UniverseScoreSummary(Contract):
    company: CompanyRead
    scores: list[ScoreCurrentRead]


class RankingDefinitionRead(Contract):
    id: UUID
    ranking_type: RankingType
    version: int
    title: str
    methodology: str
    population_rule: str
    required_inputs: str
    source_reference: str
    implementation_status: RankingImplementationStatus
    effective_from: datetime
    status: RankingDefinitionStatus
    recorded_at: datetime


class RankingRunCreate(Contract):
    ranking_type: RankingType
    actor: Actor
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None


class RankingRunRead(Contract):
    id: UUID
    definition: RankingDefinitionRead
    as_of: datetime
    recorded_at: datetime
    status: RankingRunStatus
    actor: Actor
    reason: str
    source: str | None
    company_count: int
    ranked_count: int


class RankingEntryRead(Contract):
    id: UUID
    run_id: UUID
    company_id: UUID
    position: int | None
    status: RankingEntryStatus
    reason: str


class RankingCurrentRead(Contract):
    definition: RankingDefinitionRead
    run: RankingRunRead | None
    entry: RankingEntryRead | None


class RankingHistoryEntry(Contract):
    run: RankingRunRead
    entry: RankingEntryRead


class CompanyRankingsRead(Contract):
    current: list[RankingCurrentRead]
    history: list[RankingHistoryEntry]


class RankingRunEntryRead(Contract):
    company: CompanyRead
    entry: RankingEntryRead


class RankingRunDetailRead(Contract):
    run: RankingRunRead
    entries: list[RankingRunEntryRead]


class UniverseRankingSummary(Contract):
    company: CompanyRead
    rankings: list[RankingCurrentRead]


class DomainErrorRead(Contract):
    detail: str


ModelNumber = Annotated[
    FixedDecimal, BeforeValidator(exact), Field(max_digits=38, decimal_places=18)
]
PositiveModelNumber = Annotated[ModelNumber, Field(gt=0)]
Probability = Annotated[ModelNumber, Field(ge=0, le=1)]


class DcfOperatingBase(Contract):
    base_revenue: PositiveModelNumber
    base_ebit_margin: Annotated[ModelNumber, Field(ge=-1, le=2)]
    base_tax_rate: Annotated[ModelNumber, Field(ge=0, le=1)]
    base_da_to_revenue: Annotated[ModelNumber, Field(ge=0, le=2)]
    base_capex_to_revenue: Annotated[ModelNumber, Field(ge=0, le=10)]
    base_nwc_to_revenue: Annotated[ModelNumber, Field(ge=-10, le=10)]
    net_cash_debt: ModelNumber
    diluted_shares: PositiveModelNumber


class DcfYearAssumptionInput(Contract):
    forecast_year: Annotated[int, Field(ge=1, le=5)]
    revenue_growth: Annotated[ModelNumber, Field(ge=-0.99, le=10)]
    ebit_margin: Annotated[ModelNumber, Field(ge=-1, le=2)]
    tax_rate: Annotated[ModelNumber, Field(ge=0, le=1)]
    da_to_revenue: Annotated[ModelNumber, Field(ge=0, le=2)]
    capex_to_revenue: Annotated[ModelNumber, Field(ge=0, le=10)]
    nwc_to_revenue: Annotated[ModelNumber, Field(ge=-10, le=10)]
    discount_rate: Annotated[ModelNumber, Field(ge=0, lt=1)]


class DcfScenarioInput(Contract):
    scenario: DcfScenario
    probability: Probability
    terminal_growth: Annotated[ModelNumber, Field(ge=-0.5, le=0.5)]
    year10_ufcf_growth: Annotated[ModelNumber, Field(ge=-0.99, le=10)]
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]
    years: list[DcfYearAssumptionInput] = Field(min_length=5, max_length=5)


class DcfCalculationInput(Contract):
    base: DcfOperatingBase
    scenarios: list[DcfScenarioInput] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def supported_scenario_contract(self) -> Self:
        if {scenario.scenario for scenario in self.scenarios} != set(DcfScenario):
            raise ValueError("A UFCF DCF revision requires Bear, Base and Bull scenarios")
        if sum((scenario.probability for scenario in self.scenarios), Decimal(0)) != Decimal(1):
            raise ValueError("Bear, Base and Bull probabilities must sum exactly to 1")
        for scenario in self.scenarios:
            years = {year.forecast_year for year in scenario.years}
            if years != {1, 2, 3, 4, 5}:
                raise ValueError("Each scenario must provide exactly years 1 through 5")
            terminal_discount_rate = next(
                year.discount_rate for year in scenario.years if year.forecast_year == 5
            )
            if scenario.terminal_growth >= terminal_discount_rate:
                raise ValueError("Terminal growth must be below the year-five discount rate")
        return self


class OwnerCashFlowBase(Contract):
    """Owner-cash-flow method inputs. Amounts use source-model billions convention."""

    base_revenue: PositiveModelNumber
    net_cash: ModelNumber
    diluted_shares: PositiveModelNumber


class OwnerCashFlowYearInput(Contract):
    forecast_year: Annotated[int, Field(ge=1, le=10)]
    revenue_growth: Annotated[ModelNumber, Field(ge=-0.99, le=10)]
    owner_cash_flow_margin: Annotated[ModelNumber, Field(ge=-1, le=5)]


class OwnerCashFlowScenarioInput(Contract):
    scenario: DcfScenario
    probability: Probability
    required_return: Annotated[ModelNumber, Field(ge=0, lt=1)]
    terminal_growth: Annotated[ModelNumber, Field(ge=-0.5, le=0.5)]
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]
    years: list[OwnerCashFlowYearInput] = Field(min_length=10, max_length=10)


class OwnerCashFlowInput(Contract):
    base: OwnerCashFlowBase
    scenarios: list[OwnerCashFlowScenarioInput] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_owner_cash_flow(self) -> Self:
        if {scenario.scenario for scenario in self.scenarios} != set(DcfScenario):
            raise ValueError("Owner cash-flow input requires Bear, Base and Bull scenarios")
        if sum((scenario.probability for scenario in self.scenarios), Decimal(0)) != Decimal(1):
            raise ValueError("Bear, Base and Bull probabilities must sum exactly to 1")
        for scenario in self.scenarios:
            if {year.forecast_year for year in scenario.years} != set(range(1, 11)):
                raise ValueError(
                    "Each owner cash-flow scenario requires exactly years 1 through 10"
                )
            if scenario.terminal_growth >= scenario.required_return:
                raise ValueError("Terminal growth must remain below required return")
        return self


class ResidualIncomeBase(Contract):
    current_book_value_per_share: PositiveModelNumber
    payout_ratio: Annotated[ModelNumber, Field(ge=0, le=1)]


class ResidualIncomeScenarioInput(Contract):
    scenario: DcfScenario
    probability: Probability
    starting_roe: Annotated[ModelNumber, Field(ge=-1, le=2)]
    cost_of_equity: Annotated[ModelNumber, Field(ge=0, lt=1)]
    terminal_growth: Annotated[ModelNumber, Field(ge=-0.5, le=0.5)]
    mature_roe: Annotated[ModelNumber, Field(ge=-1, le=2)]
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]


class ResidualIncomeInput(Contract):
    base: ResidualIncomeBase
    scenarios: list[ResidualIncomeScenarioInput] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_residual_income(self) -> Self:
        if {scenario.scenario for scenario in self.scenarios} != set(DcfScenario):
            raise ValueError("Residual income input requires Bear, Base and Bull scenarios")
        if sum((scenario.probability for scenario in self.scenarios), Decimal(0)) != Decimal(1):
            raise ValueError("Bear, Base and Bull probabilities must sum exactly to 1")
        for scenario in self.scenarios:
            if scenario.terminal_growth >= scenario.cost_of_equity:
                raise ValueError("Terminal growth must remain below cost of equity")
        return self


class FinancialModelRevisionCalculationPreviewCreate(DcfCalculationInput):
    base_revision_id: UUID


class FinancialModelInitialCalculationPreviewCreate(DcfCalculationInput):
    valuation_listing_id: UUID
    model_currency: Currency


class FinancialModelRevisionCreate(DcfCalculationInput):
    base_revision_id: UUID | None
    source_revision_id: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    actor: Actor
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def observed_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware effective timestamp")
        value = value.astimezone(UTC)
        if value > datetime.now(UTC):
            raise ValueError("Future-effective model revisions are not supported")
        return value


class FinancialModelCreate(Contract):
    model_type: Literal["UFCF_DCF_10Y_FADE"] = "UFCF_DCF_10Y_FADE"
    model_name: Annotated[str, Field(min_length=1, max_length=160)]
    valuation_listing_id: UUID
    model_currency: Currency
    source_model_key: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    initial_revision: FinancialModelRevisionCreate


class OwnerCashFlowRevisionCreate(OwnerCashFlowInput):
    base_revision_id: UUID | None
    source_revision_id: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    actor: Actor
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def observed_time(cls, value: datetime) -> datetime:
        return FinancialModelRevisionCreate.observed_time(value)


class ResidualIncomeRevisionCreate(ResidualIncomeInput):
    base_revision_id: UUID | None
    source_revision_id: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    actor: Actor
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def observed_time(cls, value: datetime) -> datetime:
        return FinancialModelRevisionCreate.observed_time(value)


class OwnerCashFlowInitialPreviewCreate(OwnerCashFlowInput):
    valuation_listing_id: UUID
    model_currency: Currency


class ResidualIncomeInitialPreviewCreate(ResidualIncomeInput):
    valuation_listing_id: UUID
    model_currency: Currency


class OwnerCashFlowRevisionPreviewCreate(OwnerCashFlowInput):
    base_revision_id: UUID


class ResidualIncomeRevisionPreviewCreate(ResidualIncomeInput):
    base_revision_id: UUID


class OwnerCashFlowModelCreate(Contract):
    model_name: Annotated[str, Field(min_length=1, max_length=160)]
    valuation_listing_id: UUID
    model_currency: Currency
    source_model_key: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    initial_revision: OwnerCashFlowRevisionCreate


class ResidualIncomeModelCreate(Contract):
    model_name: Annotated[str, Field(min_length=1, max_length=160)]
    valuation_listing_id: UUID
    model_currency: Currency
    source_model_key: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    initial_revision: ResidualIncomeRevisionCreate


class DcfOperatingBaseRead(DcfOperatingBase):
    pass


class DcfYearAssumptionRead(DcfYearAssumptionInput):
    id: UUID
    scenario_id: UUID


class DcfScenarioRead(Contract):
    id: UUID
    revision_id: UUID
    scenario: DcfScenario
    probability: Probability
    terminal_growth: ModelNumber
    year10_ufcf_growth: ModelNumber
    rationale: str
    years: list[DcfYearAssumptionRead]


class DcfProjectionRead(Contract):
    id: UUID
    scenario_id: UUID
    forecast_year: int
    revenue: ModelNumber | None
    ebit: ModelNumber | None
    nopat: ModelNumber | None
    depreciation_amortization: ModelNumber | None
    capex: ModelNumber | None
    net_working_capital: ModelNumber | None
    change_in_nwc: ModelNumber | None
    unlevered_free_cash_flow: ModelNumber
    revenue_growth: ModelNumber
    discount_rate: ModelNumber
    discount_factor: ModelNumber
    present_value_ufcf: ModelNumber
    terminal_value: ModelNumber | None


class DcfProjectionCalculationPreviewRead(Contract):
    scenario: DcfScenario
    forecast_year: int
    revenue: ModelNumber | None
    ebit: ModelNumber | None
    nopat: ModelNumber | None
    depreciation_amortization: ModelNumber | None
    capex: ModelNumber | None
    net_working_capital: ModelNumber | None
    change_in_nwc: ModelNumber | None
    unlevered_free_cash_flow: ModelNumber
    revenue_growth: ModelNumber
    discount_rate: ModelNumber
    discount_factor: ModelNumber
    present_value_ufcf: ModelNumber
    terminal_value: ModelNumber | None


class FinancialModelOutputsRead(Contract):
    id: UUID
    revision_id: UUID
    status: Literal["COMPLETE", "PARTIAL"]
    model_currency: Currency
    price_observation_id: UUID | None
    current_price: ModelNumber | None
    price_effective_at: datetime | None
    price_status: Literal[
        "FRESH",
        "STALE",
        "QUALITY_CHECK",
        "NO_DATA",
        "CURRENCY_MISMATCH",
        "CURRENCY_UNKNOWN",
    ]
    price_unavailable_reason: str | None
    irr_unavailable_reason: str | None
    bear_fv: ModelNumber
    base_fv: ModelNumber
    bull_fv: ModelNumber
    bear_probability: Probability
    base_probability: Probability
    bull_probability: Probability
    weighted_fv: ModelNumber
    weighted_upside: ModelNumber | None
    expected_cash_flow_irr: ModelNumber | None
    hurdle: ModelNumber
    expected_excess: ModelNumber | None
    forward_fundamental_cagr: ModelNumber | None


class FinancialModelCalculationOutputsRead(Contract):
    status: Literal["COMPLETE", "PARTIAL"]
    model_currency: Currency
    price_observation_id: UUID | None
    current_price: ModelNumber | None
    price_effective_at: datetime | None
    price_status: Literal[
        "FRESH",
        "STALE",
        "QUALITY_CHECK",
        "NO_DATA",
        "CURRENCY_MISMATCH",
        "CURRENCY_UNKNOWN",
    ]
    price_unavailable_reason: str | None
    irr_unavailable_reason: str | None
    bear_fv: ModelNumber
    base_fv: ModelNumber
    bull_fv: ModelNumber
    bear_probability: Probability
    base_probability: Probability
    bull_probability: Probability
    weighted_fv: ModelNumber
    weighted_upside: ModelNumber | None
    expected_cash_flow_irr: ModelNumber | None
    hurdle: ModelNumber
    expected_excess: ModelNumber | None
    forward_fundamental_cagr: ModelNumber | None


class FinancialModelCalculationPreviewRead(Contract):
    model_id: UUID | None
    base_revision_id: UUID | None
    current_revision_id: UUID | None
    current_revision_number: int | None
    model_currency: Currency
    outputs: FinancialModelCalculationOutputsRead
    projections: list[DcfProjectionCalculationPreviewRead] = Field(min_length=30, max_length=30)


class FinancialModelRevisionSummary(Contract):
    id: UUID
    model_id: UUID
    revision_number: int
    base_revision_id: UUID | None
    methodology_version: str
    source_revision_id: str | None
    actor: Actor
    source: str | None
    rationale: str
    effective_at: datetime
    recorded_at: datetime
    outputs: FinancialModelOutputsRead


class FinancialModelRevisionRead(FinancialModelRevisionSummary):
    base: DcfOperatingBaseRead
    scenarios: list[DcfScenarioRead]
    projections: list[DcfProjectionRead]


class FinancialModelRead(Contract):
    id: UUID
    company_id: UUID
    model_type: FinancialModelType
    model_name: str
    valuation_listing: ListingRead
    model_currency: Currency
    source_model_key: str | None
    created_at: datetime
    current_revision_id: UUID
    current_revision: FinancialModelRevisionRead
    history: list[FinancialModelRevisionSummary]


class OwnerCashFlowProjectionRead(Contract):
    scenario: DcfScenario
    forecast_year: int
    revenue: ModelNumber
    owner_cash_flow: ModelNumber
    owner_cash_flow_per_share: ModelNumber
    present_value_per_share: ModelNumber
    terminal_value_per_share: ModelNumber | None


class ResidualIncomeProjectionRead(Contract):
    scenario: DcfScenario
    forecast_year: int
    beginning_book_value_per_share: ModelNumber
    return_on_equity: ModelNumber
    net_income_per_share: ModelNumber
    dividend_per_share: ModelNumber
    ending_book_value_per_share: ModelNumber
    residual_income_per_share: ModelNumber
    present_value_residual_income: ModelNumber
    terminal_value_per_share: ModelNumber | None


class OwnerCashFlowRevisionRead(FinancialModelRevisionSummary):
    base: OwnerCashFlowBase
    scenarios: list[OwnerCashFlowScenarioInput]
    projections: list[OwnerCashFlowProjectionRead]


class ResidualIncomeRevisionRead(FinancialModelRevisionSummary):
    base: ResidualIncomeBase
    scenarios: list[ResidualIncomeScenarioInput]
    projections: list[ResidualIncomeProjectionRead]


class ExtendedFinancialModelRead(Contract):
    id: UUID
    company_id: UUID
    model_type: Literal["OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"]
    model_name: str
    valuation_listing: ListingRead
    model_currency: Currency
    source_model_key: str | None
    created_at: datetime
    current_revision_id: UUID
    current_revision: OwnerCashFlowRevisionRead | ResidualIncomeRevisionRead
    history: list[FinancialModelRevisionSummary]


class AdditionalModelContractCandidate(Contract):
    source_revision_id: Annotated[str, Field(min_length=1, max_length=160)]
    actor: Literal["IMPORT"] = "IMPORT"
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    rationale: Annotated[str, Field(max_length=4000)] | None = None
    effective_at: datetime
    owner_cash_flow: OwnerCashFlowInput | None = None
    residual_income: ResidualIncomeInput | None = None

    @model_validator(mode="after")
    def one_method_input(self) -> Self:
        if (self.owner_cash_flow is None) == (self.residual_income is None):
            raise ValueError("Provide exactly one method-specific input block")
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("Use a timezone-aware effective timestamp")
        if self.effective_at > datetime.now(UTC):
            raise ValueError("Future-effective model revisions are not supported")
        return self


class AdditionalModelPortableContractV2(Contract):
    contract_version: Literal["2.0.0"] = "2.0.0"
    exported_at: datetime
    model_id: UUID
    company_id: UUID
    model_type: Literal["OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"]
    model_name: str
    valuation_listing_id: UUID
    model_currency: Currency
    source_model_key: str | None
    base_revision_id: UUID
    base_revision_number: Annotated[int, Field(gt=0)]
    candidate_revision: AdditionalModelContractCandidate

    @model_validator(mode="after")
    def contract_method_matches_input(self) -> Self:
        if self.model_type == "OWNER_CASH_FLOW_10Y":
            if self.candidate_revision.owner_cash_flow is None:
                raise ValueError("Owner cash-flow contract requires owner_cash_flow inputs")
            if self.candidate_revision.residual_income is not None:
                raise ValueError("Owner cash-flow contract cannot include residual_income inputs")
        else:
            if self.candidate_revision.residual_income is None:
                raise ValueError("Residual-income contract requires residual_income inputs")
            if self.candidate_revision.owner_cash_flow is not None:
                raise ValueError("Residual-income contract cannot include owner_cash_flow inputs")
        if self.exported_at.tzinfo is None or self.exported_at.utcoffset() is None:
            raise ValueError("Use a timezone-aware export timestamp")
        return self


class AdditionalModelContractFieldChange(Contract):
    path: str
    previous: str | None
    proposed: str | None


class AdditionalModelContractPreviewRead(Contract):
    status: Literal["READY", "NO_CHANGES", "RATIONALE_REQUIRED", "CONFLICT", "ALREADY_IMPORTED"]
    model_id: UUID
    base_revision_id: UUID
    current_revision_id: UUID
    current_revision_number: int
    source_revision_id: str
    changes: list[AdditionalModelContractFieldChange]
    output_changes: list[AdditionalModelContractFieldChange]
    current_outputs: FinancialModelCalculationOutputsRead
    calculated_outputs: FinancialModelCalculationOutputsRead | None
    reason: str | None


class AdditionalModelContractImportRead(Contract):
    status: Literal["IMPORTED", "ALREADY_IMPORTED"]
    model: ExtendedFinancialModelRead
    revision: OwnerCashFlowRevisionRead | ResidualIncomeRevisionRead


class OwnerCashFlowCalculationPreviewRead(Contract):
    model_id: UUID | None
    base_revision_id: UUID | None
    current_revision_id: UUID | None
    current_revision_number: int | None
    model_currency: Currency
    outputs: FinancialModelCalculationOutputsRead
    projections: list[OwnerCashFlowProjectionRead]


class ResidualIncomeCalculationPreviewRead(Contract):
    model_id: UUID | None
    base_revision_id: UUID | None
    current_revision_id: UUID | None
    current_revision_number: int | None
    model_currency: Currency
    outputs: FinancialModelCalculationOutputsRead
    projections: list[ResidualIncomeProjectionRead]


class FinancialModelContractIdentity(Contract):
    model_id: UUID
    company_id: UUID
    model_type: FinancialModelType
    model_name: str
    valuation_listing_id: UUID
    valuation_listing: ListingRead
    model_currency: Currency
    source_model_key: str | None


class FinancialModelContractBaseRevision(Contract):
    revision_id: UUID
    revision_number: Annotated[int, Field(gt=0)]
    methodology_version: Literal["ufcf-dcf-fade-v1"]


class FinancialModelContractCandidateRevision(Contract):
    source_revision_id: Annotated[str, Field(min_length=1, max_length=160)]
    actor: Literal["IMPORT"] = "IMPORT"
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    rationale: Annotated[str, Field(min_length=1, max_length=4000)]
    effective_at: datetime
    base: DcfOperatingBase
    scenarios: list[DcfScenarioInput] = Field(min_length=3, max_length=3)

    @field_validator("effective_at")
    @classmethod
    def effective_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware effective timestamp")
        value = value.astimezone(UTC)
        if value > datetime.now(UTC):
            raise ValueError("Future-effective model revisions are not supported")
        return value


class FinancialModelContractCalculation(Contract):
    revision_id: UUID
    outputs: FinancialModelOutputsRead
    projections: list[DcfProjectionRead] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def revision_links_match(self) -> Self:
        if self.outputs.revision_id != self.revision_id:
            raise ValueError("Contract calculation outputs must belong to its revision")
        if len({row.scenario_id for row in self.projections}) != 3:
            raise ValueError("Contract calculation requires all three scenarios")
        return self


class FinancialModelContractV1(Contract):
    contract_version: Literal["1.0.0"]
    exported_at: datetime
    model: FinancialModelContractIdentity
    base_revision: FinancialModelContractBaseRevision
    candidate_revision: FinancialModelContractCandidateRevision
    base_calculation: FinancialModelContractCalculation

    @field_validator("exported_at")
    @classmethod
    def exported_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware contract export timestamp")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def contract_revision_links_match(self) -> Self:
        if self.base_calculation.revision_id != self.base_revision.revision_id:
            raise ValueError("Base calculation must match the exported base revision")
        if self.base_calculation.outputs.model_currency != self.model.model_currency:
            raise ValueError("Base calculation currency must match the model currency")
        FinancialModelRevisionCreate.model_validate(
            {
                "base_revision_id": self.base_revision.revision_id,
                **self.candidate_revision.model_dump(),
            }
        )
        return self


class FinancialModelContractOutputSummary(Contract):
    status: Literal["COMPLETE", "PARTIAL"]
    model_currency: Currency
    price_status: Literal[
        "FRESH",
        "STALE",
        "QUALITY_CHECK",
        "NO_DATA",
        "CURRENCY_MISMATCH",
        "CURRENCY_UNKNOWN",
    ]
    current_price: ModelNumber | None
    price_effective_at: datetime | None
    price_unavailable_reason: str | None
    bear_fv: ModelNumber
    base_fv: ModelNumber
    bull_fv: ModelNumber
    weighted_fv: ModelNumber
    weighted_upside: ModelNumber | None
    expected_cash_flow_irr: ModelNumber | None
    hurdle: ModelNumber
    expected_excess: ModelNumber | None
    irr_unavailable_reason: str | None


class FinancialModelContractFieldChange(Contract):
    path: str
    previous: str | None
    proposed: str | None


class FinancialModelContractPreviewRead(Contract):
    status: Literal[
        "READY",
        "NO_CHANGES",
        "RATIONALE_REQUIRED",
        "CONFLICT",
        "INVALID_BASE_SNAPSHOT",
        "ALREADY_IMPORTED",
    ]
    model_id: UUID
    base_revision_id: UUID
    current_revision_id: UUID
    current_revision_number: int
    source_revision_id: Annotated[str, Field(min_length=1, max_length=160)]
    actor: Literal["IMPORT"] = "IMPORT"
    source: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    effective_at: datetime
    proposed_revision_number: int | None
    already_imported_revision_id: UUID | None
    reason: str | None
    changes: list[FinancialModelContractFieldChange]
    output_changes: list[FinancialModelContractFieldChange]
    current_outputs: FinancialModelContractOutputSummary
    calculated_outputs: FinancialModelContractOutputSummary | None


class FinancialModelContractImportRead(Contract):
    status: Literal["IMPORTED", "ALREADY_IMPORTED"]
    model: FinancialModelRead
    revision: FinancialModelRevisionRead
