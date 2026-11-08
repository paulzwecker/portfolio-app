"""Durable review evidence stays isolated from canonical observed holdings."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from browser_server import local_test_url, verify_local_identity
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from portfolio_api.database import Base
from portfolio_api.domain.models import (
    HoldingSnapshot,
    Portfolio,
    PortfolioLedgerCandidate,
    PortfolioLedgerReview,
)
from portfolio_api.migrations import alembic_config, expected_heads

pytestmark = pytest.mark.integration
AT = datetime(2026, 10, 1, 12, tzinfo=UTC)
REVISION = "a832e94d6f10"
TABLES = {"portfolio_ledger_candidates", "portfolio_ledger_reviews"}


@pytest.fixture
def storage_engine(request: pytest.FixtureRequest) -> Iterator[Engine]:
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL to an explicit loopback PostgreSQL _test database")
    url = local_test_url(raw)
    check = create_engine(
        url,
        hide_parameters=True,
        connect_args={"connect_timeout": 3, "options": "-c default_transaction_read_only=on"},
    )
    try:
        with check.connect() as connection:
            verify_local_identity(connection, url)
    finally:
        check.dispose()
    # The shared fixture creates only its own random schema after identity verification.
    yield cast(Engine, request.getfixturevalue("postgres_engine"))


def anchor(session: Session) -> tuple[UUID, UUID]:
    portfolio = Portfolio(name="Synthetic ledger storage portfolio", base_currency="EUR")
    session.add(portfolio)
    session.flush()
    snapshot = HoldingSnapshot(
        portfolio_id=portfolio.id,
        effective_at=AT,
        completeness="COMPLETE",
        actor="LOCAL_USER",
        reason="Synthetic immutable opening evidence",
        source="synthetic-storage-test",
    )
    session.add(snapshot)
    session.flush()
    return portfolio.id, snapshot.id


def candidate(portfolio_id: UUID, snapshot_id: UUID) -> PortfolioLedgerCandidate:
    return PortfolioLedgerCandidate(
        id=uuid4(),
        portfolio_id=portfolio_id,
        anchor_snapshot_id=snapshot_id,
        base_candidate_id=None,
        input_sha256="1" * 64,
        packet_sha256="2" * 64,
        preview_sha256="3" * 64,
        request_sha256=uuid4().hex * 2,
        as_of=AT,
        preview_status="ENDING_RECONCILED",
        packet_data={"quantity": "0.0000000001", "cash": "0", "missing": None},
        preview_data={"input_sha256": "1" * 64},
        reason="Synthetic packet for storage guarantees",
    )


def review(value: PortfolioLedgerCandidate, revision: int | None = 1) -> PortfolioLedgerReview:
    return PortfolioLedgerReview(
        portfolio_id=value.portfolio_id,
        candidate_id=value.id,
        decision="ACCEPT" if revision is not None else "REJECT",
        revision_number=revision,
        request_sha256="5" * 64,
        reason="Synthetic explicit independent packet review",
        review_data={"candidate_id": str(value.id), "acknowledgements": ["evidence-reviewed"]},
    )


def test_additive_migration_upgrade_replay_and_downgrade(storage_engine: Engine) -> None:
    assert len(expected_heads()) == 1
    with Session(storage_engine) as session, session.begin():
        portfolio_id, _ = anchor(session)
    with storage_engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        assert isinstance(schema, str) and schema.startswith("test_")
        config = alembic_config()
        config.attributes["connection"] = connection
        command.downgrade(config, REVISION)
        before = set(inspect(connection).get_table_names(schema=schema))
        command.downgrade(config, "9f2a6d4c81b7")
        assert set(inspect(connection).get_table_names(schema=schema)) == before - TABLES
        assert connection.scalar(select(Portfolio.id).where(Portfolio.id == portfolio_id))
        command.upgrade(config, REVISION)
        command.upgrade(config, REVISION)
        assert MigrationContext.configure(connection).get_current_heads() == (REVISION,)
        assert set(inspect(connection).get_table_names(schema=schema)) == before
        for name in TABLES:
            table = Base.metadata.tables[name]
            reflected = inspect(connection)
            assert {row["name"] for row in reflected.get_columns(name, schema=schema)} == set(
                table.columns.keys()
            )
            assert {
                row["name"] for row in reflected.get_check_constraints(name, schema=schema)
            } == {item.name for item in table.constraints if isinstance(item, CheckConstraint)}
            assert {
                tuple(row["column_names"])
                for row in reflected.get_unique_constraints(name, schema=schema)
            } == {
                tuple(column.name for column in item.columns)
                for item in table.constraints
                if isinstance(item, UniqueConstraint)
            }
        assert connection.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) == 0
        assert connection.scalar(select(func.count()).select_from(PortfolioLedgerReview)) == 0


def test_exact_json_replay_and_independent_review_ancestry(storage_engine: Engine) -> None:
    with Session(storage_engine) as session, session.begin():
        portfolio_id, snapshot_id = anchor(session)
        first = candidate(portfolio_id, snapshot_id)
        session.add(first)
        session.flush()
        session.add(review(first))
        second = candidate(portfolio_id, snapshot_id)
        second.base_candidate_id = first.id
        session.add(second)
        session.flush()
        session.add(review(second, None))
        third = candidate(portfolio_id, snapshot_id)
        third.base_candidate_id = first.id
        session.add(third)
        session.flush()
        session.add(review(third, None))
        first_id = first.id
    with Session(storage_engine) as session:
        loaded = session.get(PortfolioLedgerCandidate, first_id)
        assert loaded is not None
        assert loaded.packet_data == {"quantity": "0.0000000001", "cash": "0", "missing": None}
        assert loaded.as_of == AT and loaded.submitted_at.tzinfo is not None
        assert loaded.submitted_by == "LOCAL_USER"
        accepted = session.scalar(
            select(PortfolioLedgerReview).where(PortfolioLedgerReview.revision_number == 1)
        )
        assert accepted is not None
        assert accepted.reviewed_by == "LOCAL_USER" and accepted.reviewed_at.tzinfo is not None
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == 1
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerReview)) == 3


@pytest.mark.parametrize("kind", ["candidate", "review"])
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_orm_history_is_append_only(storage_engine: Engine, kind: str, operation: str) -> None:
    with Session(storage_engine) as session, session.begin():
        portfolio_id, snapshot_id = anchor(session)
        value = candidate(portfolio_id, snapshot_id)
        session.add(value)
        session.flush()
        decision = review(value)
        session.add(decision)
        session.flush()
        identifier = value.id if kind == "candidate" else decision.id
    with Session(storage_engine) as session:
        entity = (
            session.get(PortfolioLedgerCandidate, identifier)
            if kind == "candidate"
            else session.get(PortfolioLedgerReview, identifier)
        )
        assert entity is not None
        if operation == "update":
            entity.reason = "Unapproved rewrite"
        else:
            session.delete(entity)
        with pytest.raises(ValueError, match="Historical observations are append-only"):
            session.flush()
        session.rollback()
    with Session(storage_engine) as session:
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) == 1
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerReview)) == 1


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("input_sha256", "short"),
        ("packet_sha256", "short"),
        ("preview_sha256", "short"),
        ("request_sha256", "short"),
        ("submitted_by", "AGENT"),
        ("preview_status", "ACCEPTED"),
        ("base_candidate_id", "self"),
    ],
)
def test_candidate_constraints_fail_atomically(
    storage_engine: Engine, field: str, invalid: str
) -> None:
    with Session(storage_engine) as session, session.begin():
        portfolio_id, snapshot_id = anchor(session)
    with Session(storage_engine) as session:
        value = candidate(portfolio_id, snapshot_id)
        setattr(value, field, value.id if invalid == "self" else invalid)
        session.add(value)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) == 0
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerReview)) == 0


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("decision", "UNKNOWN"),
        ("revision_number", None),
        ("revision_number", 0),
        ("reviewed_by", "AGENT"),
        ("request_sha256", "short"),
    ],
)
def test_review_constraints_reject_and_rollback_candidate(
    storage_engine: Engine, field: str, invalid: object
) -> None:
    with Session(storage_engine) as session, session.begin():
        portfolio_id, snapshot_id = anchor(session)
    with Session(storage_engine) as session:
        value = candidate(portfolio_id, snapshot_id)
        session.add(value)
        session.flush()
        decision = review(value)
        setattr(decision, field, invalid)
        session.add(decision)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) == 0
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerReview)) == 0


def test_cross_portfolio_ancestry_and_reviews_are_rejected(storage_engine: Engine) -> None:
    with Session(storage_engine) as session, session.begin():
        portfolio_id, snapshot_id = anchor(session)
        other_id, other_snapshot_id = anchor(session)
        first = candidate(portfolio_id, snapshot_id)
        session.add(first)
        session.flush()
        first_id = first.id
    with Session(storage_engine) as session:
        wrong_base = candidate(other_id, other_snapshot_id)
        wrong_base.base_candidate_id = first_id
        session.add(wrong_base)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        wrong_review = PortfolioLedgerReview(
            portfolio_id=other_id,
            candidate_id=first_id,
            decision="REJECT",
            request_sha256="5" * 64,
            reason="Synthetic invalid cross-portfolio review",
            review_data={},
        )
        session.add(wrong_review)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) == 1
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerReview)) == 0


def test_terminal_review_and_revision_uniqueness(storage_engine: Engine) -> None:
    with Session(storage_engine) as session, session.begin():
        portfolio_id, snapshot_id = anchor(session)
        first = candidate(portfolio_id, snapshot_id)
        second = candidate(portfolio_id, snapshot_id)
        session.add_all([first, second])
        session.flush()
        session.add(review(first))
        first_id, second_id = first.id, second.id
    with Session(storage_engine) as session:
        first_loaded = session.get(PortfolioLedgerCandidate, first_id)
        second_loaded = session.get(PortfolioLedgerCandidate, second_id)
        assert first_loaded is not None and second_loaded is not None
        session.add(review(first_loaded, None))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        session.add(review(second_loaded))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        reject_with_revision = review(second_loaded)
        reject_with_revision.decision = "REJECT"
        session.add(reject_with_revision)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerReview)) == 1


def test_same_portfolio_semantic_request_is_unique_across_submission_ids(
    storage_engine: Engine,
) -> None:
    with Session(storage_engine) as session, session.begin():
        portfolio_id, snapshot_id = anchor(session)
        first = candidate(portfolio_id, snapshot_id)
        session.add(first)
        session.flush()
        request_hash = first.request_sha256
    with Session(storage_engine) as session:
        duplicate = candidate(portfolio_id, snapshot_id)
        duplicate.request_sha256 = request_hash
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) == 1
    with Session(storage_engine) as session, session.begin():
        other_id, other_snapshot_id = anchor(session)
        independent = candidate(other_id, other_snapshot_id)
        independent.request_sha256 = request_hash
        session.add(independent)
    with Session(storage_engine) as session:
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) == 2
