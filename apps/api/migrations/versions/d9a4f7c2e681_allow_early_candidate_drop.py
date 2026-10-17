"""allow a failed Candidate gate to close with a Drop recommendation

Revision ID: d9a4f7c2e681
Revises: 8f1c2d6a4b70
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d9a4f7c2e681"
down_revision: str | Sequence[str] | None = "8f1c2d6a4b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_candidate_pipeline_revisions_disposition_requires_resolution",
        "candidate_pipeline_revisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_candidate_pipeline_revisions_disposition_requires_resolution",
        "candidate_pipeline_revisions",
        "disposition IS NULL OR disposition = 'DROP' OR stage = 'RESOLUTION'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_candidate_pipeline_revisions_disposition_requires_resolution",
        "candidate_pipeline_revisions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_candidate_pipeline_revisions_disposition_requires_resolution",
        "candidate_pipeline_revisions",
        "disposition IS NULL OR stage = 'RESOLUTION'",
    )
