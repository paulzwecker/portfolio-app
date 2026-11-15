"""Synthetic adapter tests; genuine provider values remain outside Git."""

import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.consensus_estimates import persist_provider_response
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    ConsensusEstimateBatch,
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
    ExternalRawPayload,
)
from portfolio_api.domain.queries import company_consensus_estimates
from portfolio_api.eodhd_consensus import (
    CURRENCY_BASIS_REASON,
    EODHD_CONSENSUS_PROVIDER_ID,
    EODHD_CONSENSUS_RECORD_ID,
    EODHD_CONSENSUS_SCHEMA_VERSION,
    EODHD_CONSENSUS_URL,
    EPS_BASIS_REASON,
    EodhdConsensusNormalizer,
    EodhdConsensusProvider,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.settings import Settings

CAPTURED = datetime(2026, 11, 14, 12, tzinfo=UTC)


def mapping() -> ConsensusEstimateProviderMapping:
    return ConsensusEstimateProviderMapping(
        id=uuid4(),
        company_id=uuid4(),
        listing_id=uuid4(),
        provider_id=EODHD_CONSENSUS_PROVIDER_ID,
        provider_symbol="AMZN.US",
        role="PRIMARY",
        priority=10,
        currency="USD",
        evidence_source="https://example.test/verified-issuer",
        currency_evidence_source="https://example.test/verified-reporting-currency",
        effective_from=CAPTURED - timedelta(days=1),
        recorded_at=CAPTURED - timedelta(days=1),
        actor="IMPORT",
    )


def payload() -> dict[str, Any]:
    def row(kind: str) -> dict[str, Any]:
        return {
            "date": "2026-12-31",
            "type": kind,
            "period": "0q" if kind == "quarterly" else "0y",
            "fiscalQuarter": "Q4",
            "revenueEstimateAvg": "100.25",
            "revenueEstimateLow": "90.25",
            "revenueEstimateHigh": "110.25",
            "revenueEstimateNumberOfAnalysts": "12",
            "earningsEstimateAvg": "0",
            "earningsEstimateLow": "-1",
            "earningsEstimateHigh": "1",
            "earningsEstimateNumberOfAnalysts": "11",
            "epsTrend7daysAgo": "99",
            "epsTrend90daysAgo": "101",
        }

    return {
        "General": {
            "Code": "AMZN",
            "PrimaryTicker": "AMZN.US",
            "Exchange": "NASDAQ",
            "Name": "Amazon.com Inc",
            "CurrencyCode": "USD",
            "Type": "Common Stock",
            "CIK": "0001018724",
            "FiscalYearEnd": "December",
            "IsDelisted": False,
        },
        "Earnings::Trend": {
            "Annual": {"2026-12-31": row("yearly")},
            "Quarterly": {"2026-12-31": row("quarterly")},
        },
    }


def record(data: dict[str, Any], at: datetime = CAPTURED) -> RawProviderRecord:
    body = json.dumps(data).encode()
    return RawProviderRecord(
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
        provider_id=EODHD_CONSENSUS_PROVIDER_ID,
        provider_schema_version=EODHD_CONSENSUS_SCHEMA_VERSION,
        source_record_id=EODHD_CONSENSUS_RECORD_ID,
        source_url=EODHD_CONSENSUS_URL,
        media_type="application/json",
        retrieved_at=at,
        payload=body,
        payload_sha256=hashlib.sha256(body).hexdigest(),
    )


def test_exact_periods_units_zero_eps_and_accounting_disclosure() -> None:
    result = EodhdConsensusNormalizer(mapping()).normalize(record(payload()))
    assert result.disposition == "ACCEPTED"
    assert result.observation is not None and len(result.observation) == 4
    assert {x.forecast_period for x in result.observation} == {"FY2026", "FY2026 Q4"}
    assert len({x.source_record_id for x in result.observation}) == 4
    for observation in result.observation:
        assert observation.currency == "USD"
        assert observation.observed_at == CAPTURED
        assert observation.snapshot_date == CAPTURED.date()
        assert observation.period_end == date(2026, 12, 31)
        assert observation.source_ref == EODHD_CONSENSUS_URL
        assert CURRENCY_BASIS_REASON in (observation.quality_reason or "")
        if observation.metric == "EPS":
            assert observation.value == 0
            assert observation.unit == "CURRENCY_PER_SHARE"
            assert observation.data_quality == "DATA_CHECK"
            assert EPS_BASIS_REASON in (observation.quality_reason or "")
        else:
            assert observation.value == Decimal("100.25")
            assert observation.unit == "CURRENCY"
            assert observation.data_quality == "PASS"
            assert observation.analyst_count == 12


@pytest.mark.parametrize(
    "field,value",
    [
        ("CurrencyCode", "EUR"),
        ("CIK", "0000000001"),
        ("Exchange", "NYSE"),
        ("Name", "Different issuer"),
        ("FiscalYearEnd", "June"),
        ("IsDelisted", True),
    ],
)
def test_identity_or_reporting_currency_drift_rejects_entire_response(
    field: str, value: object
) -> None:
    data = payload()
    data["General"][field] = value
    result = EodhdConsensusNormalizer(mapping()).normalize(record(data))
    assert result.disposition == "REJECTED"
    assert result.observation is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("revenueEstimateAvg", "NaN"),
        ("revenueEstimateAvg", "Infinity"),
        ("revenueEstimateAvg", True),
        ("revenueEstimateAvg", "-1"),
        ("revenueEstimateAvg", "1e27"),
        ("revenueEstimateAvg", "0.1234567890123"),
        ("revenueEstimateNumberOfAnalysts", "1.5"),
        ("revenueEstimateNumberOfAnalysts", "0"),
        ("revenueEstimateLow", "101"),
        ("revenueEstimateHigh", "99"),
    ],
)
def test_invalid_numeric_or_coverage_does_not_enter_canonical_values(
    field: str, value: object
) -> None:
    data = payload()
    data["Earnings::Trend"]["Annual"]["2026-12-31"][field] = value
    result = EodhdConsensusNormalizer(mapping()).normalize(record(data))
    assert result.observation is not None
    assert not any(x.metric == "REVENUE" and x.period_type == "ANNUAL" for x in result.observation)
    assert any(x.code == "INVALID_ESTIMATE_VALUE" for x in result.issues)


