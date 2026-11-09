"""Issuer filing receipts retain exact scope, conflicts and unavailable responses."""

import copy
import json
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_sec_incremental_refresh import FILINGS, _refresh
from test_source_documents import (
    ACCESSION,
    CIK,
    COMPANY_ID,
    RETRIEVED_AT,
    SECOND_COMPANY_ID,
    columnar,
    submissions_record,
)

from portfolio_api.company_sec_coverage import _issuer_result, company_sec_coverage
from portfolio_api.domain.models import (
    Company,
    ExternalIngestionRun,
    ExternalRawPayload,
    SourceDocument,
    SourceDocumentBatch,
)
from portfolio_api.domain.queries import company_source_documents
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.reported_fundamentals import record_cik_mapping
from portfolio_api.source_documents import (
    ISSUER_FILING_COUNT_FIELDS,
    SEC_ISSUER_RECONCILIATION_VERSION,
    SEC_SUBMISSIONS_BASE,
    SecIssuerFilingReconciliation,
    ingest_sec_submissions,
)

IDENTIFIERS = {COMPANY_ID: CIK, SECOND_COMPANY_ID: "0000000002"}


def _companies(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        for company_id, cik in IDENTIFIERS.items():
            session.add(
                Company(
                    id=company_id, name=f"Synthetic issuer {int(cik)}", reporting_currency="USD"
                )
            )
            session.flush()
            record_cik_mapping(
                session,
                company_id,
                cik,
                f"Synthetic issuer {int(cik)}",
                f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}",
            )


def _query(identifiers: dict[UUID, str]) -> ProviderQuery:
    return ProviderQuery(
        domain=ExternalDataDomain.SOURCE_DOCUMENTS,
        subjects=tuple(
            CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=item) for item in identifiers
        ),
        requested_at=RETRIEVED_AT,
    )


def _record(
    company_id: UUID, payload: dict[str, object] | None = None, *, history: bool = False
) -> RawProviderRecord:
    cik = IDENTIFIERS[company_id]
    if payload is None:
        payload = columnar(["10-K"], [f"{cik}-26-000001"], ["2026-02-10"], ["2025-12-31"])
    payload = {**payload, "cik": int(cik)}
    suffix = f":HISTORY:CIK{cik}-submissions-001.json" if history else ""
    return submissions_record(
        payload,
        source_record_id=f"CIK{cik}{suffix}",
        source_url=f"{SEC_SUBMISSIONS_BASE}/CIK{cik}.json",
    )


def _ingest(
    engine: Engine, records: list[RawProviderRecord], identifiers: dict[UUID, str] | None = None
) -> dict[str, Any]:
    selected = identifiers if identifiers is not None else IDENTIFIERS
    with Session(engine) as session, session.begin():
        return cast(
            dict[str, Any], ingest_sec_submissions(session, _query(selected), records, selected)
        )


