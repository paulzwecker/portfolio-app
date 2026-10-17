"""Google Sheets research/thesis transport preserves canonical revision semantics."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    GoogleSheetsResearchSyncCandidate,
    InvestmentThesisRevision,
    ResearchRevision,
)
from portfolio_api.google_sheets_sync import (
    ConnectionResult,
    ContractBlock,
    GoogleSheetsSyncError,
    InboxSnapshot,
)
from portfolio_api.main import create_app
from portfolio_api.research_sheet_sync import (
    RESEARCH_SYNC_TAB,
    THESIS_SYNC_TAB,
    accept_research_candidate,
    check_research_sync_connection,
    preview_research_candidate,
    run_research_sync_check,
)
from portfolio_api.settings import Settings

SPREADSHEET_ID = "r" * 24


class FixtureReader:
    def __init__(self, blocks: dict[str, list[ContractBlock]]) -> None:
        self.blocks = blocks

    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult:
        assert spreadsheet_id == SPREADSHEET_ID
        assert sync_tab in {RESEARCH_SYNC_TAB, THESIS_SYNC_TAB}
        return ConnectionResult(
            "Research workbook fixture",
            sync_tab in self.blocks,
            42 if sync_tab == RESEARCH_SYNC_TAB else 43,
        )

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        assert spreadsheet_id == SPREADSHEET_ID
        if sync_tab not in self.blocks:
            raise GoogleSheetsSyncError("SYNC_TAB_MISSING", f"Missing {sync_tab}")
        connection = self.test_connection(spreadsheet_id, sync_tab)
        return InboxSnapshot(connection, self.blocks[sync_tab])


class UnavailableReader:
    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult:
        raise GoogleSheetsSyncError("NETWORK_ERROR", "fixture API unavailable")

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        raise GoogleSheetsSyncError("NETWORK_ERROR", "fixture API unavailable")


def research_contract(company_id: UUID, **changes: Any) -> s.ResearchRevisionPublishContract:
    payload: dict[str, Any] = {
        "contract_type": "ResearchRevisionContractV1",
        "contract_version": "1.0.0",
        "company_id": str(company_id),
        "security_id": None,
        "stream_key": "agent/revenue-outlook",
        "external_revision_id": "research-r1",
        "supersedes_revision_id": None,
        "author_id": "research-agent",
        "source_id": "google-sheets",
        "source_reference": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=42",
        "observed_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "status": "PUBLISHED",
        "rationale": "A source-linked outlook reflects the latest disclosed demand trend.",
        "forecasts": [
            {
                "metric": "REVENUE",
                "period_type": "ANNUAL",
                "fiscal_year": 2027,
                "fiscal_period": "FY",
                "value": "125.0",
                "currency": "USD",
                "unit": "currency",
                "availability_status": "AVAILABLE",
                "confidence": "MEDIUM",
            }
        ],
        "assessments": [],
        "evidence": [
            {
                "source_name": "Issuer earnings release",
                "external_identifier": "earnings-release-2026-q3",
                "source_url": "https://issuer.example.test/earnings-q3",
                "published_at": "2026-10-10",
                "note": "The source describes the current demand environment.",
            }
        ],
    }
    payload.update(changes)
    return s.ResearchRevisionPublishContract.model_validate(payload)


def thesis_contract(company_id: UUID, **changes: Any) -> s.InvestmentThesisRevisionPublishContract:
    payload: dict[str, Any] = {
        "contract_type": "InvestmentThesisContractV1",
        "contract_version": "1.0.0",
        "company_id": str(company_id),
        "security_id": None,
        "stream_key": "investment-thesis",
        "external_revision_id": "thesis-r1",
        "supersedes_revision_id": None,
        "author_id": "research-agent",
        "source_id": "google-sheets",
        "source_reference": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=43",
        "observed_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "status": "PUBLISHED",
        "thesis_statement": "Recurring demand may support durable business economics.",
        "confidence": "MEDIUM",
        "rationale": "The claim is supported by company primary-source material.",
        "claims": [
            {
                "claim_key": "renewal-economics",
                "claim_type": "COMPETITIVE_ADVANTAGE",
                "status": "ACTIVE",
                "statement": "Renewals may reinforce customer switching costs.",
                "confidence": "MEDIUM",
                "evidence": [
                    {
                        "relationship": "SUPPORTS",
                        "source_name": "Issuer annual report",
                        "external_identifier": "annual-report-2025",
                        "source_url": "https://issuer.example.test/annual-report",
                        "published_at": "2026-02-20",
                    }
                ],
            }
        ],
    }
    payload.update(changes)
    return s.InvestmentThesisRevisionPublishContract.model_validate(payload)


def test_trigger_linked_thesis_contract_requires_independent_https_source_evidence() -> None:
    payload = thesis_contract(uuid4()).model_dump(mode="json")
    payload["contract_version"] = "1.1.0"
    payload["trigger_references"] = [
        {
            "trigger_id": str(uuid4()),
            "classification": "MAJOR-STRUCTURAL",
            "classification_rationale": "A material event is being reviewed.",
        }
    ]
    accepted = s.InvestmentThesisRevisionPublishContract.model_validate(payload)
    assert accepted.trigger_references[0].classification == "MAJOR-STRUCTURAL"

    duplicate = json.loads(json.dumps(payload))
    duplicate["trigger_references"].append(duplicate["trigger_references"][0])
    with pytest.raises(ValueError, match="repeat a trigger reference"):
        s.InvestmentThesisRevisionPublishContract.model_validate(duplicate)

    no_source = dict(payload)
    no_source["source_reference"] = "http://example.test/sheet"
    with pytest.raises(ValueError, match="HTTPS source reference"):
        s.InvestmentThesisRevisionPublishContract.model_validate(no_source)

    no_evidence = json.loads(json.dumps(payload))
    no_evidence["claims"][0]["evidence"] = []
    with pytest.raises(ValueError, match="source evidence on a claim"):
        s.InvestmentThesisRevisionPublishContract.model_validate(no_evidence)


def block(value: Any, row: int, *, raw: str | None = None) -> ContractBlock:
    return ContractBlock(
        publish_id=f"publish-{row}",
        external_revision_id=value.external_revision_id,
        first_row_number=row,
        contract_text=raw or value.model_dump_json(),
    )


def reader_for(research: list[ContractBlock], thesis: list[ContractBlock]) -> FixtureReader:
    return FixtureReader({RESEARCH_SYNC_TAB: research, THESIS_SYNC_TAB: thesis})


@pytest.mark.integration
def test_sheets_research_and_thesis_multiple_candidates_review_and_replay(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(
            name="Sheets research test issuer", reporting_currency="USD", is_demo=False
        )
        session.add(company)
        session.flush()
        research = research_contract(company.id)
        thesis = thesis_contract(company.id)
        settings = Settings(google_sheets_spreadsheet_id=SPREADSHEET_ID)
        fixture = reader_for([block(research, 2)], [block(thesis, 2)])

        connection = check_research_sync_connection(settings, fixture)
        assert connection.connected
        assert connection.research_inbox_exists and connection.thesis_inbox_exists

        checked = run_research_sync_check(session, settings, fixture)
        assert checked.run.status == "SUCCEEDED"
        assert len(checked.new_candidates) == 2
        candidates = {row.domain: row for row in checked.new_candidates}
        forecast_candidate = preview_research_candidate(session, candidates["RESEARCH"].id)
        thesis_candidate = preview_research_candidate(session, candidates["THESIS"].id)
        assert forecast_candidate.status == thesis_candidate.status == "READY"
        assert forecast_candidate.preview_data is not None
        assert forecast_candidate.preview_data["candidate_revision_number"] == 1
        assert thesis_candidate.preview_data is not None
        assert thesis_candidate.preview_data["claim_count"] == 1
        assert session.scalar(select(func.count()).select_from(ResearchRevision)) == 0
        assert session.scalar(select(func.count()).select_from(InvestmentThesisRevision)) == 0

        accepted_forecast = accept_research_candidate(
            session, forecast_candidate.id, "reviewer@example.test", "Reviewed forecast and source."
        )
        accepted_thesis = accept_research_candidate(
            session,
            thesis_candidate.id,
            "reviewer@example.test",
            "Reviewed claim and cited report.",
        )
        assert accepted_forecast.status == accepted_thesis.status == "ACCEPTED"
        assert accepted_forecast.accepted_research_revision_id is not None
        assert accepted_thesis.accepted_thesis_revision_id is not None
        assert accepted_forecast.reviewer_note == "Reviewed forecast and source."

        replay = run_research_sync_check(session, settings, fixture)
        assert replay.run.unchanged_count == 2
        assert replay.new_candidates == []
        assert session.scalar(select(func.count()).select_from(ResearchRevision)) == 1
        assert session.scalar(select(func.count()).select_from(InvestmentThesisRevision)) == 1
        all_candidates = session.scalars(select(GoogleSheetsResearchSyncCandidate)).all()
        assert len(all_candidates) == 2
        assert {row.status for row in all_candidates} == {"ACCEPTED"}


@pytest.mark.integration
def test_stale_base_reused_revision_and_invalid_contracts_remain_visible(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Sheets conflict test issuer", is_demo=False)
        session.add(company)
        session.flush()
        first = research_contract(
            company.id, observed_at=(datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        )
        settings = Settings(google_sheets_spreadsheet_id=SPREADSHEET_ID)
        first_reader = reader_for([block(first, 2)], [])
        candidate = run_research_sync_check(session, settings, first_reader).new_candidates[0]
        ready = preview_research_candidate(session, candidate.id)
        assert ready.status == "READY"
        accepted = accept_research_candidate(
            session, ready.id, "reviewer", "Accept first revision."
        )
        assert accepted.status == "ACCEPTED"

        stale = research_contract(
            company.id,
            external_revision_id="research-r2-stale",
            observed_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        )
        changed_replay = first.model_copy(
            update={"rationale": "Changed payload reuses the first external ID."}
        )
        missing_evidence = research_contract(
            company.id,
            external_revision_id="research-no-evidence",
            evidence=[],
        )
        unsupported_raw = first.model_dump(mode="json")
        unsupported_raw["contract_version"] = "9.9.9"
        unsupported_raw["external_revision_id"] = "research-unsupported"
        unsupported_text = json.dumps(unsupported_raw)
        wrong_identity = research_contract(uuid4(), external_revision_id="research-unknown-company")
        fixture = reader_for(
            [
                block(stale, 3),
                block(changed_replay, 4),
                block(missing_evidence, 5),
                ContractBlock("publish-6", "research-unsupported", 6, unsupported_text),
                block(wrong_identity, 7),
            ],
            [],
        )
        checked = run_research_sync_check(session, settings, fixture)
        rows = {row.external_revision_id: row for row in checked.new_candidates}
        assert rows["research-r2-stale"].status == "PENDING"
        assert rows["research-r1"].status == "CONFLICT"
        assert rows["research-no-evidence"].status == "INVALID"
        assert rows["research-unsupported"].status == "INVALID"
        assert rows["research-unsupported"].contract_version == "9.9.9"

        stale_preview = preview_research_candidate(session, rows["research-r2-stale"].id)
        assert stale_preview.status == "CONFLICT"
        assert "stream changed" in (stale_preview.issue or "")
        identity_preview = preview_research_candidate(session, rows["research-unknown-company"].id)
        assert identity_preview.status == "INVALID"
        assert "identity was not found" in (identity_preview.issue or "")
        assert session.scalar(select(func.count()).select_from(ResearchRevision)) == 1


@pytest.mark.integration
def test_sheets_research_api_unavailability_is_persisted(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        result = run_research_sync_check(
            session,
            Settings(google_sheets_spreadsheet_id=SPREADSHEET_ID),
            UnavailableReader(),
        )
        assert result.run.status == "FAILED"
        assert result.run.error_code == "NETWORK_ERROR"
        assert "fixture API unavailable" in (result.run.error_message or "")


@pytest.mark.integration
def test_sheets_research_api_review_end_to_end(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Sheets API roundtrip issuer", is_demo=False)
        session.add(company)
        session.flush()
        value = thesis_contract(company.id)

    fixture = reader_for([], [block(value, 2)])
    sync_settings = Settings(google_sheets_spreadsheet_id=SPREADSHEET_ID)
    app_settings = Settings(database_url=None)
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        patch("portfolio_api.domain.routes.Settings", return_value=sync_settings),
        patch("portfolio_api.research_sheet_sync.GoogleSheetsApiReader", return_value=fixture),
        TestClient(create_app(app_settings)) as client,
    ):
        check = client.post("/v1/google-sheets-research-sync/check")
        assert check.status_code == 200
        check_data = check.json()
        assert check_data["run"]["status"] == "SUCCEEDED"
        candidate_id = check_data["new_candidates"][0]["id"]
        preview = client.post(
            f"/v1/google-sheets-research-sync/candidates/{candidate_id}/preview", json={}
        )
        assert preview.status_code == 200
        assert preview.json()["status"] == "READY"
        accepted = client.post(
            f"/v1/google-sheets-research-sync/candidates/{candidate_id}/accept",
            json={"reviewer": "reviewer@example.test", "reviewer_note": "API review complete."},
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "ACCEPTED"
        canonical_id = accepted.json()["accepted_thesis_revision_id"]
        assert UUID(canonical_id)
        candidates = client.get("/v1/google-sheets-research-sync/candidates?limit=10")
        assert candidates.status_code == 200
        assert candidates.json()[0]["reviewer_note"] == "API review complete."
        runs = client.get("/v1/google-sheets-research-sync/runs?limit=10")
        assert runs.status_code == 200
        assert runs.json()[0]["status"] == "SUCCEEDED"
