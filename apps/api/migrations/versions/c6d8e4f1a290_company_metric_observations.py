"""Add canonical company metrics, guidance, and model-driver projections.

Revision ID: c6d8e4f1a290
Revises: b59f16c8a203
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6d8e4f1a290"
down_revision: str | Sequence[str] | None = "b59f16c8a203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_metric_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=160), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("value_kind", sa.String(length=16), nullable=False),
        sa.Column("canonical_unit", sa.String(length=64), nullable=False),
        sa.Column("canonical_scale", sa.Numeric(38, 12), nullable=False),
        sa.Column("currency_policy", sa.String(length=16), nullable=False),
        sa.Column("aggregation_semantics", sa.String(length=40), nullable=False),
        sa.Column("default_period_type", sa.String(length=16), nullable=False),
        sa.Column("default_basis", sa.String(length=120), nullable=True),
        sa.Column("scope_dimensions", sa.JSON(), nullable=False),
        sa.Column("actuals_allowed", sa.Boolean(), nullable=False),
        sa.Column("guidance_allowed", sa.Boolean(), nullable=False),
        sa.Column("consensus_allowed", sa.Boolean(), nullable=False),
        sa.Column("model_driver_allowed", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(metric_key) > 0",
            name=op.f("ck_company_metric_definitions_metric_key"),
        ),
        sa.CheckConstraint(
            "category IN ('FINANCIAL','CAPITAL_STRUCTURE','OPERATING','CUSTOMER','CAPACITY',"
            "'PRODUCT','MARKET_SHARE','MARKET_EXPOSURE','SEGMENT','BACKLOG','QUALITY','OTHER')",
            name=op.f("ck_company_metric_definitions_category"),
        ),
        sa.CheckConstraint(
            "value_kind IN ('CURRENCY','PERCENT','COUNT','RATIO','TEXT')",
            name=op.f("ck_company_metric_definitions_value_kind"),
        ),
        sa.CheckConstraint(
            "canonical_scale > 0",
            name=op.f("ck_company_metric_definitions_canonical_scale"),
        ),
        sa.CheckConstraint(
            "currency_policy IN ('NONE','OPTIONAL','REQUIRED')",
            name=op.f("ck_company_metric_definitions_currency_policy"),
        ),
        sa.CheckConstraint(
            "default_period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name=op.f("ck_company_metric_definitions_default_period_type"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_metric_definitions_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_metric_definitions")),
        sa.UniqueConstraint(
            "metric_key",
            name="uq_company_metric_definition_key",
        ),
    )
    op.create_index(
        "ix_company_metric_definitions_company_active",
        "company_metric_definitions",
        ["company_id", "active"],
    )

    op.create_table(
        "company_metric_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_observation_id", sa.String(length=200), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("metric_definition_id", sa.Uuid(), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("value", sa.Numeric(38, 12), nullable=False),
        sa.Column("value_qualifier", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("scale", sa.Numeric(38, 12), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("basis", sa.String(length=120), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=False),
        sa.Column("quality_status", sa.String(length=16), nullable=False),
        sa.Column("quality_reason", sa.String(length=1000), nullable=True),
        sa.Column("supersedes_observation_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name=op.f("ck_company_metric_observations_period_type"),
        ),
        sa.CheckConstraint(
            "period_start <= period_end",
            name=op.f("ck_company_metric_observations_period_dates"),
        ),
        sa.CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name=op.f("ck_company_metric_observations_fiscal_quarter"),
        ),
        sa.CheckConstraint(
            "value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE')",
            name=op.f("ck_company_metric_observations_value_qualifier"),
        ),
        sa.CheckConstraint("scale > 0", name=op.f("ck_company_metric_observations_scale")),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_company_metric_observations_currency"),
        ),
        sa.CheckConstraint(
            "quality_status IN ('VERIFIED','PROVISIONAL','CONFLICTED','RESTATED')",
            name=op.f("ck_company_metric_observations_quality_status"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_metric_observations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["metric_definition_id"],
            ["company_metric_definitions.id"],
            name=op.f(
                "fk_company_metric_observations_metric_definition_id_company_metric_definitions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "metric_definition_id", "supersedes_observation_id"],
            [
                "company_metric_observations.company_id",
                "company_metric_observations.metric_definition_id",
                "company_metric_observations.id",
            ],
            name="fk_company_metric_observation_supersession",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_metric_observations")),
        sa.UniqueConstraint(
            "company_id",
            "metric_definition_id",
            "id",
            name="uq_company_metric_observation_identity",
        ),
        sa.UniqueConstraint(
            "external_observation_id",
            name="uq_company_metric_observation_external_id",
        ),
        sa.UniqueConstraint(
            "supersedes_observation_id",
            name=op.f("uq_company_metric_observations_supersedes_observation_id"),
        ),
    )
    op.create_index(
        "ix_company_metric_observations_company_metric_period",
        "company_metric_observations",
        ["company_id", "metric_definition_id", "period_end"],
    )
    op.create_index(
        "ix_company_metric_observations_company_recorded",
        "company_metric_observations",
        ["company_id", "recorded_at"],
    )

    op.create_table(
        "company_guidance_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_guidance_id", sa.String(length=200), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("metric_definition_id", sa.Uuid(), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("lower_value", sa.Numeric(38, 12), nullable=True),
        sa.Column("midpoint_value", sa.Numeric(38, 12), nullable=True),
        sa.Column("upper_value", sa.Numeric(38, 12), nullable=True),
        sa.Column("value_qualifier", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("scale", sa.Numeric(38, 12), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("basis", sa.String(length=120), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("supersedes_guidance_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name=op.f("ck_company_guidance_observations_period_type"),
        ),
        sa.CheckConstraint(
            "period_start <= period_end",
            name=op.f("ck_company_guidance_observations_period_dates"),
        ),
        sa.CheckConstraint(
            "fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4",
            name=op.f("ck_company_guidance_observations_fiscal_quarter"),
        ),
        sa.CheckConstraint(
            "value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE','RANGE')",
            name=op.f("ck_company_guidance_observations_value_qualifier"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUPERSEDED','WITHDRAWN','ACHIEVED')",
            name=op.f("ck_company_guidance_observations_status"),
        ),
        sa.CheckConstraint(
            "status = 'WITHDRAWN' OR "
            "lower_value IS NOT NULL OR midpoint_value IS NOT NULL OR upper_value IS NOT NULL",
            name=op.f("ck_company_guidance_observations_value_or_withdrawn"),
        ),
        sa.CheckConstraint(
            "lower_value IS NULL OR upper_value IS NULL OR lower_value <= upper_value",
            name=op.f("ck_company_guidance_observations_range_order"),
        ),
        sa.CheckConstraint("scale > 0", name=op.f("ck_company_guidance_observations_scale")),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_company_guidance_observations_currency"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_guidance_observations_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["metric_definition_id"],
            ["company_metric_definitions.id"],
            name=op.f(
                "fk_company_guidance_observations_metric_definition_id_company_metric_definitions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "metric_definition_id", "supersedes_guidance_id"],
            [
                "company_guidance_observations.company_id",
                "company_guidance_observations.metric_definition_id",
                "company_guidance_observations.id",
            ],
            name="fk_company_guidance_supersession",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_guidance_observations")),
        sa.UniqueConstraint(
            "company_id",
            "metric_definition_id",
            "id",
            name="uq_company_guidance_identity",
        ),
        sa.UniqueConstraint(
            "external_guidance_id",
            name="uq_company_guidance_external_id",
        ),
        sa.UniqueConstraint(
            "supersedes_guidance_id",
            name=op.f("uq_company_guidance_observations_supersedes_guidance_id"),
        ),
    )
    op.create_index(
        "ix_company_guidance_company_metric_period",
        "company_guidance_observations",
        ["company_id", "metric_definition_id", "period_end"],
    )

    op.create_table(
        "financial_model_driver_projections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_driver_id", sa.String(length=200), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("scenario", sa.String(length=8), nullable=False),
        sa.Column("metric_definition_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(38, 12), nullable=False),
        sa.Column("value_qualifier", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("scale", sa.Numeric(38, 12), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("basis", sa.String(length=120), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scenario IN ('BEAR','BASE','BULL')",
            name=op.f("ck_financial_model_driver_projections_scenario"),
        ),
        sa.CheckConstraint(
            "period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')",
            name=op.f("ck_financial_model_driver_projections_period_type"),
        ),
        sa.CheckConstraint(
            "period_start <= period_end",
            name=op.f("ck_financial_model_driver_projections_period_dates"),
        ),
        sa.CheckConstraint(
            "forecast_year > 0",
            name=op.f("ck_financial_model_driver_projections_forecast_year"),
        ),
        sa.CheckConstraint(
            "value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE')",
            name=op.f("ck_financial_model_driver_projections_value_qualifier"),
        ),
        sa.CheckConstraint(
            "scale > 0",
            name=op.f("ck_financial_model_driver_projections_scale"),
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_financial_model_driver_projections_currency"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["financial_models.id"],
            name=op.f("fk_financial_model_driver_projections_model_id_financial_models"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_id", "revision_id"],
            ["financial_model_revisions.model_id", "financial_model_revisions.id"],
            name="fk_financial_model_driver_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["metric_definition_id"],
            ["company_metric_definitions.id"],
            name=op.f(
                "fk_financial_model_driver_projections_metric_definition_id_company_metric_definitions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_model_driver_projections")),
        sa.UniqueConstraint(
            "external_driver_id",
            name="uq_financial_model_driver_external_id",
        ),
    )
    op.create_index(
        "ix_financial_model_driver_revision_metric",
        "financial_model_driver_projections",
        ["revision_id", "metric_definition_id", "forecast_year"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_model_driver_revision_metric",
        table_name="financial_model_driver_projections",
    )
    op.drop_table("financial_model_driver_projections")
    op.drop_index(
        "ix_company_guidance_company_metric_period",
        table_name="company_guidance_observations",
    )
    op.drop_table("company_guidance_observations")
    op.drop_index(
        "ix_company_metric_observations_company_recorded",
        table_name="company_metric_observations",
    )
    op.drop_index(
        "ix_company_metric_observations_company_metric_period",
        table_name="company_metric_observations",
    )
    op.drop_table("company_metric_observations")
    op.drop_index(
        "ix_company_metric_definitions_company_active",
        table_name="company_metric_definitions",
    )
    op.drop_table("company_metric_definitions")
