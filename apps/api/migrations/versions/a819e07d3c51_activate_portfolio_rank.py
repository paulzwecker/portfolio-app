"""activate canonical Portfolio Rank

Revision ID: a819e07d3c51
Revises: a818c9070e2f
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "a819e07d3c51"
down_revision: str | Sequence[str] | None = "a818c9070e2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ID = "f9300000-0000-4000-8000-000000000001"
NEW_ID = "a8190000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute(f"UPDATE ranking_definitions SET status = 'RETIRED' WHERE id = '{OLD_ID}'")
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
    # UTC 2026-10-05 is already 2026-10-06 in the repository's Europe/Berlin zone.
    effective_from = datetime(2026, 10, 5, tzinfo=UTC)
    op.bulk_insert(
        definition,
        [
            {
                "id": UUID(NEW_ID),
                "ranking_type": "PORTFOLIO",
                "version": 2,
                "title": "Portfolio Rank (IRR-first Allocation Score)",
                "methodology": (
                    "Reproduce Portfolio_Watchlist.xlsx Overview!S2 as a 100-point score: "
                    "positive target-underweight credit (15 points); Expected Cash-Flow IRR "
                    "capped at 25% (30); 10Y Durability (15); Compounder Quality (20); "
                    "Execution (10); inverse Risk (10); valuation-range uncertainty penalty "
                    "up to 10; negative Expected Excess penalty up to 5. Sort score descending, "
                    "then canonical listing ticker ascending. This is a documented ordinal "
                    "prioritization rule, not a portfolio optimizer or allocation instruction."
                ),
                "population_rule": (
                    "Companies with positive current portfolio weight or positive accepted "
                    "strategic target weight, determined from complete point-in-time holdings "
                    "and an accepted target revision. Companies outside that population are "
                    "NOT_ELIGIBLE only when both observations are complete."
                ),
                "required_inputs": (
                    "Complete current holdings and accepted target allocation; exact, valued "
                    "current weight and explicit target weight; assessed 10Y Durability, "
                    "Compounder Quality, Execution and Risk; complete model outputs in known "
                    "currency with Expected IRR, Hurdle, Bear/Weighted/Bull Fair Value; "
                    "fresh exact-listing price for native outputs; canonical ticker. Missing "
                    "inputs remain unavailable. A run ranks a single comparable return-semantics "
                    "cohort; native shareholder-cash-flow and legacy normalized IRR scores are "
                    "never mixed."
                ),
                "source_reference": (
                    "Portfolio_Watchlist.xlsx: Overview!S1:S2 (Portfolio Score), "
                    "Universe Registry!L4:O (rank/tie-break); docs/workbook-map.md"
                ),
                "implementation_status": "READY",
                "effective_from": effective_from,
                "status": "ACTIVE",
                "recorded_at": effective_from,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM ranking_entries WHERE run_id IN "
        f"(SELECT id FROM ranking_runs WHERE definition_id = '{NEW_ID}')"
    )
    op.execute(f"DELETE FROM ranking_runs WHERE definition_id = '{NEW_ID}'")
    op.execute(f"DELETE FROM ranking_definitions WHERE id = '{NEW_ID}'")
    op.execute(f"UPDATE ranking_definitions SET status = 'ACTIVE' WHERE id = '{OLD_ID}'")
