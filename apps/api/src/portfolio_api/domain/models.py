"""Relational state plus domain-specific immutable history; no investment models."""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from portfolio_api.database import Base
from portfolio_api.return_semantics import (
    DEFINITION_ID_BY_CODE,
    native_methodology_for_revision,
)


def now() -> datetime:
    return datetime.now(UTC)


class Lifecycle(StrEnum):
    PORTFOLIO = "PORTFOLIO"
    WATCHLIST = "WATCHLIST"
    CANDIDATE = "CANDIDATE"
    DROP = "DROP"


class Actor(StrEnum):
    LOCAL_USER = "LOCAL_USER"
    SYSTEM = "SYSTEM"
    IMPORT = "IMPORT"


class ScoreDimension(StrEnum):
    DURABILITY_10Y = "DURABILITY_10Y"
    COMPOUNDER_QUALITY = "COMPOUNDER_QUALITY"
    EXECUTION = "EXECUTION"
    RISK = "RISK"


class ResearchCandidateTier(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class CandidateResearchStage(StrEnum):
    DISCOVERY = "DISCOVERY"
    INITIAL_SCREEN = "INITIAL_SCREEN"
    QUALITY_DURABILITY = "QUALITY_DURABILITY"
    FUNDAMENTAL_COMPOUNDING = "FUNDAMENTAL_COMPOUNDING"
    DEEP_DIVE = "DEEP_DIVE"
    RESOLUTION = "RESOLUTION"


class CandidateGateOutcome(StrEnum):
    NOT_ASSESSED = "NOT_ASSESSED"
    INCOMPLETE = "INCOMPLETE"
    PASS = "PASS"
    FAIL = "FAIL"
    DATA_CHECK = "DATA_CHECK"


class CandidateResearchDisposition(StrEnum):
    WATCHLIST = "WATCHLIST"
    INCUBATE = "INCUBATE"
    DROP = "DROP"


class CandidateGateEvidenceType(StrEnum):
    RESEARCH_REVISION = "RESEARCH_REVISION"
    THESIS_REVISION = "THESIS_REVISION"
    THESIS_CLAIM = "THESIS_CLAIM"
    SCORE_ASSESSMENT = "SCORE_ASSESSMENT"
    FINANCIAL_MODEL_OUTPUT = "FINANCIAL_MODEL_OUTPUT"
    LEGACY_MODEL_OUTPUT = "LEGACY_MODEL_OUTPUT"
    SOURCE_DOCUMENT = "SOURCE_DOCUMENT"
    SOURCE_URL = "SOURCE_URL"


class ResearchForecastMetric(StrEnum):
    REVENUE = "REVENUE"
    EPS = "EPS"
    EBIT = "EBIT"
    EBITDA = "EBITDA"
    FREE_CASH_FLOW = "FREE_CASH_FLOW"
    DILUTED_SHARES = "DILUTED_SHARES"


class ResearchPeriodType(StrEnum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"


class ResearchScenario(StrEnum):
    POINT = "POINT"
    BEAR = "BEAR"
    BASE = "BASE"
    BULL = "BULL"


class ResearchObservationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DATA_CHECK = "DATA_CHECK"


class ResearchConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNASSESSED = "UNASSESSED"


class ResearchRevisionStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class ResearchQueueTaskType(StrEnum):
    CANDIDATE_STAGE = "CANDIDATE_STAGE"
    THESIS_REVIEW = "THESIS_REVIEW"
    THESIS_QUESTION = "THESIS_QUESTION"
    MATERIAL_EVIDENCE = "MATERIAL_EVIDENCE"
    RESEARCH_TRIGGER = "RESEARCH_TRIGGER"
    MODEL_REUNDERWRITE = "MODEL_REUNDERWRITE"
    MODEL_INTEGRITY = "MODEL_INTEGRITY"
    WATCHLIST_READINESS = "WATCHLIST_READINESS"
    STRUCTURAL_RISK = "STRUCTURAL_RISK"


class ThesisRevisionStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class ThesisClaimType(StrEnum):
    COMPETITIVE_ADVANTAGE = "COMPETITIVE_ADVANTAGE"
    DURABILITY = "DURABILITY"
    GROWTH_DRIVER = "GROWTH_DRIVER"
    PRINCIPAL_RISK = "PRINCIPAL_RISK"
    THESIS_BREAKER = "THESIS_BREAKER"
    CATALYST = "CATALYST"
    IMPORTANT_DEVELOPMENT = "IMPORTANT_DEVELOPMENT"
    UNRESOLVED_QUESTION = "UNRESOLVED_QUESTION"


class ThesisClaimStatus(StrEnum):
    ACTIVE = "ACTIVE"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    INVALIDATED = "INVALIDATED"


class ThesisEvidenceRelationship(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXT = "CONTEXT"


class ModelEvidenceRelationship(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXT = "CONTEXT"


class ModelEvidenceType(StrEnum):
    RESEARCH_REVISION = "RESEARCH_REVISION"
    RESEARCH_FORECAST = "RESEARCH_FORECAST"
    THESIS_REVISION = "THESIS_REVISION"
    THESIS_CLAIM = "THESIS_CLAIM"


class ResearchAssessmentType(StrEnum):
    BUSINESS_OUTLOOK = "BUSINESS_OUTLOOK"
    COMPETITIVE_POSITION = "COMPETITIVE_POSITION"
    KEY_RISKS = "KEY_RISKS"


class ResearchAssessmentStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DATA_CHECK = "DATA_CHECK"


class FundamentalMetric(StrEnum):
    REVENUE = "REVENUE"
    GROSS_PROFIT = "GROSS_PROFIT"
    OPERATING_INCOME = "OPERATING_INCOME"
    NET_INCOME = "NET_INCOME"
    CASH_AND_CASH_EQUIVALENTS = "CASH_AND_CASH_EQUIVALENTS"
    CURRENT_DEBT = "CURRENT_DEBT"
    NONCURRENT_DEBT = "NONCURRENT_DEBT"
    OPERATING_CASH_FLOW = "OPERATING_CASH_FLOW"
    CAPITAL_EXPENDITURES = "CAPITAL_EXPENDITURES"
    DILUTED_WEIGHTED_AVERAGE_SHARES = "DILUTED_WEIGHTED_AVERAGE_SHARES"


class FundamentalStatement(StrEnum):
    INCOME_STATEMENT = "INCOME_STATEMENT"
    BALANCE_SHEET = "BALANCE_SHEET"
    CASH_FLOW_STATEMENT = "CASH_FLOW_STATEMENT"


class FundamentalPeriodType(StrEnum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"
    INSTANT = "INSTANT"


class FundamentalRevisionContext(StrEnum):
    ORIGINAL = "ORIGINAL"
    COMPARATIVE_REPORTED = "COMPARATIVE_REPORTED"
    POTENTIAL_RESTATEMENT = "POTENTIAL_RESTATEMENT"
    AMENDED_FILING = "AMENDED_FILING"


class FundamentalDataQuality(StrEnum):
    PASS = "PASS"
    DATA_CHECK = "DATA_CHECK"
    INVALID = "INVALID"


class SourceDocumentType(StrEnum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    EIGHT_K = "8-K"
    TWENTY_F = "20-F"
    SIX_K = "6-K"
    ANNUAL_REPORT = "ANNUAL_REPORT"
    EARNINGS_RELEASE = "EARNINGS_RELEASE"
    OTHER = "OTHER"


class SourceDocumentQuality(StrEnum):
    PASS = "PASS"
    DATA_CHECK = "DATA_CHECK"


class ConsensusEstimateMetric(StrEnum):
    REVENUE = "REVENUE"
    EPS = "EPS"


class ForecastAccuracyMetric(StrEnum):
    REVENUE = "REVENUE"
    EPS = "EPS"
    EBIT = "EBIT"
    EBITDA = "EBITDA"
    FREE_CASH_FLOW = "FREE_CASH_FLOW"


class ForecastAccuracySourceType(StrEnum):
    AGENT_RESEARCH = "AGENT_RESEARCH"
    FINANCIAL_MODEL = "FINANCIAL_MODEL"
    ANALYST_CONSENSUS = "ANALYST_CONSENSUS"


class ConsensusEstimatePeriodType(StrEnum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"


class ConsensusEstimateSourceRole(StrEnum):
    PRIMARY = "PRIMARY"
    FALLBACK = "FALLBACK"


class ConsensusEstimateDataQuality(StrEnum):
    PASS = "PASS"
    DATA_CHECK = "DATA_CHECK"
    INVALID = "INVALID"


class ConsensusEstimateRevisionContext(StrEnum):
    SNAPSHOT = "SNAPSHOT"
    REVISED = "REVISED"
    LEGACY_BASELINE = "LEGACY_BASELINE"


class ScoreDirectionality(StrEnum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    HIGHER_IS_RISK = "HIGHER_IS_RISK"


class ScoreDefinitionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ScoreAssessmentStatus(StrEnum):
    ASSESSED = "ASSESSED"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class RankingType(StrEnum):
    PORTFOLIO = "PORTFOLIO"
    WATCHLIST = "WATCHLIST"
    RESEARCH = "RESEARCH"


class RankingDefinitionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class RankingImplementationStatus(StrEnum):
    NOT_MIGRATED = "NOT_MIGRATED"
    PARTIAL = "PARTIAL"
    READY = "READY"


class RankingRunStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class RankingEntryStatus(StrEnum):
    RANKED = "RANKED"
    INPUTS_UNAVAILABLE = "INPUTS_UNAVAILABLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    EXCLUDED = "EXCLUDED"
    NOT_MIGRATED = "NOT_MIGRATED"
    DATA_CHECK = "DATA_CHECK"


class ExecutionPaceRunStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ExecutionPaceDecisionStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    REVIEW = "REVIEW"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ExecutionPace(StrEnum):
    ACCELERATE = "ACCELERATE"
    BUILD = "BUILD"
    NORMAL_BUILD = "NORMAL_BUILD"
    SMALL_LADDER = "SMALL_LADDER"
    LADDER = "LADDER"
    HOLD = "HOLD"
    SLOW_LIMIT = "SLOW_LIMIT"
    WAIT_LIMIT = "WAIT_LIMIT"
    PATIENT_TRIM = "PATIENT_TRIM"
    TRIM_FASTER = "TRIM_FASTER"
    NORMAL_TRIM = "NORMAL_TRIM"
    PATIENT_EXIT = "PATIENT_EXIT"
    NORMAL_EXIT = "NORMAL_EXIT"


class ModelOutputSnapshotKind(StrEnum):
    CURRENT_CONTRACT = "CURRENT_CONTRACT"
    LEGACY_REVISION = "LEGACY_REVISION"


class ModelOutputContractStatus(StrEnum):
    PASS = "PASS"
    NOT_MAPPED = "NOT_MAPPED"
    NO_CONTRACT = "NO_CONTRACT"
    DATA_CHECK = "DATA_CHECK"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"


class ModelOutputQuality(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    DATA_CHECK = "DATA_CHECK"
    UNAVAILABLE = "UNAVAILABLE"


class FinancialModelType(StrEnum):
    UFCF_DCF_10Y_FADE = "UFCF_DCF_10Y_FADE"
    OWNER_CASH_FLOW_10Y = "OWNER_CASH_FLOW_10Y"
    RESIDUAL_INCOME_10Y_FADE = "RESIDUAL_INCOME_10Y_FADE"


class FinancialModelMigrationStatus(StrEnum):
    PARITY_PASS = "PARITY_PASS"
    PARTIAL_MAPPING = "PARTIAL_MAPPING"
    DATA_CHECK = "DATA_CHECK"
    BLOCKED = "BLOCKED"


class DcfScenario(StrEnum):
    BEAR = "BEAR"
    BASE = "BASE"
    BULL = "BULL"


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Audit:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str | None] = mapped_column(String(1000))


class Company(Identity, Base):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(200))
    reporting_currency: Mapped[str | None] = mapped_column(String(3))


class Security(Identity, Base):
    __tablename__ = "securities"
    __table_args__ = (
        CheckConstraint(
            "security_type IN ('COMMON_STOCK', 'ADR', 'PREFERRED', 'ETF')", name="type"
        ),
        CheckConstraint(
            "(security_type = 'ETF' AND company_id IS NULL) OR "
            "(security_type <> 'ETF' AND company_id IS NOT NULL)",
            name="issuer",
        ),
        CheckConstraint(
            "underlying_security_id IS NULL OR underlying_security_id <> id", name="underlying"
        ),
    )
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    security_type: Mapped[str] = mapped_column(String(32))
    share_class: Mapped[str | None] = mapped_column(String(80))
    underlying_security_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT")
    )


class Listing(Identity, Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("venue", "ticker"),)
    security_id: Mapped[UUID] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), index=True
    )
    venue: Mapped[str] = mapped_column(String(80))
    ticker: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(3))
    identity_source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)


class LifecycleEvent(Audit, Base):
    __tablename__ = "lifecycle_events"
    __table_args__ = (
        UniqueConstraint("company_id", "sequence"),
        UniqueConstraint("company_id", "id", name="uq_lifecycle_events_company_event"),
        CheckConstraint("sequence > 0", name="sequence"),
        CheckConstraint(
            "new_state IN ('PORTFOLIO','WATCHLIST','CANDIDATE','DROP')", name="new_state"
        ),
        CheckConstraint(
            "previous_state IS NULL OR "
            "previous_state IN ('PORTFOLIO','WATCHLIST','CANDIDATE','DROP')",
            name="previous_state",
        ),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    previous_state: Mapped[str | None] = mapped_column(String(16))
    new_state: Mapped[str] = mapped_column(String(16))


class CurrentLifecycle(Base):
    __tablename__ = "company_lifecycle_current"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "event_id"],
            ["lifecycle_events.company_id", "lifecycle_events.id"],
            ondelete="RESTRICT",
        ),
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(unique=True)


class Portfolio(Identity, Base):
    __tablename__ = "portfolios"
    name: Mapped[str] = mapped_column(String(200))
    base_currency: Mapped[str] = mapped_column(String(3))


class HoldingSnapshot(Audit, Base):
    __tablename__ = "holding_snapshots"
    __table_args__ = (
        CheckConstraint(
            "completeness IN ('COMPLETE','PARTIAL','UNAVAILABLE')", name="completeness"
        ),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        UniqueConstraint("portfolio_id", "effective_at"),
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), index=True
    )
    completeness: Mapped[str] = mapped_column(String(16))


class HoldingPosition(Base):
    __tablename__ = "holding_positions"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "listing_id"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("holding_snapshots.id", ondelete="RESTRICT"), index=True
    )
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("listings.id", ondelete="RESTRICT"))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))


class CashPosition(Base):
    __tablename__ = "holding_cash_positions"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "currency"),
        CheckConstraint("balance IS NULL OR balance >= 0", name="balance"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("holding_snapshots.id", ondelete="RESTRICT"), index=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    balance: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))


