"""Explicit, evidence-gated operator handoff to the existing proposal inbox.

Read-only by default. A proposal POST requires a fresh verified issuer page,
scoped canonical read, opt-in role token and exact operator-reviewed batch ID.
This command cannot preview or accept a candidate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from uuid import UUID

from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.company_observation_proposals import (
    BATCH_ADAPTER,
    ObservationProposalSubmissionRead,
)
from portfolio_api.data_universe_public_evidence import (
    verify_official_uber_release,
    verify_uber_q3_2026_pack,
)
from portfolio_api.data_universe_shadow import (
    EvidencePackV1,
    _fetch_scoped_context,
    _NoRedirect,
    compare_source_pack,
)
from portfolio_api.settings import REPOSITORY_PATH

MAX_RESPONSE_BYTES = 500_000


def prepare_handoff(
    context: CompanyAgentContextV1,
    pack: EvidencePackV1,
    verification: dict[str, Any],
) -> dict[str, Any]:
    """Expose only candidate batches eligible for the next review stage."""
    if (
        verification.get("status") != "SOURCE_MATCHED"
        or verification.get("source_reference") != pack.source_reference
        or not re.fullmatch(r"[0-9a-f]{64}", str(verification.get("source_sha256", "")))
    ):
        raise ValueError("A valid matching primary-source verification is required")

    shadow = compare_source_pack(context, pack)
    batches = shadow["draft_proposals"]
    has_definitions = any(b["contract_type"] == "MetricDefinitionBatchV1" for b in batches)
    eligible = (
        [b for b in batches if b["contract_type"] == "MetricDefinitionBatchV1"]
        if has_definitions
        else batches
    )
    # Never submit from truncated or conflicting canonical context.
    if shadow["status"] != "DRAFTS_PREPARED":
        eligible = []

    return {
        "contract_type": "DataUniverseReviewHandoffV1",
        "contract_version": "1.0.0",
        "company_id": str(context.company.id),
        "context_known_at": context.known_at.isoformat(),
        "source_verification": verification,
        "shadow_status": shadow["status"],
        "findings": shadow["findings"],
        "ready_batches": eligible,
        "deferred_batch_types": [
            b["contract_type"] for b in batches if b not in eligible
        ],
        "candidate_submission": {"status": "NOT_ATTEMPTED"},
        "canonical_writes_performed": False,
    }


def submit_one(
    base_url: str,
    batch: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_source_sha256: str,
    verification: dict[str, Any],
) -> ObservationProposalSubmissionRead:
    """One candidate POST only; no acceptance or reviewer credentials."""
    url = urlsplit(base_url)
    if (
        not url.hostname
        or (url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")
        ))
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
    ):
        raise ValueError("Candidate API base must be HTTPS or loopback HTTP without path/credentials")
    if os.environ.get("DATA_UNIVERSE_PROPOSAL_SUBMIT_ENABLED") != "true":
        raise ValueError("Candidate submission is disabled by default")
    token = os.environ.get("OBSERVATION_PROPOSAL_AGENT_TOKEN", "")
    if len(token) < 32:
        raise ValueError("A dedicated observation agent token is required")
    if (
        batch.get("external_batch_id") != expected_batch_id
        or verification.get("source_sha256") != expected_source_sha256
        or verification.get("status") != "SOURCE_MATCHED"
    ):
        raise ValueError("Reviewed batch ID or issuer source hash changed; nothing submitted")
    validated = BATCH_ADAPTER.validate_python(batch)
    request = Request(
        f"{base_url.rstrip('/')}/v1/company-observation-proposals",
        method="POST",
        data=json.dumps(
            validated.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8"),
        headers={
            "X-Observation-Proposal-Token": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=15) as response:
            if response.status not in (200, 201):
                raise ValueError("Candidate endpoint returned an unexpected response")
            if response.headers.get_content_type() != "application/json":
                raise ValueError("Candidate endpoint returned an unexpected content type")
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        # The remote system may have committed despite a lost response;
        # replay the same external ID rather than generating a new candidate.
        raise ValueError("Candidate submission was not confirmed; check/replay same batch ID") from exc
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Candidate submission response exceeds the byte limit")
    result = ObservationProposalSubmissionRead.model_validate_json(data)
    if (
        result.proposal.proposal.company_id != validated.company_id
        or result.proposal.proposal.external_batch_id != validated.external_batch_id
        or result.proposal.proposal.model_dump(mode="json") != validated.model_dump(mode="json")
    ):
        raise ValueError("Candidate response does not match submitted batch")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--api-base-url", help="Approved HTTPS API base (loopback HTTP allowed)")
    origin.add_argument("--context-file", type=Path, help="Isolated offline scoped context JSON")
    parser.add_argument("--source-pack", type=Path, required=True)
    parser.add_argument("--source-html", type=Path, help="Offline synthetic issuer HTML only")
    parser.add_argument("--company-id", type=UUID, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--submit", action="store_true", help="Post one verified candidate only")
    parser.add_argument("--batch-id", help="Exact external_batch_id from a reviewed dry-run")
    parser.add_argument("--source-sha256", help="Exact 64-char source hash from that dry-run")
    args = parser.parse_args()

    target = args.output.expanduser().resolve()
    if target.is_relative_to(REPOSITORY_PATH.resolve()) or target.exists():
        parser.error("Private handoff output must be outside Git and not overwrite another report")
    if args.context_file is not None and args.source_html is None:
        parser.error("Offline preview requires explicit synthetic issuer HTML")
    if args.api_base_url is not None and args.source_html is not None:
        parser.error("Live API handoff cannot use local HTML instead of issuer verification")
    if args.submit:
        if args.api_base_url is None or not args.batch_id or not args.source_sha256:
            parser.error("Submission requires live API, exact batch ID and source SHA-256")
        if not re.fullmatch(r"[0-9a-f]{64}", args.source_sha256):
            parser.error("Source SHA-256 must be 64 lowercase hexadecimal characters")
        if os.environ.get("DATA_UNIVERSE_PROPOSAL_SUBMIT_ENABLED") != "true":
            parser.error("Candidate submission is disabled by default")
        if len(os.environ.get("OBSERVATION_PROPOSAL_AGENT_TOKEN", "")) < 32:
            parser.error("Dedicated observation proposal agent token required")
    elif args.batch_id is not None or args.source_sha256 is not None:
        parser.error("Batch ID and source SHA-256 are used only for explicit submission")

    pack = EvidencePackV1.model_validate_json(args.source_pack.read_text(encoding="utf-8"))
    if args.source_html is None:
        verification = verify_official_uber_release(pack)
    else:
        verification = verify_uber_q3_2026_pack(pack, args.source_html.read_bytes())

    if args.api_base_url is not None:
        context_data = _fetch_scoped_context(args.api_base_url, args.company_id)
    else:
        context_data = json.loads(args.context_file.read_text(encoding="utf-8"))
    context = CompanyAgentContextV1.model_validate(context_data)
    if context.company.id != args.company_id:
        raise ValueError("Scoped context company ID is different from the explicit target")
    handoff = prepare_handoff(context, pack, verification)

    if args.submit:
        selected = [
            b for b in handoff["ready_batches"] if b["external_batch_id"] == args.batch_id
        ]
        if len(selected) != 1:
            raise ValueError("Batch is unavailable, deferred or blocked in fresh canonical context")
        result = submit_one(
            args.api_base_url,
            selected[0],
            expected_batch_id=args.batch_id,
            expected_source_sha256=args.source_sha256,
            verification=verification,
        )
        handoff["candidate_submission"] = {
            "status": "REPLAYED" if result.replayed else "SUBMITTED",
            "proposal_id": str(result.proposal.id),
            "proposal_status": result.proposal.status,
            "external_batch_id": args.batch_id,
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(handoff, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        f"{handoff['shadow_status']}: {len(handoff['ready_batches'])} ready batch(es); "
        f"candidate {handoff['candidate_submission']['status']}; no canonical acceptance"
    )


if __name__ == "__main__":
    main()
