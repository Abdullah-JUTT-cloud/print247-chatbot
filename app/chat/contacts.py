"""Contact collection — ported from the old bot (contactFields.ts,
ourOwnContacts.ts, and the deterministic half of contactExtractor.ts).

Asked AFTER the job details, never before: someone who has just
described what they want has a reason to leave a number; someone
greeted by a form has not. A name is worth having but is not a way to
reach anybody — at least one usable email OR phone is required, or the
chat is a transcript nobody can act on.

Our own details are never recorded as the visitor's: the bot hands out
Support@print247.us and +1 (832) 807-3429 when asked how to reach us,
and without this guard the extractor reads them straight back off the
transcript as the customer's contact. The LLM half of the old
extractor (reading a name from free text) is deliberately NOT ported:
a guessed contact is worse than an empty one.
"""
import re

# Mirror of the rep pool in app/chat_ui.py (REP_NAMES). A visitor name
# that equals one of these is only theirs if they typed it themselves.
REP_NAMES = [
    "Frank Castle", "Jessica Joe", "Alex Kane", "Max Carter",
    "Harry Brook", "Ethan Wilson", "Paul Smith", "Brian Tylar",
    "Hazel Grace", "Nancy Wilson",
]
OUR_EMAIL_DOMAINS = ("print247.us",)
OUR_PHONE_DIGITS = ("18328073429", "8328073429")

CONTACT_FIELDS = [
    {"key": "name", "label": "Name", "question": "Could I take your name?"},
    {"key": "email", "label": "Email", "question": "What is the best email to send the quote to?"},
    {"key": "phone", "label": "Phone", "question": "And a phone number in case we need to check anything?"},
]
REACHABLE_KEYS = ("email", "phone")

_PLACEHOLDER_NAME = re.compile(
    r"^(yes|yeah|yep|no|nope|ok|okay|sure|thanks?|thank you|hi|hello|hey|none|n/?a|test|asap|please)\b[\s.!]*$",
    re.IGNORECASE)
_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}", re.IGNORECASE)
_PHONE_CANDIDATE = re.compile(r"\+?[\d\s().-]{7,}")
_SPOKEN_EMAIL = [
    (re.compile(r"\s+at\s+", re.IGNORECASE), "@"),
    (re.compile(r"\s+dot\s+", re.IGNORECASE), "."),
]


def is_placeholder_name(name: str | None) -> bool:
    value = (name or "").strip()
    if not value:
        return True
    if re.match(r"^visitor\s*\d*$", value, re.IGNORECASE) or re.fullmatch(r"\d+", value):
        return True
    return bool(_PLACEHOLDER_NAME.match(value))


def is_our_reps_name(name: str | None, visitor_said: list | None = None) -> bool:
    """True if the name is one of our reps' and the visitor never typed
    it themselves (the bot introduces itself, so its own name must
    never become the visitor's name)."""
    value = (name or "").strip().lower()
    if not value:
        return False
    ours = []
    for rep in REP_NAMES:
        full = rep.strip().lower()
        if full:
            ours += [full, full.split()[0]]
    if value not in ours:
        return False
    escaped = re.escape(value)
    return not any(re.search(rf"\b{escaped}\b", t or "", re.IGNORECASE) for t in (visitor_said or []))


def looks_like_email(value: str | None) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$", (value or "").strip()))


def email_in(text: str | None) -> str:
    """The email address in what they typed, including spoken form
    ('ali at gmail dot com' -> 'ali@gmail.com')."""
    raw = text or ""
    spoken = raw
    for pat, rep in _SPOKEN_EMAIL:
        spoken = pat.sub(rep, spoken)
    m = _EMAIL_RE.search(spoken)
    email = m.group(0).lower() if m else ""
    return email if looks_like_email(email) else ""


def looks_like_phone(value: str | None) -> bool:
    """7-15 digits, and no words: '8772 Hesby Court, San Diego, CA
    92129' has nine digits and was once stored as a phone number.
    Extensions ('ext 12', 'x12') are still a phone number."""
    text = value or ""
    digits = len(re.sub(r"\D", "", text))
    if digits < 7 or digits > 15:
        return False
    stripped = re.sub(r"\b(?:ext|extension|tel|phone|cell|mobile)\b\.?", "", text, flags=re.IGNORECASE)
    return not re.search(r"[a-z]{2,}", stripped, re.IGNORECASE)


def phones_in(text: str | None) -> list:
    """Phone-shaped substrings that pass looks_like_phone, in order."""
    out = []
    for m in _PHONE_CANDIDATE.finditer(text or ""):
        cand = m.group(0).strip()
        if looks_like_phone(cand) and cand not in out:
            out.append(cand)
    return out


def is_our_email(email: str | None) -> bool:
    address = (email or "").strip().lower()
    if "@" not in address:
        return False
    domain = address.split("@")[-1]
    return any(domain == d or domain.endswith("." + d) for d in OUR_EMAIL_DOMAINS)


def is_our_phone(phone: str | None) -> bool:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        return False
    tail = digits[-10:]
    return any(tail == ours[-10:] for ours in OUR_PHONE_DIGITS)


_NAME_NON_NAME_WORDS = {
    "i", "me", "my", "we", "can", "could", "will", "would", "shall", "should",
    "provide", "share", "give", "tell", "send", "yes", "no", "sure", "ok", "okay",
    "please", "here", "is", "am", "name", "the", "a", "an", "it", "not", "dont",
    "don't", "cannot", "cant", "want", "need", "prefer", "use", "call", "have",
    "got", "just", "only", "later", "maybe", "thanks", "thank", "hi", "hello", "hey",
}


def looks_like_person_name(value: str | None) -> bool:
    """A name-shaped value, not a sentence about giving one. The old
    check only rejected bare placeholders ("yes", "ok"), so "i can
    provide my name" was stored AS the name and the bot moved on to
    email — the "whatever the customer replies, next question" bug
    (Oct 29 live transcript). A usable name is 1-4 alphabetic
    words with no willingness/verb words in it."""
    text = (value or "").strip().strip(".,!")
    if not text or is_placeholder_name(text):
        return False
    words = text.split()
    if not 1 <= len(words) <= 4:
        return False
    for w in words:
        clean = w.strip(".,!'\"").lower()
        if clean in _NAME_NON_NAME_WORDS:
            return False
        if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", w.strip(".,!'\"")):
            return False
    return True


def is_contact_value_usable(key: str, value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if key == "email":
        return looks_like_email(text) and not is_our_email(text)
    if key == "phone":
        return looks_like_phone(text) and not is_our_phone(text)
    if key == "name":
        return looks_like_person_name(text) and not is_our_reps_name(text)
    return not is_placeholder_name(text) and not is_our_reps_name(text)


def missing_contact_fields(collected: dict, wanted=("name", "email", "phone")) -> list:
    return [f["key"] for f in CONTACT_FIELDS
            if f["key"] in wanted and not is_contact_value_usable(f["key"], (collected or {}).get(f["key"]))]


def contact_field_by_key(key: str) -> dict:
    return next(f for f in CONTACT_FIELDS if f["key"] == key)


def has_reachable_contact(collected: dict) -> bool:
    return any(is_contact_value_usable(k, (collected or {}).get(k)) for k in REACHABLE_KEYS)
