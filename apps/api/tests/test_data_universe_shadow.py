"""Source-backed Data Universe shadow pilot: no DB/API writes or live credentials."""

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.company_observation_proposals import BATCH_ADAPTER
from portfolio_api.data_universe_shadow import (
    EvidencePackV1,
    _fetch_scoped_context,
    compare_source_pack,
    main,
)

FIXTURE = Path(__file__).parent / "fixtures" / "data_universe_uber_q3_2026.json"


def _pack() -> EvidencePackV1:
    return EvidencePackV1.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _context() -> CompanyAgentContextV1:
    company_id, security_id, listing_id = uuid4(), uuid4(), uuid4()
    return CompanyAgentContextV1.model_validate(
        {
            "contract_type": "CompanyAgentContextV1",
            "contract_version": "1.0.0",
            "generated_at": "2026-11-19T18:50:00Z",
            "as_of": "2026-11-19",
            "known_at": "2026-11-19T18:50:00Z",
            "identity": {"status": "AVAILABLE"},
            "company": {
                "id": str(company_id),
                "name": "Synthetic Uber",
                "reporting_currency": "USD",
                "created_at": "2026-01-01T00:00:00Z",
                "is_demo": True,
                "lifecycle": None,
                "lifecycle_event_id": None,
            },
            "securities": [],
            "listings": [
                {
                    "id": str(listing_id),
                    "security_id": str(security_id),
                    "venue": "NYSE",
                    "ticker": "UBER",
                    "currency": "USD",
                    "identity_source_ref": None,
                    "is_demo": True,
                }
            ],
            "portfolio_status": {
                "status": "UNSUPPORTED",
                "reason": "Outside Data & Universe read scope",
            },
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


def _accepted_data(context: CompanyAgentContextV1, pack: EvidencePackV1) -> None:
    for definition in pack.metric_definitions:
        fields = definition.model_dump(mode="json")
        fields.pop("metric_key")
        fields.update(
            {
                "id": str(uuid4()),
                "company_id": str(context.company.id),
                "metric_id": definition.metric_key,
                "consensus_allowed": False,
                "model_driver_allowed": False,
                "active": True,
                "created_at": "2026-11-18T00:00:00Z",
                "deprecated_at": None,
            }
        )
        from portfolio_api.company_observations import CompanyMetricDefinitionRead

        context.metric_definitions.append(CompanyMetricDefinitionRead.model_validate(fields))
    for item in pack.kpi_observations:
        fields = item.model_dump(mode="json")
        fields.pop("metric_key")
        fields.update(
            {
                "id": str(uuid4()),
                "company_id": str(context.company.id),
                "metric_id": item.metric_key,
                "metric_definition_id": str(uuid4()),
                "recorded_at": "2026-11-19T18:45:00Z",
                "is_current": True,
                "quality_reason": None,
                "supersedes_observation_id": None,
            }
        )
        from portfolio_api.company_observations import CompanyMetricObservationRead

        context.metric_observations.append(CompanyMetricObservationRead.model_validate(fields))
    for guidance_item in pack.guidance_observations:
        fields = guidance_item.model_dump(mode="json")
        fields.pop("metric_key")
        fields.update(
            {
                "id": str(uuid4()),
                "company_id": str(context.company.id),
                "metric_id": guidance_item.metric_key,
                "metric_definition_id": str(uuid4()),
                "recorded_at": "2026-11-19T18:45:00Z",
                "is_current": True,
                "supersedes_guidance_id": None,
            }
        )
        from portfolio_api.company_observations import CompanyGuidanceObservationRead

        context.guidance_observations.append(CompanyGuidanceObservationRead.model_validate(fields))
    context.metrics_status.status = "AVAILABLE"
    context.guidance_status.status = "AVAILABLE"


def test_source_pack_prepares_three_typed_drafts_without_writes() -> None:
    context, pack = _context(), _pack()
    report = compare_source_pack(context, pack)
    assert report["writes_performed"] is False
    assert report["status"] == "DRAFTS_PREPARED"
    assert [item["contract_type"] for item in report["draft_proposals"]] == [
        "MetricDefinitionBatchV1",
        "KPIObservationBatchV1",
        "GuidanceObservationBatchV1",
    ]
    assert [len(item["items"]) for item in report["draft_proposals"]] == [2, 2, 1]
    assert report == compare_source_pack(context, pack)
    for proposal in report["draft_proposals"]:
        assert BATCH_ADAPTER.validate_python(proposal)
        assert proposal["company_id"] == str(context.company.id)
        assert proposal["external_batch_id"].startswith("shadow-")
    kpi_rows = report["draft_proposals"][1]["items"]
    assert [row["value"] for row in kpi_rows] == ["4061", "59819"]
    assert all(row["reported_at"] is None for row in kpi_rows)
    assert report["draft_proposals"][2]["items"][0]["upper_value"] == "65250"


def test_matching_accepted_canonical_data_yields_no_new_drafts() -> None:
    context, pack = _context(), _pack()
    _accepted_data(context, pack)
    report = compare_source_pack(context, pack)
    assert report["status"] == "MATCHED"
    assert report["draft_proposals"] == []
    assert all(item["outcome"] == "MATCHED" for item in report["findings"])


def test_conflict_requires_human_resolution_not_automatic_supersession() -> None:
    context, pack = _context(), _pack()
    _accepted_data(context, pack)
    context.metric_observations[0].value += 10
    report = compare_source_pack(context, pack)
    assert report["status"] == "NEEDS_HUMAN_RESOLUTION"
    assert any(
        item["outcome"] == "CONFLICT" and item["metric_key"] == "uber.trips"
        for item in report["findings"]
    )
    assert report["draft_proposals"] == []


def test_incomplete_history_cannot_be_assumed_missing() -> None:
    context, pack = _context(), _pack()
    context.metrics_status.truncated = True
    report = compare_source_pack(context, pack)
    assert report["status"] == "INCOMPLETE_CONTEXT"
    assert report["draft_proposals"] == []
    assert all(item["outcome"] != "DRAFT" for item in report["findings"])


def test_reject_private_or_mismatched_context_and_unreviewed_sources() -> None:
    context, pack = _context(), _pack()
    context.portfolio_status.status = "NO_DATA"
    with pytest.raises(ValueError, match="dedicated scoped"):
        compare_source_pack(context, pack)
    context = _context()
    pack.issuer_ticker = "OTHER"
    with pytest.raises(ValueError, match="issuer ticker"):
        compare_source_pack(context, pack)
    pack = _pack()
    pack.kpi_observations[0].source_reference = "https://different.example"
    with pytest.raises(ValueError, match="reviewed primary source"):
        compare_source_pack(context, pack)
    pack = _pack()
    pack.kpi_observations.append(copy.deepcopy(pack.kpi_observations[0]))
    with pytest.raises(ValueError, match="Duplicate KPI period"):
        compare_source_pack(context, pack)


def test_scoped_fetch_rejects_unencrypted_non_loopback_host() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        _fetch_scoped_context("http://example.com", uuid4())


def test_offline_cli_writes_only_explicit_external_report(tmp_path: Path) -> None:
    context = _context()
    context_file = tmp_path / "context.json"
    context_file.write_text(context.model_dump_json(), encoding="utf-8")
    output = tmp_path / "shadow.json"
    args = [
        "data_universe_shadow",
        "--context-file",
        str(context_file),
        "--company-id",
        str(context.company.id),
        "--source-pack",
        str(FIXTURE),
        "--output",
        str(output),
    ]
    with patch.object(sys, "argv", args):
        main()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "DRAFTS_PREPARED"
    assert report["writes_performed"] is False
    with patch.object(sys, "argv", args), pytest.raises(SystemExit):
        main()
