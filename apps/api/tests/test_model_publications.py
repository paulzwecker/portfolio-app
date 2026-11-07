"""Publication integrity, consistent capture and isolated native proposal round trips."""

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import dcf_fixture
from test_google_sheets_sync import (
    SPREADSHEET_ID,
    FakeHttpSession,
    FakeResponse,
    _publish_research_evidence,
)

from portfolio_api.domain.models import (
    FinancialModelRevision,
    GoogleSheetsSyncCandidate,
    GoogleSheetsSyncRun,
)
from portfolio_api.google_sheets_sync import (
    GoogleSheetsApiReader,
    GoogleSheetsSyncError,
    accept_sync_candidate,
    preview_sync_candidate,
    run_sync_check,
)
from portfolio_api.main import create_app
from portfolio_api.model_publications import FinancialModelPublicationV1
from portfolio_api.settings import Settings


def publication(contract: dict[str, object], outputs: Mapping[str, object]) -> dict[str, object]:
    raw = json.dumps(contract, ensure_ascii=False)
    return {
        "contract_type": "FinancialModelPublicationV1",
        "contract_version": "1.0.0",
        "state": "PUBLISHED",
        "published_at": datetime.now(UTC).isoformat(),
        "contract_json": raw,
        "contract_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "published_fair_values": {
            field: outputs[field] for field in ("bear_fv", "base_fv", "bull_fv", "weighted_fv")
        },
    }


def reader(settings: Settings, rows: Sequence[object]) -> GoogleSheetsApiReader:
    metadata: dict[str, object] = {
        "spreadsheetId": SPREADSHEET_ID,
        "properties": {"title": "Synthetic models"},
        "sheets": [{"properties": {"sheetId": 10, "title": settings.google_sheets_sync_tab}}],
    }
    return GoogleSheetsApiReader(
        settings,
        FakeHttpSession(
            [
                FakeResponse(metadata),
                FakeResponse(
                    {"range": "'Application Model Sync Inbox'!A2:E5001", "values": list(rows)}
                ),
                FakeResponse(
                    {"range": "'Application Model Sync Inbox'!A2:E5001", "values": list(rows)}
                ),
                FakeResponse(metadata),
            ]
        ),
    )


def test_publication_rejects_drafts_tampering_floats_and_unknown_fields() -> None:
    outputs = dict.fromkeys(("bear_fv", "base_fv", "bull_fv", "weighted_fv"), "1")
    item = publication({}, outputs)
    FinancialModelPublicationV1.model_validate(item)
    for changes in (
        {"state": "DRAFT"},
        {"contract_json": "changed"},
        {"auto_accept": True},
        {"published_fair_values": {**outputs, "weighted_fv": 1.2}},
        {"published_at": "2026-01-01"},
    ):
        with pytest.raises(ValidationError):
            FinancialModelPublicationV1.model_validate({**item, **changes})


@pytest.mark.parametrize("change", ["values", "metadata", "outage"])
def test_capture_fence_rejects_changes_and_failed_requests(tmp_path: Path, change: str) -> None:
    credential = tmp_path / "fixture.json"
    credential.write_text("synthetic")
    settings = Settings(
        google_sheets_spreadsheet_id=SPREADSHEET_ID, google_sheets_service_account_file=credential
    )
    client = reader(settings, [["publish-1", "revision-1", 1, 1, "{}"]])
    assert isinstance(client.session, FakeHttpSession)
    if change == "values":
        client.session.responses[2] = FakeResponse({"values": []})
    elif change == "metadata":
        client.session.responses[3] = FakeResponse({"spreadsheetId": "other"})
    else:
        client.session.responses[2] = FakeResponse({}, 503)
    with pytest.raises(GoogleSheetsSyncError):
        client.read_inbox(SPREADSHEET_ID, settings.google_sheets_sync_tab)


