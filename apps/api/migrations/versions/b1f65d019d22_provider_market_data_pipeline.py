"""provider-backed market facts with raw payload provenance

Revision ID: b1f65d019d22
Revises: c9d2741a6b52
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1f65d019d22"
down_revision: str | Sequence[str] | None = "c9d2741a6b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_data_batches",
        sa.Column(
            "source_kind",
            sa.String(length=32),
            nullable=False,
            server_default="WORKBOOK_SNAPSHOT",
        ),
    )
    op.alter_column(
        "market_data_batches", "workbook_sha256", existing_type=sa.String(64), nullable=True
    )
    op.alter_column(
        "market_data_batches",
        "source_as_of",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.add_column("market_data_batches", sa.Column("provider_id", sa.String(120), nullable=True))
    op.add_column(
        "market_data_batches", sa.Column("provider_schema_version", sa.String(120), nullable=True)
    )
    op.add_column("market_data_batches", sa.Column("query_scope", sa.JSON(), nullable=True))

    op.add_column(
        "price_observations",
        sa.Column("price_kind", sa.String(24), nullable=False, server_default="DAILY_CLOSE"),
    )
    op.add_column(
        "price_observations", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_price_observations_price_kind",
        "price_observations",
        "price_kind IN ('DAILY_CLOSE','CURRENT_QUOTE')",
    )

    op.add_column(
        "corporate_actions",
        sa.Column("provider", sa.String(120), nullable=False, server_default="LEGACY_WORKBOOK"),
    )
    op.add_column(
        "corporate_actions", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("corporate_actions", sa.Column("cash_amount", sa.Numeric(28, 10), nullable=True))
    op.add_column("corporate_actions", sa.Column("cash_currency", sa.String(3), nullable=True))

    op.add_column(
        "fx_observations", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "fx_observations",
        sa.Column("data_quality", sa.String(20), nullable=False, server_default="PASS"),
    )
    op.create_check_constraint(
        "ck_fx_observations_data_quality",
        "fx_observations",
        "data_quality IN ('PASS','DATA_CHECK','INVALID')",
    )
    op.add_column("fx_observations", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.add_column("fx_observations", sa.Column("source_ref", sa.String(1000), nullable=True))
    op.add_column(
        "fx_observations", sa.Column("supersedes_observation_id", sa.Uuid(), nullable=True)
    )
    op.create_unique_constraint("uq_fx_observations_source_ref", "fx_observations", ["source_ref"])
    op.create_foreign_key(
        "fk_fx_observations_batch_id_market_data_batches",
        "fx_observations",
        "market_data_batches",
        ["batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_fx_observations_supersedes_observation_id_fx_observations",
        "fx_observations",
        "fx_observations",
        ["supersedes_observation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_fx_observations_supersedes_observation_id",
        "fx_observations",
        ["supersedes_observation_id"],
    )
    op.create_index("ix_fx_observations_batch_id", "fx_observations", ["batch_id"], unique=False)

    op.create_table(
        "external_raw_payloads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(120), nullable=False),
        sa.Column("domain", sa.String(80), nullable=False),
        sa.Column("source_record_id", sa.String(500), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("media_type", sa.String(160), nullable=False),
        sa.Column("content_encoding", sa.String(16), nullable=False, server_default="gzip"),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_bytes", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "content_encoding IN ('identity','gzip')",
            name="ck_external_raw_payloads_content_encoding",
        ),
        sa.CheckConstraint(
            "length(payload_sha256) = 64", name="ck_external_raw_payloads_payload_sha256"
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["market_data_batches.id"],
            name="fk_external_raw_payloads_batch_id_market_data_batches",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_external_raw_payloads"),
        sa.UniqueConstraint(
            "batch_id", "source_record_id", name="uq_external_payload_batch_record"
        ),
    )
    op.create_index(
        "ix_external_raw_payloads_batch_id", "external_raw_payloads", ["batch_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_external_raw_payloads_batch_id", table_name="external_raw_payloads")
    op.drop_table("external_raw_payloads")
    op.drop_index("ix_fx_observations_batch_id", table_name="fx_observations")
    op.drop_constraint(
        "uq_fx_observations_supersedes_observation_id", "fx_observations", type_="unique"
    )
    op.drop_constraint(
        "fk_fx_observations_supersedes_observation_id_fx_observations",
        "fx_observations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_fx_observations_batch_id_market_data_batches", "fx_observations", type_="foreignkey"
    )
    op.drop_constraint("uq_fx_observations_source_ref", "fx_observations", type_="unique")
    op.drop_constraint("ck_fx_observations_data_quality", "fx_observations", type_="check")
    op.drop_column("fx_observations", "supersedes_observation_id")
    op.drop_column("fx_observations", "source_ref")
    op.drop_column("fx_observations", "batch_id")
    op.drop_column("fx_observations", "observed_at")
    op.drop_column("fx_observations", "data_quality")
    op.drop_column("corporate_actions", "cash_currency")
    op.drop_column("corporate_actions", "cash_amount")
    op.drop_column("corporate_actions", "observed_at")
    op.drop_column("corporate_actions", "provider")
    op.drop_constraint("ck_price_observations_price_kind", "price_observations", type_="check")
    op.drop_column("price_observations", "observed_at")
    op.drop_column("price_observations", "price_kind")
    op.drop_column("market_data_batches", "query_scope")
    op.drop_column("market_data_batches", "provider_schema_version")
    op.drop_column("market_data_batches", "provider_id")
    op.alter_column(
        "market_data_batches",
        "source_as_of",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "market_data_batches", "workbook_sha256", existing_type=sa.String(64), nullable=False
    )
    op.drop_column("market_data_batches", "source_kind")
