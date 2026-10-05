from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    CorporateAction,
    CurrentLifecycle,
    FxObservation,
    LegacyImportBatch,
    Lifecycle,
    Listing,
    MarketDataBatch,
    ModelOutputImportBatch,
    ModelOutputSnapshot,
    Portfolio,
    PriceObservation,
    PriceRegimeSnapshot,
    RankingEntry,
    RankingRun,
    ScoreAssessment,
    Security,
    TargetAllocation,
    TargetRevision,
)
from portfolio_api.domain.queries import (
    company_model_outputs_current,
    company_model_outputs_history,
    overview,
    universe_model_output_summary,
)
from portfolio_api.domain.seed import seed
from portfolio_api.legacy_import import AlreadyImported, ImportPlan, apply_plan, build_plan
from portfolio_api.market_data import apply_import as apply_market_data_import
from portfolio_api.market_data import build_import as build_market_data_import
from portfolio_api.model_outputs import apply_import as apply_model_output_import
from portfolio_api.model_outputs import build_import as build_model_output_import

ROOT = Path(__file__).resolve().parents[3]
WORKBOOKS = ROOT / "reference" / "workbook"


@pytest.fixture(scope="module")
def legacy_plan() -> ImportPlan:
    return build_plan(
        WORKBOOKS / "Portfolio_Watchlist.xlsx",
        WORKBOOKS / "Market Data.xlsx",
        datetime(2026, 10, 4, 12, tzinfo=UTC),
    )


def test_workbook_plan_is_scoped_deterministic_and_preserves_missing_values(
    legacy_plan: ImportPlan,
) -> None:
    plan = legacy_plan
    report = plan.report()

    assert len(plan.companies) == 219
    assert len(plan.listings) == 90
    assert len(plan.positions) == 22
    assert len(plan.cash) == 2
    assert len(plan.targets) == 16
    assert len(plan.scores) == 506
    assert sum(len(rows) for rows in plan.rankings.values()) == 657
    assert report["effective_time_policy"].startswith("The workbook has no documented")

    # A real zero remains an allocation; blank allocations are never normalized to zero.
    assert any(value == Decimal(0) for value in plan.targets.values())
    assert any(
        company.current_weight is None or company.target_weight is None
        for company in plan.companies
    )
    assert any(company.lifecycle is None for company in plan.companies)

    # Listing currency and alternate instrument identity are preserved exactly.
    nvo = next(item for item in plan.listings if item.canonical_ticker == "NVO")
    spyy = next(item for item in plan.listings if item.canonical_ticker == "SPYY")
    tsm_adr = next(item for item in plan.listings if item.listing_key == "TSM-ADR")
    tsm_local = next(item for item in plan.listings if item.listing_key == "TSM")
    assert (nvo.ticker, nvo.venue, nvo.currency) == ("NOVO-B", "CPH", "DKK")
    assert (spyy.ticker, spyy.venue, spyy.currency, spyy.security_type) == (
        "SPYY",
        "ETR",
        "EUR",
        "ETF",
    )
    assert (tsm_adr.ticker, tsm_adr.venue, tsm_adr.currency, tsm_adr.security_type) == (
        "TSM",
        "NYSE",
        "USD",
        "ADR",
    )
    assert (tsm_local.ticker, tsm_local.venue, tsm_local.currency, tsm_local.security_type) == (
        "2330",
        "TPE",
        "TWD",
        "COMMON_STOCK",
    )
    held_tsm = next(item for item in plan.positions if item.canonical_ticker == "TSM")
    assert (held_tsm.listing_key, held_tsm.listing_ticker, held_tsm.venue) == (
        "TSM-ADR",
        "TSM",
        "NYSE",
    )
    assert plan.target_importable
    assert plan.base_currency == "EUR"
    assert "DURABILITY_10Y" in report["score_coverage"]
    assert report["score_coverage"]["RISK"]["no_assessment_in_snapshot"] > 0
    assert report["ranking_coverage"]["PORTFOLIO"]["ranked"] > 0
    assert any(issue.code == "RANK_VALUE_INVALID" for issue in plan.issues)
    duplicate_ranks = [issue for issue in plan.issues if issue.code == "DUPLICATE_RANK_POSITION"]
    assert duplicate_ranks
    assert all("tie-break requires a unique ordinal" in issue.message for issue in duplicate_ranks)
    assert all(
        item.position is None and item.status.value == "INPUTS_UNAVAILABLE"
        for rows in plan.rankings.values()
        for item in rows
        if "duplicated in the source" in item.reason
    )


