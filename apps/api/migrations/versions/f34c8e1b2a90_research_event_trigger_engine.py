"""Persist append-only research trigger captures and queue linkage.

Revision ID: f34c8e1b2a90
Revises: e25c8a6b4910
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f34c8e1b2a90"
down_revision: str | Sequence[str] | None = "e25c8a6b4910"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_triggers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.String(length=600), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_domain", sa.String(length=120), nullable=False),
        sa.Column("source_record_id", sa.String(length=500), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("queue_task_id", sa.String(length=64), nullable=True),
        sa.Column("queue_condition_fingerprint", sa.String(length=64), nullable=True),
        sa.CheckConstraint("version > 0", name=op.f("ck_research_triggers_version")),
        sa.CheckConstraint("length(event_key) > 0", name=op.f("ck_research_triggers_event_key")),
        sa.CheckConstraint(
            "length(fingerprint) = 64", name=op.f("ck_research_triggers_fingerprint")
        ),
        sa.CheckConstraint(
            "trigger_type IN ('NEW_FILING','MODEL_REVISION','EXPECTED_IRR_CHANGE',"
            "'CONSENSUS_REVISION','REPORTED_FACT_CORRECTION','THESIS_EVIDENCE_LINKED',"
            "'RISK_ASSESSMENT')",
            name=op.f("ck_research_triggers_trigger_type"),
        ),
        sa.CheckConstraint(
            "length(source_domain) > 0", name=op.f("ck_research_triggers_source_domain")
        ),
        sa.CheckConstraint(
            "length(source_record_id) > 0", name=op.f("ck_research_triggers_source_record_id")
        ),
        sa.CheckConstraint(
            "queue_task_id IS NULL OR length(queue_task_id) = 64",
            name=op.f("ck_research_triggers_queue_task_id"),
        ),
        sa.CheckConstraint(
            "queue_condition_fingerprint IS NULL OR length(queue_condition_fingerprint) = 64",
            name=op.f("ck_research_triggers_queue_condition_fingerprint"),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_triggers")),
        sa.UniqueConstraint("event_key", "version", name="uq_research_trigger_event_version"),
        sa.UniqueConstraint("event_key", "fingerprint", name="uq_research_trigger_event_content"),
    )
    op.create_index(
        "ix_research_triggers_company_detected",
        "research_triggers",
        ["company_id", "detected_at"],
    )
    op.create_index(
        "ix_research_triggers_source",
        "research_triggers",
        ["source_domain", "source_record_id"],
    )
    op.create_index("ix_research_triggers_company_id", "research_triggers", ["company_id"])

    op.drop_constraint(
        "ck_research_queue_completions_task_type",
        "research_queue_completions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_research_queue_completions_task_type",
        "research_queue_completions",
        "task_type IN ('CANDIDATE_STAGE','THESIS_REVIEW','THESIS_QUESTION',"
        "'MATERIAL_EVIDENCE','RESEARCH_TRIGGER','MODEL_REUNDERWRITE','MODEL_INTEGRITY',"
        "'WATCHLIST_READINESS','STRUCTURAL_RISK')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_research_queue_completions_task_type",
        "research_queue_completions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_research_queue_completions_task_type",
        "research_queue_completions",
        "task_type IN ('CANDIDATE_STAGE','THESIS_REVIEW','THESIS_QUESTION',"
        "'MATERIAL_EVIDENCE','MODEL_REUNDERWRITE','MODEL_INTEGRITY',"
        "'WATCHLIST_READINESS','STRUCTURAL_RISK')",
    )
    op.drop_index("ix_research_triggers_company_id", table_name="research_triggers")
    op.drop_index("ix_research_triggers_source", table_name="research_triggers")
    op.drop_index("ix_research_triggers_company_detected", table_name="research_triggers")
    op.drop_table("research_triggers")
