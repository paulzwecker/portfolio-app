"""Select one of five US equities slots, allowing for holidays and early closes."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
REGULAR = {"09:45", "11:15", "12:45", "14:15", "15:45"}
SHORT = {"09:45", "10:30", "11:15", "12:00", "12:45"}


def refresh_slot(cron, now, calendar):
    minute, hour, *_ = cron.split()
    slot = f"{int(hour):02}:{int(minute):02}"
    local = now.astimezone(NEW_YORK)
    day = local.date().isoformat()
    if not calendar.is_session(day):
        return ""
    opening = calendar.session_open(day)
    closing = calendar.session_close(day)
    slots = SHORT if closing.astimezone(NEW_YORK).hour < 16 else REGULAR
    nominal = local.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    if slot in slots and opening <= nominal <= local < closing:
        return slot
    return ""


if __name__ == "__main__":
    import exchange_calendars

    slot = refresh_slot(
        os.environ["SCHEDULE"],
        datetime.now(NEW_YORK),
        exchange_calendars.get_calendar("XNYS"),
    )
    print(f"slot={slot}")
