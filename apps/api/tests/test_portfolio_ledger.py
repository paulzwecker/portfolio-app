"""Synthetic numerical and source-boundary regression for the candidate ledger."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain import schemas as s
from portfolio_api.domain.services import DomainError
from portfolio_api.portfolio_ledger import project_ledger

AT = datetime(2026, 1, 1, tzinfo=UTC)
ACCOUNT = UUID("11111111-1111-4111-8111-111111111111")
LISTING = UUID("22222222-2222-4222-8222-222222222222")


def anchor() -> c.PortfolioLedgerAnchorRead:
    return c.PortfolioLedgerAnchorRead(
        portfolio_id=UUID("33333333-3333-4333-8333-333333333333"),
        snapshot=s.SnapshotRead(
            id=UUID("44444444-4444-4444-8444-444444444444"),
            portfolio_id=UUID("33333333-3333-4333-8333-333333333333"),
            actor="IMPORT",
            reason="Synthetic observed anchor",
            source="synthetic-source-v1",
            effective_at=AT,
            recorded_at=AT,
            completeness="COMPLETE",
            positions=[s.PositionInput(listing_id=LISTING, quantity=Decimal("2.5"))],
            cash_positions=[
                s.CashInput(currency="USD", balance=Decimal("100")),
                s.CashInput(currency="EUR", balance=Decimal("0")),
            ],
        ),
        listings=[
            c.LedgerListingRead(
                listing_id=LISTING,
                security_id=uuid4(),
                company_id=None,
                ticker="SYNTH",
                venue="XETRA",
                currency="USD",
                security_type="ETF",
                identity_source_ref="synthetic-reviewed-identity",
            )
        ],
        anchor_sha256="a" * 64,
    )


def evidence(record: str) -> c.LedgerEvidence:
    return c.LedgerEvidence(source_sha256="b" * 64, source_record_id=record)


def cash_activity(kind: str, sequence: int, amount: str) -> c.LedgerCashActivity:
    return c.LedgerCashActivity(
        id=UUID(int=100 + sequence),
        account_id=ACCOUNT,
        sequence=sequence,
        kind=kind,
        effective_at=AT + timedelta(days=sequence),
        evidence=evidence(str(sequence)),
        currency="USD",
        amount=Decimal(amount),
    )


def trade(kind: str = "BUY", sequence: int = 1) -> c.LedgerTrade:
    return c.LedgerTrade(
        id=UUID(int=100 + sequence),
        account_id=ACCOUNT,
        sequence=sequence,
        kind=kind,
        effective_at=AT + timedelta(days=sequence),
        evidence=evidence(str(sequence)),
        listing_id=LISTING,
        quantity=Decimal("1.25"),
        currency="USD",
        gross_cash=Decimal("10.10"),
        fees=Decimal("0.20"),
        taxes=Decimal("0.05"),
        trade_date=date(2026, 1, 1),
        settlement_date=date(2026, 1, 2),
    )


def proposal(
    source: c.PortfolioLedgerAnchorRead,
    activity: list[c.LedgerTrade | c.LedgerCashActivity] | None = None,
) -> c.PortfolioLedgerPreviewCreate:
    return c.PortfolioLedgerPreviewCreate(
        contract_version="portfolio-ledger-preview-v1",
        anchor_snapshot_id=source.snapshot.id,
        anchor_sha256=source.anchor_sha256,
        as_of=AT + timedelta(days=10),
        accounts=[
            c.LedgerOpeningAccount(
                account_id=ACCOUNT,
                name="Synthetic broker account",
                kind="BROKERAGE",
                broker_name="Synthetic Broker",
                evidence=evidence("opening"),
                positions=[c.LedgerPositionInput(listing_id=LISTING, quantity=Decimal("2.5"))],
                cash=[
                    c.LedgerCashInput(currency="USD", balance=Decimal("100")),
                    c.LedgerCashInput(currency="EUR", balance=Decimal("0")),
                ],
            )
        ],
        activity=activity or [],
    )


def replay(
    source: c.PortfolioLedgerAnchorRead, value: c.PortfolioLedgerPreviewCreate
) -> c.PortfolioLedgerPreviewRead:
    return project_ledger(source, value, {item.listing_id: item for item in source.listings})


def ending_statement(
    value: c.PortfolioLedgerPreviewCreate, quantity: str = "3.75", usd: str = "89.65"
) -> c.LedgerEndingStatement:
    return c.LedgerEndingStatement(
        effective_at=value.as_of,
        accounts=[
            c.LedgerEndingAccount(
                account_id=ACCOUNT,
                evidence=evidence("ending"),
                positions=[c.LedgerPositionInput(listing_id=LISTING, quantity=Decimal(quantity))],
                cash=[
                    c.LedgerCashInput(currency="USD", balance=Decimal(usd)),
                    c.LedgerCashInput(currency="EUR", balance=Decimal("0")),
                ],
            )
        ],
    )


def test_legacy_opening_only_input_hash_and_replay_remain_compatible() -> None:
    source = anchor()
    source.listings[0].security_id = UUID("77777777-7777-4777-8777-777777777777")
    value = proposal(source, [trade()])
    result = replay(source, value)
    assert result.input_sha256 == "eba696dd14efaa5eb43ddd36da8620371cb0d49d55c0f1a61c24abdf1d4cd09f"
    assert result.status == "OPENING_RECONCILED" and result.ending_status == "NOT_PROVIDED"
    assert result.ending_statement_at is None and not result.ending_reconciliation
    assert (
        replay(source, c.PortfolioLedgerPreviewCreate.model_validate_json(value.model_dump_json()))
        == result
    )


def test_ending_statement_reconciles_exact_account_and_portfolio_balances() -> None:
    source = anchor()
    value = proposal(source, [trade()])
    value.ending_statement = ending_statement(value)
    result = replay(source, value)
    assert result.status == "ENDING_RECONCILED" and result.ending_status == "MATCH"
    assert result.ending_statement_at == value.as_of and not result.issues
    assert len(result.ending_reconciliation) == 6
    assert {row.account_id for row in result.ending_reconciliation} == {None, ACCOUNT}
    assert all(
        row.status == "MATCH" and row.difference == 0 for row in result.ending_reconciliation
    )
    assert result.consumed_listings == source.listings
    assert result.consumed_listings[0].company_id is None
    assert c.PortfolioLedgerPreviewRead.model_validate_json(result.model_dump_json()) == result


def test_ending_differences_preserve_candidate_minus_observed_sign() -> None:
    source = anchor()
    value = proposal(source, [trade()])
    value.ending_statement = ending_statement(value, quantity="4", usd="80")
    result = replay(source, value)
    assert result.status == "BLOCKED" and result.ending_status == "MISMATCH"
    position = next(
        row
        for row in result.ending_reconciliation
        if row.account_id == ACCOUNT and row.domain == "POSITION"
    )
    cash = next(
        row
        for row in result.ending_reconciliation
        if row.account_id == ACCOUNT and row.key == "USD"
    )
    assert position.projected == Decimal("3.75") and position.observed == Decimal("4")
    assert position.difference == Decimal("-0.25") and cash.difference == Decimal("9.65")
    assert len([issue for issue in result.issues if issue.code == "ENDING_MISMATCH"]) == 4


@pytest.mark.parametrize("change", ["missing_zero", "extra_zero", "missing_position"])
def test_ending_missing_and_explicit_zero_never_coalesce(change: str) -> None:
    source = anchor()
    value = proposal(source, [trade()])
    value.ending_statement = ending_statement(value)
    observed = value.ending_statement.accounts[0]
    if change == "missing_zero":
        observed.cash.pop()
    elif change == "extra_zero":
        observed.cash.append(c.LedgerCashInput(currency="DKK", balance=Decimal("0")))
    else:
        observed.positions.clear()
    result = replay(source, value)
    assert result.status == "BLOCKED" and result.ending_status == "MISMATCH"
    difference = next(
        row
        for row in result.ending_reconciliation
        if row.account_id == ACCOUNT and row.status != "MATCH"
    )
    assert difference.difference is None
    if change == "extra_zero":
        assert (
            difference.status == "EXTRA_OBSERVATION"
            and difference.projected is None
            and difference.observed == 0
        )
    else:
        assert difference.status == "MISSING_OBSERVATION" and difference.observed is None


def test_ending_same_total_wrong_account_stays_blocking() -> None:
    source = anchor()
    value = proposal(source)
    second = value.accounts[0].model_copy(
        deep=True, update={"account_id": uuid4(), "evidence": evidence("opening-2")}
    )
    value.accounts[0].positions[0].quantity = Decimal("1")
    value.accounts[0].cash[0].balance = Decimal("50")
    second.positions[0].quantity = Decimal("1.5")
    second.cash = [c.LedgerCashInput(currency="USD", balance=Decimal("50"))]
    value.accounts.append(second)
    first_observed = ending_statement(value, quantity="1.5", usd="50").accounts[0]
    second_observed = c.LedgerEndingAccount(
        account_id=second.account_id,
        evidence=evidence("ending-2"),
        positions=[c.LedgerPositionInput(listing_id=LISTING, quantity=Decimal("1"))],
        cash=[c.LedgerCashInput(currency="USD", balance=Decimal("50"))],
    )
    value.ending_statement = c.LedgerEndingStatement(
        effective_at=value.as_of, accounts=[first_observed, second_observed]
    )
    result = replay(source, value)
    assert result.status == "BLOCKED" and result.ending_status == "MISMATCH"
    assert all(
        row.status == "MATCH" for row in result.ending_reconciliation if row.account_id is None
    )
    assert len([row for row in result.ending_reconciliation if row.status == "DIFFERENCE"]) == 2


@pytest.mark.parametrize("empty", [False, True])
def test_missing_ending_account_is_blocking_even_when_its_balances_are_empty(empty: bool) -> None:
    source = anchor()
    value = proposal(source)
    if empty:
        value.accounts.append(
            c.LedgerOpeningAccount(
                account_id=uuid4(),
                name="Synthetic empty account",
                kind="BROKERAGE",
                broker_name="Synthetic broker",
                evidence=evidence("empty-opening"),
                positions=[],
                cash=[],
            )
        )
        value.ending_statement = ending_statement(value, quantity="2.5", usd="100")
    else:
        value.ending_statement = c.LedgerEndingStatement(effective_at=value.as_of, accounts=[])
    result = replay(source, value)
    assert result.status == "BLOCKED" and result.ending_status == "MISMATCH"
    assert any(issue.code == "ENDING_ACCOUNT_MISSING" for issue in result.issues)


def test_ending_hash_and_replay_bind_observations_and_provenance() -> None:
    source = anchor()
    value = proposal(source, [trade()])
    before = replay(source, value).input_sha256
    value.ending_statement = ending_statement(value)
    first = replay(source, value)
    assert first.input_sha256 != before
    recovered = c.PortfolioLedgerPreviewCreate.model_validate_json(value.model_dump_json())
    assert recovered.ending_statement is not None
    recovered.ending_statement.accounts[0].cash.reverse()
    assert replay(source, recovered) == first
    recovered.ending_statement.accounts[0].evidence = evidence("new-ending-source")
    assert replay(source, recovered).input_sha256 != first.input_sha256
    recovered.ending_statement.accounts[0].cash[0].balance = Decimal("1")
    assert replay(source, recovered).input_sha256 != first.input_sha256


@pytest.mark.parametrize(
    "change",
    [
        "time",
        "naive",
        "unknown_account",
        "duplicate_account",
        "duplicate_position",
        "duplicate_cash",
        "duplicate_evidence",
        "missing_amount",
        "float",
        "negative",
    ],
)
def test_ending_contract_rejects_ambiguous_or_invalid_observations(change: str) -> None:
    value = proposal(anchor(), [trade()])
    value.ending_statement = ending_statement(value)
    data = value.model_dump(mode="json")
    ending = data["ending_statement"]
    account = ending["accounts"][0]
    if change == "time":
        ending["effective_at"] = (value.as_of - timedelta(seconds=1)).isoformat()
    if change == "naive":
        ending["effective_at"] = "2026-01-11T00:00:00"
    if change == "unknown_account":
        account["account_id"] = str(uuid4())
    if change == "duplicate_account":
        ending["accounts"].append(dict(account))
    if change == "duplicate_position":
        account["positions"].append(dict(account["positions"][0]))
    if change == "duplicate_cash":
        account["cash"].append(dict(account["cash"][0]))
    if change == "duplicate_evidence":
        second_id = str(uuid4())
        opening = dict(
            data["accounts"][0],
            account_id=second_id,
            evidence=evidence("second").model_dump(mode="json"),
            positions=[],
            cash=[],
        )
        data["accounts"].append(opening)
        ending["accounts"].append(dict(account, account_id=second_id))
    if change == "missing_amount":
        account["cash"][0]["balance"] = None
    if change == "float":
        account["cash"][0]["balance"] = 89.65
    if change == "negative":
        account["positions"][0]["quantity"] = "-1"
    with pytest.raises(ValidationError):
        c.PortfolioLedgerPreviewCreate.model_validate(data)


def test_ending_equivalent_timestamp_offsets_use_the_same_instant() -> None:
    source = anchor()
    value = proposal(source, [trade()])
    observed = ending_statement(value).model_dump(mode="json")
    observed["effective_at"] = "2026-01-11T02:00:00+02:00"
    value.ending_statement = c.LedgerEndingStatement.model_validate(observed)
    assert replay(source, value).status == "ENDING_RECONCILED"


def test_ending_is_not_evaluated_when_opening_does_not_reconcile() -> None:
    source = anchor()
    value = proposal(source, [trade()])
    value.accounts[0].cash[0].balance = Decimal("99")
    value.ending_statement = ending_statement(value)
    result = replay(source, value)
    assert result.status == "BLOCKED" and result.ending_status == "NOT_EVALUATED"
    assert not result.ending_reconciliation and not result.accounts


def test_matching_ending_cannot_clear_an_intermediate_negative_balance() -> None:
    source = anchor()
    value = proposal(
        source, [cash_activity("WITHDRAWAL", 1, "101"), cash_activity("DEPOSIT", 2, "101")]
    )
    value.ending_statement = ending_statement(value, quantity="2.5", usd="100")
    result = replay(source, value)
    assert result.ending_status == "MATCH" and result.status == "BLOCKED"
    assert any(issue.code == "NEGATIVE_CASH" for issue in result.issues)


@pytest.mark.parametrize("domain", ["positions", "cash"])
def test_ending_work_budget_is_enforced_across_accounts(domain: str) -> None:
    value = proposal(anchor())
    data = ending_statement(value).model_dump(mode="json")
    first = data["accounts"][0]
    second = dict(
        first,
        account_id=str(uuid4()),
        evidence=evidence("ending-2").model_dump(mode="json"),
        positions=[],
        cash=[],
    )
    if domain == "positions":
        first["positions"] = [
            {"listing_id": str(UUID(int=1000 + index)), "quantity": "0"} for index in range(1000)
        ]
        second["positions"] = [{"listing_id": str(UUID(int=3000)), "quantity": "0"}]
    else:
        currencies = ["A" + chr(65 + index // 26) + chr(65 + index % 26) for index in range(101)]
        first["cash"] = [{"currency": key, "balance": "0"} for key in currencies[:100]]
        second["cash"] = [{"currency": currencies[-1], "balance": "0"}]
    data["accounts"].append(second)
    with pytest.raises(ValidationError, match="Ending scope exceeds"):
        c.LedgerEndingStatement.model_validate(data)


def test_ending_only_listing_identity_is_retained_and_bound_to_the_hash() -> None:
    source = anchor()
    value = proposal(source, [trade()])
    value.ending_statement = ending_statement(value)
    additional = source.listings[0].model_copy(
        update={"listing_id": uuid4(), "identity_source_ref": "ending-only-evidence"}
    )
    value.ending_statement.accounts[0].positions.append(
        c.LedgerPositionInput(listing_id=additional.listing_id, quantity=Decimal("0"))
    )
    identities = {LISTING: source.listings[0], additional.listing_id: additional}
    first = project_ledger(source, value, identities)
    assert first.status == "BLOCKED" and first.ending_status == "MISMATCH"
    assert additional in first.consumed_listings
    identities[additional.listing_id] = additional.model_copy(
        update={"identity_source_ref": "changed-identity-evidence"}
    )
    assert project_ledger(source, value, identities).input_sha256 != first.input_sha256


def test_matching_ending_cannot_clear_consolidated_storage_overflow() -> None:
    source = anchor()
    value = proposal(source, [cash_activity("DEPOSIT", 1, "500000000000000000")])
    second = value.accounts[0].model_copy(
        deep=True,
        update={
            "account_id": uuid4(),
            "evidence": evidence("opening-2"),
            "positions": [],
            "cash": [c.LedgerCashInput(currency="USD", balance=Decimal("500000000000000000"))],
        },
    )
    value.accounts[0].cash[0].balance = Decimal("1")
    source.snapshot.cash_positions[0].balance = Decimal("500000000000000001")
    value.accounts.append(second)
    observed = ending_statement(value, quantity="2.5", usd="500000000000000001").accounts[0]
    value.ending_statement = c.LedgerEndingStatement(
        effective_at=value.as_of,
        accounts=[
            observed,
            c.LedgerEndingAccount(
                account_id=second.account_id,
                evidence=evidence("ending-2"),
                positions=[],
                cash=second.cash,
            ),
        ],
    )
    result = replay(source, value)
    assert result.ending_status == "MATCH" and result.status == "BLOCKED"
    assert any(issue.code == "BALANCE_OUT_OF_RANGE" for issue in result.issues)


def test_settled_buy_sell_and_cash_activity_reconcile_exactly() -> None:
    source = anchor()
    value = proposal(
        source,
        [
            trade(),
            trade("SELL", 2),
            cash_activity("DEPOSIT", 3, "5.01"),
            cash_activity("WITHDRAWAL", 4, "2"),
            cash_activity("FEE", 5, "0.10"),
        ],
    )
    result = replay(source, value)
    assert result.status == "OPENING_RECONCILED" and not result.issues
    assert result.positions[0].quantity == Decimal("2.5")
    assert {row.currency: row.balance for row in result.cash} == {
        "EUR": Decimal("0"),
        "USD": Decimal("102.41"),
    }
    assert all(row.status == "MATCH" for row in result.opening_reconciliation)
    serialized = result.model_dump(mode="json")
    assert serialized["positions"][0]["quantity"] == "2.50"
    assert serialized["preview_only"] is True
    assert c.PortfolioLedgerPreviewRead.model_validate(serialized) == result


def test_exact_projection_is_independent_of_ambient_decimal_precision() -> None:
    source = anchor()
    source.snapshot.positions[0].quantity = Decimal("100000000000000000.1234567890")
    value = proposal(source, [trade().model_copy(update={"quantity": Decimal("0.0000000001")})])
    value.accounts[0].positions[0].quantity = source.snapshot.positions[0].quantity
    with localcontext() as context:
        context.prec = 6
        result = replay(source, value)
    assert result.positions[0].quantity == Decimal("100000000000000000.1234567891")


def test_replay_and_input_hash_are_deterministic_but_detect_material_changes() -> None:
    source = anchor()
    value = proposal(source, [trade(), cash_activity("DEPOSIT", 2, "2")])
    before = value.model_dump_json()
    first = replay(source, value)
    recovered = c.PortfolioLedgerPreviewCreate.model_validate_json(before)
    recovered.activity.reverse()
    recovered.accounts[0].cash.reverse()
    assert replay(source, recovered) == first
    assert value.model_dump_json() == before
    recovered.activity[0].evidence = evidence("changed-source-record")
    assert replay(source, recovered).input_sha256 != first.input_sha256


@pytest.mark.parametrize("domain", ["positions", "cash"])
def test_omitted_explicit_zero_or_position_blocks_opening_without_projection(domain: str) -> None:
    source = anchor()
    value = proposal(source)
    if domain == "cash":
        value.accounts[0].cash.pop()
    else:
        value.accounts[0].positions.clear()
    result = replay(source, value)
    assert result.status == "BLOCKED" and result.issues[0].code == "OPENING_MISMATCH"
    row = next(row for row in result.opening_reconciliation if row.status == "MISSING_OPENING")
    assert row.opening is None and row.difference is None
    assert not result.positions and not result.cash and not result.accounts


def test_incorrect_or_extra_opening_is_never_silently_excluded() -> None:
    source = anchor()
    value = proposal(source)
    value.accounts[0].positions[0].quantity = Decimal("2.6")
    value.accounts[0].cash.append(c.LedgerCashInput(currency="DKK", balance=Decimal("0")))
    result = replay(source, value)
    assert result.status == "BLOCKED"
    difference = next(row for row in result.opening_reconciliation if row.domain == "POSITION")
    assert difference.difference == Decimal("0.1")
    extra = next(row for row in result.opening_reconciliation if row.key == "DKK")
    assert extra.status == "EXTRA_OPENING" and extra.observed is None


@pytest.mark.parametrize(
    "kind,code", [("SELL", "NEGATIVE_POSITION"), ("WITHDRAWAL", "NEGATIVE_CASH")]
)
def test_intermediate_short_or_overdraft_stays_blocked_after_recovery(kind: str, code: str) -> None:
    source = anchor()
    activity: list[c.LedgerTrade | c.LedgerCashActivity]
    if kind == "SELL":
        activity = [
            trade("SELL").model_copy(update={"quantity": Decimal("3")}),
            trade("BUY", 2).model_copy(update={"quantity": Decimal("3")}),
        ]
    else:
        activity = [cash_activity("WITHDRAWAL", 1, "101"), cash_activity("DEPOSIT", 2, "101")]
    result = replay(source, proposal(source, activity))
    assert result.status == "BLOCKED" and code in {issue.code for issue in result.issues}


def test_same_timestamp_activity_uses_declared_sequence() -> None:
    source = anchor()
    withdrawal = cash_activity("WITHDRAWAL", 2, "101").model_copy(
        update={"effective_at": AT + timedelta(days=1)}
    )
    value = proposal(source, [withdrawal, cash_activity("DEPOSIT", 1, "1")])
    result = replay(source, value)
    assert result.status == "OPENING_RECONCILED"
    assert next(row.balance for row in result.cash if row.currency == "USD") == 0


def test_split_accounts_reconcile_without_spending_another_accounts_cash() -> None:
    source = anchor()
    value = proposal(source, [cash_activity("WITHDRAWAL", 1, "2")])
    other = value.accounts[0].model_copy(
        deep=True, update={"account_id": uuid4(), "evidence": evidence("second-account")}
    )
    value.accounts[0].cash[0].balance = Decimal("1")
    value.accounts[0].positions[0].quantity = Decimal("0.5")
    other.cash = [c.LedgerCashInput(currency="USD", balance=Decimal("99"))]
    other.positions[0].quantity = Decimal("2")
    value.accounts.append(other)
    result = replay(source, value)
    assert all(row.status == "MATCH" for row in result.opening_reconciliation)
    assert result.status == "BLOCKED" and result.issues[0].account_id == ACCOUNT
    assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("98")


def test_unallocated_opening_can_reconcile_without_inventing_a_broker_or_trade() -> None:
    source = anchor()
    value = proposal(source)
    value.accounts[0].kind = "UNALLOCATED_OPENING"
    value.accounts[0].broker_name = None
    assert (
        replay(source, c.PortfolioLedgerPreviewCreate.model_validate(value.model_dump())).status
        == "OPENING_RECONCILED"
    )


def test_new_exact_listing_and_cash_currency_need_no_fx_or_fake_company() -> None:
    source = anchor()
    new = source.listings[0].model_copy(update={"listing_id": uuid4(), "currency": "DKK"})
    deposit = cash_activity("DEPOSIT", 1, "20").model_copy(update={"currency": "DKK"})
    purchase = trade("BUY", 2).model_copy(update={"listing_id": new.listing_id, "currency": "DKK"})
    result = project_ledger(
        source,
        proposal(source, [deposit, purchase]),
        {LISTING: source.listings[0], new.listing_id: new},
    )
    assert result.status == "OPENING_RECONCILED"
    assert next(row.balance for row in result.cash if row.currency == "DKK") == Decimal("9.65")
    assert next(
        row.quantity for row in result.positions if row.listing_id == new.listing_id
    ) == Decimal("1.25")


@pytest.mark.parametrize("missing", [None, "#N/A", "NaN", "Infinity"])
def test_unavailable_amounts_never_become_zero(missing: object) -> None:
    value = proposal(anchor(), [trade()]).model_dump(mode="json")
    value["activity"][0]["gross_cash"] = missing
    with pytest.raises(ValidationError):
        c.PortfolioLedgerPreviewCreate.model_validate(value)


def test_unsupported_anchor_and_future_settlement_fail_closed() -> None:
    source = anchor()
    value = proposal(source, [trade()])
    source.snapshot.completeness = "PARTIAL"
    with pytest.raises(DomainError, match="complete opening"):
        replay(source, value)
    source.snapshot.completeness = "COMPLETE"
    item = value.activity[0]
    assert isinstance(item, c.LedgerTrade)
    item.settlement_date = date(2026, 2, 1)
    with pytest.raises(DomainError, match="settled trades"):
        replay(source, value)


def test_later_settlement_cannot_be_backdated_before_intervening_activity() -> None:
    item = trade().model_dump(mode="json")
    item["settlement_date"] = "2026-01-10"
    with pytest.raises(ValidationError, match="Settlement cannot follow"):
        c.LedgerTrade.model_validate(item)


def test_source_booking_offset_preserves_local_settlement_date_at_utc_boundary() -> None:
    source = anchor()
    item = trade().model_dump(mode="json")
    item["effective_at"] = "2026-01-02T00:15:00+11:00"
    captured = c.LedgerTrade.model_validate(item)
    assert captured.effective_at.utcoffset() == timedelta(hours=11)
    value = proposal(source, [captured])
    value.as_of = datetime(2026, 1, 1, 14, tzinfo=UTC)
    result = replay(source, value)
    assert result.status == "OPENING_RECONCILED"
    assert captured.effective_at.date() == date(2026, 1, 2)


def test_aggregate_overflow_blocks_even_when_each_account_fits_storage() -> None:
    source = anchor()
    value = proposal(source, [cash_activity("DEPOSIT", 1, "500000000000000000")])
    other = value.accounts[0].model_copy(
        deep=True,
        update={
            "account_id": uuid4(),
            "evidence": evidence("second-account"),
            "positions": [],
            "cash": [c.LedgerCashInput(currency="USD", balance=Decimal("500000000000000000"))],
        },
    )
    value.accounts[0].cash[0].balance = Decimal("1")
    source.snapshot.cash_positions[0].balance = Decimal("500000000000000001")
    value.accounts.append(other)
    result = replay(source, value)
    assert result.status == "BLOCKED"
    assert any(
        row.code == "BALANCE_OUT_OF_RANGE" and row.account_id is None for row in result.issues
    )


def test_additional_listing_identity_drift_changes_proposal_hash() -> None:
    source = anchor()
    extra = source.listings[0].model_copy(update={"listing_id": uuid4()})
    value = proposal(source, [trade().model_copy(update={"listing_id": extra.listing_id})])
    identities = {LISTING: source.listings[0], extra.listing_id: extra}
    first = project_ledger(source, value, identities)
    identities[extra.listing_id] = extra.model_copy(
        update={"identity_source_ref": "revised-evidence"}
    )
    assert project_ledger(source, value, identities).input_sha256 != first.input_sha256


@pytest.mark.parametrize(
    "change",
    ["hash", "snapshot", "account", "currency", "listing", "boundary", "cutoff", "unallocated"],
)
def test_invalid_identity_scope_or_time_is_rejected(change: str) -> None:
    source = anchor()
    value = proposal(source, [trade()])
    item = value.activity[0]
    assert isinstance(item, c.LedgerTrade)
    if change == "hash":
        value.anchor_sha256 = "c" * 64
    if change == "snapshot":
        value.anchor_snapshot_id = uuid4()
    if change == "account":
        item.account_id = uuid4()
    if change == "currency":
        item.currency = "EUR"
    if change == "listing":
        item.listing_id = uuid4()
    if change == "boundary":
        item.effective_at = AT
    if change == "cutoff":
        item.effective_at = value.as_of + timedelta(seconds=1)
    if change == "unallocated":
        value.accounts[0].kind = "UNALLOCATED_OPENING"
        value.accounts[0].broker_name = None
    with pytest.raises(DomainError):
        replay(source, value)


@pytest.mark.parametrize(
    "change",
    [
        "float",
        "bool",
        "missing_fee",
        "negative",
        "naive",
        "duplicate_id",
        "duplicate_source",
        "duplicate_sequence",
        "unsupported",
        "future",
        "unknown_cost",
    ],
)
def test_strict_contract_rejects_missing_unsupported_or_ambiguous_records(change: str) -> None:
    value = proposal(anchor(), [trade()]).model_dump(mode="json")
    item = value["activity"][0]
    if change == "float":
        item["quantity"] = 1.25
    if change == "bool":
        item["gross_cash"] = True
    if change == "missing_fee":
        item.pop("fees")
    if change == "negative":
        item["fees"] = "-1"
    if change == "naive":
        item["effective_at"] = "2026-01-02T00:00:00"
    if change == "duplicate_id":
        value["activity"].append(dict(item))
    if change == "duplicate_source":
        item["evidence"] = value["accounts"][0]["evidence"]
    if change == "duplicate_sequence":
        other = trade("SELL", 2).model_dump(mode="json")
        other["sequence"] = 1
        value["activity"].append(other)
    if change == "unsupported":
        item["kind"] = "FX"
    if change == "future":
        value["as_of"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    if change == "unknown_cost":
        value["accounts"][0]["positions"][0]["cost_basis"] = "0"
    with pytest.raises(ValidationError):
        c.PortfolioLedgerPreviewCreate.model_validate(value)