def _receipts(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    reconciliation = result["reconciliation"]
    assert reconciliation["issuer_results_version"] == SEC_ISSUER_RECONCILIATION_VERSION
    return {item["company_id"]: item for item in reconciliation["issuer_results"]}


def _outcome(result: dict[str, Any], company_id: UUID) -> tuple[str, int | None]:
    run = ExternalIngestionRun(
        domain="SOURCE_DOCUMENTS", status="PARTIAL", report={"provider_result": result}
    )
    return _issuer_result(run, company_id, {str(item) for item in IDENTIFIERS})


@pytest.mark.integration
def test_multi_issuer_batch_does_not_imply_per_filing_identity(postgres_engine: Engine) -> None:
    _companies(postgres_engine)
    _ingest(postgres_engine, [_record(COMPANY_ID), _record(SECOND_COMPANY_ID)])
    with Session(postgres_engine) as session:
        for company_id in IDENTIFIERS:
            result = company_source_documents(session, company_id)
            assert result.sec_identity_status == "MAPPED"
            assert len(result.documents) == 1
            assert result.documents[0].sec_issuer_attribution == "UNVERIFIED"


@pytest.mark.integration
@pytest.mark.parametrize("problem", ["rejected", "unsupported", "malformed", "orphan"])
def test_bad_issuer_does_not_contaminate_another_issuer_result(
    postgres_engine: Engine, problem: str
) -> None:
    _companies(postgres_engine)
    payload = columnar(["10-K"], ["0000000002-26-000001"], ["2026-03-01"], ["2025-12-31"])
    if problem == "rejected":
        payload = {"filings": {}}
    elif problem == "unsupported":
        payload = columnar(["S-8"], ["0000000002-26-000001"], ["2026-03-01"], [""])
    elif problem == "malformed":
        payload = columnar(["10-K"], ["invalid"], ["2026-03-01"], ["2025-12-31"])
    else:
        payload = columnar(["10-K/A"], ["0000000002-26-000001"], ["2026-03-01"], ["2025-12-31"])
    result = _ingest(postgres_engine, [_record(COMPANY_ID), _record(SECOND_COMPANY_ID, payload)])
    receipts = _receipts(result)
    assert _outcome(result, COMPANY_ID) == ("REPORTED", 1)
    assert _outcome(result, SECOND_COMPANY_ID) == ("DATA_CHECK", 1 if problem == "orphan" else 0)
    assert receipts[str(COMPANY_ID)]["response_record_count"] == 1
    key = {
        "rejected": "rejected_payloads",
        "unsupported": "unsupported_forms",
        "malformed": "malformed_filing_rows",
        "orphan": "amendments_unlinked",
    }[problem]
    assert receipts[str(SECOND_COMPANY_ID)][key] == 1 and receipts[str(COMPANY_ID)][key] == 0


@pytest.mark.integration
@pytest.mark.parametrize("has_response", [True, False])
def test_clean_empty_and_missing_response_are_distinct_despite_prior_retained_data(
    postgres_engine: Engine, has_response: bool
) -> None:
    _companies(postgres_engine)
    _ingest(
        postgres_engine,
        [_record(SECOND_COMPANY_ID)],
        {SECOND_COMPANY_ID: IDENTIFIERS[SECOND_COMPANY_ID]},
    )
    records = [_record(COMPANY_ID)]
    if has_response:
        records.append(_record(SECOND_COMPANY_ID, columnar([], [], [], [])))
    result = _ingest(postgres_engine, records)
    assert _outcome(result, COMPANY_ID) == ("REPORTED", 1)
    assert _outcome(result, SECOND_COMPANY_ID) == (
        ("UNAVAILABLE", 0) if has_response else ("NOT_REPORTED", None)
    )
    issues = result["reconciliation"]["issues"]
    code = "NO_SUPPORTED_ISSUER_FILINGS" if has_response else "MISSING_ISSUER_RESPONSE"
    assert any(
        item["code"] == code and item["company_id"] == str(SECOND_COMPANY_ID) for item in issues
    )
    with Session(postgres_engine) as session:
        assert company_sec_coverage(session, SECOND_COMPANY_ID).filings.record_count == 1


@pytest.mark.integration
def test_cross_issuer_accession_conflict_flags_every_involved_issuer_once(
    postgres_engine: Engine,
) -> None:
    _companies(postgres_engine)
    same_accession = columnar(["10-K"], [ACCESSION], ["2026-02-10"], ["2025-12-31"])
    result = _ingest(
        postgres_engine,
        [
            _record(COMPANY_ID, same_accession),
            _record(SECOND_COMPANY_ID, same_accession),
            _record(COMPANY_ID, same_accession, history=True),
        ],
    )
    assert result["reconciliation"]["conflicting_accessions"] == 1
    for company_id, receipt in _receipts(result).items():
        assert receipt["conflicting_accessions"] == 1 and receipt["documents_imported"] == 0
        assert _outcome(result, UUID(company_id)) == ("DATA_CHECK", 0)
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(SourceDocument)) == 0
        assert session.scalar(select(func.count()).select_from(ExternalRawPayload)) == 3


@pytest.mark.integration
def test_existing_metadata_conflict_keeps_old_evidence_and_other_issuer_reuse(
    postgres_engine: Engine,
) -> None:
    _companies(postgres_engine)
    first = _ingest(postgres_engine, [_record(COMPANY_ID), _record(SECOND_COMPANY_ID)])
    changed = columnar(
        ["10-K"], ["0000000002-26-000001"], ["2026-02-10"], ["2025-12-31"], ["Changed source title"]
    )
    result = _ingest(postgres_engine, [_record(COMPANY_ID), _record(SECOND_COMPANY_ID, changed)])
    assert _outcome(result, COMPANY_ID) == ("REPORTED", 1)
    assert _outcome(result, SECOND_COMPANY_ID) == ("DATA_CHECK", 0)
    assert _receipts(result)[str(COMPANY_ID)]["documents_reused"] == 1
    assert _receipts(result)[str(SECOND_COMPANY_ID)]["existing_metadata_conflicts"] == 1
    with Session(postgres_engine) as session:
        docs = list(session.scalars(select(SourceDocument)))
        assert len(docs) == 2 and all(item.title != "Changed source title" for item in docs)
        original = session.get(SourceDocumentBatch, UUID(first["batch_id"]))
        assert original is not None and original.reconciliation == first["reconciliation"]


