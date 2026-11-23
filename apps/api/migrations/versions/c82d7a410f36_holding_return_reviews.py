"""Store private dated holding return evidence separately from holdings authority."""

import sqlalchemy as sa
from alembic import op

revision = "c82d7a410f36"
down_revision = "b93e1c7af602"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holding_return_reviews",
        sa.Column("portfolio_id", sa.Uuid(), sa.ForeignKey("portfolios.id"), primary_key=True),
        sa.Column("listing_id", sa.Uuid(), sa.ForeignKey("listings.id"), primary_key=True),
        sa.Column("through", sa.Date(), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM holding_return_reviews)")):
        raise RuntimeError("Preserve holding return evidence before downgrade")
    op.drop_table("holding_return_reviews")
