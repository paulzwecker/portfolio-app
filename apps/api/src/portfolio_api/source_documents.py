"""Primary-source filing metadata ingestion and immutable company references.

SEC submissions are normalized into document metadata and stable EDGAR links.
Filing bodies are not downloaded or retained. Company-published annual reports
and earnings releases can be registered as source references through the API.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    Actor,
    Company,
    CompanyProviderIdentifier,
    ExternalRawPayload,
    Security,
    SourceDocument,
    SourceDocumentBatch,
    SourceDocumentQuality,
    SourceDocumentType,
    now,
)
from portfolio_api.domain.schemas import SourceDocumentCreate
from portfolio_api.domain.services import DomainError
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    RawProviderRecord,
    raw_batch_fingerprint,
)
from portfolio_api.settings import Settings

SEC_PROVIDER_ID = "sec_edgar"
SEC_SOURCE_NAME = "U.S. Securities and Exchange Commission · EDGAR"
SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
SEC_SUBMISSIONS_VERSION = "submissions-v1"
SEC_DOCUMENT_NORMALIZER_VERSION = "sec-edgar-filings-v1"
COMPANY_REFERENCE_PROVIDER_ID = "company_source"
SUPPORTED_FORMS: dict[str, SourceDocumentType] = {
    "10-K": SourceDocumentType.TEN_K,
    "10-Q": SourceDocumentType.TEN_Q,
    "8-K": SourceDocumentType.EIGHT_K,
    "20-F": SourceDocumentType.TWENTY_F,
    "6-K": SourceDocumentType.SIX_K,
}
_ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_HISTORY_FILE_PATTERN = re.compile(r"^CIK\d{10}-submissions-\d+\.json$")


class CanonicalSourceDocument(BaseModel):
    """Provider-neutral document metadata; no document body or AI interpretation."""

    model_config = ConfigDict(frozen=True)

    company_id: UUID
    provider_id: str
    source_name: str
    source_jurisdiction: str | None
    external_identifier: str
    document_type: SourceDocumentType
    source_form: str | None
    title: str
    reporting_period: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    period_end: date | None
    filed_at: date | None
    published_at: date | None
    canonical_url: AnyHttpUrl
    retrieved_at: datetime | None
    is_amendment: bool
    data_quality: SourceDocumentQuality
    quality_reason: str | None
    actor: Actor


class SecSubmissionNormalization(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: UUID
    documents: tuple[CanonicalSourceDocument, ...]
    unsupported_form_count: int
    malformed_record_count: int


class SecSubmissionsProvider:
    """Fetch exact CIK submissions and SEC-linked historical submissions files."""

    provider_id = SEC_PROVIDER_ID

    def __init__(self, identifiers: dict[UUID, str], user_agent: str) -> None:
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT must identify the application and a contact email")
        self.identifiers = identifiers
        self.user_agent = user_agent.strip()

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        if query.domain != ExternalDataDomain.SOURCE_DOCUMENTS:
            raise ValueError("SEC submissions supports source documents only")
        requested: list[tuple[UUID, str]] = []
        for subject in query.subjects:
            if subject.kind != CanonicalSubjectKind.COMPANY or subject.id is None:
                raise ValueError("SEC submissions requires canonical company subjects")
            cik = self.identifiers.get(subject.id)
            if cik is None:
                continue
            if not re.fullmatch(r"\d{10}", cik):
                raise ValueError("SEC company identifiers must be ten-digit CIK values")
            requested.append((subject.id, cik))

        records: list[RawProviderRecord] = []
        request_count = 0
        for _company_id, cik in requested:
            base_url = f"{SEC_SUBMISSIONS_BASE}/CIK{cik}.json"
            payload, retrieved_at = await self._fetch_json(base_url, request_count)
            request_count += 1
            records.append(
                _raw_record(
                    payload,
                    f"CIK{cik}",
                    base_url,
                    retrieved_at,
                )
            )
            data = _json_object(payload)
            filings = data.get("filings", {}) if data is not None else {}
            files = filings.get("files", []) if isinstance(filings, dict) else []
            if not isinstance(files, list):
                continue
            for item in files:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not isinstance(name, str) or not _HISTORY_FILE_PATTERN.fullmatch(name):
                    continue
                if not name.startswith(f"CIK{cik}-"):
                    continue
                history_url = f"{SEC_SUBMISSIONS_BASE}/{quote(name, safe='-.')}"
                payload, retrieved_at = await self._fetch_json(history_url, request_count)
                request_count += 1
                records.append(
                    _raw_record(
                        payload,
                        f"CIK{cik}:HISTORY:{name}",
                        history_url,
                        retrieved_at,
                    )
                )
        return records

    async def _fetch_json(self, url: str, request_count: int) -> tuple[bytes, datetime]:
        # Stay comfortably below SEC's 10 requests/second fair-access ceiling.
        if request_count:
            await asyncio.sleep(0.15)
        payload = await asyncio.to_thread(_download_sec_json, url, self.user_agent)
        return payload, now()


class SecSubmissionsNormalizer:
    """Map only explicitly supported SEC filing forms to the canonical catalog."""

    domain = ExternalDataDomain.SOURCE_DOCUMENTS
    version = SEC_DOCUMENT_NORMALIZER_VERSION

    def normalize(
        self,
        record: RawProviderRecord,
        company_id: UUID,
        expected_cik: str,
    ) -> NormalizationResult[SecSubmissionNormalization]:
        payload = _json_object(record.payload)
        if payload is None:
            return NormalizationResult(
                disposition=NormalizationDisposition.REJECTED,
                observation=None,
                issues=(
                    NormalizationIssue(
                        code="INVALID_SEC_SUBMISSIONS_JSON",
                        message="The SEC submissions payload is not a JSON object.",
                        severity="ERROR",
                    ),
                ),
            )
        raw_cik = payload.get("cik")
        if isinstance(raw_cik, bool) or not isinstance(raw_cik, int | str):
            observed_cik = ""
        else:
            try:
                observed_cik = str(int(raw_cik)).zfill(10)
            except ValueError:
                observed_cik = ""
        if observed_cik != expected_cik:
            return NormalizationResult(
                disposition=NormalizationDisposition.REJECTED,
                observation=None,
                issues=(
                    NormalizationIssue(
                        code="SEC_CIK_MISMATCH",
                        message="The SEC response CIK does not match the reviewed company mapping.",
                        severity="ERROR",
                    ),
                ),
            )

        filings = payload.get("filings")
        rows: dict[str, Any] | None = None
        if isinstance(filings, dict) and isinstance(filings.get("recent"), dict):
            rows = filings["recent"]
        elif isinstance(payload.get("form"), list):
            # SEC historical submissions files use the columnar filing shape directly.
            rows = payload
        if rows is None:
            return NormalizationResult(
                disposition=NormalizationDisposition.REJECTED,
                observation=None,
                issues=(
                    NormalizationIssue(
                        code="SEC_SUBMISSIONS_SHAPE_UNRECOGNIZED",
                        message="The SEC response has no recognized submissions filing arrays.",
                        severity="ERROR",
                    ),
                ),
            )

        forms = rows.get("form", [])
        accessions = rows.get("accessionNumber", [])
        dates = rows.get("filingDate", [])
        report_dates = rows.get("reportDate", [])
        descriptions = rows.get("primaryDocDescription", [])
        if not isinstance(descriptions, list):
            descriptions = []
        columns = (forms, accessions, dates, report_dates)
        lengths = [len(item) for item in columns if isinstance(item, list)]
        if len(lengths) != len(columns):
            return NormalizationResult(
                disposition=NormalizationDisposition.REJECTED,
                observation=None,
                issues=(
                    NormalizationIssue(
                        code="SEC_SUBMISSIONS_COLUMNS_MISSING",
                        message="The SEC response is missing one or more expected filing columns.",
                        severity="ERROR",
                    ),
                ),
            )
        row_count = max(lengths, default=0)
        documents: list[CanonicalSourceDocument] = []
        unsupported = 0
        malformed = 0
        for index in range(row_count):
            form = _column_value(forms, index)
            base_form = form.removesuffix("/A") if form else ""
            document_type = SUPPORTED_FORMS.get(base_form)
            if document_type is None:
                unsupported += 1
                continue
            accession = _column_value(accessions, index)
            if accession is None or not _ACCESSION_PATTERN.fullmatch(accession):
                malformed += 1
                continue
            filed_at = _parse_date(_column_value(dates, index))
            period_end = _parse_date(_column_value(report_dates, index))
            accession_directory = accession.replace("-", "")
            cik_directory = str(int(expected_cik))
            # Link to the stable filing index; it lists the filing document and its exhibits.
            canonical_url = (
                f"{SEC_ARCHIVES_BASE}/{cik_directory}/{accession_directory}/{accession}-index.html"
            )
            title = _column_value(descriptions, index)
            if title is None:
                title = f"{form} filing" if form else "SEC filing"
            quality_reason = None
            quality = SourceDocumentQuality.PASS
            if period_end is None:
                quality = SourceDocumentQuality.DATA_CHECK
                quality_reason = "SEC submissions did not provide a reporting period end date."
            if filed_at is None:
                quality = SourceDocumentQuality.DATA_CHECK
                quality_reason = "SEC submissions did not provide a filing date."
            documents.append(
                CanonicalSourceDocument(
                    company_id=company_id,
                    provider_id=SEC_PROVIDER_ID,
                    source_name=SEC_SOURCE_NAME,
                    source_jurisdiction="US-SEC",
                    external_identifier=accession,
                    document_type=document_type,
                    source_form=form,
                    title=title[:500],
                    reporting_period=(
                        f"Period ending {period_end.isoformat()}" if period_end else None
                    ),
                    fiscal_year=None,
                    fiscal_period=None,
                    period_end=period_end,
                    filed_at=filed_at,
                    published_at=filed_at,
                    canonical_url=AnyHttpUrl(canonical_url),
                    retrieved_at=record.retrieved_at,
                    is_amendment=bool(form and form.endswith("/A")),
                    data_quality=quality,
                    quality_reason=quality_reason,
                    actor=Actor.IMPORT,
                )
            )
        return NormalizationResult(
            disposition=NormalizationDisposition.ACCEPTED,
            observation=SecSubmissionNormalization(
                company_id=company_id,
                documents=tuple(documents),
                unsupported_form_count=unsupported,
                malformed_record_count=malformed,
            ),
        )


def _download_sec_json(url: str, user_agent: str) -> bytes:
    if not url.startswith((SEC_SUBMISSIONS_BASE + "/", SEC_SUBMISSIONS_BASE + "?")):
        raise ValueError("SEC submissions adapter may request only SEC data.sec.gov endpoints")
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed SEC HTTPS host
        if response.status != 200:
            raise RuntimeError(f"SEC submissions returned HTTP {response.status}")
        return cast(bytes, response.read())


def _raw_record(
    payload: bytes, source_record_id: str, source_url: str, retrieved_at: datetime
) -> RawProviderRecord:
    return RawProviderRecord(
        domain=ExternalDataDomain.SOURCE_DOCUMENTS,
        provider_id=SEC_PROVIDER_ID,
        provider_schema_version=SEC_SUBMISSIONS_VERSION,
        source_record_id=source_record_id,
        source_url=AnyHttpUrl(source_url),
        media_type="application/json",
        retrieved_at=retrieved_at,
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


def _json_object(payload: bytes | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    try:
        parsed: Any = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _column_value(column: object, index: int) -> str | None:
    if not isinstance(column, list) or index >= len(column):
        return None
    value = column[index]
    return value.strip() if isinstance(value, str) and value.strip() else None


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _load_cik_mappings(session: Session, company_id: UUID | None = None) -> dict[UUID, str]:
    statement = select(CompanyProviderIdentifier).where(
        CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
        CompanyProviderIdentifier.identifier_type == "SEC_CIK",
    )
    if company_id is not None:
        statement = statement.where(CompanyProviderIdentifier.company_id == company_id)
    rows = list(session.scalars(statement))
    identifiers: dict[UUID, str] = {}
    for row in rows:
        if row.company_id in identifiers:
            raise ValueError(f"Company {row.company_id} has ambiguous SEC CIK mappings")
        identifiers[row.company_id] = row.identifier_value
    return identifiers


def _record_company(
    record: RawProviderRecord, identifiers_by_cik: dict[str, UUID]
) -> tuple[UUID, str]:
    match = re.match(r"^CIK(\d{10})(?::|$)", record.source_record_id or "")
    if match is None or match.group(1) not in identifiers_by_cik:
        raise ValueError(
            "SEC submission record is not tied to a reviewed canonical company mapping"
        )
    cik = match.group(1)
    return identifiers_by_cik[cik], cik


def _document_fields(document: CanonicalSourceDocument) -> dict[str, object]:
    return {
        "company_id": document.company_id,
        "provider_id": document.provider_id,
        "external_identifier": document.external_identifier,
        "source_name": document.source_name,
        "source_jurisdiction": document.source_jurisdiction,
        "document_type": document.document_type.value,
        "source_form": document.source_form,
        "title": document.title,
        "reporting_period": document.reporting_period,
        "period_end": document.period_end,
        "filed_at": document.filed_at,
        "published_at": document.published_at,
        "canonical_url": str(document.canonical_url),
        "is_amendment": document.is_amendment,
    }


def _find_amended_original(
    session: Session,
    document: CanonicalSourceDocument,
    pending: dict[tuple[str, str], SourceDocument],
) -> SourceDocument | None:
    if not document.is_amendment or document.period_end is None:
        return None
    predicates = [
        SourceDocument.company_id == document.company_id,
        SourceDocument.provider_id == document.provider_id,
        SourceDocument.document_type == document.document_type.value,
        SourceDocument.period_end == document.period_end,
        SourceDocument.is_amendment.is_(False),
    ]
    if document.filed_at is not None:
        predicates.append(SourceDocument.filed_at < document.filed_at)
    prior_statement = select(SourceDocument).where(*predicates)
    candidates = list(session.scalars(prior_statement))
    candidates.extend(
        item
        for (provider_id, _), item in pending.items()
        if provider_id == document.provider_id
        and item.company_id == document.company_id
        and item.document_type == document.document_type.value
        and item.period_end == document.period_end
        and not item.is_amendment
        and (
            document.filed_at is None or item.filed_at is None or item.filed_at < document.filed_at
        )
    )
    candidates.sort(key=lambda item: (item.filed_at or date.min, item.recorded_at), reverse=True)
    return candidates[0] if candidates else None


def ingest_sec_submissions(
    session: Session,
    query: ProviderQuery,
    records: Sequence[RawProviderRecord],
    identifiers: dict[UUID, str],
) -> dict[str, object]:
    """Normalize and append a raw submissions receipt and unique filing references."""

    if query.domain != ExternalDataDomain.SOURCE_DOCUMENTS:
        raise ValueError("Source-document ingestion received a different domain query")
    if any(
        record.provider_id != SEC_PROVIDER_ID
        or record.domain != ExternalDataDomain.SOURCE_DOCUMENTS
        for record in records
    ):
        raise ValueError("SEC submissions batch contains an unexpected provider record")
    if not records:
        return {"status": "NO_PROVIDER_RECORDS", "documents_imported": 0}
    digest = raw_batch_fingerprint(SEC_PROVIDER_ID, query, records)
    existing_batch = session.scalar(
        select(SourceDocumentBatch).where(
            SourceDocumentBatch.source_digest == digest,
            SourceDocumentBatch.normalizer_version == SEC_DOCUMENT_NORMALIZER_VERSION,
        )
    )
    if existing_batch is not None:
        return {
            "status": "ALREADY_IMPORTED",
            "batch_id": str(existing_batch.id),
            "documents_imported": 0,
            "reconciliation": existing_batch.reconciliation,
        }

    identifiers_by_cik = {cik: company_id for company_id, cik in identifiers.items()}
    normalized: list[CanonicalSourceDocument] = []
    counters: Counter[str] = Counter()
    issues: list[dict[str, object]] = []
    normalizer = SecSubmissionsNormalizer()
    for record in records:
        company_id, cik = _record_company(record, identifiers_by_cik)
        result = normalizer.normalize(record, company_id, cik)
        if result.disposition == NormalizationDisposition.REJECTED:
            issues.extend(issue.model_dump(mode="json") for issue in result.issues)
            counters["rejected_payloads"] += 1
            continue
        observation = result.observation
        assert observation is not None
        normalized.extend(observation.documents)
        counters["provider_filings_seen"] += len(observation.documents)
        counters["unsupported_forms"] += observation.unsupported_form_count
        counters["malformed_filing_rows"] += observation.malformed_record_count

    # SEC recent/history files can overlap. Preserve one canonical row per accession.
    by_external_id: dict[tuple[str, str], CanonicalSourceDocument] = {}
    conflicting_accessions: set[tuple[str, str]] = set()
    for document in normalized:
        key = (document.provider_id, document.external_identifier)
        previous = by_external_id.get(key)
        if key in conflicting_accessions:
            continue
        if previous is None:
            by_external_id[key] = document
        elif _document_fields(previous) != _document_fields(document):
            issues.append(
                {
                    "code": "DUPLICATE_ACCESSION_METADATA_CONFLICT",
                    "severity": "ERROR",
                    "source_record_id": document.external_identifier,
                    "message": (
                        "SEC returned conflicting metadata for one accession; "
                        "neither copy was selected."
                    ),
                }
            )
            by_external_id.pop(key, None)
            conflicting_accessions.add(key)
            counters["conflicting_accessions"] += 1
    normalized = list(by_external_id.values())
    normalized.sort(
        key=lambda item: (item.company_id, item.filed_at or date.min, item.is_amendment)
    )

    existing_documents = (
        {
            (item.provider_id, item.external_identifier): item
            for item in session.scalars(
                select(SourceDocument).where(
                    SourceDocument.provider_id == SEC_PROVIDER_ID,
                    SourceDocument.external_identifier.in_(
                        [document.external_identifier for document in normalized]
                    ),
                )
            )
        }
        if normalized
        else {}
    )
    pending: dict[tuple[str, str], SourceDocument] = {}
    inserted = 0
    reused = 0
    metadata_conflicts = 0
    linked = 0
    unlinked = 0
    batch_id = uuid4()
    documents_to_store: list[SourceDocument] = []
    for document in normalized:
        key = (document.provider_id, document.external_identifier)
        existing_doc = existing_documents.get(key)
        if existing_doc is not None:
            prior_fields = {
                field: getattr(existing_doc, field)
                for field in _document_fields(document)
                if field not in {"provider_id", "external_identifier"}
            }
            expected_fields = {
                field: value
                for field, value in _document_fields(document).items()
                if field not in {"provider_id", "external_identifier"}
            }
            if prior_fields == expected_fields:
                reused += 1
            else:
                metadata_conflicts += 1
                issues.append(
                    {
                        "code": "EXISTING_ACCESSION_METADATA_CHANGED",
                        "severity": "ERROR",
                        "source_record_id": document.external_identifier,
                        "message": (
                            "Existing filing metadata changed at source; the immutable "
                            "stored record was kept for review."
                        ),
                    }
                )
            continue
        original = _find_amended_original(session, document, pending)
        quality = document.data_quality
        quality_reason = document.quality_reason
        if document.is_amendment and original is None:
            unlinked += 1
            quality = SourceDocumentQuality.DATA_CHECK
            quality_reason = (
                "This amended SEC filing has no captured original with the same form and period."
            )
        elif document.is_amendment:
            linked += 1
        stored = SourceDocument(
            id=uuid4(),
            company_id=document.company_id,
            security_id=None,
            batch_id=batch_id,
            provider_id=document.provider_id,
            source_name=document.source_name,
            source_jurisdiction=document.source_jurisdiction,
            external_identifier=document.external_identifier,
            document_type=document.document_type.value,
            source_form=document.source_form,
            title=document.title,
            reporting_period=document.reporting_period,
            fiscal_year=document.fiscal_year,
            fiscal_period=document.fiscal_period,
            period_end=document.period_end,
            filed_at=document.filed_at,
            published_at=document.published_at,
            canonical_url=str(document.canonical_url),
            retrieved_at=document.retrieved_at,
            recorded_at=now(),
            is_amendment=document.is_amendment,
            amends_document_id=original.id if original else None,
            supersedes_document_id=None,
            data_quality=quality.value,
            quality_reason=quality_reason,
            actor=document.actor.value,
        )
        documents_to_store.append(stored)
        pending[key] = stored
        inserted += 1

    reconciliation: dict[str, object] = {
        **counters,
        "documents_imported": inserted,
        "documents_reused": reused,
        "existing_metadata_conflicts": metadata_conflicts,
        "amendments_linked": linked,
        "amendments_unlinked": unlinked,
        "issues": issues,
    }
    batch = SourceDocumentBatch(
        id=batch_id,
        provider_id=SEC_PROVIDER_ID,
        provider_schema_version=SEC_SUBMISSIONS_VERSION,
        normalizer_version=SEC_DOCUMENT_NORMALIZER_VERSION,
        domain=ExternalDataDomain.SOURCE_DOCUMENTS.value,
        source_digest=digest,
        query_scope={
            "company_ids": sorted(str(item) for item in identifiers),
            "history": "all SEC submissions history files returned by the SEC index",
        },
        observed_at=max(record.retrieved_at for record in records),
        provider_summary={
            "mapped_company_count": len(identifiers),
            "raw_record_count": len(records),
            "normalized_document_count": len(normalized),
            "source_name": SEC_SOURCE_NAME,
        },
        reconciliation=reconciliation,
    )
    raw_payloads = [
        ExternalRawPayload(
            id=uuid4(),
            batch_id=None,
            reported_fundamental_batch_id=None,
            consensus_estimate_batch_id=None,
            source_document_batch_id=batch_id,
            provider_id=record.provider_id,
            domain=record.domain.value,
            source_record_id=record.source_record_id or record.payload_sha256,
            source_url=str(record.source_url) if record.source_url else None,
            media_type=record.media_type,
            content_encoding="gzip",
            payload_sha256=record.payload_sha256,
            retrieved_at=record.retrieved_at,
            payload_bytes=gzip.compress(record.payload or b"", mtime=0),
        )
        for record in records
    ]
    session.add(batch)
    session.flush()
    session.add_all([*raw_payloads, *documents_to_store])
    return {
        "status": "IMPORTED",
        "batch_id": str(batch.id),
        "source_digest": digest,
        "provider_id": SEC_PROVIDER_ID,
        "documents_imported": inserted,
        "documents_reused": reused,
        "reconciliation": batch.reconciliation,
    }


async def sync_sec_source_documents(
    session: Session,
    settings: Settings,
    company_id: UUID | None = None,
) -> list[dict[str, object]]:
    if not settings.sec_user_agent:
        raise ValueError("Set SEC_USER_AGENT to an application name and contact email before sync")
    identifiers = _load_cik_mappings(session, company_id)
    if company_id is not None and company_id not in identifiers:
        return [{"company_id": str(company_id), "status": "UNMAPPED_SEC_IDENTITY"}]
    if not identifiers:
        return [{"status": "NO_VERIFIED_SEC_IDENTITIES", "documents_imported": 0}]
    query = ProviderQuery(
        domain=ExternalDataDomain.SOURCE_DOCUMENTS,
        subjects=tuple(
            CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=item)
            for item in sorted(identifiers, key=str)
        ),
        requested_at=datetime.now(UTC),
    )
    records = await SecSubmissionsProvider(identifiers, settings.sec_user_agent).fetch(query)
    return [ingest_sec_submissions(session, query, records, identifiers)]


def create_company_source_document(
    session: Session,
    company_id: UUID,
    value: SourceDocumentCreate,
) -> SourceDocument:
    """Append a curated company-source reference without claiming it was downloaded."""

    company = session.get(Company, company_id)
    if company is None:
        raise DomainError("Company not found", 404)
    if value.security_id is not None:
        security = session.get(Security, value.security_id)
        if security is None or security.company_id != company_id:
            raise DomainError("Source security must belong to the requested company")
    if value.provider_id != COMPANY_REFERENCE_PROVIDER_ID:
        raise DomainError("Curated references must use the company_source provider identity")
    for relation_id in (value.amends_document_id, value.supersedes_document_id):
        if relation_id is None:
            continue
        related = session.get(SourceDocument, relation_id)
        if related is None or related.company_id != company_id:
            raise DomainError("Related source documents must belong to the same company")
    if value.amends_document_id is not None and not value.is_amendment:
        raise DomainError("Only an amendment can reference the document it amends")
    existing = session.scalar(
        select(SourceDocument).where(
            SourceDocument.company_id == company_id,
            SourceDocument.provider_id == value.provider_id,
            SourceDocument.external_identifier == value.external_identifier,
        )
    )
    if existing is not None:
        expected = (
            company_id,
            value.security_id,
            value.source_name,
            value.source_jurisdiction,
            value.external_identifier,
            value.document_type.value,
            value.reporting_period,
            value.fiscal_year,
            value.fiscal_period,
            value.period_end,
            value.published_at,
            str(value.canonical_url),
            value.title,
            value.is_amendment,
            value.amends_document_id,
            value.supersedes_document_id,
            value.data_quality.value,
            value.quality_reason,
            value.actor.value,
        )
        actual = (
            existing.company_id,
            existing.security_id,
            existing.source_name,
            existing.source_jurisdiction,
            existing.external_identifier,
            existing.document_type,
            existing.reporting_period,
            existing.fiscal_year,
            existing.fiscal_period,
            existing.period_end,
            existing.published_at,
            existing.canonical_url,
            existing.title,
            existing.is_amendment,
            existing.amends_document_id,
            existing.supersedes_document_id,
            existing.data_quality,
            existing.quality_reason,
            existing.actor,
        )
        if expected != actual:
            raise DomainError(
                "This source identifier is already attached to different metadata", 409
            )
        return existing
    item = SourceDocument(
        id=uuid4(),
        company_id=company_id,
        security_id=value.security_id,
        batch_id=None,
        provider_id=value.provider_id,
        source_name=value.source_name,
        source_jurisdiction=value.source_jurisdiction,
        external_identifier=value.external_identifier,
        document_type=value.document_type.value,
        source_form=None,
        title=value.title,
        reporting_period=value.reporting_period,
        fiscal_year=value.fiscal_year,
        fiscal_period=value.fiscal_period,
        period_end=value.period_end,
        filed_at=None,
        published_at=value.published_at,
        canonical_url=str(value.canonical_url),
        retrieved_at=None,
        recorded_at=now(),
        is_amendment=value.is_amendment,
        amends_document_id=value.amends_document_id,
        supersedes_document_id=value.supersedes_document_id,
        data_quality=value.data_quality.value,
        quality_reason=value.quality_reason,
        actor=value.actor.value,
    )
    session.add(item)
    session.flush()
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync")
    sync.add_argument("--company-id", type=UUID)
    args = parser.parse_args()
    settings = Settings()
    engine = create_database_engine(settings)
    if engine is None:
        raise SystemExit("Set DATABASE_URL before synchronizing source documents")
    try:
        with Session(engine) as session:
            try:
                output = asyncio.run(sync_sec_source_documents(session, settings, args.company_id))
                session.commit()
            except ValueError as error:
                session.rollback()
                raise SystemExit(str(error)) from error
            print(json.dumps({"provider_id": SEC_PROVIDER_ID, "batches": output}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
