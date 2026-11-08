"""Held-company SEC admission preserves lifecycle, evidence and operational guards."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_fundamentals_bootstrap import COMPANY_ID, RETRIEVED_AT
from test_fundamentals_portfolio_scope import _set_lifecycle, _source
from test_sec_incremental_refresh import _transports

from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Actor,
    CurrentLifecycle,
    HoldingPosition,
    HoldingSnapshot,
    Listing,
    OperationalJobAttempt,
    OperationalJobRequest,
    Portfolio,
    Security,
)
from portfolio_api.manual_operations import (
    company_refresh_options,
    create_job_request,
    retry_job_request,
)
from portfolio_api.recurring_operations import process_manual_job_requests


@pytest.mark.integration
@pytest.mark.parametrize("lifecycle", [None, "CANDIDATE", "DROP"])
def test_verified_holdings_allow_only_sec_jobs_independently_of_lifecycle(
    postgres_engine: Engine, lifecycle: str | None
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        if lifecycle is not None:
            _set_lifecycle(session, COMPANY_ID, lifecycle)
        before = queries.overview(session, source.portfolio_id)
        options = company_refresh_options(session, COMPANY_ID)
        assert options.eligible_job_names == ["SEC_FUNDAMENTALS", "SEC_FILINGS"]
        assert (
            options.lifecycle == lifecycle and options.sec_eligibility_basis == "VERIFIED_HOLDING"
        )
        assert (
            options.portfolio_id == source.portfolio_id
            and options.holding_snapshot_id == source.snapshot_id
        )
        for name in ("SEC_FUNDAMENTALS", "SEC_FILINGS"):
            job, duplicate = create_job_request(
                session,
                s.OperationalJobRequestCreate(
                    job_name=name, scope_kind="COMPANY", company_id=COMPANY_ID
                ),
            )
            assert not duplicate and job.lifecycle == lifecycle
            assert job.scope_detail["selection_basis"] == "VERIFIED_HOLDING"
            assert job.scope_detail["holding_snapshot_id"] == str(source.snapshot_id)
            assert job.affected_domains == (
                ["REPORTED_FUNDAMENTALS"] if name == "SEC_FUNDAMENTALS" else ["SOURCE_DOCUMENTS"]
            )
        for name in ("COMPANY_REFRESH", "MARKET_DATA", "FX", "MARKET_AND_FX", "RESEARCH_REFRESH"):
            with pytest.raises(ValueError, match="Portfolio and Watchlist"):
                create_job_request(
                    session,
                    s.OperationalJobRequestCreate(
                        job_name=name, scope_kind="COMPANY", company_id=COMPANY_ID
                    ),
                )
        after = queries.overview(session, source.portfolio_id)
        assert before.snapshot == after.snapshot and before.target_revision == after.target_revision
        assert (session.get(CurrentLifecycle, COMPANY_ID) is None) == (lifecycle is None)


@pytest.mark.integration
def test_missing_zero_companyless_and_ambiguous_scope_cannot_supply_admission(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        zero_company = session.scalar(
            select(Security.company_id)
            .join(Listing, Listing.security_id == Security.id)
            .where(Listing.id == source.zero_listing_id)
        )
        assert zero_company is not None
        assert company_refresh_options(session, zero_company).eligible_job_names == []
        with pytest.raises(ValueError, match="No positive verified holding"):
            create_job_request(
                session,
                s.OperationalJobRequestCreate(
                    job_name="SEC_FILINGS", scope_kind="COMPANY", company_id=zero_company
                ),
            )
        with pytest.raises(LookupError, match="not found"):
            company_refresh_options(session, source.fund_listing_id)
        with pytest.raises(ValueError, match="not found"):
            create_job_request(
                session,
                s.OperationalJobRequestCreate(
                    job_name="SEC_FILINGS", scope_kind="COMPANY", company_id=uuid4()
                ),
            )
        session.add(Portfolio(name="Other synthetic portfolio", base_currency="EUR"))
        session.flush()
        options = company_refresh_options(session, COMPANY_ID)
        assert options.eligible_job_names == [] and "one canonical portfolio" in (
            options.sec_unavailable_reason or ""
        )
        # Existing explicit Watchlist rules remain usable with multiple portfolios.
        active = company_refresh_options(session, source.watchlist_company_id)
        assert active.eligible_job_names == ["COMPANY_REFRESH", "SEC_FUNDAMENTALS", "SEC_FILINGS"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "state", ["PARTIAL", "ZERO", "FUTURE", "FUTURE_RECORDED", "MISSING_QUANTITY"]
)
def test_only_current_complete_observed_positive_holdings_prove_eligibility(
    postgres_engine: Engine, state: str
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        if state == "MISSING_QUANTITY":
            session.execute(
                update(HoldingPosition)
                .where(
                    HoldingPosition.snapshot_id == source.snapshot_id,
                    HoldingPosition.listing_id == source.held_listing_id,
                )
                .values(quantity=None)
            )
        else:
            snapshot = services.record_holdings(
                session,
                source.portfolio_id,
                s.SnapshotCreate(
                    effective_at=datetime.now(UTC) - timedelta(seconds=1),
                    actor=Actor.IMPORT,
                    reason="Synthetic admission evidence",
                    completeness="PARTIAL" if state == "PARTIAL" else "COMPLETE",
                    positions=[
                        s.PositionInput(listing_id=source.held_listing_id, quantity=Decimal("0"))
                    ],
                ),
            )
            if state in {"FUTURE", "FUTURE_RECORDED"}:
                # Model a retained future record without weakening normal command validation.
                session.execute(
                    update(HoldingSnapshot)
                    .where(HoldingSnapshot.id == snapshot.id)
                    .values(
                        **{
                            "effective_at" if state == "FUTURE" else "recorded_at": datetime.now(
                                UTC
                            )
                            + timedelta(days=1)
                        }
                    )
                )
        options = company_refresh_options(session, COMPANY_ID)
        assert bool(options.eligible_job_names) == (state in {"FUTURE", "FUTURE_RECORDED"})
        if state in {"FUTURE", "FUTURE_RECORDED"}:
            assert options.holding_snapshot_id == source.snapshot_id
        else:
            assert (
                options.holding_snapshot_id is None and options.sec_unavailable_reason is not None
            )


@pytest.mark.integration
def test_sec_admission_deduplicates_and_retry_rechecks_current_holdings(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    now = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        value = s.OperationalJobRequestCreate(
            job_name="SEC_FILINGS", scope_kind="COMPANY", company_id=COMPANY_ID
        )
        first, _ = create_job_request(session, value, now_at=now)
        repeated, duplicate = create_job_request(session, value, now_at=now + timedelta(seconds=1))
        assert duplicate and repeated.id == first.id
        first.status = "PARTIAL"
        original_scope = dict(first.scope_detail)
        services.record_holdings(
            session,
            source.portfolio_id,
            s.SnapshotCreate(
                effective_at=RETRIEVED_AT + timedelta(days=1),
                actor=Actor.IMPORT,
                reason="Synthetic changed holding",
                completeness="COMPLETE",
                positions=[],
            ),
        )
        with pytest.raises(ValueError, match="No positive verified holding"):
            retry_job_request(session, first.id)
        assert first.scope_detail == original_scope
        assert len(list(session.scalars(select(OperationalJobRequest)))) == 1


@pytest.mark.integration
def test_scoped_requests_run_real_services_and_preserve_portfolio_state(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(postgres_engine)
    calls = _transports(monkeypatch)
    settings = fixture_settings().model_copy(
        update={
            "manual_operations_enabled": True,
            "sec_user_agent": "Synthetic App test@example.invalid",
        }
    )
    with Session(postgres_engine) as session:
        before = queries.overview(session, source.portfolio_id)
    with TestClient(fixture_application(postgres_engine, settings)) as client:
        options = client.get(f"/v1/companies/{COMPANY_ID}/refresh-options").json()
        assert (
            options["execution_mode"] == "OPERATOR"
            and options["sec_eligibility_basis"] == "VERIFIED_HOLDING"
        )
        for job in ("SEC_FUNDAMENTALS", "SEC_FILINGS"):
            response = client.post(
                "/v1/operations/job-requests",
                json={"job_name": job, "scope_kind": "COMPANY", "company_id": str(COMPANY_ID)},
            )
            assert response.status_code == 202
            request_id = UUID(response.json()["id"])
            outcome = process_manual_job_requests(postgres_engine, settings, request_id=request_id)
            assert outcome["status"] in {"SUCCEEDED", "PARTIAL"}
            assert client.get(f"/v1/operations/job-requests/{request_id}").json()["scope_detail"][
                "holding_snapshot_id"
            ] == str(source.snapshot_id)
        coverage = client.get(f"/v1/companies/{COMPANY_ID}/sec-coverage").json()
        assert (
            coverage["filings"]["record_count"] == 2
            and coverage["fundamentals"]["record_count"] > 0
        )
    with Session(postgres_engine) as session:
        after = queries.overview(session, source.portfolio_id)
        assert before.snapshot == after.snapshot and before.target_revision == after.target_revision
        assert session.get(CurrentLifecycle, COMPANY_ID) is None
    assert len(calls) == 2


@pytest.mark.integration
def test_unmapped_held_issuer_keeps_explicit_blocked_outcome_without_provider_access(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(postgres_engine)
    calls = _transports(monkeypatch)
    with Session(postgres_engine) as session, session.begin():
        before = queries.overview(session, source.portfolio_id)
        job, _ = create_job_request(
            session,
            s.OperationalJobRequestCreate(
                job_name="SEC_FILINGS", scope_kind="COMPANY", company_id=source.unmapped_company_id
            ),
        )
        request_id = job.id
    settings = fixture_settings().model_copy(
        update={"sec_user_agent": "Synthetic App test@example.invalid"}
    )
    result = process_manual_job_requests(postgres_engine, settings, request_id=request_id)
    assert result["status"] == "BLOCKED"
    assert calls == []
    with Session(postgres_engine) as session:
        stored_job = session.get(OperationalJobRequest, request_id)
        assert stored_job is not None and stored_job.status == "BLOCKED"
        assert (
            session.scalar(
                select(OperationalJobAttempt.id).where(
                    OperationalJobAttempt.request_id == request_id
                )
            )
            is not None
        )
        after = queries.overview(session, source.portfolio_id)
        assert before.snapshot == after.snapshot and before.target_revision == after.target_revision
        assert session.get(CurrentLifecycle, source.unmapped_company_id) is None


@pytest.mark.integration
def test_options_are_authenticated_read_only_and_disabled_execution_cannot_queue(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    before = table_counts(postgres_engine)
    with postgres_engine.connect() as connection:
        schema = str(connection.scalar(text("SELECT current_schema()")))
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-access")}
    )
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            path = f"/v1/companies/{COMPANY_ID}/refresh-options"
            assert client.get(path).status_code == 401
            headers = {"x-api-access-token": "synthetic-access"}
            result = client.get(path, headers=headers)
            assert result.status_code == 200 and result.json()["execution_mode"] == "DISABLED"
            assert result.json()["holding_snapshot_id"] == str(source.snapshot_id)
            assert (
                client.get(f"/v1/companies/{uuid4()}/refresh-options", headers=headers).status_code
                == 404
            )
            blocked = client.post(
                "/v1/operations/job-requests",
                headers=headers,
                json={
                    "job_name": "SEC_FILINGS",
                    "scope_kind": "COMPANY",
                    "company_id": str(COMPANY_ID),
                },
            )
            assert blocked.status_code == 503
    finally:
        reader.dispose()
    assert table_counts(postgres_engine) == before
