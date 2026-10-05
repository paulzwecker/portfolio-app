"""Point-in-time consensus estimates, provider continuity, and legacy baseline import."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    Actor,
    Company,
    ConsensusEstimateBatch,
    ConsensusEstimateDataQuality,
    ConsensusEstimateMetric,
    ConsensusEstimateObservation,
    ConsensusEstimatePeriodType,
    ConsensusEstimateProviderMapping,
    ConsensusEstimateRevisionContext,
    ConsensusEstimateSourceRole,
    CurrentLifecycle,
    ExternalRawPayload,
    LifecycleEvent,
    Listing,
    Security,
    now,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    DomainNormalizer,
    ExternalDataDomain,
    ExternalDataProvider,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.legacy_import import Workbook
from portfolio_api.settings import Settings

FMP_PROVIDER_ID = "fmp_estimates"
LEGACY_PROVIDER_ID = "legacy_workbook_estimates"
NORMALIZER_VERSION = "consensus-estimates-v1"
LEGACY_SNAPSHOT_DATE = date(2026, 9, 12)
WORKBOOK_PATH = (
    Path(__file__).resolve().parents[4] / "reference" / "workbook" / "Portfolio_Watchlist.xlsx"
)
REPOSITORY_PATH = Path(__file__).resolve().parents[4]


class CanonicalConsensusEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    company_id: UUID
    listing_id: UUID | None
    provider_mapping_id: UUID
    provider_id: str
    metric: str
    period_type: str
    forecast_period: str
    period_end: date
    value: Decimal
    low_value: Decimal | None
    high_value: Decimal | None
    analyst_count: int | None
    currency: str | None
    unit: str
    snapshot_date: date
    observed_at: datetime
    source_record_id: str
    source_ref: str
    quality_reason: str | None
    data_quality: str


class FmpConsensusNormalizer(DomainNormalizer[tuple[CanonicalConsensusEstimate, ...]]):
    """Versioned FMP response-to-consensus contract, separate from transport."""

    domain = ExternalDataDomain.CONSENSUS_ESTIMATES
    version = NORMALIZER_VERSION

    def __init__(self, mapping: ConsensusEstimateProviderMapping, snapshot_date: date) -> None:
        self.mapping = mapping
        self.snapshot_date = snapshot_date

    def normalize(
        self, record: RawProviderRecord
    ) -> NormalizationResult[tuple[CanonicalConsensusEstimate, ...]]:
        values, issues = normalize_fmp_record(
            record, self.mapping, snapshot_date=self.snapshot_date
        )
        normalized = tuple(CanonicalConsensusEstimate.model_validate(value) for value in values)
        if not normalized and any(issue.severity == "ERROR" for issue in issues):
            return NormalizationResult(
                disposition=NormalizationDisposition.REJECTED,
                observation=None,
                issues=tuple(issues),
            )
        # Row-level diagnostics remain attached to the response while valid neighboring
        # periods can still be retained as explicit observations.
        warnings = tuple(issue.model_copy(update={"severity": "WARNING"}) for issue in issues)
        return NormalizationResult(
            disposition=NormalizationDisposition.ACCEPTED,
            observation=normalized,
            issues=warnings,
        )


class FmpConsensusProvider(ExternalDataProvider):
    """Transport adapter for FMP's analyst-estimates endpoint.

    It captures the provider response now; FMP's period date is the fiscal period end,
    never an estimate's historical observation timestamp.
    """

    provider_id = FMP_PROVIDER_ID

    def __init__(self, api_key: str, provider_symbols: dict[UUID, str]) -> None:
        if not api_key.strip():
            raise ValueError("FMP_API_KEY is required for estimate ingestion")
        self._api_key = api_key
        self._symbols = provider_symbols

    async def fetch(self, query: ProviderQuery) -> tuple[RawProviderRecord, ...]:
        if query.domain != ExternalDataDomain.CONSENSUS_ESTIMATES:
            raise ValueError("FMP estimate adapter only supports consensus estimates")
        records: list[RawProviderRecord] = []
        for subject in query.subjects:
            if subject.kind != CanonicalSubjectKind.COMPANY or subject.id not in self._symbols:
                raise ValueError("FMP estimates require an exact provider symbol mapping")
            symbol = self._symbols[subject.id]
            for period in ("annual", "quarter"):
                records.append(await asyncio.to_thread(self._fetch_one, symbol, period))
        return tuple(records)

    def _fetch_one(self, symbol: str, period: str) -> RawProviderRecord:
        query = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "period": period,
                "page": 0,
                "limit": 40,
                "apikey": self._api_key,
            }
        )
        url = f"https://financialmodelingprep.com/stable/analyst-estimates?{query}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                schema_version = response.headers.get("X-Api-Version")
                retrieved_at = datetime.now(UTC)
        except Exception:
            # urllib's exception text can contain the API key query parameter.
            raise RuntimeError(
                "FMP estimate request failed; request details were omitted"
            ) from None
        safe_url = (
            "https://financialmodelingprep.com/stable/analyst-estimates?"
            + urllib.parse.urlencode({"symbol": symbol, "period": period, "page": 0, "limit": 40})
        )
        return RawProviderRecord(
            domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
            provider_id=FMP_PROVIDER_ID,
            provider_schema_version=schema_version,
            source_record_id=f"{symbol}:{period}",
            source_url=safe_url,
            media_type="application/json",
            retrieved_at=retrieved_at,
            payload=payload,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
        )


def normalize_fmp_record(
    record: RawProviderRecord,
    mapping: ConsensusEstimateProviderMapping,
    *,
    snapshot_date: date,
) -> tuple[list[dict[str, Any]], list[NormalizationIssue]]:
    """Normalize only explicit forward-period mean consensus; preserve provider values."""
    if record.provider_id != FMP_PROVIDER_ID or record.payload is None:
        raise ValueError("Expected an inline FMP provider response")
    if record.source_record_id is None:
        raise ValueError("Provider response needs a stable source record ID")
    period_type = (
        ConsensusEstimatePeriodType.ANNUAL
        if record.source_record_id.endswith(":annual")
        else ConsensusEstimatePeriodType.QUARTERLY
    )
    try:
        payload = json.loads(record.payload, parse_float=Decimal, parse_int=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [], [
            NormalizationIssue(
                code="INVALID_JSON",
                message="Provider payload is not valid UTF-8 JSON",
                severity="ERROR",
            )
        ]
    if not isinstance(payload, list):
        return [], [
            NormalizationIssue(
                code="INVALID_RESPONSE_SHAPE",
                message="FMP estimates response must be a JSON array",
                severity="ERROR",
            )
        ]
    observations: list[dict[str, Any]] = []
    issues: list[NormalizationIssue] = []
    for index, raw in enumerate(payload):
        path = f"[{index}]"
        if not isinstance(raw, dict):
            issues.append(
                NormalizationIssue(
                    code="INVALID_PERIOD_ROW",
                    message="Estimate row is not an object",
                    severity="ERROR",
                    source_path=path,
                )
            )
            continue
        raw_date = raw.get("date")
        try:
            period_end = date.fromisoformat(str(raw_date))
        except (TypeError, ValueError):
            issues.append(
                NormalizationIssue(
                    code="INVALID_PERIOD_END",
                    message="Provider fiscal period date is missing or invalid",
                    severity="ERROR",
                    source_path=f"{path}.date",
                )
            )
            continue
        # Ended periods are actual/reporting data, not a forward consensus observation.
        if period_end <= snapshot_date:
            issues.append(
                NormalizationIssue(
                    code="NON_FORWARD_PERIOD",
                    message="Ended fiscal period excluded from consensus estimates",
                    severity="WARNING",
                    source_path=f"{path}.date",
                )
            )
            continue
        for metric, prefix, count_key, unit in (
            (ConsensusEstimateMetric.REVENUE, "revenue", "numAnalystsRevenue", "CURRENCY"),
            (ConsensusEstimateMetric.EPS, "eps", "numAnalystsEps", "CURRENCY_PER_SHARE"),
        ):
            average = _decimal(raw.get(f"{prefix}Avg"))
            if average is None:
                if raw.get(f"{prefix}Avg") not in (None, ""):
                    issues.append(
                        NormalizationIssue(
                            code="INVALID_ESTIMATE_VALUE",
                            message=f"{metric.value} mean estimate is not an exact decimal",
                            severity="ERROR",
                            source_path=f"{path}.{prefix}Avg",
                        )
                    )
                continue
            low = _decimal(raw.get(f"{prefix}Low"))
            high = _decimal(raw.get(f"{prefix}High"))
            analyst_count = _integer(raw.get(count_key))
            range_valid = (
                (low is None or low <= average)
                and (high is None or high >= average)
                and (low is None or high is None or low <= high)
            )
            issues_local: list[str] = []
            if metric == ConsensusEstimateMetric.REVENUE and average < 0:
                issues_local.append("Revenue mean estimate is negative")
            if not range_valid:
                issues_local.append("Provider low/mean/high estimates are inconsistent")
                low = None
                high = None
            if analyst_count is None:
                issues_local.append("Provider analyst count is unavailable")
            if mapping.currency is None:
                issues_local.append(
                    "Reporting currency has not been verified for this provider mapping"
                )
            observations.append(
                {
                    "company_id": mapping.company_id,
                    "listing_id": mapping.listing_id,
                    "provider_mapping_id": mapping.id,
                    "provider_id": FMP_PROVIDER_ID,
                    "metric": metric.value,
                    "period_type": period_type.value,
                    "forecast_period": f"{period_type.value} ending {period_end.isoformat()}",
                    "period_end": period_end,
                    "value": average,
                    "low_value": low,
                    "high_value": high,
                    "analyst_count": analyst_count,
                    "currency": mapping.currency,
                    "unit": unit,
                    "snapshot_date": snapshot_date,
                    "observed_at": record.retrieved_at,
                    "source_record_id": (
                        f"{mapping.provider_symbol}:{period_end.isoformat()}:{metric.value}"
                    ),
                    "source_ref": str(
                        record.source_url
                        or "https://financialmodelingprep.com/developer/docs/stable/financial-estimates"
                    ),
                    "quality_reason": "; ".join(issues_local) or None,
                    "data_quality": ConsensusEstimateDataQuality.DATA_CHECK.value
                    if issues_local
                    else ConsensusEstimateDataQuality.PASS.value,
                }
            )
    return observations, issues


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _integer(value: object) -> int | None:
    parsed = _decimal(value)
    if parsed is None or parsed != parsed.to_integral_value() or parsed < 0:
        return None
    return int(parsed)


def estimate_values_changed(
    previous: ConsensusEstimateObservation, candidate: dict[str, Any]
) -> bool:
    """A changed same-source period gets a new revision linked to its predecessor."""
    return any(
        getattr(previous, key) != candidate[key]
        for key in ("value", "low_value", "high_value", "analyst_count", "currency")
    )


def add_provider_mapping(
    session: Session,
    *,
    company_id: UUID,
    provider_id: str,
    provider_symbol: str,
    role: ConsensusEstimateSourceRole,
    evidence_source: str,
    effective_from: datetime,
    priority: int = 100,
    listing_id: UUID | None = None,
    currency: str | None = None,
    currency_evidence_source: str | None = None,
    actor: Actor = Actor.LOCAL_USER,
) -> ConsensusEstimateProviderMapping:
    if effective_from.tzinfo is None or effective_from.utcoffset() is None:
        raise ValueError("effective_from must include a timezone offset")
    if session.get(Company, company_id) is None:
        raise ValueError("Company does not exist")
    if listing_id is not None:
        listing = session.get(Listing, listing_id)
        security = session.get(Security, listing.security_id) if listing else None
        if security is None or security.company_id != company_id:
            raise ValueError("Listing must belong to the mapped company")
    if currency is not None and not (
        len(currency) == 3 and currency.isalpha() and currency.isupper()
    ):
        raise ValueError("Currency must be an ISO-style three-letter code")
    if (currency is None) != (currency_evidence_source is None):
        raise ValueError("Currency and currency evidence must be supplied together")
    prior = list(
        session.scalars(
            select(ConsensusEstimateProviderMapping).where(
                ConsensusEstimateProviderMapping.company_id == company_id,
                ConsensusEstimateProviderMapping.role == role.value,
            )
        )
    )
    if any(
        item.effective_from == effective_from
        and (
            item.provider_id == provider_id
            or item.role == ConsensusEstimateSourceRole.PRIMARY.value
            and role == ConsensusEstimateSourceRole.PRIMARY
        )
        for item in prior
    ):
        raise ValueError(
            "A mapping already exists for this provider/role, or another primary "
            "is effective at this time"
        )
    row = ConsensusEstimateProviderMapping(
        id=uuid4(),
        company_id=company_id,
        listing_id=listing_id,
        provider_id=provider_id,
        provider_symbol=provider_symbol,
        role=role.value,
        priority=priority,
        currency=currency,
        evidence_source=evidence_source,
        currency_evidence_source=currency_evidence_source,
        effective_from=effective_from.astimezone(UTC),
        recorded_at=now(),
        actor=actor.value,
    )
    session.add(row)
    session.flush()
    return row


def persist_provider_response(
    session: Session,
    record: RawProviderRecord,
    mapping: ConsensusEstimateProviderMapping,
) -> dict[str, Any]:
    """Persist raw FMP response and normalized immutable snapshots idempotently."""
    if record.retrieved_at.tzinfo is None:
        raise ValueError("Provider retrieved_at must be timezone-aware")
    if mapping.provider_id != record.provider_id or record.source_record_id is None:
        raise ValueError("Provider response must match the exact provider mapping")
    assert record.payload is not None
    digest = hashlib.sha256(
        f"{record.provider_id}:{record.source_record_id}:{record.payload_sha256}".encode()
    ).hexdigest()
    snapshot = record.retrieved_at.astimezone(UTC)
    existing = session.scalar(
        select(ConsensusEstimateBatch).where(
            ConsensusEstimateBatch.source_digest == digest,
            ConsensusEstimateBatch.normalizer_version == NORMALIZER_VERSION,
            ConsensusEstimateBatch.observed_at == snapshot,
        )
    )
    if existing is not None:
        return {"status": "ALREADY_IMPORTED", "batch_id": str(existing.id), "facts_inserted": 0}
    normalized_result = FmpConsensusNormalizer(mapping, snapshot.date()).normalize(record)
    normalized = [item.model_dump(mode="python") for item in (normalized_result.observation or ())]
    issues = normalized_result.issues
    try:
        response_rows = len(json.loads(record.payload))
    except (json.JSONDecodeError, TypeError):
        response_rows = 0
    batch_id = uuid4()
    reconciliation = {
        "response_rows": response_rows,
        "normalized_facts": len(normalized),
        "data_check_facts": sum(item["data_quality"] == "DATA_CHECK" for item in normalized),
        "issues": [item.model_dump(mode="json") for item in issues],
    }
    batch = ConsensusEstimateBatch(
        id=batch_id,
        provider_id=record.provider_id,
        provider_schema_version=record.provider_schema_version,
        normalizer_version=NORMALIZER_VERSION,
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES.value,
        source_kind="PROVIDER_RESPONSE",
        source_digest=digest,
        source_reference=str(record.source_url or ""),
        query_scope={
            "provider_symbol": mapping.provider_symbol,
            "period_type": record.source_record_id.rsplit(":", 1)[-1],
        },
        snapshot_date=snapshot.date(),
        observed_at=snapshot,
        recorded_at=now(),
        provider_summary={"provider_symbol": mapping.provider_symbol, "facts": len(normalized)},
        reconciliation=reconciliation,
    )
    raw = ExternalRawPayload(
        id=uuid4(),
        batch_id=None,
        reported_fundamental_batch_id=None,
        consensus_estimate_batch_id=batch_id,
        provider_id=record.provider_id,
        domain=record.domain.value,
        source_record_id=record.source_record_id,
        source_url=str(record.source_url) if record.source_url else None,
        media_type=record.media_type,
        content_encoding="identity",
        payload_sha256=digest,
        retrieved_at=snapshot,
        payload_bytes=record.payload,
    )
    session.add(batch)
    session.flush()
    session.add(raw)
    inserted = 0
    for item in normalized:
        prior = session.scalar(
            select(ConsensusEstimateObservation)
            .where(
                ConsensusEstimateObservation.provider_mapping_id == mapping.id,
                ConsensusEstimateObservation.metric == item["metric"],
                ConsensusEstimateObservation.period_type == item["period_type"],
                ConsensusEstimateObservation.period_end == item["period_end"],
                ConsensusEstimateObservation.recorded_at <= snapshot,
            )
            .order_by(
                ConsensusEstimateObservation.observed_at.desc().nullslast(),
                ConsensusEstimateObservation.recorded_at.desc(),
            )
            .limit(1)
        )
        changed = prior is not None and estimate_values_changed(prior, item)
        session.add(
            ConsensusEstimateObservation(
                id=uuid4(),
                batch_id=batch_id,
                **item,
                recorded_at=now(),
                revision_context=(
                    ConsensusEstimateRevisionContext.REVISED.value
                    if changed
                    else ConsensusEstimateRevisionContext.SNAPSHOT.value
                ),
                supersedes_observation_id=prior.id if changed and prior else None,
            )
        )
        inserted += 1
    reconciliation["facts_inserted"] = inserted
    return {
        "status": "IMPORTED",
        "batch_id": str(batch_id),
        "facts_inserted": inserted,
        "reconciliation": reconciliation,
    }


def legacy_estimate_import_plan(
    workbook_path: Path = WORKBOOK_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    workbook = Workbook.read(
        workbook_path, lambda name: name in {"Estimate History", "Universe Registry"}
    )
    history = workbook.rows("Estimate History", first_row=2)
    registry_rows = workbook.rows("Universe Registry", first_row=2)
    registry: dict[str, str] = {}
    for _, cells in registry_rows:
        ticker_cell = cells.get("A")
        name_cell = cells.get("B")
        registry_ticker = (ticker_cell.value if ticker_cell else None) or ""
        name = (name_cell.value if name_cell else None) or ""
        if registry_ticker and name:
            registry[registry_ticker.strip().upper()] = name.strip()
    source_tickers: set[str] = set()
    resolved_tickers: set[str] = set()
    rows: list[dict[str, Any]] = []
    for row_number, cells in history:
        ticker = _cell_value(cells, "B")
        if not ticker:
            continue
        source_tickers.add(ticker.upper())
        identity = registry.get(ticker.upper())
        if identity is None:
            rows.append({"row": row_number, "ticker": ticker, "status": "UNRESOLVED_IDENTITY"})
            continue
        resolved_tickers.add(ticker.upper())
        for col, metric, horizon in (
            ("D", "REVENUE", "FY+1"),
            ("E", "REVENUE", "FY+2"),
            ("F", "EPS", "FY+1"),
            ("G", "EPS", "FY+2"),
        ):
            cell = cells.get(col)
            if cell is None or cell.value in (None, ""):
                continue
            try:
                if cell.value is None:
                    continue
                value = Decimal(cell.value)
            except InvalidOperation:
                rows.append(
                    {
                        "row": row_number,
                        "ticker": ticker,
                        "metric": metric,
                        "horizon": horizon,
                        "status": "INVALID_VALUE",
                    }
                )
                continue
            snapshot = _excel_date(_cell_value(cells, "A"))
            rows.append(
                {
                    "row": row_number,
                    "ticker": ticker,
                    "company_name": identity,
                    "metric": metric,
                    "horizon": horizon,
                    "value": value,
                    "snapshot_date": snapshot.isoformat(),
                    "status": "DATA_CHECK",
                    "quality_reason": (
                        "Legacy snapshot has no vendor, currency, or absolute fiscal period "
                        "mapping."
                    ),
                    "source_record_id": f"{ticker}:{row_number}:{metric}:{horizon}",
                    "source_ref": (
                        f"{_workbook_label(workbook_path)}#Estimate History!{col}{row_number}"
                    ),
                }
            )
    report = {
        "source_file": _workbook_label(workbook_path),
        "source_sha256": workbook.sha256,
        "source_sheet": "Estimate History",
        "snapshot_date": LEGACY_SNAPSHOT_DATE.isoformat(),
        "company_rows": len(source_tickers),
        "resolved_company_count": len(resolved_tickers),
        "observation_count": len([row for row in rows if "value" in row]),
        "unresolved_identity_rows": [row for row in rows if row["status"] == "UNRESOLVED_IDENTITY"],
        "limitations": [
            "Provider/vendor identity is absent",
            "Source currency is absent",
            "FY+1/FY+2 cannot be safely mapped to absolute fiscal period-end dates",
            "Estimate Momentum formulas and older approximate source recency notes were excluded",
        ],
    }
    return report, rows


def import_legacy_estimates(
    session: Session, workbook_path: Path = WORKBOOK_PATH
) -> dict[str, Any]:
    report, rows = legacy_estimate_import_plan(workbook_path)
    digest = report["source_sha256"]
    observed_at = None
    existing = session.scalar(
        select(ConsensusEstimateBatch).where(
            ConsensusEstimateBatch.source_digest == digest,
            ConsensusEstimateBatch.normalizer_version == NORMALIZER_VERSION,
            ConsensusEstimateBatch.observed_at.is_(None),
        )
    )
    if existing is not None:
        by_name = {item.name.casefold(): item for item in session.scalars(select(Company))}
        value_reconciliation = _reconcile_legacy_values(session, existing.id, rows, by_name)
        lifecycle_coverage = _legacy_estimate_lifecycle_coverage(session, existing.id)
        return {
            "status": "ALREADY_IMPORTED",
            "batch_id": str(existing.id),
            "value_reconciliation": value_reconciliation,
            "lifecycle_company_counts": lifecycle_coverage,
            **existing.reconciliation,
        }
    by_name = {item.name.casefold(): item for item in session.scalars(select(Company))}
    batch_id = uuid4()
    mapping_by_company: dict[UUID, ConsensusEstimateProviderMapping] = {}
    canonical_rows = [row for row in rows if "value" in row]
    resolvable_rows: list[tuple[dict[str, Any], Company]] = []
    canonical_unresolved: list[dict[str, Any]] = []
    for row in canonical_rows:
        company = by_name.get(row["company_name"].casefold())
        if company is None:
            canonical_unresolved.append(
                {
                    "ticker": row["ticker"],
                    "company_name": row["company_name"],
                    "source_record_id": row["source_record_id"],
                }
            )
        else:
            resolvable_rows.append((row, company))
    for row, company in resolvable_rows:
        mapping = mapping_by_company.get(company.id)
        if mapping is None:
            mapping = session.scalar(
                select(ConsensusEstimateProviderMapping)
                .where(
                    ConsensusEstimateProviderMapping.company_id == company.id,
                    ConsensusEstimateProviderMapping.provider_id == LEGACY_PROVIDER_ID,
                    ConsensusEstimateProviderMapping.role
                    == ConsensusEstimateSourceRole.FALLBACK.value,
                )
                .order_by(ConsensusEstimateProviderMapping.effective_from.desc())
                .limit(1)
            )
            if mapping is None:
                mapping = ConsensusEstimateProviderMapping(
                    id=uuid4(),
                    company_id=company.id,
                    listing_id=None,
                    provider_id=LEGACY_PROVIDER_ID,
                    provider_symbol=row["ticker"],
                    role=ConsensusEstimateSourceRole.FALLBACK.value,
                    priority=1000,
                    currency=None,
                    evidence_source=f"sha256:{digest}#Estimate History",
                    currency_evidence_source=None,
                    effective_from=datetime.combine(LEGACY_SNAPSHOT_DATE, time.min, UTC),
                    recorded_at=now(),
                    actor=Actor.IMPORT.value,
                )
                session.add(mapping)
                session.flush()
            mapping_by_company[company.id] = mapping
    batch = ConsensusEstimateBatch(
        id=batch_id,
        provider_id=LEGACY_PROVIDER_ID,
        provider_schema_version=None,
        normalizer_version=NORMALIZER_VERSION,
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES.value,
        source_kind="LEGACY_WORKBOOK",
        source_digest=digest,
        source_reference=f"{_workbook_label(workbook_path)}#Estimate History",
        query_scope={
            "sheet": "Estimate History",
            "snapshot_date": LEGACY_SNAPSHOT_DATE.isoformat(),
        },
        snapshot_date=LEGACY_SNAPSHOT_DATE,
        observed_at=observed_at,
        recorded_at=now(),
        provider_summary={
            "company_rows": report["company_rows"],
            "raw_estimate_count": report["observation_count"],
        },
        reconciliation={
            "observations_imported": len(resolvable_rows),
            "data_check_count": len(resolvable_rows),
            "company_count": len(mapping_by_company),
            "identity_issues": report["unresolved_identity_rows"],
            "canonical_unresolved": canonical_unresolved,
            "source_sha256": digest,
        },
    )
    session.add(batch)
    session.flush()
    inserted = 0
    for row, company in resolvable_rows:
        mapping = mapping_by_company[company.id]
        session.add(
            ConsensusEstimateObservation(
                id=uuid4(),
                company_id=company.id,
                listing_id=None,
                provider_mapping_id=mapping.id,
                batch_id=batch_id,
                provider_id=LEGACY_PROVIDER_ID,
                metric=row["metric"],
                period_type="ANNUAL",
                forecast_period=row["horizon"],
                period_end=None,
                value=row["value"],
                low_value=None,
                high_value=None,
                analyst_count=None,
                currency=None,
                unit="CURRENCY" if row["metric"] == "REVENUE" else "CURRENCY_PER_SHARE",
                snapshot_date=LEGACY_SNAPSHOT_DATE,
                observed_at=None,
                recorded_at=now(),
                source_record_id=row["source_record_id"],
                source_ref=row["source_ref"],
                revision_context=ConsensusEstimateRevisionContext.LEGACY_BASELINE.value,
                data_quality=ConsensusEstimateDataQuality.DATA_CHECK.value,
                quality_reason=row["quality_reason"],
                supersedes_observation_id=None,
            )
        )
        inserted += 1
    if inserted != len(resolvable_rows):
        raise RuntimeError("Estimate migration row count changed during import")
    session.flush()
    value_reconciliation = _reconcile_legacy_values(session, batch_id, rows, by_name)
    lifecycle_coverage = _legacy_estimate_lifecycle_coverage(session, batch_id)
    return {
        "status": "IMPORTED",
        "batch_id": str(batch_id),
        "value_reconciliation": value_reconciliation,
        "lifecycle_company_counts": lifecycle_coverage,
        **batch.reconciliation,
    }


def _reconcile_legacy_values(
    session: Session,
    batch_id: UUID,
    source_rows: list[dict[str, Any]],
    companies_by_name: dict[str, Company],
) -> dict[str, Any]:
    expected = {row["source_record_id"]: row for row in source_rows if "value" in row}
    stored = {
        item.source_record_id: item
        for item in session.scalars(
            select(ConsensusEstimateObservation).where(
                ConsensusEstimateObservation.batch_id == batch_id
            )
        )
    }
    mismatches: list[dict[str, Any]] = []
    for source_id, source in expected.items():
        observation = stored.get(source_id)
        company = companies_by_name.get(source.get("company_name", "").casefold())
        if (
            observation is None
            or company is None
            or observation.company_id != company.id
            or observation.metric != source["metric"]
            or observation.forecast_period != source["horizon"]
            or observation.value != source["value"]
            or observation.currency is not None
            or observation.period_end is not None
        ):
            mismatches.append(
                {
                    "source_record_id": source_id,
                    "expected_value": str(source["value"]),
                    "stored_value": str(observation.value) if observation else None,
                }
            )
    unexpected = sorted(set(stored) - set(expected))
    if unexpected:
        mismatches.extend(
            {"source_record_id": source_id, "issue": "unexpected_stored_observation"}
            for source_id in unexpected
        )
    result = {
        "source_value_count": len(expected),
        "stored_observation_count": len(stored),
        "matched_value_count": len(expected) - len(mismatches),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
    if mismatches:
        raise RuntimeError("Legacy consensus reconciliation found stored/source mismatches")
    return result


def _legacy_estimate_lifecycle_coverage(session: Session, batch_id: UUID) -> dict[str, int]:
    rows = session.execute(
        select(LifecycleEvent.new_state, ConsensusEstimateObservation.company_id)
        .select_from(ConsensusEstimateObservation)
        .outerjoin(
            CurrentLifecycle,
            CurrentLifecycle.company_id == ConsensusEstimateObservation.company_id,
        )
        .outerjoin(
            LifecycleEvent,
            (LifecycleEvent.company_id == CurrentLifecycle.company_id)
            & (LifecycleEvent.id == CurrentLifecycle.event_id),
        )
        .where(ConsensusEstimateObservation.batch_id == batch_id)
        .distinct()
    ).all()
    coverage: dict[str, set[UUID]] = defaultdict(set)
    for lifecycle, company_id in rows:
        coverage[lifecycle or "UNASSIGNED"].add(company_id)
    return {lifecycle: len(company_ids) for lifecycle, company_ids in coverage.items()}


def _cell_value(cells: dict[str, Any], column: str) -> str | None:
    cell = cells.get(column)
    return cell.value.strip() if cell is not None and cell.value and cell.value.strip() else None


def _workbook_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_PATH).as_posix()
    except ValueError:
        return path.as_posix()


def _excel_date(value: str | None) -> date:
    if value is None:
        return LEGACY_SNAPSHOT_DATE
    # Excel's 1900 date system; the observed workbook serial is deliberately validated.
    days = int(Decimal(value))
    return date(1899, 12, 30).fromordinal(date(1899, 12, 30).toordinal() + days)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    legacy = sub.add_parser("import-legacy")
    legacy.add_argument("--apply", action="store_true")
    legacy.add_argument("--workbook", type=Path, default=WORKBOOK_PATH)
    legacy.add_argument("--report", type=Path)
    mapping = sub.add_parser("map")
    mapping.add_argument("--company-id", type=UUID, required=True)
    mapping.add_argument("--provider-id", required=True)
    mapping.add_argument("--provider-symbol", required=True)
    mapping.add_argument(
        "--role", choices=[item.value for item in ConsensusEstimateSourceRole], required=True
    )
    mapping.add_argument("--evidence-source", required=True)
    mapping.add_argument("--effective-from", type=datetime.fromisoformat, required=True)
    mapping.add_argument("--priority", type=int, default=100)
    mapping.add_argument("--listing-id", type=UUID)
    mapping.add_argument("--currency")
    mapping.add_argument("--currency-evidence-source")
    sync = sub.add_parser("sync-fmp")
    sync.add_argument("--company-id", type=UUID)
    args = parser.parse_args()
    settings = Settings()
    engine = create_database_engine(settings)
    if engine is None:
        raise SystemExit("Set DATABASE_URL before using consensus estimate commands")
    try:
        with Session(engine) as session:
            if args.command == "import-legacy":
                report, rows = legacy_estimate_import_plan(args.workbook)
                if not args.apply:
                    output: dict[str, Any] = {**report, "observations": rows}
                    if args.report:
                        args.report.write_text(json.dumps(output, indent=2, default=str) + "\n")
                    print(json.dumps(output, indent=2, default=str))
                    return
                import_result = import_legacy_estimates(session, args.workbook)
                session.commit()
                output = {"source_reconciliation": report, "import_result": import_result}
                if args.report:
                    args.report.write_text(json.dumps(output, indent=2, default=str) + "\n")
                print(json.dumps(output, indent=2, default=str))
            elif args.command == "map":
                mapping_result = add_provider_mapping(
                    session,
                    company_id=args.company_id,
                    provider_id=args.provider_id,
                    provider_symbol=args.provider_symbol,
                    role=ConsensusEstimateSourceRole(args.role),
                    evidence_source=args.evidence_source,
                    effective_from=args.effective_from,
                    priority=args.priority,
                    listing_id=args.listing_id,
                    currency=args.currency,
                    currency_evidence_source=args.currency_evidence_source,
                )
                session.commit()
                print(
                    json.dumps(
                        {
                            "id": str(mapping_result.id),
                            "provider_id": mapping_result.provider_id,
                            "provider_symbol": mapping_result.provider_symbol,
                        },
                        indent=2,
                    )
                )
            else:
                if settings.fmp_api_key is None:
                    raise SystemExit("Set FMP_API_KEY before synchronizing provider estimates")
                statement = select(ConsensusEstimateProviderMapping).where(
                    ConsensusEstimateProviderMapping.provider_id == FMP_PROVIDER_ID,
                    ConsensusEstimateProviderMapping.effective_from <= datetime.now(UTC),
                )
                if args.company_id is not None:
                    statement = statement.where(
                        ConsensusEstimateProviderMapping.company_id == args.company_id
                    )
                mappings = list(
                    session.scalars(
                        statement.order_by(
                            ConsensusEstimateProviderMapping.company_id,
                            ConsensusEstimateProviderMapping.effective_from.desc(),
                        )
                    )
                )
                latest_by_source: dict[tuple[str, UUID], ConsensusEstimateProviderMapping] = {}
                for mapping_row in mappings:
                    latest_by_source.setdefault(
                        (mapping_row.provider_id, mapping_row.company_id), mapping_row
                    )
                results: list[dict[str, Any]] = []
                for mapping_row in latest_by_source.values():
                    requested_at = datetime.now(UTC)
                    provider = FmpConsensusProvider(
                        settings.fmp_api_key.get_secret_value(),
                        {mapping_row.company_id: mapping_row.provider_symbol},
                    )
                    query = ProviderQuery(
                        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
                        subjects=(
                            CanonicalSubjectRef(
                                kind=CanonicalSubjectKind.COMPANY, id=mapping_row.company_id
                            ),
                        ),
                        requested_at=requested_at,
                    )
                    for record in asyncio.run(provider.fetch(query)):
                        results.append(persist_provider_response(session, record, mapping_row))
                session.commit()
                print(
                    json.dumps(
                        {
                            "provider_id": FMP_PROVIDER_ID,
                            "mapping_count": len(latest_by_source),
                            "batches": results,
                        },
                        indent=2,
                        default=str,
                    )
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
