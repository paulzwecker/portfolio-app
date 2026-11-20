"""The Sheets observation inbox feeds the existing reviewable proposal contract."""

import copy
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api import company_observation_proposals as proposals
from portfolio_api.company_observations import CompanyGuidanceObservation, CompanyMetricObservation
from portfolio_api.domain.models import Company
from portfolio_api.domain.services import DomainError
from portfolio_api.google_sheets_sync import (
    ConnectionResult,
    ContractBlock,
    GoogleSheetsSyncError,
    InboxSnapshot,
    assemble_contract_blocks,
)
from portfolio_api.main import create_app
from portfolio_api.observation_sheet_sync import (
    OBSERVATION_INBOX_TAB,
    check_observation_inbox,
    parse_observation_block,
)
from portfolio_api.settings import Settings

SPREADSHEET_ID = "s" * 24
SOURCE = "https://example.com/synthetic-q3-earnings"


def _settings(*, enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        app_env="development",
        google_sheets_spreadsheet_id=SPREADSHEET_ID,
        observation_proposals_enabled=True,
        observation_sheets_inbox_enabled=enabled,
    )


def _payload(company_id: UUID, domain: str) -> dict[str, Any]:
    common: dict[str, Any] = {
        "contract_type": domain,
        "contract_version": "1.0.0",
        "company_id": str(company_id),
        "external_batch_id": "sheet-" + domain.lower(),
        "authored_at": datetime.now(UTC).isoformat(),
        "rationale": "Cited company source for operator-reviewable observation.",
    }
    if domain == "MetricDefinitionBatchV1":
        common["items"] = [
            {
                "metric_key": "synthetic.trips",
                "display_name": "Trips",
                "category": "OPERATING",
                "value_kind": "COUNT",
                "canonical_unit": "trips",
                "canonical_scale": "1000000",
                "currency_policy": "NONE",
                "aggregation_semantics": "PERIOD_FLOW",
                "default_period_type": "QUARTER",
                "default_basis": "REPORTED",
                "scope_dimensions": [],
                "actuals_allowed": True,
                "guidance_allowed": True,
                "description": "Synthetic quarterly trip count in millions.",
                "source_reference": SOURCE,
            }
        ]
    elif domain == "KPIObservationBatchV1":
        common["items"] = [
            {
                "external_observation_id": "synthetic-trips-q3",
                "metric_key": "synthetic.trips",
                "period_type": "QUARTER",
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "fiscal_year": 2026,
                "fiscal_quarter": 3,
                "value": "4061",
                "unit": "trips",
                "scale": "1000000",
                "basis": "REPORTED",
                "source_type": "EARNINGS_RELEASE",
                "source_reference": SOURCE,
                "reported_at": None,
            }
        ]
    else:
        assert domain == "GuidanceObservationBatchV1"
        common["items"] = [
            {
                "external_guidance_id": "synthetic-trips-q4-guidance",
                "metric_key": "synthetic.trips",
                "period_type": "QUARTER",
                "period_start": "2026-10-01",
                "period_end": "2026-12-31",
                "fiscal_year": 2026,
                "fiscal_quarter": 4,
                "lower_value": "4200",
                "upper_value": "4500",
                "value_qualifier": "RANGE",
                "unit": "trips",
                "scale": "1000000",
                "basis": "COMPANY_GUIDANCE",
                "source_type": "EARNINGS_RELEASE",
                "source_reference": SOURCE,
                "issued_at": None,
            }
        ]
    return common


def _block(payload: dict[str, Any], row: int) -> ContractBlock:
    text = json.dumps(payload, sort_keys=True)
    return ContractBlock(
        publish_id=f"publish-row-{row}",
        external_revision_id=payload["external_batch_id"],
        first_row_number=row,
        contract_text=text,
    )


class FixtureReader:
    def __init__(self, blocks: list[ContractBlock], *, available: bool = True) -> None:
        self.blocks = blocks
        self.available = available
        self.calls = 0

    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult:
        assert spreadsheet_id == SPREADSHEET_ID
        assert sync_tab == OBSERVATION_INBOX_TAB
        return ConnectionResult("Synthetic read-only workbook", True, 42)

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        self.calls += 1
        if not self.available:
            raise GoogleSheetsSyncError("NETWORK_ERROR", "Synthetic source failure")
        return InboxSnapshot(self.test_connection(spreadsheet_id, sync_tab), self.blocks)


