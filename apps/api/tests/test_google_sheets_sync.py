"""Fixture and PostgreSQL verification for reviewed Google Sheets synchronization."""

import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Actor,
    FinancialModelRevision,
    FinancialModelRevisionEvidence,
    GoogleSheetsSyncCandidate,
    GoogleSheetsSyncRun,
    Lifecycle,
    PriceObservation,
    SourceDocument,
)
from portfolio_api.domain.services import transition_lifecycle
from portfolio_api.google_sheets_sync import (
    ConnectionResult,
    ContractBlock,
    GoogleSheetsApiReader,
    GoogleSheetsSyncError,
    InboxSnapshot,
    accept_sync_candidate,
    assemble_contract_blocks,
    parse_portable_contract,
    preview_sync_candidate,
    run_sync_check,
)
from portfolio_api.google_sheets_sync import (
    test_google_sheets_connection as check_google_sheets_connection,
)
from portfolio_api.main import create_app
from portfolio_api.research_sheet_sync import (
    THESIS_SYNC_TAB,
    accept_research_candidate,
    preview_research_candidate,
    run_research_sync_check,
)
from portfolio_api.research_triggers import refresh_research_triggers
from portfolio_api.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "p_googl_ufcf_dcf_v1.json"
ADDITIONAL_FIXTURES = Path(__file__).parent / "fixtures"
SPREADSHEET_ID = "fictional-test-spreadsheet-id-0000000000000000000000"


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self.payload


class FakeHttpSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class FakeReader:
    def __init__(self, blocks: list[ContractBlock]) -> None:
        self.blocks = blocks
        self.connection = ConnectionResult("Private Investment Workbook", True, 10)

    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult:
        assert spreadsheet_id == SPREADSHEET_ID
        assert sync_tab == "Application Model Sync Inbox"
        return self.connection

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        return InboxSnapshot(self.connection, self.blocks)


class FakeResearchReader:
    def __init__(self, thesis_block: ContractBlock) -> None:
        self.thesis_block = thesis_block

    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult:
        return ConnectionResult("Research workbook fixture", True, 43)

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        connection = self.test_connection(spreadsheet_id, sync_tab)
        return InboxSnapshot(connection, [self.thesis_block] if sync_tab == THESIS_SYNC_TAB else [])


