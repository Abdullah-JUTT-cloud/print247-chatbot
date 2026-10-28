"""Chat-closing promises — ported from the old bot (chatCompleteMessage.ts).

The promise of when pricing will be delivered depends on US Texas
(Central) time and weekday, so every reply-promise matches the closing
line: weekday daytime -> 'within today'; weekday late afternoon ->
'within today if possible; otherwise, first thing tomorrow morning';
weekday off-hours -> 'within our business hours'; weekend -> 'by
Monday morning'. All closing lines end with the contact promise.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TEXAS_TZ = ZoneInfo("America/Chicago")
CONTACT_TAIL = "If we need anything further, we'll contact you on the email/number provided."

COMPLETE_MESSAGE_WEEKDAY_DAYTIME = (
    "Thanks for sharing everything we need. We'll send your quote within today. " + CONTACT_TAIL)
COMPLETE_MESSAGE_WEEKDAY_LATE_AFTERNOON = (
    "Thanks for sharing everything we need. We'll send your quote within today if possible; "
    "otherwise, first thing tomorrow morning. " + CONTACT_TAIL)
COMPLETE_MESSAGE_WEEKDAY_OFF_HOURS = (
    "Thanks for sharing everything we need. We'll send your quote within our business hours. " + CONTACT_TAIL)
COMPLETE_MESSAGE_WEEKEND = (
    "Thanks for sharing everything we need. We'll send your quote by Monday morning. " + CONTACT_TAIL)
PRICED_COMPLETE_OPENING = "Thanks — your estimated pricing is below."


def texas_parts(at: datetime | None = None) -> dict:
    dt = (at or datetime.now(TEXAS_TZ)).astimezone(TEXAS_TZ)
    return {"hour": dt.hour, "minute": dt.minute, "weekday": dt.weekday()}  # Mon=0..Sun=6


def window_at(at: datetime | None = None) -> str:
    """'weekend' | 'daytime' | 'lateAfternoon' | 'offHours'."""
    parts = texas_parts(at)
    if parts["weekday"] >= 5:
        return "weekend"
    minutes = parts["hour"] * 60 + parts["minute"]
    if 9 * 60 <= minutes < 15 * 60 + 30:
        return "daytime"
    if 15 * 60 + 30 <= minutes < 18 * 60:
        return "lateAfternoon"
    return "offHours"


def when_the_team_replies(at: datetime | None = None) -> str:
    return {
        "daytime": "within today",
        "lateAfternoon": "within today if possible; otherwise, first thing tomorrow morning",
        "offHours": "within our business hours",
        "weekend": "by Monday morning",
    }[window_at(at)]


def get_chat_complete_message(at: datetime | None = None, priced: bool = False) -> str:
    window = window_at(at)
    if priced:
        return PRICED_COMPLETE_OPENING + " " + {
            "daytime": "We'll confirm it within today. ",
            "lateAfternoon": "We'll confirm it within today if possible; otherwise, first thing tomorrow morning. ",
            "offHours": "We'll confirm it within our business hours. ",
            "weekend": "We'll confirm it by Monday morning. ",
        }[window] + CONTACT_TAIL
    return {
        "daytime": COMPLETE_MESSAGE_WEEKDAY_DAYTIME,
        "lateAfternoon": COMPLETE_MESSAGE_WEEKDAY_LATE_AFTERNOON,
        "offHours": COMPLETE_MESSAGE_WEEKDAY_OFF_HOURS,
        "weekend": COMPLETE_MESSAGE_WEEKEND,
    }[window]


def is_chat_complete_message(text: str) -> bool:
    return (text or "") in (
        COMPLETE_MESSAGE_WEEKDAY_DAYTIME, COMPLETE_MESSAGE_WEEKDAY_LATE_AFTERNOON,
        COMPLETE_MESSAGE_WEEKDAY_OFF_HOURS, COMPLETE_MESSAGE_WEEKEND) \
        or (text or "").startswith(PRICED_COMPLETE_OPENING)
