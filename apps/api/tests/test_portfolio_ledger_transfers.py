"""Paired internal cash movement must preserve portfolio cash and source evidence."""

from datetime import timedelta, timezone
from decimal import Decimal, localcontext
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_portfolio_ledger import ACCOUNT, AT, anchor, cash_activity, evidence, proposal, replay
from test_portfolio_ledger_income import income_packet

from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain.services import DomainError

DESTINATION = UUID("88888888-8888-4888-8888-888888888888")


def test_historical_v2_income_input_hash_is_unchanged() -> None:
    source, packet = anchor(), income_packet()
    source.listings[0].security_id = UUID("77777777-7777-4777-8777-777777777777")
    for index, item in enumerate(packet.activity):
        item.id = UUID(int=500 + index)
    result = replay(source, packet)
    # Recorded against pre-transfer implementation 0a57454, with all fields compared.
    assert result.input_sha256 == "fc6e7d8fb744060fce1c068d10a8e692b40d075a63fa4e2ed44a40c2a54cb1ca"


def transfer_packet() -> c.PortfolioLedgerPreviewCreate:
    packet = proposal(anchor()).model_dump(mode="json")
    packet["contract_version"] = "portfolio-ledger-preview-v2"
    packet["accounts"].append(
        {
            "account_id": str(DESTINATION),
            "name": "Synthetic receiving account",
            "kind": "BROKERAGE",
            "broker_name": "Synthetic Second Broker",
            "evidence": evidence("receiving-opening").model_dump(mode="json"),
            "positions": [],
            "cash": [{"currency": "USD", "balance": "0"}],
        }
    )
    packet["activity"] = [
        {
            "id": str(uuid4()),
            "account_id": str(ACCOUNT),
            "sequence": 1,
            "effective_at": (AT + timedelta(days=1)).isoformat(),
            "evidence": evidence("transfer-debit").model_dump(mode="json"),
            "kind": "CASH_TRANSFER",
            "currency": "USD",
            "amount": "12.3456789012",
            "destination": {
                "account_id": str(DESTINATION),
                "currency": "USD",
                "amount": "12.3456789012",
                "effective_at": (AT + timedelta(days=1)).isoformat(),
                "evidence": evidence("transfer-receipt").model_dump(mode="json"),
            },
        }
    ]
    return c.PortfolioLedgerPreviewCreate.model_validate(packet)


def test_internal_transfer_conserves_cash_with_exact_account_legs_and_replay() -> None:
    source, packet = anchor(), transfer_packet()
    with localcontext() as context:
        context.prec = 2
        result = replay(source, packet)
    assert result.status == "OPENING_RECONCILED" and not result.issues
    assert {row.currency: row.balance for row in result.cash} == {
        "USD": Decimal("100"),
        "EUR": Decimal("0"),
    }
    amounts = {account.account_id: account.cash[0].balance for account in result.accounts}
    # Source accounts sort cash currencies independently, retaining explicit EUR zero.
    sender = next(account for account in result.accounts if account.account_id == ACCOUNT)
    assert next(row.balance for row in sender.cash if row.currency == "USD") == Decimal(
        "87.6543210988"
    )
    assert amounts[DESTINATION] == Decimal("12.3456789012")
    assert result.positions[0].quantity == Decimal("2.5")
    restored = c.PortfolioLedgerPreviewCreate.model_validate_json(packet.model_dump_json())
    restored.accounts.reverse()
    assert replay(source, restored) == result


def test_recipient_can_spend_only_after_the_transfer_booking() -> None:
    source, packet = anchor(), transfer_packet()
    fee = cash_activity("FEE", 2, "1").model_copy(update={"account_id": DESTINATION})
    packet.activity.append(fee)
    result = replay(source, packet)
    assert result.status == "OPENING_RECONCILED"
    assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("99")
    fee.effective_at = AT + timedelta(hours=1)
    blocked = replay(source, packet)
    assert blocked.status == "BLOCKED"
    assert blocked.issues[0].code == "NEGATIVE_CASH"
    assert blocked.issues[0].account_id == DESTINATION


