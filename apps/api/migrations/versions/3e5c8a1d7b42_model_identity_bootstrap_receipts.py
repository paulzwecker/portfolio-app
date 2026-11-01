"""Record guarded model-only canonical identity bootstrap receipts.

Revision ID: 3e5c8a1d7b42
Revises: c17a0b9d4e62
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e5c8a1d7b42"
down_revision: str | Sequence[str] | None = "c17a0b9d4e62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_identity_bootstrap_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("mapping_sha256", sa.String(length=64), nullable=False),
        sa.Column("mapping_version", sa.String(length=80), nullable=False),
        sa.Column("source_model_key", sa.String(length=120), nullable=False),
        sa.Column("package_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_identity_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_modified_at", sa.String(length=80), nullable=False),
        sa.Column("source_revision_id", sa.String(length=160), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "length(input_digest) = 64",
            name=op.f("ck_model_identity_bootstrap_receipts_input_digest"),
        ),
        sa.CheckConstraint(
            "length(mapping_sha256) = 64",
            name=op.f("ck_model_identity_bootstrap_receipts_mapping_sha256"),
        ),
        sa.CheckConstraint(
            "length(package_sha256) = 64",
            name=op.f("ck_model_identity_bootstrap_receipts_package_sha256"),
        ),
        sa.CheckConstraint(
            "length(source_identity_sha256) = 64",
            name=op.f("ck_model_identity_bootstrap_receipts_source_identity_sha256"),
        ),
        sa.CheckConstraint(
            "source_model_key = 'P-GOOGL'",
            name=op.f("ck_model_identity_bootstrap_receipts_source_model_key"),
        ),
        sa.CheckConstraint(
            "status = 'APPLIED'",
            name=op.f("ck_model_identity_bootstrap_receipts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
            name=op.f("fk_model_identity_bootstrap_receipts_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            ondelete="RESTRICT",
            name=op.f("fk_model_identity_bootstrap_receipts_security_id_securities"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            ondelete="RESTRICT",
            name=op.f("fk_model_identity_bootstrap_receipts_listing_id_listings"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_identity_bootstrap_receipts")),
        sa.UniqueConstraint(
            "input_digest", name=op.f("uq_model_identity_bootstrap_receipts_input_digest")
        ),
    )
    for column in ("company_id", "security_id", "listing_id", "package_sha256"):
        op.create_index(
            op.f(f"ix_model_identity_bootstrap_receipts_{column}"),
            "model_identity_bootstrap_receipts",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("package_sha256", "listing_id", "security_id", "company_id"):
        op.drop_index(
            op.f(f"ix_model_identity_bootstrap_receipts_{column}"),
            table_name="model_identity_bootstrap_receipts",
        )
    op.drop_table("model_identity_bootstrap_receipts")
