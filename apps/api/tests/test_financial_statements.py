import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    CompanyProviderIdentifier,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
)
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


@pytest.mark.integration
def test_sec_identity_guard_preserves_evidence_and_knowledge_cutoffs(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    mapping_at = datetime(2020, 1, 1, tzinfo=UTC)
    retrieved_at = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2027, 1, 1, tzinfo=UTC)
    monkeypatch.setattr("portfolio_api.reported_fundamentals.now", lambda: mapping_at)
    monkeypatch.setattr(
        "portfolio_api.domain.queries.now", lambda: datetime(2030, 1, 1, tzinfo=UTC)
    )
    with Session(postgres_engine) as session:
        session.add(Company(id=company_id, name="Identity fixture"))
        session.flush()
        record_cik_mapping(
            session,
            company_id,
            "0000000001",
            "Statement Fixture Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )
        monkeypatch.setattr("portfolio_api.reported_fundamentals.now", lambda: retrieved_at)
        ingest_sec_company_facts(
            session,
            company_id,
            "0000000001",
            _record(fy=2023, value=100, filed="2023-07-27", observed=retrieved_at),
        )
        session.commit()
        first = q.company_reported_fundamentals(session, company_id, known_at=retrieved_at)
        assert first.periods[0].selection_status == "AVAILABLE"
        assert first.periods[0].value == Decimal(100)
        too_early = q.company_reported_fundamentals(
            session, company_id, as_of=date(2019, 12, 31), known_at=retrieved_at
        )
        assert too_early.provider_ids == []

        fact = session.scalars(select(ReportedFundamentalObservation)).one()
        original_batch = session.get(ReportedFundamentalBatch, fact.batch_id)
        assert original_batch is not None
        # An observation cannot use batch identity evidence recorded later than its cutoff.
        batch_id = original_batch.id
        session.execute(
            update(ReportedFundamentalBatch)
            .where(ReportedFundamentalBatch.id == batch_id)
            .values(recorded_at=later)
        )
        session.commit()
        before_receipt = q.company_reported_fundamentals(session, company_id, known_at=retrieved_at)
        assert before_receipt.periods[0].selection_status == "DATA_CHECK"
        assert before_receipt.periods[0].value is None
        session.execute(
            update(ReportedFundamentalBatch)
            .where(ReportedFundamentalBatch.id == batch_id)
            .values(recorded_at=retrieved_at, observed_at=later)
        )
        session.commit()
        before_observation = q.company_reported_fundamentals(
            session, company_id, known_at=retrieved_at
        )
        assert before_observation.periods[0].selection_status == "DATA_CHECK"
        session.execute(
            update(ReportedFundamentalBatch)
            .where(ReportedFundamentalBatch.id == batch_id)
            .values(observed_at=retrieved_at)
        )
        session.commit()
        original_batch = session.get(ReportedFundamentalBatch, batch_id)
        assert original_batch is not None
        batch_values = {
            column.name: getattr(original_batch, column.name)
            for column in ReportedFundamentalBatch.__table__.columns
        }
        batch_values.update(
            id=uuid4(),
            source_digest="9" * 64,
            query_scope={"company_id": str(company_id), "cik": "0000000002"},
        )
        foreign_batch = ReportedFundamentalBatch(**batch_values)
        session.add(foreign_batch)
        session.flush()
        fact_values = {
            column.name: getattr(fact, column.name)
            for column in ReportedFundamentalObservation.__table__.columns
        }
        fact_values.update(
            id=uuid4(),
            batch_id=foreign_batch.id,
            provider_entity_id="0000000002",
            source_record_id="synthetic-other-cik",
            observation_fingerprint="8" * 64,
        )
        foreign = ReportedFundamentalObservation(**fact_values)
        session.add(foreign)
        fact_values.update(
            id=uuid4(),
            source_record_id="synthetic-disjoint-other-cik",
            observation_fingerprint="7" * 64,
            period_end=datetime(2024, 6, 30, tzinfo=UTC),
        )
        session.add(ReportedFundamentalObservation(**fact_values))
        # A safe quarter may not derive its fiscal label from a mixed-identity annual group.
        safe_quarter_values = {
            column.name: getattr(fact, column.name)
            for column in ReportedFundamentalObservation.__table__.columns
        }
        safe_quarter_values.update(
            id=uuid4(),
            period_type="QUARTERLY",
            period_start=datetime(2023, 4, 1, tzinfo=UTC),
            fiscal_year=None,
            fiscal_period=None,
            source_record_id="synthetic-safe-quarter",
            observation_fingerprint="6" * 64,
        )
        session.add(ReportedFundamentalObservation(**safe_quarter_values))
        non_sec_values = dict(safe_quarter_values)
        non_sec_values.update(
            id=uuid4(),
            provider_id="fixture_vendor",
            provider_entity_id="fixture",
            period_end=datetime(2023, 3, 31, tzinfo=UTC),
            period_start=datetime(2023, 1, 1, tzinfo=UTC),
            source_record_id="synthetic-non-sec",
            observation_fingerprint="5" * 64,
        )
        session.add(ReportedFundamentalObservation(**non_sec_values))
        session.commit()
        periods = q.company_reported_fundamentals(session, company_id).periods
        assert len(periods) == 4
        sec_annual = [p for p in periods if p.period_type == "ANNUAL"]
        assert all(p.selection_status == "DATA_CHECK" and p.value is None for p in sec_annual)
        quarters = [p for p in periods if p.period_type == "QUARTERLY"]
        assert all(p.selection_status == "AVAILABLE" for p in quarters)
        assert (
            next(p for p in quarters if p.period_end.date() == date(2023, 6, 30)).fiscal_period
            is None
        )
        period = next(p for p in periods if len(p.observations) == 2)
        assert period.selection_status == "DATA_CHECK"
        assert period.value is None and period.selected_observation is None
        assert period.identity_issue and len(period.observations) == 2
        assert period.fiscal_year is None and period.fiscal_period is None
        statement = company_financial_statements(session, company_id)
        cell = next(
            cell
            for row in statement.rows
            if row.metric == "REVENUE"
            for cell in row.cells
            if len(cell.source_ids) == 2
        )
        assert (
            cell.status == "DATA_CHECK" and cell.value is None and cell.selected_source_id is None
        )
        assert cell.reason and "issuer identity" in cell.reason and len(cell.source_ids) == 2

        monkeypatch.setattr("portfolio_api.reported_fundamentals.now", lambda: later)
        record_cik_mapping(
            session,
            company_id,
            "0000000002",
            "Other fixture",
            "https://www.sec.gov/edgar/browse/?CIK=2",
        )
        session.commit()
        historical = q.company_reported_fundamentals(session, company_id, known_at=retrieved_at)
        assert historical.provider_ids == ["0000000001"]
        assert (
            next(p for p in historical.periods if p.period_type == "ANNUAL").selection_status
            == "DATA_CHECK"
        )
        current = q.company_reported_fundamentals(session, company_id)
        assert current.provider_identity_status == "AMBIGUOUS"
        assert current.periods[0].value is None
        assert (
            next(
                p for p in current.periods if p.period_end.date() == date(2023, 3, 31)
            ).selection_status
            == "AVAILABLE"
        )


@pytest.mark.integration
def test_late_mapping_cannot_verify_earlier_known_fact(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    mapping_at = datetime(2025, 1, 1, tzinfo=UTC)
    fact_at = datetime(2024, 1, 1, tzinfo=UTC)
    monkeypatch.setattr("portfolio_api.reported_fundamentals.now", lambda: mapping_at)
    with Session(postgres_engine) as session:
        session.add(Company(id=company_id, name="Late identity fixture"))
        session.flush()
        record_cik_mapping(
            session,
            company_id,
            "0000000001",
            "Statement Fixture Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )
        monkeypatch.setattr("portfolio_api.reported_fundamentals.now", lambda: fact_at)
        ingest_sec_company_facts(
            session,
            company_id,
            "0000000001",
            _record(fy=2023, value=100, filed="2023-07-27", observed=fact_at),
        )
        session.commit()
        historical = q.company_reported_fundamentals(
            session, company_id, as_of=date(2024, 12, 31), known_at=fact_at
        )
        assert historical.provider_ids == [] and historical.provider_identity_status == "UNMAPPED"
        assert len(historical.periods) == 1
        assert historical.periods[0].selection_status == "DATA_CHECK"
        assert historical.periods[0].value is None and historical.periods[0].identity_issue
        assert len(historical.periods[0].observations) == 1
        # Effective and knowledge times are separate; this fixture-only backdate
        # represents evidence that became known after its effective date.
        session.execute(
            update(CompanyProviderIdentifier)
            .where(CompanyProviderIdentifier.company_id == company_id)
            .values(effective_at=datetime(2020, 1, 1, tzinfo=UTC))
        )
        session.commit()
        current_knowledge = q.company_reported_fundamentals(
            session, company_id, as_of=date(2024, 12, 31)
        )
        assert current_knowledge.periods[0].selection_status == "AVAILABLE"
        historical = q.company_reported_fundamentals(
            session, company_id, as_of=date(2024, 12, 31), known_at=fact_at
        )
        assert historical.periods[0].selection_status == "DATA_CHECK"
        assert historical.provider_ids == []
        session.execute(
            update(CompanyProviderIdentifier)
            .where(CompanyProviderIdentifier.company_id == company_id)
            .values(evidence_source="https://example.test/?CIK=1")
        )
        session.commit()
        invalid = q.company_reported_fundamentals(session, company_id)
        assert invalid.provider_identity_status == "MAPPED" and invalid.provider_identity_issue
        assert invalid.periods[0].value is None and invalid.periods[0].identity_issue


@pytest.mark.integration
def test_filing_context_does_not_duplicate_period_or_relabel_comparatives(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    first_known = datetime(2026, 10, 5, 12, tzinfo=UTC)
    second_known = datetime(2026, 10, 6, 12, tzinfo=UTC)
    monkeypatch.setattr(
        "portfolio_api.reported_fundamentals.now", lambda: datetime(2020, 1, 1, tzinfo=UTC)
    )
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


@pytest.mark.integration
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
@pytest.mark.integration
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
