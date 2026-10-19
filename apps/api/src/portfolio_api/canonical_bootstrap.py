"""Verified, resumable import of the current canonical portfolio baseline.

This command consumes only explicitly selected, schema-approved workbook snapshots.
It never contacts Google, a market-data provider, or the historical local database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api import legacy_import
from portfolio_api.bootstrap_manifest import validate_manifest
from portfolio_api.bootstrap_preflight import (
    BootstrapPreflightError,
    verify_database_preflight,
)
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import DatabaseWriteTargetError
from portfolio_api.domain.models import (
    CanonicalBootstrapRun,
    Company,
    CompanyProviderIdentifier,
    LegacyImportBatch,
    Portfolio,
    ResearchPriorityInput,
    now,
)
from portfolio_api.legacy_import import ImportPlan
from portfolio_api.reported_fundamentals import SEC_PROVIDER_ID
from portfolio_api.research_priority_import import (
    import_research_priority_inputs,
    research_priority_rows,
)
from portfolio_api.settings import REPOSITORY_PATH, Settings
from portfolio_api.workbook_sources import (
    MARKET_DATA_PROFILE,
    PORTFOLIO_PROFILE,
    SnapshotStore,
    WorkbookSourceError,
    inspect_workbook,
)

IMPORT_VERSION = "canonical-workbook-import-v1"
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_ALLOWED_SOURCE_GAP_ERRORS = {
    "SCORE_CELL_ERROR",
    "SCORE_VALUE_INVALID",
    "SCORE_RANGE_INVALID",
    "SCORE_PRECISION_UNSUPPORTED",
    "RANK_VALUE_INVALID",
    "DUPLICATE_RANK_POSITION",
    "HOLDING_QUANTITY_MISSING",
    "HOLDING_QUANTITY_UNSUPPORTED",
    "CASH_BALANCE_MISSING",
    "CASH_BALANCE_UNSUPPORTED",
}


class CanonicalBootstrapError(ValueError):
    """A sanitized operator-facing canonical bootstrap failure."""


class CanonicalReconciliationError(CanonicalBootstrapError):
    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__(
            "Canonical bootstrap reconciliation failed; the transaction was rolled back."
        )
        self.report = report


@dataclass(frozen=True)
class ApprovedWorkbookSnapshot:
    run_id: str
    profile: str
    expected_filename: str
    sha256: str
    path: Path
    acquired_at: datetime
    schema_fingerprint: str


@dataclass(frozen=True)
class ProviderIdentifier:
    canonical_ticker: str
    identifier_value: str
    provider_company_name: str
    evidence_source: str


@dataclass(frozen=True)
class ProviderIdentifierPlan:
    sha256: str
    reviewed_by: str
    reviewed_at: datetime
    mappings: tuple[ProviderIdentifier, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON keys are forbidden")
        result[key] = value
    return result


def _read_manifest(store: SnapshotStore, run_id: str) -> dict[str, Any]:
    if not _RUN_ID.fullmatch(run_id):
        raise CanonicalBootstrapError("Use a 32-character lowercase workbook snapshot run ID.")
    path = store.run_root / f"{run_id}.json"
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise CanonicalBootstrapError(
            "A selected workbook snapshot manifest is missing or invalid."
        ) from None
    if not isinstance(value, dict) or value.get("run_id") != run_id:
        raise CanonicalBootstrapError("A selected workbook snapshot manifest is invalid.")
    return cast(dict[str, Any], value)


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        raise CanonicalBootstrapError(f"The workbook snapshot {label} timestamp is invalid.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CanonicalBootstrapError(
            f"The workbook snapshot {label} timestamp is invalid."
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalBootstrapError(
            f"The workbook snapshot {label} timestamp must include an offset."
        )
    return parsed.astimezone(UTC)


def _snapshot_blob(store: SnapshotStore, manifest: dict[str, Any]) -> tuple[Path, str]:
    digest = manifest.get("artifact_sha256")
    blob_path = manifest.get("blob_path")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise CanonicalBootstrapError("The workbook snapshot has no valid content hash.")
    expected_relative = Path("blobs") / "sha256" / digest / "workbook.xlsx"
    if not isinstance(blob_path, str) or Path(blob_path) != expected_relative:
        raise CanonicalBootstrapError("The workbook snapshot cache path is invalid.")
    target = store.root / expected_relative
    try:
        if any(
            parent.is_symlink() for parent in (store.root / "blobs", store.blob_root, target.parent)
        ):
            raise OSError
        if target.is_symlink() or not target.is_file():
            raise OSError
        resolved = target.resolve(strict=True)
        resolved.relative_to(store.root.resolve(strict=True))
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise OSError
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except (OSError, RuntimeError, ValueError):
        raise CanonicalBootstrapError("The workbook snapshot blob is missing or unsafe.") from None
    if actual != digest:
        raise CanonicalBootstrapError("The workbook snapshot failed its SHA-256 integrity check.")
    return resolved, digest


def resolve_approved_snapshot(
    store: SnapshotStore,
    run_id: str,
    *,
    expected_profile: str,
    expected_contract_version: str,
    expected_filename: str,
) -> ApprovedWorkbookSnapshot:
    """Resolve only an explicitly selected, current, schema-approved Task 3 snapshot."""
    selected = _read_manifest(store, run_id)
    if (
        selected.get("profile") != expected_profile
        or selected.get("contract_version") != expected_contract_version
        or selected.get("expected_filename") != expected_filename
        or selected.get("schema_baseline_accepted") is not True
        or selected.get("review_required") is not False
    ):
        raise CanonicalBootstrapError(
            f"Snapshot {run_id} is not an approved {expected_profile} workbook snapshot."
        )

    if selected.get("status") == "ACQUIRED":
        acquisition = selected
    elif selected.get("status") == "SCHEMA_BASELINE_ACCEPTED":
        parent_id = selected.get("parent_run_id")
        if not isinstance(parent_id, str) or not _RUN_ID.fullmatch(parent_id):
            raise CanonicalBootstrapError(
                "The accepted workbook schema review has no valid parent run."
            )
        acquisition = _read_manifest(store, parent_id)
        if (
            acquisition.get("status") != "ACQUIRED_REVIEW_REQUIRED"
            or acquisition.get("artifact_sha256") != selected.get("artifact_sha256")
            or acquisition.get("profile") != expected_profile
            or acquisition.get("contract_version") != expected_contract_version
            or acquisition.get("schema_fingerprint") != selected.get("schema_fingerprint")
            or acquisition.get("source_identity_sha256") != selected.get("source_identity_sha256")
        ):
            raise CanonicalBootstrapError(
                "The workbook schema review does not match its acquired snapshot."
            )
    else:
        raise CanonicalBootstrapError(
            "The selected workbook snapshot is not in an importable state."
        )

    source_identity = acquisition.get("source_identity_sha256")
    if not isinstance(source_identity, str) or not _SHA256.fullmatch(source_identity):
        raise CanonicalBootstrapError("The workbook snapshot source identity is invalid.")
    acquired_at = _timestamp(acquisition.get("acquired_at"), "acquisition")
    schema_fingerprint = selected.get("schema_fingerprint")
    if not isinstance(schema_fingerprint, str) or not _SHA256.fullmatch(schema_fingerprint):
        raise CanonicalBootstrapError("The workbook snapshot schema fingerprint is invalid.")

    latest_run_id: str | None = None
    latest_time: datetime | None = None
    try:
        manifest_paths = list(store.run_root.glob("*.json"))
    except OSError:
        raise CanonicalBootstrapError("The private workbook run store cannot be read.") from None
    for manifest_path in manifest_paths:
        candidate_id = manifest_path.stem
        if not _RUN_ID.fullmatch(candidate_id):
            continue
        candidate = _read_manifest(store, candidate_id)
        if (
            candidate.get("profile") == expected_profile
            and candidate.get("source_identity_sha256") == source_identity
            and candidate.get("status") in {"ACQUIRED", "ACQUIRED_REVIEW_REQUIRED"}
            and candidate.get("artifact_sha256")
        ):
            candidate_at = _timestamp(candidate.get("acquired_at"), "acquisition")
            if latest_time is None or candidate_at > latest_time:
                latest_run_id, latest_time = candidate_id, candidate_at
    if latest_run_id != acquisition.get("run_id"):
        raise CanonicalBootstrapError(
            "A newer workbook acquisition exists for this source; review and select that snapshot."
        )

    path, digest = _snapshot_blob(store, selected)
    profile = (
        PORTFOLIO_PROFILE if expected_profile == PORTFOLIO_PROFILE.key else MARKET_DATA_PROFILE
    )
    try:
        inventory = inspect_workbook(path.read_bytes(), profile)
    except (OSError, WorkbookSourceError):
        raise CanonicalBootstrapError(
            "The workbook blob no longer passes its approved source contract."
        ) from None
    if inventory.schema_fingerprint != schema_fingerprint:
        raise CanonicalBootstrapError(
            "The workbook's recomputed schema fingerprint differs from its approved manifest."
        )
    return ApprovedWorkbookSnapshot(
        run_id=run_id,
        profile=expected_profile,
        expected_filename=expected_filename,
        sha256=digest,
        path=path,
        acquired_at=acquired_at,
        schema_fingerprint=schema_fingerprint,
    )


def _safe_provider_map_path(path: Path) -> Path:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise CanonicalBootstrapError(
            "The reviewed provider-identifier file is missing or unsafe."
        ) from None
    try:
        resolved.relative_to(REPOSITORY_PATH.resolve())
    except (OSError, RuntimeError, ValueError):
        return resolved
    raise CanonicalBootstrapError(
        "Keep the reviewed provider-identifier input outside the repository."
    )


def _provider_evidence_url(value: object, cik: str) -> str:
    if not isinstance(value, str) or len(value) > 1000 or value != value.strip():
        raise CanonicalBootstrapError("Provider identifier evidence must be an exact SEC URL.")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").casefold()
        port = parsed.port
        query = parse_qs(parsed.query, keep_blank_values=True)
    except ValueError:
        raise CanonicalBootstrapError(
            "Provider identifier evidence must be an exact SEC URL."
        ) from None
    if (
        parsed.scheme != "https"
        or not (host == "sec.gov" or host.endswith(".sec.gov"))
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or cik not in value
        or ("CIK" in query and cik not in query["CIK"])
    ):
        raise CanonicalBootstrapError(
            "Provider identifier evidence must identify the exact CIK on sec.gov."
        )
    return value


def load_provider_identifiers(
    path: Path,
    expected_sha256: str,
    *,
    known_tickers: set[str],
) -> ProviderIdentifierPlan:
    """Load a reviewed SEC CIK crosswalk only when its externally reviewed hash matches."""
    if not _SHA256.fullmatch(expected_sha256):
        raise CanonicalBootstrapError(
            "The reviewed provider-map SHA-256 must be 64 lowercase hex characters."
        )
    safe_path = _safe_provider_map_path(path)
    try:
        if safe_path.stat().st_size > 2 * 1024 * 1024:
            raise OSError
        raw = safe_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise CanonicalBootstrapError(
                "The reviewed provider-map SHA-256 does not match the file."
            )
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except CanonicalBootstrapError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise CanonicalBootstrapError("The reviewed provider-identifier file is invalid.") from None
    if not isinstance(value, dict) or set(value) != {
        "format_version",
        "reviewed_by",
        "reviewed_at",
        "mappings",
    }:
        raise CanonicalBootstrapError("The provider-identifier file has an unsupported schema.")
    if value["format_version"] != 1 or isinstance(value["format_version"], bool):
        raise CanonicalBootstrapError("Only provider-identifier format version 1 is supported.")
    reviewer = value["reviewed_by"]
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or len(reviewer) > 128
        or any(ord(character) < 32 for character in reviewer)
    ):
        raise CanonicalBootstrapError("Record the reviewer for the provider-identifier mapping.")
    reviewed_at = _timestamp(value["reviewed_at"], "provider mapping review")
    if reviewed_at > now():
        raise CanonicalBootstrapError(
            "The provider-identifier review timestamp cannot be in the future."
        )
    raw_mappings = value["mappings"]
    if not isinstance(raw_mappings, list) or len(raw_mappings) > 5000:
        raise CanonicalBootstrapError(
            "Provider mappings must be a bounded array of at most 5000 records."
        )
    mappings: list[ProviderIdentifier] = []
    tickers: set[str] = set()
    ciks: set[str] = set()
    for item in raw_mappings:
        if not isinstance(item, dict) or set(item) != {
            "canonical_ticker",
            "identifier_type",
            "identifier_value",
            "provider_company_name",
            "evidence_source",
        }:
            raise CanonicalBootstrapError("A provider mapping row has an unsupported schema.")
        ticker = item["canonical_ticker"]
        cik = item["identifier_value"]
        provider_name = item["provider_company_name"]
        if item["identifier_type"] != "SEC_CIK":
            raise CanonicalBootstrapError(
                "Only reviewed SEC_CIK company identifiers are supported."
            )
        if (
            not isinstance(ticker, str)
            or ticker != ticker.strip().upper()
            or ticker not in known_tickers
        ):
            raise CanonicalBootstrapError(
                "A provider identifier does not map to one exact canonical ticker."
            )
        if not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik):
            raise CanonicalBootstrapError("SEC CIK values must be exact ten-digit strings.")
        if ticker in tickers or cik in ciks:
            raise CanonicalBootstrapError(
                "Duplicate canonical ticker or SEC CIK mapping is ambiguous."
            )
        if (
            not isinstance(provider_name, str)
            or not provider_name.strip()
            or len(provider_name) > 300
            or any(ord(character) < 32 for character in provider_name)
        ):
            raise CanonicalBootstrapError("A provider mapping must include its exact issuer name.")
        evidence = _provider_evidence_url(item["evidence_source"], cik)
        tickers.add(ticker)
        ciks.add(cik)
        mappings.append(ProviderIdentifier(ticker, cik, provider_name.strip(), evidence))
    return ProviderIdentifierPlan(digest, reviewer.strip(), reviewed_at, tuple(mappings))


def build_import_plan(
    store: SnapshotStore,
    portfolio_run_id: str,
    market_run_id: str,
    *,
    observed_at: datetime | None = None,
) -> tuple[ApprovedWorkbookSnapshot, ApprovedWorkbookSnapshot, ImportPlan]:
    portfolio_snapshot = resolve_approved_snapshot(
        store,
        portfolio_run_id,
        expected_profile=PORTFOLIO_PROFILE.key,
        expected_contract_version=PORTFOLIO_PROFILE.contract_version,
        expected_filename=PORTFOLIO_PROFILE.expected_filename,
    )
    market_snapshot = resolve_approved_snapshot(
        store,
        market_run_id,
        expected_profile=MARKET_DATA_PROFILE.key,
        expected_contract_version=MARKET_DATA_PROFILE.contract_version,
        expected_filename=MARKET_DATA_PROFILE.expected_filename,
    )
    plan = legacy_import.build_plan(
        portfolio_snapshot.path,
        market_snapshot.path,
        observed_at,
        portfolio_source_name=portfolio_snapshot.expected_filename,
        market_source_name=market_snapshot.expected_filename,
    )
    return portfolio_snapshot, market_snapshot, plan


def import_blocking_issues(plan: ImportPlan) -> list[dict[str, str]]:
    return [
        issue.as_dict()
        for issue in plan.issues
        if issue.severity == "ERROR" and issue.code not in _ALLOWED_SOURCE_GAP_ERRORS
    ]


def _input_digest(
    portfolio: ApprovedWorkbookSnapshot,
    market: ApprovedWorkbookSnapshot,
    provider_plan: ProviderIdentifierPlan | None,
) -> str:
    fingerprint = {
        "import_version": IMPORT_VERSION,
        "portfolio_run_id": portfolio.run_id,
        "portfolio_sha256": portfolio.sha256,
        "market_run_id": market.run_id,
        "market_sha256": market.sha256,
        "provider_identifiers_sha256": provider_plan.sha256 if provider_plan else None,
    }
    return hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _provider_mapping_report(plan: ProviderIdentifierPlan | None) -> dict[str, Any]:
    if plan is None:
        return {
            "status": "NOT_SUPPLIED",
            "provider_id": SEC_PROVIDER_ID,
            "identifier_type": "SEC_CIK",
            "mapping_count": 0,
            "note": "No reviewed SEC mapping input was supplied; no CIK was inferred.",
        }
    return {
        "status": "REVIEWED_INPUT",
        "provider_id": SEC_PROVIDER_ID,
        "identifier_type": "SEC_CIK",
        "mapping_count": len(plan.mappings),
        "reviewed_by": plan.reviewed_by,
        "reviewed_at": plan.reviewed_at.isoformat(),
        "sha256": plan.sha256,
    }


def _execution_manifest(
    portfolio: ApprovedWorkbookSnapshot,
    market: ApprovedWorkbookSnapshot,
    plan: ImportPlan,
    provider_plan: ProviderIdentifierPlan | None,
) -> tuple[dict[str, Any], list[str]]:
    identity_mapping = {
        "companies": sorted((row.ticker, row.name) for row in plan.companies),
        "listings": sorted(
            (
                row.listing_key,
                row.canonical_ticker,
                row.security_key,
                row.underlying_security_key,
                row.name,
                row.ticker,
                row.venue,
                row.currency,
                row.security_type,
                row.share_class,
            )
            for row in plan.listings
        ),
        "sec_cik_map_sha256": provider_plan.sha256 if provider_plan else None,
    }
    identity_hash = hashlib.sha256(
        json.dumps(
            identity_mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

    def source(
        source_id: str,
        domain: str,
        snapshot: ApprovedWorkbookSnapshot,
        expected_records: int,
        *,
        dependencies: list[str] | None = None,
        decimal_domain: bool = False,
    ) -> dict[str, Any]:
        return {
            "source_id": source_id,
            "domain": domain,
            "source_kind": "workbook_snapshot",
            "source_version": (
                PORTFOLIO_PROFILE.contract_version
                if snapshot.profile == PORTFOLIO_PROFILE.key
                else MARKET_DATA_PROFILE.contract_version
            ),
            "artifact_sha256": snapshot.sha256,
            "identity_map_sha256": identity_hash,
            "recorded_at": snapshot.acquired_at.isoformat(),
            "effective_at": None,
            "expected_records": expected_records,
            "decimal_semantics": "exact_decimal_strings" if decimal_domain else "not_applicable",
            "missing_value_semantics": (
                "null_absent_distinct_from_zero" if decimal_domain else "not_applicable"
            ),
            "history_disposition": "current_snapshot_only",
            "methodology_sha256": None,
            "approval_ref": None,
            "depends_on": dependencies or [],
        }

    priority_count = sum(
        row.get("quality") != "DATA_CHECK"
        for row in research_priority_rows(plan.portfolio_workbook)
    )
    sources = [
        source("company-identities", "company_identities", portfolio, len(plan.companies)),
        source(
            "security-listings",
            "security_listings",
            market,
            len(plan.listings),
            dependencies=["company-identities"],
        ),
        source(
            "portfolio-state",
            "portfolio_state",
            portfolio,
            len(plan.positions) + len(plan.cash) + len(plan.targets),
            dependencies=["company-identities", "security-listings"],
            decimal_domain=True,
        ),
        source(
            "investment-assessments",
            "investment_assessments",
            portfolio,
            len(plan.scores),
            dependencies=["company-identities"],
            decimal_domain=True,
        ),
        source(
            "research-priority",
            "research_contracts",
            portfolio,
            priority_count,
            dependencies=["company-identities"],
            decimal_domain=True,
        ),
        source(
            "ranking-snapshots",
            "ranking_history",
            portfolio,
            sum(len(rows) for rows in plan.rankings.values()),
            dependencies=["portfolio-state", "investment-assessments", "research-priority"],
        ),
    ]
    manifest = {
        "format_version": 1,
        "baseline_id": "canonical-portfolio-bootstrap",
        "sources": sources,
    }
    return manifest, validate_manifest(manifest)


def _company_ids(plan: ImportPlan) -> dict[str, UUID]:
    return {row.ticker: legacy_import._stable_id("company", row.ticker) for row in plan.companies}


def _apply_provider_identifiers(
    session: Session,
    provider_plan: ProviderIdentifierPlan | None,
    company_ids: dict[str, UUID],
) -> dict[str, int]:
    if provider_plan is None:
        return {"inserted": 0, "already_present": 0}
    inserted = 0
    already_present = 0
    for mapping in provider_plan.mappings:
        company_id = company_ids.get(mapping.canonical_ticker)
        if company_id is None or session.get(Company, company_id) is None:
            raise CanonicalBootstrapError(
                "A reviewed provider mapping has no imported company identity."
            )
        same_identifier = session.scalar(
            select(CompanyProviderIdentifier).where(
                CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
                CompanyProviderIdentifier.identifier_type == "SEC_CIK",
                CompanyProviderIdentifier.identifier_value == mapping.identifier_value,
            )
        )
        identity = (company_id, mapping.provider_company_name, mapping.evidence_source)
        if same_identifier is not None:
            if (
                same_identifier.company_id,
                same_identifier.provider_company_name,
                same_identifier.evidence_source,
            ) != identity:
                raise CanonicalBootstrapError(
                    "An SEC CIK is already assigned to a conflicting company identity."
                )
            already_present += 1
            continue
        prior_for_company = session.scalar(
            select(CompanyProviderIdentifier).where(
                CompanyProviderIdentifier.company_id == company_id,
                CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
                CompanyProviderIdentifier.identifier_type == "SEC_CIK",
            )
        )
        if prior_for_company is not None:
            raise CanonicalBootstrapError(
                "A company already has a different reviewed SEC CIK; it will not be overwritten."
            )
        session.add(
            CompanyProviderIdentifier(
                id=legacy_import._stable_id(
                    "company-provider-identifier",
                    f"{provider_plan.sha256}:{mapping.canonical_ticker}:{mapping.identifier_value}",
                ),
                company_id=company_id,
                provider_id=SEC_PROVIDER_ID,
                identifier_type="SEC_CIK",
                identifier_value=mapping.identifier_value,
                provider_company_name=mapping.provider_company_name,
                evidence_source=mapping.evidence_source,
                effective_at=provider_plan.reviewed_at,
                recorded_at=now(),
                actor="IMPORT",
            )
        )
        inserted += 1
    session.flush()
    return {"inserted": inserted, "already_present": already_present}


def _research_priority_reconciliation(session: Session, plan: ImportPlan) -> dict[str, Any]:
    rows = research_priority_rows(plan.portfolio_workbook)
    expected = [row for row in rows if row.get("quality") != "DATA_CHECK"]
    matched = 0
    mismatches: list[str] = []
    for row in expected:
        ticker = cast(str, row["ticker"])
        company_id = legacy_import._stable_id("company", ticker)
        record = session.scalar(
            select(ResearchPriorityInput).where(
                ResearchPriorityInput.company_id == company_id,
                ResearchPriorityInput.source_digest == plan.portfolio_workbook.sha256,
            )
        )
        if record is None:
            mismatches.append("A reviewed candidate priority input is absent.")
            continue
        expected_values = (
            ticker,
            row.get("candidate_tier"),
            row.get("priority_seed"),
            row.get("input_quality"),
            row.get("quality_reason"),
            row.get("bucket_source_ref"),
            row.get("priority_seed_source_ref"),
        )
        actual_values = (
            record.canonical_ticker,
            record.candidate_tier,
            record.priority_seed,
            record.input_quality,
            record.quality_reason,
            record.bucket_source_ref,
            record.priority_seed_source_ref,
        )
        if actual_values == expected_values:
            matched += 1
        else:
            mismatches.append("A candidate priority input differs from its frozen source values.")
    return {
        "status": "MATCHED" if not mismatches else "MISMATCH",
        "expected": len(expected),
        "matched": matched,
        "source_data_check_exclusions": len(rows) - len(expected),
        "mismatches": mismatches[:20],
    }


def _provider_reconciliation(
    session: Session,
    provider_plan: ProviderIdentifierPlan | None,
    company_ids: dict[str, UUID],
) -> dict[str, Any]:
    if provider_plan is None:
        return {"status": "NOT_REQUIRED", "expected": 0, "matched": 0, "mismatches": []}
    mismatches: list[str] = []
    matched = 0
    for mapping in provider_plan.mappings:
        company_id = company_ids.get(mapping.canonical_ticker)
        record = session.scalar(
            select(CompanyProviderIdentifier).where(
                CompanyProviderIdentifier.company_id == company_id,
                CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
                CompanyProviderIdentifier.identifier_type == "SEC_CIK",
                CompanyProviderIdentifier.identifier_value == mapping.identifier_value,
            )
        )
        if record is None or (
            record.provider_company_name,
            record.evidence_source,
        ) != (mapping.provider_company_name, mapping.evidence_source):
            mismatches.append("A reviewed SEC company identifier differs from its frozen mapping.")
        else:
            matched += 1
    return {
        "status": "MATCHED" if not mismatches else "MISMATCH",
        "expected": len(provider_plan.mappings),
        "matched": matched,
        "mismatches": mismatches[:20],
    }


def reconcile_canonical_state(
    session: Session,
    plan: ImportPlan,
    provider_plan: ProviderIdentifierPlan | None,
) -> dict[str, Any]:
    companies = _company_ids(plan)
    portfolio_id = legacy_import._stable_id("portfolio", "legacy-default")
    portfolio = session.get(Portfolio, portfolio_id)
    if portfolio is None:
        return {
            "status": "MISMATCH",
            "mismatch_count": 1,
            "domains": {
                "portfolio": {
                    "status": "MISMATCH",
                    "expected": 1,
                    "matched": 0,
                    "mismatches": ["The canonical portfolio identity is absent."],
                }
            },
        }
    ids: dict[str, UUID] = {f"company:{ticker}": value for ticker, value in companies.items()}
    security_ids: dict[str, UUID] = {}
    for listing in plan.listings:
        security_ids.setdefault(
            listing.security_key,
            legacy_import._stable_id("security", listing.security_key),
        )
        ids[f"security:{listing.security_key}"] = security_ids[listing.security_key]
        if listing.underlying_security_key is not None:
            underlying_id = legacy_import._stable_id("security", listing.underlying_security_key)
            ids[f"security:{listing.underlying_security_key}"] = underlying_id
        ids[f"listing:{listing.listing_key}"] = legacy_import._stable_id(
            "listing", f"{listing.venue}:{listing.ticker}"
        )
    core = legacy_import._reconcile(session, plan, ids, companies, portfolio)
    domains = dict(core["domains"])
    for name, check in (
        ("research_priority_inputs", _research_priority_reconciliation(session, plan)),
        ("provider_identifiers", _provider_reconciliation(session, provider_plan, companies)),
    ):
        domains[name] = check
    mismatch_count = sum(
        max(0, int(item.get("expected", 0)) - int(item.get("matched", 0)))
        for item in domains.values()
        if item.get("status") == "MISMATCH"
    )
    return {
        "status": "MATCHED" if mismatch_count == 0 else "MISMATCH",
        "mismatch_count": mismatch_count,
        "unresolved_source_issue_count": core.get("unresolved_source_issue_count", 0),
        "domains": domains,
    }


def _base_report(
    portfolio: ApprovedWorkbookSnapshot,
    market: ApprovedWorkbookSnapshot,
    plan: ImportPlan,
    provider_plan: ProviderIdentifierPlan | None,
) -> dict[str, Any]:
    report = plan.report()
    execution_manifest, dependency_order = _execution_manifest(
        portfolio, market, plan, provider_plan
    )
    execution_manifest_sha256 = hashlib.sha256(
        json.dumps(
            execution_manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    report["bootstrap"] = {
        "import_version": IMPORT_VERSION,
        "execution_manifest_sha256": execution_manifest_sha256,
        "execution_manifest_format_version": execution_manifest["format_version"],
        "portfolio_snapshot_run_id": portfolio.run_id,
        "market_snapshot_run_id": market.run_id,
        "portfolio_snapshot_sha256": portfolio.sha256,
        "market_snapshot_sha256": market.sha256,
        "provider_identifiers": _provider_mapping_report(provider_plan),
        "dependency_order": dependency_order,
    }
    report["blocking_issues"] = import_blocking_issues(plan)
    report["source_gaps"] = [
        issue.as_dict()
        for issue in plan.issues
        if issue.severity == "ERROR" and issue.code in _ALLOWED_SOURCE_GAP_ERRORS
    ]
    report["ready_to_apply"] = not report["blocking_issues"]
    return report


def _database_preflight_summary(
    session: Session, plan: ImportPlan, input_digest: str
) -> dict[str, Any]:
    existing_run = session.scalar(
        select(CanonicalBootstrapRun).where(CanonicalBootstrapRun.input_digest == input_digest)
    )
    existing_batch = session.scalar(
        select(LegacyImportBatch).where(LegacyImportBatch.source_digest == plan.source_digest)
    )
    company_count = int(session.scalar(select(func.count()).select_from(Company)) or 0)
    portfolio_count = int(session.scalar(select(func.count()).select_from(Portfolio)) or 0)
    safe_resume = existing_run is not None or existing_batch is not None
    empty = company_count == 0 and portfolio_count == 0
    return {
        "status": "RESUMABLE" if safe_resume else "EMPTY" if empty else "BLOCKED_NONEMPTY",
        "company_count": company_count,
        "portfolio_count": portfolio_count,
        "matching_canonical_receipt": existing_run is not None,
        "matching_legacy_import_receipt": existing_batch is not None,
    }


def apply_canonical_bootstrap(
    session: Session,
    *,
    portfolio_snapshot: ApprovedWorkbookSnapshot,
    market_snapshot: ApprovedWorkbookSnapshot,
    plan: ImportPlan,
    provider_plan: ProviderIdentifierPlan | None,
    observed_at: datetime,
    resume: bool = False,
) -> dict[str, Any]:
    """Apply all Task 4 domains in one transaction and persist a content-keyed receipt."""
    input_digest = _input_digest(portfolio_snapshot, market_snapshot, provider_plan)
    report = _base_report(portfolio_snapshot, market_snapshot, plan, provider_plan)
    report["execution_mode"] = "RESUME" if resume else "APPLY"
    blocking = report["blocking_issues"]
    if blocking:
        report["status"] = "BLOCKED_SOURCE_VALIDATION"
        raise CanonicalBootstrapError("The source plan contains ambiguous or unsupported mappings.")

    existing_run = session.scalar(
        select(CanonicalBootstrapRun).where(CanonicalBootstrapRun.input_digest == input_digest)
    )
    if existing_run is not None:
        report["status"] = "ALREADY_APPLIED"
        report["reconciliation"] = reconcile_canonical_state(session, plan, provider_plan)
        report["canonical_receipt"] = str(existing_run.id)
        report["recorded_at"] = existing_run.recorded_at.isoformat()
        if report["reconciliation"]["status"] != "MATCHED":
            report["status"] = "RECONCILIATION_MISMATCH"
        return report

    blocking_state = _database_preflight_summary(session, plan, input_digest)
    report["database_preflight"] = blocking_state
    if blocking_state["status"] == "BLOCKED_NONEMPTY":
        raise CanonicalBootstrapError(
            "The target contains application companies or portfolios without a matching "
            "import receipt."
        )

    existing_issue_keys = {(item.code, item.source, item.message) for item in plan.issues}
    try:
        legacy_report = legacy_import.apply_plan(session, plan)
    except legacy_import.AlreadyImported as imported:
        legacy_report = dict(imported.batch.report)
        legacy_report["status"] = "ALREADY_APPLIED"
    report["legacy_import"] = legacy_report

    companies = _company_ids(plan)
    report["provider_identifier_import"] = _apply_provider_identifiers(
        session, provider_plan, companies
    )
    priority_report = import_research_priority_inputs(
        session,
        plan.portfolio_workbook,
        apply=True,
        observed_at=observed_at,
    )
    report["research_priority_import"] = priority_report

    newly_added_errors = [
        issue.as_dict()
        for issue in plan.issues
        if issue.severity == "ERROR"
        and (issue.code, issue.source, issue.message) not in existing_issue_keys
    ]
    if newly_added_errors:
        report["late_validation_errors"] = newly_added_errors
        raise CanonicalBootstrapError(
            "A write-time validation failed; the complete bootstrap transaction was rolled back."
        )

    report["reconciliation"] = reconcile_canonical_state(session, plan, provider_plan)
    if report["reconciliation"]["status"] != "MATCHED":
        raise CanonicalReconciliationError(report)
    report["status"] = "APPLIED_WITH_REPORTED_SOURCE_GAPS" if report["source_gaps"] else "APPLIED"
    receipt_id = legacy_import._stable_id("canonical-bootstrap-run", input_digest)
    report["canonical_receipt"] = str(receipt_id)
    report["resume_policy"] = (
        "All domain stages share one database transaction. An interruption before commit leaves "
        "no canonical receipt; rerun resume with the same snapshot run IDs and provider-map hash."
    )
    session.add(
        CanonicalBootstrapRun(
            id=receipt_id,
            input_digest=input_digest,
            source_digest=plan.source_digest,
            portfolio_snapshot_run_id=portfolio_snapshot.run_id,
            market_snapshot_run_id=market_snapshot.run_id,
            provider_identifiers_sha256=provider_plan.sha256 if provider_plan else None,
            import_version=IMPORT_VERSION,
            observed_at=observed_at,
            recorded_at=now(),
            status="APPLIED_WITH_GAPS" if report["source_gaps"] else "APPLIED",
            report=report,
        )
    )
    session.flush()
    return report


def _write_private_report(store: SnapshotStore, report: dict[str, Any]) -> str:
    report_root = store.root / "bootstrap-runs"
    if report_root.is_symlink():
        raise CanonicalBootstrapError("The private bootstrap report directory cannot be a symlink.")
    report_root.mkdir(mode=0o700, exist_ok=True)
    if os.name != "nt":
        report_root.chmod(0o700)
    report_id = uuid.uuid4().hex
    report_path = report_root / f"{report_id}.json"
    payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor = os.open(report_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise CanonicalBootstrapError(
            "The private bootstrap report could not be written."
        ) from None
    return str(report_path.relative_to(store.root))


def _verify_target(engine: Engine, settings: Settings, requested_environment: str) -> None:
    try:
        verify_database_preflight(
            engine,
            configured_target_environment=settings.database_target_environment,
            requested_target_environment=requested_environment,
        )
    except (BootstrapPreflightError, DatabaseWriteTargetError):
        raise
    except Exception:
        raise CanonicalBootstrapError(
            "Target identity or Alembic compatibility could not be verified; no bootstrap "
            "writes were made."
        ) from None


def _load_provider_plan(
    args: argparse.Namespace, plan: ImportPlan
) -> ProviderIdentifierPlan | None:
    if args.provider_identifiers is None:
        if args.provider_identifiers_sha256 is not None:
            raise CanonicalBootstrapError("A provider-map hash requires --provider-identifiers.")
        return None
    if args.provider_identifiers_sha256 is None:
        raise CanonicalBootstrapError(
            "Pass the reviewed --provider-identifiers-sha256 with the provider mapping file."
        )
    return load_provider_identifiers(
        args.provider_identifiers,
        args.provider_identifiers_sha256,
        known_tickers={item.ticker for item in plan.companies},
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "apply", "resume", "reconcile"):
        subparser = commands.add_parser(command)
        subparser.add_argument(
            "--store", type=Path, required=True, help="Private Task 3 snapshot store"
        )
        subparser.add_argument("--portfolio-run", required=True)
        subparser.add_argument("--market-run", required=True)
        subparser.add_argument("--provider-identifiers", type=Path)
        subparser.add_argument("--provider-identifiers-sha256")
        subparser.add_argument(
            "--target-environment",
            choices=("development", "rehearsal", "production"),
            required=True,
            help="must exactly match DATABASE_TARGET_ENVIRONMENT",
        )
        subparser.add_argument("--observed-at", type=datetime.fromisoformat)
    return parser


def _fail_report(
    store: SnapshotStore | None,
    error: Exception,
    *,
    report: dict[str, Any] | None = None,
) -> int:
    failure_report = report or {
        "status": "FAILED",
        "error_code": getattr(error, "code", type(error).__name__),
        "message": (
            str(error)
            if isinstance(
                error,
                (
                    CanonicalBootstrapError,
                    BootstrapPreflightError,
                    DatabaseWriteTargetError,
                    WorkbookSourceError,
                ),
            )
            else "Bootstrap failed; target, source, or schema validation did not complete."
        ),
        "data_values_and_credentials_redacted_from_cli": True,
    }
    if store is not None:
        try:
            relative_report = _write_private_report(store, failure_report)
        except CanonicalBootstrapError:
            relative_report = "unavailable"
    else:
        relative_report = "unavailable"
    print(
        json.dumps(
            {"status": failure_report.get("status", "FAILED"), "report": relative_report},
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store: SnapshotStore | None = None
    engine = None
    try:
        store = SnapshotStore(args.store)
        settings = Settings()
        if settings.database_url is None:
            raise CanonicalBootstrapError("DATABASE_URL is required for target verification.")
        engine = create_database_engine(
            settings,
            write_operation="canonical_portfolio_bootstrap",
            write_operation_kind="bootstrap",
        )
        if engine is None:
            raise CanonicalBootstrapError("DATABASE_URL is required for target verification.")
        _verify_target(engine, settings, args.target_environment)

        observed_at = args.observed_at or now()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise CanonicalBootstrapError("--observed-at must include a timezone offset.")
        if observed_at.astimezone(UTC) > now():
            raise CanonicalBootstrapError("--observed-at cannot be in the future.")
        portfolio, market, plan = build_import_plan(
            store,
            args.portfolio_run,
            args.market_run,
            observed_at=observed_at.astimezone(UTC),
        )
        provider_plan = _load_provider_plan(args, plan)
        report = _base_report(portfolio, market, plan, provider_plan)
        report["input_digest"] = _input_digest(portfolio, market, provider_plan)
        with Session(engine) as session:
            if args.command == "preview":
                report["database_preflight"] = _database_preflight_summary(
                    session, plan, report["input_digest"]
                )
                report["status"] = (
                    "BLOCKED_NONEMPTY_TARGET"
                    if report["database_preflight"]["status"] == "BLOCKED_NONEMPTY"
                    else "READY_WITH_SOURCE_GAPS"
                    if report["ready_to_apply"] and report.get("source_gaps")
                    else "READY"
                    if report["ready_to_apply"]
                    else "BLOCKED_SOURCE_VALIDATION"
                )
            elif args.command in {"apply", "resume"} and not report["ready_to_apply"]:
                report["status"] = "BLOCKED_SOURCE_VALIDATION"
                relative_report = _write_private_report(store, report)
                print(
                    json.dumps(
                        {"status": report["status"], "report": relative_report}, sort_keys=True
                    )
                )
                return 2
            elif args.command == "reconcile":
                report["reconciliation"] = reconcile_canonical_state(session, plan, provider_plan)
                report["status"] = report["reconciliation"]["status"]
            else:
                with session.begin():
                    report = apply_canonical_bootstrap(
                        session,
                        portfolio_snapshot=portfolio,
                        market_snapshot=market,
                        plan=plan,
                        provider_plan=provider_plan,
                        observed_at=observed_at.astimezone(UTC),
                        resume=args.command == "resume",
                    )
        relative_report = _write_private_report(store, report)
        print(json.dumps({"status": report["status"], "report": relative_report}, sort_keys=True))
        return (
            0
            if report["status"]
            not in {
                "BLOCKED_NONEMPTY_TARGET",
                "BLOCKED_SOURCE_VALIDATION",
                "MISMATCH",
                "RECONCILIATION_MISMATCH",
            }
            else 2
        )
    except CanonicalReconciliationError as error:
        return _fail_report(store, error, report=error.report)
    except (
        CanonicalBootstrapError,
        BootstrapPreflightError,
        DatabaseWriteTargetError,
        WorkbookSourceError,
        OSError,
        ValueError,
    ) as error:
        return _fail_report(store, error)
    except Exception as error:
        # SQLAlchemy and DBAPI exception strings can contain connection details and data values.
        return _fail_report(store, error)
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
