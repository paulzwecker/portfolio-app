"""Run one bounded cloud ingestion cycle and exit."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from portfolio_api.database import create_database_engine
from portfolio_api.market_data_startup import run_startup_refresh
from portfolio_api.recurring_operations import (
    JOB_CADENCES_SECONDS,
    _record_heartbeat,
    run_recurring_cycle,
)
from portfolio_api.settings import Settings

SUCCESS_STATUSES = frozenset({"COMPLETE", "SUCCEEDED", "SKIPPED", "NOT_DUE", "NOT_APPLICABLE"})
KNOWN_STATUSES = SUCCESS_STATUSES | {"PARTIAL", "FAILED", "BLOCKED", "DISABLED", "RUNNING"}


def _summary(report: dict[str, object]) -> dict[str, object]:
    """Keep source payloads and free-text errors out of the cloud command output."""
    status = report.get("operation_status", report.get("status"))
    result: dict[str, object] = {
        "status": status if isinstance(status, str) and status in KNOWN_STATUSES else "FAILED"
    }
    for field in ("error_type", "failure_code"):
        value = report.get(field)
        if isinstance(value, str) and value.isidentifier() and len(value) <= 80:
            result[field] = value
    jobs = report.get("jobs")
    if "jobs" in report:
        summaries: list[dict[str, object]] = []
        if not isinstance(jobs, list):
            result["status"] = "FAILED"
            return result
        for job in jobs:
            if not isinstance(job, dict):
                result["status"] = "FAILED"
                continue
            name = job.get("job_name")
            known_job = isinstance(name, str) and name in JOB_CADENCES_SECONDS
            job_status = job.get("operation_status", job.get("status"))
            summaries.append(
                {
                    "job_name": name if known_job else "UNKNOWN",
                    "status": job_status
                    if known_job and isinstance(job_status, str) and job_status in KNOWN_STATUSES
                    else "FAILED",
                }
            )
        result["jobs"] = summaries
        if any(item["status"] not in SUCCESS_STATUSES for item in summaries):
            result["status"] = (
                "PARTIAL"
                if any(item["status"] in SUCCESS_STATUSES for item in summaries)
                else "FAILED"
            )
    manual = report.get("manual_request")
    if manual is not None:
        manual_status = manual.get("status") if isinstance(manual, dict) else None
        known_manual = (
            SUCCESS_STATUSES
            | {"IDLE", "DEFERRED", "REQUEST_NOT_READY"}
            | {"PARTIAL", "FAILED", "BLOCKED"}
        )
        safe_status = (
            manual_status
            if isinstance(manual_status, str) and manual_status in known_manual
            else "FAILED"
        )
        result["manual_request"] = {"status": safe_status}
        if safe_status not in SUCCESS_STATUSES | {"IDLE", "DEFERRED", "REQUEST_NOT_READY"}:
            result["status"] = "PARTIAL" if safe_status == "PARTIAL" else "FAILED"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=(
            "market-data",
            "provider-data",
            "sec-data",
            "public-market-data",
            "all-operations",
        ),
        default="market-data",
        help="Market/FX by default. SEC-only also drains at most one queued SEC request.",
    )
    parser.add_argument(
        "--company-id", type=UUID, help="Limit a market-data cycle to one tracked company."
    )
    parser.add_argument("--refresh-slot", help="Stable identity for an intraday market cycle.")
    parser.add_argument("--history-start", type=date.fromisoformat)
    args = parser.parse_args(argv)
    if args.history_start and (args.company_id is None or args.scope != "market-data"):
        parser.error("--history-start requires a single company in the market-data scope")
    if (args.company_id is not None or args.refresh_slot) and args.scope != "market-data":
        parser.error("--company-id requires --scope market-data")
    settings = Settings()
    if not settings.cloud_ingestion_enabled:
        print(json.dumps({"status": "DISABLED", "reason": "CLOUD_INGESTION_ENABLED=false"}))
        return 0
    if not settings.recurring_operations_enabled:
        print(json.dumps({"status": "BLOCKED", "reason": "RECURRING_OPERATIONS_ENABLED=false"}))
        return 2

    reports: dict[str, object] = {}
    if args.scope not in {"sec-data", "public-market-data"}:
        try:
            reports["market_data"] = run_startup_refresh(
                settings,
                allow_local_proxy_bypass=False,
                cloud_incremental=True,
                company_id=args.company_id,
                refresh_slot=args.refresh_slot,
                history_start=args.history_start,
            )
        except Exception as error:
            reports["market_data"] = {"status": "FAILED", "error_type": type(error).__name__}

    if args.scope != "market-data":
        engine = None
        instance_id = uuid4()
        started_at = datetime.now(UTC)
        error_type: str | None = None
        try:
            engine = create_database_engine(
                settings,
                write_operation="cloud_cron_ingestion",
                write_operation_kind="ingestion",
            )
            if engine is None:
                reports["recurring_operations"] = {"status": "BLOCKED"}
            else:
                reports["recurring_operations"] = run_recurring_cycle(
                    settings,
                    engine=engine,
                    instance_id=instance_id,
                    process_started_at=started_at,
                    provider_only=args.scope == "provider-data",
                    sec_only=args.scope == "sec-data",
                    public_market_only=args.scope == "public-market-data",
                )
        except Exception as error:
            error_type = type(error).__name__
            reports["recurring_operations"] = {
                "status": "FAILED",
                "error_type": error_type,
            }
        finally:
            if engine is not None:
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

    summaries = {
        name: _summary(report) if isinstance(report, dict) else {"status": "FAILED"}
        for name, report in reports.items()
    }
    print(json.dumps({"scope": args.scope, "operations": summaries}, sort_keys=True), flush=True)
    return int(any(report["status"] not in SUCCESS_STATUSES for report in summaries.values()))


if __name__ == "__main__":
    raise SystemExit(main())
