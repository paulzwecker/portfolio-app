"""Historical receipt evidence must not claim unverified session coverage."""

from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.orm import Session

from portfolio_api.domain.models import MarketDataBootstrapCheckpoint, MarketDataBootstrapRun
from portfolio_api.market_data_bootstrap import (
    _coverage_for_plan,
    _history_window_evidence,
    _quarantine_temporal_plan,
    _run_report,
)


def stamp(day: int) -> datetime:
    return datetime(2026, 10, day, tzinfo=UTC)


def test_listing_span_counts_distinct_daily_dates_not_quotes() -> None:
    checkpoint = MarketDataBootstrapCheckpoint(subject_kind="LISTING")
    plan = {
        "prices": [
            {"price_kind": "DAILY_CLOSE", "market_date": stamp(5)},
            {"price_kind": "DAILY_CLOSE", "market_date": stamp(2)},
            {"price_kind": "DAILY_CLOSE", "market_date": stamp(2)},
            {"price_kind": "CURRENT_QUOTE", "market_date": stamp(6)},
        ],
        "report": {"daily_price_rows": 3},
    }
    evidence = _coverage_for_plan(checkpoint, plan)["history_window_evidence"]
    assert evidence == {
        "coverage_assessment": "NOT_ASSESSED",
        "assessment_reason": "EXPECTED_SESSIONS_NOT_EVALUATED",
        "observation_dates_known": True,
        "distinct_observed_dates": 2,
        "first_observed_date": "2026-10-02",
        "last_observed_date": "2026-10-05",
        "maximum_calendar_spacing_days": 3,
    }
    # Three calendar days include a weekend; they are not labeled missing sessions.
    assert _coverage_for_plan(checkpoint, plan)["price_status"] == "AVAILABLE"


def test_fx_span_excludes_current_quote_even_when_mixed_with_daily_rows() -> None:
    checkpoint = MarketDataBootstrapCheckpoint(subject_kind="FX_PAIR")
    plan = {
        "fx": [
            {"source_ref": "current", "effective_at": stamp(6)},
            {"source_ref": "daily", "effective_at": stamp(2)},
        ],
        "report": {"current_quote_source_refs": ["current"]},
    }
    evidence = _history_window_evidence(checkpoint, plan)
    assert evidence["distinct_observed_dates"] == 1
    assert evidence["first_observed_date"] == evidence["last_observed_date"] == "2026-10-02"
    assert evidence["maximum_calendar_spacing_days"] is None
    assert evidence["coverage_assessment"] == "NOT_ASSESSED"


def test_single_listing_observation_does_not_certify_a_long_window() -> None:
    checkpoint = MarketDataBootstrapCheckpoint(subject_kind="LISTING")
    plan = {
        "prices": [{"price_kind": "DAILY_CLOSE", "market_date": stamp(2)}],
        "report": {"daily_price_rows": 1},
    }
    coverage = _coverage_for_plan(checkpoint, plan)
    assert coverage["price_status"] == "AVAILABLE"
    assert coverage["history_window_evidence"]["coverage_assessment"] == "NOT_ASSESSED"
    assert coverage["history_window_evidence"]["distinct_observed_dates"] == 1


def test_missing_plan_differs_from_successfully_returned_empty_plan() -> None:
    checkpoint = MarketDataBootstrapCheckpoint(subject_kind="LISTING")
    missing = _history_window_evidence(checkpoint, None)
    empty = _history_window_evidence(checkpoint, {"prices": [], "report": {}})
    assert missing["observation_dates_known"] is False
    assert missing["distinct_observed_dates"] is None
    assert empty["observation_dates_known"] is True
    assert empty["distinct_observed_dates"] == 0
    assert missing["coverage_assessment"] == empty["coverage_assessment"] == "NOT_ASSESSED"


def test_quarantined_rows_do_not_report_stale_normalizer_dates() -> None:
    checkpoint = MarketDataBootstrapCheckpoint(subject_kind="LISTING")
    plan = {
        "prices": [{"price_kind": "DAILY_CLOSE", "market_date": stamp(2)}],
        "actions": [],
        "fx": [],
        "batch": {},
        "report": {
            "daily_price_rows": 1,
            "mapped_listings": [
                {"earliest_history_date": "2026-10-02", "latest_history_date": "2026-10-05"}
            ],
        },
    }
    _quarantine_temporal_plan(plan, [{"code": "PRICE_OUTSIDE_REQUESTED_WINDOW"}])
    coverage = _coverage_for_plan(checkpoint, plan)
    assert coverage["price_status"] == "UNAVAILABLE"
    assert coverage["earliest_effective_date"] is None
    assert coverage["latest_effective_date"] is None
    assert coverage["history_window_evidence"]["distinct_observed_dates"] == 0


def test_legacy_checkpoint_does_not_gain_invented_coverage_evidence() -> None:
    checkpoint = MarketDataBootstrapCheckpoint(
        subject_kind="LISTING",
        status="COMPLETE",
        retryable=False,
        attempt_count=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        report={"coverage": {"price_status": "AVAILABLE"}},
    )
    run = MarketDataBootstrapRun(
        id=uuid4(),
        input_digest="a" * 64,
        provider_id="SYNTHETIC",
        provider_schema_version="fixture",
        crosswalk_sha256="b" * 64,
        target_environment="development",
        start_date=checkpoint.start_date,
        end_date=checkpoint.end_date,
    )

    class ReadOnlySession:
        def scalars(self, statement: Any) -> list[MarketDataBootstrapCheckpoint]:
            return [checkpoint]

    report = _run_report(cast(Session, ReadOnlySession()), run)
    assert report["status"] == "COMPLETE"
    assert report["history_window_coverage"] == "NOT_ASSESSED"
    evidence = report["listing_coverage"][0]["history_window_evidence"]
    assert evidence["assessment_reason"] == "EVIDENCE_NOT_RECORDED"
    assert evidence["distinct_observed_dates"] is None
    checkpoint.report = {
        "coverage": {
            "price_status": "AVAILABLE",
            "history_window_evidence": {"coverage_assessment": "COMPLETE"},
        }
    }
    untrusted = _run_report(cast(Session, ReadOnlySession()), run)
    assert (
        untrusted["listing_coverage"][0]["history_window_evidence"]["coverage_assessment"]
        == "NOT_ASSESSED"
    )
