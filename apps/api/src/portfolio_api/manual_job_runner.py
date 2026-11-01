"""Run one explicitly queued manual operation, then exit without scheduling work."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    verify_database_write_target,
)
from portfolio_api.domain.models import OperationalJobRequest
from portfolio_api.domain.schemas import OperationalJobRequestCreate
from portfolio_api.manual_operations import JOB_DOMAINS, create_job_request
from portfolio_api.recurring_operations import JOB_STALE_AFTER, process_manual_job_requests
from portfolio_api.settings import Settings


def _summary(result: dict[str, object], request_id: UUID) -> dict[str, object]:
    """Return operational identifiers and statuses without echoing source payloads."""
    steps = result.get("steps")
    safe_steps: list[dict[str, object]] = []
    if isinstance(steps, list):
        for item in steps:
            if isinstance(item, dict):
                step_result = item.get("result")
                safe_result: dict[str, object] = {}
                if isinstance(step_result, dict):
                    for key in ("workbook_sync_run_id", "sync_status", "error_code"):
                        value = step_result.get(key)
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            safe_result[key] = value
                safe_steps.append(
                    {
                        "step_name": item.get("step_name"),
                        "status": item.get("status"),
                        "result": safe_result,
                    }
                )
    return {
        "status": result.get("status", "FAILED"),
        "request_id": str(request_id),
        "steps": safe_steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "request_id",
        type=UUID,
        nargs="?",
        help="Run one already queued request by exact ID.",
    )
    parser.add_argument(
        "--job-name",
        choices=sorted(JOB_DOMAINS),
        help="Create and run one durable request for this allowlisted operation.",
    )
    parser.add_argument("--scope-kind", choices=("ACTIVE_UNIVERSE", "COMPANY"))
    parser.add_argument("--company-id", type=UUID)
    parser.add_argument(
        "--confirm-run",
        action="store_true",
        help="Confirm execution of this exact queued request once.",
    )
    args = parser.parse_args(argv)
    if not args.confirm_run:
        parser.error("Pass --confirm-run after reviewing the exact operation request.")
    if (args.request_id is None) == (args.job_name is None):
        parser.error("Specify exactly one queued request ID or --job-name.")
    if args.request_id is not None and (args.scope_kind is not None or args.company_id is not None):
        parser.error("Scope options can only be used with --job-name.")

    settings = Settings()
    if not settings.manual_operations_enabled:
        print(
            "MANUAL_OPERATIONS_DISABLED: set MANUAL_OPERATIONS_ENABLED=true for this run.",
            file=sys.stderr,
        )
        return 2
    if settings.database_url is None:
        print("DATABASE_URL is required for the one-shot operation runner.", file=sys.stderr)
        return 2

    engine = create_database_engine(
        settings,
        write_operation="one_shot_manual_operations",
        write_operation_kind="ingestion",
    )
    if engine is None:
        return 2
    try:
        verify_database_write_target(engine)
        request_id = args.request_id
        if args.job_name is not None:
            request_value = OperationalJobRequestCreate.model_validate(
                {
                    "job_name": args.job_name,
                    "scope_kind": args.scope_kind or "ACTIVE_UNIVERSE",
                    "company_id": args.company_id,
                }
            )
            with Session(engine) as session, session.begin():
                request, deduplicated = create_job_request(session, request_value)
                request_id = request.id
                request_status = request.status
            if deduplicated and request_status not in {"QUEUED", "RUNNING"}:
                print(
                    json.dumps(
                        {
                            "status": "DEDUPLICATED_NOOP",
                            "request_id": str(request_id),
                            "existing_status": request_status,
                        },
                        sort_keys=True,
                        indent=2,
                    )
                )
                return 0
        assert request_id is not None
        with Session(engine) as session:
            queued_request = session.get(OperationalJobRequest, request_id)
            if queued_request is None:
                raise ValueError("The requested manual operation was not found.")
            if queued_request.job_name not in JOB_DOMAINS:
                raise ValueError("The queued operation is not allowlisted.")
            recoverable = (
                queued_request.status == "RUNNING"
                and queued_request.started_at is not None
                and datetime.now(UTC) - queued_request.started_at > JOB_STALE_AFTER
            )
            if queued_request.status != "QUEUED" and not recoverable:
                raise ValueError("Only a queued or recoverable interrupted request can run.")
            if queued_request.job_name == "WORKBOOK_SYNC" and not settings.workbook_sync_enabled:
                raise ValueError("Workbook synchronization is disabled in this environment.")
        result = process_manual_job_requests(engine, settings, request_id=request_id)
        print(json.dumps(_summary(result, request_id), sort_keys=True, indent=2))
        return 0 if result.get("status") in {"SUCCEEDED", "PARTIAL", "BLOCKED"} else 1
    except (DatabaseWriteTargetError, ValueError) as error:
        print(f"MANUAL_OPERATION_FAILED: {error}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
