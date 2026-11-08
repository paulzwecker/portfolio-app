"""Synthetic internal-transfer lifecycle on verified disposable PostgreSQL schemas."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from test_portfolio_ledger import evidence
from test_portfolio_ledger_api import baseline
from test_portfolio_ledger_publication import command, preview, publish
from test_portfolio_ledger_reviews import accept, decide, prepare, receipt_counts, stage, submit
from test_portfolio_ledger_storage import storage_engine as storage_engine

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services

pytestmark = pytest.mark.integration


def transfer_source(engine: Engine) -> tuple[UUID, c.PortfolioLedgerPreviewCreate]:
    portfolio_id, packet = prepare(engine)
    sender = packet.accounts[0]
    recipient = c.LedgerOpeningAccount(
        account_id=uuid4(),
        name="Synthetic receiving brokerage",
        kind="BROKERAGE",
        broker_name="Synthetic Receiving Broker",
        evidence=evidence("recipient-opening"),
        positions=[],
        cash=[c.LedgerCashInput(currency="USD", balance=Decimal("0"))],
    )
    packet.contract_version = "portfolio-ledger-preview-v2"
    packet.accounts.append(recipient)
    packet.activity = [
        c.LedgerCashTransfer(
            id=uuid4(),
            account_id=sender.account_id,
            sequence=1,
            effective_at=packet.as_of,
            evidence=evidence("transfer-sent"),
            kind="CASH_TRANSFER",
            currency="USD",
            amount=Decimal("12.3456789012"),
            destination=c.LedgerTransferReceipt(
                account_id=recipient.account_id,
                effective_at=packet.as_of,
                currency="USD",
                amount=Decimal("12.3456789012"),
                evidence=evidence("transfer-received"),
            ),
        )
    ]
    packet.ending_statement = c.LedgerEndingStatement(
        effective_at=packet.as_of,
        accounts=[
            c.LedgerEndingAccount(
                account_id=sender.account_id,
                evidence=evidence("sender-closing"),
                positions=[p.model_copy() for p in sender.positions],
                cash=[
                    c.LedgerCashInput(currency="USD", balance=Decimal("87.6543210988")),
                    c.LedgerCashInput(currency="EUR", balance=Decimal("0")),
                ],
            ),
            c.LedgerEndingAccount(
                account_id=recipient.account_id,
                evidence=evidence("recipient-closing"),
                positions=[],
                cash=[c.LedgerCashInput(currency="USD", balance=Decimal("12.3456789012"))],
            ),
        ],
    )
    return portfolio_id, c.PortfolioLedgerPreviewCreate.model_validate_json(
        packet.model_dump_json()
    )


def test_transfer_preview_review_publication_replay_preserves_portfolio_balances(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = transfer_source(storage_engine)
    before = baseline(storage_engine, portfolio_id)
    original_snapshot = s.SnapshotRead.model_validate(before["snapshot"])
    path = f"/v1/portfolios/{portfolio_id}/ledger"
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        response = client.post(f"{path}/preview", json=packet.model_dump(mode="json"))
        assert response.status_code == 200
        projection = c.PortfolioLedgerPreviewRead.model_validate(response.json())
        assert projection.status == "ENDING_RECONCILED" and projection.activity_count == 1
        assert {p.currency: p.balance for p in projection.cash} == {
            "USD": Decimal(100),
            "EUR": Decimal(0),
        }
        assert len(projection.accounts) == 2 and not projection.issues
        assert baseline(storage_engine, portfolio_id) == before
        request = submit(storage_engine, portfolio_id, packet)
        saved = client.post(f"{path}/candidates", json=request.model_dump(mode="json"))
        assert saved.status_code == 200
        row = c.LedgerCandidateRead.model_validate(saved.json())
        assert client.post(f"{path}/candidates", json=request.model_dump(mode="json")).json()[
            "replayed"
        ]
        reviewed = client.post(
            f"{path}/candidates/{row.id}/review", json=accept(row).model_dump(mode="json")
        )
        assert reviewed.status_code == 200 and reviewed.json()["status"] == "ACCEPTED"
        assert (
            client.get(f"/v1/portfolios/{portfolio_id}/overview").json()["snapshot"]
            == before["snapshot"]
        )
        plan = preview(storage_engine, portfolio_id, row.id)
        assert len(plan.account_ids) == 2
        receipt = publish(storage_engine, portfolio_id, row.id, command(plan))
        assert publish(storage_engine, portfolio_id, row.id, command(plan)).id == receipt.id
        overview = client.get(f"/v1/portfolios/{portfolio_id}/overview").json()
        assert overview["target_revision"] == before["targets"]
        persisted = s.SnapshotRead.model_validate(overview["snapshot"])
        assert len(persisted.positions) == len(original_snapshot.positions)
        assert {p.listing_id: p.quantity for p in persisted.positions} == {
            p.listing_id: p.quantity for p in original_snapshot.positions
        }
        assert {
            p["currency"]: Decimal(p["balance"]) for p in overview["snapshot"]["cash_positions"]
        } == {
            "USD": Decimal(100),
            "EUR": Decimal(0),
        }
        detail = c.LedgerCandidateRead.model_validate(
            client.get(f"{path}/candidates/{row.id}").json()
        )
        assert detail.preview == projection
        assert ledger.canonical_ledger_packet(detail.packet) == ledger.canonical_ledger_packet(
            packet
        )
        transfer = detail.packet.activity[0]
        assert isinstance(transfer, c.LedgerCashTransfer)
        assert transfer.destination.evidence == evidence("transfer-received")
    assert receipt_counts(storage_engine) == (1, 1)


def test_transfer_receipt_correction_requires_explicit_changed_activity_acknowledgement(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = transfer_source(storage_engine)
    original = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    decide(storage_engine, portfolio_id, original.id, accept(original))
    transfer = packet.activity[0]
    assert isinstance(transfer, c.LedgerCashTransfer)
    transfer.destination.evidence = evidence("reviewed-corrected-receipt")
    corrected = stage(
        storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet, original.id)
    )
    assert corrected.changes.changed_activity_ids == [transfer.id]
    assert corrected.input_sha256 != original.input_sha256
    before = baseline(storage_engine, portfolio_id)
    incomplete = accept(corrected).model_copy(update={"acknowledged_changed_activity_ids": []})
    with pytest.raises(services.DomainError, match="acknowledge"):
        decide(storage_engine, portfolio_id, corrected.id, incomplete)
    assert receipt_counts(storage_engine) == (2, 1)
    assert baseline(storage_engine, portfolio_id) == before
    accepted = decide(storage_engine, portfolio_id, corrected.id, accept(corrected))
    assert accepted.review and accepted.review.revision_number == 2
    assert receipt_counts(storage_engine) == (2, 2)


def test_incomplete_transfer_api_requests_leave_no_records_or_receipts(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = transfer_source(storage_engine)
    before = baseline(storage_engine, portfolio_id)
    path = f"/v1/portfolios/{portfolio_id}/ledger"
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        for kind in (
            "amount",
            "currency",
            "time",
            "missing",
            "unknown",
            "unallocated",
            "duplicate",
        ):
            payload = packet.model_dump(mode="json")
            transfer = payload["activity"][0]
            if kind == "amount":
                transfer["destination"]["amount"] = "12.3456789013"
            if kind == "currency":
                transfer["destination"]["currency"] = "EUR"
            if kind == "time":
                transfer["destination"]["effective_at"] = (
                    packet.as_of - timedelta(days=1)
                ).isoformat()
            if kind == "missing":
                transfer.pop("destination")
            if kind == "unknown":
                transfer["destination"]["account_id"] = str(uuid4())
            if kind == "unallocated":
                payload["accounts"][1].update(kind="UNALLOCATED_OPENING", broker_name=None)
            if kind == "duplicate":
                transfer["destination"]["evidence"] = transfer["evidence"]
            assert client.post(f"{path}/preview", json=payload).status_code == 422, kind
            rejected = {
                "submission_id": str(uuid4()),
                "expected_base_candidate_id": None,
                "expected_input_sha256": "a" * 64,
                "reason": "Synthetic rejected pair",
                "proposal": payload,
            }
            assert client.post(f"{path}/candidates", json=rejected).status_code == 422, kind
            assert baseline(storage_engine, portfolio_id) == before
    assert receipt_counts(storage_engine) == (0, 0)
