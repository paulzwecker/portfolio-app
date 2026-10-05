"""Add canonical, revisioned 10-year UFCF DCF model state.

Revision ID: bb7a6d0c9710
Revises: a21cae4f0d22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bb7a6d0c9710"
down_revision: str | Sequence[str] | None = "a21cae4f0d22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("valuation_listing_id", sa.Uuid(), nullable=False),
        sa.Column("model_type", sa.String(length=60), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("model_currency", sa.String(length=3), nullable=False),
        sa.Column("source_model_key", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_models")),
        sa.UniqueConstraint(
            "company_id", "valuation_listing_id", "model_type", name="uq_financial_model_identity"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
            name=op.f("fk_financial_models_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["valuation_listing_id"],
            ["listings.id"],
            ondelete="RESTRICT",
            name=op.f("fk_financial_models_valuation_listing_id_listings"),
        ),
    )
    op.create_table(
        "financial_model_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("model_type", sa.String(length=60), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("base_revision_id", sa.Uuid(), nullable=True),
        sa.Column("methodology_version", sa.String(length=40), nullable=False),
        sa.Column("source_revision_id", sa.String(length=160), nullable=True),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=1000), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor IN ('LOCAL_USER','SYSTEM','IMPORT')",
            name=op.f("ck_financial_model_revisions_actor"),
        ),
        sa.CheckConstraint(
            "model_type = 'UFCF_DCF_10Y_FADE'", name=op.f("ck_financial_model_revisions_model_type")
        ),
        sa.CheckConstraint(
            "revision_number > 0", name=op.f("ck_financial_model_revisions_revision_number")
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["financial_models.id"],
            ondelete="RESTRICT",
            name=op.f("fk_financial_model_revisions_model_id_financial_models"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id", "base_revision_id"],
            ["financial_model_revisions.model_id", "financial_model_revisions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_financial_model_revisions_model_base_revision"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_model_revisions")),
        sa.UniqueConstraint("model_id", "id", name="uq_financial_model_revision_identity"),
        sa.UniqueConstraint("model_id", "revision_number", name="uq_financial_model_revision_no"),
        sa.UniqueConstraint(
            "model_id", "source_revision_id", name="uq_financial_model_source_revision"
        ),
    )
    op.create_index(
        op.f("ix_financial_model_revisions_model_id"),
        "financial_model_revisions",
        ["model_id"],
        unique=False,
    )
    op.add_column("financial_models", sa.Column("current_revision_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_financial_models_id_current_revision"),
        "financial_models",
        "financial_model_revisions",
        ["id", "current_revision_id"],
        ["model_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "dcf_model_assumptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("base_revenue", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_ebit_margin", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_tax_rate", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_da_to_revenue", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_capex_to_revenue", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_nwc_to_revenue", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("net_cash_debt", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("diluted_shares", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["financial_model_revisions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_dcf_model_assumptions_revision_id_financial_model_revisions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dcf_model_assumptions")),
        sa.UniqueConstraint("revision_id", name=op.f("uq_dcf_model_assumptions_revision_id")),
    )
    op.create_table(
        "dcf_scenario_assumptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("scenario", sa.String(length=8), nullable=False),
        sa.Column("probability", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("terminal_growth", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("year10_ufcf_growth", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "probability BETWEEN 0 AND 1", name=op.f("ck_dcf_scenario_assumptions_probability")
        ),
        sa.CheckConstraint(
            "scenario IN ('BEAR','BASE','BULL')", name=op.f("ck_dcf_scenario_assumptions_scenario")
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["financial_model_revisions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_dcf_scenario_assumptions_revision_id_financial_model_revisions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dcf_scenario_assumptions")),
        sa.UniqueConstraint("revision_id", "scenario", name="uq_dcf_revision_scenario"),
    )
    op.create_index(
        op.f("ix_dcf_scenario_assumptions_revision_id"),
        "dcf_scenario_assumptions",
        ["revision_id"],
        unique=False,
    )
    op.create_table(
        "dcf_year_assumptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=False),
        sa.Column("revenue_growth", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("ebit_margin", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("da_to_revenue", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("capex_to_revenue", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("nwc_to_revenue", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("discount_rate", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.CheckConstraint(
            "forecast_year BETWEEN 1 AND 5", name=op.f("ck_dcf_year_assumptions_forecast_year")
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["dcf_scenario_assumptions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_dcf_year_assumptions_scenario_id_dcf_scenario_assumptions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dcf_year_assumptions")),
        sa.UniqueConstraint("scenario_id", "forecast_year", name="uq_dcf_scenario_year_input"),
    )
    op.create_index(
        op.f("ix_dcf_year_assumptions_scenario_id"),
        "dcf_year_assumptions",
        ["scenario_id"],
        unique=False,
    )
    op.create_table(
        "dcf_projections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("ebit", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("nopat", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("depreciation_amortization", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("capex", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("net_working_capital", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("change_in_nwc", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("unlevered_free_cash_flow", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("revenue_growth", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("discount_rate", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("discount_factor", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("present_value_ufcf", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("terminal_value", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.CheckConstraint(
            "forecast_year BETWEEN 1 AND 10", name=op.f("ck_dcf_projections_forecast_year")
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["dcf_scenario_assumptions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_dcf_projections_scenario_id_dcf_scenario_assumptions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dcf_projections")),
        sa.UniqueConstraint("scenario_id", "forecast_year", name="uq_dcf_scenario_projection"),
    )
    op.create_index(
        op.f("ix_dcf_projections_scenario_id"), "dcf_projections", ["scenario_id"], unique=False
    )
    op.create_table(
        "financial_model_outputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model_currency", sa.String(length=3), nullable=False),
        sa.Column("price_observation_id", sa.Uuid(), nullable=True),
        sa.Column("current_price", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("price_effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_status", sa.String(length=24), nullable=False),
        sa.Column("price_unavailable_reason", sa.Text(), nullable=True),
        sa.Column("irr_unavailable_reason", sa.Text(), nullable=True),
        sa.Column("bear_fv", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_fv", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("bull_fv", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("bear_probability", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_probability", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("bull_probability", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("weighted_fv", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("weighted_upside", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("expected_cash_flow_irr", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("hurdle", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("expected_excess", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column("forward_fundamental_cagr", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.CheckConstraint(
            "price_status IN ('FRESH','STALE','QUALITY_CHECK','NO_DATA','CURRENCY_MISMATCH')",
            name=op.f("ck_financial_model_outputs_price_status"),
        ),
        sa.CheckConstraint(
            "status IN ('COMPLETE','PARTIAL')", name=op.f("ck_financial_model_outputs_status")
        ),
        sa.ForeignKeyConstraint(
            ["price_observation_id"],
            ["price_observations.id"],
            ondelete="RESTRICT",
            name=op.f("fk_financial_model_outputs_price_observation_id_price_observations"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["financial_model_revisions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_financial_model_outputs_revision_id_financial_model_revisions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_model_outputs")),
        sa.UniqueConstraint("revision_id", name="uq_financial_model_output_revision"),
    )
    op.create_index(
        op.f("ix_financial_model_outputs_revision_id"),
        "financial_model_outputs",
        ["revision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_financial_model_outputs_revision_id"), table_name="financial_model_outputs"
    )
    op.drop_table("financial_model_outputs")
    op.drop_index(op.f("ix_dcf_projections_scenario_id"), table_name="dcf_projections")
    op.drop_table("dcf_projections")
    op.drop_index(op.f("ix_dcf_year_assumptions_scenario_id"), table_name="dcf_year_assumptions")
    op.drop_table("dcf_year_assumptions")
    op.drop_index(
        op.f("ix_dcf_scenario_assumptions_revision_id"), table_name="dcf_scenario_assumptions"
    )
    op.drop_table("dcf_scenario_assumptions")
    op.drop_table("dcf_model_assumptions")
    op.drop_constraint(
        op.f("fk_financial_models_id_current_revision"), "financial_models", type_="foreignkey"
    )
    op.drop_column("financial_models", "current_revision_id")
    op.drop_index(
        op.f("ix_financial_model_revisions_model_id"), table_name="financial_model_revisions"
    )
    op.drop_table("financial_model_revisions")
    op.drop_table("financial_models")
