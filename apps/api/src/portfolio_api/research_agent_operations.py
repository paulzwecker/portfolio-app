"""Bounded role-specific work delivery and append-only external-agent receipts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from portfolio_api import external_ingestion
from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    GoogleSheetsResearchSyncCandidate,
    GoogleSheetsRiskSyncCandidate,
    GoogleSheetsSyncCandidate,
    Portfolio,
    ResearchAgentWorkEvent,
    ResearchQueueTaskType,
    ResearchTrigger,
)
from portfolio_api.research_queue import get_research_queue
from portfolio_api.research_triggers import list_research_triggers, research_trigger_context
from portfolio_api.settings import Settings
from portfolio_api.thesis_watch_sheet_sync import _context_payload

ACK_INBOX_TAB = "Application Agent Work Acknowledgment Inbox"
ACK_CONTRACT_VERSION = "1.0.0"
AGENT_ROLES = {
    "DATA_UNIVERSE_STEWARD",
    "PORTFOLIO_THESIS_SENTINEL",
    "MODEL_ALLOCATION_STEWARD",
}
SENTINEL_QUEUE_TYPES = {
    ResearchQueueTaskType.CANDIDATE_STAGE,
    ResearchQueueTaskType.THESIS_REVIEW,
    ResearchQueueTaskType.THESIS_QUESTION,
    ResearchQueueTaskType.MATERIAL_EVIDENCE,
}
MODEL_QUEUE_TYPES = {
    ResearchQueueTaskType.MODEL_REUNDERWRITE,
    ResearchQueueTaskType.MODEL_INTEGRITY,
    ResearchQueueTaskType.WATCHLIST_READINESS,
}


class ResearchAgentOperationError(Exception):
    def __init__(self, detail: str, status: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ResearchAgentOperationError("as_of must include a timezone offset", 422)
    return value.astimezone(UTC)


def _delivery_key(role: str, work_type: str, work_key: str, fingerprint: str, channel: str) -> str:
    return "delivery:" + _sha256(f"{role}|{work_type}|{work_key}|{fingerprint}|{channel}")


def _latest_ack(session: Session, delivery_id: UUID) -> ResearchAgentWorkEvent | None:
    return session.scalar(
        select(ResearchAgentWorkEvent)
        .where(
            ResearchAgentWorkEvent.delivery_id == delivery_id,
            ResearchAgentWorkEvent.event_type.not_in(("DELIVERY_SUCCEEDED", "DELIVERY_FAILED")),
        )
        .order_by(ResearchAgentWorkEvent.recorded_at.desc(), ResearchAgentWorkEvent.id.desc())
        .limit(1)
    )


def _record_delivery(
    session: Session,
    *,
    role: str,
    work_type: str,
    work_key: str,
    fingerprint: str,
    channel: str,
    payload: dict[str, object],
    recorded_at: datetime,
    delivery_id: UUID | None = None,
) -> ResearchAgentWorkEvent:
    idempotency_key = _delivery_key(role, work_type, work_key, fingerprint, channel)
    existing = session.scalar(
        select(ResearchAgentWorkEvent).where(
            ResearchAgentWorkEvent.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if existing.event_type != "DELIVERY_SUCCEEDED":
            raise ResearchAgentOperationError("Delivery idempotency key has conflicting content")
        return existing
    event_id = delivery_id or uuid4()
    inserted_id = session.scalar(
        pg_insert(ResearchAgentWorkEvent)
        .values(
            id=event_id,
            agent_role=role,
            work_type=work_type,
            work_key=work_key,
            work_fingerprint=fingerprint,
            channel=channel,
            event_type="DELIVERY_SUCCEEDED",
            idempotency_key=idempotency_key,
            content_fingerprint=_sha256(_canonical(payload)),
            observed_at=recorded_at,
            recorded_at=recorded_at,
        )
        .on_conflict_do_nothing(index_elements=[ResearchAgentWorkEvent.idempotency_key])
        .returning(ResearchAgentWorkEvent.id)
    )
    if inserted_id is None:
        existing = session.scalar(
            select(ResearchAgentWorkEvent).where(
                ResearchAgentWorkEvent.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise ResearchAgentOperationError("Could not reconcile concurrent work delivery")
        return existing
    event = session.get(ResearchAgentWorkEvent, inserted_id)
    if event is None:
        raise ResearchAgentOperationError("Could not read back the work delivery receipt")
    return event


def _work_item(
    session: Session,
    *,
    role: str,
    work_type: str,
    work_key: str,
    fingerprint_source: object,
    payload: dict[str, object],
    channel: str,
    recorded_at: datetime,
    record_delivery: bool = True,
) -> s.ResearchAgentWorkItemRead | None:
    fingerprint = _sha256(_canonical(fingerprint_source))
    idempotency_key = _delivery_key(role, work_type, work_key, fingerprint, channel)
    delivery = session.scalar(
        select(ResearchAgentWorkEvent).where(
            ResearchAgentWorkEvent.idempotency_key == idempotency_key
        )
    )
    if delivery is None and record_delivery:
        delivery = _record_delivery(
            session,
            role=role,
            work_type=work_type,
            work_key=work_key,
            fingerprint=fingerprint,
            channel=channel,
            payload=payload,
            recorded_at=recorded_at,
        )
    delivery_id = delivery.id if delivery is not None else uuid5(NAMESPACE_URL, idempotency_key)
    latest = _latest_ack(session, delivery_id) if delivery is not None else None
    if latest is not None and latest.event_type == "COMPLETED":
        return None
    current_status = latest.event_type if latest is not None else "DELIVERED"
    payload_with_identity = {
        **payload,
        "work_identity": {
            "agent_role": role,
            "work_type": work_type,
            "work_key": work_key,
            "work_fingerprint": fingerprint,
            "delivery_channel": channel,
        },
        "acknowledgment_contract": {
            "contract_type": "ResearchAgentAcknowledgmentContractV1",
            "contract_version": ACK_CONTRACT_VERSION,
            "delivery_channel": channel,
        },
    }
    return s.ResearchAgentWorkItemRead(
        delivery_id=delivery_id,
        work_type=work_type,
        work_key=work_key,
        work_fingerprint=fingerprint,
        delivery_channel=channel,
        delivered_at=delivery.recorded_at if delivery is not None else recorded_at,
        current_status=cast(
            Literal[
                "DELIVERED",
                "ACKNOWLEDGED",
                "IN_PROGRESS",
                "COMPLETED",
                "BLOCKED",
                "SOURCE_UNAVAILABLE",
                "STALE_SOURCE",
                "UNRESOLVED_REVIEW",
            ],
            current_status,
        ),
        current_reason=latest.reason if latest is not None else None,
        payload=payload_with_identity,
    )


def _queue_payload(task: s.ResearchQueueTask) -> dict[str, object]:
    return cast(dict[str, object], task.model_dump(mode="json"))


def _data_work(
    session: Session,
    *,
    role: str,
    request: s.ResearchAgentWorkRequest,
    cutoff: datetime,
    channel: str,
) -> tuple[list[s.ResearchAgentWorkItemRead], str | None]:
    report = external_ingestion.status_report(session, now_at=cutoff)
    domains = cast(list[dict[str, Any]], report["domains"])
    failures = cast(list[dict[str, Any]], report["recent_failures"])
    items: list[s.ResearchAgentWorkItemRead] = []
    for domain in domains:
        domain_id = f"{domain['provider_id']}:{domain['domain']}"
        stable = {
            key: domain.get(key)
            for key in (
                "provider_id",
                "domain",
                "cadence",
                "freshness_max_age_hours",
                "freshness",
                "latest_run",
            )
        }
        if isinstance(stable.get("latest_run"), dict):
            latest = cast(dict[str, Any], stable["latest_run"])
            stable["latest_run"] = {key: latest.get(key) for key in ("status", "failure_code")}
        related_failures = [
            failure for failure in failures if failure.get("domain") == domain["domain"]
        ]
        queue_payload: dict[str, object] = {
            "domain_status": domain,
            "recent_failures": related_failures,
            "allowed_work": [
                "review provider freshness and mappings",
                "run bounded documented ingestion operations",
                "publish factual changes through supported ingestion contracts",
                "record unavailable sources or unresolved mappings explicitly",
            ],
        }
        item = _work_item(
            session,
            role=role,
            work_type="DATA_DOMAIN",
            work_key=domain_id,
            fingerprint_source=stable,
            payload=queue_payload,
            channel=channel,
            recorded_at=cutoff,
            record_delivery=channel == "API",
        )
        if item is not None:
            items.append(item)
    needs_attention = any(
        str(domain.get("freshness")) not in {"FRESH", "NOT_APPLICABLE"} for domain in domains
    ) or bool(failures)
    return items, None if needs_attention else "All configured domains are fresh or not applicable."


def _sentinel_work(
    session: Session,
    *,
    role: str,
    request: s.ResearchAgentWorkRequest,
    cutoff: datetime,
    channel: str,
) -> list[s.ResearchAgentWorkItemRead]:
    trigger_result = list_research_triggers(
        session,
        as_of=cutoff,
        processing_state="OPEN",
        limit=request.limit,
        offset=request.offset,
    )
    trigger_source_ids = {trigger.source_record_id for trigger in trigger_result.triggers}
    items: list[s.ResearchAgentWorkItemRead] = []
    for trigger in trigger_result.triggers:
        context = research_trigger_context(session, trigger.id)
        sanitized_context = _context_payload(context)
        payload: dict[str, object] = {
            "trigger": cast(dict[str, object], trigger.model_dump(mode="json")),
            "context": sanitized_context,
            "proposal_interfaces": {
                "research_and_thesis": "/v1/google-sheets-research-sync",
                "model": "/v1/google-sheets-sync",
                "acceptance": "explicit reviewer action required",
            },
        }
        item = _work_item(
            session,
            role=role,
            work_type="TRIGGER",
            work_key=str(trigger.id),
            fingerprint_source=sanitized_context,
            payload=payload,
            channel=channel,
            recorded_at=cutoff,
            record_delivery=channel == "API",
        )
        if item is not None:
            items.append(item)

    queue = get_research_queue(session, as_of=cutoff)
    for task in queue.tasks:
        if task.task_type not in SENTINEL_QUEUE_TYPES:
            continue
        if any(source.source_record_id in trigger_source_ids for source in task.sources):
            continue
        queue_payload: dict[str, object] = {
            "task": _queue_payload(task),
            "completion_endpoint": f"/v1/research-queue/{task.task_id}/complete",
            "completion_contract": "ResearchQueueCompletionCreate",
        }
        item = _work_item(
            session,
            role=role,
            work_type="QUEUE_TASK",
            work_key=task.task_id,
            fingerprint_source={
                "task_id": task.task_id,
                "condition_fingerprint": task.condition_fingerprint,
            },
            payload=queue_payload,
            channel=channel,
            recorded_at=cutoff,
            record_delivery=channel == "API",
        )
        if item is not None:
            items.append(item)
    return items[: request.limit]


def _model_work(
    session: Session,
    *,
    role: str,
    request: s.ResearchAgentWorkRequest,
    cutoff: datetime,
    channel: str,
) -> tuple[list[s.ResearchAgentWorkItemRead], str | None]:
    portfolio = session.get(Portfolio, request.portfolio_id) if request.portfolio_id else None
    if request.portfolio_id is not None and portfolio is None:
        raise ResearchAgentOperationError("The requested portfolio was not found", 404)
    if portfolio is None:
        portfolios = list(session.scalars(select(Portfolio).order_by(Portfolio.name)))
        if len(portfolios) != 1:
            reason = (
                "No portfolio is configured."
                if not portfolios
                else "portfolio_id is required when more than one portfolio exists."
            )
            return [], reason
        portfolio = portfolios[0]
    overview = q.overview(session, portfolio.id, as_of=cutoff)
    overview_payload = cast(dict[str, object], overview.model_dump(mode="json"))
    # The view is point-in-time; the delivery fingerprint omits its query cutoff so
    # a repeated retrieval of unchanged state is idempotent.
    stable_overview = dict(overview_payload)
    stable_overview.pop("valuation_as_of", None)
    stable_overview.pop("holdings_age_days", None)
    overview_fingerprint = _sha256(_canonical(stable_overview))
    state_payload: dict[str, object] = {
        "portfolio_id": str(portfolio.id),
        "portfolio_overview": overview_payload,
        "allocation_boundary": (
            "Review and propose through existing controls; do not change targets or holdings."
        ),
        "proposal_interfaces": {
            "model": "/v1/google-sheets-sync",
            "risk": "/v1/google-sheets-risk-sync",
            "target_architecture": "investor-reviewed portfolio target workflow",
        },
    }
    items: list[s.ResearchAgentWorkItemRead] = []
    state_item = _work_item(
        session,
        role=role,
        work_type="PORTFOLIO_STATE",
        work_key=str(portfolio.id),
        fingerprint_source={"portfolio_id": str(portfolio.id), "state": overview_fingerprint},
        payload=state_payload,
        channel=channel,
        recorded_at=cutoff,
        record_delivery=channel == "API",
    )
    if state_item is not None:
        items.append(state_item)

    queue = get_research_queue(session, as_of=cutoff)
    for task in queue.tasks:
        if task.task_type not in MODEL_QUEUE_TYPES:
            continue
        payload: dict[str, object] = {
            "task": _queue_payload(task),
            "proposal_interfaces": {
                "model_sync": "/v1/google-sheets-sync",
                "model_acceptance": "explicit reviewer action required",
                "target_changes": "never automatic",
            },
        }
        item = _work_item(
            session,
            role=role,
            work_type="QUEUE_TASK",
            work_key=task.task_id,
            fingerprint_source={
                "task_id": task.task_id,
                "condition_fingerprint": task.condition_fingerprint,
            },
            payload=payload,
            channel=channel,
            recorded_at=cutoff,
            record_delivery=channel == "API",
        )
        if item is not None:
            items.append(item)
    return items[: request.limit], None


def deliver_agent_work(
    session: Session,
    role: str,
    request: s.ResearchAgentWorkRequest,
    *,
    channel: str = "API",
) -> s.ResearchAgentWorkContractV1:
    if role not in AGENT_ROLES:
        raise ResearchAgentOperationError("Unsupported research-agent role", 422)
    if channel not in {"API", "GOOGLE_SHEETS"}:
        raise ResearchAgentOperationError("Unsupported research-agent delivery channel", 422)
    cutoff = _aware(request.as_of or datetime.now(UTC))
    if role == "DATA_UNIVERSE_STEWARD":
        items, no_work_reason = _data_work(
            session, role=role, request=request, cutoff=cutoff, channel=channel
        )
    elif role == "PORTFOLIO_THESIS_SENTINEL":
        items = _sentinel_work(session, role=role, request=request, cutoff=cutoff, channel=channel)
        no_work_reason = None
    else:
        items, no_work_reason = _model_work(
            session, role=role, request=request, cutoff=cutoff, channel=channel
        )
    if items:
        status: Literal["AVAILABLE", "NO_WORK", "BLOCKED"] = "AVAILABLE"
    elif no_work_reason and role == "MODEL_ALLOCATION_STEWARD":
        status = "BLOCKED"
    else:
        status = "NO_WORK"
    return s.ResearchAgentWorkContractV1(
        agent_role=cast(s.ResearchAgentRoleValue, role),
        as_of=cutoff,
        status=status,
        status_reason=no_work_reason,
        items=items,
    )


def record_sheet_agent_work_deliveries(
    session: Session, contract: s.ResearchAgentWorkContractV1, published_at: datetime
) -> int:
    """Record Sheets deliveries only after the publisher has verified the write by read-back."""
    if contract.items and contract.items[0].delivery_channel != "GOOGLE_SHEETS":
        raise ResearchAgentOperationError("Agent work contract is not a Sheets delivery", 409)
    for item in contract.items:
        if item.delivery_channel != "GOOGLE_SHEETS":
            raise ResearchAgentOperationError("Mixed agent work delivery channels are invalid", 409)
        _record_delivery(
            session,
            role=contract.agent_role,
            work_type=item.work_type,
            work_key=item.work_key,
            fingerprint=item.work_fingerprint,
            channel="GOOGLE_SHEETS",
            payload=item.payload,
            recorded_at=published_at,
            delivery_id=item.delivery_id,
        )
    return len(contract.items)


def _proposal_status(
    session: Session, value: s.ResearchAgentAcknowledgmentContractV1
) -> str | None:
    if value.proposal_candidate_id is None or value.proposal_domain is None:
        return None
    if value.proposal_domain == "MODEL":
        model_candidate = session.get(GoogleSheetsSyncCandidate, value.proposal_candidate_id)
        status = model_candidate.status if model_candidate else None
    elif value.proposal_domain in {"RESEARCH", "THESIS"}:
        research_candidate = session.get(
            GoogleSheetsResearchSyncCandidate, value.proposal_candidate_id
        )
        if research_candidate is not None and research_candidate.domain != value.proposal_domain:
            raise ResearchAgentOperationError("The referenced proposal domain does not match", 409)
        status = research_candidate.status if research_candidate else None
    else:
        risk_candidate = session.get(GoogleSheetsRiskSyncCandidate, value.proposal_candidate_id)
        status = risk_candidate.status if risk_candidate else None
    if status is None:
        raise ResearchAgentOperationError("The referenced proposal candidate was not found", 409)
    return str(status)


def record_agent_acknowledgment(
    session: Session, value: s.ResearchAgentAcknowledgmentContractV1
) -> s.ResearchAgentAcknowledgmentResult:
    external_id = value.external_update_id
    contract_data = cast(dict[str, object], value.model_dump(mode="json"))
    content_fingerprint = _sha256(_canonical(contract_data))
    existing = session.scalar(
        select(ResearchAgentWorkEvent).where(
            ResearchAgentWorkEvent.external_update_id == external_id
        )
    )
    if existing is not None:
        if existing.content_fingerprint != content_fingerprint:
            raise ResearchAgentOperationError(
                "This external_update_id was already used for different acknowledgment content"
            )
        return s.ResearchAgentAcknowledgmentResult(
            result="ALREADY_RECORDED", acknowledgment=_ack_read(session, existing)
        )

    delivery = session.scalar(
        select(ResearchAgentWorkEvent).where(
            ResearchAgentWorkEvent.agent_role == value.agent_role,
            ResearchAgentWorkEvent.work_type == value.work_type,
            ResearchAgentWorkEvent.work_key == value.work_key,
            ResearchAgentWorkEvent.work_fingerprint == value.work_fingerprint,
            ResearchAgentWorkEvent.channel == value.delivery_channel,
            ResearchAgentWorkEvent.event_type == "DELIVERY_SUCCEEDED",
        )
    )
    if delivery is None:
        raise ResearchAgentOperationError(
            "Acknowledgment has no matching successful delivery receipt"
        )
    latest_delivery = session.scalar(
        select(ResearchAgentWorkEvent)
        .where(
            ResearchAgentWorkEvent.agent_role == value.agent_role,
            ResearchAgentWorkEvent.work_type == value.work_type,
            ResearchAgentWorkEvent.work_key == value.work_key,
            ResearchAgentWorkEvent.channel == value.delivery_channel,
            ResearchAgentWorkEvent.event_type == "DELIVERY_SUCCEEDED",
        )
        .order_by(ResearchAgentWorkEvent.recorded_at.desc(), ResearchAgentWorkEvent.id.desc())
        .limit(1)
    )
    status = value.status
    reason = value.reason
    blocker_code = value.blocker_code
    if latest_delivery is not None and latest_delivery.work_fingerprint != value.work_fingerprint:
        status = "STALE_SOURCE"
        reason = (
            "Canonical work changed after this delivery; review the latest delivery "
            "before completion."
        )
        blocker_code = "STALE_DELIVERY"
    proposal_status = _proposal_status(session, value)
    idempotency_key = "ack:" + _sha256(external_id)
    inserted_id = session.scalar(
        pg_insert(ResearchAgentWorkEvent)
        .values(
            id=uuid4(),
            delivery_id=delivery.id,
            agent_role=value.agent_role,
            work_type=value.work_type,
            work_key=value.work_key,
            work_fingerprint=value.work_fingerprint,
            channel=value.delivery_channel,
            event_type=status,
            idempotency_key=idempotency_key,
            content_fingerprint=content_fingerprint,
            external_update_id=external_id,
            agent_run_id=value.agent_run_id,
            actor_id=value.actor_id,
            proposal_domain=value.proposal_domain,
            proposal_candidate_id=value.proposal_candidate_id,
            source_reference=str(value.source_reference) if value.source_reference else None,
            blocker_code=blocker_code,
            reason=reason,
            observed_at=value.observed_at,
            recorded_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=[ResearchAgentWorkEvent.idempotency_key])
        .returning(ResearchAgentWorkEvent.id)
    )
    if inserted_id is None:
        concurrent = session.scalar(
            select(ResearchAgentWorkEvent).where(
                ResearchAgentWorkEvent.external_update_id == external_id
            )
        )
        if concurrent is None or concurrent.content_fingerprint != content_fingerprint:
            raise ResearchAgentOperationError(
                "This external_update_id was already used for different acknowledgment content"
            )
        return s.ResearchAgentAcknowledgmentResult(
            result="ALREADY_RECORDED", acknowledgment=_ack_read(session, concurrent)
        )
    event = session.get(ResearchAgentWorkEvent, inserted_id)
    if event is None:
        raise ResearchAgentOperationError("Could not read back the acknowledgment receipt")
    read = _ack_read(session, event)
    read.proposal_status = proposal_status
    return s.ResearchAgentAcknowledgmentResult(result="RECORDED", acknowledgment=read)


def _ack_read(session: Session, event: ResearchAgentWorkEvent) -> s.ResearchAgentAcknowledgmentRead:
    delivery = session.get(ResearchAgentWorkEvent, event.delivery_id) if event.delivery_id else None
    return s.ResearchAgentAcknowledgmentRead(
        id=event.id,
        delivery_id=event.delivery_id or UUID(int=0),
        agent_role=event.agent_role,
        work_type=event.work_type,
        work_key=event.work_key,
        work_fingerprint=event.work_fingerprint,
        delivery_channel=delivery.channel if delivery is not None else event.channel,
        external_update_id=event.external_update_id or "",
        agent_run_id=event.agent_run_id or "",
        actor_id=event.actor_id or "",
        status=event.event_type,
        observed_at=event.observed_at or event.recorded_at,
        recorded_at=event.recorded_at,
        reason=event.reason,
        blocker_code=event.blocker_code,
        source_reference=event.source_reference,
        proposal_domain=event.proposal_domain,
        proposal_candidate_id=event.proposal_candidate_id,
        proposal_status=_proposal_status_from_delivery(session, event) if delivery else None,
    )


def _proposal_status_from_delivery(session: Session, event: ResearchAgentWorkEvent) -> str | None:
    if event.proposal_candidate_id is None or event.proposal_domain is None:
        return None
    if event.proposal_domain == "MODEL":
        model_candidate = session.get(GoogleSheetsSyncCandidate, event.proposal_candidate_id)
        status = model_candidate.status if model_candidate is not None else None
    elif event.proposal_domain in {"RESEARCH", "THESIS"}:
        research_candidate = session.get(
            GoogleSheetsResearchSyncCandidate, event.proposal_candidate_id
        )
        status = research_candidate.status if research_candidate is not None else None
    else:
        risk_candidate = session.get(GoogleSheetsRiskSyncCandidate, event.proposal_candidate_id)
        status = risk_candidate.status if risk_candidate is not None else None
    return str(status) if status is not None else "NOT_FOUND"


def work_event_read(row: ResearchAgentWorkEvent) -> s.ResearchAgentWorkEventRead:
    return s.ResearchAgentWorkEventRead(
        id=row.id,
        delivery_id=row.delivery_id,
        agent_role=row.agent_role,
        work_type=row.work_type,
        work_key=row.work_key,
        work_fingerprint=row.work_fingerprint,
        channel=row.channel,
        event_type=row.event_type,
        reason=row.reason,
        blocker_code=row.blocker_code,
        external_update_id=row.external_update_id,
        proposal_domain=row.proposal_domain,
        proposal_candidate_id=row.proposal_candidate_id,
        recorded_at=row.recorded_at,
    )


def list_agent_events(
    session: Session, *, role: str | None = None, work_key: str | None = None, limit: int = 100
) -> list[s.ResearchAgentWorkEventRead]:
    query = select(ResearchAgentWorkEvent)
    if role is not None:
        if role not in AGENT_ROLES:
            raise ResearchAgentOperationError("Unsupported research-agent role", 422)
        query = query.where(ResearchAgentWorkEvent.agent_role == role)
    if work_key is not None:
        query = query.where(ResearchAgentWorkEvent.work_key == work_key)
    rows = session.scalars(
        query.order_by(
            ResearchAgentWorkEvent.recorded_at.desc(), ResearchAgentWorkEvent.id.desc()
        ).limit(limit)
    )
    return [work_event_read(row) for row in rows]


def proposal_status(
    session: Session,
    domain: s.ResearchAgentProposalDomain,
    candidate_id: UUID,
) -> s.ResearchAgentProposalStatusRead:
    if domain == "MODEL":
        model_candidate = session.get(GoogleSheetsSyncCandidate, candidate_id)
        if model_candidate is None:
            raise ResearchAgentOperationError("The model proposal was not found", 404)
        values = {
            "status": model_candidate.status,
            "issue": model_candidate.issue,
            "external_revision_id": model_candidate.external_revision_id,
            "base_revision_id": model_candidate.base_revision_id,
            "accepted_revision_id": model_candidate.accepted_revision_id,
            "reviewer": model_candidate.reviewer,
            "reviewer_note": model_candidate.decision_note,
            "accepted_at": model_candidate.accepted_at,
            "rejected_at": model_candidate.rejected_at,
            "last_observed_at": model_candidate.last_observed_at,
        }
    elif domain in {"RESEARCH", "THESIS"}:
        research_candidate = session.get(GoogleSheetsResearchSyncCandidate, candidate_id)
        if research_candidate is None or research_candidate.domain != domain:
            raise ResearchAgentOperationError("The research proposal was not found", 404)
        values = {
            "status": research_candidate.status,
            "issue": research_candidate.issue,
            "external_revision_id": research_candidate.external_revision_id,
            "base_revision_id": research_candidate.base_revision_id,
            "accepted_revision_id": (
                research_candidate.accepted_research_revision_id
                if domain == "RESEARCH"
                else research_candidate.accepted_thesis_revision_id
            ),
            "reviewer": research_candidate.reviewer,
            "reviewer_note": research_candidate.reviewer_note,
            "accepted_at": research_candidate.accepted_at,
            "rejected_at": research_candidate.rejected_at,
            "last_observed_at": research_candidate.last_observed_at,
        }
    else:
        risk_candidate = session.get(GoogleSheetsRiskSyncCandidate, candidate_id)
        if risk_candidate is None:
            raise ResearchAgentOperationError("The risk proposal was not found", 404)
        values = {
            "status": risk_candidate.status,
            "issue": risk_candidate.issue,
            "external_revision_id": risk_candidate.external_revision_id,
            "base_revision_id": None,
            "accepted_revision_id": risk_candidate.accepted_revision_id,
            "reviewer": risk_candidate.reviewer,
            "reviewer_note": risk_candidate.reviewer_note,
            "accepted_at": risk_candidate.accepted_at,
            "rejected_at": risk_candidate.rejected_at,
            "last_observed_at": risk_candidate.last_observed_at,
        }
    return s.ResearchAgentProposalStatusRead(
        proposal_domain=domain,
        proposal_candidate_id=candidate_id,
        **values,
    )


def run_acknowledgment_inbox_check(
    session: Session,
    settings: Settings,
    reader: Any | None = None,
) -> s.ResearchAgentAcknowledgmentSyncRead:
    from portfolio_api.google_sheets_sync import GoogleSheetsApiReader, GoogleSheetsSyncError

    checked_at = datetime.now(UTC)
    issues: list[dict[str, object]] = []
    captured = replayed = invalid = blocked = 0
    if not settings.google_sheets_spreadsheet_id:
        return s.ResearchAgentAcknowledgmentSyncRead(
            status="BLOCKED",
            spreadsheet_title=None,
            tab=ACK_INBOX_TAB,
            checked_at=checked_at,
            captured=0,
            replayed=0,
            invalid=0,
            blocked=0,
            issues=[{"code": "NOT_CONFIGURED", "message": "Set GOOGLE_SHEETS_SPREADSHEET_ID"}],
        )
    client = reader or GoogleSheetsApiReader(settings)
    try:
        snapshot = client.read_inbox(settings.google_sheets_spreadsheet_id, ACK_INBOX_TAB)
    except GoogleSheetsSyncError as error:
        return s.ResearchAgentAcknowledgmentSyncRead(
            status="BLOCKED" if error.code == "SYNC_TAB_MISSING" else "FAILED",
            spreadsheet_title=None,
            tab=ACK_INBOX_TAB,
            checked_at=checked_at,
            captured=0,
            replayed=0,
            invalid=0,
            blocked=0,
            issues=[{"code": error.code, "message": str(error)}],
        )
    for block in snapshot.blocks:
        if block.issue:
            invalid += 1
            issues.append(
                {"code": "INVALID_BLOCK", "row": block.first_row_number, "message": block.issue}
            )
            continue
        try:
            value = s.ResearchAgentAcknowledgmentContractV1.model_validate_json(block.contract_text)
            if block.external_revision_id != value.external_update_id:
                raise ValueError("Inbox external revision ID must equal external_update_id")
            result = record_agent_acknowledgment(session, value)
            if result.result == "RECORDED":
                captured += 1
            else:
                replayed += 1
        except ResearchAgentOperationError as error:
            blocked += 1
            issues.append(
                {
                    "code": "ACKNOWLEDGMENT_BLOCKED",
                    "row": block.first_row_number,
                    "message": error.detail,
                }
            )
        except ValueError as error:
            invalid += 1
            issues.append(
                {
                    "code": "INVALID_ACKNOWLEDGMENT",
                    "row": block.first_row_number,
                    "message": str(error),
                }
            )
    status = (
        "FAILED"
        if invalid and not (captured or replayed or blocked)
        else "PARTIAL"
        if issues
        else "COMPLETE"
    )
    return s.ResearchAgentAcknowledgmentSyncRead(
        status=status,
        spreadsheet_title=snapshot.connection.spreadsheet_title,
        tab=ACK_INBOX_TAB,
        checked_at=checked_at,
        captured=captured,
        replayed=replayed,
        invalid=invalid,
        blocked=blocked,
        issues=issues,
    )


def record_delivery_failure(
    session: Session,
    *,
    role: str,
    work_type: str,
    work_key: str,
    fingerprint: str,
    attempt_id: str,
    channel: str,
    reason: str,
    observed_at: datetime | None = None,
) -> tuple[ResearchAgentWorkEvent, Literal["RECORDED", "ALREADY_RECORDED"]]:
    if role not in AGENT_ROLES:
        raise ResearchAgentOperationError("Unsupported research-agent role", 422)
    idempotency_key = "failed:" + _sha256(f"{role}|{work_type}|{work_key}|{attempt_id}")
    existing = session.scalar(
        select(ResearchAgentWorkEvent).where(
            ResearchAgentWorkEvent.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        content_fingerprint = _sha256(
            _canonical(
                {
                    "role": role,
                    "work_type": work_type,
                    "work_key": work_key,
                    "work_fingerprint": fingerprint,
                    "channel": channel,
                    "reason": reason,
                }
            )
        )
        if existing.content_fingerprint != content_fingerprint:
            raise ResearchAgentOperationError("Delivery attempt ID was reused with another failure")
        return existing, "ALREADY_RECORDED"
    content_fingerprint = _sha256(
        _canonical(
            {
                "role": role,
                "work_type": work_type,
                "work_key": work_key,
                "work_fingerprint": fingerprint,
                "channel": channel,
                "reason": reason,
            }
        )
    )
    inserted_id = session.scalar(
        pg_insert(ResearchAgentWorkEvent)
        .values(
            id=uuid4(),
            agent_role=role,
            work_type=work_type,
            work_key=work_key,
            work_fingerprint=fingerprint,
            channel=channel,
            event_type="DELIVERY_FAILED",
            idempotency_key=idempotency_key,
            content_fingerprint=content_fingerprint,
            reason=reason,
            observed_at=_aware(observed_at or datetime.now(UTC)),
            recorded_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=[ResearchAgentWorkEvent.idempotency_key])
        .returning(ResearchAgentWorkEvent.id)
    )
    if inserted_id is None:
        concurrent = session.scalar(
            select(ResearchAgentWorkEvent).where(
                ResearchAgentWorkEvent.idempotency_key == idempotency_key
            )
        )
        if concurrent is None or concurrent.content_fingerprint != content_fingerprint:
            raise ResearchAgentOperationError("Delivery attempt ID was reused with another failure")
        return concurrent, "ALREADY_RECORDED"
    event = session.get(ResearchAgentWorkEvent, inserted_id)
    if event is None:
        raise ResearchAgentOperationError("Could not read back the delivery failure receipt")
    return event, "RECORDED"


def record_portfolio_sheet_delivery(
    session: Session, result: s.GoogleSheetsPortfolioStatePublishRead
) -> None:
    if not result.read_back_verified:
        raise ResearchAgentOperationError("Portfolio state delivery has no successful read-back")
    fingerprint = result.content_fingerprint.removeprefix("sha256:")
    payload: dict[str, object] = {
        "portfolio_id": str(result.portfolio_id),
        "contract_version": result.contract_version,
        "content_fingerprint": result.content_fingerprint,
        "valuation_as_of": result.valuation_as_of.isoformat() if result.valuation_as_of else None,
        "valuation_status": result.valuation_status,
        "tab": result.tab,
    }
    _record_delivery(
        session,
        role="MODEL_ALLOCATION_STEWARD",
        work_type="PORTFOLIO_STATE",
        work_key=str(result.portfolio_id),
        fingerprint=fingerprint,
        channel="GOOGLE_SHEETS",
        payload=payload,
        recorded_at=result.published_at,
    )


def record_sheet_delivery_failure(
    session: Session,
    *,
    role: str,
    work_type: str,
    work_key: str,
    attempt_id: str,
    reason: str,
    fingerprint_source: object,
) -> None:
    record_delivery_failure(
        session,
        role=role,
        work_type=work_type,
        work_key=work_key,
        fingerprint=_sha256(_canonical(fingerprint_source)),
        attempt_id=attempt_id,
        channel="GOOGLE_SHEETS",
        reason=reason,
    )


def record_thesis_sheet_deliveries(
    session: Session, result: s.GoogleSheetsThesisWatchPublishRead
) -> int:
    """Record only trigger rows whose write and read-back succeeded in this request."""
    count = 0
    for raw_id in result.trigger_ids:
        try:
            trigger_id = UUID(raw_id)
            trigger = session.get(ResearchTrigger, trigger_id)
            if trigger is None:
                continue
            context = research_trigger_context(session, trigger_id)
        except (ValueError, ResearchAgentOperationError):
            continue
        payload = _context_payload(context)
        fingerprint = _sha256(_canonical(payload))
        _record_delivery(
            session,
            role="PORTFOLIO_THESIS_SENTINEL",
            work_type="TRIGGER",
            work_key=str(trigger.id),
            fingerprint=fingerprint,
            channel="GOOGLE_SHEETS",
            payload=payload,
            recorded_at=result.published_at,
        )
        count += 1
    return count
