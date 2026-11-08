"""Immutable ledger candidate review, independent of canonical snapshot authority."""

from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    Listing,
    PortfolioLedgerCandidate,
    PortfolioLedgerReview,
    Security,
)


def _stage_digest(portfolio_id: UUID, value: c.LedgerCandidateCreate) -> str:
    return ledger._digest(
        {
            "portfolio_id": str(portfolio_id),
            "base_candidate_id": str(value.expected_base_candidate_id)
            if value.expected_base_candidate_id
            else None,
            "input_sha256": value.expected_input_sha256,
            "reason": value.reason,
            "packet": ledger.canonical_ledger_packet(value.proposal),
        }
    )


def _review_digest(portfolio_id: UUID, candidate_id: UUID, value: c.LedgerReviewCreate) -> str:
    command = value.model_dump(mode="json")
    if isinstance(value, c.LedgerAcceptCreate):
        for name in ("acknowledged_changed_activity_ids", "acknowledged_removed_activity_ids"):
            command[name] = sorted(command[name])
    return ledger._digest(
        {"portfolio_id": str(portfolio_id), "candidate_id": str(candidate_id), "command": command}
    )


def _candidate(
    session: Session, portfolio_id: UUID, candidate_id: UUID
) -> PortfolioLedgerCandidate:
    row = session.scalar(
        select(PortfolioLedgerCandidate).where(
            PortfolioLedgerCandidate.portfolio_id == portfolio_id,
            PortfolioLedgerCandidate.id == candidate_id,
        )
    )
    if row is None:
        raise services.DomainError("Ledger candidate not found", status=404)
    return row


def _current(session: Session, portfolio_id: UUID) -> PortfolioLedgerReview | None:
    return session.scalar(
        select(PortfolioLedgerReview)
        .where(
            PortfolioLedgerReview.portfolio_id == portfolio_id,
            PortfolioLedgerReview.decision == "ACCEPT",
        )
        .order_by(PortfolioLedgerReview.revision_number.desc())
        .limit(1)
    )


def _review(session: Session, candidate_id: UUID) -> PortfolioLedgerReview | None:
    return session.scalar(
        select(PortfolioLedgerReview).where(PortfolioLedgerReview.candidate_id == candidate_id)
    )


def _stored(
    row: PortfolioLedgerCandidate,
) -> tuple[c.PortfolioLedgerPreviewCreate, c.PortfolioLedgerPreviewRead]:
    try:
        packet = c.PortfolioLedgerPreviewCreate.model_validate(row.packet_data)
        preview = c.PortfolioLedgerPreviewRead.model_validate(row.preview_data)
        request = c.LedgerCandidateCreate(
            submission_id=row.id,
            expected_base_candidate_id=row.base_candidate_id,
            expected_input_sha256=row.input_sha256,
            reason=row.reason,
            proposal=packet,
        )
    except ValidationError:
        raise services.DomainError(
            "Stored ledger candidate failed integrity validation", status=409
        ) from None
    if (
        ledger._digest(ledger.canonical_ledger_packet(packet)) != row.packet_sha256
        or ledger._digest(row.preview_data) != row.preview_sha256
        or _stage_digest(row.portfolio_id, request) != row.request_sha256
        or preview.input_sha256 != row.input_sha256
        or preview.portfolio_id != row.portfolio_id
        or preview.anchor_snapshot_id != row.anchor_snapshot_id
        or packet.anchor_snapshot_id != row.anchor_snapshot_id
        or preview.anchor_sha256 != packet.anchor_sha256
        or preview.contract_version != packet.contract_version
        or preview.as_of != packet.as_of
        or preview.as_of != row.as_of
        or preview.status != row.preview_status
    ):
        raise services.DomainError(
            "Stored ledger candidate failed integrity validation", status=409
        )
    return packet, preview


