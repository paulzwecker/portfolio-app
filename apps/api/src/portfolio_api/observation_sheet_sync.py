"""Opt-in, read-only Google Sheets bridge to canonical observation proposals.

The spreadsheet is a producer, not an acceptance authority. We reuse the existing
bounded, double-read GoogleSheetsApiReader and observation proposal inbox.
"""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from portfolio_api import company_observation_proposals as proposals
from portfolio_api.domain import schemas as s
from portfolio_api.domain.services import DomainError
from portfolio_api.google_sheets_sync import (
    MAX_CONTRACT_BYTES,
    ContractBlock,
    GoogleSheetsApiReader,
    GoogleSheetsReader,
    GoogleSheetsSyncError,
)
from portfolio_api.settings import Settings

OBSERVATION_INBOX_TAB = "Application Observation Inbox"
MAX_OBSERVATION_BLOCKS = 100
LOCK_NAMESPACE = 1297110364


class ObservationSheetIssue(s.Contract):
    row_number: int
    publish_id: str
    code: Literal["INVALID", "CONFLICT", "NOT_FOUND"]
    reason: str


class ObservationSheetCheck(s.Contract):
    status: Literal["SUCCEEDED", "PARTIAL", "SOURCE_UNAVAILABLE", "SYNC_IN_PROGRESS"]
    spreadsheet_id: str
    tab: str
    checked_count: int
    created_count: int
    replayed_count: int
    issues: list[ObservationSheetIssue]
    created_proposal_ids: list[UUID]
    source_error_code: str | None = None


def parse_observation_block(block: ContractBlock) -> proposals.ObservationBatchV1:
    """Validate one assembled workbook contract, preserving exact decimal strings."""
    if block.issue:
        raise ValueError(block.issue)
    if len(block.contract_text.encode("utf-8")) > MAX_CONTRACT_BYTES:
        raise ValueError("Contract exceeds the 1 MB inbox limit")
    try:
        data = json.loads(block.contract_text)
    except (ValueError, TypeError):
        raise ValueError("Contract is not valid JSON") from None
    if not isinstance(data, dict):
        raise ValueError("Contract must be one JSON object")
    try:
        batch = proposals.BATCH_ADAPTER.validate_python(data)
    except ValidationError as error:
        # Never echo raw spreadsheet cell values or credential-adjacent input.
        location = ".".join(str(part) for part in error.errors()[0]["loc"])
        raise ValueError(f"Typed observation contract invalid at {location}") from None
    if not block.external_revision_id or block.external_revision_id != batch.external_batch_id:
        raise ValueError("Inbox external batch ID does not match the contract")
    return batch


def _issue(
    block: ContractBlock,
    code: Literal["INVALID", "CONFLICT", "NOT_FOUND"],
    reason: str,
) -> ObservationSheetIssue:
    return ObservationSheetIssue(
        row_number=block.first_row_number,
        publish_id=block.publish_id[:160],
        code=code,
        reason=reason[:250],
    )


def check_observation_inbox(
    session: Session,
    settings: Settings,
    reader: GoogleSheetsReader | None = None,
) -> ObservationSheetCheck:
    """Import typed candidates only. No Sheets writes, previews, or acceptances."""
    if not settings.observation_proposals_enabled or not settings.observation_sheets_inbox_enabled:
        raise DomainError("The observation Sheets proposal inbox is disabled", 503)
    if (
        settings.app_env == "production" or settings.database_target_environment == "production"
    ) and not settings.database_production_writes_authorized:
        raise DomainError("Production proposal imports require separate owner authorization", 403)
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    if not spreadsheet_id:
        raise DomainError("Observation Sheets workbook is not configured", 503)

    tab = settings.google_sheets_observation_tab
    lock_key = int(hashlib.sha256(f"{spreadsheet_id}:{tab}".encode()).hexdigest()[:8], 16)
    acquired = session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:namespace, :lock_key)"),
        {"namespace": LOCK_NAMESPACE, "lock_key": lock_key % (2**31)},
    )
    if not acquired:
        return ObservationSheetCheck(
            status="SYNC_IN_PROGRESS",
            spreadsheet_id=spreadsheet_id,
            tab=tab,
            checked_count=0,
            created_count=0,
            replayed_count=0,
            issues=[],
            created_proposal_ids=[],
        )
    try:
        source = reader if reader is not None else GoogleSheetsApiReader(settings)
        snapshot = source.read_inbox(spreadsheet_id, tab)
    except GoogleSheetsSyncError as error:
        return ObservationSheetCheck(
            status="SOURCE_UNAVAILABLE",
            source_error_code=error.code,
            spreadsheet_id=spreadsheet_id,
            tab=tab,
            checked_count=0,
            created_count=0,
            replayed_count=0,
            issues=[],
            created_proposal_ids=[],
        )
    if not snapshot.connection.sync_tab_exists or snapshot.connection.sheet_id is None:
        raise DomainError("Observation inbox tab is not accessible", 503)
    if len(snapshot.blocks) > MAX_OBSERVATION_BLOCKS:
        raise DomainError("Observation inbox exceeds the 100-contract scan limit", 422)

    # A stable source identity isolates Sheet submissions from API agent tokens,
    # and preserves idempotency even if the workbook title changes.
    producer_id = (
        "sheets-observation:"
        + hashlib.sha256(f"{spreadsheet_id}:{snapshot.connection.sheet_id}".encode()).hexdigest()[
            :32
        ]
    )
    issues: list[ObservationSheetIssue] = []
    created: list[UUID] = []
    replayed = 0
    for block in snapshot.blocks:
        try:
            batch = parse_observation_block(block)
        except ValueError as error:
            issues.append(_issue(block, "INVALID", str(error)))
            continue
        try:
            result = proposals.submit(session, batch, producer_id=producer_id)
        except DomainError as error:
            code: Literal["CONFLICT", "NOT_FOUND"] = (
                "NOT_FOUND" if error.status == 404 else "CONFLICT"
            )
            issues.append(_issue(block, code, error.detail))
            continue
        if result.replayed:
            replayed += 1
        else:
            created.append(result.proposal.id)

    return ObservationSheetCheck(
        status="PARTIAL" if issues else "SUCCEEDED",
        spreadsheet_id=spreadsheet_id,
        tab=tab,
        checked_count=len(snapshot.blocks),
        created_count=len(created),
        replayed_count=replayed,
        issues=issues,
        created_proposal_ids=created,
    )
