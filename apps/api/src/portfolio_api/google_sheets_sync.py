"""Read-only Google Sheets contract discovery and reviewed revision acceptance."""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as operations
from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    GoogleSheetsSyncCandidate,
    GoogleSheetsSyncRun,
    Listing,
    Security,
    now,
)
from portfolio_api.model_revision_evidence import (
    resolve_model_evidence_reference,
    unresolved_model_evidence_read,
)
from portfolio_api.settings import REPOSITORY_PATH, Settings

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
MAX_INBOX_ROWS = 5000
MAX_CONTRACT_BYTES = 1_000_000
MAX_CONTRACT_CHUNKS = 100
MAX_CHUNK_CHARACTERS = 40_000
POLL_MINIMUM_SECONDS = 60
SUPPORTED_CONTRACT_VERSIONS = {"1.0.0", "1.1.0", "1.2.0", "2.0.0", "2.1.0"}


class GoogleSheetsSyncError(Exception):
    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class GoogleSheetsReader(Protocol):
    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult: ...

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot: ...


@dataclass(frozen=True)
class ConnectionResult:
    spreadsheet_title: str
    sync_tab_exists: bool
    sheet_id: int | None


@dataclass(frozen=True)
class ContractBlock:
    publish_id: str
    external_revision_id: str | None
    first_row_number: int
    contract_text: str
    issue: str | None = None


@dataclass(frozen=True)
class InboxSnapshot:
    connection: ConnectionResult
    blocks: list[ContractBlock]


@dataclass(frozen=True)
class ParsedContract:
    contract: s.FinancialModelContractV1 | s.AdditionalModelPortableContractV2
    data: dict[str, object]
    contract_version: str
    external_revision_id: str
    base_revision_id: UUID
    model_id: UUID
    company_id: UUID
    valuation_listing_id: UUID
    model_type: str
    model_name: str
    source_model_key: str | None
    model_currency: str
    rationale: str | None


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contract_version(value: dict[str, object]) -> str | None:
    version = value.get("contract_version")
    return version if isinstance(version, str) else None


def _validation_issue(error: Exception) -> str:
    from pydantic import ValidationError

    if isinstance(error, ValidationError):
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"])
        return f"Invalid model contract at {path}: {first['msg']}"
    return str(error)


def parse_portable_contract(text: str) -> ParsedContract:
    if len(text.encode("utf-8")) > MAX_CONTRACT_BYTES:
        raise ValueError("The model contract exceeds the 1 MB inbox limit")
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("The inbox cell must contain one JSON model contract object")
    version = _contract_version(cast(dict[str, object], raw))
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        raise ValueError(f"Unsupported portable model contract version: {version or 'missing'}")
    contract: s.FinancialModelContractV1 | s.AdditionalModelPortableContractV2
    candidate_rationale: str | None
    if version in {"1.0.0", "1.1.0", "1.2.0"}:
        contract = s.FinancialModelContractV1.model_validate(raw)
        identity = contract.model
        candidate_rationale = contract.candidate_revision.rationale
        external_revision_id = contract.candidate_revision.source_revision_id
        base_revision_id = contract.base_revision.revision_id
        listing_id = identity.valuation_listing_id
        model_id = identity.model_id
        company_id = identity.company_id
        model_type = str(identity.model_type)
        model_name = identity.model_name
        source_model_key = identity.source_model_key
        currency = identity.model_currency
    else:
        contract = s.AdditionalModelPortableContractV2.model_validate(raw)
        candidate_rationale = contract.candidate_revision.rationale
        external_revision_id = contract.candidate_revision.source_revision_id
        base_revision_id = contract.base_revision_id
        listing_id = contract.valuation_listing_id
        model_id = contract.model_id
        company_id = contract.company_id
        model_type = str(contract.model_type)
        model_name = contract.model_name
        source_model_key = contract.source_model_key
        currency = contract.model_currency
    rationale = candidate_rationale
    data = cast(dict[str, object], contract.model_dump(mode="json"))
    return ParsedContract(
        contract=contract,
        data=data,
        contract_version=version,
        external_revision_id=external_revision_id,
        base_revision_id=base_revision_id,
        model_id=model_id,
        company_id=company_id,
        valuation_listing_id=listing_id,
        model_type=str(model_type),
        model_name=model_name,
        source_model_key=source_model_key,
        model_currency=str(currency),
        rationale=rationale,
    )


