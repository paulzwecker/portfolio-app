"""Temporal alignment integration checks against migrated domain timestamps."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateProviderMapping,
    DcfProjection,
    DcfScenarioAssumptions,
    FinancialModel,
    FinancialModelRevision,
    FundamentalMetric,
    FundamentalPeriodType,
    Listing,
    PriceObservation,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
    Security,
)
from portfolio_api.temporal_alignment import company_temporal_alignment


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def test_temporal_alignment_rejects_naive_or_future_forecast_knowledge() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        company_temporal_alignment(
            cast(Session, None),
            uuid4(),
            fiscal_year=2027,
            as_of=date(2026, 10, 5),
            known_at=datetime(2026, 10, 5, 12),
        )
    with pytest.raises(ValueError, match="cannot be later"):
        company_temporal_alignment(
            cast(Session, None),
            uuid4(),
            fiscal_year=2027,
            as_of=date(2026, 10, 5),
            known_at=stamp("2026-10-06T00:00:00"),
        )


def test_temporal_alignment_respects_intraday_effective_and_knowledge_cutoffs(
    postgres_engine: Engine,
) -> None:
    company_id, security_id, listing_id, model_id = (uuid4() for _ in range(4))
    early_revision_id, late_revision_id = uuid4(), uuid4()
    batch_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        company = Company(id=company_id, name="Temporal fixture", reporting_currency="USD")
        security = Security(
            id=security_id,
            company_id=company_id,
            name="Temporal fixture common stock",
            security_type="COMMON_STOCK",
            share_class=None,
            underlying_security_id=None,
        )
        listing = Listing(
            id=listing_id,
            security_id=security_id,
            ticker="TIME",
            venue="NASDAQ",
            currency="USD",
            identity_source_ref="synthetic temporal fixture",
        )
        model = FinancialModel(
            id=model_id,
            company_id=company_id,
            valuation_listing_id=listing_id,
            model_type="UFCF_DCF_10Y_FADE",
            model_name="Temporal fixture DCF",
            model_currency="USD",
            source_model_key=None,
            current_revision_id=None,
        )
        session.add_all([company, security])
        session.flush()
        session.add(listing)
        session.flush()
        session.add(model)
        session.flush()

        revisions = [
            FinancialModelRevision(
                id=early_revision_id,
                model_id=model_id,
                model_type="UFCF_DCF_10Y_FADE",
                revision_number=1,
                base_revision_id=None,
                methodology_version="fixture-v1",
                source_revision_id=None,
                contract_digest=None,
                actor="LOCAL_USER",
                source="test fixture",
                rationale="Known at the forecast cutoff.",
                effective_at=stamp("2026-10-01T09:00:00"),
                recorded_at=stamp("2026-10-01T09:00:00"),
            ),
            FinancialModelRevision(
                id=late_revision_id,
                model_id=model_id,
                model_type="UFCF_DCF_10Y_FADE",
                revision_number=2,
                base_revision_id=early_revision_id,
                methodology_version="fixture-v1",
                source_revision_id=None,
                contract_digest=None,
                actor="LOCAL_USER",
                source="test fixture",
                rationale="Effective after the intraday forecast cutoff.",
                effective_at=stamp("2026-10-05T16:00:00"),
                recorded_at=stamp("2026-10-05T10:00:00"),
            ),
        ]
        session.add_all(revisions)
        session.flush()
        model.current_revision_id = late_revision_id

        for revision_id, revenue in (
            (early_revision_id, Decimal("120")),
            (late_revision_id, Decimal("999")),
        ):
            scenario_id = uuid4()
            session.add(
                DcfScenarioAssumptions(
                    id=scenario_id,
                    revision_id=revision_id,
                    scenario="BASE",
                    probability=Decimal("0.6"),
                    terminal_growth=Decimal("0.02"),
                    year10_ufcf_growth=Decimal("0.03"),
                    rationale="Synthetic fixture only.",
                )
            )
            session.flush()
            session.add(
                DcfProjection(
                    id=uuid4(),
                    scenario_id=scenario_id,
                    forecast_year=1,
                    revenue=revenue,
                    ebit=Decimal("1"),
                    nopat=Decimal("1"),
                    depreciation_amortization=Decimal("0"),
                    capex=Decimal("0"),
                    net_working_capital=Decimal("0"),
                    change_in_nwc=Decimal("0"),
                    unlevered_free_cash_flow=Decimal("1"),
                    revenue_growth=Decimal("0.1"),
                    discount_rate=Decimal("0.1"),
                    discount_factor=Decimal("1"),
                    present_value_ufcf=Decimal("1"),
                    terminal_value=None,
                )
            )

        # Effective at 16:00 but recorded at 10:00: not known/effective at noon.
        session.add(
            ConsensusEstimateProviderMapping(
                id=uuid4(),
                company_id=company_id,
                listing_id=listing_id,
                provider_id="fmp_estimates",
                provider_symbol="TIME",
                role="PRIMARY",
                priority=10,
                currency="USD",
                evidence_source="synthetic temporal fixture",
                currency_evidence_source="synthetic temporal fixture",
                effective_from=stamp("2026-10-05T16:00:00"),
                recorded_at=stamp("2026-10-05T10:00:00"),
                actor="IMPORT",
            )
        )

        # The same-day close was observed after noon and must not become the base.
        session.add_all(
            [
                PriceObservation(
                    id=uuid4(),
                    listing_id=listing_id,
                    batch_id=None,
                    price_kind="DAILY_CLOSE",
                    market_date=stamp("2026-10-05T00:00:00"),
                    observed_at=stamp("2026-10-05T14:00:00"),
                    recorded_at=stamp("2026-10-05T14:01:00"),
                    provider_close=Decimal("110"),
                    split_adjusted_close=Decimal("110"),
                    total_return_close=Decimal("110"),
                    volume=None,
                    currency="USD",
                    provider_currency="USD",
                    source_price_multiplier=Decimal("1"),
                    provider="YAHOO_FINANCE",
                    provider_symbol="TIME",
                    adjustment_basis="SPLIT_AND_DISTRIBUTION_ADJUSTED",
                    data_quality="PASS",
                    source_ref="synthetic:forecast-day-close",
                    supersedes_observation_id=None,
                ),
                PriceObservation(
                    id=uuid4(),
                    listing_id=listing_id,
                    batch_id=None,
                    price_kind="DAILY_CLOSE",
                    market_date=stamp("2026-10-02T00:00:00"),
                    observed_at=stamp("2026-10-02T21:00:00"),
                    recorded_at=stamp("2026-10-02T21:01:00"),
                    provider_close=Decimal("100"),
                    split_adjusted_close=Decimal("100"),
                    total_return_close=Decimal("100"),
                    volume=None,
                    currency="USD",
                    provider_currency="USD",
                    source_price_multiplier=Decimal("1"),
                    provider="YAHOO_FINANCE",
                    provider_symbol="TIME",
                    adjustment_basis="SPLIT_AND_DISTRIBUTION_ADJUSTED",
                    data_quality="PASS",
                    source_ref="synthetic:known-before-cutoff",
                    supersedes_observation_id=None,
                ),
                PriceObservation(
                    id=uuid4(),
                    listing_id=listing_id,
                    batch_id=None,
                    price_kind="DAILY_CLOSE",
                    market_date=stamp("2027-01-03T00:00:00"),
                    observed_at=stamp("2027-01-03T16:00:00"),
                    recorded_at=stamp("2027-01-03T16:01:00"),
                    provider_close=Decimal("120"),
                    split_adjusted_close=Decimal("120"),
                    total_return_close=Decimal("120"),
                    volume=None,
                    currency="USD",
                    provider_currency="USD",
                    source_price_multiplier=Decimal("1"),
                    provider="YAHOO_FINANCE",
                    provider_symbol="TIME",
                    adjustment_basis="SPLIT_AND_DISTRIBUTION_ADJUSTED",
                    data_quality="PASS",
                    source_ref="synthetic:horizon-close",
                    supersedes_observation_id=None,
                ),
            ]
        )

        session.add(
            ReportedFundamentalBatch(
                id=batch_id,
                provider_id="sec_edgar",
                provider_schema_version="fixture-v1",
                normalizer_version="fixture-v1",
                domain="REPORTED_FUNDAMENTALS",
                source_digest="a" * 64,
                query_scope={"fixture": True},
                observed_at=stamp("2028-03-15T15:00:00"),
                recorded_at=stamp("2028-03-15T15:00:00"),
                provider_summary={},
                reconciliation={},
            )
        )
        session.add(
            ReportedFundamentalObservation(
                id=uuid4(),
                company_id=company_id,
                security_id=security_id,
                batch_id=batch_id,
                provider_id="sec_edgar",
                provider_entity_id="0000000001",
                source_priority=10,
                metric=FundamentalMetric.REVENUE.value,
                statement="INCOME_STATEMENT",
                period_type=FundamentalPeriodType.ANNUAL.value,
                period_start=stamp("2027-01-01T00:00:00"),
                period_end=stamp("2027-12-31T00:00:00"),
                fiscal_year=2027,
                fiscal_period="FY",
                filed_at=stamp("2028-03-15T14:00:00"),
                observed_at=stamp("2028-03-15T15:00:00"),
                recorded_at=stamp("2028-03-15T15:00:00"),
                value=Decimal("90"),
                currency="USD",
                unit="currency",
                source_taxonomy="us-gaap",
                source_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
                source_unit="USD",
                accession_number="0000000001-28-000001",
                form="10-K",
                frame="CY2027",
                source_record_id="synthetic:2027-revenue",
                source_url="https://example.test/filing",
                source_ref="synthetic filing reference",
                observation_fingerprint="b" * 64,
                mapping_priority=10,
                revision_context="ORIGINAL",
                data_quality="PASS",
                quality_reason=None,
                supersedes_observation_id=None,
            )
        )
        session.flush()

        forecast = company_temporal_alignment(
            session,
            company_id,
            fiscal_year=2027,
            as_of=date(2026, 10, 5),
            known_at=stamp("2026-10-05T12:00:00"),
            outcome_known_at=stamp("2028-03-15T13:00:00"),
            horizon_days=90,
        )
        assert forecast.model_forecasts[0].revision_number == 1
        assert forecast.model_forecasts[0].status == "FISCAL_YEAR_MAPPING_UNAVAILABLE"
        assert forecast.model_forecasts[0].forecast_year is None
        assert forecast.model_forecasts[0].value is None
        assert forecast.comparison_status == "FISCAL_YEAR_MAPPING_UNAVAILABLE"
        assert forecast.model_forecasts[0].price_at_forecast.market_date == stamp(
            "2026-10-02T00:00:00"
        )
        assert forecast.consensus.status == "NO_MAPPING"
        assert forecast.consensus.value is None
        assert forecast.actual.status == "NOT_REPORTED"
        assert forecast.actual.value is None
        assert forecast.model_forecasts[0].subsequent_market_return.status == "AVAILABLE"
        assert forecast.model_forecasts[0].subsequent_market_return.return_fraction == Decimal(
            "0.2"
        )

        before_horizon = company_temporal_alignment(
            session,
            company_id,
            fiscal_year=2027,
            as_of=date(2026, 10, 5),
            known_at=stamp("2026-10-05T12:00:00"),
            outcome_known_at=stamp("2026-10-05T13:00:00"),
            horizon_days=90,
        )
        assert (
            before_horizon.model_forecasts[0].subsequent_market_return.status
            == "HORIZON_NOT_REACHED"
        )

        after_filing = company_temporal_alignment(
            session,
            company_id,
            fiscal_year=2027,
            as_of=date(2026, 10, 5),
            known_at=stamp("2026-10-05T12:00:00"),
            outcome_known_at=stamp("2028-03-15T16:00:00"),
            horizon_days=90,
        )
        assert after_filing.model_forecasts[0].revision_number == 1
        assert after_filing.model_forecasts[0].value is None
        assert after_filing.actual.status == "AVAILABLE"
        assert after_filing.actual.value == Decimal("90")
