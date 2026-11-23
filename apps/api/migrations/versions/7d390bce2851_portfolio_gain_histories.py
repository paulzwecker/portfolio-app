"""Store private retrospective portfolio gain history separately from current state."""

import sqlalchemy as sa
from alembic import op

revision = "7d390bce2851"
down_revision = "c82d7a410f36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_gain_histories",
        sa.Column("portfolio_id", sa.Uuid(), sa.ForeignKey("portfolios.id"), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("report", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM portfolio_gain_histories)")):
        raise RuntimeError("Preserve published history before downgrade")
    op.drop_table("portfolio_gain_histories")
