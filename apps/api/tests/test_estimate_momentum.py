from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateBatch,
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
)
from portfolio_api.domain.queries import company_estimate_momentum
from portfolio_api.domain.schemas import CompanyEstimateMomentumRead
from portfolio_api.estimate_momentum import (
    EXPECTED_COMPONENTS,
    ConsensusObservationPoint,
    calculate_estimate_momentum,
)

AS_OF = date(2026, 10, 5)
KNOWN_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)
MAPPING_ID = uuid4()
COMPANY_ID = uuid4()


def point(
    metric: str,
    period_end: date,
    value: str,
    snapshot_date: date,
    *,
    analyst_count: int | None = None,
    provider_id: str = "primary_estimates",
    mapping_id: UUID = MAPPING_ID,
    quality: str = "PASS",
    observed_at: datetime | None = None,
    currency: str | None = "USD",
    unit: str | None = None,
) -> ConsensusObservationPoint:
    observed = observed_at or datetime.combine(snapshot_date, datetime.min.time(), UTC)
    return ConsensusObservationPoint(
        id=uuid4(),
        provider_mapping_id=mapping_id,
        provider_id=provider_id,
        metric=metric,
        period_type="ANNUAL",
        forecast_period=str(period_end.year),
        period_end=period_end,
        value=Decimal(value),
        analyst_count=analyst_count,
        currency=currency,
        unit=unit or ("CURRENCY" if metric == "REVENUE" else "CURRENCY_PER_SHARE"),
        snapshot_date=snapshot_date,
        observed_at=observed,
        recorded_at=observed,
        data_quality=quality,
        quality_reason="Source currency needs review" if quality != "PASS" else None,
    )


def calculate(
    observations: list[ConsensusObservationPoint],
) -> CompanyEstimateMomentumRead:
    return calculate_estimate_momentum(
        company_id=COMPANY_ID,
        as_of=AS_OF,
        known_at=KNOWN_AT,
        continuity_status="PRIMARY_SELECTED",
        selected_provider_id="primary_estimates",
        selected_mapping_id=MAPPING_ID,
        observations=observations,
    )


def complete_observations(
    *,
    current_date: date = AS_OF,
    one_metric_only: bool = False,
) -> list[ConsensusObservationPoint]:
    result: list[ConsensusObservationPoint] = []
    dates = [date(2025, 10, 5), date(2026, 4, 5), date(2026, 7, 5), current_date]
    for metric, periods in (
        ("REVENUE", [date(2027, 12, 31), date(2028, 12, 31)]),
        ("EPS", [date(2027, 12, 31), date(2028, 12, 31)]),
    ):
        if one_metric_only and metric == "EPS":
            continue
        for period_end in periods:
            for snapshot in dates:
                result.append(
                    point(
                        metric,
                        period_end,
                        "110" if snapshot == current_date else "100",
                        snapshot,
                    )
                )
    return result


def test_legacy_formula_direction_revision_weights_and_coverage_reconcile() -> None:
    signal = calculate(complete_observations())

    assert signal.availability == "AVAILABLE"
    assert signal.direction == "POSITIVE"
    assert signal.raw_score == Decimal(2)
    assert signal.confidence_adjusted_score == Decimal(2)
    assert signal.coverage_count == 12
    assert signal.coverage_total == EXPECTED_COMPONENTS == 20
    assert signal.coverage_fraction == Decimal("0.6")
    assert signal.confidence == Decimal(1)
    assert len(signal.periods) == 4
    assert all(
        window.component_score == Decimal(2)
        for period in signal.periods
        for window in period.windows
    )


def test_analyst_coverage_is_independent_of_history_coverage_confidence() -> None:
    observations = complete_observations()
    observations[-1] = point(
        "EPS",
        date(2028, 12, 31),
        "12",
        AS_OF,
        analyst_count=17,
    )

    signal = calculate(observations)
    eps_fy2 = next(
        period for period in signal.periods if period.metric == "EPS" and period.horizon == "FY+2"
    )

    assert eps_fy2.analyst_count == 17
    assert signal.coverage_count == 12
    assert signal.confidence == Decimal("1")


