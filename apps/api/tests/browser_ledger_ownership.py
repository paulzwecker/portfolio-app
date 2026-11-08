"""Seed a reviewed synthetic cutover before the browser server becomes read-only."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api import portfolio_ledger_publication as publication
from portfolio_api import portfolio_ledger_reviews as reviews


def prepare_ledger_ownership(engine: Engine, metadata: dict[str, object]) -> None:
    portfolio_id = UUID(str(metadata["portfolio_id"]))
    account_id = UUID("11111111-1111-4111-8111-111111111111")
    at = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
        positions = [
            c.LedgerPositionInput.model_validate(item.model_dump())
            for item in anchor.snapshot.positions
        ]
        cash = [
            c.LedgerCashInput.model_validate(item.model_dump())
            for item in anchor.snapshot.cash_positions
        ]
        packet = c.PortfolioLedgerPreviewCreate(
            contract_version="portfolio-ledger-preview-v1",
            anchor_snapshot_id=anchor.snapshot.id,
            anchor_sha256=anchor.anchor_sha256,
            as_of=at,
            accounts=[
                c.LedgerOpeningAccount(
                    account_id=account_id,
                    name="Synthetic broker",
                    kind="BROKERAGE",
                    broker_name="Synthetic Broker",
                    evidence=c.LedgerEvidence(source_sha256="a" * 64, source_record_id="opening"),
                    positions=positions,
                    cash=cash,
                )
            ],
            activity=[
                c.LedgerCashActivity(
                    id=UUID("22222222-2222-4222-8222-222222222222"),
                    account_id=account_id,
                    sequence=1,
                    effective_at=at,
                    kind="DEPOSIT",
                    currency="USD",
                    amount=Decimal("0.125"),
                    evidence=c.LedgerEvidence(source_sha256="b" * 64, source_record_id="deposit"),
                )
            ],
            ending_statement=c.LedgerEndingStatement(
                effective_at=at,
                accounts=[
                    c.LedgerEndingAccount(
                        account_id=account_id,
                        evidence=c.LedgerEvidence(
                            source_sha256="c" * 64, source_record_id="closing"
                        ),
                        positions=positions,
                        cash=[
                            c.LedgerCashInput(currency="USD", balance=Decimal("5.125")),
                            c.LedgerCashInput(currency="EUR", balance=Decimal("10")),
                        ],
                    )
                ],
            ),
        )
        report = ledger.preview_portfolio_ledger(session, portfolio_id, packet)
        staged = reviews.stage_candidate(
            session,
            portfolio_id,
            c.LedgerCandidateCreate(
                submission_id=UUID("33333333-3333-4333-8333-333333333333"),
                expected_base_candidate_id=None,
                expected_input_sha256=report.input_sha256,
                reason="Synthetic opening and settled deposit",
                proposal=packet,
            ),
        )
        reviews.review_candidate(
            session,
            portfolio_id,
            staged.id,
            c.LedgerAcceptCreate(
                decision="ACCEPT",
                expected_base_candidate_id=None,
                expected_input_sha256=staged.input_sha256,
                expected_preview_sha256=staged.preview_sha256,
                reason="Synthetic source review",
                source_evidence_reviewed=True,
                account_allocation_reviewed=True,
                settled_balance_basis_reviewed=True,
                full_replacement_reviewed=True,
                acknowledged_changed_activity_ids=[],
                acknowledged_removed_activity_ids=[],
            ),
        )
        plan = publication.publication_preview(session, portfolio_id, staged.id)
        receipt = publication.publish(
            session,
            portfolio_id,
            staged.id,
            c.LedgerPublicationCreate(
                expected_plan_sha256=plan.plan_sha256,
                expected_previous_publication_id=None,
                confirmation=plan.confirmation_phrase,
                reason="Synthetic isolated ownership transition",
                ownership_transfer_reviewed=True,
                whole_portfolio_scope_reviewed=True,
                current_state_recovery_verified=True,
                holdings_confirmation=True,
            ),
        )
        metadata["ledger_owned"] = True
        metadata["publication_id"] = str(receipt.id)
        metadata["opening_snapshot_id"] = str(anchor.snapshot.id)