def _tab_range(sync_tab: str) -> str:
    escaped_title = sync_tab.replace("'", "''")
    return f"'{escaped_title}'!A2:E{MAX_INBOX_ROWS + 1}"


class GoogleSheetsApiReader:
    """Small Google Sheets v4 REST client using a dedicated read-only service account."""

    def __init__(self, settings: Settings, session: Any | None = None) -> None:
        if not settings.google_sheets_spreadsheet_id:
            raise GoogleSheetsSyncError("NOT_CONFIGURED", "Set GOOGLE_SHEETS_SPREADSHEET_ID")
        credential_path = settings.google_sheets_service_account_file
        if credential_path is None:
            raise GoogleSheetsSyncError(
                "CREDENTIALS_NOT_CONFIGURED", "Set GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE"
            )
        credential_path = credential_path.expanduser().resolve()
        if credential_path.is_relative_to(REPOSITORY_PATH.resolve()):
            raise GoogleSheetsSyncError(
                "CREDENTIALS_IN_REPOSITORY", "Keep the Google credential outside the repository"
            )
        if not credential_path.is_file():
            raise GoogleSheetsSyncError(
                "CREDENTIAL_FILE_MISSING", "The configured Google service-account file is missing"
            )
        self.spreadsheet_id = settings.google_sheets_spreadsheet_id
        self.timeout = settings.google_sheets_request_timeout_seconds
        if session is None:
            try:
                from google.auth.transport.requests import AuthorizedSession
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    str(credential_path), scopes=[SHEETS_SCOPE]
                )  # type: ignore[no-untyped-call]
                session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
            except Exception as error:
                raise GoogleSheetsSyncError(
                    "CREDENTIAL_INVALID", "The Google service-account credential could not load"
                ) from error
        self.session = session

    def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = self.session.get(url, timeout=(5, self.timeout))
        except Exception as error:
            raise GoogleSheetsSyncError(
                "NETWORK_ERROR", f"Google Sheets request failed ({type(error).__name__})"
            ) from error
        if response.status_code >= 400:
            if response.status_code in {401, 403}:
                message = "Google rejected the service-account credential or workbook permission"
            elif response.status_code == 404:
                message = (
                    "The configured spreadsheet was not found or is not shared "
                    "with the service account"
                )
            elif response.status_code == 429:
                message = "Google Sheets API rate limit reached; retry after a short delay"
            else:
                message = f"Google Sheets API returned HTTP {response.status_code}"
            raise GoogleSheetsSyncError("GOOGLE_API_ERROR", message, status=response.status_code)
        try:
            value = response.json()
        except (TypeError, ValueError) as error:
            raise GoogleSheetsSyncError(
                "INVALID_RESPONSE", "Google Sheets returned invalid JSON"
            ) from error
        if not isinstance(value, dict):
            raise GoogleSheetsSyncError(
                "INVALID_RESPONSE", "Google Sheets returned an invalid response"
            )
        return value

    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult:
        if spreadsheet_id != self.spreadsheet_id:
            raise GoogleSheetsSyncError("SPREADSHEET_MISMATCH", "Unexpected spreadsheet ID")
        fields = "spreadsheetId,properties(title),sheets(properties(sheetId,title))"
        url = f"{SHEETS_API}/{quote(spreadsheet_id, safe='')}?fields={fields}"
        result = self._get_json(url)
        if result.get("spreadsheetId") != spreadsheet_id:
            raise GoogleSheetsSyncError(
                "SPREADSHEET_MISMATCH", "Google returned another spreadsheet"
            )
        props = result.get("properties")
        title = props.get("title") if isinstance(props, dict) else None
        sheets = result.get("sheets")
        sheet_id: int | None = None
        if isinstance(sheets, list):
            for item in sheets:
                properties = item.get("properties") if isinstance(item, dict) else None
                if isinstance(properties, dict) and properties.get("title") == sync_tab:
                    candidate_id = properties.get("sheetId")
                    sheet_id = candidate_id if isinstance(candidate_id, int) else None
                    break
        if not isinstance(title, str):
            raise GoogleSheetsSyncError("INVALID_RESPONSE", "Google returned no workbook title")
        return ConnectionResult(title, sheet_id is not None, sheet_id)

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        connection = self.test_connection(spreadsheet_id, sync_tab)
        if not connection.sync_tab_exists or connection.sheet_id is None:
            raise GoogleSheetsSyncError(
                "SYNC_TAB_MISSING",
                f"The read-only inbox tab '{sync_tab}' is missing; install the "
                "workbook adapter and publish a contract first",
            )
        cell_range = quote(_tab_range(sync_tab), safe="!:$'")
        query = "majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
        url = f"{SHEETS_API}/{quote(spreadsheet_id, safe='')}/values/{cell_range}?{query}"
        result = self._get_json(url)
        values = result.get("values", [])
        if not isinstance(values, list):
            raise GoogleSheetsSyncError(
                "INVALID_RESPONSE", "The contract inbox did not return rows"
            )
        return InboxSnapshot(connection, assemble_contract_blocks(values))