def test_googl_legacy_formula_fixture_reconciles_supported_revision_components() -> None:
    # These cutoffs exercise the legacy formula arithmetic only. The source's
    # approximate crawl dates are not asserted as authoritative point-in-time dates.
    six_months = date(2026, 4, 5)
    three_months = date(2026, 7, 5)
    fixture_rows = [
        ("REVENUE", date(2027, 12, 31), "498.1", "407.2", None),
        ("REVENUE", date(2028, 12, 31), "609.9", "473.53", None),
        ("EPS", date(2027, 12, 31), "20.6", "11.49", "14.24"),
        ("EPS", date(2028, 12, 31), "14.85", "13.31", "14.45"),
    ]
    observations: list[ConsensusObservationPoint] = []
    for metric, period_end, current, six_month_value, three_month_value in fixture_rows:
        observations.extend(
            [
                point(metric, period_end, six_month_value, six_months),
                point(metric, period_end, current, AS_OF),
            ]
        )
        if three_month_value is not None:
            observations.append(point(metric, period_end, three_month_value, three_months))

    signal = calculate(observations)

    assert signal.direction == "POSITIVE"
    assert signal.coverage_count == 6
    assert signal.confidence == Decimal("0.6")
    assert signal.raw_score is not None
    assert signal.confidence_adjusted_score is not None
    assert abs(signal.raw_score - Decimal("1.925615422639644092931290163")) < Decimal(
        "0.000000000000000000000000001"
    )
    assert abs(
        signal.confidence_adjusted_score - Decimal("1.155369253583786455758774098")
    ) < Decimal("0.000000000000000000000000001")


def test_sparse_history_keeps_direction_only_and_never_substitutes_neutral() -> None:
    observations = [
        point("REVENUE", date(2027, 12, 31), "100", date(2026, 7, 5)),
        point("REVENUE", date(2027, 12, 31), "110", AS_OF),
    ]

    signal = calculate(observations)

    assert signal.availability == "DIRECTION_ONLY"
    assert signal.direction == "POSITIVE"
    assert signal.raw_score == Decimal(2)
    assert signal.confidence == Decimal("0.1")
    assert signal.confidence_band == "COLLECTING"
    assert signal.coverage_count == 1


def test_missing_history_has_no_zero_or_neutral_score() -> None:
    signal = calculate(
        [
            point("REVENUE", date(2027, 12, 31), "100", AS_OF),
            point("EPS", date(2027, 12, 31), "2", AS_OF),
        ]
    )

    assert signal.availability == "INSUFFICIENT_HISTORY"
    assert signal.direction is None
    assert signal.raw_score is None
    assert signal.confidence_adjusted_score is None
    assert signal.coverage_count == 0
    assert signal.reason and "not treated as neutral" in signal.reason
    assert all(
        window.status == "MISSING_REFERENCE"
        for period in signal.periods
        for window in period.windows
    )


def test_provider_change_does_not_join_old_source_history() -> None:
    old_mapping = uuid4()
    observations = complete_observations(one_metric_only=True)
    observations = [
        point(
            item.metric,
            item.period_end or date(2027, 12, 31),
            str(item.value),
            item.snapshot_date,
            provider_id="old_provider",
            mapping_id=old_mapping,
        )
        for item in observations
    ]
    observations.extend(
        [
            point("REVENUE", date(2027, 12, 31), "110", AS_OF),
        ]
    )

    signal = calculate(observations)

    assert signal.provider_id == "primary_estimates"
    assert signal.availability == "INSUFFICIENT_HISTORY"
    assert signal.direction is None
    assert signal.coverage_count == 0


def test_stale_current_estimate_is_computed_but_freshness_stays_stale() -> None:
    stale_current = date(2026, 9, 10)
    signal = calculate(complete_observations(current_date=stale_current))

    assert signal.availability == "AVAILABLE"
    assert signal.freshness == "STALE"
    assert signal.latest_snapshot_date == stale_current
    assert signal.raw_score == Decimal(2)