def _publish_research_evidence(
    client: TestClient,
    *,
    company_id: str,
    security_id: str,
    observed_at: datetime,
    stream_key: str,
) -> tuple[str, str]:
    response = client.post(
        "/v1/research-revisions",
        json={
            "contract_type": "ResearchRevisionContractV1",
            "contract_version": "1.0.0",
            "company_id": company_id,
            "security_id": security_id,
            "stream_key": stream_key,
            "external_revision_id": f"{stream_key}-r1",
            "supersedes_revision_id": None,
            "author_id": "research-agent-fixture",
            "source_id": "fixture-research-workbook",
            "source_reference": "https://docs.google.com/spreadsheets/d/research-fixture/edit",
            "observed_at": observed_at.isoformat(),
            "status": "PUBLISHED",
            "rationale": "Published source-backed forecast used to support the model proposal.",
            "uncertainty": "Fixture data; not an investment recommendation.",
            "forecasts": [
                {
                    "metric": "REVENUE",
                    "period_type": "ANNUAL",
                    "fiscal_year": 2027,
                    "fiscal_period": "FY",
                    "period_end": "2027-12-31",
                    "scenario": "BASE",
                    "value": "123456",
                    "currency": "USD",
                    "unit": "currency",
                    "availability_status": "AVAILABLE",
                    "confidence": "HIGH",
                    "rationale": "Published research estimate.",
                }
            ],
            "assessments": [],
            "evidence": [
                {
                    "source_name": "Fixture issuer filing",
                    "external_identifier": "fixture-10k-2025",
                    "source_url": "https://issuer.example/filings/2025-10k",
                    "published_at": "2026-02-01",
                    "note": "Source context for the forecast.",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    revision = response.json()["revision"]
    return revision["id"], revision["forecasts"][0]["id"]


def test_explicit_inbox_chunk_rows_reassemble_and_reject_gaps() -> None:
    chunks = assemble_contract_blocks(
        [
            ["publish-1", "sheet-rev-1", "2", "2", "world"],
            ["publish-1", "sheet-rev-1", "1", "2", "hello "],
        ]
    )
    assert chunks == [ContractBlock("publish-1", "sheet-rev-1", 2, "hello world")]

    invalid = assemble_contract_blocks([["publish-2", "sheet-rev-2", "1", "2", "incomplete"]])
    assert len(invalid) == 1
    assert invalid[0].issue == "Contract chunk sequence is incomplete or duplicated"


def test_read_only_google_api_client_reads_only_configured_inbox(tmp_path: Path) -> None:
    credential = tmp_path / "reader.json"
    credential.write_text("fixture only", encoding="utf-8")
    settings = Settings(
        google_sheets_spreadsheet_id=SPREADSHEET_ID,
        google_sheets_service_account_file=credential,
        google_sheets_sync_tab="Application Model Sync Inbox",
    )
    session = FakeHttpSession(
        [
            FakeResponse(
                {
                    "spreadsheetId": SPREADSHEET_ID,
                    "properties": {"title": "Private Investment Workbook"},
                    "sheets": [
                        {"properties": {"sheetId": 10, "title": "Application Model Sync Inbox"}}
                    ],
                }
            ),
            FakeResponse({"values": [["publish-1", "revision-1", 1, 1, "{}"]]}),
        ]
    )
    snapshot = GoogleSheetsApiReader(settings, session).read_inbox(
        SPREADSHEET_ID, "Application Model Sync Inbox"
    )
    assert snapshot.connection.sync_tab_exists
    assert snapshot.blocks[0].contract_text == "{}"
    assert len(session.requests) == 2
    assert "spreadsheets.readonly" not in session.requests[0][0]
    assert "Application%20Model%20Sync%20Inbox" in session.requests[1][0]
    assert all(
        kwargs["timeout"] == (5, settings.google_sheets_request_timeout_seconds)
        for _, kwargs in session.requests
    )


def test_google_api_auth_and_network_failures_are_explicit(tmp_path: Path) -> None:
    credential = tmp_path / "reader.json"
    credential.write_text("fixture only", encoding="utf-8")
    settings = Settings(
        google_sheets_spreadsheet_id=SPREADSHEET_ID,
        google_sheets_service_account_file=credential,
    )
    forbidden = FakeHttpSession([FakeResponse({"error": "forbidden"}, status_code=403)])
    with pytest.raises(GoogleSheetsSyncError, match="Google rejected"):
        GoogleSheetsApiReader(settings, forbidden).test_connection(
            SPREADSHEET_ID, "Application Model Sync Inbox"
        )

    class OfflineSession:
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            raise ConnectionError("fixture offline")

    with pytest.raises(GoogleSheetsSyncError, match="Google Sheets request failed"):
        GoogleSheetsApiReader(settings, OfflineSession()).test_connection(
            SPREADSHEET_ID, "Application Model Sync Inbox"
        )


def test_connection_reports_missing_credentials_without_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", raising=False)
    result = check_google_sheets_connection(
        Settings(_env_file=None, google_sheets_spreadsheet_id=SPREADSHEET_ID)
    )
    assert not result.connected
    assert "GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE" in result.message


def test_unsupported_portable_contract_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported portable model contract version"):
        parse_portable_contract('{"contract_version":"99.0.0"}')


@pytest.mark.integration
def test_candidate_replay_preview_acceptance_and_stale_base_conflict(
    postgres_engine: Engine,
) -> None:
    fixture = cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))
    now = datetime.now(UTC)
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        company = client.post(
            "/v1/companies", json={"name": "Sheets fixture issuer", "reporting_currency": "USD"}
        ).json()
        security = client.post(
            f"/v1/companies/{company['id']}/securities",
            json={"name": "Sheets fixture share", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "NASDAQ", "ticker": "SHEET", "currency": "USD"},
        ).json()
        filing_at = datetime.now(UTC).replace(microsecond=0)
        with Session(postgres_engine) as db, db.begin():
            transition_lifecycle(
                db,
                UUID(company["id"]),
                s.LifecycleChange(
                    actor=Actor.LOCAL_USER,
                    reason="Active fixture for Thesis Watch flow",
                    source="test_thesis_watch_e2e",
                    effective_at=filing_at,
                    new_state=Lifecycle.WATCHLIST,
                    expected_event_id=None,
                ),
            )
            filing = SourceDocument(
                company_id=UUID(company["id"]),
                provider_id="fixture-regulator",
                source_name="Fixture regulator",
                source_jurisdiction="US",
                external_identifier="fixture-10q-2026-q3",
                document_type="10-Q",
                title="Quarterly report",
                reporting_period="FY2026 Q3",
                published_at=filing_at.date(),
                filed_at=filing_at.date(),
                canonical_url="https://issuer.example.test/10q-2026-q3",
                recorded_at=filing_at,
                actor=Actor.IMPORT,
            )
            db.add(filing)
            db.flush()
            filing_id = filing.id
            captured = refresh_research_triggers(
                db,
                as_of=filing_at + timedelta(seconds=2),
                lookback_days=30,
                company_id=UUID(company["id"]),
            )
            filing_trigger = next(
                item for item in captured.triggers if item.source_record_id == str(filing_id)
            )
            trigger_id = filing_trigger.id
        context = client.get(f"/v1/research-triggers/{trigger_id}/context")
        assert context.status_code == 200
        assert context.json()["trigger"]["source_record_id"] == str(filing_id)
        assert context.json()["listings"][0]["id"] == listing["id"]

        observed = datetime.now(UTC)
        thesis_contract = {
            "contract_type": "InvestmentThesisContractV1",
            "contract_version": "1.1.0",
            "company_id": company["id"],
            "security_id": None,
            "stream_key": "investment-thesis",
            "external_revision_id": "thesis-trigger-e2e-r1",
            "supersedes_revision_id": None,
            "author_id": "research-agent-fixture",
            "source_id": "fixture-research-workbook",
            "source_reference": "https://docs.google.com/spreadsheets/d/research-fixture/edit#gid=43",
            "observed_at": observed.isoformat(),
            "status": "PUBLISHED",
            "thesis_statement": "The filing confirms a durable customer relationship advantage.",
            "confidence": "MEDIUM",
            "rationale": "The filing supports an incremental thesis update.",
            "uncertainty": "One quarter does not establish a trend.",
            "claims": [
                {
                    "claim_key": "customer-retention",
                    "claim_type": "COMPETITIVE_ADVANTAGE",
                    "status": "ACTIVE",
                    "statement": "Customer retention may reinforce switching costs.",
                    "confidence": "MEDIUM",
                    "evidence": [
                        {
                            "relationship": "SUPPORTS",
                            "source_document_id": str(filing_id),
                            "source_name": "Fixture regulator",
                            "external_identifier": "fixture-10q-2026-q3",
                            "published_at": filing_at.date().isoformat(),
                            "note": "Evidence from the captured quarterly report.",
                        }
                    ],
                }
            ],
            "trigger_references": [
                {
                    "trigger_id": str(trigger_id),
                    "classification": "INCREMENTAL",
                    "classification_rationale": (
                        "The disclosure updates one claim without changing "
                        "the overall thesis structure."
                    ),
                }
            ],
        }
        thesis_block = ContractBlock(
            "publish-thesis-trigger-e2e",
            "thesis-trigger-e2e-r1",
            2,
            json.dumps(thesis_contract),
        )
        research_settings = Settings(google_sheets_spreadsheet_id=SPREADSHEET_ID)
        with Session(postgres_engine) as db, db.begin():
            thesis_check = run_research_sync_check(
                db, research_settings, FakeResearchReader(thesis_block)
            )
            assert thesis_check.run.new_count == 1
            thesis_candidate = preview_research_candidate(db, thesis_check.new_candidates[0].id)
            assert thesis_candidate.status == "READY"
            accepted_thesis = accept_research_candidate(
                db,
                thesis_candidate.id,
                "reviewer@example.test",
                "Reviewed the filing and linked interpretation.",
            )
            assert accepted_thesis.status == "ACCEPTED"
            assert accepted_thesis.accepted_thesis_revision_id is not None
        thesis_read = client.get(f"/v1/companies/{company['id']}/thesis").json()
        accepted_thesis_revision = thesis_read["streams"][0]["current_revision"]
        assert accepted_thesis_revision["trigger_references"][0]["trigger_id"] == str(trigger_id)
        assert accepted_thesis_revision["trigger_references"][0]["classification"] == "INCREMENTAL"

        research_revision_id, research_forecast_id = _publish_research_evidence(
            client,
            company_id=company["id"],
            security_id=security["id"],
            observed_at=now,
            stream_key="sheets-model-support",
        )
        with Session(postgres_engine) as db, db.begin():
            db.add(
                PriceObservation(
                    listing_id=UUID(listing["id"]),
                    market_date=now - timedelta(hours=1),
                    provider_close=Decimal("100"),
                    split_adjusted_close=Decimal("100"),
                    total_return_close=None,
                    volume=None,
                    currency="USD",
                    provider="sync-test",
                    provider_symbol="NASDAQ:SHEET",
                    adjustment_basis="Fixture close",
                    data_quality="PASS",
                    source_ref="test:google-sheets-sync-price",
                )
            )
        source = cast(dict[str, object], fixture["input"])
        initial_revision = copy.deepcopy(source)
        initial_revision["effective_at"] = now.isoformat()
        create = client.post(
            f"/v1/companies/{company['id']}/financial-models",
            json={
                "model_type": "UFCF_DCF_10Y_FADE",
                "model_name": "Fixture DCF",
                "valuation_listing_id": listing["id"],
                "model_currency": "USD",
                "source_model_key": "SHEET-FIXTURE",
                "initial_revision": initial_revision,
            },
        )
        assert create.status_code == 201, create.text
        model = create.json()
        export = client.get(f"/v1/financial-models/{model['id']}/contract").json()
        assert export["contract_version"] == "1.2.0"

        unsupported = copy.deepcopy(export)
        unsupported["contract_version"] = "99.0.0"
        with pytest.raises(ValueError, match="Unsupported portable model contract version"):
            parse_portable_contract(json.dumps(unsupported))
        missing_rationale = copy.deepcopy(export)
        missing_rationale["candidate_revision"]["rationale"] = ""
        with pytest.raises(ValueError):
            parse_portable_contract(json.dumps(missing_rationale))
        mismatched_currency = copy.deepcopy(export)
        mismatched_currency["model"]["model_currency"] = "EUR"
        with pytest.raises(ValueError):
            parse_portable_contract(json.dumps(mismatched_currency))

        proposal = {
            "author_id": "research-agent-fixture",
            "authored_at": now.isoformat(),
            "source_reference": "https://docs.google.com/spreadsheets/d/research-fixture/edit",
        }
        insufficient = copy.deepcopy(export)
        insufficient["candidate_revision"]["source_revision_id"] = "sheet-rev-no-evidence"
        insufficient["candidate_revision"]["effective_at"] = now.isoformat()
        insufficient["candidate_revision"]["rationale"] = "A proposal missing canonical evidence."
        insufficient["proposal"] = proposal
        insufficient["candidate_revision"]["scenarios"][1]["years"][0]["revenue_growth"] = "0.214"
        reader = FakeReader(
            [
                ContractBlock(
                    "publish-no-evidence",
                    "sheet-rev-no-evidence",
                    2,
                    json.dumps(insufficient),
                )
            ]
        )
        settings = Settings(
            google_sheets_spreadsheet_id=SPREADSHEET_ID,
            google_sheets_sync_tab="Application Model Sync Inbox",
        )
        with Session(postgres_engine) as db, db.begin():
            missing_evidence_candidate = run_sync_check(db, settings, reader).new_candidates[0]
        with Session(postgres_engine) as db, db.begin():
            missing_evidence_preview = preview_sync_candidate(db, missing_evidence_candidate.id)
            assert missing_evidence_preview.status == "INVALID"
            assert "INSUFFICIENT_EVIDENCE" in (missing_evidence_preview.issue or "")

        changed = copy.deepcopy(export)
        changed["candidate_revision"]["source_revision_id"] = "sheet-rev-accepted"
        changed["candidate_revision"]["effective_at"] = now.isoformat()
        changed["candidate_revision"]["rationale"] = (
            "Reviewed a source-backed revenue-growth update."
        )
        changed["proposal"] = proposal
        changed["supporting_evidence"] = [
            {
                "evidence_type": "RESEARCH_FORECAST",
                "reference_id": research_forecast_id,
                "relationship": "SUPPORTS",
                "note": "Revenue estimate supporting the revised top-line path.",
            },
            {
                "evidence_type": "RESEARCH_REVISION",
                "reference_id": research_revision_id,
                "relationship": "CONTEXT",
                "note": "Read the full author rationale and its uncertainty.",
            },
            {
                "evidence_type": "THESIS_CLAIM",
                "reference_id": accepted_thesis_revision["claims"][0]["id"],
                "relationship": "CONTEXT",
                "note": "The accepted thesis interpretation is linked to the filing trigger.",
            },
        ]
        changed["candidate_revision"]["scenarios"][1]["years"][0]["revenue_growth"] = "0.215"
        block = ContractBlock(
            "publish-accepted",
            "sheet-rev-accepted",
            2,
            json.dumps(changed),
        )
        reader.blocks = [block]
        with Session(postgres_engine) as db, db.begin():
            first_check = run_sync_check(db, settings, reader)
            assert first_check.run.new_count == 1
            first_run_id = first_check.run.id
            candidate_id = first_check.new_candidates[0].id
        with Session(postgres_engine) as db, db.begin():
            preview = preview_sync_candidate(db, candidate_id)
            assert preview.status == "READY"
            assert len(preview.supporting_evidence) == 3
            assert all(item.resolution_status == "VERIFIED" for item in preview.supporting_evidence)
            thesis_evidence = next(
                item for item in preview.supporting_evidence if item.evidence_type == "THESIS_CLAIM"
            )
            assert thesis_evidence.trigger_references[0].trigger_id == trigger_id
            assert preview.preview_data is not None
            assert preview.preview_data["changes"]
            assert preview.preview_data["projection_changes"]
            assert preview.preview_data["output_changes"]
        with Session(postgres_engine) as db, db.begin():
            replay = run_sync_check(db, settings, reader)
            assert replay.run.new_count == 0
            assert replay.run.unchanged_count == 1
        with Session(postgres_engine) as db:
            first_run = db.get(GoogleSheetsSyncRun, first_run_id)
            assert first_run is not None and first_run.completed_at is not None
            first_run.status = "FAILED"
            with pytest.raises(
                ValueError, match="Completed Google Sheets synchronization runs are immutable"
            ):
                db.flush()
        with Session(postgres_engine) as db, db.begin():
            accepted = accept_sync_candidate(
                db, candidate_id, "Reviewer", "Accepted after comparison."
            )
            assert accepted.status == "ACCEPTED"
            accepted_revision_id = accepted.accepted_revision_id
            assert accepted_revision_id is not None
            assert accepted.reviewer == "Reviewer"
            assert accepted.proposal is not None
            assert accepted.proposal.author_id == "research-agent-fixture"
            assert len(accepted.supporting_evidence) == 3

        revision_history = client.get(f"/v1/financial-models/{model['id']}/revisions").json()
        accepted_read = next(
            item for item in revision_history if item["id"] == str(accepted_revision_id)
        )
        assert accepted_read["proposal_author_id"] == "research-agent-fixture"
        assert accepted_read["proposal_source_reference"].startswith("https://")
        assert len(accepted_read["supporting_evidence"]) == 3
        accepted_thesis_evidence = next(
            item
            for item in accepted_read["supporting_evidence"]
            if item["evidence_type"] == "THESIS_CLAIM"
        )
        assert accepted_thesis_evidence["trigger_references"][0]["trigger_id"] == str(trigger_id)
        assert any(
            item["evidence_type"] == "RESEARCH_FORECAST"
            and item["reference_id"] == research_forecast_id
            and "FY2027" in item["summary"]
            for item in accepted_read["supporting_evidence"]
        )
        expected_history = client.get(f"/v1/companies/{company['id']}/expected-return-history")
        assert expected_history.status_code == 200

        with Session(postgres_engine) as db:
            evidence_row = db.scalar(
                select(FinancialModelRevisionEvidence).where(
                    FinancialModelRevisionEvidence.revision_id == accepted_revision_id
                )
            )
            assert evidence_row is not None
            evidence_row.note = "attempted rewrite"
            with pytest.raises(ValueError, match="Historical observations are append-only"):
                db.flush()
            db.rollback()

        with Session(postgres_engine) as db, db.begin():
            replay_after_acceptance = run_sync_check(db, settings, reader)
            assert replay_after_acceptance.run.new_count == 0
            assert replay_after_acceptance.run.unchanged_count == 1

        stale = copy.deepcopy(export)
        stale["candidate_revision"]["source_revision_id"] = "sheet-rev-stale"
        stale["candidate_revision"]["effective_at"] = now.isoformat()
        stale["candidate_revision"]["rationale"] = "An edit from the original base revision."
        stale["proposal"] = proposal
        stale["supporting_evidence"] = changed["supporting_evidence"]
        stale["candidate_revision"]["scenarios"][1]["years"][0]["revenue_growth"] = "0.22"
        reader.blocks = [ContractBlock("publish-stale", "sheet-rev-stale", 3, json.dumps(stale))]
        with Session(postgres_engine) as db, db.begin():
            stale_check = run_sync_check(db, settings, reader)
            stale_id = stale_check.new_candidates[0].id
        with Session(postgres_engine) as db, db.begin():
            stale_preview = preview_sync_candidate(db, stale_id)
            assert stale_preview.status == "CONFLICT"
            assert "advanced" in (stale_preview.issue or "").lower()

        current_export = client.get(f"/v1/financial-models/{model['id']}/contract").json()
        wrong_listing = copy.deepcopy(current_export)
        wrong_listing["candidate_revision"]["source_revision_id"] = "sheet-wrong-listing"
        wrong_listing["candidate_revision"]["effective_at"] = now.isoformat()
        wrong_listing["candidate_revision"]["rationale"] = "Test exact listing validation."
        wrong_listing["proposal"] = proposal
        wrong_listing["supporting_evidence"] = changed["supporting_evidence"]
        wrong_listing["model"]["valuation_listing_id"] = str(UUID(int=12345))
        wrong_listing["candidate_revision"]["scenarios"][1]["years"][0]["revenue_growth"] = "0.221"
        reader.blocks = [
            ContractBlock(
                "publish-wrong-listing",
                "sheet-wrong-listing",
                4,
                json.dumps(wrong_listing),
            )
        ]
        with Session(postgres_engine) as db, db.begin():
            wrong_check = run_sync_check(db, settings, reader)
            wrong_listing_id = wrong_check.new_candidates[0].id
        with Session(postgres_engine) as db, db.begin():
            wrong_listing_preview = preview_sync_candidate(db, wrong_listing_id)
            assert wrong_listing_preview.status == "CONFLICT"
            assert "listing" in (wrong_listing_preview.issue or "").lower()

        with Session(postgres_engine) as db:
            accepted_candidate = db.get(GoogleSheetsSyncCandidate, candidate_id)
            accepted_revision = db.get(FinancialModelRevision, accepted_revision_id)
            assert accepted_candidate is not None and accepted_candidate.status == "ACCEPTED"
            assert accepted_revision is not None
            assert accepted_revision.source_revision_id == "sheet-rev-accepted"
            assert "docs.google.com/spreadsheets/d/" in (accepted_revision.source or "")
            history = db.scalars(
                select(FinancialModelRevision).where(
                    FinancialModelRevision.model_id == UUID(model["id"])
                )
            ).all()
            assert len(history) == 2
        with Session(postgres_engine) as db:
            accepted_candidate = db.get(GoogleSheetsSyncCandidate, candidate_id)
            assert accepted_candidate is not None
            accepted_candidate.decision_note = "attempted rewrite"
            with pytest.raises(
                ValueError, match="Final Google Sheets review decisions are immutable"
            ):
                db.flush()
            db.rollback()
        assert client.get(f"/v1/financial-models/{model['id']}/revisions").status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize(
    ("fixture_name", "method", "currency"),
    [
        (
            "w_tost_owner_cash_flow_v1.json",
            "owner-cash-flow",
            "USD",
        ),
        (
            "w_hdfc_residual_income_v1.json",
            "residual-income",
            "INR",
        ),
    ],
)
def test_additional_method_contract_is_reviewed_into_its_native_revision_table(
    postgres_engine: Engine,
    fixture_name: str,
    method: str,
    currency: str,
) -> None:
    fixture = cast(
        dict[str, Any], json.loads((ADDITIONAL_FIXTURES / fixture_name).read_text(encoding="utf-8"))
    )
    now = datetime.now(UTC)
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        company = client.post(
            "/v1/companies",
            json={"name": f"{fixture['model_key']} sync issuer", "reporting_currency": currency},
        ).json()
        security = client.post(
            f"/v1/companies/{company['id']}/securities",
            json={"name": f"{fixture['model_key']} common", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "SYNC-TEST", "ticker": fixture["model_key"], "currency": currency},
        ).json()
        research_revision_id, _ = _publish_research_evidence(
            client,
            company_id=company["id"],
            security_id=security["id"],
            observed_at=now,
            stream_key=f"{fixture['model_key'].lower()}-model-support",
        )
        initial_revision = {
            **copy.deepcopy(fixture["input"]),
            "base_revision_id": None,
            "source_revision_id": None,
            "actor": "LOCAL_USER",
            "source": "Fixture initial assumptions",
            "rationale": "Create a methodology fixture for external contract sync.",
            "effective_at": now.isoformat(),
        }
        created = client.post(
            f"/v1/companies/{company['id']}/canonical-financial-models/{method}",
            json={
                "model_name": f"{fixture['model_key']} sync model",
                "valuation_listing_id": listing["id"],
                "model_currency": currency,
                "source_model_key": fixture["model_key"],
                "initial_revision": initial_revision,
            },
        )
        assert created.status_code == 201, created.text
        model = created.json()
        contract = client.get(f"/v1/canonical-financial-models/{model['id']}/contract").json()
        assert contract["contract_version"] == "2.1.0"
        contract["proposal"] = {
            "author_id": "research-agent-fixture",
            "authored_at": now.isoformat(),
            "source_reference": "https://docs.google.com/spreadsheets/d/research-fixture/edit",
        }
        contract["supporting_evidence"] = [
            {
                "evidence_type": "RESEARCH_REVISION",
                "reference_id": research_revision_id,
                "relationship": "SUPPORTS",
                "note": "Published research context supporting the method-specific edit.",
            }
        ]
        contract["candidate_revision"]["source_revision_id"] = f"sheet-{method}-r2"
        contract["candidate_revision"]["effective_at"] = now.isoformat()
        contract["candidate_revision"]["rationale"] = (
            "Reviewed a method-specific assumption change."
        )
        if method == "owner-cash-flow":
            contract["candidate_revision"]["owner_cash_flow"]["scenarios"][1]["years"][0][
                "owner_cash_flow_margin"
            ] = "0.052"
        else:
            contract["candidate_revision"]["residual_income"]["scenarios"][1]["starting_roe"] = (
                "0.156"
            )
        reader = FakeReader(
            [
                ContractBlock(
                    f"publish-{method}",
                    f"sheet-{method}-r2",
                    2,
                    json.dumps(contract),
                )
            ]
        )
        settings = Settings(
            google_sheets_spreadsheet_id=SPREADSHEET_ID,
            google_sheets_sync_tab="Application Model Sync Inbox",
        )
        with Session(postgres_engine) as db, db.begin():
            check = run_sync_check(db, settings, reader)
            candidate_id = check.new_candidates[0].id
        with Session(postgres_engine) as db, db.begin():
            preview = preview_sync_candidate(db, candidate_id)
            assert preview.status == "READY"
            assert preview.preview_data is not None
            assert preview.preview_data["projection_changes"]
        with Session(postgres_engine) as db, db.begin():
            accepted = accept_sync_candidate(db, candidate_id, "Reviewer")
            assert accepted.status == "ACCEPTED"
            accepted_revision_id = accepted.accepted_revision_id
            assert accepted_revision_id is not None
            assert accepted.supporting_evidence[0].reference_id == UUID(research_revision_id)
        with Session(postgres_engine) as db:
            accepted_revision = db.get(FinancialModelRevision, accepted_revision_id)
            assert accepted_revision is not None
            assert accepted_revision.actor == "IMPORT"
            assert accepted_revision.source_revision_id == f"sheet-{method}-r2"
            assert accepted_revision.proposal_author_id == "research-agent-fixture"
            assert (
                db.scalar(
                    select(FinancialModelRevisionEvidence.id).where(
                        FinancialModelRevisionEvidence.revision_id == accepted_revision.id
                    )
                )
                is not None
            )
            assert (
                accepted_revision.model_type
                == {
                    "owner-cash-flow": "OWNER_CASH_FLOW_10Y",
                    "residual-income": "RESIDUAL_INCOME_10Y_FADE",
                }[method]
            )
