"""Retain Thesis Watch classifications and trigger-to-publication lineage.

Revision ID: fa81b2c4d6e0
Revises: f34c8e1b2a90
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fa81b2c4d6e0"
down_revision: str | Sequence[str] | None = "f34c8e1b2a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_trigger_publication_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trigger_id", sa.Uuid(), nullable=False),
        sa.Column("research_revision_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_revision_id", sa.Uuid(), nullable=True),
        sa.Column("classification", sa.String(length=24), nullable=False),
        sa.Column("classification_rationale", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(research_revision_id IS NOT NULL AND thesis_revision_id IS NULL) OR "
            "(research_revision_id IS NULL AND thesis_revision_id IS NOT NULL)",
            name=op.f("ck_research_trigger_publication_links_one_revision_type"),
        ),
        sa.CheckConstraint(
            "classification IN ('NOISE','INCREMENTAL','MAJOR-STRUCTURAL')",
            name=op.f("ck_research_trigger_publication_links_classification"),
        ),
        sa.CheckConstraint(
            "length(classification_rationale) > 0",
            name=op.f("ck_research_trigger_publication_links_classification_rationale"),
        ),
        sa.ForeignKeyConstraint(["trigger_id"], ["research_triggers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["research_revision_id"], ["research_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["thesis_revision_id"], ["investment_thesis_revisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_trigger_publication_links")),
    )
    op.create_index(
        "ix_research_trigger_publication_links_trigger_id",
        "research_trigger_publication_links",
        ["trigger_id"],
    )
    op.create_index(
        "uq_research_trigger_publication_research",
        "research_trigger_publication_links",
        ["trigger_id", "research_revision_id"],
        unique=True,
        postgresql_where=sa.text("research_revision_id IS NOT NULL"),
    )
    op.create_index(
        "uq_research_trigger_publication_thesis",
        "research_trigger_publication_links",
        ["trigger_id", "thesis_revision_id"],
        unique=True,
        postgresql_where=sa.text("thesis_revision_id IS NOT NULL"),
    )
    op.add_column(
        "research_queue_completions",
        sa.Column("trigger_classification", sa.String(length=24), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_research_queue_completions_trigger_classification"),
        "research_queue_completions",
        "trigger_classification IS NULL OR trigger_classification IN "
        "('NOISE','INCREMENTAL','MAJOR-STRUCTURAL')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_research_queue_completions_trigger_classification"),
        "research_queue_completions",
        type_="check",
    )
    op.drop_column("research_queue_completions", "trigger_classification")
    op.drop_index(
        "uq_research_trigger_publication_thesis", table_name="research_trigger_publication_links"
    )
    op.drop_index(
        "uq_research_trigger_publication_research",
        table_name="research_trigger_publication_links",
    )
    op.drop_index(
        "ix_research_trigger_publication_links_trigger_id",
        table_name="research_trigger_publication_links",
    )
    op.drop_table("research_trigger_publication_links")
