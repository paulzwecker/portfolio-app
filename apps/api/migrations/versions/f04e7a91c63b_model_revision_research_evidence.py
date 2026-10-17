"""Link accepted model revisions to canonical research and thesis evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f04e7a91c63b"
down_revision: str | None = "b67d8c4e2a91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "financial_model_revisions",
        sa.Column("proposal_author_id", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "financial_model_revisions",
        sa.Column("proposal_authored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "financial_model_revisions",
        sa.Column("proposal_source_reference", sa.String(length=1000), nullable=True),
    )
    op.create_table(
        "financial_model_revision_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("research_revision_id", sa.Uuid(), nullable=True),
        sa.Column("research_forecast_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_revision_id", sa.Uuid(), nullable=True),
        sa.Column("thesis_claim_id", sa.Uuid(), nullable=True),
        sa.Column("relationship", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "evidence_type IN ('RESEARCH_REVISION','RESEARCH_FORECAST',"
            "'THESIS_REVISION','THESIS_CLAIM')",
            name=op.f("ck_financial_model_revision_evidence_evidence_type"),
        ),
        sa.CheckConstraint(
            "relationship IN ('SUPPORTS','CONTRADICTS','CONTEXT')",
            name=op.f("ck_financial_model_revision_evidence_relationship"),
        ),
        sa.CheckConstraint(
            "(evidence_type = 'RESEARCH_REVISION' AND research_revision_id IS NOT NULL "
            "AND research_forecast_id IS NULL AND thesis_revision_id IS NULL "
            "AND thesis_claim_id IS NULL) "
            "OR (evidence_type = 'RESEARCH_FORECAST' AND research_revision_id IS NULL "
            "AND research_forecast_id IS NOT NULL AND thesis_revision_id IS NULL "
            "AND thesis_claim_id IS NULL) "
            "OR (evidence_type = 'THESIS_REVISION' AND research_revision_id IS NULL "
            "AND research_forecast_id IS NULL AND thesis_revision_id IS NOT NULL "
            "AND thesis_claim_id IS NULL) "
            "OR (evidence_type = 'THESIS_CLAIM' AND research_revision_id IS NULL "
            "AND research_forecast_id IS NULL AND thesis_revision_id IS NULL "
            "AND thesis_claim_id IS NOT NULL)",
            name=op.f("ck_financial_model_revision_evidence_one_typed_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["financial_model_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["research_revision_id"], ["research_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["research_forecast_id"], ["research_forecasts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["thesis_revision_id"], ["investment_thesis_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["thesis_claim_id"], ["investment_thesis_claims.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_model_revision_evidence")),
        sa.UniqueConstraint(
            "revision_id",
            "evidence_type",
            "research_revision_id",
            "research_forecast_id",
            "thesis_revision_id",
            "thesis_claim_id",
            name="uq_model_revision_evidence_reference",
        ),
    )
    op.create_index(
        "ix_model_revision_evidence_revision",
        "financial_model_revision_evidence",
        ["revision_id"],
    )


def downgrade() -> None:
    table_name = "financial_model_revision_evidence"
    existing_indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }
    for index_name in (
        "ix_model_revision_evidence_revision",
        "ix_financial_model_revision_evidence_revision",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=table_name)
    op.drop_table("financial_model_revision_evidence")
    op.drop_column("financial_model_revisions", "proposal_source_reference")
    op.drop_column("financial_model_revisions", "proposal_authored_at")
    op.drop_column("financial_model_revisions", "proposal_author_id")
