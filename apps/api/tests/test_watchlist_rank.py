from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from unittest.mock import patch
from uuid import UUID, uuid4

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
    Lifecycle,
    Listing,
    ModelOutputImportBatch,
    ModelOutputSnapshot,
    PriceObservation,
    RankingEntry,
    RankingEntryStatus,
    RankingType,
    ScoreAssessmentStatus,
    ScoreDimension,
    Security,
)
from portfolio_api.domain.seed import seed
from portfolio_api.watchlist_ranking import expected_irr_positions


def test_expected_irr_positions_use_descending_value_and_ticker_tie_break() -> None:
    first, second, third = (uuid4() for _ in range(3))
    positions = expected_irr_positions(
        [
            (first, "ZZZ", Decimal("0.15")),
            (second, "AAA", Decimal("0.15")),
            (third, "MID", Decimal("0.12")),
        ]
    )
    assert positions == {second: 1, first: 2, third: 3}
    assert all(position > 0 for position in positions.values())


def test_documented_formula_matches_representative_legacy_cached_positions() -> None:
    # Captured from the first nine numeric Watchlist rows of the source workbook.
    expected = [
        ("ATAT", Decimal("0.19"), 1),
        ("RELY", Decimal("0.1827"), 2),
        ("NU", Decimal("0.1718274344"), 3),
        ("MNDY", Decimal("0.1577"), 4),
        ("GRAB", Decimal("0.1463"), 5),
        ("TOST", Decimal("0.146"), 6),
        ("APP", Decimal("0.1454689327"), 7),
        ("KVYO", Decimal("0.142"), 8),
        ("MEDI", Decimal("0.14"), 9),
    ]
    company_ids = {ticker: uuid4() for ticker, _value, _rank in expected}
    positions = expected_irr_positions(
        [(company_ids[ticker], ticker, value) for ticker, value, _rank in expected]
    )
    assert [(ticker, positions[company_ids[ticker]]) for ticker, _, _ in expected] == [
        (ticker, cached_rank) for ticker, _, cached_rank in expected
    ]


