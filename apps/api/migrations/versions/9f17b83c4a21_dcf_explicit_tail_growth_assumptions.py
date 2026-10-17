"""Persist explicit annual UFCF tail growth assumptions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "9f17b83c4a21"
down_revision: str | None = "8d3a20f719c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EFFECTIVE_FROM = datetime(2026, 10, 9, tzinfo=UTC)
HMODEL_RETURN_METHOD = {
    "id": UUID("9f170000-0000-4000-8000-000000000001"),
    "code": "UFCF_ENTERPRISE_HMODEL_IRR",
    "version": 1,
    "title": "Probability-weighted enterprise UFCF IRR with H-model terminal",
    "cash_flow_basis": (
        "Probability-weighted annual unlevered free cash flow through Year 10, plus the "
        "Year 10 UFCF and a Gordon terminal value, with no additional 2.5 terminal-growth "
        "premium in the return stream."
    ),
    "perspective": "ENTERPRISE",
    "entry_value_basis": (
        "Exact listing share price × diluted shares less opening net cash/debt; this is the "
        "source model's implied enterprise cost."
    ),
    "share_price_basis": "Exact valuation-listing quote, split-adjusted close, in model currency.",
    "comparability_group": "ENTERPRISE_UFCF_HMODEL",
    "cross_method_policy": "SAME_METHOD_ONLY",
    "limitation": (
        "Not comparable with the legacy enterprise UFCF terminal-premium return method. Not "
        "shareholder-distribution IRR; future financing and payout schedules are absent."
    ),
}


def upgrade() -> None:
    definition_table = sa.table(
        "return_methodology_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("title", sa.String()),
        sa.column("cash_flow_basis", sa.Text()),
        sa.column("perspective", sa.String()),
        sa.column("entry_value_basis", sa.Text()),
        sa.column("share_price_basis", sa.Text()),
        sa.column("comparability_group", sa.String()),
        sa.column("cross_method_policy", sa.String()),
        sa.column("limitation", sa.Text()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("recorded_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        definition_table,
        [
            {
                **HMODEL_RETURN_METHOD,
                "effective_from": EFFECTIVE_FROM,
                "recorded_at": EFFECTIVE_FROM,
            }
        ],
    )
    for model_key, method_id in {
        "P-AMZN": HMODEL_RETURN_METHOD["id"],
        "P-HIMS": HMODEL_RETURN_METHOD["id"],
        "P-MSFT": UUID("7b0f0000-0000-4000-8000-000000000001"),
    }.items():
        op.execute(
            sa.text(
                "UPDATE model_output_snapshots SET return_methodology_id = :methodology_id, "
                "return_methodology_status = 'CLASSIFIED' "
                "WHERE model_key = :model_key AND return_methodology_status = 'UNCLASSIFIED'"
            ).bindparams(methodology_id=method_id, model_key=model_key)
        )
    op.create_table(
        "dcf_tail_growth_assumptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=False),
        sa.Column("ufcf_growth", sa.Numeric(38, 18), nullable=False),
        sa.CheckConstraint(
            "forecast_year BETWEEN 6 AND 10",
            name=op.f("ck_dcf_tail_growth_assumptions_forecast_year"),
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["dcf_scenario_assumptions.id"],
            name=op.f("fk_dcf_tail_growth_assumptions_scenario_id_dcf_scenario_assumptions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dcf_tail_growth_assumptions")),
        sa.UniqueConstraint(
            "scenario_id",
            "forecast_year",
            name="uq_dcf_tail_growth_year",
        ),
    )
    op.create_index(
        op.f("ix_dcf_tail_growth_assumptions_scenario_id"),
        "dcf_tail_growth_assumptions",
        ["scenario_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            "UPDATE financial_model_outputs AS output "
            "SET return_methodology_id = :methodology_id "
            "FROM financial_model_revisions AS revision "
            "WHERE output.revision_id = revision.id "
            "AND revision.methodology_version = 'ufcf-dcf-explicit-tail-v1'"
        ).bindparams(methodology_id=HMODEL_RETURN_METHOD["id"])
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_dcf_tail_growth_assumptions_scenario_id"),
        table_name="dcf_tail_growth_assumptions",
    )
    op.drop_table("dcf_tail_growth_assumptions")
    op.execute(
        sa.text(
            "UPDATE financial_model_outputs AS output "
            "SET return_methodology_id = (SELECT id FROM return_methodology_definitions "
            "WHERE code = 'UFCF_ENTERPRISE_IRR' AND version = 1) "
            "FROM financial_model_revisions AS revision "
            "WHERE output.revision_id = revision.id "
            "AND revision.methodology_version = 'ufcf-dcf-explicit-tail-v1'"
        )
    )
    op.execute(
        "UPDATE model_output_snapshots SET return_methodology_id = NULL, "
        "return_methodology_status = 'UNCLASSIFIED' "
        "WHERE model_key IN ('P-AMZN','P-HIMS','P-MSFT')"
    )
    op.execute(
        "DELETE FROM return_methodology_definitions "
        "WHERE code = 'UFCF_ENTERPRISE_HMODEL_IRR' AND version = 1"
    )
