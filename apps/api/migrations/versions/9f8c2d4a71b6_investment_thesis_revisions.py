"""Add immutable, source-linked investment thesis revisions.

Revision ID: 9f8c2d4a71b6
Revises: 7f6b9d2a310c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f8c2d4a71b6"
down_revision: str | Sequence[str] | None = "7f6b9d2a310c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investment_thesis_revisions",
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
        sa.Column("thesis_statement", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0", name="ck_investment_thesis_revisions_revision_number"
        ),
        sa.CheckConstraint(
            "length(stream_key) > 0", name="ck_investment_thesis_revisions_stream_key"
        ),
        sa.CheckConstraint(
            "length(external_revision_id) > 0",
            name="ck_investment_thesis_revisions_external_revision_id",
        ),
        sa.CheckConstraint(
            "length(author_id) > 0", name="ck_investment_thesis_revisions_author_id"
        ),
        sa.CheckConstraint(
            "length(source_id) > 0", name="ck_investment_thesis_revisions_source_id"
        ),
        sa.CheckConstraint(
            "length(source_reference) > 0",
            name="ck_investment_thesis_revisions_source_reference",
        ),
        sa.CheckConstraint(
            "length(rationale) > 0", name="ck_investment_thesis_revisions_rationale"
        ),
        sa.CheckConstraint(
            "status IN ('PUBLISHED','WITHDRAWN')",
            name="ck_investment_thesis_revisions_status",
        ),
        sa.CheckConstraint(
            "confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')",
            name="ck_investment_thesis_revisions_confidence",
        ),
        sa.CheckConstraint(
            "(status = 'PUBLISHED' AND thesis_statement IS NOT NULL) OR "
            "(status = 'WITHDRAWN' AND thesis_statement IS NULL)",
            name="ck_investment_thesis_revisions_thesis_status",
        ),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64",
            name="ck_investment_thesis_revisions_content_fingerprint",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_revision_id"],
            ["investment_thesis_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "stream_key", "revision_number", name="uq_thesis_stream_revision"
        ),
        sa.UniqueConstraint(
            "company_id",
            "stream_key",
            "external_revision_id",
            name="uq_thesis_stream_external_revision",
        ),
    )
    op.create_index(
        "ix_investment_thesis_revisions_company_id",
        "investment_thesis_revisions",
        ["company_id"],
    )
    op.create_index(
        "ix_investment_thesis_revisions_security_id",
        "investment_thesis_revisions",
        ["security_id"],
    )
    op.create_index(
        "ix_thesis_revisions_company_observed",
        "investment_thesis_revisions",
        ["company_id", "observed_at"],
    )
    op.create_index(
        "ix_thesis_revisions_company_stream",
        "investment_thesis_revisions",
        ["company_id", "stream_key", "revision_number"],
    )

    op.create_table(
        "investment_thesis_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("claim_key", sa.String(length=80), nullable=False),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.CheckConstraint("length(claim_key) > 0", name="ck_investment_thesis_claims_claim_key"),
        sa.CheckConstraint(
            "claim_type IN ('COMPETITIVE_ADVANTAGE','DURABILITY','GROWTH_DRIVER',"
            "'PRINCIPAL_RISK','THESIS_BREAKER','CATALYST','IMPORTANT_DEVELOPMENT',"
            "'UNRESOLVED_QUESTION')",
            name="ck_investment_thesis_claims_claim_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','UNDER_REVIEW','RESOLVED','INVALIDATED')",
            name="ck_investment_thesis_claims_status",
        ),
        sa.CheckConstraint("length(statement) > 0", name="ck_investment_thesis_claims_statement"),
        sa.CheckConstraint(
            "confidence IN ('HIGH','MEDIUM','LOW','UNASSESSED')",
            name="ck_investment_thesis_claims_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["investment_thesis_revisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "claim_key", name="uq_thesis_claim_revision_key"),
    )
    op.create_index(
        "ix_investment_thesis_claims_revision_id", "investment_thesis_claims", ["revision_id"]
    )
    op.create_index(
        "ix_thesis_claims_revision_type",
        "investment_thesis_claims",
        ["revision_id", "claim_type"],
    )

    op.create_table(
        "investment_thesis_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.String(length=16), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("reported_fundamental_observation_id", sa.Uuid(), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("external_identifier", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "relationship IN ('SUPPORTS','CONTRADICTS','CONTEXT')",
            name="ck_investment_thesis_evidence_relationship",
        ),
        sa.CheckConstraint(
            "length(source_name) > 0", name="ck_investment_thesis_evidence_source_name"
        ),
        sa.CheckConstraint(
            "source_document_id IS NOT NULL OR reported_fundamental_observation_id IS NOT NULL OR "
            "(external_identifier IS NOT NULL AND length(external_identifier) > 0) OR "
            "(source_url IS NOT NULL AND length(source_url) > 0)",
            name="ck_investment_thesis_evidence_source_locator",
        ),
        sa.CheckConstraint(
            "source_url IS NULL OR source_url LIKE 'https://%'",
            name="ck_investment_thesis_evidence_https_url",
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["investment_thesis_claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["source_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reported_fundamental_observation_id"],
            ["reported_fundamental_observations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investment_thesis_evidence_claim_id", "investment_thesis_evidence", ["claim_id"]
    )
    op.create_index(
        "ix_thesis_evidence_document", "investment_thesis_evidence", ["source_document_id"]
    )
    op.create_index(
        "ix_thesis_evidence_fundamental",
        "investment_thesis_evidence",
        ["reported_fundamental_observation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_thesis_evidence_fundamental", table_name="investment_thesis_evidence")
    op.drop_index("ix_thesis_evidence_document", table_name="investment_thesis_evidence")
    op.drop_index("ix_investment_thesis_evidence_claim_id", table_name="investment_thesis_evidence")
    op.drop_table("investment_thesis_evidence")
    op.drop_index("ix_thesis_claims_revision_type", table_name="investment_thesis_claims")
    op.drop_index("ix_investment_thesis_claims_revision_id", table_name="investment_thesis_claims")
    op.drop_table("investment_thesis_claims")
    op.drop_index("ix_thesis_revisions_company_stream", table_name="investment_thesis_revisions")
    op.drop_index("ix_thesis_revisions_company_observed", table_name="investment_thesis_revisions")
    op.drop_index(
        "ix_investment_thesis_revisions_security_id", table_name="investment_thesis_revisions"
    )
    op.drop_index(
        "ix_investment_thesis_revisions_company_id", table_name="investment_thesis_revisions"
    )
    op.drop_table("investment_thesis_revisions")
