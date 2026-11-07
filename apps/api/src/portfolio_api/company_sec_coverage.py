"""Current per-issuer SEC evidence and bootstrap diagnostics, without provider calls."""

from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    CompanyProviderIdentifier,
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
        ),
        filings=s.SecDomainCoverageRead(
            record_count=filing_summary[0],
            data_check_count=filing_summary[1],
            latest_period_end=_date(filing_summary[2]),
            latest_filed_at=_date(filing_summary[3]),
            latest_retrieved_at=filing_summary[4],
            latest_recorded_at=filing_summary[5],
            bootstrap=_bootstrap(session, company_id, "SOURCE_DOCUMENTS"),
        ),
        metrics_present=[metric for metric in FundamentalMetric if metric in metrics],
        metrics_missing=[metric for metric in FundamentalMetric if metric not in metrics],
    )
