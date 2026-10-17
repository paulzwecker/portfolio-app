"""Add idempotent external-agent delivery and acknowledgment history.

Revision ID: b3a6e91d5c20
Revises: fa81b2c4d6e0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3a6e91d5c20"
down_revision: str | Sequence[str] | None = "fa81b2c4d6e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_agent_work_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.Uuid(), nullable=True),
        sa.Column("agent_role", sa.String(length=40), nullable=False),
        sa.Column("work_type", sa.String(length=24), nullable=False),
        sa.Column("work_key", sa.String(length=500), nullable=False),
        sa.Column("work_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("external_update_id", sa.String(length=200), nullable=True),
        sa.Column("agent_run_id", sa.String(length=200), nullable=True),
        sa.Column("actor_id", sa.String(length=160), nullable=True),
        sa.Column("proposal_domain", sa.String(length=16), nullable=True),
        sa.Column("proposal_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("source_reference", sa.String(length=2000), nullable=True),
        sa.Column("blocker_code", sa.String(length=80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "agent_role IN ('DATA_UNIVERSE_STEWARD','PORTFOLIO_THESIS_SENTINEL',"
            "'MODEL_ALLOCATION_STEWARD')",
            name=op.f("ck_research_agent_work_events_agent_role"),
        ),
        sa.CheckConstraint(
            "work_type IN ('TRIGGER','QUEUE_TASK','DATA_DOMAIN','PORTFOLIO_STATE')",
            name=op.f("ck_research_agent_work_events_work_type"),
        ),
        sa.CheckConstraint(
            "length(work_key) > 0", name=op.f("ck_research_agent_work_events_work_key")
        ),
        sa.CheckConstraint(
            "length(work_fingerprint) = 64",
            name=op.f("ck_research_agent_work_events_work_fingerprint"),
        ),
        sa.CheckConstraint(
            "channel IN ('API','GOOGLE_SHEETS')",
            name=op.f("ck_research_agent_work_events_channel"),
        ),
        sa.CheckConstraint(
            "event_type IN ('DELIVERY_SUCCEEDED','DELIVERY_FAILED','ACKNOWLEDGED',"
            "'IN_PROGRESS','COMPLETED','BLOCKED','SOURCE_UNAVAILABLE','STALE_SOURCE',"
            "'UNRESOLVED_REVIEW')",
            name=op.f("ck_research_agent_work_events_event_type"),
        ),
        sa.CheckConstraint(
            "length(idempotency_key) > 0",
            name=op.f("ck_research_agent_work_events_idempotency_key"),
        ),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64",
            name=op.f("ck_research_agent_work_events_content_fingerprint"),
        ),
        sa.CheckConstraint(
            "(event_type IN ('ACKNOWLEDGED','IN_PROGRESS','COMPLETED','BLOCKED',"
            "'SOURCE_UNAVAILABLE','STALE_SOURCE','UNRESOLVED_REVIEW') "
            "AND delivery_id IS NOT NULL) OR "
            "(event_type IN ('DELIVERY_SUCCEEDED','DELIVERY_FAILED') AND delivery_id IS NULL)",
            name=op.f("ck_research_agent_work_events_delivery_reference"),
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('DELIVERY_FAILED','BLOCKED','SOURCE_UNAVAILABLE',"
            "'STALE_SOURCE','UNRESOLVED_REVIEW') OR (reason IS NOT NULL AND length(reason) > 0)",
            name=op.f("ck_research_agent_work_events_reason_required"),
        ),
        sa.CheckConstraint(
            "(proposal_domain IS NULL AND proposal_candidate_id IS NULL) OR "
            "(proposal_domain IN ('MODEL','RESEARCH','THESIS','RISK') "
            "AND proposal_candidate_id IS NOT NULL)",
            name=op.f("ck_research_agent_work_events_proposal_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"], ["research_agent_work_events.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_agent_work_events")),
        sa.UniqueConstraint(
            "external_update_id", name=op.f("uq_research_agent_work_events_external_update_id")
        ),
        sa.UniqueConstraint(
            "idempotency_key", name=op.f("uq_research_agent_work_event_idempotency")
        ),
    )
    op.create_index(
        "ix_research_agent_work_events_delivery",
        "research_agent_work_events",
        ["delivery_id", "recorded_at"],
    )
    op.create_index(
        "ix_research_agent_work_events_delivery_id",
        "research_agent_work_events",
        ["delivery_id"],
    )
    op.create_index(
        "ix_research_agent_work_events_identity",
        "research_agent_work_events",
        ["agent_role", "work_type", "work_key", "work_fingerprint", "recorded_at"],
    )
    op.create_index(
        "uq_research_agent_work_delivery",
        "research_agent_work_events",
        ["agent_role", "work_type", "work_key", "work_fingerprint", "channel"],
        unique=True,
        postgresql_where=sa.text("event_type = 'DELIVERY_SUCCEEDED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_research_agent_work_delivery", table_name="research_agent_work_events")
    op.drop_index("ix_research_agent_work_events_identity", table_name="research_agent_work_events")
    op.drop_index(
        "ix_research_agent_work_events_delivery_id", table_name="research_agent_work_events"
    )
    op.drop_index("ix_research_agent_work_events_delivery", table_name="research_agent_work_events")
    op.drop_table("research_agent_work_events")
