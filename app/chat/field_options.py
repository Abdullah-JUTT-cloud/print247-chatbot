"""KB-grounded options for a script field — what the bot may SUGGEST
when a visitor does not know what to answer.

A "don't know" is answered with that field's options for the CURRENT
product, taken from the knowledge base, and never invented ones. Every
option is a term from the fixed slot vocabulary that is also present
in the KB files for the visitor's product. A term the KB files do not
mention for that product is not offered.

Fields without an enumerable KB option list return [] — the caller
then explains the field from the KB/glossary instead of inventing
choices.
"""
import glob
import os
import re

from .capability import capability_source
from .size_rules import family_of
from .slots import _EXTRAS, _FINISHES, _MATERIALS, find_product

_KB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "kb")

# Style and type vocabularies the bot may offer, with the wordings the
# KB uses for them. "spout" is deliberately absent: the KB marks it
# gallery-only and not offerable as a form choice.
_STYLES_BY_FAMILY = {
    "pouch": [
        ("stand-up", ("stand-up", "stand up", "standup")),
        ("flat", ("flat", "3-side", "3 side")),
        ("flat-bottom", ("flat-bottom", "flat bottom")),
        ("side gusset", ("side gusset",)),
        ("pinch bottom", ("pinch bottom",)),
    ],
    "box": [
        ("mailer", ("mailer", "mailers")),
        ("tuck-end", ("tuck end", "tuck-end")),
        ("folding carton", ("folding carton", "folding cartons")),
        ("rigid", ("rigid",)),
    ],
}
_TYPES_VOCAB = [
    ("corrugated", ("corrugated",)),
    ("cardboard", ("cardboard", "paperboard")),
    ("rigid", ("rigid",)),
    ("kraft", ("kraft",)),
]

# Put the core finishes (matte, gloss, soft touch) ahead of specialty
# finishes so a capped list always includes the primary choices first.
_PRIMARY_FINISHES = ("matte", "gloss", "soft touch")
_ORDERED_FINISHES = (
    [(c, list(a) + (["softouch"] if c == "soft touch" else []))
     for name in _PRIMARY_FINISHES for c, a in _FINISHES if c == name]
    + [(c, list(a)) for c, a in _FINISHES if c not in _PRIMARY_FINISHES and c != "none"]
)

# Short material codes must match in capitals only ("PET lining" is a
# material; lowercase prose is not).
_CODE_MATERIALS = {"pet", "mpet", "pe", "sbs"}

_SIZE_IN_KB = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(inches|inch|mm|cm|ft)\b"
    r"(?!\s*[x×+]\s*\d)", re.IGNORECASE)

_cache: dict[str, str] = {}


def _product_stem(product: str | None) -> str | None:
    if not product:
        return None
    canon = find_product(product) or product.lower().strip()
    src = capability_source(canon)
    if not src:
        return None
    return os.path.splitext(os.path.basename(src))[0]


def _read(abs_path: str) -> str:
    if abs_path not in _cache:
        try:
            with open(abs_path, encoding="utf-8") as f:
                raw = f.read()
            m = re.match(r"^---\n.*?\n---\n(.*)$", raw, re.DOTALL)
            _cache[abs_path] = m.group(1) if m else raw
        except OSError:
            _cache[abs_path] = ""
    return _cache[abs_path]


def _kb_files_for(product: str | None, field: str) -> list[str]:
    stem = _product_stem(product)
    fam = family_of(product)
    if not stem or not fam:
        return []
    prod_base = os.path.join(_KB_ROOT, "products", f"{stem}.md")
    prod_styles = sorted(glob.glob(os.path.join(_KB_ROOT, "products", f"{stem}-*styles*.md")))
    prod_sizes = sorted(glob.glob(os.path.join(_KB_ROOT, "products", f"{stem}-*sizes*.md")))
    mat_family = sorted(glob.glob(os.path.join(_KB_ROOT, "materials", f"{stem}*.md")))
    finishes_md = os.path.join(_KB_ROOT, "materials", "finishes.md")
    extras_md = os.path.join(_KB_ROOT, "materials", "extras.md")

    if field == "finishes":
        return mat_family + [finishes_md, prod_base]
    if field == "extras":
        return ([extras_md] + mat_family) if fam.gusset else []
    if field == "material":
        return mat_family + [prod_base]
    if field == "style":
        return [prod_base] + prod_styles
    if field == "type":
        return ([prod_base] + mat_family) if fam.depth_followup else []
    if field == "sizes":
        return prod_sizes + [prod_base]
    return [prod_base]


def _kb_text(product: str | None, field: str) -> str:
    return "\n".join(_read(p) for p in _kb_files_for(product, field))


def _mentions(text: str, alias: str, code: bool = False) -> bool:
    flags = 0 if code else re.IGNORECASE
    needle = alias.upper() if code else alias
    return bool(re.search(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", text, flags))


def _vocab_in(text: str, vocab) -> list[str]:
    """Canonical terms of `vocab` ([(canonical, aliases)]) present in text."""
    out = []
    for canon, aliases in vocab:
        if any(_mentions(text, a) for a in aliases) and canon not in out:
            out.append(canon)
    return out


def options_for(field: str, product: str | None, limit: int = 5) -> list[str]:
    """The options the KB lists for `field` of this product, or [].
    Never anything the KB files for the product omit."""
    fam = family_of(product)
    if not fam:
        return []
    text = _kb_text(product, field)
    if not text:
        return []
    if field == "finishes":
        out = _vocab_in(text, _ORDERED_FINISHES)
        if not out:
            out = _vocab_in(
                _read(os.path.join(_KB_ROOT, "materials", "finishes.md")),
                _ORDERED_FINISHES)
    elif field == "extras":
        out = _vocab_in(text, _EXTRAS)
    elif field == "style":
        vocab = _STYLES_BY_FAMILY.get(fam.name, [])
        out = _vocab_in(text, vocab)
    elif field == "type":
        out = _vocab_in(text, _TYPES_VOCAB)
    elif field == "material":
        out = []
        for m in _MATERIALS:
            if m == "metalized" and "metallized" in out:
                continue
            if _mentions(text, m, code=m in _CODE_MATERIALS) and m not in out:
                out.append(m)
    elif field == "sizes":
        out = []
        for a, b, unit in _SIZE_IN_KB.findall(text):
            size = f"{a}x{b} {unit.lower()}"
            if size not in out:
                out.append(size)
    else:
        out = []
    return out[:limit]
