"""Historical receipt evidence must not claim unverified session coverage."""

import gzip
import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import _seed_canonical_scope

import portfolio_api.market_data_bootstrap as bootstrap
import portfolio_api.market_sessions as sessions
from portfolio_api.domain import queries
from portfolio_api.domain.models import (
    Listing,
    MarketDataBootstrapCheckpoint,
    MarketDataBootstrapRun,
    PriceObservation,
)
from portfolio_api.market_data_bootstrap import (
    _coverage_for_plan,
    _history_window_evidence,
    _quarantine_temporal_plan,
    _raw_payload_issue,
    _run_report,
)


def test_raw_payload_verification_handles_integrity_and_limits(monkeypatch: Any) -> None:
    content = b"synthetic provider response"
    expected = hashlib.sha256(content).hexdigest()
    assert _raw_payload_issue(gzip.compress(content), "gzip", expected) is None
    assert _raw_payload_issue(content, "identity", expected) is None
    assert _raw_payload_issue(gzip.compress(b"different"), "gzip", expected) == (
        "SOURCE_PAYLOAD_HASH_MISMATCH"
    )
    assert _raw_payload_issue(b"bad gzip", "gzip", expected) == "SOURCE_PAYLOAD_INVALID"
    assert _raw_payload_issue(gzip.compress(content)[:-4], "gzip", expected) == (
        "SOURCE_PAYLOAD_INVALID"
    )
    assert _raw_payload_issue(content, "unknown", expected) == "SOURCE_PAYLOAD_ENCODING_INVALID"
    monkeypatch.setattr(bootstrap, "MAX_RAW_PAYLOAD_VERIFY_BYTES", 64)
    assert (
        _raw_payload_issue(b"x" * 65, "identity", expected) == "SOURCE_PAYLOAD_VERIFICATION_LIMIT"
    )
    assert _raw_payload_issue(gzip.compress(b"x" * 65), "gzip", expected) == (
        "SOURCE_PAYLOAD_VERIFICATION_LIMIT"
    )
    assert _raw_payload_issue(gzip.compress(b"x" * 65), "gzip", expected, max_bytes=32) == (
        "SOURCE_PAYLOAD_VERIFICATION_LIMIT"
    )


@pytest.mark.integration
def test_listing_coverage_describes_sparse_dates_without_claiming_sessions(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)
        listing_id = listing.id
        for index, market_at in enumerate(
            [
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 1, 1, tzinfo=UTC),
            ]
        ):
            session.add(
                PriceObservation(
                    listing_id=listing.id,
                    price_kind="DAILY_CLOSE",
                    market_date=market_at,
                    recorded_at=datetime(2025, 1, 2, tzinfo=UTC),
                    split_adjusted_close=Decimal("100") + index,
                    currency="USD",
                    provider="SYNTHETIC",
                    provider_symbol="SYNTH",
                    adjustment_basis="Synthetic split-adjusted close",
                    data_quality="PASS",
                    source_ref=f"coverage-fixture-{index}-{uuid4()}",
                )
            )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        fetched_listing = session.get(Listing, listing_id)
        assert fetched_listing is not None
        result = queries.listing_market_data(
            session, fetched_listing, known_at=datetime(2025, 1, 3, tzinfo=UTC)
        )
        assert result.analytics.observation_count == 3
        assert result.analytics.distinct_market_dates == 2
        assert result.analytics.first_market_date == date(2024, 1, 1)
        assert result.analytics.max_calendar_gap_days == 366
        assert result.analytics.session_coverage == "NOT_ASSESSED"
        assert result.analytics.input_issues == ["DUPLICATE_MARKET_DATE"]
        assert result.analytics.duplicate_market_dates == [date(2025, 1, 1)]
        assert len(result.analytics.source_streams) == 1
        assert result.analytics.source_streams[0].observation_count == 3
        assert result.analytics.status == "UNAVAILABLE"
        assert result.analytics.daily_return is None
        one_date = queries.listing_market_data(
            session,
            fetched_listing,
            market_as_of=date(2024, 1, 1),
            known_at=datetime(2025, 1, 3, tzinfo=UTC),
        )
        assert one_date.analytics.distinct_market_dates == 1
        assert one_date.analytics.max_calendar_gap_days is None
        no_dates = queries.listing_market_data(
            session,
            fetched_listing,
            market_as_of=date(2023, 12, 31),
            known_at=datetime(2025, 1, 3, tzinfo=UTC),
        )
        assert no_dates.analytics.distinct_market_dates == 0
        assert no_dates.analytics.first_market_date is None
        assert no_dates.analytics.max_calendar_gap_days is None
        assert no_dates.analytics.source_streams == []


