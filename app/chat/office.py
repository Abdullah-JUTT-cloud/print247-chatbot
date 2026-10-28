"""Pakistan office-shift windows — ported from the old bot (officeHours.ts).

The team works a night shift in Pakistan, 7pm until 5am the following
morning, Monday-Friday evenings (Friday's shift finishes Saturday
morning; Saturday evening and Sunday evening are NOT shifts). The
window crosses midnight, which is why this is a tested module rather
than an inline comparison: `19 <= h < 5` is false for every hour.

NOTE ON USE: the old service used this to stay quiet while staffed.
The new chatbot must NOT stay quiet — it answers any hour. This module
is kept so the team can reason about reply promises ('the team is on
shift now' vs 'they will pick it up in the morning') and for admin
reporting, not as a gate on chat replies.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TIME_ZONE = ZoneInfo("Asia/Karachi")
START_HOUR, END_HOUR = 19, 5
SHIFT_START_DAYS = (0, 1, 2, 3, 4)  # Mon=0..Fri=4, by evening


def pakistan_parts(at: datetime | None = None) -> dict:
    dt = (at or datetime.now(TIME_ZONE)).astimezone(TIME_ZONE)
    return {"hour": dt.hour, "weekday": dt.weekday(), "minute": dt.minute}


def hour_in_pakistan(at: datetime | None = None) -> int:
    return pakistan_parts(at)["hour"]


def pakistan_stamp(at: datetime | None = None) -> str:
    parts = pakistan_parts(at)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return f"{days[parts['weekday']]} {parts['hour']:02d}:{parts['minute']:02d}"


def is_office_hours(at: datetime | None = None) -> bool:
    """Was somebody at a desk at this moment? An hour late in the
    evening belongs to the shift starting that day; an hour before
    dawn belongs to the shift that started the PREVIOUS day — which is
    what makes Saturday morning staffed but Saturday evening not."""
    parts = pakistan_parts(at)
    hour, weekday = parts["hour"], parts["weekday"]
    if hour >= START_HOUR:
        return weekday in SHIFT_START_DAYS
    if hour < END_HOUR:
        return (weekday - 1) % 7 in SHIFT_START_DAYS
    return False
