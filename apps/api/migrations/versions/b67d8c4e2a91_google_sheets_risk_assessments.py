"""Add reviewed, immutable Google Sheets risk assessments.

Revision ID: b67d8c4e2a91
Revises: 9f8c2d4a71b6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b67d8c4e2a91"
down_revision: str | Sequence[str] | None = "9f8c2d4a71b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_assessment_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("stream_key", sa.String(length=160), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(length=24), nullable=False),
        sa.Column("external_revision_id", sa.String(length=200), nullable=False),
        sa.Column("supersedes_revision_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.String(length=160), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_status_at_accept", sa.String(length=32), nullable=False),
        sa.Column("baseline_stale_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("portfolio_state_contract_version", sa.String(length=24), nullable=False),
        sa.Column("portfolio_state_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("holdings_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("target_revision_id", sa.Uuid(), nullable=True),
        sa.Column("valuation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage_status", sa.String(length=16), nullable=False),
        sa.Column("coverage_note", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0", name="ck_risk_assessment_revisions_revision_number"
        ),
        sa.CheckConstraint(
            "length(stream_key) > 0", name="ck_risk_assessment_revisions_stream_key"
        ),
        sa.CheckConstraint(
            "length(external_revision_id) > 0",
            name="ck_risk_assessment_revisions_external_revision_id",
        ),
        sa.CheckConstraint("length(author_id) > 0", name="ck_risk_assessment_revisions_author_id"),
        sa.CheckConstraint("length(source_id) > 0", name="ck_risk_assessment_revisions_source_id"),
        sa.CheckConstraint(
            "length(source_reference) > 0", name="ck_risk_assessment_revisions_source_reference"
        ),
        sa.CheckConstraint("length(reviewer) > 0", name="ck_risk_assessment_revisions_reviewer"),
        sa.CheckConstraint(
            "length(reviewer_note) > 0", name="ck_risk_assessment_revisions_reviewer_note"
        ),
        sa.CheckConstraint(
            "baseline_status_at_accept IN ('CURRENT','STALE_PORTFOLIO_STATE',"
            "'STALE_HOLDINGS','INCOMPLETE_VALUATION')",
            name="ck_risk_assessment_revisions_baseline_status",
        ),
        sa.CheckConstraint(
            "(baseline_status_at_accept = 'CURRENT' AND baseline_stale_acknowledged = false) OR "
            "(baseline_status_at_accept <> 'CURRENT' AND baseline_stale_acknowledged = true)",
            name="ck_risk_assessment_revisions_baseline_acknowledgement",
        ),
        sa.CheckConstraint(
            "coverage_status IN ('COMPLETE','PARTIAL')",
            name="ck_risk_assessment_revisions_coverage_status",
        ),
        sa.CheckConstraint(
            "coverage_status = 'COMPLETE' OR coverage_note IS NOT NULL",
            name="ck_risk_assessment_revisions_coverage_note",
        ),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64",
            name="ck_risk_assessment_revisions_content_fingerprint",
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_revision_id"], ["risk_assessment_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["holdings_snapshot_id"], ["holding_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_revision_id"], ["target_allocation_revisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "stream_key", "revision_number", name="uq_risk_stream_revision"
        ),
        sa.UniqueConstraint(
            "portfolio_id",
            "stream_key",
            "external_revision_id",
            name="uq_risk_stream_external_revision",
        ),
    )
    op.create_index(
        "ix_risk_assessment_revisions_portfolio_id", "risk_assessment_revisions", ["portfolio_id"]
    )
    op.create_index(
        "ix_risk_assessment_revisions_holdings_snapshot_id",
        "risk_assessment_revisions",
        ["holdings_snapshot_id"],
    )
    op.create_index(
        "ix_risk_revisions_portfolio_recorded",
        "risk_assessment_revisions",
        ["portfolio_id", "recorded_at"],
    )
    op.create_index(
        "ix_risk_revisions_portfolio_stream",
        "risk_assessment_revisions",
        ["portfolio_id", "stream_key", "revision_number"],
    )

    op.create_table(
        "risk_assessment_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("finding_key", sa.String(length=80), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("change_direction", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('COMPANY','PORTFOLIO')", name="ck_risk_assessment_findings_scope"
        ),
        sa.CheckConstraint(
            "(scope = 'COMPANY' AND company_id IS NOT NULL) OR scope = 'PORTFOLIO'",
            name="ck_risk_assessment_findings_company_scope",
        ),
        sa.CheckConstraint(
            "category IN ('BUSINESS','FINANCIAL','GEOGRAPHIC','CURRENCY','BUSINESS_MODEL',"
            "'REGULATORY','GOVERNANCE','GEOPOLITICAL','PORTFOLIO_CONCENTRATION',"
            "'PORTFOLIO_EXPOSURE','THESIS_CHANGE','OTHER')",
            name="ck_risk_assessment_findings_category",
        ),
        sa.CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_risk_assessment_findings_severity",
        ),
        sa.CheckConstraint(
            "confidence IN ('LOW','MEDIUM','HIGH','UNASSESSED')",
            name="ck_risk_assessment_findings_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','UNDER_REVIEW','RESOLVED')",
            name="ck_risk_assessment_findings_status",
        ),
        sa.CheckConstraint(
            "change_direction IN ('NEW','WORSENING','UNCHANGED','IMPROVING','RESOLVED')",
            name="ck_risk_assessment_findings_change_direction",
        ),
        sa.CheckConstraint(
            "length(finding_key) > 0", name="ck_risk_assessment_findings_finding_key"
        ),
        sa.CheckConstraint("length(title) > 0", name="ck_risk_assessment_findings_title"),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["risk_assessment_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "finding_key", name="uq_risk_finding_revision_key"),
    )
    op.create_index(
        "ix_risk_assessment_findings_revision_id", "risk_assessment_findings", ["revision_id"]
    )
    op.create_index(
        "ix_risk_assessment_findings_company_id", "risk_assessment_findings", ["company_id"]
    )
    op.create_index(
        "ix_risk_findings_company", "risk_assessment_findings", ["company_id", "revision_id"]
    )

    op.create_table(
        "risk_assessment_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("reported_fundamental_observation_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_revision_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_claim_id", sa.Uuid(), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("external_identifier", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(source_name) > 0", name="ck_risk_assessment_evidence_source_name"
        ),
        sa.CheckConstraint(
            "source_document_id IS NOT NULL OR reported_fundamental_observation_id IS NOT NULL "
            "OR thesis_revision_id IS NOT NULL OR thesis_claim_id IS NOT NULL "
            "OR (external_identifier IS NOT NULL AND length(external_identifier) > 0) "
            "OR (source_url IS NOT NULL AND length(source_url) > 0)",
            name="ck_risk_assessment_evidence_source_locator",
        ),
        sa.CheckConstraint(
            "source_url IS NULL OR source_url LIKE 'https://%'",
            name="ck_risk_assessment_evidence_https_url",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["risk_assessment_findings.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["source_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reported_fundamental_observation_id"],
            ["reported_fundamental_observations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thesis_revision_id"], ["investment_thesis_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["thesis_claim_id"], ["investment_thesis_claims.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_assessment_evidence_finding_id", "risk_assessment_evidence", ["finding_id"]
    )
    op.create_index(
        "ix_risk_assessment_evidence_source_document_id",
        "risk_assessment_evidence",
        ["source_document_id"],
    )

    op.create_table(
        "google_sheets_risk_sync_runs",
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
            name="ck_google_sheets_risk_sync_runs_status",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0 AND new_count >= 0 AND unchanged_count >= 0 AND issue_count >= 0",
            name="ck_google_sheets_risk_sync_runs_counts_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_google_sheets_risk_sync_runs_started", "google_sheets_risk_sync_runs", ["started_at"]
    )

    op.create_table(
        "google_sheets_risk_sync_candidates",
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
        sa.Column("portfolio_id", sa.Uuid(), nullable=True),
        sa.Column("stream_key", sa.String(length=160), nullable=True),
        sa.Column("external_revision_id", sa.String(length=200), nullable=True),
        sa.Column("author_id", sa.String(length=160), nullable=True),
        sa.Column("source_id", sa.String(length=160), nullable=True),
        sa.Column("source_reference", sa.String(length=1000), nullable=True),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("findings_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("issue", sa.Text(), nullable=True),
        sa.Column("baseline_status", sa.String(length=32), nullable=True),
        sa.Column("preview_data", sa.JSON(), nullable=True),
        sa.Column("reviewer", sa.String(length=160), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("accepted_revision_id", sa.Uuid(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','STALE_BASELINE','CONFLICT','INVALID',"
            "'ACCEPTED','REJECTED')",
            name="ck_google_sheets_risk_sync_candidates_status",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"], ["google_sheets_risk_sync_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["accepted_revision_id"], ["risk_assessment_revisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_google_sheets_risk_candidate_key"),
    )
    op.create_index(
        "ix_google_sheets_risk_sync_candidates_portfolio_id",
        "google_sheets_risk_sync_candidates",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_google_sheets_risk_candidates_status_observed",
        "google_sheets_risk_sync_candidates",
        ["status", "first_observed_at"],
    )
    op.create_index(
        "ix_google_sheets_risk_candidates_portfolio",
        "google_sheets_risk_sync_candidates",
        ["portfolio_id", "first_observed_at"],
    )


def downgrade() -> None:
    op.drop_table("google_sheets_risk_sync_candidates")
    op.drop_table("google_sheets_risk_sync_runs")
    op.drop_table("risk_assessment_evidence")
    op.drop_table("risk_assessment_findings")
    op.drop_table("risk_assessment_revisions")
