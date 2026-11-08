"""Dividend review/publication on independently verified disposable test schemas."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_portfolio_ledger import evidence
from test_portfolio_ledger_api import baseline
from test_portfolio_ledger_publication import command, preview, publish
from test_portfolio_ledger_reviews import accept, decide, prepare, receipt_counts, stage, submit
from test_portfolio_ledger_storage import storage_engine as storage_engine

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api import portfolio_ledger_publication as publication
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import HoldingSnapshot, Listing

pytestmark = pytest.mark.integration


def income_source(engine: Engine) -> tuple[UUID, c.PortfolioLedgerPreviewCreate]:
    portfolio_id, packet = prepare(engine)
    with Session(engine) as session:
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
    fund = next(row for row in anchor.listings if row.security_type == "ETF")
    assert fund.company_id is None and fund.currency == "EUR"
    packet.contract_version = "portfolio-ledger-preview-v2"
    packet.activity = [
        c.LedgerDividend(
            id=uuid4(),
            account_id=packet.accounts[0].account_id,
            sequence=1,
            effective_at=packet.as_of,
            evidence=evidence("synthetic-income"),
            kind="DIVIDEND",
            listing_id=fund.listing_id,
            currency="USD",
            gross_cash=Decimal("12.3456789012"),
            fees=Decimal("0.1"),
            taxes=Decimal("2.3456789012"),
        ),
        c.LedgerCashActivity(
            id=uuid4(),
            account_id=packet.accounts[0].account_id,
            sequence=2,
            effective_at=packet.as_of,
            evidence=evidence("synthetic-tax"),
            kind="TAX",
            currency="USD",
            amount=Decimal("0.9"),
        ),
    ]
    assert packet.ending_statement
    packet.ending_statement.accounts[0].positions = [
        row.model_copy() for row in packet.accounts[0].positions
    ]
    packet.ending_statement.accounts[0].cash = [
        c.LedgerCashInput(currency="USD", balance=Decimal("109")),
        c.LedgerCashInput(currency="EUR", balance=Decimal("0")),
    ]
    return portfolio_id, c.PortfolioLedgerPreviewCreate.model_validate_json(
        packet.model_dump_json()
    )


def test_income_read_only_preview_and_explicit_review_publication_round_trip(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = income_source(storage_engine)
    before = baseline(storage_engine, portfolio_id)
    original_snapshot = s.SnapshotRead.model_validate(before["snapshot"])
    path = f"/v1/portfolios/{portfolio_id}/ledger"
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        first = client.post(f"{path}/preview", json=packet.model_dump(mode="json"))
        assert first.status_code == 200
        projected = c.PortfolioLedgerPreviewRead.model_validate(first.json())
        assert projected.status == "ENDING_RECONCILED" and projected.activity_count == 2
        assert (
            client.post(f"{path}/preview", json=packet.model_dump(mode="json")).json()
            == first.json()
        )
        assert baseline(storage_engine, portfolio_id) == before
        request = submit(storage_engine, portfolio_id, packet)
        saved = client.post(f"{path}/candidates", json=request.model_dump(mode="json"))
        assert saved.status_code == 200
        row = c.LedgerCandidateRead.model_validate(saved.json())
        assert row.status == "PENDING" and row.preview == projected
        assert client.post(f"{path}/candidates", json=request.model_dump(mode="json")).json()[
            "replayed"
        ]
        approved = client.post(
            f"{path}/candidates/{row.id}/review", json=accept(row).model_dump(mode="json")
        )
        assert approved.status_code == 200 and approved.json()["status"] == "ACCEPTED"
        assert (
            client.get(f"/v1/portfolios/{portfolio_id}/overview").json()["snapshot"]
            == before["snapshot"]
        )
        plan = preview(storage_engine, portfolio_id, row.id)
        receipt = publish(storage_engine, portfolio_id, row.id, command(plan))
        assert publish(storage_engine, portfolio_id, row.id, command(plan)).id == receipt.id
        current = client.get(f"/v1/portfolios/{portfolio_id}/overview").json()
        assert current["target_revision"] == before["targets"]
        persisted = s.SnapshotRead.model_validate(current["snapshot"])
        assert len(persisted.positions) == len(original_snapshot.positions)
        assert {p.listing_id: p.quantity for p in persisted.positions} == {
            p.listing_id: p.quantity for p in original_snapshot.positions
        }
        assert {
            r["currency"]: Decimal(r["balance"]) for r in current["snapshot"]["cash_positions"]
        } == {
            "USD": Decimal("109"),
            "EUR": Decimal("0"),
        }
        detail = client.get(f"{path}/candidates/{row.id}")
        stored = c.LedgerCandidateRead.model_validate(detail.json())
        assert ledger.canonical_ledger_packet(stored.packet) == ledger.canonical_ledger_packet(
            packet
        )
        assert stored.preview == projected
        assert stored.packet.activity[0].evidence == evidence("synthetic-income")
    with Session(storage_engine) as session:
        original = session.get(HoldingSnapshot, packet.anchor_snapshot_id)
        assert original and original.source == "synthetic-source-v1"
        assert publication.ownership(session, portfolio_id).latest_publication == receipt
    assert receipt_counts(storage_engine) == (1, 1)


def test_failed_income_publication_rolls_back_without_partial_records(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id, packet = income_source(storage_engine)
    row = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    decide(storage_engine, portfolio_id, row.id, accept(row))
    before = baseline(storage_engine, portfolio_id)
    plan = preview(storage_engine, portfolio_id, row.id)
    wrong = command(plan).model_copy(update={"confirmation": "incorrect"})
    with pytest.raises(services.DomainError):
        publish(storage_engine, portfolio_id, row.id, wrong)
    assert baseline(storage_engine, portfolio_id) == before
    original = publication._snapshot

    def interrupted(session: Session, snapshot: HoldingSnapshot) -> s.SnapshotRead:
        if snapshot.source and snapshot.source.startswith("portfolio-ledger-publication-v1:"):
            raise RuntimeError("Synthetic failure after snapshot flush")
        return original(session, snapshot)

    with monkeypatch.context() as patch:
        # Publication creates the snapshot before hashing/readback. Interrupting
        # that read proves snapshot/cash/receipt persistence remains atomic.
        patch.setattr(publication, "_snapshot", interrupted)
        with pytest.raises(RuntimeError, match="Synthetic failure"):
            publish(storage_engine, portfolio_id, row.id, command(plan))
    assert baseline(storage_engine, portfolio_id) == before
    receipt = publish(storage_engine, portfolio_id, row.id, command(plan))
    assert receipt.sequence == 1


def test_changed_income_only_listing_invalidates_review_and_preserves_balances(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = income_source(storage_engine)
    dividend = packet.activity[0]
    assert isinstance(dividend, c.LedgerDividend)
    with Session(storage_engine) as session, session.begin():
        held = session.get(Listing, dividend.listing_id)
        assert held
        other = Listing(
            security_id=held.security_id,
            ticker="SYNTHPAY",
            venue="SYNTH",
            currency="EUR",
            identity_source_ref="synthetic-income-only-identity",
        )
        session.add(other)
        session.flush()
        dividend.listing_id = other.id
    row = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    assert dividend.listing_id not in {p.listing_id for p in row.preview.positions}
    with Session(storage_engine) as session, session.begin():
        changed = session.scalar(select(Listing).where(Listing.id == dividend.listing_id))
        assert changed
        changed.identity_source_ref = "different-reviewed-source"
    before = baseline(storage_engine, portfolio_id)
    with pytest.raises(services.DomainError, match="changed"):
        decide(storage_engine, portfolio_id, row.id, accept(row))
    assert receipt_counts(storage_engine) == (1, 0)
    assert baseline(storage_engine, portfolio_id) == before
