"""Versioned, exact inputs for a candidate settled-activity ledger."""

from datetime import UTC, date, datetime
from decimal import localcontext
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from portfolio_api.domain.schemas import (
    Contract,
    Currency,
    FixedDecimal,
    Name,
    Quantity,
    SnapshotRead,
)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PositiveQuantity = Annotated[Quantity, Field(gt=0)]


class LedgerEvidence(Contract):
    source_sha256: Digest
    source_record_id: Annotated[str, Field(min_length=1, max_length=200)]


class LedgerPositionInput(Contract):
    listing_id: UUID
    quantity: Quantity


class LedgerCashInput(Contract):
    currency: Currency
    balance: Quantity


class LedgerOpeningAccount(Contract):
    account_id: UUID
    name: Name
    kind: Literal["BROKERAGE", "UNALLOCATED_OPENING"]
    broker_name: Name | None
    evidence: LedgerEvidence
    positions: list[LedgerPositionInput] = Field(max_length=1000)
    cash: list[LedgerCashInput] = Field(max_length=100)

    @model_validator(mode="after")
    def explicit_account(self) -> Self:
        if (self.kind == "BROKERAGE") != (self.broker_name is not None):
            raise ValueError(
                "Brokerage accounts need an evidenced broker; unallocated openings have none"
            )
        if len({p.listing_id for p in self.positions}) != len(self.positions):
            raise ValueError("An opening account may contain a listing only once")
        if len({c.currency for c in self.cash}) != len(self.cash):
            raise ValueError("An opening account may contain a cash currency only once")
        return self


class LedgerActivity(Contract):
    id: UUID
    account_id: UUID
    sequence: Annotated[int, Field(strict=True, ge=1, le=1000)]
    effective_at: datetime
    evidence: LedgerEvidence

    @field_validator("effective_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware settled booking timestamp")
        # Retain the source offset for settlement-date validation. Aware datetime
        # comparisons still order bookings by their absolute instant.
        return value


class LedgerTrade(LedgerActivity):
    kind: Literal["BUY", "SELL"]
    listing_id: UUID
    quantity: PositiveQuantity
    currency: Currency
    gross_cash: PositiveQuantity
    fees: Quantity
    taxes: Quantity
    trade_date: date
    settlement_date: date

    @model_validator(mode="after")
    def settled_trade(self) -> Self:
        if self.trade_date > self.settlement_date:
            raise ValueError("A settled trade cannot precede its trade date")
        if self.settlement_date > self.effective_at.date():
            raise ValueError("Settlement cannot follow the source-local settled booking date")
        return self


class LedgerCashActivity(LedgerActivity):
    kind: Literal["DEPOSIT", "WITHDRAWAL", "FEE", "TAX"]
    currency: Currency
    amount: PositiveQuantity


class LedgerDividend(LedgerActivity):
    """Observed account cash in one settlement currency, independently of quote currency."""

    kind: Literal["DIVIDEND"]
    listing_id: UUID
    currency: Currency
    gross_cash: PositiveQuantity
    fees: Quantity
    taxes: Quantity

    @model_validator(mode="after")
    def nonnegative_net_cash(self) -> Self:
        with localcontext() as context:
            context.prec = 80
            if self.fees + self.taxes > self.gross_cash:
                raise ValueError("Dividend charges cannot exceed the evidenced gross receipt")
        return self


