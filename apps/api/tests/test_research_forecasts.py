"""Agent-authored research contracts remain separate, immutable observations."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    ResearchAssessment,
    ResearchEvidence,
    ResearchForecast,
    ResearchRevision,
    Security,
)
from portfolio_api.domain.services import DomainError
from portfolio_api.main import create_app
from portfolio_api.research_forecasts import company_research, publish_research_revision
from portfolio_api.settings import Settings
from portfolio_api.source_documents import create_company_source_document


def contract(company_id: UUID, **changes: object) -> s.ResearchRevisionPublishContract:
    payload: dict[str, object] = {
        "contract_type": "ResearchRevisionContractV1",
        "contract_version": "1.0.0",
        "company_id": str(company_id),
        "security_id": None,
        "stream_key": "research-agent/company-outlook",
        "external_revision_id": "agent-r1",
        "supersedes_revision_id": None,
        "author_id": "research-agent",
        "source_id": "google-sheets",
        "source_reference": "https://docs.google.com/spreadsheets/d/example/edit#gid=123",
        "observed_at": "2026-10-10T12:00:00Z",
        "status": "PUBLISHED",
        "rationale": "The supported evidence implies steady near-term growth.",
        "uncertainty": "Customer concentration could slow the second year.",
        "forecasts": [
            {
                "metric": "REVENUE",
                "period_type": "ANNUAL",
                "fiscal_year": 2027,
                "fiscal_period": "FY",
                "period_end": "2027-12-31",
                "scenario": "POINT",
                "value": "0",
                "currency": "USD",
                "unit": "currency",
                "availability_status": "AVAILABLE",
                "confidence": "MEDIUM",
                "rationale": "Explicit forecasted revenue is zero.",
            },
            {
                "metric": "EPS",
                "period_type": "ANNUAL",
                "fiscal_year": 2028,
                "fiscal_period": "FY",
                "value": None,
                "currency": "USD",
                "unit": "currency/share",
                "availability_status": "UNAVAILABLE",
                "availability_reason": "No fiscal 2028 share-count bridge is available.",
            },
        ],
        "assessments": [
            {
                "assessment_type": "BUSINESS_OUTLOOK",
                "status": "AVAILABLE",
                "narrative": "Demand remains resilient, with some customer concentration.",
                "confidence": "MEDIUM",
                "uncertainty": "Renewal rates are not yet reported.",
            }
        ],
        "evidence": [
            {
                "source_name": "Issuer annual report",
                "external_identifier": "annual-report-2025",
                "source_url": "https://issuer.example.test/reports/2025.pdf",
                "published_at": "2026-02-20",
                "excerpt": "The company describes its end-market exposure.",
            }
        ],
    }
    payload.update(changes)
    return s.ResearchRevisionPublishContract.model_validate(payload)


def test_research_contract_validates_period_currency_units_and_missing_values() -> None:
    company_id = uuid4()
    accepted = contract(company_id)
    assert accepted.forecasts[0].value == Decimal("0")
    assert accepted.forecasts[1].value is None
    assert accepted.forecasts[1].availability_status == "UNAVAILABLE"

    invalid_rows: list[dict[str, object]] = [
        {"metric": "REVENUE", "unit": "shares", "currency": None},
        {"metric": "EPS", "unit": "currency", "currency": "USD"},
        {"metric": "DILUTED_SHARES", "unit": "shares", "currency": "USD"},
    ]
    for invalid in invalid_rows:
        row = {
            "metric": "REVENUE",
            "period_type": "ANNUAL",
            "fiscal_year": 2027,
            "fiscal_period": "FY",
            "value": "12",
            "currency": "USD",
            "unit": "currency",
            "availability_status": "AVAILABLE",
            **invalid,
        }
        with pytest.raises(ValidationError):
            s.ResearchForecastInput.model_validate(row)

    with pytest.raises(ValidationError, match="Quarterly research forecasts"):
        s.ResearchForecastInput.model_validate(
            {
                "metric": "REVENUE",
                "period_type": "QUARTERLY",
                "fiscal_year": 2027,
                "fiscal_period": "FY",
                "value": "12",
                "currency": "USD",
                "unit": "currency",
            }
        )
    with pytest.raises(ValidationError, match="require a reason"):
        s.ResearchForecastInput.model_validate(
            {
                "metric": "EPS",
                "period_type": "ANNUAL",
                "fiscal_year": 2027,
                "fiscal_period": "FY",
                "value": None,
                "currency": "USD",
                "unit": "currency/share",
                "availability_status": "UNAVAILABLE",
            }
        )
    for invalid_value in [0.5, "NaN", "Infinity"]:
        with pytest.raises(ValidationError):
            s.ResearchForecastInput.model_validate(
                {
                    "metric": "EPS",
                    "period_type": "ANNUAL",
                    "fiscal_year": 2027,
                    "fiscal_period": "FY",
                    "value": invalid_value,
                    "currency": "USD",
                    "unit": "currency/share",
                }
            )


@pytest.mark.integration
def test_research_publication_history_provenance_and_api_idempotence(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        issuer = Company(name="Research contract issuer", reporting_currency="USD", is_demo=False)
        db.add(issuer)
        db.flush()
        security = Security(
            company_id=issuer.id,
            name="Research common stock",
            security_type="COMMON_STOCK",
            share_class=None,
            underlying_security_id=None,
            is_demo=False,
        )
        db.add(security)
        db.flush()
        company_id, security_id = issuer.id, security.id

    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        first_payload = contract(company_id, security_id=security_id).model_dump(mode="json")
        published_response = client.post("/v1/research-revisions", json=first_payload)
        assert published_response.status_code == 201
        first = published_response.json()["revision"]
        assert first["revision_number"] == 1
        assert first["contract_version"] == "1.0.0"
        assert first["author_id"] == "research-agent"
        assert first["source_id"] == "google-sheets"
        assert first["security_id"] == str(security_id)
        assert Decimal(first["forecasts"][0]["value"]) == Decimal("0")
        assert first["forecasts"][1]["value"] is None
        assert first["forecasts"][1]["availability_status"] == "UNAVAILABLE"
        assert first["assessments"][0]["assessment_type"] == "BUSINESS_OUTLOOK"
        assert first["evidence"][0]["external_identifier"] == "annual-report-2025"

        replay = client.post("/v1/research-revisions", json=first_payload)
        assert replay.status_code == 200
        assert replay.json()["result"] == "ALREADY_PUBLISHED"
        assert replay.json()["revision"]["id"] == first["id"]

        changed_replay = contract(
            company_id,
            security_id=security_id,
            rationale="Reused source revision identity with different content.",
        ).model_dump(mode="json")
        assert client.post("/v1/research-revisions", json=changed_replay).status_code == 409

        stale = contract(company_id, security_id=security_id, external_revision_id="agent-r2")
        stale_response = client.post("/v1/research-revisions", json=stale.model_dump(mode="json"))
        assert stale_response.status_code == 409

        second_payload = contract(
            company_id,
            security_id=security_id,
            external_revision_id="agent-r2",
            supersedes_revision_id=first["id"],
            observed_at="2026-10-14T09:00:00Z",
            forecasts=[
                {
                    "metric": "REVENUE",
                    "period_type": "ANNUAL",
                    "fiscal_year": 2027,
                    "fiscal_period": "FY",
                    "period_end": "2027-12-31",
                    "scenario": "POINT",
                    "value": "1250000.2500",
                    "currency": "USD",
                    "unit": "currency",
                    "availability_status": "AVAILABLE",
                    "confidence": "HIGH",
                    "rationale": "Updated following the released annual results.",
                }
            ],
        )
        second_response = client.post(
            "/v1/research-revisions", json=second_payload.model_dump(mode="json")
        )
        assert second_response.status_code == 201
        second = second_response.json()["revision"]
        assert second["revision_number"] == 2
        assert second["supersedes_revision_id"] == first["id"]

        current = client.get(f"/v1/companies/{company_id}/research")
        assert current.status_code == 200
        stream = current.json()["streams"][0]
        assert stream["current_revision"]["id"] == second["id"]
        assert [item["id"] for item in stream["history"]] == [second["id"], first["id"]]
        assert Decimal(stream["history"][1]["forecasts"][0]["value"]) == Decimal("0")

        wrong_security = contract(uuid4(), security_id=security_id).model_dump(mode="json")
        assert client.post("/v1/research-revisions", json=wrong_security).status_code == 404

    with Session(postgres_engine) as db, db.begin():
        assert db.scalar(select(func.count()).select_from(ResearchRevision)) == 2
        assert db.scalar(select(func.count()).select_from(ResearchForecast)) == 3
        assert db.scalar(select(func.count()).select_from(ResearchAssessment)) == 2
        assert db.scalar(select(func.count()).select_from(ResearchEvidence)) == 2
        revisions = list(
            db.scalars(
                select(ResearchRevision)
                .where(ResearchRevision.company_id == company_id)
                .order_by(ResearchRevision.revision_number)
            )
        )
        first, second = revisions
        historical = company_research(
            db,
            company_id,
            as_of=datetime.fromisoformat("2026-10-12T00:00:00+00:00").date(),
        )
        assert historical.streams[0].current_revision.id == first.id
        unknown_then = company_research(
            db,
            company_id,
            known_at=second.recorded_at - timedelta(microseconds=1),
        )
        assert unknown_then.streams[0].current_revision.id == first.id

        prior_value = db.scalar(
            select(ResearchForecast.value).where(
                ResearchForecast.revision_id == first.id,
                ResearchForecast.metric == "REVENUE",
            )
        )
        assert prior_value == Decimal("0")
        first.rationale = "Attempted in-place research history edit"
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()


@pytest.mark.integration
def test_research_contract_rejects_security_from_another_company(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        first = Company(name="First research issuer", is_demo=False)
        second = Company(name="Second research issuer", is_demo=False)
        db.add_all([first, second])
        db.flush()
        security = Security(
            company_id=second.id,
            name="Other issuer common",
            security_type="COMMON_STOCK",
            share_class=None,
            underlying_security_id=None,
            is_demo=False,
        )
        db.add(security)
        db.flush()
        invalid = contract(first.id, security_id=security.id)
        with pytest.raises(DomainError, match="does not belong"):
            publish_research_revision(db, invalid)
        source_document = create_company_source_document(
            db,
            second.id,
            s.SourceDocumentCreate(
                provider_id="company_source",
                source_name="Other issuer investor relations",
                external_identifier="other-issuer-report",
                document_type="OTHER",
                title="Other issuer source",
                published_at=date(2026, 2, 20),
                canonical_url="https://other-issuer.example.test/report.pdf",
            ),
        )
        wrong_evidence_owner = contract(
            first.id,
            evidence=[
                {
                    "source_document_id": str(source_document.id),
                    "source_name": "Other issuer investor relations",
                }
            ],
        )
        with pytest.raises(DomainError, match="does not belong"):
            publish_research_revision(db, wrong_evidence_owner)
