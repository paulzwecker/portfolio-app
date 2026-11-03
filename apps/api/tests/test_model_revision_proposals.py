"""Structured model proposal contracts, role authorization and isolated review flows."""

import copy
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import (
    dcf_fixture,
    owner_cash_flow_fixture,
    residual_income_fixture,
)

from portfolio_api.domain.models import FinancialModelRevision
from portfolio_api.domain.routes import session_for
from portfolio_api.domain.schemas import FinancialModelRevisionProposalV1
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

AGENT_TOKEN = "agent-proposal-token-for-test-only-000000000000"
REVIEWER_TOKEN = "reviewer-proposal-token-for-test-only-0000000000"
AGENT_ID = "synthetic-research-agent"
REVIEWER_ID = "synthetic-human-reviewer"
pytestmark = pytest.mark.integration


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "app_env": "development",
            "model_proposal_agent_token": SecretStr(AGENT_TOKEN),
            "model_proposal_agent_id": AGENT_ID,
            "model_proposal_reviewer_token": SecretStr(REVIEWER_TOKEN),
            "model_proposal_reviewer_id": REVIEWER_ID,
        }
    )


def _headers(token: str) -> dict[str, str]:
    return {"X-Model-Proposal-Token": token}


def _proposal_payload(
    *,
    model_id: str,
    company_id: str,
    listing_id: str,
    revision_id: str,
    revision_number: int,
    methodology: str,
    methodology_version: str,
    inputs: dict[str, Any],
    external_revision_id: str = "agent-model-r1",
    evidence_id: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0)
    return {
        "contract_type": "FinancialModelRevisionProposalV1",
        "contract_version": "1.0.0",
        "model_id": model_id,
        "company_id": company_id,
        "valuation_listing_id": listing_id,
        "model_currency": "USD" if methodology != "RESIDUAL_INCOME_10Y_FADE" else "INR",
        "methodology_version": methodology_version,
        "base_revision_id": revision_id,
        "base_revision_number": revision_number,
        "external_revision_id": external_revision_id,
        "authored_at": now.isoformat(),
        "effective_at": now.isoformat(),
        "source_reference": "https://research.example.test/model-note/r1",
        "rationale": "The cited evidence supports this reviewed synthetic assumption change.",
        "supporting_evidence": [
            {
                "evidence_type": "RESEARCH_REVISION",
                "reference_id": evidence_id or str(uuid4()),
                "relationship": "SUPPORTS",
                "note": "Synthetic source-linked evidence.",
            }
        ],
        "method": {"methodology": methodology, "inputs": inputs},
    }


