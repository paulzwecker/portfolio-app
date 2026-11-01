"""Bounded, review-gated synchronization of the authoritative portfolio workbook.

Google Drive is read-only. Every XLSX is frozen by ``workbook_sources`` before parsing,
then retained by content hash in PostgreSQL so one-shot cloud processes can be replayed.
Acquisition only stages a preview. Applying source-owned rows is a separate explicit command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import false, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api import canonical_bootstrap, legacy_import, model_outputs
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    verify_database_write_target,
)
from portfolio_api.domain.models import (
    Actor,
    CashPosition,
    Company,
    CurrentLifecycle,
    HoldingPosition,
    HoldingSnapshot,
    LifecycleEvent,
    Listing,
    ModelOutputSnapshot,
    ResearchPriorityInput,
    ScoreAssessment,
    ScoreDefinition,
    Security,
    TargetAllocation,
    TargetRevision,
    WorkbookSyncArtifact,
    WorkbookSyncPreview,
    WorkbookSyncRun,
    WorkbookSyncSchemaApproval,
    now,
)
from portfolio_api.research_priority_import import (
    import_research_priority_inputs,
    research_priority_rows,
)
from portfolio_api.settings import Settings
from portfolio_api.workbook_semantics import (
    SEMANTIC_FINGERPRINT_VERSION,
    semantic_fingerprint,
)
from portfolio_api.workbook_sources import (
    PORTFOLIO_PROFILE,
    SnapshotStore,
    WorkbookSourceError,
    _google_source,
    acquire_snapshot,
    inspect_workbook,
)

IMPORT_VERSION = "canonical-workbook-sync-v1"
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
WORKBOOK_SYNC_APPLY_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"portfolio-canonical-workbook-sync-apply").digest()[:8],
    "big",
    signed=True,
)


class WorkbookSyncError(ValueError):
    """Sanitized workbook sync validation or review failure."""


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _report_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _report_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_report_value(item) for item in value]
    return value


def _company_tickers(workbook: legacy_import.Workbook) -> set[str]:
    tickers: set[str] = set()
    for _row, cells in workbook.rows("Universe Registry", 5):
        ticker_cell = cells.get("A")
        if ticker_cell is not None and ticker_cell.value:
            tickers.add(ticker_cell.value.strip().upper())
    return tickers


def _canonical_listing_workbook(session: Session, tickers: set[str]) -> legacy_import.Workbook:
    """Use the reviewed canonical listing crosswalk; never infer a new venue or currency."""
    cells: dict[str, legacy_import.Cell] = {}
    digest_rows: list[tuple[str, str, str, str, str]] = []
    row_number = 5
    for ticker in sorted(tickers):
        company_id = legacy_import._stable_id("company", ticker)
        listings = list(
            session.execute(
                select(Listing, Security)
                .join(Security, Security.id == Listing.security_id)
                .where(
                    Security.company_id == company_id,
                    Security.security_type == "COMMON_STOCK",
                    Security.is_demo.is_(False),
                    Listing.is_demo.is_(False),
                )
                .order_by(Listing.venue, Listing.ticker)
            )
        )
        for listing, security in listings:
            currency = listing.currency or ""
            values = {
                "A": ticker,
                "B": security.name,
                "C": f"{listing.venue}:{listing.ticker}",
                "D": listing.venue,
                "E": currency,
                "G": "Common Stock",
                "K": "READY",
            }
            for column, value in values.items():
                cells[f"{column}{row_number}"] = legacy_import.Cell(str(value))
            digest_rows.append((ticker, security.name, listing.venue, listing.ticker, currency))
            row_number += 1
    digest = _digest(digest_rows)
    return legacy_import.Workbook(
        path=Path("canonical-listing-crosswalk.xlsx"),
        sha256=digest,
        sheets={"Listings": cells},
        source_name="canonical-listing-crosswalk",
    )


def _projection(
    plan: legacy_import.ImportPlan,
    model_plan: model_outputs.ImportPlan,
    *,
    research_rows: list[dict[str, Any]],
) -> dict[str, object]:
    domains: dict[str, object] = {
        "companies_lifecycle": [
            {
                "ticker": item.ticker,
                "name": item.name,
                "research_bucket": item.research_bucket,
                "lifecycle": item.lifecycle.value if item.lifecycle else None,
            }
            for item in plan.companies
        ],
        "listing_mappings": [
            {
                "listing_key": item.listing_key,
                "company_ticker": item.canonical_ticker,
                "venue": item.venue,
                "ticker": item.ticker,
                "currency": item.currency,
                "security_type": item.security_type,
            }
            for item in plan.listings
        ],
        "holdings": [
            {
                "ticker": item.canonical_ticker,
                "listing_key": item.listing_key,
                "quantity": item.quantity,
            }
            for item in plan.positions
        ],
        "cash": [{"currency": item.currency, "balance": item.balance} for item in plan.cash],
        "targets": sorted((ticker, weight) for ticker, weight in plan.targets.items()),
        "scores": [
            {
                "ticker": item.ticker,
                "dimension": item.dimension.value,
                "score": item.score,
                "status": item.status.value,
                "rationale": item.rationale,
            }
            for item in plan.scores
        ],
        "cached_legacy_rank_observations": {
            ranking.value: [
                {
                    "ticker": item.ticker,
                    "position": item.position,
                    "status": item.status.value,
                }
                for item in rows
            ]
            for ranking, rows in sorted(plan.rankings.items(), key=lambda item: item[0].value)
        },
        "research_priority_inputs": research_rows,
        "model_output_snapshots": [
            {
                "company_id": item["company_id"],
                "model_key": item["model_key"],
                "snapshot_key": item["snapshot_key"],
                "source_fingerprint": item["source_fingerprint"],
                "outputs": {field: item.get(field) for field in model_outputs.NUMERIC_FIELDS},
                "currency": item.get("model_currency"),
                "quality": item.get("output_quality"),
            }
            for item in model_plan.snapshots
        ],
    }
    normalized = cast(dict[str, object], _report_value(domains))
    hashes = {name: _digest(value) for name, value in normalized.items()}
    return {"domains": normalized, "domain_sha256": hashes}


def _current_state_sha256(session: Session, plan: legacy_import.ImportPlan) -> str:
    """Fingerprint only workbook-owned current state; downstream analytics are excluded."""
    ticker_ids = {
        item.ticker: legacy_import._stable_id("company", item.ticker) for item in plan.companies
    }
    company_ids = set(ticker_ids.values())
    companies = (
        list(
            session.scalars(select(Company).where(Company.id.in_(company_ids)).order_by(Company.id))
        )
        if company_ids
        else []
    )
    listings = list(
        session.execute(
            select(Listing, Security)
            .join(Security, Security.id == Listing.security_id)
            .where(Security.company_id.in_(company_ids) if company_ids else false())
            .order_by(Listing.id)
        )
    )
    lifecycle = list(
        session.scalars(
            select(LifecycleEvent)
            .join(CurrentLifecycle, CurrentLifecycle.event_id == LifecycleEvent.id)
            .where(LifecycleEvent.company_id.in_(company_ids) if company_ids else false())
            .order_by(LifecycleEvent.company_id)
        )
    )
    portfolio_id = legacy_import._stable_id("portfolio", "legacy-default")
    latest_holding = session.scalar(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.portfolio_id == portfolio_id)
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    holding_rows: list[dict[str, object]] = []
    if latest_holding is not None:
        holding_rows = [
            {"listing_id": item.listing_id, "quantity": item.quantity}
            for item in session.scalars(
                select(HoldingPosition)
                .where(HoldingPosition.snapshot_id == latest_holding.id)
                .order_by(HoldingPosition.listing_id)
            )
        ]
        holding_rows += [
            {"currency": item.currency, "balance": item.balance}
            for item in session.scalars(
                select(CashPosition)
                .where(CashPosition.snapshot_id == latest_holding.id)
                .order_by(CashPosition.currency)
            )
        ]
    latest_target = session.scalar(
        select(TargetRevision)
        .where(TargetRevision.portfolio_id == portfolio_id, TargetRevision.status == "ACCEPTED")
        .order_by(TargetRevision.effective_at.desc(), TargetRevision.accepted_at.desc())
        .limit(1)
    )
    target_rows = (
        [
            {"company_id": item.company_id, "weight": item.weight}
            for item in session.scalars(
                select(TargetAllocation)
                .where(TargetAllocation.revision_id == latest_target.id)
                .order_by(TargetAllocation.company_id)
            )
        ]
        if latest_target
        else []
    )
    score_rows: list[dict[str, object]] = []
    for score in session.scalars(
        select(ScoreAssessment)
        .where(ScoreAssessment.company_id.in_(company_ids) if company_ids else false())
        .order_by(
            ScoreAssessment.company_id,
            ScoreAssessment.score_definition_id,
            ScoreAssessment.effective_at.desc(),
            ScoreAssessment.recorded_at.desc(),
        )
    ):
        key = (score.company_id, score.score_definition_id)
        if any((row["company_id"], row["definition_id"]) == key for row in score_rows):
            continue
        score_rows.append(
            {
                "company_id": score.company_id,
                "definition_id": score.score_definition_id,
                "score": score.score,
                "status": score.status,
                "rationale": score.rationale,
                "actor": score.actor,
            }
        )
    priority_rows = list(
        session.scalars(
            select(ResearchPriorityInput)
            .where(ResearchPriorityInput.company_id.in_(company_ids) if company_ids else false())
            .order_by(ResearchPriorityInput.company_id, ResearchPriorityInput.recorded_at.desc())
        )
    )
    model_rows = list(
        session.scalars(
            select(ModelOutputSnapshot)
            .where(ModelOutputSnapshot.company_id.in_(company_ids) if company_ids else false())
            .order_by(
                ModelOutputSnapshot.company_id,
                ModelOutputSnapshot.model_key,
                ModelOutputSnapshot.snapshot_key,
            )
        )
    )
    payload = {
        "companies": [
            {"id": item.id, "name": item.name, "reporting_currency": item.reporting_currency}
            for item in companies
        ],
        "listings": [
            {
                "id": listing.id,
                "security_id": listing.security_id,
                "venue": listing.venue,
                "ticker": listing.ticker,
                "currency": listing.currency,
                "security_type": security.security_type,
            }
            for listing, security in listings
        ],
        "lifecycle": [
            {
                "company_id": item.company_id,
                "new_state": item.new_state,
                "actor": item.actor,
                "source": item.source,
            }
            for item in lifecycle
        ],
        "holding_snapshot": (
            {
                "id": latest_holding.id,
                "actor": latest_holding.actor,
                "effective_at": latest_holding.effective_at,
                "rows": holding_rows,
            }
            if latest_holding
            else None
        ),
        "targets": {
            "revision_id": latest_target.id if latest_target else None,
            "actor": latest_target.actor if latest_target else None,
            "effective_at": latest_target.effective_at if latest_target else None,
            "rows": target_rows,
        },
        "scores": score_rows,
        "research_priority": [
            {
                "company_id": item.company_id,
                "source_digest": item.source_digest,
                "candidate_tier": item.candidate_tier,
                "priority_seed": item.priority_seed,
            }
            for item in priority_rows
        ],
        "model_outputs": [
            {
                "company_id": item.company_id,
                "snapshot_key": item.snapshot_key,
                "source_fingerprint": item.source_fingerprint,
            }
            for item in model_rows
        ],
    }
    return _digest(_report_value(payload))


def _source_change_guard(session: Session, plan: legacy_import.ImportPlan) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    portfolio_id = legacy_import._stable_id("portfolio", "legacy-default")
    latest = session.scalar(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.portfolio_id == portfolio_id)
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    if latest is None:
        issues.append(
            {
                "code": "CANONICAL_BASELINE_MISSING",
                "message": "The initial portfolio bootstrap is not present.",
            }
        )
    else:
        current_positions = {
            item.listing_id
            for item in session.scalars(
                select(HoldingPosition).where(HoldingPosition.snapshot_id == latest.id)
            )
        }
        current_cash = {
            item.currency
            for item in session.scalars(
                select(CashPosition).where(CashPosition.snapshot_id == latest.id)
            )
        }
        planned_positions = {
            legacy_import._stable_id("listing", f"{item.venue}:{item.listing_ticker}")
            for item in plan.positions
        }
        removed_positions = current_positions - planned_positions
        if removed_positions:
            issues.append(
                {
                    "code": "HOLDING_SOURCE_ROW_REMOVED",
                    "message": (
                        f"{len(removed_positions)} current holding row(s) are absent. "
                        "Absence is not a liquidation; confirm through the holdings workflow."
                    ),
                }
            )
        removed_cash = current_cash - {item.currency for item in plan.cash}
        if removed_cash:
            issues.append(
                {
                    "code": "CASH_SOURCE_ROW_REMOVED",
                    "message": (
                        "A current cash currency is absent from the source. "
                        "No zero balance or liquidation is inferred."
                    ),
                }
            )
        if latest.actor != Actor.IMPORT.value:
            stored_positions = {
                item.listing_id: item.quantity
                for item in session.scalars(
                    select(HoldingPosition).where(HoldingPosition.snapshot_id == latest.id)
                )
            }
            desired_positions = {
                legacy_import._stable_id(
                    "listing", f"{item.venue}:{item.listing_ticker}"
                ): item.quantity
                for item in plan.positions
            }
            stored_cash = {
                item.currency: item.balance
                for item in session.scalars(
                    select(CashPosition).where(CashPosition.snapshot_id == latest.id)
                )
            }
            desired_cash = {item.currency: item.balance for item in plan.cash}
            if stored_positions != desired_positions or stored_cash != desired_cash:
                issues.append(
                    {
                        "code": "HOLDINGS_APPLICATION_DECISION_CONFLICT",
                        "message": (
                            "The latest holdings state is investor-confirmed; workbook sync "
                            "will not replace it."
                        ),
                    }
                )
    for ticker, row in ((item.ticker, item) for item in plan.companies):
        if row.lifecycle is None:
            continue
        company_id = legacy_import._stable_id("company", ticker)
        current = session.get(CurrentLifecycle, company_id)
        previous = session.get(LifecycleEvent, current.event_id) if current else None
        if (
            previous is not None
            and previous.new_state != row.lifecycle.value
            and previous.actor != Actor.IMPORT.value
        ):
            issues.append(
                {
                    "code": "LIFECYCLE_APPLICATION_DECISION_CONFLICT",
                    "message": (
                        f"{ticker} has an application-authored lifecycle decision; workbook "
                        "change requires review."
                    ),
                }
            )

    latest_target = session.scalar(
        select(TargetRevision)
        .where(TargetRevision.portfolio_id == portfolio_id, TargetRevision.status == "ACCEPTED")
        .order_by(TargetRevision.effective_at.desc(), TargetRevision.accepted_at.desc())
        .limit(1)
    )
    if latest_target is not None:
        current_targets = {
            item.company_id: item.weight
            for item in session.scalars(
                select(TargetAllocation).where(TargetAllocation.revision_id == latest_target.id)
            )
        }
        desired_targets = {
            legacy_import._stable_id("company", ticker): weight
            for ticker, weight in plan.targets.items()
        }
        missing = set(current_targets) - set(desired_targets)
        if missing:
            issues.append(
                {
                    "code": "TARGET_SOURCE_ROW_REMOVED",
                    "message": (
                        f"{len(missing)} target row(s) are absent. Missing target rows are not "
                        "interpreted as 0%; add an explicit zero or review deactivation."
                    ),
                }
            )
        if latest_target.actor != Actor.IMPORT.value and current_targets != desired_targets:
            issues.append(
                {
                    "code": "TARGET_APPLICATION_DECISION_CONFLICT",
                    "message": (
                        "The latest accepted targets are application-authored; workbook sync "
                        "will not replace them."
                    ),
                }
            )

    definitions = {
        item.dimension: item
        for item in session.scalars(
            select(ScoreDefinition).where(ScoreDefinition.status == "ACTIVE")
        )
    }
    for score in plan.scores:
        definition = definitions.get(score.dimension.value)
        if definition is None:
            continue
        company_id = legacy_import._stable_id("company", score.ticker)
        previous_score = session.scalar(
            select(ScoreAssessment)
            .where(
                ScoreAssessment.company_id == company_id,
                ScoreAssessment.score_definition_id == definition.id,
            )
            .order_by(ScoreAssessment.effective_at.desc(), ScoreAssessment.recorded_at.desc())
            .limit(1)
        )
        if (
            previous_score is not None
            and previous_score.actor != Actor.IMPORT.value
            and (previous_score.score, previous_score.status, previous_score.rationale)
            != (score.score, score.status.value, score.rationale)
        ):
            issues.append(
                {
                    "code": "SCORE_APPLICATION_DECISION_CONFLICT",
                    "message": (
                        f"{score.ticker} has an application-authored "
                        f"{score.dimension.value} assessment; workbook sync will not replace it."
                    ),
                }
            )
    return issues


def _model_output_conflicts(
    session: Session, model_plan: model_outputs.ImportPlan
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    for values in model_plan.snapshots:
        existing = session.scalar(
            select(ModelOutputSnapshot).where(
                ModelOutputSnapshot.company_id == values["company_id"],
                ModelOutputSnapshot.model_key == values["model_key"],
                ModelOutputSnapshot.snapshot_key == values["snapshot_key"],
            )
        )
        if existing is not None and existing.source_fingerprint != values["source_fingerprint"]:
            conflicts.append(
                {
                    "code": "MODEL_OUTPUT_REVISION_CONFLICT",
                    "message": (
                        f"{values['model_key']}:{values['snapshot_key']} changed under an existing "
                        "immutable source revision key."
                    ),
                }
            )
    return conflicts


def _source_row_identities(domain: str, rows: object) -> set[tuple[str, ...]]:
    """Return stable keys used only to report absent source rows, never to delete them."""
    if domain == "targets" and isinstance(rows, list):
        return {(str(row[0]),) for row in rows if isinstance(row, (list, tuple)) and row}
    if domain == "cached_legacy_rank_observations" and isinstance(rows, dict):
        return {
            (str(ranking), str(row.get("ticker")))
            for ranking, ranking_rows in rows.items()
            if isinstance(ranking_rows, list)
            for row in ranking_rows
            if isinstance(row, dict) and row.get("ticker") is not None
        }
    identity_fields = {
        "companies_lifecycle": ("ticker",),
        "listing_mappings": ("listing_key",),
        "holdings": ("listing_key",),
        "cash": ("currency",),
        "scores": ("ticker", "dimension"),
        "research_priority_inputs": ("ticker",),
        "model_output_snapshots": ("company_id", "model_key", "snapshot_key"),
    }.get(domain)
    if identity_fields is None or not isinstance(rows, list):
        return set()
    return {
        tuple(str(row[field]) for field in identity_fields)
        for row in rows
        if isinstance(row, dict) and all(row.get(field) is not None for field in identity_fields)
    }


def _removed_source_row_warnings(
    prior_domains: object, current_domains: object
) -> list[dict[str, object]]:
    """Report absent rows while retaining old canonical records until reviewed semantics exist."""
    if not isinstance(prior_domains, dict) or not isinstance(current_domains, dict):
        return []
    warnings: list[dict[str, object]] = []
    for domain, prior_rows in prior_domains.items():
        current_rows = current_domains.get(domain)
        missing = sorted(
            _source_row_identities(str(domain), prior_rows)
            - _source_row_identities(str(domain), current_rows)
        )
        if missing:
            warnings.append(
                {
                    "domain": domain,
                    "code": "SOURCE_ROWS_ABSENT_NOT_DELETED",
                    "count": len(missing),
                    "identities": [list(item) for item in missing[:100]],
                    "message": (
                        "Rows present in the prior frozen workbook are absent now. "
                        "No company, position, target, score, research input, model output "
                        "or cached rank was deleted or set to zero."
                    ),
                }
            )
    return warnings


def _parse_plans(
    session: Session, run: WorkbookSyncRun, payload: bytes
) -> tuple[legacy_import.ImportPlan, model_outputs.ImportPlan]:
    if run.artifact_sha256 is None or hashlib.sha256(payload).hexdigest() != run.artifact_sha256:
        raise WorkbookSyncError("The frozen workbook artifact failed its SHA-256 check.")
    inventory = inspect_workbook(payload, PORTFOLIO_PROFILE)
    if (
        inventory.schema_fingerprint != run.schema_fingerprint
        or inventory.header_fingerprint != run.header_fingerprint
        or run.contract_version != PORTFOLIO_PROFILE.contract_version
    ):
        raise WorkbookSyncError(
            "The frozen artifact no longer matches its reviewed schema contract."
        )

    with tempfile.TemporaryDirectory(prefix="portfolio-workbook-sync-") as temporary:
        path = Path(temporary) / "Portfolio_Watchlist.xlsx"
        path.write_bytes(payload)
        # Keep source references consistent with the initial canonical bootstrap.
        # The durable sync manifest separately carries the exact Drive identity hash,
        # revision metadata and artifact hash without exposing the Drive file ID.
        source_name = PORTFOLIO_PROFILE.expected_filename
        portfolio_book = legacy_import.Workbook.read(
            path,
            lambda name: (
                name
                in {
                    "Universe Registry",
                    "Current Holdings",
                    "Target Architecture",
                    "10Y Durability",
                    "Compounder Quality",
                    "Candidate Ranking",
                    "Price Feed",
                    "Model Contract",
                    "Model Revision History",
                    "Estimate History",
                    "P-",
                }
                or name.startswith(("P-", "W-", "C-"))
            ),
            source_name=source_name,
        )
        semantic_sha256, _ = semantic_fingerprint(portfolio_book)
        if (
            run.manifest.get("semantic_fingerprint_version") != SEMANTIC_FINGERPRINT_VERSION
            or run.manifest.get("semantic_sha256") != semantic_sha256
        ):
            raise WorkbookSyncError(
                "The frozen workbook semantic fingerprint is absent or no longer matches "
                "the importer-relevant source values. Reacquire it with the current source tool."
            )
        crosswalk = _canonical_listing_workbook(session, _company_tickers(portfolio_book))
        plan = legacy_import.build_plan_from_workbooks(
            portfolio_book,
            crosswalk,
            run.acquired_at,
            portfolio_source_name=source_name,
            market_source_name="canonical-listing-crosswalk",
        )
        model_plan = model_outputs.build_import(
            session, path, run.acquired_at, source_name=source_name
        )
    return plan, model_plan


def _preview(
    session: Session, run: WorkbookSyncRun, *, record_attempt: bool = True
) -> dict[str, Any]:
    artifact = session.get(WorkbookSyncArtifact, run.artifact_sha256)
    if artifact is None:
        raise WorkbookSyncError("The frozen workbook artifact is not available.")
    payload = bytes(artifact.payload)
    plan, model_plan = _parse_plans(session, run, payload)
    research_rows = research_priority_rows(plan.portfolio_workbook)
    source_projection = _projection(plan, model_plan, research_rows=research_rows)
    blockers = canonical_bootstrap.import_blocking_issues(plan)
    blockers.extend(item for item in model_plan.issues if item.get("severity") == "ERROR")
    blockers.extend(_source_change_guard(session, plan))
    blockers.extend(_model_output_conflicts(session, model_plan))

    active_without_listing = [
        item.ticker
        for item in plan.companies
        if item.lifecycle is not None
        and item.lifecycle.value in {"PORTFOLIO", "WATCHLIST"}
        and not any(listing.canonical_ticker == item.ticker for listing in plan.listings)
    ]
    if active_without_listing:
        blockers.append(
            {
                "code": "ACTIVE_LISTING_MAPPING_MISSING",
                "message": (
                    f"{len(active_without_listing)} active company listing mapping(s) are absent "
                    "from the reviewed canonical crosswalk."
                ),
            }
        )

    latest_applied = session.scalar(
        select(WorkbookSyncRun)
        .where(
            WorkbookSyncRun.source_identity_sha256 == run.source_identity_sha256,
            WorkbookSyncRun.status == "APPLIED",
            WorkbookSyncRun.id != run.id,
        )
        .order_by(WorkbookSyncRun.applied_at.desc())
        .limit(1)
    )
    prior_hashes: dict[str, str] = cast(
        dict[str, str],
        latest_applied.source_projection.get("domain_sha256", {})
        if latest_applied is not None
        else {},
    )
    prior_domains: object = (
        latest_applied.source_projection.get("domains", {}) if latest_applied is not None else {}
    )
    current_hashes = cast(dict[str, str], source_projection["domain_sha256"])
    current_domains: object = source_projection["domains"]
    removed_source_rows = _removed_source_row_warnings(prior_domains, current_domains)
    changed_domains = sorted(
        name for name, digest in current_hashes.items() if prior_hashes.get(name) != digest
    )
    status = "BLOCKED" if blockers else "PREVIEWED"
    if latest_applied is not None and not changed_domains:
        status = "NO_CHANGES"
    summary = {
        "companies": len(plan.companies),
        "listings": len(plan.listings),
        "holding_rows": len(plan.positions),
        "cash_rows": len(plan.cash),
        "targets": len(plan.targets),
        "score_assessments": len(plan.scores),
        "cached_legacy_ranks": sum(len(rows) for rows in plan.rankings.values()),
        "research_priority_inputs": len(research_rows),
        "model_output_snapshots": len(model_plan.snapshots),
        "changed_domains": changed_domains,
        "blocker_count": len(blockers),
        "warning_count": sum(issue.severity == "WARNING" for issue in plan.issues)
        + len(removed_source_rows),
        "removed_source_row_warning_count": len(removed_source_rows),
    }
    report: dict[str, Any] = {
        "status": status,
        "import_version": IMPORT_VERSION,
        "summary": summary,
        "blocking_issues": blockers[:200],
        "removed_source_rows": removed_source_rows,
        "source_issues": [issue.as_dict() for issue in plan.issues[:200]],
        "model_output_issues": model_plan.issues[:200],
        "target_state_sha256": _current_state_sha256(session, plan),
        "apply_policy": (
            "Only workbook-owned current projections are applied. Cached legacy ranks are retained "
            "as source snapshots and are not written as current application ranking runs."
        ),
    }
    run.source_projection = source_projection
    run.projection_sha256 = _digest(source_projection)
    run.import_plan_sha256 = _digest(
        {"source_digest": plan.source_digest, "model_output_digest": model_plan.source_digest}
    )
    run.preview_report = cast(dict[str, object], _report_value(report))
    run.status = status
    run.error_code = None
    run.error_message = None
    if record_attempt:
        previous_sequence = session.scalar(
            select(func.max(WorkbookSyncPreview.sequence)).where(
                WorkbookSyncPreview.run_id == run.id
            )
        )
        session.add(
            WorkbookSyncPreview(
                id=UUID(
                    bytes=hashlib.sha256(
                        f"{run.id}:preview:{(previous_sequence or 0) + 1}".encode("ascii")
                    ).digest()[:16]
                ),
                run_id=run.id,
                sequence=(previous_sequence or 0) + 1,
                status=status,
                target_state_sha256=report["target_state_sha256"],
                projection_sha256=run.projection_sha256,
                import_plan_sha256=run.import_plan_sha256,
                recorded_at=now(),
                report=cast(dict[str, object], _report_value(report)),
            )
        )
        session.flush()
    return report


def _failed_run(
    session: Session,
    *,
    source_identity: str,
    request_id: UUID | None,
    code: str,
    message: str,
) -> WorkbookSyncRun:
    identity_hash = hashlib.sha256(source_identity.encode("utf-8")).hexdigest()
    acquired_at = now()
    revision_hash = _digest({"failed_at": acquired_at.isoformat(), "code": code})
    key = _digest({"source": identity_hash, "failure": revision_hash, "request": request_id})
    run = WorkbookSyncRun(
        id=UUID(bytes=hashlib.sha256(key.encode("ascii")).digest()[:16]),
        idempotency_key=key,
        request_id=request_id,
        source_identity_sha256=identity_hash,
        source_revision_sha256=revision_hash,
        profile=PORTFOLIO_PROFILE.key,
        contract_version=PORTFOLIO_PROFILE.contract_version,
        acquired_at=acquired_at,
        recorded_at=now(),
        status="FAILED",
        manifest={"profile": PORTFOLIO_PROFILE.key, "import_triggered": False},
        source_projection={},
        preview_report={"status": "FAILED", "summary": {}},
        error_code=code[:80],
        error_message=message[:1000],
    )
    session.add(run)
    session.flush()
    return run


def stage_current_workbook(
    session: Session, settings: Settings, *, request_id: UUID | None = None
) -> WorkbookSyncRun:
    """Acquire the exact configured Drive file, freeze it, persist it, then preview."""
    if not settings.workbook_sync_enabled:
        return _failed_run(
            session,
            source_identity="google-drive:workbook-sync-disabled",
            request_id=request_id,
            code="WORKBOOK_SYNC_DISABLED",
            message="Set WORKBOOK_SYNC_ENABLED=true for an operator-requested workbook sync.",
        )
    try:
        verify_database_write_target(cast(Engine, session.get_bind()))
        reader, file_id = _google_source(PORTFOLIO_PROFILE, settings)
        source_identity = f"google-drive:{file_id}"
        with tempfile.TemporaryDirectory(prefix="portfolio-workbook-acquisition-") as temporary:
            store = SnapshotStore(Path(temporary) / "snapshot-store")
            manifest = acquire_snapshot(
                store=store,
                profile=PORTFOLIO_PROFILE,
                source_identity=source_identity,
                fetch=lambda: reader.acquire(file_id),
            )
            if manifest.get("status") == "FAILED":
                return _failed_run(
                    session,
                    source_identity=source_identity,
                    request_id=request_id,
                    code=str(manifest.get("error_code") or "WORKBOOK_ACQUISITION_FAILED"),
                    message=str(
                        manifest.get("error_message") or "Google Drive acquisition failed."
                    ),
                )
            blob_path = manifest.get("blob_path")
            if not isinstance(blob_path, str):
                raise WorkbookSyncError(
                    "The acquired workbook has no frozen content-addressed artifact."
                )
            payload = (store.root / blob_path).read_bytes()
            return stage_frozen_snapshot(
                session,
                payload=payload,
                manifest=manifest,
                request_id=request_id,
            )
    except WorkbookSourceError as error:
        return _failed_run(
            session,
            source_identity="google-drive:configured-portfolio-source",
            request_id=request_id,
            code=error.code,
            message=error.message,
        )
    except DatabaseWriteTargetError as error:
        return _failed_run(
            session,
            source_identity="google-drive:configured-portfolio-source",
            request_id=request_id,
            code=error.code,
            message=str(error),
        )
    except Exception as error:
        return _failed_run(
            session,
            source_identity="google-drive:configured-portfolio-source",
            request_id=request_id,
            code=type(error).__name__.upper()[:80],
            message=(
                "Workbook acquisition or validation failed; inspect the run diagnostics "
                "before retrying."
            ),
        )


def stage_frozen_snapshot(
    session: Session,
    *,
    payload: bytes,
    manifest: dict[str, Any],
    request_id: UUID | None = None,
) -> WorkbookSyncRun:
    """Persist a verified frozen artifact, then compare it with approved schema and state."""
    if not payload or len(payload) > MAX_ARTIFACT_BYTES:
        raise WorkbookSyncError("The frozen workbook exceeds the 32 MiB synchronization limit.")
    artifact_sha = hashlib.sha256(payload).hexdigest()
    if manifest.get("artifact_sha256") != artifact_sha:
        raise WorkbookSyncError("Acquired workbook bytes do not match the source manifest hash.")
    if (
        manifest.get("profile") != PORTFOLIO_PROFILE.key
        or manifest.get("contract_version") != PORTFOLIO_PROFILE.contract_version
    ):
        raise WorkbookSyncError(
            "The acquired source does not match the portfolio workbook contract."
        )

    source_identity_hash = manifest.get("source_identity_sha256")
    schema_fingerprint = manifest.get("schema_fingerprint")
    header_fingerprint = manifest.get("header_fingerprint")
    semantic_sha256 = manifest.get("semantic_sha256")
    acquired_at = _source_time(manifest.get("acquired_at"))
    if (
        not all(
            isinstance(item, str) and len(item) == 64
            for item in (source_identity_hash, schema_fingerprint, header_fingerprint)
        )
        or manifest.get("semantic_fingerprint_version") != SEMANTIC_FINGERPRINT_VERSION
        or not isinstance(semantic_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", semantic_sha256)
        or acquired_at is None
    ):
        raise WorkbookSyncError("The acquisition manifest is incomplete or invalid.")
    revision_context = {
        "revision": manifest.get("source_revision"),
        "checksum": manifest.get("source_checksum"),
        "modified_at": manifest.get("source_modified_at"),
        "artifact_sha256": artifact_sha,
    }
    revision_sha = _digest(revision_context)
    idempotency_key = _digest(
        {
            "source_identity_sha256": source_identity_hash,
            "source_revision_sha256": revision_sha,
            "artifact_sha256": artifact_sha,
            "contract_version": PORTFOLIO_PROFILE.contract_version,
        }
    )
    existing = session.scalar(
        select(WorkbookSyncRun).where(WorkbookSyncRun.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing

    artifact = session.get(WorkbookSyncArtifact, artifact_sha)
    if artifact is None:
        session.add(
            WorkbookSyncArtifact(
                sha256=artifact_sha,
                byte_length=len(payload),
                payload=payload,
                recorded_at=now(),
            )
        )
        session.flush()
    elif (
        artifact.byte_length != len(payload)
        or hashlib.sha256(bytes(artifact.payload)).hexdigest() != artifact_sha
    ):
        raise WorkbookSyncError("A previously stored workbook artifact failed its integrity check.")

    identity_hash = cast(str, source_identity_hash)
    schema_hash = cast(str, schema_fingerprint)
    header_hash = cast(str, header_fingerprint)
    approval = session.scalar(
        select(WorkbookSyncSchemaApproval).where(
            WorkbookSyncSchemaApproval.source_identity_sha256 == identity_hash,
            WorkbookSyncSchemaApproval.profile == PORTFOLIO_PROFILE.key,
            WorkbookSyncSchemaApproval.contract_version == PORTFOLIO_PROFILE.contract_version,
            WorkbookSyncSchemaApproval.schema_fingerprint == schema_hash,
            WorkbookSyncSchemaApproval.header_fingerprint == header_hash,
        )
    )
    run_id = UUID(bytes=hashlib.sha256(idempotency_key.encode("ascii")).digest()[:16])
    manifest_summary = {
        "manifest_version": manifest.get("manifest_version"),
        "profile": PORTFOLIO_PROFILE.key,
        "contract_version": PORTFOLIO_PROFILE.contract_version,
        "source_identity_sha256": identity_hash,
        "source_revision": manifest.get("source_revision"),
        "source_modified_at": manifest.get("source_modified_at"),
        "source_checksum": manifest.get("source_checksum"),
        "source_mime_type": manifest.get("source_mime_type"),
        "artifact_sha256": artifact_sha,
        "artifact_bytes": len(payload),
        "schema_fingerprint": schema_hash,
        "header_fingerprint": header_hash,
        "semantic_fingerprint_version": SEMANTIC_FINGERPRINT_VERSION,
        "semantic_sha256": semantic_sha256,
        "semantic_summary": manifest.get("semantic_summary", {}),
        "acquired_at": acquired_at.isoformat(),
        "acquisition_method": manifest.get("acquisition_method"),
        "inventory": manifest.get("inventory", {}),
    }
    run = WorkbookSyncRun(
        id=run_id,
        idempotency_key=idempotency_key,
        request_id=request_id,
        source_identity_sha256=identity_hash,
        source_revision_id=manifest.get("source_revision"),
        source_revision_sha256=revision_sha,
        source_modified_at=_source_time(manifest.get("source_modified_at")),
        source_checksum=manifest.get("source_checksum"),
        source_mime_type=manifest.get("source_mime_type"),
        profile=PORTFOLIO_PROFILE.key,
        contract_version=PORTFOLIO_PROFILE.contract_version,
        schema_fingerprint=schema_hash,
        header_fingerprint=header_hash,
        artifact_sha256=artifact_sha,
        acquired_at=acquired_at,
        recorded_at=now(),
        status="SCHEMA_REVIEW_REQUIRED" if approval is None else "PREVIEWED",
        manifest=cast(dict[str, object], manifest_summary),
        source_projection={},
        preview_report={},
    )
    session.add(run)
    session.flush()
    if approval is None:
        run.preview_report = {
            "status": "SCHEMA_REVIEW_REQUIRED",
            "summary": {"artifact_bytes": len(payload)},
            "blocking_issues": [
                {
                    "code": "PORTFOLIO_SCHEMA_NOT_APPROVED",
                    "message": (
                        "Review the exact schema/header fingerprints and approve this snapshot "
                        "before parsing source rows."
                    ),
                }
            ],
            "schema_review": {
                "contract_version": PORTFOLIO_PROFILE.contract_version,
                "schema_fingerprint": schema_hash,
                "header_fingerprint": header_hash,
                "sheet_inventory": manifest_summary["inventory"],
            },
        }
        return run
    _preview(session, run)
    return run


def approve_schema(
    session: Session,
    run_id: UUID,
    *,
    expected_artifact_sha256: str,
    reviewer: str,
    rationale: str,
) -> WorkbookSyncRun:
    run = session.get(WorkbookSyncRun, run_id)
    if run is None or run.status != "SCHEMA_REVIEW_REQUIRED":
        raise WorkbookSyncError("Only a staged schema-review run can be approved.")
    if run.artifact_sha256 != expected_artifact_sha256.lower():
        raise WorkbookSyncError("The supplied artifact hash does not match the staged workbook.")
    if not reviewer.strip() or len(reviewer.strip()) > 160:
        raise WorkbookSyncError("Provide a reviewer identity up to 160 characters.")
    if not rationale.strip() or len(rationale.strip()) > 1000:
        raise WorkbookSyncError("Provide a schema-review rationale up to 1000 characters.")
    artifact = session.get(WorkbookSyncArtifact, run.artifact_sha256)
    if (
        artifact is None
        or hashlib.sha256(bytes(artifact.payload)).hexdigest() != run.artifact_sha256
    ):
        raise WorkbookSyncError("The frozen workbook failed its SHA-256 integrity check.")
    inventory = inspect_workbook(bytes(artifact.payload), PORTFOLIO_PROFILE)
    if (inventory.schema_fingerprint, inventory.header_fingerprint) != (
        run.schema_fingerprint,
        run.header_fingerprint,
    ):
        raise WorkbookSyncError("The staged workbook schema differs from the reviewed manifest.")
    approval = session.scalar(
        select(WorkbookSyncSchemaApproval).where(
            WorkbookSyncSchemaApproval.source_identity_sha256 == run.source_identity_sha256,
            WorkbookSyncSchemaApproval.profile == run.profile,
            WorkbookSyncSchemaApproval.contract_version == run.contract_version,
            WorkbookSyncSchemaApproval.schema_fingerprint == run.schema_fingerprint,
            WorkbookSyncSchemaApproval.header_fingerprint == run.header_fingerprint,
        )
    )
    if approval is None:
        approval = WorkbookSyncSchemaApproval(
            id=UUID(bytes=hashlib.sha256(f"schema:{run.idempotency_key}".encode()).digest()[:16]),
            source_identity_sha256=run.source_identity_sha256,
            profile=run.profile,
            contract_version=run.contract_version,
            schema_fingerprint=cast(str, run.schema_fingerprint),
            header_fingerprint=cast(str, run.header_fingerprint),
            artifact_sha256=run.artifact_sha256,
            reviewer=reviewer.strip(),
            rationale=rationale.strip(),
            reviewed_at=now(),
        )
        session.add(approval)
        session.flush()
    run.reviewer = reviewer.strip()
    run.reviewed_at = approval.reviewed_at
    _preview(session, run)
    return run


def refresh_preview(
    session: Session,
    run_id: UUID,
    *,
    expected_artifact_sha256: str,
) -> WorkbookSyncRun:
    """Re-evaluate a pending snapshot against current canonical state and retain the attempt."""
    run = session.scalar(
        select(WorkbookSyncRun).where(WorkbookSyncRun.id == run_id).with_for_update()
    )
    if run is None or run.status not in {"PREVIEWED", "BLOCKED"}:
        raise WorkbookSyncError("Only a schema-approved pending sync run can be previewed again.")
    if run.artifact_sha256 != expected_artifact_sha256.lower():
        raise WorkbookSyncError("The supplied artifact hash does not match the frozen workbook.")
    _preview(session, run)
    return run


def apply_run(
    session: Session,
    run_id: UUID,
    *,
    expected_artifact_sha256: str,
    reviewer: str,
) -> dict[str, Any]:
    if session.get_bind().dialect.name == "postgresql":
        # Serialize applies across distinct source revisions as well as exact replays.
        # The xact lock is released automatically on commit or rollback.
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": WORKBOOK_SYNC_APPLY_LOCK_ID},
        )
    run = session.scalar(
        select(WorkbookSyncRun).where(WorkbookSyncRun.id == run_id).with_for_update()
    )
    if run is None:
        raise WorkbookSyncError("The workbook sync run was not found.")
    if run.status in {"APPLIED", "NO_CHANGES"}:
        return {"status": "ALREADY_APPLIED", "run_id": str(run.id), "applied_at": run.applied_at}
    if run.status != "PREVIEWED":
        raise WorkbookSyncError("Only an unblocked PREVIEWED workbook sync can be applied.")
    if run.artifact_sha256 != expected_artifact_sha256.lower():
        raise WorkbookSyncError("The supplied artifact hash does not match the reviewed workbook.")
    if not reviewer.strip() or len(reviewer.strip()) > 160:
        raise WorkbookSyncError("Provide a reviewer identity up to 160 characters.")
    artifact = session.get(WorkbookSyncArtifact, run.artifact_sha256)
    if artifact is None:
        raise WorkbookSyncError("The frozen workbook artifact is not available.")
    plan, model_plan = _parse_plans(session, run, bytes(artifact.payload))
    approved_target_state = run.preview_report.get("target_state_sha256")
    current_target_state = _current_state_sha256(session, plan)
    if approved_target_state != current_target_state:
        raise WorkbookSyncError(
            "Canonical workbook-owned state changed after preview; refresh the preview "
            "before apply."
        )
    current_report = _preview(session, run, record_attempt=False)
    if current_report.get("status") != "PREVIEWED":
        raise WorkbookSyncError(
            "The source is no longer eligible for apply; review the refreshed blockers."
        )
    applied_projection = session.scalar(
        select(WorkbookSyncRun).where(
            WorkbookSyncRun.source_identity_sha256 == run.source_identity_sha256,
            WorkbookSyncRun.projection_sha256 == run.projection_sha256,
            WorkbookSyncRun.status == "APPLIED",
            WorkbookSyncRun.id != run.id,
        )
    )
    if applied_projection is not None:
        run.status = "NO_CHANGES"
        run.reviewer = reviewer.strip()
        run.reviewed_at = now()
        return {
            "status": "NO_CHANGES",
            "run_id": str(run.id),
            "prior_run_id": str(applied_projection.id),
        }

    identity = legacy_import._import_identity(session, plan, incremental_sync=True)
    company_ids = {
        key.removeprefix("company:"): value
        for key, value in identity.items()
        if key.startswith("company:")
    }
    lifecycle_count = legacy_import._import_lifecycle(session, plan, company_ids)
    portfolio = legacy_import._portfolio(session, plan)
    snapshot_count, holding_rows = legacy_import._import_holdings(
        session, plan, identity, portfolio
    )
    target_count = legacy_import._import_targets(session, plan, company_ids, portfolio)
    score_count = legacy_import._import_scores(session, plan, company_ids)
    priority_report = import_research_priority_inputs(
        session, plan.portfolio_workbook, apply=True, observed_at=run.acquired_at
    )
    output_report = model_outputs.apply_import(session, model_plan)

    # Cached rank positions are represented in the frozen source_projection and remain
    # auditable there. They are deliberately not inserted as current application RankingRuns.
    source_rankings = plan.rankings
    plan.rankings = {}
    source_report = plan.report(applied=True)
    source_report["applied_records"] = {
        "companies": len(company_ids),
        "listings": sum(key.startswith("listing:") for key in identity),
        "lifecycle_events": lifecycle_count,
        "holding_snapshots": snapshot_count,
        "holding_and_cash_rows": holding_rows,
        "accepted_target_revisions": target_count,
        "score_assessments": score_count,
        "research_priority_inputs": priority_report.get("inserted", 0),
        "model_output_snapshots_added": output_report.get("persisted_snapshots_added", 0),
        "cached_legacy_rank_runs": 0,
    }
    plan.rankings = source_rankings
    reconciled_plan = legacy_import.build_plan_from_workbooks(
        plan.portfolio_workbook,
        plan.market_workbook,
        plan.observed_at,
        portfolio_source_name=plan.portfolio_workbook.source_name,
        market_source_name=plan.market_workbook.source_name,
    )
    reconciled_plan.rankings = {}
    reconciliation = canonical_bootstrap.reconcile_canonical_state(
        session, reconciled_plan, provider_plan=None
    )
    if reconciliation.get("status") != "MATCHED":
        raise WorkbookSyncError(
            "The persisted workbook state did not reconcile; transaction must roll back."
        )
    run.status = "APPLIED"
    run.reviewer = reviewer.strip()
    run.reviewed_at = now()
    run.applied_at = now()
    run.preview_report = {
        **run.preview_report,
        "apply": {
            "status": "APPLIED",
            "reviewer": reviewer.strip(),
            "applied_at": run.applied_at.isoformat(),
            "reconciliation": reconciliation,
            "model_output_reconciliation": output_report,
            "research_priority_import": priority_report,
            "source_import": source_report,
        },
    }
    legacy_import._record_batch(session, reconciled_plan, source_report)
    return {
        "status": "APPLIED",
        "run_id": str(run.id),
        "projection_sha256": run.projection_sha256,
        "reconciliation": reconciliation,
        "applied_records": source_report["applied_records"],
    }


def run_read(run: WorkbookSyncRun) -> dict[str, object]:
    """Return a sanitized run view; workbook bytes and private source IDs are never exposed."""
    return {
        "id": str(run.id),
        "status": run.status,
        "profile": run.profile,
        "contract_version": run.contract_version,
        "source_revision": run.source_revision_id,
        "source_modified_at": run.source_modified_at.isoformat()
        if run.source_modified_at
        else None,
        "artifact_sha256": run.artifact_sha256,
        "artifact_bytes": run.manifest.get("artifact_bytes"),
        "schema_fingerprint": run.schema_fingerprint,
        "header_fingerprint": run.header_fingerprint,
        "semantic_fingerprint_version": run.manifest.get("semantic_fingerprint_version"),
        "semantic_sha256": run.manifest.get("semantic_sha256"),
        "acquired_at": run.acquired_at.isoformat(),
        "recorded_at": run.recorded_at.isoformat(),
        "projection_sha256": run.projection_sha256,
        "status_summary": run.preview_report,
        "reviewer": run.reviewer,
        "reviewed_at": run.reviewed_at.isoformat() if run.reviewed_at else None,
        "applied_at": run.applied_at.isoformat() if run.applied_at else None,
        "error_code": run.error_code,
        "error_message": run.error_message,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    request = subparsers.add_parser(
        "process-request", help="Run one explicitly queued workbook stage job"
    )
    request.add_argument("request_id", type=UUID)
    approve = subparsers.add_parser(
        "approve-schema", help="Approve the exact reviewed contract fingerprint"
    )
    approve.add_argument("run_id", type=UUID)
    approve.add_argument("--expected-artifact-sha256", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--rationale", required=True)
    show = subparsers.add_parser("show", help="Show one sanitized sync run")
    show.add_argument("run_id", type=UUID)
    apply = subparsers.add_parser("apply", help="Apply one explicit reviewed workbook snapshot")
    apply.add_argument("run_id", type=UUID)
    apply.add_argument("--expected-artifact-sha256", required=True)
    apply.add_argument("--reviewer", required=True)
    apply.add_argument("--confirm-apply", action="store_true")
    preview = subparsers.add_parser(
        "refresh-preview", help="Rebuild a pending preview against current canonical state"
    )
    preview.add_argument("run_id", type=UUID)
    preview.add_argument("--expected-artifact-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    if args.command == "process-request" and not settings.workbook_sync_enabled:
        print(
            "WORKBOOK_SYNC_DISABLED: set WORKBOOK_SYNC_ENABLED=true for an operator request.",
            file=sys.stderr,
        )
        return 2
    if args.command == "apply" and not args.confirm_apply:
        print(
            "Pass --confirm-apply after reviewing the exact staged artifact and preview.",
            file=sys.stderr,
        )
        return 2
    if settings.database_url is None:
        print("DATABASE_URL is required for workbook synchronization.", file=sys.stderr)
        return 2
    read_only = args.command == "show"
    engine = create_database_engine(
        settings,
        write_operation="canonical_workbook_sync",
        write_operation_kind="import",
        read_only=read_only,
    )
    if engine is None:
        return 2
    try:
        if not read_only:
            verify_database_write_target(engine)
        if args.command == "process-request":
            from portfolio_api.recurring_operations import process_manual_job_requests

            result = process_manual_job_requests(engine, settings, request_id=args.request_id)
            print(json.dumps(result, sort_keys=True, default=str))
            return 0 if result.get("status") not in {"FAILED", "BLOCKED"} else 1
        with Session(engine) as session:
            if args.command == "show":
                run = session.get(WorkbookSyncRun, args.run_id)
                if run is None:
                    raise WorkbookSyncError("The workbook sync run was not found.")
                result = run_read(run)
            elif args.command == "approve-schema":
                with session.begin():
                    run = approve_schema(
                        session,
                        args.run_id,
                        expected_artifact_sha256=args.expected_artifact_sha256,
                        reviewer=args.reviewer,
                        rationale=args.rationale,
                    )
                    result = run_read(run)
            elif args.command == "refresh-preview":
                with session.begin():
                    run = refresh_preview(
                        session,
                        args.run_id,
                        expected_artifact_sha256=args.expected_artifact_sha256,
                    )
                    result = run_read(run)
            else:
                with session.begin():
                    result = apply_run(
                        session,
                        args.run_id,
                        expected_artifact_sha256=args.expected_artifact_sha256,
                        reviewer=args.reviewer,
                    )
        print(json.dumps(result, sort_keys=True, indent=2, default=str))
        return 0
    except (WorkbookSyncError, WorkbookSourceError, DatabaseWriteTargetError, ValueError) as error:
        print(f"WORKBOOK_SYNC_FAILED: {error}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
