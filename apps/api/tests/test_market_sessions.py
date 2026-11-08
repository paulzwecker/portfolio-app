"""The bounded schedule is evidence, never a complete trading calendar."""

from datetime import UTC, date, datetime

from portfolio_api.market_sessions import scheduled_session_review

KNOWN = datetime(2026, 11, 9, tzinfo=UTC)


def test_nyse_scheduled_gaps_exclude_holidays_and_weekends() -> None:
    result = scheduled_session_review("NYSE", [date(2026, 7, 2), date(2026, 7, 7)], KNOWN)
    assert result is not None
    assert result.scheduled_count == 3
    assert result.absent_scheduled_dates == [date(2026, 7, 6)]
    assert result.selected_unscheduled_dates == []
    assert result.full_selected_span_covered


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
