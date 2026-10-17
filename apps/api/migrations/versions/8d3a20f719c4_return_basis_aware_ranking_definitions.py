"""Require explicit return versions and retained listing quote bases in ranks.

Revision ID: 8d3a20f719c4
Revises: 7c1e62f8a4b3
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "8d3a20f719c4"
down_revision: str | Sequence[str] | None = "7c1e62f8a4b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EFFECTIVE_FROM = datetime(2026, 10, 9, tzinfo=UTC)
WATCHLIST_ID = "8d3a0000-0000-4000-8000-000000000001"
PORTFOLIO_ID = "8d3a0000-0000-4000-8000-000000000002"


def upgrade() -> None:
    op.execute(
        "UPDATE ranking_definitions SET status = 'RETIRED' "
        "WHERE status = 'ACTIVE' AND ranking_type IN ('WATCHLIST','PORTFOLIO')"
    )
    definitions = sa.table(
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
        definitions,
        [
            {
                "id": UUID(WATCHLIST_ID),
                "ranking_type": "WATCHLIST",
                "version": 5,
                "title": "Watchlist Rank (return-basis aware)",
                "methodology": (
                    "Sort explicit Watchlist members by Expected IRR descending and canonical "
                    "listing ticker ascending only when every ranked return has a classified "
                    "methodology/version and a retained exact-listing share-price basis. Same "
                    "method/version returns are directly comparable. Owner-cash-flow and "
                    "residual-income equity returns are conditionally comparable with both "
                    "method labels retained. Enterprise and equity returns, unknown method "
                    "versions, or an unresolved competing return basis produce DATA_CHECK; no "
                    "partial cohort is selected. Cross-currency IRRs remain local-currency rates "
                    "with FX excluded."
                ),
                "population_rule": (
                    "Companies with explicit WATCHLIST lifecycle only. No source priority "
                    "substitutes for versioned method and captured quote-basis evidence."
                ),
                "required_inputs": (
                    "Numeric Expected IRR; documented currency; exact valuation listing; "
                    "captured share-price observation on that listing; classified return-method "
                    "definition and supported version; complete source-quality state. Native "
                    "outputs also require a fresh reference quote. Legacy outputs without their "
                    "historical price basis remain DATA_CHECK."
                ),
                "source_reference": (
                    "Universe Registry!M4 and Expected IRR source formulas; "
                    "docs/watchlist-rank.md; "
                    "docs/return-semantics.md"
                ),
                "implementation_status": "READY",
                "effective_from": EFFECTIVE_FROM,
                "status": "ACTIVE",
                "recorded_at": EFFECTIVE_FROM,
            },
            {
                "id": UUID(PORTFOLIO_ID),
                "ranking_type": "PORTFOLIO",
                "version": 4,
                "title": "Portfolio Rank (versioned return-basis cohorts)",
                "methodology": (
                    "Preserve the documented 100-point IRR-first allocation score. A run uses "
                    "one exact Expected IRR methodology code/version because Expected Excess "
                    "uses a method-specific hurdle. Every return must have a classified supported "
                    "method version, exact valuation listing, documented currency, and captured "
                    "share-price observation. Legacy snapshots that did not retain their used "
                    "listing quote cannot enter a comparable Portfolio Score. Mixed methods or "
                    "versions remain DATA_CHECK; cross-currency values are explicitly FX-excluded."
                ),
                "population_rule": (
                    "Companies with positive current portfolio weight or positive accepted "
                    "strategic target weight, determined from complete point-in-time holdings "
                    "and an accepted target revision."
                ),
                "required_inputs": (
                    "Complete current holdings and accepted target allocation; exact current and "
                    "target weights; assessed canonical scores; complete model outputs with "
                    "classified exact-version return methodology, Expected IRR, method-specific "
                    "Hurdle, Bear/Weighted/Bull Fair Value, documented currency, exact listing, "
                    "and captured share-price observation. Native outputs additionally require a "
                    "fresh exact-listing quote."
                ),
                "source_reference": (
                    "Overview!S2; docs/portfolio-rank.md; docs/return-semantics.md"
                ),
                "implementation_status": "READY",
                "effective_from": EFFECTIVE_FROM,
                "status": "ACTIVE",
                "recorded_at": EFFECTIVE_FROM,
            },
        ],
    )


def downgrade() -> None:
    for definition_id in (WATCHLIST_ID, PORTFOLIO_ID):
        op.execute(
            "DELETE FROM ranking_entries WHERE run_id IN "
            f"(SELECT id FROM ranking_runs WHERE definition_id = '{definition_id}')"
        )
        op.execute(f"DELETE FROM ranking_runs WHERE definition_id = '{definition_id}'")
        op.execute(f"DELETE FROM ranking_definitions WHERE id = '{definition_id}'")
    op.execute(
        "UPDATE ranking_definitions SET status = 'ACTIVE' "
        "WHERE ranking_type = 'WATCHLIST' AND status = 'RETIRED' AND version = 4"
    )
    op.execute(
        "UPDATE ranking_definitions SET status = 'ACTIVE' "
        "WHERE ranking_type = 'PORTFOLIO' AND status = 'RETIRED' AND version = 3"
    )
