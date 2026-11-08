"""Current SEC evidence and attributed refresh diagnostics, without provider calls."""

from contextlib import suppress
from datetime import date, datetime
from typing import Any, Literal, cast
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    CompanyProviderIdentifier,
    ExternalIngestionAttempt,
    ExternalIngestionRun,
    FundamentalMetric,
    FundamentalsBootstrapCheckpoint,
    FundamentalsBootstrapRun,
    ReportedFundamentalObservation,
    SourceDocument,
)
from portfolio_api.fundamentals_bootstrap import (
    FundamentalsBootstrapError,
    _load_reviewed_cik_mappings,
)
from portfolio_api.reported_fundamentals import SEC_PROVIDER_ID
from portfolio_api.sec_refresh_scope import SEC_SCOPE_VERSION
from portfolio_api.source_documents import (
    SEC_ISSUER_RECONCILIATION_VERSION,
    SecIssuerFilingReconciliation,
)

IssuerOutcome = Literal["REPORTED", "DATA_CHECK", "UNAVAILABLE", "UNMAPPED", "NOT_REPORTED"]


def _date(value: date | datetime | None) -> date | None:
    return value.date() if isinstance(value, datetime) else value


def _bootstrap(
    session: Session, company_id: UUID, stage: str
) -> s.SecBootstrapCheckpointRead | None:
    checkpoint, run = FundamentalsBootstrapCheckpoint, FundamentalsBootstrapRun
    latest = session.execute(
        select(checkpoint, run)
        .join(run, run.id == checkpoint.run_id)
        .where(checkpoint.company_id == company_id, checkpoint.stage == stage)
        .order_by(
            func.coalesce(checkpoint.finished_at, checkpoint.started_at, run.prepared_at).desc(),
            run.prepared_at.desc(),
            checkpoint.id,
        )
        .limit(1)
    ).one_or_none()
    if latest is None:
        return None
    item, parent = latest
    return s.SecBootstrapCheckpointRead(
        run_id=parent.id,
        checkpoint_id=item.id,
        status=item.status,
        prepared_at=parent.prepared_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        failure_code=item.failure_code,
        retryable=item.retryable,
        next_attempt_at=item.next_attempt_at,
        provider_request_count=item.provider_request_count,
    )


def _filing_issuer_result(
    result: dict[str, Any], company_id: UUID, mapped_ids: set[str] | None
) -> tuple[IssuerOutcome, int | None]:
    reconciliation = result["reconciliation"]
    if (
        reconciliation.get("issuer_results_version") != SEC_ISSUER_RECONCILIATION_VERSION
        or mapped_ids is None
    ):
        return "NOT_REPORTED", None
    raw_items = reconciliation.get("issuer_results")
    if not isinstance(raw_items, list):
        return "NOT_REPORTED", None
    try:
        items = [SecIssuerFilingReconciliation.model_validate(item) for item in raw_items]
    except ValueError:
        return "NOT_REPORTED", None
    by_company = {str(item.company_id): item for item in items}
    if len(by_company) != len(items) or set(by_company) != mapped_ids:
        return "NOT_REPORTED", None
    item = by_company.get(str(company_id))
    if item is None or item.response_record_count == 0:
        return "NOT_REPORTED", None
    deferred_total = result.get("history_files_deferred", 0)
    if type(deferred_total) is not int or deferred_total < 0:
        return "NOT_REPORTED", None
    deferred = 0
    if "issuer_history_files_deferred" in result:
        by_issuer = result["issuer_history_files_deferred"]
        if (
            not isinstance(by_issuer, dict)
            or set(by_issuer) != mapped_ids
            or not all(type(value) is int and value >= 0 for value in by_issuer.values())
            or sum(by_issuer.values()) != deferred_total
        ):
            return "NOT_REPORTED", None
        deferred = by_issuer[str(company_id)]
    elif deferred_total:
        return "NOT_REPORTED", None
    count = item.documents_imported + item.documents_reused
    if any(
        (
            item.rejected_payloads,
            item.unsupported_forms,
            item.malformed_filing_rows,
            item.conflicting_accessions,
            item.existing_metadata_conflicts,
            item.data_check_documents,
            item.amendments_unlinked,
            deferred,
        )
    ):
        return "DATA_CHECK", count
    return ("REPORTED", count) if count else ("UNAVAILABLE", 0)


