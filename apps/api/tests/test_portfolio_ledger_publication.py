"""Synthetic source ownership cutover and canonical API readback on isolated schemas."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_portfolio_ledger import evidence
from test_portfolio_ledger_api import baseline
from test_portfolio_ledger_reviews import accept, decide, prepare, stage, submit
from test_portfolio_ledger_storage import storage_engine as storage_engine

from portfolio_api import legacy_import
from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api import portfolio_ledger_publication as publication
from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    HoldingSnapshot,
    Listing,
    Portfolio,
    PortfolioLedgerPublication,
)

pytestmark = pytest.mark.integration


def accepted(engine: Engine) -> tuple[UUID, c.LedgerCandidateRead]:
    portfolio_id, packet = prepare(engine)
    row = stage(engine, portfolio_id, submit(engine, portfolio_id, packet))
    return portfolio_id, decide(engine, portfolio_id, row.id, accept(row))


def preview(
    engine: Engine, portfolio_id: UUID, candidate_id: UUID
) -> c.LedgerPublicationPreviewRead:
    with Session(engine) as session:
        return publication.publication_preview(session, portfolio_id, candidate_id)


def command(plan: c.LedgerPublicationPreviewRead) -> c.LedgerPublicationCreate:
    return c.LedgerPublicationCreate(
        expected_plan_sha256=plan.plan_sha256,
        expected_previous_publication_id=plan.previous_publication_id,
        confirmation=plan.confirmation_phrase,
        reason="Reviewed synthetic whole-portfolio ownership publication",
        ownership_transfer_reviewed=True,
        whole_portfolio_scope_reviewed=True,
        current_state_recovery_verified=True,
        holdings_confirmation=True,
    )


def publish(
    engine: Engine, portfolio_id: UUID, candidate_id: UUID, value: c.LedgerPublicationCreate
) -> c.LedgerPublicationRead:
    with Session(engine) as session, session.begin():
        return publication.publish(session, portfolio_id, candidate_id, value)


def test_read_only_preview_then_published_snapshot_and_historical_readback(
    storage_engine: Engine,
) -> None:
    portfolio_id, row = accepted(storage_engine)
    before = baseline(storage_engine, portfolio_id)
    plan = preview(storage_engine, portfolio_id, row.id)
    assert plan.status == "READY" and plan.cutover_at == row.as_of
    assert preview(storage_engine, portfolio_id, row.id) == plan
    assert baseline(storage_engine, portfolio_id) == before
    receipt = publish(storage_engine, portfolio_id, row.id, command(plan))
    assert receipt.sequence == 1 and not receipt.replayed
    assert receipt.snapshot.source == f"portfolio-ledger-publication-v1:{receipt.id}"
    assert receipt.snapshot.actor == "LOCAL_USER" and receipt.snapshot.completeness == "COMPLETE"
    assert receipt.snapshot.recorded_at == receipt.published_at
    assert {p.currency: p.balance for p in receipt.snapshot.cash_positions} == {
        "USD": Decimal("89.65"),
        "EUR": Decimal("0"),
    }
    with Session(storage_engine) as session:
        current = queries.overview(session, portfolio_id)
        assert current.snapshot and current.snapshot.id == receipt.snapshot.id
        assert (
            current.target_revision
            and current.target_revision.model_dump(mode="json") == before["targets"]
        )
        assert current.base_market_value is None
        assert current.holdings_authority and current.holdings_authority.source == "ACCEPTED_LEDGER"
        assert current.holdings_authority.publication_id == receipt.id
        assert (
            ledger.portfolio_ledger_anchor(session, portfolio_id).snapshot.id
            == row.anchor_snapshot_id
        )
        historical = queries.overview(
            session, portfolio_id, receipt.published_at - timedelta(microseconds=1)
        )
        assert historical.snapshot and historical.snapshot.id == row.anchor_snapshot_id
        assert (
            historical.holdings_authority
            and historical.holdings_authority.source == "OBSERVED_SNAPSHOT"
        )
        assert publication.ownership(session, portfolio_id).latest_publication == receipt
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == 2
    replay = publish(storage_engine, portfolio_id, row.id, command(plan))
    assert replay.replayed and replay.id == receipt.id
    assert preview(storage_engine, portfolio_id, row.id).status == "ALREADY_PUBLISHED"
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        result = client.get(f"/v1/portfolios/{portfolio_id}/overview")
        assert result.status_code == 200 and result.json()["snapshot"]["id"] == str(
            receipt.snapshot.id
        )
        assert (
            client.get(f"/v1/portfolios/{portfolio_id}/ledger/ownership").json()["source"]
            == "ACCEPTED_LEDGER"
        )


def next_candidate(
    engine: Engine, portfolio_id: UUID, row: c.LedgerCandidateRead, *, same_cutoff: bool = False
) -> c.LedgerCandidateRead:
    packet = row.packet.model_copy(deep=True)
    if not same_cutoff:
        packet.as_of += timedelta(days=1)
        assert packet.ending_statement
        packet.ending_statement.effective_at = packet.as_of
    packet.activity.append(
        c.LedgerCashActivity(
            id=uuid4(),
            account_id=packet.accounts[0].account_id,
            sequence=2,
            effective_at=packet.as_of,
            evidence=evidence("new-deposit"),
            kind="DEPOSIT",
            currency="USD",
            amount=Decimal("0.1"),
        )
    )
    assert packet.ending_statement
    packet.ending_statement.accounts[0].evidence = evidence("new-closing-observation")
    for cash in packet.ending_statement.accounts[0].cash:
        if cash.currency == "USD":
            cash.balance = Decimal("89.75")
    staged = stage(engine, portfolio_id, submit(engine, portfolio_id, packet, row.id))
    return decide(engine, portfolio_id, staged.id, accept(staged))


def test_subsequent_publication_preserves_original_opening_and_lineage(
    storage_engine: Engine,
) -> None:
    portfolio_id, row = accepted(storage_engine)
    first = publish(
        storage_engine, portfolio_id, row.id, command(preview(storage_engine, portfolio_id, row.id))
    )
    later = next_candidate(storage_engine, portfolio_id, row)
    plan = preview(storage_engine, portfolio_id, later.id)
    assert plan.previous_publication_id == first.id and plan.cutover_at == first.plan.cutover_at
    second = publish(storage_engine, portfolio_id, later.id, command(plan))
    assert second.sequence == 2 and second.previous_publication_id == first.id
    assert next(
        c.balance for c in second.snapshot.cash_positions if c.currency == "USD"
    ) == Decimal("89.75")
    with Session(storage_engine) as session:
        assert (
            ledger.portfolio_ledger_anchor(session, portfolio_id).snapshot.id
            == row.anchor_snapshot_id
        )
        earlier = queries.overview(session, portfolio_id, first.published_at)
        assert earlier.snapshot and earlier.snapshot.id == first.snapshot.id
    assert publish(storage_engine, portfolio_id, row.id, command(first.plan)).replayed
    assert preview(storage_engine, portfolio_id, later.id).status == "ALREADY_PUBLISHED"


@pytest.mark.parametrize(
    "field",
    [
        "expected_plan_sha256",
        "expected_previous_publication_id",
        "confirmation",
        "ownership_transfer_reviewed",
        "whole_portfolio_scope_reviewed",
        "current_state_recovery_verified",
        "holdings_confirmation",
    ],
)
def test_missing_or_different_approval_fails_before_snapshot_writes(
    storage_engine: Engine, field: str
) -> None:
    portfolio_id, row = accepted(storage_engine)
    plan = preview(storage_engine, portfolio_id, row.id)
    value = command(plan).model_copy(
        update={
            field: "a" * 64
            if field.endswith("sha256")
            else uuid4()
            if field.endswith("_id")
            else "wrong confirmation"
            if field == "confirmation"
            else False
        }
    )
    before = baseline(storage_engine, portfolio_id)
    with pytest.raises(services.DomainError):
        publish(storage_engine, portfolio_id, row.id, value)
    assert baseline(storage_engine, portfolio_id) == before


def test_stale_source_or_current_accepted_candidate_blocks_publication(
    storage_engine: Engine,
) -> None:
    portfolio_id, row = accepted(storage_engine)
    plan = preview(storage_engine, portfolio_id, row.id)
    later = next_candidate(storage_engine, portfolio_id, row)
    with pytest.raises(services.DomainError, match="current accepted"):
        publish(storage_engine, portfolio_id, row.id, command(plan))
    newer_plan = preview(storage_engine, portfolio_id, later.id)
    with Session(storage_engine) as session, session.begin():
        listing = session.get(Listing, row.packet.accounts[0].positions[0].listing_id)
        assert listing
        listing.identity_source_ref = "new-source-identity"
    before = baseline(storage_engine, portfolio_id)
    with pytest.raises(services.DomainError):
        publish(storage_engine, portfolio_id, later.id, command(newer_plan))
    assert baseline(storage_engine, portfolio_id) == before


def test_future_observed_snapshot_blocks_hidden_scheduled_replacement(
    storage_engine: Engine,
) -> None:
    portfolio_id, row = accepted(storage_engine)
    with Session(storage_engine) as session, session.begin():
        session.add(
            HoldingSnapshot(
                portfolio_id=portfolio_id,
                actor="LOCAL_USER",
                reason="Synthetic invalid scheduled observation",
                effective_at=datetime.now(UTC) + timedelta(days=1),
                completeness="COMPLETE",
            )
        )
    before = baseline(storage_engine, portfolio_id)
    with pytest.raises(services.DomainError, match="expected current snapshot"):
        preview(storage_engine, portfolio_id, row.id)
    assert baseline(storage_engine, portfolio_id) == before


def test_same_cutoff_correction_can_be_reviewed_but_cannot_invent_snapshot_time(
    storage_engine: Engine,
) -> None:
    portfolio_id, row = accepted(storage_engine)
    publish(
        storage_engine, portfolio_id, row.id, command(preview(storage_engine, portfolio_id, row.id))
    )
    corrected = next_candidate(storage_engine, portfolio_id, row, same_cutoff=True)
    with pytest.raises(services.DomainError, match="strictly later"):
        preview(storage_engine, portfolio_id, corrected.id)


def test_rollback_and_concurrent_replay_are_atomic(storage_engine: Engine) -> None:
    portfolio_id, row = accepted(storage_engine)
    value = command(preview(storage_engine, portfolio_id, row.id))
    before = baseline(storage_engine, portfolio_id)
    with Session(storage_engine) as session:
        publication.publish(session, portfolio_id, row.id, value)
        session.rollback()
    assert baseline(storage_engine, portfolio_id) == before
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(
            pool.map(lambda _: publish(storage_engine, portfolio_id, row.id, value), range(2))
        )
    assert (
        len({record.id for record in records}) == 1
        and sum(record.replayed for record in records) == 1
    )
    with Session(storage_engine) as session:
        assert session.scalar(select(func.count()).select_from(PortfolioLedgerPublication)) == 1
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == 2


def test_nonledger_snapshot_and_workbook_writers_fail_closed_after_cutover(
    storage_engine: Engine,
) -> None:
    portfolio_id, row = accepted(storage_engine)
    publish(
        storage_engine, portfolio_id, row.id, command(preview(storage_engine, portfolio_id, row.id))
    )
    before = baseline(storage_engine, portfolio_id)
    with (
        Session(storage_engine) as session,
        pytest.raises(services.DomainError, match="Ledger-owned"),
    ):
        services.record_holdings(
            session,
            portfolio_id,
            s.SnapshotCreate(
                actor="IMPORT",
                reason="Unreviewed replacement",
                effective_at=row.as_of + timedelta(days=1),
                completeness="COMPLETE",
                positions=[],
                cash_positions=[],
            ),
        )
    workbook = legacy_import.Workbook(Path("synthetic-unopened.xlsx"), "a" * 64, {})
    plan = legacy_import.ImportPlan(
        portfolio_workbook=workbook,
        market_workbook=workbook,
        observed_at=row.as_of + timedelta(days=1),
        source_digest="b" * 64,
    )
    with (
        Session(storage_engine) as session,
        pytest.raises(services.DomainError, match="Ledger-owned"),
    ):
        portfolio = services.portfolio(session, portfolio_id)
        legacy_import._import_holdings(session, plan, {}, portfolio)
    assert baseline(storage_engine, portfolio_id) == before


def test_api_preview_is_read_only_and_production_flag_remains_required(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id, row = accepted(storage_engine)
    plan = preview(storage_engine, portfolio_id, row.id)
    path = f"/v1/portfolios/{portfolio_id}/ledger/candidates/{row.id}"
    settings = fixture_settings().model_copy(
        update={
            "app_env": "production",
            "database_target_environment": "production",
            "api_access_token": SecretStr("synthetic-owner-token"),
            "database_production_writes_authorized": False,
        }
    )
    modes = []
    original = publication.publication_preview

    def inspect(
        session: Session, portfolio_id: UUID, candidate_id: UUID
    ) -> c.LedgerPublicationPreviewRead:
        modes.append(
            (
                session.scalar(text("SHOW transaction_read_only")),
                session.scalar(text("SHOW transaction_isolation")),
            )
        )
        return original(session, portfolio_id, candidate_id)

    monkeypatch.setattr(publication, "publication_preview", inspect)
    before = baseline(storage_engine, portfolio_id)
    with TestClient(fixture_application(storage_engine, settings)) as client:
        assert client.get(path + "/publication-preview").status_code == 401
        headers = {"x-api-access-token": "synthetic-owner-token"}
        assert client.get(path + "/publication-preview", headers=headers).status_code == 200
        assert (
            client.post(
                path + "/publish", headers=headers, json=command(plan).model_dump(mode="json")
            ).status_code
            == 403
        )
    assert modes == [("on", "repeatable read")]
    assert baseline(storage_engine, portfolio_id) == before


@pytest.mark.parametrize("decision", ["PENDING", "REJECTED"])
def test_unaccepted_candidate_has_no_publication_authority(
    storage_engine: Engine, decision: str
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    row = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    if decision == "REJECTED":
        decide(
            storage_engine,
            portfolio_id,
            row.id,
            c.LedgerRejectCreate(
                decision="REJECT",
                expected_base_candidate_id=None,
                expected_input_sha256=row.input_sha256,
                expected_preview_sha256=row.preview_sha256,
                reason="Synthetic rejection",
            ),
        )
    before = baseline(storage_engine, portfolio_id)
    with pytest.raises(services.DomainError, match="current accepted"):
        preview(storage_engine, portfolio_id, row.id)
    assert baseline(storage_engine, portfolio_id) == before


def test_publication_replay_is_scoped_and_timezone_independent(storage_engine: Engine) -> None:
    portfolio_id, row = accepted(storage_engine)
    value = command(preview(storage_engine, portfolio_id, row.id))
    receipt = publish(storage_engine, portfolio_id, row.id, value)
    with Session(storage_engine) as session:
        session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        result = publication.ownership(session, portfolio_id).latest_publication
        assert result and result.model_dump(mode="json") == receipt.model_dump(mode="json")
    with pytest.raises(services.DomainError, match="different publication request"):
        publish(
            storage_engine,
            portfolio_id,
            row.id,
            value.model_copy(update={"reason": "Different invocation"}),
        )
    with Session(storage_engine) as session, session.begin():
        other = Portfolio(name="Other synthetic portfolio", base_currency="EUR")
        session.add(other)
        session.flush()
        other_id = other.id
    with pytest.raises(services.DomainError, match="different publication request"):
        publish(storage_engine, other_id, row.id, value)


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_published_lineage_is_append_only(storage_engine: Engine, operation: str) -> None:
    portfolio_id, row = accepted(storage_engine)
    receipt = publish(
        storage_engine, portfolio_id, row.id, command(preview(storage_engine, portfolio_id, row.id))
    )
    with Session(storage_engine) as session:
        saved = session.get(PortfolioLedgerPublication, receipt.id)
        assert saved
        if operation == "update":
            saved.plan_sha256 = "a" * 64
        else:
            session.delete(saved)
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
    with Session(storage_engine) as session:
        result = publication.ownership(session, portfolio_id).latest_publication
        assert result and result.id == receipt.id


def test_new_migration_parity_replay_and_downgrade_retain_accepted_ownership(
    storage_engine: Engine,
) -> None:
    from alembic import command as alembic_command
    from sqlalchemy import inspect

    from portfolio_api.database import Base
    from portfolio_api.migrations import alembic_config, expected_heads

    assert expected_heads() == {"b59f16c8a203"}
    with storage_engine.begin() as connection:
        config = alembic_config()
        config.attributes["connection"] = connection
        before = set(inspect(connection).get_table_names())
        alembic_command.downgrade(config, "a832e94d6f10")
        assert set(inspect(connection).get_table_names()) == before - {
            "portfolio_ledger_publications"
        }
        alembic_command.upgrade(config, "head")
        alembic_command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == before
        assert {
            item["name"]
            for item in inspect(connection).get_columns("portfolio_ledger_publications")
        } == set(Base.metadata.tables["portfolio_ledger_publications"].columns.keys())
    portfolio_id, row = accepted(storage_engine)
    receipt = publish(
        storage_engine, portfolio_id, row.id, command(preview(storage_engine, portfolio_id, row.id))
    )
    with (
        pytest.raises(RuntimeError, match="Reviewed recovery"),
        storage_engine.begin() as connection,
    ):
        config = alembic_config()
        config.attributes["connection"] = connection
        alembic_command.downgrade(config, "a832e94d6f10")
    with Session(storage_engine) as session:
        result = publication.ownership(session, portfolio_id).latest_publication
        assert result and result.id == receipt.id


def test_workbook_preview_reports_source_ownership_blocker(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio_api import workbook_sync

    portfolio_id, row = accepted(storage_engine)
    publish(
        storage_engine, portfolio_id, row.id, command(preview(storage_engine, portfolio_id, row.id))
    )
    original = legacy_import._stable_id
    monkeypatch.setattr(
        legacy_import,
        "_stable_id",
        lambda kind, key: (
            portfolio_id if (kind, key) == ("portfolio", "legacy-default") else original(kind, key)
        ),
    )
    workbook = legacy_import.Workbook(Path("synthetic-unopened.xlsx"), "a" * 64, {})
    plan = legacy_import.ImportPlan(
        portfolio_workbook=workbook,
        market_workbook=workbook,
        observed_at=row.as_of + timedelta(days=1),
        source_digest="b" * 64,
    )
    with Session(storage_engine) as session:
        issues = workbook_sync._source_change_guard(session, plan)
    assert any(issue["code"] == "HOLDINGS_OWNERSHIP_TRANSFERRED" for issue in issues)


def test_api_publication_failure_rolls_back_then_exact_retry_reads_canonical_state(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id, row = accepted(storage_engine)
    plan = preview(storage_engine, portfolio_id, row.id)
    before = baseline(storage_engine, portfolio_id)
    original = publication.publish

    def fail(
        session: Session, portfolio_id: UUID, candidate_id: UUID, value: c.LedgerPublicationCreate
    ) -> c.LedgerPublicationRead:
        original(session, portfolio_id, candidate_id, value)
        raise services.DomainError("Injected post-publication failure", status=409)

    path = f"/v1/portfolios/{portfolio_id}/ledger/candidates/{row.id}/publish"
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        monkeypatch.setattr(publication, "publish", fail)
        assert client.post(path, json=command(plan).model_dump(mode="json")).status_code == 409
        assert baseline(storage_engine, portfolio_id) == before
        monkeypatch.setattr(publication, "publish", original)
        result = client.post(path, json=command(plan).model_dump(mode="json"))
        assert result.status_code == 200 and result.json()["sequence"] == 1
        snapshot_id = result.json()["snapshot"]["id"]
        assert (
            client.get(f"/v1/portfolios/{portfolio_id}/overview").json()["snapshot"]["id"]
            == snapshot_id
        )
        assert (
            client.post(path, json=command(plan).model_dump(mode="json")).json()["replayed"] is True
        )


def test_unlinked_snapshot_cannot_silently_override_ledger_read_model(
    storage_engine: Engine,
) -> None:
    portfolio_id, row = accepted(storage_engine)
    publish(
        storage_engine, portfolio_id, row.id, command(preview(storage_engine, portfolio_id, row.id))
    )
    with Session(storage_engine) as session, session.begin():
        session.add(
            HoldingSnapshot(
                portfolio_id=portfolio_id,
                effective_at=row.as_of + timedelta(days=1),
                actor="IMPORT",
                reason="Synthetic invalid bypass",
                completeness="COMPLETE",
            )
        )
    with (
        Session(storage_engine) as session,
        pytest.raises(services.DomainError, match="conflict with accepted ledger"),
    ):
        queries.overview(session, portfolio_id)


@pytest.mark.parametrize("field", ["publication_id", "opening_snapshot_id", "cutover_at"])
def test_ledger_ownership_metadata_requires_complete_provenance(field: str) -> None:
    from pydantic import ValidationError

    values = {
        "source": "ACCEPTED_LEDGER",
        "publication_id": uuid4(),
        "opening_snapshot_id": uuid4(),
        "cutover_at": datetime.now(UTC),
    }
    values[field] = None
    with pytest.raises(ValidationError):
        s.HoldingsAuthorityRead.model_validate(values)