class TargetRevision(Audit, Base):
    __tablename__ = "target_allocation_revisions"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','ACCEPTED')", name="status"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        CheckConstraint(
            "(status = 'DRAFT' AND accepted_at IS NULL) OR "
            "(status = 'ACCEPTED' AND accepted_at IS NOT NULL)",
            name="acceptance",
        ),
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TargetAllocation(Base):
    __tablename__ = "target_allocations"
    __table_args__ = (
        UniqueConstraint("revision_id", "company_id"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="weight"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("target_allocation_revisions.id", ondelete="RESTRICT"), index=True
    )
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    weight: Mapped[Decimal] = mapped_column(Numeric(18, 12))


class ScoreDefinition(Base):
    """Versioned metadata for one of the four explicit current score dimensions."""

    __tablename__ = "score_definitions"
    __table_args__ = (
        UniqueConstraint("dimension", "version"),
        CheckConstraint(
            "dimension IN ('DURABILITY_10Y','COMPOUNDER_QUALITY','EXECUTION','RISK')",
            name="dimension",
        ),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("minimum_score >= 0 AND minimum_score <= maximum_score", name="scale"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="status"),
        CheckConstraint(
            "directionality IN ('HIGHER_IS_BETTER','HIGHER_IS_RISK')", name="directionality"
        ),
        Index(
            "uq_score_definitions_one_active_per_dimension",
            "dimension",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dimension: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    minimum_score: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    maximum_score: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    directionality: Mapped[str] = mapped_column(String(24))
    units: Mapped[str] = mapped_column(String(80))
    methodology: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default=ScoreDefinitionStatus.ACTIVE)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ScoreAssessment(Base):
    """Append-only authored observation; corrections point at the prior observation."""

    __tablename__ = "score_assessments"
    __table_args__ = (
        CheckConstraint("status IN ('ASSESSED','MISSING','UNAVAILABLE','INVALID')", name="status"),
        CheckConstraint(
            "(status = 'ASSESSED' AND score IS NOT NULL) OR "
            "(status <> 'ASSESSED' AND score IS NULL)",
            name="score_status",
        ),
        CheckConstraint("score IS NULL OR score >= 0 AND score <= 5", name="score_range"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    score_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("score_definitions.id", ondelete="RESTRICT"), index=True
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    status: Mapped[str] = mapped_column(String(20))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    rationale: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(32))
    source: Mapped[str | None] = mapped_column(String(1000))
    superseded_assessment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("score_assessments.id", ondelete="RESTRICT"), unique=True
    )


class RankingDefinition(Base):
    """Versioned metadata for one of the three deliberately distinct ranking types."""

    __tablename__ = "ranking_definitions"
    __table_args__ = (
        UniqueConstraint("ranking_type", "version"),
        CheckConstraint(
            "ranking_type IN ('PORTFOLIO','WATCHLIST','RESEARCH')", name="ranking_type"
        ),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="status"),
        CheckConstraint(
            "implementation_status IN ('NOT_MIGRATED','PARTIAL','READY')",
            name="implementation_status",
        ),
        Index(
            "uq_ranking_definitions_one_active_per_type",
            "ranking_type",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ranking_type: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    methodology: Mapped[str] = mapped_column(Text)
    population_rule: Mapped[str] = mapped_column(Text)
    required_inputs: Mapped[str] = mapped_column(Text)
    source_reference: Mapped[str] = mapped_column(String(500))
    implementation_status: Mapped[str] = mapped_column(String(24))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default=RankingDefinitionStatus.ACTIVE)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RankingRun(Base):
    """Append-only snapshot of one type's ranking availability and outcomes."""

    __tablename__ = "ranking_runs"
    __table_args__ = (
        CheckConstraint("status IN ('COMPLETE','PARTIAL','UNAVAILABLE')", name="status"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("ranking_definitions.id", ondelete="RESTRICT"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str | None] = mapped_column(String(1000))


class RankingEntry(Base):
    """Company-level result or explicit non-result captured in a particular run."""

    __tablename__ = "ranking_entries"
    __table_args__ = (
        UniqueConstraint("run_id", "company_id", name="uq_ranking_entries_run_company"),
        UniqueConstraint("run_id", "position", name="uq_ranking_entries_run_position"),
        CheckConstraint(
            "status IN ('RANKED','INPUTS_UNAVAILABLE','NOT_ELIGIBLE','EXCLUDED',"
            "'NOT_MIGRATED','DATA_CHECK')",
            name="status",
        ),
        CheckConstraint(
            "(status = 'RANKED' AND position IS NOT NULL AND position > 0) OR "
            "(status <> 'RANKED' AND position IS NULL)",
            name="position_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ranking_runs.id", ondelete="RESTRICT"), index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(1000))
    input_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class ResearchPriorityInput(Base):
    """Imported source inputs for the workbook's candidate-only Research Sort Key."""

    __tablename__ = "research_priority_inputs"
    __table_args__ = (
        UniqueConstraint("company_id", "source_digest"),
        CheckConstraint("candidate_tier IN ('HIGH','LOW')", name="candidate_tier"),
        CheckConstraint("priority_seed IS NULL OR priority_seed >= 0", name="priority_seed"),
        CheckConstraint("input_quality IN ('PASS','DATA_CHECK')", name="input_quality"),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    canonical_ticker: Mapped[str] = mapped_column(String(40))
    candidate_tier: Mapped[str] = mapped_column(String(8))
    priority_seed: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    input_quality: Mapped[str] = mapped_column(String(16), default="PASS")
    quality_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_digest: Mapped[str] = mapped_column(String(64))
    bucket_source_ref: Mapped[str] = mapped_column(String(500))
    priority_seed_source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(32), default=Actor.IMPORT)


class CandidatePipelineRevision(Base):
    """An immutable, complete Candidate research-pipeline state snapshot."""

    __tablename__ = "candidate_pipeline_revisions"
    __table_args__ = (
        UniqueConstraint("company_id", "revision_number", name="uq_candidate_pipeline_revision"),
        UniqueConstraint("company_id", "submission_id", name="uq_candidate_pipeline_submission"),
        UniqueConstraint("company_id", "id", name="uq_candidate_pipeline_company_revision"),
        ForeignKeyConstraint(
            ["company_id", "base_revision_id"],
            ["candidate_pipeline_revisions.company_id", "candidate_pipeline_revisions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision_number > 0", name="revision_number"),
        CheckConstraint(
            "stage IN ('DISCOVERY','INITIAL_SCREEN','QUALITY_DURABILITY',"
            "'FUNDAMENTAL_COMPOUNDING','DEEP_DIVE','RESOLUTION')",
            name="stage",
        ),
        CheckConstraint(
            "disposition IS NULL OR disposition IN ('WATCHLIST','INCUBATE','DROP')",
            name="disposition",
        ),
        CheckConstraint(
            "disposition IS NULL OR disposition = 'DROP' OR stage = 'RESOLUTION'",
            name="disposition_requires_resolution",
        ),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        CheckConstraint("length(author_id) > 0", name="author_id"),
        CheckConstraint("length(rationale) > 0", name="rationale"),
        CheckConstraint("length(content_fingerprint) = 64", name="content_fingerprint"),
        Index("ix_candidate_pipeline_revisions_company_recorded", "company_id", "recorded_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    base_revision_id: Mapped[UUID | None] = mapped_column(nullable=True)
    submission_id: Mapped[UUID] = mapped_column()
    stage: Mapped[str] = mapped_column(String(32))
    disposition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    unresolved_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    actor: Mapped[str] = mapped_column(String(32), default=Actor.LOCAL_USER)
    author_id: Mapped[str] = mapped_column(String(160))
    source: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    rationale: Mapped[str] = mapped_column(Text)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class CandidatePipelineGateAssessment(Base):
    """One gate state copied into an immutable Candidate pipeline revision."""

    __tablename__ = "candidate_pipeline_gate_assessments"
    __table_args__ = (
        UniqueConstraint("revision_id", "gate", name="uq_candidate_pipeline_revision_gate"),
        CheckConstraint(
            "gate IN ('DISCOVERY','INITIAL_SCREEN','QUALITY_DURABILITY',"
            "'FUNDAMENTAL_COMPOUNDING','DEEP_DIVE')",
            name="gate",
        ),
        CheckConstraint(
            "outcome IN ('NOT_ASSESSED','INCOMPLETE','PASS','FAIL','DATA_CHECK')",
            name="outcome",
        ),
        CheckConstraint(
            "NOT normalized_per_share_basis_confirmed OR gate = 'FUNDAMENTAL_COMPOUNDING'",
            name="per_share_basis_gate",
        ),
        CheckConstraint(
            "outcome <> 'PASS' OR coalesce(length(rationale), 0) > 0",
            name="pass_rationale",
        ),
        Index("ix_candidate_gate_revision", "revision_id", "gate"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_pipeline_revisions.id", ondelete="RESTRICT"), index=True
    )
    gate: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_per_share_basis_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class CandidatePipelineEvidence(Base):
    """A typed link from a gate assessment to existing canonical evidence."""

    __tablename__ = "candidate_pipeline_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('RESEARCH_REVISION','THESIS_REVISION','THESIS_CLAIM',"
            "'SCORE_ASSESSMENT','FINANCIAL_MODEL_OUTPUT','LEGACY_MODEL_OUTPUT',"
            "'SOURCE_DOCUMENT','SOURCE_URL')",
            name="evidence_type",
        ),
        CheckConstraint(
            "num_nonnulls(research_revision_id, thesis_revision_id, thesis_claim_id, "
            "score_assessment_id, financial_model_output_id, model_output_snapshot_id, "
            "source_document_id, source_url) = 1",
            name="one_reference",
        ),
        CheckConstraint(
            "(evidence_type = 'RESEARCH_REVISION' AND research_revision_id IS NOT NULL) OR "
            "(evidence_type = 'THESIS_REVISION' AND thesis_revision_id IS NOT NULL) OR "
            "(evidence_type = 'THESIS_CLAIM' AND thesis_claim_id IS NOT NULL) OR "
            "(evidence_type = 'SCORE_ASSESSMENT' AND score_assessment_id IS NOT NULL) OR "
            "(evidence_type = 'FINANCIAL_MODEL_OUTPUT' AND "
            "financial_model_output_id IS NOT NULL) OR "
            "(evidence_type = 'LEGACY_MODEL_OUTPUT' AND model_output_snapshot_id IS NOT NULL) OR "
            "(evidence_type = 'SOURCE_DOCUMENT' AND source_document_id IS NOT NULL) OR "
            "(evidence_type = 'SOURCE_URL' AND source_url IS NOT NULL)",
            name="evidence_identity",
        ),
        CheckConstraint(
            "source_url IS NULL OR source_url LIKE 'https://%'",
            name="https_url",
        ),
        CheckConstraint(
            "relationship IN ('SUPPORTS','CONTRADICTS','CONTEXT')",
            name="relationship",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    gate_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_pipeline_gate_assessments.id", ondelete="RESTRICT"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(32))
    research_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    thesis_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    thesis_claim_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_claims.id", ondelete="RESTRICT"), nullable=True
    )
    score_assessment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("score_assessments.id", ondelete="RESTRICT"), nullable=True
    )
    financial_model_output_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("financial_model_outputs.id", ondelete="RESTRICT"), nullable=True
    )
    model_output_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_output_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    relationship: Mapped[str] = mapped_column(String(16), default="SUPPORTS")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchRevision(Base):
    """One immutable, externally authored company research publication."""

    __tablename__ = "research_revisions"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "stream_key", "revision_number", name="uq_research_stream_revision"
        ),
        UniqueConstraint(
            "company_id",
            "stream_key",
            "external_revision_id",
            name="uq_research_stream_external_revision",
        ),
        CheckConstraint("revision_number > 0", name="revision_number"),
        CheckConstraint("length(stream_key) > 0", name="stream_key"),
        CheckConstraint("length(external_revision_id) > 0", name="external_revision_id"),
        CheckConstraint("length(author_id) > 0", name="author_id"),
        CheckConstraint("length(source_id) > 0", name="source_id"),
        CheckConstraint("length(source_reference) > 0", name="source_reference"),
        CheckConstraint("length(rationale) > 0", name="rationale"),
        CheckConstraint("status IN ('PUBLISHED','WITHDRAWN')", name="status"),
        CheckConstraint("length(content_fingerprint) = 64", name="content_fingerprint"),
        Index("ix_research_revisions_company_observed", "company_id", "observed_at"),
        Index(
            "ix_research_revisions_company_stream", "company_id", "stream_key", "revision_number"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    security_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    stream_key: Mapped[str] = mapped_column(String(240))
    revision_number: Mapped[int] = mapped_column(Integer)
    contract_version: Mapped[str] = mapped_column(String(24))
    external_revision_id: Mapped[str] = mapped_column(String(200))
    supersedes_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    author_id: Mapped[str] = mapped_column(String(160))
    source_id: Mapped[str] = mapped_column(String(160))
    source_reference: Mapped[str] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str] = mapped_column(Text)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class ResearchForecast(Base):
    """One agent-authored forecast cell, distinct from consensus and model state."""

    __tablename__ = "research_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "metric",
            "fiscal_year",
            "fiscal_period",
            "scenario",
            name="uq_research_forecast_period_scenario",
        ),
        CheckConstraint(
            "metric IN ('REVENUE','EPS','EBIT','EBITDA','FREE_CASH_FLOW','DILUTED_SHARES')",
            name="metric",
        ),
        CheckConstraint("period_type IN ('ANNUAL','QUARTERLY')", name="period_type"),
        CheckConstraint(
            "(period_type = 'ANNUAL' AND fiscal_period = 'FY') OR "
            "(period_type = 'QUARTERLY' AND fiscal_period IN ('Q1','Q2','Q3','Q4'))",
            name="fiscal_period",
        ),
        CheckConstraint("fiscal_year BETWEEN 1800 AND 2200", name="fiscal_year"),
        CheckConstraint("scenario IN ('POINT','BEAR','BASE','BULL')", name="scenario"),
        CheckConstraint(
            "availability_status IN ('AVAILABLE','UNAVAILABLE','DATA_CHECK')",
            name="availability_status",
        ),
        CheckConstraint(
            "(availability_status = 'AVAILABLE' AND value IS NOT NULL) OR "
            "(availability_status = 'UNAVAILABLE' AND value IS NULL) OR "
            "availability_status = 'DATA_CHECK'",
            name="availability_value",
        ),
        CheckConstraint(
            "(availability_status = 'AVAILABLE' AND availability_reason IS NULL) OR "
            "(availability_status <> 'AVAILABLE' AND "
            "coalesce(length(availability_reason), 0) > 0)",
            name="availability_reason",
        ),
        CheckConstraint(
            "(metric = 'DILUTED_SHARES' AND currency IS NULL AND unit = 'shares') OR "
            "(metric = 'EPS' AND currency IS NOT NULL AND unit = 'currency/share') OR "
            "(metric IN ('REVENUE','EBIT','EBITDA','FREE_CASH_FLOW') AND "
            "currency IS NOT NULL AND unit = 'currency')",
            name="metric_unit_currency",
        ),
        CheckConstraint(
            "value IS NULL OR metric NOT IN ('REVENUE','DILUTED_SHARES') OR value >= 0",
            name="nonnegative_metric",
        ),
        CheckConstraint("confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')", name="confidence"),
        Index("ix_research_forecasts_revision", "revision_id", "metric", "fiscal_year"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), index=True
    )
    metric: Mapped[str] = mapped_column(String(32))
    period_type: Mapped[str] = mapped_column(String(16))
    fiscal_year: Mapped[int] = mapped_column(Integer)
    fiscal_period: Mapped[str] = mapped_column(String(8))
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    scenario: Mapped[str] = mapped_column(String(16))
    value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unit: Mapped[str] = mapped_column(String(32))
    availability_status: Mapped[str] = mapped_column(String(16))
    availability_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="UNASSESSED")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchAssessment(Base):
    """A narrative business assessment; it does not encode canonical score values."""

    __tablename__ = "research_assessments"
    __table_args__ = (
        UniqueConstraint("revision_id", "assessment_type", name="uq_research_assessment_type"),
        CheckConstraint(
            "assessment_type IN ('BUSINESS_OUTLOOK','COMPETITIVE_POSITION','KEY_RISKS')",
            name="assessment_type",
        ),
        CheckConstraint("status IN ('AVAILABLE','UNAVAILABLE','DATA_CHECK')", name="status"),
        CheckConstraint(
            "(status = 'AVAILABLE' AND narrative IS NOT NULL) OR "
            "(status = 'UNAVAILABLE' AND narrative IS NULL) OR status = 'DATA_CHECK'",
            name="narrative_status",
        ),
        CheckConstraint(
            "(status = 'AVAILABLE' AND status_reason IS NULL) OR "
            "(status <> 'AVAILABLE' AND coalesce(length(status_reason), 0) > 0)",
            name="status_reason",
        ),
        CheckConstraint("confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')", name="confidence"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), index=True
    )
    assessment_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    status_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="UNASSESSED")
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchEvidence(Base):
    """A source link or citation attached to an immutable research revision."""

    __tablename__ = "research_evidence"
    __table_args__ = (
        CheckConstraint("length(source_name) > 0", name="source_name"),
        CheckConstraint(
            "source_document_id IS NOT NULL OR "
            "(external_identifier IS NOT NULL AND length(external_identifier) > 0) OR "
            "(source_url IS NOT NULL AND length(source_url) > 0)",
            name="source_locator",
        ),
        CheckConstraint("source_url IS NULL OR source_url LIKE 'https://%'", name="https_url"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_name: Mapped[str] = mapped_column(String(200))
    external_identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchQueueCompletion(Base):
    """A durable review completion for one source-derived queue condition."""

    __tablename__ = "research_queue_completions"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "condition_fingerprint", name="uq_research_queue_completion_condition"
        ),
        CheckConstraint("length(task_id) = 64", name="task_id"),
        CheckConstraint("length(condition_fingerprint) = 64", name="condition_fingerprint"),
        CheckConstraint(
            "task_type IN ('CANDIDATE_STAGE','THESIS_REVIEW','THESIS_QUESTION',"
            "'MATERIAL_EVIDENCE','RESEARCH_TRIGGER','MODEL_REUNDERWRITE','MODEL_INTEGRITY',"
            "'WATCHLIST_READINESS','STRUCTURAL_RISK')",
            name="task_type",
        ),
        CheckConstraint(
            "trigger_classification IS NULL OR trigger_classification IN "
            "('NOISE','INCREMENTAL','MAJOR-STRUCTURAL')",
            name="trigger_classification",
        ),
        CheckConstraint("length(completed_by) > 0", name="completed_by"),
        Index("ix_research_queue_completions_company_completed", "company_id", "completed_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(64))
    condition_fingerprint: Mapped[str] = mapped_column(String(64))
    task_type: Mapped[str] = mapped_column(String(32))
    task_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    completed_by: Mapped[str] = mapped_column(String(160))
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_classification: Mapped[str | None] = mapped_column(String(24), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchTriggerType(StrEnum):
    NEW_FILING = "NEW_FILING"
    MODEL_REVISION = "MODEL_REVISION"
    EXPECTED_IRR_CHANGE = "EXPECTED_IRR_CHANGE"
    CONSENSUS_REVISION = "CONSENSUS_REVISION"
    REPORTED_FACT_CORRECTION = "REPORTED_FACT_CORRECTION"
    THESIS_EVIDENCE_LINKED = "THESIS_EVIDENCE_LINKED"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"


class ThesisWatchClassification(StrEnum):
    NOISE = "NOISE"
    INCREMENTAL = "INCREMENTAL"
    MAJOR_STRUCTURAL = "MAJOR-STRUCTURAL"


class ResearchAgentRole(StrEnum):
    DATA_UNIVERSE_STEWARD = "DATA_UNIVERSE_STEWARD"
    PORTFOLIO_THESIS_SENTINEL = "PORTFOLIO_THESIS_SENTINEL"
    MODEL_ALLOCATION_STEWARD = "MODEL_ALLOCATION_STEWARD"


class ResearchAgentWorkEventType(StrEnum):
    DELIVERY_SUCCEEDED = "DELIVERY_SUCCEEDED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    STALE_SOURCE = "STALE_SOURCE"
    UNRESOLVED_REVIEW = "UNRESOLVED_REVIEW"


class ResearchTrigger(Base):
    """Append-only capture of a canonical source event that warrants research review."""

    __tablename__ = "research_triggers"
    __table_args__ = (
        UniqueConstraint("event_key", "version", name="uq_research_trigger_event_version"),
        UniqueConstraint("event_key", "fingerprint", name="uq_research_trigger_event_content"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("length(event_key) > 0", name="event_key"),
        CheckConstraint("length(fingerprint) = 64", name="fingerprint"),
        CheckConstraint(
            "trigger_type IN ('NEW_FILING','MODEL_REVISION','EXPECTED_IRR_CHANGE',"
            "'CONSENSUS_REVISION','REPORTED_FACT_CORRECTION','THESIS_EVIDENCE_LINKED',"
            "'RISK_ASSESSMENT')",
            name="trigger_type",
        ),
        CheckConstraint("length(source_domain) > 0", name="source_domain"),
        CheckConstraint("length(source_record_id) > 0", name="source_record_id"),
        CheckConstraint(
            "queue_task_id IS NULL OR length(queue_task_id) = 64", name="queue_task_id"
        ),
        CheckConstraint(
            "queue_condition_fingerprint IS NULL OR length(queue_condition_fingerprint) = 64",
            name="queue_condition_fingerprint",
        ),
        Index("ix_research_triggers_company_detected", "company_id", "detected_at"),
        Index("ix_research_triggers_source", "source_domain", "source_record_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    event_key: Mapped[str] = mapped_column(String(600))
    version: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    trigger_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(500))
    reason: Mapped[str] = mapped_column(Text)
    source_domain: Mapped[str] = mapped_column(String(120))
    source_record_id: Mapped[str] = mapped_column(String(500))
    source_reference: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    queue_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    queue_condition_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ResearchTriggerPublicationLink(Base):
    """Immutable lineage from a trigger to an accepted research or thesis revision."""

    __tablename__ = "research_trigger_publication_links"
    __table_args__ = (
        CheckConstraint(
            "(research_revision_id IS NOT NULL AND thesis_revision_id IS NULL) OR "
            "(research_revision_id IS NULL AND thesis_revision_id IS NOT NULL)",
            name="one_revision_type",
        ),
        CheckConstraint(
            "classification IN ('NOISE','INCREMENTAL','MAJOR-STRUCTURAL')",
            name="classification",
        ),
        CheckConstraint("length(classification_rationale) > 0", name="classification_rationale"),
        Index(
            "uq_research_trigger_publication_research",
            "trigger_id",
            "research_revision_id",
            unique=True,
            postgresql_where=text("research_revision_id IS NOT NULL"),
        ),
        Index(
            "uq_research_trigger_publication_thesis",
            "trigger_id",
            "thesis_revision_id",
            unique=True,
            postgresql_where=text("thesis_revision_id IS NOT NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    trigger_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_triggers.id", ondelete="RESTRICT"), index=True
    )
    research_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    thesis_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    classification: Mapped[str] = mapped_column(String(24))
    classification_rationale: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchAgentWorkEvent(Base):
    """Append-only delivery and acknowledgment history for external research agents."""

    __tablename__ = "research_agent_work_events"
    __table_args__ = (
        CheckConstraint(
            "agent_role IN ('DATA_UNIVERSE_STEWARD','PORTFOLIO_THESIS_SENTINEL',"
            "'MODEL_ALLOCATION_STEWARD')",
            name="agent_role",
        ),
        CheckConstraint(
            "work_type IN ('TRIGGER','QUEUE_TASK','DATA_DOMAIN','PORTFOLIO_STATE')",
            name="work_type",
        ),
        CheckConstraint("length(work_key) > 0", name="work_key"),
        CheckConstraint("length(work_fingerprint) = 64", name="work_fingerprint"),
        CheckConstraint(
            "channel IN ('API','GOOGLE_SHEETS')",
            name="channel",
        ),
        CheckConstraint(
            "event_type IN ('DELIVERY_SUCCEEDED','DELIVERY_FAILED','ACKNOWLEDGED',"
            "'IN_PROGRESS','COMPLETED','BLOCKED','SOURCE_UNAVAILABLE','STALE_SOURCE',"
            "'UNRESOLVED_REVIEW')",
            name="event_type",
        ),
        CheckConstraint("length(idempotency_key) > 0", name="idempotency_key"),
        CheckConstraint("length(content_fingerprint) = 64", name="content_fingerprint"),
        CheckConstraint(
            "(event_type IN ('ACKNOWLEDGED','IN_PROGRESS','COMPLETED','BLOCKED',"
            "'SOURCE_UNAVAILABLE','STALE_SOURCE','UNRESOLVED_REVIEW') "
            "AND delivery_id IS NOT NULL) OR "
            "(event_type IN ('DELIVERY_SUCCEEDED','DELIVERY_FAILED') AND delivery_id IS NULL)",
            name="delivery_reference",
        ),
        CheckConstraint(
            "event_type NOT IN ('DELIVERY_FAILED','BLOCKED','SOURCE_UNAVAILABLE',"
            "'STALE_SOURCE','UNRESOLVED_REVIEW') OR (reason IS NOT NULL AND length(reason) > 0)",
            name="reason_required",
        ),
        CheckConstraint(
            "(proposal_domain IS NULL AND proposal_candidate_id IS NULL) OR "
            "(proposal_domain IN ('MODEL','RESEARCH','THESIS','RISK') "
            "AND proposal_candidate_id IS NOT NULL)",
            name="proposal_reference",
        ),
        UniqueConstraint("idempotency_key", name="uq_research_agent_work_event_idempotency"),
        Index(
            "uq_research_agent_work_delivery",
            "agent_role",
            "work_type",
            "work_key",
            "work_fingerprint",
            "channel",
            unique=True,
            postgresql_where=text("event_type = 'DELIVERY_SUCCEEDED'"),
        ),
        Index("ix_research_agent_work_events_delivery", "delivery_id", "recorded_at"),
        Index(
            "ix_research_agent_work_events_identity",
            "agent_role",
            "work_type",
            "work_key",
            "work_fingerprint",
            "recorded_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    delivery_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_agent_work_events.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    agent_role: Mapped[str] = mapped_column(String(40))
    work_type: Mapped[str] = mapped_column(String(24))
    work_key: Mapped[str] = mapped_column(String(500))
    work_fingerprint: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    external_update_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    proposal_domain: Mapped[str | None] = mapped_column(String(16), nullable=True)
    proposal_candidate_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    blocker_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InvestmentThesisRevision(Base):
    """One immutable company investment-thesis snapshot from a research author."""

    __tablename__ = "investment_thesis_revisions"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "stream_key", "revision_number", name="uq_thesis_stream_revision"
        ),
        UniqueConstraint(
            "company_id",
            "stream_key",
            "external_revision_id",
            name="uq_thesis_stream_external_revision",
        ),
        CheckConstraint("revision_number > 0", name="revision_number"),
        CheckConstraint("length(stream_key) > 0", name="stream_key"),
        CheckConstraint("length(external_revision_id) > 0", name="external_revision_id"),
        CheckConstraint("length(author_id) > 0", name="author_id"),
        CheckConstraint("length(source_id) > 0", name="source_id"),
        CheckConstraint("length(source_reference) > 0", name="source_reference"),
        CheckConstraint("length(rationale) > 0", name="rationale"),
        CheckConstraint("status IN ('PUBLISHED','WITHDRAWN')", name="status"),
        CheckConstraint("confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')", name="confidence"),
        CheckConstraint(
            "(status = 'PUBLISHED' AND thesis_statement IS NOT NULL) OR "
            "(status = 'WITHDRAWN' AND thesis_statement IS NULL)",
            name="thesis_status",
        ),
        CheckConstraint("length(content_fingerprint) = 64", name="content_fingerprint"),
        Index("ix_thesis_revisions_company_observed", "company_id", "observed_at"),
        Index(
            "ix_thesis_revisions_company_stream",
            "company_id",
            "stream_key",
            "revision_number",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    security_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    stream_key: Mapped[str] = mapped_column(String(240))
    revision_number: Mapped[int] = mapped_column(Integer)
    contract_version: Mapped[str] = mapped_column(String(24))
    external_revision_id: Mapped[str] = mapped_column(String(200))
    supersedes_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    author_id: Mapped[str] = mapped_column(String(160))
    source_id: Mapped[str] = mapped_column(String(160))
    source_reference: Mapped[str] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(16))
    thesis_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="UNASSESSED")
    rationale: Mapped[str] = mapped_column(Text)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class InvestmentThesisClaim(Base):
    """A versioned, human-readable thesis claim or unresolved question."""

    __tablename__ = "investment_thesis_claims"
    __table_args__ = (
        UniqueConstraint("revision_id", "claim_key", name="uq_thesis_claim_revision_key"),
        CheckConstraint("length(claim_key) > 0", name="claim_key"),
        CheckConstraint(
            "claim_type IN ('COMPETITIVE_ADVANTAGE','DURABILITY','GROWTH_DRIVER',"
            "'PRINCIPAL_RISK','THESIS_BREAKER','CATALYST','IMPORTANT_DEVELOPMENT',"
            "'UNRESOLVED_QUESTION')",
            name="claim_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','UNDER_REVIEW','RESOLVED','INVALIDATED')", name="status"
        ),
        CheckConstraint("length(statement) > 0", name="statement"),
        CheckConstraint("confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')", name="confidence"),
        Index("ix_thesis_claims_revision_type", "revision_id", "claim_type"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("investment_thesis_revisions.id", ondelete="RESTRICT"), index=True
    )
    claim_key: Mapped[str] = mapped_column(String(80))
    claim_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    statement: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16), default="UNASSESSED")
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)


class InvestmentThesisEvidence(Base):
    """Evidence attached to a claim, optionally linked to canonical source facts."""

    __tablename__ = "investment_thesis_evidence"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('SUPPORTS','CONTRADICTS','CONTEXT')", name="relationship"
        ),
        CheckConstraint("length(source_name) > 0", name="source_name"),
        CheckConstraint(
            "source_document_id IS NOT NULL OR reported_fundamental_observation_id IS NOT NULL OR "
            "(external_identifier IS NOT NULL AND length(external_identifier) > 0) OR "
            "(source_url IS NOT NULL AND length(source_url) > 0)",
            name="source_locator",
        ),
        CheckConstraint("source_url IS NULL OR source_url LIKE 'https://%'", name="https_url"),
        Index("ix_thesis_evidence_document", "source_document_id"),
        Index("ix_thesis_evidence_fundamental", "reported_fundamental_observation_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("investment_thesis_claims.id", ondelete="RESTRICT"), index=True
    )
    relationship: Mapped[str] = mapped_column(String(16))
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True
    )
    reported_fundamental_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reported_fundamental_observations.id", ondelete="RESTRICT"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(String(200))
    external_identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskAssessmentRevision(Base):
    """Accepted full-snapshot qualitative risk assessment tied to exact portfolio state."""

    __tablename__ = "risk_assessment_revisions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "stream_key", "revision_number", name="uq_risk_stream_revision"
        ),
        UniqueConstraint(
            "portfolio_id",
            "stream_key",
            "external_revision_id",
            name="uq_risk_stream_external_revision",
        ),
        CheckConstraint("revision_number > 0", name="revision_number"),
        CheckConstraint("length(stream_key) > 0", name="stream_key"),
        CheckConstraint("length(external_revision_id) > 0", name="external_revision_id"),
        CheckConstraint("length(author_id) > 0", name="author_id"),
        CheckConstraint("length(source_id) > 0", name="source_id"),
        CheckConstraint("length(source_reference) > 0", name="source_reference"),
        CheckConstraint("length(reviewer) > 0", name="reviewer"),
        CheckConstraint("length(reviewer_note) > 0", name="reviewer_note"),
        CheckConstraint(
            "baseline_status_at_accept IN ('CURRENT','STALE_PORTFOLIO_STATE',"
            "'STALE_HOLDINGS','INCOMPLETE_VALUATION')",
            name="baseline_status",
        ),
        CheckConstraint(
            "(baseline_status_at_accept = 'CURRENT' AND baseline_stale_acknowledged = false) OR "
            "(baseline_status_at_accept <> 'CURRENT' AND baseline_stale_acknowledged = true)",
            name="baseline_acknowledgement",
        ),
        CheckConstraint("coverage_status IN ('COMPLETE','PARTIAL')", name="coverage_status"),
        CheckConstraint(
            "coverage_status = 'COMPLETE' OR coverage_note IS NOT NULL", name="coverage_note"
        ),
        CheckConstraint("length(content_fingerprint) = 64", name="content_fingerprint"),
        Index("ix_risk_revisions_portfolio_recorded", "portfolio_id", "recorded_at"),
        Index(
            "ix_risk_revisions_portfolio_stream", "portfolio_id", "stream_key", "revision_number"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), index=True
    )
    stream_key: Mapped[str] = mapped_column(String(160))
    revision_number: Mapped[int] = mapped_column(Integer)
    contract_version: Mapped[str] = mapped_column(String(24))
    external_revision_id: Mapped[str] = mapped_column(String(200))
    supersedes_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("risk_assessment_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    author_id: Mapped[str] = mapped_column(String(160))
    source_id: Mapped[str] = mapped_column(String(160))
    source_reference: Mapped[str] = mapped_column(String(1000))
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewer: Mapped[str] = mapped_column(String(160))
    reviewer_note: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    baseline_status_at_accept: Mapped[str] = mapped_column(String(32))
    baseline_stale_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    portfolio_state_contract_version: Mapped[str] = mapped_column(String(24))
    portfolio_state_fingerprint: Mapped[str] = mapped_column(String(80))
    holdings_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("holding_snapshots.id", ondelete="RESTRICT"), index=True
    )
    target_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("target_allocation_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    valuation_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    coverage_status: Mapped[str] = mapped_column(String(16))
    coverage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class RiskAssessmentFinding(Base):
    """One qualitative company or portfolio finding in an accepted assessment snapshot."""

    __tablename__ = "risk_assessment_findings"
    __table_args__ = (
        UniqueConstraint("revision_id", "finding_key", name="uq_risk_finding_revision_key"),
        CheckConstraint("scope IN ('COMPANY','PORTFOLIO')", name="scope"),
        CheckConstraint(
            "(scope = 'COMPANY' AND company_id IS NOT NULL) OR scope = 'PORTFOLIO'",
            name="company_scope",
        ),
        CheckConstraint(
            "category IN ('BUSINESS','FINANCIAL','GEOGRAPHIC','CURRENCY','BUSINESS_MODEL',"
            "'REGULATORY','GOVERNANCE','GEOPOLITICAL','PORTFOLIO_CONCENTRATION',"
            "'PORTFOLIO_EXPOSURE','THESIS_CHANGE','OTHER')",
            name="category",
        ),
        CheckConstraint("severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="severity"),
        CheckConstraint("confidence IN ('LOW','MEDIUM','HIGH','UNASSESSED')", name="confidence"),
        CheckConstraint("status IN ('ACTIVE','UNDER_REVIEW','RESOLVED')", name="status"),
        CheckConstraint(
            "change_direction IN ('NEW','WORSENING','UNCHANGED','IMPROVING','RESOLVED')",
            name="change_direction",
        ),
        CheckConstraint("length(finding_key) > 0", name="finding_key"),
        CheckConstraint("length(title) > 0", name="title"),
        Index("ix_risk_findings_company", "company_id", "revision_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("risk_assessment_revisions.id", ondelete="RESTRICT"), index=True
    )
    finding_key: Mapped[str] = mapped_column(String(80))
    scope: Mapped[str] = mapped_column(String(16))
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20))
    change_direction: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str] = mapped_column(Text)


