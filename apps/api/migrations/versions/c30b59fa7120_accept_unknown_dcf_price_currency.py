"""Allow explicit unknown quote-currency quality state in DCF outputs.

Revision ID: c30b59fa7120
Revises: bb7a6d0c9710
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c30b59fa7120"
down_revision: str | Sequence[str] | None = "bb7a6d0c9710"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_financial_model_outputs_price_status"),
        "financial_model_outputs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_financial_model_outputs_price_status"),
        "financial_model_outputs",
        "price_status IN ('FRESH','STALE','QUALITY_CHECK','NO_DATA',"
        "'CURRENCY_MISMATCH','CURRENCY_UNKNOWN')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_financial_model_outputs_price_status"),
        "financial_model_outputs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_financial_model_outputs_price_status"),
        "financial_model_outputs",
        "price_status IN ('FRESH','STALE','QUALITY_CHECK','NO_DATA','CURRENCY_MISMATCH')",
    )
