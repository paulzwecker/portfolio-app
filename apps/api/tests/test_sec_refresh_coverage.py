"""Operational scope evidence never becomes invented issuer success or freshness."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from browser_portfolio_data import prepare_portfolio_data
from browser_sec_data import prepare_sec_data
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_fundamentals_bootstrap import COMPANY_ID
from test_fundamentals_portfolio_scope import _source
from test_sec_incremental_refresh import FACTS, FILINGS, _refresh, _transports

from portfolio_api.company_sec_coverage import _issuer_result, company_sec_coverage
from portfolio_api.domain.models import ExternalIngestionAttempt, ExternalIngestionRun
from portfolio_api.reported_fundamentals import SEC_PROVIDER_ID
from portfolio_api.sec_refresh_scope import SEC_SCOPE_VERSION


def _record_run(
    session: Session,
    ids: list[UUID],
    *,
    domain: str = "REPORTED_FUNDAMENTALS",
    status: str = "PARTIAL",
    at: datetime | None = None,
    report: dict[str, Any] | None = None,
    mapped_ids: list[UUID] | None = None,
) -> ExternalIngestionRun:
    at = at or datetime.now(UTC)
    run = ExternalIngestionRun(
        provider_id=SEC_PROVIDER_ID,
        domain=domain,
        idempotency_key=f"synthetic:{uuid4()}",
        status=status,
        requested_at=at,
        created_at=at,
        started_at=at,
        finished_at=None if status == "RUNNING" else at + timedelta(seconds=1),
        attempt_count=0 if status == "RUNNING" else 1,
        failure_code="NETWORK_ERROR" if status == "FAILED" else None,
        request_scope={
            "scope": "sec_issuer_refresh",
            "sec_scope_version": SEC_SCOPE_VERSION,
            "company_ids": [str(item) for item in ids],
            "verified_cik_mappings": [{"company_id": str(item)} for item in (mapped_ids or [])],
        },
        report=report or {},
    )
    session.add(run)
    session.flush()
    if status != "RUNNING":
        session.add(
            ExternalIngestionAttempt(
                run_id=run.id,
                attempt_number=1,
                status="SUCCEEDED" if status == "COMPLETE" else status,
                started_at=at,
                finished_at=at + timedelta(seconds=1),
                retryable=status == "FAILED",
                report=report or {},
            )
        )
    return run


@pytest.mark.integration
def test_real_scoped_results_reach_read_only_api_without_conflating_batch_gaps(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(postgres_engine)
    calls = _transports(monkeypatch)
    request_id = uuid4()
    _refresh(postgres_engine, domains=[FACTS, FILINGS], request_nonce=request_id)
    with postgres_engine.connect() as connection:
        schema = str(connection.scalar(text("SELECT current_schema()")))
    before = table_counts(postgres_engine)
    settings = fixture_settings()
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            response = client.get(f"/v1/companies/{COMPANY_ID}/sec-coverage")
            assert response.status_code == 200
            data = response.json()
            facts, filings = data["fundamentals"]["refresh"], data["filings"]["refresh"]
            assert facts["batch_status"] == filings["batch_status"] == "PARTIAL"
            assert facts["issuer_outcome"] == "DATA_CHECK" and facts["source_record_count"] > 0
            assert filings["issuer_outcome"] == "REPORTED" and filings["source_record_count"] == 2
            assert facts["trigger"] == "MANUAL" and facts["request_id"] == str(request_id)
            assert facts["scope_company_count"] == 3 and facts["mapped_company_count"] == 1
            missing = client.get(f"/v1/companies/{source.unmapped_company_id}/sec-coverage").json()
            assert missing["fundamentals"]["refresh"]["issuer_outcome"] == "UNMAPPED"
            assert missing["fundamentals"]["refresh"]["source_record_count"] is None
    finally:
        reader.dispose()
    assert len(calls) == 2 and table_counts(postgres_engine) == before


@pytest.mark.integration
def test_batch_filings_cannot_attribute_aggregate_success_to_individual_issuer(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        run = _record_run(
            session,
            [COMPANY_ID, source.watchlist_company_id],
            domain="SOURCE_DOCUMENTS",
            mapped_ids=[COMPANY_ID, source.watchlist_company_id],
            report={
                "provider_result": {
                    "reconciliation": {"documents_imported": 100, "documents_reused": 0}
                }
            },
        )
        coverage = company_sec_coverage(session, COMPANY_ID).filings
        assert coverage.refresh is not None and coverage.refresh.run_id == run.id
        assert coverage.refresh.issuer_outcome == "NOT_REPORTED"
        assert (
            coverage.refresh.source_record_count is None
            and coverage.refresh.scope_company_count == 2
        )
        assert coverage.record_count == 0 and coverage.latest_retrieved_at is None


@pytest.mark.integration
def test_failed_refresh_keeps_retained_evidence_and_separate_execution_time(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(postgres_engine)
    _transports(monkeypatch)
    _refresh(postgres_engine, domains=[FACTS], company_ids={COMPANY_ID}, request_nonce=uuid4())
    with Session(postgres_engine) as session, session.begin():
        before = company_sec_coverage(session, COMPANY_ID).fundamentals
        run = _record_run(
            session,
            [COMPANY_ID],
            status="FAILED",
            mapped_ids=[COMPANY_ID],
            at=datetime.now(UTC) + timedelta(hours=1),
            report={
                "mapped_results": [
                    {"company_id": str(COMPANY_ID), "reconciliation": {"source_fact_count": 999}}
                ]
            },
        )
        after = company_sec_coverage(session, COMPANY_ID).fundamentals
        assert after.record_count == before.record_count and after.record_count > 0
        assert after.latest_retrieved_at == before.latest_retrieved_at
        assert after.refresh is not None and after.refresh.run_id == run.id
        assert (
            after.refresh.issuer_outcome == "NOT_REPORTED"
            and after.refresh.source_record_count is None
        )
        assert after.refresh.retryable and after.refresh.failure_code == "NETWORK_ERROR"


@pytest.mark.integration
def test_latest_relevant_attempt_is_not_hidden_by_unrelated_runs_or_newer_creation(
    postgres_engine: Engine,
) -> None:
    _source(postgres_engine)
    now = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        older = _record_run(
            session,
            [COMPANY_ID],
            at=now - timedelta(days=3),
            status="FAILED",
            mapped_ids=[COMPANY_ID],
        )
        older.last_attempt_started_at = now
        older.finished_at = now + timedelta(seconds=1)
        _record_run(session, [COMPANY_ID], at=now - timedelta(days=1), mapped_ids=[COMPANY_ID])
        for _ in range(45):
            _record_run(session, [uuid4()], at=now + timedelta(minutes=1))
        latest = company_sec_coverage(session, COMPANY_ID).fundamentals.refresh
        assert latest is not None and latest.run_id == older.id
        assert latest.started_at == now and latest.batch_status == "FAILED"
        assert company_sec_coverage(session, COMPANY_ID).filings.refresh is None


@pytest.mark.integration
def test_legacy_unknown_mapping_and_running_requests_preserve_missing_outcomes(
    postgres_engine: Engine,
) -> None:
    _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        run = _record_run(session, [COMPANY_ID], status="RUNNING")
        run.request_scope = {"company_ids": [str(COMPANY_ID)]}
        session.flush()
        result = company_sec_coverage(session, COMPANY_ID).fundamentals.refresh
        assert result is not None and result.trigger == "LEGACY"
        assert result.attempt_count == 0 and result.attempt_id is None
        assert result.mapped_company_count is None and result.source_record_count is None
        assert result.issuer_outcome == "NOT_REPORTED" and not result.retryable


@pytest.mark.integration
def test_malformed_scope_and_request_identity_cannot_imply_scheduled_success(
    postgres_engine: Engine,
) -> None:
    _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        run = _record_run(session, [COMPANY_ID], status="FAILED", mapped_ids=[COMPANY_ID])
        run.request_scope = {**run.request_scope, "operational_request_id": "invalid-private-token"}
        run.failure_message = "private-diagnostic-must-not-escape"
        session.flush()
        coverage = company_sec_coverage(session, COMPANY_ID)
        assert coverage.fundamentals.refresh is not None
        assert coverage.fundamentals.refresh.trigger == "LEGACY"
        assert coverage.fundamentals.refresh.request_id is None
        assert "private" not in coverage.model_dump_json()
        run.request_scope = {**run.request_scope, "company_ids": [str(COMPANY_ID), str(COMPANY_ID)]}
        session.flush()
        assert company_sec_coverage(session, COMPANY_ID).fundamentals.refresh is None


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario,status", [("sec-refresh-partial", "COMPLETE"), ("sec-refresh-outage", "FAILED")]
)
def test_real_browser_fixture_exposes_attributed_refresh_scope(
    postgres_engine: Engine, tmp_path: Path, scenario: str, status: str
) -> None:
    settings = fixture_settings()
    metadata = prepare_portfolio_data(postgres_engine, tmp_path, "unpriced", settings)
    prepare_sec_data(postgres_engine, metadata, scenario)
    before = table_counts(postgres_engine)
    with Session(postgres_engine) as session:
        coverage = company_sec_coverage(session, UUID(str(metadata["company_id"])))
        refresh = coverage.filings.refresh
        assert refresh is not None and refresh.batch_status == status
        assert refresh.issuer_outcome == "NOT_REPORTED" and refresh.source_record_count is None
        assert coverage.filings.record_count == 4
        assert refresh.scope_company_count == (2 if status == "COMPLETE" else 1)
    assert table_counts(postgres_engine) == before


@pytest.mark.parametrize(
    "result,expected,count",
    [
        ({"reconciliation": {"source_fact_count": 0}}, "UNAVAILABLE", 0),
        ({"reconciliation": {"source_fact_count": 0, "data_check_count": 1}}, "DATA_CHECK", 0),
        ({"reconciliation": {"source_fact_count": 12}}, "REPORTED", 12),
        ({"reconciliation": {"source_fact_count": 12, "data_check_count": 1}}, "DATA_CHECK", 12),
        ({"status": "DATA_CHECK"}, "DATA_CHECK", None),
        ({"reconciliation": {"source_fact_count": True}}, "NOT_REPORTED", None),
        ({"reconciliation": {"source_fact_count": -1}}, "NOT_REPORTED", None),
        ({"reconciliation": {"source_fact_count": "12"}}, "NOT_REPORTED", None),
        ({}, "NOT_REPORTED", None),
    ],
)
def test_typed_issuer_results_preserve_zero_missing_and_quality(
    result: dict[str, Any], expected: str, count: int | None
) -> None:
    run = ExternalIngestionRun(
        domain="REPORTED_FUNDAMENTALS",
        status="PARTIAL",
        report={"mapped_results": [{"company_id": str(COMPANY_ID), **result}]},
    )
    assert _issuer_result(run, COMPANY_ID, {str(COMPANY_ID)}) == (expected, count)


def test_duplicate_or_other_issuer_evidence_is_unattributed() -> None:
    item = {"company_id": str(COMPANY_ID), "reconciliation": {"source_fact_count": 12}}
    run = ExternalIngestionRun(
        domain="REPORTED_FUNDAMENTALS", status="PARTIAL", report={"mapped_results": [item, item]}
    )
    assert _issuer_result(run, COMPANY_ID, {str(COMPANY_ID)}) == ("NOT_REPORTED", None)
    assert _issuer_result(run, uuid4(), {str(COMPANY_ID)}) == ("UNMAPPED", None)


@pytest.mark.parametrize(
    "reconciliation,result,expected,count",
    [
        ({"documents_imported": 0, "documents_reused": 0}, {}, "UNAVAILABLE", 0),
        (
            {"documents_imported": 0, "documents_reused": 0, "existing_metadata_conflicts": 1},
            {},
            "DATA_CHECK",
            0,
        ),
        ({"documents_imported": 0, "documents_reused": 2}, {}, "REPORTED", 2),
        (
            {"documents_imported": 2, "documents_reused": 0},
            {"history_files_deferred": 1},
            "DATA_CHECK",
            2,
        ),
        ({"documents_imported": 2, "existing_metadata_conflicts": 1}, {}, "DATA_CHECK", 2),
    ],
)
def test_single_mapped_filing_subject_has_attributable_result(
    reconciliation: dict[str, Any], result: dict[str, Any], expected: str, count: int
) -> None:
    run = ExternalIngestionRun(
        domain="SOURCE_DOCUMENTS",
        status="PARTIAL",
        report={"provider_result": {"reconciliation": reconciliation, **result}},
    )
    assert _issuer_result(run, COMPANY_ID, {str(COMPANY_ID)}) == (expected, count)
