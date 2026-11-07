import json
import os
from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.cloud_cron import main
from portfolio_api.domain.models import RecurringOperationRun, RecurringOperationsWorkerState
from portfolio_api.market_data_startup import run_startup_refresh
from portfolio_api.recurring_operations import LOCK_KEY, LOCK_NAMESPACE, _record_heartbeat
from portfolio_api.settings import Settings


def test_cloud_cron_is_inert_until_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLOUD_INGESTION_ENABLED", "false")
    with (
        patch("portfolio_api.cloud_cron.run_startup_refresh") as market_refresh,
        patch("portfolio_api.cloud_cron.run_recurring_cycle") as recurring_cycle,
    ):
        assert main([]) == 0

    assert capsys.readouterr().out.strip() == (
        '{"status": "DISABLED", "reason": "CLOUD_INGESTION_ENABLED=false"}'
    )
    market_refresh.assert_not_called()
    recurring_cycle.assert_not_called()


@pytest.fixture
def cloud_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        database_url=None,
        cloud_ingestion_enabled=True,
        recurring_operations_enabled=True,
    )
    monkeypatch.setattr("portfolio_api.cloud_cron.Settings", lambda: settings)


def test_default_cloud_scope_only_refreshes_market_and_preserves_proxy_routing(
    cloud_enabled: None, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch(
            "portfolio_api.cloud_cron.run_startup_refresh",
            return_value={
                "status": "COMPLETE",
                "report": {"private_values": "PRIVATE_SOURCE_VALUE"},
            },
        ) as market,
        patch("portfolio_api.cloud_cron.create_database_engine") as factory,
        patch("portfolio_api.cloud_cron.run_recurring_cycle") as cycle,
    ):
        assert main([]) == 0
    assert market.call_args.kwargs == {"allow_local_proxy_bypass": False}
    factory.assert_not_called()
    cycle.assert_not_called()
    output = capsys.readouterr().out
    assert "PRIVATE_SOURCE_VALUE" not in output
    assert json.loads(output) == {
        "scope": "market-data",
        "operations": {"market_data": {"status": "COMPLETE"}},
    }


@pytest.mark.parametrize(
    ("scope", "provider_only"), [("provider-data", True), ("all-operations", False)]
)
def test_explicit_cloud_scope_uses_existing_guarded_engine_and_closes_it(
    cloud_enabled: None, scope: str, provider_only: bool
) -> None:
    engine = Mock()
    with (
        patch("portfolio_api.cloud_cron.run_startup_refresh", return_value={"status": "SKIPPED"}),
        patch("portfolio_api.cloud_cron.create_database_engine", return_value=engine) as factory,
        patch(
            "portfolio_api.cloud_cron.run_recurring_cycle",
            return_value={
                "status": "COMPLETE",
                "jobs": [{"job_name": "SEC_FILINGS", "status": "NOT_DUE"}],
            },
        ) as cycle,
        patch("portfolio_api.cloud_cron._record_heartbeat") as heartbeat,
    ):
        assert main(["--scope", scope]) == 0
    assert factory.call_args.kwargs == {
        "write_operation": "cloud_cron_ingestion",
        "write_operation_kind": "ingestion",
    }
    assert cycle.call_args.kwargs["provider_only"] is provider_only
    assert cycle.call_args.kwargs["engine"] is engine
    assert heartbeat.call_args.kwargs["stopped"] is True
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("status", ["PARTIAL", "FAILED", "BLOCKED", "RUNNING", "UNKNOWN", None])
def test_market_incomplete_outcome_is_nonzero(cloud_enabled: None, status: str | None) -> None:
    with patch("portfolio_api.cloud_cron.run_startup_refresh", return_value={"status": status}):
        assert main([]) == 1


@pytest.mark.parametrize(
    "jobs",
    [
        [{"job_name": "SEC_FILINGS", "status": "FAILED"}],
        [{"job_name": "SEC_FILINGS", "status": "COMPLETE", "operation_status": "PARTIAL"}],
        [
            {"job_name": "SEC_FILINGS", "status": "COMPLETE"},
            {"job_name": "SEC_FUNDAMENTALS", "status": "BLOCKED"},
        ],
        [{"job_name": "PRIVATE_UNKNOWN_JOB", "status": "COMPLETE"}],
        [{"job_name": "SEC_FILINGS", "status": {"malformed": True}}],
        [None],
        "malformed",
        None,
    ],
)
def test_nested_or_malformed_job_failure_cannot_exit_successfully(
    cloud_enabled: None, jobs: object, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch("portfolio_api.cloud_cron.run_startup_refresh", return_value={"status": "COMPLETE"}),
        patch("portfolio_api.cloud_cron.create_database_engine", return_value=Mock()),
        patch(
            "portfolio_api.cloud_cron.run_recurring_cycle",
            return_value={
                "status": "COMPLETE",
                "jobs": jobs,
                "failure_message": "PRIVATE_EXCEPTION",
            },
        ),
        patch("portfolio_api.cloud_cron._record_heartbeat"),
    ):
        assert main(["--scope", "provider-data"]) == 1
    output = capsys.readouterr().out
    assert "PRIVATE_EXCEPTION" not in output
    assert "PRIVATE_UNKNOWN_JOB" not in output