def test_chunked_observation_contract_and_strict_decimal_validation() -> None:
    payload = _payload(uuid4(), "KPIObservationBatchV1")
    encoded = json.dumps(payload, sort_keys=True)
    midpoint = len(encoded) // 2
    values: list[object] = [
        ["publish-1", payload["external_batch_id"], "2", "2", encoded[midpoint:]],
        ["publish-1", payload["external_batch_id"], "1", "2", encoded[:midpoint]],
    ]
    blocks = assemble_contract_blocks(values)
    assert len(blocks) == 1
    parsed = parse_observation_block(blocks[0])
    assert isinstance(parsed, proposals.KPIObservationBatchV1)
    assert parsed.items[0].value == 4061
    bad = copy.deepcopy(payload)
    bad["items"][0]["value"] = 4061.5
    with pytest.raises(ValueError, match="Typed observation contract invalid"):
        parse_observation_block(_block(bad, 10))
    mismatch = _block(payload, 12)
    mismatch = ContractBlock(mismatch.publish_id, "different-batch", 12, mismatch.contract_text)
    with pytest.raises(ValueError, match="external batch ID"):
        parse_observation_block(mismatch)
    with pytest.raises(ValueError, match="sequence"):
        parse_observation_block(
            assemble_contract_blocks([["broken", "id", "2", "2", "incomplete"]])[0]
        )


def test_sync_disabled_by_default_and_requires_canonical_proposal_gate() -> None:
    with pytest.raises(ValidationError, match="requires observation proposals"):
        Settings(_env_file=None, observation_sheets_inbox_enabled=True)
    with pytest.raises(DomainError, match="disabled"):
        check_observation_inbox(Session(), _settings(enabled=False), FixtureReader([]))