def assemble_contract_blocks(values: list[object]) -> list[ContractBlock]:
    """Reassemble explicitly published chunk rows; no other sheet/range is inspected."""
    grouped: OrderedDict[str, list[tuple[int, str | None, int | None, int | None, str]]] = (
        OrderedDict()
    )
    issues: list[ContractBlock] = []
    for offset, raw_row in enumerate(values):
        row_number = offset + 2
        if not isinstance(raw_row, list):
            issues.append(
                ContractBlock(f"row-{row_number}", None, row_number, "", "Inbox row is not tabular")
            )
            continue
        row = [str(value) for value in raw_row]
        if not any(value.strip() for value in row):
            continue
        padded = row + [""] * max(0, 5 - len(row))
        publish_id, external_id, index_text, count_text, chunk = padded[:5]
        if not publish_id.strip():
            issues.append(
                ContractBlock(
                    f"row-{row_number}",
                    external_id or None,
                    row_number,
                    chunk,
                    "Inbox row is missing its publish ID",
                )
            )
            continue
        try:
            index_value = int(index_text)
            count_value = int(count_text)
        except ValueError:
            index_value = None
            count_value = None
        grouped.setdefault(publish_id, []).append(
            (row_number, external_id or None, index_value, count_value, chunk)
        )

    blocks = list(issues)
    for publish_id, rows in grouped.items():
        rows.sort(key=lambda item: item[2] or 0)
        first_row = min(item[0] for item in rows)
        external_ids = {item[1] for item in rows}
        counts = {item[3] for item in rows}
        indexes = [item[2] for item in rows]
        count = next(iter(counts)) if len(counts) == 1 else None
        issue: str | None = None
        if len(external_ids) != 1:
            issue = "Chunk rows have inconsistent external revision IDs"
        elif len(counts) != 1 or count is None or count < 1 or count > MAX_CONTRACT_CHUNKS:
            issue = "Chunk rows have invalid or inconsistent chunk counts"
        elif indexes != list(range(1, count + 1)):
            issue = "Contract chunk sequence is incomplete or duplicated"
        text = "".join(item[4] for item in rows)
        if len(text.encode("utf-8")) > MAX_CONTRACT_BYTES:
            issue = "The model contract exceeds the 1 MB inbox limit"
        assembled_external_id: str | None = (
            next(iter(external_ids)) if len(external_ids) == 1 else None
        )
        blocks.append(ContractBlock(publish_id, assembled_external_id, first_row, text, issue))
    return blocks


def _settings_configured(settings: Settings) -> bool:
    credential_file = settings.google_sheets_service_account_file
    return bool(
        settings.google_sheets_spreadsheet_id
        and credential_file
        and credential_file.expanduser().is_file()
    )


def google_sheets_status(session: Session, settings: Settings) -> s.GoogleSheetsSyncStatusRead:
    last_run = session.scalar(
        select(GoogleSheetsSyncRun).order_by(GoogleSheetsSyncRun.started_at.desc()).limit(1)
    )
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    return s.GoogleSheetsSyncStatusRead(
        configured=bool(spreadsheet_id and settings.google_sheets_service_account_file),
        credentials_available=_settings_configured(settings),
        spreadsheet_id=spreadsheet_id,
        spreadsheet_url=(
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            if spreadsheet_id
            else None
        ),
        sync_tab=settings.google_sheets_sync_tab,
        polling_interval_seconds=settings.google_sheets_poll_seconds,
        last_run=s.GoogleSheetsSyncRunRead.model_validate(last_run) if last_run else None,
    )


