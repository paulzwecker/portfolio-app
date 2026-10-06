from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import queries
from portfolio_api.domain.models import (
    ExecutionPace,
    ExecutionPaceDecision,
    ExecutionPaceDecisionStatus,
    ExecutionPaceRun,
    FinancialModelRevision,
    LifecycleEvent,
    TargetRevision,
)
from portfolio_api.domain.schemas import ExecutionPaceInputSnapshot, ExecutionPaceRunCreate
from portfolio_api.domain.seed import seed
from portfolio_api.execution_pace import (
    create_execution_pace_run,
    derive_execution_pace,
    normalize_price_regime,
    valuation_zone,
)

AS_OF = datetime(2026, 10, 5, 20, 0, tzinfo=UTC)
LISTING_ID = uuid4()
PRICE_ID = uuid4()
TARGET_ID = uuid4()
HOLDING_ID = uuid4()
MODEL_ID = uuid4()


def inputs(**overrides: object) -> ExecutionPaceInputSnapshot:
    values: dict[str, object] = {
        "context_version": "execution-pace-inputs-v1",
        "lifecycle": "PORTFOLIO",
        "target_revision_id": TARGET_ID,
        "target_effective_at": AS_OF,
        "holding_snapshot_id": HOLDING_ID,
        "holding_effective_at": AS_OF,
        "allocation_status": "VALUED",
        "current_weight": "0.01",
        "target_weight": "0.05",
        "allocation_gap": "0.04",
        "model_source_kind": "IMPORTED_CURRENT_CONTRACT",
        "model_source_id": MODEL_ID,
        "model_revision_id": None,
        "model_output_snapshot_id": MODEL_ID,
        "model_key": "P-TEST",
        "return_semantics": "LEGACY_NORMALIZED_FIELD",
        "model_effective_at": AS_OF,
        "model_recorded_at": AS_OF,
        "model_currency": "USD",
        "model_output_quality": "COMPLETE",
        "model_contract_status": "PASS",
        "model_review_flag": "PASS",
        "expected_irr": "0.20",
        "hurdle": "0.09",
        "valuation_listing_id": LISTING_ID,
        "valuation_ticker": "TEST",
        "valuation_venue": "NYSE",
        "valuation_currency": "USD",
        "price_observation_id": PRICE_ID,
        "price_market_date": AS_OF,
        "price_recorded_at": AS_OF,
        "price_currency": "USD",
        "price": "100",
        "price_provider": "YAHOO_FINANCE",
        "price_quality": "PASS",
        "price_freshness": "FRESH",
        "model_price_status": "AVAILABLE",
        "model_price_effective_at": AS_OF,
        "model_price_observation_id": PRICE_ID,
        "model_reference_price": "100",
        "model_price_currency": "USD",
        "weighted_fair_value": "130",
        "weighted_upside": "0.30",
        "valuation_zone": "DEEP_DISCOUNT",
        "valuation_range_ratio": "0.90",
        "estimate_momentum_availability": "AVAILABLE",
        "estimate_momentum_direction": "POSITIVE",
        "estimate_momentum_freshness": "FRESH",
        "estimate_momentum_quality": "PASS",
        "estimate_provider_id": "primary_estimates",
        "estimate_latest_snapshot_date": date(2026, 10, 5),
        "estimate_momentum_reason": None,
        "price_regime_source_ref": "price-regime:test",
        "price_regime_as_of": AS_OF,
        "price_regime_quality": "PASS",
        "price_regime_raw": "DEEP CORRECTION",
        "price_regime": "DEEP CORR",
        "price_regime_freshness": "FRESH",
        "context_notes": [],
    }
    values.update(overrides)
    return ExecutionPaceInputSnapshot.model_validate(values)


