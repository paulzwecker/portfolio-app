"""The bounded schedule is evidence, never a complete trading calendar."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

import portfolio_api.market_sessions as sessions
from portfolio_api.market_sessions import scheduled_session_review

KNOWN = datetime(2026, 11, 9, tzinfo=UTC)


def test_nyse_scheduled_gaps_exclude_holidays_and_weekends() -> None:
    result = scheduled_session_review("NYSE", [date(2026, 7, 2), date(2026, 7, 7)], KNOWN)
    assert result is not None
    assert result.scheduled_count == 3
    assert result.absent_scheduled_dates == [date(2026, 7, 6)]
    assert result.selected_unscheduled_dates == []
    assert result.full_selected_span_covered


def test_requested_window_exposes_boundary_candidates_without_changing_selected_span() -> None:
    dates = [date(2026, 7, 2), date(2026, 7, 7)]
    selected = scheduled_session_review("NYSE", dates, KNOWN)
    window = scheduled_session_review(
        "NYSE", dates, KNOWN, window_start=date(2026, 7, 1), window_end=date(2026, 7, 10)
    )
    assert selected is not None and window is not None
    assert selected.absent_scheduled_dates == [date(2026, 7, 6)]
    assert window.absent_scheduled_dates == [
        date(2026, 7, 1),
        date(2026, 7, 6),
        date(2026, 7, 8),
        date(2026, 7, 9),
        date(2026, 7, 10),
    ]
    assert window.full_selected_span_covered


def test_requested_window_clips_to_known_schedule_and_excludes_unclosed_days() -> None:
    dates = [date(2026, 11, 6)]
    window = scheduled_session_review(
        "NYSE", dates, KNOWN, window_start=date(2025, 1, 1), window_end=date(2027, 1, 1)
    )
    assert window is not None
    assert window.start_date == date(2026, 1, 1)
    assert window.end_date == date(2026, 11, 8)
    assert date(2026, 11, 9) not in window.absent_scheduled_dates
    assert scheduled_session_review("NYSE", dates, KNOWN, window_start=date(2026, 1, 1)) is None
    assert (
        scheduled_session_review(
            "NYSE", dates, KNOWN, window_start=date(2026, 8, 1), window_end=date(2026, 7, 1)
        )
        is None
    )
    assert (
        scheduled_session_review(
            "NYSE", [], KNOWN, window_start=date(2026, 1, 1), window_end=date(2026, 1, 31)
        )
        is None
    )


def test_early_close_is_a_scheduled_session_and_unscheduled_input_is_visible() -> None:
    result = scheduled_session_review(
        "NYSE", [date(2026, 11, 26), date(2026, 11, 27)], datetime(2026, 11, 28, tzinfo=UTC)
    )
    assert result is not None
    assert result.scheduled_count == 1
    assert result.absent_scheduled_dates == []
    assert result.selected_unscheduled_dates == [date(2026, 11, 26)]


def test_full_published_year_has_251_scheduled_weekdays() -> None:
    result = scheduled_session_review(
        "NYSE", [date(2026, 1, 1), date(2026, 12, 31)], datetime(2027, 1, 1, tzinfo=UTC)
    )
    assert result is not None
    assert result.scheduled_count == 251


def test_unknown_venues_dates_and_prepublication_cutoff_are_unassessed() -> None:
    dates = [date(2026, 1, 2), date(2026, 1, 5)]
    assert scheduled_session_review("XNAS", dates, KNOWN) is None
    assert scheduled_session_review(None, dates, KNOWN) is None
    assert scheduled_session_review("NYSE", [], KNOWN) is None
    assert scheduled_session_review("NYSE", [date(2025, 2, 3)], KNOWN) is None
    assert scheduled_session_review("NYSE", [date(2025, 12, 31), date(2027, 1, 2)], KNOWN) is None
    assert (
        scheduled_session_review("NYSE", dates, datetime(2026, 11, 8, 18, 31, tzinfo=UTC)) is None
    )
    assert scheduled_session_review(
        "NYSE", dates, datetime(2026, 11, 8, 18, 37, 45, 16120, tzinfo=UTC)
    )


def test_nasdaq_schedule_uses_independent_source_and_observation_time() -> None:
    dates = [date(2026, 7, 2), date(2026, 7, 7)]
    assert (
        scheduled_session_review(
            "NASDAQ", dates, datetime(2026, 11, 8, 18, 37, 45, 961888, tzinfo=UTC)
        )
        is None
    )
    result = scheduled_session_review(
        "NASDAQ", dates, datetime(2026, 11, 8, 18, 37, 45, 961889, tzinfo=UTC)
    )
    assert result is not None
    assert result.venue == "NASDAQ"
    assert result.source_as_of is None
    assert result.source_url == "https://nasdaqtrader.com/Trader.aspx?id=Calendar"
    assert result.absent_scheduled_dates == [date(2026, 7, 6)]
    assert result.scheduled_count == 3


def test_nasdaq_early_close_is_a_session_and_exchange_holiday_is_not() -> None:
    result = scheduled_session_review(
        "NASDAQ", [date(2026, 11, 25), date(2026, 11, 30)], datetime(2026, 12, 1, tzinfo=UTC)
    )
    assert result is not None
    assert result.absent_scheduled_dates == [date(2026, 11, 27)]


def test_xetra_and_xetr_use_xetra_source_only_after_exact_capture() -> None:
    dates = [date(2026, 7, 2), date(2026, 7, 7)]
    assert (
        scheduled_session_review(
            "XETR", dates, datetime(2026, 11, 8, 18, 42, 31, 412424, tzinfo=UTC)
        )
        is None
    )
    xetr = scheduled_session_review(
        "XETR", dates, datetime(2026, 11, 8, 18, 42, 31, 412425, tzinfo=UTC)
    )
    xetra = scheduled_session_review("XETRA", dates, KNOWN)
    assert xetr == xetra
    assert xetr is not None
    assert xetr.venue == "XETRA"
    assert xetr.source_as_of is None
    assert xetr.absent_scheduled_dates == [date(2026, 7, 3), date(2026, 7, 6)]
    assert scheduled_session_review("XFRA", dates, KNOWN) is None


def test_xetra_easter_and_may_holidays_are_not_us_holidays() -> None:
    easter = scheduled_session_review("XETRA", [date(2026, 4, 2), date(2026, 4, 7)], KNOWN)
    assert easter is not None
    assert easter.scheduled_count == 2
    assert easter.absent_scheduled_dates == []
    may = scheduled_session_review("XETRA", [date(2026, 5, 22), date(2026, 5, 26)], KNOWN)
    assert may is not None
    assert may.absent_scheduled_dates == [date(2026, 5, 25)]


def test_xetra_christmas_eve_and_new_years_eve_are_closed() -> None:
    result = scheduled_session_review(
        "XETRA", [date(2026, 12, 23), date(2026, 12, 30)], datetime(2027, 1, 2, tzinfo=UTC)
    )
    assert result is not None
    assert result.absent_scheduled_dates == [date(2026, 12, 28), date(2026, 12, 29)]
    year_end = scheduled_session_review(
        "XETRA", [date(2026, 12, 30), date(2026, 12, 31)], datetime(2027, 1, 2, tzinfo=UTC)
    )
    assert year_end is not None
    assert year_end.selected_unscheduled_dates == [date(2026, 12, 31)]


def test_scope_is_bounded_and_duplicates_do_not_hide_gaps() -> None:
    result = scheduled_session_review(
        "NYSE", [date(2025, 12, 31), date(2026, 1, 5), date(2026, 1, 5)], KNOWN
    )
    assert result is not None
    assert result.start_date == date(2026, 1, 1)
    assert result.end_date == date(2026, 1, 5)
    assert not result.full_selected_span_covered
    assert result.absent_scheduled_dates == [date(2026, 1, 2)]


def test_knowledge_cutoff_cannot_compare_future_dates() -> None:
    result = scheduled_session_review(
        "NYSE", [date(2026, 11, 6), date(2026, 11, 10)], datetime(2026, 11, 9, 12, tzinfo=UTC)
    )
    assert result is not None
    assert result.end_date == date(2026, 11, 8)
    assert result.absent_scheduled_dates == []
    assert not result.full_selected_span_covered


def test_source_revision_preserves_point_in_time_results(monkeypatch: pytest.MonkeyPatch) -> None:
    original = sessions.SCHEDULES["NYSE"][0]
    revised = replace(
        original,
        schedule_id="synthetic-nyse-revision-2",
        observed_at=original.observed_at + timedelta(days=2),
        source_sha256="b" * 64,
        holidays=original.holidays | {date(2026, 7, 6)},
    )
    pins = {
        **sessions.SCHEDULE_FINGERPRINTS,
        revised.schedule_id: sessions.schedule_fingerprint(revised),
    }
    monkeypatch.setitem(sessions.SCHEDULES, "NYSE", (revised, original))
    monkeypatch.setattr(sessions, "SCHEDULE_FINGERPRINTS", pins)
    dates = [date(2026, 7, 2), date(2026, 7, 7)]
    before = scheduled_session_review(
        "NYSE", dates, revised.observed_at - timedelta(microseconds=1)
    )
    after = scheduled_session_review("NYSE", dates, revised.observed_at)
    replay = scheduled_session_review(
        "NYSE", dates, revised.observed_at - timedelta(microseconds=1)
    )
    assert before is not None and after is not None
    assert before == replay
    assert before.absent_scheduled_dates == [date(2026, 7, 6)]
    assert after.absent_scheduled_dates == []
    assert before.schedule_id == original.schedule_id
    assert after.schedule_id == revised.schedule_id
    assert before.schedule_fingerprint == pins[original.schedule_id]
    assert after.schedule_fingerprint == pins[revised.schedule_id]


def test_unpinned_tampered_or_ambiguous_revisions_fail_closed() -> None:
    original = sessions.SCHEDULES["NYSE"][0]
    tampered = replace(original, holidays=original.holidays | {date(2026, 7, 6)})
    assert sessions.schedule_at((tampered,), KNOWN) is None
    unknown = replace(
        original, schedule_id="unreviewed", observed_at=original.observed_at + timedelta(hours=1)
    )
    assert sessions.schedule_at((original, unknown), KNOWN) is None
    assert sessions.schedule_at((original, unknown), original.observed_at) == original
    duplicate_id = replace(original, observed_at=original.observed_at + timedelta(hours=1))
    assert sessions.schedule_at((original, duplicate_id), KNOWN) is None
    duplicate_time = replace(original, schedule_id="another")
    duplicate_pins = {
        original.schedule_id: sessions.schedule_fingerprint(original),
        duplicate_time.schedule_id: sessions.schedule_fingerprint(duplicate_time),
    }
    assert sessions.schedule_at((original, duplicate_time), KNOWN, duplicate_pins) is None
    assert sessions.schedule_at((original,), datetime(2026, 11, 9)) is None


def test_existing_published_revisions_remain_in_the_catalog() -> None:
    original_pins = {
        "NYSE-2026-asof-2025-12-10-observed-2026-11-08-v1": (
            "7c7ebf9ac233d1f850adbc70aa3e16245fcf2b38cf34d9922295db9775fe4283"
        ),
        "NASDAQ-2026-observed-2026-11-08-v1": (
            "5d230288dd1d158d28107fba0eea183d3517f890e8b8e34675c69e0443837af5"
        ),
        "XETRA-2026-observed-2026-11-08-v1": (
            "89d25110d0c7a4ae07c049a7fe7d840a1a0ea027df3edc005ea96ec7759377da"
        ),
    }
    all_versions = [entry for versions in sessions.SCHEDULES.values() for entry in versions]
    for revision_id, expected in original_pins.items():
        matches = [entry for entry in all_versions if entry.schedule_id == revision_id]
        assert len(matches) == 1
        assert sessions.SCHEDULE_FINGERPRINTS[revision_id] == expected
        assert sessions.schedule_fingerprint(matches[0]) == expected


def test_fingerprint_binds_source_metadata_and_is_independent_of_holiday_order() -> None:
    original = sessions.SCHEDULES["NYSE"][0]
    reordered = replace(original, holidays=frozenset(reversed(sorted(original.holidays))))
    assert sessions.schedule_fingerprint(original) == sessions.schedule_fingerprint(reordered)
    assert sessions.schedule_fingerprint(original) != sessions.schedule_fingerprint(
        replace(original, source_sha256="c" * 64)
    )


def test_wrong_venue_catalog_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sessions.SCHEDULES, "NYSE", sessions.SCHEDULES["NASDAQ"])
    assert scheduled_session_review("NYSE", [date(2026, 7, 2)], KNOWN) is None
