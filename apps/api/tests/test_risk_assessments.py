"""Google Sheets risk-assessment contracts retain exact portfolio baselines and history."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    CashPosition,
    Company,
    GoogleSheetsRiskSyncCandidate,
    HoldingSnapshot,
    Portfolio,
    RiskAssessmentEvidence,
    RiskAssessmentFinding,
    RiskAssessmentRevision,
)
from portfolio_api.domain.services import DomainError
from portfolio_api.google_sheets_sync import (
    ConnectionResult,
    ContractBlock,
    InboxSnapshot,
)
from portfolio_api.portfolio_sheet_sync import portfolio_state_fingerprint
from portfolio_api.risk_assessments import (
    RISK_SYNC_TAB,
    accept_risk_candidate,
    company_risk_assessments,
    preview_risk_candidate,
    run_risk_sync_check,
)
from portfolio_api.settings import Settings


class FixtureRiskReader:
    def __init__(self, blocks: list[ContractBlock]) -> None:
        self.blocks = blocks

    def test_connection(self, spreadsheet_id: str, sync_tab: str) -> ConnectionResult:
        assert sync_tab == RISK_SYNC_TAB
        return ConnectionResult("Risk workbook fixture", True, 42)

    def read_inbox(self, spreadsheet_id: str, sync_tab: str) -> InboxSnapshot:
        assert spreadsheet_id == "r" * 24
        assert sync_tab == RISK_SYNC_TAB
        return InboxSnapshot(ConnectionResult("Risk workbook fixture", True, 42), self.blocks)


def portfolio_baseline(
    session: Session, *, older_snapshot: bool = False
) -> tuple[Portfolio, Company, HoldingSnapshot, datetime, str]:
    now = datetime.now(UTC).replace(microsecond=0)
    portfolio = Portfolio(name="Risk sync test portfolio", base_currency="EUR", is_demo=False)
    company = Company(name="Risk sync test company", reporting_currency="EUR", is_demo=False)
    session.add_all([portfolio, company])
    session.flush()
    effective_at = now - timedelta(minutes=30)
    snapshot = HoldingSnapshot(
        id=uuid4(),
        portfolio_id=portfolio.id,
        completeness="COMPLETE",
        effective_at=effective_at,
        recorded_at=effective_at,
        actor="IMPORT",
        reason="Fixture baseline",
        source="risk assessment integration test",
    )
    session.add(snapshot)
    session.flush()
    session.info["new_snapshot_ids"] = {snapshot.id}
    try:
        session.add(
            CashPosition(snapshot_id=snapshot.id, currency="EUR", balance=Decimal("1000.00"))
        )
        session.flush()
    finally:
        session.info.pop("new_snapshot_ids", None)
    session.flush()
    valuation_as_of = effective_at + timedelta(seconds=1)
    overview = q.overview(session, portfolio.id, valuation_as_of)
    assert overview.valuation_status == "VALUED"
    return portfolio, company, snapshot, valuation_as_of, portfolio_state_fingerprint(overview)


def contract(
    portfolio_id: UUID,
    company_id: UUID,
    snapshot_id: UUID,
    valuation_as_of: datetime,
    fingerprint: str,
    **changes: Any,
) -> s.RiskAssessmentContractV1:
    authored_at = valuation_as_of + timedelta(minutes=1)
    payload: dict[str, Any] = {
        "contract_type": "RiskAssessmentContractV1",
        "contract_version": "1.0.0",
        "portfolio_id": str(portfolio_id),
        "stream_key": "portfolio-risk-review",
        "external_revision_id": "risk-review-1",
        "supersedes_revision_id": None,
        "author_id": "investment-research-agent",
        "source_id": "google-sheets-risk-agent",
        "source_reference": "https://docs.google.com/spreadsheets/d/risk-fixture/edit",
        "authored_at": authored_at.isoformat(),
        "published_at": (authored_at + timedelta(minutes=1)).isoformat(),
        "portfolio_state_contract_version": "1.0.0",
        "portfolio_state_fingerprint": fingerprint,
        "holdings_snapshot_id": str(snapshot_id),
        "target_revision_id": None,
        "valuation_as_of": valuation_as_of.isoformat(),
        "coverage_status": "COMPLETE",
        "coverage_note": None,
        "summary": "Liquidity is adequate; one company exposure requires monitoring.",
        "rationale": "Assessment is linked to the latest published portfolio state.",
        "findings": [
            {
                "finding_key": "company.customer-concentration",
                "scope": "COMPANY",
                "company_id": str(company_id),
                "category": "BUSINESS",
                "title": "Customer concentration remains elevated",
                "description": (
                    "A small group of customers contributes a material share of revenue."
                ),
                "severity": "HIGH",
                "confidence": "MEDIUM",
                "status": "ACTIVE",
                "change_direction": "NEW",
                "rationale": (
                    "A recently published filing describes concentrated customer exposure."
                ),
                "evidence": [
                    {
                        "source_name": "Company annual report",
                        "source_url": "https://issuer.example.test/annual-report",
                        "published_at": "2026-10-01",
                        "note": "Customer concentration disclosure.",
                    }
                ],
            },
            {
                "finding_key": "portfolio.eur-concentration",
                "scope": "PORTFOLIO",
                "company_id": None,
                "category": "PORTFOLIO_CONCENTRATION",
                "title": "Portfolio cash concentration",
                "description": "Cash is concentrated in the base currency.",
                "severity": "LOW",
                "confidence": "HIGH",
                "status": "ACTIVE",
                "change_direction": "UNCHANGED",
                "rationale": "The deterministic portfolio snapshot shows EUR cash only.",
                "evidence": [
                    {
                        "source_name": "Application Portfolio State",
                        "external_identifier": f"snapshot:{snapshot_id}",
                    }
                ],
            },
        ],
    }
    payload.update(changes)
    return s.RiskAssessmentContractV1.model_validate(payload)


def capture(
    session: Session,
    value: s.RiskAssessmentContractV1,
    *,
    blocks: list[ContractBlock] | None = None,
) -> tuple[Any, Any]:
    selected = blocks or [
        ContractBlock(
            publish_id="publish-risk-1",
            external_revision_id=value.external_revision_id,
            first_row_number=2,
            contract_text=value.model_dump_json(),
        )
    ]
    result = run_risk_sync_check(
        session,
        Settings(google_sheets_spreadsheet_id="r" * 24),
        FixtureRiskReader(selected),
    )
    return result.run, result.new_candidates


def test_risk_contract_requires_sources_unique_findings_and_baseline_timestamps() -> None:
    now = datetime.now(UTC)
    required = {
        "contract_type": "RiskAssessmentContractV1",
        "contract_version": "1.0.0",
        "portfolio_id": str(uuid4()),
        "stream_key": "portfolio-review",
        "external_revision_id": "risk-1",
        "author_id": "agent",
        "source_id": "sheets",
        "source_reference": "https://docs.google.com/spreadsheets/d/example/edit",
        "authored_at": now.isoformat(),
        "published_at": now.isoformat(),
        "portfolio_state_contract_version": "1.0.0",
        "portfolio_state_fingerprint": "sha256:" + "a" * 64,
        "holdings_snapshot_id": str(uuid4()),
        "valuation_as_of": now.isoformat(),
        "coverage_status": "COMPLETE",
        "summary": "No material new risks.",
        "rationale": "Reviewed current published portfolio state.",
        "findings": [],
    }
    assert s.RiskAssessmentContractV1.model_validate(required).findings == []

    unsupported_source = {
        "source_name": "Unlocated source",
    }
    with pytest.raises(ValidationError, match="source reference"):
        s.RiskAssessmentEvidenceInput.model_validate(unsupported_source)
    with pytest.raises(ValidationError, match="HTTPS"):
        s.RiskAssessmentEvidenceInput.model_validate(
            {
                "source_name": "Issuer site",
                "source_url": "http://issuer.example.test/risk",
            }
        )
    required["authored_at"] = (now - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValidationError, match="predate its portfolio-state baseline"):
        s.RiskAssessmentContractV1.model_validate(required)


@pytest.mark.integration
def test_risk_sync_preview_acceptance_history_and_idempotent_replay(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        portfolio, company, snapshot, valuation_as_of, fingerprint = portfolio_baseline(session)
        value = contract(portfolio.id, company.id, snapshot.id, valuation_as_of, fingerprint)

        run, candidates = capture(session, value)
        assert run.status == "SUCCEEDED"
        assert len(candidates) == 1
        candidate_id = candidates[0].id
        preview = preview_risk_candidate(session, candidate_id)
        assert preview.status == "READY"
        assert preview.baseline_status == "CURRENT"
        assert preview.preview_data is not None
        assert preview.preview_data["finding_changes"]

        accepted = accept_risk_candidate(
            session, candidate_id, "reviewer@example.test", "Reviewed evidence and baseline."
        )
        assert accepted.status == "ACCEPTED"
        assert accepted.accepted_revision_id is not None
        assert accepted.baseline_status == "CURRENT"
        assert session.scalar(select(func.count()).select_from(RiskAssessmentRevision)) == 1
        assert session.scalar(select(func.count()).select_from(RiskAssessmentFinding)) == 2
        assert session.scalar(select(func.count()).select_from(RiskAssessmentEvidence)) == 2
        accepted_revision = session.get(RiskAssessmentRevision, accepted.accepted_revision_id)
        assert accepted_revision is not None
        with (
            pytest.raises(ValueError, match="Historical observations are append-only"),
            session.begin_nested(),
        ):
            accepted_revision.summary = "Attempted overwrite"
            session.flush()

        company_view = company_risk_assessments(session, company.id)
        assert len(company_view.current) == 1
        assert company_view.current[0].findings[0].evidence[0].source_url == (
            "https://issuer.example.test/annual-report"
        )

        replay_run, replay_candidates = capture(session, value)
        assert replay_run.unchanged_count == 1
        assert replay_candidates == []
        assert session.scalar(select(func.count()).select_from(RiskAssessmentRevision)) == 1


@pytest.mark.integration
def test_risk_sync_marks_stale_baseline_and_requires_explicit_acceptance_acknowledgement(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        portfolio, company, snapshot, valuation_as_of, fingerprint = portfolio_baseline(session)
        value = contract(
            portfolio.id,
            company.id,
            snapshot.id,
            valuation_as_of,
            fingerprint,
            external_revision_id="risk-stale-1",
        )
        _, candidates = capture(session, value)
        candidate_id = candidates[0].id

        later = datetime.now(UTC).replace(microsecond=0)
        newer_snapshot = HoldingSnapshot(
            id=uuid4(),
            portfolio_id=portfolio.id,
            completeness="COMPLETE",
            effective_at=later,
            recorded_at=later,
            actor="IMPORT",
            reason="Newer holdings snapshot",
            source="risk assessment integration test",
        )
        session.add(newer_snapshot)
        session.flush()
        session.info["new_snapshot_ids"] = {newer_snapshot.id}
        try:
            session.add(
                CashPosition(
                    snapshot_id=newer_snapshot.id,
                    currency="EUR",
                    balance=Decimal("1200.00"),
                )
            )
            session.flush()
        finally:
            session.info.pop("new_snapshot_ids", None)
        session.flush()

        preview = preview_risk_candidate(session, candidate_id)
        assert preview.status == "STALE_BASELINE"
        assert preview.baseline_status == "STALE_PORTFOLIO_STATE"
        with pytest.raises(DomainError, match="Explicitly acknowledge"):
            accept_risk_candidate(session, candidate_id, "reviewer", "Requires review")

        accepted = accept_risk_candidate(
            session,
            candidate_id,
            "reviewer",
            "Accepted with the earlier holdings baseline acknowledged.",
            acknowledge_stale_baseline=True,
        )
        assert accepted.status == "ACCEPTED"
        stored = session.get(RiskAssessmentRevision, accepted.accepted_revision_id)
        assert stored is not None
        assert stored.baseline_status_at_accept == "STALE_PORTFOLIO_STATE"
        assert stored.baseline_stale_acknowledged is True


@pytest.mark.integration
def test_risk_sync_rejects_unknown_sources_and_concurrent_revision_conflicts(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        portfolio, company, snapshot, valuation_as_of, fingerprint = portfolio_baseline(session)
        first = contract(portfolio.id, company.id, snapshot.id, valuation_as_of, fingerprint)
        _, candidates = capture(session, first)
        first_candidate_id = candidates[0].id
        first_accepted = accept_risk_candidate(
            session, first_candidate_id, "reviewer", "Accepted baseline assessment."
        )
        assert first_accepted.accepted_revision_id is not None

        malformed = contract(
            portfolio.id,
            company.id,
            snapshot.id,
            valuation_as_of,
            fingerprint,
            external_revision_id="risk-unknown-source",
            supersedes_revision_id=first_accepted.accepted_revision_id,
            findings=[
                {
                    "finding_key": "company.unknown-source",
                    "scope": "COMPANY",
                    "company_id": str(company.id),
                    "category": "BUSINESS",
                    "title": "Unverifiable claim",
                    "description": "This claim references an absent canonical source record.",
                    "severity": "MEDIUM",
                    "confidence": "LOW",
                    "status": "ACTIVE",
                    "change_direction": "NEW",
                    "rationale": "A source identifier must resolve before acceptance.",
                    "evidence": [
                        {
                            "source_name": "Unknown filing",
                            "source_document_id": str(uuid4()),
                        }
                    ],
                }
            ],
        )
        _, malformed_candidates = capture(session, malformed)
        invalid_preview = preview_risk_candidate(session, malformed_candidates[0].id)
        assert invalid_preview.status == "INVALID"
        assert "unknown source document" in (invalid_preview.issue or "")

        concurrent = contract(
            portfolio.id,
            company.id,
            snapshot.id,
            valuation_as_of,
            fingerprint,
            external_revision_id="risk-concurrent",
            supersedes_revision_id=uuid4(),
        )
        _, conflict_candidates = capture(session, concurrent)
        conflict_preview = preview_risk_candidate(session, conflict_candidates[0].id)
        assert conflict_preview.status == "CONFLICT"
        assert "newer risk assessment revision" in (conflict_preview.issue or "")


@pytest.mark.integration
def test_risk_sync_rejects_changed_content_reusing_external_revision_id(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        portfolio, company, snapshot, valuation_as_of, fingerprint = portfolio_baseline(session)
        original = contract(portfolio.id, company.id, snapshot.id, valuation_as_of, fingerprint)
        _, original_candidates = capture(session, original)
        accepted = accept_risk_candidate(
            session, original_candidates[0].id, "reviewer", "Accepted original revision."
        )
        assert accepted.accepted_revision_id is not None

        changed = original.model_copy(
            update={
                "summary": "Changed content reusing an already accepted external revision ID.",
                "rationale": "This must be a conflict, not an overwrite.",
            }
        )
        text = json.dumps(changed.model_dump(mode="json"), sort_keys=True)
        _, candidates = capture(
            session,
            changed,
            blocks=[
                ContractBlock(
                    publish_id="publish-changed-content",
                    external_revision_id=changed.external_revision_id,
                    first_row_number=3,
                    contract_text=text,
                )
            ],
        )
        assert len(candidates) == 1
        assert candidates[0].status == "CONFLICT"
        rows = session.scalars(select(GoogleSheetsRiskSyncCandidate)).all()
        conflicts = [row for row in rows if row.status == "CONFLICT"]
        assert len(conflicts) == 1
        assert "already used for different content" in (conflicts[0].issue or "")
        assert session.scalar(select(func.count()).select_from(RiskAssessmentRevision)) == 1


@pytest.mark.integration
def test_company_current_view_uses_latest_stream_revision_when_finding_is_cleared(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        portfolio, company, snapshot, valuation_as_of, fingerprint = portfolio_baseline(session)
        first = contract(portfolio.id, company.id, snapshot.id, valuation_as_of, fingerprint)
        _, first_candidates = capture(session, first)
        first_accepted = accept_risk_candidate(
            session, first_candidates[0].id, "reviewer", "Recorded the initial finding."
        )
        assert first_accepted.accepted_revision_id is not None

        second = contract(
            portfolio.id,
            company.id,
            snapshot.id,
            valuation_as_of,
            fingerprint,
            external_revision_id="risk-review-2",
            supersedes_revision_id=first_accepted.accepted_revision_id,
            authored_at=(first.authored_at + timedelta(minutes=5)).isoformat(),
            published_at=(first.published_at + timedelta(minutes=5)).isoformat(),
            summary="No current company-specific findings remain in this complete review.",
            findings=[
                {
                    "finding_key": "portfolio.cash-review",
                    "scope": "PORTFOLIO",
                    "category": "PORTFOLIO_EXPOSURE",
                    "title": "Cash mix reviewed",
                    "description": "The current cash mix remains within the reviewed range.",
                    "severity": "LOW",
                    "confidence": "HIGH",
                    "status": "ACTIVE",
                    "change_direction": "UNCHANGED",
                    "rationale": "This is the complete assessment for the cited portfolio state.",
                    "evidence": [
                        {
                            "source_name": "Application Portfolio State",
                            "external_identifier": f"snapshot:{snapshot.id}",
                        }
                    ],
                }
            ],
        )
        _, second_candidates = capture(session, second)
        second_preview = preview_risk_candidate(session, second_candidates[0].id)
        assert second_preview.status == "READY"
        second_accepted = accept_risk_candidate(
            session, second_candidates[0].id, "reviewer", "Cleared the prior company finding."
        )
        assert second_accepted.accepted_revision_id is not None

        company_view = company_risk_assessments(session, company.id)
        assert len(company_view.current) == 1
        assert company_view.current[0].id == second_accepted.accepted_revision_id
        assert company_view.current[0].findings == []
        assert [revision.id for revision in company_view.history] == [
            first_accepted.accepted_revision_id
        ]
