"""Booking SEC evidence-to-decision pilot: read-only, source and reviewer gates."""

import json
import os
import stat
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from portfolio_api.booking_evidence_decision import (
    BookingEvidenceDecisionBrief,
    booking_quarter_signals,
    build_booking_decision_brief,
    main,
)
from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.company_observations import CompanyMetricDefinitionRead
from portfolio_api.data_universe_shadow import EvidencePackV1

HERE = Path(__file__).parent / "fixtures"
SOURCE = (HERE / "data_universe_bkng_q3_2026_excerpt.html").read_bytes()


def _pack() -> EvidencePackV1:
    return EvidencePackV1.model_validate_json(
        (HERE / "data_universe_bkng_q3_2026.json").read_text(encoding="utf-8")
    )


def _context() -> CompanyAgentContextV1:
    return CompanyAgentContextV1.model_validate(
        {
            "contract_type": "CompanyAgentContextV1",
            "contract_version": "1.0.0",
            "generated_at": "2026-11-20T18:00:00Z",
            "as_of": "2026-11-20",
            "known_at": "2026-11-20T18:00:00Z",
            "identity": {"status": "AVAILABLE"},
            "company": {
                "id": str(uuid4()),
                "name": "Booking Holdings Inc.",
                "reporting_currency": "USD",
                "created_at": "2026-01-01T00:00:00Z",
                "is_demo": True,
                "lifecycle": None,
                "lifecycle_event_id": None,
            },
            "securities": [],
            "listings": [
                {
                    "id": str(uuid4()),
                    "security_id": str(uuid4()),
                    "venue": "NASDAQ",
                    "ticker": "BKNG",
                    "currency": "USD",
                    "identity_source_ref": None,
                    "is_demo": True,
                }
            ],
            "sec_identity": {
                "status": "MAPPED",
                "cik": "0001075531",
                "evidence_source": (
                    "https://www.sec.gov/Archives/edgar/data/1075531/"
                    "000107553126000045/0001075531-26-000045-index.htm"
                ),
                "recorded_at": "2026-11-20T11:51:25Z",
            },
            "portfolio_status": {"status": "UNSUPPORTED"},
            "portfolio_id": None,
            "portfolio_snapshot_id": None,
            "portfolio_target_revision_id": None,
            "portfolio_holdings_authority": None,
            "portfolio": None,
            "metrics_status": {"status": "NO_DATA"},
            "metric_definitions": [],
            "metric_observations": [],
            "guidance_status": {"status": "NO_DATA"},
            "guidance_observations": [],
            "consensus_status": {"status": "NO_DATA"},
            "consensus_continuity_status": "NO_MAPPING",
            "consensus_provider_id": None,
            "consensus_periods": [],
            "research_status": {"status": "UNSUPPORTED"},
            "current_research": [],
            "thesis_status": {"status": "UNSUPPORTED"},
            "current_theses": [],
            "native_models_status": {"status": "UNSUPPORTED"},
            "native_models": [],
            "imported_outputs_status": {"status": "UNSUPPORTED"},
            "imported_model_outputs": None,
            "resource_links": {},
        }
    )


def test_booking_decision_evidence_is_real_reported_growth_not_rounded_quotient() -> None:
    metrics = booking_quarter_signals(_pack(), SOURCE)
    assert {
        x.metric_key: (x.reported_2026, x.reported_2025, x.reported_yoy_percent) for x in metrics
    } == {
        "bkng.room_nights": (Decimal(345), Decimal(323), Decimal("6.7")),
        "bkng.flight_tickets": (Decimal(21), Decimal(17), Decimal("19.4")),
        "bkng.gross_bookings": (Decimal(54461), Decimal(49668), Decimal("9.6")),
    }
    assert metrics[-1].currency == "USD"
    assert all(x.scale == Decimal("1000000") and x.rounded_values for x in metrics)
    assert all(x.growth_basis == "COMPANY_REPORTED_YOY" for x in metrics)