@pytest.mark.parametrize(
    ("snapshot", "pace"),
    [
        (
            inputs(expected_irr="0.199621383", weighted_upside="0.30", price_regime="CORRECTION"),
            ExecutionPace.ACCELERATE,
        ),  # Portfolio!K6 DLO
        (
            inputs(
                expected_irr="0.1159957498",
                estimate_momentum_direction="NEGATIVE",
                weighted_upside="0.30",
                price_regime="DEEP CORR",
            ),
            ExecutionPace.SMALL_LADDER,
        ),  # Portfolio!K11 SPGI
        (
            inputs(
                expected_irr="0.11736",
                weighted_upside="0.20",
                valuation_zone="DISCOUNT",
                price_regime="UPTREND",
            ),
            ExecutionPace.NORMAL_BUILD,
        ),  # Portfolio!K14 TSM
        (
            inputs(
                expected_irr="0.0953990085",
                weighted_upside="0",
                valuation_zone="NEAR_FAIR",
                price_regime="PULLBACK",
            ),
            ExecutionPace.WAIT_LIMIT,
        ),  # Portfolio!K15 MA
        (
            inputs(
                target_weight="0",
                allocation_gap="-0.01443437692",
                expected_irr="0.1630002206",
                weighted_upside="0.30",
                valuation_zone="DEEP_DISCOUNT",
                price_regime="CORRECTION",
            ),
            ExecutionPace.PATIENT_EXIT,
        ),  # Portfolio!K21 NVO
    ],
)
def test_execution_pace_matches_representative_workbook_outputs(
    snapshot: ExecutionPaceInputSnapshot, pace: ExecutionPace
) -> None:
    result = derive_execution_pace(snapshot)
    assert result.status == ExecutionPaceDecisionStatus.AVAILABLE
    assert result.pace == pace


def test_legacy_thresholds_and_regime_mapping_are_explicit() -> None:
    assert valuation_zone(Decimal("0.25")) == "DEEP_DISCOUNT"
    assert valuation_zone(Decimal("0.10")) == "DISCOUNT"
    assert valuation_zone(Decimal("-0.10")) == "NEAR_FAIR"
    assert valuation_zone(Decimal("-0.25")) == "RICH"
    assert valuation_zone(Decimal("-0.25001")) == "VERY_RICH"
    assert normalize_price_regime("RECOVERING FROM DEEP CORRECTION", None) == "DEEP RECOVERY"
    assert normalize_price_regime("HEALTHY UPTREND", None) == "UPTREND"
    assert normalize_price_regime("UNMAPPED SOURCE LABEL", None) is None


def test_hold_band_and_positive_target_trims_follow_workbook_branches() -> None:
    hold = derive_execution_pace(inputs(allocation_gap="0.002999"))
    assert hold.pace == ExecutionPace.HOLD

    patient = derive_execution_pace(
        inputs(
            current_weight="0.08",
            target_weight="0.05",
            allocation_gap="-0.03",
            weighted_upside="0.30",
            price_regime="CORRECTION",
        )
    )
    assert patient.pace == ExecutionPace.PATIENT_TRIM

    faster = derive_execution_pace(
        inputs(
            current_weight="0.08",
            target_weight="0.05",
            allocation_gap="-0.03",
            weighted_upside="-0.30",
            valuation_zone="VERY_RICH",
            price_regime="EXTENDED",
        )
    )
    assert faster.pace == ExecutionPace.TRIM_FASTER


@pytest.mark.parametrize(
    "overrides",
    [
        {"estimate_momentum_availability": "INSUFFICIENT_HISTORY"},
        {"estimate_momentum_freshness": "STALE"},
        {"price_freshness": "STALE"},
        {"price_regime_freshness": "STALE"},
        {"price_regime_quality": "DATA_CHECK"},
        {"model_price_status": "STALE"},
        {"allocation_status": "FX_UNAVAILABLE"},
        {"model_review_flag": "REASSESSMENT REQUIRED"},
        {"model_currency": "EUR"},
    ],
)
def test_missing_or_stale_critical_input_requires_review(overrides: dict[str, object]) -> None:
    result = derive_execution_pace(inputs(**overrides))
    assert result.status == ExecutionPaceDecisionStatus.REVIEW
    assert result.pace is None


def test_unavailable_estimates_are_not_treated_as_collecting_or_neutral() -> None:
    no_history = inputs(
        estimate_momentum_availability="INSUFFICIENT_HISTORY",
        estimate_momentum_direction=None,
        estimate_momentum_quality="NO_DATA",
        estimate_momentum_freshness="NO_DATA",
    )
    result = derive_execution_pace(no_history)
    assert result.status == ExecutionPaceDecisionStatus.REVIEW
    assert "no usable point-in-time history" in result.reason


