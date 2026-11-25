"""Attach optional earnings model assessments to immutable research revisions."""

import sqlalchemy as sa
from alembic import op

revision = "63ad18f0e52b"
down_revision = "7d390bce2851"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_revisions", sa.Column("earnings_review", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("research_revisions", "earnings_review")
