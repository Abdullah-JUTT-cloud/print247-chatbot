"""Quote slots + deterministic extraction — ported from the old bot.

The 7 fields (old repo: src/domain/quoteFields.ts):
  product, material, sizes, finishes, quantity, extras, skus
Defaults that never block a quote: skus="1", extras="none".
A field the visitor has not answered is absent (None), never the
word "null" or "not specified" — those words used to count as
answered, so the question was never asked again.

Three guards from real old-bot failures, all in code:
  1. Template blanks: FB/IG ads pre-fill "Qty: __ Size: __". A blank
     is NOT an answer.
  2. Pack count is not size or quantity: "10 ct", "5-pack", "30
     capsules per bag" say what goes INSIDE each bag, not how big
     the bag is or how many bags to order.
  3. Size needs a dimension pattern (e.g. 4x6, 100x150mm), not a
     lone number. A lone number is quantity, not size.
"""
import re

from .finishes_norm import finish_in, normalise_finish
from .quantity_parse import spelled_number_in

FIELDS = ["product", "material", "sizes", "finishes", "quantity", "extras", "skus"]
DEFAULTS = {"skus": "1", "extras": "none"}

_PLACEHOLDERS = {
    "null", "undefined", "none specified", "not specified", "unspecified",
    "n/a", "na", "not stated", "not mentioned", "not provided", "unknown", "tbd",
}
# "not sure" / "not given" are REAL answers (visitor said they don't
# know, or we asked twice) — deliberately NOT in _PLACEHOLDERS.

_PRODUCTS = [
    ("stand-up pouch", ["stand-up pouch", "stand up pouch", "standup pouch"]),
    ("flat pouch", ["flat pouch"]),
    ("flat-bottom pouch", ["flat-bottom pouch", "flat bottom pouch"]),
    ("mylar bag", ["mylar bag", "mylar bags"]),
    ("pouch", ["pouch", "pouches"]),
    ("bag", ["bag", "bags"]),
    ("box", ["box", "boxes", "carton", "cartons"]),
    ("label", ["label", "labels"]),
    ("sticker", ["sticker", "stickers"]),
    ("banner", ["banner", "banners"]),
]

_MATERIALS = [
    "kraft", "pet", "mpet", "pe", "foil", "vinyl", "cardboard",
    "corrugated", "matte bopp", "sbs", "plastic", "paper",
]

_FINISHES = [
    ("spot uv", ["spot uv"]),
    ("foil stamping", ["foil stamping", "gold foil", "foil"]),
    ("embossing", ["embossing"]),
    ("matte", ["matte"]),
    ("gloss", ["gloss", "glossy"]),
    ("none", ["no finish", "without finish"]),
]

_EXTRAS = [
    ("zipper", ["zipper", "ziplock", "zip lock"]),
    ("tear notch", ["tear notch"]),
    ("hang hole", ["hang hole"]),
    ("window", ["window"]),
]

_PACK_COUNT = re.compile(
    r"\b\d+\s*(?:ct|count|pack|capsules?|pieces?|pcs)\b", re.IGNORECASE)
_SIZE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:x|×|by)\s*\d+(?:\.\d+)?"
    r"(?:\s*(?:x|×|by)\s*\d+(?:\.\d+)?)?\s*(?:inches?|in\b|mm|cm)?",
    re.IGNORECASE)
_NUMBER = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|million)?\b", re.IGNORECASE)
_DESIGN_COUNT = re.compile(r"\b\d+\s*(?:different\s+)?(?:designs?|skus?|variants?|artworks?|types?)\b", re.IGNORECASE)
# Time spans are never quantities: "24 hours" used to become
# quantity=24 and fire the MOQ guard on a turnaround question.
_TIME_SPAN = re.compile(r"\b\d+\s*(?:hours?|hrs?|days?|minutes?|mins?|seconds?|weeks?|months?)\b|\b24\s*/\s*7\b", re.IGNORECASE)
_SPELLED = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
            "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "fifty": 50}
_WORD_NUM = {
    "fifty": 50, "hundred": 100, "thousand": 1000, "five hundred": 500,
    "one thousand": 1000, "two thousand": 2000, "five thousand": 5000,
    "ten thousand": 10000,
}


def is_placeholder(value: str | None) -> bool:
    """True if the value is an empty stand-in, not a real answer."""
    if value is None:
        return True
    t = value.strip().lower()
    if not t or t in _PLACEHOLDERS:
        return True
    # Template blank: "__", "Qty: __", "Size: __" — never an answer.
    if "__" in t or re.fullmatch(r"(qty|size)\s*:\s*", t):
        return True
    return False


