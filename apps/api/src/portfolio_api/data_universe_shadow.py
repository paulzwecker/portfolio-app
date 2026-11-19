"""Read-only Data & Universe Steward shadow comparison and draft proposals.

This CLI never posts to an API, writes to PostgreSQL or fetches issuer pages.
Source facts come from an explicitly reviewed evidence pack.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from pydantic import Field, field_validator

from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.company_observation_proposals import (
    BATCH_ADAPTER,
    GuidanceObservationItem,
    KPIObservationItem,
    MetricDefinitionItem,
)
from portfolio_api.domain import schemas as s
from portfolio_api.settings import REPOSITORY_PATH

MAX_CONTEXT_BYTES = 2_000_000


class EvidencePackV1(s.Contract):
    contract_type: Literal["DataUniverseEvidencePackV1"] = "DataUniverseEvidencePackV1"
    contract_version: Literal["1.0.0"] = "1.0.0"
    issuer_ticker: Annotated[str, Field(min_length=1, max_length=40)]
    source_reference: Annotated[str, Field(pattern=r"^https://", max_length=2000)]
    source_published_on: date
    authored_at: datetime
    metric_definitions: list[MetricDefinitionItem] = Field(default_factory=list, max_length=20)
    kpi_observations: list[KPIObservationItem] = Field(default_factory=list, max_length=20)
    guidance_observations: list[GuidanceObservationItem] = Field(
        default_factory=list, max_length=20
    )

    @field_validator("authored_at")
    @classmethod
    def valid_authored_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Pack authored_at must include a timezone offset")
        if value > datetime.now(UTC):
            raise ValueError("Pack authored_at must not be in the future")
        return value.astimezone(UTC)


def _fingerprint(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _same_definition(existing: dict[str, Any], proposed: MetricDefinitionItem) -> bool:
    keys = (
        "display_name",
        "category",
        "value_kind",
        "canonical_unit",
        "currency_policy",
        "aggregation_semantics",
        "default_period_type",
        "default_basis",
        "actuals_allowed",
        "guidance_allowed",
    )
    candidate = proposed.model_dump(mode="json")
    return (
        all(existing.get(key) == candidate.get(key) for key in keys)
        and Decimal(str(existing["canonical_scale"])) == proposed.canonical_scale
        and set(existing.get("scope_dimensions", [])) == set(proposed.scope_dimensions)
        and existing.get("active") is True
        and existing.get("deprecated_at") is None
    )


def _same_actual(existing: dict[str, Any], proposed: KPIObservationItem) -> bool:
    return (
        Decimal(str(existing["value"])) == proposed.value
        and existing["value_qualifier"] == proposed.value_qualifier
        and existing["unit"] == proposed.unit
        and Decimal(str(existing["scale"])) == proposed.scale
        and existing["currency"] == proposed.currency
        and existing["basis"] == proposed.basis
    )


def _same_guidance(existing: dict[str, Any], proposed: GuidanceObservationItem) -> bool:
    for key in ("lower_value", "midpoint_value", "upper_value"):
        left = existing.get(key)
        right = getattr(proposed, key)
        if left is None or right is None:
            if left is not None or right is not None:
                return False
        elif Decimal(str(left)) != right:
            return False
    return (
        existing["status"] == proposed.status
        and existing["value_qualifier"] == proposed.value_qualifier
        and existing["unit"] == proposed.unit
        and Decimal(str(existing["scale"])) == proposed.scale
        and existing["currency"] == proposed.currency
        and existing["basis"] == proposed.basis
    )


def _batch(
    contract_type: Literal[
        "MetricDefinitionBatchV1", "KPIObservationBatchV1", "GuidanceObservationBatchV1"
    ],
    items: list[MetricDefinitionItem] | list[KPIObservationItem] | list[GuidanceObservationItem],
    company_id: UUID,
    pack: EvidencePackV1,
) -> dict[str, Any]:
    fields = [item.model_dump(mode="json") for item in items]
    identity = _fingerprint(
        {
            "company_id": str(company_id),
            "contract": contract_type,
            "items": fields,
            "authored_at": pack.authored_at.isoformat(),
        }
    )
    batch = BATCH_ADAPTER.validate_python(
        {
            "contract_type": contract_type,
            "contract_version": "1.0.0",
            "company_id": str(company_id),
            "external_batch_id": f"shadow-{identity}",
            "authored_at": pack.authored_at.isoformat(),
            "rationale": (
                f"Source-backed shadow review of {pack.issuer_ticker}; no automatic acceptance."
            ),
            "items": fields,
        }
    )
    return batch.model_dump(mode="json")


def compare_source_pack(context: CompanyAgentContextV1, pack: EvidencePackV1) -> dict[str, Any]:
    """Compare a verified source pack with bounded canonical read state.

    Absence in a truncated context is not proof that a record is missing.
    Conflicting accepted facts require human correction/supersession review.
    """
    if context.contract_type != "CompanyAgentContextV1" or context.contract_version != "1.0.0":
        raise ValueError("Unsupported company context contract")
    if (
        context.portfolio_status.status != "UNSUPPORTED"
        or context.portfolio is not None
        or context.portfolio_id is not None
        or context.portfolio_snapshot_id is not None
        or context.portfolio_target_revision_id is not None
        or context.portfolio_holdings_authority is not None
        or context.resource_links
    ):
        raise ValueError("Use the dedicated scoped Data Universe context, not portfolio data")
    if context.identity.truncated or context.identity.status not in ("AVAILABLE", "NO_DATA"):
        raise ValueError("Company identity context is incomplete")
    if pack.issuer_ticker not in {listing.ticker for listing in context.listings}:
        raise ValueError("Evidence issuer ticker does not match canonical company listings")
    if (
        any(item.source_reference != pack.source_reference for item in pack.metric_definitions)
        or any(item.source_reference != pack.source_reference for item in pack.kpi_observations)
        or any(item.source_reference != pack.source_reference for item in pack.guidance_observations)
    ):
        raise ValueError("Evidence items must cite the reviewed primary source")
    if not (pack.metric_definitions or pack.kpi_observations or pack.guidance_observations):
        raise ValueError("Evidence pack contains no observations")

    definitions = {row.metric_id: row.model_dump(mode="json") for row in context.metric_definitions}
    actuals = [row.model_dump(mode="json") for row in context.metric_observations]
    guidance = [row.model_dump(mode="json") for row in context.guidance_observations]
    missing_definitions: list[MetricDefinitionItem] = []
    missing_actuals: list[KPIObservationItem] = []
    missing_guidance: list[GuidanceObservationItem] = []
    findings: list[dict[str, str]] = []
    staged_keys: set[str] = set()
    conflict_keys: set[str] = set()
    incomplete = False

    def note(domain: str, key: str, outcome: str, reason: str) -> None:
        findings.append({"domain": domain, "metric_key": key, "outcome": outcome, "reason": reason})

    for definition in pack.metric_definitions:
        key = definition.metric_key
        if key in staged_keys:
            raise ValueError("Duplicate metric definition in reviewed evidence pack")
        staged_keys.add(key)
        if context.metrics_status.truncated or context.metrics_status.status not in (
            "AVAILABLE",
            "NO_DATA",
        ):
            incomplete = True
            note("DEFINITION", key, "INCOMPLETE_CONTEXT", "Cannot establish missing definitions")
        elif key not in definitions:
            missing_definitions.append(definition)
            note("DEFINITION", key, "DRAFT", "No matching canonical metric definition")
        elif not _same_definition(definitions[key], definition):
            conflict_keys.add(key)
            note("DEFINITION", key, "CONFLICT", "Semantic definition differs; do not repurpose key")
        else:
            note("DEFINITION", key, "MATCHED", "Accepted metric definition matches")

    def observation_candidates(
        domain: str, item: KPIObservationItem | GuidanceObservationItem
    ) -> list[dict[str, Any]]:
        records = actuals if domain == "KPI" else guidance
        return [
            row
            for row in records
            if row["metric_id"] == item.metric_key
            and row["period_type"] == item.period_type
            and row["period_start"] == item.period_start.isoformat()
            and row["period_end"] == item.period_end.isoformat()
            and row["scope_json"] == item.scope_json
            and row["is_current"]
        ]

    for domain, items in (
        ("KPI", pack.kpi_observations),
        ("GUIDANCE", pack.guidance_observations),
    ):
        used: set[tuple[str, str, str, str, str]] = set()
        for item in items:
            identity = (
                item.metric_key,
                item.period_type,
                item.period_start.isoformat(),
                item.period_end.isoformat(),
                json.dumps(item.scope_json, sort_keys=True),
            )
            if identity in used:
                raise ValueError(f"Duplicate {domain} period/scope in reviewed evidence pack")
            used.add(identity)
            key = item.metric_key
            coverage = context.metrics_status if domain == "KPI" else context.guidance_status
            if coverage.truncated or coverage.status not in ("AVAILABLE", "NO_DATA"):
                incomplete = True
                note(domain, key, "INCOMPLETE_CONTEXT", "History does not prove absence")
                continue
            if key in conflict_keys:
                note(domain, key, "BLOCKED", "Metric definition has conflicting semantics")
                continue
            if context.metrics_status.truncated or context.metrics_status.status not in (
                "AVAILABLE",
                "NO_DATA",
            ):
                incomplete = True
                note(domain, key, "INCOMPLETE_CONTEXT", "Metric definition coverage is incomplete")
                continue
            if key not in definitions and key not in staged_keys:
                note(
                    domain, key, "BLOCKED", "Metric definition is unavailable in the evidence pack"
                )
                continue
            candidates = observation_candidates(domain, item)
            equivalent = len(candidates) == 1 and (
                _same_actual(candidates[0], item)
                if isinstance(item, KPIObservationItem)
                else _same_guidance(candidates[0], item)
            )
            if equivalent:
                note(domain, key, "MATCHED", "Same canonical period/scope and value")
            elif candidates:
                note(domain, key, "CONFLICT", "Accepted observation requires human supersession")
            else:
                if domain == "KPI" and isinstance(item, KPIObservationItem):
                    missing_actuals.append(item)
                elif isinstance(item, GuidanceObservationItem):
                    missing_guidance.append(item)
                prerequisite = (
                    " (definition acceptance required first)"
                    if key in {d.metric_key for d in missing_definitions}
                    else ""
                )
                note(
                    domain,
                    key,
                    "DRAFT",
                    "No current matching canonical observation" + prerequisite,
                )

    proposals: list[dict[str, Any]] = []
    if missing_definitions:
        proposals.append(
            _batch("MetricDefinitionBatchV1", missing_definitions, context.company.id, pack)
        )
    if missing_actuals:
        proposals.append(_batch("KPIObservationBatchV1", missing_actuals, context.company.id, pack))
    if missing_guidance:
        proposals.append(
            _batch("GuidanceObservationBatchV1", missing_guidance, context.company.id, pack)
        )
    has_conflict = any(item["outcome"] in ("CONFLICT", "BLOCKED") for item in findings)
    status = (
        "INCOMPLETE_CONTEXT"
        if incomplete
        else "NEEDS_HUMAN_RESOLUTION"
        if has_conflict
        else "DRAFTS_PREPARED"
        if proposals
        else "MATCHED"
    )
    return {
        "contract_type": "DataUniverseShadowReportV1",
        "contract_version": "1.0.0",
        "company_id": str(context.company.id),
        "issuer_ticker": pack.issuer_ticker,
        "source_reference": pack.source_reference,
        "source_published_on": pack.source_published_on.isoformat(),
        "context_known_at": context.known_at.isoformat(),
        "status": status,
        "findings": findings,
        "draft_proposals": proposals,
        "writes_performed": False,
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _fetch_scoped_context(base_url: str, company_id: UUID) -> dict[str, Any]:
    url = urlsplit(base_url)
    if (
        (
            url.scheme != "https"
            and (url.scheme != "http" or url.hostname not in ("127.0.0.1", "::1", "localhost"))
        )
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
        or not url.hostname
    ):
        raise ValueError("API base URL must be HTTPS (or loopback HTTP) without path/credentials")
    token = os.environ.get("DATA_UNIVERSE_READ_TOKEN", "")
    if len(token) < 32:
        raise ValueError("DATA_UNIVERSE_READ_TOKEN must be supplied privately")
    request = Request(
        f"{base_url.rstrip('/')}/v1/companies/{company_id}/agent-context",
        headers={"X-Data-Universe-Read-Token": token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=15) as response:
            if response.status != 200:
                raise ValueError("Scoped context endpoint did not return HTTP 200")
            payload = response.read(MAX_CONTEXT_BYTES + 1)
    except (HTTPError, URLError) as error:
        raise ValueError(
            "Scoped company context fetch failed; check operator authorization"
        ) from error
    if len(payload) > MAX_CONTEXT_BYTES:
        raise ValueError("Company context exceeds the bounded shadow-read limit")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Company context response must be a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--api-base-url", help="API host; token comes from environment")
    origin.add_argument("--context-file", type=Path, help="Synthetic/offline scoped context JSON")
    parser.add_argument("--company-id", type=UUID, required=True)
    parser.add_argument("--source-pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.expanduser().resolve()
    if target.is_relative_to(REPOSITORY_PATH.resolve()):
        parser.error("Keep shadow reports, which may contain private context, outside the Git repo")
    if target.exists():
        parser.error("Refusing to overwrite an existing shadow report")
    if args.api_base_url is not None:
        context_data = _fetch_scoped_context(args.api_base_url, args.company_id)
    else:
        context_data = json.loads(args.context_file.read_text(encoding="utf-8"))
    context = CompanyAgentContextV1.model_validate(context_data)
    if context.company.id != args.company_id:
        raise ValueError("Context company_id does not match the explicitly selected UUID")
    source_data = json.loads(args.source_pack.read_text(encoding="utf-8"))
    pack = EvidencePackV1.model_validate(source_data)
    report = compare_source_pack(context, pack)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Reports may expose private research; never rely on a permissive user umask.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
    print(
        f"{report['status']}: {len(report['findings'])} reviewed comparisons, "
        f"{len(report['draft_proposals'])} local draft batches; output {target}"
    )


if __name__ == "__main__":
    main()
