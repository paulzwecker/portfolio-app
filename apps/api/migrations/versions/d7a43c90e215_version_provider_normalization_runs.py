"""make provider normalization runs independently repeatable from raw batches

Revision ID: d7a43c90e215
Revises: c4a8f6d21e90
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a43c90e215"
down_revision: str | Sequence[str] | None = "c4a8f6d21e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_data_batches",
        sa.Column("normalizer_version", sa.String(length=80), nullable=True),
    )
    op.execute(
        "UPDATE market_data_batches SET normalizer_version = CASE "
        "WHEN source_kind = 'WORKBOOK_SNAPSHOT' THEN 'legacy-workbook-market-data-v1' "
        "ELSE COALESCE(reconciliation->>'normalizer_version', 'provider-normalizer-unknown-v1') "
        "END WHERE normalizer_version IS NULL"
    )
    op.alter_column("market_data_batches", "normalizer_version", nullable=False)
    op.drop_constraint(
        op.f("uq_market_data_batches_source_digest"),
        "market_data_batches",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_market_data_batches_source_normalizer"),
        "market_data_batches",
        ["source_digest", "normalizer_version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_market_data_batches_source_normalizer"),
        "market_data_batches",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_market_data_batches_source_digest"), "market_data_batches", ["source_digest"]
    )
    op.drop_column("market_data_batches", "normalizer_version")
