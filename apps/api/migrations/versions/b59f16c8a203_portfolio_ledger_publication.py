"""Append immutable ledger ownership/publication lineage.

Revision ID: b59f16c8a203
Revises: a832e94d6f10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b59f16c8a203"
down_revision: str | Sequence[str] | None = "a832e94d6f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_ledger_publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("previous_publication_id", sa.Uuid(), nullable=True),
        sa.Column("holding_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("anchor_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("cutover_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.String(24), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("plan_data", sa.JSON(), nullable=False),
        sa.Column("command_data", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_id", "id"),
        sa.UniqueConstraint(
            "portfolio_id", "sequence", name="uq_portfolio_ledger_publications_sequence"
        ),
        sa.UniqueConstraint("candidate_id"),
        sa.UniqueConstraint("review_id"),
        sa.UniqueConstraint("holding_snapshot_id"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "candidate_id"],
            ["portfolio_ledger_candidates.portfolio_id", "portfolio_ledger_candidates.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["portfolio_ledger_reviews.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["holding_snapshot_id"], ["holding_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["anchor_snapshot_id"], ["holding_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "previous_publication_id"],
            ["portfolio_ledger_publications.portfolio_id", "portfolio_ledger_publications.id"],
            ondelete="RESTRICT",
            name="fk_ledger_publication_previous",
        ),
        sa.CheckConstraint("sequence >= 1", name=op.f("ck_portfolio_ledger_publications_sequence")),
        sa.CheckConstraint(
            "cutover_at <= effective_at", name=op.f("ck_portfolio_ledger_publications_cutover_at")
        ),
        sa.CheckConstraint(
            "previous_publication_id IS NULL OR previous_publication_id <> id",
            name=op.f("ck_portfolio_ledger_publications_previous"),
        ),
        sa.CheckConstraint(
            "(sequence = 1 AND previous_publication_id IS NULL) OR "
            "(sequence > 1 AND previous_publication_id IS NOT NULL)",
            name=op.f("ck_portfolio_ledger_publications_lineage"),
        ),
        sa.CheckConstraint(
            "published_by = 'LOCAL_USER'",
            name=op.f("ck_portfolio_ledger_publications_published_by"),
        ),
        sa.CheckConstraint(
            "length(plan_sha256) = 64", name=op.f("ck_portfolio_ledger_publications_plan_sha256")
        ),
        sa.CheckConstraint(
            "length(request_sha256) = 64",
            name=op.f("ck_portfolio_ledger_publications_request_sha256"),
        ),
        sa.CheckConstraint(
            "length(snapshot_sha256) = 64",
            name=op.f("ck_portfolio_ledger_publications_snapshot_sha256"),
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM portfolio_ledger_publications)")):
        raise RuntimeError(
            "Ledger publications retain source ownership. "
            "Reviewed recovery is required before downgrade"
        )
    op.drop_table("portfolio_ledger_publications")
