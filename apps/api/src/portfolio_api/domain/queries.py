"""Read views combine stored observations; no prices, FX or invented allocation weights."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.consensus_policy import select_consensus_source
from portfolio_api.domain.models import (
    Actor,
    CashPosition,
    Company,
    CompanyProviderIdentifier,
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
    CorporateAction,
    CurrentLifecycle,
    DcfModelAssumptions,
    DcfProjection,
    DcfScenarioAssumptions,
    DcfYearAssumption,
    ExecutionPaceDecision,
    ExecutionPaceRun,
    ExecutionPaceRunStatus,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    FinancialModelType,
    FundamentalMetric,
    FundamentalStatement,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    Lifecycle,
    LifecycleEvent,
    Listing,
    MarketDataBatch,
    ModelOutputSnapshot,
    ModelOutputSnapshotKind,
    OwnerCashFlowAssumptions,
    OwnerCashFlowProjection,
    OwnerCashFlowScenarioAssumptions,
    OwnerCashFlowYearAssumption,
    Portfolio,
    PriceObservation,
    PriceRegimeSnapshot,
    RankingDefinition,
    RankingDefinitionStatus,
    RankingEntry,
    RankingRun,
    RankingType,
    ReportedFundamentalObservation,
    ResidualIncomeAssumptions,
    ResidualIncomeProjection,
    ResidualIncomeScenarioAssumptions,
    ScoreAssessment,
    ScoreDefinition,
    ScoreDefinitionStatus,
    ScoreDimension,
    Security,
    SourceDocument,
    SourceDocumentType,
    TargetAllocation,
    TargetRevision,
    now,
)
from portfolio_api.estimate_momentum import ConsensusObservationPoint, calculate_estimate_momentum
from portfolio_api.reported_fundamentals import resolve_fundamental_period

FRESH_DAYS = 5


def company_read(session: Session, issuer: Company) -> s.CompanyRead:
    pointer = session.get(CurrentLifecycle, issuer.id)
    event = session.get(LifecycleEvent, pointer.event_id) if pointer else None
    return s.CompanyRead(
        id=issuer.id,
        name=issuer.name,
        reporting_currency=issuer.reporting_currency,
        created_at=issuer.created_at,
        is_demo=issuer.is_demo,
        lifecycle=Lifecycle(event.new_state) if event else None,
        lifecycle_event_id=event.id if event else None,
    )


def universe(
    session: Session, lifecycle: Lifecycle | None = None, search: str | None = None
) -> list[s.CompanyRead]:
    statement = select(Company).order_by(Company.name, Company.id)
    if lifecycle:
        statement = (
            statement.join(CurrentLifecycle, CurrentLifecycle.company_id == Company.id)
            .join(
                LifecycleEvent,
                CurrentLifecycle.event_id == LifecycleEvent.id,
            )
            .where(LifecycleEvent.new_state == lifecycle)
        )
    if search:
        # Escape SQL wildcards: searching a ticker/name is literal substring search.
        needle = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matching = (
            select(Security.company_id)
            .join(Listing, Listing.security_id == Security.id)
            .where(
                Listing.ticker.ilike(f"%{needle}%", escape="\\"),
            )
        )
        statement = statement.where(
            Company.name.ilike(f"%{needle}%", escape="\\") | Company.id.in_(matching)
        )
    return [company_read(session, c) for c in session.scalars(statement)]


def snapshot_read(session: Session, snapshot: HoldingSnapshot) -> s.SnapshotRead:
    positions = session.scalars(
        select(HoldingPosition).where(HoldingPosition.snapshot_id == snapshot.id)
    ).all()
    cash = session.scalars(
        select(CashPosition).where(CashPosition.snapshot_id == snapshot.id)
    ).all()
    return s.SnapshotRead(
        id=snapshot.id,
        portfolio_id=snapshot.portfolio_id,
        completeness=snapshot.completeness,
        effective_at=snapshot.effective_at,
        recorded_at=snapshot.recorded_at,
        actor=snapshot.actor,
        reason=snapshot.reason,
        source=snapshot.source,
        positions=[s.PositionInput.model_validate(p) for p in positions],
        cash_positions=[s.CashInput.model_validate(c) for c in cash],
    )


def target_read(session: Session, revision: TargetRevision) -> s.TargetRead:
    items = session.scalars(
        select(TargetAllocation).where(TargetAllocation.revision_id == revision.id)
    ).all()
    invested = sum((a.weight for a in items), Decimal(0))
    return s.TargetRead(
        id=revision.id,
        portfolio_id=revision.portfolio_id,
        status=revision.status,
        effective_at=revision.effective_at,
        recorded_at=revision.recorded_at,
        actor=revision.actor,
        reason=revision.reason,
        source=revision.source,
        accepted_at=revision.accepted_at,
        allocations=[s.AllocationInput.model_validate(a) for a in items],
        invested_weight=invested,
        strategic_cash_weight=Decimal(1) - invested,
    )


def overview(
    session: Session, portfolio_id: UUID, as_of: datetime | None = None
) -> s.PortfolioOverview:
    cutoff = (as_of or now()).astimezone(UTC)
    item = services.portfolio(session, portfolio_id)
    snapshot = session.scalar(
        select(HoldingSnapshot)
        .where(
            HoldingSnapshot.portfolio_id == portfolio_id,
            HoldingSnapshot.effective_at <= cutoff,
            HoldingSnapshot.recorded_at <= cutoff,
        )
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    revision = session.scalar(
        select(TargetRevision)
        .where(
            TargetRevision.portfolio_id == portfolio_id,
            TargetRevision.status == "ACCEPTED",
            TargetRevision.effective_at <= cutoff,
            TargetRevision.recorded_at <= cutoff,
            TargetRevision.accepted_at <= cutoff,
        )
        .order_by(TargetRevision.effective_at.desc(), TargetRevision.accepted_at.desc())
        .limit(1)
    )
    snapshot_view = snapshot_read(session, snapshot) if snapshot else None
    target_view = target_read(session, revision) if revision else None
    targets = {a.company_id: a.weight for a in target_view.allocations} if target_view else {}
    positions: dict[UUID, list[s.HoldingContext]] = {}
    standalone_positions: list[s.HoldingContext] = []
    valuation_gaps: list[s.ValuationGap] = []
    snapshot_cash: list[CashPosition] = []
    if snapshot:
        snapshot_cash = list(
            session.scalars(select(CashPosition).where(CashPosition.snapshot_id == snapshot.id))
        )
        rows = session.execute(
            select(HoldingPosition, Listing, Security)
            .join(Listing, HoldingPosition.listing_id == Listing.id)
            .join(Security, Listing.security_id == Security.id)
            .where(HoldingPosition.snapshot_id == snapshot.id)
            .order_by(Listing.ticker, Listing.venue)
        ).all()
        for position, listing, security in rows:
            market = listing_market_data(
                session,
                listing,
                history_limit=0,
                market_as_of=cutoff.date(),
                known_at=cutoff,
            )
            observation = market.latest
            price_matches_holdings = (
                snapshot is not None
                and observation is not None
                and abs((snapshot.effective_at.date() - observation.market_date.date()).days)
                <= FRESH_DAYS
            )
            value = (
                position.quantity * observation.split_adjusted_close
                if position.quantity is not None
                and observation is not None
                and observation.split_adjusted_close is not None
                and market.freshness == "FRESH"
                and price_matches_holdings
                else None
            )
            valuation_status: str
            if position.quantity is None:
                valuation_status = "QUANTITY_UNAVAILABLE"
            elif (
                observation is None
                or market.freshness in {"NO_DATA", "STALE", "QUALITY_CHECK"}
                or not price_matches_holdings
            ):
                valuation_status = "PRICE_UNAVAILABLE"
            elif listing.currency == item.base_currency:
                valuation_status = "VALUED"
            elif (
                _fx_rate(
                    session,
                    listing.currency,
                    item.base_currency,
                    observation.observed_at or observation.market_date,
                    known_at=cutoff,
                )
                is None
            ):
                valuation_status = "FX_UNAVAILABLE"
            else:
                valuation_status = "VALUED"
            base_value = None
            if value is not None and observation is not None and valuation_status == "VALUED":
                rate = _fx_rate(
                    session,
                    listing.currency,
                    item.base_currency,
                    observation.observed_at or observation.market_date,
                    known_at=cutoff,
                )
                if listing.currency == item.base_currency:
                    base_value = value
                elif rate is not None:
                    base_value = value * rate
            context = s.HoldingContext(
                listing_id=listing.id,
                security_id=security.id,
                ticker=listing.ticker,
                venue=listing.venue,
                currency=listing.currency,
                security_name=security.name,
                quantity=position.quantity,
                latest_price=(observation.split_adjusted_close if observation else None),
                price_date=(observation.market_date if observation else None),
                price_currency=(observation.currency if observation else None),
                price_freshness=market.freshness,
                native_market_value=value,
                base_market_value=base_value,
                valuation_status=valuation_status,
            )
            if base_value is None:
                valuation_gaps.append(
                    s.ValuationGap(
                        identity=f"{listing.venue}:{listing.ticker}", reason=valuation_status
                    )
                )
            if security.company_id is None:
                standalone_positions.append(context)
            else:
                positions.setdefault(security.company_id, []).append(context)
    cash_valuations: list[s.CashValuation] = []
    cash_values: list[Decimal] = []
    for cash in snapshot_cash:
        rate = (
            _fx_rate(
                session,
                cash.currency,
                item.base_currency,
                snapshot.effective_at,
                known_at=cutoff,
            )
            if cash.balance is not None and snapshot is not None
            else None
        )
        base_value = (
            cash.balance
            if cash.balance is not None and cash.currency == item.base_currency
            else cash.balance * rate
            if cash.balance is not None and rate is not None
            else None
        )
        status = (
            "BALANCE_UNAVAILABLE"
            if cash.balance is None
            else "VALUED"
            if base_value is not None
            else "FX_UNAVAILABLE"
        )
        cash_valuations.append(
            s.CashValuation(
                currency=cash.currency,
                balance=cash.balance,
                base_market_value=base_value,
                valuation_status=status,
            )
        )
        if base_value is None:
            valuation_gaps.append(s.ValuationGap(identity=f"cash:{cash.currency}", reason=status))
        else:
            cash_values.append(base_value)
    ids = set(positions) | set(targets)
    companies = (
        session.scalars(select(Company).where(Company.id.in_(ids)).order_by(Company.name)).all()
        if ids
        else []
    )
    company_values: dict[UUID, Decimal | None] = {}
    for company in companies:
        company_positions = positions.get(company.id, [])
        if company_positions and all(p.base_market_value is not None for p in company_positions):
            company_values[company.id] = sum(
                (p.base_market_value for p in company_positions if p.base_market_value is not None),
                Decimal(0),
            )
        elif not company_positions:
            company_values[company.id] = (
                Decimal(0) if snapshot and snapshot.completeness == "COMPLETE" else None
            )
        else:
            company_values[company.id] = None
    all_positions = [
        position for rows in positions.values() for position in rows
    ] + standalone_positions
    missing_prices = any(
        position.valuation_status == "PRICE_UNAVAILABLE" for position in all_positions
    )
    missing_fx = any(
        position.valuation_status == "FX_UNAVAILABLE" for position in all_positions
    ) or any(item.valuation_status == "FX_UNAVAILABLE" for item in cash_valuations)
    incomplete = (
        not snapshot
        or snapshot.completeness != "COMPLETE"
        or (cutoff.date() - snapshot.effective_at.date()).days > FRESH_DAYS
    )
    total: Decimal | None = None
    if snapshot and snapshot.completeness == "COMPLETE" and not valuation_gaps:
        total = sum(
            (
                position.base_market_value
                for position in all_positions
                if position.base_market_value is not None
            ),
            Decimal(0),
        ) + sum(cash_values, Decimal(0))
    if not snapshot:
        valuation_status = "NO_HOLDING_SNAPSHOT"
    elif incomplete:
        valuation_status = "INCOMPLETE_HOLDINGS"
    elif missing_prices:
        valuation_status = "INCOMPLETE_PRICE_COVERAGE"
    elif missing_fx:
        valuation_status = "INCOMPLETE_FX_COVERAGE"
    elif total is not None:
        valuation_status = "VALUED"
    else:
        valuation_status = "INCOMPLETE_PRICE_COVERAGE"

    def current_weight(company_id: UUID) -> Decimal | None:
        value = company_values.get(company_id)
        if value is None or total is None or total <= 0:
            return None
        return value / total

    company_contexts: list[s.CompanyPortfolioContext] = []
    for company in companies:
        weight = current_weight(company.id)
        company_value = company_values.get(company.id)
        allocation_status = (
            "VALUED"
            if total is not None and company_value is not None
            else "PRICE_COVERAGE_INCOMPLETE"
            if missing_prices
            else "FX_UNAVAILABLE"
            if missing_fx
            else "PORTFOLIO_TOTAL_UNAVAILABLE"
        )
        company_contexts.append(
            s.CompanyPortfolioContext(
                company=company_read(session, company),
                positions=positions.get(company.id, []),
                target_weight=targets.get(company.id),
                current_market_value=company_value,
                current_market_currency=item.base_currency if company_value is not None else None,
                current_weight=weight,
                allocation_gap=(
                    targets[company.id] - weight
                    if weight is not None and company.id in targets
                    else None
                ),
                allocation_status=allocation_status,
            )
        )

    return s.PortfolioOverview(
        portfolio=s.PortfolioRead.model_validate(item),
        snapshot=snapshot_view,
        target_revision=target_view,
        standalone_positions=standalone_positions,
        companies=company_contexts,
        valuation_status=valuation_status,
        base_market_value=total,
        valuation_currency=item.base_currency,
        cash_valuations=cash_valuations,
        valuation_gaps=valuation_gaps,
    )


def _fx_rate(
    session: Session,
    source: str | None,
    target: str,
    as_of: object,
    known_at: datetime | None = None,
) -> Decimal | None:
    if not source:
        return None
    if source == target:
        return Decimal(1)
    if not isinstance(as_of, datetime):
        return None
    cutoff = known_at or now()
    age_as_of = (cutoff.date() - as_of.date()).days
    if age_as_of > 5:
        return None
    rows = session.scalars(
        select(FxObservation)
        .where(
            FxObservation.effective_at <= min(as_of, cutoff),
            FxObservation.effective_at >= as_of - timedelta(days=FRESH_DAYS),
            FxObservation.recorded_at <= cutoff,
            FxObservation.data_quality == "PASS",
            or_(
                and_(
                    FxObservation.base_currency == source,
                    FxObservation.quote_currency == target,
                ),
                and_(
                    FxObservation.base_currency == target,
                    FxObservation.quote_currency == source,
                ),
            ),
        )
        .order_by(FxObservation.effective_at.desc(), FxObservation.recorded_at.desc())
        .limit(1)
    ).all()
    for fx in rows:
        if (as_of.date() - fx.effective_at.date()).days < 0 or (
            as_of.date() - fx.effective_at.date()
        ).days > 5:
            continue
        if fx.base_currency == source and fx.quote_currency == target:
            return fx.rate
        if fx.base_currency == target and fx.quote_currency == source:
            return Decimal(1) / fx.rate
    return None


def _market_cutoffs(
    market_as_of: date | None, known_at: datetime | None
) -> tuple[datetime | None, datetime]:
    cutoff = known_at or now()
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    market_end = datetime.combine(market_as_of, time.max, UTC) if market_as_of is not None else None
    return market_end, cutoff.astimezone(UTC)


def _price_ordering() -> tuple[ColumnElement[Any], ...]:
    return (
        case(
            (PriceObservation.data_quality == "PASS", 0),
            (PriceObservation.data_quality == "PASS_VERIFIED_FALLBACK", 1),
            (PriceObservation.data_quality == "UNSPECIFIED", 2),
            else_=3,
        ),
        case((PriceObservation.provider == "YAHOO_FINANCE", 0), else_=1),
        case((PriceObservation.price_kind == "CURRENT_QUOTE", 0), else_=1),
        PriceObservation.recorded_at.desc(),
    )


def listing_market_data(
    session: Session,
    listing: Listing,
    history_limit: int = 90,
    market_as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.ListingMarketData:
    market_end, knowledge_cutoff = _market_cutoffs(market_as_of, known_at)
    price_filters = [
        PriceObservation.listing_id == listing.id,
        PriceObservation.recorded_at <= knowledge_cutoff,
        or_(
            PriceObservation.observed_at.is_(None), PriceObservation.observed_at <= knowledge_cutoff
        ),
    ]
    if market_end is not None:
        price_filters.append(PriceObservation.market_date <= market_end)
    latest_model = session.scalar(
        select(PriceObservation)
        .where(*price_filters)
        .order_by(PriceObservation.market_date.desc(), *_price_ordering())
        .limit(1)
    )
    history: list[PriceObservation] = []
    if history_limit > 0:
        ranked = (
            select(
                PriceObservation.id.label("observation_id"),
                func.row_number()
                .over(
                    partition_by=PriceObservation.market_date,
                    order_by=_price_ordering(),
                )
                .label("day_rank"),
            )
            .where(*price_filters, PriceObservation.price_kind == "DAILY_CLOSE")
            .subquery()
        )
        history = list(
            session.scalars(
                select(PriceObservation)
                .join(ranked, PriceObservation.id == ranked.c.observation_id)
                .where(ranked.c.day_rank == 1)
                .order_by(PriceObservation.market_date.desc())
                .limit(history_limit)
            )
        )
    comparison_date = market_as_of or knowledge_cutoff.date()
    age = (comparison_date - latest_model.market_date.date()).days if latest_model else None
    if latest_model is None:
        freshness = "NO_DATA"
    elif (
        latest_model.data_quality not in {"PASS", "PASS_VERIFIED_FALLBACK"}
        or latest_model.split_adjusted_close is None
    ):
        freshness = "QUALITY_CHECK"
    elif age is not None and age > FRESH_DAYS:
        freshness = "STALE"
    else:
        freshness = "FRESH"
    regime_statement = (
        select(PriceRegimeSnapshot)
        .join(MarketDataBatch, PriceRegimeSnapshot.batch_id == MarketDataBatch.id)
        .where(
            PriceRegimeSnapshot.listing_id == listing.id,
            MarketDataBatch.recorded_at <= knowledge_cutoff,
        )
        .order_by(PriceRegimeSnapshot.as_of.desc())
        .limit(1)
    )
    if market_end is not None:
        regime_statement = regime_statement.where(PriceRegimeSnapshot.as_of <= market_end)
    regime = session.scalar(regime_statement)
    return s.ListingMarketData(
        listing=s.ListingRead.model_validate(listing),
        latest=s.PriceObservationRead.model_validate(latest_model) if latest_model else None,
        freshness=freshness,
        age_days=age,
        price_regime=s.PriceRegimeRead.model_validate(regime) if regime else None,
        history=[s.PriceObservationRead.model_validate(observation) for observation in history],
    )


def company_market_data(
    session: Session,
    company_id: UUID,
    history_limit: int = 90,
    market_as_of: date | None = None,
    known_at: datetime | None = None,
) -> list[s.ListingMarketData]:
    services.company(session, company_id)
    listings = session.scalars(
        select(Listing)
        .join(Security, Listing.security_id == Security.id)
        .where(Security.company_id == company_id)
        .order_by(Listing.venue, Listing.ticker)
    ).all()
    return [
        listing_market_data(session, listing, history_limit, market_as_of, known_at)
        for listing in listings
    ]


def company_reported_fundamentals(
    session: Session,
    company_id: UUID,
    period_type: str | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    effective_cutoff: datetime | None = None,
) -> s.CompanyReportedFundamentalsRead:
    """Resolve immutable reported facts with visible precedence and conflict candidates."""

    services.company(session, company_id)
    identifiers = list(
        session.scalars(
            select(CompanyProviderIdentifier).where(
                CompanyProviderIdentifier.company_id == company_id
            )
        )
    )
    sec_ids = [
        item.identifier_value
        for item in identifiers
        if item.provider_id == "sec_edgar" and item.identifier_type == "SEC_CIK"
    ]
    if not sec_ids:
        identity_status = "UNMAPPED"
    elif len(sec_ids) == 1:
        identity_status = "MAPPED"
    else:
        identity_status = "AMBIGUOUS"

    statement = select(ReportedFundamentalObservation).where(
        ReportedFundamentalObservation.company_id == company_id
    )
    if period_type is not None:
        statement = statement.where(ReportedFundamentalObservation.period_type == period_type)
    if as_of is not None:
        cutoff = effective_cutoff or datetime.combine(as_of, time.max, UTC)
        statement = statement.where(
            ReportedFundamentalObservation.period_end <= cutoff,
            ReportedFundamentalObservation.filed_at.is_not(None),
            ReportedFundamentalObservation.filed_at <= cutoff,
        )
    if known_at is not None:
        statement = statement.where(
            ReportedFundamentalObservation.recorded_at <= known_at,
            ReportedFundamentalObservation.observed_at <= known_at,
        )
    observations = list(
        session.scalars(
            statement.order_by(
                ReportedFundamentalObservation.period_end.desc(),
                ReportedFundamentalObservation.metric,
                ReportedFundamentalObservation.currency,
                ReportedFundamentalObservation.recorded_at.desc(),
            )
        )
    )

    groups: dict[tuple[Any, ...], list[ReportedFundamentalObservation]] = {}
    for item in observations:
        key = (
            item.metric,
            item.statement,
            item.period_type,
            item.period_start,
            item.period_end,
            item.fiscal_year,
            item.fiscal_period,
            item.currency,
            item.unit,
        )
        groups.setdefault(key, []).append(item)

    period_reads: list[s.ReportedFundamentalPeriodRead] = []
    for key, history in groups.items():
        resolution = resolve_fundamental_period(history)
        history.sort(
            key=lambda item: (
                item.filed_at or datetime.min.replace(tzinfo=UTC),
                item.observed_at,
                item.recorded_at,
            ),
            reverse=True,
        )
        period_reads.append(
            s.ReportedFundamentalPeriodRead(
                metric=key[0],
                statement=key[1],
                period_type=key[2],
                period_start=key[3],
                period_end=key[4],
                fiscal_year=key[5],
                fiscal_period=key[6],
                currency=key[7],
                unit=key[8],
                value=resolution.selected.value if resolution.selected is not None else None,
                selection_status=resolution.status,
                selected_observation=(
                    s.ReportedFundamentalObservationRead.model_validate(resolution.selected)
                    if resolution.selected is not None
                    else None
                ),
                observations=[
                    s.ReportedFundamentalObservationRead.model_validate(item) for item in history
                ],
            )
        )

    period_reads.sort(
        key=lambda item: (
            item.period_end,
            item.metric.value,
            item.currency or "",
            item.unit,
        ),
        reverse=True,
    )
    coverage: list[s.ReportedFundamentalCoverageRead] = []
    for metric in FundamentalMetric:
        metric_periods = [item for item in period_reads if item.metric == metric]
        if not metric_periods:
            status = "NOT_IMPORTED"
            latest_period_end = None
        else:
            latest_period_end = max(item.period_end for item in metric_periods)
            latest = [item for item in metric_periods if item.period_end == latest_period_end]
            status = (
                "CONFLICT"
                if any(item.selection_status == "CONFLICT" for item in latest)
                else "DATA_CHECK"
                if any(item.selection_status == "DATA_CHECK" for item in latest)
                else "AVAILABLE"
            )
        coverage.append(
            s.ReportedFundamentalCoverageRead(
                metric=metric,
                statement=(
                    metric_periods[0].statement if metric_periods else _metric_statement(metric)
                ),
                observation_count=sum(len(item.observations) for item in metric_periods),
                latest_period_end=latest_period_end,
                status=status,
            )
        )
    return s.CompanyReportedFundamentalsRead(
        company_id=company_id,
        provider_identity_status=identity_status,
        provider_ids=sorted(set(sec_ids)),
        coverage=coverage,
        periods=period_reads,
        as_of=as_of,
        known_at=known_at,
        latest_observed_at=max((item.observed_at for item in observations), default=None),
    )


def company_source_documents(
    session: Session,
    company_id: UUID,
    document_type: SourceDocumentType | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    limit: int = 100,
) -> s.CompanySourceDocumentsRead:
    """Return immutable filing/source metadata bounded by publication and knowledge time."""

    services.company(session, company_id)
    identifiers = list(
        session.scalars(
            select(CompanyProviderIdentifier).where(
                CompanyProviderIdentifier.company_id == company_id,
                CompanyProviderIdentifier.provider_id == "sec_edgar",
                CompanyProviderIdentifier.identifier_type == "SEC_CIK",
            )
        )
    )
    if not identifiers:
        identity_status = "UNMAPPED"
    elif len(identifiers) == 1:
        identity_status = "MAPPED"
    else:
        identity_status = "AMBIGUOUS"
    statement = select(SourceDocument).where(SourceDocument.company_id == company_id)
    if document_type is not None:
        statement = statement.where(SourceDocument.document_type == document_type.value)
    if as_of is not None:
        cutoff = as_of
        statement = statement.where(
            or_(
                SourceDocument.filed_at <= cutoff,
                SourceDocument.published_at <= cutoff,
            )
        )
    if known_at is not None:
        statement = statement.where(
            SourceDocument.recorded_at <= known_at,
            or_(SourceDocument.retrieved_at.is_(None), SourceDocument.retrieved_at <= known_at),
        )
    documents = list(
        session.scalars(
            statement.order_by(
                func.coalesce(SourceDocument.published_at, SourceDocument.filed_at)
                .desc()
                .nullslast(),
                SourceDocument.recorded_at.desc(),
                SourceDocument.external_identifier,
            ).limit(limit)
        )
    )
    return s.CompanySourceDocumentsRead(
        company_id=company_id,
        sec_identity_status=identity_status,
        source_count=len(documents),
        as_of=as_of,
        known_at=known_at,
        documents=[s.SourceDocumentRead.model_validate(item) for item in documents],
    )


def company_consensus_estimates(
    session: Session,
    company_id: UUID,
    as_of: date | None = None,
    known_at: datetime | None = None,
    effective_cutoff: datetime | None = None,
) -> s.CompanyConsensusEstimatesRead:
    """Return separate provider histories under an explicit no-blending continuity rule."""
    services.company(session, company_id)
    as_of_cutoff = effective_cutoff or datetime.combine(as_of or date.today(), time.max, UTC)
    mappings = list(
        session.scalars(
            select(ConsensusEstimateProviderMapping)
            .where(
                ConsensusEstimateProviderMapping.company_id == company_id,
                ConsensusEstimateProviderMapping.effective_from <= as_of_cutoff,
                ConsensusEstimateProviderMapping.recorded_at
                <= (known_at or datetime.max.replace(tzinfo=UTC)),
            )
            .order_by(ConsensusEstimateProviderMapping.effective_from.desc())
        )
    )
    # A mapping is append-only. For each provider role, only its newest assignment
    # effective by the requested date is current; earlier mappings remain queryable
    # through an earlier as_of date.
    current_mapping_by_source: dict[tuple[str, str], ConsensusEstimateProviderMapping] = {}
    for mapping in mappings:
        key = (mapping.role, mapping.provider_id)
        current_mapping_by_source.setdefault(key, mapping)
    current_mappings = list(current_mapping_by_source.values())
    chosen, continuity = select_consensus_source(current_mappings)
    fallbacks = [item for item in current_mappings if item.role == "FALLBACK"]

    mapping_ids = [item.id for item in current_mappings]
    statement = (
        select(ConsensusEstimateObservation).where(
            ConsensusEstimateObservation.company_id == company_id,
            ConsensusEstimateObservation.provider_mapping_id.in_(mapping_ids),
            ConsensusEstimateObservation.snapshot_date <= (as_of or date.today()),
        )
        if mapping_ids
        else None
    )
    if statement is not None:
        if known_at is not None:
            statement = statement.where(
                ConsensusEstimateObservation.recorded_at <= known_at,
                (ConsensusEstimateObservation.observed_at.is_(None))
                | (ConsensusEstimateObservation.observed_at <= known_at),
            )
        observations = list(
            session.scalars(
                statement.order_by(
                    ConsensusEstimateObservation.snapshot_date.desc(),
                    ConsensusEstimateObservation.observed_at.desc().nullslast(),
                    ConsensusEstimateObservation.recorded_at.desc(),
                )
            )
        )
    else:
        observations = []

    grouped: dict[UUID, list[ConsensusEstimateObservation]] = defaultdict(list)
    for item in observations:
        grouped[item.provider_mapping_id].append(item)
    providers: list[s.ConsensusEstimateProviderRead] = []
    today = date.today()
    for mapping in sorted(
        current_mappings, key=lambda item: (item.role != "PRIMARY", item.priority, item.provider_id)
    ):
        facts = grouped.get(mapping.id, [])
        periods: dict[tuple[Any, ...], list[ConsensusEstimateObservation]] = defaultdict(list)
        for item in facts:
            period_key = (
                item.metric,
                item.period_type,
                item.forecast_period,
                item.period_end,
                item.currency,
                item.unit,
            )
            periods[period_key].append(item)
        period_reads: list[s.ConsensusEstimatePeriodRead] = []
        for period_key, history in periods.items():
            history.sort(
                key=lambda item: (
                    item.snapshot_date,
                    item.observed_at or datetime.min.replace(tzinfo=UTC),
                    item.recorded_at,
                ),
                reverse=True,
            )
            period_reads.append(
                s.ConsensusEstimatePeriodRead(
                    metric=period_key[0],
                    period_type=period_key[1],
                    forecast_period=period_key[2],
                    period_end=period_key[3],
                    currency=period_key[4],
                    unit=period_key[5],
                    current_observation=s.ConsensusEstimateObservationRead.model_validate(
                        history[0]
                    ),
                    history=[
                        s.ConsensusEstimateObservationRead.model_validate(item) for item in history
                    ],
                )
            )
        period_reads.sort(
            key=lambda item: (item.period_end or date.max, item.period_type, item.metric),
            reverse=False,
        )
        latest = facts[0] if facts else None
        latest_day = (
            latest.observed_at.date()
            if latest and latest.observed_at
            else latest.snapshot_date
            if latest
            else None
        )
        age = (today - latest_day).days if latest_day else None
        freshness = (
            "NO_DATA"
            if latest is None
            else "DATA_CHECK"
            if latest.data_quality != "PASS"
            else "FRESH"
            if age is not None and age <= 14
            else "STALE"
        )
        selected = mapping.id == (chosen.id if chosen else None)
        providers.append(
            s.ConsensusEstimateProviderRead(
                provider_id=mapping.provider_id,
                provider_symbol=mapping.provider_symbol,
                role=mapping.role,
                priority=mapping.priority,
                selected=selected,
                mapping_status="SELECTED"
                if selected
                else "AMBIGUOUS"
                if continuity == "AMBIGUOUS_FALLBACK"
                and mapping.role == "FALLBACK"
                and mapping.priority == min((i.priority for i in fallbacks), default=-1)
                else "ALTERNATE",
                currency=mapping.currency,
                currency_evidence_source=mapping.currency_evidence_source,
                identity_evidence_source=mapping.evidence_source,
                effective_from=mapping.effective_from,
                freshness=freshness,
                latest_snapshot_date=latest.snapshot_date if latest else None,
                latest_observed_at=latest.observed_at if latest else None,
                observation_count=len(facts),
                missing_metrics=[
                    metric
                    for metric in ("REVENUE", "EPS")
                    if not any(item.metric == metric for item in facts)
                ],
                periods=period_reads,
            )
        )
    if continuity == "PRIMARY_SELECTED" and chosen is not None and not grouped.get(chosen.id):
        continuity = "PRIMARY_NO_DATA"
    return s.CompanyConsensusEstimatesRead(
        company_id=company_id,
        continuity_status=continuity,
        selected_provider_id=chosen.provider_id if chosen else None,
        as_of=as_of,
        known_at=known_at,
        providers=providers,
    )


def company_estimate_momentum(
    session: Session,
    company_id: UUID,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyEstimateMomentumRead:
    """Return the deterministic momentum view from one selected provider stream."""
    services.company(session, company_id)
    day = as_of or date.today()
    return _estimate_momentum_for_companies(session, [company_id], day, known_at)[company_id]


def universe_estimate_momentum(
    session: Session,
    lifecycle: Lifecycle | None = None,
    search: str | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> list[s.UniverseEstimateMomentumRead]:
    """Build a bulk summary without per-company query loops or provider blending."""
    companies = universe(session, lifecycle, search)
    day = as_of or date.today()
    signals = _estimate_momentum_for_companies(
        session, [company.id for company in companies], day, known_at
    )
    return [
        s.UniverseEstimateMomentumRead(
            company=company,
            estimate_momentum=s.EstimateMomentumSummaryRead.model_validate(
                signals[company.id].model_dump(exclude={"periods"})
            ),
        )
        for company in companies
    ]


def _estimate_momentum_for_companies(
    session: Session,
    company_ids: list[UUID],
    as_of: date,
    known_at: datetime | None,
) -> dict[UUID, s.CompanyEstimateMomentumRead]:
    if not company_ids:
        return {}
    effective_cutoff = datetime.combine(as_of, time.max, UTC)
    mapping_statement = select(ConsensusEstimateProviderMapping).where(
        ConsensusEstimateProviderMapping.company_id.in_(company_ids),
        ConsensusEstimateProviderMapping.effective_from <= effective_cutoff,
        ConsensusEstimateProviderMapping.recorded_at
        <= (known_at or datetime.max.replace(tzinfo=UTC)),
    )
    mappings = list(
        session.scalars(
            mapping_statement.order_by(ConsensusEstimateProviderMapping.effective_from.desc())
        )
    )
    latest_by_source: dict[tuple[UUID, str, str], ConsensusEstimateProviderMapping] = {}
    for mapping in mappings:
        key = (mapping.company_id, mapping.role, mapping.provider_id)
        latest_by_source.setdefault(key, mapping)
    mappings_by_company: dict[UUID, list[ConsensusEstimateProviderMapping]] = defaultdict(list)
    for mapping in latest_by_source.values():
        mappings_by_company[mapping.company_id].append(mapping)
    selected_by_company = {
        company_id: select_consensus_source(mappings_by_company.get(company_id, []))
        for company_id in company_ids
    }
    selected_mappings = {
        company_id: selected
        for company_id, (selected, _status) in selected_by_company.items()
        if selected is not None
    }
    selected_ids = [item.id for item in selected_mappings.values()]
    observation_statement = (
        select(ConsensusEstimateObservation).where(
            ConsensusEstimateObservation.provider_mapping_id.in_(selected_ids),
            ConsensusEstimateObservation.snapshot_date <= as_of,
        )
        if selected_ids
        else None
    )
    if observation_statement is not None:
        if known_at is not None:
            observation_statement = observation_statement.where(
                ConsensusEstimateObservation.recorded_at <= known_at,
                (ConsensusEstimateObservation.observed_at.is_(None))
                | (ConsensusEstimateObservation.observed_at <= known_at),
            )
        observations = list(
            session.scalars(
                observation_statement.order_by(
                    ConsensusEstimateObservation.company_id,
                    ConsensusEstimateObservation.snapshot_date,
                    ConsensusEstimateObservation.observed_at,
                    ConsensusEstimateObservation.recorded_at,
                )
            )
        )
    else:
        observations = []
    points_by_company: dict[UUID, list[ConsensusObservationPoint]] = defaultdict(list)
    for observation in observations:
        points_by_company[observation.company_id].append(
            ConsensusObservationPoint(
                id=observation.id,
                provider_mapping_id=observation.provider_mapping_id,
                provider_id=observation.provider_id,
                metric=observation.metric,
                period_type=observation.period_type,
                forecast_period=observation.forecast_period,
                period_end=observation.period_end,
                value=observation.value,
                analyst_count=observation.analyst_count,
                currency=observation.currency,
                unit=observation.unit,
                snapshot_date=observation.snapshot_date,
                observed_at=observation.observed_at,
                recorded_at=observation.recorded_at,
                data_quality=observation.data_quality,
                quality_reason=observation.quality_reason,
            )
        )
    result: dict[UUID, s.CompanyEstimateMomentumRead] = {}
    for company_id in company_ids:
        selected, continuity = selected_by_company[company_id]
        result[company_id] = calculate_estimate_momentum(
            company_id=company_id,
            as_of=as_of,
            known_at=known_at,
            continuity_status=continuity,
            selected_provider_id=selected.provider_id if selected else None,
            selected_mapping_id=selected.id if selected else None,
            observations=points_by_company.get(company_id, []),
        )
    return result


def _metric_statement(metric: FundamentalMetric) -> FundamentalStatement:
    if metric in {
        FundamentalMetric.REVENUE,
        FundamentalMetric.GROSS_PROFIT,
        FundamentalMetric.OPERATING_INCOME,
        FundamentalMetric.NET_INCOME,
        FundamentalMetric.DILUTED_WEIGHTED_AVERAGE_SHARES,
    }:
        return FundamentalStatement.INCOME_STATEMENT
    if metric in {
        FundamentalMetric.CASH_AND_CASH_EQUIVALENTS,
        FundamentalMetric.CURRENT_DEBT,
        FundamentalMetric.NONCURRENT_DEBT,
    }:
        return FundamentalStatement.BALANCE_SHEET
    return FundamentalStatement.CASH_FLOW_STATEMENT


def listing_market_data_by_id(
    session: Session,
    listing_id: UUID,
    history_limit: int = 90,
    market_as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.ListingMarketData:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise services.DomainError("Listing not found", 404)
    return listing_market_data(session, listing, history_limit, market_as_of, known_at)


def listing_corporate_actions(
    session: Session,
    listing_id: UUID,
    *,
    as_of: date | None = None,
    known_at: datetime | None = None,
    limit: int = 100,
) -> list[s.CorporateActionRead]:
    if session.get(Listing, listing_id) is None:
        raise services.DomainError("Listing not found", 404)
    cutoff = known_at or now()
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    statement = (
        select(CorporateAction)
        .join(MarketDataBatch, CorporateAction.batch_id == MarketDataBatch.id)
        .where(
            CorporateAction.listing_id == listing_id,
            MarketDataBatch.recorded_at <= cutoff,
            or_(CorporateAction.observed_at.is_(None), CorporateAction.observed_at <= cutoff),
        )
        .order_by(CorporateAction.effective_date.desc(), CorporateAction.source_action_id)
        .limit(limit)
    )
    if as_of is not None:
        statement = statement.where(
            CorporateAction.effective_date <= datetime.combine(as_of, time.max, UTC)
        )
    return [s.CorporateActionRead.model_validate(item) for item in session.scalars(statement)]


def fx_observations(
    session: Session,
    base_currency: str | None = None,
    quote_currency: str | None = None,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
) -> list[s.FxObservationRead]:
    knowledge_cutoff = known_at or now()
    if knowledge_cutoff.tzinfo is None or knowledge_cutoff.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    statement = select(FxObservation).order_by(
        FxObservation.effective_at.desc(), FxObservation.recorded_at.desc()
    )
    statement = statement.where(FxObservation.recorded_at <= knowledge_cutoff)
    if as_of is not None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        statement = statement.where(FxObservation.effective_at <= as_of)
    if base_currency is not None:
        statement = statement.where(FxObservation.base_currency == base_currency)
    if quote_currency is not None:
        statement = statement.where(FxObservation.quote_currency == quote_currency)
    return [s.FxObservationRead.model_validate(item) for item in session.scalars(statement)]


def universe_market_summary(
    session: Session,
    lifecycle: Lifecycle | None = None,
    search: str | None = None,
    market_as_of: date | None = None,
    known_at: datetime | None = None,
) -> list[s.UniverseMarketSummary]:
    companies = universe(session, lifecycle, search)
    return [
        s.UniverseMarketSummary(
            company=company,
            market_data=company_market_data(session, company.id, 0, market_as_of, known_at),
        )
        for company in companies
    ]


def detail(session: Session, company_id: UUID) -> s.CompanyDetail:
    issuer = services.company(session, company_id)
    securities = session.scalars(
        select(Security).where(Security.company_id == company_id).order_by(Security.name)
    ).all()
    security_ids = [sec.id for sec in securities]
    listings = (
        session.scalars(
            select(Listing).where(Listing.security_id.in_(security_ids)).order_by(Listing.ticker)
        ).all()
        if securities
        else []
    )
    events = session.scalars(
        select(LifecycleEvent)
        .where(LifecycleEvent.company_id == company_id)
        .order_by(LifecycleEvent.sequence.desc())
    ).all()
    active = session.scalar(select(Portfolio).order_by(Portfolio.created_at).limit(1))
    view = overview(session, active.id) if active else None
    context = (
        next((c for c in view.companies if c.company.id == company_id), None) if view else None
    )
    return s.CompanyDetail(
        company=company_read(session, issuer),
        securities=[s.SecurityRead.model_validate(sec) for sec in securities],
        listings=[s.ListingRead.model_validate(li) for li in listings],
        lifecycle_history=[s.LifecycleEventRead.model_validate(e) for e in events],
        portfolio=view.portfolio if view else None,
        portfolio_context=context,
        holding_snapshot=view.snapshot if view else None,
        positions=context.positions if context else [],
        target_weight=context.target_weight if context else None,
        target_revision_id=view.target_revision.id if view and view.target_revision else None,
    )


def model_output_snapshot_read(snapshot: ModelOutputSnapshot) -> s.ModelOutputSnapshotRead:
    return s.ModelOutputSnapshotRead.model_validate(snapshot)


def _model_output_current_rows(
    session: Session, company_ids: list[UUID]
) -> tuple[dict[UUID, list[s.ModelOutputCurrentModelRead]], dict[UUID, int]]:
    if not company_ids:
        return {}, {}
    rows = session.scalars(
        select(ModelOutputSnapshot)
        .where(
            ModelOutputSnapshot.company_id.in_(company_ids),
            ModelOutputSnapshot.snapshot_kind == ModelOutputSnapshotKind.CURRENT_CONTRACT,
        )
        .order_by(
            ModelOutputSnapshot.company_id,
            ModelOutputSnapshot.model_key,
            ModelOutputSnapshot.recorded_at.desc(),
            ModelOutputSnapshot.id,
        )
    ).all()
    latest: dict[tuple[UUID, str], ModelOutputSnapshot] = {}
    for row in rows:
        latest.setdefault((row.company_id, row.model_key), row)
    models_by_company: dict[UUID, list[s.ModelOutputCurrentModelRead]] = {}
    for (company_id, model_key), row in latest.items():
        if row.contract_status == "PASS":
            status = "PUBLISHED" if row.output_quality == "COMPLETE" else "PARTIAL"
            if row.output_quality == "DATA_CHECK":
                status = "DATA_CHECK"
        elif row.contract_status == "NOT_MAPPED":
            status = "NOT_MAPPED"
        elif row.contract_status == "NO_CONTRACT":
            status = "NO_CONTRACT"
        else:
            status = "DATA_CHECK"
        models_by_company.setdefault(company_id, []).append(
            s.ModelOutputCurrentModelRead(
                model_key=model_key,
                status=status,
                snapshot=model_output_snapshot_read(row),
            )
        )
    history_counts = {
        company_id: count
        for company_id, count in session.execute(
            select(ModelOutputSnapshot.company_id, func.count(ModelOutputSnapshot.id))
            .where(ModelOutputSnapshot.company_id.in_(company_ids))
            .group_by(ModelOutputSnapshot.company_id)
        )
    }
    for models in models_by_company.values():
        models.sort(key=lambda item: item.model_key)
    return models_by_company, history_counts


def _company_model_outputs(
    company_id: UUID,
    models: list[s.ModelOutputCurrentModelRead],
    history_count: int,
) -> s.CompanyModelOutputsCurrentRead:
    statuses = {item.status for item in models}
    if "PUBLISHED" in statuses:
        status = "AVAILABLE"
    elif "PARTIAL" in statuses:
        status = "PARTIAL"
    elif "DATA_CHECK" in statuses:
        status = "DATA_CHECK"
    elif "NOT_MAPPED" in statuses:
        status = "NOT_MAPPED"
    elif "NO_CONTRACT" in statuses:
        status = "NO_CONTRACT"
    else:
        status = "NO_MODEL"
    return s.CompanyModelOutputsCurrentRead(
        company_id=company_id,
        status=status,
        history_count=history_count,
        models=models,
    )


def company_model_outputs_current(
    session: Session, company_id: UUID
) -> s.CompanyModelOutputsCurrentRead:
    services.company(session, company_id)
    models_by_company, history_counts = _model_output_current_rows(session, [company_id])
    return _company_model_outputs(
        company_id,
        models_by_company.get(company_id, []),
        history_counts.get(company_id, 0),
    )


def company_model_outputs_history(
    session: Session, company_id: UUID, model_key: str | None = None
) -> list[s.ModelOutputSnapshotRead]:
    services.company(session, company_id)
    statement = select(ModelOutputSnapshot).where(ModelOutputSnapshot.company_id == company_id)
    if model_key:
        statement = statement.where(ModelOutputSnapshot.model_key == model_key)
    statement = statement.order_by(
        case(
            (ModelOutputSnapshot.snapshot_kind == ModelOutputSnapshotKind.CURRENT_CONTRACT, 0),
            else_=1,
        ),
        ModelOutputSnapshot.effective_at.desc().nulls_last(),
        ModelOutputSnapshot.recorded_at.desc(),
        ModelOutputSnapshot.model_key,
    )
    return [model_output_snapshot_read(item) for item in session.scalars(statement)]


def company_expected_return_history(
    session: Session,
    company_id: UUID,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyExpectedReturnHistoryRead:
    """Compose imported outputs and immutable native revisions without persisting a new series."""
    services.company(session, company_id)
    query_now = now()
    as_of_date = as_of or query_now.date()
    effective_cutoff = datetime.combine(as_of_date, time.max, UTC)
    knowledge_cutoff = known_at or min(query_now, effective_cutoff)
    if knowledge_cutoff.tzinfo is None or knowledge_cutoff.utcoffset() is None:
        raise ValueError("known_at must include a timezone offset")
    knowledge_cutoff = knowledge_cutoff.astimezone(UTC)

    models = list(
        session.scalars(
            select(FinancialModel)
            .where(FinancialModel.company_id == company_id)
            .order_by(FinancialModel.model_name, FinancialModel.id)
        )
    )
    models_by_id = {model.id: model for model in models}
    source_models: dict[str, list[FinancialModel]] = defaultdict(list)
    for model in models:
        if model.source_model_key:
            source_models[model.source_model_key].append(model)

    native_revisions: list[FinancialModelRevision] = []
    if models:
        native_revisions = list(
            session.scalars(
                select(FinancialModelRevision)
                .where(
                    FinancialModelRevision.model_id.in_(models_by_id),
                    FinancialModelRevision.effective_at <= effective_cutoff,
                    FinancialModelRevision.effective_at <= knowledge_cutoff,
                    FinancialModelRevision.recorded_at <= knowledge_cutoff,
                )
                .order_by(
                    FinancialModelRevision.revision_number,
                )
            )
        )
    revision_ids = [revision.id for revision in native_revisions]
    native_outputs = (
        list(
            session.scalars(
                select(FinancialModelOutput).where(
                    FinancialModelOutput.revision_id.in_(revision_ids)
                )
            )
        )
        if revision_ids
        else []
    )
    output_by_revision = {output.revision_id: output for output in native_outputs}

    latest_revision_at_cutoff: dict[UUID, UUID] = {}
    for revision in native_revisions:
        latest_revision_at_cutoff[revision.model_id] = revision.id

    records: list[dict[str, Any]] = []
    for revision in native_revisions:
        model = models_by_id[revision.model_id]
        output = output_by_revision.get(revision.id)
        if output is None:
            continue
        records.append(
            {
                "point_id": f"native:{revision.id}",
                "source_kind": "NATIVE_MODEL_REVISION",
                "effective_at": revision.effective_at,
                "recorded_at": revision.recorded_at,
                "series_id": f"native:{model.id}",
                "model_key": model.source_model_key,
                "model_id": model.id,
                "revision_id": revision.id,
                "revision_number": revision.revision_number,
                "model_type": revision.model_type,
                "methodology_version": revision.methodology_version,
                "model_label": model.model_name,
                "model_currency": model.model_currency,
                "currency_status": "DOCUMENTED",
                "listing": session.get(Listing, model.valuation_listing_id),
                "is_current_at_cutoff": latest_revision_at_cutoff[model.id] == revision.id,
                "output_status": output.status,
                "output_quality": "COMPLETE" if output.status == "COMPLETE" else "PARTIAL",
                "contract_status": None,
                "return_semantics": "NATIVE_METHOD_OUTPUT",
                "actor": revision.actor,
                "source_actor": None,
                "revision_source": None,
                "revision_type": None,
                "output": output,
                "snapshot": None,
                "revision": revision,
                "source": revision.source,
                "source_revision_id": revision.source_revision_id,
                "rationale": revision.rationale,
                "evidence": None,
            }
        )

    legacy_snapshots = list(
        session.scalars(
            select(ModelOutputSnapshot)
            .where(
                ModelOutputSnapshot.company_id == company_id,
                ModelOutputSnapshot.recorded_at <= knowledge_cutoff,
                or_(
                    ModelOutputSnapshot.effective_at.is_(None),
                    and_(
                        ModelOutputSnapshot.effective_at <= effective_cutoff,
                        ModelOutputSnapshot.effective_at <= knowledge_cutoff,
                    ),
                ),
            )
            .order_by(
                ModelOutputSnapshot.effective_at.nullsfirst(),
                ModelOutputSnapshot.recorded_at,
                ModelOutputSnapshot.model_key,
            )
        )
    )
    for snapshot in legacy_snapshots:
        matches = source_models.get(snapshot.model_key, [])
        listing_ids = {model.valuation_listing_id for model in matches}
        listing = session.get(Listing, next(iter(listing_ids))) if len(listing_ids) == 1 else None
        source_kind = (
            "IMPORTED_CURRENT_CONTRACT"
            if snapshot.snapshot_kind == ModelOutputSnapshotKind.CURRENT_CONTRACT
            else "IMPORTED_LEGACY_REVISION"
        )
        records.append(
            {
                "point_id": f"imported:{snapshot.id}",
                "source_kind": source_kind,
                "effective_at": snapshot.effective_at,
                "recorded_at": snapshot.recorded_at,
                "series_id": f"legacy:{snapshot.model_key}",
                "model_key": snapshot.model_key,
                "model_id": matches[0].id if len(matches) == 1 else None,
                "revision_id": None,
                "revision_number": None,
                "model_type": None,
                "methodology_version": None,
                "model_label": snapshot.model_key,
                "model_currency": snapshot.model_currency,
                "currency_status": snapshot.currency_status,
                "listing": listing,
                "is_current_at_cutoff": False,
                "output_status": snapshot.model_status,
                "output_quality": snapshot.output_quality,
                "contract_status": snapshot.contract_status,
                "return_semantics": "LEGACY_NORMALIZED_FIELD",
                "actor": snapshot.actor,
                "source_actor": snapshot.source_actor,
                "revision_source": snapshot.revision_source,
                "revision_type": snapshot.revision_type,
                "output": snapshot,
                "snapshot": snapshot,
                "revision": None,
                "source": snapshot.source,
                "source_revision_id": snapshot.source_revision_id,
                "rationale": snapshot.rationale,
                "evidence": snapshot.evidence,
            }
        )

    listing_ids = {record["listing"].id for record in records if record["listing"] is not None}
    cutoff_quotes = (
        list(
            session.scalars(
                select(PriceObservation)
                .where(
                    PriceObservation.listing_id.in_(listing_ids),
                    PriceObservation.price_kind == "DAILY_CLOSE",
                    PriceObservation.market_date <= effective_cutoff,
                    PriceObservation.recorded_at <= knowledge_cutoff,
                    or_(
                        PriceObservation.observed_at.is_(None),
                        PriceObservation.observed_at <= knowledge_cutoff,
                    ),
                )
                .order_by(
                    PriceObservation.listing_id,
                    PriceObservation.market_date,
                    *_price_ordering(),
                )
            )
        )
        if listing_ids
        else []
    )
    quotes_by_listing: dict[UUID, list[PriceObservation]] = defaultdict(list)
    for quote in cutoff_quotes:
        quotes_by_listing[quote.listing_id].append(quote)

    native_quote_ids = {
        record["output"].price_observation_id
        for record in records
        if record["source_kind"] == "NATIVE_MODEL_REVISION"
        and record["output"].price_observation_id is not None
    }
    linked_native_quotes = (
        {
            quote.id: quote
            for quote in session.scalars(
                select(PriceObservation).where(PriceObservation.id.in_(native_quote_ids))
            )
        }
        if native_quote_ids
        else {}
    )

    mapping_rows = list(
        session.scalars(
            select(ConsensusEstimateProviderMapping)
            .where(
                ConsensusEstimateProviderMapping.company_id == company_id,
                ConsensusEstimateProviderMapping.effective_from <= effective_cutoff,
                ConsensusEstimateProviderMapping.recorded_at <= knowledge_cutoff,
            )
            .order_by(ConsensusEstimateProviderMapping.effective_from.desc())
        )
    )
    mapping_ids = [mapping.id for mapping in mapping_rows]
    estimate_rows = (
        list(
            session.scalars(
                select(ConsensusEstimateObservation)
                .where(
                    ConsensusEstimateObservation.company_id == company_id,
                    ConsensusEstimateObservation.provider_mapping_id.in_(mapping_ids),
                    ConsensusEstimateObservation.snapshot_date <= as_of_date,
                    ConsensusEstimateObservation.recorded_at <= knowledge_cutoff,
                    or_(
                        ConsensusEstimateObservation.observed_at.is_(None),
                        ConsensusEstimateObservation.observed_at <= knowledge_cutoff,
                    ),
                )
                .order_by(
                    ConsensusEstimateObservation.snapshot_date,
                    ConsensusEstimateObservation.observed_at,
                    ConsensusEstimateObservation.recorded_at,
                )
            )
        )
        if mapping_ids
        else []
    )

    for record in records:
        listing = record["listing"]
        output = record["output"]
        snapshot = record["snapshot"]
        revision = record["revision"]
        effective_at = record["effective_at"]
        model_currency = record["model_currency"]
        price_read: s.ExpectedReturnMarketPriceRead
        if revision is not None:
            price_output = output
            native_quote = linked_native_quotes.get(price_output.price_observation_id)
            if native_quote and (
                native_quote.recorded_at > revision.recorded_at
                or (
                    native_quote.observed_at is not None
                    and native_quote.observed_at > revision.recorded_at
                )
            ):
                native_quote = None
            price_status = {
                "FRESH": "AVAILABLE",
                "STALE": "STALE",
                "QUALITY_CHECK": "DATA_CHECK",
                "NO_DATA": "NO_DATA",
                "CURRENCY_MISMATCH": "CURRENCY_MISMATCH",
                "CURRENCY_UNKNOWN": "CURRENCY_UNKNOWN",
            }[price_output.price_status]
            price_reason = price_output.price_unavailable_reason
            if price_output.price_observation_id is not None and native_quote is None:
                price_status = "PRICE_NOT_CAPTURED"
                price_reason = (
                    "The linked quote was not yet recorded and observed by this revision."
                )
            elif native_quote is not None and native_quote.observed_at is None:
                price_status = "DATA_CHECK"
                price_reason = "The source quote has no observation timestamp."
            elif native_quote is not None and native_quote.currency != price_output.model_currency:
                price_status = "CURRENCY_MISMATCH"
                price_reason = "The linked quote currency differs from the model currency."
            price_read = s.ExpectedReturnMarketPriceRead(
                status=price_status,
                listing_id=listing.id if listing else None,
                ticker=listing.ticker if listing else None,
                venue=listing.venue if listing else None,
                listing_currency=listing.currency if listing else None,
                quote=native_quote.provider_close if native_quote else None,
                quote_currency=native_quote.currency if native_quote else None,
                model_reference_price=price_output.current_price,
                model_currency=price_output.model_currency,
                effective_at=price_output.price_effective_at,
                observed_at=native_quote.observed_at if native_quote else None,
                recorded_at=native_quote.recorded_at if native_quote else None,
                provider=native_quote.provider if native_quote else None,
                adjustment_basis=native_quote.adjustment_basis if native_quote else None,
                observation_id=price_output.price_observation_id,
                source_ref=native_quote.source_ref if native_quote else None,
                reason=price_reason,
            )
        elif effective_at is None:
            price_read = _expected_return_unavailable_price(
                "UNDATED",
                listing,
                model_currency,
                "The source snapshot has no effective timestamp.",
            )
        elif listing is None:
            price_read = _expected_return_unavailable_price(
                "LISTING_UNMAPPED",
                None,
                model_currency,
                "No unique valuation listing is linked to this imported model key.",
            )
        else:
            candidates = [
                quote
                for quote in quotes_by_listing.get(listing.id, [])
                if quote.market_date <= effective_at
                and quote.recorded_at <= effective_at
                and (quote.observed_at is None or quote.observed_at <= effective_at)
            ]
            historical_quote = max(
                candidates,
                key=lambda item: (
                    item.market_date,
                    item.data_quality in {"PASS", "PASS_VERIFIED_FALLBACK"},
                    item.provider == "YAHOO_FINANCE",
                    item.recorded_at,
                ),
                default=None,
            )
            if historical_quote is None:
                price_read = _expected_return_unavailable_price(
                    "NO_DATA",
                    listing,
                    model_currency,
                    "No exact-listing close was recorded by the source effective time.",
                )
            else:
                status = (
                    "DATA_CHECK"
                    if historical_quote.data_quality not in {"PASS", "PASS_VERIFIED_FALLBACK"}
                    or historical_quote.observed_at is None
                    else "CURRENCY_UNKNOWN"
                    if model_currency is None
                    else "CURRENCY_MISMATCH"
                    if historical_quote.currency != model_currency
                    else "STALE"
                    if (effective_at.date() - historical_quote.market_date.date()).days > FRESH_DAYS
                    else "AVAILABLE"
                )
                price_read = s.ExpectedReturnMarketPriceRead(
                    status=status,
                    listing_id=listing.id,
                    ticker=listing.ticker,
                    venue=listing.venue,
                    listing_currency=listing.currency,
                    quote=historical_quote.provider_close,
                    quote_currency=historical_quote.currency,
                    model_reference_price=None,
                    model_currency=model_currency,
                    effective_at=historical_quote.market_date,
                    observed_at=historical_quote.observed_at,
                    recorded_at=historical_quote.recorded_at,
                    provider=historical_quote.provider,
                    adjustment_basis=historical_quote.adjustment_basis,
                    observation_id=historical_quote.id,
                    source_ref=historical_quote.source_ref,
                    reason=(
                        "Listing and model currencies differ; no FX conversion is inferred."
                        if status == "CURRENCY_MISMATCH"
                        else "Model currency is unknown; no currency is inferred from the listing."
                        if status == "CURRENCY_UNKNOWN"
                        else "The source quote has no observation timestamp."
                        if status == "DATA_CHECK" and historical_quote.observed_at is None
                        else None
                        if status in {"AVAILABLE", "STALE"}
                        else historical_quote.data_quality
                    ),
                )

        estimate_context = _expected_return_estimate_context(
            effective_at, mapping_rows, estimate_rows
        )
        source = output
        record["market_price"] = price_read
        record["estimate_context"] = estimate_context
        record["bear_fv"] = source.bear_fv
        record["base_fv"] = source.base_fv
        record["bull_fv"] = source.bull_fv
        record["bear_probability"] = source.bear_probability
        record["base_probability"] = source.base_probability
        record["bull_probability"] = source.bull_probability
        record["weighted_fv"] = source.weighted_fv
        record["weighted_upside"] = source.weighted_upside
        record["expected_cash_flow_irr"] = source.expected_cash_flow_irr
        record["hurdle"] = source.hurdle
        record["expected_excess"] = source.expected_excess
        record["forward_fundamental_cagr"] = source.forward_fundamental_cagr

    records.sort(
        key=lambda item: (
            item["effective_at"] is None,
            item["effective_at"] or item["recorded_at"],
            item["recorded_at"],
            item["series_id"],
        )
    )
    history = [
        s.ExpectedReturnHistoryPointRead(
            point_id=item["point_id"],
            source_kind=item["source_kind"],
            event_status="DATED" if item["effective_at"] is not None else "EFFECTIVE_DATE_UNKNOWN",
            effective_at=item["effective_at"],
            recorded_at=item["recorded_at"],
            series_id=item["series_id"],
            model_key=item["model_key"],
            model_id=item["model_id"],
            revision_id=item["revision_id"],
            revision_number=item["revision_number"],
            model_type=item["model_type"],
            methodology_version=item["methodology_version"],
            model_label=item["model_label"],
            model_currency=item["model_currency"],
            currency_status=item["currency_status"],
            valuation_listing_id=item["listing"].id if item["listing"] else None,
            valuation_ticker=item["listing"].ticker if item["listing"] else None,
            valuation_venue=item["listing"].venue if item["listing"] else None,
            valuation_listing_currency=item["listing"].currency if item["listing"] else None,
            is_current_at_cutoff=item["is_current_at_cutoff"],
            output_status=item["output_status"],
            output_quality=item["output_quality"],
            contract_status=item["contract_status"],
            return_semantics=item["return_semantics"],
            actor=item["actor"],
            source_actor=item["source_actor"],
            revision_source=item["revision_source"],
            revision_type=item["revision_type"],
            bear_fv=item["bear_fv"],
            base_fv=item["base_fv"],
            bull_fv=item["bull_fv"],
            bear_probability=item["bear_probability"],
            base_probability=item["base_probability"],
            bull_probability=item["bull_probability"],
            weighted_fv=item["weighted_fv"],
            weighted_upside=item["weighted_upside"],
            expected_cash_flow_irr=item["expected_cash_flow_irr"],
            hurdle=item["hurdle"],
            expected_excess=item["expected_excess"],
            forward_fundamental_cagr=item["forward_fundamental_cagr"],
            market_price=item["market_price"],
            estimate_context=item["estimate_context"],
            source=item["source"],
            source_revision_id=item["source_revision_id"],
            rationale=item["rationale"],
            evidence=item["evidence"],
        )
        for item in records
    ]
    if not history:
        status = "NO_HISTORY"
    elif any(
        point.output_quality in {"PARTIAL", "DATA_CHECK", "UNAVAILABLE"}
        or point.event_status == "EFFECTIVE_DATE_UNKNOWN"
        for point in history
    ):
        status = "PARTIAL"
    else:
        status = "AVAILABLE"
    return s.CompanyExpectedReturnHistoryRead(
        company_id=company_id,
        as_of=as_of_date,
        known_at=knowledge_cutoff,
        status=status,
        history=history,
    )


def _expected_return_unavailable_price(
    status: str,
    listing: Listing | None,
    model_currency: str | None,
    reason: str,
) -> s.ExpectedReturnMarketPriceRead:
    return s.ExpectedReturnMarketPriceRead(
        status=status,
        listing_id=listing.id if listing else None,
        ticker=listing.ticker if listing else None,
        venue=listing.venue if listing else None,
        listing_currency=listing.currency if listing else None,
        quote=None,
        quote_currency=None,
        model_reference_price=None,
        model_currency=model_currency,
        effective_at=None,
        observed_at=None,
        recorded_at=None,
        provider=None,
        adjustment_basis=None,
        observation_id=None,
        source_ref=None,
        reason=reason,
    )


def _expected_return_estimate_context(
    effective_at: datetime | None,
    mappings: list[ConsensusEstimateProviderMapping],
    observations: list[ConsensusEstimateObservation],
) -> s.ExpectedReturnEstimateContextRead:
    if effective_at is None:
        return s.ExpectedReturnEstimateContextRead(status="UNDATED", provider_id=None, periods=[])
    cutoff = effective_at.astimezone(UTC)
    eligible_mappings = [
        mapping
        for mapping in mappings
        if mapping.effective_from <= cutoff and mapping.recorded_at <= cutoff
    ]
    latest_mappings: dict[tuple[str, str], ConsensusEstimateProviderMapping] = {}
    for mapping in sorted(eligible_mappings, key=lambda row: row.effective_from, reverse=True):
        latest_mappings.setdefault((mapping.role, mapping.provider_id), mapping)
    selected, continuity = select_consensus_source(list(latest_mappings.values()))
    if continuity == "NO_MAPPING":
        status = "NO_MAPPING"
    elif continuity == "AMBIGUOUS_FALLBACK":
        status = "AMBIGUOUS_SOURCE"
    elif selected is None:
        status = "NO_MAPPING"
    else:
        status = "AVAILABLE"
    if selected is None:
        return s.ExpectedReturnEstimateContextRead(status=status, provider_id=None, periods=[])
    facts = [
        observation
        for observation in observations
        if observation.provider_mapping_id == selected.id
        and observation.snapshot_date <= cutoff.date()
        and observation.recorded_at <= cutoff
        and (
            observation.observed_at <= cutoff
            if observation.observed_at is not None
            else observation.snapshot_date < cutoff.date()
        )
        and (observation.period_end is None or observation.period_end > cutoff.date())
    ]
    latest_by_period: dict[tuple[Any, ...], ConsensusEstimateObservation] = {}
    for observation in sorted(
        facts,
        key=lambda row: (
            row.metric,
            row.period_type,
            row.forecast_period,
            row.period_end or date.max,
            row.currency or "",
            row.unit,
            row.snapshot_date,
            row.observed_at or datetime.min.replace(tzinfo=UTC),
            row.recorded_at,
        ),
        reverse=True,
    ):
        key = (
            observation.metric,
            observation.period_type,
            observation.forecast_period,
            observation.period_end,
            observation.currency,
            observation.unit,
        )
        latest_by_period.setdefault(key, observation)
    selected_rows = sorted(
        latest_by_period.values(),
        key=lambda row: (row.period_end or date.max, row.metric, row.period_type),
    )
    if not selected_rows:
        status = "NO_OBSERVATIONS"
    return s.ExpectedReturnEstimateContextRead(
        status=status,
        provider_id=selected.provider_id,
        periods=[
            s.ExpectedReturnEstimateRead(
                observation_id=row.id,
                metric=row.metric,
                period_type=row.period_type,
                forecast_period=row.forecast_period,
                period_end=row.period_end,
                value=row.value,
                currency=row.currency,
                unit=row.unit,
                analyst_count=row.analyst_count,
                snapshot_date=row.snapshot_date,
                observed_at=row.observed_at,
                recorded_at=row.recorded_at,
                provider_id=row.provider_id,
                source_ref=row.source_ref,
                data_quality=row.data_quality,
                quality_reason=row.quality_reason,
            )
            for row in selected_rows
        ],
    )


def universe_model_output_summary(
    session: Session, lifecycle: Lifecycle | None = None, search: str | None = None
) -> list[s.UniverseModelOutputSummary]:
    companies = universe(session, lifecycle, search)
    ids = [company.id for company in companies]
    models_by_company, history_counts = _model_output_current_rows(session, ids)
    return [
        s.UniverseModelOutputSummary(
            company=company,
            outputs=_company_model_outputs(
                company.id,
                models_by_company.get(company.id, []),
                history_counts.get(company.id, 0),
            ),
        )
        for company in companies
    ]


def _financial_model_output_read(
    output: FinancialModelOutput,
) -> s.FinancialModelOutputsRead:
    return s.FinancialModelOutputsRead.model_validate(output)


def _financial_model_revision_summary(
    session: Session, revision: FinancialModelRevision
) -> s.FinancialModelRevisionSummary:
    output = session.scalar(
        select(FinancialModelOutput).where(FinancialModelOutput.revision_id == revision.id)
    )
    if output is None:
        raise services.DomainError("Accepted model revision has no calculation output", 409)
    return s.FinancialModelRevisionSummary(
        id=revision.id,
        model_id=revision.model_id,
        revision_number=revision.revision_number,
        base_revision_id=revision.base_revision_id,
        methodology_version=revision.methodology_version,
        source_revision_id=revision.source_revision_id,
        actor=revision.actor,
        source=revision.source,
        rationale=revision.rationale,
        effective_at=revision.effective_at,
        recorded_at=revision.recorded_at,
        outputs=_financial_model_output_read(output),
    )


def _financial_model_revision_read(
    session: Session, revision: FinancialModelRevision
) -> s.FinancialModelRevisionRead:
    base = session.scalar(
        select(DcfModelAssumptions).where(DcfModelAssumptions.revision_id == revision.id)
    )
    if base is None:
        raise services.DomainError("Accepted model revision has no stored assumptions", 409)
    scenarios = session.scalars(
        select(DcfScenarioAssumptions)
        .where(DcfScenarioAssumptions.revision_id == revision.id)
        .order_by(DcfScenarioAssumptions.scenario)
    ).all()
    scenario_names = {"BEAR": 0, "BASE": 1, "BULL": 2}
    scenarios = sorted(scenarios, key=lambda item: scenario_names[item.scenario])
    scenario_reads: list[s.DcfScenarioRead] = []
    projection_reads: list[s.DcfProjectionRead] = []
    for scenario in scenarios:
        year_inputs = session.scalars(
            select(DcfYearAssumption)
            .where(DcfYearAssumption.scenario_id == scenario.id)
            .order_by(DcfYearAssumption.forecast_year)
        ).all()
        projection_rows = session.scalars(
            select(DcfProjection)
            .where(DcfProjection.scenario_id == scenario.id)
            .order_by(DcfProjection.forecast_year)
        ).all()
        scenario_reads.append(
            s.DcfScenarioRead(
                id=scenario.id,
                revision_id=scenario.revision_id,
                scenario=scenario.scenario,
                probability=scenario.probability,
                terminal_growth=scenario.terminal_growth,
                year10_ufcf_growth=scenario.year10_ufcf_growth,
                rationale=scenario.rationale,
                years=[s.DcfYearAssumptionRead.model_validate(year) for year in year_inputs],
            )
        )
        projection_reads.extend(
            s.DcfProjectionRead.model_validate(item) for item in projection_rows
        )
    return s.FinancialModelRevisionRead(
        **_financial_model_revision_summary(session, revision).model_dump(),
        base=s.DcfOperatingBaseRead.model_validate(base),
        scenarios=scenario_reads,
        projections=projection_reads,
    )


def _financial_model_read(session: Session, model: FinancialModel) -> s.FinancialModelRead:
    if model.current_revision_id is None:
        raise services.DomainError("Financial model has no accepted revision", 409)
    listing = session.get(Listing, model.valuation_listing_id)
    current = session.get(FinancialModelRevision, model.current_revision_id)
    if listing is None or current is None or current.model_id != model.id:
        raise services.DomainError("Financial model current state is inconsistent", 409)
    history = session.scalars(
        select(FinancialModelRevision)
        .where(FinancialModelRevision.model_id == model.id)
        .order_by(FinancialModelRevision.revision_number.desc())
    ).all()
    return s.FinancialModelRead(
        id=model.id,
        company_id=model.company_id,
        model_type=model.model_type,
        model_name=model.model_name,
        valuation_listing=s.ListingRead.model_validate(listing),
        model_currency=model.model_currency,
        source_model_key=model.source_model_key,
        created_at=model.created_at,
        current_revision_id=current.id,
        current_revision=_financial_model_revision_read(session, current),
        history=[_financial_model_revision_summary(session, revision) for revision in history],
    )


def company_financial_models(session: Session, company_id: UUID) -> list[s.FinancialModelRead]:
    services.company(session, company_id)
    models = session.scalars(
        select(FinancialModel)
        .where(
            FinancialModel.company_id == company_id,
            FinancialModel.model_type == FinancialModelType.UFCF_DCF_10Y_FADE,
        )
        .order_by(FinancialModel.model_name, FinancialModel.id)
    ).all()
    return [_financial_model_read(session, model) for model in models]


def _extended_financial_model_revision_read(
    session: Session, revision: FinancialModelRevision
) -> s.OwnerCashFlowRevisionRead | s.ResidualIncomeRevisionRead:
    summary = _financial_model_revision_summary(session, revision).model_dump()
    if revision.model_type == FinancialModelType.OWNER_CASH_FLOW_10Y:
        owner_base = session.scalar(
            select(OwnerCashFlowAssumptions).where(
                OwnerCashFlowAssumptions.revision_id == revision.id
            )
        )
        if owner_base is None:
            raise services.DomainError("Accepted owner cash-flow revision has no inputs", 409)
        owner_scenario_rows = list(
            session.scalars(
                select(OwnerCashFlowScenarioAssumptions)
                .where(OwnerCashFlowScenarioAssumptions.revision_id == revision.id)
                .order_by(OwnerCashFlowScenarioAssumptions.scenario)
            )
        )
        scenario_order = {"BEAR": 0, "BASE": 1, "BULL": 2}
        owner_scenario_rows.sort(key=lambda item: scenario_order[item.scenario])
        owner_scenarios: list[s.OwnerCashFlowScenarioInput] = []
        for scenario in owner_scenario_rows:
            years = session.scalars(
                select(OwnerCashFlowYearAssumption)
                .where(OwnerCashFlowYearAssumption.scenario_id == scenario.id)
                .order_by(OwnerCashFlowYearAssumption.forecast_year)
            ).all()
            owner_scenarios.append(
                s.OwnerCashFlowScenarioInput(
                    scenario=scenario.scenario,
                    probability=scenario.probability,
                    required_return=scenario.required_return,
                    terminal_growth=scenario.terminal_growth,
                    rationale=scenario.rationale,
                    years=[
                        s.OwnerCashFlowYearInput(
                            forecast_year=year.forecast_year,
                            revenue_growth=year.revenue_growth,
                            owner_cash_flow_margin=year.owner_cash_flow_margin,
                        )
                        for year in years
                    ],
                )
            )
        owner_projections = session.execute(
            select(OwnerCashFlowProjection, OwnerCashFlowScenarioAssumptions.scenario)
            .join(
                OwnerCashFlowScenarioAssumptions,
                OwnerCashFlowScenarioAssumptions.id == OwnerCashFlowProjection.scenario_id,
            )
            .where(OwnerCashFlowProjection.revision_id == revision.id)
            .order_by(
                OwnerCashFlowScenarioAssumptions.scenario, OwnerCashFlowProjection.forecast_year
            )
        ).all()
        return s.OwnerCashFlowRevisionRead(
            **summary,
            base=s.OwnerCashFlowBase(
                base_revenue=owner_base.base_revenue,
                net_cash=owner_base.net_cash,
                diluted_shares=owner_base.diluted_shares,
            ),
            scenarios=owner_scenarios,
            projections=[
                s.OwnerCashFlowProjectionRead(
                    scenario=scenario,
                    forecast_year=row.forecast_year,
                    revenue=row.revenue,
                    owner_cash_flow=row.owner_cash_flow,
                    owner_cash_flow_per_share=row.owner_cash_flow_per_share,
                    present_value_per_share=row.present_value_per_share,
                    terminal_value_per_share=row.terminal_value_per_share,
                )
                for row, scenario in owner_projections
            ],
        )

    residual_base = session.scalar(
        select(ResidualIncomeAssumptions).where(
            ResidualIncomeAssumptions.revision_id == revision.id
        )
    )
    if residual_base is None:
        raise services.DomainError("Accepted residual-income revision has no inputs", 409)
    residual_scenario_rows = list(
        session.scalars(
            select(ResidualIncomeScenarioAssumptions)
            .where(ResidualIncomeScenarioAssumptions.revision_id == revision.id)
            .order_by(ResidualIncomeScenarioAssumptions.scenario)
        )
    )
    scenario_order = {"BEAR": 0, "BASE": 1, "BULL": 2}
    residual_scenario_rows.sort(key=lambda item: scenario_order[item.scenario])
    residual_projections = session.execute(
        select(ResidualIncomeProjection, ResidualIncomeScenarioAssumptions.scenario)
        .join(
            ResidualIncomeScenarioAssumptions,
            ResidualIncomeScenarioAssumptions.id == ResidualIncomeProjection.scenario_id,
        )
        .where(ResidualIncomeProjection.revision_id == revision.id)
        .order_by(
            ResidualIncomeScenarioAssumptions.scenario, ResidualIncomeProjection.forecast_year
        )
    ).all()
    return s.ResidualIncomeRevisionRead(
        **summary,
        base=s.ResidualIncomeBase(
            current_book_value_per_share=residual_base.current_book_value_per_share,
            payout_ratio=residual_base.payout_ratio,
        ),
        scenarios=[
            s.ResidualIncomeScenarioInput.model_validate(row) for row in residual_scenario_rows
        ],
        projections=[
            s.ResidualIncomeProjectionRead(
                scenario=scenario,
                forecast_year=row.forecast_year,
                beginning_book_value_per_share=row.beginning_book_value_per_share,
                return_on_equity=row.return_on_equity,
                net_income_per_share=row.net_income_per_share,
                dividend_per_share=row.dividend_per_share,
                ending_book_value_per_share=row.ending_book_value_per_share,
                residual_income_per_share=row.residual_income_per_share,
                present_value_residual_income=row.present_value_residual_income,
                terminal_value_per_share=row.terminal_value_per_share,
            )
            for row, scenario in residual_projections
        ],
    )


def _extended_financial_model_read(
    session: Session, model: FinancialModel
) -> s.ExtendedFinancialModelRead:
    if model.model_type not in {
        FinancialModelType.OWNER_CASH_FLOW_10Y,
        FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
    }:
        raise services.DomainError("Extended financial model not found", 404)
    if model.current_revision_id is None:
        raise services.DomainError("Financial model has no accepted revision", 409)
    listing = session.get(Listing, model.valuation_listing_id)
    current = session.get(FinancialModelRevision, model.current_revision_id)
    if listing is None or current is None or current.model_id != model.id:
        raise services.DomainError("Financial model current state is inconsistent", 409)
    history = session.scalars(
        select(FinancialModelRevision)
        .where(FinancialModelRevision.model_id == model.id)
        .order_by(FinancialModelRevision.revision_number.desc())
    ).all()
    return s.ExtendedFinancialModelRead(
        id=model.id,
        company_id=model.company_id,
        model_type=model.model_type,
        model_name=model.model_name,
        valuation_listing=s.ListingRead.model_validate(listing),
        model_currency=model.model_currency,
        source_model_key=model.source_model_key,
        created_at=model.created_at,
        current_revision_id=current.id,
        current_revision=_extended_financial_model_revision_read(session, current),
        history=[_financial_model_revision_summary(session, item) for item in history],
    )


def company_extended_financial_models(
    session: Session, company_id: UUID
) -> list[s.ExtendedFinancialModelRead]:
    services.company(session, company_id)
    models = session.scalars(
        select(FinancialModel)
        .where(
            FinancialModel.company_id == company_id,
            FinancialModel.model_type.in_(
                [
                    FinancialModelType.OWNER_CASH_FLOW_10Y,
                    FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
                ]
            ),
        )
        .order_by(FinancialModel.model_name, FinancialModel.id)
    ).all()
    return [_extended_financial_model_read(session, model) for model in models]


def extended_financial_model(session: Session, model_id: UUID) -> s.ExtendedFinancialModelRead:
    model = session.get(FinancialModel, model_id)
    if model is None:
        raise services.DomainError("Financial model not found", 404)
    return _extended_financial_model_read(session, model)


def extended_financial_model_revision(
    session: Session, model_id: UUID, revision_id: UUID
) -> s.OwnerCashFlowRevisionRead | s.ResidualIncomeRevisionRead:
    revision = session.get(FinancialModelRevision, revision_id)
    if revision is None or revision.model_id != model_id:
        raise services.DomainError("Financial model revision not found", 404)
    return _extended_financial_model_revision_read(session, revision)


def financial_model(session: Session, model_id: UUID) -> s.FinancialModelRead:
    model = session.get(FinancialModel, model_id)
    if model is None:
        raise services.DomainError("Financial model not found", 404)
    return _financial_model_read(session, model)


def financial_model_revision_history(
    session: Session, model_id: UUID
) -> list[s.FinancialModelRevisionSummary]:
    if session.get(FinancialModel, model_id) is None:
        raise services.DomainError("Financial model not found", 404)
    revisions = session.scalars(
        select(FinancialModelRevision)
        .where(FinancialModelRevision.model_id == model_id)
        .order_by(FinancialModelRevision.revision_number.desc())
    ).all()
    return [_financial_model_revision_summary(session, revision) for revision in revisions]


def financial_model_revision(
    session: Session, model_id: UUID, revision_id: UUID
) -> s.FinancialModelRevisionRead:
    revision = session.get(FinancialModelRevision, revision_id)
    if revision is None or revision.model_id != model_id:
        raise services.DomainError("Financial model revision not found", 404)
    return _financial_model_revision_read(session, revision)


def _score_definition_rows(
    session: Session, *, current_only: bool = False
) -> list[ScoreDefinition]:
    statement = select(ScoreDefinition).order_by(
        ScoreDefinition.dimension, ScoreDefinition.version.desc()
    )
    if current_only:
        statement = statement.where(
            ScoreDefinition.status == ScoreDefinitionStatus.ACTIVE,
            ScoreDefinition.effective_from <= now(),
        )
    return list(session.scalars(statement))


def score_definitions(
    session: Session, dimension: ScoreDimension | None = None
) -> list[s.ScoreDefinitionRead]:
    statement = select(ScoreDefinition).order_by(
        ScoreDefinition.dimension, ScoreDefinition.version.desc()
    )
    if dimension is not None:
        statement = statement.where(ScoreDefinition.dimension == dimension)
    return [s.ScoreDefinitionRead.model_validate(item) for item in session.scalars(statement)]


def _latest_scores(
    session: Session, companies: list[Company], definitions: list[ScoreDefinition]
) -> dict[tuple[UUID, UUID], s.ScoreAssessmentRead]:
    if not companies or not definitions:
        return {}
    ranked = (
        select(
            ScoreAssessment.id.label("assessment_id"),
            func.row_number()
            .over(
                partition_by=(ScoreAssessment.company_id, ScoreAssessment.score_definition_id),
                order_by=(
                    ScoreAssessment.effective_at.desc(),
                    ScoreAssessment.recorded_at.desc(),
                    ScoreAssessment.id.desc(),
                ),
            )
            .label("position"),
        )
        .where(
            ScoreAssessment.company_id.in_([company.id for company in companies]),
            ScoreAssessment.score_definition_id.in_([definition.id for definition in definitions]),
            ScoreAssessment.effective_at <= now(),
        )
        .subquery()
    )
    assessments = session.scalars(
        select(ScoreAssessment)
        .join(ranked, ranked.c.assessment_id == ScoreAssessment.id)
        .where(ranked.c.position == 1)
    ).all()
    return {
        (item.company_id, item.score_definition_id): s.ScoreAssessmentRead.model_validate(item)
        for item in assessments
    }


def current_scores(session: Session, company_id: UUID) -> list[s.ScoreCurrentRead]:
    issuer = services.company(session, company_id)
    definitions = _score_definition_rows(session, current_only=True)
    latest = _latest_scores(session, [issuer], definitions)
    return [
        s.ScoreCurrentRead(
            definition=s.ScoreDefinitionRead.model_validate(definition),
            assessment=latest.get((company_id, definition.id)),
        )
        for definition in definitions
    ]


def score_history(session: Session, company_id: UUID) -> list[s.ScoreHistoryEntry]:
    services.company(session, company_id)
    rows = session.execute(
        select(ScoreAssessment, ScoreDefinition)
        .join(ScoreDefinition, ScoreDefinition.id == ScoreAssessment.score_definition_id)
        .where(ScoreAssessment.company_id == company_id)
        .order_by(
            ScoreDefinition.dimension,
            ScoreAssessment.effective_at.desc(),
            ScoreAssessment.recorded_at.desc(),
        )
    ).all()
    return [
        s.ScoreHistoryEntry(
            definition=s.ScoreDefinitionRead.model_validate(definition),
            assessment=s.ScoreAssessmentRead.model_validate(assessment),
        )
        for assessment, definition in rows
    ]


def score_history_entry(session: Session, assessment: ScoreAssessment) -> s.ScoreHistoryEntry:
    definition = session.get(ScoreDefinition, assessment.score_definition_id)
    if definition is None:
        raise RuntimeError("Score assessment definition reference is unavailable")
    return s.ScoreHistoryEntry(
        definition=s.ScoreDefinitionRead.model_validate(definition),
        assessment=s.ScoreAssessmentRead.model_validate(assessment),
    )


def universe_score_summary(
    session: Session, lifecycle: Lifecycle | None = None, search: str | None = None
) -> list[s.UniverseScoreSummary]:
    companies = universe(session, lifecycle, search)
    if not companies:
        return []
    company_ids = [company.id for company in companies]
    company_rows = list(session.scalars(select(Company).where(Company.id.in_(company_ids))))
    definitions = _score_definition_rows(session, current_only=True)
    latest = _latest_scores(session, company_rows, definitions)
    return [
        s.UniverseScoreSummary(
            company=company,
            scores=[
                s.ScoreCurrentRead(
                    definition=s.ScoreDefinitionRead.model_validate(definition),
                    assessment=latest.get((company.id, definition.id)),
                )
                for definition in definitions
            ],
        )
        for company in companies
    ]


def ranking_definitions(
    session: Session, ranking_type: RankingType | None = None
) -> list[s.RankingDefinitionRead]:
    statement = select(RankingDefinition).order_by(
        RankingDefinition.ranking_type, RankingDefinition.version.desc()
    )
    if ranking_type is not None:
        statement = statement.where(RankingDefinition.ranking_type == ranking_type)
    return [s.RankingDefinitionRead.model_validate(item) for item in session.scalars(statement)]


def _ranking_run_counts(session: Session, run_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
    if not run_ids:
        return {}
    return {
        run_id: (int(company_count), int(ranked_count))
        for run_id, company_count, ranked_count in session.execute(
            select(
                RankingEntry.run_id,
                func.count(RankingEntry.id),
                func.count(RankingEntry.position),
            )
            .where(RankingEntry.run_id.in_(run_ids))
            .group_by(RankingEntry.run_id)
        )
    }


def _ranking_run_read(
    run: RankingRun,
    definition: RankingDefinition,
    counts: tuple[int, int] = (0, 0),
) -> s.RankingRunRead:
    return s.RankingRunRead(
        id=run.id,
        definition=s.RankingDefinitionRead.model_validate(definition),
        as_of=run.as_of,
        recorded_at=run.recorded_at,
        status=ExecutionPaceRunStatus(run.status),
        actor=Actor(run.actor),
        reason=run.reason,
        source=run.source,
        company_count=counts[0],
        ranked_count=counts[1],
    )


def _current_ranking_views(
    session: Session,
    companies: list[Company],
    definitions: list[RankingDefinition],
) -> dict[UUID, list[s.RankingCurrentRead]]:
    result: dict[UUID, list[s.RankingCurrentRead]] = {company.id: [] for company in companies}
    if not definitions:
        return result
    ranked = (
        select(
            RankingRun.id.label("run_id"),
            RankingRun.definition_id.label("definition_id"),
            func.row_number()
            .over(
                partition_by=RankingRun.definition_id,
                order_by=(
                    RankingRun.as_of.desc(),
                    RankingRun.recorded_at.desc(),
                    RankingRun.id.desc(),
                ),
            )
            .label("position"),
        )
        .where(
            RankingRun.definition_id.in_([definition.id for definition in definitions]),
            RankingRun.as_of <= now(),
        )
        .subquery()
    )
    latest_rows = session.execute(
        select(RankingRun, RankingDefinition)
        .join(ranked, ranked.c.run_id == RankingRun.id)
        .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
        .where(ranked.c.position == 1)
    ).all()
    latest = {definition.id: (run, definition) for run, definition in latest_rows}
    runs = [run for run, _ in latest.values()]
    counts = _ranking_run_counts(session, [run.id for run in runs])
    company_ids = [company.id for company in companies]
    entries = (
        session.scalars(
            select(RankingEntry).where(
                RankingEntry.run_id.in_([run.id for run in runs]),
                RankingEntry.company_id.in_(company_ids),
            )
        ).all()
        if runs and company_ids
        else []
    )
    by_company_run = {(entry.company_id, entry.run_id): entry for entry in entries}
    for company in companies:
        result[company.id] = [
            s.RankingCurrentRead(
                definition=s.RankingDefinitionRead.model_validate(definition),
                run=_ranking_run_read(run, definition, counts.get(run.id, (0, 0))) if run else None,
                entry=(
                    s.RankingEntryRead.model_validate(by_company_run[(company.id, run.id)])
                    if run and (company.id, run.id) in by_company_run
                    else None
                ),
            )
            for definition in definitions
            for run, _ in [latest.get(definition.id, (None, definition))]
        ]
    return result


def universe_ranking_summary(
    session: Session, lifecycle: Lifecycle | None = None, search: str | None = None
) -> list[s.UniverseRankingSummary]:
    companies = universe(session, lifecycle, search)
    if not companies:
        return []
    issuer_rows = list(
        session.scalars(select(Company).where(Company.id.in_([c.id for c in companies])))
    )
    definitions = list(
        session.scalars(
            select(RankingDefinition)
            .where(
                RankingDefinition.status == RankingDefinitionStatus.ACTIVE,
                RankingDefinition.effective_from <= now(),
            )
            .order_by(RankingDefinition.ranking_type)
        )
    )
    current = _current_ranking_views(session, issuer_rows, definitions)
    return [
        s.UniverseRankingSummary(company=company, rankings=current[company.id])
        for company in companies
    ]


def _execution_pace_run_read(session: Session, run: ExecutionPaceRun) -> s.ExecutionPaceRunRead:
    counts = dict(
        session.execute(
            select(ExecutionPaceDecision.decision_status, func.count(ExecutionPaceDecision.id))
            .where(ExecutionPaceDecision.run_id == run.id)
            .group_by(ExecutionPaceDecision.decision_status)
        ).all()
    )
    available = counts.get("AVAILABLE", 0)
    review = counts.get("REVIEW", 0)
    unavailable = counts.get("UNAVAILABLE", 0)
    not_applicable = counts.get("NOT_APPLICABLE", 0)
    return s.ExecutionPaceRunRead(
        id=run.id,
        portfolio_id=run.portfolio_id,
        as_of=run.as_of,
        recorded_at=run.recorded_at,
        methodology_version=run.methodology_version,
        status=run.status,
        actor=run.actor,
        reason=run.reason,
        source=run.source,
        company_count=sum(counts.values()),
        available_count=available,
        review_count=review,
        unavailable_count=unavailable,
        not_applicable_count=not_applicable,
    )


def execution_pace_run_read(session: Session, run: ExecutionPaceRun) -> s.ExecutionPaceRunRead:
    return _execution_pace_run_read(session, run)


def execution_pace_runs(session: Session, limit: int = 100) -> list[s.ExecutionPaceRunRead]:
    rows = session.scalars(
        select(ExecutionPaceRun)
        .order_by(ExecutionPaceRun.as_of.desc(), ExecutionPaceRun.recorded_at.desc())
        .limit(limit)
    ).all()
    return [_execution_pace_run_read(session, row) for row in rows]


def execution_pace_run_detail(session: Session, run_id: UUID) -> s.ExecutionPaceRunDetailRead:
    run = session.get(ExecutionPaceRun, run_id)
    if run is None:
        raise services.DomainError("Execution Pace run not found", 404)
    rows = session.execute(
        select(ExecutionPaceDecision, Company)
        .join(Company, Company.id == ExecutionPaceDecision.company_id)
        .where(ExecutionPaceDecision.run_id == run_id)
        .order_by(Company.name, Company.id)
    ).all()
    return s.ExecutionPaceRunDetailRead(
        run=_execution_pace_run_read(session, run),
        decisions=[
            s.ExecutionPaceRunDecisionRead(
                company=company_read(session, company),
                decision=s.ExecutionPaceDecisionRead.model_validate(decision),
            )
            for decision, company in rows
        ],
    )


def company_execution_pace(session: Session, company_id: UUID) -> s.CompanyExecutionPaceRead:
    services.company(session, company_id)
    rows = session.execute(
        select(ExecutionPaceRun, ExecutionPaceDecision)
        .join(ExecutionPaceDecision, ExecutionPaceDecision.run_id == ExecutionPaceRun.id)
        .where(ExecutionPaceDecision.company_id == company_id)
        .order_by(ExecutionPaceRun.as_of.desc(), ExecutionPaceRun.recorded_at.desc())
    ).all()
    history = [
        s.ExecutionPaceHistoryEntry(
            run=_execution_pace_run_read(session, run),
            decision=s.ExecutionPaceDecisionRead.model_validate(decision),
        )
        for run, decision in rows
    ]
    return s.CompanyExecutionPaceRead(
        company_id=company_id,
        current=history[0] if history else None,
        history=history,
    )


def universe_execution_pace_summary(
    session: Session, lifecycle: Lifecycle | None = None, search: str | None = None
) -> list[s.UniverseExecutionPaceSummary]:
    companies = universe(session, lifecycle, search)
    run = session.scalar(
        select(ExecutionPaceRun)
        .order_by(ExecutionPaceRun.as_of.desc(), ExecutionPaceRun.recorded_at.desc())
        .limit(1)
    )
    if run is None or not companies:
        return [
            s.UniverseExecutionPaceSummary(company=company, decision=None) for company in companies
        ]
    entries = {
        entry.company_id: entry
        for entry in session.scalars(
            select(ExecutionPaceDecision).where(
                ExecutionPaceDecision.run_id == run.id,
                ExecutionPaceDecision.company_id.in_([company.id for company in companies]),
            )
        )
    }
    run_read = _execution_pace_run_read(session, run)
    return [
        s.UniverseExecutionPaceSummary(
            company=company,
            decision=(
                s.ExecutionPaceHistoryEntry(
                    run=run_read,
                    decision=s.ExecutionPaceDecisionRead.model_validate(entries[company.id]),
                )
                if company.id in entries
                else None
            ),
        )
        for company in companies
    ]


def _ranking_history_rows(
    session: Session,
    company_id: UUID | None = None,
    ranking_type: RankingType | None = None,
) -> list[tuple[RankingRun, RankingDefinition, RankingEntry]]:
    statement = (
        select(RankingRun, RankingDefinition, RankingEntry)
        .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
        .join(RankingEntry, RankingEntry.run_id == RankingRun.id)
        .order_by(RankingRun.as_of.desc(), RankingRun.recorded_at.desc())
    )
    if company_id is not None:
        statement = statement.where(RankingEntry.company_id == company_id)
    if ranking_type is not None:
        statement = statement.where(RankingDefinition.ranking_type == ranking_type)
    return list(session.execute(statement).all())


def company_rankings(
    session: Session, company_id: UUID, ranking_type: RankingType | None = None
) -> s.CompanyRankingsRead:
    issuer = services.company(session, company_id)
    definitions_query = select(RankingDefinition).where(
        RankingDefinition.status == RankingDefinitionStatus.ACTIVE,
        RankingDefinition.effective_from <= now(),
    )
    if ranking_type is not None:
        definitions_query = definitions_query.where(RankingDefinition.ranking_type == ranking_type)
    definitions = list(session.scalars(definitions_query.order_by(RankingDefinition.ranking_type)))
    current = _current_ranking_views(session, [issuer], definitions)[issuer.id]
    rows = _ranking_history_rows(session, company_id, ranking_type)
    counts = _ranking_run_counts(session, list({run.id for run, _, _ in rows}))
    history = [
        s.RankingHistoryEntry(
            run=_ranking_run_read(run, definition, counts.get(run.id, (0, 0))),
            entry=s.RankingEntryRead.model_validate(entry),
        )
        for run, definition, entry in rows
    ]
    return s.CompanyRankingsRead(current=current, history=history)


def ranking_runs(
    session: Session, ranking_type: RankingType | None = None
) -> list[s.RankingRunRead]:
    statement = (
        select(RankingRun, RankingDefinition)
        .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
        .order_by(RankingRun.as_of.desc(), RankingRun.recorded_at.desc())
        .limit(100)
    )
    if ranking_type is not None:
        statement = statement.where(RankingDefinition.ranking_type == ranking_type)
    rows = session.execute(statement).all()
    counts = _ranking_run_counts(session, [run.id for run, _ in rows])
    return [
        _ranking_run_read(run, definition, counts.get(run.id, (0, 0))) for run, definition in rows
    ]


def ranking_run_read(session: Session, run: RankingRun) -> s.RankingRunRead:
    definition = session.get(RankingDefinition, run.definition_id)
    if definition is None:
        raise RuntimeError("Ranking run definition reference is unavailable")
    counts = _ranking_run_counts(session, [run.id])
    return _ranking_run_read(run, definition, counts.get(run.id, (0, 0)))


def ranking_run_detail(session: Session, run_id: UUID) -> s.RankingRunDetailRead:
    row = session.execute(
        select(RankingRun, RankingDefinition)
        .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
        .where(RankingRun.id == run_id)
    ).one_or_none()
    if row is None:
        raise services.DomainError("Ranking run not found", 404)
    run, definition = row
    entries = session.execute(
        select(RankingEntry, Company)
        .join(Company, Company.id == RankingEntry.company_id)
        .where(RankingEntry.run_id == run.id)
        .order_by(RankingEntry.position.nulls_last(), Company.name, Company.id)
    ).all()
    counts = _ranking_run_counts(session, [run.id])
    return s.RankingRunDetailRead(
        run=_ranking_run_read(run, definition, counts.get(run.id, (0, 0))),
        entries=[
            s.RankingRunEntryRead(
                company=company_read(session, issuer),
                entry=s.RankingEntryRead.model_validate(entry),
            )
            for entry, issuer in entries
        ],
    )
