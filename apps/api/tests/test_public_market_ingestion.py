"""Existing durable ingestion/operations with isolated official-FX adapters."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    ExternalIngestionRun,
    ExternalRawPayload,
    FxObservation,
    OperationalJobRequest,
)
from portfolio_api.ecb_reference import ECB_PROVIDER_ID, ECB_SCHEMA_VERSION, EcbReferenceProvider
from portfolio_api.external_data import (
    ExternalDataDomain,
    ProviderQuery,
    ProviderTransportError,
    RawProviderRecord,
)
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.manual_operations import create_job_request
from portfolio_api.recurring_operations import run_recurring_cycle
from portfolio_api.settings import Settings


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        fx_provider="ECB_REFERENCE",
        app_env="development",
        database_target_environment="development",
        recurring_operations_enabled=True,
        manual_operations_enabled=True,
    )


def _raw(
    currency: str, rows: list[tuple[str, str]], *, captured: datetime | None = None
) -> RawProviderRecord:
    text = (
        "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,"
        "OBS_VALUE,OBS_STATUS,UNIT,UNIT_MULT\n"
    )
    text += "".join(
        f"EXR.D.{currency}.EUR.SP00.A,D,{currency},EUR,SP00,A,{day},{rate},A,{currency},0\n"
        for day, rate in rows
    )
    body = text.encode()
    return RawProviderRecord(
        domain=ExternalDataDomain.FX,
        provider_id=ECB_PROVIDER_ID,
        provider_schema_version=ECB_SCHEMA_VERSION,
        source_record_id=f"FX:{currency}/EUR",
        media_type="text/csv",
        retrieved_at=captured or datetime.now(UTC),
        payload=body,
        payload_sha256=hashlib.sha256(body).hexdigest(),
    )


def _patch_source(monkeypatch: pytest.MonkeyPatch) -> list[ProviderQuery]:
    calls: list[ProviderQuery] = []

    async def fetch(
        _provider: EcbReferenceProvider, query: ProviderQuery
    ) -> list[RawProviderRecord]:
        calls.append(query)
        currency = query.subjects[0].base_currency
        assert currency in {"USD", "DKK"}
        assert query.start_date is not None and query.end_date is not None
        rows = [
            ("2026-11-09", "1.25" if currency == "USD" else "7.45"),
            ("2026-11-10", "1.28" if currency == "USD" else "7.46"),
        ]
        return [
            _raw(
                currency,
                [
                    (day, rate)
                    for day, rate in rows
                    if query.start_date <= date.fromisoformat(day) <= query.end_date
                ],
            )
        ]

    async def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ECB scope reached Yahoo")

    monkeypatch.setattr(EcbReferenceProvider, "fetch", fetch)
    monkeypatch.setattr("portfolio_api.yahoo_finance.YahooFinanceProvider.fetch", forbidden)
    return calls


@pytest.mark.integration
def test_ecb_scheduled_persistence_replay_incremental_and_provider_identity(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_source(monkeypatch)
    settings = _settings()
    options: dict[str, Any] = {
        "domains": [ExternalDataDomain.FX],
        "start_date": date(2026, 11, 9),
        "end_date": date(2026, 11, 9),
        "run_date": date(2026, 11, 9),
        "fx_pair_filter": {("USD", "EUR"), ("DKK", "EUR")},
    }
    with Session(postgres_engine) as session:
        initial = run_scheduled(session, settings, **options)
        session.commit()
        assert initial["status"] == "COMPLETE", initial
        assert session.scalar(select(func.count()).select_from(FxObservation)) == 2
        again = run_scheduled(session, settings, **options)
        assert again["domains"][0]["idempotent_reuse"]
        assert len(calls) == 2
        options.update(start_date=None, end_date=date(2026, 11, 10), run_date=date(2026, 11, 10))
        incremental = run_scheduled(session, settings, **options)
        session.commit()
        assert incremental["status"] == "COMPLETE", incremental
        assert len(calls) == 4
        assert calls[-1].start_date == date(2026, 11, 6)
        assert session.scalar(select(func.count()).select_from(FxObservation)) == 4
        assert set(session.scalars(select(FxObservation.provider))) == {ECB_PROVIDER_ID}
        assert set(session.scalars(select(ExternalIngestionRun.provider_id))) == {ECB_PROVIDER_ID}
        assert session.scalar(select(func.count()).select_from(ExternalRawPayload)) == 4
        usd = session.scalar(
            select(FxObservation).where(
                FxObservation.base_currency == "USD",
                FxObservation.effective_at == datetime(2026, 11, 10, tzinfo=UTC),
            )
        )
        assert usd is not None
        assert usd.rate == Decimal("0.78125000000000")


@pytest.mark.integration
def test_ecb_unavailable_pair_blocks_without_provider_fallback(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_source(monkeypatch)
    with Session(postgres_engine) as session:
        report = run_scheduled(
            session,
            _settings(),
            domains=[ExternalDataDomain.FX],
            fx_pair_filter={("GBP", "EUR")},
            end_date=date(2026, 11, 9),
        )
        assert report["status"] == "BLOCKED", report
        assert not calls
        assert session.scalar(select(func.count()).select_from(FxObservation)) == 0


@pytest.mark.integration
@pytest.mark.parametrize("retryable,expected_attempts", [(False, 1), (True, 3)])
def test_ecb_provider_failure_is_durable_and_not_success(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    retryable: bool,
    expected_attempts: int,
) -> None:
    _patch_source(monkeypatch)

    async def fail(*_args: object, **_kwargs: object) -> list[RawProviderRecord]:
        raise ProviderTransportError(
            ECB_PROVIDER_ID,
            "HTTP_503" if retryable else "HTTP_403",
            "ECB unavailable",
            retryable=retryable,
        )

    monkeypatch.setattr(EcbReferenceProvider, "fetch", fail)
    monkeypatch.setattr("portfolio_api.external_ingestion.time.sleep", lambda _delay: None)
    with Session(postgres_engine) as session:
        report = run_scheduled(
            session,
            _settings(),
            domains=[ExternalDataDomain.FX],
            fx_pair_filter={("USD", "EUR")},
            end_date=date(2026, 11, 9),
        )
        assert report["status"] == "FAILED", report
        assert report["domains"][0]["attempt_count"] == expected_attempts, json.dumps(report)
        assert report["domains"][0]["failure_code"] == ("HTTP_503" if retryable else "HTTP_403")
        assert session.scalar(select(func.count()).select_from(FxObservation)) == 0


@pytest.mark.integration
def test_manual_and_scheduled_fx_use_same_existing_path(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_source(monkeypatch)
    at = datetime(2026, 11, 11, 18, tzinfo=UTC)
    settings = _settings()
    with Session(postgres_engine) as session, session.begin():
        portfolio = services.create_portfolio(
            session, s.PortfolioCreate(name="FX fixture", base_currency="EUR")
        )
        services.record_holdings(
            session,
            portfolio.id,
            s.SnapshotCreate(
                effective_at=at,
                actor="IMPORT",
                source="FICTIONAL_FX_TEST",
                reason="Synthetic cash only",
                completeness="COMPLETE",
                positions=[],
                cash_positions=[s.CashInput(currency="USD", balance=Decimal("100"))],
            ),
        )
        request, _ = create_job_request(
            session, s.OperationalJobRequestCreate(job_name="FX"), now_at=at
        )
        request_id = request.id
    first = run_recurring_cycle(
        settings, engine=postgres_engine, now_at=at, public_market_only=True
    )
    assert first["status"] == "COMPLETE", first
    with Session(postgres_engine) as session:
        completed_request = session.get(OperationalJobRequest, request_id)
        assert completed_request is not None
        assert completed_request.status == "SUCCEEDED"
        assert session.scalar(select(func.count()).select_from(FxObservation)) == 2
    assert len(calls) == 2, "Manual and scheduled scopes each execute the same bounded provider"
    replay = run_recurring_cycle(
        settings, engine=postgres_engine, now_at=at + timedelta(minutes=1), public_market_only=True
    )
    assert replay["status"] == "COMPLETE"
    assert len(calls) == 2


@pytest.mark.parametrize("boundary", ["app_env", "database_target_environment"])
def test_demo_market_configuration_cannot_enable_production(boundary: str) -> None:
    with pytest.raises(ValueError, match="isolated-only"):
        if boundary == "app_env":
            Settings(_env_file=None, market_data_provider="EODHD_DEMO", app_env="production")
        else:
            Settings(
                _env_file=None,
                market_data_provider="EODHD_DEMO",
                database_target_environment="production",
            )


@pytest.mark.integration
@pytest.mark.source_data
def test_private_ecb_initial_incremental_canonical_readback(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = os.environ.get("ECB_REAL_CAPTURE_DIR")
    if not configured:
        pytest.skip("Set ECB_REAL_CAPTURE_DIR to the private reviewed official capture directory")
    root = Path(configured)
    captures = {
        False: [
            json.loads((root / "capture-manifest.json").read_text(encoding="utf-8-sig")),
            json.loads((root / "dkk-capture.json").read_text(encoding="utf-8-sig")),
        ],
        True: json.loads(
            (root / "incremental-capture-manifest.json").read_text(encoding="utf-8-sig")
        ),
    }
    current = False

    async def fetch(
        _provider: EcbReferenceProvider, query: ProviderQuery
    ) -> list[RawProviderRecord]:
        capture = next(
            item
            for item in captures[current]
            if item["currency"] == query.subjects[0].base_currency
        )
        body = Path(capture["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == capture["sha256"]
        return [
            RawProviderRecord(
                domain=ExternalDataDomain.FX,
                provider_id=ECB_PROVIDER_ID,
                provider_schema_version=ECB_SCHEMA_VERSION,
                source_record_id=f"FX:{capture['currency']}/EUR",
                source_url=capture["url"],
                media_type="text/csv",
                payload=body,
                payload_sha256=capture["sha256"],
                retrieved_at=datetime.fromisoformat(capture["retrieved_at"]),
            )
        ]

    monkeypatch.setattr(EcbReferenceProvider, "fetch", fetch)
    with Session(postgres_engine) as session:
        for phase, start, end, count in [
            (False, date(2025, 11, 10), date(2026, 11, 9), 510),
            (True, date(2026, 11, 5), date(2026, 11, 14), 518),
        ]:
            current = phase
            report = run_scheduled(
                session,
                _settings(),
                domains=[ExternalDataDomain.FX],
                start_date=start,
                end_date=end,
                run_date=end,
                fx_pair_filter={("USD", "EUR"), ("DKK", "EUR")},
            )
            session.commit()
            assert report["status"] == "COMPLETE", report
            assert session.scalar(select(func.count()).select_from(FxObservation)) == count
        for currency, source in [("USD", "1.1052"), ("DKK", "7.4756")]:
            observation = session.scalar(
                select(FxObservation)
                .where(FxObservation.base_currency == currency)
                .order_by(FxObservation.effective_at.desc())
                .limit(1)
            )
            assert observation is not None
            assert observation.effective_at.date() == date(2026, 11, 13)
            assert abs(observation.rate * Decimal(source) - 1) < Decimal("1e-12")
        assert session.scalar(select(func.count()).select_from(ExternalRawPayload)) == 4
