"""allow batch imports to link facts within the same immutable source filing

Revision ID: c2f8ba7019de
Revises: f84c92d17a61
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c2f8ba7019de"
down_revision: str | Sequence[str] | None = "f84c92d17a61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_reported_fundamental_supersedes",
        "reported_fundamental_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_reported_fundamental_supersedes",
        "reported_fundamental_observations",
        "reported_fundamental_observations",
        ["supersedes_observation_id"],
        ["id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_reported_fundamental_supersedes",
        "reported_fundamental_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_reported_fundamental_supersedes",
        "reported_fundamental_observations",
        "reported_fundamental_observations",
        ["supersedes_observation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
