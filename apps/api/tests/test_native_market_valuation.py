"""Native prices support mark-to-market, never inferred split-adjusted returns."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import _seed_canonical_scope

from portfolio_api.domain import queries
from portfolio_api.domain.models import FxObservation, Portfolio, PriceObservation


def native_price(**changes: object) -> PriceObservation:
    values: dict[str, object] = dict(
        id=uuid4(),
        listing_id=uuid4(),
        price_kind="DAILY_CLOSE",
        market_date=datetime(2026, 11, 13, tzinfo=UTC),
        observed_at=datetime(2026, 11, 15, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 15, tzinfo=UTC),
        provider_close=Decimal("5000"),
        source_price_multiplier=Decimal("0.01"),
        split_adjusted_close=None,
        total_return_close=Decimal("42"),
        volume=None,
        currency="GBP",
        provider_currency="GBp",
        provider="TEST_NATIVE",
        provider_symbol="SYNTH",
        adjustment_basis="UNADJUSTED_NATIVE_CLOSE",
        data_quality="PASS",
        source_ref=f"test:native:{uuid4()}",
    )
    values.update(changes)
    return PriceObservation(**values)


def test_native_price_keeps_units_and_never_uses_total_return() -> None:
    row = native_price()
    assert queries._native_close(row, "GBP", datetime(2026, 11, 15, 1, tzinfo=UTC)) == Decimal("50")
    assert row.split_adjusted_close is None and row.total_return_close == Decimal("42")


@pytest.mark.parametrize(
    "changes,currency",
    [
        ({"adjustment_basis": "UNKNOWN"}, "GBP"),
        ({"data_quality": "UNSPECIFIED"}, "GBP"),
        ({"observed_at": None}, "GBP"),
        ({"observed_at": datetime(2026, 11, 16, tzinfo=UTC)}, "GBP"),
        ({"recorded_at": datetime(2026, 11, 16, tzinfo=UTC)}, "GBP"),
        ({"market_date": datetime(2026, 11, 16, tzinfo=UTC)}, "GBP"),
        ({"provider_close": None}, "GBP"),
        ({"source_price_multiplier": Decimal("0")}, "GBP"),
        ({}, "USD"),
        ({}, None),
    ],
)
def test_native_eligibility_fails_closed(changes: dict[str, object], currency: str | None) -> None:
    assert (
        queries._native_close(
            native_price(**changes), currency, datetime(2026, 11, 15, 1, tzinfo=UTC)
        )
        is None
    )


@pytest.mark.integration
def test_native_history_and_current_eur_value_leave_split_analytics_unavailable(
    postgres_engine: Engine,
) -> None:
    recorded = datetime.now(UTC)
    cutoff = recorded + timedelta(minutes=1)
    latest_day = (recorded - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)
        portfolio = session.scalars(select(Portfolio)).one()
        for offset, close in [(1, "100"), (0, "50")]:
            session.add(
                native_price(
                    listing_id=listing.id,
                    currency="USD",
                    provider_currency="USD",
                    source_price_multiplier=Decimal(1),
                    market_date=latest_day - timedelta(days=offset),
                    observed_at=recorded,
                    recorded_at=recorded,
                    provider_close=Decimal(close),
                )
            )
        session.add(
            FxObservation(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.9"),
                effective_at=latest_day,
                observed_at=recorded,
                recorded_at=recorded,
                provider="TEST_FX",
                source="test:fx",
                actor="IMPORT",
                reason="Explicit synthetic reciprocal fixture",
            )
        )
        session.flush()
        market = queries.listing_market_data(session, listing, known_at=cutoff)
        assert [r.native_close for r in market.native_history] == [Decimal("50"), Decimal("100")]
        assert market.history == [] and market.analytics.observation_count == 0
        assert market.analytics.daily_return is None and market.analytics.dma_20 is None
        assert market.freshness == "QUALITY_CHECK" and market.native_freshness == "FRESH"
        assert market.latest is not None and market.latest.split_adjusted_close is None
        overview = queries.overview(session, portfolio.id, cutoff)
        position = overview.companies[0].positions[0]
        assert position.latest_price == Decimal("50")
        assert position.valuation_price_basis == "UNADJUSTED_NATIVE_CLOSE"
        assert position.native_market_value == Decimal("125")
        assert position.base_market_value == Decimal("112.5")
        assert overview.base_market_value == Decimal("112.5")
        assert position.portfolio_weight == Decimal(1)
        assert (
            queries.overview(session, portfolio.id, cutoff + timedelta(days=6)).base_market_value
            is None
        )
        assert (
            queries.listing_market_data(
                session, listing, known_at=recorded - timedelta(seconds=1)
            ).latest
            is None
        )
        # Do not blend a different source into a raw-price chart.
        session.add(
            native_price(
                listing_id=listing.id,
                currency="USD",
                provider_currency="USD",
                source_price_multiplier=Decimal(1),
                market_date=latest_day,
                observed_at=recorded,
                recorded_at=recorded,
                provider="OTHER_NATIVE",
            )
        )
        session.flush()
        mixed = queries.listing_market_data(session, listing, known_at=cutoff)
        assert mixed.native_history == [] and mixed.native_history_reason is not None
        assert mixed.analytics.observation_count == 0
        assert mixed.native_freshness == "QUALITY_CHECK"
        assert mixed.latest is not None and mixed.latest.native_close is None
        no_history = queries.listing_market_data(session, listing, history_limit=0, known_at=cutoff)
        assert no_history.native_freshness == "QUALITY_CHECK"
        assert no_history.latest is not None and no_history.latest.native_close is None
        unresolved = queries.overview(session, portfolio.id, cutoff)
        assert unresolved.base_market_value is None
        assert unresolved.companies[0].positions[0].valuation_status == "PRICE_UNAVAILABLE"


@pytest.mark.integration
def test_native_correction_is_point_in_time_but_unresolved_same_source_values_are_blocked(
    postgres_engine: Engine,
) -> None:
    recorded = datetime.now(UTC)
    market_day = (recorded - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)

        def observation(close: str, offset: int, **extra: object) -> PriceObservation:
            return native_price(
                listing_id=listing.id,
                currency="USD",
                provider_currency="USD",
                source_price_multiplier=Decimal(1),
                market_date=market_day,
                observed_at=recorded + timedelta(seconds=offset),
                recorded_at=recorded + timedelta(seconds=offset),
                provider_close=Decimal(close),
                **extra,
            )

        original = observation("100", 0)
        corrected = observation("101", 10, supersedes_observation_id=original.id)
        session.add_all([original, corrected])
        session.flush()
        historical = queries.listing_market_data(
            session, listing, history_limit=0, known_at=recorded + timedelta(seconds=5)
        )
        assert historical.latest is not None and historical.latest.native_close == Decimal(100)
        current = queries.listing_market_data(
            session, listing, history_limit=0, known_at=recorded + timedelta(seconds=15)
        )
        assert current.latest is not None and current.latest.native_close == Decimal(101)
        assert current.native_freshness == "FRESH"

        # A second value without an explicit correction link is ambiguous even
        # when it carries the same provider and listing symbol.
        session.add(observation("102", 20))
        session.flush()
        conflicting = queries.listing_market_data(
            session, listing, history_limit=0, known_at=recorded + timedelta(seconds=25)
        )
        assert conflicting.latest is not None and conflicting.latest.native_close is None
        assert conflicting.native_freshness == "QUALITY_CHECK"
        assert conflicting.native_history_reason is not None


@pytest.mark.integration
def test_old_native_conflict_hides_chart_but_keeps_current_valuation_usable(
    postgres_engine: Engine,
) -> None:
    recorded = datetime.now(UTC)
    latest_day = (recorded - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)
        portfolio = session.scalars(select(Portfolio)).one()

        def observation(close: str, day_offset: int, recorded_offset: int) -> PriceObservation:
            return native_price(
                listing_id=listing.id,
                currency="USD",
                provider_currency="USD",
                source_price_multiplier=Decimal(1),
                market_date=latest_day - timedelta(days=day_offset),
                observed_at=recorded + timedelta(seconds=recorded_offset),
                recorded_at=recorded + timedelta(seconds=recorded_offset),
                provider_close=Decimal(close),
            )

        older = observation("100", 1, 0)
        correction = observation("101", 1, 10)
        correction.supersedes_observation_id = older.id
        latest = observation("50", 0, 0)
        unresolved = observation("102", 1, 20)
        session.add_all([older, correction, latest, unresolved])
        session.flush()
        before_correction = queries.listing_market_data(
            session, listing, known_at=recorded + timedelta(seconds=5)
        )
        assert [row.native_close for row in before_correction.native_history] == [
            Decimal(50),
            Decimal(100),
        ]
        corrected = queries.listing_market_data(
            session, listing, known_at=recorded + timedelta(seconds=15)
        )
        assert [row.native_close for row in corrected.native_history] == [
            Decimal(50),
            Decimal(101),
        ]
        cutoff = recorded + timedelta(seconds=25)
        conflicting = queries.listing_market_data(session, listing, known_at=cutoff)
        assert conflicting.native_history == []
        assert "historical" in (conflicting.native_history_reason or "")
        assert conflicting.latest is not None and conflicting.latest.native_close == Decimal(50)
        assert conflicting.native_freshness == "FRESH"
        position = queries.overview(session, portfolio.id, cutoff).companies[0].positions[0]
        assert position.native_market_value == Decimal("125")
        assert position.price_freshness == "FRESH"