def _create_watchlist_company(session: Session, name: str, ticker: str) -> Company:
    company = ops.create_company(session, s.CompanyCreate(name=name, reporting_currency="USD"))
    security = ops.create_security(
        session,
        company.id,
        s.SecurityCreate(name=f"{name} common stock", security_type="COMMON_STOCK"),
    )
    ops.create_listing(
        session,
        security.id,
        s.ListingCreate(ticker=ticker, venue="TEST-X", currency="USD"),
    )
    ops.transition_lifecycle(
        session,
        company.id,
        s.LifecycleChange(
            new_state=Lifecycle.WATCHLIST,
            expected_event_id=None,
            actor="LOCAL_USER",
            reason="Ranking fixture lifecycle.",
            effective_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
    )
    ops.create_score_assessment(
        session,
        company.id,
        s.ScoreAssessmentCreate(
            dimension=ScoreDimension.DURABILITY_10Y,
            score="4.0",
            status=ScoreAssessmentStatus.ASSESSED,
            effective_at=datetime.now(UTC) - timedelta(seconds=1),
            rationale="Fixture durability assessment.",
            actor="LOCAL_USER",
        ),
    )
    return company


def _add_legacy_output(
    session: Session,
    batch: ModelOutputImportBatch,
    company: Company,
    ticker: str,
    expected_irr: Decimal | None,
    recorded_at: datetime,
) -> None:
    fingerprint = sha256(f"fixture:{ticker}".encode()).hexdigest()
    session.add(
        ModelOutputSnapshot(
            company_id=company.id,
            batch_id=batch.id,
            model_key=f"LEGACY-{ticker}",
            snapshot_key=f"current:{ticker}",
            source_fingerprint=fingerprint,
            snapshot_kind="CURRENT_CONTRACT",
            contract_version="1.0.0",
            contract_status="PASS",
            output_quality="COMPLETE",
            model_currency="USD",
            currency_status="DOCUMENTED",
            currency_source_ref="fixture:model-currency",
            model_status="Current output",
            effective_at=recorded_at - timedelta(days=1),
            recorded_at=recorded_at,
            actor="IMPORT",
            source="fixture workbook source",
            source_revision_id=f"source-{ticker}",
            revision_source="Fixture workbook",
            rationale="Fixture output used to verify canonical sort semantics.",
            evidence="Synthetic test fixture only.",
            field_issues=[],
            expected_cash_flow_irr=expected_irr,
            weighted_fv=Decimal("20"),
            forward_fundamental_cagr=Decimal("0.12"),
            hurdle=Decimal("0.09"),
            expected_excess=(expected_irr - Decimal("0.09") if expected_irr is not None else None),
        )
    )


def _add_native_output(
    session: Session,
    company: Company,
    listing_id: UUID,
    expected_irr: Decimal,
    recorded_at: datetime,
    *,
    stale_reference: bool = False,
) -> None:
    reference_at = recorded_at - timedelta(days=1) if stale_reference else recorded_at
    price = PriceObservation(
        listing_id=listing_id,
        market_date=reference_at.replace(hour=0, minute=0, second=0, microsecond=0),
        observed_at=reference_at,
        recorded_at=recorded_at,
        provider_close=Decimal("10"),
        split_adjusted_close=Decimal("10"),
        total_return_close=None,
        volume=None,
        currency="USD",
        provider="fixture-provider",
        provider_symbol="TEST:AAA",
        adjustment_basis="Unadjusted fixture close.",
        data_quality="PASS",
        source_ref=f"watchlist-rank-price:{company.id}",
    )
    session.add(price)
    session.flush()
    if stale_reference:
        session.add(
            PriceObservation(
                listing_id=listing_id,
                market_date=recorded_at.replace(hour=0, minute=0, second=0, microsecond=0),
                observed_at=recorded_at,
                recorded_at=recorded_at,
                provider_close=Decimal("11"),
                split_adjusted_close=Decimal("11"),
                total_return_close=None,
                volume=None,
                currency="USD",
                provider="fixture-provider",
                provider_symbol="TEST:AAA",
                adjustment_basis="Unadjusted later fixture close.",
                data_quality="PASS",
                source_ref=f"watchlist-rank-later-price:{company.id}",
            )
        )
        session.flush()
    model = FinancialModel(
        company_id=company.id,
        valuation_listing_id=listing_id,
        model_type="UFCF_DCF_10Y_FADE",
        model_name="Fixture native DCF",
        model_currency="USD",
        source_model_key=f"NATIVE-{company.id}",
        created_at=recorded_at - timedelta(seconds=1),
    )
    session.add(model)
    session.flush()
    revision = FinancialModelRevision(
        model_id=model.id,
        model_type=model.model_type,
        revision_number=1,
        methodology_version="fixture-v1",
        source_revision_id=f"native-{company.id}-r1",
        actor="SYSTEM",
        source="fixture native model",
        rationale="Create a native method-return fixture.",
        effective_at=recorded_at - timedelta(days=1),
        recorded_at=recorded_at - timedelta(seconds=1),
    )
    session.add(revision)
    session.flush()
    model.current_revision_id = revision.id
    session.add(
        FinancialModelOutput(
            revision_id=revision.id,
            status="COMPLETE",
            model_currency="USD",
            price_observation_id=price.id,
            current_price=Decimal("10"),
            price_effective_at=reference_at,
            price_status="FRESH",
            bear_fv=Decimal("12"),
            base_fv=Decimal("20"),
            bull_fv=Decimal("30"),
            bear_probability=Decimal("0.2"),
            base_probability=Decimal("0.6"),
            bull_probability=Decimal("0.2"),
            weighted_fv=Decimal("20"),
            weighted_upside=Decimal("1"),
            expected_cash_flow_irr=expected_irr,
            hurdle=Decimal("0.09"),
            expected_excess=expected_irr - Decimal("0.09"),
            forward_fundamental_cagr=Decimal("0.12"),
        )
    )
    session.flush()


@pytest.mark.integration
def test_watchlist_run_ranks_only_explicit_members_and_snapshots_inputs(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        assert cedar is not None
        alpha = _create_watchlist_company(db, "Alpha Research Fixture", "AAA")
        missing = _create_watchlist_company(db, "Missing Return Fixture", "MIS")
        batch_time = datetime.now(UTC) + timedelta(seconds=5)
        batch = ModelOutputImportBatch(
            id=uuid4(),
            source_digest=sha256(b"watchlist-rank-fixture").hexdigest(),
            workbook_sha256=sha256(b"fixture-workbook").hexdigest(),
            observed_at=batch_time,
            reconciliation={"fixture": True},
        )
        db.add(batch)
        _add_legacy_output(db, batch, cedar, "CDRN", Decimal("0.15"), batch_time)
        _add_legacy_output(db, batch, alpha, "AAA", Decimal("0.15"), batch_time)
        _add_legacy_output(db, batch, missing, "MIS", None, batch_time)
        db.flush()

        with patch("portfolio_api.domain.services.now", return_value=batch_time):
            run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.WATCHLIST,
                    actor="LOCAL_USER",
                    reason="Verify documented Expected IRR ordering and retained inputs.",
                    source="fixture-test",
                ),
            )
        detail = q.ranking_run_detail(db, run.id)
        entries = {item.company.id: item.entry for item in detail.entries}
        assert entries[alpha.id].status == RankingEntryStatus.RANKED
        assert entries[alpha.id].position == 1
        assert entries[cedar.id].position == 2
        assert entries[missing.id].status == RankingEntryStatus.INPUTS_UNAVAILABLE
        assert entries[missing.id].position is None
        missing_context = entries[missing.id].input_snapshot
        assert missing_context is not None
        assert isinstance(missing_context, s.WatchlistRankInputSnapshot)
        assert missing_context.expected_irr is None
        alpha_context = entries[alpha.id].input_snapshot
        assert alpha_context is not None
        assert isinstance(alpha_context, s.WatchlistRankInputSnapshot)
        assert alpha_context.return_semantics == "LEGACY_NORMALIZED_FIELD"
        assert alpha_context.expected_irr == Decimal("0.15")
        assert alpha_context.return_source.listing_ticker == "AAA"
        assert alpha_context.compounder_quality.status == "NOT_ASSESSED"
        assert alpha_context.decision_context == "QUALITY_GATE_THRESHOLDS_NOT_DOCUMENTED"
        assert q.company_read(db, alpha).lifecycle == Lifecycle.WATCHLIST
        stored = db.get(RankingEntry, entries[alpha.id].id)
        assert stored is not None
        with pytest.raises(ValueError, match="append-only"), db.begin_nested():
            stored.position = 9
            db.flush()