class RiskAssessmentEvidence(Base):
    """Traceable evidence linked to a finding and optionally canonical research records."""

    __tablename__ = "risk_assessment_evidence"
    __table_args__ = (
        CheckConstraint("length(source_name) > 0", name="source_name"),
        CheckConstraint(
            "source_document_id IS NOT NULL OR reported_fundamental_observation_id IS NOT NULL "
            "OR thesis_revision_id IS NOT NULL OR thesis_claim_id IS NOT NULL "
            "OR (external_identifier IS NOT NULL AND length(external_identifier) > 0) "
            "OR (source_url IS NOT NULL AND length(source_url) > 0)",
            name="source_locator",
        ),
        CheckConstraint("source_url IS NULL OR source_url LIKE 'https://%'", name="https_url"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    finding_id: Mapped[UUID] = mapped_column(
        ForeignKey("risk_assessment_findings.id", ondelete="RESTRICT"), index=True
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reported_fundamental_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reported_fundamental_observations.id", ondelete="RESTRICT"), nullable=True
    )
    thesis_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    thesis_claim_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_claims.id", ondelete="RESTRICT"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(String(200))
    external_identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoogleSheetsRiskSyncRun(Base):
    """One explicit read-only poll of the dedicated risk-assessment inbox."""

    __tablename__ = "google_sheets_risk_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CONNECTED','SUCCEEDED','PARTIAL','BLOCKED','FAILED')", name="status"
        ),
        CheckConstraint(
            "candidate_count >= 0 AND new_count >= 0 AND unchanged_count >= 0 AND issue_count >= 0",
            name="counts_nonnegative",
        ),
        Index("ix_google_sheets_risk_sync_runs_started", "started_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    spreadsheet_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spreadsheet_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoogleSheetsRiskSyncCandidate(Base):
    """Captured risk contract evidence and its mutable preview/review status."""

    __tablename__ = "google_sheets_risk_sync_candidates"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_google_sheets_risk_candidate_key"),
        CheckConstraint(
            "status IN ('PENDING','READY','STALE_BASELINE','CONFLICT','INVALID',"
            "'ACCEPTED','REJECTED')",
            name="status",
        ),
        Index("ix_google_sheets_risk_candidates_status_observed", "status", "first_observed_at"),
        Index("ix_google_sheets_risk_candidates_portfolio", "portfolio_id", "first_observed_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    spreadsheet_id: Mapped[str] = mapped_column(String(128))
    spreadsheet_title: Mapped[str] = mapped_column(String(255))
    sheet_id: Mapped[int] = mapped_column(Integer)
    sheet_title: Mapped[str] = mapped_column(String(100))
    source_row_number: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    last_seen_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("google_sheets_risk_sync_runs.id", ondelete="SET NULL"), nullable=True
    )
    contract_text: Mapped[str] = mapped_column(Text)
    contract_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    contract_version: Mapped[str | None] = mapped_column(String(24), nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    portfolio_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    stream_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_revision_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    authored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseline_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preview_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("risk_assessment_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleSheetsResearchSyncRun(Base):
    """One explicit poll of the dedicated research and thesis inboxes."""

    __tablename__ = "google_sheets_research_sync_runs"
    __table_args__ = (
        CheckConstraint("status IN ('SUCCEEDED','PARTIAL','BLOCKED','FAILED')", name="status"),
        CheckConstraint(
            "candidate_count >= 0 AND new_count >= 0 AND unchanged_count >= 0 AND issue_count >= 0",
            name="counts_nonnegative",
        ),
        Index("ix_google_sheets_research_sync_runs_started", "started_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    spreadsheet_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spreadsheet_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoogleSheetsResearchSyncCandidate(Base):
    """Immutable captured research/thesis contract and mutable review decision."""

    __tablename__ = "google_sheets_research_sync_candidates"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_google_sheets_research_candidate_key"),
        CheckConstraint("domain IN ('RESEARCH','THESIS')", name="domain"),
        CheckConstraint(
            "status IN ('PENDING','READY','CONFLICT','INVALID','ACCEPTED','REJECTED')",
            name="status",
        ),
        Index(
            "ix_google_sheets_research_candidates_status_observed", "status", "first_observed_at"
        ),
        Index(
            "ix_google_sheets_research_candidates_company_observed",
            "company_id",
            "first_observed_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    domain: Mapped[str] = mapped_column(String(16))
    spreadsheet_id: Mapped[str] = mapped_column(String(128))
    spreadsheet_title: Mapped[str] = mapped_column(String(255))
    sheet_id: Mapped[int] = mapped_column(Integer)
    sheet_title: Mapped[str] = mapped_column(String(100))
    source_row_number: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    last_seen_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("google_sheets_research_sync_runs.id", ondelete="SET NULL"), nullable=True
    )
    contract_text: Mapped[str] = mapped_column(Text)
    contract_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    contract_version: Mapped[str | None] = mapped_column(String(24), nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    # Keep unresolved identities visible in the review queue instead of dropping
    # a publication when a contract names an unknown canonical UUID.
    company_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    security_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    stream_key: Mapped[str | None] = mapped_column(String(240), nullable=True)
    external_revision_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_revision_id: Mapped[UUID | None] = mapped_column(nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    accepted_research_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    accepted_thesis_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    reviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionPaceRun(Base):
    """Immutable portfolio-wide snapshot of the Execution Pace calculation."""

    __tablename__ = "execution_pace_runs"
    __table_args__ = (
        CheckConstraint("status IN ('COMPLETE','PARTIAL','UNAVAILABLE')", name="status"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        CheckConstraint("length(methodology_version) > 0", name="methodology_version"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    methodology_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str | None] = mapped_column(String(1000))


class ExecutionPaceDecision(Base):
    """Immutable company decision and the exact canonical inputs used to derive it."""

    __tablename__ = "execution_pace_decisions"
    __table_args__ = (
        UniqueConstraint("run_id", "company_id", name="uq_execution_pace_run_company"),
        CheckConstraint(
            "decision_status IN ('AVAILABLE','REVIEW','UNAVAILABLE','NOT_APPLICABLE')",
            name="decision_status",
        ),
        CheckConstraint(
            "(decision_status = 'AVAILABLE' AND pace IS NOT NULL) OR "
            "(decision_status <> 'AVAILABLE' AND pace IS NULL)",
            name="pace_status",
        ),
        CheckConstraint(
            "pace IS NULL OR pace IN ('ACCELERATE','BUILD','NORMAL_BUILD','SMALL_LADDER',"
            "'LADDER','HOLD','SLOW_LIMIT','WAIT_LIMIT','PATIENT_TRIM','TRIM_FASTER',"
            "'NORMAL_TRIM','PATIENT_EXIT','NORMAL_EXIT')",
            name="pace",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_pace_runs.id", ondelete="RESTRICT"), index=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    target_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("target_allocation_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    holding_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("holding_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    model_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    model_output_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_output_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    price_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("price_observations.id", ondelete="RESTRICT"), nullable=True
    )
    decision_status: Mapped[str] = mapped_column(String(24))
    pace: Mapped[str | None] = mapped_column(String(24), nullable=True)
    reason: Mapped[str] = mapped_column(String(1000))
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)


class LegacyImportBatch(Base):
    """Immutable receipt for one deterministic import of the scoped workbook pair."""

    __tablename__ = "legacy_import_batches"
    __table_args__ = (
        UniqueConstraint("source_digest"),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
        CheckConstraint("status IN ('APPLIED')", name="status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_digest: Mapped[str] = mapped_column(String(64))
    portfolio_workbook_sha256: Mapped[str] = mapped_column(String(64))
    market_data_sha256: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(16), default="APPLIED")
    report: Mapped[dict[str, object]] = mapped_column(JSON)


class CanonicalBootstrapRun(Base):
    """Immutable receipt for one canonical workbook snapshot bootstrap execution."""

    __tablename__ = "canonical_bootstrap_runs"
    __table_args__ = (
        UniqueConstraint("input_digest"),
        CheckConstraint("length(input_digest) = 64", name="input_digest"),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
        CheckConstraint(
            "portfolio_snapshot_run_id ~ '^[0-9a-f]{32}$'", name="portfolio_snapshot_run_id"
        ),
        CheckConstraint("market_snapshot_run_id ~ '^[0-9a-f]{32}$'", name="market_snapshot_run_id"),
        CheckConstraint(
            "provider_identifiers_sha256 IS NULL OR length(provider_identifiers_sha256) = 64",
            name="provider_identifiers_sha256",
        ),
        CheckConstraint("status IN ('APPLIED','APPLIED_WITH_GAPS')", name="status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    input_digest: Mapped[str] = mapped_column(String(64))
    source_digest: Mapped[str] = mapped_column(String(64))
    portfolio_snapshot_run_id: Mapped[str] = mapped_column(String(32))
    market_snapshot_run_id: Mapped[str] = mapped_column(String(32))
    provider_identifiers_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_version: Mapped[str] = mapped_column(String(80))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(24), default="APPLIED")
    report: Mapped[dict[str, object]] = mapped_column(JSON)


class MarketDataBatch(Base):
    """Immutable receipt for one workbook snapshot or provider ingestion batch."""

    __tablename__ = "market_data_batches"
    __table_args__ = (
        UniqueConstraint(
            "source_digest",
            "normalizer_version",
            name="uq_market_data_batches_source_normalizer",
        ),
        CheckConstraint(
            "source_kind IN ('WORKBOOK_SNAPSHOT','PROVIDER_RESPONSE')", name="source_kind"
        ),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
        CheckConstraint("length(workbook_sha256) = 64", name="workbook_sha256"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_digest: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(
        String(32), default="WORKBOOK_SNAPSHOT", server_default=text("'WORKBOOK_SNAPSHOT'")
    )
    workbook_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_schema_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalizer_version: Mapped[str] = mapped_column(
        String(80), default="legacy-workbook-market-data-v1", nullable=False
    )
    query_scope: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    source_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_text: Mapped[str | None] = mapped_column(String(120))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider_summary: Mapped[dict[str, object]] = mapped_column(JSON)
    reconciliation: Mapped[dict[str, object]] = mapped_column(JSON)


class PriceObservation(Base):
    """Append-only daily price fact keyed to an exact listing and source record."""

    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint("source_ref", name="uq_price_observations_source_ref"),
        CheckConstraint("price_kind IN ('DAILY_CLOSE','CURRENT_QUOTE')", name="price_kind"),
        CheckConstraint(
            "data_quality IN ('PASS','PASS_VERIFIED_FALLBACK','UNSPECIFIED','INVALID')",
            name="data_quality",
        ),
        CheckConstraint("provider_close IS NULL OR provider_close > 0", name="provider_close"),
        CheckConstraint(
            "split_adjusted_close IS NULL OR split_adjusted_close > 0",
            name="split_adjusted_close",
        ),
        CheckConstraint(
            "total_return_close IS NULL OR total_return_close > 0", name="total_return_close"
        ),
        Index("ix_price_observations_listing_date", "listing_id", "market_date"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT"), index=True
    )
    batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    price_kind: Mapped[str] = mapped_column(
        String(24), default="DAILY_CLOSE", server_default=text("'DAILY_CLOSE'")
    )
    market_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider_close: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    split_adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    total_return_close: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    currency: Mapped[str] = mapped_column(String(3))
    provider_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_price_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal(1), server_default=text("1")
    )
    provider: Mapped[str] = mapped_column(String(120))
    provider_symbol: Mapped[str] = mapped_column(String(120))
    adjustment_basis: Mapped[str] = mapped_column(String(500))
    data_quality: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str] = mapped_column(String(500))
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("price_observations.id", ondelete="RESTRICT"), unique=True
    )


class CorporateAction(Base):
    """Listing-specific split or symbol event retained as observed source facts."""

    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint("source_action_id", name="uq_corporate_actions_source_action_id"),
        CheckConstraint("verified IN (true, false)", name="verified"),
        CheckConstraint(
            "(cash_amount IS NULL AND cash_currency IS NULL) OR "
            "(cash_amount > 0 AND cash_currency IS NOT NULL)",
            name="cash_dividend",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT"), index=True
    )
    source_action_id: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(
        String(120), default="LEGACY_WORKBOOK", server_default=text("'LEGACY_WORKBOOK'")
    )
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_type: Mapped[str] = mapped_column(String(80))
    ratio_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    ratio_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    old_symbol: Mapped[str | None] = mapped_column(String(120))
    new_symbol: Mapped[str | None] = mapped_column(String(120))
    old_exchange: Mapped[str | None] = mapped_column(String(120))
    new_exchange: Mapped[str | None] = mapped_column(String(120))
    currency_before: Mapped[str | None] = mapped_column(String(3))
    currency_after: Mapped[str | None] = mapped_column(String(3))
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    cash_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    provider_cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    provider_cash_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    verified: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT")
    )


class PriceRegimeSnapshot(Base):
    """Dated price-behaviour metrics and the legacy observed regime classification."""

    __tablename__ = "price_regime_snapshots"
    __table_args__ = (
        UniqueConstraint("batch_id", "listing_id", name="uq_price_regime_batch_listing"),
        CheckConstraint("data_quality IN ('PASS','DATA_CHECK','UNSPECIFIED')", name="data_quality"),
        Index("ix_price_regime_listing_date", "listing_id", "as_of"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT"), index=True
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT")
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_close: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    split_adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    dma_20: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    dma_50: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    dma_200: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    high_52w: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    drawdown_52w: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    vs_dma_20: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    vs_dma_50: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    vs_dma_200: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    return_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    return_3m: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    return_6m: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    realized_vol_20d: Mapped[Decimal | None] = mapped_column(Numeric(18, 12))
    trend_state: Mapped[str | None] = mapped_column(String(40))
    correction_state: Mapped[str | None] = mapped_column(String(40))
    regime: Mapped[str | None] = mapped_column(String(80))
    data_quality: Mapped[str] = mapped_column(String(20))
    quality_reason: Mapped[str | None] = mapped_column(String(1000))
    methodology_version: Mapped[str] = mapped_column(String(40))
    source_ref: Mapped[str] = mapped_column(String(500))


class FxObservation(Base):
    """Append-only exchange-rate fact, quoted as quote units per one base unit."""

    __tablename__ = "fx_observations"
    __table_args__ = (
        CheckConstraint("base_currency <> quote_currency", name="distinct_currencies"),
        CheckConstraint("rate > 0", name="positive_rate"),
        CheckConstraint("data_quality IN ('PASS','DATA_CHECK','INVALID')", name="data_quality"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        UniqueConstraint("source_ref", name="uq_fx_observations_source_ref"),
        Index(
            "ix_fx_observations_pair_effective", "base_currency", "quote_currency", "effective_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(28, 14))
    data_quality: Mapped[str] = mapped_column(
        String(20), default="PASS", server_default=text("'PASS'")
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fx_observations.id", ondelete="RESTRICT"), unique=True, nullable=True
    )
    provider: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(1000))
    actor: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))


class ExternalRawPayload(Base):
    """Compressed immutable provider response retained for replay and audit."""

    __tablename__ = "external_raw_payloads"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_record_id", name="uq_external_payload_batch_record"),
        UniqueConstraint(
            "reported_fundamental_batch_id",
            "source_record_id",
            name="uq_external_payload_fundamental_batch_record",
        ),
        UniqueConstraint(
            "consensus_estimate_batch_id",
            "source_record_id",
            name="uq_external_payload_consensus_batch_record",
        ),
        UniqueConstraint(
            "source_document_batch_id",
            "source_record_id",
            name="uq_external_payload_source_document_batch_record",
        ),
        CheckConstraint(
            "num_nonnulls(batch_id, reported_fundamental_batch_id, "
            "consensus_estimate_batch_id, source_document_batch_id) = 1",
            name="exactly_one_batch",
        ),
        CheckConstraint("length(payload_sha256) = 64", name="payload_sha256"),
        CheckConstraint("content_encoding IN ('identity','gzip')", name="content_encoding"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    reported_fundamental_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "reported_fundamental_batches.id",
            ondelete="RESTRICT",
            name="fk_external_raw_payloads_fundamental_batch",
        ),
        index=True,
        nullable=True,
    )
    consensus_estimate_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "consensus_estimate_batches.id",
            ondelete="RESTRICT",
            name="fk_external_raw_payloads_consensus_batch",
        ),
        index=True,
        nullable=True,
    )
    source_document_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "source_document_batches.id",
            ondelete="RESTRICT",
            name="fk_external_raw_payloads_source_document_batch",
        ),
        index=True,
        nullable=True,
    )
    provider_id: Mapped[str] = mapped_column(String(120))
    domain: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    media_type: Mapped[str] = mapped_column(String(160))
    content_encoding: Mapped[str] = mapped_column(
        String(16), default="gzip", server_default=text("'gzip'")
    )
    payload_sha256: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_bytes: Mapped[bytes] = mapped_column(LargeBinary)


class MarketDataBootstrapRun(Base):
    """Operator-run, resumable historical price/FX bootstrap scope."""

    __tablename__ = "market_data_bootstrap_runs"
    __table_args__ = (
        CheckConstraint("length(input_digest) = 64", name="input_digest"),
        CheckConstraint("length(crosswalk_sha256) = 64", name="crosswalk_sha256"),
        CheckConstraint("start_date <= end_date", name="date_window"),
        CheckConstraint(
            "target_environment IN ('development','rehearsal')", name="target_environment"
        ),
        CheckConstraint(
            "status IN ('PREPARED','RUNNING','PARTIAL','COMPLETE','FAILED','BLOCKED')",
            name="status",
        ),
        Index("ix_market_data_bootstrap_runs_status_prepared", "status", "prepared_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    input_digest: Mapped[str] = mapped_column(String(64))
    provider_id: Mapped[str] = mapped_column(String(120))
    provider_schema_version: Mapped[str] = mapped_column(String(120))
    crosswalk_sha256: Mapped[str] = mapped_column(String(64))
    target_environment: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    scope: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="PREPARED")
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_provider_request_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class MarketDataBootstrapCheckpoint(Base):
    """Durable outcome for one exact listing or allowlisted FX pair request."""

    __tablename__ = "market_data_bootstrap_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "subject_kind", "subject_key", name="uq_market_data_bootstrap_checkpoint"
        ),
        CheckConstraint("subject_kind IN ('LISTING','FX_PAIR')", name="subject_kind"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETE','UNAVAILABLE','FAILED','BLOCKED')",
            name="status",
        ),
        CheckConstraint("attempt_count BETWEEN 0 AND 3", name="attempt_count"),
        CheckConstraint(
            "(subject_kind = 'LISTING' AND listing_id IS NOT NULL "
            "AND base_currency IS NULL AND quote_currency IS NULL) OR "
            "(subject_kind = 'FX_PAIR' AND listing_id IS NULL "
            "AND company_id IS NULL AND base_currency IS NOT NULL AND quote_currency IS NOT NULL)",
            name="subject_identity",
        ),
        CheckConstraint(
            "base_currency IS NULL OR base_currency ~ '^[A-Z]{3}$'", name="base_currency"
        ),
        CheckConstraint(
            "quote_currency IS NULL OR quote_currency ~ '^[A-Z]{3}$'", name="quote_currency"
        ),
        Index("ix_market_data_bootstrap_checkpoint_run_status", "run_id", "status"),
        Index("ix_market_data_bootstrap_checkpoint_retry", "status", "next_attempt_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_data_bootstrap_runs.id", ondelete="RESTRICT"), index=True
    )
    subject_kind: Mapped[str] = mapped_column(String(16))
    subject_key: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True
    )
    listing_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT"), nullable=True
    )
    base_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    quote_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class FundamentalsBootstrapRun(Base):
    """Target-bound operator run for SEC facts and filing metadata bootstrap."""

    __tablename__ = "fundamentals_bootstrap_runs"
    __table_args__ = (
        CheckConstraint("length(input_digest) = 64", name="input_digest"),
        CheckConstraint("length(mapping_sha256) = 64", name="mapping_sha256"),
        CheckConstraint(
            "target_environment IN ('development','rehearsal')", name="target_environment"
        ),
        CheckConstraint(
            "status IN ('PREPARED','RUNNING','PARTIAL','COMPLETE','FAILED','BLOCKED')",
            name="status",
        ),
        Index("ix_fundamentals_bootstrap_run_status", "status", "prepared_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    input_digest: Mapped[str] = mapped_column(String(64))
    mapping_sha256: Mapped[str] = mapped_column(String(64))
    bootstrap_version: Mapped[str] = mapped_column(String(80))
    target_environment: Mapped[str] = mapped_column(String(20))
    scope: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="PREPARED")
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_provider_request_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class FundamentalsBootstrapCheckpoint(Base):
    """Resumable outcome for one mapped issuer and SEC bootstrap stage."""

    __tablename__ = "fundamentals_bootstrap_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "stage", "company_id", name="uq_fundamentals_bootstrap_checkpoint"
        ),
        UniqueConstraint("run_id", "sequence_number", name="uq_fundamentals_bootstrap_sequence"),
        CheckConstraint("stage IN ('SOURCE_DOCUMENTS','REPORTED_FUNDAMENTALS')", name="stage"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETE','UNAVAILABLE','FAILED','BLOCKED')",
            name="status",
        ),
        CheckConstraint("attempt_count BETWEEN 0 AND 3", name="attempt_count"),
        CheckConstraint("sequence_number >= 0", name="sequence_number"),
        CheckConstraint("page_count >= 0", name="page_count"),
        CheckConstraint("provider_request_count >= 0", name="provider_request_count"),
        CheckConstraint("cik ~ '^[0-9]{10}$'", name="cik"),
        Index("ix_fundamentals_bootstrap_checkpoint_run_status", "run_id", "status"),
        Index("ix_fundamentals_bootstrap_checkpoint_retry", "status", "next_attempt_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("fundamentals_bootstrap_runs.id", ondelete="RESTRICT"), index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(32))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    mapping_identifier_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_provider_identifiers.id", ondelete="RESTRICT")
    )
    cik: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    provider_request_count: Mapped[int] = mapped_column(Integer, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class ExternalIngestionRun(Base):
    """Operational state for one idempotent provider/domain execution."""

    __tablename__ = "external_ingestion_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_external_ingestion_run_idempotency"),
        CheckConstraint(
            "domain IN ('MARKET_DATA','FX','CORPORATE_ACTIONS','REPORTED_FUNDAMENTALS',"
            "'CONSENSUS_ESTIMATES','SOURCE_DOCUMENTS')",
            name="domain",
        ),
        CheckConstraint(
            "status IN ('RUNNING','COMPLETE','PARTIAL','FAILED','BLOCKED','NOT_APPLICABLE')",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0 AND max_attempts BETWEEN 1 AND 3", name="attempts"),
        Index(
            "ix_external_ingestion_run_provider_domain_created",
            "provider_id",
            "domain",
            "created_at",
        ),
        Index("ix_external_ingestion_run_status_created", "status", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_id: Mapped[str] = mapped_column(String(120))
    domain: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    replay_of_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("external_ingestion_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_attempt_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    request_scope: Mapped[dict[str, object]] = mapped_column(JSON)
    report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class ExternalIngestionAttempt(Base):
    """Persisted outcome and diagnostics for one bounded provider attempt."""

    __tablename__ = "external_ingestion_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "attempt_number", name="uq_external_ingestion_attempt_number"),
        CheckConstraint("attempt_number > 0", name="attempt_number"),
        CheckConstraint(
            "status IN ('SUCCEEDED','PARTIAL','FAILED','BLOCKED','NOT_APPLICABLE')",
            name="status",
        ),
        Index("ix_external_ingestion_attempt_run_finished", "run_id", "finished_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_ingestion_runs.id", ondelete="RESTRICT"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class RecurringOperationRun(Base):
    """Operational status for one bounded scheduled application job attempt."""

    __tablename__ = "recurring_operation_runs"
    __table_args__ = (
        CheckConstraint(
            "job_name IN ('SEC_FUNDAMENTALS','SEC_FILINGS','FMP_CONSENSUS','SHEETS_DISCOVERY',"
            "'RESEARCH_TRIGGER_SCAN','AGENT_WORK_FEED','DECISION_RECOMPUTE')",
            name="job_name",
        ),
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','PARTIAL','BLOCKED','FAILED','SKIPPED')",
            name="status",
        ),
        Index("ix_recurring_operation_runs_job_started", "job_name", "started_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_name: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    result: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class RecurringOperationsWorkerState(Base):
    """Singleton heartbeat for the local recurring-operations worker."""

    __tablename__ = "recurring_operations_worker_state"
    __table_args__ = (
        CheckConstraint("worker_key = 'primary'", name="primary_worker"),
        CheckConstraint("status IN ('STARTING','RUNNING','STOPPED','FAILED')", name="status"),
    )
    worker_key: Mapped[str] = mapped_column(String(16), primary_key=True, default="primary")
    instance_id: Mapped[UUID] = mapped_column(default=uuid4)
    status: Mapped[str] = mapped_column(String(16), default="STARTING")
    process_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class OperationalJobRequest(Base):
    """Durable user request for one allowlisted background operation."""

    __tablename__ = "operational_job_requests"
    __table_args__ = (
        CheckConstraint(
            "job_name IN ('MARKET_DATA','FX','MARKET_AND_FX','SEC_FUNDAMENTALS','SEC_FILINGS',"
            "'SHEETS_DISCOVERY','RESEARCH_REFRESH','AGENT_WORK_FEED','COMPANY_REFRESH','REFRESH_ALL')",
            name="job_name",
        ),
        CheckConstraint("scope_kind IN ('ACTIVE_UNIVERSE','COMPANY')", name="scope_kind"),
        CheckConstraint(
            "(scope_kind = 'COMPANY' AND company_id IS NOT NULL) OR "
            "(scope_kind = 'ACTIVE_UNIVERSE' AND company_id IS NULL)",
            name="scope_company",
        ),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','PARTIAL','BLOCKED','FAILED')",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        Index("ix_operational_job_requests_status_requested", "status", "requested_at"),
        Index(
            "ix_operational_job_requests_fingerprint_requested",
            "request_fingerprint",
            "requested_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_name: Mapped[str] = mapped_column(String(40))
    scope_kind: Mapped[str] = mapped_column(String(20))
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True
    )
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lifecycle: Mapped[str | None] = mapped_column(String(16), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(32), default="LOCAL_USER")
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operational_job_requests.id", ondelete="RESTRICT"), nullable=True
    )
    affected_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_detail: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class OperationalJobAttempt(Base):
    """Append-oriented execution record for one request step."""

    __tablename__ = "operational_job_attempts"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "attempt_number", "step_name", name="uq_operational_job_step_attempt"
        ),
        CheckConstraint("attempt_number > 0", name="attempt_number"),
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','PARTIAL','BLOCKED','FAILED','SKIPPED','DEFERRED')",
            name="status",
        ),
        Index("ix_operational_job_attempts_request_started", "request_id", "started_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_job_requests.id", ondelete="RESTRICT"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    affected_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class SourceDocumentBatch(Base):
    """Immutable provider response and normalizer receipt for source-document metadata."""

    __tablename__ = "source_document_batches"
    __table_args__ = (
        UniqueConstraint(
            "source_digest", "normalizer_version", name="uq_source_document_batches_digest_version"
        ),
        CheckConstraint("domain = 'SOURCE_DOCUMENTS'", name="domain"),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_id: Mapped[str] = mapped_column(String(120))
    provider_schema_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalizer_version: Mapped[str] = mapped_column(String(80))
    domain: Mapped[str] = mapped_column(String(80), default="SOURCE_DOCUMENTS")
    source_digest: Mapped[str] = mapped_column(String(64))
    query_scope: Mapped[dict[str, object]] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider_summary: Mapped[dict[str, object]] = mapped_column(JSON)
    reconciliation: Mapped[dict[str, object]] = mapped_column(JSON)


class SourceDocument(Base):
    """Immutable filing or issuer-published source reference, not document content."""

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "provider_id",
            "external_identifier",
            name="uq_source_document_company_provider_external_id",
        ),
        CheckConstraint(
            "document_type IN ('10-K','10-Q','8-K','20-F','6-K','ANNUAL_REPORT',"
            "'EARNINGS_RELEASE','OTHER')",
            name="document_type",
        ),
        CheckConstraint("data_quality IN ('PASS','DATA_CHECK')", name="data_quality"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        CheckConstraint("length(source_name) > 0", name="source_name"),
        CheckConstraint("length(canonical_url) > 0", name="canonical_url"),
        CheckConstraint(
            "batch_id IS NOT NULL OR retrieved_at IS NULL",
            name="retrieved_only_for_ingested_source",
        ),
        Index("ix_source_documents_company_published", "company_id", "published_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    security_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), nullable=True
    )
    batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_document_batches.id", ondelete="RESTRICT"), nullable=True
    )
    provider_id: Mapped[str] = mapped_column(String(120))
    source_name: Mapped[str] = mapped_column(String(200))
    source_jurisdiction: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_identifier: Mapped[str] = mapped_column(String(500))
    document_type: Mapped[str] = mapped_column(String(32))
    source_form: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    reporting_period: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    filed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    canonical_url: Mapped[str] = mapped_column(String(2000))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    amends_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True
    )
    supersedes_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True
    )
    data_quality: Mapped[str] = mapped_column(
        String(20), default=SourceDocumentQuality.PASS.value, server_default=text("'PASS'")
    )
    quality_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    actor: Mapped[str] = mapped_column(String(32), default=Actor.IMPORT.value)


class CompanyProviderIdentifier(Base):
    """Operator-verified issuer identity crosswalk for one external provider."""

    __tablename__ = "company_provider_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "identifier_type",
            "identifier_value",
            name="uq_company_provider_identifiers_external_id",
        ),
        CheckConstraint("identifier_type IN ('SEC_CIK')", name="identifier_type"),
        CheckConstraint("length(evidence_source) > 0", name="evidence_source"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    provider_id: Mapped[str] = mapped_column(String(120))
    identifier_type: Mapped[str] = mapped_column(String(24))
    identifier_value: Mapped[str] = mapped_column(String(20))
    provider_company_name: Mapped[str] = mapped_column(String(300))
    evidence_source: Mapped[str] = mapped_column(String(1000))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(32), default=Actor.IMPORT)


class ReportedFundamentalBatch(Base):
    """Immutable provider response and normalizer receipt for reported facts."""

    __tablename__ = "reported_fundamental_batches"
    __table_args__ = (
        UniqueConstraint(
            "source_digest", "normalizer_version", name="uq_fundamental_batches_digest_version"
        ),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
        CheckConstraint("domain = 'REPORTED_FUNDAMENTALS'", name="domain"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_id: Mapped[str] = mapped_column(String(120))
    provider_schema_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalizer_version: Mapped[str] = mapped_column(String(80))
    domain: Mapped[str] = mapped_column(String(80), default="REPORTED_FUNDAMENTALS")
    source_digest: Mapped[str] = mapped_column(String(64))
    query_scope: Mapped[dict[str, object]] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider_summary: Mapped[dict[str, object]] = mapped_column(JSON)
    reconciliation: Mapped[dict[str, object]] = mapped_column(JSON)


class ReportedFundamentalObservation(Base):
    """Append-only normalized fact from a dated reported financial statement."""

    __tablename__ = "reported_fundamental_observations"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "source_record_id",
            "observation_fingerprint",
            name="uq_reported_fundamental_source_version",
        ),
        CheckConstraint(
            "metric IN ('REVENUE','GROSS_PROFIT','OPERATING_INCOME','NET_INCOME',"
            "'CASH_AND_CASH_EQUIVALENTS','CURRENT_DEBT','NONCURRENT_DEBT',"
            "'OPERATING_CASH_FLOW','CAPITAL_EXPENDITURES',"
            "'DILUTED_WEIGHTED_AVERAGE_SHARES')",
            name="metric",
        ),
        CheckConstraint(
            "statement IN ('INCOME_STATEMENT','BALANCE_SHEET','CASH_FLOW_STATEMENT')",
            name="statement",
        ),
        CheckConstraint("period_type IN ('ANNUAL','QUARTERLY','INSTANT')", name="period_type"),
        CheckConstraint(
            "(period_type = 'INSTANT' AND period_start IS NULL) OR "
            "(period_type <> 'INSTANT' AND period_start IS NOT NULL "
            "AND period_start <= period_end)",
            name="period_dates",
        ),
        CheckConstraint("value IS NOT NULL", name="value_required"),
        CheckConstraint("source_priority >= 0 AND mapping_priority >= 0", name="priorities"),
        CheckConstraint(
            "revision_context IN ('ORIGINAL','COMPARATIVE_REPORTED','POTENTIAL_RESTATEMENT',"
            "'AMENDED_FILING')",
            name="revision_context",
        ),
        CheckConstraint("data_quality IN ('PASS','DATA_CHECK','INVALID')", name="data_quality"),
        Index(
            "ix_reported_fundamentals_company_metric_period",
            "company_id",
            "metric",
            "period_end",
        ),
        Index(
            "ix_reported_fundamentals_company_known_at",
            "company_id",
            "recorded_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "companies.id",
            ondelete="RESTRICT",
            name="fk_reported_fundamental_company",
        ),
        index=True,
    )
    security_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "securities.id",
            ondelete="RESTRICT",
            name="fk_reported_fundamental_security",
        ),
        nullable=True,
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "reported_fundamental_batches.id",
            ondelete="RESTRICT",
            name="fk_reported_fundamental_batch",
        ),
        index=True,
    )
    provider_id: Mapped[str] = mapped_column(String(120))
    provider_entity_id: Mapped[str] = mapped_column(String(80))
    source_priority: Mapped[int] = mapped_column(Integer)
    metric: Mapped[str] = mapped_column(String(48))
    statement: Mapped[str] = mapped_column(String(32))
    period_type: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(12), nullable=True)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unit: Mapped[str] = mapped_column(String(80))
    source_taxonomy: Mapped[str] = mapped_column(String(80))
    source_concept: Mapped[str] = mapped_column(String(200))
    source_unit: Mapped[str] = mapped_column(String(80))
    accession_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    form: Mapped[str | None] = mapped_column(String(20), nullable=True)
    frame: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_record_id: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(String(1000))
    source_ref: Mapped[str] = mapped_column(String(1000))
    observation_fingerprint: Mapped[str] = mapped_column(String(64))
    mapping_priority: Mapped[int] = mapped_column(Integer, default=0)
    revision_context: Mapped[str] = mapped_column(String(32), default="ORIGINAL")
    data_quality: Mapped[str] = mapped_column(String(20), default="PASS")
    quality_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "reported_fundamental_observations.id",
            ondelete="RESTRICT",
            name="fk_reported_fundamental_supersedes",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )


