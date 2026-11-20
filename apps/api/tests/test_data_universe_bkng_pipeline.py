"""Real Booking issuer metrics through a reviewed synthetic canonical identity.

SEC values are sourced from the Booking Q3 2026 10-Q. The database, issuer
crosswalk and role credentials are isolated test fixtures, not owner state.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.data_universe_proposal_handoff import prepare_handoff
from portfolio_api.data_universe_public_evidence import (
    BKNG_Q3_2026_CIK,
    verify_booking_q3_2026_pack,
)
from portfolio_api.data_universe_shadow import EvidencePackV1
from portfolio_api.domain.models import Company, CompanyProviderIdentifier, Listing, Security
from portfolio_api.main import create_app
from portfolio_api.reported_fundamentals import SEC_PROVIDER_ID
from portfolio_api.settings import Settings

pytestmark = pytest.mark.integration

HERE = Path(__file__).parent / "fixtures"
AGENT = "synthetic-booking-agent-0000000000000000000"
REVIEWER = "synthetic-booking-reviewer-000000000000000"
READ = "synthetic-booking-scoped-read-00000000000000"


def test_booking_sec_cik_to_reviewed_kpis_full_loop(postgres_engine: Engine) -> None:
    pack = EvidencePackV1.model_validate_json(
        (HERE / "data_universe_bkng_q3_2026.json").read_text(encoding="utf-8")
    )
    verified = verify_booking_q3_2026_pack(
        pack, (HERE / "data_universe_bkng_q3_2026_excerpt.html").read_bytes()
    )
    company_id, security_id = uuid4(), uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(Company(id=company_id, name="Booking Holdings Inc.", reporting_currency="USD"))
        session.flush()
        session.add(
            Security(
                id=security_id,
                company_id=company_id,
                name="Booking Holdings common stock",
                security_type="COMMON_STOCK",
            )
        )
        session.add(
            CompanyProviderIdentifier(
                company_id=company_id,
                provider_id=SEC_PROVIDER_ID,
                identifier_type="SEC_CIK",
                identifier_value=BKNG_Q3_2026_CIK,
                provider_company_name="Booking Holdings Inc.",
                evidence_source="https://www.sec.gov/Archives/edgar/data/1075531/000107553126000045/0001075531-26-000045-index.htm",
                effective_at=datetime(2026, 11, 3, tzinfo=UTC),
                actor="LOCAL_USER",
            )
        )
        session.flush()
        session.add(
            Listing(
                security_id=security_id,
                venue="NASDAQ",
                ticker="BKNG",
                currency="USD",
            )
        )

    # The crosswalk is already the application's operator-reviewed issuer
    # identity. Never substitute an inferred ticker or hard-coded company UUID.
    with Session(postgres_engine) as session:
        resolved = session.scalars(
            select(CompanyProviderIdentifier.company_id).where(
                CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
                CompanyProviderIdentifier.identifier_type == "SEC_CIK",
                CompanyProviderIdentifier.identifier_value == BKNG_Q3_2026_CIK,
            )
        ).all()
    assert resolved == [company_id]

    settings = Settings(
        _env_file=None,
        app_env="development",
        data_universe_read_enabled=True,
        data_universe_read_token=SecretStr(READ),
        data_universe_read_company_ids=str(company_id),
        observation_proposals_enabled=True,
        observation_acceptance_enabled=True,
        observation_proposal_agent_token=SecretStr(AGENT),
        observation_proposal_agent_id="synthetic-booking-agent",
        observation_proposal_reviewer_token=SecretStr(REVIEWER),
        observation_proposal_reviewer_id="synthetic-booking-human-reviewer",
    )
    url = f"/v1/companies/{company_id}/agent-context"
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(settings)) as client,
    ):
        for phase in ("definitions", "actuals"):
            response = client.get(url, headers={"X-Data-Universe-Read-Token": READ})
            assert response.status_code == 200, response.text
            context = CompanyAgentContextV1.model_validate(response.json())
            assert context.company.name == "Booking Holdings Inc."
            assert [item.ticker for item in context.listings] == ["BKNG"]
            assert context.sec_identity is not None
            assert context.sec_identity.status == "MAPPED"
            assert context.sec_identity.cik == BKNG_Q3_2026_CIK
            assert context.sec_identity.evidence_source is not None
            if phase == "definitions":
                with pytest.raises(ValueError, match="reviewed matching SEC CIK"):
                    prepare_handoff(context.model_copy(update={"sec_identity": None}), pack, verified)
                wrong = context.sec_identity.model_copy(update={"cik": "0001234567"})
                with pytest.raises(ValueError, match="reviewed matching SEC CIK"):
                    prepare_handoff(
                        context.model_copy(update={"sec_identity": wrong}), pack, verified
                    )
            assert context.portfolio_status.status == "UNSUPPORTED"
            assert context.native_models_status.status == "UNSUPPORTED"
            handoff = prepare_handoff(context, pack, verified)
            target_type = (
                "MetricDefinitionBatchV1" if phase == "definitions" else "KPIObservationBatchV1"
            )
            assert [batch["contract_type"] for batch in handoff["ready_batches"]] == [target_type]
            batch = handoff["ready_batches"][0]
            submitted = client.post(
                "/v1/company-observation-proposals",
                json=batch,
                headers={"X-Observation-Proposal-Token": AGENT},
            )
            assert submitted.status_code == 201, submitted.text
            ident = submitted.json()["proposal"]["id"]
            assert submitted.json()["replayed"] is False
            replay = client.post(
                "/v1/company-observation-proposals",
                json=batch,
                headers={"X-Observation-Proposal-Token": AGENT},
            )
            assert replay.status_code == 200
            assert replay.json()["replayed"] is True
            assert replay.json()["proposal"]["id"] == ident
            preview = client.post(
                f"/v1/company-observation-proposals/{ident}/preview",
                headers={"X-Observation-Proposal-Token": REVIEWER},
            )
            assert preview.status_code == 200
            assert preview.json()["status"] == "READY", preview.text
            accepted = client.post(
                f"/v1/company-observation-proposals/{ident}/accept",
                headers={"X-Observation-Proposal-Token": REVIEWER},
                json={
                    "preview_fingerprint": preview.json()["preview_fingerprint"],
                    "decision_note": "Reviewed Booking SEC 10-Q period, source and rounded units.",
                },
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["status"] == "ACCEPTED"

        result = client.get(url, headers={"X-Data-Universe-Read-Token": READ})
        assert result.status_code == 200
        current = CompanyAgentContextV1.model_validate(result.json())
        values = {row.metric_id: row for row in current.metric_observations}
        assert set(values) == {
            "bkng.room_nights",
            "bkng.flight_tickets",
            "bkng.gross_bookings",
        }
        assert values["bkng.room_nights"].value == Decimal("345")
        assert values["bkng.flight_tickets"].value == Decimal("21")
        assert values["bkng.gross_bookings"].value == Decimal("54461")
        assert values["bkng.gross_bookings"].currency == "USD"
        assert all(row.value_qualifier == "APPROX" for row in values.values())
        assert all(row.reported_at is None for row in values.values())
        assert all(row.source_reference == pack.source_reference for row in values.values())
        assert not current.guidance_observations
        finished = prepare_handoff(current, pack, verified)
        assert finished["shadow_status"] == "MATCHED"
        assert finished["ready_batches"] == []
        assert finished["candidate_submission"]["status"] == "NOT_ATTEMPTED"
