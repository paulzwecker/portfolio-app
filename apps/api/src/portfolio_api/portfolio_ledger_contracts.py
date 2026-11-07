"""Versioned, exact inputs for a candidate settled-activity ledger."""

from datetime import UTC, date, datetime
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
        return value.astimezone(UTC)


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
        return self


class LedgerCashActivity(LedgerActivity):
    kind: Literal["DEPOSIT", "WITHDRAWAL", "FEE"]
    currency: Currency
    amount: PositiveQuantity


class PortfolioLedgerPreviewCreate(Contract):
    contract_version: Literal["portfolio-ledger-preview-v1"]
    anchor_snapshot_id: UUID
    anchor_sha256: Digest
    as_of: datetime
    accounts: list[LedgerOpeningAccount] = Field(min_length=1, max_length=20)
    activity: list[Annotated[LedgerTrade | LedgerCashActivity, Field(discriminator="kind")]] = (
        Field(max_length=1000)
    )

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
        if len({(e.source_sha256, e.source_record_id) for e in evidence}) != len(evidence):
            raise ValueError("A source record may contribute only once to this ledger scope")
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
    code: Literal["OPENING_MISMATCH", "NEGATIVE_POSITION", "NEGATIVE_CASH", "BALANCE_OUT_OF_RANGE"]
    activity_id: UUID | None
    account_id: UUID | None
    asset_key: str | None


class PortfolioLedgerPreviewRead(Contract):
    contract_version: Literal["portfolio-ledger-preview-v1"]
    projection_version: Literal["settled-booking-v1"]
    preview_only: Literal[True]
    status: Literal["RECONCILED", "BLOCKED"]
    portfolio_id: UUID
    anchor_snapshot_id: UUID
    anchor_sha256: Digest
    input_sha256: Digest
    as_of: datetime
    opening_reconciliation: list[LedgerReconciliationRead]
    accounts: list[LedgerAccountProjectionRead]
    positions: list[LedgerPositionRead]
    cash: list[LedgerCashRead]
    activity_count: int
    issues: list[LedgerIssueRead]
