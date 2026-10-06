from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops
from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    Listing,
    Portfolio,
    PriceObservation,
    RankingEntryStatus,
    RankingType,
    Security,
    TargetRevision,
)
from portfolio_api.domain.seed import seed
from portfolio_api.portfolio_ranking import (
    PortfolioScoreInputs,
    calculate_portfolio_score,
    portfolio_score_positions,
)


def _googl_inputs(*, lifecycle: str | None = "PORTFOLIO") -> PortfolioScoreInputs:
    # Captured source inputs and cached score from Portfolio_Watchlist.xlsx.
    return PortfolioScoreInputs(
        lifecycle=lifecycle,
        current_weight=Decimal("0.08644111749"),
        target_weight=Decimal("0.09"),
        expected_irr=Decimal("0.1268953551"),
        durability_10y=Decimal("4.575"),
        compounder_quality=Decimal("4.63"),
        execution=Decimal("4"),
        risk=Decimal("3"),
        valuation_uncertainty=Decimal("0.879126213"),
        expected_excess=Decimal("0.03665021294"),
    )


def test_documented_score_reconciles_to_legacy_cached_company_score() -> None:
    result = calculate_portfolio_score(_googl_inputs())
    assert abs(result.score - Decimal("57.66995863")) <= Decimal("0.00000001")
    assert result.contributions["target_underweight"] > 0
    assert result.contributions["valuation_uncertainty_penalty"] < 0
    assert result.contributions["negative_expected_excess_penalty"] == 0


def test_target_underweight_credit_is_only_for_portfolio_lifecycle() -> None:
    portfolio = calculate_portfolio_score(_googl_inputs(lifecycle="PORTFOLIO"))
    watchlist = calculate_portfolio_score(_googl_inputs(lifecycle="WATCHLIST"))
    unknown_lifecycle = calculate_portfolio_score(_googl_inputs(lifecycle=None))

    assert portfolio.contributions["target_underweight"] > 0
    assert watchlist.contributions["target_underweight"] == 0
    assert unknown_lifecycle.contributions["target_underweight"] == 0
    assert portfolio.score > watchlist.score


def test_source_caps_and_floors_are_deterministic() -> None:
    capped = calculate_portfolio_score(
        PortfolioScoreInputs(
            lifecycle="PORTFOLIO",
            current_weight=Decimal("0"),
            target_weight=Decimal("0.20"),
            expected_irr=Decimal("0.80"),
            durability_10y=Decimal("5"),
            compounder_quality=Decimal("5"),
            execution=Decimal("5"),
            risk=Decimal("1"),
            valuation_uncertainty=Decimal("3"),
            expected_excess=Decimal("-0.20"),
        )
    )
    assert capped.contributions["target_underweight"] == Decimal("15.00")
    assert capped.contributions["expected_irr"] == Decimal("30.0")
    assert capped.contributions["valuation_uncertainty_penalty"] == Decimal("-10.0")
    assert capped.contributions["negative_expected_excess_penalty"] == Decimal("-5.00")

    negative_return = calculate_portfolio_score(
        PortfolioScoreInputs(
            lifecycle="PORTFOLIO",
            current_weight=Decimal("0.1"),
            target_weight=Decimal("0.1"),
            expected_irr=Decimal("-0.05"),
            durability_10y=Decimal("0"),
            compounder_quality=Decimal("0"),
            execution=Decimal("1"),
            risk=Decimal("5"),
            valuation_uncertainty=Decimal("0"),
            expected_excess=Decimal("-0.14"),
        )
    )
    assert negative_return.contributions["expected_irr"] == 0
    assert negative_return.contributions["negative_expected_excess_penalty"] == -5


def test_ties_use_canonical_ticker_ascending_and_never_emit_rank_zero() -> None:
    later_ticker, earlier_ticker, lower_score = uuid4(), uuid4(), uuid4()
    positions = portfolio_score_positions(
        [
            (later_ticker, "ZZZ", Decimal("60")),
            (earlier_ticker, "AAA", Decimal("60")),
            (lower_score, "MID", Decimal("59.99")),
        ]
    )
    assert positions == {earlier_ticker: 1, later_ticker: 2, lower_score: 3}
    assert min(positions.values()) == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("current_weight", Decimal("1.01"), "current weight"),
        ("target_weight", Decimal("-0.01"), "target weight"),
        ("durability_10y", Decimal("5.1"), "10Y Durability"),
        ("execution", Decimal("0"), "Execution"),
        ("risk", Decimal("6"), "Risk"),
        ("valuation_uncertainty", Decimal("-0.1"), "uncertainty"),
    ],
)
def test_invalid_score_inputs_do_not_become_numeric_positions(
    field: str, value: Decimal, message: str
) -> None:
    inputs = _googl_inputs()
    with pytest.raises(ValueError, match=message):
        calculate_portfolio_score(inputs.__class__(**{**inputs.__dict__, field: value}))


