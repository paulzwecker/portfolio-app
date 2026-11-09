"""SEC filing normalization, metadata provenance and append-only source references."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts

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
from portfolio_api.fundamentals_bootstrap import _known_history_records
from portfolio_api.source_documents import (
    COMPANY_REFERENCE_PROVIDER_ID,
    SEC_DOCUMENT_NORMALIZER_VERSION,
    SEC_PROVIDER_ID,
    SEC_SUBMISSIONS_BASE,
    SecSubmissionsNormalizer,
    SecSubmissionsProvider,
    _NoSecRedirects,
    create_company_source_document,
    ingest_sec_submissions,
    known_processed_sec_history,
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


@pytest.mark.integration
def test_history_skip_requires_exact_accepted_page_receipt_and_raw_metadata(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history_name = f"CIK{CIK}-submissions-001.json"
    history_id = f"CIK{CIK}:HISTORY:{history_name}"
    url = f"{SEC_SUBMISSIONS_BASE}/{history_name}"
    bad = submissions_record({"form": []}, source_record_id=history_id, source_url=url)
    good = submissions_record(
        columnar(["10-K"], [ACCESSION], ["2026-02-10"], ["2025-12-31"]),
        source_record_id=history_id,
        source_url=url,
    )
    with Session(postgres_engine) as session, session.begin():
        session.add(Company(id=COMPANY_ID, name="Receipt fixture"))
        session.flush()
        failed = ingest_sec_submissions(session, query(), [bad], {COMPANY_ID: CIK})
        assert cast(dict[str, Any], failed["reconciliation"])["rejected_payloads"] == 1
        session.flush()
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()
        assert _known_history_records(session, COMPANY_ID, CIK) == set()
        failed_batch_id = UUID(str(failed["batch_id"]))
        failed_batch = session.get(SourceDocumentBatch, failed_batch_id)
        assert failed_batch is not None
        failed_reconciliation = dict(failed_batch.reconciliation)
        forged = {
            "company_id": str(COMPANY_ID),
            "cik": CIK,
            "source_record_id": history_id,
            "payload_sha256": bad.payload_sha256,
        }
        session.execute(
            update(SourceDocumentBatch)
            .where(SourceDocumentBatch.id == failed_batch_id)
            .values(reconciliation={**failed_reconciliation, "processed_history_pages": [forged]})
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()
        session.execute(
            update(SourceDocumentBatch)
            .where(SourceDocumentBatch.id == failed_batch_id)
            .values(reconciliation=failed_reconciliation)
        )
        success = ingest_sec_submissions(session, query(), [good], {COMPANY_ID: CIK})
        session.flush()
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == {history_id}
        with monkeypatch.context() as bounded:
            bounded.setattr("portfolio_api.source_documents.MAX_HISTORY_RECEIPT_VERIFY_PAGES", 0)
            with pytest.raises(ValueError, match="bounded budget"):
                known_processed_sec_history(session, {COMPANY_ID: CIK})
        assert _known_history_records(session, COMPANY_ID, CIK) == {history_id}
        assert known_processed_sec_history(session, {COMPANY_ID: "0000000002"}) == set()
        batch_id = UUID(str(success["batch_id"]))
        raw = session.scalar(
            select(ExternalRawPayload).where(
                ExternalRawPayload.source_document_batch_id == batch_id
            )
        )
        assert raw is not None
        # Fixture-only SQL corruption models metadata mismatch without mutating ORM history.
        session.execute(
            update(ExternalRawPayload)
            .where(ExternalRawPayload.id == raw.id)
            .values(payload_sha256="0" * 64)
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()
        session.execute(
            update(ExternalRawPayload)
            .where(ExternalRawPayload.id == raw.id)
            .values(payload_sha256=good.payload_sha256)
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == {history_id}
        original_bytes = raw.payload_bytes
        session.execute(
            update(ExternalRawPayload)
            .where(ExternalRawPayload.id == raw.id)
            .values(payload_bytes=gzip.compress(b"tampered"))
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()
        session.execute(
            update(ExternalRawPayload)
            .where(ExternalRawPayload.id == raw.id)
            .values(payload_bytes=original_bytes)
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == {history_id}
        batch = session.get(SourceDocumentBatch, batch_id)
        assert batch is not None
        reconciliation = dict(batch.reconciliation)
        pages = cast(list[dict[str, object]], reconciliation["processed_history_pages"])
        session.execute(
            update(SourceDocumentBatch)
            .where(SourceDocumentBatch.id == batch_id)
            .values(reconciliation={**reconciliation, "processed_history_pages": pages * 2})
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()
        session.execute(
            update(SourceDocumentBatch)
            .where(SourceDocumentBatch.id == batch_id)
            .values(reconciliation=reconciliation)
        )
        for issue in (
            {"code": "EXISTING_ACCESSION_METADATA_CHANGED", "source_record_id": ACCESSION},
            {"code": ["malformed"], "source_record_id": ACCESSION},
        ):
            session.execute(
                update(SourceDocumentBatch)
                .where(SourceDocumentBatch.id == batch_id)
                .values(reconciliation={**reconciliation, "issues": [issue]})
            )
            assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()
        session.execute(
            update(SourceDocumentBatch)
            .where(SourceDocumentBatch.id == batch_id)
            .values(reconciliation=reconciliation)
        )
        session.execute(
            update(SourceDocumentBatch)
            .where(SourceDocumentBatch.id == batch_id)
            .values(normalizer_version="sec-edgar-filings-v1")
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()
        replay = ingest_sec_submissions(session, query(), [good], {COMPANY_ID: CIK})
        session.flush()
        assert replay["status"] == "IMPORTED" and replay["documents_imported"] == 0
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == {history_id}
        assert (
            ingest_sec_submissions(session, query(), [good], {COMPANY_ID: CIK})["status"]
            == "ALREADY_IMPORTED"
        )
        assert session.scalar(select(func.count(SourceDocument.id))) == 1


@pytest.mark.integration
def test_valid_empty_history_page_is_processed_but_malformed_rows_are_not(
    postgres_engine: Engine,
) -> None:
    name = f"CIK{CIK}-submissions-001.json"
    source_id = f"CIK{CIK}:HISTORY:{name}"
    url = f"{SEC_SUBMISSIONS_BASE}/{name}"
    empty = submissions_record(columnar([], [], [], []), source_record_id=source_id, source_url=url)
    malformed = submissions_record(
        columnar(["10-K"], ["bad"], ["2026-02-10"], ["2025-12-31"]),
        source_record_id=source_id,
        source_url=url,
    ).model_copy(update={"retrieved_at": RETRIEVED_AT + timedelta(days=1)})
    with Session(postgres_engine) as session, session.begin():
        session.add(Company(id=COMPANY_ID, name="Empty page fixture"))
        session.flush()
        ingest_sec_submissions(session, query(), [empty], {COMPANY_ID: CIK})
        session.flush()
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == {source_id}
        ingest_sec_submissions(session, query(), [malformed], {COMPANY_ID: CIK})
        session.flush()
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()


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


def test_cikless_history_requires_exact_valid_prior_issuer_index() -> None:
    name = f"CIK{CIK}-submissions-001.json"
    history = submissions_record(
        {
            "form": ["10-K"],
            "accessionNumber": [ACCESSION],
            "filingDate": ["2026-02-10"],
            "reportDate": ["2025-12-31"],
        },
        source_record_id=f"CIK{CIK}:HISTORY:{name}",
        source_url=f"{SEC_SUBMISSIONS_BASE}/{name}",
    )
    main = columnar([], [], [], [])
    cast(dict[str, Any], main["filings"])["files"] = [{"name": name}]
    index = submissions_record(main)
    normalizer = SecSubmissionsNormalizer()
    assert (
        normalizer.normalize(history, COMPANY_ID, CIK, index).disposition
        == NormalizationDisposition.ACCEPTED
    )
    assert (
        normalizer.normalize(history, COMPANY_ID, CIK).disposition
        == NormalizationDisposition.REJECTED
    )
    for invalid in (
        index.model_copy(update={"source_record_id": "CIK0000000002"}),
        index.model_copy(update={"source_url": f"{SEC_SUBMISSIONS_BASE}/CIK0000000002.json"}),
        index.model_copy(update={"retrieved_at": RETRIEVED_AT + timedelta(seconds=1)}),
        submissions_record({**main, "cik": 2}),
        submissions_record(
            {**main, "filings": {**cast(dict[str, Any], main["filings"]), "files": []}}
        ),
        submissions_record(
            {
                **main,
                "filings": {
                    **cast(dict[str, Any], main["filings"]),
                    "files": [{"name": name}, {"name": name}],
                },
            }
        ),
    ):
        assert (
            normalizer.normalize(history, COMPANY_ID, CIK, invalid).disposition
            == NormalizationDisposition.REJECTED
        )
    explicit_wrong_cik = submissions_record(
        {"cik": 2, "form": [], "accessionNumber": [], "filingDate": [], "reportDate": []},
        source_record_id=history.source_record_id or "",
        source_url=str(history.source_url),
    )
    assert (
        normalizer.normalize(explicit_wrong_cik, COMPANY_ID, CIK, index).disposition
        == NormalizationDisposition.REJECTED
    )
    unaligned_index = submissions_record(
        {
            **main,
            "filings": {
                **cast(dict[str, Any], main["filings"]),
                "recent": {
                    "form": [],
                    "accessionNumber": [ACCESSION],
                    "filingDate": [],
                    "reportDate": [],
                },
            },
        }
    )
    missing_columns_index = submissions_record(
        {**main, "filings": {"recent": {"form": []}, "files": [{"name": name}]}}
    )
    unaligned_page = submissions_record(
        {"form": [], "accessionNumber": [ACCESSION], "filingDate": [], "reportDate": []},
        source_record_id=history.source_record_id or "",
        source_url=str(history.source_url),
    )
    assert (
        normalizer.normalize(history, COMPANY_ID, CIK, unaligned_index).disposition
        == NormalizationDisposition.REJECTED
    )
    assert (
        normalizer.normalize(history, COMPANY_ID, CIK, missing_columns_index).disposition
        == NormalizationDisposition.REJECTED
    )
    assert (
        normalizer.normalize(unaligned_page, COMPANY_ID, CIK, index).disposition
        == NormalizationDisposition.REJECTED
    )


def test_sec_transport_disallows_redirects() -> None:
    assert (
        _NoSecRedirects().redirect_request(None, None, 302, "", {}, "https://example.com") is None
    )


@pytest.mark.integration
def test_cikless_history_receipt_revalidates_retained_index(
    postgres_engine: Engine,
) -> None:
    name = f"CIK{CIK}-submissions-001.json"
    source_id = f"CIK{CIK}:HISTORY:{name}"
    history = submissions_record(
        {
            "form": ["10-K"],
            "accessionNumber": [ACCESSION],
            "filingDate": ["2026-02-10"],
            "reportDate": ["2025-12-31"],
        },
        source_record_id=source_id,
        source_url=f"{SEC_SUBMISSIONS_BASE}/{name}",
    )
    main = columnar([], [], [], [])
    cast(dict[str, Any], main["filings"])["files"] = [{"name": name}]
    index = submissions_record(main)
    with Session(postgres_engine) as session, session.begin():
        session.add(Company(id=COMPANY_ID, name="Indexed history fixture"))
        session.flush()
        result = ingest_sec_submissions(session, query(), [index, history], {COMPANY_ID: CIK})
        session.flush()
        assert result["documents_imported"] == 1
        receipt = cast(dict[str, Any], result["reconciliation"])["processed_history_pages"][0]
        assert receipt["index_payload_sha256"] == index.payload_sha256
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == {source_id}
        batch_id = UUID(str(result["batch_id"]))
        session.execute(
            update(ExternalRawPayload)
            .where(
                ExternalRawPayload.source_document_batch_id == batch_id,
                ExternalRawPayload.source_record_id == index.source_record_id,
            )
            .values(payload_bytes=gzip.compress(b"{}"))
        )
        assert known_processed_sec_history(session, {COMPANY_ID: CIK}) == set()


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
    history_wrapped = columnar(
        ["20-F", "6-K"],
        ["0000000001-20-000001", "0000000001-20-000002"],
        ["2020-01-01", "2020-02-01"],
        ["2019-12-31", ""],
    )
    history = cast(dict[str, Any], history_wrapped["filings"])["recent"]
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
    assert provider.request_count == 2
    assert requested == list(responses)
    assert delays == [0.15]
    assert records[1].source_record_id == f"CIK{CIK}:HISTORY:CIK{CIK}-submissions-001.json"
    normalized = SecSubmissionsNormalizer().normalize(records[1], COMPANY_ID, CIK, records[0])
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
    assert already_known.request_count == 1
    assert incremental[0].source_record_id == f"CIK{CIK}"
    assert requested == [f"{SEC_SUBMISSIONS_BASE}/CIK{CIK}.json"]
    assert already_known.skipped_history_files == 1


def test_provider_does_not_follow_history_links_from_an_invalid_issuer_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong = columnar([], [], [], [])
    wrong["cik"] = 2
    cast(dict[str, Any], wrong["filings"])["files"] = [{"name": f"CIK{CIK}-submissions-001.json"}]
    calls: list[str] = []

    def download(url: str, _agent: str) -> bytes:
        calls.append(url)
        return json.dumps(wrong).encode()

    monkeypatch.setattr("portfolio_api.source_documents._download_sec_json", download)
    provider = SecSubmissionsProvider({COMPANY_ID: CIK}, "Portfolio Research test@example.com")
    records = asyncio.run(provider.fetch(query()))
    assert len(records) == len(calls) == provider.request_count == 1


def test_sec_provider_bounds_new_history_files_for_resumable_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history_names = [f"CIK{CIK}-submissions-{index:03d}.json" for index in range(1, 4)]
    main = {
        "cik": 1,
        "filings": {
            "recent": {"form": [], "accessionNumber": [], "filingDate": [], "reportDate": []},
            "files": [{"name": name} for name in history_names],
        },
    }
    requested: list[str] = []

    def download(url: str, _user_agent: str) -> bytes:
        requested.append(url)
        return json.dumps(main if url.endswith("CIK0000000001.json") else {}).encode()

    async def sleep(_seconds: float) -> None:
        return None

    async def to_thread(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr("portfolio_api.source_documents._download_sec_json", download)
    monkeypatch.setattr("portfolio_api.source_documents.asyncio.sleep", sleep)
    monkeypatch.setattr("portfolio_api.source_documents.asyncio.to_thread", to_thread)

    first = SecSubmissionsProvider(
        {COMPANY_ID: CIK},
        "Portfolio Research test@example.com",
        max_new_history_files=1,
    )
    first_records = asyncio.run(first.fetch(query()))
    assert len(first_records) == 2
    assert first.deferred_history_files == 2
    assert first.deferred_history_file_ids == [
        f"CIK{CIK}:HISTORY:{history_names[1]}",
        f"CIK{CIK}:HISTORY:{history_names[2]}",
    ]

    requested.clear()
    second = SecSubmissionsProvider(
        {COMPANY_ID: CIK},
        "Portfolio Research test@example.com",
        known_source_record_ids={first_records[1].source_record_id or ""},
        max_new_history_files=1,
    )
    second_records = asyncio.run(second.fetch(query()))
    assert len(second_records) == 2
    assert second_records[1].source_record_id == f"CIK{CIK}:HISTORY:{history_names[1]}"
    assert second.skipped_history_files == 1
    assert second.deferred_history_files == 1
    assert len(requested) == 2


@pytest.mark.integration
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
        assert at_filing.sec_identity_status == "UNMAPPED"
        assert at_filing.documents[0].sec_issuer_attribution == "UNVERIFIED"
        before_import = company_source_documents(
            session, COMPANY_ID, known_at=datetime(2020, 1, 1, tzinfo=UTC)
        )
        assert before_import.documents == []
        assert before_import.sec_identity_status == "UNMAPPED"

    with Session(postgres_engine) as session, session.begin():
        document = session.scalar(
            select(SourceDocument).where(SourceDocument.company_id == COMPANY_ID)
        )
        assert document is not None
        document.title = "Illicit in-place edit"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()


@pytest.mark.integration
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
        readback = company_source_documents(session, COMPANY_ID)
        assert readback.documents[0].sec_issuer_attribution == "NOT_SEC"
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


@pytest.mark.integration
def test_filing_mapping_status_respects_effective_and_knowledge_time(
    postgres_engine: Engine,
) -> None:
    before = datetime(2024, 6, 1, tzinfo=UTC)
    after = datetime(2025, 6, 1, tzinfo=UTC)
    future = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        session.add(Company(id=COMPANY_ID, name="Temporal filing fixture"))
        session.flush()
        session.add(
            CompanyProviderIdentifier(
                company_id=COMPANY_ID,
                provider_id=SEC_PROVIDER_ID,
                identifier_type="SEC_CIK",
                identifier_value=CIK,
                provider_company_name="Fixture issuer",
                evidence_source="https://www.sec.gov/edgar/browse/?CIK=1",
                effective_at=datetime(2020, 1, 1, tzinfo=UTC),
                recorded_at=after,
                actor=Actor.IMPORT.value,
            )
        )
        session.add(
            SourceDocument(
                company_id=COMPANY_ID,
                provider_id=SEC_PROVIDER_ID,
                source_name="SEC",
                external_identifier=ACCESSION,
                document_type="10-K",
                title="Fixture filing",
                published_at=date(2023, 12, 1),
                filed_at=date(2023, 12, 1),
                canonical_url="https://www.sec.gov/fixture",
                recorded_at=before,
                data_quality="PASS",
                actor=Actor.IMPORT.value,
            )
        )
        session.flush()
        historical = company_source_documents(session, COMPANY_ID, known_at=before)
        assert historical.sec_identity_status == "UNMAPPED"
        assert historical.source_count == 1
        assert historical.documents[0].sec_issuer_attribution == "UNVERIFIED"
        assert (
            company_source_documents(
                session, COMPANY_ID, as_of=date(2024, 12, 31)
            ).sec_identity_status
            == "MAPPED"
        )
        assert (
            company_source_documents(session, COMPANY_ID, known_at=after).sec_identity_status
            == "MAPPED"
        )
        session.add(
            CompanyProviderIdentifier(
                company_id=COMPANY_ID,
                provider_id=SEC_PROVIDER_ID,
                identifier_type="SEC_CIK",
                identifier_value="0000000002",
                provider_company_name="Different fixture",
                evidence_source="https://www.sec.gov/edgar/browse/?CIK=2",
                effective_at=future,
                recorded_at=future,
                actor=Actor.IMPORT.value,
            )
        )
        session.flush()
        assert (
            company_source_documents(session, COMPANY_ID, known_at=after).sec_identity_status
            == "MAPPED"
        )
        assert (
            company_source_documents(
                session, COMPANY_ID, as_of=date(2024, 12, 31)
            ).sec_identity_status
            == "MAPPED"
        )
        assert company_source_documents(session, COMPANY_ID).sec_identity_status == "AMBIGUOUS"
        assert not session.dirty
    before_counts = table_counts(postgres_engine)
    with postgres_engine.connect() as connection:
        from sqlalchemy import text

        schema = str(connection.scalar(text("SELECT current_schema()")))
    settings = fixture_settings()
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            response = client.get(
                f"/v1/companies/{COMPANY_ID}/source-documents",
                params={"known_at": "2024-06-01T00:00:00Z"},
            )
            assert response.status_code == 200
            assert response.json()["sec_identity_status"] == "UNMAPPED"
            assert response.json()["documents"][0]["sec_issuer_attribution"] == "UNVERIFIED"
    finally:
        reader.dispose()
    assert table_counts(postgres_engine) == before_counts


@pytest.mark.integration
def test_filing_mapping_discloses_invalid_recorded_evidence(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        session.add(Company(id=COMPANY_ID, name="Invalid identity fixture"))
        session.flush()
        session.add(
            CompanyProviderIdentifier(
                company_id=COMPANY_ID,
                provider_id=SEC_PROVIDER_ID,
                identifier_type="SEC_CIK",
                identifier_value=CIK,
                provider_company_name="Fixture issuer",
                evidence_source="https://example.test/?CIK=1",
                effective_at=datetime(2020, 1, 1, tzinfo=UTC),
                recorded_at=datetime(2020, 1, 1, tzinfo=UTC),
                actor=Actor.IMPORT.value,
            )
        )
        session.flush()
        readback = company_source_documents(session, COMPANY_ID)
        assert readback.sec_identity_status == "MAPPED"
        assert readback.sec_identity_issue is not None
        assert not session.dirty


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
