"""Bounded, resumable bootstrap of SEC-reported facts and filing references.

This stage composes the established Company Facts and EDGAR submissions adapters
with the append-only canonical import functions. It does not fetch consensus data,
download filing bodies, infer identities, or recalculate financial models.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.bootstrap_preflight import verify_database_preflight
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import DatabaseWriteTargetError
from portfolio_api.domain.models import (
    Company,
    CompanyProviderIdentifier,
    CurrentLifecycle,
    ExternalRawPayload,
    FundamentalsBootstrapCheckpoint,
    FundamentalsBootstrapRun,
    LifecycleEvent,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
    SourceDocument,
    SourceDocumentBatch,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.reported_fundamentals import (
    SEC_NORMALIZER_VERSION,
    SEC_PROVIDER_ID,
    SecCompanyFactsProvider,
    ingest_sec_company_facts,
)
from portfolio_api.settings import Settings
from portfolio_api.source_documents import (
    SEC_DOCUMENT_NORMALIZER_VERSION,
    SEC_SUBMISSIONS_VERSION,
    SecSubmissionsProvider,
    ingest_sec_submissions,
)

BOOTSTRAP_VERSION = "sec-fundamentals-source-bootstrap-v1"
MAX_CHECKPOINTS_PER_INVOCATION = 10
DEFAULT_CHECKPOINTS_PER_INVOCATION = 5
MAX_CHECKPOINT_FAILURES = 3
MAX_HISTORY_FILES_PER_FETCH = 5
MIN_SEC_REQUEST_INTERVAL_SECONDS = 0.15
LOCK_NAMESPACE = 1296321106
LOCK_KEY = 1178681684
ACTIVE_LIFECYCLES = frozenset({"PORTFOLIO", "WATCHLIST"})
STAGE_ORDER = ("SOURCE_DOCUMENTS", "REPORTED_FUNDAMENTALS")
REPOSITORY_PATH = Path(__file__).resolve().parents[4]
_CIK_PATTERN = re.compile(r"^[0-9]{10}$")
_CONTACT_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+$")


class FundamentalsBootstrapError(RuntimeError):
    """Operator-actionable bootstrap configuration or integrity failure."""


class FundamentalsBootstrapExecutionError(RuntimeError):
    """Unexpected interrupted work left safely resumable in the run ledger."""


@dataclass(frozen=True)
class ReviewedCikMapping:
    mapping_id: UUID
    company_id: UUID
    company_name: str
    cik: str
    provider_company_name: str
    evidence_source: str
    lifecycle: str | None
    effective_at: datetime
    recorded_at: datetime

    def manifest(self) -> dict[str, str | None]:
        return {
            "mapping_identifier_id": str(self.mapping_id),
            "company_id": str(self.company_id),
            "company_name": self.company_name,
            "cik": self.cik,
            "provider_company_name": self.provider_company_name,
            "evidence_source": self.evidence_source,
            "lifecycle": self.lifecycle,
            "effective_at": self.effective_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True)
class ProviderFetchResult:
    records: tuple[RawProviderRecord, ...]
    deferred_history_file_ids: tuple[str, ...] = ()
    skipped_history_files: int = 0
    request_count: int = 1


class ProviderFetchFailure(Exception):
    """Provider failure with the number of HTTP requests attempted so far."""

    def __init__(self, error: Exception, request_count: int) -> None:
        self.error = error
        self.request_count = request_count
        super().__init__(type(error).__name__)


class ProviderAdapter(Protocol):
    async def fetch(
        self,
        *,
        stage: str,
        company_id: UUID,
        cik: str,
        query: ProviderQuery,
        known_source_record_ids: set[str],
    ) -> ProviderFetchResult: ...


class SecBootstrapProvider:
    """Adapter facade over the existing SEC Company Facts and submissions paths."""

    def __init__(self, user_agent: str) -> None:
        if not _has_contact_email(user_agent):
            raise FundamentalsBootstrapError(
                "SEC_USER_AGENT must identify the application and a monitored contact email."
            )
        self.user_agent = user_agent.strip()

    async def fetch(
        self,
        *,
        stage: str,
        company_id: UUID,
        cik: str,
        query: ProviderQuery,
        known_source_record_ids: set[str],
    ) -> ProviderFetchResult:
        identifiers = {company_id: cik}
        if stage == "REPORTED_FUNDAMENTALS":
            facts_provider = SecCompanyFactsProvider(identifiers, self.user_agent)
            try:
                records = await facts_provider.fetch(query)
            except Exception as error:
                raise ProviderFetchFailure(error, request_count=1) from error
            return ProviderFetchResult(tuple(records), request_count=1)
        if stage == "SOURCE_DOCUMENTS":
            documents_provider = SecSubmissionsProvider(
                identifiers,
                self.user_agent,
                known_source_record_ids=known_source_record_ids,
                max_new_history_files=MAX_HISTORY_FILES_PER_FETCH,
            )
            try:
                records = await documents_provider.fetch(query)
            except Exception as error:
                raise ProviderFetchFailure(error, documents_provider.request_count) from error
            return ProviderFetchResult(
                tuple(records),
                tuple(documents_provider.deferred_history_file_ids),
                documents_provider.skipped_history_files,
                documents_provider.request_count,
            )
        raise FundamentalsBootstrapError("The requested SEC bootstrap stage is unsupported.")


def _now() -> datetime:
    return datetime.now(UTC)


def _has_contact_email(user_agent: str) -> bool:
    parts = user_agent.strip().split()
    return bool(parts and _CONTACT_EMAIL_PATTERN.fullmatch(parts[-1]))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _current_lifecycle(session: Session) -> dict[UUID, str]:
    rows = session.execute(
        select(CurrentLifecycle.company_id, LifecycleEvent.new_state)
        .join(LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id)
        .order_by(CurrentLifecycle.company_id)
    ).all()
    return {company_id: str(state) for company_id, state in rows}


def _load_reviewed_cik_mappings(
    session: Session, company_id: UUID | None = None
) -> list[ReviewedCikMapping]:
    statement = (
        select(CompanyProviderIdentifier, Company)
        .join(Company, Company.id == CompanyProviderIdentifier.company_id)
        .where(
            CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
            CompanyProviderIdentifier.identifier_type == "SEC_CIK",
        )
        .order_by(CompanyProviderIdentifier.company_id, CompanyProviderIdentifier.id)
    )
    if company_id is not None:
        statement = statement.where(CompanyProviderIdentifier.company_id == company_id)
    rows = session.execute(statement).all()
    by_company: dict[UUID, list[tuple[CompanyProviderIdentifier, Company]]] = defaultdict(list)
    by_cik: dict[str, set[UUID]] = defaultdict(set)
    for mapping, company in rows:
        by_company[mapping.company_id].append((mapping, company))
        by_cik[mapping.identifier_value].add(mapping.company_id)
    ambiguous = sorted(str(key) for key, items in by_company.items() if len(items) != 1)
    duplicate_ciks = sorted(cik for cik, companies in by_cik.items() if len(companies) != 1)
    if ambiguous or duplicate_ciks:
        raise FundamentalsBootstrapError(
            "Reviewed SEC identity mappings are ambiguous. Resolve duplicate company or CIK "
            "mappings before preparing this run."
        )
    lifecycle = _current_lifecycle(session)
    mappings: list[ReviewedCikMapping] = []
    for mapping, company in (items[0] for items in by_company.values()):
        if not _CIK_PATTERN.fullmatch(mapping.identifier_value):
            raise FundamentalsBootstrapError(
                "A reviewed SEC CIK must contain exactly ten digits, including leading zeroes."
            )
        evidence = urlsplit(mapping.evidence_source)
        evidence_host = evidence.hostname.casefold().rstrip(".") if evidence.hostname else ""
        cik_number = str(int(mapping.identifier_value))
        evidence_reference = f"{evidence.path}?{evidence.query}"
        if (
            not mapping.provider_company_name
            or not mapping.provider_company_name.strip()
            or evidence.scheme != "https"
            or not (evidence_host == "sec.gov" or evidence_host.endswith(".sec.gov"))
            or re.search(rf"(?<![0-9]){re.escape(cik_number)}(?![0-9])", evidence_reference) is None
        ):
            raise FundamentalsBootstrapError(
                "Each reviewed SEC CIK mapping needs an issuer name and an HTTPS SEC.gov "
                "evidence URL containing that exact CIK."
            )
        mappings.append(
            ReviewedCikMapping(
                mapping_id=mapping.id,
                company_id=company.id,
                company_name=company.name,
                cik=mapping.identifier_value,
                provider_company_name=mapping.provider_company_name,
                evidence_source=mapping.evidence_source,
                lifecycle=lifecycle.get(company.id),
                effective_at=mapping.effective_at,
                recorded_at=mapping.recorded_at,
            )
        )
    return sorted(mappings, key=lambda item: (item.company_name.casefold(), str(item.company_id)))


def _unmapped_active_companies(
    session: Session, mappings: Sequence[ReviewedCikMapping]
) -> list[dict[str, str]]:
    mapped_ids = {item.company_id for item in mappings}
    rows = session.execute(
        select(Company.id, Company.name, LifecycleEvent.new_state)
        .join(CurrentLifecycle, CurrentLifecycle.company_id == Company.id)
        .join(LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id)
        .where(LifecycleEvent.new_state.in_(ACTIVE_LIFECYCLES))
        .order_by(Company.name, Company.id)
    ).all()
    return [
        {"company_id": str(company_id), "company_name": name, "lifecycle": str(state)}
        for company_id, name, state in rows
        if company_id not in mapped_ids
    ]


def _mapping_sha256(mappings: Sequence[ReviewedCikMapping]) -> str:
    manifest = [
        {key: value for key, value in item.manifest().items() if key != "lifecycle"}
        for item in mappings
    ]
    return _sha256(_canonical_json(manifest).encode("utf-8"))


def preview_fundamentals_bootstrap(
    session: Session,
    *,
    target_environment: str,
    company_id: UUID | None = None,
) -> dict[str, Any]:
    """Return a request inventory from reviewed database mappings without network access."""
    if target_environment not in {"development", "rehearsal"}:
        raise FundamentalsBootstrapError(
            "SEC fundamentals bootstrap accepts development or rehearsal targets only."
        )
    mappings = _load_reviewed_cik_mappings(session, company_id)
    unmapped = _unmapped_active_companies(session, mappings) if company_id is None else []
    return {
        "status": "READY" if mappings else "BLOCKED",
        "target_environment": target_environment,
        "bootstrap_version": BOOTSTRAP_VERSION,
        "mapping_sha256": _mapping_sha256(mappings),
        "provider": SEC_PROVIDER_ID,
        "stages": list(STAGE_ORDER),
        "mapped_company_count": len(mappings),
        "active_company_without_reviewed_cik_count": len(unmapped),
        "active_companies_without_reviewed_cik": unmapped,
        "mappings": [item.manifest() for item in mappings],
        "source_limits": {
            "sec_user_agent_required": True,
            "minimum_request_interval_seconds": MIN_SEC_REQUEST_INTERVAL_SECONDS,
            "historical_submission_files_per_checkpoint": MAX_HISTORY_FILES_PER_FETCH,
            "consensus_estimates": "EXCLUDED_LICENSED_SOURCE_DISABLED",
            "filing_bodies": "NOT_DOWNLOADED",
        },
        "reason": None if mappings else "NO_REVIEWED_SEC_CIK_MAPPINGS",
    }


def prepare_fundamentals_bootstrap(
    session: Session,
    *,
    target_environment: str,
    company_id: UUID | None = None,
) -> FundamentalsBootstrapRun:
    preview = preview_fundamentals_bootstrap(
        session, target_environment=target_environment, company_id=company_id
    )
    mappings = _load_reviewed_cik_mappings(session, company_id)
    mapping_hash = str(preview["mapping_sha256"])
    scope = {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "provider_id": SEC_PROVIDER_ID,
        "company_facts_provider_schema_version": "companyfacts-v1",
        "company_facts_normalizer_version": SEC_NORMALIZER_VERSION,
        "submissions_provider_schema_version": SEC_SUBMISSIONS_VERSION,
        "submissions_normalizer_version": SEC_DOCUMENT_NORMALIZER_VERSION,
        "mapping_sha256": mapping_hash,
        "mappings": [item.manifest() for item in mappings],
        "unmapped_active_companies": preview["active_companies_without_reviewed_cik"],
        "stage_order": list(STAGE_ORDER),
        "consensus_estimates": "EXCLUDED_LICENSED_SOURCE_DISABLED",
        "filing_bodies": "NOT_DOWNLOADED",
        "history_files_per_page": MAX_HISTORY_FILES_PER_FETCH,
    }
    input_digest = _sha256(
        _canonical_json({"target_environment": target_environment, "scope": scope}).encode("utf-8")
    )
    run = FundamentalsBootstrapRun(
        id=uuid4(),
        input_digest=input_digest,
        mapping_sha256=mapping_hash,
        bootstrap_version=BOOTSTRAP_VERSION,
        target_environment=target_environment,
        scope=scope,
        status="PREPARED" if mappings else "BLOCKED",
        prepared_at=_now(),
        finished_at=None if mappings else _now(),
        report={"status": "PREPARED" if mappings else "BLOCKED", "preview": preview},
    )
    session.add(run)
    session.flush()
    sequence_number = 0
    for stage in STAGE_ORDER:
        for mapping in mappings:
            session.add(
                FundamentalsBootstrapCheckpoint(
                    id=uuid4(),
                    run_id=run.id,
                    sequence_number=sequence_number,
                    stage=stage,
                    company_id=mapping.company_id,
                    mapping_identifier_id=mapping.mapping_id,
                    cik=mapping.cik,
                    status="PENDING",
                    attempt_count=0,
                    page_count=0,
                    provider_request_count=0,
                    retryable=False,
                    report={"company_name": mapping.company_name, "cik": mapping.cik},
                )
            )
            sequence_number += 1
    session.flush()
    return run


def _mapping_still_matches(
    session: Session,
    checkpoint: FundamentalsBootstrapCheckpoint,
    run: FundamentalsBootstrapRun,
) -> tuple[bool, str | None]:
    frozen = next(
        (
            item
            for item in _dict_items(run.scope.get("mappings"))
            if item.get("mapping_identifier_id") == str(checkpoint.mapping_identifier_id)
        ),
        None,
    )
    if not isinstance(frozen, dict):
        return False, "The frozen SEC identity mapping is absent from the run manifest."
    mapping = session.get(CompanyProviderIdentifier, checkpoint.mapping_identifier_id)
    company = session.get(Company, checkpoint.company_id)
    if mapping is None or company is None:
        return False, "The reviewed SEC identity mapping or canonical company no longer exists."
    current = {
        "mapping_identifier_id": str(mapping.id),
        "company_id": str(mapping.company_id),
        "company_name": company.name,
        "cik": mapping.identifier_value,
        "provider_company_name": mapping.provider_company_name,
        "evidence_source": mapping.evidence_source,
        "effective_at": mapping.effective_at.isoformat(),
        "recorded_at": mapping.recorded_at.isoformat(),
    }
    if any(current.get(key) != frozen.get(key) for key in current):
        return False, "The reviewed SEC identity mapping changed after run preparation."
    if (
        mapping.provider_id != SEC_PROVIDER_ID
        or mapping.identifier_type != "SEC_CIK"
        or mapping.identifier_value != checkpoint.cik
    ):
        return False, "The prepared checkpoint no longer matches its exact SEC CIK mapping."
    return True, None


def _query_for_checkpoint(checkpoint: FundamentalsBootstrapCheckpoint) -> ProviderQuery:
    domain = (
        ExternalDataDomain.SOURCE_DOCUMENTS
        if checkpoint.stage == "SOURCE_DOCUMENTS"
        else ExternalDataDomain.REPORTED_FUNDAMENTALS
    )
    return ProviderQuery(
        domain=domain,
        subjects=(
            CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=checkpoint.company_id),
        ),
        requested_at=_now(),
    )


def _known_history_records(session: Session, cik: str) -> set[str]:
    return set(
        session.scalars(
            select(ExternalRawPayload.source_record_id).where(
                ExternalRawPayload.source_document_batch_id.is_not(None),
                ExternalRawPayload.provider_id == SEC_PROVIDER_ID,
                ExternalRawPayload.domain == ExternalDataDomain.SOURCE_DOCUMENTS.value,
                ExternalRawPayload.source_record_id.like(f"CIK{cik}:HISTORY:%"),
            )
        )
    )


def _retry_delay(failure_count: int) -> int:
    return int(min(5 * (2 ** max(0, failure_count - 1)), 60))


def _provider_error(error: Exception) -> tuple[str, str, bool, bool]:
    if isinstance(error, HTTPError):
        status = int(error.code)
        retryable = status == 429 or status >= 500
        blocked = status in {401, 403}
        return (
            f"SEC_HTTP_{status}",
            "SEC rejected the request; inspect the configured user agent and fair-access policy.",
            retryable,
            blocked,
        )
    if isinstance(error, (URLError, TimeoutError, OSError)):
        return (
            "SEC_NETWORK_FAILURE",
            "The SEC request did not complete; resume after the bounded retry delay.",
            True,
            False,
        )
    if isinstance(error, ValueError):
        return (
            "SEC_RESPONSE_REJECTED",
            "The SEC response or request identity failed validation; review the "
            "mapping and source status.",
            False,
            True,
        )
    return (
        "SEC_PROVIDER_FAILURE",
        "The SEC provider operation failed; inspect sanitized runtime logs before retrying.",
        False,
        False,
    )


@contextmanager
def _advisory_lock(engine: Engine) -> Iterator[None]:
    with engine.connect() as connection:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:namespace, :lock_key)"),
                {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
            ).scalar()
        )
        connection.commit()
        if not acquired:
            raise FundamentalsBootstrapError(
                "Another fundamentals bootstrap is running against this database."
            )
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                {"namespace": LOCK_NAMESPACE, "lock_key": LOCK_KEY},
            )
            connection.commit()


def _json_value(value: Any) -> Any:
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _batch_models(stage: str) -> tuple[type[Any], type[Any], type[Any], str]:
    if stage == "REPORTED_FUNDAMENTALS":
        return (
            ReportedFundamentalBatch,
            ReportedFundamentalObservation,
            ExternalRawPayload,
            "reported_fundamental_batch_id",
        )
    return SourceDocumentBatch, SourceDocument, ExternalRawPayload, "source_document_batch_id"


def _batch_counts(session: Session, stage: str, batch_id: UUID) -> dict[str, int]:
    _batch_model, observation_model, raw_model, raw_fk = _batch_models(stage)
    observation_batch_fk = "batch_id"
    raw_count = int(
        session.scalar(
            select(func.count())
            .select_from(raw_model)
            .where(getattr(raw_model, raw_fk) == batch_id)
        )
        or 0
    )
    observation_count = int(
        session.scalar(
            select(func.count())
            .select_from(observation_model)
            .where(getattr(observation_model, observation_batch_fk) == batch_id)
        )
        or 0
    )
    return {"raw_payloads": raw_count, "canonical_observations": observation_count}


def _batch_fingerprint(session: Session, stage: str, batch_id: UUID) -> str:
    batch_model, observation_model, raw_model, raw_fk = _batch_models(stage)
    if stage == "REPORTED_FUNDAMENTALS":
        raw_fk_predicate = getattr(raw_model, raw_fk) == batch_id
    else:
        raw_fk_predicate = getattr(raw_model, raw_fk) == batch_id
    tables: dict[str, list[dict[str, Any]]] = {}
    selectors = (
        (batch_model, batch_model.id == batch_id),
        (observation_model, observation_model.batch_id == batch_id),
        (raw_model, raw_fk_predicate),
    )
    for model, predicate in selectors:
        rows: list[dict[str, Any]] = []
        items: Sequence[Any] = session.scalars(select(model).where(predicate)).all()
        for item in items:
            row = {
                column.name: _json_value(getattr(item, column.name))
                for column in model.__table__.columns
                if column.name != "payload_bytes"
            }
            rows.append(row)
        tables[model.__tablename__] = sorted(rows, key=_canonical_json)
    return _sha256(_canonical_json(tables).encode("utf-8"))


def _batch_descriptor(
    session: Session,
    *,
    stage: str,
    batch_id: UUID,
    records: Sequence[RawProviderRecord],
    import_result: dict[str, Any],
) -> dict[str, Any]:
    batch_model, _observation_model, _raw_model, _raw_fk = _batch_models(stage)
    batch = session.get(batch_model, batch_id)
    if batch is None:
        raise FundamentalsBootstrapError("The importer returned a missing source batch receipt.")
    return {
        "batch_id": str(batch_id),
        "source_digest": batch.source_digest,
        "normalizer_version": batch.normalizer_version,
        "provider_schema_version": batch.provider_schema_version,
        "source_record_ids": sorted(
            record.source_record_id or record.payload_sha256 for record in records
        ),
        "payloads": [
            {
                "source_record_id": record.source_record_id,
                "retrieved_at": record.retrieved_at.isoformat(),
                "payload_sha256": record.payload_sha256,
            }
            for record in records
        ],
        "canonical_counts": _batch_counts(session, stage, batch_id),
        "canonical_fingerprint": _batch_fingerprint(session, stage, batch_id),
        "import_result": import_result,
    }


def _eligible(checkpoint: FundamentalsBootstrapCheckpoint, at: datetime) -> bool:
    if checkpoint.status == "PENDING":
        return True
    return bool(
        checkpoint.status == "FAILED"
        and checkpoint.retryable
        and checkpoint.attempt_count < MAX_CHECKPOINT_FAILURES
        and (checkpoint.next_attempt_at is None or checkpoint.next_attempt_at <= at)
    )


def _append_failure_history(
    checkpoint: FundamentalsBootstrapCheckpoint, code: str, message: str, at: datetime
) -> None:
    report = dict(checkpoint.report)
    failures = report.get("failure_history")
    history = list(failures) if isinstance(failures, list) else []
    history.append({"code": code, "message": message, "recorded_at": at.isoformat()})
    report["failure_history"] = history
    checkpoint.report = report


def _next_checkpoint(
    session: Session, run_id: UUID, at: datetime
) -> FundamentalsBootstrapCheckpoint | None:
    candidates = list(
        session.scalars(
            select(FundamentalsBootstrapCheckpoint)
            .where(
                FundamentalsBootstrapCheckpoint.run_id == run_id,
                FundamentalsBootstrapCheckpoint.status.in_(("PENDING", "FAILED")),
            )
            .order_by(FundamentalsBootstrapCheckpoint.sequence_number)
            .with_for_update(skip_locked=True)
        )
    )
    return next((item for item in candidates if _eligible(item, at)), None)


def _recover_interrupted_checkpoints(session: Session, run_id: UUID) -> None:
    now_at = _now()
    for checkpoint in session.scalars(
        select(FundamentalsBootstrapCheckpoint).where(
            FundamentalsBootstrapCheckpoint.run_id == run_id,
            FundamentalsBootstrapCheckpoint.status == "RUNNING",
        )
    ):
        checkpoint.attempt_count += 1
        checkpoint.status = "FAILED"
        checkpoint.failure_code = "WORKER_INTERRUPTED"
        checkpoint.failure_message = (
            "The previous bounded invocation stopped before this checkpoint committed."
        )
        _append_failure_history(
            checkpoint,
            "WORKER_INTERRUPTED",
            "The previous bounded invocation stopped before this checkpoint committed.",
            now_at,
        )
        checkpoint.retryable = checkpoint.attempt_count < MAX_CHECKPOINT_FAILURES
        checkpoint.next_attempt_at = now_at if checkpoint.retryable else None
        checkpoint.finished_at = now_at
    session.commit()


def _append_result_batch(
    session: Session,
    checkpoint: FundamentalsBootstrapCheckpoint,
    stage: str,
    records: Sequence[RawProviderRecord],
    import_result: dict[str, Any],
) -> None:
    raw_id = import_result.get("batch_id")
    if not isinstance(raw_id, str):
        return
    batch_id = UUID(raw_id)
    descriptor = _batch_descriptor(
        session,
        stage=stage,
        batch_id=batch_id,
        records=records,
        import_result=import_result,
    )
    checkpoint_report = dict(checkpoint.report)
    batches_value = checkpoint_report.get("batches")
    batches = list(batches_value) if isinstance(batches_value, list) else []
    known_ids = {item.get("batch_id") for item in batches if isinstance(item, dict)}
    if str(batch_id) not in known_ids:
        batches.append(descriptor)
    checkpoint_report["batches"] = batches
    checkpoint.report = checkpoint_report


def _process_checkpoint(
    session: Session,
    run: FundamentalsBootstrapRun,
    checkpoint: FundamentalsBootstrapCheckpoint,
    *,
    provider: ProviderAdapter,
) -> None:
    mapping_ok, mapping_error = _mapping_still_matches(session, checkpoint, run)
    if not mapping_ok:
        checkpoint.status = "BLOCKED"
        checkpoint.failure_code = "REVIEWED_SEC_MAPPING_CHANGED"
        checkpoint.failure_message = mapping_error
        checkpoint.retryable = False
        checkpoint.finished_at = _now()
        session.commit()
        return

    checkpoint.status = "RUNNING"
    checkpoint.started_at = _now()
    checkpoint.finished_at = None
    checkpoint.failure_code = None
    checkpoint.failure_message = None
    checkpoint.retryable = False
    checkpoint.next_attempt_at = None
    run.status = "RUNNING"
    run.started_at = run.started_at or checkpoint.started_at
    run.finished_at = None
    session.commit()

    if run.last_provider_request_at is not None:
        remaining = (
            MIN_SEC_REQUEST_INTERVAL_SECONDS
            - (_now() - run.last_provider_request_at).total_seconds()
        )
        if remaining > 0:
            time.sleep(remaining)

    query = _query_for_checkpoint(checkpoint)
    try:
        if checkpoint.stage == "SOURCE_DOCUMENTS":
            known_history = _known_history_records(session, checkpoint.cik)
        else:
            known_history = set()
        result = asyncio.run(
            provider.fetch(
                stage=checkpoint.stage,
                company_id=checkpoint.company_id,
                cik=checkpoint.cik,
                query=query,
                known_source_record_ids=known_history,
            )
        )
    except ProviderFetchFailure as failure:
        code, message, retryable, blocked = _provider_error(failure.error)
        checkpoint.attempt_count += 1
        checkpoint.provider_request_count += failure.request_count
        checkpoint.status = "BLOCKED" if blocked else "FAILED"
        checkpoint.failure_code = code
        checkpoint.failure_message = message
        _append_failure_history(checkpoint, code, message, _now())
        checkpoint.retryable = retryable and checkpoint.attempt_count < MAX_CHECKPOINT_FAILURES
        checkpoint.next_attempt_at = (
            _now() + timedelta(seconds=_retry_delay(checkpoint.attempt_count))
            if checkpoint.retryable
            else None
        )
        checkpoint.finished_at = _now()
        run.last_provider_request_at = checkpoint.finished_at
        session.commit()
        return
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        code, message, retryable, blocked = _provider_error(error)
        checkpoint.attempt_count += 1
        checkpoint.provider_request_count += 1
        checkpoint.status = "BLOCKED" if blocked else "FAILED"
        checkpoint.failure_code = code
        checkpoint.failure_message = message
        _append_failure_history(checkpoint, code, message, _now())
        checkpoint.retryable = retryable and checkpoint.attempt_count < MAX_CHECKPOINT_FAILURES
        checkpoint.next_attempt_at = (
            _now() + timedelta(seconds=_retry_delay(checkpoint.attempt_count))
            if checkpoint.retryable
            else None
        )
        checkpoint.finished_at = _now()
        run.last_provider_request_at = checkpoint.finished_at
        session.commit()
        return
    except Exception:
        session.rollback()
        raise FundamentalsBootstrapExecutionError(
            "SEC provider processing stopped before the checkpoint was recorded. Resume the run."
        ) from None

    records = result.records
    checkpoint.provider_request_count += result.request_count
    now_at = _now()
    run.last_provider_request_at = now_at
    checkpoint.page_count += 1
    checkpoint.attempt_count = 0
    checkpoint_report = dict(checkpoint.report)
    checkpoint_report["last_source_record_ids"] = sorted(
        record.source_record_id or record.payload_sha256 for record in records
    )
    checkpoint_report["last_payload_sha256"] = sorted(record.payload_sha256 for record in records)
    checkpoint_report["last_retrieved_at"] = [record.retrieved_at.isoformat() for record in records]
    checkpoint_report["history_files_skipped_as_unchanged"] = result.skipped_history_files

    try:
        if not records:
            import_result: dict[str, Any] = {
                "status": "NO_PROVIDER_RECORDS",
                "documents_imported": 0,
                "facts_inserted": 0,
            }
        elif checkpoint.stage == "REPORTED_FUNDAMENTALS":
            if len(records) != 1:
                raise ValueError(
                    "SEC Company Facts must return exactly one mapped issuer response."
                )
            import_result = ingest_sec_company_facts(
                session,
                checkpoint.company_id,
                checkpoint.cik,
                records[0],
            )
            _append_result_batch(session, checkpoint, checkpoint.stage, records, import_result)
        elif checkpoint.stage == "SOURCE_DOCUMENTS":
            import_result = ingest_sec_submissions(
                session,
                query,
                records,
                {checkpoint.company_id: checkpoint.cik},
            )
            _append_result_batch(session, checkpoint, checkpoint.stage, records, import_result)
        else:
            raise ValueError("Unsupported SEC bootstrap checkpoint stage.")
    except ValueError:
        session.rollback()
        reloaded_checkpoint = session.get(FundamentalsBootstrapCheckpoint, checkpoint.id)
        reloaded_run = session.get(FundamentalsBootstrapRun, run.id)
        if reloaded_checkpoint is None or reloaded_run is None:
            raise FundamentalsBootstrapExecutionError(
                "The SEC import checkpoint could not be recovered. Inspect the run ledger."
            ) from None
        reloaded_checkpoint.attempt_count += 1
        reloaded_checkpoint.provider_request_count += len(records)
        reloaded_checkpoint.status = "BLOCKED"
        reloaded_checkpoint.failure_code = "SEC_IMPORT_VALIDATION"
        reloaded_checkpoint.failure_message = (
            "The SEC response failed the existing canonical importer identity or schema checks."
        )
        _append_failure_history(
            reloaded_checkpoint,
            "SEC_IMPORT_VALIDATION",
            "The SEC response failed the existing canonical importer identity or schema checks.",
            _now(),
        )
        reloaded_checkpoint.retryable = False
        reloaded_checkpoint.finished_at = _now()
        reloaded_run.last_provider_request_at = reloaded_checkpoint.finished_at
        session.commit()
        return

    committed_batches = checkpoint.report.get("batches")
    if isinstance(committed_batches, list):
        checkpoint_report["batches"] = committed_batches
    checkpoint_report["last_import_result"] = import_result
    deferred = result.deferred_history_file_ids
    if deferred:
        checkpoint_report["deferred_history_file_ids"] = list(deferred)
    else:
        checkpoint_report.pop("deferred_history_file_ids", None)
    checkpoint.report = checkpoint_report
    checkpoint.failure_code = None
    checkpoint.failure_message = None
    checkpoint.retryable = False
    checkpoint.next_attempt_at = None

    if deferred:
        checkpoint.status = "PENDING"
        checkpoint.finished_at = None
    else:
        reconciliation = import_result.get("reconciliation")
        reconciliation = reconciliation if isinstance(reconciliation, dict) else {}
        if import_result.get("status") == "NO_PROVIDER_RECORDS":
            checkpoint.status = "UNAVAILABLE"
            checkpoint.failure_code = "SEC_EMPTY_RESPONSE"
            checkpoint.failure_message = "SEC returned no provider records for the reviewed issuer."
        elif checkpoint.stage == "REPORTED_FUNDAMENTALS":
            batch_ids = [
                item.get("batch_id")
                for item in _dict_items(checkpoint_report.get("batches"))
                if isinstance(item.get("batch_id"), str)
            ]
            mapped_fact_count = sum(
                _batch_counts(session, checkpoint.stage, UUID(item))["canonical_observations"]
                for item in batch_ids
            )
            checkpoint.status = "COMPLETE" if mapped_fact_count else "UNAVAILABLE"
            if not mapped_fact_count:
                checkpoint.failure_code = "NO_MAPPED_STANDARD_FACTS"
                checkpoint.failure_message = (
                    "The valid SEC response contained no facts in the reviewed canonical "
                    "concept map."
                )
        else:
            imported = int(import_result.get("documents_imported", 0) or 0)
            reused = int(import_result.get("documents_reused", 0) or 0)
            supported_count = imported + reused
            checkpoint.status = "COMPLETE" if supported_count else "UNAVAILABLE"
            if not supported_count:
                checkpoint.failure_code = "NO_SUPPORTED_FILINGS"
                checkpoint.failure_message = (
                    "The valid SEC submissions response contained no supported filing documents."
                )
        checkpoint.finished_at = _now()
    checkpoint.report = {
        **checkpoint_report,
        "last_import_result": import_result,
    }
    session.commit()


def execute_fundamentals_bootstrap(
    engine: Engine,
    run_id: UUID,
    *,
    target_environment: str,
    provider: ProviderAdapter,
    user_agent: str,
    max_checkpoints: int = DEFAULT_CHECKPOINTS_PER_INVOCATION,
) -> dict[str, Any]:
    """Execute at most N checkpoint pages; each receipt and checkpoint commits atomically."""
    if target_environment not in {"development", "rehearsal"}:
        raise FundamentalsBootstrapError(
            "SEC fundamentals bootstrap accepts development or rehearsal targets only."
        )
    if not _has_contact_email(user_agent):
        raise FundamentalsBootstrapError(
            "SEC_USER_AGENT must identify the application and a monitored contact email."
        )
    if max_checkpoints < 1 or max_checkpoints > MAX_CHECKPOINTS_PER_INVOCATION:
        raise FundamentalsBootstrapError(
            f"--max-checkpoints must be between 1 and {MAX_CHECKPOINTS_PER_INVOCATION}."
        )
    with _advisory_lock(engine), Session(engine) as session:
        run = session.get(FundamentalsBootstrapRun, run_id)
        if run is None:
            raise FundamentalsBootstrapError("The fundamentals bootstrap run does not exist.")
        if run.target_environment != target_environment:
            raise FundamentalsBootstrapError(
                "The requested target environment does not match the prepared run."
            )
        if run.status in {"COMPLETE", "FAILED", "BLOCKED"}:
            report = _run_report(session, run)
            report["status"] = run.status
            return report
        try:
            current_mappings = _load_reviewed_cik_mappings(session)
        except FundamentalsBootstrapError:
            run.status = "BLOCKED"
            run.finished_at = _now()
            run.report = {
                "status": "BLOCKED",
                "failure_code": "REVIEWED_SEC_MAPPING_INVALID",
                "message": (
                    "The reviewed SEC identity set became ambiguous or invalid; resolve it and "
                    "prepare a new run."
                ),
            }
            session.commit()
            return run.report
        scoped_ids = {
            item.get("mapping_identifier_id") for item in _dict_items(run.scope.get("mappings"))
        }
        scoped_mappings = [item for item in current_mappings if str(item.mapping_id) in scoped_ids]
        if (
            len(scoped_mappings) != len(scoped_ids)
            or _mapping_sha256(scoped_mappings) != run.mapping_sha256
        ):
            run.status = "BLOCKED"
            run.finished_at = _now()
            run.report = {
                "status": "BLOCKED",
                "failure_code": "REVIEWED_SEC_MAPPING_CHANGED",
                "message": "The reviewed SEC identity set changed; prepare a new run.",
            }
            session.commit()
            return run.report
        _recover_interrupted_checkpoints(session, run.id)
        processed = 0
        while processed < max_checkpoints:
            checkpoint = _next_checkpoint(session, run.id, _now())
            if checkpoint is None:
                break
            _process_checkpoint(
                session,
                run,
                checkpoint,
                provider=provider,
            )
            processed += 1
        session.refresh(run)
        report = _run_report(session, run)
        run.status = report["status"]
        terminal = report["pending_checkpoints"] == 0 and report["retryable_checkpoints"] == 0
        run.finished_at = _now() if terminal else None
        run.report = report
        session.commit()
        return report


def _run_batch_descriptors(
    checkpoints: Sequence[FundamentalsBootstrapCheckpoint],
) -> tuple[list[dict[str, Any]], set[UUID], set[UUID]]:
    descriptors: list[dict[str, Any]] = []
    fact_batch_ids: set[UUID] = set()
    document_batch_ids: set[UUID] = set()
    for checkpoint in checkpoints:
        batches = checkpoint.report.get("batches", [])
        if not isinstance(batches, list):
            continue
        for item in batches:
            if not isinstance(item, dict) or not isinstance(item.get("batch_id"), str):
                continue
            try:
                batch_id = UUID(item["batch_id"])
            except ValueError:
                continue
            descriptors.append({"stage": checkpoint.stage, **item})
            (document_batch_ids if checkpoint.stage == "SOURCE_DOCUMENTS" else fact_batch_ids).add(
                batch_id
            )
    return descriptors, fact_batch_ids, document_batch_ids


def _coverage_report(
    session: Session,
    run: FundamentalsBootstrapRun,
    checkpoints: Sequence[FundamentalsBootstrapCheckpoint],
) -> dict[str, Any]:
    descriptors, fact_batch_ids, document_batch_ids = _run_batch_descriptors(checkpoints)
    fact_batches = sorted(fact_batch_ids, key=str)
    document_batches = sorted(document_batch_ids, key=str)
    facts: list[ReportedFundamentalObservation] = (
        list(
            session.scalars(
                select(ReportedFundamentalObservation)
                .where(ReportedFundamentalObservation.batch_id.in_(fact_batches))
                .order_by(
                    ReportedFundamentalObservation.company_id,
                    ReportedFundamentalObservation.statement,
                    ReportedFundamentalObservation.period_end,
                    ReportedFundamentalObservation.metric,
                )
            )
        )
        if fact_batches
        else []
    )
    documents: list[SourceDocument] = (
        list(
            session.scalars(
                select(SourceDocument)
                .where(SourceDocument.batch_id.in_(document_batches))
                .order_by(
                    SourceDocument.company_id,
                    SourceDocument.filed_at,
                    SourceDocument.external_identifier,
                )
            )
        )
        if document_batches
        else []
    )
    company_names = {
        str(item.get("company_id")): str(item.get("company_name"))
        for item in _dict_items(run.scope.get("mappings"))
    }
    checkpoints_by_company: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for checkpoint in checkpoints:
        details = {
            "status": checkpoint.status,
            "failure_code": checkpoint.failure_code,
            "attempt_count": checkpoint.attempt_count,
            "page_count": checkpoint.page_count,
            "provider_request_count": checkpoint.provider_request_count,
            "batches": checkpoint.report.get("batches", []),
        }
        checkpoints_by_company[str(checkpoint.company_id)][checkpoint.stage] = details

    company_fact_counts: dict[str, int] = defaultdict(int)
    period_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    statement_groups: dict[tuple[str, str, str, str | None, str], dict[str, Any]] = {}
    fact_accessions: set[tuple[UUID, str]] = set()
    for fact in facts:
        company_key = str(fact.company_id)
        company_fact_counts[company_key] += 1
        key = (
            company_key,
            fact.statement,
            fact.period_type,
            fact.period_start.date().isoformat() if fact.period_start else None,
            fact.period_end.date().isoformat(),
            fact.currency,
            fact.unit,
        )
        period = period_groups.setdefault(
            key,
            {
                "company_id": company_key,
                "company_name": company_names.get(company_key),
                "statement": fact.statement,
                "period_type": fact.period_type,
                "period_start": key[3],
                "period_end": key[4],
                "currency": fact.currency,
                "unit": fact.unit,
                "fiscal_labels": set(),
                "providers": set(),
                "metrics": set(),
                "observation_count": 0,
                "reported_zero_count": 0,
                "source_accession_count": 0,
            },
        )
        if fact.fiscal_year is not None and fact.fiscal_period:
            period["fiscal_labels"].add(f"{fact.fiscal_year}:{fact.fiscal_period}")
        period["providers"].add(fact.provider_id)
        period["metrics"].add(fact.metric)
        period["observation_count"] += 1
        period["reported_zero_count"] += int(fact.value == Decimal(0))
        period["source_accession_count"] += int(fact.accession_number is not None)
        if fact.accession_number is not None:
            fact_accessions.add((fact.company_id, fact.accession_number))

        aggregate_key = (
            fact.statement,
            fact.period_type,
            fact.provider_id,
            fact.currency,
            fact.unit,
        )
        aggregate = statement_groups.setdefault(
            aggregate_key,
            {
                "statement": fact.statement,
                "period_type": fact.period_type,
                "provider_id": fact.provider_id,
                "currency": fact.currency,
                "unit": fact.unit,
                "companies": set(),
                "period_ends": set(),
                "observation_count": 0,
                "reported_zero_count": 0,
            },
        )
        aggregate["companies"].add(company_key)
        aggregate["period_ends"].add(fact.period_end.date().isoformat())
        aggregate["observation_count"] += 1
        aggregate["reported_zero_count"] += int(fact.value == Decimal(0))

    document_keys = {(document.company_id, document.external_identifier) for document in documents}
    linked_accessions = sum(1 for key in fact_accessions if key in document_keys)
    document_coverage_counts: dict[tuple[str, str | None, int | None], int] = defaultdict(int)
    company_document_counts: dict[str, int] = defaultdict(int)
    for document in documents:
        period_year = document.period_end.year if document.period_end else None
        document_coverage_counts[(document.document_type, document.source_form, period_year)] += 1
        company_document_counts[str(document.company_id)] += 1

    period_coverage = []
    for item in period_groups.values():
        item["fiscal_labels"] = sorted(item["fiscal_labels"])
        item["providers"] = sorted(item["providers"])
        item["metrics"] = sorted(item["metrics"])
        period_coverage.append(item)
    statement_coverage = []
    for item in statement_groups.values():
        period_ends = sorted(item.pop("period_ends"))
        companies = sorted(item.pop("companies"))
        item["company_count"] = len(companies)
        item["period_count"] = len(period_ends)
        item["earliest_period_end"] = period_ends[0] if period_ends else None
        item["latest_period_end"] = period_ends[-1] if period_ends else None
        statement_coverage.append(item)

    company_coverage = []
    for mapping in _dict_items(run.scope.get("mappings")):
        company_key = str(mapping.get("company_id"))
        company_coverage.append(
            {
                "company_id": company_key,
                "company_name": mapping.get("company_name"),
                "cik": mapping.get("cik"),
                "lifecycle_at_prepare": mapping.get("lifecycle"),
                "source_documents": checkpoints_by_company.get(company_key, {}).get(
                    "SOURCE_DOCUMENTS", {"status": "MISSING"}
                ),
                "reported_fundamentals": checkpoints_by_company.get(company_key, {}).get(
                    "REPORTED_FUNDAMENTALS", {"status": "MISSING"}
                ),
                "source_document_count": company_document_counts.get(company_key, 0),
                "reported_fact_count": company_fact_counts.get(company_key, 0),
            }
        )

    flags: dict[str, int] = defaultdict(int)
    for checkpoint in checkpoints:
        last_result = checkpoint.report.get("last_import_result")
        if not isinstance(last_result, dict):
            continue
        reconciliation = last_result.get("reconciliation")
        if not isinstance(reconciliation, dict):
            continue
        for flag_name in (
            "data_check_count",
            "unsupported_forms",
            "malformed_filing_rows",
            "existing_metadata_conflicts",
            "amendments_unlinked",
        ):
            raw = reconciliation.get(flag_name, 0)
            if isinstance(raw, int):
                flags[flag_name] += raw
        counters = reconciliation.get("normalization_counters")
        if isinstance(counters, dict):
            for counter_name, raw in counters.items():
                if isinstance(raw, int) and raw > 0:
                    flags[str(counter_name)] += raw
    flags["unmapped_active_company_count"] = len(
        _dict_items(run.scope.get("unmapped_active_companies"))
    )
    flags["facts_without_matching_sec_document"] = len(fact_accessions) - linked_accessions

    return {
        "company_coverage": company_coverage,
        "fundamental_statement_coverage": sorted(
            statement_coverage,
            key=lambda item: (
                str(item["statement"]),
                str(item["period_type"]),
                str(item["provider_id"]),
                str(item["currency"]),
                str(item["unit"]),
            ),
        ),
        "fundamental_period_coverage": sorted(
            period_coverage,
            key=lambda item: (
                str(item["company_name"]),
                str(item["statement"]),
                str(item["period_type"]),
                str(item["period_end"]),
            ),
        ),
        "source_document_coverage": [
            {
                "document_type": key[0],
                "source_form": key[1],
                "period_year": key[2],
                "provider_id": SEC_PROVIDER_ID,
                "document_count": count,
            }
            for key, count in sorted(
                document_coverage_counts.items(), key=lambda item: str(item[0])
            )
        ],
        "accession_reference_coverage": {
            "fact_accessions": len(fact_accessions),
            "matched_source_documents": linked_accessions,
            "fact_accessions_without_supported_source_document": len(fact_accessions)
            - linked_accessions,
        },
        "review_flags": dict(sorted(flags.items())),
        "raw_batch_count": len(descriptors),
        "fact_batch_count": len(fact_batches),
        "source_document_batch_count": len(document_batches),
        "consensus_estimates": "EXCLUDED_LICENSED_SOURCE_DISABLED",
        "canonical_values_are_not_included": True,
    }


def _run_report(
    session: Session,
    run: FundamentalsBootstrapRun,
) -> dict[str, Any]:
    checkpoints = list(
        session.scalars(
            select(FundamentalsBootstrapCheckpoint)
            .where(FundamentalsBootstrapCheckpoint.run_id == run.id)
            .order_by(FundamentalsBootstrapCheckpoint.sequence_number)
        )
    )
    statuses = [checkpoint.status for checkpoint in checkpoints]
    has_work = any(
        checkpoint.status != "PENDING" or checkpoint.attempt_count > 0 or checkpoint.page_count > 0
        for checkpoint in checkpoints
    )
    pending_count = sum(status in {"PENDING", "RUNNING"} for status in statuses)
    retryable_count = sum(
        checkpoint.status == "FAILED" and checkpoint.retryable for checkpoint in checkpoints
    )
    failed_count = sum(checkpoint.status == "FAILED" for checkpoint in checkpoints)
    blocked_count = sum(status == "BLOCKED" for status in statuses)
    unavailable_count = sum(status == "UNAVAILABLE" for status in statuses)
    coverage = _coverage_report(session, run, checkpoints)
    review_flags = coverage["review_flags"]
    review_required = any(value > 0 for value in review_flags.values())

    if not checkpoints or run.status == "BLOCKED" or blocked_count:
        status = "BLOCKED"
    elif not has_work and pending_count:
        status = "PREPARED"
    elif pending_count or retryable_count:
        status = "PARTIAL"
    elif failed_count:
        status = (
            "PARTIAL" if any(item in {"COMPLETE", "UNAVAILABLE"} for item in statuses) else "FAILED"
        )
    elif unavailable_count or review_required:
        status = "PARTIAL"
    else:
        status = "COMPLETE"

    checkpoint_reports = [
        {
            "sequence_number": item.sequence_number,
            "stage": item.stage,
            "company_id": str(item.company_id),
            "cik": item.cik,
            "status": item.status,
            "attempt_count": item.attempt_count,
            "page_count": item.page_count,
            "provider_request_count": item.provider_request_count,
            "retryable": item.retryable,
            "next_attempt_at": item.next_attempt_at.isoformat() if item.next_attempt_at else None,
            "failure_code": item.failure_code,
            "failure_message": item.failure_message,
            "report": item.report,
        }
        for item in checkpoints
    ]
    return {
        "run_id": str(run.id),
        "input_digest": run.input_digest,
        "mapping_sha256": run.mapping_sha256,
        "bootstrap_version": run.bootstrap_version,
        "target_environment": run.target_environment,
        "status": status,
        "prepared_at": run.prepared_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "provider_id": SEC_PROVIDER_ID,
        "stages": list(STAGE_ORDER),
        "pending_checkpoints": pending_count,
        "retryable_checkpoints": retryable_count,
        "failed_checkpoints": failed_count,
        "blocked_checkpoints": blocked_count,
        "unavailable_checkpoints": unavailable_count,
        "total_checkpoints": len(checkpoints),
        "coverage": coverage,
        "checkpoints": checkpoint_reports,
    }


def reconcile_fundamentals_bootstrap(session: Session, run_id: UUID) -> dict[str, Any]:
    run = session.get(FundamentalsBootstrapRun, run_id)
    if run is None:
        raise FundamentalsBootstrapError("The fundamentals bootstrap run does not exist.")
    checkpoints = list(
        session.scalars(
            select(FundamentalsBootstrapCheckpoint)
            .where(FundamentalsBootstrapCheckpoint.run_id == run.id)
            .order_by(FundamentalsBootstrapCheckpoint.sequence_number)
        )
    )
    differences: list[dict[str, str]] = []
    batch_results: list[dict[str, Any]] = []
    for checkpoint in checkpoints:
        batches = checkpoint.report.get("batches", [])
        if not isinstance(batches, list):
            batches = []
        for descriptor in batches:
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get("batch_id"), str):
                continue
            try:
                batch_id = UUID(descriptor["batch_id"])
            except ValueError:
                differences.append(
                    {"subject": str(checkpoint.company_id), "code": "INVALID_BATCH_ID"}
                )
                continue
            actual_counts = _batch_counts(session, checkpoint.stage, batch_id)
            actual_fingerprint = _batch_fingerprint(session, checkpoint.stage, batch_id)
            expected_counts = descriptor.get("canonical_counts")
            expected_fingerprint = descriptor.get("canonical_fingerprint")
            status = "MATCHED"
            if actual_counts != expected_counts:
                status = "MISMATCH"
                differences.append(
                    {
                        "subject": str(checkpoint.company_id),
                        "batch_id": str(batch_id),
                        "code": "CANONICAL_COUNTS_MISMATCH",
                    }
                )
            if actual_fingerprint != expected_fingerprint:
                status = "MISMATCH"
                differences.append(
                    {
                        "subject": str(checkpoint.company_id),
                        "batch_id": str(batch_id),
                        "code": "CANONICAL_FINGERPRINT_MISMATCH",
                    }
                )
            batch_model, _observation_model, raw_model, raw_fk = _batch_models(checkpoint.stage)
            batch_exists = session.get(batch_model, batch_id) is not None
            if not batch_exists:
                status = "MISMATCH"
                differences.append(
                    {
                        "subject": str(checkpoint.company_id),
                        "batch_id": str(batch_id),
                        "code": "BATCH_RECEIPT_MISSING",
                    }
                )
            raw_rows: list[Any] = list(
                session.scalars(select(raw_model).where(getattr(raw_model, raw_fk) == batch_id))
            )
            for raw in raw_rows:
                try:
                    content = gzip.decompress(raw.payload_bytes)
                except (OSError, EOFError):
                    content = b""
                if _sha256(content) != raw.payload_sha256:
                    status = "MISMATCH"
                    differences.append(
                        {
                            "subject": str(checkpoint.company_id),
                            "batch_id": str(batch_id),
                            "code": "RAW_PAYLOAD_HASH_MISMATCH",
                        }
                    )
            batch_results.append(
                {
                    "company_id": str(checkpoint.company_id),
                    "stage": checkpoint.stage,
                    "batch_id": str(batch_id),
                    "expected_counts": expected_counts,
                    "actual_counts": actual_counts,
                    "expected_fingerprint": expected_fingerprint,
                    "actual_fingerprint": actual_fingerprint,
                    "reconciliation": status,
                }
            )
    incomplete = any(
        checkpoint.status not in {"COMPLETE", "UNAVAILABLE"} for checkpoint in checkpoints
    )
    report = _run_report(session, run)
    report["reconciliation"] = {
        "status": "MISMATCH" if differences else "INCOMPLETE" if incomplete else "MATCHED",
        "differences": differences,
        "batches": batch_results,
    }
    return report


def _validate_private_report_path(path: Path) -> None:
    absolute = path.absolute()
    resolved = path.resolve(strict=False)
    repository = REPOSITORY_PATH.resolve()
    if absolute.is_relative_to(repository) or resolved.is_relative_to(repository):
        raise FundamentalsBootstrapError("Reports must be written outside the repository.")
    if path.is_symlink():
        raise FundamentalsBootstrapError("The private report path cannot be a symlink.")
    if path.exists():
        raise FundamentalsBootstrapError(
            "The private report file already exists; choose a new unique path."
        )


def _write_private_report(path: Path, report: dict[str, Any]) -> Path:
    _validate_private_report_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise FundamentalsBootstrapError("The private report could not be written.") from None
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "prepare"):
        subparser = commands.add_parser(command)
        subparser.add_argument(
            "--target-environment", choices=("development", "rehearsal"), required=True
        )
        subparser.add_argument("--company-id", type=UUID)
        subparser.add_argument("--report", type=Path)
    for command in ("run", "resume", "status", "reconcile"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--run-id", type=UUID, required=True)
        subparser.add_argument(
            "--target-environment", choices=("development", "rehearsal"), required=True
        )
        subparser.add_argument("--report", type=Path)
        if command in {"run", "resume"}:
            subparser.add_argument(
                "--max-checkpoints",
                type=int,
                default=DEFAULT_CHECKPOINTS_PER_INVOCATION,
            )
    return parser


def _verify_target(engine: Engine, settings: Settings, requested_environment: str) -> None:
    verify_database_preflight(
        engine,
        configured_target_environment=settings.database_target_environment,
        requested_target_environment=requested_environment,
    )


def _report_exit_code(command: str, report: dict[str, Any]) -> int:
    if command == "preview":
        return 0 if report.get("status") == "READY" else 2
    if command == "prepare":
        return 0 if report.get("status") == "PREPARED" else 2
    if command in {"run", "resume", "status"}:
        return 0 if report.get("status") in {"COMPLETE", "PREPARED"} else 2
    if command == "reconcile":
        reconciliation = report.get("reconciliation")
        if isinstance(reconciliation, dict) and reconciliation.get("status") == "MATCHED":
            return 0
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine: Engine | None = None
    try:
        if args.report:
            _validate_private_report_path(args.report)
        settings = Settings()
        user_agent = settings.sec_user_agent or ""
        if not settings.database_url:
            raise FundamentalsBootstrapError("DATABASE_URL is required for target verification.")
        engine = create_database_engine(
            settings,
            write_operation=f"fundamentals_bootstrap.{args.command}",
            write_operation_kind="bootstrap",
        )
        if engine is None:
            raise FundamentalsBootstrapError("DATABASE_URL is required for target verification.")
        _verify_target(engine, settings, args.target_environment)
        if args.command in {"run", "resume"} and not user_agent:
            raise FundamentalsBootstrapError(
                "Set SEC_USER_AGENT to an application name and monitored contact email."
            )

        with Session(engine) as session:
            if args.command == "preview":
                report = preview_fundamentals_bootstrap(
                    session,
                    target_environment=args.target_environment,
                    company_id=args.company_id,
                )
            elif args.command == "prepare":
                with session.begin():
                    prepared_run = prepare_fundamentals_bootstrap(
                        session,
                        target_environment=args.target_environment,
                        company_id=args.company_id,
                    )
                session.refresh(prepared_run)
                report = _run_report(session, prepared_run)
            else:
                loaded_run = session.get(FundamentalsBootstrapRun, args.run_id)
                if loaded_run is None:
                    raise FundamentalsBootstrapError(
                        "The fundamentals bootstrap run does not exist."
                    )
                if loaded_run.target_environment != args.target_environment:
                    raise FundamentalsBootstrapError(
                        "The requested target environment does not match the prepared run."
                    )
                if args.command in {"run", "resume"}:
                    adapter = SecBootstrapProvider(user_agent)
                    report = execute_fundamentals_bootstrap(
                        engine,
                        loaded_run.id,
                        target_environment=args.target_environment,
                        provider=adapter,
                        user_agent=user_agent,
                        max_checkpoints=args.max_checkpoints,
                    )
                elif args.command == "status":
                    report = _run_report(session, loaded_run)
                else:
                    report = reconcile_fundamentals_bootstrap(session, loaded_run.id)

        if args.report:
            _write_private_report(args.report, report)
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
        return _report_exit_code(args.command, report)
    except (
        DatabaseWriteTargetError,
        FundamentalsBootstrapError,
        FundamentalsBootstrapExecutionError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
