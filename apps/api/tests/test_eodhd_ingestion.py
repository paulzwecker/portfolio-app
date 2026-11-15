"""Private demo integration mechanics using synthetic values, never provider source data."""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_eodhd_demo import metadata

from portfolio_api import external_ingestion
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    Actor,
    CorporateAction,
    ExternalIngestionRun,
    ExternalRawPayload,
    HoldingPosition,
    Listing,
    MarketDataBatch,
    PriceObservation,
)
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.settings import Settings


def _seed(session: Session) -> tuple[UUID, UUID]:
    listings = []
    for name, ticker in [("Amazon", "AMZN"), ("Uncovered fixture", "OTHER")]:
        company = services.create_company(
            session, s.CompanyCreate(name=name, reporting_currency="USD")
        )
        security = services.create_security(
            session, company.id, s.SecurityCreate(name=name, security_type="COMMON_STOCK")
        )
        listing = services.create_listing(
            session, security.id, s.ListingCreate(ticker=ticker, venue="NASDAQ", currency="USD")
        )
        listings.append(listing)
    portfolio = services.create_portfolio(
        session, s.PortfolioCreate(name="Isolated demo test", base_currency="EUR")
    )
    services.record_holdings(
        session,
        portfolio.id,
        s.SnapshotCreate(
            actor=Actor.IMPORT,
            reason="Synthetic market test",
            source="synthetic-eodhd-test",
            effective_at=datetime(2026, 11, 1, tzinfo=UTC),
            completeness="COMPLETE",
            positions=[
                s.PositionInput(listing_id=item.id, quantity=Decimal(2)) for item in listings
            ],
            cash_positions=[s.CashInput(currency="EUR", balance=Decimal(10))],
        ),
    )
    session.commit()
    return listings[0].id, listings[1].id


