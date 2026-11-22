"""Preserve complete model migration receipt mapping versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b93e1c7af602"
down_revision: str | Sequence[str] | None = "d7b4a6c8e2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "financial_model_migration_assessments"


def upgrade() -> None:
    op.alter_column(TABLE, "mapping_version", existing_type=sa.String(40), type_=sa.String(80))


def downgrade() -> None:
    # Never shorten an immutable receipt, including a version ending in spaces.
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    oversized = sa.text(f"SELECT EXISTS (SELECT 1 FROM {TABLE} WHERE length(mapping_version) > 40)")
    if op.get_bind().scalar(oversized):
        raise RuntimeError("Cannot downgrade while receipt mapping versions exceed 40 characters")
    op.alter_column(TABLE, "mapping_version", existing_type=sa.String(80), type_=sa.String(40))
