"""Finished-chat handling — ported from the old bot
(chatEngine.ts closingLineFor + handoff.ts isPleasantry).

A chat that already closed and gets picked back up is where the
old bot embarrassed itself most: "did you email me" answered with
the closing line twice, "ok thanks" got the whole closing paragraph
again, and a sign-off got "talk soon" three times running. Rules:

- A pleasantry after the close gets a sign-off, never the same one
  twice in a row, never the closing paragraph again.
- "Did you email me / has it arrived?" gets the one true answer:
  it has not gone out yet, and when it will.
- A detail added after the close is noted, not answered with the
  whole closing paragraph again.
- A question after the close is answered (by the normal fact /
  intent path), and the chat stays finished.
"""
import re

_PLEASANTRY = re.compile(
    r"^(?:(?:ok(?:ay)?|k|thanks?|thank you|thank u|ty|thx|so much|great|perfect|cool|awesome|sounds good|will do|got it|noted|yes|yep|sure|bye|good ?bye|bye[\s-]bye|good|nice|hi|hello|hey|hiya|howdy|good morning|good afternoon|good evening|good ?night|see (?:you|ya|u)(?: (?:soon|later|then|tomorrow))?|talk (?:to you )?(?:soon|later)|you too|take care|cheers|alright|all good|appreciate it|much appreciated|have a (?:good|great|nice|lovely|blessed) (?:day|night|evening|weekend|one)|👍|🙏|🙂|😊)[\s,.!]*)+$",
    re.IGNORECASE | re.UNICODE)

ASKS_IF_IT_ARRIVED = re.compile(
    r"\b(did|have) you (e-?mail|sent|send)\b|\bany(thing)? (yet|come through)\b|"
    r"\bnot receiv|\bhaven'?t (got|received)\b|"
    r"\bwhere('?s| is) (the|my) (quote|email)\b|"
    r"\bis (the|my) quote (ready|sent|done)\b",
    re.IGNORECASE)

SIGN_OFFS = ["You're welcome — talk soon.", "Great — talk soon."]
NOTED_AFTER_THE_QUOTE = "Noted — I've added that to your request."
NOT_SENT_YET = "Not yet — the quote has not gone out. You will have it in the morning."


def is_pleasantry(text: str) -> bool:
    """'Thanks', 'ok', 'sounds good', 'hi' — nothing a rep needs a
    note about, and nothing that re-opens a finished quote."""
    return bool(_PLEASANTRY.match((text or "").strip()))


def asks_if_it_arrived(text: str) -> bool:
    return bool(ASKS_IF_IT_ARRIVED.search(text or ""))


def sign_off_after(last_bot_text: str) -> str:
    """A sign-off that is never the same one twice in a row."""
    if "thanks" in (last_bot_text or "").lower():
        return SIGN_OFFS[1] if SIGN_OFFS[0] in (last_bot_text or "") else SIGN_OFFS[0]
    return SIGN_OFFS[0] if SIGN_OFFS[0] not in (last_bot_text or "") else SIGN_OFFS[1]