class LedgerTransferReceipt(Contract):
    account_id: UUID
    currency: Currency
    amount: PositiveQuantity
    effective_at: datetime
    evidence: LedgerEvidence

    @field_validator("effective_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return LedgerActivity.aware_time(value)


class LedgerCashTransfer(LedgerActivity):
    kind: Literal["CASH_TRANSFER"]
    currency: Currency
    amount: PositiveQuantity
    destination: LedgerTransferReceipt

    @model_validator(mode="after")
    def matching_internal_legs(self) -> Self:
        if self.account_id == self.destination.account_id:
            raise ValueError("An internal cash transfer requires two different accounts")
        if self.currency != self.destination.currency or self.amount != self.destination.amount:
            raise ValueError("Internal cash transfer legs require equal amounts in one currency")
        if self.effective_at != self.destination.effective_at:
            raise ValueError("Internal cash transfer legs require the same settled booking instant")
        return self


class LedgerSecurityTransferReceipt(Contract):
    account_id: UUID
    listing_id: UUID
    quantity: PositiveQuantity
    effective_at: datetime
    evidence: LedgerEvidence

    @field_validator("effective_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return LedgerActivity.aware_time(value)


class LedgerSecurityTransfer(LedgerActivity):
    kind: Literal["SECURITY_TRANSFER"]
    listing_id: UUID
    quantity: PositiveQuantity
    basis_status: Literal["UNAVAILABLE"]
    destination: LedgerSecurityTransferReceipt

    @model_validator(mode="after")
    def matching_internal_legs(self) -> Self:
        if self.account_id == self.destination.account_id:
            raise ValueError("An internal security transfer requires two different accounts")
        if (
            self.listing_id != self.destination.listing_id
            or self.quantity != self.destination.quantity
        ):
            raise ValueError(
                "Internal security transfer legs require equal quantities of one listing"
            )
        if self.effective_at != self.destination.effective_at:
            raise ValueError(
                "Internal security transfer legs require the same settled booking instant"
            )
        return self


class LedgerEndingAccount(Contract):
    account_id: UUID
    evidence: LedgerEvidence
    positions: list[LedgerPositionInput] = Field(max_length=1000)
    cash: list[LedgerCashInput] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_balances(self) -> Self:
        if len({p.listing_id for p in self.positions}) != len(self.positions):
            raise ValueError("An ending account may contain a listing only once")
        if len({c.currency for c in self.cash}) != len(self.cash):
            raise ValueError("An ending account may contain a cash currency only once")
        return self


class LedgerEndingStatement(Contract):
    effective_at: datetime
    accounts: list[LedgerEndingAccount] = Field(max_length=20)

    @field_validator("effective_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware ending statement timestamp")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def bounded_unique_accounts(self) -> Self:
        if len({a.account_id for a in self.accounts}) != len(self.accounts):
            raise ValueError("An account may have only one ending observation")
        if (
            sum(len(a.positions) for a in self.accounts) > 1000
            or sum(len(a.cash) for a in self.accounts) > 100
        ):
            raise ValueError("Ending scope exceeds 1000 position or 100 cash rows")
        evidence = [a.evidence for a in self.accounts]
        if len({(e.source_sha256, e.source_record_id) for e in evidence}) != len(evidence):
            raise ValueError("An ending source record may describe only one account")
        return self


class PortfolioLedgerPreviewCreate(Contract):
    contract_version: Literal["portfolio-ledger-preview-v1", "portfolio-ledger-preview-v2"]
    anchor_snapshot_id: UUID
    anchor_sha256: Digest
    as_of: datetime
    accounts: list[LedgerOpeningAccount] = Field(min_length=1, max_length=20)
    activity: list[
        Annotated[
            LedgerTrade
            | LedgerCashActivity
            | LedgerDividend
            | LedgerCashTransfer
            | LedgerSecurityTransfer,
            Field(discriminator="kind"),
        ]
    ] = Field(max_length=1000)
    ending_statement: LedgerEndingStatement | None = None

    @field_validator("as_of")
    @classmethod
    def observed_cutoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Use a timezone-aware projection cutoff")
        value = value.astimezone(UTC)
        if value > datetime.now(UTC):
            raise ValueError("Future ledger projections are outside this contract")
        return value

    @model_validator(mode="after")
    def bounded_unique_records(self) -> Self:
        if self.contract_version == "portfolio-ledger-preview-v1" and any(
            item.kind in {"DIVIDEND", "TAX", "CASH_TRANSFER", "SECURITY_TRANSFER"}
            for item in self.activity
        ):
            raise ValueError("Income and internal transfers require portfolio-ledger-preview-v2")
        if len({a.account_id for a in self.accounts}) != len(self.accounts):
            raise ValueError("An account may have only one opening boundary")
        if (
            sum(len(a.positions) for a in self.accounts) > 1000
            or sum(len(a.cash) for a in self.accounts) > 100
        ):
            raise ValueError("Opening scope exceeds 1000 position or 100 cash rows")
        if len({a.id for a in self.activity}) != len(self.activity) or len(
            {a.sequence for a in self.activity}
        ) != len(self.activity):
            raise ValueError("Activity IDs and sequence numbers must be unique")
        evidence = [a.evidence for a in self.accounts] + [a.evidence for a in self.activity]
        evidence.extend(
            item.destination.evidence
            for item in self.activity
            if isinstance(item, (LedgerCashTransfer, LedgerSecurityTransfer))
        )
        if len({(e.source_sha256, e.source_record_id) for e in evidence}) != len(evidence):
            raise ValueError("A source record may contribute only once to this ledger scope")
        if self.ending_statement is not None:
            if self.ending_statement.effective_at != self.as_of:
                raise ValueError("The ending statement timestamp must equal the projection cutoff")
            if not {a.account_id for a in self.ending_statement.accounts} <= {
                a.account_id for a in self.accounts
            }:
                raise ValueError("Ending observations must use declared opening accounts")
        return self


class LedgerListingRead(Contract):
    listing_id: UUID
    security_id: UUID
    company_id: UUID | None
    ticker: str
    venue: str
    currency: Currency
    security_type: str
    identity_source_ref: str | None


class LedgerListingSearchItem(LedgerListingRead):
    security_name: str
    share_class: str | None
    company_name: str | None
    is_demo: bool


class LedgerListingSearchRead(Contract):
    results: list[LedgerListingSearchItem]
    truncated: bool
    unsupported_results: bool


class PortfolioLedgerAnchorRead(Contract):
    portfolio_id: UUID
    snapshot: SnapshotRead
    listings: list[LedgerListingRead]
    anchor_sha256: Digest


class LedgerPositionRead(Contract):
    listing_id: UUID
    quantity: FixedDecimal


class LedgerCashRead(Contract):
    currency: Currency
    balance: FixedDecimal


class LedgerAccountProjectionRead(Contract):
    account_id: UUID
    positions: list[LedgerPositionRead]
    cash: list[LedgerCashRead]


class LedgerReconciliationRead(Contract):
    domain: Literal["POSITION", "CASH"]
    key: str
    observed: FixedDecimal | None
    opening: FixedDecimal | None
    difference: FixedDecimal | None
    status: Literal["MATCH", "MISSING_OPENING", "EXTRA_OPENING", "DIFFERENCE"]


class LedgerIssueRead(Contract):
    code: Literal[
        "OPENING_MISMATCH",
        "NEGATIVE_POSITION",
        "NEGATIVE_CASH",
        "BALANCE_OUT_OF_RANGE",
        "ENDING_MISMATCH",
        "ENDING_ACCOUNT_MISSING",
    ]
    activity_id: UUID | None
    account_id: UUID | None
    asset_key: str | None


class LedgerEndingReconciliationRead(Contract):
    account_id: UUID | None
    domain: Literal["POSITION", "CASH"]
    key: str
    projected: FixedDecimal | None
    observed: FixedDecimal | None
    difference: FixedDecimal | None
    status: Literal["MATCH", "MISSING_OBSERVATION", "EXTRA_OBSERVATION", "DIFFERENCE"]


class PortfolioLedgerPreviewRead(Contract):
    contract_version: Literal["portfolio-ledger-preview-v1", "portfolio-ledger-preview-v2"]
    projection_version: Literal["settled-booking-v1", "settled-booking-v2"]
    preview_only: Literal[True]
    status: Literal["OPENING_RECONCILED", "ENDING_RECONCILED", "BLOCKED"]
    portfolio_id: UUID
    anchor_snapshot_id: UUID
    anchor_recorded_at: datetime
    anchor_sha256: Digest
    input_sha256: Digest
    as_of: datetime
    opening_reconciliation: list[LedgerReconciliationRead]
    accounts: list[LedgerAccountProjectionRead]
    positions: list[LedgerPositionRead]
    cash: list[LedgerCashRead]
    activity_count: int
    issues: list[LedgerIssueRead]
    ending_status: Literal["NOT_PROVIDED", "MATCH", "MISMATCH", "NOT_EVALUATED"] = "NOT_PROVIDED"
    ending_statement_at: datetime | None = None
    ending_reconciliation: list[LedgerEndingReconciliationRead] = Field(default_factory=list)
    consumed_listings: list[LedgerListingRead] = Field(default_factory=list)

    @model_validator(mode="after")
    def matching_projection_contract(self) -> Self:
        expected = (
            "settled-booking-v2"
            if self.contract_version == "portfolio-ledger-preview-v2"
            else "settled-booking-v1"
        )
        if self.projection_version != expected:
            raise ValueError("Ledger input and projection versions must match")
        return self


class LedgerCandidateCreate(Contract):
    submission_id: UUID
    expected_base_candidate_id: UUID | None
    expected_input_sha256: Digest
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    proposal: PortfolioLedgerPreviewCreate


class LedgerReviewCommand(Contract):
    expected_base_candidate_id: UUID | None
    expected_input_sha256: Digest
    expected_preview_sha256: Digest
    reason: Annotated[str, Field(min_length=1, max_length=1000)]


class LedgerAcceptCreate(LedgerReviewCommand):
    decision: Literal["ACCEPT"]
    source_evidence_reviewed: Literal[True]
    account_allocation_reviewed: Literal[True]
    settled_balance_basis_reviewed: Literal[True]
    full_replacement_reviewed: Literal[True]
    acknowledged_removed_activity_ids: list[UUID] = Field(max_length=1000)
    acknowledged_changed_activity_ids: list[UUID] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_acknowledgements(self) -> Self:
        if len(set(self.acknowledged_removed_activity_ids)) != len(
            self.acknowledged_removed_activity_ids
        ) or len(set(self.acknowledged_changed_activity_ids)) != len(
            self.acknowledged_changed_activity_ids
        ):
            raise ValueError("Correction acknowledgements must contain unique activity IDs")
        return self


class LedgerRejectCreate(LedgerReviewCommand):
    decision: Literal["REJECT"]


LedgerReviewCreate = Annotated[
    LedgerAcceptCreate | LedgerRejectCreate, Field(discriminator="decision")
]


class LedgerReviewRead(Contract):
    id: UUID
    decision: Literal["ACCEPT", "REJECT"]
    revision_number: int | None
    reviewed_by: Literal["LOCAL_USER"]
    reviewed_at: datetime
    command: LedgerReviewCreate


class LedgerActivityChangesRead(Contract):
    added_activity_ids: list[UUID]
    changed_activity_ids: list[UUID]
    removed_activity_ids: list[UUID]
    opening_changed: bool


class LedgerCandidateSummaryRead(Contract):
    id: UUID
    portfolio_id: UUID
    base_candidate_id: UUID | None
    anchor_snapshot_id: UUID
    input_sha256: Digest
    packet_sha256: Digest
    preview_sha256: Digest
    status: Literal["PENDING", "ACCEPTED", "REJECTED"]
    preview_status: Literal["BLOCKED", "OPENING_RECONCILED", "ENDING_RECONCILED"]
    as_of: datetime
    reason: str
    submitted_by: Literal["LOCAL_USER"]
    submitted_at: datetime
    review: LedgerReviewRead | None


class LedgerCandidateRead(LedgerCandidateSummaryRead):
    packet: PortfolioLedgerPreviewCreate
    preview: PortfolioLedgerPreviewRead
    changes: LedgerActivityChangesRead
    replayed: bool = False


class LedgerCandidatesRead(Contract):
    portfolio_id: UUID
    current_accepted_candidate_id: UUID | None
    current_revision_number: int
    candidates: list[LedgerCandidateSummaryRead]


class LedgerPublicationPreviewRead(Contract):
    contract_version: Literal["portfolio-ledger-publication-v1"]
    status: Literal["READY", "ALREADY_PUBLISHED"]
    portfolio_id: UUID
    candidate_id: UUID
    review_id: UUID
    review_revision_number: int
    anchor_snapshot_id: UUID
    anchor_sha256: Digest
    candidate_input_sha256: Digest
    candidate_preview_sha256: Digest
    previous_publication_id: UUID | None
    publication_id: UUID | None
    ownership_scope: Literal["WHOLE_PORTFOLIO"]
    cutover_at: datetime
    effective_at: datetime
    current_snapshot: SnapshotRead
    current_snapshot_sha256: Digest
    account_ids: list[UUID]
    positions: list[LedgerPositionRead]
    cash: list[LedgerCashRead]
    plan_sha256: Digest
    confirmation_phrase: str


class LedgerPublicationCreate(Contract):
    expected_plan_sha256: Digest
    expected_previous_publication_id: UUID | None
    confirmation: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    ownership_transfer_reviewed: Literal[True]
    whole_portfolio_scope_reviewed: Literal[True]
    current_state_recovery_verified: Literal[True]
    holdings_confirmation: Literal[True]


class LedgerPublicationRead(Contract):
    id: UUID
    portfolio_id: UUID
    candidate_id: UUID
    sequence: int
    previous_publication_id: UUID | None
    published_at: datetime
    published_by: Literal["LOCAL_USER"]
    plan: LedgerPublicationPreviewRead
    command: LedgerPublicationCreate
    snapshot: SnapshotRead
    snapshot_sha256: Digest
    replayed: bool = False


class LedgerOwnershipRead(Contract):
    portfolio_id: UUID
    source: Literal["OBSERVED_SNAPSHOT", "ACCEPTED_LEDGER"]
    scope: Literal["WHOLE_PORTFOLIO"]
    latest_publication: LedgerPublicationRead | None
