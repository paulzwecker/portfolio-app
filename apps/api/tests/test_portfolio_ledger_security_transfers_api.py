"""Synthetic quantity transfer review/publication on verified disposable PostgreSQL schemas."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_portfolio_ledger import evidence
from test_portfolio_ledger_api import baseline
from test_portfolio_ledger_publication import command, preview, publish
from test_portfolio_ledger_reviews import accept, receipt_counts, stage, submit
from test_portfolio_ledger_storage import storage_engine as storage_engine
from test_portfolio_ledger_transfers_api import transfer_source

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import Listing

pytestmark = pytest.mark.integration


def security_source(engine: Engine) -> tuple[UUID, c.PortfolioLedgerPreviewCreate]:
    portfolio_id, packet = transfer_source(engine)
    previous = packet.activity[0]
    assert isinstance(previous, c.LedgerCashTransfer)
    with Session(engine) as session:
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
    fund = next(row for row in anchor.listings if row.security_type == "ETF")
    assert fund.company_id is None
    assert next(
        row.quantity for row in anchor.snapshot.positions if row.listing_id == fund.listing_id
    ) == Decimal(1)
    packet.activity = [
        c.LedgerSecurityTransfer(
            id=previous.id,
            account_id=previous.account_id,
            effective_at=packet.as_of,
            sequence=1,
            evidence=evidence("security-sent"),
            kind="SECURITY_TRANSFER",
            listing_id=fund.listing_id,
            quantity=Decimal("0.1234567891"),
            basis_status="UNAVAILABLE",
            destination=c.LedgerSecurityTransferReceipt(
                account_id=previous.destination.account_id,
                listing_id=fund.listing_id,
                quantity=Decimal("0.1234567891"),
                effective_at=packet.as_of,
                evidence=evidence("security-received"),
            ),
        )
    ]
    assert packet.ending_statement
    for account, ending in zip(packet.accounts, packet.ending_statement.accounts, strict=True):
        ending.cash = [cash.model_copy() for cash in account.cash]
    packet.ending_statement.accounts[0].positions = [
        row.model_copy(update={"quantity": Decimal("0.8765432109")})
        if row.listing_id == fund.listing_id
        else row.model_copy()
        for row in packet.accounts[0].positions
    ]
    packet.ending_statement.accounts[1].positions = [
        c.LedgerPositionInput(
            listing_id=fund.listing_id,
            quantity=Decimal("0.1234567891"),
        )
    ]
    return portfolio_id, c.PortfolioLedgerPreviewCreate.model_validate_json(
        packet.model_dump_json()
    )


def test_companyless_security_transfer_review_publication_and_idempotent_readback(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = security_source(storage_engine)
    before = baseline(storage_engine, portfolio_id)
    original = s.SnapshotRead.model_validate(before["snapshot"])
    path = f"/v1/portfolios/{portfolio_id}/ledger"
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        response = client.post(f"{path}/preview", json=packet.model_dump(mode="json"))
        assert response.status_code == 200
        projection = c.PortfolioLedgerPreviewRead.model_validate(response.json())
        assert projection.status == "ENDING_RECONCILED" and projection.activity_count == 1
        assert not projection.issues and len(projection.accounts) == 2
        assert len(projection.positions) == len(original.positions)
        assert {p.listing_id: p.quantity for p in projection.positions} == {
            p.listing_id: p.quantity for p in original.positions
        }
        assert baseline(storage_engine, portfolio_id) == before
        saved = client.post(
            f"{path}/candidates",
            json=submit(storage_engine, portfolio_id, packet).model_dump(mode="json"),
        )
        assert saved.status_code == 200
        row = c.LedgerCandidateRead.model_validate(saved.json())
        reviewed = client.post(
            f"{path}/candidates/{row.id}/review", json=accept(row).model_dump(mode="json")
        )
        assert reviewed.status_code == 200 and reviewed.json()["status"] == "ACCEPTED"
        assert (
            client.get(f"/v1/portfolios/{portfolio_id}/overview").json()["snapshot"]
            == before["snapshot"]
        )
        plan = preview(storage_engine, portfolio_id, row.id)
        receipt = publish(storage_engine, portfolio_id, row.id, command(plan))
        assert publish(storage_engine, portfolio_id, row.id, command(plan)).id == receipt.id
        current = client.get(f"/v1/portfolios/{portfolio_id}/overview").json()
        assert current["target_revision"] == before["targets"]
        assert {p.listing_id: p.quantity for p in receipt.snapshot.positions} == {
            p.listing_id: p.quantity for p in projection.positions
        }
        assert len(receipt.snapshot.positions) == len(projection.positions)
        assert {p.currency: p.balance for p in receipt.snapshot.cash_positions} == {
            "USD": Decimal(100),
            "EUR": Decimal(0),
        }
        assert current["snapshot"]["id"] == str(receipt.snapshot.id)
        detail = c.LedgerCandidateRead.model_validate(
            client.get(f"{path}/candidates/{row.id}").json()
        )
        assert ledger.canonical_ledger_packet(detail.packet) == ledger.canonical_ledger_packet(
            packet
        )
        transfer = detail.packet.activity[0]
        assert isinstance(transfer, c.LedgerSecurityTransfer)
        assert transfer.basis_status == "UNAVAILABLE"
        assert transfer.destination.evidence == evidence("security-received")
        assert (
            next(
                p for p in detail.preview.consumed_listings if p.listing_id == transfer.listing_id
            ).company_id
            is None
        )
    assert receipt_counts(storage_engine) == (1, 1)


def test_security_identity_drift_blocks_review_without_records_or_receipts(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = security_source(storage_engine)
    row = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerSecurityTransfer)
    with Session(storage_engine) as session, session.begin():
        listing = session.get(Listing, transfer.listing_id)
        assert listing
        listing.identity_source_ref = "different-reviewed-security-identity"
    before = baseline(storage_engine, portfolio_id)
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        response = client.post(
            f"/v1/portfolios/{portfolio_id}/ledger/candidates/{row.id}/review",
            json=accept(row).model_dump(mode="json"),
        )
        assert response.status_code == 409
    assert receipt_counts(storage_engine) == (1, 0)
    assert baseline(storage_engine, portfolio_id) == before


def test_incomplete_security_transfers_cannot_create_candidates(storage_engine: Engine) -> None:
    portfolio_id, packet = security_source(storage_engine)
    before = baseline(storage_engine, portfolio_id)
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        for kind in (
            "quantity",
            "listing",
            "time",
            "basis",
            "cost",
            "missing",
            "unknown",
            "duplicate",
        ):
            payload = packet.model_dump(mode="json")
            item = payload["activity"][0]
            if kind == "quantity":
                item["destination"]["quantity"] = "0.1234567892"
            if kind == "listing":
                item["destination"]["listing_id"] = str(uuid4())
            if kind == "time":
                item["destination"]["effective_at"] = (packet.as_of - timedelta(days=1)).isoformat()
            if kind == "basis":
                item.pop("basis_status")
            if kind == "cost":
                item["cost_basis"] = "0"
            if kind == "missing":
                item.pop("destination")
            if kind == "unknown":
                item["destination"]["account_id"] = str(uuid4())
            if kind == "duplicate":
                item["destination"]["evidence"] = item["evidence"]
            request = {
                "submission_id": str(uuid4()),
                "expected_base_candidate_id": None,
                "expected_input_sha256": "a" * 64,
                "reason": "Synthetic rejected security pair",
                "proposal": payload,
            }
            assert (
                client.post(
                    f"/v1/portfolios/{portfolio_id}/ledger/preview", json=payload
                ).status_code
                == 422
            ), kind
            assert (
                client.post(
                    f"/v1/portfolios/{portfolio_id}/ledger/candidates", json=request
                ).status_code
                == 422
            ), kind
            assert baseline(storage_engine, portfolio_id) == before
    assert receipt_counts(storage_engine) == (0, 0)
