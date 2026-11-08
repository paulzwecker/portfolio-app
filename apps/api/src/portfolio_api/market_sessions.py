"""Bounded published schedules for investigating selected daily price dates.

Schedules describe planned exchange openings, not verified trading or listing activity.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Literal

from portfolio_api.domain.schemas import ScheduledSessionReviewRead

NYSE_2026_SOURCE = "https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf"
NYSE_2026_SOURCE_SHA256 = "70f5577eb43e60a9dbbecaae3cec23d0f02028c05c7f175013bb3e97816d394f"
# The NYSE document says its dates were correct as of 10 December 2025. We observed
# the document at this later time; its earlier availability is not established.
# Ad hoc closures and instrument halts are not captured.
NYSE_2026_KNOWN_SINCE = datetime(2026, 11, 8, 18, 37, 45, 16120, tzinfo=UTC)
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

NASDAQ_2026_SOURCE = "https://nasdaqtrader.com/Trader.aspx?id=Calendar"
NASDAQ_2026_SOURCE_SHA256 = "33e2c294b3959430f9b4edbbbb0e6c5ed832ca6da30a3ea0de53748857e6698f"
NASDAQ_2026_KNOWN_SINCE = datetime(2026, 11, 8, 18, 37, 45, 961889, tzinfo=UTC)
NASDAQ_2026_HOLIDAYS = frozenset(
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

XETRA_2026_SOURCE = (
    "https://www.cashmarket.deutsche-boerse.com/resource/blob/4481276/"
    "1b643791fcb4d60bdd7f25efad3f4626/data/deutsche-boerse-trading-calendar-2026.pdf"
)
XETRA_2026_SOURCE_SHA256 = "1edfc7b737ae1f5fe93179bfa9af59223b3c9d11cc8deddd127b386fb87e44b6"
XETRA_2026_KNOWN_SINCE = datetime(2026, 11, 8, 18, 42, 31, 412425, tzinfo=UTC)
XETRA_2026_HOLIDAYS = frozenset(
    date.fromisoformat(day)
    for day in (
        "2026-01-01",
        "2026-04-03",
        "2026-04-06",
        "2026-05-01",
        "2026-12-24",
        "2026-12-25",
        "2026-12-31",
    )
)


@dataclass(frozen=True)
class PublishedSchedule:
    venue: Literal["NYSE", "NASDAQ", "XETRA"]
    schedule_id: str
    source_url: str
    source_sha256: str
    source_as_of: date | None
    observed_at: datetime
    holidays: frozenset[date]


SCHEDULES = {
    "NYSE": (
        PublishedSchedule(
            "NYSE",
            "NYSE-2026-asof-2025-12-10-observed-2026-11-08-v1",
            NYSE_2026_SOURCE,
            NYSE_2026_SOURCE_SHA256,
            date(2025, 12, 10),
            NYSE_2026_KNOWN_SINCE,
            NYSE_2026_HOLIDAYS,
        ),
    ),
    "NASDAQ": (
        PublishedSchedule(
            "NASDAQ",
            "NASDAQ-2026-observed-2026-11-08-v1",
            NASDAQ_2026_SOURCE,
            NASDAQ_2026_SOURCE_SHA256,
            None,
            NASDAQ_2026_KNOWN_SINCE,
            NASDAQ_2026_HOLIDAYS,
        ),
    ),
    "XETRA": (
        PublishedSchedule(
            "XETRA",
            "XETRA-2026-observed-2026-11-08-v1",
            XETRA_2026_SOURCE,
            XETRA_2026_SOURCE_SHA256,
            None,
            XETRA_2026_KNOWN_SINCE,
            XETRA_2026_HOLIDAYS,
        ),
    ),
}

# Reviewers must retain these pins and add a new ID/pin for each revision.
# They protect the interpreted holiday set as well as the raw source identity.
SCHEDULE_FINGERPRINTS = {
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


def schedule_fingerprint(schedule: PublishedSchedule) -> str:
    """Hash the interpreted schedule and provenance, independent of set order."""
    payload = {
        "contract": "published-schedule-2026-v1",
        "venue": schedule.venue,
        "schedule_id": schedule.schedule_id,
        "source_url": schedule.source_url,
        "source_sha256": schedule.source_sha256,
        "source_as_of": schedule.source_as_of.isoformat() if schedule.source_as_of else None,
        "observed_at": schedule.observed_at.astimezone(UTC).isoformat(),
        "year": 2026,
        "holidays": sorted(day.isoformat() for day in schedule.holidays),
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def schedule_at(
    versions: tuple[PublishedSchedule, ...],
    known_at: datetime,
    pins: Mapping[str, str] | None = None,
) -> PublishedSchedule | None:
    """Pick the latest unambiguous source observed by the knowledge cutoff."""
    if known_at.utcoffset() is None or any(
        item.observed_at.utcoffset() is None for item in versions
    ):
        return None
    pins = SCHEDULE_FINGERPRINTS if pins is None else pins
    eligible = [item for item in versions if item.observed_at <= known_at]
    if not eligible:
        return None
    if len({item.schedule_id for item in eligible}) != len(eligible):
        return None
    if len({item.observed_at for item in eligible}) != len(eligible):
        return None
    if any(pins.get(item.schedule_id) != schedule_fingerprint(item) for item in eligible):
        return None
    return max(eligible, key=lambda item: item.observed_at)


def scheduled_session_review(
    venue: str | None,
    observed_dates: list[date],
    known_at: datetime,
    *,
    window_start: date | None = None,
    window_end: date | None = None,
) -> ScheduledSessionReviewRead | None:
    """Compare selected series dates with the exact venue's published schedule."""
    # XETR is the ISO 10383 MIC of Deutsche Börse Xetra. It is not XFRA.
    schedule_venue = "XETRA" if venue == "XETR" else venue or ""
    versions = SCHEDULES.get(schedule_venue, ())
    schedule = schedule_at(versions, known_at)
    if schedule is None or schedule.venue != schedule_venue or not observed_dates:
        return None
    if (window_start is None) != (window_end is None):
        return None
    if window_start is not None and window_end is not None and window_start > window_end:
        return None
    start = max(window_start or min(observed_dates), date(2026, 1, 1))
    known_day = known_at.astimezone(UTC).date()
    # A session on the knowledge day may not have closed yet. Include that day
    # only when a selected close already exists for it.
    last_closed_day = known_day if known_day in observed_dates else known_day - timedelta(days=1)
    end = min(window_end or max(observed_dates), date(2026, 12, 31), last_closed_day)
    if start > end:
        return None
    selected = {day for day in observed_dates if start <= day <= end}
    if not selected:
        return None
    scheduled = {
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5
        and (start + timedelta(days=offset)) not in schedule.holidays
    }
    return ScheduledSessionReviewRead(
        venue=schedule.venue,
        schedule_id=schedule.schedule_id,
        source_url=schedule.source_url,
        source_sha256=schedule.source_sha256,
        schedule_fingerprint=schedule_fingerprint(schedule),
        source_as_of=schedule.source_as_of,
        source_observed_at=schedule.observed_at,
        start_date=start,
        end_date=end,
        full_selected_span_covered=start <= min(observed_dates) and end >= max(observed_dates),
        scheduled_count=len(scheduled),
        absent_scheduled_dates=sorted(scheduled - selected),
        selected_unscheduled_dates=sorted(selected - scheduled),
    )
