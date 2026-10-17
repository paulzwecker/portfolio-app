"""Capture Google Sheets model-contract candidates for review.

Revision ID: c42e8f12b591
Revises: 9f17b83c4a21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c42e8f12b591"
down_revision: str | Sequence[str] | None = "9f17b83c4a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_sheets_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("spreadsheet_id", sa.String(length=128), nullable=True),
        sa.Column("spreadsheet_title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("new_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('CONNECTED','SUCCEEDED','PARTIAL','BLOCKED','FAILED')",
            name="ck_google_sheets_sync_runs_status",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0 AND new_count >= 0 AND unchanged_count >= 0 AND issue_count >= 0",
            name="ck_google_sheets_sync_runs_counts_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_google_sheets_sync_runs"),
    )
    op.create_index(
        "ix_google_sheets_sync_runs_started",
        "google_sheets_sync_runs",
        ["started_at"],
    )

    op.create_table(
        "google_sheets_sync_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("spreadsheet_id", sa.String(length=128), nullable=False),
        sa.Column("spreadsheet_title", sa.String(length=255), nullable=False),
        sa.Column("sheet_id", sa.Integer(), nullable=False),
        sa.Column("sheet_title", sa.String(length=100), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_seen_run_id", sa.Uuid(), nullable=True),
        sa.Column("contract_text", sa.Text(), nullable=False),
        sa.Column("contract_data", sa.JSON(), nullable=True),
        sa.Column("contract_version", sa.String(length=24), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=False),
        sa.Column("external_revision_id", sa.String(length=160), nullable=True),
        sa.Column("base_revision_id", sa.Uuid(), nullable=True),
        sa.Column("model_id", sa.Uuid(), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("valuation_listing_id", sa.Uuid(), nullable=True),
        sa.Column("model_type", sa.String(length=60), nullable=True),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("source_model_key", sa.String(length=120), nullable=True),
        sa.Column("model_currency", sa.String(length=3), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("issue", sa.Text(), nullable=True),
        sa.Column("preview_status", sa.String(length=40), nullable=True),
        sa.Column("preview_data", sa.JSON(), nullable=True),
        sa.Column("preview_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_revision_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer", sa.String(length=160), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','CONFLICT','INVALID','NO_CHANGES','ACCEPTED','REJECTED')",
            name="ck_google_sheets_sync_candidates_status",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["google_sheets_sync_runs.id"],
            name="fk_sheets_candidate_run",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_google_sheets_sync_candidates"),
        sa.UniqueConstraint("idempotency_key", name="uq_google_sheets_candidate_key"),
    )
    op.create_index(
        "ix_google_sheets_candidates_status_observed",
        "google_sheets_sync_candidates",
        ["status", "first_observed_at"],
    )
    op.create_index(
        "ix_google_sheets_candidates_model",
        "google_sheets_sync_candidates",
        ["model_id", "first_observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_google_sheets_candidates_model", table_name="google_sheets_sync_candidates")
    op.drop_index(
        "ix_google_sheets_candidates_status_observed",
        table_name="google_sheets_sync_candidates",
    )
    op.drop_table("google_sheets_sync_candidates")
    op.drop_index("ix_google_sheets_sync_runs_started", table_name="google_sheets_sync_runs")
    op.drop_table("google_sheets_sync_runs")
