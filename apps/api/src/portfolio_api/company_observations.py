"""Canonical company operating metrics, management guidance, and model-driver reads."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BeforeValidator, Field
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from portfolio_api.database import Base
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import Company, FinancialModel, FinancialModelRevision, now

ObservationDecimal = Annotated[
    s.FixedDecimal,
    BeforeValidator(s.exact),
    Field(max_digits=38, decimal_places=12),
]

PERIOD_TYPES = ("DATE", "MONTH", "QUARTER", "FY", "TTM", "EVENT")
QUALIFIERS = ("EQ", "APPROX", "GT", "GTE", "LT", "LTE")
QUALITY_STATES = ("VERIFIED", "PROVISIONAL", "CONFLICTED", "RESTATED")
GUIDANCE_STATES = ("ACTIVE", "SUPERSEDED", "WITHDRAWN", "ACHIEVED")
DRIVER_SCENARIOS = ("BEAR", "BASE", "BULL")


def _not_found(detail: str) -> Exception:
    # Import lazily so ORM metadata registration never imports the service layer
    # while domain schemas are still being initialized.
    from portfolio_api.domain.services import DomainError

    return DomainError(detail, 404)


class CompanyMetricDefinition(Base):
    """Stable semantic identity for a reusable or company-specific metric."""

    __tablename__ = "company_metric_definitions"
    __table_args__ = (
        UniqueConstraint("metric_key", name="uq_company_metric_definition_key"),
        CheckConstraint("length(metric_key) > 0", name="metric_key"),
        CheckConstraint(
            "category IN ('FINANCIAL','CAPITAL_STRUCTURE','OPERATING','CUSTOMER','CAPACITY',"
            "'PRODUCT','MARKET_SHARE','MARKET_EXPOSURE','SEGMENT','BACKLOG','QUALITY','OTHER')",
            name="category",
        ),
        CheckConstraint(
            "value_kind IN ('CURRENCY','PERCENT','COUNT','RATIO','TEXT')",
            name="value_kind",
        ),
        CheckConstraint("canonical_scale > 0", name="canonical_scale"),
        CheckConstraint(
            "currency_policy IN ('NONE','OPTIONAL','REQUIRED')",
            name="currency_policy",
        ),
        CheckConstraint(
            "default_period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name="default_period_type",
        ),
        Index("ix_company_metric_definitions_company_active", "company_id", "active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    metric_key: Mapped[str] = mapped_column(String(160))
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    value_kind: Mapped[str] = mapped_column(String(16))
    canonical_unit: Mapped[str] = mapped_column(String(64))
    canonical_scale: Mapped[Decimal] = mapped_column(Numeric(38, 12), default=Decimal("1"))
    currency_policy: Mapped[str] = mapped_column(String(16), default="NONE")
    aggregation_semantics: Mapped[str] = mapped_column(String(40))
    default_period_type: Mapped[str] = mapped_column(String(16))
    default_basis: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scope_dimensions: Mapped[list[str]] = mapped_column(JSON, default=list)
    actuals_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    guidance_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    consensus_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_driver_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanyMetricObservation(Base):
    """Append-only factual company KPI observation outside statement fundamentals."""

    __tablename__ = "company_metric_observations"
    __table_args__ = (
        UniqueConstraint(
            "external_observation_id",
            name="uq_company_metric_observation_external_id",
        ),
        CheckConstraint(
            "period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name="period_type",
        ),
        CheckConstraint("period_start <= period_end", name="period_dates"),
        CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name="fiscal_quarter",
        ),
        CheckConstraint(
            "value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE')",
            name="value_qualifier",
        ),
        CheckConstraint("scale > 0", name="scale"),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint(
            "quality_status IN ('VERIFIED','PROVISIONAL','CONFLICTED','RESTATED')",
            name="quality_status",
        ),
        Index(
            "ix_company_metric_observations_company_metric_period",
            "company_id",
            "metric_definition_id",
            "period_end",
        ),
        Index(
            "ix_company_metric_observations_company_recorded",
            "company_id",
            "recorded_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    external_observation_id: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    metric_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_metric_definitions.id", ondelete="RESTRICT"), index=True
    )
    period_type: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    value_qualifier: Mapped[str] = mapped_column(String(16), default="EQ")
    unit: Mapped[str] = mapped_column(String(64))
    scale: Mapped[Decimal] = mapped_column(Numeric(38, 12), default=Decimal("1"))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    basis: Mapped[str] = mapped_column(String(120))
    scope_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80))
    source_reference: Mapped[str] = mapped_column(String(2000))
    quality_status: Mapped[str] = mapped_column(String(16), default="VERIFIED")
    quality_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("company_metric_observations.id", ondelete="RESTRICT"),
        unique=True,
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompanyGuidanceObservation(Base):
    """Append-only management guidance, separate from facts and provider consensus."""

    __tablename__ = "company_guidance_observations"
    __table_args__ = (
        UniqueConstraint("external_guidance_id", name="uq_company_guidance_external_id"),
        CheckConstraint(
            "period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name="period_type",
        ),
        CheckConstraint("period_start <= period_end", name="period_dates"),
        CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name="fiscal_quarter",
        ),
        CheckConstraint(
            "value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE','RANGE')",
            name="value_qualifier",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','SUPERSEDED','WITHDRAWN','ACHIEVED')",
            name="status",
        ),
        CheckConstraint(
            "status = 'WITHDRAWN' OR "
            "lower_value IS NOT NULL OR midpoint_value IS NOT NULL OR upper_value IS NOT NULL",
            name="value_or_withdrawn",
        ),
        CheckConstraint(
            "lower_value IS NULL OR upper_value IS NULL OR lower_value <= upper_value",
            name="range_order",
        ),
        CheckConstraint("scale > 0", name="scale"),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency"),
        Index(
            "ix_company_guidance_company_metric_period",
            "company_id",
            "metric_definition_id",
            "period_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    external_guidance_id: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    metric_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_metric_definitions.id", ondelete="RESTRICT"), index=True
    )
    period_type: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lower_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    midpoint_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    upper_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    value_qualifier: Mapped[str] = mapped_column(String(16), default="RANGE")
    unit: Mapped[str] = mapped_column(String(64))
    scale: Mapped[Decimal] = mapped_column(Numeric(38, 12), default=Decimal("1"))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    basis: Mapped[str] = mapped_column(String(120))
    scope_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80))
    source_reference: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    supersedes_guidance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("company_guidance_observations.id", ondelete="RESTRICT"),
        unique=True,
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FinancialModelDriverProjection(Base):
    """Accepted company-specific KPI path tied to one financial-model revision."""

    __tablename__ = "financial_model_driver_projections"
    __table_args__ = (
        UniqueConstraint("external_driver_id", name="uq_financial_model_driver_external_id"),
        ForeignKeyConstraint(
            ["model_id", "revision_id"],
            ["financial_model_revisions.model_id", "financial_model_revisions.id"],
            ondelete="RESTRICT",
            name="fk_financial_model_driver_revision",
        ),
        CheckConstraint("scenario IN ('BEAR','BASE','BULL')", name="scenario"),
        CheckConstraint(
            "period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name="period_type",
        ),
        CheckConstraint("period_start <= period_end", name="period_dates"),
        CheckConstraint("forecast_year > 0", name="forecast_year"),
        CheckConstraint(
            "value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE')",
            name="value_qualifier",
        ),
        CheckConstraint("scale > 0", name="scale"),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency"),
        Index(
            "ix_financial_model_driver_revision_metric",
            "revision_id",
            "metric_definition_id",
            "forecast_year",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    external_driver_id: Mapped[str] = mapped_column(String(200))
    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_models.id", ondelete="RESTRICT"), index=True
    )
    revision_id: Mapped[UUID] = mapped_column(index=True)
    scenario: Mapped[str] = mapped_column(String(8))
    metric_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_metric_definitions.id", ondelete="RESTRICT"), index=True
    )
    forecast_year: Mapped[int] = mapped_column(Integer)
    period_type: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    value_qualifier: Mapped[str] = mapped_column(String(16), default="EQ")
    unit: Mapped[str] = mapped_column(String(64))
    scale: Mapped[Decimal] = mapped_column(Numeric(38, 12), default=Decimal("1"))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    basis: Mapped[str] = mapped_column(String(120))
    scope_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompanyMetricDefinitionRead(s.Contract):
    id: UUID
    metric_id: str
    company_id: UUID | None
    display_name: str
    category: str
    value_kind: str
    canonical_unit: str
    canonical_scale: ObservationDecimal
    currency_policy: str
    aggregation_semantics: str
    default_period_type: str
    default_basis: str | None
    scope_dimensions: list[str]
    actuals_allowed: bool
    guidance_allowed: bool
    consensus_allowed: bool
    model_driver_allowed: bool
    active: bool
    description: str
    source_reference: str | None
    created_at: datetime
    deprecated_at: datetime | None


class CompanyMetricObservationRead(s.Contract):
    id: UUID
    external_observation_id: str
    company_id: UUID
    metric_definition_id: UUID
    metric_id: str
    period_type: str
    period_start: date
    period_end: date
    fiscal_year: int | None
    fiscal_quarter: int | None
    value: ObservationDecimal
    value_qualifier: str
    unit: str
    scale: ObservationDecimal
    currency: s.Currency | None
    basis: str
    scope_json: dict[str, object]
    reported_at: datetime | None
    source_type: str
    source_reference: str
    quality_status: str
    quality_reason: str | None
    supersedes_observation_id: UUID | None
    is_current: bool
    recorded_at: datetime


class CompanyGuidanceObservationRead(s.Contract):
    id: UUID
    external_guidance_id: str
    company_id: UUID
    metric_definition_id: UUID
    metric_id: str
    period_type: str
    period_start: date
    period_end: date
    fiscal_year: int | None
    fiscal_quarter: int | None
    lower_value: ObservationDecimal | None
    midpoint_value: ObservationDecimal | None
    upper_value: ObservationDecimal | None
    value_qualifier: str
    unit: str
    scale: ObservationDecimal
    currency: s.Currency | None
    basis: str
    scope_json: dict[str, object]
    issued_at: datetime | None
    source_type: str
    source_reference: str
    status: str
    supersedes_guidance_id: UUID | None
    is_current: bool
    recorded_at: datetime


class FinancialModelDriverProjectionRead(s.Contract):
    id: UUID
    external_driver_id: str
    model_id: UUID
    revision_id: UUID
    scenario: Literal["BEAR", "BASE", "BULL"]
    metric_definition_id: UUID
    metric_id: str
    forecast_year: int
    period_type: str
    period_start: date
    period_end: date
    value: ObservationDecimal
    value_qualifier: str
    unit: str
    scale: ObservationDecimal
    currency: s.Currency | None
    basis: str
    scope_json: dict[str, object]
    rationale: str
    recorded_at: datetime


def _definition_read(row: CompanyMetricDefinition) -> CompanyMetricDefinitionRead:
    return CompanyMetricDefinitionRead(
        id=row.id,
        metric_id=row.metric_key,
        company_id=row.company_id,
        display_name=row.display_name,
        category=row.category,
        value_kind=row.value_kind,
        canonical_unit=row.canonical_unit,
        canonical_scale=row.canonical_scale,
        currency_policy=row.currency_policy,
        aggregation_semantics=row.aggregation_semantics,
        default_period_type=row.default_period_type,
        default_basis=row.default_basis,
        scope_dimensions=row.scope_dimensions,
        actuals_allowed=row.actuals_allowed,
        guidance_allowed=row.guidance_allowed,
        consensus_allowed=row.consensus_allowed,
        model_driver_allowed=row.model_driver_allowed,
        active=row.active,
        description=row.description,
        source_reference=row.source_reference,
        created_at=row.created_at,
        deprecated_at=row.deprecated_at,
    )


def metric_definitions(
    session: Session,
    company_id: UUID | None = None,
    include_deprecated: bool = False,
) -> list[CompanyMetricDefinitionRead]:
    if company_id is not None and session.get(Company, company_id) is None:
        raise _not_found("Company not found")
    statement = select(CompanyMetricDefinition)
    if company_id is not None:
        statement = statement.where(
            or_(
                CompanyMetricDefinition.company_id.is_(None),
                CompanyMetricDefinition.company_id == company_id,
            )
        )
    if not include_deprecated:
        statement = statement.where(
            CompanyMetricDefinition.active.is_(True),
            CompanyMetricDefinition.deprecated_at.is_(None),
        )
    rows = session.scalars(
        statement.order_by(
            CompanyMetricDefinition.company_id.nullsfirst(),
            CompanyMetricDefinition.metric_key,
        )
    ).all()
    return [_definition_read(row) for row in rows]


def company_metric_history(
    session: Session,
    company_id: UUID,
    metric_id: str | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    limit: int = 500,
) -> list[CompanyMetricObservationRead]:
    if session.get(Company, company_id) is None:
        raise _not_found("Company not found")
    statement = (
        select(CompanyMetricObservation, CompanyMetricDefinition)
        .join(
            CompanyMetricDefinition,
            CompanyMetricDefinition.id == CompanyMetricObservation.metric_definition_id,
        )
        .where(CompanyMetricObservation.company_id == company_id)
    )
    if metric_id is not None:
        statement = statement.where(CompanyMetricDefinition.metric_key == metric_id)
    if as_of is not None:
        statement = statement.where(CompanyMetricObservation.period_end <= as_of)
    if known_at is not None:
        statement = statement.where(
            CompanyMetricObservation.recorded_at <= known_at,
            or_(
                CompanyMetricObservation.reported_at.is_(None),
                CompanyMetricObservation.reported_at <= known_at,
            ),
        )
    rows = session.execute(
        statement.order_by(
            CompanyMetricObservation.period_end.desc(),
            CompanyMetricObservation.recorded_at.desc(),
            CompanyMetricObservation.id,
        ).limit(limit)
    ).all()
    supersession_statement = select(CompanyMetricObservation.supersedes_observation_id).where(
        CompanyMetricObservation.company_id == company_id,
        CompanyMetricObservation.supersedes_observation_id.is_not(None),
    )
    if as_of is not None:
        supersession_statement = supersession_statement.where(
            CompanyMetricObservation.period_end <= as_of
        )
    if known_at is not None:
        supersession_statement = supersession_statement.where(
            CompanyMetricObservation.recorded_at <= known_at,
            or_(
                CompanyMetricObservation.reported_at.is_(None),
                CompanyMetricObservation.reported_at <= known_at,
            ),
        )
    superseded = set(session.scalars(supersession_statement))
    return [
        CompanyMetricObservationRead(
            id=row.id,
            external_observation_id=row.external_observation_id,
            company_id=row.company_id,
            metric_definition_id=row.metric_definition_id,
            metric_id=definition.metric_key,
            period_type=row.period_type,
            period_start=row.period_start,
            period_end=row.period_end,
            fiscal_year=row.fiscal_year,
            fiscal_quarter=row.fiscal_quarter,
            value=row.value,
            value_qualifier=row.value_qualifier,
            unit=row.unit,
            scale=row.scale,
            currency=row.currency,
            basis=row.basis,
            scope_json=row.scope_json,
            reported_at=row.reported_at,
            source_type=row.source_type,
            source_reference=row.source_reference,
            quality_status=row.quality_status,
            quality_reason=row.quality_reason,
            supersedes_observation_id=row.supersedes_observation_id,
            is_current=row.id not in superseded,
            recorded_at=row.recorded_at,
        )
        for row, definition in rows
    ]


def company_guidance_history(
    session: Session,
    company_id: UUID,
    metric_id: str | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    current_only: bool = False,
    limit: int = 500,
) -> list[CompanyGuidanceObservationRead]:
    if session.get(Company, company_id) is None:
        raise _not_found("Company not found")
    statement = (
        select(CompanyGuidanceObservation, CompanyMetricDefinition)
        .join(
            CompanyMetricDefinition,
            CompanyMetricDefinition.id == CompanyGuidanceObservation.metric_definition_id,
        )
        .where(CompanyGuidanceObservation.company_id == company_id)
    )
    if metric_id is not None:
        statement = statement.where(CompanyMetricDefinition.metric_key == metric_id)
    if as_of is not None:
        statement = statement.where(CompanyGuidanceObservation.period_end <= as_of)
    if known_at is not None:
        statement = statement.where(
            CompanyGuidanceObservation.recorded_at <= known_at,
            or_(
                CompanyGuidanceObservation.issued_at.is_(None),
                CompanyGuidanceObservation.issued_at <= known_at,
            ),
        )
    rows = session.execute(
        statement.order_by(
            CompanyGuidanceObservation.period_end.desc(),
            CompanyGuidanceObservation.recorded_at.desc(),
            CompanyGuidanceObservation.id,
        ).limit(limit)
    ).all()
    supersession_statement = select(CompanyGuidanceObservation.supersedes_guidance_id).where(
        CompanyGuidanceObservation.company_id == company_id,
        CompanyGuidanceObservation.supersedes_guidance_id.is_not(None),
    )
    if as_of is not None:
        supersession_statement = supersession_statement.where(
            CompanyGuidanceObservation.period_end <= as_of
        )
    if known_at is not None:
        supersession_statement = supersession_statement.where(
            CompanyGuidanceObservation.recorded_at <= known_at,
            or_(
                CompanyGuidanceObservation.issued_at.is_(None),
                CompanyGuidanceObservation.issued_at <= known_at,
            ),
        )
    superseded = set(session.scalars(supersession_statement))
    result = [
        CompanyGuidanceObservationRead(
            id=row.id,
            external_guidance_id=row.external_guidance_id,
            company_id=row.company_id,
            metric_definition_id=row.metric_definition_id,
            metric_id=definition.metric_key,
            period_type=row.period_type,
            period_start=row.period_start,
            period_end=row.period_end,
            fiscal_year=row.fiscal_year,
            fiscal_quarter=row.fiscal_quarter,
            lower_value=row.lower_value,
            midpoint_value=row.midpoint_value,
            upper_value=row.upper_value,
            value_qualifier=row.value_qualifier,
            unit=row.unit,
            scale=row.scale,
            currency=row.currency,
            basis=row.basis,
            scope_json=row.scope_json,
            issued_at=row.issued_at,
            source_type=row.source_type,
            source_reference=row.source_reference,
            status=row.status,
            supersedes_guidance_id=row.supersedes_guidance_id,
            is_current=row.id not in superseded,
            recorded_at=row.recorded_at,
        )
        for row, definition in rows
    ]
    if current_only:
        return [row for row in result if row.is_current and row.status != "WITHDRAWN"]
    return result


def model_driver_projections(
    session: Session,
    model_id: UUID,
    revision_id: UUID,
) -> list[FinancialModelDriverProjectionRead]:
    model = session.get(FinancialModel, model_id)
    if model is None:
        raise _not_found("Financial model not found")
    revision = session.get(FinancialModelRevision, revision_id)
    if revision is None or revision.model_id != model.id:
        raise _not_found("Financial model revision not found")
    rows = session.execute(
        select(FinancialModelDriverProjection, CompanyMetricDefinition)
        .join(
            CompanyMetricDefinition,
            CompanyMetricDefinition.id == FinancialModelDriverProjection.metric_definition_id,
        )
        .where(
            FinancialModelDriverProjection.model_id == model_id,
            FinancialModelDriverProjection.revision_id == revision_id,
        )
        .order_by(
            FinancialModelDriverProjection.scenario,
            FinancialModelDriverProjection.forecast_year,
            CompanyMetricDefinition.metric_key,
        )
    ).all()
    return [
        FinancialModelDriverProjectionRead(
            id=row.id,
            external_driver_id=row.external_driver_id,
            model_id=row.model_id,
            revision_id=row.revision_id,
            scenario=row.scenario,
            metric_definition_id=row.metric_definition_id,
            metric_id=definition.metric_key,
            forecast_year=row.forecast_year,
            period_type=row.period_type,
            period_start=row.period_start,
            period_end=row.period_end,
            value=row.value,
            value_qualifier=row.value_qualifier,
            unit=row.unit,
            scale=row.scale,
            currency=row.currency,
            basis=row.basis,
            scope_json=row.scope_json,
            rationale=row.rationale,
            recorded_at=row.recorded_at,
        )
        for row, definition in rows
    ]


@event.listens_for(Session, "before_flush")
def protect_company_observation_history(
    session: Session, flush_context: object, instances: object
) -> None:
    """Accepted metric observations and model-driver paths are append-only."""

    immutable = (
        CompanyMetricObservation,
        CompanyGuidanceObservation,
        FinancialModelDriverProjection,
    )
    for item in session.dirty.union(session.deleted):
        if isinstance(item, immutable):
            raise ValueError("Company observation history is append-only")
        if isinstance(item, CompanyMetricDefinition):
            if item in session.deleted:
                raise ValueError("Metric definitions are retained")
            state = inspect(item)
            mutable = {"active", "deprecated_at"}
            changed = {
                attr.key
                for attr in state.mapper.column_attrs
                if state.attrs[attr.key].history.has_changes()
            }
            if changed - mutable:
                raise ValueError(
                    "Metric definition semantics are immutable; create a new metric_id"
                )
