"""One fixed, private EODHD demo snapshot; not a production estimates entitlement.

Relative trend/revision fields stay in the retained payload. They do not establish
historical application snapshots or an independently verified EPS accounting basis.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Context, Decimal, InvalidOperation
from typing import Any

from portfolio_api.consensus_estimates import CanonicalConsensusEstimate
from portfolio_api.domain.models import ConsensusEstimateProviderMapping
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    ExternalDataDomain,
    NormalizationDisposition,
    NormalizationIssue,
    NormalizationResult,
    ProviderQuery,
    ProviderTransportError,
    RawProviderRecord,
    parse_retry_after_seconds,
)
from portfolio_api.settings import Settings

EODHD_CONSENSUS_PROVIDER_ID = "eodhd_demo_estimates"
EODHD_CONSENSUS_SCHEMA_VERSION = "eodhd-fundamentals-v1.1"
EODHD_CONSENSUS_URL = (
    "https://eodhd.com/api/v1.1/fundamentals/AMZN.US"
    "?api_token=demo&fmt=json&filter=General,Earnings::Trend"
)
EODHD_CONSENSUS_RECORD_ID = "AMZN.US:trend"
MAX_RESPONSE_BYTES = 4_000_000
CURRENCY_BASIS_REASON = (
    "USD is constrained to this independently reviewed Amazon reporting/listing currency "
    "and the provider endpoint reporting-currency policy; General.CurrencyCode alone "
    "does not establish estimate currency for other issuers."
)
EPS_BASIS_REASON = (
    "Provider-defined EPS: GAAP versus adjusted accounting basis is not explicitly "
    "verified for this row; do not equate it with reported EPS or accepted model assumptions."
)


def _mapping(mapping: ConsensusEstimateProviderMapping) -> None:
    if (
        mapping.provider_id != EODHD_CONSENSUS_PROVIDER_ID
        or mapping.provider_symbol != "AMZN.US"
        or mapping.currency != "USD"
        or mapping.listing_id is None
        or not mapping.evidence_source
        or not mapping.currency_evidence_source
    ):
        raise ValueError("Demo estimates require an exact evidenced AMZN.US/USD listing mapping")


def _isolated(settings: Settings) -> None:
    if settings.app_env == "production" or settings.database_target_environment == "production":
        raise ValueError("EODHD demo estimates are isolated-only, not production feed approval")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _default_transport(url: str) -> bytes:
    if url != EODHD_CONSENSUS_URL:
        raise ValueError("Only the documented fixed AMZN demo estimates request is allowed")
    request = urllib.request.Request(
        url, headers={"User-Agent": "PortfolioResearch private estimates evaluation/1.0"}
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=30) as response:
            payload = bytes(response.read(MAX_RESPONSE_BYTES + 1))
    except urllib.error.HTTPError as error:
        raise ProviderTransportError(
            EODHD_CONSENSUS_PROVIDER_ID,
            "PROVIDER_HTTP_ERROR",
            f"EODHD demo returned HTTP {error.code}; no alternate endpoint was used.",
            retryable=error.code == 429 or error.code >= 500,
            retry_after_seconds=parse_retry_after_seconds(error.headers.get("Retry-After")),
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderTransportError(
            EODHD_CONSENSUS_PROVIDER_ID,
            "PROVIDER_UNAVAILABLE",
            "EODHD demo estimates request failed; no alternate endpoint was used.",
            retryable=True,
        ) from None
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Demo estimates response exceeds the bounded size")
    return payload


class EodhdConsensusProvider:
    provider_id = EODHD_CONSENSUS_PROVIDER_ID

    def __init__(
        self,
        settings: Settings,
        mapping: ConsensusEstimateProviderMapping,
        *,
        transport: Callable[[str], bytes] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        _isolated(settings)
        _mapping(mapping)
        self.settings = settings
        self.mapping = mapping
        self.transport = transport or _default_transport
        self.clock = clock or (lambda: datetime.now(UTC))

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        _isolated(self.settings)
        _mapping(self.mapping)
        if (
            query.domain != ExternalDataDomain.CONSENSUS_ESTIMATES
            or len(query.subjects) != 1
            or query.subjects[0].kind != CanonicalSubjectKind.COMPANY
            or query.subjects[0].id != self.mapping.company_id
            or query.start_date is not None
            or query.end_date is not None
        ):
            raise ValueError("Demo estimates support one mapped company and current snapshots only")
        payload = await asyncio.to_thread(self.transport, EODHD_CONSENSUS_URL)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("Demo estimates response exceeds the bounded size")
        return [
            RawProviderRecord(
                domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
                provider_id=self.provider_id,
                provider_schema_version=EODHD_CONSENSUS_SCHEMA_VERSION,
                source_record_id=EODHD_CONSENSUS_RECORD_ID,
                source_url=EODHD_CONSENSUS_URL,
                media_type="application/json",
                retrieved_at=self.clock(),
                payload=payload,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
            )
        ]


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a financial observation")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid financial decimal") from error
    if not result.is_finite() or abs(result) >= Decimal("1e26"):
        raise ValueError("Financial decimal is outside canonical precision")
    if result != result.quantize(Decimal("1e-12"), context=Context(prec=50)):
        raise ValueError("Financial decimal exceeds canonical scale")
    return result


def _count(value: object) -> int | None:
    count = _decimal(value)
    if count is None:
        return None
    if count != count.to_integral_value() or not 0 < count <= 2_147_483_647:
        raise ValueError("Analyst count must be a positive integer")
    return int(count)


def _reject(code: str, message: str) -> NormalizationResult[tuple[CanonicalConsensusEstimate, ...]]:
    return NormalizationResult(
        disposition=NormalizationDisposition.REJECTED,
        observation=None,
        issues=(NormalizationIssue(code=code, message=message, severity="ERROR"),),
    )


class EodhdConsensusNormalizer:
    domain = ExternalDataDomain.CONSENSUS_ESTIMATES
    version = "eodhd-demo-consensus-v1"

    def __init__(self, mapping: ConsensusEstimateProviderMapping) -> None:
        _mapping(mapping)
        self.mapping = mapping

    def normalize(
        self, record: RawProviderRecord
    ) -> NormalizationResult[tuple[CanonicalConsensusEstimate, ...]]:
        _mapping(self.mapping)
        if (
            record.provider_id != EODHD_CONSENSUS_PROVIDER_ID
            or record.provider_schema_version != EODHD_CONSENSUS_SCHEMA_VERSION
            or record.domain != self.domain
            or record.source_record_id != EODHD_CONSENSUS_RECORD_ID
            or str(record.source_url) != EODHD_CONSENSUS_URL
            or record.payload is None
            or len(record.payload) > MAX_RESPONSE_BYTES
        ):
            return _reject(
                "PROVIDER_IDENTITY_MISMATCH", "Exact demo estimates evidence is required"
            )
        try:
            payload = json.loads(record.payload, parse_float=Decimal)
        except (ValueError, UnicodeError):
            return _reject("INVALID_JSON", "Demo estimates response is not valid JSON")
        if not isinstance(payload, dict) or not isinstance(payload.get("General"), dict):
            return _reject("INVALID_RESPONSE_SHAPE", "Combined General and Trend data is required")
        general = payload["General"]
        expected = {
            "Code": "AMZN",
            "PrimaryTicker": "AMZN.US",
            "Exchange": "NASDAQ",
            "CurrencyCode": "USD",
            "Type": "Common Stock",
            "CIK": "0001018724",
            "FiscalYearEnd": "December",
            "IsDelisted": False,
        }
        if (
            any(general.get(key) != value for key, value in expected.items())
            or general.get("IsDelisted") is not False
            or str(general.get("Name", "")).casefold().replace(" ", "").rstrip(".")
            != "amazon.cominc"
        ):
            return _reject(
                "ISSUER_CURRENCY_MISMATCH", "Reviewed issuer, listing or currency changed"
            )
        earnings = payload.get("Earnings")
        nested = earnings.get("Trend") if isinstance(earnings, dict) else None
        trend = payload.get("Earnings::Trend", nested)
        if nested is not None and "Earnings::Trend" in payload and trend != nested:
            return _reject("CONFLICTING_TREND_DATA", "Two Trend representations disagree")
        if not isinstance(trend, dict) or set(trend) - {"Annual", "Quarterly"}:
            return _reject(
                "INVALID_TREND_SHAPE", "Separate annual and quarterly periods are required"
            )
        observations: list[CanonicalConsensusEstimate] = []
        issues: list[NormalizationIssue] = []
        snapshot = record.retrieved_at.astimezone(UTC)
        for group, period_type in (("Annual", "ANNUAL"), ("Quarterly", "QUARTERLY")):
            rows = trend.get(group, {})
            if not isinstance(rows, dict) or len(rows) > 128:
                return _reject(
                    "INVALID_PERIOD_ROWS", "Period rows must be bounded date-keyed objects"
                )
            for key, row in rows.items():
                path = f"Earnings.Trend.{group}.{key}"
                try:
                    end = date.fromisoformat(key)
                    if not isinstance(row, dict) or row.get("date") != key:
                        raise ValueError("Date identity mismatch")
                    if end <= snapshot.date():
                        issues.append(
                            NormalizationIssue(
                                code="NON_FORWARD_PERIOD",
                                message=(
                                    "Ended period is not a current forward estimate "
                                    "or historic snapshot"
                                ),
                                severity="WARNING",
                                source_path=path,
                            )
                        )
                        continue
                    quarter = (end.month - 1) // 3 + 1
                    if (
                        end.day != calendar.monthrange(end.year, end.month)[1]
                        or (
                            period_type == "ANNUAL"
                            and (end.month != 12 or row.get("type") != "yearly")
                        )
                        or (
                            period_type == "QUARTERLY"
                            and (
                                end.month not in {3, 6, 9, 12}
                                or row.get("type") != "quarterly"
                                or row.get("fiscalQuarter") != f"Q{quarter}"
                            )
                        )
                    ):
                        raise ValueError("Fiscal period does not match December year end")
                    if (
                        row.get("currency", "USD") != "USD"
                        or row.get("unit", "currency") != "currency"
                    ):
                        raise ValueError("Unexpected row currency or unit")
                except (ValueError, TypeError):
                    issues.append(
                        NormalizationIssue(
                            code="INVALID_PERIOD_IDENTITY",
                            message="Date, fiscal period, currency or unit is inconsistent",
                            severity="WARNING",
                            source_path=path,
                        )
                    )
                    continue
                for metric, prefix, unit in (
                    ("REVENUE", "revenueEstimate", "CURRENCY"),
                    ("EPS", "earningsEstimate", "CURRENCY_PER_SHARE"),
                ):
                    try:
                        value = _decimal(row.get(f"{prefix}Avg"))
                        if value is None:
                            continue
                        low, high = (
                            _decimal(row.get(f"{prefix}Low")),
                            _decimal(row.get(f"{prefix}High")),
                        )
                        count = _count(row.get(f"{prefix}NumberOfAnalysts"))
                        if metric == "REVENUE" and any(
                            v is not None and v < 0 for v in (value, low, high)
                        ):
                            raise ValueError("Revenue cannot be negative")
                        if (low is not None and low > value) or (high is not None and high < value):
                            raise ValueError("Estimate range is inconsistent")
                    except ValueError:
                        issues.append(
                            NormalizationIssue(
                                code="INVALID_ESTIMATE_VALUE",
                                message=f"{metric} value, range or analyst count is malformed",
                                severity="WARNING",
                                source_path=f"{path}.{prefix}",
                            )
                        )
                        continue
                    reasons = []
                    if low is None or high is None:
                        reasons.append("Provider estimate range is incomplete")
                    if count is None:
                        reasons.append("Provider analyst count is unavailable")
                    if metric == "EPS":
                        reasons.append(EPS_BASIS_REASON)
                    observations.append(
                        CanonicalConsensusEstimate(
                            company_id=self.mapping.company_id,
                            listing_id=self.mapping.listing_id,
                            provider_mapping_id=self.mapping.id,
                            provider_id=EODHD_CONSENSUS_PROVIDER_ID,
                            metric=metric,
                            period_type=period_type,
                            forecast_period=f"FY{end.year}"
                            if period_type == "ANNUAL"
                            else f"FY{end.year} Q{quarter}",
                            period_end=end,
                            value=value,
                            low_value=low,
                            high_value=high,
                            analyst_count=count,
                            currency="USD",
                            unit=unit,
                            snapshot_date=snapshot.date(),
                            observed_at=snapshot,
                            source_record_id=f"AMZN.US:{period_type}:{end}:{metric}",
                            source_ref=EODHD_CONSENSUS_URL,
                            quality_reason="; ".join([CURRENCY_BASIS_REASON, *reasons]),
                            data_quality="DATA_CHECK" if reasons else "PASS",
                        )
                    )
        return NormalizationResult(
            disposition=NormalizationDisposition.ACCEPTED,
            observation=tuple(observations),
            issues=tuple(issues),
        )
