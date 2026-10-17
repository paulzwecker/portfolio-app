"""canonical research revisions, forecasts, assessments and evidence

Revision ID: 7f6b9d2a310c
Revises: d6f9a2c83170
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f6b9d2a310c"
down_revision: str | Sequence[str] | None = "d6f9a2c83170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=True),
        sa.Column("stream_key", sa.String(length=240), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(length=24), nullable=False),
        sa.Column("external_revision_id", sa.String(length=200), nullable=False),
        sa.Column("supersedes_revision_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.String(length=160), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint("revision_number > 0", name="ck_research_revisions_revision_number"),
        sa.CheckConstraint("length(stream_key) > 0", name="ck_research_revisions_stream_key"),
        sa.CheckConstraint(
            "length(external_revision_id) > 0",
            name="ck_research_revisions_external_revision_id",
        ),
        sa.CheckConstraint("length(author_id) > 0", name="ck_research_revisions_author_id"),
        sa.CheckConstraint("length(source_id) > 0", name="ck_research_revisions_source_id"),
        sa.CheckConstraint(
            "length(source_reference) > 0", name="ck_research_revisions_source_reference"
        ),
        sa.CheckConstraint("length(rationale) > 0", name="ck_research_revisions_rationale"),
        sa.CheckConstraint(
            "status IN ('PUBLISHED','WITHDRAWN')", name="ck_research_revisions_status"
        ),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64", name="ck_research_revisions_content_fingerprint"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_revision_id"], ["research_revisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "stream_key", "revision_number", name="uq_research_stream_revision"
        ),
        sa.UniqueConstraint(
            "company_id",
            "stream_key",
            "external_revision_id",
            name="uq_research_stream_external_revision",
        ),
    )
    op.create_index("ix_research_revisions_company_id", "research_revisions", ["company_id"])
    op.create_index("ix_research_revisions_security_id", "research_revisions", ["security_id"])
    op.create_index(
        "ix_research_revisions_company_observed",
        "research_revisions",
        ["company_id", "observed_at"],
    )
    op.create_index(
        "ix_research_revisions_company_stream",
        "research_revisions",
        ["company_id", "stream_key", "revision_number"],
    )

    op.create_table(
        "research_forecasts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=8), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("scenario", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("availability_status", sa.String(length=16), nullable=False),
        sa.Column("availability_reason", sa.String(length=1000), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "metric IN ('REVENUE','EPS','EBIT','EBITDA','FREE_CASH_FLOW','DILUTED_SHARES')",
            name="ck_research_forecasts_metric",
        ),
        sa.CheckConstraint(
            "period_type IN ('ANNUAL','QUARTERLY')", name="ck_research_forecasts_period_type"
        ),
        sa.CheckConstraint(
            "(period_type = 'ANNUAL' AND fiscal_period = 'FY') OR "
            "(period_type = 'QUARTERLY' AND fiscal_period IN ('Q1','Q2','Q3','Q4'))",
            name="ck_research_forecasts_fiscal_period",
        ),
        sa.CheckConstraint(
            "fiscal_year BETWEEN 1800 AND 2200", name="ck_research_forecasts_fiscal_year"
        ),
        sa.CheckConstraint(
            "scenario IN ('POINT','BEAR','BASE','BULL')", name="ck_research_forecasts_scenario"
        ),
        sa.CheckConstraint(
            "availability_status IN ('AVAILABLE','UNAVAILABLE','DATA_CHECK')",
            name="ck_research_forecasts_availability_status",
        ),
        sa.CheckConstraint(
            "(availability_status = 'AVAILABLE' AND value IS NOT NULL) OR "
            "(availability_status = 'UNAVAILABLE' AND value IS NULL) OR "
            "availability_status = 'DATA_CHECK'",
            name="ck_research_forecasts_availability_value",
        ),
        sa.CheckConstraint(
            "(availability_status = 'AVAILABLE' AND availability_reason IS NULL) OR "
            "(availability_status <> 'AVAILABLE' AND "
            "coalesce(length(availability_reason), 0) > 0)",
            name="ck_research_forecasts_availability_reason",
        ),
        sa.CheckConstraint(
            "(metric = 'DILUTED_SHARES' AND currency IS NULL AND unit = 'shares') OR "
            "(metric = 'EPS' AND currency IS NOT NULL AND unit = 'currency/share') OR "
            "(metric IN ('REVENUE','EBIT','EBITDA','FREE_CASH_FLOW') AND "
            "currency IS NOT NULL AND unit = 'currency')",
            name="ck_research_forecasts_metric_unit_currency",
        ),
        sa.CheckConstraint(
            "value IS NULL OR metric NOT IN ('REVENUE','DILUTED_SHARES') OR value >= 0",
            name="ck_research_forecasts_nonnegative_metric",
        ),
        sa.CheckConstraint(
            "confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')",
            name="ck_research_forecasts_confidence",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["research_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_id",
            "metric",
            "fiscal_year",
            "fiscal_period",
            "scenario",
            name="uq_research_forecast_period_scenario",
        ),
    )
    op.create_index("ix_research_forecasts_revision_id", "research_forecasts", ["revision_id"])
    op.create_index(
        "ix_research_forecasts_revision",
        "research_forecasts",
        ["revision_id", "metric", "fiscal_year"],
    )

    op.create_table(
        "research_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("status_reason", sa.String(length=1000), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "assessment_type IN ('BUSINESS_OUTLOOK','COMPETITIVE_POSITION','KEY_RISKS')",
            name="ck_research_assessments_assessment_type",
        ),
        sa.CheckConstraint(
            "status IN ('AVAILABLE','UNAVAILABLE','DATA_CHECK')",
            name="ck_research_assessments_status",
        ),
        sa.CheckConstraint(
            "(status = 'AVAILABLE' AND narrative IS NOT NULL) OR "
            "(status = 'UNAVAILABLE' AND narrative IS NULL) OR status = 'DATA_CHECK'",
            name="ck_research_assessments_narrative_status",
        ),
        sa.CheckConstraint(
            "(status = 'AVAILABLE' AND status_reason IS NULL) OR "
            "(status <> 'AVAILABLE' AND coalesce(length(status_reason), 0) > 0)",
            name="ck_research_assessments_status_reason",
        ),
        sa.CheckConstraint(
            "confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')",
            name="ck_research_assessments_confidence",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["research_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "assessment_type", name="uq_research_assessment_type"),
    )
    op.create_index("ix_research_assessments_revision_id", "research_assessments", ["revision_id"])

    op.create_table(
        "research_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("external_identifier", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("length(source_name) > 0", name="ck_research_evidence_source_name"),
        sa.CheckConstraint(
            "source_document_id IS NOT NULL OR "
            "(external_identifier IS NOT NULL AND length(external_identifier) > 0) OR "
            "(source_url IS NOT NULL AND length(source_url) > 0)",
            name="ck_research_evidence_source_locator",
        ),
        sa.CheckConstraint(
            "source_url IS NULL OR source_url LIKE 'https://%'",
            name="ck_research_evidence_https_url",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["research_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["source_documents.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_evidence_revision_id", "research_evidence", ["revision_id"])
    op.create_index(
        "ix_research_evidence_source_document_id", "research_evidence", ["source_document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_research_evidence_source_document_id", table_name="research_evidence")
    op.drop_index("ix_research_evidence_revision_id", table_name="research_evidence")
    op.drop_table("research_evidence")
    op.drop_index("ix_research_assessments_revision_id", table_name="research_assessments")
    op.drop_table("research_assessments")
    op.drop_index("ix_research_forecasts_revision", table_name="research_forecasts")
    op.drop_index("ix_research_forecasts_revision_id", table_name="research_forecasts")
    op.drop_table("research_forecasts")
    op.drop_index("ix_research_revisions_company_stream", table_name="research_revisions")
    op.drop_index("ix_research_revisions_company_observed", table_name="research_revisions")
    op.drop_index("ix_research_revisions_security_id", table_name="research_revisions")
    op.drop_index("ix_research_revisions_company_id", table_name="research_revisions")
    op.drop_table("research_revisions")
