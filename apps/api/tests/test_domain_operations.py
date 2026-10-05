from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops
from portfolio_api.domain.models import (
    CashPosition,
    Company,
    CurrentLifecycle,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    LifecycleEvent,
    Listing,
    Portfolio,
    PriceObservation,
    RankingEntry,
    RankingEntryStatus,
    RankingRun,
    RankingType,
    ScoreAssessment,
    ScoreDimension,
    Security,
    TargetAllocation,
    TargetRevision,
)
from portfolio_api.domain.seed import seed
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

pytestmark = pytest.mark.integration


def provenance() -> dict[str, str]:
    return {
        "actor": "LOCAL_USER",
        "reason": "Test observation",
        "effective_at": datetime.now(UTC).isoformat(),
    }


def create_issuer(session: Session) -> Company:
    return ops.create_company(session, s.CompanyCreate(name="Test issuer"))


def test_seed_idempotent_identity_and_cash_separate(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        identifier = seed(db)
        assert seed(db) == identifier
        assert db.scalar(select(func.count()).select_from(Company)) == 4
        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        assert atlas is not None
        assert (
            db.scalar(
                select(func.count()).select_from(Security).where(Security.company_id == atlas.id)
            )
            == 2
        )
        context = q.detail(db, atlas.id)
        assert len(context.listings) == 3
        assert context.portfolio_context is not None
        assert context.portfolio_context.current_market_value is None
        assert context.portfolio_context.current_weight is None
        overview = q.overview(db, identifier)
        assert overview.snapshot is not None
        assert {c.currency for c in overview.snapshot.cash_positions} == {"EUR", "USD"}
        assert overview.target_revision is not None
        assert overview.target_revision.strategic_cash_weight == Decimal("0.4")
        assert all(
            c.current_weight is None and c.allocation_gap is None for c in overview.companies
        )


def test_fresh_listing_prices_and_dated_fx_enable_current_weights_without_changing_targets(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        portfolio_id = seed(db)
        before = q.overview(db, portfolio_id)
        assert before.snapshot is not None
        assert before.target_revision is not None
        targets_before = {row.company.id: row.target_weight for row in before.companies}
        observed_date = before.snapshot.effective_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        positions = list(before.snapshot.positions)
        for position in positions:
            listing = db.get(Listing, position.listing_id)
            assert listing is not None and listing.currency is not None
            db.add(
                PriceObservation(
                    listing_id=listing.id,
                    market_date=observed_date,
                    provider_close=Decimal("10"),
                    split_adjusted_close=Decimal("10"),
                    total_return_close=None,
                    volume=None,
                    currency=listing.currency,
                    provider="test-fixture-provider",
                    provider_symbol=f"{listing.venue}:{listing.ticker}",
                    adjustment_basis="Explicit synthetic fixture per share",
                    data_quality="PASS",
                    source_ref=f"test-fixture:{listing.id}:{observed_date.isoformat()}",
                )
            )
        currencies = {cash.currency for cash in before.snapshot.cash_positions}
        currencies.update(
            listing.currency
            for position in positions
            if (listing := db.get(Listing, position.listing_id)) is not None
            and listing.currency is not None
        )
        for currency in currencies - {before.portfolio.base_currency}:
            inverse = currency == "DKK"
            db.add(
                FxObservation(
                    base_currency=before.portfolio.base_currency if inverse else currency,
                    quote_currency=currency if inverse else before.portfolio.base_currency,
                    rate=(Decimal(1) / Decimal("0.12")) if inverse else Decimal("0.9"),
                    effective_at=observed_date,
                    provider="test-fixture-provider",
                    source=f"test-fixture:{currency}-EUR:{observed_date.date()}",
                    actor="IMPORT",
                    reason="Explicit synthetic integration fixture rate",
                )
            )
        after = q.overview(db, portfolio_id)
        assert after.valuation_status == "VALUED"
        assert after.base_market_value is not None and after.base_market_value > 0
        assert all(row.current_weight is not None for row in after.companies)
        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        assert atlas is not None
        company_context = q.detail(db, atlas.id).portfolio_context
        overview_context = next(row for row in after.companies if row.company.id == atlas.id)
        assert company_context is not None
        assert company_context.current_market_value == overview_context.current_market_value
        assert company_context.current_weight == overview_context.current_weight
        assert company_context.allocation_gap == overview_context.allocation_gap
        assert company_context.allocation_status == "VALUED"
        assert all(row.valuation_status == "VALUED" for row in after.cash_valuations)
        assert {row.company.id: row.target_weight for row in after.companies} == targets_before
        assert all(
            row.allocation_gap is not None
            for row in after.companies
            if row.target_weight is not None
        )


def test_listing_price_history_respects_effective_and_known_at_cutoffs(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        listing = db.scalar(select(Listing).order_by(Listing.venue, Listing.ticker).limit(1))
        assert listing is not None and listing.currency is not None
        market_date = datetime(2024, 1, 3, tzinfo=UTC)
        earlier_recorded = datetime(2024, 1, 4, tzinfo=UTC)
        later_recorded = datetime(2024, 1, 9, tzinfo=UTC)
        db.add_all(
            [
                PriceObservation(
                    listing_id=listing.id,
                    market_date=market_date,
                    recorded_at=earlier_recorded,
                    provider_close=Decimal("100"),
                    split_adjusted_close=Decimal("100"),
                    total_return_close=None,
                    volume=None,
                    currency=listing.currency,
                    provider="YAHOO_FINANCE",
                    provider_symbol=listing.ticker,
                    adjustment_basis="split-adjusted close",
                    data_quality="PASS",
                    source_ref="test-as-of:original",
                ),
                PriceObservation(
                    listing_id=listing.id,
                    market_date=market_date,
                    recorded_at=later_recorded,
                    provider_close=Decimal("102"),
                    split_adjusted_close=Decimal("102"),
                    total_return_close=None,
                    volume=None,
                    currency=listing.currency,
                    provider="YAHOO_FINANCE",
                    provider_symbol=listing.ticker,
                    adjustment_basis="split-adjusted close; corrected source observation",
                    data_quality="PASS",
                    source_ref="test-as-of:correction",
                ),
            ]
        )

        as_first_known = q.listing_market_data(
            db,
            listing,
            market_as_of=date(2024, 1, 5),
            known_at=datetime(2024, 1, 8, tzinfo=UTC),
        )
        as_currently_known = q.listing_market_data(
            db,
            listing,
            market_as_of=date(2024, 1, 5),
            known_at=datetime(2024, 1, 10, tzinfo=UTC),
        )

        assert as_first_known.latest is not None
        assert as_first_known.latest.split_adjusted_close == Decimal("100")
        assert as_currently_known.latest is not None
        assert as_currently_known.latest.split_adjusted_close == Decimal("102")


def test_fx_history_respects_effective_and_known_at_cutoffs(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        effective_at = datetime(2024, 1, 3, tzinfo=UTC)
        first_recorded = datetime(2024, 1, 4, tzinfo=UTC)
        correction_recorded = datetime(2024, 1, 9, tzinfo=UTC)
        first = FxObservation(
            base_currency="USD",
            quote_currency="EUR",
            rate=Decimal("0.90"),
            effective_at=effective_at,
            observed_at=first_recorded,
            recorded_at=first_recorded,
            provider="YAHOO_FINANCE",
            source="test-fixture:EUR=X",
            source_ref="test-fx-as-of:original",
            actor="IMPORT",
            reason="Original dated provider observation",
        )
        db.add(first)
        db.flush()
        db.add(
            FxObservation(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.91"),
                effective_at=effective_at,
                observed_at=correction_recorded,
                recorded_at=correction_recorded,
                supersedes_observation_id=first.id,
                provider="YAHOO_FINANCE",
                source="test-fixture:EUR=X",
                source_ref="test-fx-as-of:correction",
                actor="IMPORT",
                reason="Corrected dated provider observation",
            )
        )

        known_before_correction = q.fx_observations(
            db,
            base_currency="USD",
            quote_currency="EUR",
            as_of=effective_at,
            known_at=datetime(2024, 1, 8, tzinfo=UTC),
        )
        known_after_correction = q.fx_observations(
            db,
            base_currency="USD",
            quote_currency="EUR",
            as_of=effective_at,
            known_at=datetime(2024, 1, 10, tzinfo=UTC),
        )

        assert [row.rate for row in known_before_correction] == [Decimal("0.90")]
        assert [row.rate for row in known_after_correction] == [
            Decimal("0.91"),
            Decimal("0.90"),
        ]


def test_missing_and_zero_targets_remain_distinct(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        harbor = db.scalar(select(Company).where(Company.name.startswith("Harbor")))
        assert cedar and harbor
        assert q.detail(db, cedar.id).target_weight == Decimal(0)
        assert q.detail(db, harbor.id).target_weight is None


def test_lifecycle_is_explicit_optimistic_and_atomic(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        issuer = create_issuer(db)
        assert q.company_read(db, issuer).lifecycle is None
        event = ops.transition_lifecycle(
            db,
            issuer.id,
            s.LifecycleChange.model_validate(
                {
                    **provenance(),
                    "new_state": "CANDIDATE",
                    "expected_event_id": None,
                }
            ),
        )
        identifier, event_id = issuer.id, event.id
    with Session(postgres_engine) as db:
        with pytest.raises(ops.DomainError, match="changed since"):
            ops.transition_lifecycle(
                db,
                identifier,
                s.LifecycleChange.model_validate(
                    {
                        **provenance(),
                        "new_state": "PORTFOLIO",
                        "expected_event_id": None,
                    }
                ),
            )
        db.rollback()
        assert db.scalar(select(func.count()).select_from(LifecycleEvent)) == 1
        assert db.get(CurrentLifecycle, identifier).event_id == event_id  # type: ignore[union-attr]


def test_concurrent_lifecycle_writes_cannot_lose_a_transition(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        identifier = create_issuer(db).id

    def transition(state: str) -> str:
        try:
            with Session(postgres_engine) as db, db.begin():
                ops.transition_lifecycle(
                    db,
                    identifier,
                    s.LifecycleChange.model_validate(
                        {
                            **provenance(),
                            "new_state": state,
                            "expected_event_id": None,
                        }
                    ),
                )
            return "accepted"
        except ops.DomainError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(transition, ["CANDIDATE", "WATCHLIST"])) == [
            "accepted",
            "conflict",
        ]
    with Session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(LifecycleEvent)) == 1
        pointer = db.get(CurrentLifecycle, identifier)
        assert pointer is not None and db.get(LifecycleEvent, pointer.event_id) is not None


def test_accepted_targets_and_observations_are_immutable(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        identifier = seed(db)
    for model in [
        LifecycleEvent,
        HoldingSnapshot,
        HoldingPosition,
        CashPosition,
        TargetRevision,
        TargetAllocation,
        ScoreAssessment,
        RankingRun,
        RankingEntry,
    ]:
        with Session(postgres_engine) as db:
            item = db.scalar(select(model).limit(1))
            assert item is not None
            db.delete(item)
            with pytest.raises(ValueError, match="append-only|immutable"):
                db.flush()
            db.rollback()
    with Session(postgres_engine) as db:
        accepted = db.scalar(select(TargetRevision))
        assert accepted is not None
        accepted.reason = "Rewrite history"
        with pytest.raises(ValueError, match="immutable"):
            db.flush()
        db.rollback()
    with Session(postgres_engine) as db:
        assert q.overview(db, identifier).target_revision is not None


def test_score_definition_metadata_and_fictional_seed_coverage(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        definitions = q.score_definitions(db)
        metadata = {item.dimension: item for item in definitions}
        assert set(metadata) == {dimension.value for dimension in ScoreDimension}
        assert metadata[ScoreDimension.DURABILITY_10Y].minimum_score == Decimal("0.00")
        assert metadata[ScoreDimension.COMPOUNDER_QUALITY].maximum_score == Decimal("5.00")
        assert metadata[ScoreDimension.EXECUTION].minimum_score == Decimal("1.00")
        risk = metadata[ScoreDimension.RISK]
        assert risk.minimum_score == Decimal("1.00")
        assert risk.maximum_score == Decimal("5.00")
        assert risk.directionality == "HIGHER_IS_RISK"
        assert "valuation" in risk.methodology.lower()

        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        harbor = db.scalar(select(Company).where(Company.name.startswith("Harbor")))
        assert atlas and cedar and harbor
        atlas_scores = q.current_scores(db, atlas.id)
        assert len(atlas_scores) == 4
        current_durability = next(
            item for item in atlas_scores if item.definition.dimension == "DURABILITY_10Y"
        )
        assert current_durability.assessment is not None
        assert current_durability.assessment.score == Decimal("4.25")
        history = [
            item
            for item in q.score_history(db, atlas.id)
            if item.definition.dimension == "DURABILITY_10Y"
        ]
        assert len(history) == 2
        latest = next(item for item in history if item.assessment.score == Decimal("4.25"))
        earlier = next(item for item in history if item.assessment.score == Decimal("3.50"))
        assert latest.assessment.superseded_assessment_id == earlier.assessment.id
        cedar_scores = {
            item.definition.dimension: item.assessment for item in q.current_scores(db, cedar.id)
        }
        cedar_durability = cedar_scores[ScoreDimension.DURABILITY_10Y]
        assert cedar_durability is not None
        assert cedar_durability.score == Decimal("0.00")
        cedar_quality = cedar_scores[ScoreDimension.COMPOUNDER_QUALITY]
        assert cedar_quality is not None
        assert cedar_quality.status == "MISSING"
        assert cedar_quality.score is None
        cedar_execution = cedar_scores[ScoreDimension.EXECUTION]
        assert cedar_execution is not None
        assert cedar_execution.status == "UNAVAILABLE"
        assert all(item.assessment is None for item in q.current_scores(db, harbor.id))


def test_score_correction_appends_and_current_uses_latest_assessment(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        assert atlas
        previous = next(
            item.assessment
            for item in q.current_scores(db, atlas.id)
            if item.definition.dimension == "DURABILITY_10Y"
        )
        assert previous and previous.score == Decimal("4.25")
        revised = ops.create_score_assessment(
            db,
            atlas.id,
            s.ScoreAssessmentCreate(
                dimension=ScoreDimension.DURABILITY_10Y,
                score="4.50",
                status="ASSESSED",
                effective_at=datetime.now(UTC),
                rationale="Fictional correction for an append-only history check.",
                actor="LOCAL_USER",
                superseded_assessment_id=previous.id,
            ),
        )
        assert revised.superseded_assessment_id == previous.id
        assert previous.score == Decimal("4.25")
        current = next(
            item
            for item in q.current_scores(db, atlas.id)
            if item.definition.dimension == "DURABILITY_10Y"
        )
        assert current.assessment and current.assessment.id == revised.id
        assert current.assessment.score == Decimal("4.50")
        assert (
            len(
                [
                    item
                    for item in q.score_history(db, atlas.id)
                    if item.definition.dimension == "DURABILITY_10Y"
                ]
            )
            == 3
        )


def test_score_scale_semantics_and_stale_correction_rejected(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        issuer = create_issuer(db)
        with pytest.raises(ops.DomainError, match="between 1.00 and 5.00"):
            ops.create_score_assessment(
                db,
                issuer.id,
                s.ScoreAssessmentCreate(
                    dimension=ScoreDimension.RISK,
                    score="0",
                    status="ASSESSED",
                    effective_at=datetime.now(UTC),
                    rationale="Risk cannot be zero.",
                    actor="LOCAL_USER",
                ),
            )
        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        assert atlas
        previous = next(
            item.assessment
            for item in q.current_scores(db, atlas.id)
            if item.definition.dimension == "DURABILITY_10Y"
        )
        assert previous
        with pytest.raises(ops.DomainError, match="newer score assessment"):
            ops.create_score_assessment(
                db,
                atlas.id,
                s.ScoreAssessmentCreate(
                    dimension=ScoreDimension.DURABILITY_10Y,
                    score="4.60",
                    status="ASSESSED",
                    effective_at=datetime.now(UTC),
                    rationale="Stale edit must not branch history.",
                    actor="LOCAL_USER",
                    superseded_assessment_id=None,
                ),
            )


def test_score_assessments_universe_api_and_missing_semantics(postgres_engine: Engine) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        issuer = client.post("/v1/companies", json={"name": "Score API issuer"}).json()
        company_id = issuer["id"]
        definitions = client.get("/v1/score-definitions?dimension=RISK")
        assert definitions.status_code == 200
        assert definitions.json()[0]["directionality"] == "HIGHER_IS_RISK"
        current_url = f"/v1/companies/{company_id}/scores/current"
        current = client.get(current_url)
        assert current.status_code == 200
        assert len(current.json()) == 4
        assert all(item["assessment"] is None for item in current.json())
        payload = {
            "dimension": "DURABILITY_10Y",
            "score": "0.00",
            "status": "ASSESSED",
            "effective_at": datetime.now(UTC).isoformat(),
            "rationale": "Explicit zero is an observed score.",
            "actor": "LOCAL_USER",
            "source": "https://example.test/evidence",
        }
        assert (
            client.post(
                f"/v1/companies/{company_id}/score-assessments",
                json={**payload, "dimension": "RISK", "score": "0"},
            ).status_code
            == 422
        )
        created = client.post(f"/v1/companies/{company_id}/score-assessments", json=payload)
        assert created.status_code == 201
        old = created.json()["assessment"]
        assert old["score"] == "0.00"
        corrected = client.post(
            f"/v1/companies/{company_id}/score-assessments",
            json={
                **payload,
                "score": None,
                "status": "MISSING",
                "rationale": "The prior observed score has been withdrawn pending evidence.",
                "superseded_assessment_id": old["id"],
            },
        )
        assert corrected.status_code == 201
        assert corrected.json()["assessment"]["score"] is None
        assert corrected.json()["assessment"]["recorded_at"] > old["recorded_at"]
        assert len(client.get(f"/v1/companies/{company_id}/scores/history").json()) == 2
        current_scores = client.get(current_url).json()
        durability = next(
            item for item in current_scores if item["definition"]["dimension"] == "DURABILITY_10Y"
        )
        assert durability["assessment"]["status"] == "MISSING"
        assert durability["assessment"]["score"] is None
        universe = client.get("/v1/universe/score-summary?search=Score%20API").json()
        assert len(universe) == 1 and universe[0]["company"]["id"] == company_id
        assert len(universe[0]["scores"]) == 4


def test_ranking_definitions_preserve_distinct_workbook_rules_and_inputs(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        definitions = q.ranking_definitions(db)
        assert [item.ranking_type for item in definitions] == [
            "PORTFOLIO",
            "RESEARCH",
            "WATCHLIST",
        ]
        by_type = {item.ranking_type: item for item in definitions}
        assert all(item.version == 1 for item in definitions)
        assert all(item.implementation_status == "NOT_MIGRATED" for item in definitions)
        assert "Portfolio Score" in by_type[RankingType.PORTFOLIO].methodology
        assert "Expected IRR" in by_type[RankingType.WATCHLIST].methodology
        assert "Research Sort Key" in by_type[RankingType.RESEARCH].methodology
        assert by_type[RankingType.WATCHLIST].id != by_type[RankingType.RESEARCH].id


def test_ranking_runs_store_unavailable_and_excluded_entries_without_rank_zero(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        runs = {item.definition.ranking_type: item for item in q.ranking_runs(db)}
        assert set(runs) == set(RankingType)
        assert all(
            item.status == "UNAVAILABLE" and item.ranked_count == 0 for item in runs.values()
        )
        assert all(item.company_count == 4 for item in runs.values())
        portfolio = q.ranking_run_detail(db, runs[RankingType.PORTFOLIO].id)
        assert all(item.entry.position is None for item in portfolio.entries)
        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        harbor = db.scalar(select(Company).where(Company.name.startswith("Harbor")))
        assert cedar and atlas and harbor
        by_id = {item.company.id: item.entry for item in portfolio.entries}
        assert by_id[atlas.id].status == RankingEntryStatus.NOT_MIGRATED
        assert by_id[harbor.id].status == RankingEntryStatus.NOT_ELIGIBLE
        assert by_id[cedar.id].status == RankingEntryStatus.NOT_ELIGIBLE

        watchlist = q.ranking_run_detail(db, runs[RankingType.WATCHLIST].id)
        watchlist_by_id = {item.company.id: item.entry for item in watchlist.entries}
        assert watchlist_by_id[cedar.id].status == RankingEntryStatus.NOT_MIGRATED
        assert watchlist_by_id[atlas.id].status == RankingEntryStatus.NOT_ELIGIBLE
        research = q.ranking_run_detail(db, runs[RankingType.RESEARCH].id)
        assert all(
            item.entry.status == RankingEntryStatus.NOT_MIGRATED for item in research.entries
        )


def test_portfolio_ranking_run_ignores_targets_accepted_after_as_of(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        portfolio = db.scalar(select(Portfolio))
        assert cedar and portfolio
        # Keep the as-of boundary well clear of the host clock's resolution.
        # A separately controlled accepted_at lets the new target be effective
        # before the run while remaining unaccepted at that historical instant.
        run_as_of = datetime.now(UTC) + timedelta(seconds=30)
        previous_targets = db.scalar(
            select(TargetRevision)
            .where(TargetRevision.portfolio_id == portfolio.id, TargetRevision.status == "ACCEPTED")
            .order_by(TargetRevision.effective_at.desc())
            .limit(1)
        )
        assert previous_targets is not None
        future_targets = ops.create_targets(
            db,
            portfolio.id,
            s.TargetCreate(
                actor="LOCAL_USER",
                reason="Future-effective test target.",
                # Effective time is in the past; acceptance is controlled
                # separately to fall just after the as-of boundary.
                effective_at=previous_targets.effective_at + timedelta(microseconds=1),
                allocations=[s.AllocationInput(company_id=cedar.id, weight=Decimal("0.2"))],
            ),
        )
        with patch(
            "portfolio_api.domain.services.now",
            return_value=run_as_of + timedelta(microseconds=1),
        ):
            ops.accept_targets(db, portfolio.id, future_targets.id)
        with patch("portfolio_api.domain.services.now", return_value=run_as_of):
            run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.PORTFOLIO,
                    actor="LOCAL_USER",
                    reason="Current as-of snapshot excludes targets not yet accepted.",
                ),
            )
        detail = q.ranking_run_detail(db, run.id)
        cedar_entry = next(item.entry for item in detail.entries if item.company.id == cedar.id)
        assert cedar_entry.status == RankingEntryStatus.NOT_ELIGIBLE
        assert cedar_entry.position is None


def test_ranking_history_is_snapshot_based_when_lifecycle_and_universe_change(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        assert cedar
        previous = next(
            item for item in q.ranking_runs(db) if item.definition.ranking_type == "WATCHLIST"
        )
        previous_entry = next(
            item.entry
            for item in q.ranking_run_detail(db, previous.id).entries
            if item.company.id == cedar.id
        )
        lifecycle = q.company_read(db, cedar)
        ops.transition_lifecycle(
            db,
            cedar.id,
            s.LifecycleChange(
                new_state="CANDIDATE",
                expected_event_id=lifecycle.lifecycle_event_id,
                actor="LOCAL_USER",
                reason="Explicit test transition.",
                effective_at=datetime.now(UTC),
            ),
        )
        ops.create_company(db, s.CompanyCreate(name="Added after prior ranking"))
        same_as_of = datetime.now(UTC)
        with patch("portfolio_api.domain.services.now", return_value=same_as_of):
            new_run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.WATCHLIST,
                    actor="LOCAL_USER",
                    reason="Capture updated lifecycle and universe.",
                ),
            )
            same_as_of_run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.WATCHLIST,
                    actor="LOCAL_USER",
                    reason="Capture the same effective time a second time.",
                ),
            )
        assert same_as_of_run.recorded_at > new_run.recorded_at
        issuer_rankings = q.company_rankings(db, cedar.id, RankingType.WATCHLIST)
        assert len(issuer_rankings.history) == 3
        assert issuer_rankings.current[0].run is not None
        assert issuer_rankings.current[0].run.id == same_as_of_run.id
        assert issuer_rankings.current[0].entry is not None
        assert issuer_rankings.current[0].entry.status == RankingEntryStatus.NOT_ELIGIBLE
        unchanged = q.ranking_run_detail(db, previous.id)
        cedar_previous = next(
            item.entry for item in unchanged.entries if item.company.id == cedar.id
        )
        assert cedar_previous.id == previous_entry.id
        assert cedar_previous.status == RankingEntryStatus.NOT_MIGRATED
        assert unchanged.run.company_count == 4
        assert q.ranking_run_detail(db, new_run.id).run.company_count == 5


def test_ranking_api_exposes_metadata_runs_current_and_complete_history(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        atlas = db.scalar(select(Company).where(Company.name.startswith("Atlas")))
        assert atlas
        company_id = str(atlas.id)
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        definitions = client.get("/v1/ranking-definitions")
        assert definitions.status_code == 200 and len(definitions.json()) == 3
        assert (
            client.get("/v1/ranking-definitions?ranking_type=RESEARCH").json()[0][
                "implementation_status"
            ]
            == "NOT_MIGRATED"
        )
        runs = client.get("/v1/ranking-runs?ranking_type=RESEARCH")
        assert runs.status_code == 200 and len(runs.json()) == 1
        created = client.post(
            "/v1/ranking-runs",
            json={
                "ranking_type": "RESEARCH",
                "actor": "LOCAL_USER",
                "reason": "API test snapshot.",
                "source": "fixture-test",
            },
        )
        assert created.status_code == 201
        run_id = created.json()["id"]
        assert created.json()["status"] == "UNAVAILABLE"
        detail = client.get(f"/v1/ranking-runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["run"]["company_count"] == 4
        assert len(detail.json()["entries"]) == 4
        issuer = client.get(f"/v1/companies/{company_id}/rankings").json()
        assert len(issuer["current"]) == 3
        assert len([item for item in issuer["history"] if item["run"]["id"] == run_id]) == 1
        summary = client.get("/v1/universe/ranking-summary").json()
        assert len(summary) == 4 and len(summary[0]["rankings"]) == 3


def test_restrictive_foreign_keys_preserve_history(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
    with Session(postgres_engine) as db:
        position = db.scalar(select(HoldingPosition))
        assert position is not None
        db.delete(db.get(Listing, position.listing_id))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_latest_snapshot_is_effective_time_not_import_time(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        identifier = seed(db)
        old = s.SnapshotCreate.model_validate(
            {
                **provenance(),
                "effective_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "completeness": "UNAVAILABLE",
                "positions": [],
            }
        )
        ops.record_holdings(db, identifier, old)
        current = q.overview(db, identifier)
        assert current.snapshot is not None and current.snapshot.completeness == "COMPLETE"


def test_portfolio_writes_never_change_lifecycle(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        identifier = seed(db)
        before = list(db.scalars(select(LifecycleEvent.id)))
        issuer = create_issuer(db)
        revision = ops.create_targets(
            db,
            identifier,
            s.TargetCreate.model_validate(
                {
                    **provenance(),
                    "allocations": [{"company_id": issuer.id, "weight": "0.2"}],
                }
            ),
        )
        ops.accept_targets(db, identifier, revision.id)
        assert q.company_read(db, issuer).lifecycle is None
        assert list(db.scalars(select(LifecycleEvent.id))) == before


def test_cross_company_adr_relationship_rejected(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        first, second = create_issuer(db), create_issuer(db)
        ordinary = ops.create_security(
            db, first.id, s.SecurityCreate(name="Ordinary", security_type="COMMON_STOCK")
        )
        with pytest.raises(ops.DomainError, match="same company"):
            ops.create_security(
                db,
                second.id,
                s.SecurityCreate(
                    name="ADR", security_type="ADR", underlying_security_id=ordinary.id
                ),
            )


def test_new_target_acceptance_validates_persisted_total(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        identifier = seed(db)
        companies = list(db.scalars(select(Company)))
        revision = ops.create_targets(
            db, identifier, s.TargetCreate.model_validate({**provenance(), "allocations": []})
        )
        db.add_all(
            [
                TargetAllocation(revision_id=revision.id, company_id=c.id, weight=Decimal("0.6"))
                for c in companies[:2]
            ]
        )
        db.flush()
        with pytest.raises(ops.DomainError, match="sum to at most 1"):
            ops.accept_targets(db, identifier, revision.id)


def test_api_operations_filtering_conflicts_and_decimal_output(postgres_engine: Engine) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        result = client.post(
            "/v1/companies", json={"name": "Example issuer", "reporting_currency": None}
        )
        assert result.status_code == 201
        issuer = result.json()["id"]
        assert result.json()["lifecycle"] is None
        result = client.post(
            f"/v1/companies/{issuer}/lifecycle-transitions",
            json={**provenance(), "new_state": "WATCHLIST", "expected_event_id": None},
        )
        assert result.status_code == 201
        assert (
            client.get("/v1/universe?lifecycle=WATCHLIST&search=Example").json()[0]["id"] == issuer
        )
        assert client.get("/v1/universe?lifecycle=PORTFOLIO").json() == []
        assert client.get(f"/v1/companies/{uuid4()}").status_code == 404
        security = client.post(
            f"/v1/companies/{issuer}/securities",
            json={"name": "Ordinary", "security_type": "COMMON_STOCK"},
        ).json()["id"]
        listing_payload = {"venue": "X-TEST", "ticker": "EXMP", "currency": "USD"}
        listing = client.post(f"/v1/securities/{security}/listings", json=listing_payload).json()[
            "id"
        ]
        assert (
            client.post(f"/v1/securities/{security}/listings", json=listing_payload).status_code
            == 409
        )
        identifier = client.post(
            "/v1/portfolios", json={"name": "Test", "base_currency": "EUR"}
        ).json()["id"]
        assert (
            client.post(
                "/v1/portfolios", json={"name": "Second", "base_currency": "EUR"}
            ).status_code
            == 409
        )
        snapshot = client.post(
            f"/v1/portfolios/{identifier}/holding-snapshots",
            json={
                **provenance(),
                "completeness": "PARTIAL",
                "positions": [{"listing_id": listing, "quantity": None}],
            },
        ).json()
        assert snapshot["positions"][0]["quantity"] is None
        revision = client.post(
            f"/v1/portfolios/{identifier}/target-revisions",
            json={**provenance(), "allocations": [{"company_id": issuer, "weight": "0.1"}]},
        ).json()
        accepted = client.post(
            f"/v1/portfolios/{identifier}/target-revisions/{revision['id']}/accept"
        )
        assert accepted.status_code == 200
        assert Decimal(accepted.json()["strategic_cash_weight"]) == Decimal("0.9")
        assert (
            client.post(
                f"/v1/portfolios/{identifier}/target-revisions/{revision['id']}/accept"
            ).status_code
            == 409
        )
        overview = client.get(f"/v1/portfolios/{identifier}/overview").json()
        assert overview["companies"][0]["allocation_gap"] is None
        assert Decimal(overview["companies"][0]["target_weight"]) == Decimal("0.1")
        assert (
            client.get(f"/v1/companies/{issuer}").json()["lifecycle_history"][0]["actor"]
            == "LOCAL_USER"
        )


def test_empty_workspace_and_demo_seed_refusal(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db, db.begin():
        assert q.universe(db) == []
        create_issuer(db)
        with pytest.raises(ops.DomainError, match="empty universe"):
            seed(db)
