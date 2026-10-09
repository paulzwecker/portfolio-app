"""SEC filing normalization, metadata provenance and append-only source references."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Actor,
    Company,
    CompanyProviderIdentifier,
    ExternalRawPayload,
    SourceDocument,
    SourceDocumentBatch,
)
from portfolio_api.domain.queries import company_source_documents
from portfolio_api.domain.schemas import SourceDocumentCreate
from portfolio_api.domain.services import DomainError
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.source_documents import (
    COMPANY_REFERENCE_PROVIDER_ID,
    SEC_DOCUMENT_NORMALIZER_VERSION,
    SEC_PROVIDER_ID,
    SEC_SUBMISSIONS_BASE,
    SecSubmissionsNormalizer,
    SecSubmissionsProvider,
    create_company_source_document,
    ingest_sec_submissions,
)

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_COMPANY_ID = UUID("33333333-3333-4333-8333-333333333333")
CIK = "0000000001"
RETRIEVED_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)
ACCESSION = "0000000001-26-000001"


def submissions_record(
    payload: dict[str, object],
    *,
    source_record_id: str = f"CIK{CIK}",
    source_url: str = f"{SEC_SUBMISSIONS_BASE}/CIK{CIK}.json",
) -> RawProviderRecord:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return RawProviderRecord(
        domain=ExternalDataDomain.SOURCE_DOCUMENTS,
        provider_id=SEC_PROVIDER_ID,
        provider_schema_version="submissions-v1",
        source_record_id=source_record_id,
        source_url=source_url,
        media_type="application/json",
        retrieved_at=RETRIEVED_AT,
        payload=raw,
        payload_sha256=hashlib.sha256(raw).hexdigest(),
    )


def columnar(
    forms: list[str],
    accessions: list[str],
    filed: list[str],
    report: list[str],
    descriptions: list[str] | None = None,
) -> dict[str, object]:
    recent: dict[str, object] = {
        "form": forms,
        "accessionNumber": accessions,
        "filingDate": filed,
        "reportDate": report,
    }
    if descriptions is not None:
        recent["primaryDocDescription"] = descriptions
    return {"cik": 1, "name": "Example Issuer", "filings": {"recent": recent}}


def query(company_id: UUID = COMPANY_ID) -> ProviderQuery:
    return ProviderQuery(
        domain=ExternalDataDomain.SOURCE_DOCUMENTS,
        subjects=(CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=company_id),),
        requested_at=RETRIEVED_AT,
    )


def test_sec_normalizer_maps_forms_without_inventing_fiscal_period_or_dates() -> None:
    record = submissions_record(
        columnar(
            ["10-K", "10-K/A", "8-K", "S-8"],
            [
                ACCESSION,
                "0000000001-26-000002",
                "0000000001-26-000003",
                "0000000001-26-000004",
            ],
            ["2026-02-10", "2026-03-01", "2026-04-01", "2026-04-02"],
            ["2025-12-31", "2025-12-31", "", ""],
            ["Example annual report", "Amended annual report", "Current report", ""],
        )
    )

    result = SecSubmissionsNormalizer().normalize(record, COMPANY_ID, CIK)

    assert result.disposition == NormalizationDisposition.ACCEPTED
    assert SecSubmissionsNormalizer.version == SEC_DOCUMENT_NORMALIZER_VERSION
    assert result.observation is not None
    assert result.observation.unsupported_form_count == 1
    assert [item.document_type.value for item in result.observation.documents] == [
        "10-K",
        "10-K",
        "8-K",
    ]
    annual, amendment, current = result.observation.documents
    assert annual.period_end == date(2025, 12, 31)
    assert annual.published_at == annual.filed_at == date(2026, 2, 10)
    assert annual.fiscal_year is None and annual.fiscal_period is None
    assert str(annual.canonical_url).endswith(f"/{ACCESSION}-index.html")
    assert amendment.is_amendment
    assert amendment.source_form == "10-K/A"
    assert current.period_end is None
    assert current.data_quality.value == "DATA_CHECK"
    assert current.quality_reason is not None


def test_sec_normalizer_rejects_cik_mismatch_and_malformed_accessions() -> None:
    mismatch = submissions_record({"cik": 2, "filings": {"recent": {"form": []}}})
    result = SecSubmissionsNormalizer().normalize(mismatch, COMPANY_ID, CIK)
    assert result.disposition == NormalizationDisposition.REJECTED
    assert result.issues[0].code == "SEC_CIK_MISMATCH"

    malformed = submissions_record(columnar(["10-K"], ["bad"], ["2026-01-01"], [""]))
    result = SecSubmissionsNormalizer().normalize(malformed, COMPANY_ID, CIK)
    assert result.disposition == NormalizationDisposition.ACCEPTED
    assert result.observation is not None
    assert result.observation.documents == ()
    assert result.observation.malformed_record_count == 1


def test_sec_provider_fetches_index_and_linked_full_history_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = {
        "cik": 1,
        "filings": {
            "recent": {"form": [], "accessionNumber": [], "filingDate": [], "reportDate": []},
            "files": [{"name": f"CIK{CIK}-submissions-001.json"}],
        },
    }
    history = columnar(
        ["20-F", "6-K"],
        ["0000000001-20-000001", "0000000001-20-000002"],
        ["2020-01-01", "2020-02-01"],
        ["2019-12-31", ""],
    )
    responses = {
        f"{SEC_SUBMISSIONS_BASE}/CIK{CIK}.json": json.dumps(main).encode(),
        f"{SEC_SUBMISSIONS_BASE}/CIK{CIK}-submissions-001.json": json.dumps(history).encode(),
    }
    requested: list[str] = []
    delays: list[float] = []

    def download(url: str, user_agent: str) -> bytes:
        requested.append(url)
        assert user_agent == "Portfolio Research test@example.com"
        return responses[url]

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    async def to_thread(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr("portfolio_api.source_documents._download_sec_json", download)
    monkeypatch.setattr("portfolio_api.source_documents.asyncio.sleep", sleep)
    monkeypatch.setattr("portfolio_api.source_documents.asyncio.to_thread", to_thread)
    provider = SecSubmissionsProvider({COMPANY_ID: CIK}, "Portfolio Research test@example.com")

    records = asyncio.run(provider.fetch(query()))

    assert len(records) == 2
    assert requested == list(responses)
    assert delays == [0.15]
    assert records[1].source_record_id == f"CIK{CIK}:HISTORY:CIK{CIK}-submissions-001.json"
    normalized = SecSubmissionsNormalizer().normalize(records[1], COMPANY_ID, CIK)
    assert normalized.observation is not None
    assert [item.document_type.value for item in normalized.observation.documents] == [
        "20-F",
        "6-K",
    ]

    requested.clear()
    already_known = SecSubmissionsProvider(
        {COMPANY_ID: CIK},
        "Portfolio Research test@example.com",
        known_source_record_ids={f"CIK{CIK}:HISTORY:CIK{CIK}-submissions-001.json"},
    )
    incremental = asyncio.run(already_known.fetch(query()))
    assert len(incremental) == 1
    assert incremental[0].source_record_id == f"CIK{CIK}"
    assert requested == [f"{SEC_SUBMISSIONS_BASE}/CIK{CIK}.json"]
    assert already_known.skipped_history_files == 1


def test_sec_import_is_idempotent_links_amendments_and_respects_as_of(
    postgres_engine: Engine,
) -> None:
    amendment_accession = "0000000001-26-000002"
    record = submissions_record(
        columnar(
            ["10-K/A", "10-K"],
            [amendment_accession, ACCESSION],
            ["2026-03-01", "2026-02-10"],
            ["2025-12-31", "2025-12-31"],
        )
    )
    with Session(postgres_engine) as session, session.begin():
        session.add(
            Company(
                id=COMPANY_ID,
                name="Example Issuer",
                reporting_currency="USD",
                is_demo=False,
            )
        )
        session.add(
            CompanyProviderIdentifier(
                id=UUID("22222222-2222-4222-8222-222222222222"),
                company_id=COMPANY_ID,
                provider_id=SEC_PROVIDER_ID,
                identifier_type="SEC_CIK",
                identifier_value=CIK,
                provider_company_name="Example Issuer",
                evidence_source="https://www.sec.gov/edgar/browse/?CIK=1",
                effective_at=RETRIEVED_AT,
                recorded_at=RETRIEVED_AT,
                actor=Actor.IMPORT.value,
            )
        )
        session.flush()
        first = ingest_sec_submissions(session, query(), [record], {COMPANY_ID: CIK})
        assert first["status"] == "IMPORTED"
        session.flush()
        repeated = ingest_sec_submissions(session, query(), [record], {COMPANY_ID: CIK})
        assert repeated["status"] == "ALREADY_IMPORTED"

        docs = list(
            session.scalars(select(SourceDocument).where(SourceDocument.company_id == COMPANY_ID))
        )
        assert len(docs) == 2
        original = next(item for item in docs if not item.is_amendment)
        amendment = next(item for item in docs if item.is_amendment)
        assert amendment.amends_document_id == original.id
        assert amendment.retrieved_at == RETRIEVED_AT
        raw = session.scalar(select(ExternalRawPayload))
        assert raw is not None
        assert raw.source_document_batch_id is not None
        assert gzip.decompress(raw.payload_bytes) == record.payload
        assert session.scalar(select(func.count(SourceDocumentBatch.id))) == 1
        assert session.scalar(select(func.count(SourceDocument.id))) == 2

        at_filing = company_source_documents(session, COMPANY_ID, as_of=date(2026, 2, 20))
        assert at_filing.source_count == 1
        assert at_filing.documents[0].external_identifier == ACCESSION
        before_import = company_source_documents(
            session, COMPANY_ID, known_at=datetime(2020, 1, 1, tzinfo=UTC)
        )
        assert before_import.documents == []

    with Session(postgres_engine) as session, session.begin():
        document = session.scalar(
            select(SourceDocument).where(SourceDocument.company_id == COMPANY_ID)
        )
        assert document is not None
        document.title = "Illicit in-place edit"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()


def test_company_source_reference_is_link_only_and_idempotent(postgres_engine: Engine) -> None:
    value = SourceDocumentCreate(
        provider_id=COMPANY_REFERENCE_PROVIDER_ID,
        source_name="Example investor relations",
        source_jurisdiction="GB",
        external_identifier="annual-report-2025",
        document_type="ANNUAL_REPORT",
        title="Annual report 2025",
        reporting_period="FY 2025",
        fiscal_year=2025,
        fiscal_period="FY",
        period_end=date(2025, 12, 31),
        published_at=date(2026, 2, 20),
        canonical_url="https://ir.example.test/reports/2025.pdf",
        actor=Actor.LOCAL_USER,
    )
    with Session(postgres_engine) as session, session.begin():
        session.add(
            Company(
                id=COMPANY_ID,
                name="Example Issuer",
                reporting_currency="USD",
                is_demo=False,
            )
        )
        session.flush()
        first = create_company_source_document(session, COMPANY_ID, value)
        repeated = create_company_source_document(session, COMPANY_ID, value)
        assert first.id == repeated.id
        with pytest.raises(DomainError, match="already attached to different metadata"):
            create_company_source_document(
                session, COMPANY_ID, value.model_copy(update={"title": "Different title"})
            )
        assert repeated.retrieved_at is None
        assert repeated.batch_id is None
        assert repeated.canonical_url == "https://ir.example.test/reports/2025.pdf"
        session.add(
            Company(
                id=SECOND_COMPANY_ID,
                name="Another Issuer",
                reporting_currency="GBP",
                is_demo=False,
            )
        )
        session.flush()
        other_company_source = create_company_source_document(
            session,
            SECOND_COMPANY_ID,
            value.model_copy(
                update={
                    "canonical_url": "https://ir.other.example.test/reports/2025.pdf",
                }
            ),
        )
        assert other_company_source.id != first.id


def test_manual_source_reference_requires_https_and_explicit_missing_dates() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        SourceDocumentCreate(
            source_name="Example source",
            external_identifier="release-1",
            document_type="EARNINGS_RELEASE",
            title="Quarterly results",
            published_at=date(2026, 1, 1),
            canonical_url="http://ir.example.test/results",
        )
    with pytest.raises(ValueError, match="DATA_CHECK"):
        SourceDocumentCreate(
            source_name="Example source",
            external_identifier="release-2",
            document_type="EARNINGS_RELEASE",
            title="Undated results",
            canonical_url="https://ir.example.test/results",
        )
