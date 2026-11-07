"""Synthetic coverage for the bounded, frozen cloud market correction path."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import (
    _crosswalk,
    _fx_payload,
    _listing_payload,
    _mapping,
    _seed_canonical_scope,
)

from portfolio_api.database import Base
from portfolio_api.domain import queries, schemas, services
from portfolio_api.domain.models import (
    Actor,
    Company,
    CurrentLifecycle,
    ExternalIngestionRun,
    LifecycleEvent,
    Listing,
    Portfolio,
)
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.main import create_app
from portfolio_api.market_data_bootstrap import MarketDataBootstrapError
from portfolio_api.market_data_startup import run_cloud_incremental_refresh, run_startup_refresh
from portfolio_api.settings import Settings
from portfolio_api.yahoo_finance import FX_SYMBOLS, YahooFinanceProvider, YahooListingCrosswalk


@pytest.fixture
def market_scope(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, _digest = _crosswalk(_mapping(company.id, security.id, listing.id))
    path = tmp_path / "synthetic-crosswalk.json"
    path.write_text(crosswalk.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("portfolio_api.market_data_startup.CROSSWALK_PATH", path)
    return path


def table_counts(engine: Engine) -> dict[str, int | None]:
    with Session(engine) as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


@pytest.mark.integration
def test_cloud_correction_pins_ninety_day_scope_and_required_fx_without_writes(
    postgres_engine: Engine,
    market_scope: Path,
) -> None:
    settings = Settings(
        _env_file=None, database_url=None, database_target_environment="development"
    )
    before = table_counts(postgres_engine)
    scheduled = Mock(return_value={"status": "COMPLETE"})
    with (
        patch("portfolio_api.market_data_startup.run_scheduled", scheduled),
        Session(postgres_engine) as session,
    ):
        result = run_cloud_incremental_refresh(session, settings, datetime.now(UTC))
    assert result["status"] == "COMPLETE"
    assert result["subject_count"] == 2
    assert result["provider_http_attempt_upper_bound"] == 8
    arguments = scheduled.call_args.kwargs
    assert (arguments["end_date"] - arguments["start_date"]).days + 1 == 90
    assert arguments["listing_key_filter"] == {("NASDAQ", "SYNTH")}
    assert arguments["fx_pair_filter"] == {("USD", "EUR")}
    frozen, digest = arguments["frozen_yahoo_crosswalk"]
    assert frozen.mappings[0].ticker == "SYNTH"
    assert len(digest) == 64
    assert before == table_counts(postgres_engine)


@pytest.mark.integration
@pytest.mark.parametrize(
    "problem", ["identity", "budget", "mapping", "target", "baseline", "fx_mapping"]
)
def test_cloud_scope_fails_before_claims_or_provider_calls(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    import json

    payload = json.loads(market_scope.read_text(encoding="utf-8"))
    if problem == "identity":
        payload["mappings"][0]["canonical_company_id"] = str(uuid4())
    elif problem == "mapping":
        payload["mappings"] = []
    elif problem == "budget":
        monkeypatch.setattr("portfolio_api.market_data_startup.CLOUD_MAX_SUBJECTS", 1)
    elif problem == "fx_mapping":
        monkeypatch.delitem(FX_SYMBOLS, ("USD", "EUR"))
    market_scope.write_text(json.dumps(payload), encoding="utf-8")
    settings = Settings(
        _env_file=None,
        database_url=None,
        database_target_environment=(
            None
            if problem == "target"
            else "production"
            if problem == "baseline"
            else "development"
        ),
    )
    before = table_counts(postgres_engine)
    with (
        patch("portfolio_api.market_data_startup.run_scheduled") as scheduled,
        Session(postgres_engine) as session,
    ):
        result = run_cloud_incremental_refresh(session, settings, datetime.now(UTC))
    assert result["status"] == "BLOCKED"
    scheduled.assert_not_called()
    assert before == table_counts(postgres_engine)


def test_pinned_replay_refuses_changed_mapping_bytes_before_claims(tmp_path: Path) -> None:
    path = tmp_path / "changed-mapping.json"
    path.write_text("{}", encoding="utf-8")
    with (
        patch("portfolio_api.external_ingestion._claim_run") as claim,
        pytest.raises(ValueError, match="crosswalk changed"),
    ):
        run_scheduled(
            cast(Session, None),
            Settings(_env_file=None, database_url=None),
            replay_scope={"crosswalk_sha256": "a" * 64},
            yahoo_crosswalk_path=path,
        )
    claim.assert_not_called()


@pytest.mark.parametrize("replacement", [{"listing_key_filter": set()}, {"fx_pair_filter": set()}])
def test_frozen_replay_filters_cannot_be_replaced(replacement: dict[str, Any]) -> None:
    with (
        patch("portfolio_api.external_ingestion._claim_run") as claim,
        pytest.raises(ValueError, match="cannot replace"),
    ):
        run_scheduled(
            cast(Session, None),
            Settings(_env_file=None, database_url=None),
            replay_scope={"crosswalk_sha256": "a" * 64},
            **replacement,
        )
    claim.assert_not_called()


@pytest.mark.parametrize(
    "replacement",
    [
        {"domains": [ExternalDataDomain.REPORTED_FUNDAMENTALS]},
        {"request_nonce": uuid4()},
        {"replay_of_run_id": uuid4()},
        {"frozen_yahoo_crosswalk": None},
        {"listing_key_filter": None},
        {"fx_pair_filter": None},
    ],
)
def test_cloud_recovery_cannot_escape_its_original_yahoo_scope(
    replacement: dict[str, Any],
) -> None:
    crosswalk = _crosswalk(_mapping(uuid4(), uuid4(), uuid4()))
    arguments = {
        "domains": [ExternalDataDomain.MARKET_DATA],
        "frozen_yahoo_crosswalk": crosswalk,
        "listing_key_filter": set(),
        "fx_pair_filter": set(),
        **replacement,
    }
    with (
        patch("portfolio_api.external_ingestion._claim_run") as claim,
        pytest.raises(ValueError, match="original frozen Yahoo scope"),
    ):
        run_scheduled(
            cast(Session, None),
            Settings(_env_file=None, database_url=None),
            retry_failed=True,
            **arguments,
        )
    claim.assert_not_called()


def source_payload(symbol: str, at: datetime) -> bytes:
    payload = json.loads(_listing_payload() if symbol == "SYNTH" else _fx_payload())
    result = payload["chart"]["result"][0]
    shift = (at.date() - timedelta(days=1) - date(2026, 10, 5)).days * 86400
    result["timestamp"] = [stamp + shift for stamp in result["timestamp"]]
    result["meta"]["regularMarketTime"] = int((at - timedelta(minutes=1)).timestamp())
    result["events"] = {}
    return json.dumps(payload).encode()


@pytest.mark.integration
@pytest.mark.parametrize("fx_outage", [False, True])
def test_actual_cloud_import_drives_portfolio_and_operations_without_rewriting_ownership(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
    fx_outage: bool,
) -> None:
    at = datetime.now(UTC) - timedelta(days=1)
    settings = Settings(
        _env_file=None, database_url=None, database_target_environment="development"
    )
    with Session(postgres_engine) as session, session.begin():
        portfolio = session.scalars(select(Portfolio)).one()
        company = session.scalars(select(Company)).one()
        listing = session.scalars(select(Listing)).one()
        snapshot = services.record_holdings(
            session,
            portfolio.id,
            schemas.SnapshotCreate(
                effective_at=at - timedelta(days=2),
                actor=Actor.IMPORT,
                reason="Synthetic cloud valuation",
                source="synthetic-cloud-test",
                completeness="COMPLETE",
                positions=[schemas.PositionInput(listing_id=listing.id, quantity=Decimal("2.5"))],
                cash_positions=[
                    schemas.CashInput(currency="EUR", balance=Decimal("10")),
                    schemas.CashInput(currency="USD", balance=Decimal("5")),
                ],
            ),
        )
        target = services.create_targets(
            session,
            portfolio.id,
            schemas.TargetCreate(
                effective_at=at - timedelta(days=2),
                actor=Actor.IMPORT,
                reason="Synthetic target",
                allocations=[schemas.AllocationInput(company_id=company.id, weight=Decimal("0.5"))],
            ),
        )
        services.accept_targets(session, portfolio.id, target.id)
        portfolio_id, snapshot_id = portfolio.id, snapshot.id
    with Session(postgres_engine) as session:
        before = queries.overview(session, portfolio_id)
        assert before.base_market_value is None
        assert before.snapshot is not None and before.target_revision is not None
        original_snapshot = before.snapshot.model_dump()
        original_target = before.target_revision.model_dump()

    calls: list[str] = []

    def transport(url: str) -> bytes:
        parts = urlsplit(url)
        parameters = parse_qs(parts.query)
        assert "range" not in parameters
        assert int(parameters["period2"][0]) - int(parameters["period1"][0]) == 90 * 86400
        symbol = unquote(parts.path.rsplit("/", 1)[-1])
        assert symbol in {"SYNTH", "EUR=X"}
        calls.append(symbol)
        if fx_outage and symbol == "EUR=X":
            raise URLError("Synthetic FX outage")
        return source_payload(symbol, at)

    def provider(crosswalk: YahooListingCrosswalk) -> YahooFinanceProvider:
        return YahooFinanceProvider(crosswalk, transport=transport, retries=0)

    monkeypatch.setattr("portfolio_api.external_ingestion.YahooFinanceProvider", provider)
    with patch("portfolio_api.external_ingestion.load_yahoo_crosswalk") as reload:
        reload.side_effect = AssertionError("Frozen mapping must not be loaded again")
        with Session(postgres_engine) as session:
            first = run_cloud_incremental_refresh(session, settings, at)
        counts = table_counts(postgres_engine)
        postgres_engine.dispose()
        with Session(postgres_engine) as session:
            second = run_cloud_incremental_refresh(session, settings, at)
    assert second["status"] == first["status"]
    assert len(calls) == 2
    assert counts == table_counts(postgres_engine)
    assert first["status"] == ("FAILED" if fx_outage else "COMPLETE")
    digest = hashlib.sha256(market_scope.read_bytes()).hexdigest()
    with Session(postgres_engine) as session:
        after = queries.overview(session, portfolio_id)
        assert after.snapshot is not None and after.snapshot.id == snapshot_id
        assert after.snapshot.model_dump() == original_snapshot
        assert (
            after.target_revision is not None
            and after.target_revision.model_dump() == original_target
        )
        assert after.valuation_status == ("INCOMPLETE_FX_COVERAGE" if fx_outage else "VALUED")
        assert after.base_market_value == (None if fx_outage else Decimal("291.75"))
        runs = list(session.scalars(select(ExternalIngestionRun)))
        assert len(runs) == 3
        assert all(run.request_scope["crosswalk_sha256"] == digest for run in runs)
        fx = next(run for run in runs if run.domain == "FX")
        assert fx.request_scope["required_fx_pairs"] == [["USD", "EUR"]]

    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(
            create_app(
                Settings(
                    _env_file=None, database_url=None, app_env="development", api_access_token=None
                )
            )
        ) as client,
    ):
        response = client.get(f"/v1/portfolios/{portfolio_id}/overview")
        assert response.status_code == 200
        value = response.json()["base_market_value"]
        if fx_outage:
            assert value is None
        else:
            assert isinstance(value, str) and Decimal(value) == Decimal("291.75")
        operations = client.get("/v1/recurring-operations/status")
        assert operations.status_code == 200
        assert operations.json()["market_data"]["state"] == (
            "PARTIAL" if fx_outage else "AVAILABLE"
        )
    assert counts == table_counts(postgres_engine)
    if fx_outage:
        fx_outage = False
        at += timedelta(days=1)
        with Session(postgres_engine) as session:
            recovered = run_cloud_incremental_refresh(session, settings, at)
        assert recovered["status"] == "COMPLETE"
        assert len(calls) == 4
        with Session(postgres_engine) as session:
            restored = queries.overview(session, portfolio_id)
            assert restored.valuation_status == "VALUED"
            assert restored.base_market_value == Decimal("291.75")
            assert (
                restored.snapshot is not None
                and restored.snapshot.model_dump() == original_snapshot
            )
            assert restored.target_revision is not None
            assert restored.target_revision.model_dump() == original_target
            assert queries.market_refresh_status(session).state == "AVAILABLE"


@pytest.mark.integration
def test_mapping_capture_is_immutable_during_fetch_and_invalid_next_source_is_blocked(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime.now(UTC)
    original = market_scope.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    settings = Settings(
        _env_file=None, database_url=None, database_target_environment="development"
    )
    calls: list[str] = []

    def transport(url: str) -> bytes:
        symbol = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        calls.append(symbol)
        return source_payload(symbol, at)

    def provider(crosswalk: YahooListingCrosswalk) -> YahooFinanceProvider:
        assert crosswalk == YahooListingCrosswalk.model_validate_json(original)
        market_scope.write_text("{}", encoding="utf-8")
        return YahooFinanceProvider(crosswalk, transport=transport, retries=0)

    monkeypatch.setattr("portfolio_api.external_ingestion.YahooFinanceProvider", provider)
    with patch(
        "portfolio_api.market_data_startup.create_database_engine", return_value=postgres_engine
    ):
        result = run_startup_refresh(
            settings,
            cloud_incremental=True,
            allow_local_proxy_bypass=False,
            ready_wait_seconds=1,
            ready_poll_seconds=0,
        )
    assert result["status"] == "COMPLETE"
    assert set(calls) == {"SYNTH", "EUR=X"}
    with Session(postgres_engine) as session:
        runs = session.scalars(select(ExternalIngestionRun)).all()
        assert all(run.request_scope["crosswalk_sha256"] == digest for run in runs)
    before = table_counts(postgres_engine)
    with Session(postgres_engine) as session, pytest.raises(MarketDataBootstrapError):
        run_cloud_incremental_refresh(session, settings, at)
    assert before == table_counts(postgres_engine)
    assert len(calls) == 2


@pytest.mark.integration
def test_legacy_universe_gaps_remain_visible_outside_explicit_cloud_listing_scope(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Synthetic unlisted Watchlist company")
        session.add(company)
        session.flush()
        event = LifecycleEvent(
            company_id=company.id,
            sequence=1,
            previous_state=None,
            new_state="WATCHLIST",
            effective_at=at - timedelta(days=1),
            actor=Actor.IMPORT,
            reason="Synthetic missing-listing coverage",
            source="synthetic-cloud-test",
        )
        session.add(event)
        session.flush()
        session.add(CurrentLifecycle(company_id=company.id, event_id=event.id))

    def transport(url: str) -> bytes:
        return source_payload(unquote(urlsplit(url).path.rsplit("/", 1)[-1]), at)

    def provider(crosswalk: YahooListingCrosswalk) -> YahooFinanceProvider:
        return YahooFinanceProvider(crosswalk, transport=transport, retries=0)

    monkeypatch.setattr("portfolio_api.external_ingestion.YahooFinanceProvider", provider)
    raw = market_scope.read_bytes()
    frozen = (YahooListingCrosswalk.model_validate_json(raw), hashlib.sha256(raw).hexdigest())
    settings = Settings(
        _env_file=None, database_url=None, database_target_environment="development"
    )
    with Session(postgres_engine) as session:
        legacy = run_scheduled(
            session,
            settings,
            domains=[ExternalDataDomain.MARKET_DATA, ExternalDataDomain.FX],
            start_date=at.date() - timedelta(days=89),
            end_date=at.date(),
            lookback_days=90,
            run_date=at.date(),
            frozen_yahoo_crosswalk=frozen,
            fx_pair_filter={("USD", "EUR")},
        )
    assert legacy["status"] == "PARTIAL"
    with Session(postgres_engine) as session:
        scoped = run_cloud_incremental_refresh(session, settings, at)
    assert scoped["status"] == "COMPLETE"
