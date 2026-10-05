from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from portfolio_api.domain.models import ScoreAssessmentStatus
from portfolio_api.domain.schemas import (
    AllocationInput,
    CashInput,
    PositionInput,
    ScoreAssessmentCreate,
    SnapshotCreate,
    TargetCreate,
)


def audit() -> dict[str, str]:
    return {
        "actor": "LOCAL_USER",
        "reason": "Observed",
        "effective_at": datetime.now(UTC).isoformat(),
    }


@pytest.mark.parametrize("weight", ["-0.01", "1.0001", 0.1, "NaN", "Infinity"])
def test_invalid_or_floating_target_weight_rejected(weight: object) -> None:
    with pytest.raises(ValidationError):
        AllocationInput.model_validate({"company_id": uuid4(), "weight": weight})


def test_exact_weight_residual_and_explicit_zero() -> None:
    zero = AllocationInput(company_id=uuid4(), weight=Decimal(0))
    revision = TargetCreate.model_validate(
        {**audit(), "allocations": [zero.model_dump(), {"company_id": uuid4(), "weight": "0.3"}]}
    )
    assert sum(a.weight for a in revision.allocations) == Decimal("0.3")
    assert revision.allocations[0].weight == 0


@pytest.mark.parametrize("value", ["0E-12", "1E-12", "0.350000000000"])
def test_decimal_response_uses_exact_fixed_notation(value: str) -> None:
    allocation = AllocationInput(company_id=uuid4(), weight=Decimal(value))
    result = allocation.model_dump(mode="json")["weight"]
    assert result == format(Decimal(value), "f")
    assert Decimal(result) == Decimal(value)


def test_target_total_and_duplicate_companies_rejected() -> None:
    identifier = uuid4()
    for allocations in [
        [{"company_id": identifier, "weight": "0.6"}, {"company_id": uuid4(), "weight": "0.5"}],
        [{"company_id": identifier, "weight": "0"}, {"company_id": identifier, "weight": "0"}],
    ]:
        with pytest.raises(ValidationError):
            TargetCreate.model_validate({**audit(), "allocations": allocations})


def test_observed_zero_and_unknown_quantity_distinct() -> None:
    listing = uuid4()
    zero = PositionInput(listing_id=listing, quantity=Decimal(0))
    unknown = PositionInput(listing_id=listing, quantity=None)
    assert zero.model_dump(mode="json")["quantity"] == "0"
    assert unknown.model_dump(mode="json")["quantity"] is None
    SnapshotCreate.model_validate(
        {**audit(), "completeness": "PARTIAL", "positions": [unknown.model_dump()]}
    )
    with pytest.raises(ValidationError):
        SnapshotCreate.model_validate(
            {**audit(), "completeness": "COMPLETE", "positions": [unknown.model_dump()]}
        )


def test_complete_empty_differs_from_unavailable() -> None:
    empty = SnapshotCreate.model_validate({**audit(), "completeness": "COMPLETE", "positions": []})
    missing = SnapshotCreate.model_validate(
        {**audit(), "completeness": "UNAVAILABLE", "positions": []}
    )
    assert empty.completeness != missing.completeness


@pytest.mark.parametrize("quantity", ["-1", 1.5, "0.00000000001"])
def test_short_float_and_unrepresentable_quantities_rejected(quantity: object) -> None:
    with pytest.raises(ValidationError):
        PositionInput.model_validate({"listing_id": uuid4(), "quantity": quantity})


def test_unknown_cash_currency_not_allowed() -> None:
    with pytest.raises(ValidationError):
        CashInput.model_validate({"currency": None, "balance": "0"})


def test_score_precision_range_direction_and_null_status_contract() -> None:
    base = {
        "dimension": "DURABILITY_10Y",
        "score": "0.00",
        "status": "ASSESSED",
        "effective_at": datetime.now(UTC).isoformat(),
        "rationale": "Explicit observed zero.",
        "actor": "LOCAL_USER",
    }
    observed_zero = ScoreAssessmentCreate.model_validate(base)
    assert observed_zero.score == 0
    assert observed_zero.model_dump(mode="json")["score"] == "0.00"
    precise = ScoreAssessmentCreate.model_validate(
        {**base, "score": "4.3725", "rationale": "Workbook precision is preserved."}
    )
    assert precise.score == Decimal("4.3725")
    assert precise.model_dump(mode="json")["score"] == "4.3725"
    missing = ScoreAssessmentCreate.model_validate(
        {**base, "score": None, "status": "MISSING", "rationale": "Not recorded."}
    )
    assert missing.score is None
    assert missing.status == ScoreAssessmentStatus.MISSING
    for score in ["-0.0001", "5.0001", "1.00001", 0.5, "NaN", "Infinity"]:
        with pytest.raises(ValidationError):
            ScoreAssessmentCreate.model_validate({**base, "score": score})
    for score, status in [(None, "ASSESSED"), ("0", "MISSING")]:
        with pytest.raises(ValidationError):
            ScoreAssessmentCreate.model_validate({**base, "score": score, "status": status})


def test_naive_and_future_timestamp_rejected() -> None:
    for timestamp in ["2026-01-01T00:00:00", "2100-01-01T00:00:00Z"]:
        with pytest.raises(ValidationError):
            TargetCreate.model_validate({**audit(), "effective_at": timestamp, "allocations": []})
