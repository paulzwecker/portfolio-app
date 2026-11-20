"""Source-backed Data Universe shadow pilot: no DB/API writes or live credentials."""

import copy
import json
import os
import stat
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.request import Request
from uuid import uuid4

import pytest

from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.company_observation_proposals import BATCH_ADAPTER
from portfolio_api.data_universe_proposal_handoff import (
    main as handoff_main,
    prepare_handoff,
    submit_one,
)
from portfolio_api.data_universe_public_evidence import verify_uber_q3_2026_pack
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


def test_definition_permissions_and_actual_quality_must_match() -> None:
    context, pack = _context(), _pack()
    _accepted_data(context, pack)
    pack.metric_definitions[0].model_driver_allowed = True
    context.metric_observations[0].quality_status = "PROVISIONAL"
    report = compare_source_pack(context, pack)
    assert report["status"] == "NEEDS_HUMAN_RESOLUTION"
    assert report["draft_proposals"] == []
    assert {(row["domain"], row["metric_key"], row["outcome"]) for row in report["findings"]} >= {
        ("DEFINITION", "uber.trips", "CONFLICT"),
        ("KPI", "uber.trips", "BLOCKED"),
    }

    pack.metric_definitions[0].model_driver_allowed = False
    report = compare_source_pack(context, pack)
    assert ("KPI", "uber.trips", "CONFLICT") in {
        (row["domain"], row["metric_key"], row["outcome"]) for row in report["findings"]
    }


def test_source_must_exist_before_authorship_and_canonical_cutoff() -> None:
    context, pack = _context(), _pack()
    pack.source_published_on = date(2026, 11, 20)
    with pytest.raises(ValueError, match="after its pack was authored"):
        compare_source_pack(context, pack)
    pack = _pack()
    context.known_at = datetime(2026, 11, 3, tzinfo=UTC)
    with pytest.raises(ValueError, match="postdates the canonical knowledge cutoff"):
        compare_source_pack(context, pack)


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


def _verified_pack(pack: EvidencePackV1) -> dict[str, Any]:
    html = Path(__file__).parent / "fixtures" / "data_universe_uber_q3_2026_excerpt.html"
    return verify_uber_q3_2026_pack(pack, html.read_bytes())


def test_review_handoff_waits_for_definition_acceptance_and_never_self_approves() -> None:
    context, pack = _context(), _pack()
    source = _verified_pack(pack)
    initial = prepare_handoff(context, pack, source)
    assert initial["shadow_status"] == "DRAFTS_PREPARED"
    assert [batch["contract_type"] for batch in initial["ready_batches"]] == [
        "MetricDefinitionBatchV1",
    ]
    assert initial["deferred_batch_types"] == [
        "KPIObservationBatchV1",
        "GuidanceObservationBatchV1",
    ]
    assert initial["candidate_submission"] == {"status": "NOT_ATTEMPTED"}
    assert initial["canonical_writes_performed"] is False

    _accepted_data(context, pack)
    context.metric_observations = []
    context.guidance_observations = []
    next_stage = prepare_handoff(context, pack, source)
    assert [batch["contract_type"] for batch in next_stage["ready_batches"]] == [
        "KPIObservationBatchV1",
        "GuidanceObservationBatchV1",
    ]
    _accepted_data(context, pack)
    assert prepare_handoff(context, pack, source)["ready_batches"] == []

    wrong = dict(source)
    wrong["source_sha256"] = "bad"
    with pytest.raises(ValueError, match="primary-source verification"):
        prepare_handoff(context, pack, wrong)


def test_review_handoff_withholds_every_batch_if_canonical_context_is_incomplete() -> None:
    context, pack = _context(), _pack()
    context.metrics_status.truncated = True
    plan = prepare_handoff(context, pack, _verified_pack(pack))
    assert plan["shadow_status"] == "INCOMPLETE_CONTEXT"
    assert plan["ready_batches"] == []
    assert plan["deferred_batch_types"] == []
    assert any(row["outcome"] == "INCOMPLETE_CONTEXT" for row in plan["findings"])


def test_candidate_post_is_opt_in_and_confirms_exact_reviewed_inputs() -> None:
    context, pack = _context(), _pack()
    source = _verified_pack(pack)
    batch = prepare_handoff(context, pack, source)["ready_batches"][0]
    external_id = batch["external_batch_id"]
    with patch.dict(os.environ, {}, clear=True), pytest.raises(
        ValueError, match="disabled by default"
    ):
        submit_one(
            "https://example.com", batch, expected_batch_id=external_id,
            expected_source_sha256=source["source_sha256"], verification=source,
        )
    with patch.dict(
        os.environ,
        {
            "DATA_UNIVERSE_PROPOSAL_SUBMIT_ENABLED": "true",
            "OBSERVATION_PROPOSAL_AGENT_TOKEN": "synthetic-issuer-agent-00000000000000000000",
        },
    ):
        with pytest.raises(ValueError, match="path/credentials"):
            submit_one(
                "https://example.com/other", batch, expected_batch_id=external_id,
                expected_source_sha256=source["source_sha256"], verification=source,
            )
        with pytest.raises(ValueError, match="Reviewed batch ID"):
            submit_one(
                "https://example.com", batch, expected_batch_id="wrong",
                expected_source_sha256=source["source_sha256"], verification=source,
            )
        with pytest.raises(ValueError, match="Reviewed batch ID"):
            submit_one(
                "https://example.com", batch, expected_batch_id=external_id,
                expected_source_sha256="0" * 64, verification=source,
            )


