"""persist recurring data and research operation status"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c19d4c30f6a2"
down_revision: str | Sequence[str] | None = "b3a6e91d5c20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recurring_operation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.String(length=2000), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "job_name IN ('SEC_FUNDAMENTALS','SEC_FILINGS','FMP_CONSENSUS','SHEETS_DISCOVERY',"
            "'RESEARCH_TRIGGER_SCAN','AGENT_WORK_FEED','DECISION_RECOMPUTE')",
            name=op.f("ck_recurring_operation_runs_job_name"),
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','PARTIAL','BLOCKED','FAILED','SKIPPED')",
            name=op.f("ck_recurring_operation_runs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_operation_runs")),
    )
    op.create_index(
        "ix_recurring_operation_runs_job_started",
        "recurring_operation_runs",
        ["job_name", "started_at"],
    )

    op.create_table(
        "recurring_operations_worker_state",
        sa.Column("worker_key", sa.String(length=16), nullable=False),
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("process_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "worker_key = 'primary'",
            name=op.f("ck_recurring_operations_worker_state_primary_worker"),
        ),
        sa.CheckConstraint(
            "status IN ('STARTING','RUNNING','STOPPED','FAILED')",
            name=op.f("ck_recurring_operations_worker_state_status"),
        ),
        sa.PrimaryKeyConstraint("worker_key", name=op.f("pk_recurring_operations_worker_state")),
    )


def downgrade() -> None:
    op.drop_table("recurring_operations_worker_state")
    op.drop_index("ix_recurring_operation_runs_job_started", table_name="recurring_operation_runs")
    op.drop_table("recurring_operation_runs")