def test_low_confidence_observed_momentum_uses_documented_collecting_state() -> None:
    result = derive_execution_pace(
        inputs(
            estimate_momentum_availability="DIRECTION_ONLY",
            estimate_momentum_direction="NEGATIVE",
            expected_irr="0.14",
        )
    )
    assert result.pace == ExecutionPace.BUILD


def test_return_below_hurdle_prevents_faster_underweight_buying() -> None:
    result = derive_execution_pace(inputs(expected_irr="0.08", hurdle="0.09"))
    assert result.pace == ExecutionPace.WAIT_LIMIT


def test_momentum_is_required_only_when_the_selected_legacy_branch_consumes_it() -> None:
    missing_momentum = {
        "estimate_momentum_availability": "INSUFFICIENT_HISTORY",
        "estimate_momentum_direction": None,
        "estimate_momentum_freshness": "NO_DATA",
        "estimate_momentum_quality": "NO_DATA",
    }
    patient_trim = derive_execution_pace(
        inputs(
            current_weight="0.08",
            target_weight="0.05",
            allocation_gap="-0.03",
            **missing_momentum,
        )
    )
    assert patient_trim.pace == ExecutionPace.PATIENT_TRIM

    normal_exit = derive_execution_pace(
        inputs(
            target_weight="0",
            allocation_gap="-0.05",
            price_regime="SIDEWAYS",
            valuation_zone="NEAR_FAIR",
            weighted_upside="0",
            **missing_momentum,
        )
    )
    assert normal_exit.pace == ExecutionPace.NORMAL_EXIT

    unknown_faster_exit = derive_execution_pace(
        inputs(
            target_weight="0",
            allocation_gap="-0.05",
            price_regime="EXTENDED",
            valuation_zone="NEAR_FAIR",
            weighted_upside="0",
            **missing_momentum,
        )
    )
    assert unknown_faster_exit.status == ExecutionPaceDecisionStatus.REVIEW
    assert unknown_faster_exit.pace is None


def test_recorded_run_keeps_review_states_and_does_not_mutate_targets_or_models(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        portfolio_id = seed(db)
        as_of = datetime.now(UTC)
        before = queries.overview(db, portfolio_id, as_of)
        assert before.snapshot is not None
        assert before.target_revision is not None
        target_revision_id = before.target_revision.id
        holding_snapshot_id = before.snapshot.id
        target_weights = {row.company.id: row.target_weight for row in before.companies}
        lifecycle_count = db.scalar(select(func.count()).select_from(LifecycleEvent))
        target_revision_count = db.scalar(select(func.count()).select_from(TargetRevision))
        model_revision_count = db.scalar(select(func.count()).select_from(FinancialModelRevision))

        run = create_execution_pace_run(
            db,
            ExecutionPaceRunCreate(
                actor="LOCAL_USER",
                reason="Verify execution decision ownership boundaries.",
                source="test_execution_pace",
                as_of=as_of,
            ),
        )
        decisions = list(
            db.scalars(select(ExecutionPaceDecision).where(ExecutionPaceDecision.run_id == run.id))
        )
        after = queries.overview(db, portfolio_id, as_of)

        assert run.status in {"PARTIAL", "UNAVAILABLE"}
        assert decisions
        assert all(
            decision.decision_status in {"REVIEW", "NOT_APPLICABLE"} and decision.pace is None
            for decision in decisions
        )
        assert after.target_revision is not None
        assert after.snapshot is not None
        assert after.target_revision.id == target_revision_id
        assert after.snapshot.id == holding_snapshot_id
        assert {row.company.id: row.target_weight for row in after.companies} == target_weights
        assert db.scalar(select(func.count()).select_from(LifecycleEvent)) == lifecycle_count
        assert db.scalar(select(func.count()).select_from(TargetRevision)) == target_revision_count
        assert (
            db.scalar(select(func.count()).select_from(FinancialModelRevision))
            == model_revision_count
        )
        assert db.scalar(select(func.count()).select_from(ExecutionPaceRun)) == 1
