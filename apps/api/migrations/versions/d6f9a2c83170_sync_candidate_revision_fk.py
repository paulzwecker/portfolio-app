"""Link reviewed Google Sheets decisions to canonical model revisions.

Revision ID: d6f9a2c83170
Revises: c42e8f12b591
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d6f9a2c83170"
down_revision: str | Sequence[str] | None = "c42e8f12b591"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_sheets_candidate_revision",
        "google_sheets_sync_candidates",
        "financial_model_revisions",
        ["accepted_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_sheets_candidate_revision",
        "google_sheets_sync_candidates",
        type_="foreignkey",
    )
