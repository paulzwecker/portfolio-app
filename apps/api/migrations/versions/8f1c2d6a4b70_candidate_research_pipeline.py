"""candidate research pipeline revisions and evidence

Revision ID: 8f1c2d6a4b70
Revises: a71b4c3d2e80
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f1c2d6a4b70"
down_revision: str | Sequence[str] | None = "a71b4c3d2e80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_pipeline_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("base_revision_id", sa.Uuid(), nullable=True),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("disposition", sa.String(length=16), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("author_id", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=1000), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0", name="ck_candidate_pipeline_revisions_revision_number"
        ),
        sa.CheckConstraint(
            "stage IN ('DISCOVERY','INITIAL_SCREEN','QUALITY_DURABILITY',"
            "'FUNDAMENTAL_COMPOUNDING','DEEP_DIVE','RESOLUTION')",
            name="ck_candidate_pipeline_revisions_stage",
        ),
        sa.CheckConstraint(
            "disposition IS NULL OR disposition IN ('WATCHLIST','INCUBATE','DROP')",
            name="ck_candidate_pipeline_revisions_disposition",
        ),
        sa.CheckConstraint(
            "disposition IS NULL OR stage = 'RESOLUTION'",
            name="ck_candidate_pipeline_revisions_disposition_requires_resolution",
        ),
        sa.CheckConstraint(
            "actor IN ('LOCAL_USER','SYSTEM','IMPORT')",
            name="ck_candidate_pipeline_revisions_actor",
        ),
        sa.CheckConstraint(
            "length(author_id) > 0", name="ck_candidate_pipeline_revisions_author_id"
        ),
        sa.CheckConstraint(
            "length(rationale) > 0", name="ck_candidate_pipeline_revisions_rationale"
        ),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64",
            name="ck_candidate_pipeline_revisions_content_fingerprint",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "base_revision_id"],
            ["candidate_pipeline_revisions.company_id", "candidate_pipeline_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "revision_number", name="uq_candidate_pipeline_revision"),
        sa.UniqueConstraint("company_id", "submission_id", name="uq_candidate_pipeline_submission"),
        sa.UniqueConstraint("company_id", "id", name="uq_candidate_pipeline_company_revision"),
    )
    op.create_index(
        "ix_candidate_pipeline_revisions_company_id",
        "candidate_pipeline_revisions",
        ["company_id"],
    )
    op.create_index(
        "ix_candidate_pipeline_revisions_company_recorded",
        "candidate_pipeline_revisions",
        ["company_id", "recorded_at"],
    )

    op.create_table(
        "candidate_pipeline_gate_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("gate", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("normalized_per_share_basis_confirmed", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "gate IN ('DISCOVERY','INITIAL_SCREEN','QUALITY_DURABILITY',"
            "'FUNDAMENTAL_COMPOUNDING','DEEP_DIVE')",
            name="ck_candidate_pipeline_gate_assessments_gate",
        ),
        sa.CheckConstraint(
            "outcome IN ('NOT_ASSESSED','INCOMPLETE','PASS','FAIL','DATA_CHECK')",
            name="ck_candidate_pipeline_gate_assessments_outcome",
        ),
        sa.CheckConstraint(
            "NOT normalized_per_share_basis_confirmed OR gate = 'FUNDAMENTAL_COMPOUNDING'",
            name="ck_candidate_pipeline_gate_assessments_per_share_basis_gate",
        ),
        sa.CheckConstraint(
            "outcome <> 'PASS' OR coalesce(length(rationale), 0) > 0",
            name="ck_candidate_pipeline_gate_assessments_pass_rationale",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["candidate_pipeline_revisions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "gate", name="uq_candidate_pipeline_revision_gate"),
    )
    op.create_index(
        "ix_candidate_pipeline_gate_assessments_revision_id",
        "candidate_pipeline_gate_assessments",
        ["revision_id"],
    )
    op.create_index(
        "ix_candidate_gate_revision",
        "candidate_pipeline_gate_assessments",
        ["revision_id", "gate"],
    )

    op.create_table(
        "candidate_pipeline_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gate_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("research_revision_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_revision_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_claim_id", sa.Uuid(), nullable=True),
        sa.Column("score_assessment_id", sa.Uuid(), nullable=True),
        sa.Column("financial_model_output_id", sa.Uuid(), nullable=True),
        sa.Column("model_output_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("relationship", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "evidence_type IN ('RESEARCH_REVISION','THESIS_REVISION','THESIS_CLAIM',"
            "'SCORE_ASSESSMENT','FINANCIAL_MODEL_OUTPUT','LEGACY_MODEL_OUTPUT',"
            "'SOURCE_DOCUMENT','SOURCE_URL')",
            name="ck_candidate_pipeline_evidence_evidence_type",
        ),
        sa.CheckConstraint(
            "num_nonnulls(research_revision_id, thesis_revision_id, thesis_claim_id, "
            "score_assessment_id, financial_model_output_id, model_output_snapshot_id, "
            "source_document_id, source_url) = 1",
            name="ck_candidate_pipeline_evidence_one_reference",
        ),
        sa.CheckConstraint(
            "(evidence_type = 'RESEARCH_REVISION' AND research_revision_id IS NOT NULL) OR "
            "(evidence_type = 'THESIS_REVISION' AND thesis_revision_id IS NOT NULL) OR "
            "(evidence_type = 'THESIS_CLAIM' AND thesis_claim_id IS NOT NULL) OR "
            "(evidence_type = 'SCORE_ASSESSMENT' AND score_assessment_id IS NOT NULL) OR "
            "(evidence_type = 'FINANCIAL_MODEL_OUTPUT' AND "
            "financial_model_output_id IS NOT NULL) OR "
            "(evidence_type = 'LEGACY_MODEL_OUTPUT' AND model_output_snapshot_id IS NOT NULL) OR "
            "(evidence_type = 'SOURCE_DOCUMENT' AND source_document_id IS NOT NULL) OR "
            "(evidence_type = 'SOURCE_URL' AND source_url IS NOT NULL)",
            name="ck_candidate_pipeline_evidence_evidence_identity",
        ),
        sa.CheckConstraint(
            "source_url IS NULL OR source_url LIKE 'https://%'",
            name="ck_candidate_pipeline_evidence_https_url",
        ),
        sa.CheckConstraint(
            "relationship IN ('SUPPORTS','CONTRADICTS','CONTEXT')",
            name="ck_candidate_pipeline_evidence_relationship",
        ),
        sa.ForeignKeyConstraint(
            ["gate_assessment_id"],
            ["candidate_pipeline_gate_assessments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["research_revision_id"], ["research_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["thesis_revision_id"], ["investment_thesis_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["thesis_claim_id"], ["investment_thesis_claims.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["score_assessment_id"], ["score_assessments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["financial_model_output_id"], ["financial_model_outputs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["model_output_snapshot_id"], ["model_output_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["source_documents.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_pipeline_evidence_gate_assessment_id",
        "candidate_pipeline_evidence",
        ["gate_assessment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_pipeline_evidence_gate_assessment_id",
        table_name="candidate_pipeline_evidence",
    )
    op.drop_table("candidate_pipeline_evidence")
    op.drop_index("ix_candidate_gate_revision", table_name="candidate_pipeline_gate_assessments")
    op.drop_index(
        "ix_candidate_pipeline_gate_assessments_revision_id",
        table_name="candidate_pipeline_gate_assessments",
    )
    op.drop_table("candidate_pipeline_gate_assessments")
    op.drop_index(
        "ix_candidate_pipeline_revisions_company_recorded",
        table_name="candidate_pipeline_revisions",
    )
    op.drop_index(
        "ix_candidate_pipeline_revisions_company_id", table_name="candidate_pipeline_revisions"
    )
    op.drop_table("candidate_pipeline_revisions")