def test_model_proposal_contract_rejects_outputs_and_untrusted_author_fields() -> None:
    payload = _proposal_payload(
        model_id=str(uuid4()),
        company_id=str(uuid4()),
        listing_id=str(uuid4()),
        revision_id=str(uuid4()),
        revision_number=1,
        methodology="OWNER_CASH_FLOW_10Y",
        methodology_version="owner-cash-flow-10y-v1",
        inputs=owner_cash_flow_fixture()["input"],
    )
    parsed = FinancialModelRevisionProposalV1.model_validate(payload)
    assert parsed.method.methodology == "OWNER_CASH_FLOW_10Y"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FinancialModelRevisionProposalV1.model_validate({**payload, "author_id": "spoofed"})
    payload_with_outputs = copy.deepcopy(payload)
    payload_with_outputs["method"]["outputs"] = {"weighted_fv": "999"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FinancialModelRevisionProposalV1.model_validate(payload_with_outputs)


def test_model_proposal_roles_are_enforced_in_development_without_database() -> None:
    with TestClient(create_app(_settings())) as client:
        agent_cannot_list_for_review = client.get(
            "/v1/model-revision-proposals", headers=_headers(AGENT_TOKEN)
        )
        assert agent_cannot_list_for_review.status_code == 401
        agent_cannot_preview = client.post(
            f"/v1/model-revision-proposals/{uuid4()}/preview",
            headers=_headers(AGENT_TOKEN),
        )
        assert agent_cannot_preview.status_code == 401
        agent_cannot_accept = client.post(
            f"/v1/model-revision-proposals/{uuid4()}/accept",
            headers=_headers(AGENT_TOKEN),
            json={
                "preview_fingerprint": "a" * 64,
                "decision_note": "Agent cannot self-approve.",
            },
        )
        assert agent_cannot_accept.status_code == 401
        reviewer_cannot_submit = client.post(
            "/v1/model-revision-proposals",
            headers=_headers(REVIEWER_TOKEN),
            json={},
        )
        assert reviewer_cannot_submit.status_code == 401


def test_reviewer_proposal_list_accepts_a_company_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    observed: dict[str, object] = {}

    def fake_list(
        session: Session,
        *,
        status: str | None = None,
        company_id: UUID | None = None,
        limit: int = 50,
    ) -> list[Any]:
        del session
        observed.update({"company_id": company_id, "status": status, "limit": limit})
        return []

    def fake_session() -> Iterator[Session]:
        yield cast(Session, object())

    monkeypatch.setattr(
        "portfolio_api.domain.routes.proposal_operations.list_model_revision_proposals",
        fake_list,
    )
    app = create_app(_settings())
    app.dependency_overrides[session_for] = fake_session

    with TestClient(app) as client:
        response = client.get(
            f"/v1/model-revision-proposals?company_id={company_id}&limit=100",
            headers=_headers(REVIEWER_TOKEN),
        )

    assert response.status_code == 200
    assert response.json() == []
    assert observed == {"company_id": company_id, "status": None, "limit": 100}


def test_remote_proposal_api_uses_role_token_without_broad_api_token() -> None:
    remote_settings = Settings.model_validate(
        {
            "app_env": "preview",
            "database_url": SecretStr(
                "postgresql+psycopg://test:test@192.0.2.1:5432/preview?sslmode=verify-full"
            ),
            "api_access_token": SecretStr("broad-api-token-for-test-only-000000000000"),
            "model_proposal_agent_token": SecretStr(AGENT_TOKEN),
            "model_proposal_agent_id": AGENT_ID,
            "model_proposal_reviewer_token": SecretStr(REVIEWER_TOKEN),
            "model_proposal_reviewer_id": REVIEWER_ID,
        }
    )
    with (
        patch("portfolio_api.main.create_database_engine", return_value=None),
        TestClient(create_app(remote_settings)) as client,
    ):
        response = client.get(
            "/v1/model-revision-proposals",
            headers=_headers(REVIEWER_TOKEN),
        )
        assert response.status_code == 503
        assert "Database is unavailable" in response.json()["detail"]

        unauthenticated = client.get("/v1/model-revision-proposals")
        assert unauthenticated.status_code == 401

        broad_token_does_not_grant_review_role = client.get(
            "/v1/model-revision-proposals",
            headers={"X-API-ACCESS-TOKEN": "broad-api-token-for-test-only-000000000000"},
        )
        assert broad_token_does_not_grant_review_role.status_code == 401

        neighboring_path_remains_under_outer_gate = client.get(
            "/v1/model-revision-proposals-unrelated"
        )
        assert neighboring_path_remains_under_outer_gate.status_code == 401


@pytest.mark.parametrize(
    ("methodology", "currency", "fixture", "methodology_version", "method_path"),
    [
        (
            "UFCF_DCF_10Y_FADE",
            "USD",
            dcf_fixture,
            "ufcf-dcf-fade-v1",
            "dcf",
        ),
        (
            "OWNER_CASH_FLOW_10Y",
            "USD",
            owner_cash_flow_fixture,
            "owner-cash-flow-10y-v1",
            "owner",
        ),
        (
            "RESIDUAL_INCOME_10Y_FADE",
            "INR",
            residual_income_fixture,
            "residual-income-10y-fade-v1",
            "residual",
        ),
    ],
)
def test_agent_proposal_review_accept_replay_conflict_and_provenance(
    postgres_engine: Engine,
    methodology: str,
    currency: str,
    fixture: Any,
    methodology_version: str,
    method_path: str,
) -> None:
    source = fixture()
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(_settings())) as client,
    ):
        company = client.post(
            "/v1/companies",
            json={"name": f"Proposal fixture {method_path}", "reporting_currency": currency},
        ).json()
        security = client.post(
            f"/v1/companies/{company['id']}/securities",
            json={"name": "Synthetic proposal common", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "XNAS", "ticker": f"PROP{method_path.upper()}", "currency": currency},
        ).json()

        research = client.post(
            "/v1/research-revisions",
            json={
                "contract_type": "ResearchRevisionContractV1",
                "contract_version": "1.0.0",
                "company_id": company["id"],
                "security_id": security["id"],
                "stream_key": "model-proposal-evidence",
                "external_revision_id": f"evidence-{method_path}-r1",
                "supersedes_revision_id": None,
                "author_id": "synthetic-research-author",
                "source_id": "synthetic-fixture-source",
                "source_reference": "https://research.example.test/evidence",
                "observed_at": datetime.now(UTC).isoformat(),
                "status": "PUBLISHED",
                "rationale": "Synthetic evidence for proposal review integration testing.",
                "uncertainty": "Synthetic-only fixture.",
                "forecasts": [
                    {
                        "metric": "REVENUE",
                        "period_type": "ANNUAL",
                        "fiscal_year": 2027,
                        "fiscal_period": "FY",
                        "period_end": "2027-12-31",
                        "scenario": "BASE",
                        "value": "100",
                        "currency": currency,
                        "unit": "currency",
                        "availability_status": "AVAILABLE",
                        "confidence": "HIGH",
                        "rationale": "Synthetic forecast evidence.",
                    }
                ],
                "assessments": [],
                "evidence": [
                    {
                        "source_name": "Synthetic filing",
                        "external_identifier": f"synthetic-{method_path}-source",
                        "source_url": "https://issuer.example.test/filing",
                        "published_at": "2026-10-01",
                        "note": "Synthetic evidence used only in tests.",
                    }
                ],
            },
        )
        assert research.status_code == 201, research.text
        evidence_id = research.json()["revision"]["id"]

        initial_input = copy.deepcopy(source["input"])
        if method_path == "dcf":
            initial_input["base_revision_id"] = None
            initial_input["source_revision_id"] = f"synthetic:{method_path}:initial"
            initial_input["actor"] = "IMPORT"
            initial_input["source"] = "Synthetic model fixture"
            initial_input["rationale"] = "Initial synthetic model state."
            initial_input["effective_at"] = datetime.now(UTC).isoformat()
            create_body = {
                "model_name": f"Synthetic {methodology} model",
                "valuation_listing_id": listing["id"],
                "model_currency": currency,
                "source_model_key": f"SYNTHETIC_{method_path.upper()}",
                "initial_revision": initial_input,
            }
            create_path = f"/v1/companies/{company['id']}/financial-models"
            create_body["model_type"] = methodology
        else:
            create_body = {
                "model_name": f"Synthetic {methodology} model",
                "valuation_listing_id": listing["id"],
                "model_currency": currency,
                "source_model_key": f"SYNTHETIC_{method_path.upper()}",
                "initial_revision": {
                    **initial_input,
                    "base_revision_id": None,
                    "source_revision_id": None,
                    "actor": "LOCAL_USER",
                    "source": "Synthetic model fixture",
                    "rationale": "Initial synthetic model state.",
                    "effective_at": datetime.now(UTC).isoformat(),
                },
            }
            archetype_path = "owner-cash-flow" if method_path == "owner" else "residual-income"
            create_path = (
                f"/v1/companies/{company['id']}/canonical-financial-models/{archetype_path}"
            )
        created = client.post(create_path, json=create_body)
        assert created.status_code == 201, created.text
        model = created.json()
        current = model["current_revision"]
        method_inputs = copy.deepcopy(source["input"])
        method_inputs.pop("base_revision_id", None)
        method_inputs.pop("source_revision_id", None)
        method_inputs.pop("actor", None)
        method_inputs.pop("source", None)
        method_inputs.pop("rationale", None)
        method_inputs.pop("effective_at", None)
        alternate_inputs = copy.deepcopy(method_inputs)
        if method_path == "dcf":
            alternate_inputs["scenarios"][1]["years"][0]["revenue_growth"] = "0.081"
            alternate_inputs["scenarios"][2]["years"][0]["revenue_growth"] = "0.122"
        elif method_path == "owner":
            alternate_inputs["scenarios"][1]["years"][0]["owner_cash_flow_margin"] = "0.221"
            alternate_inputs["scenarios"][2]["years"][0]["owner_cash_flow_margin"] = "0.261"
        else:
            alternate_inputs["scenarios"][1]["starting_roe"] = "0.151"
            alternate_inputs["scenarios"][2]["starting_roe"] = "0.181"

        proposal = _proposal_payload(
            model_id=model["id"],
            company_id=company["id"],
            listing_id=listing["id"],
            revision_id=current["id"],
            revision_number=current["revision_number"],
            methodology=methodology,
            methodology_version=methodology_version,
            inputs=alternate_inputs,
            evidence_id=evidence_id,
        )
        submitted = client.post(
            "/v1/model-revision-proposals", json=proposal, headers=_headers(AGENT_TOKEN)
        )
        assert submitted.status_code == 201, submitted.text
        first_candidate = submitted.json()["proposal"]
        assert first_candidate["status"] == "PENDING"
        assert first_candidate["producer_id"] == AGENT_ID
        assert "author_id" not in proposal

        replay = client.post(
            "/v1/model-revision-proposals", json=proposal, headers=_headers(AGENT_TOKEN)
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["proposal"]["id"] == first_candidate["id"]

        changed_replay = copy.deepcopy(proposal)
        changed_replay["method"]["inputs"] = copy.deepcopy(method_inputs)
        changed = client.post(
            "/v1/model-revision-proposals",
            json=changed_replay,
            headers=_headers(AGENT_TOKEN),
        )
        assert changed.status_code == 409

        second_proposal = copy.deepcopy(proposal)
        second_proposal["external_revision_id"] = "agent-model-r2"
        second_proposal["method"]["inputs"] = alternate_inputs
        second = client.post(
            "/v1/model-revision-proposals",
            json=second_proposal,
            headers=_headers(AGENT_TOKEN),
        )
        assert second.status_code == 201, second.text
        assert (
            first_candidate["id"] in replay.text
            or replay.json()["proposal"]["id"] == first_candidate["id"]
        )

        listing_for_reviewer = client.get(
            "/v1/model-revision-proposals?status=PENDING", headers=_headers(REVIEWER_TOKEN)
        )
        assert listing_for_reviewer.status_code == 200, listing_for_reviewer.text
        assert len(listing_for_reviewer.json()) == 2

        candidate_id = first_candidate["id"]
        agent_preview = client.post(
            f"/v1/model-revision-proposals/{candidate_id}/preview",
            headers=_headers(AGENT_TOKEN),
        )
        assert agent_preview.status_code == 401
        preview = client.post(
            f"/v1/model-revision-proposals/{candidate_id}/preview",
            headers=_headers(REVIEWER_TOKEN),
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "READY"
        assert preview.json()["input_changes"]
        assert preview.json()["output_changes"]
        fingerprint = preview.json()["preview_fingerprint"]

        accepted = client.post(
            f"/v1/model-revision-proposals/{candidate_id}/accept",
            headers=_headers(REVIEWER_TOKEN),
            json={
                "preview_fingerprint": fingerprint,
                "decision_note": "Reviewed the synthetic proposal and evidence.",
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "ACCEPTED"
        accepted_revision_id = accepted.json()["accepted_revision_id"]
        revision = (
            client.get(
                f"/v1/canonical-financial-models/{model['id']}/revisions/{accepted_revision_id}"
            )
            if method_path != "dcf"
            else client.get(f"/v1/financial-models/{model['id']}/revisions/{accepted_revision_id}")
        )
        assert revision.status_code == 200, revision.text
        revision_data = revision.json()
        assert revision_data["revision_number"] == 2
        assert revision_data["actor"] == "IMPORT"
        assert revision_data["proposal_author_id"] == AGENT_ID
        assert revision_data["proposal_source_reference"] == proposal["source_reference"]
        assert len(revision_data["supporting_evidence"]) == 1
        assert accepted.json()["proposal"]["reviewer_id"] == REVIEWER_ID

        stale_preview = client.post(
            f"/v1/model-revision-proposals/{second.json()['proposal']['id']}/preview",
            headers=_headers(REVIEWER_TOKEN),
        )
        assert stale_preview.status_code == 200, stale_preview.text
        assert stale_preview.json()["status"] == "CONFLICT"
        rejected = client.post(
            f"/v1/model-revision-proposals/{second.json()['proposal']['id']}/reject",
            headers=_headers(REVIEWER_TOKEN),
            json={"decision_note": "Rejected after the base revision advanced."},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "REJECTED"
        assert rejected.json()["proposal"]["reviewer_id"] == REVIEWER_ID

        with Session(postgres_engine) as db:
            revisions = list(
                db.query(FinancialModelRevision)
                .filter(FinancialModelRevision.model_id == UUID(model["id"]))
                .order_by(FinancialModelRevision.revision_number)
            )
            assert len(revisions) == 2


def test_model_proposal_settings_require_distinct_role_credentials() -> None:
    with pytest.raises(ValidationError, match="must be configured together"):
        Settings.model_validate({"model_proposal_agent_id": AGENT_ID})
    with pytest.raises(ValidationError, match="must be distinct"):
        Settings.model_validate(
            {
                "model_proposal_agent_token": SecretStr(AGENT_TOKEN),
                "model_proposal_agent_id": AGENT_ID,
                "model_proposal_reviewer_token": SecretStr(AGENT_TOKEN),
                "model_proposal_reviewer_id": REVIEWER_ID,
            }
        )
    with pytest.raises(ValidationError, match="identities must be distinct"):
        Settings.model_validate(
            {
                "model_proposal_agent_token": SecretStr(AGENT_TOKEN),
                "model_proposal_agent_id": AGENT_ID,
                "model_proposal_reviewer_token": SecretStr(REVIEWER_TOKEN),
                "model_proposal_reviewer_id": AGENT_ID,
            }
        )
