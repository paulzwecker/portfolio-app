"""Bounded published schedules for investigating selected daily price dates.

Schedules describe planned exchange openings, not verified trading or listing activity.
"""

from datetime import UTC, date, datetime, timedelta

from portfolio_api.domain.schemas import ScheduledSessionReviewRead

NYSE_2026_SOURCE = "https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf"
NYSE_2026_SOURCE_SHA256 = "70f5577eb43e60a9dbbecaae3cec23d0f02028c05c7f175013bb3e97816d394f"
# The NYSE document says its dates were correct as of 10 December 2025. We observed
# the document at this later time; its earlier availability is not established.
# Ad hoc closures and instrument halts are not captured.
NYSE_2026_KNOWN_SINCE = datetime(2026, 11, 8, 18, 34, tzinfo=UTC)
NYSE_2026_HOLIDAYS = frozenset(
    date.fromisoformat(day)
    for day in (
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-04-03",
        "2026-05-25",
        "2026-06-19",
        "2026-07-03",
        "2026-09-07",
        "2026-11-26",
        "2026-12-25",
    )
)


def scheduled_session_review(
    venue: str | None, observed_dates: list[date], known_at: datetime
) -> ScheduledSessionReviewRead | None:
    """Compare only the selected series span with the published NYSE 2026 schedule."""
    if venue != "NYSE" or not observed_dates or known_at < NYSE_2026_KNOWN_SINCE:
        return None
    start = max(min(observed_dates), date(2026, 1, 1))
    known_day = known_at.astimezone(UTC).date()
    # A session on the knowledge day may not have closed yet. Include that day
    # only when a selected close already exists for it.
    last_closed_day = known_day if known_day in observed_dates else known_day - timedelta(days=1)
    end = min(max(observed_dates), date(2026, 12, 31), last_closed_day)
    if start > end:
        return None
    selected = {day for day in observed_dates if start <= day <= end}
    if not selected:
        return None
    scheduled = {
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5
        and (start + timedelta(days=offset)) not in NYSE_2026_HOLIDAYS
    }
    return ScheduledSessionReviewRead(
        schedule_id="NYSE-2026-asof-2025-12-10-observed-2026-11-08-v1",
        source_url=NYSE_2026_SOURCE,
        source_sha256=NYSE_2026_SOURCE_SHA256,
        source_as_of=date(2025, 12, 10),
        source_observed_at=NYSE_2026_KNOWN_SINCE,
        start_date=start,
        end_date=end,
        full_selected_span_covered=start == min(observed_dates) and end == max(observed_dates),
        scheduled_count=len(scheduled),
        absent_scheduled_dates=sorted(scheduled - selected),
        selected_unscheduled_dates=sorted(selected - scheduled),
    )
