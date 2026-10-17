from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    GoogleSheetsSyncCandidate,
    ResearchAgentWorkEvent,
    ResearchQueueCompletion,
)
from portfolio_api.google_sheets_sync import ConnectionResult, ContractBlock, InboxSnapshot
from portfolio_api.research_agent_operations import (
    ResearchAgentOperationError,
    _record_delivery,
    deliver_agent_work,
    proposal_status,
    record_agent_acknowledgment,
    record_delivery_failure,
    run_acknowledgment_inbox_check,
)
from portfolio_api.settings import Settings


def _delivery(
    session: Session,
    fingerprint: str,
    *,
    recorded_at: datetime | None = None,
    channel: str = "API",
) -> ResearchAgentWorkEvent:
    return _record_delivery(
        session,
        role="PORTFOLIO_THESIS_SENTINEL",
        work_type="TRIGGER",
        work_key="trigger-1",
        fingerprint=fingerprint,
        channel=channel,
        payload={"source": fingerprint},
        recorded_at=recorded_at or datetime.now(UTC),
    )


def _acknowledgment(
    fingerprint: str,
    external_update_id: str,
    *,
    status: str = "COMPLETED",
    reason: str | None = None,
    channel: str = "API",
) -> s.ResearchAgentAcknowledgmentContractV1:
    return s.ResearchAgentAcknowledgmentContractV1(
        agent_role="PORTFOLIO_THESIS_SENTINEL",
        work_type="TRIGGER",
        work_key="trigger-1",
        work_fingerprint=fingerprint,
        external_update_id=external_update_id,
        delivery_channel=channel,
        agent_run_id="sentinel-run-1",
        actor_id="sentinel-agent",
        status=status,
        observed_at=datetime.now(UTC),
        reason=reason,
    )


def test_blocked_agent_acknowledgment_requires_reason() -> None:
    with pytest.raises(ValueError, match="SOURCE_UNAVAILABLE requires an explicit reason"):
        _acknowledgment("f" * 64, "unavailable-1", status="SOURCE_UNAVAILABLE")


@pytest.mark.integration
def test_retrieval_is_idempotent_and_completed_work_is_not_redelivered(
    postgres_engine: Engine,
) -> None:
    cutoff = datetime(2026, 10, 15, 9, tzinfo=UTC)
    request = s.ResearchAgentWorkRequest(as_of=cutoff, limit=50)
    with Session(postgres_engine) as session, session.begin():
        first = deliver_agent_work(session, "DATA_UNIVERSE_STEWARD", request)
        second = deliver_agent_work(session, "DATA_UNIVERSE_STEWARD", request)
        assert [item.delivery_id for item in first.items] == [
            item.delivery_id for item in second.items
        ]
        assert [item.work_fingerprint for item in first.items] == [
            item.work_fingerprint for item in second.items
        ]
        assert first.items
        assert session.scalar(
            select(func.count())
            .select_from(ResearchAgentWorkEvent)
            .where(ResearchAgentWorkEvent.event_type == "DELIVERY_SUCCEEDED")
        ) == len(first.items)

    with Session(postgres_engine) as session, session.begin():
        item = first.items[0]
        acknowledgment = s.ResearchAgentAcknowledgmentContractV1(
            agent_role=first.agent_role,
            work_type=item.work_type,
            work_key=item.work_key,
            work_fingerprint=item.work_fingerprint,
            external_update_id="data-check-1",
            agent_run_id="data-run-1",
            actor_id="data-steward",
            status="COMPLETED",
            observed_at=cutoff,
        )
        record_agent_acknowledgment(session, acknowledgment)
        replay = deliver_agent_work(session, "DATA_UNIVERSE_STEWARD", request)
        assert item.delivery_id not in {row.delivery_id for row in replay.items}
        assert session.scalar(select(func.count()).select_from(ResearchQueueCompletion)) == 0


@pytest.mark.integration
def test_acknowledgment_replay_is_idempotent_and_changed_replay_conflicts(
    postgres_engine: Engine,
) -> None:
    fingerprint = hashlib.sha256(b"trigger version 1").hexdigest()
    with Session(postgres_engine) as session, session.begin():
        _delivery(session, fingerprint)
        value = _acknowledgment(fingerprint, "sentinel-update-1")
        first = record_agent_acknowledgment(session, value)
        replay = record_agent_acknowledgment(session, value)
        assert first.result == "RECORDED"
        assert replay.result == "ALREADY_RECORDED"
        assert replay.acknowledgment.id == first.acknowledgment.id
        assert replay.acknowledgment.status == "COMPLETED"
        with pytest.raises(ResearchAgentOperationError, match="different acknowledgment content"):
            record_agent_acknowledgment(
                session,
                value.model_copy(update={"status": "BLOCKED", "reason": "Changed outcome"}),
            )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchAgentWorkEvent)
                .where(ResearchAgentWorkEvent.event_type == "COMPLETED")
            )
            == 1
        )