def test_google_sheets_connection(
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
            message=(
                "Set GOOGLE_SHEETS_SPREADSHEET_ID and the read-only service-account credential."
            ),
        )
    try:
        client = reader or GoogleSheetsApiReader(settings)
        connection = client.test_connection(spreadsheet_id, settings.google_sheets_sync_tab)
    except GoogleSheetsSyncError as error:
        return s.GoogleSheetsConnectionTestRead(
            connected=False,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_title=None,
            sync_tab_exists=False,
            checked_at=checked_at,
            message=str(error),
        )
    message = (
        "Workbook access is ready; only the explicit model-contract inbox is read."
        if connection.sync_tab_exists
        else (
            f"Workbook access works. Add the '{settings.google_sheets_sync_tab}' tab "
            "with the Apps Script adapter to enable model-contract discovery."
        )
    )
    return s.GoogleSheetsConnectionTestRead(
        connected=True,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=connection.spreadsheet_title,
        sync_tab_exists=connection.sync_tab_exists,
        checked_at=checked_at,
        message=message,
    )


def _identity_material(raw: object) -> tuple[str, str]:
    raw_text = raw if isinstance(raw, str) else ""
    raw_digest = _sha256(raw_text)
    try:
        parsed = json.loads(raw_text)
        return _sha256(_canonical_json(parsed)), raw_digest
    except (TypeError, ValueError):
        return raw_digest, raw_digest


def _candidate_read(
    session: Session, row: GoogleSheetsSyncCandidate
) -> s.GoogleSheetsSyncCandidateRead:
    company = session.get(Company, row.company_id) if row.company_id else None
    contract_data = row.contract_data or {}
    proposal: s.FinancialModelProposalProvenance | None = None
    raw_proposal = contract_data.get("proposal")
    if isinstance(raw_proposal, dict):
        try:
            proposal = s.FinancialModelProposalProvenance.model_validate(raw_proposal)
        except Exception:
            proposal = None
    evidence_reads: list[s.FinancialModelEvidenceRead] = []
    raw_evidence = contract_data.get("supporting_evidence")
    if isinstance(raw_evidence, list):
        model = session.get(FinancialModel, row.model_id) if row.model_id else None
        listing = session.get(Listing, model.valuation_listing_id) if model else None
        security = session.get(Security, listing.security_id) if listing else None
        for raw_reference in raw_evidence:
            if not isinstance(raw_reference, dict):
                continue
            try:
                reference = s.FinancialModelEvidenceReference.model_validate(raw_reference)
            except Exception:
                continue
            if model is None or security is None:
                evidence_reads.append(
                    unresolved_model_evidence_read(
                        reference,
                        recorded_at=row.first_observed_at,
                        issue="The candidate model or valuation listing is unresolved.",
                    )
                )
                continue
            try:
                _, evidence_read = resolve_model_evidence_reference(
                    session,
                    company_id=model.company_id,
                    security_id=security.id,
                    reference=reference,
                )
            except ValueError as error:
                evidence_read = unresolved_model_evidence_read(
                    reference,
                    recorded_at=row.first_observed_at,
                    issue=str(error),
                )
            evidence_reads.append(evidence_read)
    return s.GoogleSheetsSyncCandidateRead(
        id=row.id,
        status=row.status,
        spreadsheet_id=row.spreadsheet_id,
        spreadsheet_title=row.spreadsheet_title,
        sheet_id=row.sheet_id,
        sheet_title=row.sheet_title,
        source_row_number=row.source_row_number,
        source_url=row.source_url,
        contract_version=row.contract_version,
        content_fingerprint=row.content_fingerprint,
        external_revision_id=row.external_revision_id,
        base_revision_id=row.base_revision_id,
        model_id=row.model_id,
        company_id=row.company_id,
        valuation_listing_id=row.valuation_listing_id,
        company_name=company.name if company else None,
        model_name=row.model_name,
        source_model_key=row.source_model_key,
        model_type=row.model_type,
        model_currency=row.model_currency,
        rationale=row.rationale,
        proposal=proposal,
        supporting_evidence=evidence_reads,
        issue=row.issue,
        preview_status=row.preview_status,
        preview_data=row.preview_data,
        previewed_at=row.previewed_at,
        accepted_revision_id=row.accepted_revision_id,
        reviewer=row.reviewer,
        decision_note=row.decision_note,
        first_observed_at=row.first_observed_at,
        last_observed_at=row.last_observed_at,
        accepted_at=row.accepted_at,
        rejected_at=row.rejected_at,
    )