@pytest.mark.integration
def test_demo_ingestion_durable_partial_incremental_and_metadata_evidence(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(_env_file=None, market_data_provider="EODHD_DEMO")
    calls: list[str] = []
    phase = "initial"
    metadata_version = "one"
    source_rows: list[dict[str, Any]] = [
        {"date": "2026-11-10", "close": 101, "adjusted_close": 100},
        {"date": "2026-11-11", "close": 102, "adjusted_close": 101},
        {"date": "2026-11-12", "close": 103, "adjusted_close": 102},
        {"date": "2026-11-13", "close": 104, "adjusted_close": 103},
    ]

    def transport(url: str) -> bytes:
        calls.append(url)
        if "/fundamentals/" in url:
            payload = metadata(UpdatedAt=metadata_version).payload
            assert payload is not None
            return payload
        params = parse_qs(urlsplit(url).query)
        assert params["api_token"] == ["demo"]
        assert "/AMZN.US?" in url
        selected = source_rows[:3] if phase == "initial" else source_rows[1:]
        assert all(params["from"][0] <= row["date"] <= params["to"][0] for row in selected)
        return json.dumps(selected).encode()

    monkeypatch.setattr("portfolio_api.eodhd_demo._default_transport", transport)
    with Session(postgres_engine) as session:
        listing_id, other_id = _seed(session)
        baseline_positions = list(
            session.execute(select(HoldingPosition.listing_id, HoldingPosition.quantity)).all()
        )
        kwargs: dict[str, Any] = {
            "domains": [ExternalDataDomain.MARKET_DATA],
            "start_date": date(2026, 11, 10),
            "end_date": date(2026, 11, 12),
            "run_date": date(2026, 11, 15),
        }
        first = run_scheduled(session, settings, **kwargs)
        assert first["status"] == "PARTIAL", first
        assert len(calls) == 2
        market = next(item for item in first["domains"] if item["domain"] == "MARKET_DATA")
        assert market["report"]["unresolved_listings"] == [
            {"listing_id": str(other_id), "reason": "NO_VERIFIED_FREE_DEMO_COVERAGE"}
        ]
        prices = list(
            session.scalars(select(PriceObservation).order_by(PriceObservation.market_date))
        )
        assert len(prices) == 3
        assert all(
            row.listing_id == listing_id and row.split_adjusted_close is None for row in prices
        )
        assert prices[-1].provider_close == Decimal(103)
        assert prices[-1].total_return_close == Decimal(102)
        assert session.scalar(select(func.count()).select_from(CorporateAction)) == 0
        raw = list(session.scalars(select(ExternalRawPayload)))
        assert {row.domain for row in raw} == {"MARKET_DATA", "COMPANY_REFERENCE"}
        assert {row.provider_id for row in raw} == {"EODHD_DEMO"}
        assert len(raw) == 2
        first_batch = session.scalar(select(MarketDataBatch))
        assert first_batch is not None
        first_digest = first_batch.source_digest

        again = run_scheduled(session, settings, **kwargs)
        assert all(row["idempotent_reuse"] for row in again["domains"])
        assert len(calls) == 2

        # New metadata evidence binds a new batch, even if normalized prices agree.
        metadata_version = "two"
        updated = run_scheduled(session, settings, **kwargs, request_nonce=uuid4())
        assert updated["status"] == "PARTIAL"
        assert session.scalar(select(func.count()).select_from(MarketDataBatch)) == 2
        assert session.scalar(select(func.count()).select_from(PriceObservation)) == 3
        assert len(set(session.scalars(select(MarketDataBatch.source_digest)))) == 2
        assert first_digest in set(session.scalars(select(MarketDataBatch.source_digest)))

        phase = "incremental"
        refreshed = run_scheduled(
            session,
            settings,
            domains=[ExternalDataDomain.MARKET_DATA],
            end_date=date(2026, 11, 13),
            run_date=date(2026, 11, 16),
        )
        assert refreshed["status"] == "PARTIAL"
        assert session.scalar(select(func.count()).select_from(PriceObservation)) == 4
        final_date = session.scalar(select(func.max(PriceObservation.market_date)))
        assert final_date is not None and final_date.date() == date(2026, 11, 13)
        assert len(calls) == 6
        assert (
            list(
                session.execute(select(HoldingPosition.listing_id, HoldingPosition.quantity)).all()
            )
            == baseline_positions
        )
        assert all(
            run.finished_at is not None for run in session.scalars(select(ExternalIngestionRun))
        )


@pytest.mark.integration
def test_demo_metadata_conflict_is_visible_without_price_fetch_or_persistence(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        assert "/fundamentals/" in url
        payload = metadata(CurrencyCode="EUR").payload
        assert payload is not None
        return payload

    monkeypatch.setattr("portfolio_api.eodhd_demo._default_transport", transport)
    with Session(postgres_engine) as session:
        _seed(session)
        result = run_scheduled(
            session,
            Settings(_env_file=None, market_data_provider="EODHD_DEMO"),
            domains=[ExternalDataDomain.MARKET_DATA],
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 13),
            run_date=date(2026, 11, 15),
        )
        market = next(row for row in result["domains"] if row["domain"] == "MARKET_DATA")
        assert market["status"] == "FAILED"
        assert market["attempt_count"] == 1
        assert market["failure_code"] is not None
        assert len(calls) == 1
        assert session.scalar(select(func.count()).select_from(PriceObservation)) == 0
        assert session.scalar(select(func.count()).select_from(MarketDataBatch)) == 0
        run = session.get(ExternalIngestionRun, UUID(market["run_id"]))
        assert run is not None and run.finished_at is not None
        assert run.report["retryable"] is False


def test_demo_rejects_production_before_any_database_or_provider_access() -> None:
    settings = Settings(_env_file=None, market_data_provider="EODHD_DEMO")
    # Exercise the runtime boundary as well as Settings validation.
    production = settings.model_copy(update={"app_env": "production"})
    with pytest.raises(ValueError, match="production"):
        run_scheduled(None, production, domains=[ExternalDataDomain.MARKET_DATA])  # type: ignore[arg-type]


@pytest.mark.integration
def test_demo_frozen_identity_change_fails_before_provider_fetch(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    changed = False
    execute_cycle = external_ingestion._execute_cycle

    def transport(url: str) -> bytes:
        calls.append(url)
        raise AssertionError("Identity mismatch must stop before provider access")

    with Session(postgres_engine) as session:
        listing_id, _ = _seed(session)

        def change_after_claim(
            cycle_session: Session,
            claims: list[external_ingestion.RunClaim],
            operation: Callable[[], dict[ExternalDataDomain, external_ingestion.DomainOutcome]],
            *,
            single_attempt: bool = False,
        ) -> None:
            nonlocal changed
            claim = next(
                (claim for claim in claims if claim.domain == ExternalDataDomain.MARKET_DATA),
                None,
            )
            if claim is not None and not changed:
                # A separate connection proves the reviewed identity was durably
                # frozen before the canonical record changes.
                with Session(postgres_engine) as observer:
                    frozen = observer.get(ExternalIngestionRun, claim.run_id)
                    assert frozen is not None
                    identities = frozen.request_scope["listing_identities"]
                    assert isinstance(identities, list)
                    identity = next(
                        row
                        for row in identities
                        if isinstance(row, dict) and row["listing_id"] == str(listing_id)
                    )
                    assert identity["currency"] == "USD"
                listing = cycle_session.get(Listing, listing_id)
                assert listing is not None
                listing.currency = "EUR"
                cycle_session.commit()
                changed = True
            execute_cycle(cycle_session, claims, operation, single_attempt=single_attempt)

        monkeypatch.setattr("portfolio_api.eodhd_demo._default_transport", transport)
        monkeypatch.setattr(external_ingestion, "_execute_cycle", change_after_claim)
        result = run_scheduled(
            session,
            Settings(_env_file=None, market_data_provider="EODHD_DEMO"),
            domains=[ExternalDataDomain.MARKET_DATA],
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 13),
            run_date=date(2026, 11, 15),
            request_nonce=uuid4(),
        )
        market = next(row for row in result["domains"] if row["domain"] == "MARKET_DATA")
        assert changed and calls == []
        assert market["status"] == "FAILED"
        assert market["attempt_count"] == 1
        assert market["failure_code"] == "INGESTION_VALIDATION_ERROR"
        assert (
            "frozen demo company/security/listing identity changed"
            in market["report"]["failure_message"]
        )
        assert session.scalar(select(func.count()).select_from(PriceObservation)) == 0
        assert session.scalar(select(func.count()).select_from(ExternalRawPayload)) == 0
