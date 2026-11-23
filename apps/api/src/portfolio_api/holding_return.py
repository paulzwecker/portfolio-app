"""Retrospective return for a fully reviewed, single-listing broker history."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from math import exp
from typing import Literal

from pydantic import Field, ValidationError

from portfolio_api.domain.schemas import Contract, Currency, HoldingReturn


class Activity(Contract):
    day: date
    kind: Literal["BUY", "SELL", "DIVIDEND", "SPLIT"]
    # Net settled base-currency cash, or new shares per old share for SPLIT.
    amount: Decimal = Field(gt=0, max_digits=30, decimal_places=16)
    shares: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=10)


class Evidence(Contract):
    currency: Currency
    quote_currency: Currency
    close: Decimal = Field(gt=0)
    quote_units_per_base: Decimal = Field(gt=0)
    price_ref: str = Field(min_length=1)
    fx_ref: str = Field(min_length=1)
    broker_ref: str = Field(min_length=1)
    split_refs: list[str]
    activities: list[Activity] = Field(min_length=1, max_length=10000)


def _annualized(flows: dict[date, Decimal]) -> Decimal | None:
    ordered = sorted((day, amount) for day, amount in flows.items() if amount)
    if len(ordered) < 2 or ordered[0][1] >= 0 or ordered[-1][1] <= 0:
        return None
    end = ordered[-1][0]
    terms = [(float(amount), (end - day).days / 365) for day, amount in ordered]
    # The accumulated capital must remain invested through the final distribution.
    balance = Decimal(0)
    for _, amount in ordered[:-1]:
        balance += amount
        if balance >= 0:
            return None
    lo, hi = -10.0, 10.0

    def residual(rate: float) -> float:
        shift = max(0.0, terms[0][1] * rate)
        return sum(amount * exp(years * rate - shift) for amount, years in terms)

    if residual(lo) <= 0 or residual(hi) >= 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if residual(mid) > 0:
            lo = mid
        else:
            hi = mid
    return Decimal(str(exp((lo + hi) / 2) - 1)).quantize(Decimal("0.00000001"))


def reviewed_return(
    raw: dict[str, object], through: date, base_currency: str
) -> HoldingReturn | None:
    try:
        evidence = Evidence.model_validate(raw)
    except ValidationError:
        return None
    if evidence.currency != base_currency or (
        evidence.quote_currency == base_currency and evidence.quote_units_per_base != 1
    ):
        return None
    shares = purchases = sales = dividends = Decimal(0)
    flows: dict[date, Decimal] = defaultdict(Decimal)
    split_count = 0
    previous = date.min
    for row in evidence.activities:
        if not previous <= row.day <= through:
            return None
        previous = row.day
        if (row.kind in ("BUY", "SELL")) != (row.shares is not None):
            return None
        if row.kind == "SPLIT":
            shares *= row.amount
            split_count += 1
        elif row.kind == "DIVIDEND":
            dividends += row.amount
            flows[row.day] += row.amount
        elif row.shares is not None and row.kind == "BUY":
            purchases += row.amount
            shares += row.shares
            flows[row.day] -= row.amount
        elif row.shares is not None:
            sales += row.amount
            shares -= row.shares
            flows[row.day] += row.amount
        if shares < 0:
            return None
    if (
        not purchases
        or split_count != len(set(evidence.split_refs))
        or split_count != len(evidence.split_refs)
    ):
        return None
    value = shares * evidence.close / evidence.quote_units_per_base
    gain = value + dividends + sales - purchases
    flows[through] += value
    return HoldingReturn(
        through=through,
        currency=evidence.currency,
        shares=shares,
        purchases=purchases,
        sales=sales,
        dividends=dividends,
        market_value=value,
        gain=gain,
        cumulative_return=gain / purchases,
        annualized_money_weighted_return=_annualized(flows),
    )
