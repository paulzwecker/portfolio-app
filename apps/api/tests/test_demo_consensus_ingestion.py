"""Synthetic PostgreSQL checks for the bounded optional demo dispatch."""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_eodhd_consensus import CAPTURED, mapping, payload, record

from portfolio_api.consensus_estimates import persist_provider_response
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
    ExternalIngestionAttempt,
    ExternalIngestionRun,
    ExternalRawPayload,
    Listing,
)
from portfolio_api.eodhd_consensus import (
    EODHD_CONSENSUS_PROVIDER_ID,
    EodhdConsensusNormalizer,
    EodhdConsensusProvider,
)
from portfolio_api.external_data import ExternalDataDomain, ProviderQuery, RawProviderRecord
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.financial_statements import company_financial_statements
from portfolio_api.settings import Settings


def _seed(session: Session, *, mapped: bool = True) -> tuple[UUID, UUID]:
    company = services.create_company(
        session, s.CompanyCreate(name="Amazon", reporting_currency="USD")
    )
    security = services.create_security(
        session,
        company.id,
        s.SecurityCreate(name="Amazon common stock", security_type="COMMON_STOCK"),
    )
    listing = services.create_listing(
        session, security.id, s.ListingCreate(ticker="AMZN", venue="NASDAQ", currency="USD")
    )
    services.transition_lifecycle(
        session,
        company.id,
        s.LifecycleChange(
            new_state="PORTFOLIO",
            expected_event_id=None,
            actor="IMPORT",
            reason="Synthetic isolated source eligibility",
            source="synthetic-demo-test",
            effective_at=CAPTURED - timedelta(days=60),
        ),
    )
    if mapped:
        identity = mapping()
        identity.company_id, identity.listing_id = company.id, listing.id
        identity.effective_from = CAPTURED - timedelta(days=60)
        identity.recorded_at = CAPTURED - timedelta(days=60)
        session.add(identity)
    session.commit()
    return company.id, listing.id


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="development",
        database_target_environment="development",
        consensus_provider=EODHD_CONSENSUS_PROVIDER_ID,
    )


def _source(monkeypatch: pytest.MonkeyPatch) -> list[ProviderQuery]:
    calls: list[ProviderQuery] = []

    async def fetch(
        _provider: EodhdConsensusProvider, query: ProviderQuery
    ) -> list[RawProviderRecord]:
        calls.append(query)
        return [record(payload())]

    async def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Demo dispatch attempted an unrelated provider")

    monkeypatch.setattr(EodhdConsensusProvider, "fetch", fetch)
    monkeypatch.setattr("portfolio_api.consensus_estimates.FmpConsensusProvider.fetch", forbidden)
    return calls


def _run(session: Session, settings: Settings | None = None, **kwargs: Any) -> dict[str, Any]:
    return run_scheduled(
        session,
        settings or _settings(),
        domains=[ExternalDataDomain.CONSENSUS_ESTIMATES],
        run_date=CAPTURED.date(),
        **kwargs,
    )


