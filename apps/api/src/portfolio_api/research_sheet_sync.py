"""Versioned Sheets transport for canonical research and thesis contracts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    GoogleSheetsResearchSyncCandidate,
    GoogleSheetsResearchSyncRun,
    InvestmentThesisRevision,
    ResearchRevision,
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
    _sha256,
)
from portfolio_api.investment_thesis import publish_investment_thesis_revision
from portfolio_api.research_forecasts import publish_research_revision
from portfolio_api.settings import Settings

RESEARCH_SYNC_TAB = "Application Research Inbox"
THESIS_SYNC_TAB = "Application Thesis Inbox"
MAX_RESEARCH_CANDIDATES = 200


def _configured(settings: Settings) -> bool:
    path = settings.google_sheets_service_account_file
    return bool(settings.google_sheets_spreadsheet_id and path and path.expanduser().is_file())


def _fingerprint(value: object) -> str:
    if hasattr(value, "model_dump"):
        payload = cast(dict[str, object], value.model_dump(mode="json"))
    else:
        payload = cast(dict[str, object], value)
    return _sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def _run_read(run: GoogleSheetsResearchSyncRun) -> s.GoogleSheetsResearchSyncRunRead:
    return s.GoogleSheetsResearchSyncRunRead.model_validate(run)


def _candidate_read(
    candidate: GoogleSheetsResearchSyncCandidate,
) -> s.GoogleSheetsResearchCandidateRead:
    return s.GoogleSheetsResearchCandidateRead(
        id=candidate.id,
        domain=candidate.domain,
        company_id=candidate.company_id,
        security_id=candidate.security_id,
        stream_key=candidate.stream_key,
        external_revision_id=candidate.external_revision_id,
        base_revision_id=candidate.base_revision_id,
        contract_version=candidate.contract_version,
        content_fingerprint=candidate.content_fingerprint,
        source_url=candidate.source_url,
        sheet_title=candidate.sheet_title,
        source_row_number=candidate.source_row_number,
        author_id=candidate.author_id,
        source_id=candidate.source_id,
        source_reference=candidate.source_reference,
        observed_at=candidate.observed_at,
        rationale=candidate.rationale,
        item_count=candidate.item_count,
        evidence_count=candidate.evidence_count,
        status=candidate.status,
        issue=candidate.issue,
        preview_data=candidate.preview_data,
        reviewer=candidate.reviewer,
        reviewer_note=candidate.reviewer_note,
        accepted_research_revision_id=candidate.accepted_research_revision_id,
        accepted_thesis_revision_id=candidate.accepted_thesis_revision_id,
        first_observed_at=candidate.first_observed_at,
        last_observed_at=candidate.last_observed_at,
        accepted_at=candidate.accepted_at,
        rejected_at=candidate.rejected_at,
    )


def research_sync_status(
    session: Session, settings: Settings
) -> s.GoogleSheetsResearchSyncStatusRead:
    run = session.scalar(
        select(GoogleSheetsResearchSyncRun)
        .order_by(GoogleSheetsResearchSyncRun.started_at.desc())
        .limit(1)
    )
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    return s.GoogleSheetsResearchSyncStatusRead(
        configured=bool(spreadsheet_id and settings.google_sheets_service_account_file),
        credentials_available=_configured(settings),
        spreadsheet_id=spreadsheet_id,
        spreadsheet_url=(
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            if spreadsheet_id
            else None
        ),
        research_inbox_tab=RESEARCH_SYNC_TAB,
        thesis_inbox_tab=THESIS_SYNC_TAB,
        last_run=_run_read(run) if run is not None else None,
    )


def check_research_sync_connection(
    settings: Settings, reader: GoogleSheetsReader | None = None
) -> s.GoogleSheetsResearchConnectionTestRead:
    checked_at = now()
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    if not spreadsheet_id:
        return s.GoogleSheetsResearchConnectionTestRead(
            connected=False,
            spreadsheet_id=None,
            spreadsheet_title=None,
            research_inbox_exists=False,
            thesis_inbox_exists=False,
            checked_at=checked_at,
            message="Set GOOGLE_SHEETS_SPREADSHEET_ID and the service-account credential.",
        )
    try:
        client = reader or GoogleSheetsApiReader(settings)
        research = client.test_connection(spreadsheet_id, RESEARCH_SYNC_TAB)
        thesis = client.test_connection(spreadsheet_id, THESIS_SYNC_TAB)
    except GoogleSheetsSyncError as error:
        return s.GoogleSheetsResearchConnectionTestRead(
            connected=False,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_title=None,
            research_inbox_exists=False,
            thesis_inbox_exists=False,
            checked_at=checked_at,
            message=str(error),
        )
    return s.GoogleSheetsResearchConnectionTestRead(
        connected=True,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=research.spreadsheet_title,
        research_inbox_exists=research.sync_tab_exists,
        thesis_inbox_exists=thesis.sync_tab_exists,
        checked_at=checked_at,
        message=(
            "Workbook access is ready; the research and thesis inboxes are read-only."
            if research.sync_tab_exists and thesis.sync_tab_exists
            else (
                "Workbook access works. Add each missing application-owned inbox tab "
                "to enable discovery."
            )
        ),
    )


def list_research_sync_runs(
    session: Session, limit: int = 25
) -> list[s.GoogleSheetsResearchSyncRunRead]:
    rows = session.scalars(
        select(GoogleSheetsResearchSyncRun)
        .order_by(GoogleSheetsResearchSyncRun.started_at.desc())
        .limit(limit)
    ).all()
    return [_run_read(row) for row in rows]


def list_research_sync_candidates(
    session: Session, status: str | None = None, limit: int = 100
) -> list[s.GoogleSheetsResearchCandidateRead]:
    query = select(GoogleSheetsResearchSyncCandidate).order_by(
        GoogleSheetsResearchSyncCandidate.first_observed_at.desc(),
        GoogleSheetsResearchSyncCandidate.id,
    )
    if status:
        query = query.where(GoogleSheetsResearchSyncCandidate.status == status)
    rows = session.scalars(query.limit(limit)).all()
    return [_candidate_read(row) for row in rows]


def _parse_contract(
    domain: Literal["RESEARCH", "THESIS"], text: str
) -> s.ResearchRevisionPublishContract | s.InvestmentThesisRevisionPublishContract:
    if len(text.encode("utf-8")) > MAX_CONTRACT_BYTES:
        raise ValueError("The contract exceeds the 1 MB inbox limit")
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("The inbox cell must contain one JSON contract object")
    if domain == "RESEARCH":
        research_value = s.ResearchRevisionPublishContract.model_validate(raw)
        if not research_value.evidence:
            raise ValueError("Research publication requires at least one source evidence item")
        return research_value
    thesis_value = s.InvestmentThesisRevisionPublishContract.model_validate(raw)
    if not any(claim.evidence for claim in thesis_value.claims):
        raise ValueError("Thesis publication requires evidence on at least one claim")
    return thesis_value


def _raw_text(raw: object, key: str) -> str | None:
    value = raw.get(key) if isinstance(raw, dict) else None
    return value.strip()[:1000] if isinstance(value, str) and value.strip() else None


def _make_candidate(
    session: Session,
    run: GoogleSheetsResearchSyncRun,
    spreadsheet_id: str,
    spreadsheet_title: str,
    sheet_id: int,
    domain: Literal["RESEARCH", "THESIS"],
    block: ContractBlock,
    seen_at: datetime,
) -> tuple[GoogleSheetsResearchSyncCandidate, bool]:
    raw_digest = _sha256(block.contract_text)
    parsed: s.ResearchRevisionPublishContract | s.InvestmentThesisRevisionPublishContract | None = (
        None
    )
    issue = block.issue
    raw: object = None
    if not issue:
        try:
            raw = json.loads(block.contract_text)
            parsed = _parse_contract(domain, block.contract_text)
            if block.external_revision_id != parsed.external_revision_id:
                raise ValueError("Inbox revision ID does not match the contract")
        except Exception as error:
            issue = f"Invalid {domain.lower()} contract: {error}"

    data = cast(dict[str, object], parsed.model_dump(mode="json")) if parsed is not None else None
    fingerprint = _fingerprint(parsed) if parsed is not None else raw_digest
    external_revision_id = (
        parsed.external_revision_id if parsed is not None else block.external_revision_id
    )
    company_id = parsed.company_id if parsed is not None else None
    security_id = parsed.security_id if parsed is not None else None
    stream_key = parsed.stream_key if parsed is not None else None
    author_id = parsed.author_id if parsed is not None else None
    source_id = parsed.source_id if parsed is not None else None
    source_reference = parsed.source_reference if parsed is not None else None
    observed_at = parsed.observed_at if parsed is not None else None
    rationale = parsed.rationale if parsed is not None else None
    base_revision_id = parsed.supersedes_revision_id if parsed is not None else None
    if parsed is None:
        external_revision_id = external_revision_id or _raw_text(raw, "external_revision_id")

    contract_version: str | None
    if domain == "RESEARCH" and isinstance(parsed, s.ResearchRevisionPublishContract):
        item_count = len(parsed.forecasts) + len(parsed.assessments)
        evidence_count = len(parsed.evidence)
        contract_version = parsed.contract_version
    elif isinstance(parsed, s.InvestmentThesisRevisionPublishContract):
        item_count = (1 if parsed.thesis_statement is not None else 0) + len(parsed.claims)
        evidence_count = len([evidence for claim in parsed.claims for evidence in claim.evidence])
        contract_version = parsed.contract_version
    else:
        item_count = 0
        evidence_count = 0
        contract_version = _raw_text(raw, "contract_version")

    idempotency_key = _sha256(
        "|".join((spreadsheet_id, domain, external_revision_id or block.publish_id, fingerprint))
    )
    existing = session.scalar(
        select(GoogleSheetsResearchSyncCandidate).where(
            GoogleSheetsResearchSyncCandidate.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        existing.last_seen_run_id = run.id
        existing.last_observed_at = seen_at
        return existing, False

    row_number = block.first_row_number
    candidate = GoogleSheetsResearchSyncCandidate(
        idempotency_key=idempotency_key,
        domain=domain,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=spreadsheet_title,
        sheet_id=sheet_id,
        sheet_title=RESEARCH_SYNC_TAB if domain == "RESEARCH" else THESIS_SYNC_TAB,
        source_row_number=row_number,
        source_url=(
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            f"#gid={sheet_id}&range=A{row_number}:E{row_number}"
        ),
        last_seen_run_id=run.id,
        contract_text=block.contract_text,
        contract_data=data,
        contract_version=contract_version,
        content_fingerprint=fingerprint,
        raw_sha256=raw_digest,
        company_id=company_id,
        security_id=security_id,
        stream_key=stream_key,
        external_revision_id=external_revision_id,
        base_revision_id=base_revision_id,
        author_id=author_id,
        source_id=source_id,
        source_reference=source_reference,
        observed_at=observed_at,
        rationale=rationale,
        item_count=item_count,
        evidence_count=evidence_count,
        status="INVALID" if issue else "PENDING",
        issue=issue,
        first_observed_at=seen_at,
        last_observed_at=seen_at,
    )
    session.add(candidate)
    session.flush()

    if parsed is not None:
        if domain == "RESEARCH":
            canonical_research = session.scalar(
                select(ResearchRevision).where(
                    ResearchRevision.company_id == company_id,
                    ResearchRevision.stream_key == stream_key,
                    ResearchRevision.external_revision_id == external_revision_id,
                )
            )
            if canonical_research is not None:
                if canonical_research.content_fingerprint == fingerprint:
                    candidate.status = "ACCEPTED"
                    candidate.accepted_research_revision_id = canonical_research.id
                    candidate.accepted_at = canonical_research.recorded_at
                    candidate.reviewer_note = "Exact replay; the canonical revision already exists."
                else:
                    candidate.status = "CONFLICT"
                    candidate.issue = "External revision ID was already used for different content"
        else:
            canonical_thesis = session.scalar(
                select(InvestmentThesisRevision).where(
                    InvestmentThesisRevision.company_id == company_id,
                    InvestmentThesisRevision.stream_key == stream_key,
                    InvestmentThesisRevision.external_revision_id == external_revision_id,
                )
            )
            if canonical_thesis is not None:
                if canonical_thesis.content_fingerprint == fingerprint:
                    candidate.status = "ACCEPTED"
                    candidate.accepted_thesis_revision_id = canonical_thesis.id
                    candidate.accepted_at = canonical_thesis.recorded_at
                    candidate.reviewer_note = "Exact replay; the canonical revision already exists."
                else:
                    candidate.status = "CONFLICT"
                    candidate.issue = "External revision ID was already used for different content"

        pending_conflict = session.scalar(
            select(GoogleSheetsResearchSyncCandidate).where(
                GoogleSheetsResearchSyncCandidate.domain == domain,
                GoogleSheetsResearchSyncCandidate.company_id == company_id,
                GoogleSheetsResearchSyncCandidate.stream_key == stream_key,
                GoogleSheetsResearchSyncCandidate.external_revision_id == external_revision_id,
                GoogleSheetsResearchSyncCandidate.content_fingerprint != fingerprint,
                GoogleSheetsResearchSyncCandidate.id != candidate.id,
            )
        )
        if pending_conflict is not None and candidate.status == "PENDING":
            candidate.status = "CONFLICT"
            candidate.issue = "This external revision ID already has a different captured contract"
    session.flush()
    return candidate, True


def run_research_sync_check(
    session: Session,
    settings: Settings,
    reader: GoogleSheetsReader | None = None,
) -> s.GoogleSheetsResearchSyncCheckRead:
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    run = GoogleSheetsResearchSyncRun(
        spreadsheet_id=spreadsheet_id,
        status="BLOCKED" if not spreadsheet_id else "SUCCEEDED",
        started_at=now(),
    )
    session.add(run)
    session.flush()
    if not spreadsheet_id:
        run.error_code = "NOT_CONFIGURED"
        run.error_message = "Set GOOGLE_SHEETS_SPREADSHEET_ID"
        run.completed_at = now()
        return s.GoogleSheetsResearchSyncCheckRead(run=_run_read(run), new_candidates=[])

    client = reader or GoogleSheetsApiReader(settings)
    tabs: tuple[tuple[Literal["RESEARCH", "THESIS"], str], ...] = (
        ("RESEARCH", RESEARCH_SYNC_TAB),
        ("THESIS", THESIS_SYNC_TAB),
    )
    snapshots: list[tuple[Literal["RESEARCH", "THESIS"], InboxSnapshot]] = []
    failures: list[tuple[str, str, str]] = []
    for domain, tab in tabs:
        try:
            snapshot = client.read_inbox(spreadsheet_id, tab)
            if not snapshot.connection.sync_tab_exists or snapshot.connection.sheet_id is None:
                failures.append((tab, "SYNC_TAB_MISSING", f"The fixed inbox '{tab}' is missing"))
                continue
            snapshots.append((domain, snapshot))
            run.spreadsheet_title = snapshot.connection.spreadsheet_title
        except GoogleSheetsSyncError as error:
            failures.append((tab, error.code, str(error)))

    if not snapshots:
        run.status = (
            "BLOCKED"
            if failures and all(code == "SYNC_TAB_MISSING" for _, code, _ in failures)
            else "FAILED"
        )
        run.error_code = failures[0][1] if failures else "NO_INBOXES"
        run.error_message = "; ".join(message for _, _, message in failures) or (
            "No research inbox was readable"
        )
        run.completed_at = now()
        session.flush()
        return s.GoogleSheetsResearchSyncCheckRead(run=_run_read(run), new_candidates=[])

    seen_at = now()
    new_candidates: list[GoogleSheetsResearchSyncCandidate] = []
    run.candidate_count = sum(len(snapshot.blocks) for _, snapshot in snapshots)
    for domain, snapshot in snapshots:
        assert snapshot.connection.sheet_id is not None
        for block in snapshot.blocks:
            row, inserted = _make_candidate(
                session,
                run,
                spreadsheet_id,
                snapshot.connection.spreadsheet_title,
                snapshot.connection.sheet_id,
                domain,
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
    if failures:
        run.status = "PARTIAL"
        run.error_code = failures[0][1]
        run.error_message = "; ".join(f"{tab}: {message}" for tab, _, message in failures)
    elif run.issue_count:
        run.status = "PARTIAL"
    else:
        run.status = "SUCCEEDED"
    run.completed_at = now()
    session.flush()
    return s.GoogleSheetsResearchSyncCheckRead(
        run=_run_read(run),
        new_candidates=[_candidate_read(row) for row in new_candidates],
    )


def _load_candidate_contract(
    candidate: GoogleSheetsResearchSyncCandidate,
) -> s.ResearchRevisionPublishContract | s.InvestmentThesisRevisionPublishContract:
    value = _parse_contract(candidate.domain, candidate.contract_text)  # type: ignore[arg-type]
    if (
        value.company_id != candidate.company_id
        or value.security_id != candidate.security_id
        or value.stream_key != candidate.stream_key
        or value.external_revision_id != candidate.external_revision_id
        or value.supersedes_revision_id != candidate.base_revision_id
    ):
        raise ValueError("Stored contract identity changed after capture")
    return value


def _preview_payload(
    session: Session,
    candidate: GoogleSheetsResearchSyncCandidate,
    value: s.ResearchRevisionPublishContract | s.InvestmentThesisRevisionPublishContract,
) -> dict[str, object]:
    current_revision_id: UUID | None
    current_revision_number: int | None
    if candidate.domain == "RESEARCH":
        current_research = session.scalar(
            select(ResearchRevision)
            .where(
                ResearchRevision.company_id == value.company_id,
                ResearchRevision.stream_key == value.stream_key,
            )
            .order_by(ResearchRevision.revision_number.desc())
            .limit(1)
        )
        assert isinstance(value, s.ResearchRevisionPublishContract)
        result = {
            "contract_type": "ResearchRevisionContractV1",
            "forecast_count": len(value.forecasts),
            "assessment_count": len(value.assessments),
            "evidence_count": len(value.evidence),
            "forecasts": [
                {
                    "metric": row.metric.value,
                    "fiscal_year": row.fiscal_year,
                    "fiscal_period": row.fiscal_period,
                    "scenario": row.scenario.value,
                    "value": str(row.value) if row.value is not None else None,
                    "currency": row.currency,
                    "unit": row.unit,
                    "availability_status": row.availability_status.value,
                    "confidence": row.confidence.value,
                }
                for row in value.forecasts
            ],
            "assessments": [
                {
                    "assessment_type": row.assessment_type.value,
                    "status": row.status.value,
                    "narrative": row.narrative,
                }
                for row in value.assessments
            ],
            "evidence": [
                {
                    "source_document_id": (
                        str(row.source_document_id) if row.source_document_id else None
                    ),
                    "source_name": row.source_name,
                    "external_identifier": row.external_identifier,
                    "source_url": str(row.source_url) if row.source_url else None,
                    "published_at": row.published_at.isoformat() if row.published_at else None,
                    "excerpt": row.excerpt,
                    "note": row.note,
                }
                for row in value.evidence
            ],
            "trigger_references": [
                {
                    "trigger_id": str(row.trigger_id),
                    "classification": row.classification.value,
                    "classification_rationale": row.classification_rationale,
                }
                for row in value.trigger_references
            ],
        }
        current_revision_id = current_research.id if current_research else None
        current_revision_number = current_research.revision_number if current_research else None
    else:
        current_thesis = session.scalar(
            select(InvestmentThesisRevision)
            .where(
                InvestmentThesisRevision.company_id == value.company_id,
                InvestmentThesisRevision.stream_key == value.stream_key,
            )
            .order_by(InvestmentThesisRevision.revision_number.desc())
            .limit(1)
        )
        assert isinstance(value, s.InvestmentThesisRevisionPublishContract)
        result = {
            "contract_type": "InvestmentThesisContractV1",
            "thesis_statement": value.thesis_statement,
            "confidence": value.confidence.value,
            "claim_count": len(value.claims),
            "evidence_count": len(
                [evidence for claim in value.claims for evidence in claim.evidence]
            ),
            "claims": [
                {
                    "claim_key": claim.claim_key,
                    "claim_type": claim.claim_type.value,
                    "status": claim.status.value,
                    "statement": claim.statement,
                    "confidence": claim.confidence.value,
                    "evidence": [
                        {
                            "source_document_id": (
                                str(evidence.source_document_id)
                                if evidence.source_document_id
                                else None
                            ),
                            "reported_fundamental_observation_id": (
                                str(evidence.reported_fundamental_observation_id)
                                if evidence.reported_fundamental_observation_id
                                else None
                            ),
                            "source_name": evidence.source_name,
                            "external_identifier": evidence.external_identifier,
                            "source_url": str(evidence.source_url) if evidence.source_url else None,
                            "published_at": evidence.published_at.isoformat()
                            if evidence.published_at
                            else None,
                            "excerpt": evidence.excerpt,
                            "note": evidence.note,
                        }
                        for evidence in claim.evidence
                    ],
                }
                for claim in value.claims
            ],
            "trigger_references": [
                {
                    "trigger_id": str(row.trigger_id),
                    "classification": row.classification.value,
                    "classification_rationale": row.classification_rationale,
                }
                for row in value.trigger_references
            ],
        }
        current_revision_id = current_thesis.id if current_thesis else None
        current_revision_number = current_thesis.revision_number if current_thesis else None
    result.update(
        {
            "status": "READY",
            "base_revision_id": str(value.supersedes_revision_id)
            if value.supersedes_revision_id
            else None,
            "current_revision_id": (str(current_revision_id) if current_revision_id else None),
            "current_revision_number": current_revision_number,
            "observed_at": value.observed_at.isoformat(),
            "company_id": str(value.company_id),
            "security_id": str(value.security_id) if value.security_id else None,
        }
    )
    return result


def preview_research_candidate(
    session: Session, candidate_id: UUID
) -> s.GoogleSheetsResearchCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsResearchSyncCandidate)
        .where(GoogleSheetsResearchSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise DomainError("Google Sheets research candidate not found", 404)
    if candidate.status in {"ACCEPTED", "REJECTED"}:
        raise DomainError("This candidate already has a final review decision", 409)
    try:
        value = _load_candidate_contract(candidate)
    except Exception as error:
        candidate.status = "INVALID"
        candidate.issue = f"Invalid captured contract: {error}"
        candidate.preview_data = {"status": "INVALID", "reason": candidate.issue}
        session.flush()
        return _candidate_read(candidate)

    probe = session.begin_nested()
    canonical_revision_id: UUID
    canonical_recorded_at: datetime
    try:
        if candidate.domain == "RESEARCH":
            assert isinstance(value, s.ResearchRevisionPublishContract)
            canonical_research, publish_result = publish_research_revision(session, value)
            revision_number = canonical_research.revision_number
            canonical_revision_id = canonical_research.id
            canonical_recorded_at = canonical_research.recorded_at
        else:
            assert isinstance(value, s.InvestmentThesisRevisionPublishContract)
            canonical_thesis, publish_result = publish_investment_thesis_revision(session, value)
            revision_number = canonical_thesis.revision_number
            canonical_revision_id = canonical_thesis.id
            canonical_recorded_at = canonical_thesis.recorded_at
    except DomainError as error:
        probe.rollback()
        candidate.status = "CONFLICT" if error.status == 409 else "INVALID"
        candidate.issue = error.detail
        candidate.preview_data = {"status": candidate.status, "reason": error.detail}
        session.flush()
        return _candidate_read(candidate)
    except Exception as error:
        probe.rollback()
        candidate.status = "INVALID"
        candidate.issue = f"Contract validation failed: {type(error).__name__}"
        candidate.preview_data = {"status": "INVALID", "reason": candidate.issue}
        session.flush()
        return _candidate_read(candidate)
    else:
        probe.rollback()

    if publish_result == "ALREADY_PUBLISHED":
        candidate.status = "ACCEPTED"
        if candidate.domain == "RESEARCH":
            candidate.accepted_research_revision_id = canonical_revision_id
        else:
            candidate.accepted_thesis_revision_id = canonical_revision_id
        candidate.accepted_at = canonical_recorded_at
        candidate.reviewer_note = "Exact replay; the canonical revision already exists."
        candidate.issue = None
        candidate.preview_data = {
            "status": "ACCEPTED",
            "reason": "Exact canonical replay; no new revision was created.",
            "canonical_revision_id": str(canonical_revision_id),
        }
        session.flush()
        return _candidate_read(candidate)

    candidate.status = "READY"
    candidate.issue = None
    preview_data = _preview_payload(session, candidate, value)
    preview_data["candidate_revision_number"] = revision_number
    candidate.preview_data = preview_data
    session.flush()
    return _candidate_read(candidate)


def accept_research_candidate(
    session: Session,
    candidate_id: UUID,
    reviewer: str,
    reviewer_note: str,
) -> s.GoogleSheetsResearchCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsResearchSyncCandidate)
        .where(GoogleSheetsResearchSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise DomainError("Google Sheets research candidate not found", 404)
    if candidate.status == "ACCEPTED":
        return _candidate_read(candidate)
    if candidate.status == "REJECTED":
        raise DomainError("This research proposal was rejected", 409)
    if candidate.status != "READY":
        raise DomainError("Preview a valid proposal before accepting it", 409)
    try:
        value = _load_candidate_contract(candidate)
        if candidate.domain == "RESEARCH":
            assert isinstance(value, s.ResearchRevisionPublishContract)
            canonical_research, _ = publish_research_revision(session, value)
            candidate.accepted_research_revision_id = canonical_research.id
        else:
            assert isinstance(value, s.InvestmentThesisRevisionPublishContract)
            canonical_thesis, _ = publish_investment_thesis_revision(session, value)
            candidate.accepted_thesis_revision_id = canonical_thesis.id
    except DomainError as error:
        candidate.status = "CONFLICT" if error.status == 409 else "INVALID"
        candidate.issue = error.detail
        candidate.preview_data = {"status": candidate.status, "reason": error.detail}
        session.flush()
        return _candidate_read(candidate)
    candidate.status = "ACCEPTED"
    candidate.reviewer = reviewer.strip()
    candidate.reviewer_note = reviewer_note.strip()
    candidate.accepted_at = now()
    candidate.issue = None
    session.flush()
    return _candidate_read(candidate)


def reject_research_candidate(
    session: Session, candidate_id: UUID, reviewer: str, reviewer_note: str
) -> s.GoogleSheetsResearchCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsResearchSyncCandidate)
        .where(GoogleSheetsResearchSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise DomainError("Google Sheets research candidate not found", 404)
    if candidate.status == "ACCEPTED":
        raise DomainError("An accepted research revision cannot be rejected", 409)
    if candidate.status == "REJECTED":
        return _candidate_read(candidate)
    candidate.status = "REJECTED"
    candidate.reviewer = reviewer.strip()
    candidate.reviewer_note = reviewer_note.strip()
    candidate.rejected_at = now()
    session.flush()
    return _candidate_read(candidate)