def _review_read(
    row: PortfolioLedgerCandidate, review: PortfolioLedgerReview | None
) -> c.LedgerReviewRead | None:
    if review is None:
        return None
    try:
        command = TypeAdapter[c.LedgerAcceptCreate | c.LedgerRejectCreate](
            c.LedgerReviewCreate
        ).validate_python(review.review_data)
        result = c.LedgerReviewRead(
            id=review.id,
            decision=command.decision,
            revision_number=review.revision_number,
            reviewed_by=review.reviewed_by,
            reviewed_at=review.reviewed_at,
            command=command,
        )
    except ValidationError:
        raise services.DomainError(
            "Stored ledger review failed integrity validation", status=409
        ) from None
    if (
        review.portfolio_id != row.portfolio_id
        or review.candidate_id != row.id
        or review.decision != command.decision
        or review.reason != command.reason
        or _review_digest(row.portfolio_id, row.id, command) != review.request_sha256
        or command.expected_input_sha256 != row.input_sha256
        or command.expected_preview_sha256 != row.preview_sha256
        or command.expected_base_candidate_id != row.base_candidate_id
        or (
            review.decision == "ACCEPT"
            and (review.revision_number is None or review.revision_number < 1)
        )
        or (review.decision == "REJECT" and review.revision_number is not None)
    ):
        raise services.DomainError("Stored ledger review failed integrity validation", status=409)
    return result


def _summary(
    row: PortfolioLedgerCandidate, review: PortfolioLedgerReview | None
) -> c.LedgerCandidateSummaryRead:
    return c.LedgerCandidateSummaryRead.model_validate(
        {
            "id": row.id,
            "portfolio_id": row.portfolio_id,
            "base_candidate_id": row.base_candidate_id,
            "anchor_snapshot_id": row.anchor_snapshot_id,
            "input_sha256": row.input_sha256,
            "packet_sha256": row.packet_sha256,
            "preview_sha256": row.preview_sha256,
            "status": "PENDING"
            if review is None
            else "ACCEPTED"
            if review.decision == "ACCEPT"
            else "REJECTED",
            "preview_status": row.preview_status,
            "as_of": row.as_of,
            "reason": row.reason,
            "submitted_by": row.submitted_by,
            "submitted_at": row.submitted_at,
            "review": _review_read(row, review),
        }
    )


def _changes(
    session: Session, row: PortfolioLedgerCandidate, packet: c.PortfolioLedgerPreviewCreate
) -> c.LedgerActivityChangesRead:
    previous: dict[UUID, Any] = {}
    opening_changed = False
    if row.base_candidate_id is not None:
        base, _ = _stored(_candidate(session, row.portfolio_id, row.base_candidate_id))
        previous = {item.id: item.model_dump(mode="json") for item in base.activity}
        opening_changed = (
            ledger.canonical_ledger_packet(base)["accounts"]
            != ledger.canonical_ledger_packet(packet)["accounts"]
        )
    proposed = {item.id: item.model_dump(mode="json") for item in packet.activity}
    return c.LedgerActivityChangesRead(
        added_activity_ids=sorted(proposed.keys() - previous.keys(), key=str),
        removed_activity_ids=sorted(previous.keys() - proposed.keys(), key=str),
        changed_activity_ids=sorted(
            (key for key in previous.keys() & proposed.keys() if previous[key] != proposed[key]),
            key=str,
        ),
        opening_changed=opening_changed,
    )


def candidate_read(
    session: Session, portfolio_id: UUID, candidate_id: UUID, *, replayed: bool = False
) -> c.LedgerCandidateRead:
    row = _candidate(session, portfolio_id, candidate_id)
    packet, preview = _stored(row)
    summary = _summary(row, _review(session, candidate_id))
    return c.LedgerCandidateRead(
        **summary.model_dump(),
        packet=packet,
        preview=preview,
        changes=_changes(session, row, packet),
        replayed=replayed,
    )


