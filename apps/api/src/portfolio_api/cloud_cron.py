"""Run one bounded cloud ingestion cycle and exit."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from portfolio_api.database import create_database_engine
from portfolio_api.market_data_startup import run_startup_refresh
from portfolio_api.recurring_operations import _record_heartbeat, run_recurring_cycle
from portfolio_api.settings import Settings


def main() -> int:
    settings = Settings()
    if not settings.cloud_ingestion_enabled:
        print(json.dumps({"status": "DISABLED", "reason": "CLOUD_INGESTION_ENABLED=false"}))
        return 0
    if not settings.recurring_operations_enabled:
        print(json.dumps({"status": "BLOCKED", "reason": "RECURRING_OPERATIONS_ENABLED=false"}))
        return 2

    reports: dict[str, object] = {}
    try:
        reports["market_data"] = run_startup_refresh(settings)
    except Exception as error:
        reports["market_data"] = {"status": "FAILED", "error_type": type(error).__name__}

    engine = create_database_engine(
        settings,
        write_operation="cloud_cron_ingestion",
        write_operation_kind="ingestion",
    )
    if engine is None:
        reports["recurring_operations"] = {
            "status": "BLOCKED",
            "reason": "DATABASE_URL is not configured.",
        }
    else:
        instance_id = uuid4()
        started_at = datetime.now(UTC)
        error_type: str | None = None
        try:
            reports["recurring_operations"] = run_recurring_cycle(
                settings,
                engine=engine,
                instance_id=instance_id,
                process_started_at=started_at,
            )
        except Exception as error:
            error_type = type(error).__name__
            reports["recurring_operations"] = {
                "status": "FAILED",
                "error_type": error_type,
            }
        finally:
            try:
                _record_heartbeat(
                    engine,
                    instance_id,
                    started_at=started_at,
                    now_at=datetime.now(UTC),
                    status="STOPPED",
                    error=error_type,
                    stopped=True,
                )
            except Exception as error:
                reports["heartbeat"] = {"status": "FAILED", "error_type": type(error).__name__}
            engine.dispose()

    print(json.dumps(reports, indent=2, sort_keys=True, default=str), flush=True)
    if any(
        isinstance(report, dict) and report.get("status") in {"BLOCKED", "FAILED"}
        for report in reports.values()
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