@pytest.mark.integration
def test_old_delivery_is_recorded_stale_after_new_source_and_unknown_delivery_blocks(
    postgres_engine: Engine,
) -> None:
    old_fingerprint = "a" * 64
    new_fingerprint = "b" * 64
    first_time = datetime(2026, 10, 14, 9, tzinfo=UTC)
    with Session(postgres_engine) as session, session.begin():
        _delivery(session, old_fingerprint, recorded_at=first_time)
        _delivery(session, new_fingerprint, recorded_at=first_time + timedelta(hours=1))
        stale = record_agent_acknowledgment(
            session, _acknowledgment(old_fingerprint, "stale-update-1")
        )
        assert stale.acknowledgment.status == "STALE_SOURCE"
        assert stale.acknowledgment.blocker_code == "STALE_DELIVERY"
        with pytest.raises(ResearchAgentOperationError, match="no matching successful delivery"):
            record_agent_acknowledgment(session, _acknowledgment("c" * 64, "unknown-update-1"))


@pytest.mark.integration
def test_proposal_status_lookup_keeps_missing_candidates_explicit(
    postgres_engine: Engine,
) -> None:
    with (
        Session(postgres_engine) as session,
        pytest.raises(ResearchAgentOperationError, match="model proposal was not found"),
    ):
        proposal_status(session, "MODEL", uuid4())


@pytest.mark.integration
def test_proposal_status_reports_conflict_and_reviewer_context(
    postgres_engine: Engine,
) -> None:
    candidate_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            GoogleSheetsSyncCandidate(
                id=candidate_id,
                idempotency_key=hashlib.sha256(str(candidate_id).encode()).hexdigest(),
                spreadsheet_id="spreadsheet-test",
                spreadsheet_title="Test workbook",
                sheet_id=1,
                sheet_title="Model Sync Inbox",
                source_row_number=2,
                source_url="https://docs.google.com/spreadsheets/d/test",
                contract_text="{}",
                content_fingerprint="a" * 64,
                raw_sha256="b" * 64,
                external_revision_id="model-external-1",
                status="CONFLICT",
                issue="The canonical model base has advanced.",
                reviewer="reviewer-1",
                decision_note="Refresh the external base before resubmission.",
                last_observed_at=datetime.now(UTC),
            )
        )
        session.flush()
        status = proposal_status(session, "MODEL", candidate_id)
        assert status.status == "CONFLICT"
        assert status.issue == "The canonical model base has advanced."
        assert status.reviewer == "reviewer-1"


@pytest.mark.integration
def test_failed_publication_attempt_and_retry_are_separate_receipts(
    postgres_engine: Engine,
) -> None:
    fingerprint = hashlib.sha256(b"portfolio state").hexdigest()
    with Session(postgres_engine) as session, session.begin():
        failed, result = record_delivery_failure(
            session,
            role="MODEL_ALLOCATION_STEWARD",
            work_type="PORTFOLIO_STATE",
            work_key="portfolio-1",
            fingerprint=fingerprint,
            attempt_id="portfolio-publish-attempt-1",
            channel="GOOGLE_SHEETS",
            reason="READBACK_FAILED: response missing",
        )
        replay, replay_result = record_delivery_failure(
            session,
            role="MODEL_ALLOCATION_STEWARD",
            work_type="PORTFOLIO_STATE",
            work_key="portfolio-1",
            fingerprint=fingerprint,
            attempt_id="portfolio-publish-attempt-1",
            channel="GOOGLE_SHEETS",
            reason="READBACK_FAILED: response missing",
        )
        success = _record_delivery(
            session,
            role="MODEL_ALLOCATION_STEWARD",
            work_type="PORTFOLIO_STATE",
            work_key="portfolio-1",
            fingerprint=fingerprint,
            channel="GOOGLE_SHEETS",
            payload={"content_fingerprint": fingerprint},
            recorded_at=datetime.now(UTC),
        )
        assert result == "RECORDED"
        assert replay_result == "ALREADY_RECORDED"
        assert replay.id == failed.id
        assert success.id != failed.id
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchAgentWorkEvent)
                .where(ResearchAgentWorkEvent.work_key == "portfolio-1")
            )
            == 2
        )


class _AcknowledgmentReader:
    def __init__(self, blocks: list[ContractBlock]) -> None:
        self.blocks = blocks

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        return InboxSnapshot(ConnectionResult("Test research workbook", True, 10), self.blocks)


@pytest.mark.integration
def test_sheet_acknowledgment_inbox_accepts_multiple_blocks_and_replays(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        fingerprints = ["d" * 64, "e" * 64]
        for fingerprint in fingerprints:
            _delivery(session, fingerprint, channel="GOOGLE_SHEETS")
        blocks = []
        for index, fingerprint in enumerate(fingerprints):
            value = _acknowledgment(
                fingerprint,
                f"sheets-ack-{index}",
                channel="GOOGLE_SHEETS",
            )
            blocks.append(
                ContractBlock(
                    publish_id=f"publish-{index}",
                    external_revision_id=value.external_update_id,
                    first_row_number=index + 2,
                    contract_text=value.model_dump_json(),
                )
            )
        reader = _AcknowledgmentReader(blocks)
        settings = Settings(google_sheets_spreadsheet_id="a" * 25)
        first = run_acknowledgment_inbox_check(session, settings, reader)
        replay = run_acknowledgment_inbox_check(session, settings, reader)
        assert (first.status, first.captured, first.replayed) == ("COMPLETE", 2, 0)
        assert (replay.status, replay.captured, replay.replayed) == ("COMPLETE", 0, 2)
