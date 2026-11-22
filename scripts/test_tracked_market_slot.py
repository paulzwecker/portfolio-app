from datetime import datetime, time
from unittest import TestCase

from tracked_market_slot import NEW_YORK, refresh_slot


class Calendar:
    def is_session(self, day):
        return day != "2026-11-26"

    def session_open(self, day):
        return datetime.combine(datetime.fromisoformat(day), time(9, 30), NEW_YORK)

    def session_close(self, day):
        hour = 13 if day == "2026-11-27" else 16
        return datetime.combine(datetime.fromisoformat(day), time(hour), NEW_YORK)


class TestSchedule(TestCase):
    def test_five_open_session_slots_and_zero_on_holidays(self):
        for day, expected in (
            ("2026-11-25", ["09:45", "11:15", "12:45", "14:15", "15:45"]),
            ("2026-11-26", []),
            ("2026-11-27", ["09:45", "10:30", "11:15", "12:00", "12:45"]),
        ):
            slots = []
            for hour, minute in (
                (9, 45),
                (10, 30),
                (11, 15),
                (12, 0),
                (12, 45),
                (14, 15),
                (15, 45),
            ):
                now = datetime.combine(
                    datetime.fromisoformat(day), time(hour, minute), NEW_YORK
                )
                slot = refresh_slot(f"{minute} {hour} * * 1-5", now, Calendar())
                if slot:
                    slots.append(slot)
            self.assertEqual(slots, expected)
