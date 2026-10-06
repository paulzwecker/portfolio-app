"""activate canonical Watchlist Rank

Revision ID: a817d392de61
Revises: efbcaa0ca40c
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "a817d392de61"
down_revision: str | Sequence[str] | None = "efbcaa0ca40c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ranking_entries", sa.Column("input_snapshot", sa.JSON(), nullable=True))
    op.drop_constraint(op.f("ck_ranking_entries_status"), "ranking_entries", type_="check")
    op.create_check_constraint(
        "status",
        "ranking_entries",
        "status IN ('RANKED','INPUTS_UNAVAILABLE','NOT_ELIGIBLE','EXCLUDED',"
        "'NOT_MIGRATED','DATA_CHECK')",
    )

    op.execute(
        "UPDATE ranking_definitions SET status = 'RETIRED' "
        "WHERE id = 'f9300000-0000-4000-8000-000000000002' AND status = 'ACTIVE'"
    )
    effective_from = datetime(2026, 10, 5, tzinfo=UTC)
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
                "id": UUID("a8170000-0000-4000-8000-000000000002"),
                "ranking_type": "WATCHLIST",
                "version": 2,
                "title": "Watchlist Rank (Expected IRR)",
                "methodology": (
                    "Among explicit WATCHLIST members with assessed 10Y Durability and "
                    "Compounder Quality, rank comparable Expected IRR values descending; "
                    "break equal values by canonical listing ticker ascending. The rank is "
                    "an ordinal ordering, not a composite score or gate decision. The legacy "
                    "Fit Tier-first Candidate Rank remains separate. Native shareholder-cash-"
                    "flow IRR is the preferred cohort. It is never mixed in one run with a "
                    "legacy normalized Expected IRR field; when native inputs exist, legacy-"
                    "only peers are DATA_CHECK. Otherwise only comparable current legacy "
                    "contract values may form the legacy cohort. Missing values are never "
                    "zero. Quality/durability numeric thresholds are not documented, so "
                    "assessments are shown as context and no pass/fail result is inferred."
                ),
                "population_rule": (
                    "Only companies whose effective and recorded lifecycle at run time is "
                    "explicitly WATCHLIST. Every other universe company is NOT_ELIGIBLE."
                ),
                "required_inputs": (
                    "Effective/recorded WATCHLIST lifecycle; assessed 10Y Durability and "
                    "Compounder Quality observations; one unambiguous Expected IRR from a "
                    "point-in-time native output or comparable current normalized legacy "
                    "contract; known model currency and usable output quality; canonical "
                    "listing ticker for the documented tie-break. Forward Fundamental CAGR, "
                    "Fair Value, Hurdle, and portfolio state are retained as context only."
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
        "DELETE FROM ranking_entries WHERE run_id IN (SELECT id FROM ranking_runs "
        "WHERE definition_id = 'a8170000-0000-4000-8000-000000000002')"
    )
    op.execute(
        "DELETE FROM ranking_runs WHERE definition_id = 'a8170000-0000-4000-8000-000000000002'"
    )
    op.execute("DELETE FROM ranking_definitions WHERE id = 'a8170000-0000-4000-8000-000000000002'")
    op.execute(
        "UPDATE ranking_definitions SET status = 'ACTIVE' "
        "WHERE id = 'f9300000-0000-4000-8000-000000000002'"
    )
    op.drop_constraint(op.f("ck_ranking_entries_status"), "ranking_entries", type_="check")
    op.create_check_constraint(
        "status",
        "ranking_entries",
        "status IN ('RANKED','INPUTS_UNAVAILABLE','NOT_ELIGIBLE','EXCLUDED','NOT_MIGRATED')",
    )
    op.drop_column("ranking_entries", "input_snapshot")