def test_missing_values_stay_missing_and_partial_coverage_remains_explicit() -> None:
    data = payload()
    annual = data["Earnings::Trend"]["Annual"]["2026-12-31"]
    annual.update(
        revenueEstimateHigh=None, revenueEstimateNumberOfAnalysts=None, earningsEstimateAvg=None
    )
    result = EodhdConsensusNormalizer(mapping()).normalize(record(data))
    assert result.observation is not None and len(result.observation) == 3
    revenue = next(x for x in result.observation if x.period_type == "ANNUAL")
    assert revenue.high_value is None and revenue.analyst_count is None
    assert revenue.data_quality == "DATA_CHECK"
    assert "incomplete" in (revenue.quality_reason or "")


def test_ended_rows_and_relative_trend_fields_are_not_historic_snapshots() -> None:
    data = payload()
    old = deepcopy(data["Earnings::Trend"]["Annual"]["2026-12-31"])
    old["date"] = "2025-12-31"
    data["Earnings::Trend"]["Annual"]["2025-12-31"] = old
    result = EodhdConsensusNormalizer(mapping()).normalize(record(data))
    assert result.observation is not None and len(result.observation) == 4
    assert {x.snapshot_date for x in result.observation} == {CAPTURED.date()}
    assert not any(x.value in {99, 101} for x in result.observation)
    assert any(x.code == "NON_FORWARD_PERIOD" for x in result.issues)