def list_sync_candidates(
    session: Session, status: str | None = None, limit: int = 100
) -> list[s.GoogleSheetsSyncCandidateRead]:
    query = select(GoogleSheetsSyncCandidate).order_by(
        GoogleSheetsSyncCandidate.first_observed_at.desc(), GoogleSheetsSyncCandidate.id
    )
    if status:
        query = query.where(GoogleSheetsSyncCandidate.status == status)
    rows = session.scalars(query.limit(limit)).all()
    return [_candidate_read(session, row) for row in rows]


def list_sync_runs(session: Session, limit: int = 25) -> list[s.GoogleSheetsSyncRunRead]:
    rows = session.scalars(
        select(GoogleSheetsSyncRun).order_by(GoogleSheetsSyncRun.started_at.desc()).limit(limit)
    ).all()
    return [s.GoogleSheetsSyncRunRead.model_validate(row) for row in rows]


def _record_block(
    session: Session,
    run: GoogleSheetsSyncRun,
    spreadsheet_id: str,
    spreadsheet_title: str,
    sheet_id: int,
    sheet_title: str,
    block: ContractBlock,
    observed_at: datetime,
) -> tuple[GoogleSheetsSyncCandidate, bool]:
    fingerprint, raw_sha256 = _identity_material(block.contract_text)
    parsed: ParsedContract | None = None
    issue = block.issue
    if issue is None:
        try:
            parsed = parse_portable_contract(block.contract_text)
        except Exception as error:
            issue = _validation_issue(error)
    external_revision_id = block.external_revision_id
    if parsed is not None:
        if external_revision_id and external_revision_id != parsed.external_revision_id:
            issue = "Inbox revision ID does not match the portable contract"
        external_revision_id = parsed.external_revision_id
    material = "|".join(
        [spreadsheet_id, str(sheet_id), external_revision_id or block.publish_id, fingerprint]
    )
    key = _sha256(material)
    existing = session.scalar(
        select(GoogleSheetsSyncCandidate).where(GoogleSheetsSyncCandidate.idempotency_key == key)
    )
    if existing:
        existing.last_observed_at = observed_at
        existing.last_seen_run_id = run.id
        return existing, False

    status = "PENDING" if parsed is not None and issue is None else "INVALID"
    if external_revision_id:
        prior = session.scalar(
            select(GoogleSheetsSyncCandidate)
            .where(
                GoogleSheetsSyncCandidate.spreadsheet_id == spreadsheet_id,
                GoogleSheetsSyncCandidate.sheet_id == sheet_id,
                GoogleSheetsSyncCandidate.external_revision_id == external_revision_id,
            )
            .order_by(GoogleSheetsSyncCandidate.first_observed_at)
            .limit(1)
        )
        if prior and prior.content_fingerprint != fingerprint:
            status = "CONFLICT"
            issue = "This external revision ID was already observed with different content"

    parsed_data = parsed.data if parsed else None
    source_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet_id}"
    row = GoogleSheetsSyncCandidate(
        idempotency_key=key,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=spreadsheet_title,
        sheet_id=sheet_id,
        sheet_title=sheet_title,
        source_row_number=block.first_row_number,
        source_url=source_url,
        last_seen_run_id=run.id,
        contract_text=block.contract_text,
        contract_data=parsed_data,
        contract_version=parsed.contract_version if parsed else None,
        content_fingerprint=fingerprint,
        raw_sha256=raw_sha256,
        external_revision_id=external_revision_id,
        base_revision_id=parsed.base_revision_id if parsed else None,
        model_id=parsed.model_id if parsed else None,
        company_id=parsed.company_id if parsed else None,
        valuation_listing_id=parsed.valuation_listing_id if parsed else None,
        model_type=parsed.model_type if parsed else None,
        model_name=parsed.model_name if parsed else None,
        source_model_key=parsed.source_model_key if parsed else None,
        model_currency=parsed.model_currency if parsed else None,
        rationale=parsed.rationale if parsed else None,
        status=status,
        issue=issue,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
    )
    session.add(row)
    session.flush()
    return row, True


