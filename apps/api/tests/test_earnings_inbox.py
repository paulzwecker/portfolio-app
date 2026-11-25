from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from portfolio_api.database import Base
from portfolio_api.domain import models as m
from portfolio_api.earnings_inbox import Review, add_impact, earnings_inbox


def test_exact_holdings_include_issuerless_etf_and_skip_newer_partial_snapshot() -> None:
    engine = create_engine("sqlite://")
    classes = [
        m.Portfolio,
        m.Company,
        m.Security,
        m.Listing,
        m.HoldingSnapshot,
        m.HoldingPosition,
        m.SourceDocument,
        m.FinancialModel,
        m.FinancialModelRevision,
        m.ResearchRevision,
        m.ResearchEvidence,
        m.AgentModelRevisionProposal,
    ]
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[c.__tablename__] for c in classes]
    )
    with Session(engine) as db:
        portfolio = m.Portfolio(name="Test portfolio", base_currency="USD")
        db.add(portfolio)
        db.flush()
        for day, status in [(1, "COMPLETE"), (2, "PARTIAL")]:
            snapshot = m.HoldingSnapshot(
                id=uuid4(),
                portfolio_id=portfolio.id,
                completeness=status,
                effective_at=datetime(2025, 1, day, tzinfo=UTC),
                actor="IMPORT",
                reason="Test",
            )
            positions = []
            for ticker in ["A", "B", "ETF", "ZERO"] if day == 1 else ["OTHER"]:
                company = None if ticker == "ETF" else m.Company(name=ticker)
                if company:
                    db.add(company)
                    db.flush()
                security = m.Security(
                    name=ticker,
                    company_id=company.id if company else None,
                    security_type="COMMON_STOCK" if company else "ETF",
                )
                db.add(security)
                db.flush()
                listing = m.Listing(security_id=security.id, ticker=ticker, venue="TEST")
                db.add(listing)
                db.flush()
                positions.append(
                    m.HoldingPosition(
                        snapshot_id=snapshot.id,
                        listing_id=listing.id,
                        quantity=0 if ticker == "ZERO" else 1,
                    )
                )
                if company:
                    db.add(
                        m.SourceDocument(
                            company_id=company.id,
                            provider_id="test",
                            external_identifier=ticker,
                            source_name="Issuer",
                            title="Q3 results",
                            document_type="EARNINGS_RELEASE",
                            canonical_url=f"https://issuer.test/{ticker}",
                            data_quality="PASS",
                            actor="IMPORT",
                        )
                    )
            db.add_all([snapshot, *positions])
            db.flush()
        inbox = earnings_inbox(db, portfolio.id)
        assert inbox.listing_count == 3 and inbox.modeled_count == 0
        assert [(r.listing, r.url) for r in inbox.rows] == [
            ("TEST:A", "https://issuer.test/A"),
            ("TEST:B", "https://issuer.test/B"),
            ("TEST:ETF", None),
        ]


@pytest.mark.parametrize(
    ("new_price", "status", "expected"),
    [("same", "FRESH", Decimal("100")), ("other", "FRESH", None), ("same", "STALE", None)],
)
def test_irr_crossing_requires_comparable_preview(
    new_price: str, status: str, expected: Decimal | None
) -> None:
    row = Review(
        listing_id=uuid4(),
        company_id=uuid4(),
        listing="A",
        company="A",
        revision_number=1,
        title="Q3",
    )
    proposal = m.AgentModelRevisionProposal(
        id=uuid4(), status="SUBMITTED", rationale="Based on Q3."
    )
    outputs = dict(price_observation_id="same", price_status="FRESH", expected_cash_flow_irr=".14")
    proposal.preview_data = dict(
        proposal_id=str(proposal.id),
        status="READY",
        reason=None,
        current_revision_id=None,
        current_revision_number=1,
        current_inputs={},
        proposed_inputs={},
        current_outputs=outputs,
        proposed_outputs={
            **outputs,
            "price_observation_id": new_price,
            "price_status": status,
            "expected_cash_flow_irr": ".15",
        },
        preview_fingerprint=None,
        previewed_at=datetime.now(UTC).isoformat(),
    )
    add_impact(row, proposal)
    assert row.impact_bps == expected
    assert row.crosses_hurdle == (expected is not None)
