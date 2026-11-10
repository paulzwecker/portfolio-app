"""Read-only issuer evidence retains dates, mapping gaps and failed bootstrap context."""

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_fundamentals_bootstrap import COMPANY_ID, RETRIEVED_AT, SyntheticSecProvider, _execute
from test_fundamentals_portfolio_scope import _source

from portfolio_api.company_sec_coverage import _bootstrap_identity, company_sec_coverage
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Actor,
    CompanyProviderIdentifier,
    FundamentalsBootstrapCheckpoint,
    FundamentalsBootstrapRun,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
)
from portfolio_api.fundamentals_bootstrap import (
    BOOTSTRAP_VERSION,
    ReviewedCikMapping,
    _canonical_json,
    _sha256,
    prepare_fundamentals_bootstrap,
)
from portfolio_api.reported_fundamentals import record_cik_mapping
from portfolio_api.sec_refresh_scope import _mapping_values
from portfolio_api.source_documents import create_company_source_document


def test_bootstrap_identity_requires_bound_run_and_matching_checkpoint() -> None:
    mapping = ReviewedCikMapping(
        mapping_id=uuid4(),
        company_id=COMPANY_ID,
        company_name="Synthetic",
        cik="0000000001",
        provider_company_name="Synthetic issuer",
        evidence_source="https://www.sec.gov/edgar/browse/?CIK=1",
        lifecycle="WATCHLIST",
        effective_at=datetime(2026, 1, 1, tzinfo=UTC),
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    mappings = [mapping.manifest()]
    digest = _sha256(_canonical_json(_mapping_values(mappings)).encode("utf-8"))
    scope = {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "provider_id": "sec_edgar",
        "mapping_sha256": digest,
        "mappings": mappings,
    }
    run = FundamentalsBootstrapRun(
        id=uuid4(),
        bootstrap_version=BOOTSTRAP_VERSION,
        target_environment="rehearsal",
        mapping_sha256=digest,
        scope=scope,
        input_digest=_sha256(
            _canonical_json({"target_environment": "rehearsal", "scope": scope}).encode("utf-8")
        ),
    )
    checkpoint = FundamentalsBootstrapCheckpoint(
        run_id=run.id,
        company_id=COMPANY_ID,
        mapping_identifier_id=mapping.mapping_id,
        cik=mapping.cik,
    )
    assert _bootstrap_identity(run, checkpoint, mapping).status == "MATCHED"
    assert (
        _bootstrap_identity(run, checkpoint, replace(mapping, lifecycle="PORTFOLIO")).status
        == "MATCHED"
    )
    assert (
        _bootstrap_identity(run, checkpoint, replace(mapping, company_name="Renamed")).status
        == "CHANGED"
    )
    assert _bootstrap_identity(run, checkpoint, None).status == "CURRENT_UNAVAILABLE"
    checkpoint.run_id = uuid4()
    assert _bootstrap_identity(run, checkpoint, mapping).status == "UNVERIFIED"
    checkpoint.run_id = run.id
    checkpoint.cik = "0000000002"
    assert _bootstrap_identity(run, checkpoint, mapping).status == "UNVERIFIED"
    checkpoint.cik = mapping.cik
    run.input_digest = "0" * 64
    assert _bootstrap_identity(run, checkpoint, mapping).status == "UNVERIFIED"
    run.input_digest = _sha256(
        _canonical_json({"target_environment": "rehearsal", "scope": scope}).encode("utf-8")
    )
    run.mapping_sha256 = "0" * 64
    assert _bootstrap_identity(run, checkpoint, mapping).status == "UNVERIFIED"
    malformed = [{**mappings[0], "mapping_identifier_id": {"bad": "value"}}]
    malformed_digest = _sha256(_canonical_json(_mapping_values(malformed)).encode("utf-8"))
    run.mapping_sha256 = malformed_digest
    run.scope = {**scope, "mappings": malformed, "mapping_sha256": malformed_digest}
    run.input_digest = _sha256(
        _canonical_json({"target_environment": "rehearsal", "scope": run.scope}).encode("utf-8")
    )
    assert _bootstrap_identity(run, checkpoint, mapping).status == "UNVERIFIED"
    duplicate_cik = [
        mappings[0],
        {**mappings[0], "company_id": str(uuid4()), "mapping_identifier_id": str(uuid4())},
    ]
    duplicate_digest = _sha256(_canonical_json(_mapping_values(duplicate_cik)).encode("utf-8"))
    run.scope = {**scope, "mappings": duplicate_cik, "mapping_sha256": duplicate_digest}
    run.mapping_sha256 = duplicate_digest
    run.input_digest = _sha256(
        _canonical_json({"target_environment": "rehearsal", "scope": run.scope}).encode("utf-8")
    )
    assert _bootstrap_identity(run, checkpoint, mapping).status == "UNVERIFIED"


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
            assert data["fundamental_identity_counts"] == {
                "matching_cik": 0,
                "other_cik": 0,
                "unverified": 0,
            }
            assert data["fundamentals"]["latest_retrieved_at"] is None
            assert data["fundamentals"]["latest_period_end"] is None
            assert data["fundamentals"]["bootstrap"] is None
            assert data["metrics_present"] == [] and len(data["metrics_missing"]) == 10
            assert client.get(f"/v1/companies/{uuid4()}/sec-coverage").status_code == 404
    finally:
        reader.dispose()
    assert table_counts(postgres_engine) == before


@pytest.mark.integration
def test_bootstrap_identity_drift_and_bad_run_fingerprint_are_read_only(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        prepared = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id = prepared.id
    with Session(postgres_engine) as session, session.begin():
        run = session.get(FundamentalsBootstrapRun, run_id)
        assert run is not None
        scope = cast(dict[str, Any], dict(run.scope))
        mappings = [
            {**item, "provider_company_name": "Historical synthetic issuer"}
            for item in scope["mappings"]
        ]
        digest = _sha256(_canonical_json(_mapping_values(mappings)).encode("utf-8"))
        scope.update({"mappings": mappings, "mapping_sha256": digest})
        run.scope = scope
        run.mapping_sha256 = digest
        run.input_digest = _sha256(
            _canonical_json({"target_environment": run.target_environment, "scope": scope}).encode(
                "utf-8"
            )
        )
    with postgres_engine.connect() as connection:
        schema = str(connection.scalar(text("SELECT current_schema()")))
    reader = fixture_read_engine(postgres_engine.url, schema, fixture_settings())
    try:
        before = table_counts(postgres_engine)
        with TestClient(fixture_application(reader, fixture_settings())) as client:
            response = client.get(f"/v1/companies/{COMPANY_ID}/sec-coverage")
            assert response.status_code == 200
            data = response.json()
            assert data["filings"]["bootstrap"]["identity"] == {
                "status": "CHANGED",
                "frozen_cik": "0000000001",
            }
            assert data["fundamentals"]["bootstrap"]["identity"]["status"] == "CHANGED"
        assert table_counts(postgres_engine) == before
        with Session(postgres_engine) as session, session.begin():
            tampered = session.get(FundamentalsBootstrapRun, run_id)
            assert tampered is not None
            tampered.input_digest = "0" * 64
        before = table_counts(postgres_engine)
        with TestClient(fixture_application(reader, fixture_settings())) as client:
            response = client.get(f"/v1/companies/{COMPANY_ID}/sec-coverage")
            assert response.status_code == 200
            assert response.json()["filings"]["bootstrap"]["identity"] == {
                "status": "UNVERIFIED",
                "frozen_cik": None,
            }
        assert table_counts(postgres_engine) == before
    finally:
        reader.dispose()


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
        assert (
            coverage.fundamentals.bootstrap is not None
            and coverage.fundamentals.bootstrap.identity is not None
        )
        assert coverage.fundamentals.bootstrap.identity.status == "MATCHED"
        assert (
            coverage.filings.bootstrap is not None
            and coverage.filings.bootstrap.identity is not None
        )
        assert coverage.filings.bootstrap.identity.status == "MATCHED"
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
def test_retained_fact_identity_counts_follow_recorded_batch_and_current_mapping(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        run_id = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        ).id
    _execute(postgres_engine, run_id, SyntheticSecProvider(), 10)
    with Session(postgres_engine) as session:
        initial = company_sec_coverage(session, COMPANY_ID)
        counts = initial.fundamental_identity_counts
        assert counts is not None and counts.matching_cik == initial.fundamentals.record_count > 1
        assert counts.other_cik == counts.unverified == 0
    # Corrupt fixture-only historical metadata through SQL: ORM history is append-only.
    with postgres_engine.begin() as connection:
        fact_id = connection.scalar(
            select(ReportedFundamentalObservation.id)
            .where(ReportedFundamentalObservation.company_id == COMPANY_ID)
            .limit(1)
        )
        assert fact_id is not None
        connection.execute(
            update(ReportedFundamentalObservation)
            .where(ReportedFundamentalObservation.id == fact_id)
            .values(provider_entity_id="malformed")
        )
    with Session(postgres_engine) as session:
        counts = company_sec_coverage(session, COMPANY_ID).fundamental_identity_counts
        assert counts is not None and counts.unverified == 1
        assert counts.matching_cik == initial.fundamentals.record_count - 1
    with postgres_engine.begin() as connection:
        connection.execute(
            update(CompanyProviderIdentifier)
            .where(
                CompanyProviderIdentifier.company_id == COMPANY_ID,
                CompanyProviderIdentifier.provider_id == "sec_edgar",
            )
            .values(
                identifier_value="0000000099",
                evidence_source="https://www.sec.gov/edgar/browse/?CIK=99",
            )
        )
    with Session(postgres_engine) as session:
        counts = company_sec_coverage(session, COMPANY_ID).fundamental_identity_counts
        assert counts is not None and counts.matching_cik == 0
        assert counts.other_cik == initial.fundamentals.record_count - 1
        assert counts.unverified == 1
    with postgres_engine.begin() as connection:
        connection.execute(
            update(ReportedFundamentalBatch).values(
                query_scope={"company_id": str(COMPANY_ID), "cik": "bad"}
            )
        )
    with Session(postgres_engine) as session:
        counts = company_sec_coverage(session, COMPANY_ID).fundamental_identity_counts
        assert counts is not None and counts.unverified == initial.fundamentals.record_count
    with postgres_engine.begin() as connection:
        connection.execute(
            update(ReportedFundamentalBatch).values(
                query_scope={"company_id": str(COMPANY_ID), "cik": "0000000001"}
            )
        )
        connection.execute(
            update(CompanyProviderIdentifier)
            .where(
                CompanyProviderIdentifier.company_id == COMPANY_ID,
                CompanyProviderIdentifier.provider_id == "sec_edgar",
            )
            .values(evidence_source="invalid")
        )
    with Session(postgres_engine) as session:
        coverage = company_sec_coverage(session, COMPANY_ID)
        assert coverage.mapping_status == "INVALID"
        assert coverage.fundamental_identity_counts is not None
        assert coverage.fundamental_identity_counts.unverified == coverage.fundamentals.record_count


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
        with pytest.raises(ValueError, match="SEC.gov issuer URL"):
            record_cik_mapping(
                session,
                source.unmapped_company_id,
                "0000000090",
                "Invalid fixture",
                "javascript:invalid",
            )
        session.add(
            CompanyProviderIdentifier(
                company_id=source.unmapped_company_id,
                provider_id="sec_edgar",
                identifier_type="SEC_CIK",
                identifier_value="0000000090",
                provider_company_name="Invalid fixture",
                evidence_source="javascript:invalid",
                effective_at=datetime(2026, 1, 1, tzinfo=UTC),
                actor="IMPORT",
            )
        )
        if ambiguous:
            with pytest.raises(ValueError, match="different SEC CIK"):
                record_cik_mapping(
                    session,
                    source.unmapped_company_id,
                    "0000000091",
                    "Other fixture",
                    "https://www.sec.gov/edgar/browse/?CIK=91",
                )
            session.add(
                CompanyProviderIdentifier(
                    company_id=source.unmapped_company_id,
                    provider_id="sec_edgar",
                    identifier_type="SEC_CIK",
                    identifier_value="0000000091",
                    provider_company_name="Other fixture",
                    evidence_source="https://www.sec.gov/edgar/browse/?CIK=91",
                    effective_at=datetime(2026, 1, 1, tzinfo=UTC),
                    actor="IMPORT",
                )
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
        evidence = "https://fixture:synthetic@www.sec.gov/edgar/browse/?CIK=90"
        with pytest.raises(ValueError, match="SEC.gov issuer URL"):
            record_cik_mapping(
                session, source.unmapped_company_id, "0000000090", "Synthetic issuer", evidence
            )
        session.add(
            CompanyProviderIdentifier(
                company_id=source.unmapped_company_id,
                provider_id="sec_edgar",
                identifier_type="SEC_CIK",
                identifier_value="0000000090",
                provider_company_name="Synthetic issuer",
                evidence_source=evidence,
                effective_at=datetime(2026, 1, 1, tzinfo=UTC),
                actor="IMPORT",
            )
        )
        coverage = company_sec_coverage(session, source.unmapped_company_id)
        assert coverage.mapping_status == "INVALID"
        assert coverage.identity_evidence_url is coverage.provider_company_name is None
