"""Retrospective security P&L in EUR from dated settlements and daily reference marks."""

from datetime import date, timedelta
from decimal import Decimal
from math import prod

from portfolio_api.domain.schemas import GainPoint
from portfolio_api.holding_return import Activity


def listing_gains(
    activities: list[Activity],
    closes: dict[date, Decimal],
    fx: dict[date, Decimal] | None,
    splits: dict[date, Decimal],
    through: date,
) -> dict[date, Decimal | None]:
    """Closes are dividend-unadjusted, normalized to the final split basis of the archive.
    FX is quote units per EUR. None denotes an EUR listing. Cash uses settled EUR.
    """
    if not activities or activities != sorted(activities, key=lambda a: a.day):
        raise ValueError("Expected ordered activities")
    if any(v <= 0 for series in (closes, fx or {}, splits) for v in series.values()):
        raise ValueError("Expected positive marks and split ratios")
    day = activities[0].day
    if activities[-1].day > through:
        raise ValueError("Activity exceeds cutoff")
    # Convert each trade to the SAME share basis as the adjusted close, including
    # later splits after a sale. The split itself then needs no second application.
    cash = shares = Decimal(0)
    result: dict[date, Decimal | None] = {}
    index = 0
    last_price = max((d for d in closes if d < day), default=None)
    last_rate = max((d for d in (fx or {}) if d < day), default=None)
    while day <= through:
        while index < len(activities) and activities[index].day == day:
            a = activities[index]
            if a.kind in ("BUY", "SELL"):
                if a.shares is None:
                    raise ValueError("Missing trade quantity")
                basis = prod((v for d, v in splits.items() if d > day), start=Decimal(1))
                sign = 1 if a.kind == "BUY" else -1
                shares += sign * a.shares * basis
                cash -= sign * a.amount
            elif a.kind == "DIVIDEND":
                cash += a.amount
            elif splits.get(day) != a.amount:
                raise ValueError("Inconsistent split evidence")
            if shares < 0:
                raise ValueError("Sale exceeds reconstructed position")
            index += 1
        if day in closes:
            last_price = day
        if fx is not None and day in fx:
            last_rate = day
        gain = None
        if not shares:
            gain = cash
        elif last_price and (day - last_price).days <= 7:
            if fx is None:
                gain = cash + shares * closes[last_price]
            elif last_rate and (day - last_rate).days <= 7:
                gain = cash + shares * closes[last_price] / fx[last_rate]
        result[day] = gain
        day += timedelta(days=1)
    return result


def cumulative_points(series: list[dict[date, Decimal | None]]) -> list[GainPoint]:
    """Only dates before a listing's first acquisition contribute an implicit zero."""
    if not series or any(not gains for gains in series):
        raise ValueError("Missing listing history")
    start = min(min(gains) for gains in series)
    through = max(max(gains) for gains in series)
    histories = [(min(gains), gains) for gains in series]
    points = []
    day = start
    while day <= through:
        total = Decimal(0)
        gain = None
        for first, gains in histories:
            if day < first:
                continue
            amount = gains.get(day)
            if amount is None:
                break
            total += amount
        else:
            gain = round(total, 2)
        points.append(GainPoint(day=day, gain=gain))
        day += timedelta(days=1)
    return points
