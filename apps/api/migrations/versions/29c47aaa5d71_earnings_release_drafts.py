"""Persist reviewer-owned release drafts keyed by EDGAR accession and DCF revision."""

import sqlalchemy as sa
from alembic import op

revision = "29c47aaa5d71"
down_revision = "63ad18f0e52b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "earnings_release_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("listing_id", sa.Uuid(), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column(
            "base_revision_id",
            sa.Uuid(),
            sa.ForeignKey("financial_model_revisions.id"),
            nullable=False,
        ),
        sa.Column("accession", sa.String(20), nullable=False),
        sa.Column("assessment", sa.JSON(), nullable=False),
        sa.Column("replacement", sa.Numeric(22, 12)),
        sa.Column("publication_id", sa.Uuid(), sa.ForeignKey("research_revisions.id")),
        sa.Column("proposal_id", sa.Uuid(), sa.ForeignKey("agent_model_revision_proposals.id")),
        sa.UniqueConstraint(
            "listing_id", "accession", "base_revision_id", name="uq_earnings_draft_event_base"
        ),
    )


def downgrade() -> None:
    op.drop_table("earnings_release_drafts")