@pytest.mark.integration
def test_two_company_publications_use_one_capture_and_native_review_path(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    credential = tmp_path / "fixture.json"
    credential.write_text("synthetic")
    settings = Settings(
        google_sheets_spreadsheet_id=SPREADSHEET_ID, google_sheets_service_account_file=credential
    )
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        for ticker in ("SYNTHA", "SYNTHB"):
            company = client.post(
                "/v1/companies", json={"name": ticker, "reporting_currency": "USD"}
            ).json()
            security = client.post(
                f"/v1/companies/{company['id']}/securities",
                json={"name": ticker, "security_type": "COMMON_STOCK"},
            ).json()
            listing = client.post(
                f"/v1/securities/{security['id']}/listings",
                json={"venue": "NASDAQ", "ticker": ticker, "currency": "USD"},
            ).json()
            inputs = copy.deepcopy(dcf_fixture()["input"])
            if ticker == "SYNTHB":
                inputs["base"]["base_revenue"] = "175"
            inputs["effective_at"] = datetime.now(UTC).isoformat()
            response = client.post(
                f"/v1/companies/{company['id']}/financial-models",
                json={
                    "model_type": "UFCF_DCF_10Y_FADE",
                    "model_name": ticker,
                    "valuation_listing_id": listing["id"],
                    "model_currency": "USD",
                    "source_model_key": ticker,
                    "initial_revision": inputs,
                },
            )
            assert response.status_code == 201, response.text
            model = response.json()
            revision_id, _ = _publish_research_evidence(
                client,
                company_id=company["id"],
                security_id=security["id"],
                observed_at=datetime.now(UTC),
                stream_key=ticker,
            )
            contract = client.get(f"/v1/financial-models/{model['id']}/contract").json()
            contract["proposal"] = {
                "author_id": "synthetic-agent",
                "authored_at": datetime.now(UTC).isoformat(),
                "source_reference": "https://research.example.test/model",
            }
            contract["supporting_evidence"] = [
                {
                    "evidence_type": "RESEARCH_REVISION",
                    "reference_id": revision_id,
                    "relationship": "SUPPORTS",
                    "note": "Synthetic evidence",
                }
            ]
            contract["candidate_revision"]["source_revision_id"] = ticker + "-publication-r2"
            contract["candidate_revision"]["rationale"] = (
                "Synthetic evidence supports revised growth."
            )
            contract["candidate_revision"]["scenarios"][1]["years"][0]["revenue_growth"] = "0.21"
            proposed = client.post(
                f"/v1/financial-models/{model['id']}/contract/preview", json=contract
            )
            assert proposed.status_code == 200, proposed.text
            outputs = proposed.json()["calculated_outputs"]
            envelope = publication(contract, outputs)
            raw = json.dumps(envelope)
            # Same source protocol as the Apps Script. Deliberately cross chunk boundaries.
            chunks = [raw[offset : offset + 4000] for offset in range(0, len(raw), 4000)]
            rows = [
                [
                    ticker,
                    contract["candidate_revision"]["source_revision_id"],
                    i + 1,
                    len(chunks),
                    chunk,
                ]
                for i, chunk in enumerate(chunks)
            ]
            with Session(postgres_engine) as db, db.begin():
                captured = run_sync_check(db, settings, reader(settings, rows))
                candidate_id = captured.new_candidates[0].id
                assert captured.run.new_count == 1
                replayed = run_sync_check(db, settings, reader(settings, rows))
                assert replayed.run.unchanged_count == 1
                preview = preview_sync_candidate(db, candidate_id)
                assert preview.status == "READY", preview.issue
                assert preview.preview_data is not None
                parity = preview.preview_data["publication"]
                assert isinstance(parity, dict)
                assert parity["parity_status"] == "MATCH"
                assert (
                    db.scalar(
                        select(func.count())
                        .select_from(FinancialModelRevision)
                        .where(FinancialModelRevision.model_id == UUID(model["id"]))
                    )
                    == 1
                )
                # Tampered published output is captured as a different candidate and never promoted.
                bad_contract = copy.deepcopy(contract)
                bad_contract["candidate_revision"]["source_revision_id"] += "-bad"
                bad = publication(bad_contract, {**outputs, "weighted_fv": "1"})
                bad_rows = [
                    [
                        ticker + "-bad",
                        bad_contract["candidate_revision"]["source_revision_id"],
                        1,
                        1,
                        json.dumps(bad),
                    ]
                ]
                failed = run_sync_check(db, settings, reader(settings, bad_rows))
                bad_id = failed.new_candidates[0].id
                assert preview_sync_candidate(db, bad_id).status == "INVALID"
                assert accept_sync_candidate(db, bad_id, "synthetic-reviewer").status == "INVALID"
                accepted = accept_sync_candidate(
                    db, candidate_id, "synthetic-reviewer", "Reviewed synthetic fixture"
                )
                assert accepted.status == "ACCEPTED"
                assert (
                    accept_sync_candidate(
                        db, candidate_id, "synthetic-reviewer"
                    ).accepted_revision_id
                    == accepted.accepted_revision_id
                )
                assert (
                    db.scalar(
                        select(func.count())
                        .select_from(FinancialModelRevision)
                        .where(FinancialModelRevision.model_id == UUID(model["id"]))
                    )
                    == 2
                )
                collision = copy.deepcopy(envelope)
                collision_values = collision["published_fair_values"]
                assert isinstance(collision_values, dict)
                collision_values["weighted_fv"] = "2"
                collision_rows = [
                    [
                        ticker + "-collision",
                        contract["candidate_revision"]["source_revision_id"],
                        1,
                        1,
                        json.dumps(collision),
                    ]
                ]
                collision_check = run_sync_check(db, settings, reader(settings, collision_rows))
                collision_id = collision_check.new_candidates[0].id
                assert collision_check.new_candidates[0].status == "CONFLICT"
                assert preview_sync_candidate(db, collision_id).status == "CONFLICT"
                assert accept_sync_candidate(db, collision_id, "reviewer").status == "CONFLICT"
                wrong_contract = copy.deepcopy(contract)
                wrong_contract["candidate_revision"]["source_revision_id"] += "-identity"
                wrong = publication(wrong_contract, outputs)
                wrong_rows = [[ticker + "-identity", "wrong-identity", 1, 1, json.dumps(wrong)]]
                wrong_check = run_sync_check(db, settings, reader(settings, wrong_rows))
                wrong_id = wrong_check.new_candidates[0].id
                assert preview_sync_candidate(db, wrong_id).status == "INVALID"
                assert accept_sync_candidate(db, wrong_id, "reviewer").status == "INVALID"
                failing_reader = reader(settings, [])
                assert isinstance(failing_reader.session, FakeHttpSession)
                failing_reader.session.responses[2] = FakeResponse({}, 503)
                failure = run_sync_check(db, settings, failing_reader)
                assert failure.run.status == "FAILED"
                assert failure.new_candidates == []
                assert failure.run.error_code == "GOOGLE_API_ERROR"
                retained = db.get(GoogleSheetsSyncCandidate, candidate_id)
                assert retained is not None and retained.status == "ACCEPTED"
                rollback_contract = copy.deepcopy(contract)
                rollback_contract["candidate_revision"]["source_revision_id"] += "-rollback"
                rollback_rows = [
                    [
                        ticker + "-rollback",
                        rollback_contract["candidate_revision"]["source_revision_id"],
                        1,
                        1,
                        json.dumps(publication(rollback_contract, outputs)),
                    ]
                ]
                savepoint = db.begin_nested()
                rolled = run_sync_check(db, settings, reader(settings, rollback_rows))
                rolled_id = rolled.new_candidates[0].id
                savepoint.rollback()
                assert db.get(GoogleSheetsSyncCandidate, rolled_id) is None
                stored = db.get(GoogleSheetsSyncCandidate, candidate_id)
                assert stored is not None
                assert (
                    json.loads(stored.contract_text)["contract_sha256"]
                    == envelope["contract_sha256"]
                )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"error": "malformed"},
        {"range": "Other!A2:E5001"},
        {"range": "'Application Model Sync Inbox'!A2:E5001", "values": None},
    ],
)
def test_missing_or_malformed_value_range_fails_closed(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    credential = tmp_path / "fixture.json"
    credential.write_text("synthetic")
    settings = Settings(
        google_sheets_spreadsheet_id=SPREADSHEET_ID, google_sheets_service_account_file=credential
    )
    client = reader(settings, [])
    assert isinstance(client.session, FakeHttpSession)
    client.session.responses[1] = FakeResponse(payload)
    client.session.responses[2] = FakeResponse(payload)
    with pytest.raises(GoogleSheetsSyncError):
        client.read_inbox(SPREADSHEET_ID, settings.google_sheets_sync_tab)


def test_valid_empty_value_range_is_an_empty_inbox(tmp_path: Path) -> None:
    credential = tmp_path / "fixture.json"
    credential.write_text("synthetic")
    settings = Settings(
        google_sheets_spreadsheet_id=SPREADSHEET_ID, google_sheets_service_account_file=credential
    )
    client = reader(settings, [])
    assert isinstance(client.session, FakeHttpSession)
    empty: dict[str, object] = {"range": "'Application Model Sync Inbox'!A2:E5001"}
    client.session.responses[1] = FakeResponse(empty)
    client.session.responses[2] = FakeResponse(empty)
    assert client.read_inbox(SPREADSHEET_ID, settings.google_sheets_sync_tab).blocks == []


@pytest.mark.integration
def test_concurrent_discovery_is_bounded_and_records_blocked_run(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    credential = tmp_path / "fixture.json"
    credential.write_text("synthetic")
    settings = Settings(
        google_sheets_spreadsheet_id=SPREADSHEET_ID, google_sheets_service_account_file=credential
    )
    with Session(postgres_engine) as first, first.begin():
        assert run_sync_check(first, settings, reader(settings, [])).run.status == "SUCCEEDED"
        with Session(postgres_engine) as second, second.begin():
            blocked_reader = reader(settings, [])
            blocked = run_sync_check(second, settings, blocked_reader)
            assert blocked.run.status == "BLOCKED"
            assert blocked.run.error_code == "SYNC_IN_PROGRESS"
            assert isinstance(blocked_reader.session, FakeHttpSession)
            assert blocked_reader.session.requests == []
    with Session(postgres_engine) as retried, retried.begin():
        saved = retried.get(GoogleSheetsSyncRun, blocked.run.id)
        assert saved is not None and saved.error_code == "SYNC_IN_PROGRESS"
        assert run_sync_check(retried, settings, reader(settings, [])).run.status == "SUCCEEDED"
