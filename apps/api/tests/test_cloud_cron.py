from unittest.mock import patch

import pytest

from portfolio_api.cloud_cron import main


def test_cloud_cron_is_inert_until_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLOUD_INGESTION_ENABLED", "false")
    with (
        patch("portfolio_api.cloud_cron.run_startup_refresh") as market_refresh,
        patch("portfolio_api.cloud_cron.run_recurring_cycle") as recurring_cycle,
    ):
        assert main() == 0

    assert capsys.readouterr().out.strip() == (
        '{"status": "DISABLED", "reason": "CLOUD_INGESTION_ENABLED=false"}'
    )
    market_refresh.assert_not_called()
    recurring_cycle.assert_not_called()
