"""SEC Company Facts adapter and canonical reported-fact ingestion.

SEC/XBRL names are retained as provenance. Only the explicit mappings in this
module become canonical investment-domain facts; custom issuer taxonomies and
unmapped contexts are never guessed.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    Company,
    CompanyProviderIdentifier,
    ExternalRawPayload,
    FundamentalDataQuality,
    FundamentalMetric,
    FundamentalPeriodType,
    FundamentalRevisionContext,
    FundamentalStatement,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
    now,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    RawProviderRecord,
    raw_batch_fingerprint,
)
from portfolio_api.settings import Settings

SEC_PROVIDER_ID = "sec_edgar"
SEC_SOURCE_PRIORITY = 10
NORMALIZED_PROVIDER_PRIORITY = 50
SEC_NORMALIZER_VERSION = "sec-company-facts-us-gaap-ifrs-v1"
SEC_API_BASE = "https://data.sec.gov/api/xbrl/companyfacts"
_DURATION_MIN_QUARTER_DAYS = 70
_DURATION_MAX_QUARTER_DAYS = 110
_DURATION_MIN_YEAR_DAYS = 330
_DURATION_MAX_YEAR_DAYS = 400


class FactConcept(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: FundamentalMetric
    statement: FundamentalStatement
    unit_kind: str
    mapping_priority: int


class MetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: FundamentalMetric
    statement: FundamentalStatement
    display_name: str
    canonical_unit: str
    description: str


class CanonicalReportedFundamental(BaseModel):
    """Provider-neutral fact plus source metadata needed for reconciliation."""

    model_config = ConfigDict(frozen=True)

    provider_entity_id: str
    metric: FundamentalMetric
    statement: FundamentalStatement
    period_type: FundamentalPeriodType
    period_start: datetime | None
    period_end: datetime
    fiscal_year: int | None
    fiscal_period: str | None
    filed_at: datetime | None
    value: Decimal
    currency: str | None
    unit: str
    source_taxonomy: str
    source_concept: str
    source_unit: str
    accession_number: str | None
    form: str | None
    frame: str | None
    source_record_id: str
    source_url: str
    source_ref: str
    observation_fingerprint: str
    mapping_priority: int


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        metric=FundamentalMetric.REVENUE,
        statement=FundamentalStatement.INCOME_STATEMENT,
        display_name="Revenue",
        canonical_unit="currency",
        description="Reported revenue for the fiscal duration shown.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.GROSS_PROFIT,
        statement=FundamentalStatement.INCOME_STATEMENT,
        display_name="Gross profit",
        canonical_unit="currency",
        description="Reported gross profit for the fiscal duration shown.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.OPERATING_INCOME,
        statement=FundamentalStatement.INCOME_STATEMENT,
        display_name="Operating income",
        canonical_unit="currency",
        description="Reported operating income or profit for the fiscal duration shown.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.NET_INCOME,
        statement=FundamentalStatement.INCOME_STATEMENT,
        display_name="Net income",
        canonical_unit="currency",
        description="Reported net income or profit for the fiscal duration shown.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.CASH_AND_CASH_EQUIVALENTS,
        statement=FundamentalStatement.BALANCE_SHEET,
        display_name="Cash & equivalents",
        canonical_unit="currency",
        description="Reported cash and cash equivalents at the period end.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.CURRENT_DEBT,
        statement=FundamentalStatement.BALANCE_SHEET,
        display_name="Current debt",
        canonical_unit="currency",
        description="Reported current borrowings; not added to other debt facts.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.NONCURRENT_DEBT,
        statement=FundamentalStatement.BALANCE_SHEET,
        display_name="Non-current debt",
        canonical_unit="currency",
        description="Reported non-current borrowings; not added to other debt facts.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.OPERATING_CASH_FLOW,
        statement=FundamentalStatement.CASH_FLOW_STATEMENT,
        display_name="Operating cash flow",
        canonical_unit="currency",
        description="Reported net cash provided by or used in operating activities.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.CAPITAL_EXPENDITURES,
        statement=FundamentalStatement.CASH_FLOW_STATEMENT,
        display_name="Capital expenditures",
        canonical_unit="currency",
        description="Reported capital-expenditure line. Its provider sign is preserved.",
    ),
    MetricDefinition(
        metric=FundamentalMetric.DILUTED_WEIGHTED_AVERAGE_SHARES,
        statement=FundamentalStatement.INCOME_STATEMENT,
        display_name="Diluted weighted-average shares",
        canonical_unit="shares",
        description="Reported diluted weighted-average shares for the fiscal duration shown.",
    ),
)


def _concept(
    metric: FundamentalMetric,
    statement: FundamentalStatement,
    unit_kind: str = "CURRENCY",
    priority: int = 0,
) -> FactConcept:
    return FactConcept(
        metric=metric, statement=statement, unit_kind=unit_kind, mapping_priority=priority
    )


# Mappings deliberately cover standard concepts only. Similar-sounding custom
# taxonomy extensions are not treated as equivalent without a reviewed mapping.
CONCEPT_MAP: dict[tuple[str, str], FactConcept] = {
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"): _concept(
        FundamentalMetric.REVENUE, FundamentalStatement.INCOME_STATEMENT
    ),
    ("us-gaap", "Revenues"): _concept(
        FundamentalMetric.REVENUE, FundamentalStatement.INCOME_STATEMENT, priority=1
    ),
    ("us-gaap", "SalesRevenueNet"): _concept(
        FundamentalMetric.REVENUE, FundamentalStatement.INCOME_STATEMENT, priority=2
    ),
    ("ifrs-full", "Revenue"): _concept(
        FundamentalMetric.REVENUE, FundamentalStatement.INCOME_STATEMENT
    ),
    ("us-gaap", "GrossProfit"): _concept(
        FundamentalMetric.GROSS_PROFIT, FundamentalStatement.INCOME_STATEMENT
    ),
    ("ifrs-full", "GrossProfit"): _concept(
        FundamentalMetric.GROSS_PROFIT, FundamentalStatement.INCOME_STATEMENT
    ),
    ("us-gaap", "OperatingIncomeLoss"): _concept(
        FundamentalMetric.OPERATING_INCOME, FundamentalStatement.INCOME_STATEMENT
    ),
    ("ifrs-full", "ProfitLossFromOperatingActivities"): _concept(
        FundamentalMetric.OPERATING_INCOME, FundamentalStatement.INCOME_STATEMENT
    ),
    ("us-gaap", "NetIncomeLoss"): _concept(
        FundamentalMetric.NET_INCOME, FundamentalStatement.INCOME_STATEMENT
    ),
    ("ifrs-full", "ProfitLoss"): _concept(
        FundamentalMetric.NET_INCOME, FundamentalStatement.INCOME_STATEMENT
    ),
    ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"): _concept(
        FundamentalMetric.CASH_AND_CASH_EQUIVALENTS, FundamentalStatement.BALANCE_SHEET
    ),
    ("ifrs-full", "CashAndCashEquivalents"): _concept(
        FundamentalMetric.CASH_AND_CASH_EQUIVALENTS, FundamentalStatement.BALANCE_SHEET
    ),
    ("us-gaap", "ShortTermBorrowings"): _concept(
        FundamentalMetric.CURRENT_DEBT, FundamentalStatement.BALANCE_SHEET
    ),
    ("us-gaap", "LongTermDebtCurrent"): _concept(
        FundamentalMetric.CURRENT_DEBT, FundamentalStatement.BALANCE_SHEET, priority=1
    ),
    ("ifrs-full", "BorrowingsCurrent"): _concept(
        FundamentalMetric.CURRENT_DEBT, FundamentalStatement.BALANCE_SHEET
    ),
    ("us-gaap", "LongTermDebtNoncurrent"): _concept(
        FundamentalMetric.NONCURRENT_DEBT, FundamentalStatement.BALANCE_SHEET
    ),
    ("ifrs-full", "BorrowingsNoncurrent"): _concept(
        FundamentalMetric.NONCURRENT_DEBT, FundamentalStatement.BALANCE_SHEET
    ),
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"): _concept(
        FundamentalMetric.OPERATING_CASH_FLOW, FundamentalStatement.CASH_FLOW_STATEMENT
    ),
    ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"): _concept(
        FundamentalMetric.OPERATING_CASH_FLOW, FundamentalStatement.CASH_FLOW_STATEMENT
    ),
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"): _concept(
        FundamentalMetric.CAPITAL_EXPENDITURES, FundamentalStatement.CASH_FLOW_STATEMENT
    ),
    ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"): _concept(
        FundamentalMetric.CAPITAL_EXPENDITURES, FundamentalStatement.CASH_FLOW_STATEMENT
    ),
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"): _concept(
        FundamentalMetric.DILUTED_WEIGHTED_AVERAGE_SHARES,
        FundamentalStatement.INCOME_STATEMENT,
        unit_kind="SHARES",
    ),
    ("ifrs-full", "DilutedWeightedAverageNumberOfSharesOutstanding"): _concept(
        FundamentalMetric.DILUTED_WEIGHTED_AVERAGE_SHARES,
        FundamentalStatement.INCOME_STATEMENT,
        unit_kind="SHARES",
    ),
}


class SecCompanyFactsProvider:
    """Public SEC data.sec.gov adapter; it accepts canonical company IDs only."""

    provider_id = SEC_PROVIDER_ID

    def __init__(self, identifiers: dict[UUID, str], user_agent: str) -> None:
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT must identify the application and a contact email")
        self.identifiers = identifiers
        self.user_agent = user_agent.strip()

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        if query.domain != ExternalDataDomain.REPORTED_FUNDAMENTALS:
            raise ValueError("SEC Company Facts supports reported fundamentals only")
        records: list[RawProviderRecord] = []
        for index, subject in enumerate(query.subjects):
            if subject.kind != CanonicalSubjectKind.COMPANY or subject.id is None:
                raise ValueError("SEC Company Facts requires canonical company subjects")
            cik = self.identifiers.get(subject.id)
            if cik is None:
                continue
            if not re.fullmatch(r"\d{10}", cik):
                raise ValueError("SEC company identifiers must be ten-digit CIK values")
            if index:
                # Keep a sequential development import below the SEC's published limit.
                await asyncio.sleep(0.12)
            url = f"{SEC_API_BASE}/CIK{cik}.json"
            payload = await asyncio.to_thread(_download_sec_json, url, self.user_agent)
            records.append(
                RawProviderRecord(
                    domain=ExternalDataDomain.REPORTED_FUNDAMENTALS,
                    provider_id=self.provider_id,
                    provider_schema_version="companyfacts-v1",
                    source_record_id=f"CIK{cik}",
                    source_url=AnyHttpUrl(url),
                    media_type="application/json",
                    retrieved_at=query.requested_at,
                    payload=payload,
                    payload_sha256=hashlib.sha256(payload).hexdigest(),
                )
            )
        return records


def _download_sec_json(url: str, user_agent: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed SEC HTTPS host
        if response.status != 200:
            raise RuntimeError(f"SEC Company Facts returned HTTP {response.status}")
        return cast(bytes, response.read())


def _fact_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _period_type(start: date | None, end: date) -> FundamentalPeriodType | None:
    if start is None:
        return FundamentalPeriodType.INSTANT
    duration = (end - start).days + 1
    if _DURATION_MIN_QUARTER_DAYS <= duration <= _DURATION_MAX_QUARTER_DAYS:
        return FundamentalPeriodType.QUARTERLY
    if _DURATION_MIN_YEAR_DAYS <= duration <= _DURATION_MAX_YEAR_DAYS:
        return FundamentalPeriodType.ANNUAL
    return None


def _source_url(cik: str, accession: str | None) -> tuple[str, str]:
    if accession:
        compact = accession.replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}/{accession}-index.html"
        )
        return filing_url, accession
    facts_url = f"{SEC_API_BASE}/CIK{cik}.json"
    return facts_url, f"CIK{cik}:companyfacts"


def _normalize_companyfacts_json(
    record: RawProviderRecord,
    company_id: UUID,
    cik: str,
) -> tuple[
    tuple[CanonicalReportedFundamental, ...],
    dict[str, int],
    tuple[NormalizationIssue, ...],
]:
    if record.payload is None:
        issue = NormalizationIssue(
            code="RAW_PAYLOAD_REQUIRED",
            message="SEC Company Facts must be retained inline for deterministic normalization.",
            severity="ERROR",
        )
        return (), {}, (issue,)
    try:
        payload: Any = json.loads(
            record.payload,
            parse_float=Decimal,
            parse_int=Decimal,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, InvalidOperation):
        issue = NormalizationIssue(
            code="INVALID_JSON",
            message="The SEC Company Facts payload is not valid JSON.",
            severity="ERROR",
        )
        return (), {}, (issue,)
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
        issue = NormalizationIssue(
            code="UNRECOGNIZED_COMPANYFACTS",
            message="The SEC response does not have the documented company-facts structure.",
            severity="ERROR",
        )
        return (), {}, (issue,)

    facts = payload["facts"]
    counters: Counter[str] = Counter()
    observations: list[CanonicalReportedFundamental] = []
    for taxonomy, concepts in facts.items():
        if not isinstance(taxonomy, str) or not isinstance(concepts, dict):
            continue
        for tag, definition in concepts.items():
            concept = CONCEPT_MAP.get((taxonomy, tag)) if isinstance(tag, str) else None
            if concept is None:
                if isinstance(tag, str) and taxonomy in {"us-gaap", "ifrs-full"}:
                    counters["unmapped_standard_concepts"] += 1
                continue
            units = definition.get("units") if isinstance(definition, dict) else None
            if not isinstance(units, dict):
                counters["malformed_concepts"] += 1
                continue
            matched_unit = False
            for source_unit, entries in units.items():
                if not isinstance(source_unit, str) or not isinstance(entries, list):
                    continue
                valid_unit = (
                    source_unit == "shares"
                    if concept.unit_kind == "SHARES"
                    else bool(re.fullmatch(r"[A-Z]{3}", source_unit))
                )
                if not valid_unit:
                    counters["unsupported_units"] += len(entries)
                    continue
                matched_unit = True
                for item in entries:
                    if not isinstance(item, dict):
                        counters["malformed_facts"] += 1
                        continue
                    form = item.get("form")
                    if not isinstance(form, str) or form.rstrip("/A") not in {
                        "10-K",
                        "10-Q",
                        "20-F",
                        "40-F",
                        "6-K",
                    }:
                        counters["unsupported_forms"] += 1
                        continue
                    end = _fact_date(item.get("end"))
                    start = _fact_date(item.get("start"))
                    if end is None:
                        counters["missing_period_end"] += 1
                        continue
                    classification = _period_type(start, end)
                    if classification is None:
                        counters["year_to_date_or_unclassified_durations"] += 1
                        continue
                    try:
                        value = Decimal(str(item["val"]))
                    except (KeyError, InvalidOperation, ValueError):
                        counters["invalid_values"] += 1
                        continue
                    if not value.is_finite():
                        counters["invalid_values"] += 1
                        continue
                    filed = _fact_date(item.get("filed"))
                    filed_at = datetime.combine(filed, time.min, UTC) if filed is not None else None
                    accession = item.get("accn") if isinstance(item.get("accn"), str) else None
                    fiscal_year_value = item.get("fy")
                    try:
                        fiscal_year = (
                            int(str(fiscal_year_value)) if fiscal_year_value is not None else None
                        )
                    except (TypeError, ValueError, OverflowError):
                        fiscal_year = None
                    fiscal_period = item.get("fp") if isinstance(item.get("fp"), str) else None
                    frame = item.get("frame") if isinstance(item.get("frame"), str) else None
                    period_start = (
                        datetime.combine(start, time.min, UTC) if start is not None else None
                    )
                    period_end = datetime.combine(end, time.min, UTC)
                    currency = source_unit if concept.unit_kind == "CURRENCY" else None
                    unit = "currency" if currency is not None else "shares"
                    filing_url, filing_ref = _source_url(cik, accession)
                    fact_identity = ":".join(
                        (
                            f"CIK{cik}",
                            taxonomy,
                            tag,
                            source_unit,
                            accession or "NO_ACCESSION",
                            start.isoformat() if start else "INSTANT",
                            end.isoformat(),
                            fiscal_period or "NO_FP",
                        )
                    )
                    stable = {
                        "company_id": str(company_id),
                        "provider_entity_id": cik,
                        "metric": concept.metric.value,
                        "statement": concept.statement.value,
                        "period_type": classification.value,
                        "period_start": start.isoformat() if start else None,
                        "period_end": end.isoformat(),
                        "value": format(value, "f"),
                        "currency": currency,
                        "unit": unit,
                        "taxonomy": taxonomy,
                        "concept": tag,
                        "source_unit": source_unit,
                        "accession": accession,
                        "filed_at": filed.isoformat() if filed else None,
                        "fiscal_year": fiscal_year,
                        "fiscal_period": fiscal_period,
                        "frame": frame,
                    }
                    fingerprint = hashlib.sha256(
                        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                    observations.append(
                        CanonicalReportedFundamental(
                            provider_entity_id=cik,
                            metric=concept.metric,
                            statement=concept.statement,
                            period_type=classification,
                            period_start=period_start,
                            period_end=period_end,
                            fiscal_year=fiscal_year,
                            fiscal_period=fiscal_period,
                            filed_at=filed_at,
                            value=value,
                            currency=currency,
                            unit=unit,
                            source_taxonomy=taxonomy,
                            source_concept=tag,
                            source_unit=source_unit,
                            accession_number=accession,
                            form=form,
                            frame=frame,
                            source_record_id=fact_identity[:500],
                            source_url=filing_url,
                            source_ref=f"{filing_ref}:{taxonomy}:{tag}:{source_unit}",
                            observation_fingerprint=fingerprint,
                            mapping_priority=concept.mapping_priority,
                        )
                    )
                    counters["mapped_facts"] += 1
            if not matched_unit:
                counters["mapped_concepts_without_supported_unit"] += 1

    issues: tuple[NormalizationIssue, ...] = ()
    if counters["unmapped_standard_concepts"]:
        issues = (
            NormalizationIssue(
                code="UNMAPPED_STANDARD_CONCEPTS",
                message=(
                    f"{counters['unmapped_standard_concepts']} standard taxonomy concepts are "
                    "not mapped to the current canonical fact set."
                ),
                severity="WARNING",
                source_path="facts",
            ),
        )
    return tuple(observations), dict(counters), issues


def normalize_sec_company_facts(
    record: RawProviderRecord,
    company_id: UUID,
    cik: str,
) -> NormalizationResult[tuple[CanonicalReportedFundamental, ...]]:
    """Convert supported standard XBRL facts; preserve unsupported concepts as diagnostics."""

    if (
        record.provider_id != SEC_PROVIDER_ID
        or record.domain != ExternalDataDomain.REPORTED_FUNDAMENTALS
    ):
        issue = NormalizationIssue(
            code="PROVIDER_DOMAIN_MISMATCH",
            message=(
                "The SEC Company Facts normalizer accepts SEC reported-fundamentals records only."
            ),
            severity="ERROR",
        )
        return NormalizationResult(
            disposition=NormalizationDisposition.REJECTED, observation=None, issues=(issue,)
        )
    observations, _counters, issues = _normalize_companyfacts_json(record, company_id, cik)
    if any(item.severity == "ERROR" for item in issues):
        return NormalizationResult(
            disposition=NormalizationDisposition.REJECTED, observation=None, issues=issues
        )
    return NormalizationResult(
        disposition=NormalizationDisposition.ACCEPTED,
        observation=observations,
        issues=issues,
    )


def _lineage_key(
    fact: CanonicalReportedFundamental | ReportedFundamentalObservation,
) -> tuple[object, ...]:
    if isinstance(fact, CanonicalReportedFundamental):
        return (
            fact.provider_entity_id,
            fact.metric.value,
            fact.source_taxonomy,
            fact.source_concept,
            fact.source_unit,
            fact.currency,
            fact.period_type.value,
            fact.period_start,
            fact.period_end,
        )
    return (
        fact.provider_entity_id,
        fact.metric,
        fact.source_taxonomy,
        fact.source_concept,
        fact.source_unit,
        fact.currency,
        fact.period_type,
        fact.period_start,
        fact.period_end,
    )


def _recorded_sort_key(fact: ReportedFundamentalObservation) -> tuple[datetime, datetime]:
    return (fact.filed_at or datetime.min.replace(tzinfo=UTC), fact.recorded_at)


@dataclass(frozen=True)
class FundamentalSourceResolution:
    current_sources: tuple[ReportedFundamentalObservation, ...]
    selected: ReportedFundamentalObservation | None
    status: Literal["AVAILABLE", "CONFLICT", "DATA_CHECK"]


def resolve_fundamental_period(
    observations: Sequence[ReportedFundamentalObservation],
) -> FundamentalSourceResolution:
    """Apply source/tag precedence and surface any conflicting current disclosures."""

    latest_by_source: dict[tuple[object, ...], ReportedFundamentalObservation] = {}
    for item in observations:
        lineage = (
            item.provider_id,
            item.provider_entity_id,
            item.source_priority,
            item.source_taxonomy,
            item.source_concept,
            item.source_unit,
            item.mapping_priority,
        )
        prior = latest_by_source.get(lineage)
        order = (
            item.filed_at or datetime.min.replace(tzinfo=UTC),
            item.observed_at,
            item.recorded_at,
        )
        if prior is None or order > (
            prior.filed_at or datetime.min.replace(tzinfo=UTC),
            prior.observed_at,
            prior.recorded_at,
        ):
            latest_by_source[lineage] = item
    current_sources = sorted(
        latest_by_source.values(),
        key=lambda item: (
            item.source_priority,
            item.mapping_priority,
            item.provider_id,
            item.source_concept,
            str(item.id),
        ),
    )
    best_priority = min((item.source_priority, item.mapping_priority) for item in current_sources)
    preferred = [
        item
        for item in current_sources
        if (item.source_priority, item.mapping_priority) == best_priority
    ]
    selected: ReportedFundamentalObservation | None = preferred[0]
    conflict = len({item.value for item in preferred}) > 1 or any(
        item.value != preferred[0].value for item in current_sources
    )
    if len({item.value for item in preferred}) > 1:
        selected = None
    if conflict:
        status: Literal["AVAILABLE", "CONFLICT", "DATA_CHECK"] = "CONFLICT"
    elif any(item.data_quality != "PASS" for item in preferred):
        status = "DATA_CHECK"
    else:
        status = "AVAILABLE"
    return FundamentalSourceResolution(tuple(current_sources), selected, status)


def _filing_context(
    fact: CanonicalReportedFundamental,
    prior: ReportedFundamentalObservation | None,
) -> tuple[FundamentalRevisionContext, FundamentalDataQuality, str | None]:
    if prior is None:
        return FundamentalRevisionContext.ORIGINAL, FundamentalDataQuality.PASS, None
    if fact.form is not None and fact.form.endswith("/A"):
        context = FundamentalRevisionContext.AMENDED_FILING
    elif fact.value != prior.value:
        context = FundamentalRevisionContext.POTENTIAL_RESTATEMENT
    else:
        context = FundamentalRevisionContext.COMPARATIVE_REPORTED
    if fact.value != prior.value:
        reason = "A later filing reported a different value for this same concept and period."
        return context, FundamentalDataQuality.DATA_CHECK, reason
    return context, FundamentalDataQuality.PASS, None


def ingest_sec_company_facts(
    session: Session,
    company_id: UUID,
    cik: str,
    record: RawProviderRecord,
) -> dict[str, object]:
    """Append an SEC response once, including every supported historical revision."""

    issuer = session.get(Company, company_id)
    if issuer is None:
        raise ValueError("Canonical company was not found")
    if not re.fullmatch(r"\d{10}", cik):
        raise ValueError("SEC CIK must contain ten digits")
    identifiers = list(
        session.scalars(
            select(CompanyProviderIdentifier).where(
                CompanyProviderIdentifier.company_id == company_id,
                CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
                CompanyProviderIdentifier.identifier_type == "SEC_CIK",
            )
        )
    )
    if len(identifiers) != 1 or identifiers[0].identifier_value != cik:
        raise ValueError("An exact, unambiguous SEC CIK mapping is required before ingestion")
    payload: Any = json.loads(record.payload or b"{}")
    sec_name = payload.get("entityName") if isinstance(payload, dict) else None
    if (
        not isinstance(sec_name, str)
        or sec_name.strip().casefold() != identifiers[0].provider_company_name.strip().casefold()
    ):
        raise ValueError("SEC entity name does not match the recorded provider identity mapping")
    if record.source_record_id != f"CIK{cik}" or record.provider_id != SEC_PROVIDER_ID:
        raise ValueError("SEC response identity does not match the mapped CIK")

    query = ProviderQuery(
        domain=ExternalDataDomain.REPORTED_FUNDAMENTALS,
        subjects=(CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=company_id),),
        requested_at=record.retrieved_at,
    )
    source_digest = raw_batch_fingerprint(SEC_PROVIDER_ID, query, (record,))
    existing_batch = session.scalar(
        select(ReportedFundamentalBatch).where(
            ReportedFundamentalBatch.source_digest == source_digest,
            ReportedFundamentalBatch.normalizer_version == SEC_NORMALIZER_VERSION,
        )
    )
    if existing_batch is not None:
        mapped_facts = existing_batch.provider_summary.get("mapped_facts", 0)
        return {
            "status": "ALREADY_IMPORTED",
            "batch_id": str(existing_batch.id),
            "source_digest": source_digest,
            "facts_inserted": 0,
            "facts_reused": mapped_facts if isinstance(mapped_facts, int) else 0,
            "reconciliation": existing_batch.reconciliation,
        }

    facts, counters, issues = _normalize_companyfacts_json(record, company_id, cik)
    if not record.payload:
        raise ValueError("SEC Company Facts payload must be available inline")
    previous = list(
        session.scalars(
            select(ReportedFundamentalObservation).where(
                ReportedFundamentalObservation.company_id == company_id,
                ReportedFundamentalObservation.provider_id == SEC_PROVIDER_ID,
                ReportedFundamentalObservation.provider_entity_id == cik,
            )
        )
    )
    by_fingerprint = {item.observation_fingerprint for item in previous}
    latest_lineage: dict[tuple[object, ...], ReportedFundamentalObservation] = {}
    for item in previous:
        key = _lineage_key(item)
        incumbent = latest_lineage.get(key)
        if incumbent is None or _recorded_sort_key(item) > _recorded_sort_key(incumbent):
            latest_lineage[key] = item

    inserted = 0
    restatements = 0
    data_checks = 0
    batch_id = uuid4()
    new_observations: list[ReportedFundamentalObservation] = []
    for fact in facts:
        if fact.observation_fingerprint in by_fingerprint:
            continue
        prior = latest_lineage.get(_lineage_key(fact))
        context, quality, reason = _filing_context(fact, prior)
        if context == FundamentalRevisionContext.POTENTIAL_RESTATEMENT:
            restatements += 1
        if quality == FundamentalDataQuality.DATA_CHECK:
            data_checks += 1
        item = ReportedFundamentalObservation(
            id=uuid4(),
            company_id=company_id,
            security_id=None,
            batch_id=batch_id,
            provider_id=SEC_PROVIDER_ID,
            provider_entity_id=fact.provider_entity_id,
            source_priority=SEC_SOURCE_PRIORITY,
            metric=fact.metric.value,
            statement=fact.statement.value,
            period_type=fact.period_type.value,
            period_start=fact.period_start,
            period_end=fact.period_end,
            fiscal_year=fact.fiscal_year,
            fiscal_period=fact.fiscal_period,
            filed_at=fact.filed_at,
            observed_at=record.retrieved_at,
            recorded_at=now(),
            value=fact.value,
            currency=fact.currency,
            unit=fact.unit,
            source_taxonomy=fact.source_taxonomy,
            source_concept=fact.source_concept,
            source_unit=fact.source_unit,
            accession_number=fact.accession_number,
            form=fact.form,
            frame=fact.frame,
            source_record_id=fact.source_record_id,
            source_url=fact.source_url,
            source_ref=fact.source_ref,
            observation_fingerprint=fact.observation_fingerprint,
            mapping_priority=fact.mapping_priority,
            revision_context=context.value,
            data_quality=quality.value,
            quality_reason=reason,
            supersedes_observation_id=prior.id if prior is not None else None,
        )
        new_observations.append(item)
        by_fingerprint.add(fact.observation_fingerprint)
        latest_lineage[_lineage_key(fact)] = item
        inserted += 1

    reconciliation: dict[str, object] = {
        "source_fact_count": counters.get("mapped_facts", 0),
        "facts_inserted": inserted,
        "facts_reused": counters.get("mapped_facts", 0) - inserted,
        "potential_restatements": restatements,
        "data_check_count": data_checks,
        "normalization_counters": counters,
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }
    batch = ReportedFundamentalBatch(
        id=batch_id,
        provider_id=SEC_PROVIDER_ID,
        provider_schema_version=record.provider_schema_version,
        normalizer_version=SEC_NORMALIZER_VERSION,
        domain=ExternalDataDomain.REPORTED_FUNDAMENTALS.value,
        source_digest=source_digest,
        query_scope={"company_id": str(company_id), "cik": cik},
        observed_at=record.retrieved_at,
        provider_summary={"entity_name": sec_name, **counters},
        reconciliation=reconciliation,
    )
    raw_payload = ExternalRawPayload(
        id=uuid4(),
        reported_fundamental_batch_id=batch_id,
        batch_id=None,
        provider_id=record.provider_id,
        domain=record.domain.value,
        source_record_id=record.source_record_id or f"CIK{cik}",
        source_url=str(record.source_url) if record.source_url else None,
        media_type=record.media_type,
        content_encoding="gzip",
        payload_sha256=record.payload_sha256,
        retrieved_at=record.retrieved_at,
        payload_bytes=gzip.compress(record.payload, mtime=0),
    )
    session.add(batch)
    session.flush()
    session.add_all([raw_payload, *new_observations])
    return {
        "status": "IMPORTED",
        "batch_id": str(batch.id),
        "source_digest": source_digest,
        "facts_inserted": inserted,
        "facts_reused": counters.get("mapped_facts", 0) - inserted,
        "reconciliation": reconciliation,
    }


def _load_cik_mappings(
    session: Session,
    company_id: UUID | None = None,
    company_ids: Sequence[UUID] | None = None,
) -> dict[UUID, str]:
    query = select(CompanyProviderIdentifier).where(
        CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
        CompanyProviderIdentifier.identifier_type == "SEC_CIK",
    )
    if company_id is not None:
        query = query.where(CompanyProviderIdentifier.company_id == company_id)
    if company_ids is not None:
        query = query.where(CompanyProviderIdentifier.company_id.in_(company_ids))
    rows = list(session.scalars(query))
    result: dict[UUID, str] = {}
    grouped: dict[UUID, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row.company_id].append(row.identifier_value)
    ambiguous = [str(key) for key, values in grouped.items() if len(values) != 1]
    if ambiguous:
        raise ValueError(f"Ambiguous SEC CIK mappings for company ids: {', '.join(ambiguous)}")
    result = {key: values[0] for key, values in grouped.items()}
    return result


async def sync_reported_fundamentals(
    session: Session,
    settings: Settings,
    company_id: UUID | None = None,
    company_ids: Sequence[UUID] | None = None,
) -> list[dict[str, object]]:
    if not settings.sec_user_agent:
        raise ValueError("Set SEC_USER_AGENT to an application name and contact email before sync")
    identifiers = _load_cik_mappings(session, company_id, company_ids)
    if company_id is not None and company_id not in identifiers:
        return [{"company_id": str(company_id), "status": "UNMAPPED_SEC_IDENTITY"}]
    if not identifiers:
        return [{"status": "NO_VERIFIED_SEC_IDENTITIES"}]
    ordered_company_ids = (
        [item for item in company_ids if item in identifiers]
        if company_ids is not None
        else sorted(identifiers, key=str)
    )
    query = ProviderQuery(
        domain=ExternalDataDomain.REPORTED_FUNDAMENTALS,
        subjects=tuple(
            CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=item)
            for item in ordered_company_ids
        ),
        requested_at=datetime.now(UTC),
    )
    provider = SecCompanyFactsProvider(identifiers, settings.sec_user_agent)
    records = await provider.fetch(query)
    by_cik = {identifier: company for company, identifier in identifiers.items()}
    results: list[dict[str, object]] = []
    for record in records:
        cik = record.source_record_id.removeprefix("CIK") if record.source_record_id else ""
        company = by_cik[cik]
        results.append(
            {
                "company_id": str(company),
                **ingest_sec_company_facts(session, company, cik, record),
            }
        )
    return results


def record_cik_mapping(
    session: Session,
    company_id: UUID,
    cik: str,
    provider_company_name: str,
    evidence_source: str,
) -> CompanyProviderIdentifier:
    if session.get(Company, company_id) is None:
        raise ValueError("Canonical company was not found")
    if not re.fullmatch(r"\d{10}", cik):
        raise ValueError("SEC CIK must contain ten digits, including leading zeroes")
    if not provider_company_name.strip() or not evidence_source.strip():
        raise ValueError("Record the SEC issuer name and identity evidence source")
    existing = session.scalar(
        select(CompanyProviderIdentifier).where(
            CompanyProviderIdentifier.provider_id == SEC_PROVIDER_ID,
            CompanyProviderIdentifier.identifier_type == "SEC_CIK",
            CompanyProviderIdentifier.identifier_value == cik,
        )
    )
    if existing is not None:
        if existing.company_id == company_id:
            return existing
        raise ValueError("This SEC CIK is already mapped to a different canonical company")
    mapping = CompanyProviderIdentifier(
        id=uuid4(),
        company_id=company_id,
        provider_id=SEC_PROVIDER_ID,
        identifier_type="SEC_CIK",
        identifier_value=cik,
        provider_company_name=provider_company_name.strip(),
        evidence_source=evidence_source.strip(),
        effective_at=now(),
        recorded_at=now(),
        actor="IMPORT",
    )
    session.add(mapping)
    session.flush()
    return mapping


def _run_cli() -> int:
    parser = argparse.ArgumentParser(description="Import canonical reported financial facts")
    commands = parser.add_subparsers(dest="command", required=True)
    map_parser = commands.add_parser("map", help="record a manually verified SEC issuer identity")
    map_parser.add_argument("--company-id", type=UUID, required=True)
    map_parser.add_argument("--cik", required=True, help="ten-digit SEC Central Index Key")
    map_parser.add_argument("--provider-company-name", required=True)
    map_parser.add_argument("--evidence-source", required=True, help="SEC issuer or filing URL")
    sync_parser = commands.add_parser("sync", help="fetch and append facts for mapped issuers")
    sync_parser.add_argument("--company-id", type=UUID)
    args = parser.parse_args()
    settings = Settings()
    engine = create_database_engine(settings)
    if engine is None:
        parser.error("Set DATABASE_URL before running reported-fundamentals ingestion")
    try:
        with Session(engine) as session:
            if args.command == "map":
                mapping = record_cik_mapping(
                    session,
                    args.company_id,
                    args.cik,
                    args.provider_company_name,
                    args.evidence_source,
                )
                session.commit()
                print(
                    json.dumps(
                        {
                            "company_id": str(mapping.company_id),
                            "provider_id": mapping.provider_id,
                            "identifier_type": mapping.identifier_type,
                            "identifier_value": mapping.identifier_value,
                            "provider_company_name": mapping.provider_company_name,
                            "evidence_source": mapping.evidence_source,
                        },
                        indent=2,
                    )
                )
            else:
                results = asyncio.run(
                    sync_reported_fundamentals(session, settings, args.company_id)
                )
                session.commit()
                print(json.dumps(results, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(_run_cli())
