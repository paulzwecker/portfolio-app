"""versioned return methodology metadata and comparable return bases

Revision ID: 7b0f1c4a91d2
Revises: 6e6c2d4e8a19
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "7b0f1c4a91d2"
down_revision: str | Sequence[str] | None = "6e6c2d4e8a19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EFFECTIVE_FROM = datetime(2026, 10, 9, tzinfo=UTC)
METHODS = {
    "UFCF_ENTERPRISE_IRR": {
        "id": UUID("7b0f0000-0000-4000-8000-000000000001"),
        "title": "Probability-weighted enterprise UFCF IRR",
        "cash_flow_basis": (
            "Probability-weighted annual unlevered free cash flow plus terminal enterprise value."
        ),
        "perspective": "ENTERPRISE",
        "entry_value_basis": (
            "Exact listing share price × diluted shares less opening net cash/debt; the source "
            "model's implied enterprise cost."
        ),
        "share_price_basis": "Exact valuation-listing split-adjusted close, in model currency.",
        "comparability_group": "ENTERPRISE_UFCF",
        "cross_method_policy": "SAME_METHOD_ONLY",
        "limitation": (
            "Not shareholder-distribution IRR. Future debt/cash, financing, interest, and "
            "payout schedules are not modeled; no enterprise-to-equity bridge is supported."
        ),
    },
    "OWNER_CASH_FLOW_EQUITY_IRR": {
        "id": UUID("7b0f0000-0000-4000-8000-000000000002"),
        "title": "Probability-weighted owner cash-flow equity IRR",
        "cash_flow_basis": (
            "Probability-weighted owner cash flow per diluted listing share, terminal owner cash "
            "flow, and net cash per share in terminal proceeds."
        ),
        "perspective": "EQUITY",
        "entry_value_basis": "Exact valuation-listing share price.",
        "share_price_basis": "Exact valuation-listing split-adjusted close, in model currency.",
        "comparability_group": "EQUITY_RETURN",
        "cross_method_policy": "CONDITIONAL_EQUITY_CROSS_METHOD",
        "limitation": (
            "Owner cash flow is an owner-available cash-flow convention, not necessarily an "
            "actual dividend or a forecast of cash distributed to shareholders."
        ),
    },
    "RESIDUAL_INCOME_EQUITY_IRR": {
        "id": UUID("7b0f0000-0000-4000-8000-000000000003"),
        "title": "Probability-weighted residual-income equity IRR",
        "cash_flow_basis": (
            "Probability-weighted explicit dividends plus terminal book value and terminal "
            "residual income per share."
        ),
        "perspective": "EQUITY",
        "entry_value_basis": "Exact valuation-listing share price.",
        "share_price_basis": "Exact valuation-listing split-adjusted close, in model currency.",
        "comparability_group": "EQUITY_RETURN",
        "cross_method_policy": "CONDITIONAL_EQUITY_CROSS_METHOD",
        "limitation": (
            "Uses explicit dividends and book-value/residual-income terminal proceeds; this is "
            "a different shareholder cash-flow basis from owner cash flow."
        ),
    },
}
LEGACY_MODEL_KEYS = {
    "P-GOOGL": "UFCF_ENTERPRISE_IRR",
    "P-ASML": "UFCF_ENTERPRISE_IRR",
    "P-ISRG": "UFCF_ENTERPRISE_IRR",
    "P-MA": "UFCF_ENTERPRISE_IRR",
    "P-CPRT": "UFCF_ENTERPRISE_IRR",
    "P-UBER": "UFCF_ENTERPRISE_IRR",
    "W-TOST": "OWNER_CASH_FLOW_EQUITY_IRR",
    "W-HDFC": "RESIDUAL_INCOME_EQUITY_IRR",
}


def upgrade() -> None:
    op.create_table(
        "return_methodology_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("cash_flow_basis", sa.Text(), nullable=False),
        sa.Column("perspective", sa.String(length=20), nullable=False),
        sa.Column("entry_value_basis", sa.Text(), nullable=False),
        sa.Column("share_price_basis", sa.Text(), nullable=False),
        sa.Column("comparability_group", sa.String(length=80), nullable=False),
        sa.Column("cross_method_policy", sa.String(length=48), nullable=False),
        sa.Column("limitation", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_return_methodology_definitions_version"),
        sa.CheckConstraint(
            "perspective IN ('ENTERPRISE','EQUITY')",
            name="ck_return_methodology_definitions_perspective",
        ),
        sa.CheckConstraint(
            "cross_method_policy IN ('SAME_METHOD_ONLY','CONDITIONAL_EQUITY_CROSS_METHOD')",
            name="ck_return_methodology_definitions_cross_method_policy",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_return_methodology_definitions"),
        sa.UniqueConstraint("code", "version", name="uq_return_methodology_code_version"),
    )
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
                "id": values["id"],
                "code": code,
                "version": 1,
                **{key: value for key, value in values.items() if key != "id"},
                "effective_from": EFFECTIVE_FROM,
                "recorded_at": EFFECTIVE_FROM,
            }
            for code, values in METHODS.items()
        ],
    )

    op.add_column(
        "financial_model_outputs",
        sa.Column("return_methodology_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_financial_model_outputs_return_methodology_id",
        "financial_model_outputs",
        "return_methodology_definitions",
        ["return_methodology_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_financial_model_outputs_return_methodology_id",
        "financial_model_outputs",
        ["return_methodology_id"],
    )
    op.execute(
        """
        UPDATE financial_model_outputs AS output
        SET return_methodology_id = definition.id
        FROM financial_model_revisions AS revision
        JOIN financial_models AS model ON model.id = revision.model_id
        JOIN return_methodology_definitions AS definition ON definition.code = CASE model.model_type
            WHEN 'UFCF_DCF_10Y_FADE' THEN 'UFCF_ENTERPRISE_IRR'
            WHEN 'OWNER_CASH_FLOW_10Y' THEN 'OWNER_CASH_FLOW_EQUITY_IRR'
            WHEN 'RESIDUAL_INCOME_10Y_FADE' THEN 'RESIDUAL_INCOME_EQUITY_IRR'
        END AND definition.version = 1
        WHERE output.revision_id = revision.id
        """
    )
    op.alter_column("financial_model_outputs", "return_methodology_id", nullable=False)

    op.add_column(
        "model_output_snapshots",
        sa.Column("return_methodology_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "model_output_snapshots",
        sa.Column(
            "return_methodology_status",
            sa.String(length=20),
            server_default="UNCLASSIFIED",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_model_output_snapshots_return_methodology_id",
        "model_output_snapshots",
        "return_methodology_definitions",
        ["return_methodology_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_model_output_snapshots_return_methodology_status",
        "model_output_snapshots",
        "return_methodology_status IN ('CLASSIFIED','UNCLASSIFIED')",
    )
    op.create_check_constraint(
        "ck_model_output_snapshots_return_methodology_identity",
        "model_output_snapshots",
        "(return_methodology_id IS NULL AND return_methodology_status = 'UNCLASSIFIED') OR "
        "(return_methodology_id IS NOT NULL AND return_methodology_status = 'CLASSIFIED')",
    )
    op.create_index(
        "ix_model_output_snapshots_return_methodology_id",
        "model_output_snapshots",
        ["return_methodology_id"],
    )
    for model_key, method_code in LEGACY_MODEL_KEYS.items():
        op.execute(
            sa.text(
                "UPDATE model_output_snapshots SET return_methodology_id = :methodology_id, "
                "return_methodology_status = 'CLASSIFIED' WHERE model_key = :model_key"
            ).bindparams(
                methodology_id=METHODS[method_code]["id"],
                model_key=model_key,
            )
        )
    op.alter_column(
        "model_output_snapshots",
        "return_methodology_status",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_output_snapshots_return_methodology_id",
        table_name="model_output_snapshots",
    )
    op.drop_constraint(
        "ck_model_output_snapshots_return_methodology_identity",
        "model_output_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "ck_model_output_snapshots_return_methodology_status",
        "model_output_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "fk_model_output_snapshots_return_methodology_id",
        "model_output_snapshots",
        type_="foreignkey",
    )
    op.drop_column("model_output_snapshots", "return_methodology_status")
    op.drop_column("model_output_snapshots", "return_methodology_id")
    op.drop_index(
        "ix_financial_model_outputs_return_methodology_id",
        table_name="financial_model_outputs",
    )
    op.drop_constraint(
        "fk_financial_model_outputs_return_methodology_id",
        "financial_model_outputs",
        type_="foreignkey",
    )
    op.drop_column("financial_model_outputs", "return_methodology_id")
    op.drop_table("return_methodology_definitions")
