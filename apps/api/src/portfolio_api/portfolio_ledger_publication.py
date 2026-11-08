"""Explicit, hash-bound whole-portfolio ledger publication into immutable snapshots."""

from datetime import UTC
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api import portfolio_ledger_reviews as reviews
from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import HoldingSnapshot, PortfolioLedgerPublication


def _latest(session: Session, portfolio_id: UUID) -> PortfolioLedgerPublication | None:
    return session.scalar(
        select(PortfolioLedgerPublication)
        .where(
            PortfolioLedgerPublication.portfolio_id == portfolio_id,
        )
        .order_by(PortfolioLedgerPublication.sequence.desc())
        .limit(1)
    )


def _snapshot(session: Session, row: HoldingSnapshot) -> s.SnapshotRead:
    value = queries.snapshot_read(session, row)
    return value.model_copy(
        update={
            "recorded_at": value.recorded_at.astimezone(UTC),
            "positions": sorted(value.positions, key=lambda p: str(p.listing_id)),
            "cash_positions": sorted(value.cash_positions, key=lambda p: p.currency),
        }
    )


def _plan_hash(plan: c.LedgerPublicationPreviewRead) -> str:
    return ledger._digest(
        plan.model_dump(
            mode="json", exclude={"plan_sha256", "confirmation_phrase", "publication_id", "status"}
        )
    )


def _confirmation(portfolio_id: UUID, candidate_id: UUID, plan_sha256: str) -> str:
    return f"PUBLISH LEDGER {portfolio_id}/{candidate_id}/{plan_sha256}"


def _request_hash(
    portfolio_id: UUID, candidate_id: UUID, command: c.LedgerPublicationCreate
) -> str:
    return ledger._digest(
        {
            "portfolio_id": str(portfolio_id),
            "candidate_id": str(candidate_id),
            "command": command.model_dump(mode="json"),
        }
    )


def _read(
    session: Session, row: PortfolioLedgerPublication, *, replayed: bool = False
) -> c.LedgerPublicationRead:
    try:
        plan = c.LedgerPublicationPreviewRead.model_validate(row.plan_data)
        command = c.LedgerPublicationCreate.model_validate(row.command_data)
    except ValidationError:
        raise services.DomainError(
            "Stored ledger publication failed integrity validation", status=409
        ) from None
    snapshot = session.get(HoldingSnapshot, row.holding_snapshot_id)
    if snapshot is None:
        raise services.DomainError("Published holdings snapshot is unavailable", status=409)
    view = _snapshot(session, snapshot)
    candidate = reviews.candidate_read(session, row.portfolio_id, row.candidate_id)
    review = candidate.review
    previous = (
        session.get(PortfolioLedgerPublication, row.previous_publication_id)
        if row.previous_publication_id
        else None
    )
    original_snapshot = session.get(HoldingSnapshot, plan.current_snapshot.id)
    if (
        original_snapshot is None
        or original_snapshot.portfolio_id != row.portfolio_id
        or ledger._digest(_snapshot(session, original_snapshot).model_dump(mode="json"))
        != plan.current_snapshot_sha256
        or ledger._digest(plan.current_snapshot.model_dump(mode="json"))
        != plan.current_snapshot_sha256
        or row.sequence != (previous.sequence + 1 if previous else 1)
        or (
            previous is None
            and (
                row.cutover_at != row.effective_at
                or plan.current_snapshot.id != row.anchor_snapshot_id
            )
        )
        or (
            previous is not None
            and (
                previous.portfolio_id != row.portfolio_id
                or previous.cutover_at != row.cutover_at
                or previous.holding_snapshot_id != plan.current_snapshot.id
            )
        )
        or candidate.anchor_snapshot_id != plan.anchor_snapshot_id
        or candidate.packet.anchor_sha256 != plan.anchor_sha256
        or sorted((a.account_id for a in candidate.packet.accounts), key=str) != plan.account_ids
    ):
        raise services.DomainError(
            "Stored ledger publication lineage failed integrity validation", status=409
        )
    if (
        plan.status != "READY"
        or plan.publication_id is not None
        or plan.portfolio_id != row.portfolio_id
        or plan.candidate_id != row.candidate_id
        or plan.review_id != row.review_id
        or plan.previous_publication_id != row.previous_publication_id
        or plan.anchor_snapshot_id != row.anchor_snapshot_id
        or plan.cutover_at != row.cutover_at
        or plan.effective_at != row.effective_at
        or plan.plan_sha256 != row.plan_sha256
        or _plan_hash(plan) != row.plan_sha256
        or plan.confirmation_phrase
        != _confirmation(row.portfolio_id, row.candidate_id, row.plan_sha256)
        or command.expected_plan_sha256 != row.plan_sha256
        or command.expected_previous_publication_id != row.previous_publication_id
        or command.confirmation != plan.confirmation_phrase
        or _request_hash(row.portfolio_id, row.candidate_id, command) != row.request_sha256
        or view.portfolio_id != row.portfolio_id
        or view.effective_at != row.effective_at
        or view.recorded_at != row.published_at
        or view.actor != "LOCAL_USER"
        or view.completeness != "COMPLETE"
        or view.reason != command.reason
        or view.source != f"portfolio-ledger-publication-v1:{row.id}"
        or ledger._digest(view.model_dump(mode="json")) != row.snapshot_sha256
        or {p.listing_id: p.quantity for p in view.positions}
        != {p.listing_id: p.quantity for p in plan.positions}
        or {p.currency: p.balance for p in view.cash_positions}
        != {p.currency: p.balance for p in plan.cash}
        or review is None
        or review.decision != "ACCEPT"
        or review.id != row.review_id
        or review.revision_number != plan.review_revision_number
        or candidate.input_sha256 != plan.candidate_input_sha256
        or candidate.preview_sha256 != plan.candidate_preview_sha256
    ):
        raise services.DomainError(
            "Stored ledger publication failed integrity validation", status=409
        )
    return c.LedgerPublicationRead(
        id=row.id,
        portfolio_id=row.portfolio_id,
        candidate_id=row.candidate_id,
        sequence=row.sequence,
        previous_publication_id=row.previous_publication_id,
        published_at=row.published_at.astimezone(UTC),
        published_by=row.published_by,
        plan=plan,
        command=command,
        snapshot=view,
        snapshot_sha256=row.snapshot_sha256,
        replayed=replayed,
    )


