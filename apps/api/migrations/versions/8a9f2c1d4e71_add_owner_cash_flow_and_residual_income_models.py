"""Add method-specific inputs and projections for two model archetypes.

Revision ID: 8a9f2c1d4e71
Revises: d07edb6e2a13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8a9f2c1d4e71"
down_revision: str | Sequence[str] | None = "d07edb6e2a13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

N = sa.Numeric(38, 18)
UUID = sa.Uuid(as_uuid=True)


def _common(name: str):
    return [
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "revision_id",
            UUID,
            sa.ForeignKey("financial_model_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_financial_model_revisions_model_type"),
        "financial_model_revisions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_financial_model_revisions_model_type"),
        "financial_model_revisions",
        "model_type IN ('UFCF_DCF_10Y_FADE','OWNER_CASH_FLOW_10Y','RESIDUAL_INCOME_10Y_FADE')",
    )

    op.create_table(
        "owner_cash_flow_assumptions",
        *_common("owner_cash_flow_assumptions"),
        sa.Column("base_revenue", N, nullable=False),
        sa.Column("net_cash", N, nullable=False),
        sa.Column("diluted_shares", N, nullable=False),
        sa.UniqueConstraint("revision_id"),
    )
    op.create_table(
        "owner_cash_flow_scenarios",
        *_common("owner_cash_flow_scenarios"),
        sa.Column("scenario", sa.String(8), nullable=False),
        sa.Column("probability", N, nullable=False),
        sa.Column("required_return", N, nullable=False),
        sa.Column("terminal_growth", N, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.UniqueConstraint("revision_id", "scenario", name="uq_owner_cf_revision_scenario"),
        sa.CheckConstraint("scenario IN ('BEAR','BASE','BULL')", name="scenario"),
        sa.CheckConstraint("probability BETWEEN 0 AND 1", name="probability"),
    )
    op.create_index(
        op.f("ix_owner_cash_flow_scenarios_revision_id"),
        "owner_cash_flow_scenarios",
        ["revision_id"],
    )
    op.create_table(
        "owner_cash_flow_year_assumptions",
        *_common("owner_cash_flow_year_assumptions"),
        sa.Column("scenario_id", UUID, nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=False),
        sa.Column("revenue_growth", N, nullable=False),
        sa.Column("owner_cash_flow_margin", N, nullable=False),
        sa.UniqueConstraint("scenario_id", "forecast_year", name="uq_owner_cf_scenario_year"),
        sa.CheckConstraint("forecast_year BETWEEN 1 AND 10", name="forecast_year"),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["owner_cash_flow_scenarios.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        op.f("ix_owner_cash_flow_year_assumptions_scenario_id"),
        "owner_cash_flow_year_assumptions",
        ["scenario_id"],
    )
    op.create_index(
        op.f("ix_owner_cash_flow_year_assumptions_revision_id"),
        "owner_cash_flow_year_assumptions",
        ["revision_id"],
    )
    op.create_table(
        "owner_cash_flow_projections",
        *_common("owner_cash_flow_projections"),
        sa.Column("scenario_id", UUID, nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=False),
        sa.Column("revenue", N, nullable=False),
        sa.Column("owner_cash_flow", N, nullable=False),
        sa.Column("owner_cash_flow_per_share", N, nullable=False),
        sa.Column("present_value_per_share", N, nullable=False),
        sa.Column("terminal_value_per_share", N, nullable=True),
        sa.UniqueConstraint("scenario_id", "forecast_year", name="uq_owner_cf_projection_year"),
        sa.CheckConstraint("forecast_year BETWEEN 1 AND 10", name="forecast_year"),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["owner_cash_flow_scenarios.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        op.f("ix_owner_cash_flow_projections_scenario_id"),
        "owner_cash_flow_projections",
        ["scenario_id"],
    )
    op.create_index(
        op.f("ix_owner_cash_flow_projections_revision_id"),
        "owner_cash_flow_projections",
        ["revision_id"],
    )

    op.create_table(
        "residual_income_assumptions",
        *_common("residual_income_assumptions"),
        sa.Column("current_book_value_per_share", N, nullable=False),
        sa.Column("payout_ratio", N, nullable=False),
        sa.UniqueConstraint("revision_id"),
    )
    op.create_table(
        "residual_income_scenarios",
        *_common("residual_income_scenarios"),
        sa.Column("scenario", sa.String(8), nullable=False),
        sa.Column("probability", N, nullable=False),
        sa.Column("starting_roe", N, nullable=False),
        sa.Column("cost_of_equity", N, nullable=False),
        sa.Column("terminal_growth", N, nullable=False),
        sa.Column("mature_roe", N, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.UniqueConstraint("revision_id", "scenario", name="uq_ri_revision_scenario"),
        sa.CheckConstraint("scenario IN ('BEAR','BASE','BULL')", name="scenario"),
        sa.CheckConstraint("probability BETWEEN 0 AND 1", name="probability"),
    )
    op.create_index(
        op.f("ix_residual_income_scenarios_revision_id"),
        "residual_income_scenarios",
        ["revision_id"],
    )
    op.create_table(
        "residual_income_projections",
        *_common("residual_income_projections"),
        sa.Column("scenario_id", UUID, nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=False),
        sa.Column("beginning_book_value_per_share", N, nullable=False),
        sa.Column("return_on_equity", N, nullable=False),
        sa.Column("net_income_per_share", N, nullable=False),
        sa.Column("dividend_per_share", N, nullable=False),
        sa.Column("ending_book_value_per_share", N, nullable=False),
        sa.Column("residual_income_per_share", N, nullable=False),
        sa.Column("present_value_residual_income", N, nullable=False),
        sa.Column("terminal_value_per_share", N, nullable=True),
        sa.UniqueConstraint("scenario_id", "forecast_year", name="uq_ri_projection_year"),
        sa.CheckConstraint("forecast_year BETWEEN 1 AND 10", name="forecast_year"),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["residual_income_scenarios.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        op.f("ix_residual_income_projections_scenario_id"),
        "residual_income_projections",
        ["scenario_id"],
    )
    op.create_index(
        op.f("ix_residual_income_projections_revision_id"),
        "residual_income_projections",
        ["revision_id"],
    )


def downgrade() -> None:
    for table in (
        "residual_income_projections",
        "residual_income_scenarios",
        "residual_income_assumptions",
        "owner_cash_flow_projections",
        "owner_cash_flow_year_assumptions",
        "owner_cash_flow_scenarios",
        "owner_cash_flow_assumptions",
    ):
        op.drop_table(table)
    op.drop_constraint(
        op.f("ck_financial_model_revisions_model_type"),
        "financial_model_revisions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_financial_model_revisions_model_type"),
        "financial_model_revisions",
        "model_type = 'UFCF_DCF_10Y_FADE'",
    )
