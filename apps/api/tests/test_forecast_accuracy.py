"""Forecast accuracy must use dated, fiscal-period-aligned canonical observations."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateBatch,
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
    DcfProjection,
    DcfScenarioAssumptions,
    FinancialModel,
    FinancialModelRevision,
    ForecastAccuracyMetric,
    ForecastAccuracySourceType,
    FundamentalMetric,
    FundamentalStatement,
    Listing,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
    ResearchForecast,
    ResearchRevision,
    Security,
)
from portfolio_api.forecast_accuracy import company_forecast_accuracy
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def add_research_forecast(
    session: Session,
    company_id: UUID,
    *,
    revision_number: int,
    observed_at: datetime,
    recorded_at: datetime,
    value: Decimal | None,
    metric: str = "REVENUE",
    fiscal_year: int = 2026,
    fiscal_period: str = "FY",
    period_type: str = "ANNUAL",
    period_end: date | None = date(2026, 12, 31),
    scenario: str = "POINT",
    author_id: str = "research-agent-a",
    stream_key: str = "research-agent/revenue",
    availability_status: str = "AVAILABLE",
    availability_reason: str | None = None,
    supersedes_revision_id: UUID | None = None,
) -> tuple[ResearchRevision, ResearchForecast]:
    revision = ResearchRevision(
        id=uuid4(),
        company_id=company_id,
        security_id=None,
        stream_key=stream_key,
        revision_number=revision_number,
        contract_version="1.0.0",
        external_revision_id=f"forecast-{revision_number}",
        supersedes_revision_id=supersedes_revision_id,
        author_id=author_id,
        source_id="google-sheets",
        source_reference="https://docs.google.com/spreadsheets/d/example/edit",
        observed_at=observed_at,
        recorded_at=recorded_at,
        status="PUBLISHED",
        rationale="Dated research forecast for a point-in-time evaluation.",
        uncertainty=None,
        content_fingerprint=f"{revision_number:064x}",
    )
    session.add(revision)
    session.flush()
    forecast = ResearchForecast(
        id=uuid4(),
        revision_id=revision.id,
        metric=metric,
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_end=period_end,
        scenario=scenario,
        value=value,
        currency="USD",
        unit="currency" if metric != "EPS" else "currency/share",
        availability_status=availability_status,
        availability_reason=availability_reason,
        confidence="HIGH",
        rationale="Source-linked forecast.",
        uncertainty=None,
    )
    session.add(forecast)
    session.flush()
    return revision, forecast


def add_reported_revenue(
    session: Session,
    company_id: UUID,
    *,
    value: Decimal,
    filed_at: datetime | None,
    observed_at: datetime,
    recorded_at: datetime,
    currency: str = "USD",
    period_end: date = date(2026, 12, 31),
    period_type: str = "ANNUAL",
    period_start: date = date(2026, 1, 1),
    fiscal_year: int = 2026,
    fiscal_period: str = "FY",
    supersedes_observation_id: UUID | None = None,
    quality: str = "PASS",
    accession_suffix: str = "1",
) -> ReportedFundamentalObservation:
    batch_id = uuid4()
    session.add(
        ReportedFundamentalBatch(
            id=batch_id,
            provider_id="sec_edgar",
            provider_schema_version="companyfacts-fixture-v1",
            normalizer_version="fixture-v1",
            domain="REPORTED_FUNDAMENTALS",
            source_digest=f"{uuid4().hex}{uuid4().hex[:32]}",
            query_scope={"fixture": True},
            observed_at=observed_at,
            recorded_at=recorded_at,
            provider_summary={},
            reconciliation={},
        )
    )
    session.flush()
    observation = ReportedFundamentalObservation(
        id=uuid4(),
        company_id=company_id,
        security_id=None,
        batch_id=batch_id,
        provider_id="sec_edgar",
        provider_entity_id="0000000001",
        source_priority=10,
        metric=FundamentalMetric.REVENUE.value,
        statement=FundamentalStatement.INCOME_STATEMENT.value,
        period_type=period_type,
        period_start=stamp(f"{period_start.isoformat()}T00:00:00Z"),
        period_end=stamp(f"{period_end.isoformat()}T00:00:00Z"),
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        filed_at=filed_at,
        observed_at=observed_at,
        recorded_at=recorded_at,
        value=value,
        currency=currency,
        unit="currency",
        source_taxonomy="us-gaap",
        source_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        source_unit=currency,
        accession_number=f"0000000001-27-00000{accession_suffix}",
        form="10-K",
        frame=f"CY{fiscal_year}",
        source_record_id=f"fixture:revenue:{accession_suffix}",
        source_url="https://example.test/filing",
        source_ref=f"fixture filing {accession_suffix}",
        observation_fingerprint=f"{accession_suffix:0>64}"[-64:],
        mapping_priority=10,
        revision_context="ORIGINAL"
        if supersedes_observation_id is None
        else "POTENTIAL_RESTATEMENT",
        data_quality=quality,
        quality_reason="Changed later reported value." if quality != "PASS" else None,
        supersedes_observation_id=supersedes_observation_id,
    )
    session.add(observation)
    session.flush()
    return observation


@pytest.mark.integration
def test_research_accuracy_uses_later_actual_and_preserves_forecast_revisions(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Accuracy revenue fixture", reporting_currency="USD", is_demo=False)
        session.add(company)
        session.flush()
        company_id = company.id
        first_revision, first_forecast = add_research_forecast(
            session,
            company_id,
            revision_number=1,
            observed_at=stamp("2026-02-01T09:00:00Z"),
            recorded_at=stamp("2026-02-01T09:05:00Z"),
            value=Decimal("100"),
        )
        second_revision, _ = add_research_forecast(
            session,
            company_id,
            revision_number=2,
            observed_at=stamp("2026-06-01T09:00:00Z"),
            recorded_at=stamp("2026-06-01T09:05:00Z"),
            value=Decimal("110"),
            supersedes_revision_id=first_revision.id,
        )
        add_research_forecast(
            session,
            company_id,
            revision_number=3,
            observed_at=stamp("2026-02-01T09:00:00Z"),
            recorded_at=stamp("2026-02-01T09:05:00Z"),
            value=None,
            metric="EPS",
            availability_status="UNAVAILABLE",
            availability_reason="No EPS estimate was published.",
        )
        add_research_forecast(
            session,
            company_id,
            revision_number=4,
            observed_at=stamp("2026-02-01T09:00:00Z"),
            recorded_at=stamp("2026-02-01T09:05:00Z"),
            value=Decimal("115"),
            scenario="BASE",
        )
        _, quarter_forecast = add_research_forecast(
            session,
            company_id,
            revision_number=5,
            observed_at=stamp("2026-01-15T09:00:00Z"),
            recorded_at=stamp("2026-01-15T09:05:00Z"),
            value=Decimal("25"),
            period_type="QUARTERLY",
            fiscal_period="Q1",
            period_end=date(2026, 3, 31),
        )
        actual = add_reported_revenue(
            session,
            company_id,
            value=Decimal("120"),
            filed_at=stamp("2027-03-01T10:00:00Z"),
            observed_at=stamp("2027-03-01T11:00:00Z"),
            recorded_at=stamp("2027-03-01T11:00:00Z"),
        )
        quarter_actual = add_reported_revenue(
            session,
            company_id,
            value=Decimal("30"),
            filed_at=stamp("2026-05-10T10:00:00Z"),
            observed_at=stamp("2026-05-10T11:00:00Z"),
            recorded_at=stamp("2026-05-10T11:00:00Z"),
            period_end=date(2026, 3, 31),
            period_type="QUARTERLY",
            period_start=date(2026, 1, 1),
            fiscal_period="Q1",
            accession_suffix="3",
        )

        before_publication = company_forecast_accuracy(
            session,
            company_id,
            metric=None,
            outcome_known_at=stamp("2027-02-28T23:59:00Z"),
        )
        old_row = next(
            item
            for item in before_publication.observations
            if item.forecast_id == first_forecast.id
        )
        assert old_row.status == "NOT_REPORTED"
        assert old_row.error.absolute_error is None

        after_publication = company_forecast_accuracy(
            session,
            company_id,
            outcome_known_at=stamp("2027-03-20T00:00:00Z"),
        )
        assert after_publication.total_count == 5
        first = next(
            item for item in after_publication.observations if item.forecast_id == first_forecast.id
        )
        second = next(
            item
            for item in after_publication.observations
            if item.revision_id == second_revision.id and item.metric == "REVENUE"
        )
        unavailable_eps = next(
            item for item in after_publication.observations if item.metric == "EPS"
        )
        conditional = next(
            item for item in after_publication.observations if item.scenario == "BASE"
        )
        quarter = next(
            item
            for item in after_publication.observations
            if item.forecast_id == quarter_forecast.id
        )
        assert first.status == "AVAILABLE"
        assert first.actual.source_observation_id == actual.id
        assert first.error.signed_error == Decimal("-20")
        assert first.error.absolute_error == Decimal("20")
        assert first.error.signed_percentage_error == Decimal("-1") / Decimal("6")
        assert second.status == "AVAILABLE"
        assert second.supersedes_revision_id == first_revision.id
        assert second.error.absolute_error == Decimal("10")
        assert unavailable_eps.status == "FORECAST_UNAVAILABLE"
        assert unavailable_eps.actual.status == "NOT_EVALUATED"
        assert conditional.status == "SCENARIO_NOT_EVALUATED"
        assert conditional.error.absolute_error is None
        assert quarter.status == "AVAILABLE"
        assert quarter.actual.period_type == "QUARTERLY"
        assert quarter.actual.fiscal_period == "Q1"
        assert quarter.actual.source_observation_id == quarter_actual.id

        restatement = add_reported_revenue(
            session,
            company_id,
            value=Decimal("130"),
            filed_at=stamp("2027-04-01T10:00:00Z"),
            observed_at=stamp("2027-04-01T11:00:00Z"),
            recorded_at=stamp("2027-04-01T11:00:00Z"),
            supersedes_observation_id=actual.id,
            quality="DATA_CHECK",
            accession_suffix="2",
        )
        restated = company_forecast_accuracy(
            session,
            company_id,
            metric=ForecastAccuracyMetric.REVENUE,
            outcome_known_at=stamp("2027-04-10T00:00:00Z"),
        )
        restated_first = next(
            item for item in restated.observations if item.forecast_id == first_forecast.id
        )
        assert restated_first.status == "ACTUAL_DATA_CHECK"
        assert restated_first.actual.revision_context == "POTENTIAL_RESTATEMENT"
        assert restated_first.actual.supersedes_observation_id == actual.id
        assert restated_first.actual.source_observation_id == restatement.id
        assert restated_first.error.absolute_error is None


@pytest.mark.integration
def test_accuracy_withholds_currency_mismatch_and_actuals_public_before_forecast(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Accuracy currency fixture", reporting_currency="USD", is_demo=False)
        session.add(company)
        session.flush()
        company_id = company.id
        _revision, forecast = add_research_forecast(
            session,
            company_id,
            revision_number=1,
            observed_at=stamp("2026-02-01T09:00:00Z"),
            recorded_at=stamp("2026-02-01T09:05:00Z"),
            value=Decimal("100"),
        )
        actual = add_reported_revenue(
            session,
            company_id,
            value=Decimal("90"),
            currency="EUR",
            filed_at=stamp("2027-03-01T10:00:00Z"),
            observed_at=stamp("2027-03-01T11:00:00Z"),
            recorded_at=stamp("2027-03-01T11:00:00Z"),
        )
        mismatch = company_forecast_accuracy(
            session, company_id, outcome_known_at=stamp("2027-03-20T00:00:00Z")
        )
        row = next(item for item in mismatch.observations if item.forecast_id == forecast.id)
        assert row.status == "CURRENCY_MISMATCH"
        assert row.actual.currency == "EUR"
        assert row.actual.source_observation_id == actual.id
        assert row.error.absolute_error is None

    with Session(postgres_engine) as session, session.begin():
        company = Company(
            name="Accuracy actual-known fixture", reporting_currency="USD", is_demo=False
        )
        session.add(company)
        session.flush()
        company_id = company.id
        add_reported_revenue(
            session,
            company_id,
            value=Decimal("90"),
            filed_at=stamp("2027-02-01T08:00:00Z"),
            observed_at=stamp("2027-02-01T09:00:00Z"),
            recorded_at=stamp("2027-02-01T09:00:00Z"),
            accession_suffix="4",
        )
        _revision, forecast = add_research_forecast(
            session,
            company_id,
            revision_number=1,
            observed_at=stamp("2027-02-15T09:00:00Z"),
            recorded_at=stamp("2027-02-15T09:05:00Z"),
            value=Decimal("100"),
        )
        row = next(
            item
            for item in company_forecast_accuracy(
                session, company_id, outcome_known_at=stamp("2027-03-20T00:00:00Z")
            ).observations
            if item.forecast_id == forecast.id
        )
        assert row.status == "ACTUAL_KNOWN_AT_FORECAST"
        assert row.error.absolute_error is None


@pytest.mark.integration
def test_consensus_accuracy_uses_selected_provider_and_keeps_each_observation_horizon(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(
            name="Accuracy consensus fixture", reporting_currency="USD", is_demo=False
        )
        session.add(company)
        session.flush()
        company_id = company.id
        mapping = ConsensusEstimateProviderMapping(
            id=uuid4(),
            company_id=company_id,
            listing_id=None,
            provider_id="primary-provider",
            provider_symbol="EXACT",
            role="PRIMARY",
            priority=10,
            currency="USD",
            evidence_source="https://example.test/identity",
            currency_evidence_source="https://example.test/currency",
            effective_from=stamp("2026-01-01T00:00:00Z"),
            recorded_at=stamp("2026-01-01T00:00:00Z"),
            actor="LOCAL_USER",
        )
        fallback = ConsensusEstimateProviderMapping(
            id=uuid4(),
            company_id=company_id,
            listing_id=None,
            provider_id="fallback-provider",
            provider_symbol="OTHER",
            role="FALLBACK",
            priority=1,
            currency="USD",
            evidence_source="https://example.test/fallback-identity",
            currency_evidence_source="https://example.test/fallback-currency",
            effective_from=stamp("2026-01-01T00:00:00Z"),
            recorded_at=stamp("2026-01-01T00:00:00Z"),
            actor="LOCAL_USER",
        )
        session.add_all([mapping, fallback])
        session.flush()

        first_observation_id = None
        for index, observed, value in (
            (1, "2026-02-01T12:00:00Z", Decimal("100")),
            (2, "2026-09-01T12:00:00Z", Decimal("110")),
        ):
            observed_at = stamp(observed)
            batch_id = uuid4()
            session.add(
                ConsensusEstimateBatch(
                    id=batch_id,
                    provider_id="primary-provider",
                    provider_schema_version="fixture-v1",
                    normalizer_version="fixture-v1",
                    domain="CONSENSUS_ESTIMATES",
                    source_kind="PROVIDER_RESPONSE",
                    source_digest=f"{uuid4().hex}{uuid4().hex[:32]}",
                    source_reference="https://example.test/consensus",
                    query_scope={"fixture": True},
                    snapshot_date=observed_at.date(),
                    observed_at=observed_at,
                    recorded_at=observed_at,
                    provider_summary={},
                    reconciliation={},
                )
            )
            session.flush()
            observation = ConsensusEstimateObservation(
                id=uuid4(),
                company_id=company_id,
                listing_id=None,
                provider_mapping_id=mapping.id,
                batch_id=batch_id,
                provider_id="primary-provider",
                metric="REVENUE",
                period_type="ANNUAL",
                forecast_period="FY2026",
                period_end=date(2026, 12, 31),
                value=value,
                low_value=value - Decimal("10"),
                high_value=value + Decimal("10"),
                analyst_count=12,
                currency="USD",
                unit="currency",
                snapshot_date=observed_at.date(),
                observed_at=observed_at,
                recorded_at=observed_at,
                source_record_id=f"primary:{index}",
                source_ref="https://example.test/consensus/history",
                revision_context="SNAPSHOT" if index == 1 else "REVISED",
                data_quality="PASS",
                quality_reason=None,
                supersedes_observation_id=first_observation_id,
            )
            session.add(observation)
            session.flush()
            first_observation_id = observation.id

        fallback_batch_id = uuid4()
        session.add(
            ConsensusEstimateBatch(
                id=fallback_batch_id,
                provider_id="fallback-provider",
                provider_schema_version="fixture-v1",
                normalizer_version="fixture-v1",
                domain="CONSENSUS_ESTIMATES",
                source_kind="PROVIDER_RESPONSE",
                source_digest=f"{uuid4().hex}{uuid4().hex[:32]}",
                source_reference="https://example.test/fallback-consensus",
                query_scope={"fixture": True},
                snapshot_date=date(2026, 10, 1),
                observed_at=stamp("2026-10-01T12:00:00Z"),
                recorded_at=stamp("2026-10-01T12:00:00Z"),
                provider_summary={},
                reconciliation={},
            )
        )
        session.flush()
        session.add(
            ConsensusEstimateObservation(
                id=uuid4(),
                company_id=company_id,
                listing_id=None,
                provider_mapping_id=fallback.id,
                batch_id=fallback_batch_id,
                provider_id="fallback-provider",
                metric="REVENUE",
                period_type="ANNUAL",
                forecast_period="FY2026",
                period_end=date(2026, 12, 31),
                value=Decimal("999"),
                low_value=None,
                high_value=None,
                analyst_count=3,
                currency="USD",
                unit="currency",
                snapshot_date=date(2026, 10, 1),
                observed_at=stamp("2026-10-01T12:00:00Z"),
                recorded_at=stamp("2026-10-01T12:00:00Z"),
                source_record_id="fallback:1",
                source_ref="https://example.test/fallback-consensus/history",
                revision_context="SNAPSHOT",
                data_quality="PASS",
                quality_reason=None,
                supersedes_observation_id=None,
            )
        )
        add_reported_revenue(
            session,
            company_id,
            value=Decimal("120"),
            filed_at=stamp("2027-03-01T10:00:00Z"),
            observed_at=stamp("2027-03-01T11:00:00Z"),
            recorded_at=stamp("2027-03-01T11:00:00Z"),
        )

        read = company_forecast_accuracy(
            session,
            company_id,
            source=ForecastAccuracySourceType.ANALYST_CONSENSUS,
            outcome_known_at=stamp("2027-03-20T00:00:00Z"),
        )
        primary_rows = [row for row in read.observations if row.source_name == "primary-provider"]
        fallback_row = next(
            row for row in read.observations if row.source_name == "fallback-provider"
        )
        assert len(primary_rows) == 2
        assert all(row.status == "AVAILABLE" for row in primary_rows), [
            (row.status, row.status_reason, row.actual.status, row.actual.reason)
            for row in primary_rows
        ]
        assert {row.error.absolute_error for row in primary_rows} == {
            Decimal("20"),
            Decimal("10"),
        }
        assert fallback_row.status == "ALTERNATE_PROVIDER_NOT_SELECTED"
        assert fallback_row.error.absolute_error is None


@pytest.mark.integration
def test_native_model_scenarios_are_not_scored_without_fiscal_period_anchor(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Accuracy model fixture", reporting_currency="USD", is_demo=False)
        session.add(company)
        session.flush()
        security = Security(
            company_id=company.id,
            name="Accuracy common stock",
            security_type="COMMON_STOCK",
            share_class=None,
            underlying_security_id=None,
            is_demo=False,
        )
        session.add(security)
        session.flush()
        listing = Listing(
            security_id=security.id,
            ticker="ACCURACY",
            venue="NASDAQ",
            currency="USD",
            identity_source_ref="synthetic accuracy fixture",
        )
        session.add(listing)
        session.flush()
        model = FinancialModel(
            company_id=company.id,
            valuation_listing_id=listing.id,
            model_type="UFCF_DCF_10Y_FADE",
            model_name="Test operating DCF",
            model_currency="USD",
            source_model_key=None,
            current_revision_id=None,
        )
        session.add(model)
        session.flush()
        revision = FinancialModelRevision(
            model_id=model.id,
            model_type="UFCF_DCF_10Y_FADE",
            revision_number=1,
            base_revision_id=None,
            methodology_version="fixture-v1",
            source_revision_id=None,
            contract_digest=None,
            actor="LOCAL_USER",
            source="test fixture",
            rationale="A model projection is not assigned a fiscal year by revision time.",
            effective_at=stamp("2026-01-01T09:00:00Z"),
            recorded_at=stamp("2026-01-01T09:00:00Z"),
        )
        session.add(revision)
        session.flush()
        model.current_revision_id = revision.id
        for scenario_name, probability in (("BEAR", "0.2"), ("BASE", "0.6"), ("BULL", "0.2")):
            scenario = DcfScenarioAssumptions(
                revision_id=revision.id,
                scenario=scenario_name,
                probability=Decimal(probability),
                terminal_growth=Decimal("0.02"),
                year10_ufcf_growth=Decimal("0.03"),
                rationale="Conditional fixture scenario.",
            )
            session.add(scenario)
            session.flush()
            session.add(
                DcfProjection(
                    scenario_id=scenario.id,
                    forecast_year=1,
                    revenue=Decimal("100"),
                    ebit=Decimal("20"),
                    nopat=Decimal("15"),
                    depreciation_amortization=Decimal("2"),
                    capex=Decimal("3"),
                    net_working_capital=Decimal("1"),
                    change_in_nwc=Decimal("1"),
                    unlevered_free_cash_flow=Decimal("13"),
                    revenue_growth=Decimal("0.1"),
                    discount_rate=Decimal("0.1"),
                    discount_factor=Decimal("0.9"),
                    present_value_ufcf=Decimal("11.7"),
                    terminal_value=None,
                )
            )
        session.flush()

        read = company_forecast_accuracy(
            session,
            company.id,
            metric=ForecastAccuracyMetric.REVENUE,
            source=ForecastAccuracySourceType.FINANCIAL_MODEL,
            outcome_known_at=stamp("2026-12-31T23:59:00Z"),
        )
        assert read.total_count == 3
        assert {row.status for row in read.observations} == {"SCENARIO_NOT_EVALUATED"}
        assert all(row.forecast_year == 1 and row.fiscal_year is None for row in read.observations)
        assert all(
            row.actual.status == "FISCAL_PERIOD_MAPPING_UNAVAILABLE" for row in read.observations
        )
        assert all(row.observed_at is None for row in read.observations)
        assert all(row.effective_at == stamp("2026-01-01T09:00:00Z") for row in read.observations)
        assert all(row.error.absolute_error is None for row in read.observations)


@pytest.mark.integration
def test_accuracy_requires_later_publication_and_handles_zero_actual(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(
            name="Accuracy time precision fixture", reporting_currency="USD", is_demo=False
        )
        session.add(company)
        session.flush()
        company_id = company.id
        add_reported_revenue(
            session,
            company_id,
            value=Decimal("90"),
            filed_at=stamp("2027-03-01T10:00:00Z"),
            observed_at=stamp("2026-12-01T10:00:00Z"),
            recorded_at=stamp("2026-12-01T10:01:00Z"),
        )
        _revision, known_before_forecast = add_research_forecast(
            session,
            company_id,
            revision_number=1,
            observed_at=stamp("2026-11-15T09:00:00Z"),
            recorded_at=stamp("2026-12-15T09:00:00Z"),
            value=Decimal("100"),
        )
        first = company_forecast_accuracy(
            session,
            company_id,
            outcome_known_at=stamp("2027-03-20T00:00:00Z"),
        )
        first_row = next(
            row for row in first.observations if row.forecast_id == known_before_forecast.id
        )
        assert first_row.status == "ACTUAL_KNOWN_AT_FORECAST"
        assert first_row.error.absolute_error is None

    with Session(postgres_engine) as session, session.begin():
        company = Company(
            name="Accuracy zero actual fixture", reporting_currency="USD", is_demo=False
        )
        session.add(company)
        session.flush()
        company_id = company.id
        _revision, forecast = add_research_forecast(
            session,
            company_id,
            revision_number=1,
            observed_at=stamp("2026-02-01T09:00:00Z"),
            recorded_at=stamp("2026-02-01T09:05:00Z"),
            value=Decimal("5"),
        )
        add_reported_revenue(
            session,
            company_id,
            value=Decimal("0"),
            filed_at=stamp("2027-03-01T10:00:00Z"),
            observed_at=stamp("2027-03-01T11:00:00Z"),
            recorded_at=stamp("2027-03-01T11:00:00Z"),
            accession_suffix="5",
        )
        row = next(
            row
            for row in company_forecast_accuracy(
                session,
                company_id,
                outcome_known_at=stamp("2027-03-20T00:00:00Z"),
            ).observations
            if row.forecast_id == forecast.id
        )
        assert row.status == "AVAILABLE"
        assert row.error.absolute_error == Decimal("5")
        assert row.error.absolute_percentage_error is None
        assert row.error.status == "RELATIVE_ERROR_UNDEFINED_ZERO_ACTUAL"


@pytest.mark.integration
def test_aggregates_require_distinct_periods_and_keep_authors_separate(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Accuracy summary fixture", reporting_currency="USD", is_demo=False)
        session.add(company)
        session.flush()
        company_id = company.id

        for index, fiscal_year in enumerate(range(2020, 2025), start=1):
            end = date(fiscal_year, 12, 31)
            for author in ("agent-a", "agent-b"):
                add_research_forecast(
                    session,
                    company_id,
                    revision_number=index,
                    observed_at=stamp(f"{fiscal_year}-01-15T09:00:00Z"),
                    recorded_at=stamp(f"{fiscal_year}-01-15T09:01:00Z"),
                    value=Decimal("100"),
                    fiscal_year=fiscal_year,
                    period_end=end,
                    author_id=author,
                    stream_key=f"{author}/revenue",
                )
            add_reported_revenue(
                session,
                company_id,
                value=Decimal("110"),
                filed_at=stamp(f"{fiscal_year + 1}-03-01T10:00:00Z"),
                observed_at=stamp(f"{fiscal_year + 1}-03-01T11:00:00Z"),
                recorded_at=stamp(f"{fiscal_year + 1}-03-01T11:00:00Z"),
                period_end=end,
                period_start=date(fiscal_year, 1, 1),
                fiscal_year=fiscal_year,
                accession_suffix=str(index),
            )

        read = company_forecast_accuracy(
            session,
            company_id,
            source=ForecastAccuracySourceType.AGENT_RESEARCH,
            outcome_known_at=stamp("2026-06-01T00:00:00Z"),
        )
        summaries = {summary.source_name: summary for summary in read.summaries}
        assert set(summaries) == {"agent-a", "agent-b"}
        assert all(summary.sample_count == 5 for summary in summaries.values())
        assert all(summary.status == "AVAILABLE" for summary in summaries.values())
        for summary in summaries.values():
            assert summary.mean_absolute_percentage_error is not None
            assert abs(
                summary.mean_absolute_percentage_error - Decimal(10) / Decimal(110)
            ) < Decimal("0.000000000000000000000000001")


@pytest.mark.integration
def test_forecast_accuracy_api_returns_contract_and_requires_aware_cutoff(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Accuracy API fixture", reporting_currency="USD", is_demo=False)
        session.add(company)
        session.flush()
        company_id = company.id

    app = create_app(Settings(database_url=None))
    with TestClient(app) as client:
        app.state.database_engine = postgres_engine
        response = client.get(
            f"/v1/companies/{company_id}/forecast-accuracy",
            params={
                "metric": "REVENUE",
                "source": "ANALYST_CONSENSUS",
                "outcome_known_at": "2026-10-15T23:59:59Z",
                "limit": 10,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["company_id"] == str(company_id)
        assert body["selected_metric"] == "REVENUE"
        assert body["selected_source"] == "ANALYST_CONSENSUS"
        assert body["observations"] == []
        assert body["summaries"] == []

        naive_cutoff = client.get(
            f"/v1/companies/{company_id}/forecast-accuracy",
            params={"outcome_known_at": "2026-10-15T23:59:59"},
        )
        assert naive_cutoff.status_code == 422