class ConsensusEstimateProviderMapping(Base):
    """Reviewed provider-symbol identity and source-continuity assignment."""

    __tablename__ = "consensus_estimate_provider_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "provider_symbol",
            name="uq_consensus_provider_mapping_provider_symbol",
        ),
        CheckConstraint("role IN ('PRIMARY','FALLBACK')", name="role"),
        CheckConstraint("priority >= 0", name="priority"),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("length(evidence_source) > 0", name="evidence_source"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        UniqueConstraint(
            "company_id",
            "role",
            "provider_id",
            "effective_from",
            name="uq_consensus_estimate_mapping_company_source_effective",
        ),
        Index(
            "uq_consensus_estimate_primary_company_effective",
            "company_id",
            "effective_from",
            unique=True,
            postgresql_where=text("role = 'PRIMARY'"),
        ),
        Index(
            "ix_consensus_estimate_mapping_company_effective",
            "company_id",
            "effective_from",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    listing_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    provider_id: Mapped[str] = mapped_column(String(120))
    provider_symbol: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    evidence_source: Mapped[str] = mapped_column(String(1000))
    currency_evidence_source: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(32), default=Actor.IMPORT)


class ConsensusEstimateBatch(Base):
    """Immutable receipt for one consensus provider or legacy snapshot batch."""

    __tablename__ = "consensus_estimate_batches"
    __table_args__ = (
        UniqueConstraint(
            "source_digest",
            "normalizer_version",
            "observed_at",
            name="uq_consensus_estimate_batch_snapshot",
        ),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
        CheckConstraint("domain = 'CONSENSUS_ESTIMATES'", name="domain"),
        CheckConstraint(
            "source_kind IN ('PROVIDER_RESPONSE','LEGACY_WORKBOOK')", name="source_kind"
        ),
        CheckConstraint(
            "(source_kind = 'LEGACY_WORKBOOK' AND observed_at IS NULL) OR "
            "(source_kind = 'PROVIDER_RESPONSE' AND observed_at IS NOT NULL)",
            name="source_observation_time",
        ),
        Index(
            "uq_consensus_legacy_batch_snapshot",
            "source_digest",
            "normalizer_version",
            "snapshot_date",
            unique=True,
            postgresql_where=text("observed_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_id: Mapped[str] = mapped_column(String(120))
    provider_schema_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalizer_version: Mapped[str] = mapped_column(String(80))
    domain: Mapped[str] = mapped_column(String(80), default="CONSENSUS_ESTIMATES")
    source_kind: Mapped[str] = mapped_column(String(32))
    source_digest: Mapped[str] = mapped_column(String(64))
    source_reference: Mapped[str] = mapped_column(String(1000))
    query_scope: Mapped[dict[str, object]] = mapped_column(JSON)
    snapshot_date: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider_summary: Mapped[dict[str, object]] = mapped_column(JSON)
    reconciliation: Mapped[dict[str, object]] = mapped_column(JSON)


class ConsensusEstimateObservation(Base):
    """Immutable provider-specific consensus point-in-time fact."""

    __tablename__ = "consensus_estimate_observations"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "source_record_id", name="uq_consensus_estimate_batch_source_record"
        ),
        CheckConstraint("metric IN ('REVENUE','EPS')", name="metric"),
        CheckConstraint("period_type IN ('ANNUAL','QUARTERLY')", name="period_type"),
        CheckConstraint("length(forecast_period) > 0", name="forecast_period"),
        CheckConstraint("value IS NOT NULL", name="value_required"),
        CheckConstraint("analyst_count IS NULL OR analyst_count >= 0", name="analyst_count"),
        CheckConstraint(
            "(low_value IS NULL OR low_value <= value) AND "
            "(high_value IS NULL OR high_value >= value) AND "
            "(low_value IS NULL OR high_value IS NULL OR low_value <= high_value)",
            name="range_order",
        ),
        CheckConstraint("data_quality IN ('PASS','DATA_CHECK','INVALID')", name="data_quality"),
        CheckConstraint(
            "revision_context IN ('SNAPSHOT','REVISED','LEGACY_BASELINE')",
            name="revision_context",
        ),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency"),
        Index(
            "ix_consensus_estimates_company_metric_period",
            "company_id",
            "metric",
            "period_end",
        ),
        Index(
            "ix_consensus_estimates_company_observed",
            "company_id",
            "snapshot_date",
            "observed_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    listing_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    provider_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("consensus_estimate_provider_mappings.id", ondelete="RESTRICT"), index=True
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("consensus_estimate_batches.id", ondelete="RESTRICT"), index=True
    )
    provider_id: Mapped[str] = mapped_column(String(120))
    metric: Mapped[str] = mapped_column(String(16))
    period_type: Mapped[str] = mapped_column(String(16))
    forecast_period: Mapped[str] = mapped_column(String(80))
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    low_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    high_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    analyst_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unit: Mapped[str] = mapped_column(String(32))
    snapshot_date: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source_record_id: Mapped[str] = mapped_column(String(500))
    source_ref: Mapped[str] = mapped_column(String(1000))
    revision_context: Mapped[str] = mapped_column(String(24))
    data_quality: Mapped[str] = mapped_column(String(16))
    quality_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "consensus_estimate_observations.id",
            ondelete="RESTRICT",
            name="fk_consensus_estimate_supersedes",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )


class ModelOutputImportBatch(Base):
    """Immutable receipt for one deterministic model-output workbook import."""

    __tablename__ = "model_output_import_batches"
    __table_args__ = (
        UniqueConstraint("source_digest"),
        CheckConstraint("length(source_digest) = 64", name="source_digest"),
        CheckConstraint("length(workbook_sha256) = 64", name="workbook_sha256"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_digest: Mapped[str] = mapped_column(String(64))
    workbook_sha256: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reconciliation: Mapped[dict[str, object]] = mapped_column(JSON)


class ReturnMethodologyDefinition(Base):
    """Immutable, versioned economic definition for an Expected IRR calculation."""

    __tablename__ = "return_methodology_definitions"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_return_methodology_code_version"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("perspective IN ('ENTERPRISE','EQUITY')", name="perspective"),
        CheckConstraint(
            "cross_method_policy IN ('SAME_METHOD_ONLY','CONDITIONAL_EQUITY_CROSS_METHOD')",
            name="cross_method_policy",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    cash_flow_basis: Mapped[str] = mapped_column(Text)
    perspective: Mapped[str] = mapped_column(String(20))
    entry_value_basis: Mapped[str] = mapped_column(Text)
    share_price_basis: Mapped[str] = mapped_column(Text)
    comparability_group: Mapped[str] = mapped_column(String(80))
    cross_method_policy: Mapped[str] = mapped_column(String(48))
    limitation: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelOutputSnapshot(Base):
    """Immutable normalized output snapshot; assumptions and calculations stay external."""

    __tablename__ = "model_output_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "model_key", "snapshot_key", name="uq_model_output_snapshot_identity"
        ),
        CheckConstraint(
            "snapshot_kind IN ('CURRENT_CONTRACT','LEGACY_REVISION')", name="snapshot_kind"
        ),
        CheckConstraint(
            "contract_status IN ('PASS','NOT_MAPPED','NO_CONTRACT','DATA_CHECK','HISTORICAL_ONLY')",
            name="contract_status",
        ),
        CheckConstraint(
            "output_quality IN ('COMPLETE','PARTIAL','DATA_CHECK','UNAVAILABLE')",
            name="output_quality",
        ),
        CheckConstraint(
            "(model_currency IS NULL AND currency_status = 'UNKNOWN') OR "
            "(model_currency IS NOT NULL AND currency_status = 'DOCUMENTED')",
            name="currency_status",
        ),
        CheckConstraint(
            "return_methodology_status IN ('CLASSIFIED','UNCLASSIFIED')",
            name="return_methodology_status",
        ),
        CheckConstraint(
            "(return_methodology_id IS NULL AND return_methodology_status = 'UNCLASSIFIED') OR "
            "(return_methodology_id IS NOT NULL AND return_methodology_status = 'CLASSIFIED')",
            name="return_methodology_identity",
        ),
        CheckConstraint(
            "bear_probability IS NULL OR bear_probability BETWEEN 0 AND 1",
            name="bear_probability",
        ),
        CheckConstraint(
            "base_probability IS NULL OR base_probability BETWEEN 0 AND 1",
            name="base_probability",
        ),
        CheckConstraint(
            "bull_probability IS NULL OR bull_probability BETWEEN 0 AND 1",
            name="bull_probability",
        ),
        Index("ix_model_output_snapshots_company_recorded", "company_id", "recorded_at"),
        Index("ix_model_output_snapshots_company_model", "company_id", "model_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_output_import_batches.id", ondelete="RESTRICT"), index=True
    )
    model_key: Mapped[str] = mapped_column(String(120))
    snapshot_key: Mapped[str] = mapped_column(String(200))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    snapshot_kind: Mapped[str] = mapped_column(String(24))
    contract_version: Mapped[str | None] = mapped_column(String(40))
    contract_status: Mapped[str] = mapped_column(String(24))
    output_quality: Mapped[str] = mapped_column(String(20))
    model_currency: Mapped[str | None] = mapped_column(String(3))
    currency_status: Mapped[str] = mapped_column(String(16))
    currency_source_ref: Mapped[str | None] = mapped_column(String(1000))
    return_methodology_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("return_methodology_definitions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    return_methodology_status: Mapped[str] = mapped_column(String(20), default="UNCLASSIFIED")
    return_methodology: Mapped[ReturnMethodologyDefinition | None] = relationship(lazy="joined")
    model_status: Mapped[str | None] = mapped_column(Text)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(32), default=Actor.IMPORT)
    source: Mapped[str] = mapped_column(String(1000))
    source_revision_id: Mapped[str | None] = mapped_column(String(160))
    revision_source: Mapped[str | None] = mapped_column(String(500))
    revision_type: Mapped[str | None] = mapped_column(String(300))
    source_actor: Mapped[str | None] = mapped_column(String(300))
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    field_issues: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    bear_fv: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    base_fv: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    bull_fv: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    bear_probability: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    base_probability: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    bull_probability: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    weighted_fv: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    weighted_upside: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    expected_cash_flow_irr: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    hurdle: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    expected_excess: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))
    forward_fundamental_cagr: Mapped[Decimal | None] = mapped_column(Numeric(38, 22))


class FinancialModel(Base):
    """Stable identity for one company/listing methodology pair."""

    __tablename__ = "financial_models"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "valuation_listing_id", "model_type", name="uq_financial_model_identity"
        ),
        ForeignKeyConstraint(
            ["id", "current_revision_id"],
            ["financial_model_revisions.model_id", "financial_model_revisions.id"],
            ondelete="RESTRICT",
            name="fk_financial_models_id_current_revision",
            use_alter=True,
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    valuation_listing_id: Mapped[UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="RESTRICT")
    )
    model_type: Mapped[str] = mapped_column(String(60))
    model_name: Mapped[str] = mapped_column(String(160))
    model_currency: Mapped[str] = mapped_column(String(3))
    source_model_key: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    current_revision_id: Mapped[UUID | None] = mapped_column(nullable=True)