@pytest.mark.integration
@pytest.mark.parametrize(
    ("mode", "expected_issue"),
    [
        ("provider", "MULTIPLE_SOURCE_STREAMS"),
        ("symbol", "MULTIPLE_SOURCE_STREAMS"),
        ("currency", "LISTING_CURRENCY_MISMATCH"),
        ("missing_listing_currency", "LISTING_CURRENCY_UNVERIFIED"),
        ("adjustment", "ADJUSTMENT_BASIS_MISMATCH"),
        ("missing_adjustment", "ADJUSTMENT_BASIS_UNVERIFIED"),
    ],
)
def test_listing_analytics_reject_incompatible_price_streams(
    postgres_engine: Engine, mode: str, expected_issue: str
) -> None:
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)
        listing_id = listing.id
        if mode == "missing_listing_currency":
            listing.currency = None
        for index in range(2):
            session.add(
                PriceObservation(
                    listing_id=listing_id,
                    price_kind="DAILY_CLOSE",
                    market_date=datetime(2026, 10, index + 2, tzinfo=UTC),
                    recorded_at=datetime(2026, 10, 4 + index, tzinfo=UTC),
                    split_adjusted_close=Decimal("100") + index * 30,
                    currency="EUR" if index == 1 and mode == "currency" else "USD",
                    provider="OTHER" if index == 1 and mode == "provider" else "SYNTHETIC",
                    provider_symbol="OTHER" if index == 1 and mode == "symbol" else "SYNTH",
                    adjustment_basis=(
                        "Different adjustment"
                        if index == 1 and mode == "adjustment"
                        else "  "
                        if index == 1 and mode == "missing_adjustment"
                        else "Synthetic split-adjusted close"
                    ),
                    data_quality="PASS",
                    source_ref=f"stream-fixture-{index}-{uuid4()}",
                )
            )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        fetched_listing = session.get(Listing, listing_id)
        assert fetched_listing is not None
        result = queries.listing_market_data(
            session, fetched_listing, known_at=datetime(2026, 10, 6, tzinfo=UTC)
        )
        assert expected_issue in result.analytics.input_issues
        assert result.analytics.status == "UNAVAILABLE"
        assert result.analytics.daily_return is None
        assert result.analytics.trend_state is None
        assert len(result.history) == 2
        assert sum(stream.observation_count for stream in result.analytics.source_streams) == 2
        assert result.analytics.duplicate_market_dates == []
        if mode == "adjustment":
            assert {stream.adjustment_basis for stream in result.analytics.source_streams} == {
                "Synthetic split-adjusted close",
                "Different adjustment",
            }
        if mode == "missing_adjustment":
            assert result.analytics.input_issues == ["ADJUSTMENT_BASIS_UNVERIFIED"]
            assert any(
                stream.adjustment_basis is None for stream in result.analytics.source_streams
            )
        if mode in {"provider", "symbol", "adjustment"}:
            assert len(result.analytics.source_streams) == 2
            earlier = queries.listing_market_data(
                session, fetched_listing, known_at=datetime(2026, 10, 4, 12, tzinfo=UTC)
            )
            assert earlier.analytics.input_issues == []
            assert earlier.analytics.source_streams == []