def test_fiscal_quarter_and_nested_shape_validation() -> None:
    data = payload()
    data["Earnings"] = {"Trend": data.pop("Earnings::Trend")}
    normalizer = EodhdConsensusNormalizer(mapping())
    assert len(normalizer.normalize(record(data)).observation or ()) == 4
    data["Earnings"]["Trend"]["Quarterly"]["2026-12-31"]["fiscalQuarter"] = "Q1"
    result = normalizer.normalize(record(data))
    assert result.observation is not None and len(result.observation) == 2
    assert any(x.code == "INVALID_PERIOD_IDENTITY" for x in result.issues)


def test_transport_fixed_request_and_runtime_guard_even_after_model_copy() -> None:
    mapped = mapping()
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        return json.dumps(payload()).encode()

    provider = EodhdConsensusProvider(
        Settings(_env_file=None),
        mapped,
        transport=transport,
        clock=lambda: CAPTURED,
    )
    query = ProviderQuery(
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
        subjects=(CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=mapped.company_id),),
        requested_at=CAPTURED,
    )
    result = asyncio.run(provider.fetch(query))
    assert calls == [EODHD_CONSENSUS_URL]
    assert result[0].retrieved_at == CAPTURED
    with pytest.raises(ValueError, match="current snapshots"):
        asyncio.run(provider.fetch(query.model_copy(update={"start_date": date(2020, 1, 1)})))
    provider.settings = provider.settings.model_copy(update={"app_env": "production"})
    with pytest.raises(ValueError, match="isolated-only"):
        asyncio.run(provider.fetch(query))
    assert len(calls) == 1
    with pytest.raises(ValueError, match="isolated-only"):
        EodhdConsensusProvider(
            Settings(_env_file=None).model_copy(
                update={"database_target_environment": "production"}
            ),
            mapped,
        )


@pytest.mark.integration
def test_persistence_raw_identity_replay_revisions_and_knowledge_cutoff(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = CAPTURED
    monkeypatch.setattr("portfolio_api.consensus_estimates.now", lambda: at + timedelta(seconds=1))
    with Session(postgres_engine) as session:
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
        mapped = mapping()
        mapped.company_id, mapped.listing_id = company.id, listing.id
        session.add(mapped)
        session.flush()
        normalizer = EodhdConsensusNormalizer(mapped)
        first_record = record(payload(), at)
        first = persist_provider_response(session, first_record, mapped, normalizer=normalizer)
        session.commit()
        assert first["facts_inserted"] == 4
        duplicate = persist_provider_response(session, first_record, mapped, normalizer=normalizer)
        assert duplicate["status"] == "ALREADY_IMPORTED"
        at += timedelta(minutes=5)
        changed = payload()
        changed["Earnings::Trend"]["Annual"]["2026-12-31"]["revenueEstimateAvg"] = "105.25"
        persist_provider_response(session, record(changed, at), mapped, normalizer=normalizer)
        session.commit()
        assert session.scalar(select(func.count()).select_from(ConsensusEstimateBatch)) == 2
        assert session.scalar(select(func.count()).select_from(ExternalRawPayload)) == 2
        assert session.scalar(select(func.count()).select_from(ConsensusEstimateObservation)) == 8
        revised = session.scalar(
            select(ConsensusEstimateObservation).where(
                ConsensusEstimateObservation.revision_context == "REVISED"
            )
        )
        assert revised is not None and revised.value == Decimal("105.25")
        assert revised.supersedes_observation_id is not None
        assert revised.provider_id == EODHD_CONSENSUS_PROVIDER_ID
        before = company_consensus_estimates(
            session, company.id, known_at=CAPTURED - timedelta(seconds=1)
        )
        assert before.providers[0].observation_count == 0
        then = company_consensus_estimates(
            session, company.id, known_at=CAPTURED + timedelta(seconds=2)
        )
        assert then.providers[0].observation_count == 4
        latest = company_consensus_estimates(session, company.id)
        assert latest.providers[0].observation_count == 8
        raw = session.scalar(
            select(ExternalRawPayload).where(
                ExternalRawPayload.payload_sha256 == first_record.payload_sha256
            )
        )
        assert raw is not None and raw.payload_bytes == first_record.payload
