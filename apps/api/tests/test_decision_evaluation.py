"""Decision evaluation uses strict point-in-time facts and explicit sample states."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.decision_evaluation import (
    _Signal,
    _summaries,
    discrete_crps,
    spearman_correlation,
)
from portfolio_api.domain.models import (
    Company,
    Listing,
    PriceObservation,
    RankingDefinition,
    RankingEntry,
    RankingRun,
    Security,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings
from portfolio_api.temporal_alignment import snapshot_market_return


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_discrete_crps_scores_probability_weighted_scenarios() -> None:
    score = discrete_crps(
        [
            (Decimal("0"), Decimal("0.25")),
            (Decimal("10"), Decimal("0.5")),
            (Decimal("20"), Decimal("0.25")),
        ],
        Decimal("12"),
    )
    assert score == Decimal("2.25")


def test_discrete_crps_rejects_missing_probability_mass() -> None:
    with pytest.raises(ValueError, match="sum to one"):
        discrete_crps([(Decimal("10"), Decimal("0.6"))], Decimal("12"))


def test_spearman_is_rank_based_and_handles_ties() -> None:
    correlation = spearman_correlation(
        [Decimal("1"), Decimal("2"), Decimal("2"), Decimal("4")],
        [Decimal("5"), Decimal("5"), Decimal("7"), Decimal("9")],
    )
    assert correlation is not None
    assert Decimal("0") < correlation <= Decimal("1")
    assert spearman_correlation([Decimal("1")], [Decimal("2")]) is None


def test_return_summaries_keep_methodology_versions_separate() -> None:
    run_id = uuid4()
    run_as_of = stamp("2025-10-14T12:00:00Z")
    signals: list[_Signal] = []
    outcomes = {}
    for version in (1, 2):
        for position in range(1, 6):
            signal_id = uuid4()
            signals.append(
                _Signal(
                    signal_type="PORTFOLIO_RANK",
                    signal_id=signal_id,
                    run_id=run_id,
                    run_as_of=run_as_of,
                    recorded_at=stamp("2025-10-14T22:00:00Z"),
                    source_methodology=f"Portfolio Rank v{version}",
                    status="RANKED",
                    value=str(position),
                    position=position,
                    expected_irr=Decimal(position) / Decimal(100),
                    return_methodology={
                        "code": "OWNER_CASH_FLOW_EQUITY_IRR",
                        "version": version,
                        "perspective": "EQUITY",
                    },
                    listing=type("ListingCurrency", (), {"currency": "USD"})(),
                    model_currency="USD",
                    price_observation_id=uuid4(),
                )
            )
            outcomes[(signal_id, 365)] = type(
                "Outcome",
                (),
                {
                    "status": "AVAILABLE",
                    "annualized_return": Decimal(position + version) / Decimal(100),
                },
            )()

    summaries = _summaries(
        {run_id: signals},
        outcomes,
        [365],
        {run_id: (run_as_of, "Portfolio Rank v2")},
    )
    expected_irr = [
        item for item in summaries if item.signal_type == "EXPECTED_IRR_RETURN_ASSOCIATION"
    ]
    assert {item.group_value for item in expected_irr} == {
        "OWNER_CASH_FLOW_EQUITY_IRR@1",
        "OWNER_CASH_FLOW_EQUITY_IRR@2",
    }
    assert all(item.sample_count == 5 for item in expected_irr)


@pytest.mark.integration
def test_decision_evaluation_uses_captured_price_and_outcome_knowledge_cutoff(
    postgres_engine: Engine,
) -> None:
    company_id, security_id, listing_id = (uuid4() for _ in range(3))
    signal_id, run_id, definition_id = (uuid4() for _ in range(3))
    baseline_id, endpoint_id = uuid4(), uuid4()
    with Session(postgres_engine) as session, session.begin():
        company = Company(id=company_id, name="Evaluation fixture", reporting_currency="USD")
        security = Security(
            id=security_id,
            company_id=company_id,
            name="Evaluation fixture common",
            security_type="COMMON_STOCK",
            share_class=None,
            underlying_security_id=None,
        )
        listing = Listing(
            id=listing_id,
            security_id=security_id,
            ticker="EVAL",
            venue="NASDAQ",
            currency="USD",
            identity_source_ref="synthetic evaluation fixture",
        )
        definition = RankingDefinition(
            id=definition_id,
            ranking_type="PORTFOLIO",
            version=999,
            title="Portfolio Rank fixture",
            methodology="Expected IRR-first fixture method.",
            population_rule="Portfolio only.",
            required_inputs="Synthetic test inputs.",
            source_reference="test fixture",
            implementation_status="READY",
            effective_from=stamp("2025-01-01T00:00:00Z"),
            status="RETIRED",
        )
        run = RankingRun(
            id=run_id,
            definition_id=definition_id,
            as_of=stamp("2025-10-14T12:00:00Z"),
            recorded_at=stamp("2025-10-14T22:00:00Z"),
            status="COMPLETE",
            actor="SYSTEM",
            reason="Synthetic point-in-time evaluation run.",
            source="test fixture",
        )
        session.add_all([company, security, definition, run])
        session.flush()
        session.add(listing)
        session.flush()
        session.add(
            RankingEntry(
                id=signal_id,
                run_id=run_id,
                company_id=company_id,
                position=1,
                status="RANKED",
                reason="Synthetic rank entry.",
                input_snapshot={
                    "expected_irr": "0.15",
                    "return_comparability_cohort": "OWNER_CASH_FLOW_EQUITY_IRR@1",
                    "model_source": {
                        "listing_id": str(listing_id),
                        "model_currency": "USD",
                        "share_price_basis_status": "CAPTURED",
                        "price_observation_id": str(baseline_id),
                        "return_methodology": {
                            "code": "OWNER_CASH_FLOW_EQUITY_IRR",
                            "version": 1,
                            "perspective": "EQUITY",
                        },
                    },
                },
            )
        )
        session.add_all(
            [
                PriceObservation(
                    id=baseline_id,
                    listing_id=listing_id,
                    batch_id=None,
                    price_kind="DAILY_CLOSE",
                    market_date=stamp("2025-10-14T20:00:00Z"),
                    observed_at=stamp("2025-10-14T20:05:00Z"),
                    recorded_at=stamp("2025-10-14T20:06:00Z"),
                    provider_close=Decimal("100"),
                    split_adjusted_close=Decimal("100"),
                    total_return_close=Decimal("100"),
                    volume=None,
                    currency="USD",
                    provider_currency="USD",
                    source_price_multiplier=Decimal(1),
                    provider="FIXTURE",
                    provider_symbol="EVAL",
                    adjustment_basis="synthetic total-return fixture",
                    data_quality="PASS",
                    source_ref=f"fixture:{baseline_id}",
                ),
                PriceObservation(
                    id=endpoint_id,
                    listing_id=listing_id,
                    batch_id=None,
                    price_kind="DAILY_CLOSE",
                    market_date=stamp("2026-10-14T20:00:00Z"),
                    observed_at=stamp("2026-10-14T20:05:00Z"),
                    recorded_at=stamp("2026-10-14T20:06:00Z"),
                    provider_close=Decimal("110"),
                    split_adjusted_close=Decimal("110"),
                    total_return_close=Decimal("110"),
                    volume=None,
                    currency="USD",
                    provider_currency="USD",
                    source_price_multiplier=Decimal(1),
                    provider="FIXTURE",
                    provider_symbol="EVAL",
                    adjustment_basis="synthetic total-return fixture",
                    data_quality="PASS",
                    source_ref=f"fixture:{endpoint_id}",
                ),
            ]
        )

    app = create_app(Settings(database_url=None))
    with TestClient(app) as client:
        app.state.database_engine = postgres_engine
        available = client.get(
            f"/v1/companies/{company_id}/decision-evaluation",
            params={
                "outcome_known_at": "2026-10-15T00:00:00Z",
                "horizons_days": 365,
            },
        )
        assert available.status_code == 200, available.text
        body = available.json()
        assert body["portfolio_implementation_status"] == "NOT_AVAILABLE_NO_TRANSACTION_LEDGER"
        assert body["scenario_evaluations"] == []
        signal = body["signals"][0]
        outcome = signal["outcomes"][0]
        assert signal["price_observation_id"] == str(baseline_id)
        assert outcome["status"] == "AVAILABLE"
        assert outcome["start_observation_id"] == str(baseline_id)
        assert outcome["end_observation_id"] == str(endpoint_id)
        assert Decimal(outcome["total_return"]) == Decimal("0.1")
        assert body["summaries"]
        assert all(item["status"] == "INSUFFICIENT_SAMPLE" for item in body["summaries"])

        before_horizon = client.get(
            f"/v1/companies/{company_id}/decision-evaluation",
            params={
                "outcome_known_at": "2026-10-13T23:59:59Z",
                "horizons_days": 365,
            },
        )
        assert before_horizon.status_code == 200, before_horizon.text
        assert before_horizon.json()["signals"][0]["outcomes"][0]["status"] in {
            "HORIZON_NOT_REACHED",
            "NO_END_PRICE",
        }

    correction_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            PriceObservation(
                id=correction_id,
                listing_id=listing_id,
                batch_id=None,
                price_kind="DAILY_CLOSE",
                market_date=stamp("2026-10-14T20:00:00Z"),
                observed_at=stamp("2026-10-14T20:10:00Z"),
                recorded_at=stamp("2026-10-14T20:11:00Z"),
                provider_close=Decimal("110"),
                split_adjusted_close=Decimal("110"),
                total_return_close=Decimal("110"),
                volume=None,
                currency="JPY",
                provider_currency="JPY",
                source_price_multiplier=Decimal(1),
                provider="FIXTURE_CURRENCY_CHECK",
                provider_symbol="EVAL",
                adjustment_basis="synthetic conflicting-currency fixture",
                data_quality="PASS",
                source_ref=f"fixture:{correction_id}",
                supersedes_observation_id=endpoint_id,
            )
        )
    app = create_app(Settings(database_url=None))
    with TestClient(app) as client:
        app.state.database_engine = postgres_engine
        mismatch = client.get(
            f"/v1/companies/{company_id}/decision-evaluation",
            params={
                "outcome_known_at": "2026-10-15T00:00:00Z",
                "horizons_days": 365,
            },
        )
        assert mismatch.status_code == 200, mismatch.text
        assert mismatch.json()["signals"][0]["outcomes"][0]["status"] == "END_PRICE_DATA_CHECK"


@pytest.mark.integration
def test_decision_evaluation_flags_missing_baseline_source_time(
    postgres_engine: Engine,
) -> None:
    company_id, security_id, listing_id = (uuid4() for _ in range(3))
    definition_id, run_id, entry_id, baseline_id = (uuid4() for _ in range(4))
    with Session(postgres_engine) as session, session.begin():
        company = Company(
            id=company_id, name="Missing source-time fixture", reporting_currency="USD"
        )
        security = Security(
            id=security_id,
            company_id=company_id,
            name="Missing source-time common",
            security_type="COMMON_STOCK",
            share_class=None,
            underlying_security_id=None,
        )
        listing = Listing(
            id=listing_id,
            security_id=security_id,
            ticker="NOSRC",
            venue="NASDAQ",
            currency="USD",
            identity_source_ref="synthetic evaluation fixture",
        )
        definition = RankingDefinition(
            id=definition_id,
            ranking_type="WATCHLIST",
            version=999,
            title="Watchlist Rank fixture",
            methodology="Expected IRR-first fixture method.",
            population_rule="Watchlist only.",
            required_inputs="Synthetic test inputs.",
            source_reference="test fixture",
            implementation_status="READY",
            effective_from=stamp("2025-01-01T00:00:00Z"),
            status="RETIRED",
        )
        run = RankingRun(
            id=run_id,
            definition_id=definition_id,
            as_of=stamp("2025-10-14T12:00:00Z"),
            recorded_at=stamp("2025-10-14T22:00:00Z"),
            status="PARTIAL",
            actor="SYSTEM",
            reason="Synthetic source-time check.",
            source="test fixture",
        )
        session.add_all([company, security, definition, run])
        session.flush()
        session.add(listing)
        session.flush()
        session.add(
            RankingEntry(
                id=entry_id,
                run_id=run_id,
                company_id=company_id,
                position=1,
                status="RANKED",
                reason="Synthetic rank entry.",
                input_snapshot={
                    "return_source": {
                        "listing_id": str(listing_id),
                        "model_currency": "USD",
                        "return_methodology": {
                            "code": "OWNER_CASH_FLOW_EQUITY_IRR",
                            "version": 1,
                            "perspective": "EQUITY",
                        },
                        "price_observation_id": str(baseline_id),
                    }
                },
            )
        )
        session.add(
            PriceObservation(
                id=baseline_id,
                listing_id=listing_id,
                batch_id=None,
                price_kind="DAILY_CLOSE",
                market_date=stamp("2025-10-14T20:00:00Z"),
                observed_at=None,
                recorded_at=stamp("2025-10-14T20:06:00Z"),
                provider_close=Decimal("100"),
                split_adjusted_close=Decimal("100"),
                total_return_close=Decimal("100"),
                volume=None,
                currency="USD",
                provider_currency="USD",
                source_price_multiplier=Decimal(1),
                provider="FIXTURE",
                provider_symbol="NOSRC",
                adjustment_basis="synthetic fixture with missing source time",
                data_quality="PASS",
                source_ref=f"fixture:{baseline_id}",
            )
        )

    app = create_app(Settings(database_url=None))
    with TestClient(app) as client:
        app.state.database_engine = postgres_engine
        response = client.get(
            f"/v1/companies/{company_id}/decision-evaluation",
            params={
                "outcome_known_at": "2026-10-15T00:00:00Z",
                "horizons_days": 365,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["signals"][0]["outcomes"][0]["status"] == "BASE_PRICE_DATA_CHECK"


@pytest.mark.integration
def test_snapshot_return_rejects_a_baseline_from_another_listing(
    postgres_engine: Engine,
) -> None:
    company_id, first_security_id, second_security_id = (uuid4() for _ in range(3))
    first_listing_id, second_listing_id, baseline_id = (uuid4() for _ in range(3))
    with Session(postgres_engine) as session, session.begin():
        company = Company(id=company_id, name="Exact listing fixture", reporting_currency="USD")
        first_security = Security(
            id=first_security_id,
            company_id=company_id,
            name="Class A",
            security_type="COMMON_STOCK",
            share_class="A",
            underlying_security_id=None,
        )
        second_security = Security(
            id=second_security_id,
            company_id=company_id,
            name="Class B",
            security_type="COMMON_STOCK",
            share_class="B",
            underlying_security_id=None,
        )
        session.add_all([company, first_security, second_security])
        session.flush()
        session.add_all(
            [
                Listing(
                    id=first_listing_id,
                    security_id=first_security_id,
                    ticker="CLASSA",
                    venue="NASDAQ",
                    currency="USD",
                    identity_source_ref="synthetic exact-listing fixture",
                ),
                Listing(
                    id=second_listing_id,
                    security_id=second_security_id,
                    ticker="CLASSB",
                    venue="NASDAQ",
                    currency="USD",
                    identity_source_ref="synthetic exact-listing fixture",
                ),
            ]
        )
        session.flush()
        session.add(
            PriceObservation(
                id=baseline_id,
                listing_id=second_listing_id,
                batch_id=None,
                price_kind="DAILY_CLOSE",
                market_date=stamp("2025-10-14T20:00:00Z"),
                observed_at=stamp("2025-10-14T20:05:00Z"),
                recorded_at=stamp("2025-10-14T20:06:00Z"),
                provider_close=Decimal("100"),
                split_adjusted_close=Decimal("100"),
                total_return_close=Decimal("100"),
                volume=None,
                currency="USD",
                provider_currency="USD",
                source_price_multiplier=Decimal(1),
                provider="FIXTURE",
                provider_symbol="CLASSB",
                adjustment_basis="synthetic exact-listing fixture",
                data_quality="PASS",
                source_ref=f"fixture:{baseline_id}",
            )
        )
    with Session(postgres_engine) as session:
        result = snapshot_market_return(
            session,
            listing_id=first_listing_id,
            start_observation_id=baseline_id,
            signal_as_of=stamp("2025-10-14T21:00:00Z"),
            signal_recorded_at=stamp("2025-10-14T22:00:00Z"),
            horizon_days=365,
            outcome_known_at=stamp("2026-10-15T00:00:00Z"),
        )
        assert result.result.status == "BASE_LISTING_MISMATCH"
        assert result.result.return_fraction is None