def _find(haystack: str, table) -> str | None:
    for label, keys in table:
        if any(k in haystack for k in keys):
            return label
    return None


def _quantity_in(text: str) -> str | None:
    """First real order quantity, or None.

    Never reads a design count as quantity: "3 design of bags" has
    designs=3 and NO quantity, whatever other words are in the text
    (the old guard only skipped it when no product word was present,
    so "3 design of bags" wrongly became quantity=3 and the MOQ
    guard fired on designs instead of asking for a quantity).
    "15 thousand" = 15000, "2 million" = 2000000, "2k" = 2000.
    """
    low = text.lower()
    # Links and addresses are not quantities (an ad link's digits were
    # once read as an order of thousands).
    low = re.sub(r"https?://\S+|www\.\S+|\S+@\S+", " ", low)
    # Strip design-count spans first, so their numbers can never leak
    # into the quantity search below.
    cleaned = _DESIGN_COUNT.sub(" ", low)
    # Time spans stripped before any number is read as quantity.
    cleaned = _TIME_SPAN.sub(" ", cleaned)
    # Remove pack-count phrases so "10 ct" is never read as quantity.
    cleaned = _PACK_COUNT.sub(" ", cleaned)
    # Remove size spans so "4 by 6 inches" never leaks its first
    # dimension (4) into quantity — same class of bug as designs.
    cleaned = _SIZE.sub(" ", cleaned)
    m = _NUMBER.search(cleaned)
    if m:
        n = float(m.group(1).replace(",", ""))
        mult = (m.group(2) or "").lower()
        if mult == "k" or mult == "thousand":
            n *= 1000
        elif mult == "million":
            n *= 1000000
        return str(int(n))
    # Full spelled-number algorithm first: the old single regex matched
    # "five thousand" inside "twenty five thousand" and returned 5000.
    spelled = spelled_number_in(cleaned)
    if spelled is not None:
        return str(spelled)
    return None


_WORD_SKUS = {"single": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _skus_in(text: str) -> str | None:
    m = re.search(r"\b(\d+)\s*(?:different\s+)?(?:designs?|skus?|variants?|artworks?|types?)\b", text.lower())
    if m:
        return m.group(1)
    m = re.search(r"\b(single|one|two|three|four|five)\s+(?:designs?|skus?|variants?|artworks?)\b", text.lower())
    return str(_WORD_SKUS[m.group(1)]) if m else None


def extract_from_message(text: str) -> dict:
    """Deterministic slot extraction from one visitor message.

    Only fills what the text clearly says. Anything unclear stays
    None so the LLM (or the next question) can ask, instead of the
    code inventing an answer.
    """
    low = (text or "").lower()
    out: dict = {}
    product = _find(low, _PRODUCTS)
    if product:
        out["product"] = product
    for mat in _MATERIALS:
        if re.search(rf"\b{re.escape(mat)}\b", low):
            out["material"] = mat
            break
    size = _SIZE.search(low)
    if size and not _PACK_COUNT.search(low.split("x")[0] if "x" in low else low):
        out["sizes"] = size.group(0).strip()
    finish = _find(low, _FINISHES)
    if finish:
        out["finishes"] = normalise_finish(finish)
    else:
        slip = finish_in(low)
        if slip:
            out["finishes"] = slip
    qty = _quantity_in(text)
    if qty:
        out["quantity"] = qty
    extras = [label for label, keys in _EXTRAS if any(k in low for k in keys)]
    if extras:
        out["extras"] = ", ".join(extras)
    skus = _skus_in(text)
    if skus:
        out["skus"] = skus
    return out


def merge_slots(old: dict, new: dict) -> dict:
    """Merge new answers over old ones, never letting a placeholder
    overwrite a real answer, and never overwriting with blanks."""
    merged = {k: v for k, v in (old or {}).items() if not is_placeholder(v)}
    for k, v in (new or {}).items():
        if k in FIELDS and not is_placeholder(v):
            merged[k] = v
    for k, v in DEFAULTS.items():
        merged.setdefault(k, v)
    return merged


def missing_fields(slots: dict) -> list[str]:
    """Fields that still block a quote. skus/extras have defaults,
    so they never block. Material/finishes may be 'not sure' — that
    is a real answer and does not block either."""
    required = ["product", "sizes", "quantity"]
    return [f for f in required if is_placeholder(slots.get(f))]
