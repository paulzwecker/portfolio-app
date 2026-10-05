"""Store portable contract digests for idempotent model imports.

Revision ID: d07edb6e2a13
Revises: c30b59fa7120
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d07edb6e2a13"
down_revision: str | Sequence[str] | None = "c30b59fa7120"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "financial_model_revisions",
        sa.Column("contract_digest", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("financial_model_revisions", "contract_digest")
