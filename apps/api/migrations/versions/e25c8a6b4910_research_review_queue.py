"""Record completion of source-derived research queue conditions.

Revision ID: e25c8a6b4910
Revises: d9a4f7c2e681
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e25c8a6b4910"
down_revision: str | Sequence[str] | None = "d9a4f7c2e681"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_queue_completions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("condition_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("task_snapshot", sa.JSON(), nullable=False),
        sa.Column("completed_by", sa.String(length=160), nullable=False),
        sa.Column("completion_note", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(task_id) = 64", name="ck_research_queue_completions_task_id"),
        sa.CheckConstraint(
            "length(condition_fingerprint) = 64",
            name="ck_research_queue_completions_condition_fingerprint",
        ),
        sa.CheckConstraint(
            "task_type IN ('CANDIDATE_STAGE','THESIS_REVIEW','THESIS_QUESTION',"
            "'MATERIAL_EVIDENCE','MODEL_REUNDERWRITE','MODEL_INTEGRITY',"
            "'WATCHLIST_READINESS','STRUCTURAL_RISK')",
            name="ck_research_queue_completions_task_type",
        ),
        sa.CheckConstraint(
            "length(completed_by) > 0", name="ck_research_queue_completions_completed_by"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "condition_fingerprint",
            name="uq_research_queue_completion_condition",
        ),
    )
    op.create_index(
        "ix_research_queue_completions_company_completed",
        "research_queue_completions",
        ["company_id", "completed_at"],
    )
    op.create_index(
        "ix_research_queue_completions_company_id",
        "research_queue_completions",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_queue_completions_company_id", table_name="research_queue_completions"
    )
    op.drop_index(
        "ix_research_queue_completions_company_completed", table_name="research_queue_completions"
    )
    op.drop_table("research_queue_completions")
