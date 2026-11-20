"""Public issuer evidence → agent shadow → reviewer → accepted scoped context.

All database mutations are confined to the isolated PostgreSQL test fixture.
The actual values and periods are publicly disclosed; identities and review
credentials in this test are synthetic, never the owner's canonical holdings.
"""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.data_universe_proposal_handoff import prepare_handoff
from portfolio_api.data_universe_public_evidence import verify_uber_q3_2026_pack
from portfolio_api.data_universe_shadow import EvidencePackV1, compare_source_pack
from portfolio_api.domain.models import Company, Listing, Security
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

pytestmark = pytest.mark.integration

AGENT_TOKEN = "synthetic-issuer-agent-token-00000000000000000"
REVIEWER_TOKEN = "synthetic-issuer-reviewer-token-00000000000000"
READ_TOKEN = "synthetic-issuer-scoped-read-token-00000000000"
HERE = Path(__file__).parent


def test_public_issuer_shadow_proposals_complete_a_reviewed_company_loop(
    postgres_engine: Engine,
) -> None:
    company_id, security_id, listing_id = uuid4(), uuid4(), uuid4()
    source_file = HERE / "fixtures" / "data_universe_uber_q3_2026.json"
    html_file = HERE / "fixtures" / "data_universe_uber_q3_2026_excerpt.html"
    pack = EvidencePackV1.model_validate(json.loads(source_file.read_text(encoding="utf-8")))
    verified = verify_uber_q3_2026_pack(pack, html_file.read_bytes())
    assert verified["status"] == "SOURCE_MATCHED"

    # Make the issuer identity explicit; never infer a ticker-to-company mapping.
    with Session(postgres_engine) as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Uber isolated public-source review",
                reporting_currency="USD",
                is_demo=True,
            )
        )
        session.flush()  # Preserve Company → Security FK order without ORM relationships.
        session.add(
            Security(
                id=security_id,
                company_id=company_id,
                name="Uber common stock (isolated)",
                security_type="COMMON_STOCK",
                is_demo=True,
            )
        )
        session.flush()  # Listing refers to an existing security.
        session.add(
            Listing(
                id=listing_id,
                security_id=security_id,
                ticker="UBER",
                venue="NYSE",
                currency="USD",
                is_demo=True,
            )
        )

    settings = Settings(
        _env_file=None,
        app_env="development",
        data_universe_read_enabled=True,
        data_universe_read_token=SecretStr(READ_TOKEN),
        data_universe_read_company_ids=str(company_id),
        observation_proposals_enabled=True,
        observation_acceptance_enabled=True,
        observation_proposal_agent_token=SecretStr(AGENT_TOKEN),
        observation_proposal_agent_id="synthetic-issuer-agent",
        observation_proposal_reviewer_token=SecretStr(REVIEWER_TOKEN),
        observation_proposal_reviewer_id="synthetic-issuer-human-reviewer",
    )
    read_headers = {"X-Data-Universe-Read-Token": READ_TOKEN}
    agent_headers = {"X-Observation-Proposal-Token": AGENT_TOKEN}
    reviewer_headers = {"X-Observation-Proposal-Token": REVIEWER_TOKEN}
    context_url = f"/v1/companies/{company_id}/agent-context"
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(settings)) as client,
    ):
        initial = client.get(context_url, headers=read_headers)
        assert initial.status_code == 200, initial.text
        context = CompanyAgentContextV1.model_validate(initial.json())
        assert context.portfolio_status.status == "UNSUPPORTED"
        assert context.native_models_status.status == "UNSUPPORTED"
        assert context.resource_links == {}

        report = compare_source_pack(context, pack)
        assert report["status"] == "DRAFTS_PREPARED"
        handoff = prepare_handoff(context, pack, verified)
        assert [b["contract_type"] for b in handoff["ready_batches"]] == [
            "MetricDefinitionBatchV1",
        ]
        assert handoff["deferred_batch_types"] == [
            "KPIObservationBatchV1",
            "GuidanceObservationBatchV1",
        ]

        # A proposal is never self-approved: only the reviewer role can preview
        # and explicitly accept each dependency in order. Definitions must be
        # accepted before a fresh context makes KPI/guidance candidates eligible.
        for phase in ("definitions", "observations"):
            if phase == "observations":
                updated = client.get(context_url, headers=read_headers)
                assert updated.status_code == 200, updated.text
                handoff = prepare_handoff(
                    CompanyAgentContextV1.model_validate(updated.json()), pack, verified
                )
                assert [b["contract_type"] for b in handoff["ready_batches"]] == [
                    "KPIObservationBatchV1",
                    "GuidanceObservationBatchV1",
                ]
            for batch in handoff["ready_batches"]:
                denied = client.post(
                    "/v1/company-observation-proposals",
                    json=batch,
                    headers=reviewer_headers,
                )
                assert denied.status_code == 401
                submitted = client.post(
                    "/v1/company-observation-proposals",
                    json=batch,
                    headers=agent_headers,
                )
                assert submitted.status_code == 201, submitted.text
                proposal_id = submitted.json()["proposal"]["id"]
                preview = client.post(
                    f"/v1/company-observation-proposals/{proposal_id}/preview",
                    headers=reviewer_headers,
                )
                assert preview.status_code == 200, preview.text
                assert preview.json()["status"] == "READY", preview.text
                assert preview.json()["preview_fingerprint"]
                accepted = client.post(
                    f"/v1/company-observation-proposals/{proposal_id}/accept",
                    headers=reviewer_headers,
                    json={
                        "preview_fingerprint": preview.json()["preview_fingerprint"],
                        "decision_note": "Reviewed source extract, periods and units in isolation.",
                    },
                )
                assert accepted.status_code == 200, accepted.text
                assert accepted.json()["status"] == "ACCEPTED"

        current = client.get(context_url, headers=read_headers)
        assert current.status_code == 200, current.text
        final_context = CompanyAgentContextV1.model_validate(current.json())
        observed = {row.metric_id: row for row in final_context.metric_observations}
        assert set(observed) == {"uber.trips", "uber.gross_bookings"}
        assert observed["uber.trips"].value == Decimal("4061")
        assert observed["uber.gross_bookings"].value == Decimal("59819")
        assert observed["uber.gross_bookings"].currency == "USD"
        assert observed["uber.gross_bookings"].reported_at is None
        assert len(final_context.guidance_observations) == 1
        assert final_context.guidance_observations[0].lower_value == Decimal("63250")
        assert final_context.guidance_observations[0].upper_value == Decimal("65250")
        assert final_context.guidance_observations[0].issued_at is None
        assert final_context.native_models_status.status == "UNSUPPORTED"
        matched = compare_source_pack(final_context, pack)
        assert matched["status"] == "MATCHED"
        assert matched["draft_proposals"] == []
        assert all(row["outcome"] == "MATCHED" for row in matched["findings"])
        finished = prepare_handoff(final_context, pack, verified)
        assert finished["shadow_status"] == "MATCHED"
        assert finished["ready_batches"] == []
        assert finished["candidate_submission"]["status"] == "NOT_ATTEMPTED"
