"""Ask-attempt accounting — ported from the old bot (askAttempts.ts).

An attempt is spent only when the visitor had a go and the bot still
lacks the detail. Asking twice for the same detail and then giving up
(MAX_ASKS = 2) is fair; counting the question itself as an attempt is
not — one chat lost a complete enquiry because the email question was
"spent" on a mistyped word and on a turn where the visitor asked where
the company was.
"""
import re

MAX_ASKS = 2
CONTACT_KEYS = ("name", "email", "phone")

_IS_A_QUESTION = re.compile(
    r"\?\s*$|^\s*(where|what|who|when|why|how|which|is|are|do|does|did|can|could|would|will|should)\b",
    re.IGNORECASE)
_DECLINES = re.compile(
    r"^\s*(no|nope|nah|none|not now|later|skip|maybe later|n/a|na)\b"
    r"|\b(no|dont|don't|do not|haven't|havent|not|wont|won't) (have |got |a |give |share )?(phone|email|number|e-mail|mail|cell)\b"
    r"|\bprefer not\b|\brather not\b"
    r"|\b(?:reach|contact|email|message|write|call)(?:\s+(?:me|out))?\s+(?:on|by|via|through)\s+(?:email|mail|phone|number)\b"
    r"|\b(?:just|only|use)\s+(?:email|mail|phone|number)\b"
    r"|\b(?:email|mail|phone)\s+(?:only|please|is fine|is enough|instead)\b",
    re.IGNORECASE)
_SPEC_WORDS = re.compile(
    r"\b(matte|gloss|soft\s*touch|finish|cheaper|cheapest|economical|cost[-\s]?effective|lowest\s*cost|inches|cm|mm|size|dimension|depth|height|width|x\s*\d|\d+\s*x|qty|quantity|pcs|pieces|units|boxes|bags|pouches|labels|stickers|cardboard|corrugated|rigid|kraft|foil|mylar|material|paper|coating|laminate|laminated)\b",
    re.IGNORECASE)
# "Stop everything", not "skip this field": a visitor who says they
# do not want this now is ending the contact flow, not declining one
# field. The old decline list only caught a refusal at the START of
# the message or one naming a contact noun — "I SAID I DONT WANT
# NOW" matched neither, so the bot asked for the email again after
# an explicit refusal. That repeat is the pestering failure.
_STOP_ALL = re.compile(
    r"\b(dont|don't|do not) want (it|this|that|now|anymore|any more|to continue)\b"
    r"|\bnot now\b"
    r"|(?<![\w-])stop\b"
    r"|\bleave me alone\b"
    r"|\bdon'?t (contact|message|email|call) me\b"
    r"|\bno more questions\b"
    r"|\bnot interested\b"
    r"|\b(dont|don't|do not) want to (share|give|tell)\b"
    r"|\bi said\b.{0,15}\b(dont|don't|do not)\b",
    re.IGNORECASE)
# Field-level refusal in looser words ("not interested", "don't want
# to share") — only when no spec word is present, so "I don't want
# matte" stays a finish answer, not a contact refusal.
_WONT_SHARE = re.compile(
    r"\b(dont|don't|do not) want to (share|give|tell)\b"
    r"|\bnot interested\b"
    r"|\bprefer not to (share|give)\b"
    r"|\brather not (share|give)\b",
    re.IGNORECASE)


def wants_to_stop(text: str | None) -> bool:
    """True when the visitor ends the conversation here, in any
    wording — not when they decline one field or answer a spec
    question. A spec word ('I don't want matte') is never a stop."""
    value = text or ""
    if _SPEC_WORDS.search(value):
        return False
    return bool(_STOP_ALL.search(value))


_PREFERS_EMAIL = re.compile(
    r"\b(?:send|share|forward|mail)\b[^.?!]{0,25}\b(?:to\s+)?(?:my\s+|the\s+)?e-?mail\b"
    r"|\b(?:communicate|talk|deal|correspond)\b[^.?!]{0,20}\b(?:through|via|by|over|on)\s+(?:the\s+)?e-?mail\b",
    re.IGNORECASE)
