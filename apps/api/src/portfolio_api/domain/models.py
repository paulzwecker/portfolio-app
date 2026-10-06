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
from sqlalchemy.orm import Mapped, Session, mapped_column

from portfolio_api.database import Base


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
    actor: Mapped[str] = mapped_column(String(32))
    source: Mapped[str | None] = mapped_column(String(1000))
    rationale: Mapped[str] = mapped_column(Text)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


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
        ModelOutputImportBatch,
        ModelOutputSnapshot,
        FinancialModelRevision,
        DcfModelAssumptions,
        DcfScenarioAssumptions,
        DcfYearAssumption,
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
    )
    for item in session.dirty.union(session.deleted):
        if isinstance(item, immutable):
            raise ValueError("Historical observations are append-only")
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