@pytest.mark.integration
def test_reused_flagged_filing_stays_in_issuer_and_aggregate_quality_counts(
    postgres_engine: Engine,
) -> None:
    _companies(postgres_engine)
    orphan = _record(
        SECOND_COMPANY_ID,
        columnar(["10-K/A"], ["0000000002-26-000002"], ["2026-03-01"], ["2025-12-31"]),
    )
    _ingest(postgres_engine, [orphan], {SECOND_COMPANY_ID: IDENTIFIERS[SECOND_COMPANY_ID]})
    result = _ingest(postgres_engine, [_record(COMPANY_ID), orphan])
    receipt = _receipts(result)[str(SECOND_COMPANY_ID)]
    assert receipt["documents_reused"] == receipt["data_check_documents"] == 1
    assert result["reconciliation"]["data_check_documents"] == 1
    assert _outcome(result, SECOND_COMPANY_ID) == ("DATA_CHECK", 1)


@pytest.mark.integration
def test_receipt_replay_is_deterministic_across_connections_and_legacy_stays_unchanged(
    postgres_engine: Engine,
) -> None:
    _companies(postgres_engine)
    records = [_record(COMPANY_ID), _record(SECOND_COMPANY_ID)]
    first = _ingest(postgres_engine, records)
    before = table_counts(postgres_engine)
    repeated = _ingest(postgres_engine, list(reversed(records)))
    assert repeated["status"] == "ALREADY_IMPORTED"
    assert (
        repeated["reconciliation"] == first["reconciliation"]
        and table_counts(postgres_engine) == before
    )
    # Seed the pre-contract representation only in this isolated synthetic schema.
    legacy = {
        key: value
        for key, value in first["reconciliation"].items()
        if not key.startswith("issuer_results")
    }
    with postgres_engine.begin() as connection:
        connection.execute(
            update(SourceDocumentBatch)
            .where(SourceDocumentBatch.id == UUID(first["batch_id"]))
            .values(reconciliation=legacy)
        )
    replayed = _ingest(postgres_engine, records)
    assert replayed["reconciliation"] == legacy and table_counts(postgres_engine) == before
    assert _outcome(replayed, COMPANY_ID) == ("NOT_REPORTED", None)


@pytest.mark.integration
def test_rejected_scope_and_rollback_leave_no_filing_records_or_receipts(
    postgres_engine: Engine,
) -> None:
    _companies(postgres_engine)
    before = table_counts(postgres_engine)
    with Session(postgres_engine) as session:
        with pytest.raises(ValueError, match="exact requested"):
            ingest_sec_submissions(
                session, _query({COMPANY_ID: CIK}), [_record(COMPANY_ID)], IDENTIFIERS
            )
        with pytest.raises(ValueError, match="distinct reviewed"):
            ingest_sec_submissions(
                session,
                _query(IDENTIFIERS),
                [_record(COMPANY_ID)],
                {COMPANY_ID: CIK, SECOND_COMPANY_ID: CIK},
            )
        with pytest.raises(ValueError, match="reviewed canonical"):
            ingest_sec_submissions(
                session,
                _query(IDENTIFIERS),
                [_record(COMPANY_ID)],
                {COMPANY_ID: "0000000009", SECOND_COMPANY_ID: "0000000002"},
            )
        session.rollback()
    with (
        pytest.raises(RuntimeError, match="Synthetic rollback"),
        Session(postgres_engine) as session,
        session.begin(),
    ):
        ingest_sec_submissions(
            session,
            _query(IDENTIFIERS),
            [_record(COMPANY_ID), _record(SECOND_COMPANY_ID)],
            IDENTIFIERS,
        )
        session.flush()
        raise RuntimeError("Synthetic rollback")
    assert table_counts(postgres_engine) == before


