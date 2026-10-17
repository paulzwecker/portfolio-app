"""version rank definitions for return-method comparability

Revision ID: 7c1e62f8a4b3
Revises: 7b0f1c4a91d2
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "7c1e62f8a4b3"
down_revision: str | Sequence[str] | None = "7b0f1c4a91d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EFFECTIVE_FROM = datetime(2026, 10, 9, tzinfo=UTC)


def upgrade() -> None:
    op.execute(
        "UPDATE ranking_definitions SET status = 'RETIRED' "
        "WHERE status = 'ACTIVE' AND ranking_type IN ('WATCHLIST','PORTFOLIO')"
    )
    definition = sa.table(
        "ranking_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("ranking_type", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("title", sa.String()),
        sa.column("methodology", sa.Text()),
        sa.column("population_rule", sa.Text()),
        sa.column("required_inputs", sa.Text()),
        sa.column("source_reference", sa.String()),
        sa.column("implementation_status", sa.String()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("status", sa.String()),
        sa.column("recorded_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        definition,
        [
            {
                "id": UUID("7c1e0000-0000-4000-8000-000000000001"),
                "ranking_type": "WATCHLIST",
                "version": 4,
                "title": "Watchlist Rank (versioned Expected IRR cohorts)",
                "methodology": (
                    "Sort eligible explicit Watchlist companies by Expected IRR descending and "
                    "canonical valuation-listing ticker ascending within one documented return "
                    "cohort. Identical methodology/version returns are directly comparable. "
                    "Owner-cash-flow and residual-income equity returns may share the equity "
                    "cohort conditionally with method labels retained. Enterprise UFCF returns "
                    "cannot be mixed with equity returns. If more than one eligible cohort is "
                    "present, the run reports DATA_CHECK rather than selecting one."
                ),
                "population_rule": (
                    "Companies with explicit WATCHLIST lifecycle only. No current/legacy source "
                    "priority substitutes for a versioned return-method definition."
                ),
                "required_inputs": (
                    "Numeric Expected IRR; exact listing mapping and currency; classified "
                    "versioned return-method definition; complete source-quality state. Native "
                    "outputs additionally require a fresh exact-listing reference quote. A single "
                    "run cannot order enterprise UFCF and equity-return methods together."
                ),
                "source_reference": (
                    "Universe Registry!M4 and Expected IRR source formulas; "
                    "docs/watchlist-rank.md; "
                    "docs/financial-models.md"
                ),
                "implementation_status": "READY",
                "effective_from": EFFECTIVE_FROM,
                "status": "ACTIVE",
                "recorded_at": EFFECTIVE_FROM,
            },
            {
                "id": UUID("7c1e0000-0000-4000-8000-000000000002"),
                "ranking_type": "PORTFOLIO",
                "version": 3,
                "title": "Portfolio Rank (IRR-first allocation score, method cohort aware)",
                "methodology": (
                    "Preserve the documented 100-point IRR-first allocation score: positive "
                    "target-underweight credit (15); Expected IRR capped at 25% (30); 10Y "
                    "Durability (15); Compounder Quality (20); Execution (10); inverse Risk "
                    "(10); valuation-range uncertainty penalty up to 10; negative Expected Excess "
                    "penalty up to 5. Rank only companies with the same exact versioned Expected "
                    "IRR methodology in one run. "
                    "Portfolio Score includes Expected Excess, whose hurdle basis is method "
                    "specific; no cross-method score equivalence or enterprise-to-equity bridge "
                    "is inferred. Mixed return-method populations are DATA_CHECK."
                ),
                "population_rule": (
                    "Companies with positive current portfolio weight or positive accepted "
                    "strategic target weight, determined from complete point-in-time holdings and "
                    "an accepted target revision."
                ),
                "required_inputs": (
                    "Complete current holdings and accepted target allocation; exact current and "
                    "target weights; assessed canonical scores; complete model outputs with "
                    "classified return-method metadata, Expected IRR, method-specific Hurdle, "
                    "Bear/Weighted/Bull Fair Value, currency and listing. Native outputs also "
                    "require a fresh exact-listing quote."
                ),
                "source_reference": (
                    "Overview!S2; docs/portfolio-rank.md; docs/financial-models.md"
                ),
                "implementation_status": "READY",
                "effective_from": EFFECTIVE_FROM,
                "status": "ACTIVE",
                "recorded_at": EFFECTIVE_FROM,
            },
        ],
    )


def downgrade() -> None:
    new_ids = (
        "7c1e0000-0000-4000-8000-000000000001",
        "7c1e0000-0000-4000-8000-000000000002",
    )
    op.execute(
        "DELETE FROM ranking_entries WHERE run_id IN "
        "(SELECT id FROM ranking_runs WHERE definition_id IN ('" + "','".join(new_ids) + "'))"
    )
    op.execute("DELETE FROM ranking_runs WHERE definition_id IN ('" + "','".join(new_ids) + "')")
    op.execute("DELETE FROM ranking_definitions WHERE id IN ('" + "','".join(new_ids) + "')")
    op.execute(
        "UPDATE ranking_definitions SET status = 'ACTIVE' "
        "WHERE ranking_type IN ('WATCHLIST','PORTFOLIO') AND status = 'RETIRED' "
        "AND version = (SELECT max(active.version) FROM ranking_definitions AS active "
        "WHERE active.ranking_type = ranking_definitions.ranking_type "
        "AND active.status = 'RETIRED' AND active.version < "
        "CASE ranking_definitions.ranking_type WHEN 'WATCHLIST' THEN 4 ELSE 3 END)"
    )