_ASKS_US = re.compile(
    r"\?|\b(please (confirm|advise|let me know|share|send)|can you|could you|do you|does your|are you able|is it possible|what is your|what's your|what are your|how long|how much|how soon|how fast|let me know|i'?d like to know|wondering)\b",
    re.IGNORECASE)
_ASKS_WHAT_IS_USUAL = re.compile(
    r"\b(standard|typical|usual|common|average|normal)\b|\b(?:what\s+do\s+you\s+|what\s+would\s+you\s+|can\s+you\s+)?(recommend|suggest)\b",
    re.IGNORECASE)
_NOT_SPEC_RECOMMENDATION = re.compile(
    r"\b(someone|somebody|person|contact|rep|who|who\s+to|manager|call)\b",
    re.IGNORECASE)
_DOES_NOT_KNOW = re.compile(
    r"\b(?:no idea|not sure|unsure|no clue|don'?t know|do not know|dunno|not decided|haven'?t decided|undecided|not yet decided|no preference|you tell me|up to you|your call|whatever you (?:recommend|suggest|think))\b",
    re.IGNORECASE)


def is_contact_key(key: str) -> bool:
    return key in CONTACT_KEYS


def ask_outcome(last_asked: str, text: str, have_it_now: bool) -> str:
    """'spent' | 'free' | 'declined' for one reply to a question."""
    if have_it_now:
        return "free"
    if is_contact_key(last_asked):
        if _DECLINES.search(text or ""):
            return "declined"
        if _WONT_SHARE.search(text or "") and not _SPEC_WORDS.search(text or ""):
            return "declined"
        if last_asked != "email" and _PREFERS_EMAIL.search(text or ""):
            return "declined"
        if _SPEC_WORDS.search(text or ""):
            return "free"
    if _IS_A_QUESTION.search(text or "") or visitor_is_asking(text):
        return "free"
    return "spent"


def visitor_is_asking(text: str) -> bool:
    """True if any sentence in the message asks us something."""
    message = text or ""
    if _ASKS_US.search(message):
        return True
    return any(_IS_A_QUESTION.search(s) for s in re.split(r"(?<=[.!?])\s+|\n+", message))


def asks_what_is_usual(text: str) -> bool:
    """Asking what is usual (e.g. 'what is a standard size?'), not
    telling us what they want. The usual-word must sit in a question
    sentence, and a recommendation about a person does not count."""
    s = text or ""
    if not visitor_is_asking(s):
        return False
    if _NOT_SPEC_RECOMMENDATION.search(s):
        return False
    return any(
        (_IS_A_QUESTION.search(sent) or re.search(r"\?\s*$", sent))
        and _ASKS_WHAT_IS_USUAL.search(sent)
        for sent in re.split(r"(?<=[.!?])\s+|\n+", s))


def says_they_do_not_know(text: str) -> bool:
    """'no idea' / 'not sure' / 'you tell me'. False on empty text and
    on anything containing a digit ('not sure, maybe 4x6' is a size)."""
    value = (text or "").strip()
    if not value or re.search(r"\d", value):
        return False
    return bool(_DOES_NOT_KNOW.search(value))


def says_nothing_useful(text: str) -> bool:
    """Gibberish guard: >=3 words, no word >=4 letters, >=60% of words
    <=2 letters, no digits, no '@', and not a question."""
    value = (text or "").strip()
    if not value or re.search(r"[\d@]", value) or visitor_is_asking(value):
        return False
    words = [w for w in re.split(r"\s+", value) if w]
    if len(words) < 3:
        return False
    letters = [re.sub(r"[^A-Za-z]", "", w) for w in words]
    has_real_word = any(len(w) >= 4 for w in letters)
    mostly_tiny = sum(1 for w in letters if len(w) <= 2) / len(words) >= 0.6
    return (not has_real_word) and mostly_tiny


def apply_ask_outcome(current: int, outcome: str) -> int:
    if outcome == "declined":
        return MAX_ASKS
    if outcome == "spent":
        return current + 1
    return current
