"""Category -> subcategory grounding (Oct 30).

A visitor rarely asks about a bare product: they ask about a
SUBCATEGORY of it — a material ("wooden"), a type ("NFC"), a style
("spout"). Two failures came from answering those without checking
the subcategory against the category's own files:

- "do you have wodden NFC business cards?" got a generic Yes plus
  the card stocks list, never addressing wooden — wooden is not in
  the listed stocks, so the Yes read as if wooden were standard.
- "i need wodden ones" then lost the product entirely and asked a
  box style question (an LLM product guess, stored without any
  switch check, is part of that story — see brain.py).

Rule: a qualifier word is checked against the CURRENT product's
own files (type lists, stocks, materials). Listed -> the existing
answer stands. NOT listed -> the reply must say so plainly and let
the team confirm that part — never a generic Yes that implies the
subcategory is standard, and never a refusal either (the company
may still do it; it is just not published).

The check is deliberately narrow: only attribute-ish words count
(materials, styles, types). Finishes are universal (matte/gloss
are offered across products), generic adjectives ("custom",
"premium") are not subcategories, and product words themselves are
not qualifiers. A typo-close word ("wodden") is corrected to its
vocabulary word first, so the caveat names what the visitor meant.
"""

import difflib
import re

_STOP = {
    "do", "you", "have", "can", "could", "will", "would", "make",
    "print", "offer", "offers", "produce", "provide", "sell", "create",
    "manufacture", "handle", "supply", "need", "want", "needs", "wants",
    "i", "me", "my", "a", "an", "the", "for", "in", "of", "to", "and",
    "or", "custom", "ones", "one", "please", "hi", "hello", "hey", "ok",
    "us", "your", "we", "get", "like", "just", "with", "about", "is",
    "are", "does", "did", "any", "some", "that", "this", "it", "on",
    "by", "per", "from", "as", "at", "be", "am", "if", "so", "than",
    "then", "too", "very", "really", "also", "only", "all", "into",
    "more", "most", "other", "others", "another", "first", "new",
    "good", "best", "cheap", "affordable", "high", "quality",
    "premium", "looking", "look", "something", "anything", "please",
    "kind", "kinds", "type", "types", "material", "materials",
    "which", "what", "how", "many", "much", "there", "here",
}
# Single-word product aliases are not qualifiers.
_PRODUCT_WORDS = {
    "box", "boxes", "carton", "cartons", "caja", "cajas", "label",
    "labels", "etiqueta", "etiquetas", "sticker", "stickers",
    "business", "card", "cards", "banner", "banners", "pouch",
    "pouches", "bag", "bags", "bolsa", "bolsas", "mylar",
}
# Finish words are universal, not subcategories — never qualifiers.
_FINISH_WORDS = {
    "matte", "gloss", "glossy", "soft", "touch", "spot", "uv",
    "embossing", "stamping", "foil",
}
# Attribute-ish words visitors use for subcategories, beyond what
# the slot tables already hold (materials, styles, card stocks).
_EXTRA = {
    "wooden", "wood", "metal", "glass", "leather", "fabric", "cotton",
    "silk", "jute", "bamboo", "cork", "tin", "aluminum", "aluminium",
    "steel", "iron", "linen", "canvas", "nylon", "polyester", "tyvek",
    "acrylic", "cardstock", "pvc", "nfc", "shape", "display",
    "cosmetic", "cbd", "pharmaceutical", "apparel", "metalized",
    "gusset", "zipper",
}

_POUCH_FILES = ["kb/products/pouches.md",
                "kb/products/pouches-mylar-styles.md",
                "kb/materials/pouches-mylar-materials-finishes.md"]
_PRODUCT_FILES = {
    "box": ["kb/products/boxes.md",
            "kb/products/boxes-campaign-styles.md",
            "kb/materials/boxes-campaign-materials.md"],
    "pouch": _POUCH_FILES,
    "mylar bag": _POUCH_FILES,
    "bag": _POUCH_FILES,
    "stand-up pouch": _POUCH_FILES,
    "flat pouch": _POUCH_FILES,
    "flat-bottom pouch": _POUCH_FILES,
    "label": ["kb/products/labels.md"],
    "sticker": ["kb/products/labels.md"],
    "business card": ["kb/products/business-cards.md"],
    "banner": ["kb/products/banners.md"],
}


def _vocab() -> set:
    from .slots import _MATERIALS, _STYLE_WORDS

    vocab = set(_MATERIALS)
    vocab |= {label for _, label in _STYLE_WORDS}
    vocab |= _EXTRA
    vocab -= _FINISH_WORDS
    vocab.discard("matte bopp")
    return vocab


def _product_text(product: str) -> str:
    parts = []
    for path in _PRODUCT_FILES.get(product, []):
        try:
            raw = open(path, encoding="utf-8").read()
        except OSError:
            continue
        m = re.match(r"^---\n.*?\n---\n(.*)$", raw, re.DOTALL)
        parts.append(m.group(1) if m else raw)
    return "\n".join(parts)


def unlisted_qualifiers(message: str, product: str) -> list:
    """Qualifier words in the message that the product's own files
    never name, in message order, deduplicated. Empty when the
    product has no file map, or every qualifier is listed."""
    if not product or product not in _PRODUCT_FILES:
        return []
    vocab = _vocab()
    text = _product_text(product)
    if not text:
        return []
    tokens = re.findall(r"[a-z]+(?:-[a-z]+)?", (message or "").lower())
    out = []
    for tok in tokens:
        if tok in _STOP or tok in _PRODUCT_WORDS or tok in _FINISH_WORDS:
            continue
        if any(ch.isdigit() for ch in tok):
            continue
        word = tok
        if word not in vocab:
            if len(word) < 3:
                continue
            close = difflib.get_close_matches(word, vocab, n=1, cutoff=0.8)
            if not close:
                continue
            word = close[0]
        if word in out:
            continue
        # Word-prefix match: "metal" finds "metalized" (a listed box
        # type); "wooden" finds nothing, because no file names wood.
        if not re.search(rf"\b{re.escape(word)}\w*\b", text, re.IGNORECASE):
            out.append(word)
    return out


def qualifier_caveat(product: str, words: list) -> str:
    """One plain sentence: the subcategory is not published, so
    the team confirms that part. Never a refusal, never a Yes."""
    names = [w[0].upper() + w[1:] for w in words]
    if len(names) == 1:
        joined, verb, pron = names[0], "isn't", "it's"
    elif len(names) == 2:
        joined, verb, pron = " and ".join(names), "aren't", "they're"
    else:
        joined = ", ".join(names[:-1]) + " and " + names[-1]
        verb, pron = "aren't", "they're"
    return (f"{joined} {verb} in our listed {product} options — "
            f"the team can confirm whether {pron} possible.")
