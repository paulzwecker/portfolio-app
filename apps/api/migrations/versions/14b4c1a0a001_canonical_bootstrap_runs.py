"""Record canonical workbook bootstrap receipts.

Revision ID: 14b4c1a0a001
Revises: 12a6f0d9c3e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "14b4c1a0a001"
down_revision: str | Sequence[str] | None = "12a6f0d9c3e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_bootstrap_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("portfolio_snapshot_run_id", sa.String(length=32), nullable=False),
        sa.Column("market_snapshot_run_id", sa.String(length=32), nullable=False),
        sa.Column("provider_identifiers_sha256", sa.String(length=64), nullable=True),
        sa.Column("import_version", sa.String(length=80), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "length(input_digest) = 64", name=op.f("ck_canonical_bootstrap_runs_input_digest")
        ),
        sa.CheckConstraint(
            "length(source_digest) = 64", name=op.f("ck_canonical_bootstrap_runs_source_digest")
        ),
        sa.CheckConstraint(
            "portfolio_snapshot_run_id ~ '^[0-9a-f]{32}$'",
            name=op.f("ck_canonical_bootstrap_runs_portfolio_snapshot_run_id"),
        ),
        sa.CheckConstraint(
            "market_snapshot_run_id ~ '^[0-9a-f]{32}$'",
            name=op.f("ck_canonical_bootstrap_runs_market_snapshot_run_id"),
        ),
        sa.CheckConstraint(
            "provider_identifiers_sha256 IS NULL OR length(provider_identifiers_sha256) = 64",
            name=op.f("ck_canonical_bootstrap_runs_provider_identifiers_sha256"),
        ),
        sa.CheckConstraint(
            "status IN ('APPLIED','APPLIED_WITH_GAPS')",
            name=op.f("ck_canonical_bootstrap_runs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_canonical_bootstrap_runs")),
        sa.UniqueConstraint("input_digest", name=op.f("uq_canonical_bootstrap_runs_input_digest")),
    )


def downgrade() -> None:
    op.drop_table("canonical_bootstrap_runs")
