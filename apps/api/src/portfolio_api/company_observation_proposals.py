"""Typed, review-gated company KPI/management-guidance proposal batches.

One small candidate table serves three domain-specific contracts; accepted state
remains in the existing immutable observation tables.
"""

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, Self, cast
from uuid import UUID, uuid4

from pydantic import Field, TypeAdapter, field_validator, model_validator
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from portfolio_api.company_observations import (
    CompanyGuidanceObservation,
    CompanyMetricDefinition,
    CompanyMetricObservation,
    ObservationDecimal,
)
from portfolio_api.database import Base
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import Company, now
from portfolio_api.domain.services import DomainError

Period = Literal["DATE", "MONTH", "QUARTER", "FY", "TTM", "EVENT"]
Qualifier = Literal["EQ", "APPROX", "GT", "GTE", "LT", "LTE"]
BatchStatus = Literal["PENDING", "READY", "CONFLICT", "INVALID", "ACCEPTED", "REJECTED"]
MetricCategory = Literal[
    "OPERATING",
    "CUSTOMER",
    "CAPACITY",
    "PRODUCT",
    "MARKET_SHARE",
    "MARKET_EXPOSURE",
    "SEGMENT",
    "BACKLOG",
    "QUALITY",
    "OTHER",
]
Url = Annotated[str, Field(pattern=r"^https://", min_length=9, max_length=2000)]
Key = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")]


class MetricDefinitionItem(s.Contract):
    metric_key: Key
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    category: MetricCategory
    value_kind: Literal["CURRENCY", "PERCENT", "COUNT", "RATIO"]
    canonical_unit: Annotated[str, Field(min_length=1, max_length=64)]
    canonical_scale: Annotated[ObservationDecimal, Field(gt=0)]
    currency_policy: Literal["REQUIRED", "OPTIONAL", "NONE"]
    aggregation_semantics: Annotated[str, Field(min_length=1, max_length=40)]
    default_period_type: Period
    default_basis: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    scope_dimensions: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=10
    )
    actuals_allowed: bool = True
    guidance_allowed: bool = False
    description: Annotated[str, Field(min_length=10, max_length=4000)]
    source_reference: Url


class ObservationItem(s.Contract):
    metric_key: Key
    period_type: Period
    period_start: date
    period_end: date
    fiscal_year: Annotated[int, Field(ge=1900, le=2200)] | None = None
    fiscal_quarter: Annotated[int, Field(ge=1, le=4)] | None = None
    unit: Annotated[str, Field(min_length=1, max_length=64)]
    scale: Annotated[ObservationDecimal, Field(gt=0)]
    currency: s.Currency | None = None
    basis: Annotated[str, Field(min_length=1, max_length=120)]
    scope_json: dict[Annotated[str, Field(min_length=1, max_length=64)], str] = Field(
        default_factory=dict, max_length=10
    )
    source_type: Annotated[str, Field(min_length=1, max_length=80)]
    source_reference: Url

    @model_validator(mode="after")
    def valid_period(self) -> Self:
        if self.period_start > self.period_end:
            raise ValueError("period_start cannot exceed period_end")
        return self


class KPIObservationItem(ObservationItem):
    external_observation_id: Annotated[str, Field(min_length=1, max_length=200)]
    value: ObservationDecimal
    value_qualifier: Qualifier = "EQ"
    reported_at: datetime | None = None
    quality_status: Literal["VERIFIED", "PROVISIONAL", "CONFLICTED", "RESTATED"] = "VERIFIED"
    quality_reason: Annotated[str, Field(max_length=1000)] | None = None
    supersedes_observation_id: UUID | None = None


