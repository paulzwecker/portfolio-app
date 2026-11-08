"""Retain independent ledger candidates and terminal review receipts.

Revision ID: a832e94d6f10
Revises: 9f2a6d4c81b7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a832e94d6f10"
down_revision: str | Sequence[str] | None = "9f2a6d4c81b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_ledger_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("anchor_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("base_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("packet_sha256", sa.String(64), nullable=False),
        sa.Column("preview_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preview_status", sa.String(24), nullable=False),
        sa.Column("packet_data", sa.JSON(), nullable=False),
        sa.Column("preview_data", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("submitted_by", sa.String(24), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "base_candidate_id IS NULL OR base_candidate_id <> id",
            name=op.f("ck_portfolio_ledger_candidates_base_candidate"),
        ),
        sa.CheckConstraint(
            "length(input_sha256) = 64", name=op.f("ck_portfolio_ledger_candidates_input_sha256")
        ),
        sa.CheckConstraint(
            "length(packet_sha256) = 64", name=op.f("ck_portfolio_ledger_candidates_packet_sha256")
        ),
        sa.CheckConstraint(
            "length(preview_sha256) = 64",
            name=op.f("ck_portfolio_ledger_candidates_preview_sha256"),
        ),
        sa.CheckConstraint(
            "length(request_sha256) = 64",
            name=op.f("ck_portfolio_ledger_candidates_request_sha256"),
        ),
        sa.CheckConstraint(
            "submitted_by = 'LOCAL_USER'", name=op.f("ck_portfolio_ledger_candidates_submitted_by")
        ),
        sa.CheckConstraint(
            "preview_status IN ('BLOCKED','OPENING_RECONCILED','ENDING_RECONCILED')",
            name=op.f("ck_portfolio_ledger_candidates_preview_status"),
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            ondelete="RESTRICT",
            name=op.f("fk_portfolio_ledger_candidates_portfolio_id_portfolios"),
        ),
        sa.ForeignKeyConstraint(
            ["anchor_snapshot_id"],
            ["holding_snapshots.id"],
            ondelete="RESTRICT",
            name=op.f("fk_portfolio_ledger_candidates_anchor_snapshot_id_holding_snapshots"),
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "base_candidate_id"],
            ["portfolio_ledger_candidates.portfolio_id", "portfolio_ledger_candidates.id"],
            ondelete="RESTRICT",
            name=op.f("fk_portfolio_ledger_candidates_portfolio_id_portfolio_ledger_candidates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_ledger_candidates")),
        sa.UniqueConstraint(
            "portfolio_id", "id", name=op.f("uq_portfolio_ledger_candidates_portfolio_id")
        ),
        sa.UniqueConstraint(
            "portfolio_id",
            "request_sha256",
            name=op.f("uq_portfolio_ledger_candidates_portfolio_request"),
        ),
    )
    op.create_index(
        "ix_portfolio_ledger_candidates_portfolio_submitted",
        "portfolio_ledger_candidates",
        ["portfolio_id", "submitted_at"],
    )
    op.create_table(
        "portfolio_ledger_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(24), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_data", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('ACCEPT','REJECT')", name=op.f("ck_portfolio_ledger_reviews_decision")
        ),
        sa.CheckConstraint(
            "(decision = 'ACCEPT' AND revision_number IS NOT NULL AND revision_number >= 1) OR "
            "(decision = 'REJECT' AND revision_number IS NULL)",
            name=op.f("ck_portfolio_ledger_reviews_revision_number"),
        ),
        sa.CheckConstraint(
            "length(request_sha256) = 64",
            name=op.f("ck_portfolio_ledger_reviews_request_sha256"),
        ),
        sa.CheckConstraint(
            "reviewed_by = 'LOCAL_USER'", name=op.f("ck_portfolio_ledger_reviews_reviewed_by")
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            ondelete="RESTRICT",
            name=op.f("fk_portfolio_ledger_reviews_portfolio_id_portfolios"),
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "candidate_id"],
            ["portfolio_ledger_candidates.portfolio_id", "portfolio_ledger_candidates.id"],
            ondelete="RESTRICT",
            name=op.f("fk_portfolio_ledger_reviews_portfolio_id_portfolio_ledger_candidates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_ledger_reviews")),
        sa.UniqueConstraint("candidate_id", name=op.f("uq_portfolio_ledger_reviews_candidate_id")),
        sa.UniqueConstraint(
            "portfolio_id", "revision_number", name=op.f("uq_portfolio_ledger_reviews_portfolio_id")
        ),
    )
    op.create_index(
        "ix_portfolio_ledger_reviews_portfolio_reviewed",
        "portfolio_ledger_reviews",
        ["portfolio_id", "reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_ledger_reviews_portfolio_reviewed", table_name="portfolio_ledger_reviews"
    )
    op.drop_table("portfolio_ledger_reviews")
    op.drop_index(
        "ix_portfolio_ledger_candidates_portfolio_submitted",
        table_name="portfolio_ledger_candidates",
    )
    op.drop_table("portfolio_ledger_candidates")
