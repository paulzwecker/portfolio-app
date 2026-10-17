from datetime import UTC, date, datetime
from decimal import Decimal
from math import sqrt
from statistics import stdev

import pytest
from pydantic import ValidationError

from portfolio_api.domain.schemas import FxObservationCreate
from portfolio_api.market_data import (
    _date,
    _quality,
    _regime_metrics,
    calculate_price_history_metrics,
)
from portfolio_api.market_data_startup import configure_yahoo_no_proxy


def test_legacy_price_regime_metrics_match_documented_session_windows() -> None:
    closes = [float(value) for value in range(1, 261)]
    metrics = _regime_metrics(closes)
    assert metrics["dma_20"] == pytest.approx(250.5)
    assert metrics["dma_50"] == pytest.approx(235.5)
    assert metrics["dma_200"] == pytest.approx(160.5)
    assert metrics["high_52w"] == 260
    assert metrics["drawdown_52w"] == 0
    assert metrics["return_1m"] == pytest.approx(260 / 239 - 1)
    assert metrics["return_3m"] == pytest.approx(260 / 197 - 1)
    assert metrics["return_6m"] == pytest.approx(260 / 134 - 1)
    daily_returns = [closes[index] / closes[index - 1] - 1 for index in range(240, 260)]
    assert metrics["realized_vol_20d"] == pytest.approx(stdev(daily_returns) * sqrt(252))
    assert metrics["trend_state"] == "STRONG UPTREND"
    assert metrics["correction_state"] == "NEAR HIGHS"


def test_short_history_keeps_unsupported_windows_null() -> None:
    metrics = _regime_metrics([100.0, 101.0, 102.0])
    assert metrics["dma_20"] is None
    assert metrics["dma_50"] is None
    assert metrics["high_52w"] is None
    assert metrics["return_1m"] is None
    assert metrics["realized_vol_20d"] is None
    assert metrics["trend_state"] is None
    assert metrics["correction_state"] is None


def test_current_analytics_are_price_only_and_keep_unavailable_windows_null() -> None:
    metrics = calculate_price_history_metrics([Decimal("100"), Decimal("110")])
    assert metrics["daily_return"] == pytest.approx(0.10)
    assert metrics["price_return_1m"] is None
    assert metrics["dma_50"] is None
    assert metrics["realized_vol_20d"] is None


def test_startup_bypasses_only_the_known_local_port_nine_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "portfolio_api.networking.urllib.request.getproxies",
        lambda: {"https": "http://127.0.0.1:9"},
    )
    env = {"NO_PROXY": "localhost,internal.example"}
    assert configure_yahoo_no_proxy(env)
    assert env["NO_PROXY"] == (
        "localhost,internal.example,query1.finance.yahoo.com,query2.finance.yahoo.com"
    )
    assert env["no_proxy"] == env["NO_PROXY"]


def test_startup_preserves_nonlocal_proxy_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "portfolio_api.networking.urllib.request.getproxies",
        lambda: {"https": "http://proxy.example:8080"},
    )
    env = {"NO_PROXY": "localhost"}
    assert not configure_yahoo_no_proxy(env)
    assert env == {"NO_PROXY": "localhost"}


def test_legacy_quality_and_excel_market_date_are_preserved_explicitly() -> None:
    assert _date("46296.0") == date(2026, 10, 1)
    assert _quality("PASS") == "PASS"
    assert _quality("PASS - VERIFIED FALLBACK") == "PASS_VERIFIED_FALLBACK"
    assert _quality(None) == "UNSPECIFIED"


def test_fx_observation_requires_positive_exact_dated_source_fact() -> None:
    valid = FxObservationCreate.model_validate(
        {
            "base_currency": "USD",
            "quote_currency": "EUR",
            "rate": "0.91",
            "effective_at": datetime(2026, 10, 1, 12, tzinfo=UTC),
            "provider": "Fixture provider",
            "source": "fixture:USD-EUR-2026-10-01",
            "actor": "IMPORT",
            "reason": "Explicit integration fixture",
        }
    )
    assert str(valid.rate) == "0.91"
    with pytest.raises(ValidationError):
        FxObservationCreate.model_validate({**valid.model_dump(mode="json"), "rate": 0.0})
    with pytest.raises(ValidationError):
        FxObservationCreate.model_validate(
            {**valid.model_dump(mode="json"), "base_currency": "EUR", "quote_currency": "EUR"}
        )
    with pytest.raises(ValidationError):
        FxObservationCreate.model_validate({**valid.model_dump(mode="json"), "rate": 0.9})