def test_first_brief_identifies_definitions_before_observations_without_model_changes() -> None:
    context, pack = _context(), _pack()
    brief = build_booking_decision_brief(context, pack, SOURCE)
    assert isinstance(brief, BookingEvidenceDecisionBrief)
    assert brief.company_id == context.company.id
    assert brief.issuer_cik == "0001075531"
    assert len(brief.source_sha256) == 64
    assert len(brief.quarter_signals) == 3
    assert brief.next_review_step == "REVIEW_METRIC_DEFINITIONS"
    assert brief.ready_batch_type == "MetricDefinitionBatchV1"
    assert brief.ready_external_batch_id and brief.ready_external_batch_id.startswith("shadow-")
    assert brief.deferred_batch_types == ["KPIObservationBatchV1"]
    assert brief.fair_value_change is None
    assert brief.expected_irr_change is None
    assert brief.valuation_impact_status == "NOT_ESTIMATED"
    assert not brief.canonical_writes_performed and not brief.accepted_model_changed
    assert not brief.proposal_submitted
    assert len(brief.decision_questions) == 3
    assert all(x.proposed_model_change is None for x in brief.decision_questions)
    assert [signal.reported_yoy_percent for signal in brief.quarter_signals] == [
        Decimal("6.7"),
        Decimal("19.4"),
        Decimal("9.6"),
    ]


def test_accepted_definitions_unlock_only_kpi_proposal_review() -> None:
    context, pack = _context(), _pack()
    for definition in pack.metric_definitions:
        fields = definition.model_dump(mode="json")
        fields.pop("metric_key")
        fields.update(
            {
                "id": str(uuid4()),
                "company_id": str(context.company.id),
                "metric_id": definition.metric_key,
                "consensus_allowed": False,
                "active": True,
                "created_at": "2026-11-19T00:00:00Z",
                "deprecated_at": None,
            }
        )
        context.metric_definitions.append(CompanyMetricDefinitionRead.model_validate(fields))
    context.metrics_status.status = "AVAILABLE"
    brief = build_booking_decision_brief(context, pack, SOURCE)
    assert brief.next_review_step == "REVIEW_KPI_OBSERVATIONS"
    assert brief.ready_batch_type == "KPIObservationBatchV1"
    assert brief.deferred_batch_types == []


def test_changed_evidence_or_wrong_issuer_is_rejected_not_summarized() -> None:
    changed = [
        SOURCE.replace(b"345", b"346", 1),
        SOURCE.replace(b"6.7 %", b"70.0 %", 1),
        SOURCE.replace(b"19.4 %", b"99.9 %", 1),
        SOURCE.replace(b"9.6 %", b"99.6 %", 1),
        SOURCE.replace(b"Three Months Ended", b"Nine Months Ended"),
    ]
    for html in changed:
        with pytest.raises(ValueError):
            build_booking_decision_brief(_context(), _pack(), html)
    context = _context()
    context.sec_identity = None
    with pytest.raises(ValueError, match="reviewed matching SEC CIK"):
        build_booking_decision_brief(context, _pack(), SOURCE)
    context = _context()
    context.portfolio_status.status = "AVAILABLE"
    with pytest.raises(ValueError, match="dedicated scoped"):
        build_booking_decision_brief(context, _pack(), SOURCE)
    context = _context()
    context.metrics_status.truncated = True
    blocked = build_booking_decision_brief(context, _pack(), SOURCE)
    assert blocked.next_review_step == "CONTEXT_INCOMPLETE"
    assert blocked.ready_batch_type is None


def test_report_file_private_and_cli_never_submits(tmp_path: Path) -> None:
    context = _context()
    context_file = tmp_path / "context.json"
    context_file.write_text(context.model_dump_json(), encoding="utf-8")
    output = tmp_path / "brief.json"
    arguments = [
        "booking-evidence-decision",
        "--company-id",
        str(context.company.id),
        "--source-pack",
        str(HERE / "data_universe_bkng_q3_2026.json"),
        "--source-html",
        str(HERE / "data_universe_bkng_q3_2026_excerpt.html"),
        "--context-file",
        str(context_file),
        "--output",
        str(output),
    ]
    with patch.object(sys, "argv", arguments):
        main()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["next_review_step"] == "REVIEW_METRIC_DEFINITIONS"
    assert written["canonical_writes_performed"] is False
    assert written["accepted_model_changed"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with patch.object(sys, "argv", arguments), pytest.raises(SystemExit):
        main()


def test_live_path_requires_real_sec_and_private_read_token(
    tmp_path: Path,
) -> None:
    output = tmp_path / "live.json"
    arguments = [
        "booking-evidence-decision",
        "--company-id",
        str(uuid4()),
        "--source-pack",
        str(HERE / "data_universe_bkng_q3_2026.json"),
        "--api-base-url",
        "https://portfolio-api.example.org",
        "--output",
        str(output),
    ]
    with (
        patch.dict(os.environ, {"SEC_USER_AGENT": ""}),
        patch("portfolio_api.data_universe_public_evidence.build_opener") as opener,
        patch.object(sys, "argv", arguments),
        pytest.raises(ValueError, match="SEC_USER_AGENT"),
    ):
        main()
    opener.assert_not_called()
    assert not output.exists()
