"""Synthetic SEC bootstrap coverage and Company Explorer integration tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import URLError
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateBatch,
    FundamentalsBootstrapCheckpoint,
    FundamentalsBootstrapRun,
    ReportedFundamentalObservation,
    SourceDocument,
    SourceDocumentBatch,
)
from portfolio_api.external_data import ExternalDataDomain, RawProviderRecord
from portfolio_api.financial_statements import company_financial_statements
from portfolio_api.fundamentals_bootstrap import (
    FundamentalsBootstrapError,
    ProviderFetchResult,
    SecBootstrapProvider,
    _report_exit_code,
    execute_fundamentals_bootstrap,
    prepare_fundamentals_bootstrap,
    preview_fundamentals_bootstrap,
    reconcile_fundamentals_bootstrap,
)
from portfolio_api.main import create_app
from portfolio_api.reported_fundamentals import SEC_PROVIDER_ID, record_cik_mapping
from portfolio_api.settings import Settings
from portfolio_api.source_documents import SEC_SUBMISSIONS_BASE

COMPANY_ID = UUID("9d131761-7220-4f56-bc2e-381b5ae0d671")
CIK = "0000000001"
RETRIEVED_AT = datetime(2026, 10, 19, 10, tzinfo=UTC)
ANNUAL_ACCESSION = "0000000001-24-000001"
QUARTER_ACCESSION = "0000000001-24-000002"
AMENDED_ACCESSION = "0000000001-25-000003"
HISTORY_ONE = f"CIK{CIK}:HISTORY:CIK{CIK}-submissions-001.json"
HISTORY_TWO = f"CIK{CIK}:HISTORY:CIK{CIK}-submissions-002.json"


def _raw_record(
    domain: ExternalDataDomain,
    payload: dict[str, object],
    *,
    source_record_id: str,
    source_url: str,
    schema_version: str,
) -> RawProviderRecord:
    content = json.dumps(payload, separators=(",", ":")).encode()
    return RawProviderRecord(
        domain=domain,
        provider_id=SEC_PROVIDER_ID,
        provider_schema_version=schema_version,
        source_record_id=source_record_id,
        source_url=source_url,
        media_type="application/json",
        retrieved_at=RETRIEVED_AT,
        payload=content,
        payload_sha256=hashlib.sha256(content).hexdigest(),
    )


def _facts_record() -> RawProviderRecord:
    return _raw_record(
        ExternalDataDomain.REPORTED_FUNDAMENTALS,
        {
            "cik": 1,
            "entityName": "Synthetic Holdings Inc.",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2023-01-01",
                                    "end": "2023-12-31",
                                    "val": 9007199254740993,
                                    "accn": ANNUAL_ACCESSION,
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-02-10",
                                    "frame": "CY2023",
                                },
                                {
                                    "start": "2023-01-01",
                                    "end": "2023-12-31",
                                    "val": 9007199254740994,
                                    "accn": AMENDED_ACCESSION,
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K/A",
                                    "filed": "2025-03-01",
                                    "frame": "CY2023",
                                },
                                {
                                    "start": "2024-01-01",
                                    "end": "2024-03-31",
                                    "val": 250,
                                    "accn": QUARTER_ACCESSION,
                                    "fy": 2024,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2024-05-10",
                                    "frame": "CY2024Q1",
                                },
                            ]
                        }
                    },
                    "CashAndCashEquivalentsAtCarryingValue": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2023-12-31",
                                    "val": 0,
                                    "accn": ANNUAL_ACCESSION,
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-02-10",
                                }
                            ]
                        }
                    },
                }
            },
        },
        source_record_id=f"CIK{CIK}",
        source_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json",
        schema_version="companyfacts-v1",
    )


def _columnar(
    forms: list[str], accessions: list[str], filed: list[str], periods: list[str]
) -> dict[str, object]:
    return {
        "cik": 1,
        "name": "Synthetic Holdings Inc.",
        "filings": {
            "recent": {
                "form": forms,
                "accessionNumber": accessions,
                "filingDate": filed,
                "reportDate": periods,
            }
        },
    }


def _document_record(
    source_record_id: str,
    payload: dict[str, object],
    *,
    history_file: str | None = None,
) -> RawProviderRecord:
    if history_file:
        url = f"{SEC_SUBMISSIONS_BASE}/{history_file}"
    else:
        url = f"{SEC_SUBMISSIONS_BASE}/CIK{CIK}.json"
    return _raw_record(
        ExternalDataDomain.SOURCE_DOCUMENTS,
        payload,
        source_record_id=source_record_id,
        source_url=url,
        schema_version="submissions-v1",
    )


MAIN_SUBMISSIONS = _document_record(
    f"CIK{CIK}",
    _columnar(
        ["10-K", "10-Q"],
        [ANNUAL_ACCESSION, QUARTER_ACCESSION],
        ["2024-02-10", "2024-05-10"],
        ["2023-12-31", "2024-03-31"],
    ),
)
HISTORY_ONE_RECORD = _document_record(
    HISTORY_ONE,
    _columnar(["10-K/A"], [AMENDED_ACCESSION], ["2025-03-01"], ["2023-12-31"]),
    history_file=f"CIK{CIK}-submissions-001.json",
)
HISTORY_TWO_RECORD = _document_record(
    HISTORY_TWO,
    _columnar(["8-K"], ["0000000001-25-000004"], ["2025-04-01"], [""]),
    history_file=f"CIK{CIK}-submissions-002.json",
)


class SyntheticSecProvider:
    def __init__(self, *, fail_first_source_request: bool = False) -> None:
        self.calls: list[tuple[str, UUID, set[str]]] = []
        self.fail_first_source_request = fail_first_source_request
        self.source_request_failed = False

    async def fetch(
        self,
        *,
        stage: str,
        company_id: UUID,
        cik: str,
        query: Any,
        known_source_record_ids: set[str],
    ) -> ProviderFetchResult:
        assert cik == CIK
        assert len(query.subjects) == 1
        self.calls.append((stage, company_id, set(known_source_record_ids)))
        if stage == "SOURCE_DOCUMENTS":
            if self.fail_first_source_request and not self.source_request_failed:
                self.source_request_failed = True
                raise URLError("synthetic temporary SEC outage")
            if HISTORY_ONE not in known_source_record_ids:
                return ProviderFetchResult(
                    (MAIN_SUBMISSIONS, HISTORY_ONE_RECORD),
                    (HISTORY_TWO,),
                    request_count=2,
                )
            if HISTORY_TWO not in known_source_record_ids:
                return ProviderFetchResult((HISTORY_TWO_RECORD,), request_count=2)
            return ProviderFetchResult((MAIN_SUBMISSIONS,))
        assert stage == "REPORTED_FUNDAMENTALS"
        return ProviderFetchResult((_facts_record(),), request_count=1)


def _prepare_run(engine: Engine) -> UUID:
    with Session(engine) as session:
        session.add(
            Company(
                id=COMPANY_ID,
                name="Synthetic canonical company",
                reporting_currency="USD",
            )
        )
        session.flush()
        record_cik_mapping(
            session,
            COMPANY_ID,
            CIK,
            "Synthetic Holdings Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )
        run = prepare_fundamentals_bootstrap(session, target_environment="rehearsal")
        session.commit()
        return run.id


def _execute(
    engine: Engine,
    run_id: UUID,
    provider: SyntheticSecProvider,
    max_checkpoints: int,
) -> dict[str, Any]:
    return execute_fundamentals_bootstrap(
        engine,
        run_id,
        target_environment="rehearsal",
        provider=provider,
        user_agent="Synthetic Portfolio Research test@example.test",
        max_checkpoints=max_checkpoints,
    )


def test_bootstrap_preview_is_read_only_and_production_is_rejected() -> None:
    with pytest.raises(FundamentalsBootstrapError, match="development or rehearsal"):
        preview_fundamentals_bootstrap(None, target_environment="production")  # type: ignore[arg-type]


def test_sec_provider_requires_contact_bearing_user_agent() -> None:
    with pytest.raises(FundamentalsBootstrapError, match="monitored contact email"):
        SecBootstrapProvider("Portfolio Research Platform")


def test_bootstrap_cli_reports_blocked_readiness_as_failure() -> None:
    assert _report_exit_code("preview", {"status": "READY"}) == 0
    assert _report_exit_code("preview", {"status": "BLOCKED"}) == 2
    assert _report_exit_code("prepare", {"status": "BLOCKED"}) == 2
    assert _report_exit_code("reconcile", {"reconciliation": {"status": "MATCHED"}}) == 0


def test_ci_has_no_sec_contact_or_licensed_provider_credentials() -> None:
    workflow = Path(__file__).parents[3] / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8").upper()
    assert "SEC_USER_AGENT" not in text
    assert "FMP_API_KEY" not in text
    assert "NEON_DATABASE_URL" not in text


@pytest.mark.integration
def test_fundamentals_bootstrap_is_resumable_exact_and_company_explorer_compatible(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _prepare_run(postgres_engine)
    provider = SyntheticSecProvider()

    first = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert first["status"] == "PARTIAL"
    assert first["pending_checkpoints"] == 2
    assert provider.calls[0][0] == "SOURCE_DOCUMENTS"

    second = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert second["status"] == "PARTIAL"
    assert second["pending_checkpoints"] == 1
    assert provider.calls[1][2] == {HISTORY_ONE}

    with Session(postgres_engine) as session:
        fact_checkpoint = session.scalar(
            select(FundamentalsBootstrapCheckpoint).where(
                FundamentalsBootstrapCheckpoint.run_id == run_id,
                FundamentalsBootstrapCheckpoint.stage == "REPORTED_FUNDAMENTALS",
            )
        )
        run = session.get(FundamentalsBootstrapRun, run_id)
        assert fact_checkpoint is not None and run is not None
        fact_checkpoint.status = "RUNNING"
        fact_checkpoint.started_at = RETRIEVED_AT
        run.status = "RUNNING"
        session.commit()

    complete = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert complete["status"] == "PARTIAL"  # changed amendment is explicitly DATA_CHECK
    assert complete["pending_checkpoints"] == 0
    reconciliation = reconcile_fundamentals_bootstrap
    with Session(postgres_engine) as session:
        report = reconciliation(session, run_id)
        assert report["reconciliation"]["status"] == "MATCHED"
        assert report["coverage"]["consensus_estimates"] == "EXCLUDED_LICENSED_SOURCE_DISABLED"
        assert report["coverage"]["accession_reference_coverage"] == {
            "fact_accessions": 3,
            "matched_source_documents": 3,
            "fact_accessions_without_supported_source_document": 0,
        }
        checkpoint = session.scalar(
            select(FundamentalsBootstrapCheckpoint).where(
                FundamentalsBootstrapCheckpoint.run_id == run_id,
                FundamentalsBootstrapCheckpoint.stage == "REPORTED_FUNDAMENTALS",
            )
        )
        assert checkpoint is not None
        history = checkpoint.report.get("failure_history")
        assert isinstance(history, list)
        assert history[0]["code"] == "WORKER_INTERRUPTED"

        facts = list(
            session.scalars(
                select(ReportedFundamentalObservation).where(
                    ReportedFundamentalObservation.company_id == COMPANY_ID
                )
            )
        )
        assert len(facts) == 4
        annual = next(
            item
            for item in facts
            if item.accession_number == ANNUAL_ACCESSION and item.metric == "REVENUE"
        )
        amended = next(
            item
            for item in facts
            if item.accession_number == AMENDED_ACCESSION and item.metric == "REVENUE"
        )
        assert annual.value == Decimal("9007199254740993")
        assert amended.value == Decimal("9007199254740994")
        assert amended.supersedes_observation_id == annual.id
        cash = next(item for item in facts if item.metric == "CASH_AND_CASH_EQUIVALENTS")
        assert cash.period_type == "INSTANT" and cash.period_start is None
        assert cash.value == Decimal(0)
        assert all(item.accession_number for item in facts)

        documents = list(
            session.scalars(select(SourceDocument).where(SourceDocument.company_id == COMPANY_ID))
        )
        assert len(documents) == 4
        original = next(item for item in documents if item.external_identifier == ANNUAL_ACCESSION)
        amendment = next(
            item for item in documents if item.external_identifier == AMENDED_ACCESSION
        )
        assert amendment.amends_document_id == original.id
        assert session.scalar(select(func.count()).select_from(SourceDocumentBatch)) == 2

        statements = company_financial_statements(session, COMPANY_ID, period_type="ANNUAL")
        revenue = next(row for row in statements.rows if row.metric == "REVENUE")
        assert len(revenue.cells) == 1
        assert revenue.cells[0].period_end.isoformat() == "2023-12-31"
        assert revenue.cells[0].value == Decimal("9007199254740994")
        assert revenue.cells[0].status == "DATA_CHECK"
        cash_row = next(row for row in statements.rows if row.metric == "CASH_AND_CASH_EQUIVALENTS")
        assert len(cash_row.cells) == 1 and cash_row.cells[0].value == Decimal(0)

        monkeypatch.setattr(
            "portfolio_api.main.create_database_engine",
            lambda _settings, **_kwargs: postgres_engine,
        )
        with TestClient(create_app(Settings.model_construct())) as client:
            statement_response = client.get(
                f"/v1/companies/{COMPANY_ID}/financial-statements?period_type=ANNUAL"
            )
            document_response = client.get(f"/v1/companies/{COMPANY_ID}/source-documents")
        assert statement_response.status_code == 200
        assert statement_response.json()["periods"][0]["period_end"] == "2023-12-31"
        assert document_response.status_code == 200
        assert len(document_response.json()["documents"]) == 4

        fact_count_before = session.scalar(
            select(func.count()).select_from(ReportedFundamentalObservation)
        )
        document_count_before = session.scalar(select(func.count()).select_from(SourceDocument))
        consensus_count = session.scalar(select(func.count()).select_from(ConsensusEstimateBatch))
        assert consensus_count == 0

    repeated = _execute(postgres_engine, run_id, provider, max_checkpoints=10)
    assert repeated["status"] == "PARTIAL"
    assert len(provider.calls) == 3
    with Session(postgres_engine) as session:
        assert (
            session.scalar(select(func.count()).select_from(ReportedFundamentalObservation))
            == fact_count_before
        )
        assert (
            session.scalar(select(func.count()).select_from(SourceDocument))
            == document_count_before
        )


@pytest.mark.integration
def test_bootstrap_blocks_mapping_changes_before_provider_access(postgres_engine: Engine) -> None:
    run_id = _prepare_run(postgres_engine)
    with Session(postgres_engine) as session:
        session.execute(
            text(
                "UPDATE company_provider_identifiers "
                "SET provider_company_name = :issuer_name "
                "WHERE company_id = :company_id AND provider_id = :provider_id"
            ),
            {
                "issuer_name": "A different synthetic issuer",
                "company_id": COMPANY_ID,
                "provider_id": SEC_PROVIDER_ID,
            },
        )
        session.commit()
    provider = SyntheticSecProvider()
    report = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert report["status"] == "BLOCKED"
    assert provider.calls == []


@pytest.mark.integration
def test_bootstrap_blocks_new_ambiguous_mapping_before_provider_access(
    postgres_engine: Engine,
) -> None:
    run_id = _prepare_run(postgres_engine)
    with Session(postgres_engine) as session:
        record_cik_mapping(
            session,
            COMPANY_ID,
            "0000000002",
            "Another synthetic issuer",
            "https://www.sec.gov/edgar/browse/?CIK=2",
        )
        session.commit()
    provider = SyntheticSecProvider()
    report = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert report["status"] == "BLOCKED"
    assert report["failure_code"] == "REVIEWED_SEC_MAPPING_INVALID"
    assert provider.calls == []


@pytest.mark.integration
def test_bootstrap_rejects_missing_and_ambiguous_reviewed_cik_mappings(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        session.add(
            Company(
                id=COMPANY_ID,
                name="Synthetic canonical company",
                reporting_currency="USD",
            )
        )
        session.flush()
        preview = preview_fundamentals_bootstrap(session, target_environment="rehearsal")
        assert preview["status"] == "BLOCKED"
        assert preview["reason"] == "NO_REVIEWED_SEC_CIK_MAPPINGS"
        run = prepare_fundamentals_bootstrap(session, target_environment="rehearsal")
        assert run.status == "BLOCKED"
        assert run.scope["mappings"] == []
        session.commit()

    with Session(postgres_engine) as session:
        record_cik_mapping(
            session,
            COMPANY_ID,
            CIK,
            "Synthetic Holdings Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )
        record_cik_mapping(
            session,
            COMPANY_ID,
            "0000000002",
            "Another synthetic issuer",
            "https://www.sec.gov/edgar/browse/?CIK=2",
        )
        session.commit()
        with pytest.raises(FundamentalsBootstrapError, match="ambiguous"):
            preview_fundamentals_bootstrap(session, target_environment="rehearsal")


@pytest.mark.integration
@pytest.mark.parametrize(
    "evidence_source",
    (
        "https://issuer.example.test/company/1",
        "https://www.sec.gov/edgar/browse/?CIK=2",
    ),
)
def test_bootstrap_requires_cik_specific_sec_evidence_url(
    postgres_engine: Engine,
    evidence_source: str,
) -> None:
    with Session(postgres_engine) as session:
        session.add(
            Company(
                id=COMPANY_ID,
                name="Synthetic canonical company",
                reporting_currency="USD",
            )
        )
        session.flush()
        record_cik_mapping(
            session,
            COMPANY_ID,
            CIK,
            "Synthetic Holdings Inc.",
            evidence_source,
        )
        with pytest.raises(FundamentalsBootstrapError, match="SEC.gov evidence URL"):
            preview_fundamentals_bootstrap(session, target_environment="rehearsal")


@pytest.mark.integration
def test_bootstrap_retry_after_sec_network_failure_is_bounded_and_recorded(
    postgres_engine: Engine,
) -> None:
    run_id = _prepare_run(postgres_engine)
    provider = SyntheticSecProvider(fail_first_source_request=True)
    failed = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert failed["status"] == "PARTIAL"
    with Session(postgres_engine) as session:
        checkpoint = session.scalar(
            select(FundamentalsBootstrapCheckpoint).where(
                FundamentalsBootstrapCheckpoint.run_id == run_id,
                FundamentalsBootstrapCheckpoint.stage == "SOURCE_DOCUMENTS",
            )
        )
        assert checkpoint is not None
        assert checkpoint.status == "FAILED" and checkpoint.retryable
        assert checkpoint.failure_code == "SEC_NETWORK_FAILURE"
        checkpoint.next_attempt_at = datetime(2026, 10, 18, tzinfo=UTC)
        session.commit()
    resumed = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert resumed["status"] == "PARTIAL"
    with Session(postgres_engine) as session:
        checkpoint = session.scalar(
            select(FundamentalsBootstrapCheckpoint).where(
                FundamentalsBootstrapCheckpoint.run_id == run_id,
                FundamentalsBootstrapCheckpoint.stage == "SOURCE_DOCUMENTS",
            )
        )
        assert checkpoint is not None
        failure_history = checkpoint.report.get("failure_history")
        assert isinstance(failure_history, list)
        assert any(
            isinstance(item, dict) and item.get("code") == "SEC_NETWORK_FAILURE"
            for item in failure_history
        )
        assert checkpoint.page_count == 1
        assert checkpoint.provider_request_count == 3
