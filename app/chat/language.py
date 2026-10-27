"""Language detection — deterministic heuristic, no LLM call.

Why: the old bot thought in English and translated on output. That
pattern stays, but it needs to know WHAT to translate into first.
This is a first guess only: if it is wrong, the LLM answer step can
still reply in the visitor's language, because the visitor's own
message is in the prompt. Urdu in Arabic script and Roman Urdu are
included here — the old bot had neither.
"""
import re

_ARABIC = re.compile(r"[\u0600-\u06FF]")
_ROMAN_URDU = [
    "mujhe", "chahiye", "kitne", "kya", "hai", "kaise", "kab", "kahan",
    "price", "batao", "bataen", "chahte", "ho", "mera", "meri", "aur",
]
_SPANISH = [
    "necesito", "quiero", "cuánto", "cuanto", "precio", "gracias",
    "bolsas", "cajas", "etiquetas", "tamaño", "tamano",
]


def detect_language(text: str) -> str:
    """Return 'en', 'es', 'ur' (Arabic script) or 'ur-roman'."""
    t = (text or "").strip()
    if not t:
        return "en"
    if _ARABIC.search(t):
        return "ur"
    low = t.lower()
    words = set(re.findall(r"[a-záéíóúñ]+", low))
    if words & set(_SPANISH):
        return "es"
    if words & set(_ROMAN_URDU):
        return "ur-roman"
    return "en"
