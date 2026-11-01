"""Persist versioned agent-authored model revision proposals.

Revision ID: 9f2a6d4c81b7
Revises: 3e5c8a1d7b42
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f2a6d4c81b7"
down_revision: str | Sequence[str] | None = "3e5c8a1d7b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_model_revision_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("producer_id", sa.String(length=160), nullable=False),
        sa.Column("author_id", sa.String(length=160), nullable=False),
        sa.Column("external_revision_id", sa.String(length=160), nullable=False),
        sa.Column("base_revision_id", sa.Uuid(), nullable=False),
        sa.Column("base_revision_number", sa.Integer(), nullable=False),
        sa.Column("valuation_listing_id", sa.Uuid(), nullable=False),
        sa.Column("model_type", sa.String(length=60), nullable=False),
        sa.Column("methodology_version", sa.String(length=40), nullable=False),
        sa.Column("model_currency", sa.String(length=3), nullable=False),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("proposal_data", sa.JSON(), nullable=False),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("issue", sa.Text(), nullable=True),
        sa.Column("preview_data", sa.JSON(), nullable=True),
        sa.Column("preview_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflicting_proposal_ids", sa.JSON(), nullable=False),
        sa.Column("accepted_revision_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer_id", sa.String(length=160), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','CONFLICT','INVALID','ACCEPTED','REJECTED')",
            name=op.f("ck_agent_model_revision_proposals_status"),
        ),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64",
            name=op.f("ck_agent_model_revision_proposals_content_fingerprint"),
        ),
        sa.CheckConstraint(
            "model_type IN ('UFCF_DCF_10Y_FADE','OWNER_CASH_FLOW_10Y','RESIDUAL_INCOME_10Y_FADE')",
            name=op.f("ck_agent_model_revision_proposals_model_type"),
        ),
        sa.ForeignKeyConstraint(
            ["accepted_revision_id"],
            ["financial_model_revisions.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_agent_model_revision_proposals_accepted_revision_id_financial_model_revisions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
            name=op.f("fk_agent_model_revision_proposals_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id", "base_revision_id"],
            ["financial_model_revisions.model_id", "financial_model_revisions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_agent_model_revision_proposals_model_id_financial_model_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["financial_models.id"],
            ondelete="RESTRICT",
            name=op.f("fk_agent_model_revision_proposals_model_id_financial_models"),
        ),
        sa.ForeignKeyConstraint(
            ["valuation_listing_id"],
            ["listings.id"],
            ondelete="RESTRICT",
            name=op.f("fk_agent_model_revision_proposals_valuation_listing_id_listings"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_model_revision_proposals")),
        sa.UniqueConstraint(
            "model_id",
            "producer_id",
            "external_revision_id",
            name=op.f("uq_agent_model_proposal_external_revision"),
        ),
    )
    op.create_index(
        op.f("ix_agent_model_proposals_status_submitted"),
        "agent_model_revision_proposals",
        ["status", "submitted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_model_proposals_model_base"),
        "agent_model_revision_proposals",
        ["model_id", "base_revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_model_revision_proposals_model_id"),
        "agent_model_revision_proposals",
        ["model_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_model_revision_proposals_model_id"),
        table_name="agent_model_revision_proposals",
    )
    op.drop_index(
        op.f("ix_agent_model_proposals_model_base"),
        table_name="agent_model_revision_proposals",
    )
    op.drop_index(
        op.f("ix_agent_model_proposals_status_submitted"),
        table_name="agent_model_revision_proposals",
    )
    op.drop_table("agent_model_revision_proposals")
