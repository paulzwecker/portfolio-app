"""Review-gated company observation proposals.

Revision ID: d7b4a6c8e2f0
Revises: c6d8e4f1a290
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7b4a6c8e2f0"
down_revision: str | Sequence[str] | None = "c6d8e4f1a290"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_observation_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("producer_id", sa.String(length=160), nullable=False),
        sa.Column("external_batch_id", sa.String(length=160), nullable=False),
        sa.Column("contract_type", sa.String(length=60), nullable=False),
        sa.Column("payload_data", sa.JSON(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issue", sa.Text(), nullable=True),
        sa.Column("preview_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("accepted_record_ids", sa.JSON(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=160), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_observation_proposals_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_observation_proposals")),
        sa.UniqueConstraint(
            "producer_id",
            "external_batch_id",
            name="uq_company_observation_producer_batch",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','CONFLICT','INVALID','ACCEPTED','REJECTED')",
            name=op.f("ck_company_observation_proposals_status"),
        ),
    )
    op.create_index(
        "ix_company_observation_proposals_company_status",
        "company_observation_proposals",
        ["company_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_observation_proposals_company_status",
        table_name="company_observation_proposals",
    )
    op.drop_table("company_observation_proposals")
