"""Producer-neutral publication integrity and source/native valuation reconciliation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from portfolio_api.domain import schemas as s

PARITY_TOLERANCE = Decimal("0.0000001")


class PublishedFairValues(s.Contract):
    bear_fv: s.ModelNumber
    base_fv: s.ModelNumber
    bull_fv: s.ModelNumber
    weighted_fv: s.ModelNumber


class FinancialModelPublicationV1(s.Contract):
    contract_type: Literal["FinancialModelPublicationV1"]
    contract_version: Literal["1.0.0"]
    state: Literal["PUBLISHED"]
    published_at: datetime
    contract_json: Annotated[str, Field(min_length=1, max_length=1_000_000)]
    contract_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    published_fair_values: PublishedFairValues

    @field_validator("published_at")
    @classmethod
    def publication_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Publication time must include a timezone")
        if value > datetime.now(UTC):
            raise ValueError("Publication time cannot be in the future")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def verify_frozen_payload(self) -> FinancialModelPublicationV1:
        digest = hashlib.sha256(self.contract_json.encode("utf-8")).hexdigest()
        if digest != self.contract_sha256:
            raise ValueError("Published contract hash mismatch")
        return self


def reconcile_publication(
    publication: FinancialModelPublicationV1, preview: dict[str, object]
) -> dict[str, object]:
    """Gate the existing preview and acceptance path on published fair-value parity."""
    result = dict(preview)
    calculated = preview.get("calculated_outputs")
    if not isinstance(calculated, dict):
        if preview.get("status") == "READY":
            result["status"] = "INVALID"
            result["reason"] = "Native candidate outputs are unavailable for publication parity"
        return result
    differences = []
    for field, published in publication.published_fair_values.model_dump().items():
        native = calculated.get(field)
        if native is None or abs(Decimal(str(native)) - published) > PARITY_TOLERANCE:
            differences.append(field)
    result["publication"] = {
        "contract_sha256": publication.contract_sha256,
        "published_at": publication.published_at.isoformat(),
        "parity_status": "MISMATCH" if differences else "MATCH",
        "mismatched_fields": differences,
        "absolute_tolerance": str(PARITY_TOLERANCE),
    }
    if differences:
        result["status"] = "INVALID"
        result["reason"] = "Published fair values do not reconcile with native calculation"
    return result


if __name__ == "__main__":
    import json

    print(json.dumps(FinancialModelPublicationV1.model_json_schema(), indent=2, sort_keys=True))
