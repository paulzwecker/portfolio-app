"""Investment thesis opinions retain evidence links and immutable point-in-time history."""

import hashlib
from datetime import UTC, date, datetime, timedelta
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
    InvestmentThesisClaim,
    InvestmentThesisEvidence,
    InvestmentThesisRevision,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
    Security,
    SourceDocument,
)
from portfolio_api.domain.services import DomainError
from portfolio_api.investment_thesis import (
    company_investment_thesis,
    publish_investment_thesis_revision,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


def contract(company_id: UUID, **changes: object) -> s.InvestmentThesisRevisionPublishContract:
    payload: dict[str, object] = {
        "contract_type": "InvestmentThesisContractV1",
        "contract_version": "1.0.0",
        "company_id": str(company_id),
        "security_id": None,
        "stream_key": "investment-thesis",
        "external_revision_id": "thesis-r1",
        "supersedes_revision_id": None,
        "author_id": "external-research-agent",
        "source_id": "google-sheets",
        "source_reference": "https://docs.google.com/spreadsheets/d/example/edit#gid=456",
        "observed_at": "2026-10-10T12:00:00Z",
        "status": "PUBLISHED",
        "thesis_statement": "Recurring demand may support long-duration compounding.",
        "confidence": "MEDIUM",
        "rationale": "The current evidence supports the view, with unresolved risks.",
        "uncertainty": "Customer concentration may limit future growth.",
        "claims": [
            {
                "claim_key": "renewal-economics",
                "claim_type": "COMPETITIVE_ADVANTAGE",
                "status": "ACTIVE",
                "statement": "Renewals may reinforce customer switching costs.",
                "confidence": "MEDIUM",
                "uncertainty": "Cohort renewal data is not yet complete.",
                "evidence": [],
            }
        ],
    }
    payload.update(changes)
    return s.InvestmentThesisRevisionPublishContract.model_validate(payload)


def test_thesis_contract_validates_snapshot_identity_claims_and_sources() -> None:
    issuer_id = uuid4()
    value = contract(issuer_id)
    assert value.claims[0].claim_key == "renewal-economics"

    with pytest.raises(ValidationError, match="claim_key"):
        contract(
            issuer_id,
            claims=[
                *contract(issuer_id).claims,
                contract(issuer_id).claims[0].model_dump(),
            ],
        )

    with pytest.raises(ValidationError, match="source reference"):
        s.InvestmentThesisEvidenceInput.model_validate(
            {"relationship": "SUPPORTS", "source_name": "Unlocated source"}
        )

    with pytest.raises(ValidationError, match="HTTPS"):
        s.InvestmentThesisEvidenceInput.model_validate(
            {
                "relationship": "SUPPORTS",
                "source_name": "Issuer site",
                "source_url": "http://issuer.example.test/thesis",
            }
        )

    with pytest.raises(ValidationError, match="withdrawn thesis"):
        contract(
            issuer_id,
            status="WITHDRAWN",
            thesis_statement=None,
            claims=contract(issuer_id).model_dump(mode="python")["claims"],
        )


@pytest.mark.integration
def test_thesis_revision_history_links_facts_and_is_point_in_time_and_immutable(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    first_observed = now - timedelta(days=5)
    second_observed = now - timedelta(days=1)
    fact_filed = first_observed - timedelta(days=10)
    fact_recorded = first_observed - timedelta(days=9)
    with Session(postgres_engine) as db, db.begin():
        issuer = Company(name="Thesis evidence issuer", reporting_currency="USD", is_demo=False)
        other = Company(name="Other thesis issuer", reporting_currency="USD", is_demo=False)
        db.add_all([issuer, other])
        db.flush()
        security = Security(
            company_id=issuer.id,
            name="Thesis issuer common stock",
            security_type="COMMON_STOCK",
            share_class=None,
            underlying_security_id=None,
            is_demo=False,
        )
        db.add(security)
        db.flush()
        source = SourceDocument(
            company_id=issuer.id,
            security_id=security.id,
            batch_id=None,
            provider_id="company_source",
            source_name="Issuer investor relations",
            source_jurisdiction="US",
            external_identifier="annual-report-prior-year",
            document_type="ANNUAL_REPORT",
            source_form=None,
            title="Prior-year annual report",
            reporting_period="FY prior year",
            fiscal_year=now.year - 1,
            fiscal_period="FY",
            period_end=date(now.year - 1, 12, 31),
            filed_at=None,
            published_at=fact_filed.date(),
            canonical_url="https://issuer.example.test/annual-report.pdf",
            retrieved_at=None,
            recorded_at=fact_recorded,
            is_amendment=False,
            amends_document_id=None,
            supersedes_document_id=None,
            data_quality="PASS",
            quality_reason=None,
            actor="LOCAL_USER",
        )
        batch = ReportedFundamentalBatch(
            provider_id="sec_edgar",
            normalizer_version="thesis-test-v1",
            source_digest=hashlib.sha256(f"thesis-{issuer.id}".encode()).hexdigest(),
            query_scope={"company_id": str(issuer.id)},
            observed_at=fact_recorded,
            provider_summary={},
            reconciliation={},
        )
        db.add_all([source, batch])
        db.flush()
        fact = ReportedFundamentalObservation(
            company_id=issuer.id,
            security_id=None,
            batch_id=batch.id,
            provider_id="sec_edgar",
            provider_entity_id="CIK0000000001",
            source_priority=1,
            metric="REVENUE",
            statement="INCOME_STATEMENT",
            period_type="ANNUAL",
            period_start=datetime(now.year - 1, 1, 1, tzinfo=UTC),
            period_end=datetime(now.year - 1, 12, 31, tzinfo=UTC),
            fiscal_year=now.year - 1,
            fiscal_period="FY",
            filed_at=fact_filed,
            observed_at=fact_recorded,
            recorded_at=fact_recorded,
            value=Decimal("950.25"),
            currency="USD",
            unit="currency",
            source_taxonomy="us-gaap",
            source_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
            source_unit="USD",
            accession_number="0000000001-25-000001",
            form="10-K",
            frame=f"CY{now.year - 1}",
            source_record_id=f"thesis-source:{issuer.id}",
            source_url="https://www.sec.gov/Archives/edgar/data/example/filing-index.html",
            source_ref="thesis-test-fact",
            observation_fingerprint=hashlib.sha256(b"thesis-fact").hexdigest(),
            mapping_priority=1,
            revision_context="ORIGINAL",
            data_quality="PASS",
            quality_reason=None,
            supersedes_observation_id=None,
        )
        db.add(fact)
        db.flush()
        company_id, security_id, source_id, fact_id, other_company_id = (
            issuer.id,
            security.id,
            source.id,
            fact.id,
            other.id,
        )

    first_value = contract(
        company_id,
        security_id=security_id,
        observed_at=first_observed.isoformat(),
        claims=[
            {
                "claim_key": "renewal-economics",
                "claim_type": "COMPETITIVE_ADVANTAGE",
                "status": "ACTIVE",
                "statement": "Renewals may reinforce customer switching costs.",
                "confidence": "MEDIUM",
                "evidence": [
                    {
                        "relationship": "SUPPORTS",
                        "source_document_id": str(source_id),
                        "source_name": "Issuer annual report",
                        "external_identifier": "annual-report-prior-year",
                        "excerpt": "The company reports recurring customer renewals.",
                    },
                    {
                        "relationship": "CONTRADICTS",
                        "reported_fundamental_observation_id": str(fact_id),
                        "source_name": "SEC reported revenue",
                        "note": "The observed revenue result challenges the prior growth claim.",
                    },
                ],
            },
            {
                "claim_key": "retention-question",
                "claim_type": "UNRESOLVED_QUESTION",
                "status": "UNDER_REVIEW",
                "statement": "Will renewal rates remain stable as the installed base matures?",
                "confidence": "UNASSESSED",
                "evidence": [],
            },
        ],
    )
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        first_response = client.post(
            "/v1/investment-thesis-revisions", json=first_value.model_dump(mode="json")
        )
        assert first_response.status_code == 201
        first = first_response.json()["revision"]
        assert first["revision_number"] == 1
        claim = next(row for row in first["claims"] if row["claim_key"] == "renewal-economics")
        document_evidence = next(
            evidence
            for evidence in claim["evidence"]
            if evidence["source_document_id"] == str(source_id)
        )
        assert document_evidence["source_document_title"] == "Prior-year annual report"
        assert document_evidence["published_at"] == fact_filed.date().isoformat()
        fact_evidence = next(
            evidence
            for claim_row in first["claims"]
            for evidence in claim_row["evidence"]
            if evidence["reported_fundamental_observation_id"] == str(fact_id)
        )
        assert Decimal(fact_evidence["reported_fundamental"]["value"]) == Decimal("950.25")
        assert fact_evidence["reported_fundamental"]["data_quality"] == "PASS"

        replay = client.post(
            "/v1/investment-thesis-revisions", json=first_value.model_dump(mode="json")
        )
        assert replay.status_code == 200
        assert replay.json()["result"] == "ALREADY_PUBLISHED"
        assert replay.json()["revision"]["id"] == first["id"]

        stale = contract(
            company_id,
            security_id=security_id,
            external_revision_id="thesis-stale",
            observed_at=(first_observed + timedelta(hours=1)).isoformat(),
        )
        assert (
            client.post(
                "/v1/investment-thesis-revisions", json=stale.model_dump(mode="json")
            ).status_code
            == 409
        )

        changed_replay = first_value.model_copy(
            update={"rationale": "Different content under the reused external revision ID."}
        )
        assert (
            client.post(
                "/v1/investment-thesis-revisions",
                json=changed_replay.model_dump(mode="json"),
            ).status_code
            == 409
        )

        second_value = contract(
            company_id,
            security_id=security_id,
            external_revision_id="thesis-r2",
            supersedes_revision_id=UUID(first["id"]),
            observed_at=second_observed.isoformat(),
            thesis_statement=(
                "Renewals still support the thesis, but revenue durability needs review."
            ),
            confidence="LOW",
            claims=[
                {
                    "claim_key": "renewal-economics",
                    "claim_type": "COMPETITIVE_ADVANTAGE",
                    "status": "UNDER_REVIEW",
                    "statement": (
                        "Switching costs remain plausible but need stronger cohort evidence."
                    ),
                    "confidence": "LOW",
                    "evidence": [],
                }
            ],
        )
        second_response = client.post(
            "/v1/investment-thesis-revisions", json=second_value.model_dump(mode="json")
        )
        assert second_response.status_code == 201
        second = second_response.json()["revision"]
        assert second["revision_number"] == 2
        assert second["supersedes_revision_id"] == first["id"]

        current = client.get(f"/v1/companies/{company_id}/thesis")
        assert current.status_code == 200
        stream = current.json()["streams"][0]
        assert stream["current_revision"]["id"] == second["id"]
        assert [row["id"] for row in stream["history"]] == [second["id"], first["id"]]
        at_first = client.get(
            f"/v1/companies/{company_id}/thesis?as_of={first_observed.date().isoformat()}"
        )
        assert at_first.status_code == 200
        assert at_first.json()["streams"][0]["current_revision"]["id"] == first["id"]
        before_second_recorded_at = datetime.fromisoformat(second["recorded_at"]) - timedelta(
            microseconds=1
        )
        before_second_known = client.get(
            f"/v1/companies/{company_id}/thesis",
            params={"known_at": before_second_recorded_at.isoformat()},
        )
        assert before_second_known.status_code == 200
        assert before_second_known.json()["streams"][0]["current_revision"]["id"] == first["id"]

        foreign_security = contract(other_company_id, security_id=security_id)
        assert (
            client.post(
                "/v1/investment-thesis-revisions",
                json=foreign_security.model_dump(mode="json"),
            ).status_code
            == 422
        )

    with Session(postgres_engine) as db, db.begin():
        revisions = list(
            db.scalars(
                select(InvestmentThesisRevision)
                .where(InvestmentThesisRevision.company_id == company_id)
                .order_by(InvestmentThesisRevision.revision_number)
            )
        )
        first, second = revisions
        latest_revision_id = second.id
        assert db.scalar(select(func.count()).select_from(InvestmentThesisClaim)) == 3
        assert db.scalar(select(func.count()).select_from(InvestmentThesisEvidence)) == 2
        before_second = company_investment_thesis(
            db, company_id, known_at=second.recorded_at - timedelta(microseconds=1)
        )
        assert before_second.streams[0].current_revision.id == first.id
        first.rationale = "Attempted in-place thesis history edit"
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()

    with Session(postgres_engine) as db, db.begin():
        other_document = SourceDocument(
            company_id=other_company_id,
            security_id=None,
            batch_id=None,
            provider_id="company_source",
            source_name="Other issuer",
            source_jurisdiction=None,
            external_identifier="other-annual-report",
            document_type="ANNUAL_REPORT",
            source_form=None,
            title="Other issuer annual report",
            reporting_period=None,
            fiscal_year=None,
            fiscal_period=None,
            period_end=None,
            filed_at=None,
            published_at=fact_filed.date(),
            canonical_url="https://other.example.test/annual-report.pdf",
            retrieved_at=None,
            recorded_at=fact_recorded,
            is_amendment=False,
            amends_document_id=None,
            supersedes_document_id=None,
            data_quality="PASS",
            quality_reason=None,
            actor="LOCAL_USER",
        )
        db.add(other_document)
        db.flush()
        wrong_owner = contract(
            company_id,
            external_revision_id="thesis-wrong-owner",
            observed_at=now.isoformat(),
            supersedes_revision_id=latest_revision_id,
            claims=[
                {
                    "claim_key": "foreign-evidence",
                    "claim_type": "PRINCIPAL_RISK",
                    "statement": "This claim attempts to cite another company's source.",
                    "evidence": [
                        {
                            "relationship": "CONTRADICTS",
                            "source_document_id": str(other_document.id),
                            "source_name": "Other issuer annual report",
                        }
                    ],
                }
            ],
        )
        with pytest.raises(DomainError, match="does not belong"):
            publish_investment_thesis_revision(db, wrong_owner)