@pytest.mark.integration
def test_no_mapping_blocks_without_any_fetch(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _source(monkeypatch)
    with Session(postgres_engine) as session:
        _seed(session, mapped=False)
        result = _run(session)
        session.commit()
        assert result["status"] == "BLOCKED"
        run = session.scalar(select(ExternalIngestionRun))
        assert run is not None and run.failure_code == "NO_DEMO_MAPPING"
        assert run.attempt_count == 1
        assert calls == []
        assert session.scalar(select(func.count()).select_from(ExternalRawPayload)) == 0


@pytest.mark.integration
def test_one_mapped_issuer_records_partial_receipt_and_same_day_reuse(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _source(monkeypatch)
    with Session(postgres_engine) as session:
        company_id, _ = _seed(session)
        first = _run(session)
        session.commit()
        assert first["status"] == "PARTIAL", first
        run = session.scalar(select(ExternalIngestionRun))
        assert run is not None and run.provider_id == EODHD_CONSENSUS_PROVIDER_ID
        assert run.attempt_count == 1 and run.status == "PARTIAL"
        assert run.finished_at is not None
        assert run.request_scope["company_ids"] == [str(company_id)]
        assert run.report["normalized_estimate_count"] == 4
        assert run.report["data_check_estimate_count"] == 2
        assert session.scalar(select(func.count()).select_from(ExternalIngestionAttempt)) == 1
        repeat = _run(session)
        assert repeat["domains"][0]["idempotent_reuse"]
        assert len(calls) == 1
        assert session.scalar(select(func.count()).select_from(ConsensusEstimateObservation)) == 4
        assert session.scalar(select(func.count()).select_from(ExternalRawPayload)) == 1


@pytest.mark.integration
@pytest.mark.parametrize("change", ["company", "reporting_currency", "listing_currency", "ticker"])
def test_canonical_identity_mismatch_stops_before_fetch(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    calls = _source(monkeypatch)
    with Session(postgres_engine) as session:
        company_id, listing_id = _seed(session)
        company, listing = session.get(Company, company_id), session.get(Listing, listing_id)
        assert company is not None and listing is not None
        if change == "company":
            company.name = "Different issuer"
        elif change == "reporting_currency":
            company.reporting_currency = "EUR"
        elif change == "listing_currency":
            listing.currency = "EUR"
        else:
            listing.ticker = "OTHER"
        session.commit()
        with pytest.raises(ValueError, match="reviewed Amazon"):
            _run(session)
        assert calls == []
        assert session.scalar(select(func.count()).select_from(ConsensusEstimateObservation)) == 0


@pytest.mark.integration
@pytest.mark.parametrize("boundary", ["app_env", "database_target_environment"])
def test_model_copy_cannot_bypass_production_runtime_guard(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    calls = _source(monkeypatch)
    with Session(postgres_engine) as session:
        _seed(session)
        settings = _settings().model_copy(update={boundary: "production"})
        with pytest.raises(ValueError, match="cannot execute against production"):
            _run(session, settings)
        assert calls == []
        assert session.scalar(select(func.count()).select_from(ExternalIngestionRun)) == 0


@pytest.mark.integration
@pytest.mark.parametrize("original_provider", ["fmp_estimates", "eodhd_demo_estimates"])
def test_replay_cannot_change_provider_in_either_direction(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    original_provider: str,
) -> None:
    calls = _source(monkeypatch)
    with Session(postgres_engine) as session:
        _seed(session)
        settings = _settings().model_copy(update={"consensus_provider": original_provider})
        _run(session, settings)
        session.commit()
        original = session.scalar(select(ExternalIngestionRun))
        assert original is not None
        before = len(calls)
        alternative = (
            "fmp_estimates"
            if original_provider == EODHD_CONSENSUS_PROVIDER_ID
            else EODHD_CONSENSUS_PROVIDER_ID
        )
        with pytest.raises(ValueError, match="cannot replace its provider"):
            _run(
                session,
                settings.model_copy(update={"consensus_provider": alternative}),
                replay_of_run_id=original.id,
                replay_scope=original.request_scope,
            )
        assert len(calls) == before
        assert session.scalar(select(func.count()).select_from(ExternalIngestionRun)) == 1


@pytest.mark.integration
@pytest.mark.parametrize("revenue_age_days,expected_status", [(1, "AVAILABLE"), (30, "DATA_CHECK")])
def test_freshness_is_specific_to_each_estimate_not_neighbor_quality(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    revenue_age_days: int,
    expected_status: str,
) -> None:
    with Session(postgres_engine) as session:
        company_id, _ = _seed(session)
        identity = session.scalar(select(ConsensusEstimateProviderMapping))
        assert identity is not None
        normalizer = EodhdConsensusNormalizer(identity)
        revenue = payload()
        eps = payload()
        for group in ("Annual", "Quarterly"):
            revenue["Earnings::Trend"][group]["2026-12-31"]["earningsEstimateAvg"] = None
            eps["Earnings::Trend"][group]["2026-12-31"]["revenueEstimateAvg"] = None
        at = CAPTURED - timedelta(days=revenue_age_days)
        monkeypatch.setattr(
            "portfolio_api.consensus_estimates.now", lambda: at + timedelta(seconds=1)
        )
        persist_provider_response(session, record(revenue, at), identity, normalizer=normalizer)
        session.commit()
        at = CAPTURED
        persist_provider_response(session, record(eps, at), identity, normalizer=normalizer)
        session.commit()
        result = company_financial_statements(session, company_id, as_of=CAPTURED.date())
        assert result.consensus.providers[0].freshness == "DATA_CHECK"
        row = next(x for x in result.rows if x.source_kind == "CONSENSUS" and x.metric == "REVENUE")
        assert len(row.cells) == 1
        assert row.cells[0].status == expected_status
        eps_row = next(x for x in result.rows if x.source_kind == "CONSENSUS" and x.metric == "EPS")
        assert eps_row.cells[0].status == "DATA_CHECK"
        if revenue_age_days > 14:
            assert "STALE" in (row.cells[0].reason or "")
