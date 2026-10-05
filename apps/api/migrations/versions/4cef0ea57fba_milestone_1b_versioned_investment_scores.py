"""Add versioned definitions and append-only investment score assessments.

Revision ID: 4cef0ea57fba
Revises: a57efdd8015f
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "4cef0ea57fba"
down_revision: str | Sequence[str] | None = "a57efdd8015f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "score_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dimension", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("minimum_score", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("maximum_score", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("directionality", sa.String(length=24), nullable=False),
        sa.Column("units", sa.String(length=80), nullable=False),
        sa.Column("methodology", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dimension IN ('DURABILITY_10Y','COMPOUNDER_QUALITY','EXECUTION','RISK')",
            name=op.f("ck_score_definitions_dimension"),
        ),
        sa.CheckConstraint(
            "directionality IN ('HIGHER_IS_BETTER','HIGHER_IS_RISK')",
            name=op.f("ck_score_definitions_directionality"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','RETIRED')", name=op.f("ck_score_definitions_status")
        ),
        sa.CheckConstraint(
            "minimum_score >= 0 AND minimum_score <= maximum_score",
            name=op.f("ck_score_definitions_scale"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_score_definitions_version")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_definitions")),
        sa.UniqueConstraint("dimension", "version", name=op.f("uq_score_definitions_dimension")),
    )
    op.create_index(
        "uq_score_definitions_one_active_per_dimension",
        "score_definitions",
        ["dimension"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "score_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("score_definition_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=1000), nullable=True),
        sa.Column("superseded_assessment_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(status = 'ASSESSED' AND score IS NOT NULL) OR "
            "(status <> 'ASSESSED' AND score IS NULL)",
            name=op.f("ck_score_assessments_score_status"),
        ),
        sa.CheckConstraint(
            "actor IN ('LOCAL_USER','SYSTEM','IMPORT')",
            name=op.f("ck_score_assessments_actor"),
        ),
        sa.CheckConstraint(
            "status IN ('ASSESSED','MISSING','UNAVAILABLE','INVALID')",
            name=op.f("ck_score_assessments_status"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR score >= 0 AND score <= 5",
            name=op.f("ck_score_assessments_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_score_assessments_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["score_definition_id"],
            ["score_definitions.id"],
            name=op.f("fk_score_assessments_score_definition_id_score_definitions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_assessment_id"],
            ["score_assessments.id"],
            name=op.f("fk_score_assessments_superseded_assessment_id_score_assessments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_assessments")),
        sa.UniqueConstraint(
            "superseded_assessment_id",
            name=op.f("uq_score_assessments_superseded_assessment_id"),
        ),
    )
    op.create_index(op.f("ix_score_assessments_company_id"), "score_assessments", ["company_id"])
    op.create_index(
        op.f("ix_score_assessments_score_definition_id"),
        "score_assessments",
        ["score_definition_id"],
    )

    definitions = sa.table(
        "score_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("dimension", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("minimum_score", sa.Numeric(4, 2)),
        sa.column("maximum_score", sa.Numeric(4, 2)),
        sa.column("directionality", sa.String()),
        sa.column("units", sa.String()),
        sa.column("methodology", sa.Text()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("status", sa.String()),
        sa.column("recorded_at", sa.DateTime(timezone=True)),
    )
    effective_from = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {
            "id": UUID("d0d20000-0000-4000-8000-000000000001"),
            "dimension": "DURABILITY_10Y",
            "version": 1,
            "minimum_score": 0,
            "maximum_score": 5,
            "directionality": "HIGHER_IS_BETTER",
            "units": "points",
            "methodology": (
                "Rate the evidence that the business can remain relevant and defend its "
                "competitive position over a ten-year horizon. 0 is no demonstrated durability; "
                "5 is exceptional, resilient long-term durability."
            ),
            "effective_from": effective_from,
            "status": "ACTIVE",
            "recorded_at": effective_from,
        },
        {
            "id": UUID("d0d20000-0000-4000-8000-000000000002"),
            "dimension": "COMPOUNDER_QUALITY",
            "version": 1,
            "minimum_score": 0,
            "maximum_score": 5,
            "directionality": "HIGHER_IS_BETTER",
            "units": "points",
            "methodology": (
                "Rate business quality and its capacity to reinvest at attractive returns "
                "and compound long-term shareholder value. 0 is poor demonstrated quality; "
                "5 is exceptional compounding quality."
            ),
            "effective_from": effective_from,
            "status": "ACTIVE",
            "recorded_at": effective_from,
        },
        {
            "id": UUID("d0d20000-0000-4000-8000-000000000003"),
            "dimension": "EXECUTION",
            "version": 1,
            "minimum_score": 1,
            "maximum_score": 5,
            "directionality": "HIGHER_IS_BETTER",
            "units": "points",
            "methodology": (
                "Rate execution evidence including operating delivery, KPI and guidance "
                "reliability, improving economics, and capital discipline. 1 is repeated "
                "execution failure; 5 is consistently strong execution."
            ),
            "effective_from": effective_from,
            "status": "ACTIVE",
            "recorded_at": effective_from,
        },
        {
            "id": UUID("d0d20000-0000-4000-8000-000000000004"),
            "dimension": "RISK",
            "version": 1,
            "minimum_score": 1,
            "maximum_score": 5,
            "directionality": "HIGHER_IS_RISK",
            "units": "points",
            "methodology": (
                "Rate structural, business, financial, regulatory, and geopolitical risk. "
                "Higher values mean greater risk. Valuation is explicitly excluded."
            ),
            "effective_from": effective_from,
            "status": "ACTIVE",
            "recorded_at": effective_from,
        },
    ]
    op.bulk_insert(definitions, rows)


def downgrade() -> None:
    op.drop_index(op.f("ix_score_assessments_score_definition_id"), table_name="score_assessments")
    op.drop_index(op.f("ix_score_assessments_company_id"), table_name="score_assessments")
    op.drop_table("score_assessments")
    op.drop_index(
        "uq_score_definitions_one_active_per_dimension",
        table_name="score_definitions",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_table("score_definitions")