def _issuer_result(
    run: ExternalIngestionRun, company_id: UUID, mapped_ids: set[str] | None
) -> tuple[IssuerOutcome, int | None]:
    if mapped_ids is not None and str(company_id) not in mapped_ids:
        return "UNMAPPED", None
    # A failed attempt rolls its provider data back. Prior retained facts are separate.
    if run.status not in {"COMPLETE", "PARTIAL"}:
        return "NOT_REPORTED", None
    report = cast(dict[str, Any], run.report)
    if run.domain == "REPORTED_FUNDAMENTALS":
        results = report.get("mapped_results", [])
        if not isinstance(results, list):
            return "NOT_REPORTED", None
        matches = [
            item
            for item in results
            if isinstance(item, dict) and item.get("company_id") == str(company_id)
        ]
        if len(matches) != 1:
            return "NOT_REPORTED", None
        result = matches[0]
        if result.get("status") == "DATA_CHECK":
            return "DATA_CHECK", None
        count_key = "source_fact_count"
    elif run.domain == "SOURCE_DOCUMENTS":
        result = report.get("provider_result", {})
        reconciliation = result.get("reconciliation") if isinstance(result, dict) else None
        if isinstance(reconciliation, dict) and (
            "issuer_results_version" in reconciliation or "issuer_results" in reconciliation
        ):
            return _filing_issuer_result(result, company_id, mapped_ids)
        # Legacy batches retain aggregate-only evidence. Attribution requires a
        # sole mapped provider subject when issuer-level receipts are absent.
        if mapped_ids != {str(company_id)}:
            return "NOT_REPORTED", None
        count_key = "documents_imported"
    else:
        return "NOT_REPORTED", None
    if not isinstance(result, dict) or not isinstance(result.get("reconciliation"), dict):
        return "NOT_REPORTED", None
    reconciliation = result["reconciliation"]
    count = reconciliation.get(count_key)
    if type(count) is not int or count < 0:
        return "NOT_REPORTED", None
    if run.domain == "SOURCE_DOCUMENTS":
        reused = reconciliation.get("documents_reused", 0)
        if type(reused) is not int or reused < 0:
            return "NOT_REPORTED", None
        count += reused
    checks = (
        "data_check_count",
        "data_check_documents",
        "unsupported_forms",
        "malformed_filing_rows",
        "existing_metadata_conflicts",
        "amendments_unlinked",
        "history_files_deferred",
    )
    if (
        reconciliation.get("issues")
        or any(reconciliation.get(key) for key in checks)
        or result.get("history_files_deferred")
    ):
        return "DATA_CHECK", count
    if count == 0:
        return "UNAVAILABLE", 0
    return "REPORTED", count


def _refresh(session: Session, company_id: UUID, domain: str) -> s.SecRefreshRead | None:
    run = session.scalar(
        select(ExternalIngestionRun)
        .where(
            ExternalIngestionRun.provider_id == SEC_PROVIDER_ID,
            ExternalIngestionRun.domain == domain,
            ExternalIngestionRun.request_scope["company_ids"]
            .cast(JSONB)
            .contains([str(company_id)]),
        )
        .order_by(
            func.coalesce(
                ExternalIngestionRun.finished_at,
                ExternalIngestionRun.last_attempt_started_at,
                ExternalIngestionRun.started_at,
            ).desc(),
            ExternalIngestionRun.created_at.desc(),
            ExternalIngestionRun.id,
        )
        .limit(1)
    )
    if run is None:
        return None
    scope = cast(dict[str, Any], run.request_scope)
    ids = scope.get("company_ids")
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        return None
    try:
        if [str(UUID(item)) for item in ids] != ids or len(set(ids)) != len(ids):
            return None
    except ValueError:
        return None
    mappings = scope.get("verified_cik_mappings")
    mapped_ids = None
    if isinstance(mappings, list) and all(
        isinstance(item, dict) and isinstance(item.get("company_id"), str) for item in mappings
    ):
        mapped_ids = {item["company_id"] for item in mappings}
        if len(mapped_ids) != len(mappings) or not mapped_ids.issubset(ids):
            mapped_ids = None
    attempt = session.scalar(
        select(ExternalIngestionAttempt)
        .where(ExternalIngestionAttempt.run_id == run.id)
        .order_by(ExternalIngestionAttempt.attempt_number.desc())
        .limit(1)
    )
    request_id = None
    if isinstance(scope.get("operational_request_id"), str):
        with suppress(ValueError):
            request_id = UUID(scope["operational_request_id"])
    trigger: Literal["MANUAL", "SCHEDULED", "LEGACY"] = "LEGACY"
    if request_id is not None:
        trigger = "MANUAL"
    elif (
        scope.get("sec_scope_version") == SEC_SCOPE_VERSION
        and scope.get("operational_request_id") is None
    ):
        trigger = "SCHEDULED"
    outcome, count = _issuer_result(run, company_id, mapped_ids)
    return s.SecRefreshRead(
        run_id=run.id,
        attempt_id=attempt.id if attempt else None,
        request_id=request_id,
        trigger=trigger,
        batch_status=run.status,
        requested_at=run.requested_at,
        started_at=run.last_attempt_started_at or run.started_at,
        finished_at=run.finished_at,
        attempt_count=run.attempt_count,
        retryable=bool(attempt and attempt.retryable),
        failure_code=run.failure_code,
        scope_company_count=len(set(ids)),
        mapped_company_count=len(mapped_ids) if mapped_ids is not None else None,
        issuer_outcome=outcome,
        source_record_count=count,
    )