@pytest.mark.integration
def test_portfolio_run_ranks_supported_native_cohort_without_mutating_allocation(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        northstar = db.scalar(select(Company).where(Company.name.startswith("Northstar")))
        portfolio = db.scalar(select(Portfolio))
        assert atlas and northstar and portfolio
        holdings = db.scalar(
            select(HoldingSnapshot)
            .where(HoldingSnapshot.portfolio_id == portfolio.id)
            .order_by(HoldingSnapshot.effective_at.desc())
            .limit(1)
        )
        target_revision = db.scalar(
            select(TargetRevision)
            .where(TargetRevision.portfolio_id == portfolio.id, TargetRevision.status == "ACCEPTED")
            .order_by(TargetRevision.effective_at.desc())
            .limit(1)
        )
        atlas_listing = db.scalar(
            select(Listing)
            .join(Security, Security.id == Listing.security_id)
            .where(Security.company_id == atlas.id, Listing.ticker == "ATLA")
        )
        northstar_listing = db.scalar(
            select(Listing)
            .join(Security, Security.id == Listing.security_id)
            .where(Security.company_id == northstar.id, Listing.ticker == "NSTR")
        )
        assert holdings and target_revision and atlas_listing and northstar_listing
        as_of = datetime.now(UTC) + timedelta(seconds=20)
        reference_time = holdings.effective_at
        price_by_listing: dict[str, PriceObservation] = {}
        for listing in (atlas_listing, northstar_listing):
            price = PriceObservation(
                listing_id=listing.id,
                market_date=reference_time,
                observed_at=reference_time,
                recorded_at=as_of - timedelta(seconds=2),
                provider_close=Decimal("100"),
                split_adjusted_close=Decimal("100"),
                total_return_close=Decimal("100"),
                volume=Decimal("1000"),
                currency=listing.currency or "USD",
                provider="rank-test-provider",
                provider_symbol=f"TEST:{listing.ticker}",
                adjustment_basis="Unadjusted fixture close.",
                data_quality="PASS",
                source_ref=f"portfolio-rank-price:{listing.ticker}",
            )
            db.add(price)
            price_by_listing[listing.ticker] = price
        db.add(
            FxObservation(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.90"),
                effective_at=reference_time,
                observed_at=reference_time,
                recorded_at=as_of - timedelta(seconds=2),
                source_ref="portfolio-rank-fixture-usd-eur",
                provider="rank-test-provider",
                source="fixture:USD/EUR",
                actor="IMPORT",
                reason="Dated fixture FX needed for a comparable total portfolio weight.",
            )
        )
        db.flush()

        model = FinancialModel(
            company_id=atlas.id,
            valuation_listing_id=atlas_listing.id,
            model_type="UFCF_DCF_10Y_FADE",
            model_name="Portfolio Rank native fixture",
            model_currency="USD",
            source_model_key=f"portfolio-rank:{atlas.id}",
            created_at=as_of - timedelta(days=1),
        )
        db.add(model)
        db.flush()
        revision = FinancialModelRevision(
            model_id=model.id,
            model_type=model.model_type,
            revision_number=1,
            methodology_version="portfolio-rank-test-v1",
            source_revision_id=f"portfolio-rank-test:{atlas.id}:r1",
            actor="SYSTEM",
            source="test fixture",
            rationale="Support deterministic rank integration coverage.",
            effective_at=as_of - timedelta(days=1),
            recorded_at=as_of - timedelta(seconds=3),
        )
        db.add(revision)
        db.flush()
        model.current_revision_id = revision.id
        db.add(
            FinancialModelOutput(
                revision_id=revision.id,
                status="COMPLETE",
                model_currency="USD",
                price_observation_id=price_by_listing["ATLA"].id,
                current_price=Decimal("100"),
                price_effective_at=reference_time,
                price_status="FRESH",
                bear_fv=Decimal("80"),
                base_fv=Decimal("110"),
                bull_fv=Decimal("140"),
                bear_probability=Decimal("0.2"),
                base_probability=Decimal("0.6"),
                bull_probability=Decimal("0.2"),
                weighted_fv=Decimal("110"),
                weighted_upside=Decimal("0.1"),
                expected_cash_flow_irr=Decimal("0.15"),
                hurdle=Decimal("0.09"),
                expected_excess=Decimal("0.06"),
                forward_fundamental_cagr=Decimal("0.12"),
            )
        )
        db.flush()
        original_positions = list(
            db.scalars(select(HoldingPosition).where(HoldingPosition.snapshot_id == holdings.id))
        )
        original_targets = list(
            db.scalars(select(TargetRevision.id).where(TargetRevision.portfolio_id == portfolio.id))
        )

        with patch("portfolio_api.domain.services.now", return_value=as_of):
            run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.PORTFOLIO,
                    actor="LOCAL_USER",
                    reason="Verify source Portfolio Score with complete native inputs.",
                ),
            )
        detail = q.ranking_run_detail(db, run.id)
        entries = {item.company.id: item.entry for item in detail.entries}
        assert entries[atlas.id].status == RankingEntryStatus.RANKED, entries[atlas.id].reason
        assert entries[atlas.id].position == 1
        atlas_context = entries[atlas.id].input_snapshot
        assert atlas_context is not None
        assert isinstance(atlas_context, s.PortfolioRankInputSnapshot)
        assert atlas_context.portfolio_score is not None
        assert atlas_context.current_weight is not None
        assert atlas_context.target_weight == Decimal("0.35")
        assert atlas_context.target_minus_current_gap is not None
        assert atlas_context.lifecycle == "PORTFOLIO"
        assert entries[northstar.id].status == RankingEntryStatus.INPUTS_UNAVAILABLE
        assert entries[northstar.id].position is None
        assert len(
            list(
                db.scalars(
                    select(HoldingPosition).where(HoldingPosition.snapshot_id == holdings.id)
                )
            )
        ) == len(original_positions)
        assert (
            list(
                db.scalars(
                    select(TargetRevision.id).where(TargetRevision.portfolio_id == portfolio.id)
                )
            )
            == original_targets
        )

        stored = db.get(Company, atlas.id)
        assert stored is not None
        overview = q.overview(db, portfolio.id, as_of)
        atlas_current = next(row for row in overview.companies if row.company.id == atlas.id)
        assert atlas_current.target_weight == Decimal("0.35")
        assert atlas_current.current_weight is not None
