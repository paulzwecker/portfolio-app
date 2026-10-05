"""Provider-neutral contracts for future external-data ingestion adapters.

Provider payloads end at this boundary. Domain normalizers own the conversion to
the existing or future canonical observation schemas.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class ExternalDataDomain(StrEnum):
    MARKET_DATA = "MARKET_DATA"
    FX = "FX"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"
    REPORTED_FUNDAMENTALS = "REPORTED_FUNDAMENTALS"
    CONSENSUS_ESTIMATES = "CONSENSUS_ESTIMATES"
    COMPANY_REFERENCE = "COMPANY_REFERENCE"
    SOURCE_DOCUMENTS = "SOURCE_DOCUMENTS"


class CanonicalSubjectKind(StrEnum):
    COMPANY = "COMPANY"
    SECURITY = "SECURITY"
    LISTING = "LISTING"
    CURRENCY_PAIR = "CURRENCY_PAIR"


class CanonicalSubjectRef(BaseModel):
    """Canonical query identity; adapters resolve provider symbols privately."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CanonicalSubjectKind
    id: UUID | None = None
    base_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    quote_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_identity(self) -> CanonicalSubjectRef:
        if self.kind == CanonicalSubjectKind.CURRENCY_PAIR:
            if self.id is not None or self.base_currency is None or self.quote_currency is None:
                raise ValueError("Currency-pair subjects require exactly two ISO currencies")
            if self.base_currency == self.quote_currency:
                raise ValueError("Currency-pair currencies must be distinct")
        elif self.id is None or self.base_currency is not None or self.quote_currency is not None:
            raise ValueError("Company, security and listing subjects require one canonical id")
        return self


class ProviderQuery(BaseModel):
    """Canonical subjects and requested date window passed to any provider adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: ExternalDataDomain
    subjects: tuple[CanonicalSubjectRef, ...] = Field(min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    requested_at: datetime

    @field_validator("requested_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> ProviderQuery:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must be on or before end_date")
        return self


class RawProviderRecord(BaseModel):
    """One retained provider-native response record before domain normalization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: ExternalDataDomain
    provider_id: str = Field(min_length=1, max_length=120)
    provider_schema_version: str | None = Field(default=None, max_length=120)
    source_record_id: str | None = Field(default=None, max_length=500)
    source_url: AnyHttpUrl | None = None
    media_type: str = Field(min_length=1, max_length=160)
    retrieved_at: datetime
    payload: bytes | None = None
    payload_ref: str | None = Field(default=None, max_length=2000)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("provider_id", "source_record_id", "media_type", "payload_ref")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Text identifiers must not be blank")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def verify_payload_digest(self) -> RawProviderRecord:
        if (self.payload is None) == (self.payload_ref is None):
            raise ValueError("Provide exactly one of inline payload bytes or payload_ref")
        if self.payload is not None:
            actual = hashlib.sha256(self.payload).hexdigest()
            if actual != self.payload_sha256:
                raise ValueError("payload_sha256 does not match the raw payload bytes")
        return self


class NormalizationDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class NormalizationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1000)
    severity: str = Field(pattern=r"^(WARNING|ERROR)$")
    source_path: str | None = Field(default=None, max_length=500)


class NormalizationResult[CanonicalObservation](BaseModel):
    """Domain-specific canonical value plus adapter diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    disposition: NormalizationDisposition
    observation: CanonicalObservation | None
    issues: tuple[NormalizationIssue, ...] = ()

    @model_validator(mode="after")
    def validate_disposition(self) -> NormalizationResult[CanonicalObservation]:
        errors = any(issue.severity == "ERROR" for issue in self.issues)
        if self.disposition == NormalizationDisposition.ACCEPTED:
            if self.observation is None or errors:
                raise ValueError("Accepted normalization requires an observation and no errors")
        elif self.observation is not None or not errors:
            raise ValueError("Rejected normalization requires errors and no observation")
        return self


class ExternalDataProvider(Protocol):
    """Transport adapter. It returns raw records, never canonical domain objects."""

    provider_id: str

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]: ...


class DomainNormalizer[CanonicalObservation](Protocol):
    """Deterministic, versioned conversion from raw payload to one domain contract."""

    domain: ExternalDataDomain
    version: str

    def normalize(self, record: RawProviderRecord) -> NormalizationResult[CanonicalObservation]: ...


def raw_record_fingerprint(record: RawProviderRecord) -> str:
    """Stable content identity; a changed payload is a new correction candidate."""

    identity = record.source_record_id or record.payload_sha256
    value = {
        "domain": record.domain.value,
        "provider_id": record.provider_id,
        "source_record_id": identity,
        "payload_sha256": record.payload_sha256,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def raw_batch_fingerprint(
    provider_id: str,
    query: ProviderQuery,
    records: Sequence[RawProviderRecord],
) -> str:
    """Stable batch content identity independent of fetch order or retry time."""

    if not provider_id.strip():
        raise ValueError("provider_id must not be blank")
    if any(
        record.provider_id != provider_id or record.domain != query.domain for record in records
    ):
        raise ValueError("Every raw record must match the batch provider and requested domain")
    subjects = sorted(
        json.dumps(subject.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        for subject in query.subjects
    )
    request = {
        "domain": query.domain.value,
        "subjects": subjects,
        "start_date": query.start_date.isoformat() if query.start_date else None,
        "end_date": query.end_date.isoformat() if query.end_date else None,
    }
    value = {
        "provider_id": provider_id,
        "request": request,
        "records": sorted(raw_record_fingerprint(record) for record in records),
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
