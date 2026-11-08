"""Exact same-listing account transfers retain quantity and unavailable acquisition basis."""

from datetime import timedelta, timezone
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_portfolio_ledger import ACCOUNT, AT, LISTING, anchor, evidence, replay, trade
from test_portfolio_ledger_transfers import DESTINATION, transfer_packet

from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain.services import DomainError


def security_packet() -> c.PortfolioLedgerPreviewCreate:
    packet = transfer_packet()
    previous = packet.activity[0]
    packet.activity = [
        c.LedgerSecurityTransfer(
            id=previous.id,
            account_id=ACCOUNT,
            sequence=1,
            effective_at=previous.effective_at,
            evidence=evidence("security-sent"),
            kind="SECURITY_TRANSFER",
            listing_id=LISTING,
            quantity=Decimal("1.2345678901"),
            basis_status="UNAVAILABLE",
            destination=c.LedgerSecurityTransferReceipt(
                account_id=DESTINATION,
                listing_id=LISTING,
                quantity=Decimal("1.2345678901"),
                effective_at=previous.effective_at,
                evidence=evidence("security-received"),
            ),
        )
    ]
    return c.PortfolioLedgerPreviewCreate.model_validate_json(packet.model_dump_json())


def test_security_transfer_preserves_consolidated_quantity_cash_and_exact_replay() -> None:
    source, packet = anchor(), security_packet()
    with localcontext() as context:
        context.prec = 2
        result = replay(source, packet)
    assert result.status == "OPENING_RECONCILED" and not result.issues
    assert result.positions[0].quantity == Decimal("2.5")
    assert {row.currency: row.balance for row in result.cash} == {
        "USD": Decimal(100),
        "EUR": Decimal(0),
    }
    quantities = {row.account_id: row.positions[0].quantity for row in result.accounts}
    assert quantities == {ACCOUNT: Decimal("1.2654321099"), DESTINATION: Decimal("1.2345678901")}
    assert result.consumed_listings[0].company_id is None
    assert packet.activity[0].model_dump(mode="json")["basis_status"] == "UNAVAILABLE"
    restored = c.PortfolioLedgerPreviewCreate.model_validate_json(packet.model_dump_json())
    restored.accounts.reverse()
    assert replay(source, restored) == result


def test_whole_position_transfer_keeps_a_zero_source_row_and_requires_ending_evidence() -> None:
    packet = security_packet()
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerSecurityTransfer)
    transfer.quantity = transfer.destination.quantity = Decimal("2.5")
    packet.ending_statement = c.LedgerEndingStatement(
        effective_at=packet.as_of,
        accounts=[
            c.LedgerEndingAccount(
                account_id=account.account_id,
                evidence=evidence(f"closing-{account.account_id}"),
                positions=[]
                if account.account_id == ACCOUNT
                else [c.LedgerPositionInput(listing_id=LISTING, quantity=Decimal("2.5"))],
                cash=[cash.model_copy() for cash in account.cash],
            )
            for account in packet.accounts
        ],
    )
    blocked = replay(anchor(), packet)
    assert blocked.status == "BLOCKED" and blocked.ending_status == "MISMATCH"
    assert any(
        row.account_id == ACCOUNT and row.status == "MISSING_OBSERVATION"
        for row in blocked.ending_reconciliation
    )
    packet.ending_statement.accounts[0].positions = [
        c.LedgerPositionInput(listing_id=LISTING, quantity=Decimal(0))
    ]
    result = replay(anchor(), packet)
    assert result.status == "ENDING_RECONCILED"
    sender = next(row for row in result.accounts if row.account_id == ACCOUNT)
    assert sender.positions[0].quantity == 0


def test_sale_uses_recipient_inventory_only_after_the_settled_transfer() -> None:
    packet = security_packet()
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerSecurityTransfer)
    transfer.effective_at = transfer.destination.effective_at = AT + timedelta(days=2)
    sale = trade("SELL", 2).model_copy(update={"account_id": DESTINATION, "quantity": Decimal(1)})
    sale.effective_at = AT + timedelta(days=3)
    packet.activity.append(sale)
    result = replay(anchor(), packet)
    assert result.status == "OPENING_RECONCILED"
    assert result.positions[0].quantity == Decimal("1.5")
    assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("109.85")
    sale.effective_at = AT + timedelta(days=1)
    blocked = replay(anchor(), packet)
    assert blocked.status == "BLOCKED"
    assert (
        blocked.issues[0].code == "NEGATIVE_POSITION"
        and blocked.issues[0].account_id == DESTINATION
    )


