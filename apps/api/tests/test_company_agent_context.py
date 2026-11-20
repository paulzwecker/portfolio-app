"""CompanyAgentContextV1 read boundary, temporal semantics and portfolio identity."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.company_observations import (
    CompanyGuidanceObservation,
    CompanyMetricDefinition,
    CompanyMetricObservation,
)
from portfolio_api.domain.models import Company, CompanyProviderIdentifier, Portfolio

pytestmark = pytest.mark.integration


def _company(session: Session) -> Company:
    company = Company(name="Agent Context Synthetic", reporting_currency="USD")
    session.add(company)
    session.flush()
    return company


def test_agent_context_has_explicit_empty_sections_and_unknown_company_404(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = _company(session)
        company_id = company.id

    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        response = client.get(f"/v1/companies/{company_id}/agent-context")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["contract_type"] == "CompanyAgentContextV1"
        assert body["contract_version"] == "1.0.0"
        assert body["company"]["id"] == str(company_id)
        assert body["metrics_status"]["status"] == "NO_DATA"
        assert body["guidance_status"]["status"] == "NO_DATA"
        assert body["consensus_status"]["status"] == "NO_DATA"
        assert body["native_models_status"]["status"] == "NO_DATA"
        assert body["portfolio_status"]["status"] == "NO_DATA"
        assert body["resource_links"]["financial_statements"].startswith("/v1/")
        assert client.get(f"/v1/companies/{uuid4()}/agent-context").status_code == 404
        assert (
            client.get(
                f"/v1/companies/{company_id}/agent-context",
                params={"known_at": "2026-10-01T12:00:00"},
            ).status_code
            == 422
        )


def test_agent_context_explicit_portfolio_selection(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = _company(session)
        first = Portfolio(name="Alpha", base_currency="EUR")
        second = Portfolio(name="Beta", base_currency="EUR")
        session.add_all([first, second])
        session.flush()
        company_id, first_id = company.id, first.id

    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        ambiguous = client.get(f"/v1/companies/{company_id}/agent-context")
        assert ambiguous.status_code == 200
        assert ambiguous.json()["portfolio_status"]["status"] == "AMBIGUOUS"
        assert ambiguous.json()["portfolio_id"] is None
        selected = client.get(
            f"/v1/companies/{company_id}/agent-context",
            params={"portfolio_id": str(first_id)},
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["portfolio_id"] == str(first_id)
        assert selected.json()["portfolio_status"]["status"] == "NO_DATA"
        assert (
            client.get(
                f"/v1/companies/{company_id}/agent-context",
                params={"portfolio_id": str(uuid4())},
            ).status_code
            == 404
        )


def test_future_target_guidance_is_visible_when_already_known(
    postgres_engine: Engine,
) -> None:
    reported = datetime.now(UTC) - timedelta(days=2)
    before = reported - timedelta(hours=1)
    with Session(postgres_engine) as session, session.begin():
        company = _company(session)
        company.created_at = reported - timedelta(days=3)
        definition = CompanyMetricDefinition(
            metric_key="synthetic.context.trips",
            company_id=company.id,
            display_name="Trips",
            category="OPERATING",
            value_kind="COUNT",
            canonical_unit="trips",
            canonical_scale=Decimal(1),
            currency_policy="NONE",
            aggregation_semantics="PERIOD_FLOW",
            default_period_type="QUARTER",
            default_basis="REPORTED",
            scope_dimensions=[],
            actuals_allowed=True,
            guidance_allowed=True,
            consensus_allowed=False,
            model_driver_allowed=False,
            active=True,
            description="Synthetic",
            source_reference="https://example.com/metric",
            created_at=reported - timedelta(days=2),
        )
        session.add(definition)
        session.flush()
        session.add(
            CompanyGuidanceObservation(
                external_guidance_id="context-next-quarter",
                company_id=company.id,
                metric_definition_id=definition.id,
                period_type="QUARTER",
                period_start=date(2027, 1, 1),
                period_end=date(2027, 3, 31),
                fiscal_year=2027,
                fiscal_quarter=1,
                lower_value=Decimal("10"),
                midpoint_value=None,
                upper_value=Decimal("12"),
                value_qualifier="RANGE",
                unit="trips",
                scale=Decimal(1),
                currency=None,
                basis="COMPANY_GUIDANCE",
                scope_json={},
                issued_at=reported,
                source_type="EARNINGS_RELEASE",
                source_reference="https://example.com/guidance",
                status="ACTIVE",
                recorded_at=reported,
            )
        )
        session.add(
            CompanyMetricObservation(
                external_observation_id="context-prior-trips",
                company_id=company.id,
                metric_definition_id=definition.id,
                period_type="QUARTER",
                period_start=date(2026, 7, 1),
                period_end=date(2026, 9, 30),
                fiscal_year=2026,
                fiscal_quarter=3,
                value=Decimal("9"),
                value_qualifier="GT",
                unit="trips",
                scale=Decimal(1),
                currency=None,
                basis="REPORTED",
                scope_json={},
                reported_at=reported,
                source_type="EARNINGS_RELEASE",
                source_reference="https://example.com/actual",
                quality_status="VERIFIED",
                quality_reason=None,
                recorded_at=reported,
            )
        )
        company_id = company.id

    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        after = client.get(
            f"/v1/companies/{company_id}/agent-context",
            params={"as_of": reported.date().isoformat(), "known_at": reported.isoformat()},
        )
        assert after.status_code == 200, after.text
        payload = after.json()
        assert len(payload["guidance_observations"]) == 1
        assert payload["guidance_observations"][0]["period_end"] == "2027-03-31"
        assert payload["metric_observations"][0]["value_qualifier"] == "GT"
        assert payload["imported_outputs_status"]["status"] == "UNSUPPORTED"
        earlier = client.get(
            f"/v1/companies/{company_id}/agent-context",
            params={"as_of": before.date().isoformat(), "known_at": before.isoformat()},
        )
        assert earlier.status_code == 200, earlier.text
        assert earlier.json()["guidance_observations"] == []
        assert earlier.json()["metric_observations"] == []


def test_agent_context_sec_mapping_is_public_and_point_in_time(
    postgres_engine: Engine,
) -> None:
    """No ticker-based CIK inference, even for an otherwise valid company."""
    company_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Booking Holdings Inc.",
                reporting_currency="USD",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.flush()
        session.add(
            CompanyProviderIdentifier(
                company_id=company_id,
                provider_id="sec_edgar",
                identifier_type="SEC_CIK",
                identifier_value="0001075531",
                provider_company_name="Booking Holdings Inc.",
                evidence_source=(
                    "https://www.sec.gov/Archives/edgar/data/1075531/"
                    "000107553126000045/0001075531-26-000045-index.htm"
                ),
                effective_at=datetime(2026, 11, 3, tzinfo=UTC),
                recorded_at=datetime(2026, 11, 3, tzinfo=UTC),
                actor="LOCAL_USER",
            )
        )

    path = f"/v1/companies/{company_id}/agent-context"
    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        before = client.get(path, params={"known_at": "2026-10-20T12:00:00Z"})
        assert before.status_code == 200, before.text
        assert before.json()["sec_identity"]["status"] == "UNMAPPED"
        assert before.json()["sec_identity"]["cik"] is None

        after = client.get(path)
        assert after.status_code == 200, after.text
        identity = after.json()["sec_identity"]
        assert identity["status"] == "MAPPED"
        assert identity["cik"] == "0001075531"
        assert identity["evidence_source"].startswith("https://www.sec.gov/")
        assert identity["recorded_at"] is not None

    # Multiple known CIK records cannot silently select one for the steward.
    with Session(postgres_engine) as session, session.begin():
        session.add(
            CompanyProviderIdentifier(
                company_id=company_id,
                provider_id="sec_edgar",
                identifier_type="SEC_CIK",
                identifier_value="0009999999",
                provider_company_name="Booking Holdings Inc.",
                evidence_source="https://www.sec.gov/Archives/edgar/data/9999999/",
                effective_at=datetime(2026, 11, 4, tzinfo=UTC),
                recorded_at=datetime(2026, 11, 4, tzinfo=UTC),
                actor="LOCAL_USER",
            )
        )
    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        ambiguous = client.get(path)
        assert ambiguous.status_code == 200, ambiguous.text
        assert ambiguous.json()["sec_identity"]["status"] == "AMBIGUOUS"
        assert ambiguous.json()["sec_identity"]["cik"] is None