def ownership(session: Session, portfolio_id: UUID) -> c.LedgerOwnershipRead:
    services.portfolio(session, portfolio_id)
    current = _latest(session, portfolio_id)
    return c.LedgerOwnershipRead(
        portfolio_id=portfolio_id,
        source="ACCEPTED_LEDGER" if current else "OBSERVED_SNAPSHOT",
        scope="WHOLE_PORTFOLIO",
        latest_publication=_read(session, current) if current else None,
    )


def publication_preview(
    session: Session, portfolio_id: UUID, candidate_id: UUID
) -> c.LedgerPublicationPreviewRead:
    candidate = reviews.candidate_read(session, portfolio_id, candidate_id)
    existing = session.scalar(
        select(PortfolioLedgerPublication).where(
            PortfolioLedgerPublication.candidate_id == candidate_id
        )
    )
    if existing is not None:
        record = _read(session, existing)
        return record.plan.model_copy(
            update={"status": "ALREADY_PUBLISHED", "publication_id": record.id}
        )
    review = candidate.review
    current_review = reviews._current(session, portfolio_id)
    if (
        review is None
        or review.decision != "ACCEPT"
        or review.revision_number is None
        or current_review is None
        or current_review.id != review.id
    ):
        raise services.DomainError(
            "Publication requires the current accepted ledger candidate", status=409
        )
    fresh = ledger.preview_portfolio_ledger(session, portfolio_id, candidate.packet)
    if (
        fresh.status != "ENDING_RECONCILED"
        or fresh.input_sha256 != candidate.input_sha256
        or ledger._digest(fresh.model_dump(mode="json")) != candidate.preview_sha256
    ):
        raise services.DomainError(
            "Ledger source or calculation changed; review a new candidate", status=409
        )
    previous = _latest(session, portfolio_id)
    if previous:
        _read(session, previous)
    # Include future observations in this conflict check. They must never become
    # a hidden scheduled replacement of an explicitly selected ledger owner.
    latest = session.scalar(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.portfolio_id == portfolio_id)
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    expected_snapshot_id = (
        previous.holding_snapshot_id if previous else candidate.anchor_snapshot_id
    )
    if (
        latest is None
        or latest.id != expected_snapshot_id
        or latest.effective_at >= candidate.as_of
    ):
        raise services.DomainError(
            "Publication needs the expected current snapshot and a strictly later evidenced cutoff",
            status=409,
        )
    snapshot = _snapshot(session, latest)
    plan = c.LedgerPublicationPreviewRead(
        contract_version="portfolio-ledger-publication-v1",
        status="READY",
        portfolio_id=portfolio_id,
        candidate_id=candidate_id,
        review_id=review.id,
        review_revision_number=review.revision_number,
        anchor_snapshot_id=candidate.anchor_snapshot_id,
        anchor_sha256=candidate.packet.anchor_sha256,
        candidate_input_sha256=candidate.input_sha256,
        candidate_preview_sha256=candidate.preview_sha256,
        previous_publication_id=previous.id if previous else None,
        publication_id=None,
        ownership_scope="WHOLE_PORTFOLIO",
        cutover_at=previous.cutover_at if previous else candidate.as_of,
        effective_at=candidate.as_of,
        current_snapshot=snapshot,
        current_snapshot_sha256=ledger._digest(snapshot.model_dump(mode="json")),
        account_ids=sorted((a.account_id for a in candidate.packet.accounts), key=str),
        positions=fresh.positions,
        cash=fresh.cash,
        plan_sha256="0" * 64,
        confirmation_phrase="",
    )
    digest = _plan_hash(plan)
    return plan.model_copy(
        update={
            "plan_sha256": digest,
            "confirmation_phrase": _confirmation(portfolio_id, candidate_id, digest),
        }
    )


