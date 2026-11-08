"""Synthetic isolated PostgreSQL review, correction, replay and authority boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from browser_server import fixture_application, fixture_settings
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_portfolio_ledger_api import baseline, candidate, ending_candidate, source
from test_portfolio_ledger_storage import storage_engine as storage_engine

from portfolio_api import portfolio_ledger as ledger
from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api import portfolio_ledger_reviews as reviews
from portfolio_api.database_write_target import install_database_write_target_guard
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    Listing,
    Portfolio,
    PortfolioLedgerCandidate,
    PortfolioLedgerReview,
)

pytestmark = pytest.mark.integration


def prepare(engine: Engine) -> tuple[UUID, c.PortfolioLedgerPreviewCreate]:
    portfolio_id = source(engine)
    with Session(engine) as session:
        anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
    packet = candidate(anchor)
    packet.ending_statement = ending_candidate(anchor, packet)
    return portfolio_id, packet


def submit(
    engine: Engine,
    portfolio_id: UUID,
    packet: c.PortfolioLedgerPreviewCreate,
    base: UUID | None = None,
    reason: str = "Review synthetic broker statement",
) -> c.LedgerCandidateCreate:
    with Session(engine) as session:
        preview = ledger.preview_portfolio_ledger(session, portfolio_id, packet)
    return c.LedgerCandidateCreate(
        submission_id=uuid4(),
        expected_base_candidate_id=base,
        expected_input_sha256=preview.input_sha256,
        reason=reason,
        proposal=packet,
    )


def stage(
    engine: Engine, portfolio_id: UUID, value: c.LedgerCandidateCreate
) -> c.LedgerCandidateRead:
    with Session(engine) as session, session.begin():
        return reviews.stage_candidate(session, portfolio_id, value)


def accept(value: c.LedgerCandidateRead) -> c.LedgerAcceptCreate:
    return c.LedgerAcceptCreate(
        decision="ACCEPT",
        expected_base_candidate_id=value.base_candidate_id,
        expected_input_sha256=value.input_sha256,
        expected_preview_sha256=value.preview_sha256,
        reason="Reviewed synthetic source and complete replacement scope",
        source_evidence_reviewed=True,
        account_allocation_reviewed=True,
        settled_balance_basis_reviewed=True,
        full_replacement_reviewed=True,
        acknowledged_removed_activity_ids=value.changes.removed_activity_ids,
        acknowledged_changed_activity_ids=value.changes.changed_activity_ids,
    )


def decide(
    engine: Engine, portfolio_id: UUID, candidate_id: UUID, value: c.LedgerReviewCreate
) -> c.LedgerCandidateRead:
    with Session(engine) as session, session.begin():
        return reviews.review_candidate(session, portfolio_id, candidate_id, value)


def protected(engine: Engine, portfolio_id: UUID) -> dict[str, object]:
    state = baseline(engine, portfolio_id)
    counts = cast(dict[str, int], state["counts"])
    state["counts"] = {
        key: value
        for key, value in counts.items()
        if key not in {"portfolio_ledger_candidates", "portfolio_ledger_reviews"}
    }
    return state


def receipt_counts(engine: Engine) -> tuple[int, int]:
    with Session(engine) as session:
        return (
            session.scalar(select(func.count()).select_from(PortfolioLedgerCandidate)) or 0,
            session.scalar(select(func.count()).select_from(PortfolioLedgerReview)) or 0,
        )


def test_staging_review_replay_and_history_preserve_canonical_snapshot(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    before = protected(storage_engine, portfolio_id)
    request = submit(storage_engine, portfolio_id, packet)
    first = stage(storage_engine, portfolio_id, request)
    assert first.status == "PENDING" and first.preview_status == "ENDING_RECONCILED"
    assert any(row.balance == Decimal("0") for row in first.packet.accounts[0].cash)
    assert any(row.balance == Decimal("89.65") for row in first.preview.cash)
    replay = stage(storage_engine, portfolio_id, request)
    assert replay.replayed and replay.id == first.id
    reordered = request.model_copy(deep=True, update={"submission_id": uuid4()})
    reordered.proposal.accounts[0].positions.reverse()
    reordered.proposal.accounts[0].cash.reverse()
    assert stage(storage_engine, portfolio_id, reordered).id == first.id
    accepted = decide(storage_engine, portfolio_id, first.id, accept(first))
    assert accepted.status == "ACCEPTED" and accepted.review is not None
    assert accepted.review.revision_number == 1 and accepted.review.reviewed_by == "LOCAL_USER"
    assert decide(storage_engine, portfolio_id, first.id, accept(first)).replayed
    assert receipt_counts(storage_engine) == (1, 1)
    with Session(storage_engine) as session:
        history = reviews.list_candidates(session, portfolio_id)
        assert (
            history.current_accepted_candidate_id == first.id
            and history.current_revision_number == 1
        )
        assert history.candidates[0].review == accepted.review
        assert reviews.candidate_read(session, portfolio_id, first.id).preview == first.preview
    assert protected(storage_engine, portfolio_id) == before


def test_stage_hash_submission_scope_and_packet_changes_fail_atomically(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    with pytest.raises(services.DomainError, match="hash changed"):
        stage(
            storage_engine,
            portfolio_id,
            request.model_copy(update={"expected_input_sha256": "a" * 64}),
        )
    assert receipt_counts(storage_engine) == (0, 0)
    first = stage(storage_engine, portfolio_id, request)
    changed = request.model_copy(deep=True)
    changed.proposal.activity[0].evidence.source_record_id = "other-source"
    with pytest.raises(services.DomainError, match="Submission ID conflicts"):
        stage(storage_engine, portfolio_id, changed)
    with Session(storage_engine) as session, session.begin():
        other = Portfolio(name="Other synthetic portfolio", base_currency="EUR")
        session.add(other)
        session.flush()
        other_id = other.id
    with pytest.raises(services.DomainError, match="Submission ID conflicts"):
        stage(storage_engine, other_id, request)
    assert receipt_counts(storage_engine) == (1, 0)
    assert first.id == request.submission_id


@pytest.mark.parametrize("mode", ["opening_only", "blocked"])
def test_unreconciled_candidate_can_only_be_rejected(storage_engine: Engine, mode: str) -> None:
    portfolio_id, packet = prepare(storage_engine)
    if mode == "opening_only":
        packet.ending_statement = None
    else:
        assert packet.ending_statement
        packet.ending_statement.accounts[0].cash[0].balance = Decimal("0")
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    with pytest.raises(services.DomainError, match="complete matching"):
        decide(storage_engine, portfolio_id, first.id, accept(first))
    assert receipt_counts(storage_engine) == (1, 0)
    rejection = c.LedgerRejectCreate(
        decision="REJECT",
        expected_base_candidate_id=None,
        expected_input_sha256=first.input_sha256,
        expected_preview_sha256=first.preview_sha256,
        reason="Missing independent statement coverage",
    )
    rejected = decide(storage_engine, portfolio_id, first.id, rejection)
    assert (
        rejected.status == "REJECTED"
        and rejected.review
        and rejected.review.revision_number is None
    )
    assert decide(storage_engine, portfolio_id, first.id, rejection).replayed
    with pytest.raises(services.DomainError, match="terminal review"):
        decide(storage_engine, portfolio_id, first.id, accept(first))


@pytest.mark.parametrize(
    "field", ["expected_input_sha256", "expected_preview_sha256", "expected_base_candidate_id"]
)
def test_review_is_bound_to_exact_hashes_and_base(storage_engine: Engine, field: str) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    value = accept(first).model_copy(
        update={field: uuid4() if field == "expected_base_candidate_id" else "a" * 64}
    )
    with pytest.raises(services.DomainError, match="exact candidate"):
        decide(storage_engine, portfolio_id, first.id, value)
    assert receipt_counts(storage_engine) == (1, 0)


def test_complete_replacement_correction_requires_explicit_changed_and_removed_ids(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    decide(storage_engine, portfolio_id, first.id, accept(first))
    modified = packet.model_copy(deep=True)
    modified.activity[0].evidence.source_record_id = "corrected-source-record"
    second = stage(
        storage_engine, portfolio_id, submit(storage_engine, portfolio_id, modified, first.id)
    )
    assert second.changes.changed_activity_ids == [packet.activity[0].id]
    with pytest.raises(services.DomainError, match="explicitly acknowledge"):
        decide(
            storage_engine,
            portfolio_id,
            second.id,
            accept(second).model_copy(update={"acknowledged_changed_activity_ids": []}),
        )
    accepted_second = decide(storage_engine, portfolio_id, second.id, accept(second))
    assert accepted_second.review and accepted_second.review.revision_number == 2
    removed = modified.model_copy(deep=True, update={"activity": []})
    assert removed.ending_statement
    removed.ending_statement.accounts[0].positions = removed.accounts[0].positions
    removed.ending_statement.accounts[0].cash = removed.accounts[0].cash
    third = stage(
        storage_engine, portfolio_id, submit(storage_engine, portfolio_id, removed, second.id)
    )
    assert third.changes.removed_activity_ids == [packet.activity[0].id]
    with pytest.raises(services.DomainError, match="explicitly acknowledge"):
        decide(
            storage_engine,
            portfolio_id,
            third.id,
            accept(third).model_copy(update={"acknowledged_removed_activity_ids": []}),
        )
    accepted_third = decide(storage_engine, portfolio_id, third.id, accept(third))
    assert accepted_third.review and accepted_third.review.revision_number == 3
    assert receipt_counts(storage_engine) == (3, 3)
    with Session(storage_engine) as session:
        assert len(reviews.candidate_read(session, portfolio_id, first.id).packet.activity) == 1
        original = reviews.candidate_read(session, portfolio_id, first.id)
        assert original.review and original.review.revision_number == 1


def test_stale_base_conflicts_and_rejection_remains_available(storage_engine: Engine) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    first = stage(storage_engine, portfolio_id, request)
    alternative = stage(
        storage_engine,
        portfolio_id,
        request.model_copy(
            update={"submission_id": uuid4(), "reason": "Alternative separately reviewed packet"}
        ),
    )
    decide(storage_engine, portfolio_id, first.id, accept(first))
    with pytest.raises(services.DomainError, match="base changed"):
        decide(storage_engine, portfolio_id, alternative.id, accept(alternative))
    with pytest.raises(services.DomainError, match="base changed"):
        stage(
            storage_engine,
            portfolio_id,
            request.model_copy(update={"submission_id": uuid4(), "reason": "stale new request"}),
        )
    rejected = c.LedgerRejectCreate(
        decision="REJECT",
        expected_base_candidate_id=None,
        expected_input_sha256=alternative.input_sha256,
        expected_preview_sha256=alternative.preview_sha256,
        reason="Superseded base",
    )
    assert decide(storage_engine, portfolio_id, alternative.id, rejected).status == "REJECTED"
    assert stage(storage_engine, portfolio_id, request).replayed


@pytest.mark.parametrize("change", ["listing", "snapshot", "calculation"])
def test_fresh_acceptance_rejects_source_or_calculation_drift(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    if change == "listing":
        with Session(storage_engine) as session, session.begin():
            listing = session.get(Listing, packet.accounts[0].positions[0].listing_id)
            assert listing
            listing.identity_source_ref = "new-reviewed-identity"
    elif change == "snapshot":
        from portfolio_api.domain.schemas import SnapshotCreate

        with Session(storage_engine) as session, session.begin():
            anchor = ledger.portfolio_ledger_anchor(session, portfolio_id)
            services.record_holdings(
                session,
                portfolio_id,
                SnapshotCreate(
                    actor="IMPORT",
                    reason="New synthetic observation",
                    source="new-statement",
                    effective_at=anchor.snapshot.effective_at + timedelta(days=1),
                    completeness="COMPLETE",
                    positions=[row.model_dump() for row in anchor.snapshot.positions],
                    cash_positions=[row.model_dump() for row in anchor.snapshot.cash_positions],
                ),
            )
    else:
        original = ledger.preview_portfolio_ledger

        def altered(
            session: Session, portfolio_id: UUID, value: c.PortfolioLedgerPreviewCreate
        ) -> c.PortfolioLedgerPreviewRead:
            return original(session, portfolio_id, value).model_copy(update={"activity_count": 999})

        monkeypatch.setattr(ledger, "preview_portfolio_ledger", altered)
    with pytest.raises(services.DomainError):
        decide(storage_engine, portfolio_id, first.id, accept(first))
    assert receipt_counts(storage_engine) == (1, 0)
    with Session(storage_engine) as session:
        assert reviews.candidate_read(session, portfolio_id, first.id).preview == first.preview


def test_concurrent_submission_and_review_produce_one_receipt_each(storage_engine: Engine) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: stage(
                    storage_engine,
                    portfolio_id,
                    request.model_copy(update={"submission_id": uuid4()}),
                ),
                range(2),
            )
        )
    assert len({row.id for row in results}) == 1 and sum(row.replayed for row in results) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = list(
            pool.map(
                lambda _: decide(storage_engine, portfolio_id, results[0].id, accept(results[0])),
                range(2),
            )
        )
    assert sum(row.replayed for row in accepted) == 1 and receipt_counts(storage_engine) == (1, 1)


def test_outer_rollback_removes_staged_packet_and_review(storage_engine: Engine) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    before = protected(storage_engine, portfolio_id)
    with Session(storage_engine) as session:
        first = reviews.stage_candidate(session, portfolio_id, request)
        reviews.review_candidate(session, portfolio_id, first.id, accept(first))
        session.rollback()
    assert (
        receipt_counts(storage_engine) == (0, 0)
        and protected(storage_engine, portfolio_id) == before
    )


def test_authenticated_api_read_history_and_explicit_review(storage_engine: Engine) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    settings = fixture_settings().model_copy(
        update={"app_env": "staging", "api_access_token": SecretStr("synthetic-owner-token")}
    )
    headers = {"x-api-access-token": "synthetic-owner-token"}
    path = f"/v1/portfolios/{portfolio_id}/ledger/candidates"
    with TestClient(fixture_application(storage_engine, settings)) as client:
        assert client.post(path, json=request.model_dump(mode="json")).status_code == 401
        assert (
            client.post(
                path,
                headers={"x-model-proposal-token": "synthetic-owner-token"},
                json=request.model_dump(mode="json"),
            ).status_code
            == 401
        )
        response = client.post(path, headers=headers, json=request.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        first = c.LedgerCandidateRead.model_validate(response.json())
        assert client.get(path, headers=headers).json()["candidates"][0]["id"] == str(first.id)
        assert client.get(path + "?limit=101", headers=headers).status_code == 422
        body = accept(first).model_dump(mode="json")
        body["source_evidence_reviewed"] = False
        assert (
            client.post(f"{path}/{first.id}/review", headers=headers, json=body).status_code == 422
        )
        body = accept(first).model_dump(mode="json")
        response = client.post(f"{path}/{first.id}/review", headers=headers, json=body)
        assert response.status_code == 200 and response.json()["status"] == "ACCEPTED"
        assert (
            client.get(f"{path}/{first.id}", headers=headers).json()["review"]["revision_number"]
            == 1
        )
        assert (
            client.get(
                f"/v1/portfolios/{uuid4()}/ledger/candidates/{first.id}", headers=headers
            ).status_code
            == 404
        )
    assert receipt_counts(storage_engine) == (1, 1)


def test_production_flag_off_and_existing_target_guard_block_mutations(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    path = f"/v1/portfolios/{portfolio_id}/ledger/candidates"
    settings = fixture_settings().model_copy(
        update={
            "app_env": "production",
            "database_target_environment": "production",
            "api_access_token": SecretStr("synthetic-token"),
            "database_production_writes_authorized": False,
        }
    )
    headers = {"x-api-access-token": "synthetic-token"}
    with TestClient(fixture_application(storage_engine, settings)) as client:
        assert (
            client.post(path, headers=headers, json=request.model_dump(mode="json")).status_code
            == 403
        )
    # An app labelled development still cannot bypass the installed central target guard.
    guard_settings = fixture_settings().model_copy(
        update={
            "database_target_environment": "production",
            "database_production_writes_authorized": False,
        }
    )
    with storage_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    assert isinstance(schema, str) and schema.startswith("test_")
    guarded = create_engine(
        storage_engine.url,
        hide_parameters=True,
        connect_args={
            "options": f"-c search_path={schema}",
            "connect_timeout": 3,
        },
    )
    try:
        install_database_write_target_guard(guarded, guard_settings, operation="api_request")
        with TestClient(fixture_application(guarded, fixture_settings())) as client:
            assert client.post(path, json=request.model_dump(mode="json")).status_code == 403
    finally:
        guarded.dispose()
    assert receipt_counts(storage_engine) == (0, 0)


def test_tampered_private_storage_fails_closed_without_leaking_payload(
    storage_engine: Engine,
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    with storage_engine.begin() as connection:
        connection.execute(
            text("UPDATE portfolio_ledger_candidates SET packet_sha256 = :hash WHERE id = :id"),
            {"hash": "a" * 64, "id": first.id},
        )
    with pytest.raises(services.DomainError, match="integrity validation"):
        decide(storage_engine, portfolio_id, first.id, accept(first))
    assert receipt_counts(storage_engine) == (1, 0)


def test_review_acknowledgements_require_unique_exact_ids() -> None:
    with pytest.raises(ValidationError):
        c.LedgerAcceptCreate(
            decision="ACCEPT",
            expected_base_candidate_id=None,
            expected_input_sha256="a" * 64,
            expected_preview_sha256="b" * 64,
            reason="Synthetic review",
            source_evidence_reviewed=True,
            account_allocation_reviewed=True,
            settled_balance_basis_reviewed=True,
            full_replacement_reviewed=True,
            acknowledged_removed_activity_ids=[UUID(int=1), UUID(int=1)],
            acknowledged_changed_activity_ids=[],
        )


def test_retained_identity_map_is_refreshed_under_source_locks(storage_engine: Engine) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    listing_id = next(
        item.listing_id
        for item in first.preview.consumed_listings
        if item.security_type == "COMMON_STOCK"
    )
    with Session(storage_engine) as session:
        retained = session.get(Listing, listing_id)
        assert retained and retained.identity_source_ref is None
        with Session(storage_engine) as concurrent, concurrent.begin():
            listing = concurrent.get(Listing, listing_id)
            assert listing
            listing.identity_source_ref = "changed-in-concurrent-session"
        with pytest.raises(services.DomainError):
            reviews.review_candidate(session, portfolio_id, first.id, accept(first))
        assert retained.identity_source_ref == "changed-in-concurrent-session"
        session.rollback()
    assert receipt_counts(storage_engine) == (1, 0)


def test_api_failure_after_flush_rolls_back_every_receipt(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    original = reviews.stage_candidate

    def fail(
        session: Session, portfolio_id: UUID, value: c.LedgerCandidateCreate
    ) -> c.LedgerCandidateRead:
        original(session, portfolio_id, value)
        raise services.DomainError("Injected atomicity check", status=409)

    monkeypatch.setattr(reviews, "stage_candidate", fail)
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        assert (
            client.post(
                f"/v1/portfolios/{portfolio_id}/ledger/candidates",
                json=request.model_dump(mode="json"),
            ).status_code
            == 409
        )
    assert receipt_counts(storage_engine) == (0, 0)


@pytest.mark.parametrize("change", ["anchor", "accounts", "cutoff", "duplicate"])
def test_correction_cannot_rebase_or_duplicate_current_acceptance(
    storage_engine: Engine, change: str
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    decide(storage_engine, portfolio_id, first.id, accept(first))
    request = submit(storage_engine, portfolio_id, packet, first.id)
    if change == "anchor":
        request.proposal.anchor_sha256 = "a" * 64
    elif change == "accounts":
        request.proposal.accounts[0].account_id = uuid4()
    elif change == "cutoff":
        request.proposal.as_of -= timedelta(seconds=1)
    with pytest.raises(services.DomainError):
        stage(storage_engine, portfolio_id, request)
    assert receipt_counts(storage_engine) == (1, 1)


def test_review_history_queries_use_read_only_repeatable_read(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    original = reviews.list_candidates
    observed = []

    def inspect(session: Session, portfolio_id: UUID, limit: int = 30) -> c.LedgerCandidatesRead:
        observed.append(
            (
                session.scalar(text("SHOW transaction_read_only")),
                session.scalar(text("SHOW transaction_isolation")),
            )
        )
        return original(session, portfolio_id, limit)

    monkeypatch.setattr(reviews, "list_candidates", inspect)
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        response = client.get(f"/v1/portfolios/{portfolio_id}/ledger/candidates")
        assert response.status_code == 200 and response.json()["candidates"][0]["id"] == str(
            first.id
        )
    assert observed == [("on", "repeatable read")]
    assert receipt_counts(storage_engine) == (1, 0)


def test_failed_api_acceptance_rolls_back_review_receipt(
    storage_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio_id, packet = prepare(storage_engine)
    first = stage(storage_engine, portfolio_id, submit(storage_engine, portfolio_id, packet))
    original = reviews.review_candidate

    def fail(
        session: Session, portfolio_id: UUID, candidate_id: UUID, value: c.LedgerReviewCreate
    ) -> c.LedgerCandidateRead:
        original(session, portfolio_id, candidate_id, value)
        raise services.DomainError("Injected post-review failure", status=409)

    monkeypatch.setattr(reviews, "review_candidate", fail)
    with TestClient(fixture_application(storage_engine, fixture_settings())) as client:
        assert (
            client.post(
                f"/v1/portfolios/{portfolio_id}/ledger/candidates/{first.id}/review",
                json=accept(first).model_dump(mode="json"),
            ).status_code
            == 409
        )
    assert receipt_counts(storage_engine) == (1, 0)
