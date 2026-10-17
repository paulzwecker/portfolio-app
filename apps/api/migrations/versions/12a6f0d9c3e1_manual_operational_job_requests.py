"""persist manual operational refresh requests and attempts"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "12a6f0d9c3e1"
down_revision: str | Sequence[str] | None = "c19d4c30f6a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_job_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(length=40), nullable=False),
        sa.Column("scope_kind", sa.String(length=20), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("lifecycle", sa.String(length=16), nullable=True),
        sa.Column("requested_by", sa.String(length=32), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("retry_of_id", sa.Uuid(), nullable=True),
        sa.Column("affected_domains", sa.JSON(), nullable=False),
        sa.Column("scope_detail", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "job_name IN ('MARKET_DATA','FX','MARKET_AND_FX','SEC_FUNDAMENTALS','SEC_FILINGS',"
            "'SHEETS_DISCOVERY','RESEARCH_REFRESH','AGENT_WORK_FEED','COMPANY_REFRESH','REFRESH_ALL')",
            name=op.f("ck_operational_job_requests_job_name"),
        ),
        sa.CheckConstraint(
            "scope_kind IN ('ACTIVE_UNIVERSE','COMPANY')",
            name=op.f("ck_operational_job_requests_scope_kind"),
        ),
        sa.CheckConstraint(
            "(scope_kind = 'COMPANY' AND company_id IS NOT NULL) OR "
            "(scope_kind = 'ACTIVE_UNIVERSE' AND company_id IS NULL)",
            name=op.f("ck_operational_job_requests_scope_company"),
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','PARTIAL','BLOCKED','FAILED')",
            name=op.f("ck_operational_job_requests_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_operational_job_requests_attempt_count")
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["retry_of_id"], ["operational_job_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operational_job_requests")),
    )
    op.create_index(
        "ix_operational_job_requests_status_requested",
        "operational_job_requests",
        ["status", "requested_at"],
    )
    op.create_index(
        "ix_operational_job_requests_fingerprint_requested",
        "operational_job_requests",
        ["request_fingerprint", "requested_at"],
    )
    op.create_table(
        "operational_job_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("affected_domains", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "attempt_number > 0", name=op.f("ck_operational_job_attempts_attempt_number")
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','PARTIAL','BLOCKED','FAILED','SKIPPED','DEFERRED')",
            name=op.f("ck_operational_job_attempts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["operational_job_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operational_job_attempts")),
        sa.UniqueConstraint(
            "request_id", "attempt_number", "step_name", name="uq_operational_job_step_attempt"
        ),
    )
    op.create_index(
        "ix_operational_job_attempts_request_started",
        "operational_job_attempts",
        ["request_id", "started_at"],
    )
    op.create_index(
        "ix_operational_job_attempts_request_id", "operational_job_attempts", ["request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_operational_job_attempts_request_id", table_name="operational_job_attempts")
    op.drop_index(
        "ix_operational_job_attempts_request_started", table_name="operational_job_attempts"
    )
    op.drop_table("operational_job_attempts")
    op.drop_index(
        "ix_operational_job_requests_fingerprint_requested", table_name="operational_job_requests"
    )
    op.drop_index(
        "ix_operational_job_requests_status_requested", table_name="operational_job_requests"
    )
    op.drop_table("operational_job_requests")
