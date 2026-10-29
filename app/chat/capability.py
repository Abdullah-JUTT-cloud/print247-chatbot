"""Capability questions: "do you make pizza boxes?", "can you
print mylar bags?" — with or without a question mark, and with the
typos visitors actually type ("do you maqke corrogated boxes").

Why this file exists: the old question-not-answer rule treated
every question as "not an answer", so a capability question fell
through to the product question — the bot asked what the visitor
had just told it. "Can you make mylar bags?" only worked by
accident (the "?" made it a fact question); "do you make pizza
boxes" without a "?" did not. A capability question about a product
we make IS the visitor choosing that product: answer Yes from the
product file, store the product, and ask the size — never the
product question again. Sizes are deliberately NOT stored from a
capability question: "13 inch" is one dimension, not a box size,
and the old rule against filling sizes from questions stays.
"""
import difflib
import re

# A capability question ASKS WHETHER ("do you make boxes?"), it
# does not ask what ("What box materials do you offer?" starts
# with What and must reach the materials answer, not a Yes). So the
# auxiliary must lead the message, after only a greeting or 'ok'.
_AUX = re.compile(
    r"^\s*(?:(?:ok|hi|hello|hey|please)[,.\s]*)?"
    r"(?:do|does|can|could|will|would)\s+(?:you|u)\s+(\w+)",
    re.IGNORECASE)
# Qualifiers with their own dedicated file (wine/whiskey labels,
# beef jerky bags) must reach that file, not the generic product
# Yes — "Do you print wine labels?" is answered by the wine-labels
# file, not by labels.md.
_VARIANT_QUALIFIERS = ("wine", "whiskey", "whisky", "spirit", "beverage",
                       "jerky")
_VERBS = {"make", "print", "offer", "do", "produce", "provide", "sell",
          "create", "manufacture", "handle", "supply", "have"}


def _is_make_like(token: str) -> bool:
    """'maqke', 'maek', 'mak', 'makee' — one transposed or dropped
    letter away from 'make'. 'bake' would also score 0.75, so the
    token must start with 'm' as well — 'bake'/'take' never do."""
    t = (token or "").lower()
    if not t.startswith("m"):
        return False
    return difflib.SequenceMatcher(None, t, "make").ratio() >= 0.7


def capability_product(text: str) -> str | None:
    """The product a capability question asks about, or None.

    Returns the canonical product from slots._PRODUCTS (longest
    alias wins, so 'mylar bags' beats 'bags'). None when the message
    is not a capability question, or the product is not one we make
    — an unknown product must never get a Yes."""
    from .slots import _PRODUCTS, fuzzy_product, mylar_like

    said = text or ""
    low = said.lower()
    if any(re.search(rf"\b{q}\b", low) for q in _VARIANT_QUALIFIERS):
        return None
    m = _AUX.search(low)
    if not m:
        return None
    verb = m.group(1)
    if verb not in _VERBS and not _is_make_like(verb):
        return None
    best = None
    for canonical, aliases in _PRODUCTS:
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", low):
                if best is None or len(alias) > len(best[1]):
                    best = (canonical, alias)
    if best:
        if best[0] == "bag" and mylar_like(low):
            return "mylar bag"
        return best[0]
    # "do you make lables" — the exact table misses, the fuzzy one
    # must not, or the typo gets the product question again.
    return fuzzy_product(low)


# Canonical product -> the ONE general product file that answers a
# capability question. Retrieval must not choose here: keyword
# search once ranked the beef-jerky campaign file first for "milar
# bags" and the bot answered Yes with jerky text.
_PRODUCT_FILE = {
    "box": "kb/products/boxes.md",
    "mylar bag": "kb/products/pouches.md",
    "pouch": "kb/products/pouches.md",
    "bag": "kb/products/pouches.md",
    "stand-up pouch": "kb/products/pouches.md",
    "flat pouch": "kb/products/pouches.md",
    "flat-bottom pouch": "kb/products/pouches.md",
    "label": "kb/products/labels.md",
    "sticker": "kb/products/labels.md",
    "business card": "kb/products/business-cards.md",
    "banner": "kb/products/banners.md",
}


def capability_source(product: str) -> str | None:
    """The product file path for a canonical product, or None."""
    return _PRODUCT_FILE.get(product or "")


def capability_fact(product: str) -> str | None:
    """The general product file's text, or None if it is not on
    disk — then the branch falls through instead of guessing."""
    path = _PRODUCT_FILE.get(product or "")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


# NOTE (Oct 29, philosophy correction): the whitelist guard that
# lived here (unlisted_options + option tables) is DELETED. The KB
# is a reference, not the limit of what the company makes — a
# packaging company makes the product family, so an option the
# files do not name still gets a Yes. "Team will confirm" survives
# only for out-of-domain requests and company hard facts the KB
# does not hold.
