"""normalize consensus payload batch check name

Revision ID: a9c138fdd222
Revises: 00b1fb118089
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "a9c138fdd222"
down_revision: str | Sequence[str] | None = "00b1fb118089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_consensus_batch_check(expression: str | None) -> None:
    if context.is_offline_mode():
        return
    checks = sa.inspect(op.get_bind()).get_check_constraints("external_raw_payloads")
    consensus_checks = [
        item
        for item in checks
        if "num_nonnulls" in item["sqltext"].lower()
        and "consensus_estimate_batch_id" in item["sqltext"]
    ]
    expected_name = "ck_external_raw_payloads_exactly_one_batch"
    if expression is not None:
        correct = any(item["name"] == expected_name for item in consensus_checks)
        for item in consensus_checks:
            if item["name"] != expected_name:
                op.drop_constraint(op.f(item["name"]), "external_raw_payloads", type_="check")
        if not correct:
            op.create_check_constraint(op.f(expected_name), "external_raw_payloads", expression)
        return

    for item in consensus_checks:
        op.drop_constraint(op.f(item["name"]), "external_raw_payloads", type_="check")
    old_checks = [
        item
        for item in checks
        if "num_nonnulls" in item["sqltext"].lower()
        and "reported_fundamental_batch_id" in item["sqltext"]
        and "consensus_estimate_batch_id" not in item["sqltext"]
    ]
    if not old_checks:
        op.create_check_constraint(
            op.f(expected_name),
            "external_raw_payloads",
            "num_nonnulls(batch_id, reported_fundamental_batch_id) = 1",
        )


def upgrade() -> None:
    _replace_consensus_batch_check(
        "num_nonnulls(batch_id, reported_fundamental_batch_id, consensus_estimate_batch_id) = 1"
    )


def downgrade() -> None:
    _replace_consensus_batch_check(None)