def test_absent_second_forecast_period_stays_missing_and_reduces_coverage() -> None:
    observations = [
        item
        for item in complete_observations(one_metric_only=True)
        if item.period_end == date(2027, 12, 31)
    ]

    signal = calculate(observations)

    assert [(period.metric, period.horizon) for period in signal.periods] == [("REVENUE", "FY+1")]
    assert signal.coverage_count == 3
    assert signal.confidence == Decimal("0.3")
    assert signal.direction == "POSITIVE"
    assert signal.availability == "DIRECTION_ONLY"


def test_stale_reference_and_invalid_percentage_baseline_are_not_scored() -> None:
    stale_anchor = point("REVENUE", date(2027, 12, 31), "100", date(2025, 9, 1))
    current = point("REVENUE", date(2027, 12, 31), "110", AS_OF)
    stale = calculate([stale_anchor, current])
    assert stale.coverage_count == 0
    assert stale.periods[0].windows[0].status == "STALE_REFERENCE"

    zero_anchor = point("REVENUE", date(2027, 12, 31), "0", date(2026, 7, 5))
    invalid = calculate([zero_anchor, current])
    assert invalid.coverage_count == 0
    assert invalid.periods[0].windows[2].status == "INVALID_BASELINE"
    assert invalid.direction is None


def test_non_pass_provider_rows_remain_data_check_and_are_not_used() -> None:
    observations = [
        point(
            "REVENUE",
            date(2027, 12, 31),
            "100",
            date(2026, 7, 5),
            quality="DATA_CHECK",
        ),
        point("REVENUE", date(2027, 12, 31), "110", AS_OF),
    ]

    signal = calculate(observations)

    assert signal.data_quality == "DATA_CHECK"
    assert signal.coverage_count == 0
    assert signal.direction is None
    assert signal.periods[0].windows[2].status == "DATA_CHECK"


def test_invalid_observation_quality_is_not_downgraded_to_data_check() -> None:
    signal = calculate(
        [
            point(
                "REVENUE",
                date(2027, 12, 31),
                "110",
                AS_OF,
                quality="INVALID",
            )
        ]
    )

    assert signal.data_quality == "INVALID"
    assert signal.freshness == "DATA_CHECK"
    assert signal.availability == "INSUFFICIENT_HISTORY"
    assert signal.direction is None


def test_as_of_and_known_at_exclude_later_observations() -> None:
    observations = complete_observations()
    observations.append(
        point(
            "REVENUE",
            date(2027, 12, 31),
            "150",
            date(2026, 10, 5),
            observed_at=datetime(2026, 10, 5, 18, tzinfo=UTC),
        )
    )
    signal = calculate(observations)

    assert signal.periods[0].current_value == Decimal(110)
    assert signal.raw_score == Decimal(2)


def test_historical_anchor_observed_after_its_reference_cutoff_is_excluded() -> None:
    anchor_date = date(2026, 7, 5)
    observations = [
        point(
            "REVENUE",
            date(2027, 12, 31),
            "100",
            anchor_date,
            observed_at=datetime(2026, 7, 6, 8, tzinfo=UTC),
        ),
        point("REVENUE", date(2027, 12, 31), "110", AS_OF),
    ]

    signal = calculate(observations)

    assert signal.coverage_count == 0
    assert signal.direction is None
    assert signal.periods[0].windows[2].status == "MISSING_REFERENCE"


