"""Merge the parallel market-facts and workbook-domain migration histories.

Revision ID: a21cae4f0d22
Revises: 74ab83c99170, ac6e0a489b51
"""

from collections.abc import Sequence

revision: str = "a21cae4f0d22"
down_revision: str | Sequence[str] | None = ("74ab83c99170", "ac6e0a489b51")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