@pytest.mark.integration
def test_bounded_history_pages_reach_persisted_read_only_issuer_coverage(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _companies(postgres_engine)
    requests: list[str] = []

    def download(url: str, _agent: str) -> bytes:
        requests.append(url)
        company_id = SECOND_COMPANY_ID if "CIK0000000002" in url else COMPANY_ID
        payload = _record(company_id).payload
        assert payload is not None
        data = json.loads(payload)
        if company_id == COMPANY_ID:
            data["filings"]["files"] = [
                {"name": f"CIK{CIK}-submissions-{index:03d}.json"} for index in range(1, 8)
            ]
        return json.dumps(data).encode()

    monkeypatch.setattr("portfolio_api.source_documents._download_sec_json", download)
    first = _refresh(
        postgres_engine, domains=[FILINGS], company_ids=set(IDENTIFIERS), request_nonce=uuid4()
    )
    assert first["status"] == "PARTIAL" and len(requests) == 7
    with Session(postgres_engine) as session:
        primary = company_sec_coverage(session, COMPANY_ID).filings.refresh
        other = company_sec_coverage(session, SECOND_COMPANY_ID).filings.refresh
        assert primary is not None and other is not None
        assert primary.issuer_outcome == "DATA_CHECK" and primary.source_record_count == 1
        assert other.issuer_outcome == "REPORTED" and other.source_record_count == 1
    recovered = _refresh(
        postgres_engine, domains=[FILINGS], company_ids=set(IDENTIFIERS), request_nonce=uuid4()
    )
    assert recovered["status"] == "COMPLETE" and len(requests) == 11
    before = table_counts(postgres_engine)
    with postgres_engine.connect() as connection:
        schema = str(connection.scalar(text("SELECT current_schema()")))
    settings = fixture_settings()
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            for company_id in IDENTIFIERS:
                response = client.get(f"/v1/companies/{company_id}/sec-coverage")
                assert response.status_code == 200
                result = response.json()["filings"]
                assert result["record_count"] == 1 and result["refresh"]["source_record_count"] == 1
                assert result["refresh"]["issuer_outcome"] == "REPORTED"
    finally:
        reader.dispose()
    assert table_counts(postgres_engine) == before


def _typed_result() -> dict[str, Any]:
    return {
        "reconciliation": {
            "issuer_results_version": SEC_ISSUER_RECONCILIATION_VERSION,
            "issuer_results": [
                {
                    "company_id": str(company_id),
                    **{field: 0 for field in ISSUER_FILING_COUNT_FIELDS},
                    "response_record_count": 1,
                    "provider_filings_seen": 1,
                    "documents_imported": 1,
                }
                for company_id in IDENTIFIERS
            ],
        }
    }


@pytest.mark.parametrize(
    "problem",
    ["version", "missing", "duplicate", "foreign", "boolean", "negative", "contradiction"],
)
def test_malformed_new_contract_never_falls_back_to_aggregate_counts(problem: str) -> None:
    result = _typed_result()
    reconciliation = result["reconciliation"]
    reconciliation["documents_imported"] = 100
    items = reconciliation["issuer_results"]
    if problem == "version":
        reconciliation["issuer_results_version"] = "unknown"
    elif problem == "missing":
        del items[0]["response_record_count"]
    elif problem == "duplicate":
        items.append(copy.deepcopy(items[0]))
    elif problem == "foreign":
        items[0]["company_id"] = str(uuid4())
    elif problem == "boolean":
        items[0]["documents_imported"] = True
    elif problem == "negative":
        items[0]["documents_imported"] = -1
    else:
        items[0]["provider_filings_seen"] = 0
    assert _outcome(result, COMPANY_ID) == ("NOT_REPORTED", None)


def test_history_deferral_is_attributed_only_to_its_issuer_and_verified_totals() -> None:
    result = _typed_result()
    result.update(
        history_files_deferred=2,
        issuer_history_files_deferred={str(COMPANY_ID): 2, str(SECOND_COMPANY_ID): 0},
    )
    assert _outcome(result, COMPANY_ID) == ("DATA_CHECK", 1)
    assert _outcome(result, SECOND_COMPANY_ID) == ("REPORTED", 1)
    result["issuer_history_files_deferred"][str(COMPANY_ID)] = 1
    assert _outcome(result, SECOND_COMPANY_ID) == ("NOT_REPORTED", None)
    del result["issuer_history_files_deferred"]
    assert _outcome(result, COMPANY_ID) == ("NOT_REPORTED", None)


def test_receipt_requires_response_evidence_and_strict_nonnegative_counts() -> None:
    result = _typed_result()
    empty = {"company_id": str(COMPANY_ID), **{field: 0 for field in ISSUER_FILING_COUNT_FIELDS}}
    result["reconciliation"]["issuer_results"][0] = empty
    assert _outcome(result, COMPANY_ID) == ("NOT_REPORTED", None)
    with pytest.raises(ValidationError):
        SecIssuerFilingReconciliation.model_validate({**empty, "documents_reused": 1})
