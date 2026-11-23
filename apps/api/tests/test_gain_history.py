from datetime import date
from decimal import Decimal as D

from portfolio_api.gain_history import cumulative_points, listing_gains
from portfolio_api.holding_return import Activity


def test_split_holiday_fx_partial_exit_and_late_cash() -> None:
    days = [date(2024, 1, i) for i in range(1, 14)]
    buy, split, partial, sale, dividend = days[0], days[1], days[2], days[11], days[12]
    activities = [
        Activity(day=buy, kind="BUY", amount=D(100), shares=D(1)),
        Activity(day=split, kind="SPLIT", amount=D(2)),
        Activity(day=partial, kind="SELL", amount=D(55), shares=D(1)),
        Activity(day=sale, kind="SELL", amount=D(40), shares=D(1)),
        Activity(day=dividend, kind="DIVIDEND", amount=D(8)),
    ]
    series = listing_gains(activities, {buy: D(100)}, {buy: D(2)}, {split: D(2)}, dividend)
    assert [series[d] for d in (buy, split, partial, days[8], sale, dividend)] == [
        0,
        0,
        5,
        None,
        -5,
        3,
    ]


def test_portfolio_aggregation_preserves_gaps_and_realized_cash() -> None:
    a, b, c, d = [date(2024, 1, i) for i in range(1, 5)]
    points = cumulative_points([{a: D("1.123"), b: None, c: D(2), d: D(2)}, {c: D(10)}])
    assert [p.gain for p in points] == [D("1.12"), None, D(12), None]


def test_latest_history_is_scoped_to_portfolio() -> None:
    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from portfolio_api.database import Base
    from portfolio_api.domain.models import Portfolio, PortfolioGainHistory
    from portfolio_api.domain.routes import get_gain_history

    engine = create_engine("sqlite://")
    tables = Base.metadata.tables
    Base.metadata.create_all(
        engine, tables=[tables["portfolios"], tables["portfolio_gain_histories"]]
    )
    with Session(engine) as session:
        p = Portfolio(name="Test", base_currency="EUR")
        other = Portfolio(name="Other", base_currency="EUR")
        session.add_all([p, other])
        session.flush()
        assert get_gain_history(p.id, session) is None
        for day in (1, 2):
            session.add(
                PortfolioGainHistory(
                    portfolio_id=p.id,
                    recorded_at=datetime(2026, 5, day, tzinfo=UTC),
                    report=dict(
                        portfolio_id=str(p.id),
                        open_positions=1,
                        closed_positions=1,
                        excluded=[],
                        provisional=[],
                        points=[{"day": "2026-05-01", "gain": str(day)}],
                    ),
                )
            )
        session.flush()
        newest = get_gain_history(p.id, session)
        assert newest and newest.points[-1].gain == 2
        assert get_gain_history(other.id, session) is None
