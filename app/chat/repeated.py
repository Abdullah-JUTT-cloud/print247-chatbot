"""Repeat-question detection — ported from the old bot (repeatedQuestion.ts).

In one week 101 of 360 old chats had a bot question sharing most of its
words with one it had already put. Measured on the question sentences
themselves, by shared meaningful words — or, failing that, by whether
both questions ask for the same detail (reworded repeats score low on
words but still ask the same thing).
"""
import re

FILLER = set(
    ("the you your are for and what that this with looking thank thanks great got perfect just can could "
     "would will like want need have has any please our out about into from them they its is was be to "
     "of in on a an or do does sure okay also").split())
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘'])")
_OPENS_A_QUESTION = re.compile(
    r"^\s*(?:what|which|how|where|when|why|who|do|does|did|can|could|would|will|should|is|are|may)\b",
    re.IGNORECASE)
_ASKS_ABOUT = [
    ("quantity", re.compile(r"\bquantit(?:y|ies)\b|\bhow many (?:\w+ )?(?:units|pieces|pcs|kits|boxes|bags|pouches|labels|stickers)\b", re.IGNORECASE)),
    ("sizes", re.compile(r"\bwhat size\b|\bsizes? (?:are|do|would|should|is)\b|\bdimensions\b", re.IGNORECASE)),
    ("finishes", re.compile(r"\bfinish\b", re.IGNORECASE)),
    ("skus", re.compile(r"\bdesigns?\b|\bsku['’]?s?\b", re.IGNORECASE)),
    ("material", re.compile(r"\b(?:material|special features?|stock|substrate)\b", re.IGNORECASE)),
    ("extras", re.compile(r"\b(?:zipper|tear notch|hang hole|window)\b", re.IGNORECASE)),
    ("name", re.compile(r"\b(?:take your name|what(?:'s| is) your name|who am i speaking with|could i have your name)\b", re.IGNORECASE)),
    ("email", re.compile(r"\b(?:email|email address|send the quote to)\b", re.IGNORECASE)),
    ("phone", re.compile(r"\b(?:phone|phone number|number in case)\b", re.IGNORECASE)),
]
SAME_QUESTION = 0.6


def _content_words(text: str) -> set:
    return {
        w for w in re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()
        if len(w) > 2 and w not in FILLER
    }


def is_question_sentence(sentence: str) -> bool:
    text = (sentence or "").strip()
    return bool(re.search(r"\?\s*$", text)) or bool(_OPENS_A_QUESTION.search(text))


def question_sentences(text: str) -> list:
    return [s for s in SENTENCE_BREAK.split(text or "") if is_question_sentence(s)]


def question_in(text: str) -> str:
    return " ".join(s for s in SENTENCE_BREAK.split(text or "") if "?" in s)


def fields_asked_about(question: str) -> list:
    return [key for key, pat in _ASKS_ABOUT if pat.search(question or "")]


def question_overlap(a: str, b: str) -> float:
    first, second = _content_words(a), _content_words(b)
    if not first or not second:
        return 0.0
    shared = len(first & second)
    return shared / (len(first) + len(second) - shared)


def repeats_the_question(reply: str, earlier: str) -> bool:
    if question_overlap(question_in(reply), question_in(earlier)) >= SAME_QUESTION:
        return True
    asked, before = fields_asked_about(question_in(reply)), fields_asked_about(question_in(earlier))
    return bool(asked) and any(key in before for key in asked)