class GuidanceObservationItem(ObservationItem):
    external_guidance_id: Annotated[str, Field(min_length=1, max_length=200)]
    lower_value: ObservationDecimal | None = None
    midpoint_value: ObservationDecimal | None = None
    upper_value: ObservationDecimal | None = None
    value_qualifier: Literal["EQ", "APPROX", "GT", "GTE", "LT", "LTE", "RANGE"] = "RANGE"
    issued_at: datetime | None = None
    status: Literal["ACTIVE", "WITHDRAWN", "ACHIEVED"] = "ACTIVE"
    supersedes_guidance_id: UUID | None = None

    @model_validator(mode="after")
    def valid_guidance(self) -> Self:
        if self.status != "WITHDRAWN" and all(
            value is None for value in (self.lower_value, self.midpoint_value, self.upper_value)
        ):
            raise ValueError("Non-withdrawn guidance requires a value")
        if (
            self.lower_value is not None
            and self.upper_value is not None
            and self.lower_value > self.upper_value
        ):
            raise ValueError("Guidance lower bound must not exceed upper bound")
        if self.status == "WITHDRAWN" and self.supersedes_guidance_id is None:
            raise ValueError("Withdrawn guidance requires an explicit prior guidance ID")
        return self


class ObservationBatchBase(s.Contract):
    contract_version: Literal["1.0.0"] = "1.0.0"
    company_id: UUID
    external_batch_id: Annotated[str, Field(min_length=1, max_length=160)]
    authored_at: datetime
    rationale: Annotated[str, Field(min_length=10, max_length=2000)]

    @field_validator("authored_at")
    @classmethod
    def valid_authored_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authored_at requires a timezone offset")
        if value.astimezone(UTC) > now():
            raise ValueError("Future proposal timestamps are not supported")
        return value.astimezone(UTC)


class MetricDefinitionBatchV1(ObservationBatchBase):
    contract_type: Literal["MetricDefinitionBatchV1"] = "MetricDefinitionBatchV1"
    items: list[MetricDefinitionItem] = Field(min_length=1, max_length=20)


class KPIObservationBatchV1(ObservationBatchBase):
    contract_type: Literal["KPIObservationBatchV1"] = "KPIObservationBatchV1"
    items: list[KPIObservationItem] = Field(min_length=1, max_length=20)


class GuidanceObservationBatchV1(ObservationBatchBase):
    contract_type: Literal["GuidanceObservationBatchV1"] = "GuidanceObservationBatchV1"
    items: list[GuidanceObservationItem] = Field(min_length=1, max_length=20)


ProposalItem = MetricDefinitionItem | KPIObservationItem | GuidanceObservationItem

ObservationBatchV1 = Annotated[
    MetricDefinitionBatchV1 | KPIObservationBatchV1 | GuidanceObservationBatchV1,
    Field(discriminator="contract_type"),
]
BATCH_ADAPTER: TypeAdapter[ObservationBatchV1] = TypeAdapter(ObservationBatchV1)


