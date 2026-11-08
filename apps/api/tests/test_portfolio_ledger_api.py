"""Real PostgreSQL/API ledger previews must preserve the canonical baseline."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from psycopg import Connection as PsycopgConnection
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_portfolio_ledger import AT, cash_activity, evidence, proposal, trade

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Listing,
    Portfolio,
    Security,
)

pytestmark = pytest.mark.integration


def source(engine: Engine) -> UUID:
    with Session(engine) as session, session.begin():
        company = services.create_company(session, s.CompanyCreate(name="Synthetic Ledger Issuer"))
        stock = services.create_security(
            session,
            company.id,
            s.SecurityCreate(name="Synthetic Common", security_type="COMMON_STOCK"),
        )
        listing = services.create_listing(
            session, stock.id, s.ListingCreate(ticker="SYNTH", venue="NASDAQ", currency="USD")
        )
        fund = Security(name="Synthetic Global ETF", security_type="ETF", company_id=None)
        session.add(fund)
        session.flush()
        fund_listing = Listing(
            security_id=fund.id,
            ticker="SYNF",
            venue="XETRA",
            currency="EUR",
            identity_source_ref="synthetic-reviewed-fund",
        )
        session.add(fund_listing)
        session.flush()
        portfolio = services.create_portfolio(
            session, s.PortfolioCreate(name="Synthetic Ledger Portfolio", base_currency="EUR")
        )
        services.record_holdings(
            session,
            portfolio.id,
            s.SnapshotCreate(
                actor="IMPORT",
                reason="Synthetic immutable source",
                source="synthetic-source-v1",
                effective_at=AT,
                completeness="COMPLETE",
                positions=[
                    s.PositionInput(listing_id=listing.id, quantity=Decimal("2.5")),
                    s.PositionInput(listing_id=fund_listing.id, quantity=Decimal("1")),
                ],
                cash_positions=[
                    s.CashInput(currency="USD", balance=Decimal("100")),
                    s.CashInput(currency="EUR", balance=Decimal("0")),
                ],
            ),
        )
        target = services.create_targets(
            session,
            portfolio.id,
            s.TargetCreate(
                actor="IMPORT",
                reason="Synthetic independent target",
                effective_at=AT,
                allocations=[s.AllocationInput(company_id=company.id, weight=Decimal("1"))],
            ),
        )
        services.accept_targets(session, portfolio.id, target.id)
        return portfolio.id


def candidate(anchor: c.PortfolioLedgerAnchorRead) -> c.PortfolioLedgerPreviewCreate:
    common = next(item for item in anchor.listings if item.security_type == "COMMON_STOCK")
    activity = trade().model_copy(update={"listing_id": common.listing_id})
    value = proposal(anchor, [activity])
    value.accounts[0].positions = [
        c.LedgerPositionInput.model_validate(row.model_dump()) for row in anchor.snapshot.positions
    ]
    value.accounts[0].cash = [
        c.LedgerCashInput.model_validate(row.model_dump()) for row in anchor.snapshot.cash_positions
    ]
    return value


def ending_candidate(
    anchor: c.PortfolioLedgerAnchorRead,
    value: c.PortfolioLedgerPreviewCreate,
) -> c.LedgerEndingStatement:
    common = next(item for item in anchor.listings if item.security_type == "COMMON_STOCK")
    return c.LedgerEndingStatement(
        effective_at=value.as_of,
        accounts=[
            c.LedgerEndingAccount(
                account_id=value.accounts[0].account_id,
                evidence=evidence("api-ending"),
                positions=[
                    c.LedgerPositionInput(
                        listing_id=row.listing_id,
                        quantity=Decimal("3.75")
                        if row.listing_id == common.listing_id
                        else row.quantity,
                    )
                    for row in value.accounts[0].positions
                ],
                cash=[
                    c.LedgerCashInput(currency="USD", balance=Decimal("89.65")),
                    c.LedgerCashInput(currency="EUR", balance=Decimal("0")),
                ],
            )
        ],
    )


def baseline(engine: Engine, portfolio_id: UUID) -> dict[str, object]:
    with Session(engine) as session:
        overview = queries.overview(session, portfolio_id)
        sequences = session.execute(
            text(
                "SELECT sequencename, last_value FROM pg_sequences "
                "WHERE schemaname = current_schema() ORDER BY sequencename"
            )
        ).all()
        return {
            "snapshot": overview.snapshot.model_dump(mode="json") if overview.snapshot else None,
            "targets": overview.target_revision.model_dump(mode="json")
            if overview.target_revision
            else None,
            "counts": table_counts(engine),
            "sequences": [tuple(row) for row in sequences],
        }


def test_authenticated_exact_preview_replay_is_sql_read_only_and_preserves_canonical_state(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id = source(postgres_engine)
    before = baseline(postgres_engine, portfolio_id)
    with postgres_engine.connect() as connection:
        original_read_only = cast(
            PsycopgConnection[tuple[object, ...]], connection.connection.driver_connection
        ).read_only
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    original = ledger.portfolio_ledger_anchor
    transaction_modes = []

    def inspect(session: Session, portfolio_id: UUID) -> c.PortfolioLedgerAnchorRead:
        transaction_modes.append(
            (
                session.scalar(text("SHOW transaction_read_only")),
                session.scalar(text("SHOW transaction_isolation")),
            )
        )
        return original(session, portfolio_id)

    monkeypatch.setattr(ledger, "portfolio_ledger_anchor", inspect)
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        path = f"/v1/portfolios/{portfolio_id}/ledger"
        assert client.get(f"{path}/anchor").status_code == 401
        assert client.post(f"{path}/preview", json={}).status_code == 401
        headers = {"x-api-access-token": "synthetic-token"}
        response = client.get(f"{path}/anchor", headers=headers)
        assert response.status_code == 200
        anchor = c.PortfolioLedgerAnchorRead.model_validate(response.json())
        fund = next(item for item in anchor.listings if item.security_type == "ETF")
        assert fund.company_id is None and fund.identity_source_ref == "synthetic-reviewed-fund"
        value = candidate(anchor).model_dump(mode="json")
        first = client.post(f"{path}/preview", headers=headers, json=value)
        assert first.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(first.json())
        assert result.status == "OPENING_RECONCILED" and result.preview_only and not result.issues
        common = next(item for item in anchor.listings if item.security_type == "COMMON_STOCK")
        assert next(
            row.quantity for row in result.positions if row.listing_id == common.listing_id
        ) == Decimal("3.75")
        assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("89.65")
        assert next(row.balance for row in result.cash if row.currency == "EUR") == Decimal("0")
        assert client.post(f"{path}/preview", headers=headers, json=value).json() == first.json()
        value["accounts"][0]["cash"].pop()
        rejected = client.post(f"{path}/preview", headers=headers, json=value)
        assert rejected.status_code == 200 and rejected.json()["status"] == "BLOCKED"
        assert (
            client.get(f"/v1/portfolios/{uuid4()}/ledger/anchor", headers=headers).status_code
            == 404
        )
    assert transaction_modes and set(transaction_modes) == {("on", "repeatable read")}
    assert baseline(postgres_engine, portfolio_id) == before
    with postgres_engine.connect() as connection:
        assert (
            cast(
                PsycopgConnection[tuple[object, ...]], connection.connection.driver_connection
            ).read_only
            is original_read_only
        )
        assert connection.scalar(text("SHOW transaction_read_only")) == "off"
        assert connection.scalar(text("SHOW transaction_isolation")) == "read committed"


def test_guided_v2_cash_activity_replays_read_only(postgres_engine: Engine) -> None:
    portfolio_id = source(postgres_engine)
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        path = f"/v1/portfolios/{portfolio_id}/ledger"
        headers = {"x-api-access-token": "synthetic-token"}
        anchor = c.PortfolioLedgerAnchorRead.model_validate(
            client.get(f"{path}/anchor", headers=headers).json()
        )
        value = candidate(anchor)
        value.contract_version = "portfolio-ledger-preview-v2"
        value.activity = [cash_activity("DEPOSIT", 1, "1.25"), cash_activity("TAX", 2, "0.25")]
        payload = value.model_dump(mode="json")
        response = client.post(f"{path}/preview", headers=headers, json=payload)
        assert response.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(response.json())
        assert result.status == "OPENING_RECONCILED" and result.activity_count == 2
        assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("101")
        assert next(row.balance for row in result.cash if row.currency == "EUR") == Decimal("0")
        assert (
            client.post(f"{path}/preview", headers=headers, json=payload).json() == response.json()
        )
        payload["activity"][1]["evidence"] = payload["activity"][0]["evidence"]
        assert client.post(f"{path}/preview", headers=headers, json=payload).status_code == 422
    assert baseline(postgres_engine, portfolio_id) == before


def test_guided_ending_after_cash_activity_preserves_baseline(postgres_engine: Engine) -> None:
    portfolio_id = source(postgres_engine)
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        path = f"/v1/portfolios/{portfolio_id}/ledger"
        headers = {"x-api-access-token": "synthetic-token"}
        anchor = c.PortfolioLedgerAnchorRead.model_validate(
            client.get(f"{path}/anchor", headers=headers).json()
        )
        value = candidate(anchor)
        value.contract_version = "portfolio-ledger-preview-v2"
        value.activity = [cash_activity("DEPOSIT", 1, "1.25")]
        value.ending_statement = c.LedgerEndingStatement(
            effective_at=value.as_of,
            accounts=[
                c.LedgerEndingAccount(
                    account_id=value.accounts[0].account_id,
                    evidence=evidence("guided-ending"),
                    positions=value.accounts[0].positions,
                    cash=[
                        c.LedgerCashInput(currency="USD", balance=Decimal("101.25")),
                        c.LedgerCashInput(currency="EUR", balance=Decimal("0")),
                    ],
                )
            ],
        )
        payload = value.model_dump(mode="json")
        response = client.post(f"{path}/preview", headers=headers, json=payload)
        assert response.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(response.json())
        assert result.status == "ENDING_RECONCILED" and result.ending_status == "MATCH"
        assert (
            client.post(f"{path}/preview", headers=headers, json=payload).json() == response.json()
        )
        payload["ending_statement"]["accounts"][0]["cash"].pop()
        missing = client.post(f"{path}/preview", headers=headers, json=payload)
        assert missing.status_code == 200 and missing.json()["status"] == "BLOCKED"
        assert any(
            row["status"] == "MISSING_OBSERVATION" and row["key"] == "EUR"
            for row in missing.json()["ending_reconciliation"]
        )
    assert baseline(postgres_engine, portfolio_id) == before


def test_guided_v2_opening_at_anchor_boundary_preserves_canonical_state(
    postgres_engine: Engine,
) -> None:
    portfolio_id = source(postgres_engine)
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        path = f"/v1/portfolios/{portfolio_id}/ledger"
        headers = {"x-api-access-token": "synthetic-token"}
        anchor = c.PortfolioLedgerAnchorRead.model_validate(
            client.get(f"{path}/anchor", headers=headers).json()
        )
        value = candidate(anchor)
        value.contract_version = "portfolio-ledger-preview-v2"
        value.as_of = anchor.snapshot.effective_at
        value.activity = []
        payload = value.model_dump(mode="json")
        response = client.post(f"{path}/preview", headers=headers, json=payload)
        assert response.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(response.json())
        assert result.status == "OPENING_RECONCILED" and not result.issues
        assert result.as_of == anchor.snapshot.effective_at and result.activity_count == 0
        assert result.ending_status == "NOT_PROVIDED"
        assert result.projection_version == "settled-booking-v2"
        assert (
            client.post(f"{path}/preview", headers=headers, json=payload).json() == response.json()
        )
    assert baseline(postgres_engine, portfolio_id) == before


def test_ending_statement_api_replay_and_rejections_preserve_the_read_only_baseline(
    postgres_engine: Engine,
) -> None:
    portfolio_id = source(postgres_engine)
    with Session(postgres_engine) as session:
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
        schema = str(session.scalar(text("SELECT current_schema()")))
    value = candidate(anchor)
    value.ending_statement = ending_candidate(anchor, value)
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings()
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            path = f"/v1/portfolios/{portfolio_id}/ledger/preview"
            payload = value.model_dump(mode="json")
            response = client.post(path, json=payload)
            assert response.status_code == 200
            result = c.PortfolioLedgerPreviewRead.model_validate(response.json())
            assert result.status == "ENDING_RECONCILED" and result.ending_status == "MATCH"
            assert (
                result.ending_statement_at == value.as_of and len(result.ending_reconciliation) == 8
            )
            assert all(row.difference == 0 for row in result.ending_reconciliation)
            assert client.post(path, json=payload).json() == response.json()

            missing_zero = value.model_dump(mode="json")
            missing_zero["ending_statement"]["accounts"][0]["cash"].pop()
            missing = client.post(path, json=missing_zero)
            assert missing.status_code == 200 and missing.json()["status"] == "BLOCKED"
            rows = missing.json()["ending_reconciliation"]
            euro = next(
                row for row in rows if row["account_id"] is not None and row["key"] == "EUR"
            )
            assert euro["status"] == "MISSING_OBSERVATION" and euro["observed"] is None
            assert euro["projected"] == "0.0000000000"

            changed_value = value.model_dump(mode="json")
            changed_value["ending_statement"]["accounts"][0]["cash"][0]["balance"] = "89.64"
            changed = client.post(path, json=changed_value)
            assert changed.status_code == 200 and changed.json()["status"] == "BLOCKED"
            assert changed.json()["input_sha256"] != result.input_sha256
            unknown_listing = value.model_dump(mode="json")
            unknown_listing["ending_statement"]["accounts"][0]["positions"][0]["listing_id"] = str(
                uuid4()
            )
            assert client.post(path, json=unknown_listing).status_code == 422
            unknown_account = value.model_dump(mode="json")
            unknown_account["ending_statement"]["accounts"][0]["account_id"] = str(uuid4())
            assert client.post(path, json=unknown_account).status_code == 422
            wrong_time = value.model_dump(mode="json")
            wrong_time["ending_statement"]["effective_at"] = (
                value.as_of - timedelta(seconds=1)
            ).isoformat()
            assert client.post(path, json=wrong_time).status_code == 422
        with reader.connect() as connection:
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
    finally:
        reader.dispose()
    assert baseline(postgres_engine, portfolio_id) == before


def test_ending_only_listing_metadata_is_verified_and_returned_without_writes(
    postgres_engine: Engine,
) -> None:
    portfolio_id = source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
        fund = next(item for item in anchor.listings if item.security_type == "ETF")
        additional = Listing(
            security_id=fund.security_id,
            ticker="SYNF-ALT",
            venue="ALT",
            currency="EUR",
            identity_source_ref="synthetic-ending-only",
        )
        session.add(additional)
        session.flush()
        additional_id = additional.id
    value = candidate(anchor)
    value.ending_statement = ending_candidate(anchor, value)
    value.ending_statement.accounts[0].positions.append(
        c.LedgerPositionInput(listing_id=additional_id, quantity=Decimal("0"))
    )
    before = baseline(postgres_engine, portfolio_id)
    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        response = client.post(
            f"/v1/portfolios/{portfolio_id}/ledger/preview", json=value.model_dump(mode="json")
        )
        assert response.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(response.json())
        assert result.status == "BLOCKED" and result.ending_status == "MISMATCH"
        identity = next(row for row in result.consumed_listings if row.listing_id == additional_id)
        assert (
            identity.identity_source_ref == "synthetic-ending-only" and identity.company_id is None
        )
        assert identity.security_type == "ETF" and identity.currency == "EUR"
        extra = next(
            row
            for row in result.ending_reconciliation
            if row.account_id is not None and row.key == str(additional_id)
        )
        assert (
            extra.status == "EXTRA_OBSERVATION" and extra.projected is None and extra.observed == 0
        )
    assert baseline(postgres_engine, portfolio_id) == before


def test_same_total_wrong_account_is_blocked_through_the_real_api(postgres_engine: Engine) -> None:
    portfolio_id = source(postgres_engine)
    with Session(postgres_engine) as session:
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
    value = candidate(anchor)
    value.activity = []
    first = value.accounts[0]
    common = next(row for row in anchor.listings if row.security_type == "COMMON_STOCK")
    second = first.model_copy(
        deep=True,
        update={
            "account_id": uuid4(),
            "evidence": evidence("second-api-opening"),
            "positions": [
                c.LedgerPositionInput(listing_id=common.listing_id, quantity=Decimal("1.5"))
            ],
            "cash": [c.LedgerCashInput(currency="USD", balance=Decimal("50"))],
        },
    )
    next(row for row in first.positions if row.listing_id == common.listing_id).quantity = Decimal(
        "1"
    )
    next(row for row in first.cash if row.currency == "USD").balance = Decimal("50")
    value.accounts.append(second)
    first_observed = c.LedgerEndingAccount(
        account_id=first.account_id,
        evidence=evidence("first-api-ending"),
        positions=[
            row.model_copy(update={"quantity": Decimal("1.5")})
            if row.listing_id == common.listing_id
            else row.model_copy()
            for row in first.positions
        ],
        cash=first.cash,
    )
    second_observed = c.LedgerEndingAccount(
        account_id=second.account_id,
        evidence=evidence("second-api-ending"),
        positions=[c.LedgerPositionInput(listing_id=common.listing_id, quantity=Decimal("1"))],
        cash=second.cash,
    )
    value.ending_statement = c.LedgerEndingStatement(
        effective_at=value.as_of, accounts=[first_observed, second_observed]
    )
    before = baseline(postgres_engine, portfolio_id)
    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        response = client.post(
            f"/v1/portfolios/{portfolio_id}/ledger/preview", json=value.model_dump(mode="json")
        )
        assert response.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(response.json())
        assert result.status == "BLOCKED" and result.ending_status == "MISMATCH"
        assert all(
            row.status == "MATCH" for row in result.ending_reconciliation if row.account_id is None
        )
        assert len([row for row in result.ending_reconciliation if row.status == "DIFFERENCE"]) == 2
    assert baseline(postgres_engine, portfolio_id) == before


def test_ledger_route_rejects_accidental_dml_even_on_a_writable_engine(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id = source(postgres_engine)
    before = baseline(postgres_engine, portfolio_id)

    def mutate(session: Session, portfolio_id: UUID) -> c.PortfolioLedgerAnchorRead:
        session.execute(
            text("UPDATE portfolios SET name = 'Invalid mutation' WHERE id = :id"),
            {"id": portfolio_id},
        )
        raise AssertionError("PostgreSQL must reject DML before reaching this line")

    monkeypatch.setattr(ledger, "portfolio_ledger_anchor", mutate)
    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        result = client.get(f"/v1/portfolios/{portfolio_id}/ledger/anchor")
        assert result.status_code == 503 and "Invalid mutation" not in result.text
    assert baseline(postgres_engine, portfolio_id) == before


def test_existing_read_guard_and_source_target_conflicts_remain_fail_closed(
    postgres_engine: Engine,
) -> None:
    portfolio_id = source(postgres_engine)
    other_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(Portfolio(id=other_id, name="Other synthetic portfolio", base_currency="EUR"))
        session.flush()
        schema = str(session.scalar(text("SELECT current_schema()")))
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
        services.record_holdings(
            session,
            other_id,
            s.SnapshotCreate(
                actor="IMPORT",
                reason="Synthetic same balances in another portfolio",
                effective_at=AT,
                completeness="COMPLETE",
                positions=anchor.snapshot.positions,
                cash_positions=anchor.snapshot.cash_positions,
            ),
        )
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings()
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with reader.connect() as connection:
            original_read_only = cast(
                PsycopgConnection[tuple[object, ...]], connection.connection.driver_connection
            ).read_only
        with TestClient(fixture_application(reader, settings)) as client:
            value = candidate(anchor).model_dump(mode="json")
            path = f"/v1/portfolios/{portfolio_id}/ledger/preview"
            assert client.post(path, json=value).json()["status"] == "OPENING_RECONCILED"
            changed = dict(value, anchor_sha256="c" * 64)
            assert client.post(path, json=changed).status_code == 409
            changed = dict(value, anchor_snapshot_id=str(uuid4()))
            assert client.post(path, json=changed).status_code == 409
            assert (
                client.post(f"/v1/portfolios/{other_id}/ledger/preview", json=value).status_code
                == 409
            )
            original_listing = value["activity"][0]["listing_id"]
            value["activity"][0]["listing_id"] = str(uuid4())
            assert client.post(path, json=value).status_code == 422
            value["activity"][0]["listing_id"] = original_listing
            value["activity"][0]["currency"] = "EUR"
            assert client.post(path, json=value).status_code == 422
            value["activity"][0]["currency"] = "USD"
            value["activity"][0]["quantity"] = None
            assert client.post(path, json=value).status_code == 422
        with reader.connect() as connection:
            assert (
                cast(
                    PsycopgConnection[tuple[object, ...]], connection.connection.driver_connection
                ).read_only
                is original_read_only
            )
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
            assert connection.scalar(text("SHOW transaction_isolation")) == "read committed"
    finally:
        reader.dispose()
    assert baseline(postgres_engine, portfolio_id) == before


@pytest.mark.parametrize(
    "state", ["PARTIAL", "UNAVAILABLE_AMOUNT", "NEW_SNAPSHOT", "CURRENCY_DRIFT"]
)
def test_current_anchor_integrity_and_stale_identity_are_checked(
    postgres_engine: Engine, state: str
) -> None:
    portfolio_id = source(postgres_engine)
    with Session(postgres_engine) as session:
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
    with Session(postgres_engine) as session, session.begin():
        if state in {"PARTIAL", "NEW_SNAPSHOT"}:
            services.record_holdings(
                session,
                portfolio_id,
                s.SnapshotCreate(
                    actor="IMPORT",
                    reason="Synthetic newer source",
                    effective_at=AT + timedelta(days=1),
                    completeness="PARTIAL" if state == "PARTIAL" else "COMPLETE",
                    positions=[],
                    cash_positions=[],
                ),
            )
        elif state == "UNAVAILABLE_AMOUNT":
            session.execute(
                text("UPDATE holding_positions SET quantity = NULL WHERE snapshot_id = :id"),
                {"id": anchor.snapshot.id},
            )
        else:
            listing = session.get(Listing, anchor.listings[0].listing_id)
            assert listing is not None
            listing.currency = "DKK"
    before = (
        baseline(postgres_engine, portfolio_id)
        if state != "UNAVAILABLE_AMOUNT"
        else table_counts(postgres_engine)
    )
    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        result = client.post(
            f"/v1/portfolios/{portfolio_id}/ledger/preview",
            json=candidate(anchor).model_dump(mode="json"),
        )
        assert result.status_code == 409
    after = (
        baseline(postgres_engine, portfolio_id)
        if state != "UNAVAILABLE_AMOUNT"
        else table_counts(postgres_engine)
    )
    assert before == after


@pytest.mark.parametrize("future_field", ["effective_at", "recorded_at"])
def test_future_snapshot_cannot_replace_observed_anchor(
    postgres_engine: Engine, future_field: str
) -> None:
    portfolio_id = source(postgres_engine)
    with Session(postgres_engine) as session:
        original = ledger.portfolio_ledger_anchor(session, portfolio_id)
    with Session(postgres_engine) as session, session.begin():
        snapshot = services.record_holdings(
            session,
            portfolio_id,
            s.SnapshotCreate(
                actor="IMPORT",
                reason="Synthetic future boundary",
                effective_at=AT + timedelta(days=1),
                completeness="COMPLETE",
                positions=[],
                cash_positions=[],
            ),
        )
        # Retained legacy/future observations remain outside the current anchor.
        session.execute(
            text(f"UPDATE holding_snapshots SET {future_field} = :future WHERE id = :id"),
            {"future": datetime.now(UTC) + timedelta(days=1), "id": snapshot.id},
        )
    before = baseline(postgres_engine, portfolio_id)
    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        response = client.get(f"/v1/portfolios/{portfolio_id}/ledger/anchor")
        assert response.status_code == 200
        assert response.json()["anchor_sha256"] == original.anchor_sha256
        assert response.json()["snapshot"]["id"] == str(original.snapshot.id)
    assert baseline(postgres_engine, portfolio_id) == before


def test_guided_mixed_trade_payload_replays_and_rejects_invalid_dates_read_only(
    postgres_engine: Engine,
) -> None:
    portfolio_id = source(postgres_engine)
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        path = f"/v1/portfolios/{portfolio_id}/ledger"
        headers = {"x-api-access-token": "synthetic-token"}
        anchor = c.PortfolioLedgerAnchorRead.model_validate(
            client.get(f"{path}/anchor", headers=headers).json()
        )
        common = next(item for item in anchor.listings if item.security_type == "COMMON_STOCK")
        value = candidate(anchor)
        value.contract_version = "portfolio-ledger-preview-v2"
        payload = value.model_dump(mode="json")
        account_id = str(value.accounts[0].account_id)

        def entry(
            kind: str, sequence: int, quantity: str, gross: str, fees: str, taxes: str
        ) -> dict[str, object]:
            return {
                "id": str(UUID(int=100 + sequence)),
                "account_id": account_id,
                "kind": kind,
                "sequence": sequence,
                "effective_at": f"2026-01-0{sequence + 1}T00:00:00Z",
                "evidence": {"source_sha256": "c" * 64, "source_record_id": str(sequence)},
                "currency": "USD",
                "listing_id": str(common.listing_id),
                "quantity": quantity,
                "gross_cash": gross,
                "fees": fees,
                "taxes": taxes,
                "trade_date": "2026-01-01",
                "settlement_date": "2026-01-02",
            }

        payload["activity"] = [
            entry("BUY", 1, "0.5000000000", "10.00", "0.20", "0.05"),
            entry("SELL", 2, "0.2500000000", "6.00", "0.10", "0.02"),
            {
                "id": str(UUID(int=103)),
                "account_id": account_id,
                "kind": "DEPOSIT",
                "sequence": 3,
                "effective_at": "2026-01-04T00:00:00Z",
                "evidence": {"source_sha256": "c" * 64, "source_record_id": "3"},
                "currency": "USD",
                "amount": "1.00",
            },
        ]
        first = client.post(f"{path}/preview", headers=headers, json=payload)
        assert first.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(first.json())
        assert result.status == "OPENING_RECONCILED" and not result.issues
        assert next(
            row.quantity for row in result.positions if row.listing_id == common.listing_id
        ) == Decimal("2.75")
        assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("96.63")
        assert client.post(f"{path}/preview", headers=headers, json=payload).json() == first.json()
        payload["activity"][1]["settlement_date"] = "2025-12-31"
        assert client.post(f"{path}/preview", headers=headers, json=payload).status_code == 422
    assert baseline(postgres_engine, portfolio_id) == before


def test_guided_dividend_preserves_native_currency_and_rejects_excess_charges(
    postgres_engine: Engine,
) -> None:
    portfolio_id = source(postgres_engine)
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        path = f"/v1/portfolios/{portfolio_id}/ledger"
        headers = {"x-api-access-token": "synthetic-token"}
        anchor = c.PortfolioLedgerAnchorRead.model_validate(
            client.get(f"{path}/anchor", headers=headers).json()
        )
        common = next(item for item in anchor.listings if item.security_type == "COMMON_STOCK")
        value = candidate(anchor)
        value.contract_version = "portfolio-ledger-preview-v2"
        payload = value.model_dump(mode="json")
        payload["activity"] = [
            {
                "id": str(UUID(int=201)),
                "account_id": str(value.accounts[0].account_id),
                "kind": "DIVIDEND",
                "sequence": 1,
                "effective_at": "2026-01-02T00:00:00Z",
                "evidence": {"source_sha256": "c" * 64, "source_record_id": "income"},
                "currency": "EUR",
                "listing_id": str(common.listing_id),
                "gross_cash": "1.2500000000",
                "fees": "0",
                "taxes": "0.1500000000",
            }
        ]
        first = client.post(f"{path}/preview", headers=headers, json=payload)
        assert first.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(first.json())
        assert result.status == "OPENING_RECONCILED" and not result.issues
        assert next(row.balance for row in result.cash if row.currency == "EUR") == Decimal("1.10")
        assert next(row.balance for row in result.cash if row.currency == "USD") == Decimal("100")
        assert next(
            row.quantity for row in result.positions if row.listing_id == common.listing_id
        ) == Decimal("2.5")
        assert client.post(f"{path}/preview", headers=headers, json=payload).json() == first.json()
        payload["activity"][0]["taxes"] = "1.26"
        assert client.post(f"{path}/preview", headers=headers, json=payload).status_code == 422
    assert baseline(postgres_engine, portfolio_id) == before


def test_listing_search_is_exact_bounded_authenticated_and_read_only(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio_id = source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        company = services.create_company(session, s.CompanyCreate(name="Synthetic other issuer"))
        stock = services.create_security(
            session,
            company.id,
            s.SecurityCreate(
                name="Synthetic B shares", security_type="COMMON_STOCK", share_class="B"
            ),
        )
        other = Listing(
            security_id=stock.id,
            ticker="SYNF",
            venue="XLON",
            currency="GBP",
            identity_source_ref="synthetic-other",
            is_demo=True,
        )
        missing_currency = Listing(security_id=stock.id, ticker="SYNF", venue="XAMS", currency=None)
        malformed_currency = Listing(
            security_id=stock.id, ticker="SYNF", venue="XBER", currency="usd"
        )
        session.add_all([other, missing_currency, malformed_currency])
    before = baseline(postgres_engine, portfolio_id)
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    original_search = ledger.search_ledger_listings
    transaction_modes: list[tuple[object, object]] = []

    def inspect_search(
        session: Session, portfolio_id: UUID, ticker: str
    ) -> c.LedgerListingSearchRead:
        transaction_modes.append(
            (
                session.scalar(text("SHOW transaction_read_only")),
                session.scalar(text("SHOW transaction_isolation")),
            )
        )
        return original_search(session, portfolio_id, ticker)

    monkeypatch.setattr(ledger, "search_ledger_listings", inspect_search)
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        path = f"/v1/portfolios/{portfolio_id}/ledger/listings"
        assert client.get(path, params={"ticker": "SYNF"}).status_code == 401
        headers = {"x-api-access-token": "synthetic-token"}
        response = client.get(path, params={"ticker": "synf"}, headers=headers)
        assert response.status_code == 200
        result = response.json()
        assert result["truncated"] is False and len(result["results"]) == 2
        assert result["unsupported_results"] is True
        fund, stock_row = result["results"]
        assert (
            fund["security_type"] == "ETF"
            and fund["company_id"] is None
            and fund["company_name"] is None
        )
        assert (
            stock_row["security_name"],
            stock_row["share_class"],
            stock_row["venue"],
            stock_row["currency"],
        ) == ("Synthetic B shares", "B", "XLON", "GBP")
        assert stock_row["company_name"] == "Synthetic other issuer"
        assert stock_row["is_demo"] is True and fund["is_demo"] is False
        anchor = c.PortfolioLedgerAnchorRead.model_validate(
            client.get(f"/v1/portfolios/{portfolio_id}/ledger/anchor", headers=headers).json()
        )
        assert stock_row["listing_id"] not in {str(row.listing_id) for row in anchor.listings}
        packet = candidate(anchor).model_dump(mode="json")
        packet["contract_version"] = "portfolio-ledger-preview-v2"
        deposit = cash_activity("DEPOSIT", 1, "20").model_dump(mode="json")
        deposit["currency"] = "GBP"
        purchase = trade("BUY", 2).model_dump(mode="json")
        purchase["listing_id"] = stock_row["listing_id"]
        purchase["currency"] = "GBP"
        packet["activity"] = [deposit, purchase]
        preview = client.post(
            f"/v1/portfolios/{portfolio_id}/ledger/preview", headers=headers, json=packet
        )
        assert preview.status_code == 200
        result = c.PortfolioLedgerPreviewRead.model_validate(preview.json())
        assert result.status == "OPENING_RECONCILED" and not result.issues
        assert next(row.balance for row in result.cash if row.currency == "GBP") == Decimal("9.65")
        assert next(
            row.quantity
            for row in result.positions
            if str(row.listing_id) == stock_row["listing_id"]
        ) == Decimal("1.25")
        assert any(
            str(row.listing_id) == stock_row["listing_id"] for row in result.consumed_listings
        )
        assert client.get(path, params={"ticker": "SYN"}, headers=headers).json()["results"] == []
        assert client.get(path, params={"ticker": "%"}, headers=headers).json()["results"] == []
        assert client.get(path, params={"ticker": " "}, headers=headers).status_code == 422
        assert client.get(path, params={"ticker": "SYN\x00F"}, headers=headers).status_code == 422
        assert (
            client.get(
                f"/v1/portfolios/{uuid4()}/ledger/listings",
                params={"ticker": "SYNF"},
                headers=headers,
            ).status_code
            == 404
        )
    assert transaction_modes and set(transaction_modes) == {("on", "repeatable read")}
    assert baseline(postgres_engine, portfolio_id) == before


def test_listing_search_reports_truncation_at_the_51st_match(postgres_engine: Engine) -> None:
    portfolio_id = source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        fund = Security(name="Synthetic test fund", security_type="ETF", company_id=None)
        session.add(fund)
        session.flush()
        for number in range(50):
            session.add(
                Listing(
                    security_id=fund.id, ticker="BOUND", venue=f"VENUE{number:02}", currency="USD"
                )
            )
        fund_id = fund.id
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-token")}
    )
    headers = {"x-api-access-token": "synthetic-token"}
    path = f"/v1/portfolios/{portfolio_id}/ledger/listings"
    before = baseline(postgres_engine, portfolio_id)
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        first = client.get(path, params={"ticker": "BOUND"}, headers=headers).json()
        assert (
            len(first["results"]) == 50
            and not first["truncated"]
            and not first["unsupported_results"]
        )
        assert baseline(postgres_engine, portfolio_id) == before
        with Session(postgres_engine) as session, session.begin():
            session.add(
                Listing(security_id=fund_id, ticker="BOUND", venue="VENUE50", currency="USD")
            )
        before_second = baseline(postgres_engine, portfolio_id)
        second = client.get(path, params={"ticker": "BOUND"}, headers=headers).json()
        assert (
            len(second["results"]) == 50
            and second["truncated"]
            and not second["unsupported_results"]
        )
        assert [row["listing_id"] for row in second["results"]] == [
            row["listing_id"] for row in first["results"]
        ]
        assert baseline(postgres_engine, portfolio_id) == before_second
