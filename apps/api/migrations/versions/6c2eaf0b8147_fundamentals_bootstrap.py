"""Add resumable SEC fundamentals and filing bootstrap runs.

Revision ID: 6c2eaf0b8147
Revises: 3f7c9d12b6a4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c2eaf0b8147"
down_revision: str | Sequence[str] | None = "3f7c9d12b6a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fundamentals_bootstrap_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("mapping_sha256", sa.String(length=64), nullable=False),
        sa.Column("bootstrap_version", sa.String(length=80), nullable=False),
        sa.Column("target_environment", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_provider_request_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "length(input_digest) = 64", name=op.f("ck_fundamentals_bootstrap_runs_input_digest")
        ),
        sa.CheckConstraint(
            "length(mapping_sha256) = 64",
            name=op.f("ck_fundamentals_bootstrap_runs_mapping_sha256"),
        ),
        sa.CheckConstraint(
            "target_environment IN ('development','rehearsal')",
            name=op.f("ck_fundamentals_bootstrap_runs_target_environment"),
        ),
        sa.CheckConstraint(
            "status IN ('PREPARED','RUNNING','PARTIAL','COMPLETE','FAILED','BLOCKED')",
            name=op.f("ck_fundamentals_bootstrap_runs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fundamentals_bootstrap_runs")),
    )
    op.create_index(
        "ix_fundamentals_bootstrap_run_status",
        "fundamentals_bootstrap_runs",
        ["status", "prepared_at"],
    )

    op.create_table(
        "fundamentals_bootstrap_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_identifier_id", sa.Uuid(), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("provider_request_count", sa.Integer(), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "stage IN ('SOURCE_DOCUMENTS','REPORTED_FUNDAMENTALS')",
            name=op.f("ck_fundamentals_bootstrap_checkpoints_stage"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETE','UNAVAILABLE','FAILED','BLOCKED')",
            name=op.f("ck_fundamentals_bootstrap_checkpoints_status"),
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3",
            name=op.f("ck_fundamentals_bootstrap_checkpoints_attempt_count"),
        ),
        sa.CheckConstraint(
            "sequence_number >= 0",
            name=op.f("ck_fundamentals_bootstrap_checkpoints_sequence_number"),
        ),
        sa.CheckConstraint(
            "page_count >= 0", name=op.f("ck_fundamentals_bootstrap_checkpoints_page_count")
        ),
        sa.CheckConstraint(
            "provider_request_count >= 0",
            name=op.f("ck_fundamentals_bootstrap_checkpoints_provider_request_count"),
        ),
        sa.CheckConstraint(
            "cik ~ '^[0-9]{10}$'", name=op.f("ck_fundamentals_bootstrap_checkpoints_cik")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["fundamentals_bootstrap_runs.id"],
            name=op.f("fk_fundamentals_bootstrap_checkpoints_run_id_fundamentals_bootstrap_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_fundamentals_bootstrap_checkpoints_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_identifier_id"],
            ["company_provider_identifiers.id"],
            name=op.f(
                "fk_fundamentals_bootstrap_checkpoints_mapping_identifier_id_"
                "company_provider_identifiers"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fundamentals_bootstrap_checkpoints")),
        sa.UniqueConstraint(
            "run_id", "stage", "company_id", name="uq_fundamentals_bootstrap_checkpoint"
        ),
        sa.UniqueConstraint("run_id", "sequence_number", name="uq_fundamentals_bootstrap_sequence"),
    )
    op.create_index(
        op.f("ix_fundamentals_bootstrap_checkpoints_run_id"),
        "fundamentals_bootstrap_checkpoints",
        ["run_id"],
    )
    op.create_index(
        "ix_fundamentals_bootstrap_checkpoint_run_status",
        "fundamentals_bootstrap_checkpoints",
        ["run_id", "status"],
    )
    op.create_index(
        "ix_fundamentals_bootstrap_checkpoint_retry",
        "fundamentals_bootstrap_checkpoints",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fundamentals_bootstrap_checkpoint_retry",
        table_name="fundamentals_bootstrap_checkpoints",
    )
    op.drop_index(
        "ix_fundamentals_bootstrap_checkpoint_run_status",
        table_name="fundamentals_bootstrap_checkpoints",
    )
    op.drop_index(
        op.f("ix_fundamentals_bootstrap_checkpoints_run_id"),
        table_name="fundamentals_bootstrap_checkpoints",
    )
    op.drop_table("fundamentals_bootstrap_checkpoints")
    op.drop_index("ix_fundamentals_bootstrap_run_status", table_name="fundamentals_bootstrap_runs")
    op.drop_table("fundamentals_bootstrap_runs")