@pytest.mark.integration
def test_import_is_auditable_reconciled_and_repeatable(
    legacy_plan: ImportPlan, postgres_engine: Engine
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        report = apply_plan(db, legacy_plan, replace_demo=True)
        portfolio = db.scalar(select(Portfolio).where(Portfolio.is_demo.is_(False)))
        assert portfolio is not None
        imported_overview = overview(db, portfolio.id)
        mismatches = {
            name: {
                "expected": domain["expected"],
                "matched": domain["matched"],
                "unmatched_by_dimension": domain.get("unmatched_by_dimension"),
                "sample_mismatches": domain.get("mismatches", [])[:5],
            }
            for name, domain in report["reconciliation"]["domains"].items()
            if domain["status"] == "MISMATCH"
        }
        assert report["reconciliation"]["mismatch_count"] == 0, mismatches
        assert report["reconciliation"]["domains"]["companies"]["matched"] == 219
        assert report["reconciliation"]["domains"]["strategic_targets"]["matched"] == 16
        assert report["reconciliation"]["domains"]["scores"]["matched"] == 506
        assert imported_overview.snapshot is not None
        assert imported_overview.snapshot.completeness == "COMPLETE"
        assert len(imported_overview.snapshot.positions) == 22
        assert len(imported_overview.snapshot.cash_positions) == 2
        assert len(imported_overview.standalone_positions) == 1
        assert imported_overview.standalone_positions[0].ticker == "SPYY"
        assert imported_overview.portfolio.base_currency == "EUR"
        tsm_company = db.scalar(
            select(Company).where(Company.name == "Taiwan Semiconductor Manufacturing")
        )
        assert tsm_company is not None
        tsm_listings = db.scalars(
            select(Listing).join(Security).where(Security.company_id == tsm_company.id)
        ).all()
        assert {(item.venue, item.ticker, item.currency) for item in tsm_listings} >= {
            ("NYSE", "TSM", "USD"),
            ("TPE", "2330", "TWD"),
        }
        tsm_holding = next(
            item for item in imported_overview.companies if item.company.id == tsm_company.id
        )
        assert [(item.ticker, item.venue, item.currency) for item in tsm_holding.positions] == [
            ("TSM", "NYSE", "USD")
        ]

        assert db.scalar(select(func.count()).select_from(Company)) == 219
        assert db.scalar(select(func.count()).select_from(TargetRevision)) == 1
        assert db.scalar(select(func.count()).select_from(TargetAllocation)) == 16
        assert db.scalar(select(func.count()).select_from(ScoreAssessment)) == 506
        assert db.scalar(select(func.count()).select_from(RankingRun)) == 3
        assert db.scalar(select(func.count()).select_from(RankingEntry)) == 657
        assert db.scalar(select(func.count()).select_from(LegacyImportBatch)) == 1
        standalone = db.scalars(select(Security).where(Security.company_id.is_(None))).all()
        assert len(standalone) == 1, [
            (item.name, item.security_type, item.is_demo) for item in standalone
        ]

        target_revision = imported_overview.target_revision
        assert target_revision is not None
        zero_weight = db.execute(
            select(TargetAllocation.weight).where(
                TargetAllocation.revision_id == target_revision.id,
                TargetAllocation.weight == Decimal(0),
            )
        ).scalar_one_or_none()
        assert zero_weight == Decimal(0)
        lifecycle_count = db.scalar(
            select(func.count())
            .select_from(CurrentLifecycle)
            .where(
                CurrentLifecycle.company_id.in_(
                    select(Company.id).where(Company.is_demo.is_(False))
                )
            )
        )
        assert (lifecycle_count or 0) > 0

        with pytest.raises(AlreadyImported):
            apply_plan(db, legacy_plan)

        market_report, market_rows = build_market_data_import(db, WORKBOOKS / "Market Data.xlsx")
        parity = market_report["calculated_metric_reconciliation"]
        assert market_report["listed_identities_matched"] == 88
        assert market_report["observations_ready"] == 65_535
        assert market_report["price_regime_rows"] == 71
        assert market_report["corporate_actions"] == 2
        assert parity["compared_metric_values"] == 852
        assert parity["discrepancy_count"] == 0
        assert parity["compared_states"] == 142
        assert parity["state_discrepancy_count"] == 0
        assert any(
            issue["code"] == "PRICE_IDENTITY_MISMATCH" and issue.get("ticker") == "6146"
            for issue in market_report["unresolved_issues"]
        )
        result = apply_market_data_import(db, market_report, market_rows)
        assert result["status"] == "APPLIED"
        assert result["imported"] == {
            "price_observations": 65_535,
            "corporate_actions": 2,
            "price_regime_snapshots": 71,
        }
        repeated = apply_market_data_import(db, market_report, market_rows)
        assert repeated["status"] == "ALREADY_APPLIED"
        assert db.scalar(select(func.count()).select_from(MarketDataBatch)) == 1
        assert db.scalar(select(func.count()).select_from(PriceObservation)) == 65_535
        assert db.scalar(select(func.count()).select_from(CorporateAction)) == 2
        assert db.scalar(select(func.count()).select_from(PriceRegimeSnapshot)) == 71
        assert db.scalar(select(func.count()).select_from(FxObservation)) == 0

        model_plan = build_model_output_import(
            db,
            WORKBOOKS / "Portfolio_Watchlist.xlsx",
            datetime(2026, 10, 5, 12, tzinfo=UTC),
        )
        model_report = model_plan.report()
        reconciliation = model_report["field_reconciliation"]
        assert reconciliation["representative_comparison_count"] == 9
        assert reconciliation["mismatches"] == 0
        assert model_report["counts"]["current_contract_rows_matched"] > 100
        assert model_report["counts"]["legacy_history_snapshots"] > 200
        assert model_report["model_currency_coverage"]["UNKNOWN"] > 0
        assert any(
            issue["code"] == "MODEL_COMPANY_UNRESOLVED"
            for issue in model_report["unresolved_issues"]
        )
        plejd = next(
            item
            for item in model_plan.snapshots
            if item["model_key"] == "W-PLEJD" and item["snapshot_kind"].value == "CURRENT_CONTRACT"
        )
        assert plejd["contract_status"] == "DATA_CHECK"
        assert all(plejd[field] is None for field in ("bear_fv", "base_fv", "bull_fv"))
        # The historical ledger does not contain scenario probabilities; they stay null.
        assert all(
            item["bear_probability"] is None
            and item["base_probability"] is None
            and item["bull_probability"] is None
            for item in model_plan.snapshots
            if item["snapshot_kind"].value == "LEGACY_REVISION"
        )

        applied_outputs = apply_model_output_import(db, model_plan)
        assert applied_outputs["status"] == "APPLIED"
        assert applied_outputs["persisted_output_value_mismatches"] == 0
        assert applied_outputs["persisted_snapshots_added"] == len(model_plan.snapshots)
        assert db.scalar(select(func.count()).select_from(ModelOutputImportBatch)) == 1
        assert db.scalar(select(func.count()).select_from(ModelOutputSnapshot)) == len(
            model_plan.snapshots
        )
        repeated_outputs = apply_model_output_import(db, model_plan)
        assert repeated_outputs["status"] == "ALREADY_APPLIED"
        assert repeated_outputs["persisted_snapshots_added"] == 0
        assert repeated_outputs["identical_snapshots_reused"] == len(model_plan.snapshots)

        googl_values = next(
            item
            for item in model_plan.snapshots
            if item["model_key"] == "P-GOOGL" and item["snapshot_kind"].value == "CURRENT_CONTRACT"
        )
        googl = company_model_outputs_current(db, googl_values["company_id"])
        assert googl.status in {"AVAILABLE", "PARTIAL"}
        googl_model = next(item for item in googl.models if item.model_key == "P-GOOGL")
        assert googl_model.status in {"PUBLISHED", "PARTIAL"}
        assert googl_model.snapshot.bear_fv is not None
        assert len(company_model_outputs_history(db, googl_values["company_id"])) > 1
        universe_outputs = universe_model_output_summary(db)
        assert len(universe_outputs) == 219
        assert any(item.outputs.status == "DATA_CHECK" for item in universe_outputs)

    # Accepted revisions are immutable; a correction arrives under a new source key.
    with Session(postgres_engine) as db:
        accepted = db.scalar(select(ModelOutputSnapshot).limit(1))
        assert accepted is not None
        accepted.base_fv = Decimal("1")
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()


def test_unresolved_lifecycle_is_not_mapped_to_a_default(legacy_plan: ImportPlan) -> None:
    # The dry-run plan is intentionally the only input needed for this assertion; unresolved
    # lifecycle is a source gap and must never be converted to DROP, Candidate, or Portfolio.
    unresolved = [company for company in legacy_plan.companies if company.lifecycle is None]
    assert unresolved
    assert all(company.lifecycle not in set(Lifecycle) for company in unresolved)
