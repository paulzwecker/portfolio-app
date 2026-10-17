"""Allowlisted, durable requests for existing background operations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    CurrentLifecycle,
    Lifecycle,
    LifecycleEvent,
    OperationalJobAttempt,
    OperationalJobRequest,
)

JOB_DOMAINS: dict[str, list[str]] = {
    "MARKET_DATA": ["MARKET_DATA", "CORPORATE_ACTIONS"],
    "FX": ["FX"],
    "MARKET_AND_FX": ["MARKET_DATA", "CORPORATE_ACTIONS", "FX"],
    "SEC_FUNDAMENTALS": ["REPORTED_FUNDAMENTALS"],
    "SEC_FILINGS": ["SOURCE_DOCUMENTS"],
    "SHEETS_DISCOVERY": ["MODEL_SYNC", "RESEARCH_SYNC", "RISK_SYNC", "ACKNOWLEDGMENTS"],
    "RESEARCH_REFRESH": ["RESEARCH_TRIGGERS", "RESEARCH_QUEUE"],
    "AGENT_WORK_FEED": ["AGENT_WORK_FEED"],
    "COMPANY_REFRESH": [
        "MARKET_DATA",
        "CORPORATE_ACTIONS",
        "FX",
        "REPORTED_FUNDAMENTALS",
        "SOURCE_DOCUMENTS",
        "RESEARCH_TRIGGERS",
        "RESEARCH_QUEUE",
    ],
    "REFRESH_ALL": [
        "MARKET_DATA",
        "CORPORATE_ACTIONS",
        "FX",
        "REPORTED_FUNDAMENTALS",
        "SOURCE_DOCUMENTS",
        "MODEL_SYNC",
        "RESEARCH_SYNC",
        "RISK_SYNC",
        "ACKNOWLEDGMENTS",
        "RESEARCH_TRIGGERS",
        "RESEARCH_QUEUE",
        "AGENT_WORK_FEED",
    ],
}

GLOBAL_ONLY = {"SHEETS_DISCOVERY", "AGENT_WORK_FEED", "REFRESH_ALL"}
COMPANY_ONLY = {"COMPANY_REFRESH"}
MAX_ACTIVE_REQUESTS = 8
MANUAL_QUEUE_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"portfolio-manual-operational-job-queue").digest()[:8],
    "big",
    signed=True,
)
COOLDOWN = {
    "MARKET_DATA": timedelta(minutes=5),
    "FX": timedelta(minutes=5),
    "MARKET_AND_FX": timedelta(minutes=5),
    "SEC_FUNDAMENTALS": timedelta(minutes=15),
    "SEC_FILINGS": timedelta(minutes=15),
    "SHEETS_DISCOVERY": timedelta(minutes=3),
    "RESEARCH_REFRESH": timedelta(minutes=3),
    "AGENT_WORK_FEED": timedelta(minutes=5),
    "COMPANY_REFRESH": timedelta(minutes=10),
    "REFRESH_ALL": timedelta(minutes=10),
}


def _fingerprint(job_name: str, scope_kind: str, company_id: UUID | None) -> str:
    value = json.dumps(
        {"job_name": job_name, "scope_kind": scope_kind, "company_id": str(company_id or "")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_job_request(
    session: Session,
    value: s.OperationalJobRequestCreate,
    *,
    now_at: datetime | None = None,
    retry_of: OperationalJobRequest | None = None,
    bypass_cooldown: bool = False,
) -> tuple[OperationalJobRequest, bool]:
    now = now_at or datetime.now(UTC)
    job_name = value.job_name
    scope_kind = value.scope_kind
    company_id = value.company_id
    if job_name not in JOB_DOMAINS:
        raise ValueError("This operation is not available for manual refresh.")
    if job_name in GLOBAL_ONLY and scope_kind != "ACTIVE_UNIVERSE":
        raise ValueError("This operation is available only for the active universe.")
    if job_name in COMPANY_ONLY and scope_kind != "COMPANY":
        raise ValueError("This operation requires a company scope.")
    if (scope_kind == "COMPANY") != (company_id is not None):
        raise ValueError("Choose one active company for a company-scoped refresh.")

    company_name = None
    lifecycle = None
    scope_detail: dict[str, object] = {"scope_kind": scope_kind}
    if company_id is not None:
        identity = session.execute(
            select(Company, LifecycleEvent.new_state)
            .join(CurrentLifecycle, CurrentLifecycle.company_id == Company.id)
            .join(LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id)
            .where(Company.id == company_id)
        ).one_or_none()
        if identity is None:
            raise ValueError("The company was not found in the canonical universe.")
        company, lifecycle = identity
        if lifecycle not in {"PORTFOLIO", "WATCHLIST"}:
            raise ValueError("Company-scoped refresh is limited to Portfolio and Watchlist.")
        company_name = company.name
        scope_detail.update(
            {"company_id": str(company_id), "company_name": company_name, "lifecycle": lifecycle}
        )

    fingerprint = _fingerprint(job_name, scope_kind, company_id)
    if session.get_bind().dialect.name == "postgresql":
        # Serialize only queue creation, keeping concurrent submits within the
        # deduplication and queue-cap checks without a process-local mutex.
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": MANUAL_QUEUE_LOCK_ID},
        )
    if not bypass_cooldown:
        # Serialize equal requests to prevent concurrent clicks from creating
        # duplicate work. The queue lock above serializes these lookups.
        existing = session.scalar(
            select(OperationalJobRequest)
            .where(
                OperationalJobRequest.request_fingerprint == fingerprint,
                OperationalJobRequest.requested_at >= now - COOLDOWN[job_name],
            )
            .order_by(OperationalJobRequest.requested_at.desc())
            .limit(1)
        )
        if existing is not None:
            return existing, True
    active_count = session.scalar(
        select(func.count())
        .select_from(OperationalJobRequest)
        .where(OperationalJobRequest.status.in_(("QUEUED", "RUNNING")))
    )
    if (active_count or 0) >= MAX_ACTIVE_REQUESTS:
        raise ValueError("The manual refresh queue is full. Wait for queued work to finish.")

    request = OperationalJobRequest(
        id=uuid4(),
        job_name=job_name,
        scope_kind=scope_kind,
        company_id=company_id,
        company_name=company_name,
        lifecycle=lifecycle,
        requested_by="LOCAL_USER",
        request_fingerprint=fingerprint,
        status="QUEUED",
        requested_at=now,
        attempt_count=0,
        retry_of_id=retry_of.id if retry_of else None,
        affected_domains=list(JOB_DOMAINS[job_name]),
        scope_detail=scope_detail,
        result={"steps": []},
    )
    session.add(request)
    session.flush()
    return request, False


def retry_job_request(
    session: Session, request_id: UUID, *, now_at: datetime | None = None
) -> OperationalJobRequest:
    if session.get_bind().dialect.name == "postgresql":
        lock_id = int.from_bytes(
            hashlib.sha256(f"manual-refresh-retry:{request_id}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
    original = session.get(OperationalJobRequest, request_id)
    if original is None:
        raise LookupError("Operational job request was not found.")
    if original.status not in {"FAILED", "PARTIAL", "BLOCKED"}:
        raise ValueError("Only completed failed, partial or blocked requests can be retried.")
    active = session.scalar(
        select(OperationalJobRequest.id).where(
            OperationalJobRequest.retry_of_id == original.id,
            OperationalJobRequest.status.in_(("QUEUED", "RUNNING")),
        )
    )
    if active is not None:
        raise ValueError("A retry of this request is already queued or running.")
    request, _ = create_job_request(
        session,
        s.OperationalJobRequestCreate(
            job_name=cast(s.OperationalJobName, original.job_name),
            scope_kind=cast(s.OperationalJobScope, original.scope_kind),
            company_id=original.company_id,
        ),
        now_at=now_at,
        retry_of=original,
        bypass_cooldown=True,
    )
    return request


def job_request_read(
    session: Session,
    request: OperationalJobRequest,
    *,
    deduplicated: bool = False,
) -> s.OperationalJobRequestRead:
    attempts = list(
        session.scalars(
            select(OperationalJobAttempt)
            .where(OperationalJobAttempt.request_id == request.id)
            .order_by(OperationalJobAttempt.started_at, OperationalJobAttempt.id)
        )
    )
    return s.OperationalJobRequestRead(
        id=request.id,
        job_name=cast(s.OperationalJobName, request.job_name),
        scope_kind=cast(s.OperationalJobScope, request.scope_kind),
        company_id=request.company_id,
        company_name=request.company_name,
        lifecycle=cast(Lifecycle | None, request.lifecycle),
        requested_by=cast(s.OperationalJobActor, request.requested_by),
        status=cast(s.OperationalJobStatus, request.status),
        requested_at=request.requested_at,
        started_at=request.started_at,
        finished_at=request.finished_at,
        next_attempt_at=request.next_attempt_at,
        attempt_count=request.attempt_count,
        retry_of_id=request.retry_of_id,
        affected_domains=request.affected_domains,
        scope_detail=request.scope_detail,
        result=request.result,
        error_code=request.error_code,
        error_message=request.error_message,
        retry_available=request.status in {"FAILED", "PARTIAL", "BLOCKED"},
        deduplicated=deduplicated,
        cooldown_until=request.requested_at + COOLDOWN[request.job_name],
        attempts=[
            s.OperationalJobAttemptRead(
                id=item.id,
                attempt_number=item.attempt_number,
                step_name=item.step_name,
                status=cast(s.OperationalJobAttemptStatus, item.status),
                affected_domains=item.affected_domains,
                started_at=item.started_at,
                finished_at=item.finished_at,
                result=item.result,
                error_code=item.error_code,
                error_message=item.error_message,
            )
            for item in attempts
        ],
    )


def list_job_requests(session: Session, limit: int = 30) -> list[s.OperationalJobRequestRead]:
    requests = list(
        session.scalars(
            select(OperationalJobRequest)
            .order_by(OperationalJobRequest.requested_at.desc())
            .limit(limit)
        )
    )
    return [job_request_read(session, item) for item in requests]
