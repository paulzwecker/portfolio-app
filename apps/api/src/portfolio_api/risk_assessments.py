"""Versioned Google Sheets risk assessments and their explicit review workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    GoogleSheetsRiskSyncCandidate,
    GoogleSheetsRiskSyncRun,
    HoldingSnapshot,
    InvestmentThesisClaim,
    InvestmentThesisRevision,
    Portfolio,
    ReportedFundamentalObservation,
    RiskAssessmentEvidence,
    RiskAssessmentFinding,
    RiskAssessmentRevision,
    SourceDocument,
    TargetRevision,
    now,
)
from portfolio_api.domain.services import DomainError
from portfolio_api.google_sheets_sync import (
    MAX_CONTRACT_BYTES,
    ContractBlock,
    GoogleSheetsApiReader,
    GoogleSheetsReader,
    GoogleSheetsSyncError,
    InboxSnapshot,
    _canonical_json,
    _sha256,
)
from portfolio_api.portfolio_sheet_sync import (
    PORTFOLIO_STATE_CONTRACT_VERSION,
    portfolio_state_fingerprint,
)
from portfolio_api.settings import Settings

RISK_SYNC_TAB = "Application Risk Assessment Inbox"
MAX_RISK_CANDIDATES = 200


def _contract_fingerprint(value: s.RiskAssessmentContractV1) -> str:
    return _sha256(_canonical_json(cast(dict[str, object], value.model_dump(mode="json"))))


def _is_configured(settings: Settings) -> bool:
    path = settings.google_sheets_service_account_file
    return bool(settings.google_sheets_spreadsheet_id and path and path.expanduser().is_file())


def _run_read(run: GoogleSheetsRiskSyncRun) -> s.GoogleSheetsRiskSyncRunRead:
    return s.GoogleSheetsRiskSyncRunRead.model_validate(run)


def risk_sync_status(session: Session, settings: Settings) -> s.GoogleSheetsRiskSyncStatusRead:
    run = session.scalar(
        select(GoogleSheetsRiskSyncRun).order_by(GoogleSheetsRiskSyncRun.started_at.desc()).limit(1)
    )
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    return s.GoogleSheetsRiskSyncStatusRead(
        configured=bool(spreadsheet_id and settings.google_sheets_service_account_file),
        credentials_available=_is_configured(settings),
        spreadsheet_id=spreadsheet_id,
        spreadsheet_url=(
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            if spreadsheet_id
            else None
        ),
        inbox_tab=RISK_SYNC_TAB,
        last_run=_run_read(run) if run is not None else None,
    )


def test_risk_sync_connection(
    settings: Settings, reader: GoogleSheetsReader | None = None
) -> s.GoogleSheetsConnectionTestRead:
    checked_at = now()
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    if not spreadsheet_id:
        return s.GoogleSheetsConnectionTestRead(
            connected=False,
            spreadsheet_id=None,
            spreadsheet_title=None,
            sync_tab_exists=False,
            checked_at=checked_at,
            message="Set GOOGLE_SHEETS_SPREADSHEET_ID and the service-account credential.",
        )
    try:
        client = reader or GoogleSheetsApiReader(settings)
        connection = client.test_connection(spreadsheet_id, RISK_SYNC_TAB)
    except GoogleSheetsSyncError as error:
        return s.GoogleSheetsConnectionTestRead(
            connected=False,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_title=None,
            sync_tab_exists=False,
            checked_at=checked_at,
            message=str(error),
        )
    return s.GoogleSheetsConnectionTestRead(
        connected=True,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=connection.spreadsheet_title,
        sync_tab_exists=connection.sync_tab_exists,
        checked_at=checked_at,
        message=(
            "Workbook access is ready; only the explicit risk-assessment inbox is read."
            if connection.sync_tab_exists
            else f"Workbook access works. Add the '{RISK_SYNC_TAB}' tab to enable risk discovery."
        ),
    )


def _candidate_read(
    session: Session, candidate: GoogleSheetsRiskSyncCandidate
) -> s.GoogleSheetsRiskCandidateRead:
    return s.GoogleSheetsRiskCandidateRead(
        id=candidate.id,
        portfolio_id=candidate.portfolio_id,
        stream_key=candidate.stream_key,
        external_revision_id=candidate.external_revision_id,
        contract_version=candidate.contract_version,
        content_fingerprint=candidate.content_fingerprint,
        source_url=candidate.source_url,
        sheet_title=candidate.sheet_title,
        source_row_number=candidate.source_row_number,
        status=candidate.status,
        issue=candidate.issue,
        author_id=candidate.author_id,
        source_id=candidate.source_id,
        source_reference=candidate.source_reference,
        authored_at=candidate.authored_at,
        published_at=candidate.published_at,
        summary=candidate.summary,
        findings_count=candidate.findings_count,
        baseline_status=candidate.baseline_status,
        preview_data=candidate.preview_data,
        reviewer=candidate.reviewer,
        reviewer_note=candidate.reviewer_note,
        accepted_revision_id=candidate.accepted_revision_id,
        first_observed_at=candidate.first_observed_at,
        last_observed_at=candidate.last_observed_at,
        accepted_at=candidate.accepted_at,
        rejected_at=candidate.rejected_at,
    )


def list_risk_sync_candidates(
    session: Session, status: str | None = None, limit: int = 100
) -> list[s.GoogleSheetsRiskCandidateRead]:
    query = select(GoogleSheetsRiskSyncCandidate).order_by(
        GoogleSheetsRiskSyncCandidate.first_observed_at.desc(),
        GoogleSheetsRiskSyncCandidate.id,
    )
    if status:
        query = query.where(GoogleSheetsRiskSyncCandidate.status == status)
    rows = session.scalars(query.limit(limit)).all()
    return [_candidate_read(session, row) for row in rows]


def list_risk_sync_runs(session: Session, limit: int = 25) -> list[s.GoogleSheetsRiskSyncRunRead]:
    rows = session.scalars(
        select(GoogleSheetsRiskSyncRun)
        .order_by(GoogleSheetsRiskSyncRun.started_at.desc())
        .limit(limit)
    ).all()
    return [_run_read(row) for row in rows]


def _risk_block_candidate(
    session: Session,
    run: GoogleSheetsRiskSyncRun,
    spreadsheet_id: str,
    spreadsheet_title: str,
    sheet_id: int,
    block: ContractBlock,
    seen_at: datetime,
) -> tuple[GoogleSheetsRiskSyncCandidate, bool]:
    raw_digest = _sha256(block.contract_text)
    issue = block.issue
    parsed: s.RiskAssessmentContractV1 | None = None
    raw: object = None
    if not issue:
        if len(block.contract_text.encode("utf-8")) > MAX_CONTRACT_BYTES:
            issue = "The risk contract exceeds the 1 MB inbox limit"
        else:
            try:
                raw = json.loads(block.contract_text)
                if not isinstance(raw, dict):
                    raise ValueError("The inbox cell must contain one JSON risk contract object")
                parsed = s.RiskAssessmentContractV1.model_validate(raw)
                if block.external_revision_id != parsed.external_revision_id:
                    raise ValueError("Inbox revision ID does not match the risk contract")
            except Exception as error:
                issue = f"Invalid risk assessment contract: {error}"

    normalized = (
        cast(dict[str, object], parsed.model_dump(mode="json")) if parsed is not None else None
    )
    fingerprint = _contract_fingerprint(parsed) if parsed is not None else raw_digest
    external_revision_id = (
        parsed.external_revision_id if parsed is not None else block.external_revision_id
    )
    portfolio_id = parsed.portfolio_id if parsed is not None else None
    stream_key = parsed.stream_key if parsed is not None else None
    idempotency_key = _sha256(
        "|".join(
            (spreadsheet_id, RISK_SYNC_TAB, external_revision_id or block.publish_id, fingerprint)
        )
    )
    existing = session.scalar(
        select(GoogleSheetsRiskSyncCandidate).where(
            GoogleSheetsRiskSyncCandidate.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        existing.last_seen_run_id = run.id
        existing.last_observed_at = seen_at
        if existing.status in {"ACCEPTED", "REJECTED"}:
            return existing, False
        if issue:
            existing.status = "INVALID"
            existing.issue = issue
        return existing, False

    row = GoogleSheetsRiskSyncCandidate(
        idempotency_key=idempotency_key,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=spreadsheet_title,
        sheet_id=sheet_id,
        sheet_title=RISK_SYNC_TAB,
        source_row_number=block.first_row_number,
        source_url=(
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            f"#gid={sheet_id}&range=A{block.first_row_number}:E{block.first_row_number}"
        ),
        last_seen_run_id=run.id,
        contract_text=block.contract_text,
        contract_data=normalized,
        contract_version=parsed.contract_version if parsed is not None else None,
        content_fingerprint=fingerprint,
        raw_sha256=raw_digest,
        portfolio_id=portfolio_id,
        stream_key=stream_key,
        external_revision_id=external_revision_id,
        author_id=parsed.author_id if parsed is not None else None,
        source_id=parsed.source_id if parsed is not None else None,
        source_reference=parsed.source_reference if parsed is not None else None,
        authored_at=parsed.authored_at if parsed is not None else None,
        published_at=parsed.published_at if parsed is not None else None,
        summary=parsed.summary if parsed is not None else None,
        findings_count=len(parsed.findings) if parsed is not None else 0,
        status="INVALID" if issue else "PENDING",
        issue=issue,
        first_observed_at=seen_at,
        last_observed_at=seen_at,
    )
    session.add(row)
    session.flush()

    if parsed is not None:
        accepted = session.scalar(
            select(RiskAssessmentRevision).where(
                RiskAssessmentRevision.portfolio_id == parsed.portfolio_id,
                RiskAssessmentRevision.stream_key == parsed.stream_key,
                RiskAssessmentRevision.external_revision_id == parsed.external_revision_id,
            )
        )
        if accepted is not None:
            if accepted.content_fingerprint == fingerprint:
                row.status = "ACCEPTED"
                row.accepted_revision_id = accepted.id
                row.reviewer = accepted.reviewer
                row.reviewer_note = "Exact replay; the canonical revision was already accepted."
                row.accepted_at = accepted.accepted_at
            else:
                row.status = "CONFLICT"
                row.issue = "External revision ID was already used for different content"
    session.flush()
    return row, True


def run_risk_sync_check(
    session: Session,
    settings: Settings,
    reader: GoogleSheetsReader | None = None,
) -> s.GoogleSheetsRiskSyncCheckRead:
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    run = GoogleSheetsRiskSyncRun(
        spreadsheet_id=spreadsheet_id,
        status="BLOCKED" if not spreadsheet_id else "CONNECTED",
        started_at=now(),
    )
    session.add(run)
    session.flush()
    if not spreadsheet_id:
        run.error_code = "NOT_CONFIGURED"
        run.error_message = "Set GOOGLE_SHEETS_SPREADSHEET_ID"
        run.completed_at = now()
        return s.GoogleSheetsRiskSyncCheckRead(run=_run_read(run), new_candidates=[])
    try:
        client = reader or GoogleSheetsApiReader(settings)
        snapshot: InboxSnapshot = client.read_inbox(spreadsheet_id, RISK_SYNC_TAB)
    except GoogleSheetsSyncError as error:
        run.status = "FAILED"
        run.error_code = error.code
        run.error_message = str(error)
        run.completed_at = now()
        session.flush()
        return s.GoogleSheetsRiskSyncCheckRead(run=_run_read(run), new_candidates=[])

    run.spreadsheet_title = snapshot.connection.spreadsheet_title
    run.status = "SUCCEEDED"
    if not snapshot.connection.sync_tab_exists or snapshot.connection.sheet_id is None:
        run.status = "BLOCKED"
        run.error_code = "RISK_INBOX_MISSING"
        run.error_message = f"The fixed inbox tab '{RISK_SYNC_TAB}' does not exist"
        run.completed_at = now()
        session.flush()
        return s.GoogleSheetsRiskSyncCheckRead(run=_run_read(run), new_candidates=[])

    seen_at = now()
    new_candidates: list[GoogleSheetsRiskSyncCandidate] = []
    run.candidate_count = len(snapshot.blocks)
    for block in snapshot.blocks:
        row, inserted = _risk_block_candidate(
            session,
            run,
            spreadsheet_id,
            snapshot.connection.spreadsheet_title,
            snapshot.connection.sheet_id,
            block,
            seen_at,
        )
        if inserted:
            new_candidates.append(row)
            run.new_count += 1
        else:
            run.unchanged_count += 1
        if row.status in {"INVALID", "CONFLICT"}:
            run.issue_count += 1
    if run.issue_count:
        run.status = "PARTIAL"
    run.completed_at = now()
    session.flush()
    return s.GoogleSheetsRiskSyncCheckRead(
        run=_run_read(run),
        new_candidates=[_candidate_read(session, row) for row in new_candidates],
    )


def _candidate_contract(
    candidate: GoogleSheetsRiskSyncCandidate,
) -> s.RiskAssessmentContractV1 | None:
    try:
        raw = json.loads(candidate.contract_text)
        parsed = s.RiskAssessmentContractV1.model_validate(raw)
    except Exception as error:
        candidate.status = "INVALID"
        candidate.issue = f"Invalid risk assessment contract: {error}"
        candidate.preview_data = None
        return None
    if (
        parsed.portfolio_id != candidate.portfolio_id
        or parsed.external_revision_id != candidate.external_revision_id
    ):
        candidate.status = "INVALID"
        candidate.issue = "Stored portfolio or external revision identity changed"
        return None
    return parsed


def _validate_evidence(
    session: Session,
    value: s.RiskAssessmentContractV1,
) -> None:
    for finding in value.findings:
        if finding.company_id is not None:
            company = session.get(Company, finding.company_id)
            if company is None:
                raise DomainError("Risk finding references an unknown company", 422)
        for evidence in finding.evidence:
            document: SourceDocument | None = None
            fact: ReportedFundamentalObservation | None = None
            thesis: InvestmentThesisRevision | None = None
            if evidence.source_document_id is not None:
                document = session.get(SourceDocument, evidence.source_document_id)
                if document is None:
                    raise DomainError("Risk evidence references an unknown source document", 422)
            if evidence.reported_fundamental_observation_id is not None:
                fact = session.get(
                    ReportedFundamentalObservation, evidence.reported_fundamental_observation_id
                )
                if fact is None:
                    raise DomainError("Risk evidence references an unknown reported fact", 422)
            if evidence.thesis_revision_id is not None:
                thesis = session.get(InvestmentThesisRevision, evidence.thesis_revision_id)
                if thesis is None:
                    raise DomainError("Risk evidence references an unknown thesis revision", 422)
            if evidence.thesis_claim_id is not None:
                claim = session.get(InvestmentThesisClaim, evidence.thesis_claim_id)
                if claim is None:
                    raise DomainError("Risk evidence references an unknown thesis claim", 422)
                claim_revision = session.get(InvestmentThesisRevision, claim.revision_id)
                if claim_revision is None:
                    raise DomainError("Risk evidence claim has no thesis revision", 422)
                if thesis is not None and thesis.id != claim_revision.id:
                    raise DomainError("Risk evidence thesis claim and revision do not match", 422)
                thesis = claim_revision

            expected_company = finding.company_id
            linked_companies = [
                item.company_id
                for item in (document, fact, thesis)
                if item is not None and getattr(item, "company_id", None) is not None
            ]
            if expected_company is not None and any(
                linked_company != expected_company for linked_company in linked_companies
            ):
                raise DomainError("Risk evidence refers to a different company", 422)


@dataclass(frozen=True)
class _Baseline:
    status: str
    issue: str | None
    current_overview: s.PortfolioOverview
    current_fingerprint: str


def _baseline_status(session: Session, value: s.RiskAssessmentContractV1) -> _Baseline:
    if value.portfolio_state_contract_version != PORTFOLIO_STATE_CONTRACT_VERSION:
        raise DomainError("Unsupported published portfolio-state contract version", 422)
    portfolio = session.scalar(select(Portfolio).where(Portfolio.id == value.portfolio_id))
    if portfolio is None:
        raise DomainError("Risk assessment portfolio identity was not found", 404)
    published_view = q.overview(session, value.portfolio_id, value.valuation_as_of)
    if published_view.snapshot is None:
        raise DomainError("The cited portfolio baseline has no holdings snapshot", 422)
    if (
        published_view.snapshot.id != value.holdings_snapshot_id
        or (published_view.target_revision.id if published_view.target_revision else None)
        != value.target_revision_id
        or portfolio_state_fingerprint(published_view) != value.portfolio_state_fingerprint
    ):
        raise DomainError(
            "The cited snapshot, target revision, or fingerprint does not match canonical state "
            "at the supplied valuation_as_of",
            422,
        )

    snapshot = session.get(HoldingSnapshot, value.holdings_snapshot_id)
    if snapshot is None or snapshot.portfolio_id != value.portfolio_id:
        raise DomainError(
            "Risk assessment references a holdings snapshot from another portfolio", 422
        )
    if snapshot.recorded_at > value.published_at or snapshot.effective_at > value.valuation_as_of:
        raise DomainError("Risk assessment baseline was not available at publication time", 422)
    if value.target_revision_id is not None:
        target = session.get(TargetRevision, value.target_revision_id)
        if (
            target is None
            or target.portfolio_id != value.portfolio_id
            or target.status != "ACCEPTED"
            or target.accepted_at is None
            or target.accepted_at > value.published_at
            or target.effective_at > value.valuation_as_of
        ):
            raise DomainError("Risk assessment references an invalid target revision", 422)

    current = q.overview(session, value.portfolio_id, now())
    current_fingerprint = portfolio_state_fingerprint(current)
    snapshot_matches = (
        current.snapshot is not None and current.snapshot.id == value.holdings_snapshot_id
    )
    target_matches = (
        current.target_revision.id if current.target_revision else None
    ) == value.target_revision_id
    if not (snapshot_matches and target_matches):
        return _Baseline(
            "STALE_PORTFOLIO_STATE",
            "Canonical holdings, target revision, prices/FX, or portfolio fingerprint "
            "changed after publication.",
            current,
            current_fingerprint,
        )
    if current.valuation_status != "VALUED":
        return _Baseline(
            "INCOMPLETE_VALUATION",
            f"Current portfolio valuation is {current.valuation_status}; the assessment "
            "retains its cited baseline.",
            current,
            current_fingerprint,
        )
    if current.holdings_freshness != "FRESH":
        return _Baseline(
            "STALE_HOLDINGS",
            "The latest accepted holdings snapshot is operationally stale.",
            current,
            current_fingerprint,
        )
    if current_fingerprint != value.portfolio_state_fingerprint:
        return _Baseline(
            "STALE_PORTFOLIO_STATE",
            "Canonical prices, FX, allocation context, or valuation fingerprint changed "
            "after publication.",
            current,
            current_fingerprint,
        )
    return _Baseline("CURRENT", None, current, current_fingerprint)


def _latest_revision(
    session: Session, portfolio_id: UUID, stream_key: str, *, lock: bool = False
) -> RiskAssessmentRevision | None:
    query = (
        select(RiskAssessmentRevision)
        .where(
            RiskAssessmentRevision.portfolio_id == portfolio_id,
            RiskAssessmentRevision.stream_key == stream_key,
        )
        .order_by(RiskAssessmentRevision.revision_number.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return session.scalar(query)


def _finding_changes(
    session: Session,
    previous: RiskAssessmentRevision | None,
    value: s.RiskAssessmentContractV1,
) -> list[dict[str, object]]:
    old_rows = (
        session.scalars(
            select(RiskAssessmentFinding).where(RiskAssessmentFinding.revision_id == previous.id)
        ).all()
        if previous is not None
        else []
    )
    old = {row.finding_key: row for row in old_rows}
    new = {item.finding_key: item for item in value.findings}
    changes: list[dict[str, object]] = []
    for key in sorted(old.keys() | new.keys()):
        before = old.get(key)
        after = new.get(key)
        if before is None:
            changes.append(
                {"finding_key": key, "change": "ADDED", "title": after.title if after else None}
            )
        elif after is None:
            changes.append({"finding_key": key, "change": "REMOVED", "title": before.title})
        elif (
            before.title != after.title
            or before.description != after.description
            or before.severity != after.severity
            or before.confidence != after.confidence
            or before.status != after.status
            or before.change_direction != after.change_direction
            or before.rationale != after.rationale
        ):
            changes.append(
                {
                    "finding_key": key,
                    "change": "UPDATED",
                    "title": after.title,
                    "prior_severity": before.severity,
                    "current_severity": after.severity,
                }
            )
    return changes


def _preview(
    session: Session,
    candidate: GoogleSheetsRiskSyncCandidate,
    value: s.RiskAssessmentContractV1,
) -> dict[str, object]:
    if candidate.portfolio_id != value.portfolio_id:
        raise DomainError("Risk candidate belongs to another portfolio", 409)
    portfolio = session.scalar(
        select(Portfolio).where(Portfolio.id == value.portfolio_id).with_for_update()
    )
    if portfolio is None:
        raise DomainError("Risk assessment portfolio identity was not found", 404)
    _validate_evidence(session, value)

    duplicate = session.scalar(
        select(RiskAssessmentRevision).where(
            RiskAssessmentRevision.portfolio_id == value.portfolio_id,
            RiskAssessmentRevision.stream_key == value.stream_key,
            RiskAssessmentRevision.external_revision_id == value.external_revision_id,
        )
    )
    if duplicate is not None:
        if duplicate.content_fingerprint == candidate.content_fingerprint:
            candidate.status = "ACCEPTED"
            candidate.accepted_revision_id = duplicate.id
            candidate.accepted_at = duplicate.accepted_at
            candidate.reviewer = duplicate.reviewer
            candidate.reviewer_note = "Exact replay; the canonical revision was already accepted."
            return {"status": "ALREADY_ACCEPTED", "accepted_revision_id": str(duplicate.id)}
        raise DomainError("External revision ID was already used for different content", 409)

    baseline = _baseline_status(session, value)
    prior = _latest_revision(session, value.portfolio_id, value.stream_key)
    expected_supersedes = prior.id if prior is not None else None
    if value.supersedes_revision_id != expected_supersedes:
        raise DomainError(
            "A newer risk assessment revision exists; reload and author against its revision ID",
            409,
        )
    if prior is not None and value.published_at < prior.published_at:
        raise DomainError("Risk assessment revisions cannot be backdated", 409)
    status = "CURRENT" if baseline.status == "CURRENT" else baseline.status
    candidate.baseline_status = status
    candidate.status = "READY" if baseline.status == "CURRENT" else "STALE_BASELINE"
    candidate.issue = baseline.issue
    return {
        "status": candidate.status,
        "baseline_status": status,
        "baseline_issue": baseline.issue,
        "current_holdings_snapshot_id": str(baseline.current_overview.snapshot.id)
        if baseline.current_overview.snapshot
        else None,
        "current_target_revision_id": str(baseline.current_overview.target_revision.id)
        if baseline.current_overview.target_revision
        else None,
        "current_fingerprint": baseline.current_fingerprint,
        "current_revision_id": str(prior.id) if prior else None,
        "finding_changes": _finding_changes(session, prior, value),
        "can_accept": candidate.status in {"READY", "STALE_BASELINE"},
    }


def preview_risk_candidate(session: Session, candidate_id: UUID) -> s.GoogleSheetsRiskCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsRiskSyncCandidate)
        .where(GoogleSheetsRiskSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise DomainError("Google Sheets risk candidate not found", 404)
    if candidate.status in {"ACCEPTED", "REJECTED"}:
        raise DomainError("This candidate already has a final review decision", 409)
    value = _candidate_contract(candidate)
    if value is None:
        return _candidate_read(session, candidate)
    try:
        preview = _preview(session, candidate, value)
    except DomainError as error:
        candidate.status = "CONFLICT" if error.status == 409 else "INVALID"
        candidate.issue = error.detail
        candidate.preview_data = {"status": candidate.status, "reason": error.detail}
        session.flush()
        return _candidate_read(session, candidate)
    except Exception as error:
        candidate.status = "INVALID"
        candidate.issue = f"Risk assessment validation failed: {type(error).__name__}"
        candidate.preview_data = {"status": "INVALID", "reason": candidate.issue}
        session.flush()
        return _candidate_read(session, candidate)
    candidate.preview_data = preview
    session.flush()
    return _candidate_read(session, candidate)


def _persist_revision(
    session: Session,
    candidate: GoogleSheetsRiskSyncCandidate,
    value: s.RiskAssessmentContractV1,
    reviewer: str,
    reviewer_note: str,
    baseline: _Baseline,
    acknowledge_stale_baseline: bool,
) -> RiskAssessmentRevision:
    prior = _latest_revision(session, value.portfolio_id, value.stream_key, lock=True)
    expected_supersedes = prior.id if prior is not None else None
    if value.supersedes_revision_id != expected_supersedes:
        raise DomainError(
            "A concurrent risk revision was accepted; preview this candidate again", 409
        )
    if prior is not None and value.published_at < prior.published_at:
        raise DomainError("Risk assessment revisions cannot be backdated", 409)
    if baseline.status != "CURRENT" and not acknowledge_stale_baseline:
        raise DomainError(
            "This assessment uses a stale or incomplete portfolio baseline. Explicitly "
            "acknowledge that limitation to accept it.",
            409,
        )
    if baseline.status == "CURRENT" and acknowledge_stale_baseline:
        raise DomainError("Stale-baseline acknowledgement was supplied for a current baseline", 422)

    revision = RiskAssessmentRevision(
        portfolio_id=value.portfolio_id,
        stream_key=value.stream_key,
        revision_number=1 if prior is None else prior.revision_number + 1,
        contract_version=value.contract_version,
        external_revision_id=value.external_revision_id,
        supersedes_revision_id=expected_supersedes,
        author_id=value.author_id,
        source_id=value.source_id,
        source_reference=value.source_reference,
        authored_at=value.authored_at,
        published_at=value.published_at,
        recorded_at=now(),
        reviewer=reviewer,
        reviewer_note=reviewer_note,
        accepted_at=now(),
        baseline_status_at_accept=baseline.status,
        baseline_stale_acknowledged=baseline.status != "CURRENT",
        portfolio_state_contract_version=value.portfolio_state_contract_version,
        portfolio_state_fingerprint=value.portfolio_state_fingerprint,
        holdings_snapshot_id=value.holdings_snapshot_id,
        target_revision_id=value.target_revision_id,
        valuation_as_of=value.valuation_as_of,
        coverage_status=value.coverage_status,
        coverage_note=value.coverage_note,
        summary=value.summary,
        rationale=value.rationale,
        content_fingerprint=candidate.content_fingerprint,
    )
    session.add(revision)
    session.flush()
    for item in value.findings:
        finding = RiskAssessmentFinding(
            revision_id=revision.id,
            finding_key=item.finding_key,
            scope=item.scope,
            company_id=item.company_id,
            category=item.category,
            title=item.title,
            description=item.description,
            severity=item.severity,
            confidence=item.confidence,
            status=item.status,
            change_direction=item.change_direction,
            rationale=item.rationale,
        )
        session.add(finding)
        session.flush()
        session.add_all(
            [
                RiskAssessmentEvidence(
                    finding_id=finding.id,
                    source_document_id=evidence.source_document_id,
                    reported_fundamental_observation_id=evidence.reported_fundamental_observation_id,
                    thesis_revision_id=evidence.thesis_revision_id,
                    thesis_claim_id=evidence.thesis_claim_id,
                    source_name=evidence.source_name,
                    external_identifier=evidence.external_identifier,
                    source_url=str(evidence.source_url) if evidence.source_url else None,
                    published_at=evidence.published_at,
                    excerpt=evidence.excerpt,
                    note=evidence.note,
                )
                for evidence in item.evidence
            ]
        )
    candidate.status = "ACCEPTED"
    candidate.accepted_revision_id = revision.id
    candidate.reviewer = reviewer
    candidate.reviewer_note = reviewer_note
    candidate.accepted_at = revision.accepted_at
    candidate.baseline_status = baseline.status
    candidate.issue = baseline.issue
    session.flush()
    return revision


def accept_risk_candidate(
    session: Session,
    candidate_id: UUID,
    reviewer: str,
    reviewer_note: str,
    acknowledge_stale_baseline: bool = False,
) -> s.GoogleSheetsRiskCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsRiskSyncCandidate)
        .where(GoogleSheetsRiskSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise DomainError("Google Sheets risk candidate not found", 404)
    if candidate.status == "ACCEPTED":
        return _candidate_read(session, candidate)
    if candidate.status == "REJECTED":
        raise DomainError("This risk assessment was rejected", 409)
    value = _candidate_contract(candidate)
    if value is None:
        raise DomainError(candidate.issue or "Risk assessment contract is invalid", 422)
    portfolio = session.scalar(
        select(Portfolio).where(Portfolio.id == value.portfolio_id).with_for_update()
    )
    if portfolio is None:
        raise DomainError("Risk assessment portfolio identity was not found", 404)
    _validate_evidence(session, value)
    baseline = _baseline_status(session, value)
    _persist_revision(
        session,
        candidate,
        value,
        reviewer,
        reviewer_note,
        baseline,
        acknowledge_stale_baseline,
    )
    return _candidate_read(session, candidate)


def reject_risk_candidate(
    session: Session, candidate_id: UUID, reviewer: str, reviewer_note: str
) -> s.GoogleSheetsRiskCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsRiskSyncCandidate)
        .where(GoogleSheetsRiskSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise DomainError("Google Sheets risk candidate not found", 404)
    if candidate.status == "ACCEPTED":
        raise DomainError("An accepted risk assessment cannot be rejected", 409)
    if candidate.status == "REJECTED":
        return _candidate_read(session, candidate)
    candidate.status = "REJECTED"
    candidate.reviewer = reviewer
    candidate.reviewer_note = reviewer_note
    candidate.rejected_at = now()
    session.flush()
    return _candidate_read(session, candidate)


def risk_revision_read(
    session: Session,
    revision: RiskAssessmentRevision,
    company_filter: UUID | None = None,
) -> s.RiskAssessmentRevisionRead:
    finding_query = select(RiskAssessmentFinding).where(
        RiskAssessmentFinding.revision_id == revision.id
    )
    if company_filter is not None:
        finding_query = finding_query.where(RiskAssessmentFinding.company_id == company_filter)
    findings = session.scalars(finding_query.order_by(RiskAssessmentFinding.finding_key)).all()
    finding_reads: list[s.RiskAssessmentFindingRead] = []
    for finding in findings:
        company = session.get(Company, finding.company_id) if finding.company_id else None
        evidence_rows = session.scalars(
            select(RiskAssessmentEvidence)
            .where(RiskAssessmentEvidence.finding_id == finding.id)
            .order_by(RiskAssessmentEvidence.id)
        ).all()
        evidence_reads: list[s.RiskAssessmentEvidenceRead] = []
        for evidence in evidence_rows:
            document = (
                session.get(SourceDocument, evidence.source_document_id)
                if evidence.source_document_id
                else None
            )
            evidence_reads.append(
                s.RiskAssessmentEvidenceRead(
                    id=evidence.id,
                    source_document_id=evidence.source_document_id,
                    source_document_title=document.title if document else None,
                    source_document_url=document.canonical_url if document else None,
                    reported_fundamental_observation_id=evidence.reported_fundamental_observation_id,
                    thesis_revision_id=evidence.thesis_revision_id,
                    thesis_claim_id=evidence.thesis_claim_id,
                    source_name=evidence.source_name,
                    external_identifier=evidence.external_identifier,
                    source_url=evidence.source_url,
                    published_at=evidence.published_at,
                    excerpt=evidence.excerpt,
                    note=evidence.note,
                )
            )
        finding_reads.append(
            s.RiskAssessmentFindingRead(
                id=finding.id,
                finding_key=finding.finding_key,
                scope=finding.scope,
                company_id=finding.company_id,
                company_name=company.name if company else None,
                category=finding.category,
                title=finding.title,
                description=finding.description,
                severity=finding.severity,
                confidence=finding.confidence,
                status=finding.status,
                change_direction=finding.change_direction,
                rationale=finding.rationale,
                evidence=evidence_reads,
            )
        )
    return s.RiskAssessmentRevisionRead(
        id=revision.id,
        portfolio_id=revision.portfolio_id,
        stream_key=revision.stream_key,
        revision_number=revision.revision_number,
        contract_version=revision.contract_version,
        external_revision_id=revision.external_revision_id,
        supersedes_revision_id=revision.supersedes_revision_id,
        author_id=revision.author_id,
        source_id=revision.source_id,
        source_reference=revision.source_reference,
        authored_at=revision.authored_at,
        published_at=revision.published_at,
        recorded_at=revision.recorded_at,
        reviewer=revision.reviewer,
        reviewer_note=revision.reviewer_note,
        accepted_at=revision.accepted_at,
        baseline_status_at_accept=revision.baseline_status_at_accept,
        baseline_stale_acknowledged=revision.baseline_stale_acknowledged,
        portfolio_state_contract_version=revision.portfolio_state_contract_version,
        portfolio_state_fingerprint=revision.portfolio_state_fingerprint,
        holdings_snapshot_id=revision.holdings_snapshot_id,
        target_revision_id=revision.target_revision_id,
        valuation_as_of=revision.valuation_as_of,
        coverage_status=revision.coverage_status,
        coverage_note=revision.coverage_note,
        summary=revision.summary,
        rationale=revision.rationale,
        content_fingerprint=revision.content_fingerprint,
        findings=finding_reads,
    )


def _revision_rows(
    session: Session, portfolio_id: UUID, limit: int
) -> list[RiskAssessmentRevision]:
    return list(
        session.scalars(
            select(RiskAssessmentRevision)
            .where(RiskAssessmentRevision.portfolio_id == portfolio_id)
            .order_by(
                RiskAssessmentRevision.recorded_at.desc(),
                RiskAssessmentRevision.revision_number.desc(),
            )
            .limit(limit)
        ).all()
    )


def portfolio_risk_assessments(
    session: Session, portfolio_id: UUID, limit: int = 50
) -> s.PortfolioRiskAssessmentsRead:
    if session.get(Portfolio, portfolio_id) is None:
        raise DomainError("Portfolio not found", 404)
    history = _revision_rows(session, portfolio_id, limit)
    current_by_stream: dict[str, RiskAssessmentRevision] = {}
    for revision in history:
        current_by_stream.setdefault(revision.stream_key, revision)
    current_rows = list(current_by_stream.values())
    return s.PortfolioRiskAssessmentsRead(
        portfolio_id=portfolio_id,
        current=[risk_revision_read(session, row) for row in current_rows],
        history=[risk_revision_read(session, row) for row in history],
    )


def company_risk_assessments(
    session: Session, company_id: UUID, limit: int = 50
) -> s.CompanyRiskAssessmentsRead:
    if session.get(Company, company_id) is None:
        raise DomainError("Company not found", 404)
    revisions = (
        session.scalars(
            select(RiskAssessmentRevision)
            .join(
                RiskAssessmentFinding,
                RiskAssessmentFinding.revision_id == RiskAssessmentRevision.id,
            )
            .where(RiskAssessmentFinding.company_id == company_id)
            .order_by(RiskAssessmentRevision.recorded_at.desc())
            .limit(limit)
        )
        .unique()
        .all()
    )
    stream_keys = {(revision.portfolio_id, revision.stream_key) for revision in revisions}
    latest_streams: list[RiskAssessmentRevision] = []
    for portfolio_id, stream_key in sorted(stream_keys, key=lambda item: (str(item[0]), item[1])):
        latest = session.scalar(
            select(RiskAssessmentRevision)
            .where(
                RiskAssessmentRevision.portfolio_id == portfolio_id,
                RiskAssessmentRevision.stream_key == stream_key,
            )
            .order_by(RiskAssessmentRevision.revision_number.desc())
            .limit(1)
        )
        if latest is not None:
            latest_streams.append(latest)
    return s.CompanyRiskAssessmentsRead(
        company_id=company_id,
        current=[risk_revision_read(session, row, company_id) for row in latest_streams],
        history=[risk_revision_read(session, row, company_id) for row in revisions],
    )


def _empty_sync_check(run: GoogleSheetsRiskSyncRun) -> s.GoogleSheetsRiskSyncCheckRead:
    return s.GoogleSheetsRiskSyncCheckRead(run=_run_read(run), new_candidates=[])