class CompanyObservationProposal(Base):
    __tablename__ = "company_observation_proposals"
    __table_args__ = (
        UniqueConstraint(
            "producer_id", "external_batch_id", name="uq_company_observation_producer_batch"
        ),
        Index("ix_company_observation_proposals_company_status", "company_id", "status"),
        CheckConstraint(
            "status IN ('PENDING','READY','CONFLICT','INVALID','ACCEPTED','REJECTED')",
            name="status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    producer_id: Mapped[str] = mapped_column(String(160))
    external_batch_id: Mapped[str] = mapped_column(String(160))
    contract_type: Mapped[str] = mapped_column(String(60))
    payload_data: Mapped[dict[str, object]] = mapped_column(JSON)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    reviewer_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ObservationProposalRead(s.Contract):
    id: UUID
    producer_id: str
    proposal: ObservationBatchV1
    content_fingerprint: str
    status: BatchStatus
    issue: str | None
    preview_fingerprint: str | None
    accepted_record_ids: list[UUID]
    reviewer_id: str | None
    decision_note: str | None
    submitted_at: datetime
    reviewed_at: datetime | None


class ObservationProposalSubmissionRead(s.Contract):
    proposal: ObservationProposalRead
    replayed: bool


class ObservationProposalIssue(s.Contract):
    row_index: int
    code: Literal["CONFLICT", "INVALID"]
    detail: str


class ObservationProposalChange(s.Contract):
    row_index: int
    metric_key: str
    operation: Literal["CREATE", "SUPERSEDE"]
    previous_id: UUID | None


class ObservationProposalPreviewRead(s.Contract):
    proposal_id: UUID
    status: Literal["READY", "CONFLICT", "INVALID"]
    issues: list[ObservationProposalIssue]
    changes: list[ObservationProposalChange]
    preview_fingerprint: str | None


class ObservationProposalDecisionRequest(s.Contract):
    preview_fingerprint: Annotated[
        str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    ]
    decision_note: Annotated[str, Field(min_length=1, max_length=2000)]


class ObservationProposalRejectRequest(s.Contract):
    decision_note: Annotated[str, Field(min_length=1, max_length=2000)]


class ObservationProposalDecisionRead(s.Contract):
    status: Literal["ACCEPTED", "REJECTED", "PREVIEW_CHANGED"]
    proposal: ObservationProposalRead
    preview: ObservationProposalPreviewRead | None = None


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _read(item: CompanyObservationProposal) -> ObservationProposalRead:
    return ObservationProposalRead(
        id=item.id,
        producer_id=item.producer_id,
        proposal=BATCH_ADAPTER.validate_python(item.payload_data),
        content_fingerprint=item.content_fingerprint,
        status=cast(BatchStatus, item.status),
        issue=item.issue,
        preview_fingerprint=item.preview_fingerprint,
        accepted_record_ids=[UUID(value) for value in item.accepted_record_ids],
        reviewer_id=item.reviewer_id,
        decision_note=item.decision_note,
        submitted_at=item.submitted_at,
        reviewed_at=item.reviewed_at,
    )


def submit(
    session: Session, batch: ObservationBatchV1, *, producer_id: str
) -> ObservationProposalSubmissionRead:
    if session.get(Company, batch.company_id) is None:
        raise DomainError("Company not found", 404)
    payload = batch.model_dump(mode="json")
    fingerprint = _hash({"producer": producer_id, "payload": payload})
    prior = session.scalar(
        select(CompanyObservationProposal).where(
            CompanyObservationProposal.producer_id == producer_id,
            CompanyObservationProposal.external_batch_id == batch.external_batch_id,
        )
    )
    if prior is not None:
        if prior.content_fingerprint != fingerprint:
            raise DomainError("External batch ID reused with different content", 409)
        return ObservationProposalSubmissionRead(proposal=_read(prior), replayed=True)
    candidate = CompanyObservationProposal(
        company_id=batch.company_id,
        producer_id=producer_id,
        external_batch_id=batch.external_batch_id,
        contract_type=batch.contract_type,
        payload_data=payload,
        content_fingerprint=fingerprint,
        status="PENDING",
    )
    session.add(candidate)
    session.flush()
    return ObservationProposalSubmissionRead(proposal=_read(candidate), replayed=False)


def get(session: Session, proposal_id: UUID) -> ObservationProposalRead:
    item = session.get(CompanyObservationProposal, proposal_id)
    if item is None:
        raise DomainError("Company observation proposal not found", 404)
    return _read(item)


def list_proposals(
    session: Session,
    *,
    company_id: UUID | None = None,
    status: BatchStatus | None = None,
    limit: int = 50,
) -> list[ObservationProposalRead]:
    statement = select(CompanyObservationProposal)
    if company_id is not None:
        statement = statement.where(CompanyObservationProposal.company_id == company_id)
    if status is not None:
        statement = statement.where(CompanyObservationProposal.status == status)
    statement = statement.order_by(
        CompanyObservationProposal.submitted_at.desc(),
        CompanyObservationProposal.id,
    ).limit(limit)
    return [_read(item) for item in session.scalars(statement)]


def _preflight(
    session: Session, candidate: CompanyObservationProposal
) -> ObservationProposalPreviewRead:
    batch = BATCH_ADAPTER.validate_python(candidate.payload_data)
    issues: list[ObservationProposalIssue] = []
    changes: list[ObservationProposalChange] = []
    dependencies: list[object] = []
    seen: set[str] = set()
    seen_external_ids: set[str] = set()
    for index, item in enumerate(cast(list[ProposalItem], batch.items)):
        key = item.metric_key
        if isinstance(item, MetricDefinitionItem):
            identity = key
            prior = session.scalar(
                select(CompanyMetricDefinition).where(CompanyMetricDefinition.metric_key == key)
            )
            dependencies.append((key, str(prior.id) if prior else None))
            if prior is not None:
                issues.append(
                    ObservationProposalIssue(
                        row_index=index, code="CONFLICT", detail="Metric key is already registered"
                    )
                )
            operation: Literal["CREATE", "SUPERSEDE"] = "CREATE"
            predecessor: UUID | None = None
        else:
            identity = json.dumps(
                [
                    key,
                    item.period_type,
                    item.period_start.isoformat(),
                    item.period_end.isoformat(),
                    item.scope_json,
                ],
                sort_keys=True,
            )
            definition = session.scalar(
                select(CompanyMetricDefinition).where(CompanyMetricDefinition.metric_key == key)
            )
            if definition is None:
                issues.append(
                    ObservationProposalIssue(
                        row_index=index, code="INVALID", detail="Metric key is not registered"
                    )
                )
                dependencies.append((key, None))
                continue
            dependencies.append(
                (
                    key,
                    str(definition.id),
                    definition.active,
                    definition.deprecated_at.isoformat() if definition.deprecated_at else None,
                )
            )
            enabled = (
                definition.actuals_allowed
                if isinstance(item, KPIObservationItem)
                else definition.guidance_allowed
            )
            if (
                not definition.active
                or definition.deprecated_at is not None
                or definition.company_id not in (None, batch.company_id)
                or not enabled
                or item.unit != definition.canonical_unit
                or item.scale != definition.canonical_scale
                or set(item.scope_json) - set(definition.scope_dimensions)
                or (definition.currency_policy == "REQUIRED" and item.currency is None)
                or (definition.currency_policy == "NONE" and item.currency is not None)
            ):
                issues.append(
                    ObservationProposalIssue(
                        row_index=index,
                        code="INVALID",
                        detail="Metric scope, units, currency or usage violate its definition",
                    )
                )
            if isinstance(item, KPIObservationItem):
                model: Any = CompanyMetricObservation
                external_column = model.external_observation_id
                external_id = item.external_observation_id
                predecessor = item.supersedes_observation_id
                if item.period_end > date.today():
                    issues.append(
                        ObservationProposalIssue(
                            row_index=index,
                            code="INVALID",
                            detail="KPI actual period ends in the future",
                        )
                    )
                source_at = item.reported_at
            else:
                model = CompanyGuidanceObservation
                external_column = model.external_guidance_id
                external_id = item.external_guidance_id
                predecessor = item.supersedes_guidance_id
                source_at = item.issued_at
            if source_at is not None and (
                source_at.tzinfo is None or source_at.utcoffset() is None or source_at > now()
            ):
                issues.append(
                    ObservationProposalIssue(
                        row_index=index,
                        code="INVALID",
                        detail="Publication time is missing or future",
                    )
                )
            existing: list[Any] = list(
                session.scalars(
                    select(model)
                    .where(
                        model.company_id == batch.company_id,
                        model.metric_definition_id == definition.id,
                        model.period_start == item.period_start,
                        model.period_end == item.period_end,
                    )
                    .order_by(model.id)
                )
            )
            external = session.scalar(select(model).where(external_column == external_id))
            if external_id in seen_external_ids:
                issues.append(
                    ObservationProposalIssue(
                        row_index=index,
                        code="INVALID",
                        detail="Duplicate external observation ID within batch",
                    )
                )
            seen_external_ids.add(external_id)
            dependencies.append(
                (
                    external_id,
                    str(external.id) if external else None,
                    [
                        (
                            str(row.id),
                            str(row.supersedes_observation_id)
                            if isinstance(row, CompanyMetricObservation)
                            else str(row.supersedes_guidance_id),
                        )
                        for row in existing
                    ],
                )
            )
            if external is not None:
                issues.append(
                    ObservationProposalIssue(
                        row_index=index,
                        code="CONFLICT",
                        detail="External observation ID already exists",
                    )
                )
            current = [row for row in existing if row.scope_json == item.scope_json]
            predecessor_row = session.get(model, predecessor) if predecessor else None
            if predecessor is not None:
                if predecessor_row is None or predecessor_row not in current:
                    issues.append(
                        ObservationProposalIssue(
                            row_index=index,
                            code="CONFLICT",
                            detail="Superseded observation identity mismatches",
                        )
                    )
                else:
                    successors: list[Any] = list(
                        session.scalars(
                            select(model.id).where(
                                (
                                    model.supersedes_observation_id
                                    if isinstance(item, KPIObservationItem)
                                    else model.supersedes_guidance_id
                                )
                                == predecessor
                            )
                        )
                    )
                    dependencies.append((str(predecessor), [str(value) for value in successors]))
                    if successors:
                        issues.append(
                            ObservationProposalIssue(
                                row_index=index,
                                code="CONFLICT",
                                detail="Superseded observation is no longer current",
                            )
                        )
            elif current:
                issues.append(
                    ObservationProposalIssue(
                        row_index=index,
                        code="CONFLICT",
                        detail="Existing observation for this period and scope "
                        "requires explicit supersession",
                    )
                )
            operation = "SUPERSEDE" if predecessor else "CREATE"
        if identity in seen:
            issues.append(
                ObservationProposalIssue(
                    row_index=index, code="INVALID", detail="Duplicate identity within batch"
                )
            )
        seen.add(identity)
        changes.append(
            ObservationProposalChange(
                row_index=index,
                metric_key=key,
                operation=operation,
                previous_id=predecessor,
            )
        )
    status: Literal["READY", "CONFLICT", "INVALID"] = (
        "INVALID" if any(i.code == "INVALID" for i in issues) else "CONFLICT" if issues else "READY"
    )
    fingerprint = (
        _hash(
            {
                "proposal": candidate.content_fingerprint,
                "dependencies": dependencies,
                "issues": [issue.model_dump(mode="json") for issue in issues],
            }
        )
        if status == "READY"
        else None
    )

    return ObservationProposalPreviewRead(
        proposal_id=candidate.id,
        status=status,
        issues=issues,
        changes=changes,
        preview_fingerprint=fingerprint,
    )


def preview(session: Session, proposal_id: UUID) -> ObservationProposalPreviewRead:
    candidate = session.get(CompanyObservationProposal, proposal_id)
    if candidate is None:
        raise DomainError("Company observation proposal not found", 404)
    if candidate.status in ("ACCEPTED", "REJECTED"):
        raise DomainError("Finalized proposals cannot be previewed", 409)
    result = _preflight(session, candidate)
    candidate.status = result.status
    candidate.issue = "; ".join(x.detail for x in result.issues) or None
    candidate.preview_fingerprint = result.preview_fingerprint
    session.flush()
    return result


def accept(
    session: Session,
    proposal_id: UUID,
    request: ObservationProposalDecisionRequest,
    *,
    reviewer_id: str,
) -> ObservationProposalDecisionRead:
    candidate = session.get(CompanyObservationProposal, proposal_id)
    if candidate is None:
        raise DomainError("Company observation proposal not found", 404)
    # Serialize acceptances within one company; no direct agent writes to accepted state.
    session.scalar(select(Company).where(Company.id == candidate.company_id).with_for_update())
    candidate = session.scalar(
        select(CompanyObservationProposal)
        .where(CompanyObservationProposal.id == proposal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if candidate is None:
        raise DomainError("Company observation proposal not found", 404)
    if candidate.status in ("ACCEPTED", "REJECTED"):
        raise DomainError("Proposal has a final decision", 409)
    if candidate.preview_fingerprint is None or candidate.status != "READY":
        raise DomainError("A READY reviewer preview is required before acceptance", 409)
    if candidate.preview_fingerprint != request.preview_fingerprint:
        raise DomainError("Review fingerprint does not match the recorded preview", 409)
    result = _preflight(session, candidate)
    if result.status != "READY" or result.preview_fingerprint != request.preview_fingerprint:
        candidate.status = "CONFLICT"
        candidate.issue = "Accepted source state changed since reviewer preview"
        candidate.preview_fingerprint = None
        return ObservationProposalDecisionRead(
            status="PREVIEW_CHANGED",
            proposal=_read(candidate),
            preview=result,
        )
    batch = BATCH_ADAPTER.validate_python(candidate.payload_data)
    accepted_ids: list[UUID] = []
    for item in cast(list[ProposalItem], batch.items):
        if isinstance(item, MetricDefinitionItem):
            record: CompanyMetricDefinition | CompanyMetricObservation | CompanyGuidanceObservation
            record = CompanyMetricDefinition(
                metric_key=item.metric_key,
                company_id=batch.company_id,
                display_name=item.display_name,
                category=item.category,
                value_kind=item.value_kind,
                canonical_unit=item.canonical_unit,
                canonical_scale=item.canonical_scale,
                currency_policy=item.currency_policy,
                aggregation_semantics=item.aggregation_semantics,
                default_period_type=item.default_period_type,
                default_basis=item.default_basis,
                scope_dimensions=item.scope_dimensions,
                actuals_allowed=item.actuals_allowed,
                guidance_allowed=item.guidance_allowed,
                consensus_allowed=False,
                model_driver_allowed=False,
                active=True,
                description=item.description,
                source_reference=item.source_reference,
            )
        else:
            definition = session.scalar(
                select(CompanyMetricDefinition).where(
                    CompanyMetricDefinition.metric_key == item.metric_key
                )
            )
            if definition is None:
                raise DomainError("Accepted metric definition disappeared during review", 409)
            shared = dict(
                company_id=batch.company_id,
                metric_definition_id=definition.id,
                period_type=item.period_type,
                period_start=item.period_start,
                period_end=item.period_end,
                fiscal_year=item.fiscal_year,
                fiscal_quarter=item.fiscal_quarter,
                unit=item.unit,
                scale=item.scale,
                currency=item.currency,
                basis=item.basis,
                scope_json=item.scope_json,
                source_type=item.source_type,
                source_reference=item.source_reference,
            )
            if isinstance(item, KPIObservationItem):
                record = CompanyMetricObservation(
                    **shared,
                    external_observation_id=item.external_observation_id,
                    value=item.value,
                    value_qualifier=item.value_qualifier,
                    reported_at=item.reported_at,
                    quality_status=item.quality_status,
                    quality_reason=item.quality_reason,
                    supersedes_observation_id=item.supersedes_observation_id,
                )
            else:
                record = CompanyGuidanceObservation(
                    **shared,
                    external_guidance_id=item.external_guidance_id,
                    lower_value=item.lower_value,
                    midpoint_value=item.midpoint_value,
                    upper_value=item.upper_value,
                    value_qualifier=item.value_qualifier,
                    issued_at=item.issued_at,
                    status=item.status,
                    supersedes_guidance_id=item.supersedes_guidance_id,
                )
        session.add(record)
        session.flush()
        accepted_ids.append(record.id)
    candidate.status = "ACCEPTED"
    candidate.accepted_record_ids = [str(value) for value in accepted_ids]
    candidate.reviewer_id = reviewer_id
    candidate.decision_note = request.decision_note
    candidate.reviewed_at = now()
    session.flush()
    return ObservationProposalDecisionRead(status="ACCEPTED", proposal=_read(candidate))


def reject(
    session: Session,
    proposal_id: UUID,
    reason: str,
    *,
    reviewer_id: str,
) -> ObservationProposalDecisionRead:
    candidate = session.scalar(
        select(CompanyObservationProposal)
        .where(CompanyObservationProposal.id == proposal_id)
        .with_for_update()
    )
    if candidate is None:
        raise DomainError("Company observation proposal not found", 404)
    if candidate.status == "ACCEPTED":
        raise DomainError("Accepted proposals cannot be rejected", 409)
    if candidate.status != "REJECTED":
        candidate.status = "REJECTED"
        candidate.issue = None
        candidate.preview_fingerprint = None
        candidate.reviewer_id = reviewer_id
        candidate.decision_note = reason
        candidate.reviewed_at = now()
        session.flush()
    return ObservationProposalDecisionRead(status="REJECTED", proposal=_read(candidate))
