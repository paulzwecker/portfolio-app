"""Keep quality observations as context rather than inventing a score gate.

Revision ID: a818c9070e2f
Revises: a817d392de61
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "a818c9070e2f"
down_revision: str | Sequence[str] | None = "a817d392de61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ID = "a8170000-0000-4000-8000-000000000002"
NEW_ID = "a8180000-0000-4000-8000-000000000002"


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
    effective_from = datetime(2026, 10, 5, tzinfo=UTC)
    op.bulk_insert(
        definition,
        [
            {
                "id": UUID(NEW_ID),
                "ranking_type": "WATCHLIST",
                "version": 3,
                "title": "Watchlist Rank (Expected IRR)",
                "methodology": (
                    "Among explicit WATCHLIST members, rank comparable Expected IRR values "
                    "descending; break equal values by canonical listing ticker ascending. "
                    "This is an ordinal ordering, not a composite score or gate decision. "
                    "Native shareholder-cash-flow IRR is kept separate from legacy normalized "
                    "Expected IRR. Durability, Compounder Quality and forward compounding are "
                    "retained as context. Numeric quality-gate thresholds and portfolio-fit "
                    "adjustments are not documented and are not inferred."
                ),
                "population_rule": (
                    "Only companies whose effective and recorded lifecycle at run time is "
                    "explicitly WATCHLIST. Every other universe company is NOT_ELIGIBLE."
                ),
                "required_inputs": (
                    "Effective/recorded WATCHLIST lifecycle; one unambiguous point-in-time "
                    "Expected IRR from a comparable native output or normalized legacy contract; "
                    "documented currency and usable output quality; canonical listing ticker "
                    "for the documented tie-break. Quality scores, forward CAGR, Fair Value, "
                    "Hurdle and portfolio state are retained as separate context only."
                ),
                "source_reference": (
                    "Portfolio_Watchlist.xlsx: Universe Registry!M4:P; docs/workbook-map.md"
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
