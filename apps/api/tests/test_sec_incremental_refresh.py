"""Held-issuer refreshes use real SEC importers and isolated synthetic PostgreSQL data."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Event
from types import SimpleNamespace
from typing import Any, cast
from urllib.error import URLError
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_fundamentals_bootstrap import CIK, COMPANY_ID, MAIN_SUBMISSIONS, _facts_record
from test_fundamentals_portfolio_scope import _set_lifecycle, _source

from portfolio_api.domain import queries
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    CompanyProviderIdentifier,
    CurrentLifecycle,
    ExternalIngestionAttempt,
    ExternalIngestionRun,
    OperationalJobAttempt,
    OperationalJobRequest,
    Portfolio,
    ReportedFundamentalObservation,
    SourceDocument,
)
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import _claim_run, run_scheduled
from portfolio_api.main import create_app
from portfolio_api.manual_operations import create_job_request
from portfolio_api.recurring_operations import _run_sec_domain, process_manual_job_requests
from portfolio_api.reported_fundamentals import SEC_PROVIDER_ID, record_cik_mapping
from portfolio_api.sec_refresh_scope import (
    MAX_SEC_ISSUERS,
    SecRefreshScopeError,
    capture_sec_refresh_scope,
    validate_sec_refresh_scope,
)
from portfolio_api.settings import Settings

FACTS = ExternalDataDomain.REPORTED_FUNDAMENTALS
FILINGS = ExternalDataDomain.SOURCE_DOCUMENTS
SETTINGS = Settings(_env_file=None, sec_user_agent="Synthetic App test@example.invalid")


def _transports(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def download(url: str, _agent: str) -> bytes:
        calls.append(url)
        assert f"CIK{CIK}" in url  # Never fetch the unrelated reviewed issuers in this fixture.
        payload = _facts_record().payload if "companyfacts" in url else MAIN_SUBMISSIONS.payload
        assert payload is not None
        return payload

    monkeypatch.setattr("portfolio_api.reported_fundamentals._download_sec_json", download)
    monkeypatch.setattr("portfolio_api.source_documents._download_sec_json", download)
    monkeypatch.setattr("portfolio_api.external_ingestion.time.sleep", lambda _seconds: None)
    return calls


def _refresh(engine: Engine, **kwargs: Any) -> dict[str, Any]:
    with Session(engine) as session:
        result = run_scheduled(session, SETTINGS, sec_research_scope=True, **kwargs)
        session.commit()
        return result


def _scheduled_clock(monkeypatch: pytest.MonkeyPatch) -> datetime:
    # Retry-budget checks must stay within one UTC day even when CI runs near midnight.
    at = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(
        "portfolio_api.external_ingestion.datetime", SimpleNamespace(now=lambda _tz: at)
    )
    return at


@pytest.mark.integration
def test_held_issuer_without_lifecycle_refreshes_real_financials_and_filings(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(postgres_engine)
    calls = _transports(monkeypatch)
    with Session(postgres_engine) as session:
        before = queries.overview(session, source.portfolio_id)
    request_id = uuid4()
    result = _refresh(postgres_engine, domains=[FACTS, FILINGS], request_nonce=request_id)
    assert result["status"] == "PARTIAL"  # Missing mappings and amended fact checks stay visible.
    assert len(calls) == 2
    with Session(postgres_engine) as session:
        after = queries.overview(session, source.portfolio_id)
        assert before.snapshot == after.snapshot and before.target_revision == after.target_revision
        assert session.get(CurrentLifecycle, COMPANY_ID) is None
        runs = list(session.scalars(select(ExternalIngestionRun)))
        assert len(runs) == 2 and runs[0].request_scope == runs[1].request_scope
        scope = cast(dict[str, Any], runs[0].request_scope)
        assert str(COMPANY_ID) in scope["company_ids"][:2]
        assert scope["company_ids"][-1] == str(source.watchlist_company_id)
        assert scope["selection"]["holding_snapshot_id"] == str(source.snapshot_id)
        assert scope["selection"]["companyless_held_listings"][0]["listing_id"] == str(
            source.fund_listing_id
        )
        assert scope["selection"]["excluded_zero_quantity_listing_ids"] == [
            str(source.zero_listing_id)
        ]
        assert {
            row.company_id for row in session.scalars(select(ReportedFundamentalObservation))
        } == {COMPANY_ID}
        assert {row.company_id for row in session.scalars(select(SourceDocument))} == {COMPANY_ID}
        assert all(
            row.report["lifecycle_counts"] == {"PORTFOLIO": 0, "WATCHLIST": 1} for row in runs
        )
    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine", lambda _settings, **_kwargs: postgres_engine
    )
    with TestClient(create_app(Settings.model_construct())) as client:
        statements = client.get(
            f"/v1/companies/{COMPANY_ID}/financial-statements?period_type=ANNUAL"
        )
        coverage = client.get(f"/v1/companies/{COMPANY_ID}/sec-coverage")
    assert statements.status_code == coverage.status_code == 200
    revenue = next(row for row in statements.json()["rows"] if row["metric"] == "REVENUE")
    assert Decimal(revenue["cells"][0]["value"]) == Decimal("9007199254740994")
    assert coverage.json()["filings"]["record_count"] == 2
    before_replay = table_counts(postgres_engine)
    repeated = _refresh(postgres_engine, domains=[FACTS, FILINGS], request_nonce=request_id)
    assert all(row["idempotent_reuse"] for row in repeated["domains"])
    assert len(calls) == 2 and table_counts(postgres_engine) == before_replay


@pytest.mark.integration
def test_manual_request_freezes_both_steps_and_survives_midnight_and_new_mapping(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(postgres_engine)
    calls = _transports(monkeypatch)
    request_id = uuid4()
    day = datetime.now(UTC).date()
    first = _refresh(postgres_engine, domains=[FACTS], request_nonce=request_id, run_date=day)
    with Session(postgres_engine) as session, session.begin():
        record_cik_mapping(
            session,
            source.watchlist_company_id,
            "0000000002",
            "Watchlist Synthetic Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=2",
        )
        _set_lifecycle(session, COMPANY_ID, "DROP")
    second = _refresh(
        postgres_engine,
        domains=[FILINGS],
        request_nonce=request_id,
        run_date=day + timedelta(days=1),
    )
    repeated = _refresh(
        postgres_engine, domains=[FACTS], request_nonce=request_id, run_date=day + timedelta(days=1)
    )
    assert repeated["domains"][0]["run_id"] == first["domains"][0]["run_id"]
    assert second["run_date"] == day.isoformat() and len(calls) == 2
    with Session(postgres_engine) as session:
        scopes = cast(
            list[dict[str, Any]], list(session.scalars(select(ExternalIngestionRun.request_scope)))
        )
        assert len(scopes) == 2 and scopes[0] == scopes[1]
        assert len(scopes[0]["verified_cik_mappings"]) == 1
    with pytest.raises(ValueError, match="cannot replace"):
        _refresh(
            postgres_engine, domains=[FACTS], request_nonce=request_id, company_ids={COMPANY_ID}
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "column,value",
    [
        ("provider_company_name", "Changed identity"),
        ("evidence_source", "https://www.sec.gov/edgar/browse/?CIK=1&changed=1"),
        ("identifier_value", "0000000010"),
    ],
)
def test_captured_identity_drift_blocks_replay_before_provider_calls(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch, column: str, value: str
) -> None:
    _source(postgres_engine)
    calls = _transports(monkeypatch)
    result = _refresh(postgres_engine, domains=[FACTS], request_nonce=uuid4())
    with Session(postgres_engine) as session, session.begin():
        original = session.get(ExternalIngestionRun, UUID(result["domains"][0]["run_id"]))
        assert original is not None
        scope, run_id = original.request_scope, original.id
        session.execute(
            update(CompanyProviderIdentifier)
            .where(CompanyProviderIdentifier.company_id == COMPANY_ID)
            .values(**{column: value})
        )
    before = table_counts(postgres_engine)
    replay = _refresh(postgres_engine, domains=[FACTS], replay_of_run_id=run_id, replay_scope=scope)
    assert replay["status"] == "BLOCKED"
    assert replay["domains"][0]["failure_code"] == "SEC_SCOPE_INVALID"
    assert len(calls) == 1
    after = table_counts(postgres_engine)
    assert {
        key: value
        for key, value in before.items()
        if key not in {"external_ingestion_runs", "external_ingestion_attempts"}
    } == {
        key: value
        for key, value in after.items()
        if key not in {"external_ingestion_runs", "external_ingestion_attempts"}
    }


@pytest.mark.integration
def test_scope_replacement_budget_and_ambiguous_portfolio_fail_closed(
    postgres_engine: Engine,
) -> None:
    _source(postgres_engine)
    with Session(postgres_engine) as session:
        scope = capture_sec_refresh_scope(
            session, company_ids=None, run_date=datetime.now(UTC).date(), request_id=None
        )
        assert scope is not None
        for key, value in (
            ("scope", "legacy"),
            ("max_mapped_issuers", 1000),
            ("max_new_history_files", 1000),
            ("mapping_sha256", "0" * 64),
        ):
            with pytest.raises(SecRefreshScopeError):
                validate_sec_refresh_scope(session, {**scope, key: value})
        altered = copy.deepcopy(scope)
        altered["company_ids"] = [str(uuid4())]
        with pytest.raises(SecRefreshScopeError):
            validate_sec_refresh_scope(session, altered)
        with pytest.raises(SecRefreshScopeError, match="not found"):
            capture_sec_refresh_scope(
                session, company_ids={uuid4()}, run_date=datetime.now(UTC).date(), request_id=None
            )
        session.add(Portfolio(name="Other portfolio", base_currency="EUR"))
        session.flush()
        with pytest.raises(SecRefreshScopeError, match="one explicit portfolio"):
            capture_sec_refresh_scope(
                session, company_ids=None, run_date=datetime.now(UTC).date(), request_id=None
            )


@pytest.mark.integration
def test_issuer_budget_stops_before_claim_or_network(postgres_engine: Engine) -> None:
    _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        for index in range(MAX_SEC_ISSUERS):
            company = Company(name=f"Bounded synthetic issuer {index}", reporting_currency="USD")
            session.add(company)
            session.flush()
            _set_lifecycle(session, company.id, "WATCHLIST")
            cik = f"{index + 100:010d}"
            record_cik_mapping(
                session,
                company.id,
                cik,
                company.name,
                f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}",
            )
            if index == MAX_SEC_ISSUERS - 2:
                scope = capture_sec_refresh_scope(
                    session, company_ids=None, run_date=datetime.now(UTC).date(), request_id=None
                )
                assert scope is not None and len(scope["verified_cik_mappings"]) == MAX_SEC_ISSUERS
    with pytest.raises(SecRefreshScopeError, match="30 mapped-issuer"):
        _refresh(postgres_engine, domains=[FACTS])
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(ExternalIngestionRun)) == 0


@pytest.mark.integration
def test_filings_history_is_bounded_and_continues_with_retained_raw_ids(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(postgres_engine)
    calls: list[str] = []

    def download(url: str, _agent: str) -> bytes:
        calls.append(url)
        assert MAIN_SUBMISSIONS.payload is not None
        data = json.loads(MAIN_SUBMISSIONS.payload)
        if url.endswith(f"CIK{CIK}.json"):
            data["filings"]["files"] = [
                {"name": f"CIK{CIK}-submissions-{index:03d}.json"} for index in range(1, 8)
            ]
        return json.dumps(data).encode()

    monkeypatch.setattr("portfolio_api.source_documents._download_sec_json", download)
    first = _refresh(
        postgres_engine, domains=[FILINGS], company_ids={COMPANY_ID}, request_nonce=uuid4()
    )
    assert len(calls) == 6  # One recent submissions response and five historical files.
    assert first["status"] == "PARTIAL"
    assert first["domains"][0]["report"]["history_files_deferred"] == 2
    second = _refresh(
        postgres_engine, domains=[FILINGS], company_ids={COMPANY_ID}, request_nonce=uuid4()
    )
    assert len(calls) == 9
    report = second["domains"][0]["report"]
    assert (
        report["history_files_deferred"] == 0 and report["history_files_skipped_as_unchanged"] == 5
    )


@pytest.mark.integration
def test_scheduled_outage_retains_daily_scope_cooldown_and_retry_budget(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(postgres_engine)
    calls = _transports(monkeypatch)

    def unavailable(url: str, _agent: str) -> bytes:
        calls.append(url)
        assert f"CIK{CIK}" in url
        raise URLError("Synthetic outage")

    monkeypatch.setattr("portfolio_api.reported_fundamentals._download_sec_json", unavailable)
    now = _scheduled_clock(monkeypatch)
    result = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now)
    assert result["status"] == "FAILED" and len(calls) == 3
    assert result["retry_after_seconds"] == 900
    with Session(postgres_engine) as session, session.begin():
        record_cik_mapping(
            session,
            source.watchlist_company_id,
            "0000000002",
            "Watchlist Synthetic Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=2",
        )
    cooling = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now + timedelta(seconds=1))
    assert cooling["idempotent_reuse"] and len(calls) == 3
    for offset in (16, 32):
        _run_sec_domain(postgres_engine, SETTINGS, FACTS, now + timedelta(minutes=offset))
    assert len(calls) == 9
    exhausted = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now + timedelta(minutes=48))
    assert exhausted["idempotent_reuse"] and "retry_after_seconds" not in exhausted
    assert len(calls) == 9
    with Session(postgres_engine) as session:
        runs = list(session.scalars(select(ExternalIngestionRun)))
        assert len(runs) == 3 and all(row.request_scope == runs[0].request_scope for row in runs)


@pytest.mark.integration
def test_overlapping_same_manual_request_has_one_provider_cycle(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(postgres_engine)
    entered, release = Event(), Event()
    calls: list[str] = []

    def download(url: str, _agent: str) -> bytes:
        calls.append(url)
        entered.set()
        assert release.wait(15)
        payload = _facts_record().payload
        assert payload is not None
        return payload

    monkeypatch.setattr("portfolio_api.reported_fundamentals._download_sec_json", download)
    request_id = uuid4()
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(
            _refresh,
            postgres_engine,
            domains=[FACTS],
            company_ids={COMPANY_ID},
            request_nonce=request_id,
        )
        try:
            assert entered.wait(15)
            overlap = _refresh(
                postgres_engine, domains=[FACTS], company_ids={COMPANY_ID}, request_nonce=request_id
            )
            assert (
                overlap["domains"][0]["status"] == "RUNNING"
                and overlap["domains"][0]["idempotent_reuse"]
            )
        finally:
            release.set()
        assert first.result(timeout=15)["status"] == "PARTIAL"
    assert len(calls) == 1
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(ExternalIngestionRun)) == 1


@pytest.mark.integration
def test_existing_manual_queue_refreshes_unclassified_holdings_and_records_outcome(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(postgres_engine)
    calls = _transports(monkeypatch)
    with Session(postgres_engine) as session, session.begin():
        request, _ = create_job_request(
            session, s.OperationalJobRequestCreate(job_name="SEC_FUNDAMENTALS")
        )
        request_id = request.id
    result = process_manual_job_requests(postgres_engine, SETTINGS, request_id=request_id)
    assert result["status"] == "PARTIAL" and len(calls) == 1
    with Session(postgres_engine) as session:
        stored_request = session.get(OperationalJobRequest, request_id)
        attempt = session.scalar(select(OperationalJobAttempt))
        assert stored_request is not None and stored_request.status == "PARTIAL"
        assert attempt is not None and attempt.status == "PARTIAL"
        run = session.scalar(select(ExternalIngestionRun))
        assert run is not None and run.request_scope["operational_request_id"] == str(request_id)
        assert session.get(CurrentLifecycle, COMPANY_ID) is None
    repeated = process_manual_job_requests(postgres_engine, SETTINGS, request_id=request_id)
    assert repeated["status"] == "REQUEST_NOT_READY" and len(calls) == 1


@pytest.mark.integration
def test_scheduled_refresh_is_independent_of_manual_runs_and_new_utc_day(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(postgres_engine)
    calls = _transports(monkeypatch)
    now = _scheduled_clock(monkeypatch)
    _refresh(postgres_engine, domains=[FACTS], company_ids={COMPANY_ID}, request_nonce=uuid4())
    first = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now)
    assert first["status"] == "PARTIAL" and len(calls) == 2
    same_day = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now)
    assert same_day["idempotent_reuse"] and len(calls) == 2
    next_day = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now + timedelta(days=1))
    assert next_day["status"] == "PARTIAL" and len(calls) == 3
    with Session(postgres_engine) as session:
        dates = [
            row.request_scope["scope_date"] for row in session.scalars(select(ExternalIngestionRun))
        ]
        assert len(dates) == 3 and dates.count(now.date().isoformat()) == 2


@pytest.mark.integration
def test_outage_recovery_keeps_approved_issuers_and_rejects_replay_scope_replacement(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(postgres_engine)
    calls = _transports(monkeypatch)

    def unavailable(url: str, _agent: str) -> bytes:
        calls.append(url)
        raise URLError("Synthetic outage")

    monkeypatch.setattr("portfolio_api.reported_fundamentals._download_sec_json", unavailable)
    now = _scheduled_clock(monkeypatch)
    assert _run_sec_domain(postgres_engine, SETTINGS, FACTS, now)["status"] == "FAILED"
    with Session(postgres_engine) as session, session.begin():
        original = session.scalar(select(ExternalIngestionRun))
        assert original is not None
        run_id, scope = original.id, original.request_scope
        record_cik_mapping(
            session,
            source.watchlist_company_id,
            "0000000002",
            "Watchlist Synthetic Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=2",
        )
    restored_calls = _transports(monkeypatch)
    recovered = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now + timedelta(minutes=16))
    assert recovered["status"] == "PARTIAL" and len(restored_calls) == 1
    with Session(postgres_engine) as session:
        child = session.scalar(
            select(ExternalIngestionRun).where(ExternalIngestionRun.replay_of_run_id == run_id)
        )
        assert child is not None and child.request_scope == scope
        assert (
            session.scalar(select(func.count()).select_from(ReportedFundamentalObservation)) or 0
        ) > 0
    before = table_counts(postgres_engine)
    with pytest.raises(ValueError, match="recorded domain and scope"):
        _refresh(postgres_engine, domains=[FILINGS], replay_of_run_id=run_id, replay_scope=scope)
    altered = {**scope, "max_new_history_files": 1000}
    with pytest.raises(ValueError, match="recorded domain and scope"):
        _refresh(postgres_engine, domains=[FACTS], replay_of_run_id=run_id, replay_scope=altered)
    assert table_counts(postgres_engine) == before and len(restored_calls) == 1


@pytest.mark.integration
def test_interrupted_scheduled_claim_is_recorded_without_widening_or_refetching(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(postgres_engine)
    calls = _transports(monkeypatch)
    now = _scheduled_clock(monkeypatch)
    with Session(postgres_engine) as session:
        scope = capture_sec_refresh_scope(
            session, company_ids=None, run_date=now.date(), request_id=None
        )
        assert scope is not None
        claim = _claim_run(session, SEC_PROVIDER_ID, FACTS, scope, run_date=now.date())
        run = session.get(ExternalIngestionRun, claim.run_id)
        assert run is not None
        run.started_at = run.last_attempt_started_at = now - timedelta(hours=5)
        run.attempt_count = 1
        session.commit()
    result = _run_sec_domain(postgres_engine, SETTINGS, FACTS, now)
    assert result["status"] == "FAILED" and not calls
    with Session(postgres_engine) as session:
        attempt = session.scalar(select(ExternalIngestionAttempt))
        assert attempt is not None and attempt.failure_code == "WORKER_INTERRUPTED"
        run = session.get(ExternalIngestionRun, claim.run_id)
        assert run is not None and run.request_scope == scope


@pytest.mark.integration
def test_identity_is_revalidated_between_transport_attempts(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(postgres_engine)
    calls: list[str] = []

    def changed_during_outage(url: str, _agent: str) -> bytes:
        calls.append(url)
        with postgres_engine.begin() as connection:
            connection.execute(
                update(CompanyProviderIdentifier)
                .where(CompanyProviderIdentifier.company_id == COMPANY_ID)
                .values(provider_company_name="Changed during retry")
            )
        raise URLError("Synthetic outage")

    monkeypatch.setattr(
        "portfolio_api.reported_fundamentals._download_sec_json", changed_during_outage
    )
    monkeypatch.setattr("portfolio_api.external_ingestion.time.sleep", lambda _seconds: None)
    result = _refresh(
        postgres_engine, domains=[FACTS], company_ids={COMPANY_ID}, request_nonce=uuid4()
    )
    assert result["status"] == "BLOCKED" and len(calls) == 1
    assert result["domains"][0]["failure_code"] == "SEC_SCOPE_INVALID"
    with Session(postgres_engine) as session:
        run = session.scalar(select(ExternalIngestionRun))
        assert run is not None and run.attempt_count == 2
        assert session.scalar(select(func.count()).select_from(ReportedFundamentalObservation)) == 0
