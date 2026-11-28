import json
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import dcf_fixture

from portfolio_api import earnings_release_review as review
from portfolio_api import earnings_release_source as source
from portfolio_api.domain import models as m
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.earnings_release_agent import Analysis
from portfolio_api.holding_earnings_publication import BatchInput, review_batch
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


def test_sec_discovery_checks_listing_and_distinguishes_amendments(monkeypatch):
    issuer = source.ISSUERS["NASDAQ:BKNG"]
    recent = dict(
        form=["8-K", "8-K/A", "8-K"],
        items=["2.02", "2.02,9.01", "9.01"],
        accessionNumber=[issuer.baseline, "0001075531-26-000045", "0001075531-26-000046"],
        filingDate=["2026-11-03"] * 3,
    )
    data = dict(cik=issuer.cik, tickers=["BKNG"], exchanges=["Nasdaq"], filings=dict(recent=recent))
    monkeypatch.setattr(source, "fetch", lambda *_: json.dumps(data).encode())
    assert len(source.announcements("NASDAQ:BKNG", "test", baseline_reviewed=False)) == 2
    filings = source.announcements("NASDAQ:BKNG", "test", baseline_reviewed=True)
    assert [x.accession for x in filings] == ["0001075531-26-000045"]
    data["exchanges"] = ["NYSE"]
    with pytest.raises(ValueError, match="identity"):
        source.announcements("NASDAQ:BKNG", "test", baseline_reviewed=True)


@pytest.mark.integration
@pytest.mark.parametrize("decision", ["CHANGE", "INSUFFICIENT_EVIDENCE", "RETAIN"])
def test_new_filing_review_and_replay(postgres_engine: Engine, decision: str):
    settings = Settings(database_url=None, sec_user_agent="Test research contact")
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(settings)) as client,
    ):
        company = client.post(
            "/v1/companies", json={"name": "Synthetic", "reporting_currency": "USD"}
        ).json()["id"]
        sec = client.post(
            f"/v1/companies/{company}/securities",
            json={"name": "Synthetic", "security_type": "COMMON_STOCK"},
        ).json()["id"]
        listing = UUID(
            client.post(
                f"/v1/securities/{sec}/listings",
                json={"venue": "NASDAQ", "ticker": "BKNG", "currency": "USD"},
            ).json()["id"]
        )
        res = client.post(
            f"/v1/companies/{company}/financial-models",
            json=dict(
                model_type="UFCF_DCF_10Y_FADE",
                model_name="Synthetic DCF",
                valuation_listing_id=str(listing),
                model_currency="USD",
                source_model_key="TEST",
                initial_revision=dcf_fixture()["input"],
            ),
        )
        assert res.status_code == 201, res.text
        mid = UUID(res.json()["id"])
        revision = UUID(res.json()["current_revision_id"])
    with Session(postgres_engine) as db, db.begin():
        port = m.Portfolio(name="Portfolio", base_currency="USD")
        db.add(port)
        db.flush()
        portfolio = port.id
        snapshot = services._record_holdings(
            db,
            portfolio,
            s.SnapshotCreate.model_validate(
                dict(
                    completeness="COMPLETE",
                    effective_at=datetime.now(UTC),
                    actor="IMPORT",
                    reason="Test",
                    positions=[dict(listing_id=listing, quantity=1)],
                )
            ),
        ).id
        db.add(
            m.ResearchRevision(
                company_id=UUID(company),
                stream_key="launch",
                contract_version="1.2.0",
                revision_number=1,
                external_revision_id="1",
                author_id="test",
                source_id="test",
                source_reference=source.BASELINE_SOURCES["NASDAQ:BKNG"],
                rationale="Prior review",
                status="PUBLISHED",
                observed_at=datetime.now(UTC),
                content_fingerprint="1" * 64,
                earnings_review={"listing_id": str(listing)},
            )
        )
    filing = source.Filing(
        "0001075531-26-000099",
        date(2026, 11, 18),
        "https://www.sec.gov/Archives/edgar/data/1075531/test/",
    )
    result = Analysis(
        driver="revenue_growth",
        conclusion=decision,
        period="Synthetic Q3",
        period_end=date(2026, 9, 30),
        comparable_period="Next fiscal year",
        passage="Management expects annual growth of 21 percent.",
        rationale="Annual guidance supports an updated forecast.",
        uncertainty="Guidance may change.",
        replacement=Decimal("0.21") if decision == "CHANGE" else None,
    )
    with (
        patch.object(source, "announcements", return_value=[filing]),
        patch.object(
            source, "release_text", return_value=(filing.folder + "results.htm", result.passage)
        ),
        patch.object(review.agent, "assess", return_value=result) as agent,
    ):
        with Session(postgres_engine) as db, db.begin():
            review.check_release(db, settings, portfolio, listing)
        with Session(postgres_engine) as db, db.begin():
            review.check_release(db, settings, portfolio, listing)
            (draft,) = review.pending(db, portfolio)
            assert db.get(m.FinancialModel, mid).current_revision_id == revision
            assert not db.scalars(select(m.AgentModelRevisionProposal)).all()
            preview = review_batch(
                db, portfolio, BatchInput(snapshot_id=snapshot, assessments=[draft.assessment])
            )
            receipt = review.publish_draft(db, portfolio, draft.id, snapshot, preview.digest)
        with Session(postgres_engine) as db, db.begin():
            assert (
                review.publish_draft(db, portfolio, draft.id, snapshot, preview.digest) == receipt
            )
            assert not review.pending(db, portfolio)
            assert len(db.scalars(select(m.AgentModelRevisionProposal)).all()) == int(
                decision == "CHANGE"
            )
            assert db.get(m.FinancialModel, mid).current_revision_id == revision
        agent.assert_called_once()


@pytest.mark.parametrize("bad_quote, future_period", [(True, False), (False, True), (False, False)])
def test_agent_validates_quoted_evidence_and_period(bad_quote, future_period):
    from io import BytesIO

    import portfolio_api.earnings_release_agent as agent

    passage = "Cash spending on equipment was unchanged from last year."
    content = dict(
        driver="capex_to_revenue",
        conclusion="RETAIN",
        period="Q3",
        period_end="2026-12-31" if future_period else "2026-09-30",
        comparable_period="Prior year",
        passage="A fabricated excerpt." if bad_quote else passage,
        rationale="Cash spending supports the existing assumption.",
        uncertainty="Annual timing may differ.",
    )
    envelope = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]}
    with patch.object(agent, "build_opener") as opener:
        opener.return_value.open.return_value = BytesIO(json.dumps(envelope).encode())
        settings = Settings(earnings_agent_model="fixture", earnings_agent_api_key="fixture")
        args = (
            settings,
            "NASDAQ:MSFT",
            passage,
            {"capex_to_revenue": "0.21"},
            "Prior review",
            date(2026, 10, 28),
        )
        if bad_quote or future_period:
            with pytest.raises(ValueError, match="verified"):
                agent.assess(*args)
        else:
            assert agent.assess(*args).conclusion == "RETAIN"
    content.update(
        conclusion="CHANGE",
        replacement="0.49",
        passage="Capex including finance leases was 49 percent.",
    )
    with pytest.raises(ValueError, match="cash-basis"):
        Analysis.model_validate(content)