@pytest.mark.integration
@pytest.mark.parametrize("venue", ["NYSE", "NASDAQ", "XETR", "XETRA"])
def test_schedule_review_uses_only_point_in_time_selected_closes(
    postgres_engine: Engine,
    venue: str,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)
        listing.venue = venue
        listing_id = listing.id
        for day, recorded in ((2, 3), (7, 8)):
            session.add(
                PriceObservation(
                    listing_id=listing.id,
                    price_kind="DAILY_CLOSE",
                    market_date=datetime(2026, 7, day, tzinfo=UTC),
                    recorded_at=datetime(2026, 7, recorded, tzinfo=UTC),
                    split_adjusted_close=Decimal("100"),
                    currency="USD",
                    provider="SYNTHETIC",
                    provider_symbol="SYNTH",
                    adjustment_basis="Synthetic split-adjusted close",
                    data_quality="PASS",
                    source_ref=f"scheduled-review-{day}-{uuid4()}",
                )
            )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        fetched_listing = session.get(Listing, listing_id)
        assert fetched_listing is not None
        result = queries.listing_market_data(
            session, fetched_listing, known_at=datetime(2026, 11, 9, tzinfo=UTC)
        )
        review = result.analytics.scheduled_session_review
        assert review is not None
        assert review.venue == ("XETRA" if venue == "XETR" else venue)
        assert review.absent_scheduled_dates == (
            [date(2026, 7, 3), date(2026, 7, 6)]
            if venue in {"XETR", "XETRA"}
            else [date(2026, 7, 6)]
        )
        assert result.analytics.session_coverage == "NOT_ASSESSED"
        earlier = queries.listing_market_data(
            session, fetched_listing, known_at=datetime(2026, 7, 4, tzinfo=UTC)
        )
        assert earlier.analytics.scheduled_session_review is None


@pytest.mark.integration
def test_database_history_replays_the_schedule_known_at_each_cutoff(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = sessions.SCHEDULES["NYSE"][0]
    revised = replace(
        original,
        schedule_id="synthetic-nyse-revision-2",
        observed_at=datetime(2026, 11, 10, tzinfo=UTC),
        source_sha256="b" * 64,
        holidays=original.holidays | {date(2026, 7, 6)},
    )
    pins = {
        **sessions.SCHEDULE_FINGERPRINTS,
        revised.schedule_id: sessions.schedule_fingerprint(revised),
    }
    monkeypatch.setitem(sessions.SCHEDULES, "NYSE", (original, revised))
    monkeypatch.setattr(sessions, "SCHEDULE_FINGERPRINTS", pins)
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)
        listing.venue = "NYSE"
        listing_id = listing.id
        for day in (2, 7):
            session.add(
                PriceObservation(
                    listing_id=listing.id,
                    price_kind="DAILY_CLOSE",
                    market_date=datetime(2026, 7, day, tzinfo=UTC),
                    recorded_at=datetime(2026, 7, 8, tzinfo=UTC),
                    split_adjusted_close=Decimal("100"),
                    currency="USD",
                    provider="SYNTHETIC",
                    provider_symbol="SYNTH",
                    adjustment_basis="Synthetic split-adjusted close",
                    data_quality="PASS",
                    source_ref=f"revision-replay-{day}-{uuid4()}",
                )
            )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        fetched_listing = session.get(Listing, listing_id)
        assert fetched_listing is not None
        before = queries.listing_market_data(
            session, fetched_listing, known_at=datetime(2026, 11, 9, tzinfo=UTC)
        )
        after = queries.listing_market_data(
            session, fetched_listing, known_at=datetime(2026, 11, 11, tzinfo=UTC)
        )
        replay = queries.listing_market_data(
            session, fetched_listing, known_at=datetime(2026, 11, 9, tzinfo=UTC)
        )
        assert (
            before.analytics.scheduled_session_review == replay.analytics.scheduled_session_review
        )
        assert before.analytics.scheduled_session_review is not None
        assert after.analytics.scheduled_session_review is not None
        assert before.analytics.scheduled_session_review.absent_scheduled_dates == [
            date(2026, 7, 6)
        ]
        assert after.analytics.scheduled_session_review.absent_scheduled_dates == []


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
    assert report["warning_evidence_unrecorded_checkpoints"] == 1
    assert report["history_window_coverage"] == "NOT_ASSESSED"
    evidence = report["listing_coverage"][0]["history_window_evidence"]
    assert evidence["assessment_reason"] == "EVIDENCE_NOT_RECORDED"
    assert evidence["distinct_observed_dates"] is None
    checkpoint.report = {
        "coverage": {"normalization_warnings_captured": True, "normalization_warnings": None}
    }
    malformed = _run_report(cast(Session, ReadOnlySession()), run)
    assert malformed["warning_evidence_unrecorded_checkpoints"] == 1
    assert malformed["listing_coverage"][0]["normalization_warnings_captured"] is False
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
