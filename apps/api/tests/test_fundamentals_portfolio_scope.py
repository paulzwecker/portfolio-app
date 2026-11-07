"""Portfolio-prioritized SEC scope through the existing guarded bootstrap."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import table_counts
from test_fundamentals_bootstrap import (
    CIK,
    COMPANY_ID,
    RETRIEVED_AT,
    SyntheticSecProvider,
    _execute,
)

from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Actor,
    Company,
    CompanyProviderIdentifier,
    CurrentLifecycle,
    FundamentalsBootstrapCheckpoint,
    FundamentalsBootstrapRun,
    Lifecycle,
    Portfolio,
    ReportedFundamentalObservation,
    Security,
)
from portfolio_api.fundamentals_bootstrap import (
    FundamentalsBootstrapError,
    ReviewedCikMapping,
    _load_reviewed_cik_mappings,
    _next_checkpoint,
    _parser,
    prepare_fundamentals_bootstrap,
    preview_fundamentals_bootstrap,
    reconcile_fundamentals_bootstrap,
)
from portfolio_api.main import create_app
from portfolio_api.reported_fundamentals import record_cik_mapping
from portfolio_api.settings import Settings


@dataclass(frozen=True)
class PortfolioScope:
    portfolio_id: UUID
    snapshot_id: UUID
    held_listing_id: UUID
    fund_listing_id: UUID
    zero_listing_id: UUID
    unmapped_company_id: UUID
    watchlist_company_id: UUID


def _set_lifecycle(session: Session, company_id: UUID, state: str) -> None:
    current = session.get(CurrentLifecycle, company_id)
    services.transition_lifecycle(
        session,
        company_id,
        s.LifecycleChange(
            actor=Actor.IMPORT,
            reason="Synthetic selection evidence",
            effective_at=RETRIEVED_AT,
            new_state=Lifecycle(state),
            expected_event_id=current.event_id if current else None,
        ),
    )


def _source(
    engine: Engine, *, map_watchlist: bool = False, map_held: bool = True
) -> PortfolioScope:
    with Session(engine) as session, session.begin():
        session.add(Company(id=COMPANY_ID, name="Z Held issuer", reporting_currency="USD"))
        session.flush()
        stock = services.create_security(
            session,
            COMPANY_ID,
            s.SecurityCreate(name="Synthetic shares", security_type="COMMON_STOCK"),
        )
        listing = services.create_listing(
            session, stock.id, s.ListingCreate(ticker="SYNTH", venue="NASDAQ", currency="USD")
        )
        second_listing = services.create_listing(
            session, stock.id, s.ListingCreate(ticker="SYNTH", venue="XETRA", currency="EUR")
        )
        fund = Security(name="Standalone synthetic ETF", security_type="ETF", company_id=None)
        session.add(fund)
        session.flush()
        fund_listing = services.create_listing(
            session, fund.id, s.ListingCreate(ticker="SYNF", venue="XETRA", currency="EUR")
        )
        unmapped = services.create_company(
            session, s.CompanyCreate(name="Unmapped held issuer", reporting_currency="EUR")
        )
        unknown = services.create_security(
            session, unmapped.id, s.SecurityCreate(name="Unmapped", security_type="COMMON_STOCK")
        )
        unknown_listing = services.create_listing(
            session, unknown.id, s.ListingCreate(ticker="UNMAPPED", venue="XETRA", currency="EUR")
        )
        zero = services.create_company(
            session, s.CompanyCreate(name="Zero holding issuer", reporting_currency="USD")
        )
        zero_stock = services.create_security(
            session, zero.id, s.SecurityCreate(name="Zero shares", security_type="COMMON_STOCK")
        )
        zero_listing = services.create_listing(
            session, zero_stock.id, s.ListingCreate(ticker="ZERO", venue="NASDAQ", currency="USD")
        )
        watchlist = services.create_company(
            session, s.CompanyCreate(name="A Watchlist issuer", reporting_currency="USD")
        )
        _set_lifecycle(session, watchlist.id, "WATCHLIST")
        unrelated = services.create_company(
            session, s.CompanyCreate(name="Unheld Portfolio label", reporting_currency="USD")
        )
        _set_lifecycle(session, unrelated.id, "PORTFOLIO")
        for company_id, cik, name in (
            (COMPANY_ID, CIK, "Synthetic Holdings Inc."),
            (unrelated.id, "0000000003", "Unrelated Synthetic Inc."),
            (zero.id, "0000000004", "Zero Synthetic Inc."),
        ):
            if company_id == COMPANY_ID and not map_held:
                continue
            record_cik_mapping(
                session, company_id, cik, name, f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}"
            )
        if map_watchlist:
            record_cik_mapping(
                session,
                watchlist.id,
                "0000000002",
                "Watchlist Synthetic Inc.",
                "https://www.sec.gov/edgar/browse/?CIK=2",
            )
        portfolio = services.create_portfolio(
            session, s.PortfolioCreate(name="Synthetic scope portfolio", base_currency="EUR")
        )
        snapshot = services.record_holdings(
            session,
            portfolio.id,
            s.SnapshotCreate(
                effective_at=RETRIEVED_AT,
                actor=Actor.IMPORT,
                reason="Synthetic holdings anchor",
                source="sec-scope-fixture-v1",
                completeness="COMPLETE",
                positions=[
                    s.PositionInput(listing_id=listing.id, quantity=Decimal("2.5")),
                    s.PositionInput(listing_id=second_listing.id, quantity=Decimal("1")),
                    s.PositionInput(listing_id=fund_listing.id, quantity=Decimal("1")),
                    s.PositionInput(listing_id=unknown_listing.id, quantity=Decimal("1")),
                    s.PositionInput(listing_id=zero_listing.id, quantity=Decimal("0")),
                ],
                cash_positions=[s.CashInput(currency="EUR", balance=Decimal("10"))],
            ),
        )
        target = services.create_targets(
            session,
            portfolio.id,
            s.TargetCreate(
                effective_at=RETRIEVED_AT,
                actor=Actor.IMPORT,
                reason="Synthetic strategic target",
                allocations=[s.AllocationInput(company_id=COMPANY_ID, weight=Decimal("0.5"))],
            ),
        )
        services.accept_targets(session, portfolio.id, target.id)
        return PortfolioScope(
            portfolio.id,
            snapshot.id,
            listing.id,
            fund_listing.id,
            zero_listing.id,
            unmapped.id,
            watchlist.id,
        )


def test_sec_cli_requires_unambiguous_company_or_portfolio_selection() -> None:
    args = _parser().parse_args(
        ["preview", "--target-environment", "production", "--portfolio-id", str(uuid4())]
    )
    assert args.portfolio_id is not None and args.company_id is None
    with pytest.raises(SystemExit):
        _parser().parse_args(
            [
                "prepare",
                "--target-environment",
                "rehearsal",
                "--portfolio-id",
                str(uuid4()),
                "--company-id",
                str(COMPANY_ID),
            ]
        )


@pytest.mark.integration
def test_portfolio_preview_includes_unclassified_holdings_without_inventing_lifecycle(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine, map_watchlist=True)
    before = table_counts(postgres_engine)
    with Session(postgres_engine) as session:
        preview = preview_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        selection = preview["selection"]
        assert selection["holding_snapshot_id"] == str(source.snapshot_id)
        assert preview["status"] == "READY" and preview["mapped_company_count"] == 2
        assert [item["company_id"] for item in preview["mappings"]] == [
            str(COMPANY_ID),
            str(source.watchlist_company_id),
        ]
        held = next(
            item for item in selection["companies"] if item["company_id"] == str(COMPANY_ID)
        )
        assert held["selection_basis"] == ["HELD"] and held["lifecycle"] is None
        assert preview["active_company_without_reviewed_cik_count"] == 1
        assert preview["active_companies_without_reviewed_cik"][0]["company_id"] == str(
            source.unmapped_company_id
        )
        assert selection["companyless_held_listings"][0]["listing_id"] == str(
            source.fund_listing_id
        )
        assert selection["excluded_zero_quantity_listing_ids"] == [str(source.zero_listing_id)]
        assert session.get(CurrentLifecycle, COMPANY_ID) is None
    assert table_counts(postgres_engine) == before


@pytest.mark.integration
def test_scoped_import_preserves_portfolio_and_reaches_financials_and_filing_api(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session:
        before = queries.overview(session, source.portfolio_id)
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id = run.id
        session.commit()
    provider = SyntheticSecProvider()
    complete = _execute(postgres_engine, run_id, provider, max_checkpoints=10)
    assert complete["status"] == "PARTIAL"  # Unmapped coverage and amended facts remain explicit.
    assert complete["selection"]["holding_snapshot_id"] == str(source.snapshot_id)
    assert complete["pending_checkpoints"] == 0
    assert {company_id for _stage, company_id, _known in provider.calls} == {COMPANY_ID}
    with Session(postgres_engine) as session:
        after = queries.overview(session, source.portfolio_id)
        assert before.snapshot == after.snapshot and before.target_revision == after.target_revision
        assert session.get(CurrentLifecycle, COMPANY_ID) is None
        assert session.scalar(select(func.count()).select_from(CompanyProviderIdentifier)) == 3
        assert (
            reconcile_fundamentals_bootstrap(session, run_id)["reconciliation"]["status"]
            == "MATCHED"
        )
    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine", lambda _settings, **_kwargs: postgres_engine
    )
    with TestClient(create_app(Settings.model_construct())) as client:
        statements = client.get(
            f"/v1/companies/{COMPANY_ID}/financial-statements?period_type=ANNUAL"
        )
        filings = client.get(f"/v1/companies/{COMPANY_ID}/source-documents")
    assert statements.status_code == filings.status_code == 200
    revenue = next(row for row in statements.json()["rows"] if row["metric"] == "REVENUE")
    assert Decimal(revenue["cells"][0]["value"]) == Decimal("9007199254740994")
    assert len(filings.json()["documents"]) == 4
    repeated = _execute(postgres_engine, run_id, provider, max_checkpoints=10)
    assert repeated["status"] == "PARTIAL" and len(provider.calls) == 3


@pytest.mark.integration
def test_resume_keeps_prepared_order_after_lifecycle_and_holdings_changes(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine, map_watchlist=True)
    with Session(postgres_engine) as session:
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id, frozen = run.id, run.scope
        session.commit()
    provider = SyntheticSecProvider()
    _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    with Session(postgres_engine) as session, session.begin():
        _set_lifecycle(session, COMPANY_ID, "WATCHLIST")
        _set_lifecycle(session, source.watchlist_company_id, "PORTFOLIO")
        services.record_holdings(
            session,
            source.portfolio_id,
            s.SnapshotCreate(
                effective_at=RETRIEVED_AT + timedelta(days=1),
                actor=Actor.IMPORT,
                reason="New synthetic observation",
                completeness="COMPLETE",
                positions=[],
                cash_positions=[],
            ),
        )
    result = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert result["status"] == "PARTIAL" and len(provider.calls) == 2
    with Session(postgres_engine) as session:
        persisted = session.get(FundamentalsBootstrapRun, run_id)
        assert persisted is not None and persisted.scope == frozen
        checkpoints = session.scalars(
            select(FundamentalsBootstrapCheckpoint).where(
                FundamentalsBootstrapCheckpoint.run_id == run_id
            )
        ).all()
        assert {row.company_id for row in checkpoints} == {COMPANY_ID, source.watchlist_company_id}


@pytest.mark.integration
def test_mapping_change_blocks_scoped_resume_before_another_provider_call(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session:
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id = run.id
        session.commit()
    provider = SyntheticSecProvider()
    _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    with Session(postgres_engine) as session, session.begin():
        # Simulate out-of-band administrator corruption in this disposable schema.
        session.execute(
            update(CompanyProviderIdentifier)
            .where(CompanyProviderIdentifier.company_id == COMPANY_ID)
            .values(provider_company_name="Changed source issuer")
        )
    before = table_counts(postgres_engine)
    result = _execute(postgres_engine, run_id, provider, max_checkpoints=10)
    assert result["failure_code"] == "REVIEWED_SEC_MAPPING_CHANGED"
    assert len(provider.calls) == 1 and table_counts(postgres_engine) == before


@pytest.mark.integration
def test_preparation_rejects_mapping_change_between_inventory_reads(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(postgres_engine)
    calls = 0

    def changing_mappings(
        session: Session, company_id: UUID | None = None
    ) -> list[ReviewedCikMapping]:
        nonlocal calls
        calls += 1
        current = _load_reviewed_cik_mappings(session, company_id)
        return (
            [replace(item, provider_company_name="Changed") for item in current]
            if calls == 2
            else current
        )

    monkeypatch.setattr(
        "portfolio_api.fundamentals_bootstrap._load_reviewed_cik_mappings", changing_mappings
    )
    with (
        Session(postgres_engine) as session,
        pytest.raises(FundamentalsBootstrapError, match="changed during preparation"),
    ):
        prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(FundamentalsBootstrapRun)) == 0
        assert (
            session.scalar(select(func.count()).select_from(FundamentalsBootstrapCheckpoint)) == 0
        )
        assert session.scalar(select(func.count()).select_from(ReportedFundamentalObservation)) == 0


@pytest.mark.integration
def test_portfolio_selection_rejects_unknown_portfolio_and_incomplete_latest_snapshot(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        with pytest.raises(FundamentalsBootstrapError, match="does not exist"):
            preview_fundamentals_bootstrap(
                session, target_environment="rehearsal", portfolio_id=uuid4()
            )
        services.record_holdings(
            session,
            source.portfolio_id,
            s.SnapshotCreate(
                effective_at=RETRIEVED_AT + timedelta(days=1),
                actor=Actor.IMPORT,
                reason="Incomplete observation",
                completeness="PARTIAL",
                positions=[],
            ),
        )
        with pytest.raises(FundamentalsBootstrapError, match="current complete"):
            preview_fundamentals_bootstrap(
                session, target_environment="rehearsal", portfolio_id=source.portfolio_id
            )


@pytest.mark.integration
def test_scoped_selection_does_not_borrow_another_portfolios_newer_snapshot(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        # Seed schema-level multi-portfolio data for the isolation regression.
        other = Portfolio(name="Other synthetic portfolio", base_currency="USD")
        session.add(other)
        session.flush()
        services.record_holdings(
            session,
            other.id,
            s.SnapshotCreate(
                effective_at=RETRIEVED_AT + timedelta(days=2),
                actor=Actor.IMPORT,
                reason="Newer other-portfolio snapshot",
                completeness="COMPLETE",
                positions=[],
            ),
        )
        preview = preview_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        assert preview["selection"]["holding_snapshot_id"] == str(source.snapshot_id)
        assert [item["company_id"] for item in preview["mappings"]] == [str(COMPANY_ID)]


@pytest.mark.integration
def test_missing_held_mappings_remain_blocked_despite_unrelated_reviewed_issuers(
    postgres_engine: Engine,
) -> None:
    source = _source(postgres_engine, map_held=False)
    before = table_counts(postgres_engine)
    with Session(postgres_engine) as session:
        preview = preview_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        assert preview["status"] == "BLOCKED"
        assert preview["reason"] == "NO_REVIEWED_SEC_CIK_MAPPINGS"
        assert preview["mappings"] == []
        assert preview["active_company_without_reviewed_cik_count"] == 3
    assert table_counts(postgres_engine) == before


@pytest.mark.integration
def test_newly_reviewed_mapping_cannot_expand_an_existing_run(postgres_engine: Engine) -> None:
    source = _source(postgres_engine)
    with Session(postgres_engine) as session:
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id = run.id
        session.commit()
    with Session(postgres_engine) as session, session.begin():
        record_cik_mapping(
            session,
            source.unmapped_company_id,
            "0000000005",
            "Later reviewed issuer",
            "https://www.sec.gov/edgar/browse/?CIK=5",
        )
    provider = SyntheticSecProvider()
    result = _execute(postgres_engine, run_id, provider, max_checkpoints=10)
    assert result["pending_checkpoints"] == 0
    assert {company_id for _stage, company_id, _known in provider.calls} == {COMPANY_ID}
    with Session(postgres_engine) as session:
        next_preview = preview_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        assert next_preview["mapped_company_count"] == 2
        assert result["coverage"]["review_flags"]["unmapped_active_company_count"] == 2


@pytest.mark.integration
def test_filing_outage_keeps_fundamentals_waiting_until_bounded_retry_succeeds(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(postgres_engine)
    clock = datetime.now(UTC)
    monkeypatch.setattr("portfolio_api.fundamentals_bootstrap._now", lambda: clock)
    with Session(postgres_engine) as session:
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id = run.id
        session.commit()
    provider = SyntheticSecProvider(fail_first_source_request=True)
    first = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert first["retryable_checkpoints"] == 1 and len(provider.calls) == 1
    waiting = _execute(postgres_engine, run_id, provider, max_checkpoints=10)
    assert waiting["retryable_checkpoints"] == 1 and len(provider.calls) == 1
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(ReportedFundamentalObservation)) == 0
    clock += timedelta(seconds=6)
    recovered = _execute(postgres_engine, run_id, provider, max_checkpoints=10)
    assert recovered["retryable_checkpoints"] == recovered["pending_checkpoints"] == 0
    assert [stage for stage, _company, _known in provider.calls] == [
        "SOURCE_DOCUMENTS",
        "SOURCE_DOCUMENTS",
        "SOURCE_DOCUMENTS",
        "REPORTED_FUNDAMENTALS",
    ]
    assert len(recovered["checkpoints"][0]["report"]["failure_history"]) == 1
    with Session(postgres_engine) as session:
        assert (
            reconcile_fundamentals_bootstrap(session, run_id)["reconciliation"]["status"]
            == "MATCHED"
        )


@pytest.mark.integration
def test_one_issuers_filing_cooldown_keeps_other_issuers_eligible(postgres_engine: Engine) -> None:
    source = _source(postgres_engine, map_watchlist=True)
    with Session(postgres_engine) as session:
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=source.portfolio_id
        )
        run_id = run.id
        session.commit()
    provider = SyntheticSecProvider(fail_first_source_request=True)
    failed = _execute(postgres_engine, run_id, provider, max_checkpoints=1)
    assert failed["retryable_checkpoints"] == 1
    with Session(postgres_engine) as session:
        next_work = _next_checkpoint(session, run_id, datetime.now(UTC))
        assert next_work is not None
        assert next_work.company_id == source.watchlist_company_id
        assert next_work.stage == "SOURCE_DOCUMENTS"