def run_sync_check(
    session: Session,
    settings: Settings,
    reader: GoogleSheetsReader | None = None,
) -> s.GoogleSheetsSyncCheckRead:
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    run = GoogleSheetsSyncRun(
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=None,
        status="BLOCKED",
        started_at=now(),
        candidate_count=0,
        new_count=0,
        unchanged_count=0,
        issue_count=0,
    )
    session.add(run)
    session.flush()
    if not spreadsheet_id:
        run.error_code = "NOT_CONFIGURED"
        run.error_message = (
            "Set GOOGLE_SHEETS_SPREADSHEET_ID and the read-only service-account credential."
        )
        run.completed_at = now()
        return s.GoogleSheetsSyncCheckRead(
            run=s.GoogleSheetsSyncRunRead.model_validate(run), new_candidates=[]
        )
    try:
        client = reader or GoogleSheetsApiReader(settings)
        snapshot = client.read_inbox(spreadsheet_id, settings.google_sheets_sync_tab)
    except GoogleSheetsSyncError as error:
        run.error_code = error.code
        run.error_message = str(error)
        run.status = (
            "BLOCKED"
            if error.code
            in {
                "NOT_CONFIGURED",
                "CREDENTIALS_NOT_CONFIGURED",
                "CREDENTIALS_IN_REPOSITORY",
                "CREDENTIAL_FILE_MISSING",
                "CREDENTIAL_INVALID",
                "SYNC_TAB_MISSING",
            }
            else "FAILED"
        )
        run.completed_at = now()
        return s.GoogleSheetsSyncCheckRead(
            run=s.GoogleSheetsSyncRunRead.model_validate(run), new_candidates=[]
        )

    run.spreadsheet_title = snapshot.connection.spreadsheet_title
    run.status = "SUCCEEDED"
    sheet_id = snapshot.connection.sheet_id
    if sheet_id is None:
        run.status = "BLOCKED"
        run.error_code = "SYNC_TAB_MISSING"
        run.error_message = (
            f"The configured tab '{settings.google_sheets_sync_tab}' does not exist."
        )
        run.completed_at = now()
        return s.GoogleSheetsSyncCheckRead(
            run=s.GoogleSheetsSyncRunRead.model_validate(run), new_candidates=[]
        )

    new_rows: list[GoogleSheetsSyncCandidate] = []
    observed_at = now()
    run.candidate_count = len(snapshot.blocks)
    for block in snapshot.blocks:
        row, inserted = _record_block(
            session,
            run,
            spreadsheet_id,
            snapshot.connection.spreadsheet_title,
            sheet_id,
            settings.google_sheets_sync_tab,
            block,
            observed_at,
        )
        if inserted:
            new_rows.append(row)
            run.new_count += 1
        else:
            run.unchanged_count += 1
        if row.status in {"INVALID", "CONFLICT"}:
            run.issue_count += 1
    if run.issue_count:
        run.status = "PARTIAL"
    run.completed_at = now()
    session.flush()
    return s.GoogleSheetsSyncCheckRead(
        run=s.GoogleSheetsSyncRunRead.model_validate(run),
        new_candidates=[_candidate_read(session, row) for row in new_rows],
    )


def _contract_from_candidate(
    candidate: GoogleSheetsSyncCandidate,
) -> ParsedContract | None:
    try:
        parsed = parse_portable_contract(candidate.contract_text)
    except Exception as error:
        candidate.status = "INVALID"
        candidate.issue = _validation_issue(error)
        candidate.preview_status = "INVALID"
        candidate.previewed_at = now()
        candidate.preview_data = None
        candidate.preview_fingerprint = None
        return None
    if (
        parsed.model_id != candidate.model_id
        or parsed.external_revision_id != candidate.external_revision_id
    ):
        candidate.status = "INVALID"
        candidate.issue = "Stored model identity or external revision identity changed"
        return None
    return parsed


def _preview_contract(
    session: Session, model_id: UUID, parsed: ParsedContract
) -> dict[str, object]:
    if parsed.model_id != model_id:
        raise operations.DomainError("The stored contract belongs to another model", 409)
    if isinstance(parsed.contract, s.FinancialModelContractV1):
        preview = operations.preview_financial_model_contract(session, model_id, parsed.contract)
        return cast(dict[str, object], preview.model_dump(mode="json"))
    else:
        additional_preview = operations.preview_additional_model_contract(
            session, model_id, parsed.contract
        )
        return cast(dict[str, object], additional_preview.model_dump(mode="json"))


