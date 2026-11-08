"""Exact account-statement income, withholding and tax evidence for ledger v2."""

from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_portfolio_ledger import ACCOUNT, AT, LISTING, anchor, cash_activity, evidence, proposal

from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain.services import DomainError
from portfolio_api.portfolio_ledger import canonical_ledger_packet, project_ledger


def income_packet() -> c.PortfolioLedgerPreviewCreate:
    value = proposal(anchor()).model_dump(mode="json")
    value["contract_version"] = "portfolio-ledger-preview-v2"
    value["activity"] = [
        {
            "id": str(uuid4()),
            "account_id": str(ACCOUNT),
            "sequence": 1,
            "effective_at": (AT + timedelta(days=1)).isoformat(),
            "evidence": evidence("dividend-payment").model_dump(mode="json"),
            "kind": "DIVIDEND",
            "listing_id": str(LISTING),
            "currency": "EUR",
            "gross_cash": "12.3456789012",
            "fees": "0.1",
            "taxes": "2.3456789012",
        },
        cash_activity("TAX", 2, "0.9")
        .model_copy(update={"currency": "EUR"})
        .model_dump(mode="json"),
    ]
    return c.PortfolioLedgerPreviewCreate.model_validate(value)


def test_observed_dividend_and_tax_preserve_quantities_and_native_cash() -> None:
    source, packet = anchor(), income_packet()
    with localcontext() as context:
        context.prec = 3
        result = project_ledger(source, packet, {LISTING: source.listings[0]})
    assert result.status == "OPENING_RECONCILED" and not result.issues
    assert result.projection_version == "settled-booking-v2"
    assert result.positions[0].quantity == Decimal("2.5")
    assert {row.currency: row.balance for row in result.cash} == {
        "USD": Decimal("100"),
        "EUR": Decimal("9"),
    }
    assert result.consumed_listings[0].company_id is None
    original = canonical_ledger_packet(packet)
    assert original["activity"][0]["gross_cash"] == "12.3456789012"
    assert original["activity"][0]["taxes"] == "2.3456789012"
    replay = c.PortfolioLedgerPreviewCreate.model_validate_json(packet.model_dump_json())
    replay.activity.reverse()
    assert project_ledger(source, replay, {LISTING: source.listings[0]}) == result


def test_fully_withheld_dividend_keeps_an_explicit_zero_cash_row() -> None:
    source, packet = anchor(), income_packet()
    dividend = packet.activity[0]
    assert isinstance(dividend, c.LedgerDividend)
    dividend.gross_cash, dividend.fees, dividend.taxes = Decimal(1), Decimal(0), Decimal(1)
    packet.activity = [dividend]
    result = project_ledger(source, packet, {LISTING: source.listings[0]})
    assert result.status == "OPENING_RECONCILED"
    assert {row.currency: row.balance for row in result.cash}["EUR"] == Decimal(0)


@pytest.mark.parametrize("kind", ["DIVIDEND", "TAX"])
def test_income_requires_explicit_v2_opt_in(kind: str) -> None:
    packet = income_packet().model_dump(mode="json")
    packet["contract_version"] = "portfolio-ledger-preview-v1"
    packet["activity"] = [row for row in packet["activity"] if row["kind"] == kind]
    with pytest.raises(ValidationError, match="require portfolio-ledger-preview-v2"):
        c.PortfolioLedgerPreviewCreate.model_validate(packet)


@pytest.mark.parametrize("field", ["gross_cash", "fees", "taxes"])
@pytest.mark.parametrize("invalid", [None, "", "#VALUE!", "-0.01", "NaN", 0.1])
def test_invalid_and_missing_dividend_amounts_fail_closed(field: str, invalid: object) -> None:
    packet = income_packet().model_dump(mode="json")
    packet["activity"][0][field] = invalid
    with pytest.raises(ValidationError):
        c.PortfolioLedgerPreviewCreate.model_validate(packet)


def test_dividend_deductions_and_explicit_required_fields() -> None:
    packet = income_packet().model_dump(mode="json")
    for field in ("fees", "taxes", "listing_id", "currency"):
        missing = dict(packet["activity"][0])
        missing.pop(field)
        with pytest.raises(ValidationError):
            c.LedgerDividend.model_validate(missing)
    packet["activity"][0]["taxes"] = "12.3"
    with localcontext() as context:
        context.prec = 2
        with pytest.raises(ValidationError, match="cannot exceed"):
            c.PortfolioLedgerPreviewCreate.model_validate(packet)


def test_income_only_listing_is_required_and_hash_bound_without_fabricated_holdings() -> None:
    source, packet = anchor(), income_packet()
    dividend = packet.activity[0]
    assert isinstance(dividend, c.LedgerDividend)
    other_id = uuid4()
    dividend.listing_id = other_id
    with pytest.raises(DomainError, match="existing exact listing"):
        project_ledger(source, packet, {LISTING: source.listings[0]})
    other = source.listings[0].model_copy(update={"listing_id": other_id})
    listings = {LISTING: source.listings[0], other_id: other}
    first = project_ledger(source, packet, listings)
    other.identity_source_ref = "different-reviewed-evidence"
    second = project_ledger(source, packet, listings)
    assert first.input_sha256 != second.input_sha256
    assert {row.listing_id for row in first.positions} == {LISTING}
    assert {row.listing_id for row in first.consumed_listings} == {LISTING, other_id}


def test_prior_tax_overdraft_cannot_be_repaired_by_later_dividend() -> None:
    source, packet = anchor(), income_packet()
    dividend, tax = packet.activity
    tax.effective_at = AT + timedelta(hours=1)
    result = project_ledger(source, packet, {LISTING: source.listings[0]})
    assert result.status == "BLOCKED"
    assert result.issues[0].code == "NEGATIVE_CASH" and result.issues[0].activity_id == tax.id


def test_projection_versions_cannot_be_mixed() -> None:
    source, packet = anchor(), income_packet()
    result = project_ledger(source, packet, {LISTING: source.listings[0]}).model_dump(mode="json")
    result["projection_version"] = "settled-booking-v1"
    with pytest.raises(ValidationError, match="versions must match"):
        c.PortfolioLedgerPreviewRead.model_validate(result)
