"""canonical normalized financial-model outputs and history

Revision ID: 74ab83c99170
Revises: 01773da3b70f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "74ab83c99170"
down_revision: str | Sequence[str] | None = "01773da3b70f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_output_import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("workbook_sha256", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reconciliation", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "length(source_digest) = 64",
            name=op.f("ck_model_output_import_batches_source_digest"),
        ),
        sa.CheckConstraint(
            "length(workbook_sha256) = 64",
            name=op.f("ck_model_output_import_batches_workbook_sha256"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_output_import_batches")),
        sa.UniqueConstraint(
            "source_digest", name=op.f("uq_model_output_import_batches_source_digest")
        ),
    )
    op.create_table(
        "model_output_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("model_key", sa.String(length=120), nullable=False),
        sa.Column("snapshot_key", sa.String(length=200), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=24), nullable=False),
        sa.Column("contract_version", sa.String(length=40), nullable=True),
        sa.Column("contract_status", sa.String(length=24), nullable=False),
        sa.Column("output_quality", sa.String(length=20), nullable=False),
        sa.Column("model_currency", sa.String(length=3), nullable=True),
        sa.Column("currency_status", sa.String(length=16), nullable=False),
        sa.Column("currency_source_ref", sa.String(length=1000), nullable=True),
        sa.Column("model_status", sa.Text(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=1000), nullable=False),
        sa.Column("source_revision_id", sa.String(length=160), nullable=True),
        sa.Column("revision_source", sa.String(length=500), nullable=True),
        sa.Column("revision_type", sa.String(length=300), nullable=True),
        sa.Column("source_actor", sa.String(length=300), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("field_issues", sa.JSON(), nullable=False),
        sa.Column("bear_fv", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("base_fv", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("bull_fv", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("bear_probability", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("base_probability", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("bull_probability", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("weighted_fv", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("weighted_upside", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("expected_cash_flow_irr", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("hurdle", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("expected_excess", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.Column("forward_fundamental_cagr", sa.Numeric(precision=38, scale=22), nullable=True),
        sa.CheckConstraint(
            "snapshot_kind IN ('CURRENT_CONTRACT','LEGACY_REVISION')",
            name=op.f("ck_model_output_snapshots_snapshot_kind"),
        ),
        sa.CheckConstraint(
            "contract_status IN ('PASS','NOT_MAPPED','NO_CONTRACT','DATA_CHECK','HISTORICAL_ONLY')",
            name=op.f("ck_model_output_snapshots_contract_status"),
        ),
        sa.CheckConstraint(
            "output_quality IN ('COMPLETE','PARTIAL','DATA_CHECK','UNAVAILABLE')",
            name=op.f("ck_model_output_snapshots_output_quality"),
        ),
        sa.CheckConstraint(
            "(model_currency IS NULL AND currency_status = 'UNKNOWN') OR "
            "(model_currency IS NOT NULL AND currency_status = 'DOCUMENTED')",
            name=op.f("ck_model_output_snapshots_currency_status"),
        ),
        sa.CheckConstraint(
            "bear_probability IS NULL OR bear_probability BETWEEN 0 AND 1",
            name=op.f("ck_model_output_snapshots_bear_probability"),
        ),
        sa.CheckConstraint(
            "base_probability IS NULL OR base_probability BETWEEN 0 AND 1",
            name=op.f("ck_model_output_snapshots_base_probability"),
        ),
        sa.CheckConstraint(
            "bull_probability IS NULL OR bull_probability BETWEEN 0 AND 1",
            name=op.f("ck_model_output_snapshots_bull_probability"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["model_output_import_batches.id"],
            name=op.f("fk_model_output_snapshots_batch_id_model_output_import_batches"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_model_output_snapshots_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_output_snapshots")),
        sa.UniqueConstraint(
            "company_id",
            "model_key",
            "snapshot_key",
            name="uq_model_output_snapshot_identity",
        ),
    )
    op.create_index(
        op.f("ix_model_output_snapshots_batch_id"),
        "model_output_snapshots",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_output_snapshots_company_id"),
        "model_output_snapshots",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_output_snapshots_company_recorded",
        "model_output_snapshots",
        ["company_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_output_snapshots_company_model",
        "model_output_snapshots",
        ["company_id", "model_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_output_snapshots_company_model", table_name="model_output_snapshots")
    op.drop_index("ix_model_output_snapshots_company_recorded", table_name="model_output_snapshots")
    op.drop_index(op.f("ix_model_output_snapshots_company_id"), table_name="model_output_snapshots")
    op.drop_index(op.f("ix_model_output_snapshots_batch_id"), table_name="model_output_snapshots")
    op.drop_table("model_output_snapshots")
    op.drop_table("model_output_import_batches")
