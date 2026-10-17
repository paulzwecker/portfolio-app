from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Actor,
    CandidatePipelineRevision,
    CandidateResearchStage,
    Company,
    Lifecycle,
    ResearchRevision,
)
from portfolio_api.domain.schemas import (
    CandidatePipelineGateInput,
    CandidatePipelineRevisionCreate,
    LifecycleChange,
)
from portfolio_api.domain.services import transition_lifecycle
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

GATES = (
    CandidateResearchStage.DISCOVERY,
    CandidateResearchStage.INITIAL_SCREEN,
    CandidateResearchStage.QUALITY_DURABILITY,
    CandidateResearchStage.FUNDAMENTAL_COMPOUNDING,
    CandidateResearchStage.DEEP_DIVE,
)


def gate_payload(
    stage: CandidateResearchStage,
    outcome: str = "NOT_ASSESSED",
    *,
    rationale: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    per_share: bool = False,
) -> dict[str, Any]:
    return {
        "gate": stage.value,
        "outcome": outcome,
        "rationale": rationale,
        "normalized_per_share_basis_confirmed": per_share,
        "evidence": evidence or [],
    }


def payload(
    *,
    expected_revision_id: str | None = None,
    submission_id: str | None = None,
    stage: CandidateResearchStage = CandidateResearchStage.DISCOVERY,
    discovery: dict[str, Any] | None = None,
    gates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gate_rows = gates or [gate_payload(gate) for gate in GATES]
    if discovery is not None:
        gate_rows = [
            discovery if row["gate"] == CandidateResearchStage.DISCOVERY.value else row
            for row in gate_rows
        ]
    return {
        "expected_revision_id": expected_revision_id,
        "submission_id": submission_id or str(uuid4()),
        "stage": stage.value,
        "disposition": None,
        "next_action": "Review the initial company screen.",
        "unresolved_questions": ["Is the product advantage durable?"],
        "actor": Actor.LOCAL_USER.value,
        "author_id": "researcher",
        "source": "local-candidate-pipeline",
        "rationale": "Initial research work is recorded for audit.",
        "effective_at": datetime.now(UTC).isoformat(),
        "gates": gate_rows,
    }


def make_candidate(postgres_engine: Engine, name: str) -> UUID:
    with Session(postgres_engine) as db, db.begin():
        company = Company(name=name, reporting_currency="USD", is_demo=False)
        db.add(company)
        db.flush()
        transition_lifecycle(
            db,
            company.id,
            LifecycleChange(
                actor=Actor.LOCAL_USER,
                reason="Added to research queue",
                source="test",
                effective_at=datetime.now(UTC),
                new_state=Lifecycle.CANDIDATE,
                expected_event_id=None,
            ),
        )
        return company.id


def test_candidate_pipeline_contract_requires_explicit_gates_and_per_share_basis() -> None:
    valid = payload()
    assert (
        CandidatePipelineRevisionCreate.model_validate(valid).stage
        == CandidateResearchStage.DISCOVERY
    )

    incomplete_gates = {**valid, "gates": valid["gates"][:-1]}
    with pytest.raises(ValueError, match="List should have at least 5 items"):
        CandidatePipelineRevisionCreate.model_validate(incomplete_gates)

    passed_discovery = gate_payload(
        CandidateResearchStage.DISCOVERY,
        "PASS",
        rationale="The initial evidence justifies screening.",
        evidence=[
            {
                "evidence_type": "SOURCE_URL",
                "source_url": "https://example.com/research",
            }
        ],
    )
    bad_basis = payload(discovery=passed_discovery)
    fundamental = gate_payload(
        CandidateResearchStage.FUNDAMENTAL_COMPOUNDING,
        "PASS",
        rationale="It appears to exceed the hurdle.",
        evidence=[
            {
                "evidence_type": "SOURCE_URL",
                "source_url": "https://example.com/model",
            }
        ],
    )
    bad_basis["gates"] = [
        fundamental if row["gate"] == CandidateResearchStage.FUNDAMENTAL_COMPOUNDING.value else row
        for row in bad_basis["gates"]
    ]
    with pytest.raises(ValueError, match="normalized per-share basis"):
        CandidatePipelineRevisionCreate.model_validate(bad_basis)

    http_source = dict(passed_discovery)
    http_source["evidence"] = [{"evidence_type": "SOURCE_URL", "source_url": "http://example.com"}]
    with pytest.raises(ValueError, match="HTTPS"):
        CandidatePipelineGateInput.model_validate(http_source)

    failed_discovery = gate_payload(
        CandidateResearchStage.DISCOVERY,
        "FAIL",
        rationale="The company is outside the documented research scope.",
        evidence=[
            {
                "evidence_type": "SOURCE_URL",
                "source_url": "https://issuer.example/filing",
            }
        ],
    )
    drop = payload(discovery=failed_discovery)
    drop["disposition"] = "DROP"
    drop["next_action"] = None
    assert CandidatePipelineRevisionCreate.model_validate(drop).disposition == "DROP"

    premature_watchlist = {**drop, "disposition": "WATCHLIST"}
    with pytest.raises(ValueError, match="resolution stage"):
        CandidatePipelineRevisionCreate.model_validate(premature_watchlist)


@pytest.mark.integration
def test_candidate_pipeline_history_progression_idempotence_and_lifecycle_separation(
    postgres_engine: Engine,
) -> None:
    company_id = make_candidate(postgres_engine, "Pipeline issuer")
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        queue = client.get("/v1/candidate-pipeline")
        assert queue.status_code == 200
        queued = next(row for row in queue.json() if row["company"]["id"] == str(company_id))
        assert queued["status"] == "NOT_STARTED"
        assert queued["stage"] is None
        assert queued["research_rank_position"] is None

        first_payload = payload()
        first_response = client.post(
            f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=first_payload
        )
        assert first_response.status_code == 201, first_response.text
        first = first_response.json()["revision"]
        assert first["revision_number"] == 1
        assert first["stage"] == "DISCOVERY"
        assert len(first["gates"]) == 5
        first_discovery = next(gate for gate in first["gates"] if gate["gate"] == "DISCOVERY")
        assert first_discovery["outcome"] == "NOT_ASSESSED"

        replay = client.post(
            f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=first_payload
        )
        assert replay.status_code == 200
        assert replay.json()["result"] == "ALREADY_RECORDED"
        assert replay.json()["revision"]["id"] == first["id"]

        changed_replay = {**first_payload, "rationale": "Changed content under same submission"}
        assert (
            client.post(
                f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=changed_replay
            ).status_code
            == 409
        )

        discovery_pass = gate_payload(
            CandidateResearchStage.DISCOVERY,
            "PASS",
            rationale="A primary-source review supports a first screen.",
            evidence=[
                {
                    "evidence_type": "SOURCE_URL",
                    "source_url": "https://issuer.example/about",
                    "note": "Issuer description reviewed.",
                }
            ],
        )
        second_payload = payload(
            expected_revision_id=first["id"],
            discovery=discovery_pass,
        )
        second_response = client.post(
            f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=second_payload
        )
        assert second_response.status_code == 201, second_response.text
        second = second_response.json()["revision"]

        skipped = payload(
            expected_revision_id=second["id"], stage=CandidateResearchStage.QUALITY_DURABILITY
        )
        assert (
            client.post(
                f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=skipped
            ).status_code
            == 422
        )

        third_payload = payload(
            expected_revision_id=second["id"],
            stage=CandidateResearchStage.INITIAL_SCREEN,
            discovery=discovery_pass,
        )
        third_response = client.post(
            f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=third_payload
        )
        assert third_response.status_code == 201, third_response.text
        third = third_response.json()["revision"]
        assert third["revision_number"] == 3
        assert third["base_revision_id"] == second["id"]

        stale = payload()
        stale["submission_id"] = str(uuid4())
        assert (
            client.post(
                f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=stale
            ).status_code
            == 409
        )

        read = client.get(f"/v1/companies/{company_id}/candidate-pipeline")
        assert read.status_code == 200
        body = read.json()
        assert body["queue_entry"]["stage"] == "INITIAL_SCREEN"
        assert body["queue_entry"]["status"] == "IN_PROGRESS"
        assert [row["id"] for row in body["history"]] == [third["id"], second["id"], first["id"]]
        latest_discovery = next(
            gate for gate in body["history"][0]["gates"] if gate["gate"] == "DISCOVERY"
        )
        original_discovery = next(
            gate for gate in body["history"][2]["gates"] if gate["gate"] == "DISCOVERY"
        )
        assert latest_discovery["outcome"] == "PASS"
        assert original_discovery["outcome"] == "NOT_ASSESSED"
        assert body["lifecycle"] == "CANDIDATE"
        assert body["company"]["lifecycle"] == "CANDIDATE"

    with Session(postgres_engine) as db, db.begin():
        assert (
            db.scalar(
                select(func.count())
                .select_from(CandidatePipelineRevision)
                .where(CandidatePipelineRevision.company_id == company_id)
            )
            == 3
        )
        revision = db.scalar(
            select(CandidatePipelineRevision).where(
                CandidatePipelineRevision.company_id == company_id,
                CandidatePipelineRevision.revision_number == 1,
            )
        )
        assert revision is not None
        revision.rationale = "Attempted history rewrite"
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()


@pytest.mark.integration
def test_candidate_pipeline_gates_require_existing_scores_and_canonical_compounding(
    postgres_engine: Engine,
) -> None:
    company_id = make_candidate(postgres_engine, "Incomplete gate issuer")
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        quality_pass = gate_payload(
            CandidateResearchStage.QUALITY_DURABILITY,
            "PASS",
            rationale="Both dimensions were reviewed.",
            evidence=[
                {
                    "evidence_type": "SOURCE_URL",
                    "source_url": "https://issuer.example/quality",
                }
            ],
        )
        quality_payload = payload()
        quality_payload["gates"] = [
            quality_pass if row["gate"] == CandidateResearchStage.QUALITY_DURABILITY.value else row
            for row in quality_payload["gates"]
        ]
        failed_quality = client.post(
            f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=quality_payload
        )
        assert failed_quality.status_code == 422
        assert "current assessed 10Y Durability" in failed_quality.json()["detail"]

        fundamental_pass = gate_payload(
            CandidateResearchStage.FUNDAMENTAL_COMPOUNDING,
            "PASS",
            rationale="The selected output supports the hurdle.",
            per_share=True,
            evidence=[
                {
                    "evidence_type": "SOURCE_URL",
                    "source_url": "https://issuer.example/model-output",
                }
            ],
        )
        fundamental_payload = payload()
        fundamental_payload["gates"] = [
            fundamental_pass
            if row["gate"] == CandidateResearchStage.FUNDAMENTAL_COMPOUNDING.value
            else row
            for row in fundamental_payload["gates"]
        ]
        failed_compounding = client.post(
            f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=fundamental_payload
        )
        assert failed_compounding.status_code == 422
        assert "current complete normalized model output" in failed_compounding.json()["detail"]

        non_candidate = client.post(
            "/v1/companies",
            json={"name": "Not a candidate", "reporting_currency": "USD"},
        ).json()["id"]
        denied = client.post(
            f"/v1/companies/{non_candidate}/candidate-pipeline-revisions", json=payload()
        )
        assert denied.status_code == 409


@pytest.mark.integration
def test_candidate_pipeline_rejects_cross_company_evidence(postgres_engine: Engine) -> None:
    first_company_id = make_candidate(postgres_engine, "First evidence issuer")
    second_company_id = make_candidate(postgres_engine, "Second evidence issuer")
    with Session(postgres_engine) as db, db.begin():
        foreign_revision = ResearchRevision(
            company_id=second_company_id,
            security_id=None,
            stream_key="candidate-pipeline-test",
            revision_number=1,
            contract_version="1.0.0",
            external_revision_id="foreign-research-r1",
            supersedes_revision_id=None,
            author_id="test-agent",
            source_id="test",
            source_reference="https://issuer.example/research",
            observed_at=datetime.now(UTC),
            status="PUBLISHED",
            rationale="Foreign-company evidence fixture.",
            uncertainty=None,
            content_fingerprint="a" * 64,
        )
        db.add(foreign_revision)
        db.flush()
        foreign_id = foreign_revision.id
    discovery = gate_payload(
        CandidateResearchStage.DISCOVERY,
        "PASS",
        rationale="Evidence should be checked against the owning company.",
        evidence=[{"evidence_type": "RESEARCH_REVISION", "reference_id": str(foreign_id)}],
    )
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        body = payload(discovery=discovery)
        response = client.post(
            f"/v1/companies/{first_company_id}/candidate-pipeline-revisions", json=body
        )
        assert response.status_code == 404
        assert "same canonical company" in response.json()["detail"]


@pytest.mark.integration
def test_candidate_pipeline_can_record_early_drop_without_changing_lifecycle(
    postgres_engine: Engine,
) -> None:
    company_id = make_candidate(postgres_engine, "Early drop issuer")
    discovery_fail = gate_payload(
        CandidateResearchStage.DISCOVERY,
        "FAIL",
        rationale="The public evidence does not meet the documented initial screen.",
        evidence=[
            {
                "evidence_type": "SOURCE_URL",
                "source_url": "https://issuer.example/filing",
            }
        ],
    )
    body = payload(discovery=discovery_fail)
    body["disposition"] = "DROP"
    body["next_action"] = None
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        response = client.post(
            f"/v1/companies/{company_id}/candidate-pipeline-revisions", json=body
        )
        assert response.status_code == 201, response.text
        revision = response.json()["revision"]
        assert revision["stage"] == "DISCOVERY"
        assert revision["disposition"] == "DROP"
        queue = client.get("/v1/candidate-pipeline").json()
        row = next(item for item in queue if item["company"]["id"] == str(company_id))
        assert row["status"] == "COMPLETE"
        assert row["disposition"] == "DROP"
        assert row["company"]["lifecycle"] == "CANDIDATE"