def test_company_query_uses_point_in_time_source_mapping_without_provider_blending(
    postgres_engine: Engine,
) -> None:
    company_id = uuid4()
    old_mapping_id = uuid4()
    new_mapping_id = uuid4()
    old_effective = datetime(2025, 1, 1, tzinfo=UTC)
    new_effective = datetime(2026, 9, 1, tzinfo=UTC)
    prior_dates = [date(2025, 10, 5), date(2026, 4, 5), date(2026, 7, 5)]
    with Session(postgres_engine) as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Estimate momentum history test",
                reporting_currency="USD",
                is_demo=False,
            )
        )
        old_mapping = ConsensusEstimateProviderMapping(
            id=old_mapping_id,
            company_id=company_id,
            listing_id=None,
            provider_id="old_estimates",
            provider_symbol="OLD",
            role="PRIMARY",
            priority=10,
            currency="USD",
            evidence_source="https://example.test/old-identity",
            currency_evidence_source="https://example.test/old-currency",
            effective_from=old_effective,
            recorded_at=old_effective,
            actor="LOCAL_USER",
        )
        new_mapping = ConsensusEstimateProviderMapping(
            id=new_mapping_id,
            company_id=company_id,
            listing_id=None,
            provider_id="new_estimates",
            provider_symbol="NEW",
            role="PRIMARY",
            priority=10,
            currency="USD",
            evidence_source="https://example.test/new-identity",
            currency_evidence_source="https://example.test/new-currency",
            effective_from=new_effective,
            recorded_at=new_effective,
            actor="LOCAL_USER",
        )
        session.add_all([old_mapping, new_mapping])
        session.flush()
        for index, snapshot_date in enumerate(prior_dates + [date(2026, 8, 1)]):
            observed_at = datetime.combine(snapshot_date, datetime.min.time(), UTC)
            batch = _momentum_batch(f"old-{index}", "old_estimates", observed_at)
            session.add(batch)
            session.flush()
            session.add(
                _momentum_observation(
                    company_id,
                    old_mapping_id,
                    batch.id,
                    "110" if snapshot_date == date(2026, 8, 1) else "100",
                    snapshot_date,
                    observed_at,
                    provider="old_estimates",
                    record=f"old:{index}",
                )
            )
        new_observed = datetime(2026, 10, 5, 10, tzinfo=UTC)
        new_batch = _momentum_batch("new-0", "new_estimates", new_observed)
        session.add(new_batch)
        session.flush()
        session.add(
            _momentum_observation(
                company_id,
                new_mapping_id,
                new_batch.id,
                "150",
                date(2026, 10, 5),
                new_observed,
                provider="new_estimates",
                record="new:0",
            )
        )
        session.flush()

        current = company_estimate_momentum(session, company_id, as_of=AS_OF)
        historically_known = company_estimate_momentum(
            session,
            company_id,
            as_of=AS_OF,
            known_at=datetime(2026, 8, 31, 23, 59, tzinfo=UTC),
        )

        assert current.provider_id == "new_estimates"
        assert current.availability == "INSUFFICIENT_HISTORY"
        assert current.raw_score is None
        assert historically_known.provider_id == "old_estimates"
        assert historically_known.direction == "POSITIVE"
        assert historically_known.coverage_count == 3
        assert historically_known.freshness == "STALE"


def _momentum_batch(batch_key: str, provider: str, observed_at: datetime) -> ConsensusEstimateBatch:
    from hashlib import sha256

    digest = sha256(batch_key.encode()).hexdigest()
    return ConsensusEstimateBatch(
        id=uuid4(),
        provider_id=provider,
        provider_schema_version="test",
        normalizer_version="test-v1",
        domain="CONSENSUS_ESTIMATES",
        source_kind="PROVIDER_RESPONSE",
        source_digest=digest,
        source_reference="https://example.test/estimates",
        query_scope={"test": batch_key},
        snapshot_date=observed_at.date(),
        observed_at=observed_at,
        recorded_at=observed_at,
        provider_summary={},
        reconciliation={},
    )


def _momentum_observation(
    company_id: UUID,
    mapping_id: UUID,
    batch_id: UUID,
    value: str,
    snapshot_date: date,
    observed_at: datetime,
    *,
    provider: str,
    record: str,
) -> ConsensusEstimateObservation:
    return ConsensusEstimateObservation(
        id=uuid4(),
        company_id=company_id,
        listing_id=None,
        provider_mapping_id=mapping_id,
        batch_id=batch_id,
        provider_id=provider,
        metric="REVENUE",
        period_type="ANNUAL",
        forecast_period="FY2027",
        period_end=date(2027, 12, 31),
        value=Decimal(value),
        low_value=None,
        high_value=None,
        analyst_count=8,
        currency="USD",
        unit="CURRENCY",
        snapshot_date=snapshot_date,
        observed_at=observed_at,
        recorded_at=observed_at,
        source_record_id=record,
        source_ref="https://example.test/estimates",
        revision_context="SNAPSHOT",
        data_quality="PASS",
        quality_reason=None,
        supersedes_observation_id=None,
    )