def company_sec_coverage(session: Session, company_id: UUID) -> s.CompanySecCoverageRead:
    issuer = services.company(session, company_id)
    identifiers = list(
        session.scalars(
            select(CompanyProviderIdentifier).where(
                CompanyProviderIdentifier.company_id == company_id,
                CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
                CompanyProviderIdentifier.identifier_type == "SEC_CIK",
            )
        )
    )
    mapping_status: Literal["MAPPED", "UNMAPPED", "AMBIGUOUS", "INVALID"] = "UNMAPPED"
    mapping = None
    if len(identifiers) > 1:
        mapping_status = "AMBIGUOUS"
    elif identifiers:
        try:
            mapping = _load_reviewed_cik_mappings(session, company_id)[0]
            evidence = urlsplit(mapping.evidence_source)
            if evidence.username or evidence.password or evidence.port not in {None, 443}:
                raise FundamentalsBootstrapError(
                    "SEC identity evidence requires a public HTTPS URL."
                )
            mapping_status = "MAPPED"
        except (FundamentalsBootstrapError, ValueError):
            mapping = None
            mapping_status = "INVALID"

    fact = ReportedFundamentalObservation
    fact_summary = session.execute(
        select(
            func.count(fact.id),
            func.count(case((fact.data_quality != "PASS", 1))),
            func.max(fact.period_end),
            func.max(fact.filed_at),
            func.max(fact.observed_at),
            func.max(fact.recorded_at),
        ).where(fact.company_id == company_id, fact.provider_id == SEC_PROVIDER_ID)
    ).one()
    metrics = set(
        session.scalars(
            select(fact.metric)
            .where(
                fact.company_id == company_id,
                fact.provider_id == SEC_PROVIDER_ID,
            )
            .distinct()
        )
    )
    document = SourceDocument
    filing_summary = session.execute(
        select(
            func.count(document.id),
            func.count(case((document.data_quality != "PASS", 1))),
            func.max(document.period_end),
            func.max(document.filed_at),
            func.max(document.retrieved_at),
            func.max(document.recorded_at),
        ).where(
            document.company_id == company_id,
            document.provider_id == SEC_PROVIDER_ID,
            document.batch_id.is_not(None),
        )
    ).one()
    return s.CompanySecCoverageRead(
        company_id=issuer.id,
        company_name=issuer.name,
        mapping_status=mapping_status,
        cik=mapping.cik if mapping else None,
        provider_company_name=mapping.provider_company_name if mapping else None,
        identity_evidence_url=mapping.evidence_source if mapping else None,
        fundamentals=s.SecDomainCoverageRead(
            record_count=fact_summary[0],
            data_check_count=fact_summary[1],
            latest_period_end=_date(fact_summary[2]),
            latest_filed_at=_date(fact_summary[3]),
            latest_retrieved_at=fact_summary[4],
            latest_recorded_at=fact_summary[5],
            bootstrap=_bootstrap(session, company_id, "REPORTED_FUNDAMENTALS"),
            refresh=_refresh(session, company_id, "REPORTED_FUNDAMENTALS"),
        ),
        filings=s.SecDomainCoverageRead(
            record_count=filing_summary[0],
            data_check_count=filing_summary[1],
            latest_period_end=_date(filing_summary[2]),
            latest_filed_at=_date(filing_summary[3]),
            latest_retrieved_at=filing_summary[4],
            latest_recorded_at=filing_summary[5],
            bootstrap=_bootstrap(session, company_id, "SOURCE_DOCUMENTS"),
            refresh=_refresh(session, company_id, "SOURCE_DOCUMENTS"),
        ),
        metrics_present=[metric for metric in FundamentalMetric if metric in metrics],
        metrics_missing=[metric for metric in FundamentalMetric if metric not in metrics],
    )