def publish(
    session: Session, portfolio_id: UUID, candidate_id: UUID, command: c.LedgerPublicationCreate
) -> c.LedgerPublicationRead:
    try:
        command = c.LedgerPublicationCreate.model_validate(command.model_dump())
    except ValidationError:
        raise services.DomainError(
            "Publication requires explicit ownership, scope, recovery and holdings confirmations",
            status=422,
        ) from None
    services.portfolio(session, portfolio_id, lock=True)
    existing = session.scalar(
        select(PortfolioLedgerPublication).where(
            PortfolioLedgerPublication.candidate_id == candidate_id
        )
    )
    request_sha256 = _request_hash(portfolio_id, candidate_id, command)
    if existing:
        if existing.portfolio_id != portfolio_id or existing.request_sha256 != request_sha256:
            raise services.DomainError(
                "This candidate already has a different publication request", status=409
            )
        return _read(session, existing, replayed=True)
    candidate = reviews.candidate_read(session, portfolio_id, candidate_id)
    reviews._lock_sources(session, portfolio_id, candidate.packet)
    plan = publication_preview(session, portfolio_id, candidate_id)
    if (
        command.expected_plan_sha256 != plan.plan_sha256
        or command.expected_previous_publication_id != plan.previous_publication_id
        or command.confirmation != plan.confirmation_phrase
    ):
        raise services.DomainError(
            "Publication must match the exact plan, previous publication and typed confirmation",
            status=409,
        )
    previous = _latest(session, portfolio_id)
    publication_id = uuid4()
    snapshot = services._record_holdings(
        session,
        portfolio_id,
        s.SnapshotCreate(
            actor="LOCAL_USER",
            reason=command.reason,
            source=f"portfolio-ledger-publication-v1:{publication_id}",
            effective_at=plan.effective_at,
            completeness="COMPLETE",
            positions=[
                s.PositionInput(listing_id=p.listing_id, quantity=p.quantity)
                for p in plan.positions
            ],
            cash_positions=[s.CashInput(currency=p.currency, balance=p.balance) for p in plan.cash],
        ),
    )
    view = _snapshot(session, snapshot)
    row = PortfolioLedgerPublication(
        id=publication_id,
        portfolio_id=portfolio_id,
        candidate_id=candidate_id,
        review_id=plan.review_id,
        previous_publication_id=plan.previous_publication_id,
        holding_snapshot_id=snapshot.id,
        anchor_snapshot_id=plan.anchor_snapshot_id,
        sequence=previous.sequence + 1 if previous else 1,
        cutover_at=plan.cutover_at,
        effective_at=plan.effective_at,
        published_at=snapshot.recorded_at,
        plan_sha256=plan.plan_sha256,
        request_sha256=request_sha256,
        snapshot_sha256=ledger._digest(view.model_dump(mode="json")),
        plan_data=plan.model_dump(mode="json"),
        command_data=command.model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    return _read(session, row)
