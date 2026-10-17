import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.attention import _event, _recent_imported_output, deduplicate_and_order
from portfolio_api.domain.models import (
    ExecutionPaceDecision,
    FinancialModelRevision,
    HoldingSnapshot,
    ModelOutputSnapshot,
    Portfolio,
    PriceObservation,
    RankingRun,
    RiskAssessmentFinding,
    RiskAssessmentRevision,
    SourceDocument,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


def test_feed_deduplicates_by_source_and_orders_by_effective_then_recorded_time() -> None:
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    recent = _event(
        issuer=None,
        lifecycle=None,
        event_type="NEW_FILING",
        severity="MEDIUM",
        title="Recent filing",
        explanation="Same immutable source record.",
        effective_at=now - timedelta(days=1),
        recorded_at=now,
        source_domain="source_document",
        source_id="filing-1",
    )
    older = _event(
        issuer=None,
        lifecycle=None,
        event_type="MODEL_REVISION",
        severity="MEDIUM",
        title="Older revision",
        explanation="An older effective event.",
        effective_at=now - timedelta(days=2),
        recorded_at=now + timedelta(days=1),
        source_domain="model_revision",
        source_id="revision-1",
    )
    undated = _event(
        issuer=None,
        lifecycle=None,
        event_type="DATA_QUALITY",
        severity="LOW",
        status="REVIEW",
        title="Missing model value",
        explanation="No observation timestamp exists.",
        effective_at=None,
        recorded_at=None,
        source_domain="model_output_coverage",
        source_id="missing-1",
    )
    ordered = deduplicate_and_order([older, recent, recent, undated])
    assert [item.id for item in ordered] == [recent.id, older.id, undated.id]
    assert undated.effective_at is None
    assert undated.recorded_at is None
    assert undated.current_value is None
    assert undated.prior_value is None


def test_undated_output_import_is_not_made_recent_by_its_recorded_time() -> None:
    now = datetime(2026, 10, 10, 12, tzinfo=UTC)
    cutoff = now - timedelta(days=30)
    undated_backfill = ModelOutputSnapshot(effective_at=None, recorded_at=now - timedelta(days=1))
    dated_source_event = ModelOutputSnapshot(
        effective_at=now - timedelta(days=2), recorded_at=now - timedelta(days=1)
    )

    assert not _recent_imported_output(undated_backfill, cutoff, now)
    assert _recent_imported_output(dated_source_event, cutoff, now)


def test_attention_endpoint_is_filtered_and_read_only_for_missing_states(
    postgres_engine: Engine,
) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        company = client.post("/v1/companies", json={"name": "Attention Example"}).json()
        company_id = company["id"]
        lifecycle = client.post(
            f"/v1/companies/{company_id}/lifecycle-transitions",
            json={
                "actor": "LOCAL_USER",
                "reason": "Attention feed fixture",
                "source": "test",
                "effective_at": "2026-10-01T00:00:00Z",
                "expected_event_id": None,
                "new_state": "PORTFOLIO",
            },
        )
        assert lifecycle.status_code == 201

        assessed_at = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
        with Session(postgres_engine) as session, session.begin():
            portfolio = Portfolio(
                name="Attention risk portfolio",
                base_currency="EUR",
                is_demo=False,
            )
            session.add(portfolio)
            session.flush()
            snapshot = HoldingSnapshot(
                portfolio_id=portfolio.id,
                completeness="COMPLETE",
                effective_at=assessed_at,
                recorded_at=assessed_at,
                actor="IMPORT",
                reason="Risk finding snapshot reference",
                source="attention-test",
            )
            session.add(snapshot)
            session.flush()
            revision = RiskAssessmentRevision(
                portfolio_id=portfolio.id,
                stream_key="attention-risk-review",
                revision_number=1,
                contract_version="1.0.0",
                external_revision_id="risk-attention-1",
                supersedes_revision_id=None,
                author_id="research-agent",
                source_id="google-sheets",
                source_reference="https://docs.google.com/spreadsheets/d/example/edit",
                authored_at=assessed_at,
                published_at=assessed_at,
                recorded_at=assessed_at,
                reviewer="Research reviewer",
                reviewer_note="Reviewed stale baseline and source evidence.",
                accepted_at=assessed_at,
                baseline_status_at_accept="STALE_HOLDINGS",
                baseline_stale_acknowledged=True,
                portfolio_state_contract_version="1.0.0",
                portfolio_state_fingerprint="sha256:" + "a" * 64,
                holdings_snapshot_id=snapshot.id,
                target_revision_id=None,
                valuation_as_of=assessed_at,
                coverage_status="COMPLETE",
                coverage_note=None,
                summary="A new company risk needs review.",
                rationale="The agent cites a recent filing.",
                content_fingerprint=hashlib.sha256(b"attention-risk").hexdigest(),
            )
            session.add(revision)
            session.flush()
            session.add(
                RiskAssessmentFinding(
                    revision_id=revision.id,
                    finding_key="company.regulatory-exposure",
                    scope="COMPANY",
                    company_id=company_id,
                    category="REGULATORY",
                    title="Regulatory exposure increased",
                    description="A disclosure describes a material regulatory inquiry.",
                    severity="HIGH",
                    confidence="MEDIUM",
                    status="ACTIVE",
                    change_direction="NEW",
                    rationale="The filing indicates a newly elevated risk.",
                )
            )

        with Session(postgres_engine) as session:
            before = {
                model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in (
                    FinancialModelRevision,
                    PriceObservation,
                    RankingRun,
                    ExecutionPaceDecision,
                    SourceDocument,
                )
            }

        query = (
            f"/v1/attention?company_id={company_id}&event_type=DATA_QUALITY"
            "&lifecycle=PORTFOLIO&status=REVIEW"
        )
        first = client.get(query)
        second = client.get(query)
        assert first.status_code == 200
        assert second.status_code == 200
        body = first.json()
        assert body["events"] == second.json()["events"]
        assert body["total"] == second.json()["total"]
        assert body["total"] == 2
        assert {event["event_type"] for event in body["events"]} == {"DATA_QUALITY"}
        missing_model = next(
            event for event in body["events"] if event["source_domain"] == "model_output_coverage"
        )
        assert missing_model["effective_at"] is None
        assert missing_model["recorded_at"] is None
        assert missing_model["prior_value"] is None
        assert missing_model["current_value"] is None
        assert "unavailable" in missing_model["explanation"].lower()

        risk_feed = client.get(f"/v1/attention?company_id={company_id}&event_type=RISK_ASSESSMENT")
        assert risk_feed.status_code == 200
        risk_events = risk_feed.json()["events"]
        assert len(risk_events) == 1
        assert "stale holdings baseline" in risk_events[0]["explanation"].lower()
        assert "reviewer acknowledgement" in risk_events[0]["explanation"].lower()

        with Session(postgres_engine) as session:
            after = {
                model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in (
                    FinancialModelRevision,
                    PriceObservation,
                    RankingRun,
                    ExecutionPaceDecision,
                    SourceDocument,
                )
            }
        assert after == before