def test_wrong_account_statement_cannot_pass_on_consolidated_cash_alone() -> None:
    packet = transfer_packet()
    packet.ending_statement = c.LedgerEndingStatement(
        effective_at=packet.as_of,
        accounts=[
            c.LedgerEndingAccount(
                account_id=ACCOUNT,
                evidence=evidence("sender-closing"),
                positions=[p.model_copy() for p in packet.accounts[0].positions],
                cash=[
                    c.LedgerCashInput(currency="USD", balance=Decimal("100")),
                    c.LedgerCashInput(currency="EUR", balance=Decimal("0")),
                ],
            ),
            c.LedgerEndingAccount(
                account_id=DESTINATION,
                evidence=evidence("recipient-closing"),
                positions=[],
                cash=[c.LedgerCashInput(currency="USD", balance=Decimal("0"))],
            ),
        ],
    )
    result = replay(anchor(), packet)
    assert result.status == "BLOCKED" and result.ending_status == "MISMATCH"
    assert all(
        row.status == "MATCH" for row in result.ending_reconciliation if row.account_id is None
    )
    assert len([row for row in result.ending_reconciliation if row.status == "DIFFERENCE"]) == 2


def test_later_reversal_cannot_repair_an_earlier_transfer_overdraft() -> None:
    source, packet = anchor(), transfer_packet()
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerCashTransfer)
    transfer.amount = transfer.destination.amount = Decimal("101")
    reverse = transfer.model_copy(deep=True)
    reverse.id, reverse.sequence = uuid4(), 2
    reverse.effective_at = reverse.destination.effective_at = AT + timedelta(days=2)
    reverse.account_id, reverse.destination.account_id = DESTINATION, ACCOUNT
    reverse.evidence = evidence("return-debit")
    reverse.destination.evidence = evidence("return-receipt")
    packet.activity.append(reverse)
    result = replay(source, packet)
    assert result.status == "BLOCKED"
    assert result.issues[0].activity_id == transfer.id
    assert result.issues[0].code == "NEGATIVE_CASH"
    assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("100")


@pytest.mark.parametrize("change", ["unallocated", "unknown"])
def test_destination_requires_a_declared_evidenced_brokerage_account(change: str) -> None:
    packet = transfer_packet()
    if change == "unallocated":
        packet.accounts[1].kind, packet.accounts[1].broker_name = "UNALLOCATED_OPENING", None
    else:
        packet.accounts.pop()
    with pytest.raises(DomainError, match="destination brokerage"):
        replay(anchor(), packet)


@pytest.mark.parametrize(
    "change",
    [
        "legacy",
        "amount",
        "currency",
        "time",
        "same_account",
        "missing_leg",
        "missing_evidence",
        "duplicate_evidence",
        "float",
        "zero",
        "naive_time",
    ],
)
def test_mismatched_incomplete_or_ambiguous_transfer_legs_fail_closed(change: str) -> None:
    packet = transfer_packet().model_dump(mode="json")
    transfer = packet["activity"][0]
    if change == "legacy":
        packet["contract_version"] = "portfolio-ledger-preview-v1"
    if change == "amount":
        transfer["destination"]["amount"] = "12.3456789013"
    if change == "currency":
        transfer["destination"]["currency"] = "EUR"
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
        transfer["destination"]["amount"] = 12.345
    if change == "zero":
        transfer["amount"] = transfer["destination"]["amount"] = "0"
    if change == "naive_time":
        transfer["destination"]["effective_at"] = "2026-01-02T00:00:00"
    with pytest.raises(ValidationError):
        c.PortfolioLedgerPreviewCreate.model_validate(packet)


def test_transfer_receipt_cannot_be_reused_as_another_cash_record() -> None:
    packet = transfer_packet()
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerCashTransfer)
    deposit = cash_activity("DEPOSIT", 2, "12.3456789012")
    deposit.evidence = transfer.destination.evidence
    packet.activity.append(deposit)
    with pytest.raises(ValidationError, match="only once"):
        c.PortfolioLedgerPreviewCreate.model_validate_json(packet.model_dump_json())


def test_receiving_evidence_is_hash_bound_and_offsets_keep_the_same_booking_instant() -> None:
    source, packet = anchor(), transfer_packet()
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerCashTransfer)
    transfer.destination.effective_at = transfer.effective_at.astimezone(
        timezone(timedelta(hours=1))
    )
    packet = c.PortfolioLedgerPreviewCreate.model_validate_json(packet.model_dump_json())
    first = replay(source, packet)
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerCashTransfer)
    assert transfer.destination.effective_at.utcoffset() == timedelta(hours=1)
    transfer.destination.evidence = evidence("different-reviewed-receipt")
    second = replay(source, packet)
    assert first.cash == second.cash and first.accounts == second.accounts
    assert first.input_sha256 != second.input_sha256