def preview_sync_candidate(session: Session, candidate_id: UUID) -> s.GoogleSheetsSyncCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsSyncCandidate)
        .where(GoogleSheetsSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise operations.DomainError("Google Sheets candidate not found", 404)
    if candidate.status in {"ACCEPTED", "REJECTED"}:
        raise operations.DomainError("This candidate already has a final review decision", 409)
    parsed = _contract_from_candidate(candidate)
    if parsed is None or candidate.model_id is None:
        return _candidate_read(session, candidate)
    try:
        preview = _preview_contract(session, candidate.model_id, parsed)
    except operations.DomainError as error:
        preview = {
            "status": "CONFLICT" if error.status == 409 else "INVALID",
            "reason": error.detail,
        }
    status = str(preview.get("status", "INVALID"))
    candidate.preview_status = status
    candidate.preview_data = preview
    candidate.preview_fingerprint = _sha256(_canonical_json(preview))
    candidate.previewed_at = now()
    candidate.issue = cast(str | None, preview.get("reason"))
    if status == "READY":
        candidate.status = "READY"
    elif status == "CONFLICT":
        candidate.status = "CONFLICT"
    elif status in {"NO_CHANGES", "ALREADY_IMPORTED"}:
        candidate.status = "NO_CHANGES"
        if status == "ALREADY_IMPORTED":
            candidate.issue = (
                "This exact candidate is already present in canonical revision history."
            )
    elif status == "INVALID_BASE_SNAPSHOT" or status == "INVALID":
        candidate.status = "INVALID"
    else:
        candidate.status = "PENDING"
    session.flush()
    return _candidate_read(session, candidate)


def _candidate_contract_with_source(
    parsed: ParsedContract, candidate: GoogleSheetsSyncCandidate
) -> ParsedContract:
    source_suffix = f"Google Sheets workbook: {candidate.source_url}"
    updated: s.FinancialModelContractV1 | s.AdditionalModelPortableContractV2
    if isinstance(parsed.contract, s.FinancialModelContractV1):
        contract = parsed.contract
        existing_source = (
            contract.candidate_revision.source or "Google Sheets portable model contract"
        )
        source = f"{existing_source} | {source_suffix}"[-1000:]
        updated_candidate = contract.candidate_revision.model_copy(update={"source": source})
        updated = contract.model_copy(update={"candidate_revision": updated_candidate})
    else:
        additional_contract = parsed.contract
        existing_source = (
            additional_contract.candidate_revision.source or "Google Sheets portable model contract"
        )
        source = f"{existing_source} | {source_suffix}"[-1000:]
        additional_candidate = additional_contract.candidate_revision.model_copy(
            update={"source": source}
        )
        updated = additional_contract.model_copy(
            update={"candidate_revision": additional_candidate}
        )
    return ParsedContract(
        contract=updated,
        data=cast(dict[str, object], updated.model_dump(mode="json")),
        contract_version=parsed.contract_version,
        external_revision_id=parsed.external_revision_id,
        base_revision_id=parsed.base_revision_id,
        model_id=parsed.model_id,
        company_id=parsed.company_id,
        valuation_listing_id=parsed.valuation_listing_id,
        model_type=parsed.model_type,
        model_name=parsed.model_name,
        source_model_key=parsed.source_model_key,
        model_currency=parsed.model_currency,
        rationale=parsed.rationale,
    )


def accept_sync_candidate(
    session: Session,
    candidate_id: UUID,
    reviewer: str,
    decision_note: str | None = None,
) -> s.GoogleSheetsSyncCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsSyncCandidate)
        .where(GoogleSheetsSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise operations.DomainError("Google Sheets candidate not found", 404)
    if candidate.status == "ACCEPTED":
        return _candidate_read(session, candidate)
    if candidate.status == "REJECTED":
        raise operations.DomainError("A rejected candidate cannot be accepted", 409)
    parsed = _contract_from_candidate(candidate)
    if parsed is None or candidate.model_id is None:
        return _candidate_read(session, candidate)

    prior_preview_fingerprint = candidate.preview_fingerprint
    fresh_preview = _preview_contract(session, candidate.model_id, parsed)
    fresh_fingerprint = _sha256(_canonical_json(fresh_preview))
    candidate.preview_data = fresh_preview
    candidate.preview_status = cast(str | None, fresh_preview.get("status"))
    candidate.preview_fingerprint = fresh_fingerprint
    candidate.previewed_at = now()
    candidate.issue = cast(str | None, fresh_preview.get("reason"))
    if fresh_preview.get("status") != "READY":
        status = str(fresh_preview.get("status"))
        candidate.status = (
            "CONFLICT"
            if status == "CONFLICT"
            else (
                "INVALID"
                if status in {"INVALID", "INVALID_BASE_SNAPSHOT"}
                else ("NO_CHANGES" if status in {"NO_CHANGES", "ALREADY_IMPORTED"} else "PENDING")
            )
        )
        session.flush()
        return _candidate_read(session, candidate)
    if prior_preview_fingerprint is None or prior_preview_fingerprint != fresh_fingerprint:
        candidate.status = "READY"
        candidate.issue = (
            "Preview changed since it was last reviewed. Review the refreshed "
            "differences before accepting."
        )
        session.flush()
        return _candidate_read(session, candidate)

    sourced = _candidate_contract_with_source(parsed, candidate)
    try:
        if isinstance(sourced.contract, s.FinancialModelContractV1):
            dcf_import = operations.import_financial_model_contract(
                session, candidate.model_id, sourced.contract
            )
            imported_revision_id = dcf_import.revision.id
        else:
            additional_import = operations.import_additional_model_contract(
                session, candidate.model_id, sourced.contract
            )
            imported_revision_id = additional_import.revision.id
    except operations.DomainError as error:
        if error.status == 409:
            candidate.status = "CONFLICT"
            candidate.issue = error.detail
            candidate.preview_status = "CONFLICT"
            candidate.preview_data = {"status": "CONFLICT", "reason": error.detail}
            candidate.preview_fingerprint = _sha256(_canonical_json(candidate.preview_data))
            candidate.previewed_at = now()
            session.flush()
            return _candidate_read(session, candidate)
        raise
    candidate.status = "ACCEPTED"
    candidate.accepted_revision_id = imported_revision_id
    candidate.accepted_at = now()
    candidate.reviewer = reviewer.strip()
    candidate.decision_note = decision_note.strip() if decision_note else None
    candidate.issue = None
    session.flush()
    return _candidate_read(session, candidate)


def reject_sync_candidate(
    session: Session, candidate_id: UUID, reviewer: str, decision_note: str
) -> s.GoogleSheetsSyncCandidateRead:
    candidate = session.scalar(
        select(GoogleSheetsSyncCandidate)
        .where(GoogleSheetsSyncCandidate.id == candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise operations.DomainError("Google Sheets candidate not found", 404)
    if candidate.status == "ACCEPTED":
        raise operations.DomainError("An accepted candidate cannot be rejected", 409)
    if candidate.status != "REJECTED":
        candidate.status = "REJECTED"
        candidate.rejected_at = now()
        candidate.reviewer = reviewer.strip()
        candidate.decision_note = decision_note.strip()
        session.flush()
    return _candidate_read(session, candidate)


def _run_check_once(settings: Settings) -> dict[str, object]:
    from portfolio_api.database import create_database_engine
    from portfolio_api.research_sheet_sync import run_research_sync_check
    from portfolio_api.risk_assessments import run_risk_sync_check

    engine = create_database_engine(
        settings,
        write_operation="google_sheets_sync",
        write_operation_kind="ingestion",
    )
    if engine is None:
        raise SystemExit("Set DATABASE_URL before running Google Sheets sync")
    try:
        with Session(engine, expire_on_commit=False) as session:
            model_result = run_sync_check(session, settings)
            risk_result = run_risk_sync_check(session, settings)
            research_result = run_research_sync_check(session, settings)
            session.commit()
            return {
                "model_sync": cast(dict[str, object], model_result.model_dump(mode="json")),
                "risk_sync": cast(dict[str, object], risk_result.model_dump(mode="json")),
                "research_sync": cast(dict[str, object], research_result.model_dump(mode="json")),
            }
    finally:
        engine.dispose()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Read the explicit Google Sheets model, research and thesis inboxes"
    )
    parser.add_argument("check", nargs="?", choices=["check"], default="check")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=0,
        help="Optional repeat interval; must be at least 60 seconds. Omit for one check.",
    )
    args = parser.parse_args()
    if args.poll_seconds and args.poll_seconds < POLL_MINIMUM_SECONDS:
        parser.error("--poll-seconds must be zero or at least 60")
    settings = Settings()
    while True:
        print(json.dumps(_run_check_once(settings), indent=2))
        if not args.poll_seconds:
            break
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
