from datetime import date
from decimal import Decimal

from portfolio_api.holding_return import reviewed_return


def test_split_net_income_fees_in_settled_cash_and_sale() -> None:
    data: dict[str, object] = {
        "currency": "EUR",
        "quote_currency": "USD",
        "close": "11",
        "quote_units_per_base": "1.1",
        "price_ref": "close",
        "fx_ref": "fx",
        "broker_ref": "export",
        "split_refs": ["split"],
        "activities": [
            {"day": "2024-01-01", "kind": "BUY", "shares": "2.5", "amount": "40"},
            {"day": "2024-05-01", "kind": "SPLIT", "amount": "2"},
            {"day": "2024-05-01", "kind": "DIVIDEND", "amount": "2"},
            {"day": "2024-06-01", "kind": "SELL", "shares": "1", "amount": "9"},
        ],
    }
    end = date(2024, 12, 31)
    result = reviewed_return(data, end, "EUR")
    assert result and result.shares == 4 and result.market_value == 40 and result.gain == 11
    assert result.cumulative_return == Decimal("0.275")
    assert result.annualized_money_weighted_return is not None
    assert reviewed_return(data, end, "USD") is None
    assert reviewed_return(data, date(2024, 5, 20), "EUR") is None
    assert reviewed_return({**data, "split_refs": []}, end, "EUR") is None
