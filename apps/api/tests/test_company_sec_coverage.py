"""Read-only issuer evidence retains dates, mapping gaps and failed bootstrap context."""

from datetime import date
from uuid import uuid4

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_fundamentals_bootstrap import COMPANY_ID, RETRIEVED_AT, SyntheticSecProvider, _execute
from test_fundamentals_portfolio_scope import _source

from portfolio_api.company_sec_coverage import company_sec_coverage
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import Actor
from portfolio_api.fundamentals_bootstrap import prepare_fundamentals_bootstrap
from portfolio_api.reported_fundamentals import record_cik_mapping
from portfolio_api.source_documents import create_company_source_document


@pytest.mark.integration
def test_unmapped_coverage_is_empty_and_api_reads_are_database_read_only(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    before = table_counts(postgres_engine)
    with postgres_engine.connect() as connection:
        schema = str(connection.scalar(text("SELECT current_schema()")))
    settings = fixture_settings()
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            response = client.get(f"/v1/companies/{source.unmapped_company_id}/sec-coverage")
            assert response.status_code == 200
            data = response.json()
            assert data["mapping_status"] == "UNMAPPED" and data["cik"] is None
            assert data["fundamentals"]["record_count"] == data["filings"]["record_count"] == 0
            assert data["fundamentals"]["latest_retrieved_at"] is None
            assert data["fundamentals"]["latest_period_end"] is None
            assert data["fundamentals"]["bootstrap"] is None
            assert data["metrics_present"] == [] and len(data["metrics_missing"]) == 10
            assert client.get(f"/v1/companies/{uuid4()}/sec-coverage").status_code == 404
    finally:
        reader.dispose()
    assert table_counts(postgres_engine) == before


@pytest.mark.integration
def test_imported_coverage_keeps_economic_filing_retrieval_and_recording_dates_distinct(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session:
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id = run.id
        session.commit()
    provider = SyntheticSecProvider()
    _execute(postgres_engine, run_id, provider, 10)
    with Session(postgres_engine) as session:
        coverage = company_sec_coverage(session, COMPANY_ID)
        unrelated = company_sec_coverage(session, source.unmapped_company_id)
        assert coverage.mapping_status == "MAPPED" and coverage.cik == "0000000001"
        assert coverage.fundamentals.record_count > 0 and coverage.filings.record_count == 4
        assert coverage.fundamentals.latest_period_end == date(2024, 3, 31)
        assert coverage.fundamentals.latest_filed_at == date(2025, 3, 1)
        assert coverage.fundamentals.latest_retrieved_at == RETRIEVED_AT
        assert coverage.fundamentals.latest_recorded_at is not None
        assert coverage.fundamentals.latest_recorded_at > RETRIEVED_AT
        assert coverage.fundamentals.data_check_count > 0
        assert len(coverage.metrics_present) == 2 and len(coverage.metrics_missing) == 8
        assert unrelated.fundamentals.record_count == unrelated.filings.record_count == 0
    _execute(postgres_engine, run_id, provider, 10)
    with Session(postgres_engine) as session:
        replay = company_sec_coverage(session, COMPANY_ID)
        assert replay.fundamentals.latest_retrieved_at == coverage.fundamentals.latest_retrieved_at
        assert replay.fundamentals.latest_recorded_at == coverage.fundamentals.latest_recorded_at
        assert replay.fundamentals.record_count == coverage.fundamentals.record_count


@pytest.mark.integration
def test_failed_new_bootstrap_remains_visible_beside_retained_coverage(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session:
        first = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        first_id = first.id
        session.commit()
    _execute(postgres_engine, first_id, SyntheticSecProvider(), 10)
    with Session(postgres_engine) as session:
        before = company_sec_coverage(session, COMPANY_ID)
        next_run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        next_id = next_run.id
        session.commit()
    _execute(postgres_engine, next_id, SyntheticSecProvider(fail_first_source_request=True), 1)
    with Session(postgres_engine) as session:
        after = company_sec_coverage(session, COMPANY_ID)
        assert after.fundamentals.record_count == before.fundamentals.record_count
        assert after.filings.bootstrap is not None and after.filings.bootstrap.status == "FAILED"
        assert (
            after.filings.bootstrap.retryable
            and after.filings.bootstrap.next_attempt_at is not None
        )
        assert after.filings.bootstrap.run_id == next_id
        assert (
            after.fundamentals.bootstrap is not None
            and after.fundamentals.bootstrap.status == "PENDING"
        )


@pytest.mark.integration
@pytest.mark.parametrize("ambiguous", [False, True])
def test_invalid_identity_evidence_never_becomes_a_source_link(
    postgres_engine: Engine, ambiguous: bool
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        record_cik_mapping(
            session,
            source.unmapped_company_id,
            "0000000090",
            "Invalid fixture",
            "javascript:invalid",
        )
        if ambiguous:
            record_cik_mapping(
                session,
                source.unmapped_company_id,
                "0000000091",
                "Other fixture",
                "https://www.sec.gov/edgar/browse/?CIK=91",
            )
        status = company_sec_coverage(session, source.unmapped_company_id)
        assert status.mapping_status == ("AMBIGUOUS" if ambiguous else "INVALID")
        assert status.identity_evidence_url is status.cik is None


@pytest.mark.integration
def test_manual_source_link_does_not_claim_an_sec_retrieval(postgres_engine: Engine) -> None:
    _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        create_company_source_document(
            session,
            COMPANY_ID,
            s.SourceDocumentCreate(
                provider_id="company_source",
                source_name="Synthetic IR",
                external_identifier="ir-report",
                document_type="ANNUAL_REPORT",
                title="Synthetic report",
                published_at=date(2026, 11, 1),
                canonical_url="https://ir.example.test/report",
                actor=Actor.LOCAL_USER,
            ),
        )
        status = company_sec_coverage(session, COMPANY_ID)
        assert status.filings.record_count == 0 and status.filings.latest_retrieved_at is None


@pytest.mark.integration
def test_identity_evidence_with_embedded_credentials_is_withheld(postgres_engine: Engine) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        record_cik_mapping(
            session,
            source.unmapped_company_id,
            "0000000090",
            "Synthetic issuer",
            "https://fixture:synthetic@www.sec.gov/edgar/browse/?CIK=90",
        )
        coverage = company_sec_coverage(session, source.unmapped_company_id)
        assert coverage.mapping_status == "INVALID"
        assert coverage.identity_evidence_url is coverage.provider_company_name is None
