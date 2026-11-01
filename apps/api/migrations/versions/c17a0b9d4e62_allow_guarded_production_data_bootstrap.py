"""Allow guarded market and SEC bootstrap run ledgers on production.

Revision ID: c17a0b9d4e62
Revises: b16d4f8a2c91
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c17a0b9d4e62"
down_revision: str | Sequence[str] | None = "b16d4f8a2c91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("market_data_bootstrap_runs", "fundamentals_bootstrap_runs"):
        constraint_name = op.f(f"ck_{table_name}_target_environment")
        op.drop_constraint(constraint_name, table_name, type_="check")
        op.create_check_constraint(
            constraint_name,
            table_name,
            "target_environment IN ('development','rehearsal','production')",
        )


def downgrade() -> None:
    for table_name in ("fundamentals_bootstrap_runs", "market_data_bootstrap_runs"):
        constraint_name = op.f(f"ck_{table_name}_target_environment")
        op.drop_constraint(constraint_name, table_name, type_="check")
        op.create_check_constraint(
            constraint_name,
            table_name,
            "target_environment IN ('development','rehearsal')",
        )