@pytest.mark.parametrize("failure", ["market", "factory", "cycle", "heartbeat"])
def test_cloud_exception_is_sanitized_and_resources_are_released(
    cloud_enabled: None, failure: str, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = Mock()
    with (
        patch(
            "portfolio_api.cloud_cron.run_startup_refresh", return_value={"status": "COMPLETE"}
        ) as market,
        patch("portfolio_api.cloud_cron.create_database_engine", return_value=engine) as factory,
        patch(
            "portfolio_api.cloud_cron.run_recurring_cycle", return_value={"status": "COMPLETE"}
        ) as cycle,
        patch("portfolio_api.cloud_cron._record_heartbeat") as heartbeat,
    ):
        actions = {"market": market, "factory": factory, "cycle": cycle, "heartbeat": heartbeat}
        actions[failure].side_effect = RuntimeError("PRIVATE_CONNECTION_URL_AND_PASSWORD")
        assert main(["--scope", "provider-data"]) == 1
    output = capsys.readouterr().out
    assert "PRIVATE_CONNECTION_URL_AND_PASSWORD" not in output
    assert '"error_type": "RuntimeError"' in output
    if failure != "factory":
        engine.dispose.assert_called_once()


def test_enabled_cloud_still_requires_recurring_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "portfolio_api.cloud_cron.Settings",
        lambda: Settings(
            _env_file=None,
            database_url=None,
            cloud_ingestion_enabled=True,
            recurring_operations_enabled=False,
        ),
    )
    with patch("portfolio_api.cloud_cron.run_startup_refresh") as market:
        assert main([]) == 2
    market.assert_not_called()


def test_unknown_scope_is_rejected_before_settings_or_provider_access() -> None:
    with patch("portfolio_api.cloud_cron.Settings") as settings, pytest.raises(SystemExit):
        main(["--scope", "unrestricted"])
    settings.assert_not_called()


@pytest.mark.integration
def test_cloud_provider_cycle_persists_isolated_failure_without_leaking_details(
    postgres_engine: Engine,
    cloud_enabled: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def sec(_engine: Engine, _settings: Settings, domain: object, _at: object) -> dict[str, object]:
        if str(domain) == "REPORTED_FUNDAMENTALS":
            raise RuntimeError("PRIVATE_CREDENTIAL_AND_CONNECTION_DETAILS")
        return {"status": "COMPLETE", "source_details": "PRIVATE_SOURCE_CONTENT"}

    monkeypatch.setattr("portfolio_api.recurring_operations._run_sec_domain", sec)
    with (
        patch("portfolio_api.cloud_cron.run_startup_refresh", return_value={"status": "SKIPPED"}),
        patch("portfolio_api.cloud_cron.create_database_engine", return_value=postgres_engine),
    ):
        assert main(["--scope", "provider-data"]) == 1
    output = capsys.readouterr().out
    assert "PRIVATE_CREDENTIAL" not in output + caplog.text
    assert "PRIVATE_SOURCE_CONTENT" not in output
    with Session(postgres_engine) as session:
        runs = {run.job_name: run for run in session.scalars(select(RecurringOperationRun))}
        assert set(runs) == {"SEC_FUNDAMENTALS", "SEC_FILINGS"}
        assert runs["SEC_FUNDAMENTALS"].status == "FAILED"
        assert runs["SEC_FUNDAMENTALS"].failure_code == "RuntimeError"
        assert "PRIVATE" not in str(runs["SEC_FUNDAMENTALS"].failure_message)
        assert runs["SEC_FILINGS"].status == "SUCCEEDED"
    summary = json.loads(output)["operations"]["recurring_operations"]
    assert summary["status"] == "PARTIAL"


@pytest.mark.integration
def test_cloud_market_path_respects_proxy_environment_before_due_check(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "operator-approved-host.invalid")
    with (
        patch(
            "portfolio_api.market_data_startup.create_database_engine", return_value=postgres_engine
        ),
        patch("portfolio_api.market_data_startup.wait_for_database", return_value=True),
        patch(
            "portfolio_api.market_data_startup.market_refresh_due", return_value=(False, "Not due")
        ),
        patch("portfolio_api.market_data_startup.configure_yahoo_no_proxy") as configure_proxy,
        patch("portfolio_api.market_data_startup.run_scheduled") as provider,
    ):
        result = run_startup_refresh(
            Settings(_env_file=None, database_url=None),
            allow_local_proxy_bypass=False,
        )
    configure_proxy.assert_not_called()
    provider.assert_not_called()
    assert result["status"] == "SKIPPED"
    assert result["proxy_bypass_applied"] is False
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert os.environ["NO_PROXY"] == "operator-approved-host.invalid"


@pytest.mark.integration
def test_overlapping_cloud_cycle_does_not_stop_the_active_worker_heartbeat(
    postgres_engine: Engine,
    cloud_enabled: None,
) -> None:
    active_instance = uuid4()
    at = datetime.now(UTC)
    _record_heartbeat(postgres_engine, active_instance, started_at=at, now_at=at)
    with postgres_engine.connect() as active:
        assert active.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
            {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
        ).scalar_one()
        active.commit()
        try:
            with (
                patch(
                    "portfolio_api.cloud_cron.run_startup_refresh",
                    return_value={"status": "SKIPPED"},
                ),
                patch(
                    "portfolio_api.cloud_cron.create_database_engine", return_value=postgres_engine
                ),
            ):
                assert main(["--scope", "provider-data"]) == 0
        finally:
            active.execute(
                text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
            )
            active.commit()
    with Session(postgres_engine) as session:
        state = session.get(RecurringOperationsWorkerState, "primary")
        assert state is not None
        assert state.instance_id == active_instance
        assert state.status == "RUNNING"
        assert state.last_heartbeat_at == at
        assert state.stopped_at is None
