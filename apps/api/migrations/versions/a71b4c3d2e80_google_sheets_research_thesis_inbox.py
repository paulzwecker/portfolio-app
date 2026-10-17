"""Capture and review Google Sheets research and thesis publications.

Revision ID: a71b4c3d2e80
Revises: f04e7a91c63b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a71b4c3d2e80"
down_revision: str | Sequence[str] | None = "f04e7a91c63b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_sheets_research_sync_runs",
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
            "status IN ('SUCCEEDED','PARTIAL','BLOCKED','FAILED')",
            name="ck_google_sheets_research_sync_runs_status",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0 AND new_count >= 0 AND unchanged_count >= 0 AND issue_count >= 0",
            name="ck_google_sheets_research_sync_runs_counts_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_google_sheets_research_sync_runs"),
    )
    op.create_index(
        "ix_google_sheets_research_sync_runs_started",
        "google_sheets_research_sync_runs",
        ["started_at"],
    )

    op.create_table(
        "google_sheets_research_sync_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=16), nullable=False),
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
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("security_id", sa.Uuid(), nullable=True),
        sa.Column("stream_key", sa.String(length=240), nullable=True),
        sa.Column("external_revision_id", sa.String(length=200), nullable=True),
        sa.Column("base_revision_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.String(length=160), nullable=True),
        sa.Column("source_id", sa.String(length=160), nullable=True),
        sa.Column("source_reference", sa.String(length=1000), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("issue", sa.Text(), nullable=True),
        sa.Column("preview_data", sa.JSON(), nullable=True),
        sa.Column("accepted_research_revision_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_thesis_revision_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer", sa.String(length=160), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "domain IN ('RESEARCH','THESIS')",
            name="ck_google_sheets_research_candidate_domain",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','CONFLICT','INVALID','ACCEPTED','REJECTED')",
            name="ck_google_sheets_research_candidate_status",
        ),
        sa.CheckConstraint(
            "item_count >= 0 AND evidence_count >= 0",
            name="ck_google_sheets_research_candidate_counts",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["google_sheets_research_sync_runs.id"],
            ondelete="SET NULL",
            name="fk_google_sheets_research_candidate_run",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_research_revision_id"], ["research_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["accepted_thesis_revision_id"],
            ["investment_thesis_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_google_sheets_research_sync_candidates"),
        sa.UniqueConstraint("idempotency_key", name="uq_google_sheets_research_candidate_key"),
    )
    op.create_index(
        "ix_google_sheets_research_candidates_status_observed",
        "google_sheets_research_sync_candidates",
        ["status", "first_observed_at"],
    )
    op.create_index(
        "ix_google_sheets_research_candidates_company_observed",
        "google_sheets_research_sync_candidates",
        ["company_id", "first_observed_at"],
    )
    op.create_index(
        "ix_google_sheets_research_sync_candidates_company_id",
        "google_sheets_research_sync_candidates",
        ["company_id"],
    )
    op.create_index(
        "ix_google_sheets_research_sync_candidates_security_id",
        "google_sheets_research_sync_candidates",
        ["security_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_google_sheets_research_sync_candidates_security_id",
        table_name="google_sheets_research_sync_candidates",
    )
    op.drop_index(
        "ix_google_sheets_research_sync_candidates_company_id",
        table_name="google_sheets_research_sync_candidates",
    )
    op.drop_index(
        "ix_google_sheets_research_candidates_company_observed",
        table_name="google_sheets_research_sync_candidates",
    )
    op.drop_index(
        "ix_google_sheets_research_candidates_status_observed",
        table_name="google_sheets_research_sync_candidates",
    )
    op.drop_table("google_sheets_research_sync_candidates")
    op.drop_index(
        "ix_google_sheets_research_sync_runs_started",
        table_name="google_sheets_research_sync_runs",
    )
    op.drop_table("google_sheets_research_sync_runs")