class FinancialModelRevision(Base):
    """Accepted immutable input state and provenance for one deterministic calculation."""

    __tablename__ = "financial_model_revisions"
    __table_args__ = (
        UniqueConstraint("model_id", "revision_number", name="uq_financial_model_revision_no"),
        UniqueConstraint("model_id", "id", name="uq_financial_model_revision_identity"),
        UniqueConstraint(
            "model_id", "source_revision_id", name="uq_financial_model_source_revision"
        ),
        ForeignKeyConstraint(
            ["model_id", "base_revision_id"],
            ["financial_model_revisions.model_id", "financial_model_revisions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision_number > 0", name="revision_number"),
        CheckConstraint("actor IN ('LOCAL_USER','SYSTEM','IMPORT')", name="actor"),
        CheckConstraint(
            "model_type IN ('UFCF_DCF_10Y_FADE','OWNER_CASH_FLOW_10Y','RESIDUAL_INCOME_10Y_FADE')",
            name="model_type",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_models.id", ondelete="RESTRICT"), index=True
    )
    model_type: Mapped[str] = mapped_column(String(60))
    revision_number: Mapped[int] = mapped_column(Integer)
    base_revision_id: Mapped[UUID | None] = mapped_column(nullable=True)
    methodology_version: Mapped[str] = mapped_column(String(40))
    source_revision_id: Mapped[str | None] = mapped_column(String(160))
    contract_digest: Mapped[str | None] = mapped_column(String(64))
    proposal_author_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    proposal_authored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proposal_source_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    actor: Mapped[str] = mapped_column(String(32))
    source: Mapped[str | None] = mapped_column(String(1000))
    rationale: Mapped[str] = mapped_column(Text)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FinancialModelRevisionEvidence(Base):
    """Immutable links from an accepted model revision to canonical research state."""

    __tablename__ = "financial_model_revision_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('RESEARCH_REVISION','RESEARCH_FORECAST','THESIS_REVISION',"
            "'THESIS_CLAIM')",
            name="evidence_type",
        ),
        CheckConstraint(
            "relationship IN ('SUPPORTS','CONTRADICTS','CONTEXT')",
            name="relationship",
        ),
        CheckConstraint(
            "(evidence_type = 'RESEARCH_REVISION' AND research_revision_id IS NOT NULL "
            "AND research_forecast_id IS NULL AND thesis_revision_id IS NULL "
            "AND thesis_claim_id IS NULL) "
            "OR (evidence_type = 'RESEARCH_FORECAST' AND research_revision_id IS NULL "
            "AND research_forecast_id IS NOT NULL AND thesis_revision_id IS NULL "
            "AND thesis_claim_id IS NULL) "
            "OR (evidence_type = 'THESIS_REVISION' AND research_revision_id IS NULL "
            "AND research_forecast_id IS NULL AND thesis_revision_id IS NOT NULL "
            "AND thesis_claim_id IS NULL) "
            "OR (evidence_type = 'THESIS_CLAIM' AND research_revision_id IS NULL "
            "AND research_forecast_id IS NULL AND thesis_revision_id IS NULL "
            "AND thesis_claim_id IS NOT NULL)",
            name="one_typed_reference",
        ),
        UniqueConstraint(
            "revision_id",
            "evidence_type",
            "research_revision_id",
            "research_forecast_id",
            "thesis_revision_id",
            "thesis_claim_id",
            name="uq_model_revision_evidence_reference",
        ),
        Index("ix_model_revision_evidence_revision", "revision_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT")
    )
    evidence_type: Mapped[str] = mapped_column(String(32))
    research_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    research_forecast_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_forecasts.id", ondelete="RESTRICT"), nullable=True
    )
    thesis_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    thesis_claim_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investment_thesis_claims.id", ondelete="RESTRICT"), nullable=True
    )
    relationship: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoogleSheetsSyncRun(Base):
    """One explicit read-only poll of the configured model-contract inbox."""

    __tablename__ = "google_sheets_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CONNECTED','SUCCEEDED','PARTIAL','BLOCKED','FAILED')",
            name="status",
        ),
        CheckConstraint(
            "candidate_count >= 0 AND new_count >= 0 AND unchanged_count >= 0 AND issue_count >= 0",
            name="counts_nonnegative",
        ),
        Index("ix_google_sheets_sync_runs_started", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    spreadsheet_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spreadsheet_title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)