def test_later_return_cannot_clear_an_earlier_short_position() -> None:
    packet = security_packet()
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerSecurityTransfer)
    transfer.quantity = transfer.destination.quantity = Decimal(3)
    returned = transfer.model_copy(deep=True)
    returned.id, returned.sequence = uuid4(), 2
    returned.account_id, returned.destination.account_id = DESTINATION, ACCOUNT
    returned.effective_at = returned.destination.effective_at = AT + timedelta(days=2)
    returned.evidence, returned.destination.evidence = (
        evidence("returned"),
        evidence("returned-receipt"),
    )
    packet.activity.append(returned)
    result = replay(anchor(), packet)
    assert result.status == "BLOCKED" and result.positions[0].quantity == Decimal("2.5")
    assert (
        result.issues[0].code == "NEGATIVE_POSITION" and result.issues[0].activity_id == transfer.id
    )


@pytest.mark.parametrize("change", ["unknown", "unallocated", "listing"])
def test_transfer_needs_verified_listing_and_declared_destination(change: str) -> None:
    packet = security_packet()
    if change == "unknown":
        packet.accounts.pop()
    elif change == "unallocated":
        packet.accounts[1].kind, packet.accounts[1].broker_name = "UNALLOCATED_OPENING", None
    else:
        transfer = packet.activity[0]
        assert isinstance(transfer, c.LedgerSecurityTransfer)
        transfer.listing_id = transfer.destination.listing_id = uuid4()
    with pytest.raises(DomainError):
        replay(anchor(), packet)


@pytest.mark.parametrize(
    "change",
    [
        "legacy",
        "quantity",
        "listing",
        "time",
        "same_account",
        "missing_leg",
        "missing_evidence",
        "duplicate_evidence",
        "float",
        "zero",
        "error",
        "missing_basis",
        "invented_basis",
        "extra_cost",
    ],
)
def test_mismatched_or_incomplete_security_transfer_is_rejected(change: str) -> None:
    packet = security_packet().model_dump(mode="json")
    transfer = packet["activity"][0]
    if change == "legacy":
        packet["contract_version"] = "portfolio-ledger-preview-v1"
    if change == "quantity":
        transfer["destination"]["quantity"] = "1.2345678902"
    if change == "listing":
        transfer["destination"]["listing_id"] = str(uuid4())
    if change == "time":
        transfer["destination"]["effective_at"] = (AT + timedelta(days=2)).isoformat()
    if change == "same_account":
        transfer["destination"]["account_id"] = str(ACCOUNT)
    if change == "missing_leg":
        transfer.pop("destination")
    if change == "missing_evidence":
        transfer["destination"].pop("evidence")
    if change == "duplicate_evidence":
        transfer["destination"]["evidence"] = transfer["evidence"]
    if change == "float":
        transfer["destination"]["quantity"] = 1.234
    if change == "zero":
        transfer["quantity"] = transfer["destination"]["quantity"] = "0"
    if change == "error":
        transfer["destination"]["quantity"] = "#VALUE!"
    if change == "missing_basis":
        transfer.pop("basis_status")
    if change == "invented_basis":
        transfer["basis_status"] = "KNOWN"
    if change == "extra_cost":
        transfer["cost_basis"] = "0"
    with pytest.raises(ValidationError):
        c.PortfolioLedgerPreviewCreate.model_validate(packet)


def test_receiving_source_and_listing_identity_are_hash_bound() -> None:
    source, packet = anchor(), security_packet()
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerSecurityTransfer)
    transfer.destination.effective_at = transfer.effective_at.astimezone(
        timezone(timedelta(hours=1))
    )
    packet = c.PortfolioLedgerPreviewCreate.model_validate_json(packet.model_dump_json())
    original = replay(source, packet)
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerSecurityTransfer)
    transfer.destination.evidence = evidence("different-reviewed-receipt")
    assert replay(source, packet).input_sha256 != original.input_sha256
    updated = replay(source, packet)
    source.listings[0].identity_source_ref = "different-reviewed-listing"
    assert replay(source, packet).input_sha256 != updated.input_sha256
