"""Canonical company KPI, guidance, and model-driver observation contracts."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from portfolio_api.company_observations import (
    CompanyGuidanceObservation,
    CompanyMetricDefinition,
    CompanyMetricObservation,
    FinancialModelDriverProjection,
    company_guidance_history,
    company_metric_history,
    metric_definitions,
    model_driver_projections,
)
from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelRevision,
    Listing,
    Security,
)

pytestmark = pytest.mark.integration


def seed_company(session: Session) -> tuple[Company, Listing]:
    company = Company(name="Synthetic Mobility", reporting_currency="USD")
    session.add(company)
    session.flush()
    security = Security(
        company_id=company.id,
        name="Synthetic Mobility common",
        security_type="COMMON_STOCK",
        share_class=None,
        underlying_security_id=None,
    )
    session.add(security)
    session.flush()
    listing = Listing(
        security_id=security.id,
        venue="NYSE",
        ticker="SMOB",
        currency="USD",
        identity_source_ref="https://example.com/identity",
    )
    session.add(listing)
    session.flush()
    return company, listing


def metric(
    session: Session,
    company: Company,
    *,
    key: str = "synthetic.gross_bookings",
    display_name: str = "Gross Bookings",
    value_kind: str = "CURRENCY",
    canonical_unit: str = "currency",
) -> CompanyMetricDefinition:
    definition = CompanyMetricDefinition(
        metric_key=key,
        company_id=company.id,
        display_name=display_name,
        category="OPERATING",
        value_kind=value_kind,
        canonical_unit=canonical_unit,
        canonical_scale=Decimal("1000000000"),
        currency_policy="REQUIRED",
        aggregation_semantics="PERIOD_FLOW",
        default_period_type="QUARTER",
        default_basis="REPORTED",
        scope_dimensions=["segment", "geography"],
        actuals_allowed=True,
        guidance_allowed=True,
        consensus_allowed=False,
        model_driver_allowed=True,
        active=True,
        description="Synthetic platform gross bookings.",
        source_reference="https://example.com/metric-definition",
    )
    session.add(definition)
    session.flush()
    return definition


def test_metric_actual_guidance_and_driver_histories_are_explicit_and_append_only(
    postgres_engine,
) -> None:
    recorded = datetime(2026, 11, 19, 12, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        company, listing = seed_company(session)
        definition = metric(session, company)
        original = CompanyMetricObservation(
            external_observation_id="smob-q3-gb-v1",
            company_id=company.id,
            metric_definition_id=definition.id,
            period_type="QUARTER",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 9, 30),
            fiscal_year=2026,
            fiscal_quarter=3,
            value=Decimal("59.8"),
            value_qualifier="EQ",
            unit="currency",
            scale=Decimal("1000000000"),
            currency="USD",
            basis="REPORTED",
            scope_json={},
            reported_at=recorded,
            source_type="EARNINGS_RELEASE",
            source_reference="https://example.com/q3",
            quality_status="VERIFIED",
            quality_reason=None,
            recorded_at=recorded,
        )
        session.add(original)
        session.flush()
        corrected = CompanyMetricObservation(
            external_observation_id="smob-q3-gb-v2",
            company_id=company.id,
            metric_definition_id=definition.id,
            period_type="QUARTER",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 9, 30),
            fiscal_year=2026,
            fiscal_quarter=3,
            value=Decimal("60.1"),
            value_qualifier="EQ",
            unit="currency",
            scale=Decimal("1000000000"),
            currency="USD",
            basis="RESTATED",
            scope_json={},
            reported_at=recorded + timedelta(hours=1),
            source_type="EARNINGS_RELEASE",
            source_reference="https://example.com/q3-corrected",
            quality_status="RESTATED",
            quality_reason="Synthetic correction",
            supersedes_observation_id=original.id,
            recorded_at=recorded + timedelta(hours=1),
        )
        session.add(corrected)

        guidance = CompanyGuidanceObservation(
            external_guidance_id="smob-q4-gb-guidance",
            company_id=company.id,
            metric_definition_id=definition.id,
            period_type="QUARTER",
            period_start=date(2026, 10, 1),
            period_end=date(2026, 12, 31),
            fiscal_year=2026,
            fiscal_quarter=4,
            lower_value=Decimal("63.25"),
            midpoint_value=None,
            upper_value=Decimal("65.25"),
            value_qualifier="RANGE",
            unit="currency",
            scale=Decimal("1000000000"),
            currency="USD",
            basis="COMPANY_GUIDANCE",
            scope_json={},
            issued_at=recorded,
            source_type="EARNINGS_RELEASE",
            source_reference="https://example.com/q3",
            status="ACTIVE",
            recorded_at=recorded,
        )
        session.add(guidance)

        model = FinancialModel(
            company_id=company.id,
            valuation_listing_id=listing.id,
            model_type="UFCF_DCF_10Y_FADE",
            model_name="Synthetic DCF",
            model_currency="USD",
            source_model_key="P-SMOB",
        )
        session.add(model)
        session.flush()
        revision = FinancialModelRevision(
            model_id=model.id,
            model_type="UFCF_DCF_10Y_FADE",
            revision_number=1,
            base_revision_id=None,
            methodology_version="synthetic-v1",
            source_revision_id="synthetic-r1",
            contract_digest=None,
            proposal_author_id=None,
            proposal_authored_at=None,
            proposal_source_reference=None,
            actor="LOCAL_USER",
            source="https://example.com/model",
            rationale="Synthetic accepted model",
            effective_at=recorded,
            recorded_at=recorded,
        )
        session.add(revision)
        session.flush()
        model.current_revision_id = revision.id
        driver = FinancialModelDriverProjection(
            external_driver_id="synthetic-r1-base-gb-2027",
            model_id=model.id,
            revision_id=revision.id,
            scenario="BASE",
            metric_definition_id=definition.id,
            forecast_year=1,
            period_type="FY",
            period_start=date(2027, 1, 1),
            period_end=date(2027, 12, 31),
            value=Decimal("300"),
            value_qualifier="EQ",
            unit="currency",
            scale=Decimal("1000000000"),
            currency="USD",
            basis="MODEL_DRIVER",
            scope_json={},
            rationale="Explicitly underwritten bookings path",
            recorded_at=recorded,
        )
        session.add(driver)
        company_id, model_id, revision_id, original_id = (
            company.id,
            model.id,
            revision.id,
            original.id,
        )

    with Session(postgres_engine) as session:
        definitions = metric_definitions(session, company_id)
        assert [row.metric_id for row in definitions] == ["synthetic.gross_bookings"]
        actuals = company_metric_history(session, company_id, "synthetic.gross_bookings")
        assert [row.external_observation_id for row in actuals] == [
            "smob-q3-gb-v2",
            "smob-q3-gb-v1",
        ]
        assert actuals[0].is_current and not actuals[1].is_current
        assert actuals[0].value == Decimal("60.100000000000")
        guidance_rows = company_guidance_history(
            session, company_id, "synthetic.gross_bookings", current_only=True
        )
        assert len(guidance_rows) == 1 and guidance_rows[0].lower_value == Decimal(
            "63.250000000000"
        )
        drivers = model_driver_projections(session, model_id, revision_id)
        assert len(drivers) == 1
        assert drivers[0].scenario == "BASE"
        assert drivers[0].metric_id == "synthetic.gross_bookings"

    with Session(postgres_engine) as session:
        row = session.get(CompanyMetricObservation, original_id)
        assert row is not None
        row.value = Decimal("999")
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()


def test_company_observation_read_endpoints_preserve_units_sources_and_qualifiers(
    postgres_engine,
) -> None:
    observed = datetime(2026, 11, 19, 12, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        company, _ = seed_company(session)
        definition = metric(
            session,
            company,
            key="synthetic.trips",
            display_name="Trips",
            value_kind="COUNT",
            canonical_unit="trips",
        )
        session.add(
            CompanyMetricObservation(
                external_observation_id="smob-q3-trips",
                company_id=company.id,
                metric_definition_id=definition.id,
                period_type="QUARTER",
                period_start=date(2026, 7, 1),
                period_end=date(2026, 9, 30),
                fiscal_year=2026,
                fiscal_quarter=3,
                value=Decimal("4.1"),
                value_qualifier="GT",
                unit="trips",
                scale=Decimal("1000000000"),
                currency=None,
                basis="REPORTED",
                scope_json={"platform": "all"},
                reported_at=observed,
                source_type="EARNINGS_RELEASE",
                source_reference="https://example.com/q3",
                quality_status="VERIFIED",
                quality_reason=None,
                recorded_at=observed,
            )
        )
        company_id = company.id

    with TestClient(fixture_application(postgres_engine, fixture_settings())) as client:
        definitions = client.get(
            "/v1/company-metric-definitions",
            params={"company_id": str(company_id)},
        )
        assert definitions.status_code == 200
        assert definitions.json()[0]["metric_id"] == "synthetic.trips"
        response = client.get(
            f"/v1/companies/{company_id}/metric-observations",
            params={"metric_id": "synthetic.trips"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["value"] == "4.100000000000"
        assert payload[0]["value_qualifier"] == "GT"
        assert payload[0]["unit"] == "trips"
        assert payload[0]["scale"] == "1000000000.000000000000"
        assert payload[0]["source_reference"] == "https://example.com/q3"
