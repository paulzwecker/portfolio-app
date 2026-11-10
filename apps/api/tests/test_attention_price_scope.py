"""Point-in-time and exact-source safety of price-move attention events."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import _seed_canonical_scope

from portfolio_api.attention import attention_feed
from portfolio_api.domain.models import PriceObservation


@pytest.mark.integration
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("clean", 1),
        ("late_baseline", 1),
        ("recorded_later", 0),
        ("observed_later", 0),
        ("inconsistent_time", 0),
        ("other_provider", 0),
        ("other_symbol", 0),
        ("other_currency", 0),
        ("other_basis", 0),
        ("missing_basis", 0),
        ("blank_basis", 0),
        ("unverified_currency", 0),
        ("same_day_duplicate", 0),
    ],
)
def test_price_move_requires_known_unambiguous_compatible_closes(
    postgres_engine: Engine, mode: str, expected: int
) -> None:
    as_of = datetime(2026, 10, 6, 12, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        company, _, listing = _seed_canonical_scope(session, known_at=as_of - timedelta(days=5))
        company_id = company.id

        def observation(day: int, close: str, *, suffix: str) -> PriceObservation:
            return PriceObservation(
                id=uuid4(),
                listing_id=listing.id,
                price_kind="DAILY_CLOSE",
                market_date=datetime(2026, 10, day, tzinfo=UTC),
                observed_at=as_of - timedelta(days=1),
                recorded_at=as_of - timedelta(hours=1),
                split_adjusted_close=Decimal(close),
                currency="USD",
                provider="SYNTHETIC",
                provider_symbol="SYNTH",
                adjustment_basis="split adjusted",
                data_quality="PASS",
                source_ref=f"price-test-{suffix}-{uuid4()}",
            )

        prior = observation(2, "100", suffix="prior")
        current = observation(5, "120", suffix="current")
        if mode == "late_baseline":
            prior.recorded_at = as_of - timedelta(minutes=1)
        elif mode == "recorded_later":
            current.recorded_at = as_of + timedelta(hours=1)
        elif mode == "observed_later":
            current.observed_at = as_of + timedelta(hours=1)
        elif mode == "inconsistent_time":
            current.observed_at = as_of - timedelta(minutes=30)
        elif mode == "other_provider":
            current.provider = "OTHER"
        elif mode == "other_symbol":
            current.provider_symbol = "OTHER"
        elif mode == "other_currency":
            current.currency = "EUR"
        elif mode == "other_basis":
            current.adjustment_basis = "different basis"
        elif mode == "missing_basis":
            prior.adjustment_basis = current.adjustment_basis = ""
        elif mode == "blank_basis":
            prior.adjustment_basis = current.adjustment_basis = " "
        elif mode == "unverified_currency":
            listing.currency = None
        session.add_all([prior, current])
        if mode == "same_day_duplicate":
            session.add(observation(5, "121", suffix="duplicate"))
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        result = attention_feed(
            session, as_of=as_of, company_id=company_id, event_type="PRICE_MOVE"
        )
        assert result.total == expected
        if result.events:
            assert "previous recorded close" in result.events[0].title
            assert "sessions have not been verified" in result.events[0].explanation
            if mode == "late_baseline":
                assert result.events[0].recorded_at == as_of - timedelta(minutes=1)


@pytest.mark.integration
def test_future_correction_cannot_change_earlier_feed_or_bridge_corrected_day(
    postgres_engine: Engine,
) -> None:
    as_of = datetime(2026, 10, 6, 12, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        company, _, listing = _seed_canonical_scope(session, known_at=as_of - timedelta(days=5))
        company_id = company.id

        def observation(day: int, close: str, recorded: datetime) -> PriceObservation:
            return PriceObservation(
                id=uuid4(),
                listing_id=listing.id,
                price_kind="DAILY_CLOSE",
                market_date=datetime(2026, 10, day, tzinfo=UTC),
                observed_at=recorded,
                recorded_at=recorded,
                split_adjusted_close=Decimal(close),
                currency="USD",
                provider="SYNTHETIC",
                provider_symbol="SYNTH",
                adjustment_basis="split adjusted",
                data_quality="PASS",
                source_ref=f"correction-test-{uuid4()}",
            )

        prior = observation(2, "100", as_of - timedelta(hours=2))
        current = observation(5, "120", as_of - timedelta(hours=1))
        session.add_all([prior, current])
        session.flush()
        correction = observation(5, "115", as_of + timedelta(hours=1))
        correction.supersedes_observation_id = current.id
        next_day = observation(6, "130", as_of + timedelta(hours=2))
        session.add_all([correction, next_day])
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        before = attention_feed(
            session, as_of=as_of, company_id=company_id, event_type="PRICE_MOVE"
        )
        after = attention_feed(
            session,
            as_of=as_of + timedelta(hours=3),
            company_id=company_id,
            event_type="PRICE_MOVE",
        )
        assert before.total == 1
        assert after.total == 0
