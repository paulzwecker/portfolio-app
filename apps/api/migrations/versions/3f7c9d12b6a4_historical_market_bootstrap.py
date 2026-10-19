"""Add resumable historical market-data bootstrap run checkpoints.

Revision ID: 3f7c9d12b6a4
Revises: 14b4c1a0a001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f7c9d12b6a4"
down_revision: str | Sequence[str] | None = "14b4c1a0a001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_data_bootstrap_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=120), nullable=False),
        sa.Column("provider_schema_version", sa.String(length=120), nullable=False),
        sa.Column("crosswalk_sha256", sa.String(length=64), nullable=False),
        sa.Column("target_environment", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_provider_request_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "length(input_digest) = 64", name=op.f("ck_market_data_bootstrap_runs_input_digest")
        ),
        sa.CheckConstraint(
            "length(crosswalk_sha256) = 64",
            name=op.f("ck_market_data_bootstrap_runs_crosswalk_sha256"),
        ),
        sa.CheckConstraint(
            "start_date <= end_date", name=op.f("ck_market_data_bootstrap_runs_date_window")
        ),
        sa.CheckConstraint(
            "target_environment IN ('development','rehearsal')",
            name=op.f("ck_market_data_bootstrap_runs_target_environment"),
        ),
        sa.CheckConstraint(
            "status IN ('PREPARED','RUNNING','PARTIAL','COMPLETE','FAILED','BLOCKED')",
            name=op.f("ck_market_data_bootstrap_runs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_data_bootstrap_runs")),
    )
    op.create_index(
        "ix_market_data_bootstrap_runs_status_prepared",
        "market_data_bootstrap_runs",
        ["status", "prepared_at"],
    )

    op.create_table(
        "market_data_bootstrap_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("subject_kind", sa.String(length=16), nullable=False),
        sa.Column("subject_key", sa.String(length=200), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("listing_id", sa.Uuid(), nullable=True),
        sa.Column("base_currency", sa.String(length=3), nullable=True),
        sa.Column("quote_currency", sa.String(length=3), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.Column("source_digest", sa.String(length=64), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "subject_kind IN ('LISTING','FX_PAIR')",
            name=op.f("ck_market_data_bootstrap_checkpoints_subject_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETE','UNAVAILABLE','FAILED','BLOCKED')",
            name=op.f("ck_market_data_bootstrap_checkpoints_status"),
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3",
            name=op.f("ck_market_data_bootstrap_checkpoints_attempt_count"),
        ),
        sa.CheckConstraint(
            "(subject_kind = 'LISTING' AND listing_id IS NOT NULL "
            "AND base_currency IS NULL AND quote_currency IS NULL) OR "
            "(subject_kind = 'FX_PAIR' AND listing_id IS NULL AND company_id IS NULL "
            "AND base_currency IS NOT NULL AND quote_currency IS NOT NULL)",
            name=op.f("ck_market_data_bootstrap_checkpoints_subject_identity"),
        ),
        sa.CheckConstraint(
            "base_currency IS NULL OR base_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_market_data_bootstrap_checkpoints_base_currency"),
        ),
        sa.CheckConstraint(
            "quote_currency IS NULL OR quote_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_market_data_bootstrap_checkpoints_quote_currency"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["market_data_bootstrap_runs.id"],
            name=op.f("fk_market_data_bootstrap_checkpoints_run_id_market_data_bootstrap_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_market_data_bootstrap_checkpoints_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name=op.f("fk_market_data_bootstrap_checkpoints_listing_id_listings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["market_data_batches.id"],
            name=op.f("fk_market_data_bootstrap_checkpoints_batch_id_market_data_batches"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_data_bootstrap_checkpoints")),
        sa.UniqueConstraint(
            "run_id", "subject_kind", "subject_key", name="uq_market_data_bootstrap_checkpoint"
        ),
    )
    op.create_index(
        op.f("ix_market_data_bootstrap_checkpoints_run_id"),
        "market_data_bootstrap_checkpoints",
        ["run_id"],
    )
    op.create_index(
        "ix_market_data_bootstrap_checkpoint_run_status",
        "market_data_bootstrap_checkpoints",
        ["run_id", "status"],
    )
    op.create_index(
        "ix_market_data_bootstrap_checkpoint_retry",
        "market_data_bootstrap_checkpoints",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_data_bootstrap_checkpoint_retry",
        table_name="market_data_bootstrap_checkpoints",
    )
    op.drop_index(
        "ix_market_data_bootstrap_checkpoint_run_status",
        table_name="market_data_bootstrap_checkpoints",
    )
    op.drop_index(
        op.f("ix_market_data_bootstrap_checkpoints_run_id"),
        table_name="market_data_bootstrap_checkpoints",
    )
    op.drop_table("market_data_bootstrap_checkpoints")
    op.drop_index(
        "ix_market_data_bootstrap_runs_status_prepared", table_name="market_data_bootstrap_runs"
    )
    op.drop_table("market_data_bootstrap_runs")