@pytest.mark.integration
def test_native_and_legacy_expected_irr_are_never_mixed_in_one_run(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        assert cedar is not None
        native_company = _create_watchlist_company(db, "Native Model Fixture", "NAT")
        stale_company = _create_watchlist_company(db, "Stale Native Fixture", "STL")
        listing = db.scalar(
            select(Listing)
            .join(Security, Security.id == Listing.security_id)
            .where(Security.company_id == native_company.id)
        )
        assert listing is not None
        stale_listing = db.scalar(
            select(Listing)
            .join(Security, Security.id == Listing.security_id)
            .where(Security.company_id == stale_company.id)
        )
        assert stale_listing is not None
        as_of = datetime.now(UTC) + timedelta(seconds=5)
        batch = ModelOutputImportBatch(
            id=uuid4(),
            source_digest=sha256(b"mixed-semantics-fixture").hexdigest(),
            workbook_sha256=sha256(b"mixed-fixture-workbook").hexdigest(),
            observed_at=as_of - timedelta(seconds=1),
            reconciliation={"fixture": True},
        )
        db.add(batch)
        _add_legacy_output(db, batch, cedar, "CDRN", Decimal("0.30"), as_of - timedelta(seconds=1))
        _add_native_output(
            db, native_company, listing.id, Decimal("0.10"), as_of - timedelta(seconds=1)
        )
        _add_native_output(
            db,
            stale_company,
            stale_listing.id,
            Decimal("0.40"),
            as_of - timedelta(seconds=1),
            stale_reference=True,
        )
        with patch("portfolio_api.domain.services.now", return_value=as_of):
            run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.WATCHLIST,
                    actor="LOCAL_USER",
                    reason="Verify separate native and legacy return semantics.",
                ),
            )
        entries = {item.company.id: item.entry for item in q.ranking_run_detail(db, run.id).entries}
        assert entries[native_company.id].status == RankingEntryStatus.RANKED, entries[
            native_company.id
        ].reason
        assert entries[native_company.id].position == 1
        native_context = entries[native_company.id].input_snapshot
        assert native_context is not None
        assert isinstance(native_context, s.WatchlistRankInputSnapshot)
        assert native_context.return_semantics == "NATIVE_METHOD_OUTPUT"
        assert entries[cedar.id].status == RankingEntryStatus.DATA_CHECK
        assert entries[cedar.id].position is None
        legacy_context = entries[cedar.id].input_snapshot
        assert legacy_context is not None
        assert isinstance(legacy_context, s.WatchlistRankInputSnapshot)
        assert legacy_context.expected_irr == Decimal("0.30")
        assert "not assumed comparable" in entries[cedar.id].reason
        assert entries[stale_company.id].status == RankingEntryStatus.DATA_CHECK
        stale_context = entries[stale_company.id].input_snapshot
        assert stale_context is not None
        assert isinstance(stale_context, s.WatchlistRankInputSnapshot)
        assert stale_context.return_semantics == "NATIVE_METHOD_OUTPUT"
        assert stale_context.expected_irr == Decimal("0.40")
        assert "later exact-listing price" in entries[stale_company.id].reason