def list_candidates(
    session: Session, portfolio_id: UUID, limit: int = 30
) -> c.LedgerCandidatesRead:
    services.portfolio(session, portfolio_id)
    current = _current(session, portfolio_id)
    rows = session.execute(
        select(PortfolioLedgerCandidate, PortfolioLedgerReview)
        .outerjoin(
            PortfolioLedgerReview,
            PortfolioLedgerReview.candidate_id == PortfolioLedgerCandidate.id,
        )
        .where(PortfolioLedgerCandidate.portfolio_id == portfolio_id)
        .options(
            load_only(
                PortfolioLedgerCandidate.id,
                PortfolioLedgerCandidate.portfolio_id,
                PortfolioLedgerCandidate.base_candidate_id,
                PortfolioLedgerCandidate.anchor_snapshot_id,
                PortfolioLedgerCandidate.input_sha256,
                PortfolioLedgerCandidate.packet_sha256,
                PortfolioLedgerCandidate.preview_sha256,
                PortfolioLedgerCandidate.as_of,
                PortfolioLedgerCandidate.preview_status,
                PortfolioLedgerCandidate.reason,
                PortfolioLedgerCandidate.submitted_by,
                PortfolioLedgerCandidate.submitted_at,
            )
        )
        .order_by(PortfolioLedgerCandidate.submitted_at.desc(), PortfolioLedgerCandidate.id)
        .limit(limit)
    ).all()
    return c.LedgerCandidatesRead(
        portfolio_id=portfolio_id,
        current_accepted_candidate_id=current.candidate_id if current else None,
        current_revision_number=current.revision_number
        if current and current.revision_number
        else 0,
        candidates=[_summary(row, review) for row, review in rows],
    )