def test_candidate_post_only_uses_agent_role_and_verifies_server_echo() -> None:
    context, pack = _context(), _pack()
    verified = _verified_pack(pack)
    batch = prepare_handoff(context, pack, verified)["ready_batches"][0]
    body = {
        "proposal": {
            "id": str(uuid4()),
            "producer_id": "synthetic-agent",
            "proposal": batch,
            "content_fingerprint": "a" * 64,
            "status": "PENDING",
            "issue": None,
            "preview_fingerprint": None,
            "accepted_record_ids": [],
            "reviewer_id": None,
            "decision_note": None,
            "submitted_at": datetime.now(UTC).isoformat(),
            "reviewed_at": None,
        },
        "replayed": False,
    }
    class Response:
        status = 201

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            data = json.dumps(body).encode("utf-8")
            assert len(data) < limit
            return data

        class headers:
            @staticmethod
            def get_content_type() -> str:
                return "application/json"

    class Opener:
        calls = 0

        def open(self, request: Request, timeout: int) -> Response:
            self.calls += 1
            assert timeout == 15
            assert request.get_method() == "POST"
            assert request.full_url == "https://localhost.example/v1/company-observation-proposals"
            assert request.get_header("X-observation-proposal-token") is not None
            assert json.loads(request.data or b"{}")["external_batch_id"] == batch[
                "external_batch_id"
            ]
            return Response()

    opener = Opener()
    with (
        patch.dict(
            os.environ,
            {
                "DATA_UNIVERSE_PROPOSAL_SUBMIT_ENABLED": "true",
                "OBSERVATION_PROPOSAL_AGENT_TOKEN": "synthetic-issuer-agent-00000000000000000000",
            },
        ),
        patch(
            "portfolio_api.data_universe_proposal_handoff.build_opener",
            return_value=opener,
        ),
    ):
        result = submit_one(
            "https://localhost.example", batch,
            expected_batch_id=batch["external_batch_id"],
            expected_source_sha256=verified["source_sha256"],
            verification=verified,
        )
    assert opener.calls == 1
    assert result.replayed is False
    assert result.proposal.proposal.external_batch_id == batch["external_batch_id"]
    assert result.proposal.status == "PENDING"
    body["proposal"]["proposal"] = {**batch, "external_batch_id": "forged"}
    with (
        patch.dict(
            os.environ,
            {
                "DATA_UNIVERSE_PROPOSAL_SUBMIT_ENABLED": "true",
                "OBSERVATION_PROPOSAL_AGENT_TOKEN": "synthetic-issuer-agent-00000000000000000000",
            },
        ),
        patch(
            "portfolio_api.data_universe_proposal_handoff.build_opener",
            return_value=opener,
        ),
        pytest.raises(ValueError, match="does not match"),
    ):
        submit_one(
            "https://localhost.example", batch,
            expected_batch_id=batch["external_batch_id"],
            expected_source_sha256=verified["source_sha256"],
            verification=verified,
        )


def test_handoff_cli_offline_preview_is_private_and_never_posts(tmp_path: Path) -> None:
    context = _context()
    context_file = tmp_path / "context.json"
    context_file.write_text(context.model_dump_json(), encoding="utf-8")
    output = tmp_path / "handoff.json"
    source_html = Path(__file__).parent / "fixtures" / "data_universe_uber_q3_2026_excerpt.html"
    args = [
        "data_universe_proposal_handoff",
        "--context-file", str(context_file),
        "--source-html", str(source_html),
        "--company-id", str(context.company.id),
        "--source-pack", str(FIXTURE),
        "--output", str(output),
    ]
    with (
        patch.object(sys, "argv", args),
        patch("portfolio_api.data_universe_proposal_handoff.submit_one") as submitter,
    ):
        handoff_main()
    submitter.assert_not_called()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["source_verification"]["status"] == "SOURCE_MATCHED"
    assert [r["contract_type"] for r in report["ready_batches"]] == [
        "MetricDefinitionBatchV1",
    ]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with patch.object(sys, "argv", args), pytest.raises(SystemExit):
        handoff_main()

    submit_args = args + ["--submit", "--batch-id", "synthetic", "--source-sha256", "0" * 64]
    with (
        patch.object(sys, "argv", submit_args),
        patch("portfolio_api.data_universe_proposal_handoff.submit_one") as submitter,
        pytest.raises(SystemExit),
    ):
        handoff_main()
    submitter.assert_not_called()


def test_scoped_fetch_rejects_unencrypted_non_loopback_host() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        _fetch_scoped_context("http://example.com", uuid4())


def test_verified_public_source_is_checked_before_any_private_context_read(
    tmp_path: Path,
) -> None:
    company_id = uuid4()
    output = tmp_path / "verified-shadow.json"
    args = [
        "data_universe_shadow",
        "--api-base-url",
        "https://private-api.example",
        "--company-id",
        str(company_id),
        "--source-pack",
        str(FIXTURE),
        "--verify-public-source",
        "--output",
        str(output),
    ]
    with (
        patch.object(sys, "argv", args),
        patch(
            "portfolio_api.data_universe_public_evidence.verify_official_uber_release",
            side_effect=ValueError("Source changed"),
        ) as verifier,
        patch("portfolio_api.data_universe_shadow._fetch_scoped_context") as private_read,
        pytest.raises(ValueError, match="Source changed"),
    ):
        main()
    verifier.assert_called_once()
    private_read.assert_not_called()
    assert not output.exists()


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
    assert report["source_verification"]["status"] == "NOT_CHECKED"
    with patch.object(sys, "argv", args), pytest.raises(SystemExit):
        main()