class GoogleSheetsSyncCandidate(Base):
    """Captured portable contract evidence and its explicit human review state."""

    __tablename__ = "google_sheets_sync_candidates"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_google_sheets_candidate_key"),
        CheckConstraint(
            "status IN ('PENDING','READY','CONFLICT','INVALID','NO_CHANGES','ACCEPTED','REJECTED')",
            name="status",
        ),
        Index("ix_google_sheets_candidates_status_observed", "status", "first_observed_at"),
        Index("ix_google_sheets_candidates_model", "model_id", "first_observed_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    spreadsheet_id: Mapped[str] = mapped_column(String(128))
    spreadsheet_title: Mapped[str] = mapped_column(String(255))
    sheet_id: Mapped[int] = mapped_column(Integer)
    sheet_title: Mapped[str] = mapped_column(String(100))
    source_row_number: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    last_seen_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "google_sheets_sync_runs.id", ondelete="SET NULL", name="fk_sheets_candidate_run"
        )
    )
    contract_text: Mapped[str] = mapped_column(Text)
    contract_data: Mapped[dict[str, object] | None] = mapped_column(JSON)
    contract_version: Mapped[str | None] = mapped_column(String(24))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    external_revision_id: Mapped[str | None] = mapped_column(String(160))
    base_revision_id: Mapped[UUID | None] = mapped_column()
    model_id: Mapped[UUID | None] = mapped_column()
    company_id: Mapped[UUID | None] = mapped_column()
    valuation_listing_id: Mapped[UUID | None] = mapped_column()
    model_type: Mapped[str | None] = mapped_column(String(60))
    model_name: Mapped[str | None] = mapped_column(String(160))
    source_model_key: Mapped[str | None] = mapped_column(String(120))
    model_currency: Mapped[str | None] = mapped_column(String(3))
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    issue: Mapped[str | None] = mapped_column(Text)
    preview_status: Mapped[str | None] = mapped_column(String(40))
    preview_data: Mapped[dict[str, object] | None] = mapped_column(JSON)
    preview_fingerprint: Mapped[str | None] = mapped_column(String(64))
    previewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "financial_model_revisions.id",
            ondelete="RESTRICT",
            name="fk_sheets_candidate_revision",
        )
    )
    reviewer: Mapped[str | None] = mapped_column(String(160))
    decision_note: Mapped[str | None] = mapped_column(Text)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DcfModelAssumptions(Base):
    """Shared base-year and per-share assumptions for the supported UFCF DCF."""

    __tablename__ = "dcf_model_assumptions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), unique=True
    )
    base_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    base_ebit_margin: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    base_tax_rate: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    base_da_to_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    base_capex_to_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    base_nwc_to_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    net_cash_debt: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    diluted_shares: Mapped[Decimal] = mapped_column(Numeric(38, 18))