def _lock_sources(
    session: Session, portfolio_id: UUID, packet: c.PortfolioLedgerPreviewCreate
) -> None:
    # All snapshot writers lock the same portfolio first. Pin consumed listing/security
    # identities until the review transaction finishes, including opening-only rows.
    anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
    ids = {item.listing_id for item in anchor.listings} | {
        item.listing_id for account in packet.accounts for item in account.positions
    }
    ids.update(
        item.listing_id
        for item in packet.activity
        if isinstance(item, (c.LedgerTrade, c.LedgerDividend))
    )
    if packet.ending_statement:
        ids.update(
            item.listing_id
            for account in packet.ending_statement.accounts
            for item in account.positions
        )
    session.execute(
        select(Listing, Security)
        .join(Security, Security.id == Listing.security_id)
        .where(
            Listing.id.in_(ids),
        )
        .order_by(Listing.id, Security.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()


def stage_candidate(
    session: Session, portfolio_id: UUID, value: c.LedgerCandidateCreate
) -> c.LedgerCandidateRead:
    services.portfolio(session, portfolio_id, lock=True)
    request_sha256 = _stage_digest(portfolio_id, value)
    existing = session.get(PortfolioLedgerCandidate, value.submission_id)
    if existing is not None:
        if existing.portfolio_id != portfolio_id or existing.request_sha256 != request_sha256:
            raise services.DomainError(
                "Submission ID conflicts with a different ledger candidate", status=409
            )
        return candidate_read(session, portfolio_id, existing.id, replayed=True)
    existing = session.scalar(
        select(PortfolioLedgerCandidate).where(
            PortfolioLedgerCandidate.portfolio_id == portfolio_id,
            PortfolioLedgerCandidate.request_sha256 == request_sha256,
        )
    )
    if existing is not None:
        return candidate_read(session, portfolio_id, existing.id, replayed=True)
    current = _current(session, portfolio_id)
    if value.expected_base_candidate_id != (current.candidate_id if current else None):
        raise services.DomainError(
            "Ledger base changed; review the current accepted candidate", status=409
        )
    if current:
        base, _ = _stored(_candidate(session, portfolio_id, current.candidate_id))
        if (
            value.proposal.anchor_snapshot_id != base.anchor_snapshot_id
            or value.proposal.anchor_sha256 != base.anchor_sha256
            or {a.account_id for a in value.proposal.accounts}
            != {a.account_id for a in base.accounts}
            or value.proposal.as_of < base.as_of
        ):
            raise services.DomainError(
                "Corrections require the same opening anchor/accounts and a nondecreasing cutoff",
                status=409,
            )
    _lock_sources(session, portfolio_id, value.proposal)
    preview = ledger.preview_portfolio_ledger(session, portfolio_id, value.proposal)
    if preview.input_sha256 != value.expected_input_sha256:
        raise services.DomainError(
            "Ledger source/input hash changed; obtain a new preview", status=409
        )
    preview_data = preview.model_dump(mode="json")
    preview_sha256 = ledger._digest(preview_data)
    if current:
        accepted = _candidate(session, portfolio_id, current.candidate_id)
        if (
            accepted.input_sha256 == preview.input_sha256
            and accepted.preview_sha256 == preview_sha256
        ):
            raise services.DomainError(
                "This ledger packet is already the current accepted candidate", status=409
            )
    row = PortfolioLedgerCandidate(
        id=value.submission_id,
        portfolio_id=portfolio_id,
        base_candidate_id=value.expected_base_candidate_id,
        anchor_snapshot_id=value.proposal.anchor_snapshot_id,
        input_sha256=preview.input_sha256,
        packet_sha256=ledger._digest(ledger.canonical_ledger_packet(value.proposal)),
        preview_sha256=preview_sha256,
        request_sha256=request_sha256,
        as_of=preview.as_of,
        preview_status=preview.status,
        packet_data=ledger.canonical_ledger_packet(value.proposal),
        preview_data=preview_data,
        reason=value.reason,
    )
    session.add(row)
    session.flush()
    return candidate_read(session, portfolio_id, row.id)


def review_candidate(
    session: Session, portfolio_id: UUID, candidate_id: UUID, value: c.LedgerReviewCreate
) -> c.LedgerCandidateRead:
    services.portfolio(session, portfolio_id, lock=True)
    row = _candidate(session, portfolio_id, candidate_id)
    packet, _ = _stored(row)
    request_sha256 = _review_digest(portfolio_id, candidate_id, value)
    previous_review = _review(session, candidate_id)
    if previous_review is not None:
        if previous_review.request_sha256 != request_sha256:
            raise services.DomainError(
                "Ledger candidate already has a different terminal review", status=409
            )
        return candidate_read(session, portfolio_id, candidate_id, replayed=True)
    if (
        value.expected_input_sha256 != row.input_sha256
        or value.expected_preview_sha256 != row.preview_sha256
        or value.expected_base_candidate_id != row.base_candidate_id
    ):
        raise services.DomainError(
            "Review must match the exact candidate hashes and base", status=409
        )
    revision_number = None
    if isinstance(value, c.LedgerAcceptCreate):
        current = _current(session, portfolio_id)
        if row.base_candidate_id != (current.candidate_id if current else None):
            raise services.DomainError(
                "Ledger base changed; stage and review a new candidate", status=409
            )
        changes = _changes(session, row, packet)
        if set(value.acknowledged_removed_activity_ids) != set(changes.removed_activity_ids) or set(
            value.acknowledged_changed_activity_ids
        ) != set(changes.changed_activity_ids):
            raise services.DomainError(
                "Acceptance must explicitly acknowledge every changed and removed activity ID",
                status=409,
            )
        _lock_sources(session, portfolio_id, packet)
        fresh = ledger.preview_portfolio_ledger(session, portfolio_id, packet)
        if fresh.status != "ENDING_RECONCILED":
            raise services.DomainError(
                "Acceptance requires complete matching opening and ending evidence", status=409
            )
        if (
            fresh.input_sha256 != row.input_sha256
            or ledger._digest(fresh.model_dump(mode="json")) != row.preview_sha256
        ):
            raise services.DomainError(
                "Ledger source or calculation changed; stage and review a new candidate", status=409
            )
        revision_number = (
            current.revision_number if current and current.revision_number else 0
        ) + 1
    session.add(
        PortfolioLedgerReview(
            portfolio_id=portfolio_id,
            candidate_id=candidate_id,
            decision=value.decision,
            revision_number=revision_number,
            request_sha256=request_sha256,
            reason=value.reason,
            review_data=value.model_dump(mode="json"),
        )
    )
    session.flush()
    return candidate_read(session, portfolio_id, candidate_id)