@pytest.mark.integration
def test_sheet_candidates_are_identical_to_api_review_flow(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Synthetic Sheets issuer", reporting_currency="USD")
        session.add(company)
        session.flush()
        cid = company.id

    domains = ["MetricDefinitionBatchV1", "KPIObservationBatchV1", "GuidanceObservationBatchV1"]
    blocks = [_block(_payload(cid, name), 2 + index) for index, name in enumerate(domains)]
    fixture = FixtureReader(blocks)
    settings = _settings()
    with Session(postgres_engine) as session, session.begin():
        scanned = check_observation_inbox(session, settings, fixture)
        assert scanned.status == "SUCCEEDED"
        assert scanned.checked_count == scanned.created_count == 3
        assert len(scanned.created_proposal_ids) == 3
        assert session.scalar(select(func.count()).select_from(CompanyMetricObservation)) == 0
        assert session.scalar(select(func.count()).select_from(CompanyGuidanceObservation)) == 0

        # Definition must be accepted by a human before observation preview.
        first = proposals.preview(session, scanned.created_proposal_ids[0])
        assert first.status == "READY"
        assert first.preview_fingerprint is not None
        proposals.accept(
            session,
            first.proposal_id,
            proposals.ObservationProposalDecisionRequest(
                preview_fingerprint=first.preview_fingerprint,
                decision_note="Reviewed the synthetic metric semantics and source.",
            ),
            reviewer_id="synthetic-human-reviewer",
        )
        for proposal_id in scanned.created_proposal_ids[1:]:
            preview = proposals.preview(session, proposal_id)
            assert preview.status == "READY"
            assert preview.preview_fingerprint is not None
            outcome = proposals.accept(
                session,
                proposal_id,
                proposals.ObservationProposalDecisionRequest(
                    preview_fingerprint=preview.preview_fingerprint,
                    decision_note="Verified the source, unit and reporting period.",
                ),
                reviewer_id="synthetic-human-reviewer",
            )
            assert outcome.status == "ACCEPTED"
        assert session.scalar(select(func.count()).select_from(CompanyMetricObservation)) == 1
        assert session.scalar(select(func.count()).select_from(CompanyGuidanceObservation)) == 1
        replay = check_observation_inbox(session, settings, fixture)
        assert replay.status == "SUCCEEDED"
        assert replay.created_count == 0
        assert replay.replayed_count == 3
        assert replay.created_proposal_ids == []
        assert len(proposals.list_proposals(session, company_id=cid)) == 3


@pytest.mark.integration
def test_invalid_and_conflicting_sheet_rows_do_not_block_other_batches(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Synthetic partial scan issuer")
        session.add(company)
        session.flush()
        cid = company.id

    definition = _payload(cid, "MetricDefinitionBatchV1")
    changed = copy.deepcopy(definition)
    changed["items"][0]["description"] = "Different definition with same external batch ID."
    invalid = ContractBlock("bad-json", "bad", 6, "not-json")
    mismatched = ContractBlock("wrong-id", "other", 8, json.dumps(definition))
    fixture = FixtureReader([_block(definition, 2), _block(changed, 4), invalid, mismatched])
    with Session(postgres_engine) as session, session.begin():
        scanned = check_observation_inbox(session, _settings(), fixture)
        assert scanned.status == "PARTIAL"
        assert scanned.checked_count == 4
        assert scanned.created_count == 1
        assert scanned.replayed_count == 0
        assert len(scanned.issues) == 3
        assert {item.code for item in scanned.issues} == {"CONFLICT", "INVALID"}
        assert len(proposals.list_proposals(session, company_id=cid)) == 1
        assert session.scalar(select(func.count()).select_from(CompanyMetricObservation)) == 0


@pytest.mark.integration
def test_failed_sheet_read_and_oversized_inbox_produce_no_proposals(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Synthetic Sheets outage issuer")
        session.add(company)
        session.flush()
        cid = company.id

    with Session(postgres_engine) as session, session.begin():
        failed = check_observation_inbox(session, _settings(), FixtureReader([], available=False))
        assert failed.status == "SOURCE_UNAVAILABLE"
        assert failed.source_error_code == "NETWORK_ERROR"
        assert failed.created_count == 0

        payload = _payload(cid, "MetricDefinitionBatchV1")
        too_many = FixtureReader([_block(payload, i + 2) for i in range(101)])
        with pytest.raises(DomainError, match="100-contract"):
            check_observation_inbox(session, _settings(), too_many)
        assert len(proposals.list_proposals(session, company_id=cid)) == 0


@pytest.mark.integration
def test_operator_trigger_endpoint_is_protected_and_uses_same_service(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Synthetic Sheets HTTP issuer")
        session.add(company)
        session.flush()
        cid = company.id
    reader = FixtureReader([_block(_payload(cid, "KPIObservationBatchV1"), 2)])
    settings = _settings()
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        patch(
            "portfolio_api.observation_sheet_sync.GoogleSheetsApiReader",
            return_value=reader,
        ),
        TestClient(create_app(settings)) as client,
    ):
        result = client.post("/v1/google-sheets-observation-sync/check")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["created_count"] == 1
        assert len(body["created_proposal_ids"]) == 1
        assert reader.calls == 1
        replay = client.post("/v1/google-sheets-observation-sync/check")
        assert replay.status_code == 200
        assert replay.json()["replayed_count"] == 1

    with Session(postgres_engine) as session:
        rows = proposals.list_proposals(session, company_id=cid)
        assert len(rows) == 1
        assert rows[0].status == "PENDING"


def test_observation_sheet_check_requires_broad_proxy_auth_in_preview() -> None:
    settings = Settings(
        _env_file=None,
        app_env="preview",
        database_url=SecretStr(
            "postgresql+psycopg://test:test@192.0.2.1:5432/preview?sslmode=verify-full"
        ),
        api_access_token=SecretStr("operator-proxy-test-token-000000000000000000"),
        observation_proposals_enabled=True,
        observation_sheets_inbox_enabled=True,
        data_universe_read_enabled=True,
        data_universe_read_token=SecretStr("data-only-synthetic-token-00000000000000000"),
        data_universe_read_company_ids=str(uuid4()),
        google_sheets_spreadsheet_id=SPREADSHEET_ID,
    )
    with (
        patch("portfolio_api.main.create_database_engine", return_value=None),
        TestClient(create_app(settings)) as client,
    ):
        path = "/v1/google-sheets-observation-sync/check"
        assert client.post(path).status_code == 401
        assert (
            client.post(
                path,
                headers={
                    "X-Data-Universe-Read-Token": "data-only-synthetic-token-00000000000000000"
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                path,
                headers={"X-API-ACCESS-TOKEN": "operator-proxy-test-token-000000000000000000"},
            ).status_code
            == 503
        )


@pytest.mark.integration
def test_production_target_requires_separate_owner_write_authorization(
    postgres_engine: Engine,
) -> None:
    settings = _settings()
    settings.database_target_environment = "production"
    with (
        Session(postgres_engine) as session,
        session.begin(),
        pytest.raises(DomainError, match="owner authorization"),
    ):
        check_observation_inbox(session, settings, FixtureReader([]))