class DcfScenarioAssumptions(Base):
    """Bear/Base/Bull assumptions and long-run UFCF fade endpoints."""

    __tablename__ = "dcf_scenario_assumptions"
    __table_args__ = (
        UniqueConstraint("revision_id", "scenario", name="uq_dcf_revision_scenario"),
        CheckConstraint("scenario IN ('BEAR','BASE','BULL')", name="scenario"),
        CheckConstraint("probability BETWEEN 0 AND 1", name="probability"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    scenario: Mapped[str] = mapped_column(String(8))
    probability: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    terminal_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    year10_ufcf_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    rationale: Mapped[str] = mapped_column(Text)


class DcfYearAssumption(Base):
    """Editable operating and discount assumptions for years one through five."""

    __tablename__ = "dcf_year_assumptions"
    __table_args__ = (
        UniqueConstraint("scenario_id", "forecast_year", name="uq_dcf_scenario_year_input"),
        CheckConstraint("forecast_year BETWEEN 1 AND 5", name="forecast_year"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("dcf_scenario_assumptions.id", ondelete="RESTRICT"), index=True
    )
    forecast_year: Mapped[int] = mapped_column(Integer)
    revenue_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    ebit_margin: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    da_to_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    capex_to_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    nwc_to_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(38, 18))


class DcfTailGrowthAssumption(Base):
    """Explicit annual UFCF growth assumptions for source models with a non-linear tail."""

    __tablename__ = "dcf_tail_growth_assumptions"
    __table_args__ = (
        UniqueConstraint("scenario_id", "forecast_year", name="uq_dcf_tail_growth_year"),
        CheckConstraint("forecast_year BETWEEN 6 AND 10", name="forecast_year"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("dcf_scenario_assumptions.id", ondelete="RESTRICT"), index=True
    )
    forecast_year: Mapped[int] = mapped_column(Integer)
    ufcf_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))


class DcfProjection(Base):
    """Immutable server-calculated operating forecast, stored apart from assumptions."""

    __tablename__ = "dcf_projections"
    __table_args__ = (
        UniqueConstraint("scenario_id", "forecast_year", name="uq_dcf_scenario_projection"),
        CheckConstraint("forecast_year BETWEEN 1 AND 10", name="forecast_year"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("dcf_scenario_assumptions.id", ondelete="RESTRICT"), index=True
    )
    forecast_year: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    ebit: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    nopat: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    depreciation_amortization: Mapped[Decimal | None] = mapped_column(
        Numeric(38, 18), nullable=True
    )
    capex: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    net_working_capital: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    change_in_nwc: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    unlevered_free_cash_flow: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    revenue_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    discount_factor: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    present_value_ufcf: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    terminal_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)


class OwnerCashFlowAssumptions(Base):
    """Shared starting revenue, net cash and share-count inputs for owner-CF models."""

    __tablename__ = "owner_cash_flow_assumptions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), unique=True
    )
    base_revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    net_cash: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    diluted_shares: Mapped[Decimal] = mapped_column(Numeric(38, 18))


