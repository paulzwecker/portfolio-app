"""Opt-in fictional demonstration data. Never a workbook import or startup hook."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops
from portfolio_api.domain.models import (
    Actor,
    Company,
    Lifecycle,
    Portfolio,
    RankingDefinition,
    RankingRun,
    RankingType,
    ScoreAssessment,
    ScoreAssessmentStatus,
    ScoreDefinition,
    ScoreDimension,
)
from portfolio_api.settings import Settings

DEMO_NAME = "Demonstration portfolio"


def seed(session: Session) -> UUID:
    session.execute(text("SELECT pg_advisory_xact_lock(1347375700)"))
    portfolios = session.scalars(select(Portfolio)).all()
    companies = session.scalars(select(Company)).all()
    if portfolios or companies:
        if len(portfolios) == 1 and portfolios[0].is_demo and all(c.is_demo for c in companies):
            demo_issuers = list(
                session.scalars(select(Company).where(Company.is_demo).order_by(Company.name))
            )
            if len(demo_issuers) == 4:
                seed_scores(session, demo_issuers, datetime.now(UTC))
                seed_rankings(session)
            return portfolios[0].id
        raise ops.DomainError(
            "Demo seed requires an empty universe/portfolio; existing real data is preserved", 409
        )
    moment = datetime.now(UTC)
    provenance = {
        "actor": Actor.SYSTEM,
        "reason": "Fictional development demonstration; not a workbook migration",
        "source": "development-seed-v1",
        "effective_at": moment,
    }
    issuers: list[Company] = []
    listing_ids: list[UUID] = []
    for name, currency, ticker, lifecycle in [
        ("Atlas Software (Demo)", "USD", "ATLA", Lifecycle.PORTFOLIO),
        ("Northstar Instruments (Demo)", "EUR", "NSTR", Lifecycle.PORTFOLIO),
        ("Cedar Networks (Demo)", "USD", "CDRN", Lifecycle.WATCHLIST),
        ("Harbor Robotics (Demo)", None, "HBRR", Lifecycle.CANDIDATE),
    ]:
        issuer = ops.create_company(
            session, s.CompanyCreate(name=name, reporting_currency=currency), demo=True
        )
        security = ops.create_security(
            session,
            issuer.id,
            s.SecurityCreate(
                name=f"{name} ordinary A", security_type="COMMON_STOCK", share_class="A"
            ),
        )
        listing = ops.create_listing(
            session, security.id, s.ListingCreate(ticker=ticker, venue="DEMO-X", currency=currency)
        )
        ops.transition_lifecycle(
            session,
            issuer.id,
            s.LifecycleChange(new_state=lifecycle, expected_event_id=None, **provenance),
        )
        issuers.append(issuer)
        listing_ids.append(listing.id)
    alternate = ops.create_security(
        session,
        issuers[0].id,
        s.SecurityCreate(
            name="Atlas class C (Demo)", security_type="COMMON_STOCK", share_class="C"
        ),
    )
    ops.create_listing(
        session, alternate.id, s.ListingCreate(ticker="ATLC", venue="DEMO-X", currency="USD")
    )
    # Same economic class, separate venue quotation. No share or FX conversion inferred.
    ops.create_listing(
        session, alternate.id, s.ListingCreate(ticker="ATLC", venue="DEMO-EU", currency="EUR")
    )
    ordinary = session.scalar(select(Company.id).where(Company.id == issuers[1].id))
    assert ordinary is not None
    from portfolio_api.domain.models import Security

    underlying = session.scalar(select(Security).where(Security.company_id == ordinary))
    assert underlying is not None
    adr = ops.create_security(
        session,
        ordinary,
        s.SecurityCreate(
            name="Northstar ADR (Demo)", security_type="ADR", underlying_security_id=underlying.id
        ),
    )
    ops.create_listing(
        session, adr.id, s.ListingCreate(ticker="NSTA", venue="DEMO-US", currency="USD")
    )
    portfolio = ops.create_portfolio(
        session, s.PortfolioCreate(name=DEMO_NAME, base_currency="EUR"), demo=True
    )
    ops.record_holdings(
        session,
        portfolio.id,
        s.SnapshotCreate(
            completeness="COMPLETE",
            positions=[
                s.PositionInput(listing_id=listing_ids[0], quantity=Decimal("12.5")),
                s.PositionInput(listing_id=listing_ids[1], quantity=Decimal("8")),
            ],
            cash_positions=[
                s.CashInput(currency="EUR", balance=Decimal("1500")),
                s.CashInput(currency="USD", balance=Decimal("200")),
            ],
            **provenance,
        ),
    )
    targets = ops.create_targets(
        session,
        portfolio.id,
        s.TargetCreate(
            allocations=[
                s.AllocationInput(company_id=issuers[0].id, weight=Decimal("0.35")),
                s.AllocationInput(company_id=issuers[1].id, weight=Decimal("0.25")),
                s.AllocationInput(company_id=issuers[2].id, weight=Decimal("0")),
            ],
            **provenance,
        ),
    )
    ops.accept_targets(session, portfolio.id, targets.id)
    seed_scores(session, issuers, moment)
    seed_rankings(session)
    return portfolio.id


def seed_scores(session: Session, issuers: list[Company], moment: datetime) -> None:
    """Add only explicitly fictional score examples; retain existing authored history."""
    existing_dimensions = {
        (company_id, dimension)
        for company_id, dimension in session.execute(
            select(ScoreAssessment.company_id, ScoreDefinition.dimension)
            .join(ScoreDefinition, ScoreDefinition.id == ScoreAssessment.score_definition_id)
            .where(ScoreAssessment.company_id.in_([issuer.id for issuer in issuers]))
        )
    }
    examples: dict[int, dict[ScoreDimension, tuple[str | None, ScoreAssessmentStatus, str]]] = {
        0: {
            ScoreDimension.DURABILITY_10Y: (
                "4.25",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional updated assessment after stronger evidence of lasting "
                "customer relevance.",
            ),
            ScoreDimension.COMPOUNDER_QUALITY: (
                "4.00",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional example: strong reinvestment opportunities support durable "
                "value creation.",
            ),
            ScoreDimension.EXECUTION: (
                "4.00",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional example: operating delivery has generally matched stated priorities.",
            ),
            ScoreDimension.RISK: (
                "2.00",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional structural business risk review; valuation is excluded.",
            ),
        },
        1: {
            ScoreDimension.DURABILITY_10Y: (
                "3.50",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional example: long-lived products, with durability still under review.",
            ),
            ScoreDimension.COMPOUNDER_QUALITY: (
                "3.75",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional example: healthy reinvestment economics with limited history.",
            ),
            ScoreDimension.EXECUTION: (
                "3.50",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional example: steady operating delivery with some execution variance.",
            ),
            ScoreDimension.RISK: (
                "3.00",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional business and regulatory risk assessment; valuation is excluded.",
            ),
        },
        2: {
            ScoreDimension.DURABILITY_10Y: (
                "0.00",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional explicit zero illustrates a completed low-durability assessment.",
            ),
            ScoreDimension.COMPOUNDER_QUALITY: (
                None,
                ScoreAssessmentStatus.MISSING,
                "A quality assessment has not been recorded in this fictional example.",
            ),
            ScoreDimension.EXECUTION: (
                None,
                ScoreAssessmentStatus.UNAVAILABLE,
                "Operating evidence is unavailable in this fictional example.",
            ),
            ScoreDimension.RISK: (
                "3.50",
                ScoreAssessmentStatus.ASSESSED,
                "Fictional elevated structural risk review; valuation is excluded.",
            ),
        },
    }
    for company_index, records in examples.items():
        issuer = issuers[company_index]
        for dimension, (score, status, rationale) in records.items():
            if (issuer.id, dimension) in existing_dimensions:
                continue
            superseded = None
            if company_index == 0 and dimension == ScoreDimension.DURABILITY_10Y:
                superseded = ops.create_score_assessment(
                    session,
                    issuer.id,
                    s.ScoreAssessmentCreate(
                        dimension=dimension,
                        score="3.50",
                        status=ScoreAssessmentStatus.ASSESSED,
                        effective_at=moment - timedelta(days=180),
                        rationale=(
                            "Fictional earlier assessment: business durability evidence "
                            "warrants review."
                        ),
                        actor=Actor.SYSTEM,
                        source="development-seed-v1",
                    ),
                ).id
            ops.create_score_assessment(
                session,
                issuer.id,
                s.ScoreAssessmentCreate(
                    dimension=dimension,
                    score=score,
                    status=status,
                    effective_at=moment - timedelta(days=1),
                    rationale=rationale,
                    actor=Actor.SYSTEM,
                    source="development-seed-v1",
                    superseded_assessment_id=superseded,
                ),
            )
            existing_dimensions.add((issuer.id, dimension))


def seed_rankings(session: Session) -> None:
    """Capture fictional availability snapshots without fabricating ordinal ranks."""
    for ranking_type in RankingType:
        existing = session.scalar(
            select(RankingRun.id)
            .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
            .where(
                RankingDefinition.ranking_type == ranking_type,
                RankingRun.source == "development-seed-v1",
            )
            .limit(1)
        )
        if existing is not None:
            continue
        ops.create_ranking_run(
            session,
            s.RankingRunCreate(
                ranking_type=ranking_type,
                actor=Actor.SYSTEM,
                reason=(
                    "Fictional development snapshot. Ranking inputs are not migrated, so no "
                    "numeric position is assigned."
                ),
                source="development-seed-v1",
            ),
        )


def main() -> None:
    engine = create_database_engine(Settings())
    if engine is None:
        raise SystemExit("Configure DATABASE_URL and migrate before seeding")
    try:
        with Session(engine) as session, session.begin():
            identifier = seed(session)
        print(f"Fictional demonstration portfolio ready: {identifier}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
