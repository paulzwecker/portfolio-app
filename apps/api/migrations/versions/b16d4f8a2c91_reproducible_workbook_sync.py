"""Persist frozen workbook artifacts and reviewed sync outcomes.

Revision ID: b16d4f8a2c91
Revises: 6c2eaf0b8147
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b16d4f8a2c91"
down_revision: str | Sequence[str] | None = "6c2eaf0b8147"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_operational_job_requests_job_name"),
        "operational_job_requests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_operational_job_requests_job_name"),
        "operational_job_requests",
        "job_name IN ('MARKET_DATA','FX','MARKET_AND_FX','SEC_FUNDAMENTALS','SEC_FILINGS',"
        "'SHEETS_DISCOVERY','WORKBOOK_SYNC','RESEARCH_REFRESH','DECISION_RECOMPUTE',"
        "'AGENT_WORK_FEED',"
        "'COMPANY_REFRESH','REFRESH_ALL')",
    )
    op.create_table(
        "workbook_sync_artifacts",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(sha256) = 64", name=op.f("ck_workbook_sync_artifacts_sha256")),
        sa.CheckConstraint(
            "byte_length > 0 AND byte_length <= 33554432",
            name=op.f("ck_workbook_sync_artifacts_byte_length"),
        ),
        sa.PrimaryKeyConstraint("sha256", name="pk_workbook_sync_artifacts"),
    )
    op.create_table(
        "workbook_sync_schema_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_identity_sha256", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.String(length=24), nullable=False),
        sa.Column("contract_version", sa.String(length=80), nullable=False),
        sa.Column("schema_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("header_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("rationale", sa.String(length=1000), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(source_identity_sha256) = 64",
            name=op.f("ck_workbook_sync_schema_approvals_source_identity_sha256"),
        ),
        sa.CheckConstraint(
            "length(artifact_sha256) = 64",
            name=op.f("ck_workbook_sync_schema_approvals_artifact_sha256"),
        ),
        sa.CheckConstraint(
            "profile = 'portfolio'", name=op.f("ck_workbook_sync_schema_approvals_profile")
        ),
        sa.ForeignKeyConstraint(
            ["artifact_sha256"],
            ["workbook_sync_artifacts.sha256"],
            name=op.f("fk_workbook_sync_schema_approvals_artifact_sha256"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workbook_sync_schema_approvals"),
        sa.UniqueConstraint(
            "source_identity_sha256",
            "profile",
            "contract_version",
            "schema_fingerprint",
            "header_fingerprint",
            name="uq_workbook_sync_schema_approval_identity",
        ),
    )
    op.create_table(
        "workbook_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("source_identity_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_revision_id", sa.String(length=160), nullable=True),
        sa.Column("source_revision_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_checksum", sa.String(length=128), nullable=True),
        sa.Column("source_mime_type", sa.String(length=160), nullable=True),
        sa.Column("profile", sa.String(length=24), nullable=False),
        sa.Column("contract_version", sa.String(length=80), nullable=False),
        sa.Column("schema_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("header_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("projection_sha256", sa.String(length=64), nullable=True),
        sa.Column("import_plan_sha256", sa.String(length=64), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("source_projection", sa.JSON(), nullable=False),
        sa.Column("preview_report", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("reviewer", sa.String(length=160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(idempotency_key) = 64", name=op.f("ck_workbook_sync_runs_idempotency_key")
        ),
        sa.CheckConstraint(
            "length(source_identity_sha256) = 64",
            name=op.f("ck_workbook_sync_runs_source_identity_sha256"),
        ),
        sa.CheckConstraint(
            "length(source_revision_sha256) = 64",
            name=op.f("ck_workbook_sync_runs_source_revision_sha256"),
        ),
        sa.CheckConstraint(
            "artifact_sha256 IS NULL OR length(artifact_sha256) = 64",
            name=op.f("ck_workbook_sync_runs_artifact_sha256"),
        ),
        sa.CheckConstraint("profile = 'portfolio'", name=op.f("ck_workbook_sync_runs_profile")),
        sa.CheckConstraint(
            "status IN ('SCHEMA_REVIEW_REQUIRED','PREVIEWED','NO_CHANGES','BLOCKED',"
            "'APPLIED','FAILED')",
            name=op.f("ck_workbook_sync_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["artifact_sha256"],
            ["workbook_sync_artifacts.sha256"],
            name=op.f("fk_workbook_sync_runs_artifact_sha256"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["operational_job_requests.id"],
            name=op.f("fk_workbook_sync_runs_request_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workbook_sync_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_workbook_sync_run_idempotency_key"),
    )
    op.create_index("ix_workbook_sync_runs_recorded", "workbook_sync_runs", ["recorded_at"])
    op.create_index(
        "ix_workbook_sync_runs_status_recorded",
        "workbook_sync_runs",
        ["status", "recorded_at"],
    )
    op.create_table(
        "workbook_sync_previews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("target_state_sha256", sa.String(length=64), nullable=False),
        sa.Column("projection_sha256", sa.String(length=64), nullable=False),
        sa.Column("import_plan_sha256", sa.String(length=64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint("sequence > 0", name=op.f("ck_workbook_sync_previews_sequence")),
        sa.CheckConstraint(
            "status IN ('PREVIEWED','NO_CHANGES','BLOCKED')",
            name=op.f("ck_workbook_sync_previews_status"),
        ),
        sa.CheckConstraint(
            "length(target_state_sha256) = 64",
            name=op.f("ck_workbook_sync_previews_target_state_sha256"),
        ),
        sa.CheckConstraint(
            "length(projection_sha256) = 64",
            name=op.f("ck_workbook_sync_previews_projection_sha256"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workbook_sync_runs.id"],
            name=op.f("fk_workbook_sync_previews_run_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workbook_sync_previews"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_workbook_sync_previews_run_sequence"),
    )
    op.create_index(
        "ix_workbook_sync_previews_run_recorded",
        "workbook_sync_previews",
        ["run_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workbook_sync_previews_run_recorded", table_name="workbook_sync_previews")
    op.drop_table("workbook_sync_previews")
    op.drop_index("ix_workbook_sync_runs_status_recorded", table_name="workbook_sync_runs")
    op.drop_index("ix_workbook_sync_runs_recorded", table_name="workbook_sync_runs")
    op.drop_table("workbook_sync_runs")
    op.drop_table("workbook_sync_schema_approvals")
    op.drop_table("workbook_sync_artifacts")
    op.drop_constraint(
        op.f("ck_operational_job_requests_job_name"),
        "operational_job_requests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_operational_job_requests_job_name"),
        "operational_job_requests",
        "job_name IN ('MARKET_DATA','FX','MARKET_AND_FX','SEC_FUNDAMENTALS','SEC_FILINGS',"
        "'SHEETS_DISCOVERY','RESEARCH_REFRESH','AGENT_WORK_FEED','COMPANY_REFRESH','REFRESH_ALL')",
    )