class OwnerCashFlowScenarioAssumptions(Base):
    """Method-specific scenario economics; not shared with operating DCF scenarios."""

    __tablename__ = "owner_cash_flow_scenarios"
    __table_args__ = (
        UniqueConstraint("revision_id", "scenario", name="uq_owner_cf_revision_scenario"),
        CheckConstraint("scenario IN ('BEAR','BASE','BULL')", name="scenario"),
        CheckConstraint("probability BETWEEN 0 AND 1", name="probability"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    scenario: Mapped[str] = mapped_column(String(8))
    probability: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    required_return: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    terminal_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    rationale: Mapped[str] = mapped_column(Text)


class OwnerCashFlowYearAssumption(Base):
    __tablename__ = "owner_cash_flow_year_assumptions"
    __table_args__ = (
        UniqueConstraint("scenario_id", "forecast_year", name="uq_owner_cf_scenario_year"),
        CheckConstraint("forecast_year BETWEEN 1 AND 10", name="forecast_year"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("owner_cash_flow_scenarios.id", ondelete="RESTRICT"), index=True
    )
    forecast_year: Mapped[int] = mapped_column(Integer)
    revenue_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    owner_cash_flow_margin: Mapped[Decimal] = mapped_column(Numeric(38, 18))


class OwnerCashFlowProjection(Base):
    __tablename__ = "owner_cash_flow_projections"
    __table_args__ = (
        UniqueConstraint("scenario_id", "forecast_year", name="uq_owner_cf_projection_year"),
        CheckConstraint("forecast_year BETWEEN 1 AND 10", name="forecast_year"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("owner_cash_flow_scenarios.id", ondelete="RESTRICT"), index=True
    )
    forecast_year: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    owner_cash_flow: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    owner_cash_flow_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    present_value_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    terminal_value_per_share: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))


class ResidualIncomeAssumptions(Base):
    """Book-value and payout inputs for a distinct financial-company method."""

    __tablename__ = "residual_income_assumptions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), unique=True
    )
    current_book_value_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    payout_ratio: Mapped[Decimal] = mapped_column(Numeric(38, 18))


class ResidualIncomeScenarioAssumptions(Base):
    __tablename__ = "residual_income_scenarios"
    __table_args__ = (
        UniqueConstraint("revision_id", "scenario", name="uq_ri_revision_scenario"),
        CheckConstraint("scenario IN ('BEAR','BASE','BULL')", name="scenario"),
        CheckConstraint("probability BETWEEN 0 AND 1", name="probability"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    scenario: Mapped[str] = mapped_column(String(8))
    probability: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    starting_roe: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    cost_of_equity: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    terminal_growth: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    mature_roe: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    rationale: Mapped[str] = mapped_column(Text)


class ResidualIncomeProjection(Base):
    __tablename__ = "residual_income_projections"
    __table_args__ = (
        UniqueConstraint("scenario_id", "forecast_year", name="uq_ri_projection_year"),
        CheckConstraint("forecast_year BETWEEN 1 AND 10", name="forecast_year"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("residual_income_scenarios.id", ondelete="RESTRICT"), index=True
    )
    forecast_year: Mapped[int] = mapped_column(Integer)
    beginning_book_value_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    return_on_equity: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    net_income_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    dividend_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    ending_book_value_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    residual_income_per_share: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    present_value_residual_income: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    terminal_value_per_share: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))


class FinancialModelOutput(Base):
    """Normalized deterministic output bundle for one accepted model revision."""

    __tablename__ = "financial_model_outputs"
    __table_args__ = (
        UniqueConstraint("revision_id", name="uq_financial_model_output_revision"),
        CheckConstraint("status IN ('COMPLETE','PARTIAL')", name="status"),
        CheckConstraint(
            "price_status IN ('FRESH','STALE','QUALITY_CHECK','NO_DATA',"
            "'CURRENCY_MISMATCH','CURRENCY_UNKNOWN')",
            name="price_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    return_methodology_id: Mapped[UUID] = mapped_column(
        ForeignKey("return_methodology_definitions.id", ondelete="RESTRICT"), index=True
    )
    return_methodology: Mapped[ReturnMethodologyDefinition] = relationship(lazy="joined")
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    model_currency: Mapped[str] = mapped_column(String(3))
    price_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("price_observations.id", ondelete="RESTRICT"), nullable=True
    )
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    price_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_status: Mapped[str] = mapped_column(String(24))
    price_unavailable_reason: Mapped[str | None] = mapped_column(Text)
    irr_unavailable_reason: Mapped[str | None] = mapped_column(Text)
    bear_fv: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    base_fv: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    bull_fv: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    bear_probability: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    base_probability: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    bull_probability: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    weighted_fv: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    weighted_upside: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    expected_cash_flow_irr: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    hurdle: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    expected_excess: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    forward_fundamental_cagr: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)


class FinancialModelMigrationAssessment(Base):
    """Immutable workbook-to-native mapping and parity assessment for one source revision."""

    __tablename__ = "financial_model_migration_assessments"
    __table_args__ = (
        UniqueConstraint(
            "source_model_key",
            "source_workbook_sha256",
            "mapping_version",
            name="uq_financial_model_migration_source",
        ),
        CheckConstraint("length(source_workbook_sha256) = 64", name="source_workbook_sha256"),
        CheckConstraint(
            "status IN ('PARITY_PASS','PARTIAL_MAPPING','DATA_CHECK','BLOCKED')", name="status"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_models.id", ondelete="RESTRICT"), index=True
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"), index=True
    )
    source_model_key: Mapped[str] = mapped_column(String(120))
    source_workbook_sha256: Mapped[str] = mapped_column(String(64))
    mapping_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    input_digest: Mapped[str] = mapped_column(String(64))
    report: Mapped[dict[str, object]] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@event.listens_for(Session, "before_flush")
def protect_ranking_history(session: Session, flush_context: object, instances: object) -> None:
    """Ranking definitions are versioned; run observations are append-only."""
    immutable = (
        RankingRun,
        RankingEntry,
        ExecutionPaceRun,
        ExecutionPaceDecision,
    )
    for item in session.dirty.union(session.deleted):
        if isinstance(item, immutable):
            raise ValueError("Ranking history is append-only")
        if isinstance(item, RankingDefinition):
            raise ValueError("Ranking definitions are immutable; add a new version")


@event.listens_for(Session, "before_flush")
def protect_history(session: Session, flush_context: object, instances: object) -> None:
    """API/ORM writes cannot rewrite history. Raw administrator SQL is outside this boundary."""
    immutable = (
        LifecycleEvent,
        HoldingSnapshot,
        HoldingPosition,
        CashPosition,
        ScoreAssessment,
        LegacyImportBatch,
        ExternalIngestionAttempt,
        ReportedFundamentalBatch,
        ReportedFundamentalObservation,
        SourceDocumentBatch,
        SourceDocument,
        CompanyProviderIdentifier,
        MarketDataBatch,
        ConsensusEstimateProviderMapping,
        ConsensusEstimateBatch,
        ConsensusEstimateObservation,
        PriceObservation,
        CorporateAction,
        PriceRegimeSnapshot,
        FxObservation,
        ExternalRawPayload,
        ResearchPriorityInput,
        CandidatePipelineRevision,
        CandidatePipelineGateAssessment,
        CandidatePipelineEvidence,
        ResearchRevision,
        ResearchForecast,
        ResearchAssessment,
        ResearchEvidence,
        ResearchQueueCompletion,
        ResearchTriggerPublicationLink,
        ResearchAgentWorkEvent,
        InvestmentThesisRevision,
        InvestmentThesisClaim,
        InvestmentThesisEvidence,
        RiskAssessmentRevision,
        RiskAssessmentFinding,
        RiskAssessmentEvidence,
        ModelOutputImportBatch,
        ModelOutputSnapshot,
        FinancialModelRevision,
        FinancialModelRevisionEvidence,
        DcfModelAssumptions,
        DcfScenarioAssumptions,
        DcfYearAssumption,
        DcfTailGrowthAssumption,
        DcfProjection,
        OwnerCashFlowAssumptions,
        OwnerCashFlowScenarioAssumptions,
        OwnerCashFlowYearAssumption,
        OwnerCashFlowProjection,
        ResidualIncomeAssumptions,
        ResidualIncomeScenarioAssumptions,
        ResidualIncomeProjection,
        FinancialModelOutput,
        FinancialModelMigrationAssessment,
        ReturnMethodologyDefinition,
    )
    for item in session.dirty.union(session.deleted):
        if isinstance(item, immutable):
            raise ValueError("Historical observations are append-only")
        if isinstance(item, GoogleSheetsSyncRun):
            if item in session.deleted:
                raise ValueError("Google Sheets synchronization runs are retained")
            completed_history = inspect(item).attrs.completed_at.history
            previously_completed = (
                completed_history.deleted[0]
                if completed_history.has_changes() and completed_history.deleted
                else (None if completed_history.has_changes() else item.completed_at)
            )
            if previously_completed is not None:
                raise ValueError("Completed Google Sheets synchronization runs are immutable")
        if isinstance(item, GoogleSheetsSyncCandidate):
            if item in session.deleted:
                raise ValueError("Captured Google Sheets contract evidence is retained")
            model_candidate_evidence = (
                "idempotency_key",
                "spreadsheet_id",
                "spreadsheet_title",
                "sheet_id",
                "sheet_title",
                "source_row_number",
                "source_url",
                "contract_text",
                "contract_data",
                "contract_version",
                "content_fingerprint",
                "raw_sha256",
                "external_revision_id",
                "base_revision_id",
                "model_id",
                "company_id",
                "valuation_listing_id",
                "model_type",
                "model_name",
                "source_model_key",
                "model_currency",
                "rationale",
                "first_observed_at",
            )
            if any(
                inspect(item).attrs[name].history.has_changes() for name in model_candidate_evidence
            ):
                raise ValueError("Captured Google Sheets contract evidence is immutable")
            status_history = inspect(item).attrs.status.history
            prior_status = status_history.deleted[0] if status_history.deleted else item.status
            if prior_status in {"ACCEPTED", "REJECTED"} and status_history.has_changes():
                raise ValueError("Final Google Sheets review decisions are immutable")
            model_final_decision_fields = (
                "accepted_revision_id",
                "reviewer",
                "decision_note",
                "accepted_at",
                "rejected_at",
            )
            if prior_status in {"ACCEPTED", "REJECTED"} and any(
                inspect(item).attrs[name].history.has_changes()
                for name in model_final_decision_fields
            ):
                raise ValueError("Final Google Sheets review decisions are immutable")
        if isinstance(item, GoogleSheetsRiskSyncRun):
            if item in session.deleted:
                raise ValueError("Google Sheets risk synchronization runs are retained")
            completed_history = inspect(item).attrs.completed_at.history
            previously_completed = (
                completed_history.deleted[0]
                if completed_history.has_changes() and completed_history.deleted
                else (None if completed_history.has_changes() else item.completed_at)
            )
            if previously_completed is not None:
                raise ValueError("Completed Google Sheets risk synchronization runs are immutable")
        if isinstance(item, GoogleSheetsRiskSyncCandidate):
            if item in session.deleted:
                raise ValueError("Captured risk-assessment contract evidence is retained")
            risk_candidate_evidence = (
                "idempotency_key",
                "spreadsheet_id",
                "spreadsheet_title",
                "sheet_id",
                "sheet_title",
                "source_row_number",
                "source_url",
                "contract_text",
                "contract_data",
                "contract_version",
                "content_fingerprint",
                "raw_sha256",
                "portfolio_id",
                "stream_key",
                "external_revision_id",
                "author_id",
                "source_id",
                "source_reference",
                "authored_at",
                "published_at",
                "summary",
                "findings_count",
                "first_observed_at",
            )
            if any(
                inspect(item).attrs[name].history.has_changes() for name in risk_candidate_evidence
            ):
                raise ValueError("Captured risk-assessment contract evidence is immutable")
            status_history = inspect(item).attrs.status.history
            prior_status = status_history.deleted[0] if status_history.deleted else item.status
            if prior_status in {"ACCEPTED", "REJECTED"} and status_history.has_changes():
                raise ValueError("Final Google Sheets risk review decisions are immutable")
            risk_final_decision_fields = (
                "reviewer",
                "reviewer_note",
                "accepted_revision_id",
                "accepted_at",
                "rejected_at",
            )
            if prior_status in {"ACCEPTED", "REJECTED"} and any(
                inspect(item).attrs[name].history.has_changes()
                for name in risk_final_decision_fields
            ):
                raise ValueError("Final Google Sheets risk review decisions are immutable")
        if isinstance(item, GoogleSheetsResearchSyncRun):
            if item in session.deleted:
                raise ValueError("Google Sheets research synchronization runs are retained")
            completed_history = inspect(item).attrs.completed_at.history
            previously_completed = (
                completed_history.deleted[0]
                if completed_history.has_changes() and completed_history.deleted
                else (None if completed_history.has_changes() else item.completed_at)
            )
            if previously_completed is not None:
                raise ValueError(
                    "Completed Google Sheets research synchronization runs are immutable"
                )
        if isinstance(item, GoogleSheetsResearchSyncCandidate):
            if item in session.deleted:
                raise ValueError("Captured research and thesis contracts are retained")
            research_candidate_evidence = (
                "idempotency_key",
                "domain",
                "spreadsheet_id",
                "spreadsheet_title",
                "sheet_id",
                "sheet_title",
                "source_row_number",
                "source_url",
                "contract_text",
                "contract_data",
                "contract_version",
                "content_fingerprint",
                "raw_sha256",
                "company_id",
                "security_id",
                "stream_key",
                "external_revision_id",
                "base_revision_id",
                "author_id",
                "source_id",
                "source_reference",
                "observed_at",
                "rationale",
                "item_count",
                "evidence_count",
                "first_observed_at",
            )
            if any(
                inspect(item).attrs[name].history.has_changes()
                for name in research_candidate_evidence
            ):
                raise ValueError("Captured research and thesis contract evidence is immutable")
            status_history = inspect(item).attrs.status.history
            prior_status = status_history.deleted[0] if status_history.deleted else item.status
            if prior_status in {"ACCEPTED", "REJECTED"} and status_history.has_changes():
                raise ValueError("Final Google Sheets research review decisions are immutable")
            research_final_decision_fields = (
                "accepted_research_revision_id",
                "accepted_thesis_revision_id",
                "reviewer",
                "reviewer_note",
                "accepted_at",
                "rejected_at",
            )
            if prior_status in {"ACCEPTED", "REJECTED"} and any(
                inspect(item).attrs[name].history.has_changes()
                for name in research_final_decision_fields
            ):
                raise ValueError("Final Google Sheets research review decisions are immutable")
        if isinstance(item, FinancialModel):
            if item in session.deleted:
                raise ValueError("Financial model identities cannot be deleted")
            identity = (
                "company_id",
                "valuation_listing_id",
                "model_type",
                "model_name",
                "model_currency",
                "source_model_key",
            )
            if any(inspect(item).attrs[name].history.has_changes() for name in identity):
                raise ValueError("Financial model identity is immutable")
        if isinstance(item, ReturnMethodologyDefinition):
            raise ValueError("Return methodology definitions are immutable; add a new version")
        if isinstance(item, ScoreDefinition):
            raise ValueError("Score definitions are immutable; add a new version")
        if isinstance(item, TargetRevision):
            history = inspect(item).attrs.status.history
            was_accepted = "ACCEPTED" in history.deleted or (
                not history.has_changes() and item.status == "ACCEPTED"
            )
            if was_accepted:
                raise ValueError("Accepted target revisions are immutable")
    for item in session.new.union(session.dirty).union(session.deleted):
        if isinstance(item, FinancialModelOutput) and item.return_methodology_id is None:
            revision = session.get(FinancialModelRevision, item.revision_id)
            if revision is None:
                raise ValueError("Financial model output requires an accepted model revision")
            code = native_methodology_for_revision(
                str(revision.model_type), revision.methodology_version
            )
            if code is None:
                raise ValueError("Financial model output has no registered return methodology")
            item.return_methodology_id = DEFINITION_ID_BY_CODE[code]
        if isinstance(item, ScoreDefinition) and item in session.deleted:
            raise ValueError("Score definitions cannot be deleted")
        if isinstance(item, TargetAllocation):
            parent = session.get(TargetRevision, item.revision_id)
            if parent is not None and parent.status == "ACCEPTED":
                raise ValueError("Accepted target allocations are immutable")
        if isinstance(item, (HoldingPosition, CashPosition)) and item in session.new:
            parent_snapshot = session.get(HoldingSnapshot, item.snapshot_id)
            if (
                parent_snapshot is not None
                and parent_snapshot not in session.new
                and item.snapshot_id not in session.info.get("new_snapshot_ids", set())
            ):
                raise ValueError("Cannot add positions to a historical snapshot")
