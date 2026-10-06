"""activate canonical Research Rank and retain its workbook inputs

Revision ID: a820d4e6f119
Revises: a819e07d3c51
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "a820d4e6f119"
down_revision: str | Sequence[str] | None = "a819e07d3c51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ID = "f9300000-0000-4000-8000-000000000003"
NEW_ID = "a8200000-0000-4000-8000-000000000003"


def upgrade() -> None:
    op.create_table(
        "research_priority_inputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_ticker", sa.String(length=40), nullable=False),
        sa.Column("candidate_tier", sa.String(length=8), nullable=False),
        sa.Column("priority_seed", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("input_quality", sa.String(length=16), nullable=False),
        sa.Column("quality_reason", sa.String(length=1000), nullable=True),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("bucket_source_ref", sa.String(length=500), nullable=False),
        sa.Column("priority_seed_source_ref", sa.String(length=500), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "candidate_tier IN ('HIGH','LOW')",
            name=op.f("ck_research_priority_inputs_candidate_tier"),
        ),
        sa.CheckConstraint(
            "priority_seed IS NULL OR priority_seed >= 0",
            name=op.f("ck_research_priority_inputs_priority_seed"),
        ),
        sa.CheckConstraint(
            "input_quality IN ('PASS','DATA_CHECK')",
            name=op.f("ck_research_priority_inputs_input_quality"),
        ),
        sa.CheckConstraint(
            "length(source_digest) = 64", name=op.f("ck_research_priority_inputs_source_digest")
        ),
        sa.CheckConstraint(
            "actor IN ('LOCAL_USER','SYSTEM','IMPORT')",
            name=op.f("ck_research_priority_inputs_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
            name=op.f("fk_research_priority_inputs_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_priority_inputs")),
        sa.UniqueConstraint(
            "company_id", "source_digest", name=op.f("uq_research_priority_inputs_company_id")
        ),
    )
    op.create_index(
        op.f("ix_research_priority_inputs_company_id"),
        "research_priority_inputs",
        ["company_id"],
        unique=False,
    )

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
                "ranking_type": "RESEARCH",
                "version": 2,
                "title": "Research Rank (Candidate Deep-Dive Priority)",
                "methodology": (
                    "Reproduce the documented Research Sort Key: among explicit CANDIDATE "
                    "lifecycle companies with Candidate - High or Candidate - Low research "
                    "bucket, key = 200000 (High) or 100000 (Low) minus the persistent "
                    "deep-dive priority seed. When that seed is blank, the source formula "
                    "explicitly substitutes 50000. Sort the key descending, then canonical "
                    "ticker ascending. Research Rank prioritizes research attention only; "
                    "it is not an investment-attractiveness, Watchlist, or Portfolio rank."
                ),
                "population_rule": (
                    "Only companies with effective/recorded CANDIDATE lifecycle and an "
                    "explicit Candidate - High or Candidate - Low source bucket. Other "
                    "lifecycle states are NOT_ELIGIBLE. Missing candidate-tier evidence or "
                    "lifecycle remains INPUTS_UNAVAILABLE."
                ),
                "required_inputs": (
                    "Point-in-time CANDIDATE lifecycle; candidate bucket from Universe "
                    "Registry column C; optional persistent deep-dive priority seed linked "
                    "from Candidate Ranking column A; canonical registry ticker. A missing "
                    "seed uses the documented 50000 source fallback and is flagged in the "
                    "input snapshot. Expected IRR, quality scores, targets, holdings, and "
                    "Execution Pace are not inputs."
                ),
                "source_reference": (
                    "Portfolio_Watchlist.xlsx: Universe Registry!I4:J and Q4:Q; "
                    "Candidate Ranking!A1:B; docs/workbook-map.md"
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
    op.drop_index(
        op.f("ix_research_priority_inputs_company_id"), table_name="research_priority_inputs"
    )
    op.drop_table("research_priority_inputs")
