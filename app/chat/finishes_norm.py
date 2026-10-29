"""Finish normalisation — ported from the old bot (finishes.ts).

'glass' for gloss, 'matt' for matte, 'softtouch' run together: the bot
once repeated one straight back ('you prefer a glass finish') and the
wrong word went onto the lead. Fixed here rather than in the prompt,
because the damage is in the record, not only in the sentence. Only
these three are corrected, and only when the whole answer is one of
them — a customer who writes something we do not recognise is saying
something we should not overwrite. Spot UV, foil, embossing and
'none' all come through exactly as given.
"""
import re

_FINISHES = [
    ("gloss", re.compile(r"^(gloss|glossy|glossey|glosy|glass|gluss|gloos|shiny|shine|high gloss)$"),
     re.compile(r"\b(glass|gluss|glosy|glossey|gloos)\b")),
    ("matte", re.compile(r"^(matte|matt|mat|mattee|matty|mate)$"),
     re.compile(r"\b(matt|mat|mattee|matty)\b")),
    ("soft touch", re.compile(r"^(soft ?-? ?touch|softtouch|soft tuch|soft touche|softouch)$"),
     re.compile(r"\b(soft ?touch|softtouch|softouch|soft tuch)\b")),
]
_BARE_NOISE = re.compile(r"\b(finish|finishing|lamination|laminate|laminated|please|prefer|i|want|the|a)\b")


def finish_in(text: str | None) -> str | None:
    """The finish mentioned anywhere in a message, including the
    misspellings ('glass finish' -> gloss). Used when the exact
    finish table misses, so a near-miss still lands on a real finish
    instead of being stored as a word we do not make."""
    low = (text or "").lower()
    for canonical, exact, slip in _FINISHES:
        if slip.search(low):
            return canonical
    return None


def normalise_finish(value: str | None) -> str:
    answer = (value or "").strip()
    if not answer:
        return answer
    bare = re.sub(r"[.,!?]", " ", _BARE_NOISE.sub(" ", answer.lower()))
    bare = re.sub(r"\s+", " ", bare).strip()
    for canonical, exact, _slip in _FINISHES:
        if exact.match(bare):
            return canonical
    corrected = answer
    for canonical, _exact, slip in _FINISHES:
        corrected = slip.sub(canonical, corrected)
    return corrected
