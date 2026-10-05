"""Empty platform baseline; no domain tables are introduced in Milestone 0.

Revision ID: 0001_platform_baseline
Revises:
"""

revision: str = "0001_platform_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
