"""Persist provider/domain ingestion runs and bounded attempt outcomes.

Revision ID: 6e6c2d4e8a19
Revises: 8f96876cc9e9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e6c2d4e8a19"
down_revision: str | Sequence[str] | None = "8f96876cc9e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=120), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("replay_of_run_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=2000), nullable=True),
        sa.Column("request_scope", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "domain IN ('MARKET_DATA','FX','CORPORATE_ACTIONS','REPORTED_FUNDAMENTALS',"
            "'CONSENSUS_ESTIMATES','SOURCE_DOCUMENTS')",
            name=op.f("ck_external_ingestion_runs_domain"),
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','COMPLETE','PARTIAL','FAILED','BLOCKED','NOT_APPLICABLE')",
            name=op.f("ck_external_ingestion_runs_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 3",
            name=op.f("ck_external_ingestion_runs_attempts"),
        ),
        sa.ForeignKeyConstraint(
            ["replay_of_run_id"],
            ["external_ingestion_runs.id"],
            name=op.f("fk_external_ingestion_runs_replay_of_run_id_external_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_ingestion_runs")),
        sa.UniqueConstraint("idempotency_key", name="uq_external_ingestion_run_idempotency"),
    )
    op.create_index(
        "ix_external_ingestion_run_provider_domain_created",
        "external_ingestion_runs",
        ["provider_id", "domain", "created_at"],
    )
    op.create_index(
        "ix_external_ingestion_run_status_created",
        "external_ingestion_runs",
        ["status", "created_at"],
    )
    op.create_index(
        op.f("ix_external_ingestion_runs_replay_of_run_id"),
        "external_ingestion_runs",
        ["replay_of_run_id"],
    )

    op.create_table(
        "external_ingestion_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=2000), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "attempt_number > 0",
            name=op.f("ck_external_ingestion_attempts_attempt_number"),
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED','PARTIAL','FAILED','BLOCKED','NOT_APPLICABLE')",
            name=op.f("ck_external_ingestion_attempts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["external_ingestion_runs.id"],
            name=op.f("fk_external_ingestion_attempts_run_id_external_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_ingestion_attempts")),
        sa.UniqueConstraint(
            "run_id", "attempt_number", name="uq_external_ingestion_attempt_number"
        ),
    )
    op.create_index(
        op.f("ix_external_ingestion_attempts_run_id"),
        "external_ingestion_attempts",
        ["run_id"],
    )
    op.create_index(
        "ix_external_ingestion_attempt_run_finished",
        "external_ingestion_attempts",
        ["run_id", "finished_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_ingestion_attempt_run_finished", table_name="external_ingestion_attempts"
    )
    op.drop_index(
        op.f("ix_external_ingestion_attempts_run_id"), table_name="external_ingestion_attempts"
    )
    op.drop_table("external_ingestion_attempts")
    op.drop_index(
        op.f("ix_external_ingestion_runs_replay_of_run_id"), table_name="external_ingestion_runs"
    )
    op.drop_index("ix_external_ingestion_run_status_created", table_name="external_ingestion_runs")
    op.drop_index(
        "ix_external_ingestion_run_provider_domain_created", table_name="external_ingestion_runs"
    )
    op.drop_table("external_ingestion_runs")
