import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import Company, ReportedFundamentalObservation
from portfolio_api.external_data import ExternalDataDomain, RawProviderRecord
from portfolio_api.financial_statements import company_financial_statements
from portfolio_api.main import create_app
from portfolio_api.reported_fundamentals import ingest_sec_company_facts, record_cik_mapping
from portfolio_api.settings import Settings


def _record(*, fy: int, value: int, filed: str, observed: datetime) -> RawProviderRecord:
    content = json.dumps(
        {
            "cik": 1,
            "entityName": "Statement Fixture Inc.",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2022-07-01",
                                    "end": "2023-06-30",
                                    "val": value,
                                    "fy": fy,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": filed,
                                    "accn": f"0000000001-{fy % 100:02d}-000001",
                                    "frame": "CY2023",
                                }
                            ]
                        }
                    }
                }
            },
        }
    ).encode()
    return RawProviderRecord(
        domain=ExternalDataDomain.REPORTED_FUNDAMENTALS,
        provider_id="sec_edgar",
        provider_schema_version="companyfacts-v1",
        source_record_id="CIK0000000001",
        source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json",
        media_type="application/json",
        retrieved_at=observed,
        payload=content,
        payload_sha256=hashlib.sha256(content).hexdigest(),
    )


def test_filing_context_does_not_duplicate_period_or_relabel_comparatives(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    first_known = datetime(2026, 10, 5, 12, tzinfo=UTC)
    second_known = datetime(2026, 10, 6, 12, tzinfo=UTC)
    with Session(postgres_engine) as session:
        session.add(Company(id=company_id, name="Statement fixture", reporting_currency="USD"))
        session.flush()
        record_cik_mapping(
            session,
            company_id,
            "0000000001",
            "Statement Fixture Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )
        monkeypatch.setattr("portfolio_api.reported_fundamentals.now", lambda: first_known)
        ingest_sec_company_facts(
            session,
            company_id,
            "0000000001",
            _record(fy=2023, value=100, filed="2023-07-27", observed=first_known),
        )
        session.commit()
        monkeypatch.setattr("portfolio_api.reported_fundamentals.now", lambda: second_known)
        ingest_sec_company_facts(
            session,
            company_id,
            "0000000001",
            _record(fy=2024, value=95, filed="2024-07-30", observed=second_known),
        )
        session.commit()
        latest = q.company_reported_fundamentals(session, company_id)
        assert len(latest.periods) == 1
        period = latest.periods[0]
        assert (period.fiscal_year, period.fiscal_period) == (2023, "FY")
        assert period.value == Decimal(95) and period.selection_status == "DATA_CHECK"
        assert {item.fiscal_year for item in period.observations} == {2023, 2024}
        historical = q.company_reported_fundamentals(
            session, company_id, as_of=date(2023, 12, 31), known_at=second_known
        )
        assert historical.periods[0].value == Decimal(100)
        known_before = q.company_reported_fundamentals(session, company_id, known_at=first_known)
        assert known_before.periods[0].value == Decimal(100)
        assert len(known_before.periods[0].observations) == 1
        view = company_financial_statements(session, company_id)
        assert view.periods[0].label == "FY2023"
        assert len([row for row in view.rows if row.metric == "REVENUE"]) == 1
        assert view.periods[0].period_end == date(2023, 6, 30)
        assert any(row.metric == "FREE_CASH_FLOW" and not row.cells for row in view.rows)
        assert session.scalar(select(func.count()).select_from(ReportedFundamentalObservation)) == 2
    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine",
        lambda _settings, **_kwargs: postgres_engine,
    )
    with TestClient(create_app(Settings.model_construct())) as client:
        response = client.get(f"/v1/companies/{company_id}/financial-statements?period_limit=5")
        assert response.status_code == 200
        assert response.json()["periods"][0]["label"] == "FY2023"
        assert (
            client.get(
                f"/v1/companies/{company_id}/financial-statements?period_type=INSTANT"
            ).status_code
            == 422
        )
        assert (
            client.get(
                f"/v1/companies/{company_id}/financial-statements?period_limit=200"
            ).status_code
            == 422
        )


def test_later_comparative_without_original_context_keeps_fiscal_label_unknown(
    postgres_engine: Engine,
) -> None:
    company_id = uuid4()
    with Session(postgres_engine) as session:
        session.add(Company(id=company_id, name="Unknown calendar issuer"))
        session.flush()
        record_cik_mapping(
            session,
            company_id,
            "0000000001",
            "Statement Fixture Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )
        ingest_sec_company_facts(
            session,
            company_id,
            "0000000001",
            _record(fy=2024, value=100, filed="2024-07-30", observed=datetime.now(UTC)),
        )
        session.commit()
        period = q.company_reported_fundamentals(session, company_id).periods[0]
        assert period.fiscal_year is None and period.fiscal_period is None
        assert (
            company_financial_statements(session, company_id).periods[0].label
            == "Year ended 2023-06-30"
        )


@pytest.mark.parametrize("missing", ["period", "currency", "observed", "units", "stale"])
def test_unknown_consensus_metadata_never_becomes_an_available_aligned_line(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    company_id = uuid4()
    observation = s.ConsensusEstimateObservationRead.model_construct(
        id=uuid4(),
        value=Decimal(120),
        data_quality="PASS",
        quality_reason=None,
        observed_at=None if missing == "observed" else datetime.now(UTC),
    )  # type: ignore[call-arg]
    period = s.ConsensusEstimatePeriodRead.model_construct(
        metric="REVENUE",
        period_type="ANNUAL",
        forecast_period="FY2027",
        period_end=None if missing == "period" else date(2027, 6, 30),
        currency=None if missing == "currency" else "USD",
        unit="unknown" if missing == "units" else "currency",
        current_observation=observation,
        history=[observation],
    )
    provider = s.ConsensusEstimateProviderRead.model_construct(
        provider_id="fixture",
        selected=True,
        freshness="STALE" if missing == "stale" else "FRESH",
        periods=[period],
    )  # type: ignore[call-arg]
    with Session(postgres_engine) as session:
        session.add(Company(id=company_id, name="Forecast fixture"))
        session.commit()
        monkeypatch.setattr(
            q,
            "company_consensus_estimates",
            lambda *_args: s.CompanyConsensusEstimatesRead.model_construct(providers=[provider]),  # type: ignore[call-arg]
        )
        view = company_financial_statements(session, company_id)
        consensus_rows = [row for row in view.rows if row.source_kind == "CONSENSUS"]
        if missing == "stale":
            assert consensus_rows[0].cells[0].status == "DATA_CHECK"
        else:
            assert consensus_rows == []
            assert any(item.reference_id == observation.id for item in view.limitations)
