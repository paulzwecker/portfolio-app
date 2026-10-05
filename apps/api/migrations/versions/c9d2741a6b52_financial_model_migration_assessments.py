"""Store immutable legacy model input mapping and parity assessments.

Revision ID: c9d2741a6b52
Revises: 8a9f2c1d4e71
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d2741a6b52"
down_revision: str | Sequence[str] | None = "8a9f2c1d4e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_model_migration_assessments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("revision_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_model_key", sa.String(length=120), nullable=False),
        sa.Column("source_workbook_sha256", sa.String(length=64), nullable=False),
        sa.Column("mapping_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(source_workbook_sha256) = 64",
            name=op.f("ck_financial_model_migration_assessments_source_workbook_sha256"),
        ),
        sa.CheckConstraint(
            "status IN ('PARITY_PASS','PARTIAL_MAPPING','DATA_CHECK','BLOCKED')",
            name=op.f("ck_financial_model_migration_assessments_status"),
        ),
        sa.ForeignKeyConstraint(["model_id"], ["financial_models.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["financial_model_revisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_model_migration_assessments")),
        sa.UniqueConstraint(
            "source_model_key",
            "source_workbook_sha256",
            "mapping_version",
            name=op.f("uq_financial_model_migration_source"),
        ),
    )
    op.create_index(
        op.f("ix_financial_model_migration_assessments_model_id"),
        "financial_model_migration_assessments",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_financial_model_migration_assessments_revision_id"),
        "financial_model_migration_assessments",
        ["revision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_financial_model_migration_assessments_revision_id"),
        table_name="financial_model_migration_assessments",
    )
    op.drop_index(
        op.f("ix_financial_model_migration_assessments_model_id"),
        table_name="financial_model_migration_assessments",
    )
    op.drop_table("financial_model_migration_assessments")
