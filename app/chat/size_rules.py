"""Family-aware size validation — ONE validator, ONE table, every product.

Everything that depends on a product's size shape reads the FAMILIES
table below:

- flat  : width x height only (2 dimensions, no gusset, no depth).
          Any 3-dimension size is refused on the spot with a
          flat-product explanation and a 2-dimension re-ask.
- box   : width x height, optionally x depth (2 or 3 dimensions;
          the depth follow-up fires for a 2-number size, unchanged).
- pouch : width x height plus an optional gusset (+N format).
          Never a separate third "depth" dimension.

validate_size() is called by the brain at the turn a size arrives —
before the unit question, before anything is stored, before any
confirmation can be built — and on every turn after (so a size given
before the product is known is checked the moment the product lands).
A single measurement is a fragment that other flows complete, so it
passes.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SizeFamily:
    name: str
    max_dims: int            # most dimensions a size may carry
    gusset: bool             # an optional +N gusset is part of the size
    depth_followup: bool     # a 2-number size gets the "add depth?" question
    holds_contents: bool     # something goes INSIDE it (drives pack wording)
    question_key: str        # script.QUESTIONS key for the size question


FAMILIES = {
    "flat": SizeFamily("flat", 2, False, False, False, "sizes_flat"),
    "box": SizeFamily("box", 3, False, True, True, "sizes"),
    "pouch": SizeFamily("pouch", 2, True, False, True, "sizes_flat"),
}


def family_of(product: str | None) -> SizeFamily | None:
    """The size family of a product, or None when the product is not
    known (then nothing about its size can be judged)."""
    if not product:
        return None
    from .script import family_order, is_bag_family, is_banner_family
    from .slots import find_product

    order = family_order(product)
    if "type" in order:
        return FAMILIES["box"]
    if "extras" in order or is_bag_family(product):
        return FAMILIES["pouch"]
    if find_product(product) or is_banner_family(product):
        return FAMILIES["flat"]
    return None


# A dimension span: numbers (each optionally carrying a unit or a
# length/width word) joined by x / × / * / by.
_NUM = r"\d+(?:\.\d+)?"
_UNIT = r"(?:(?:inches|inch|in|feet|foot|ft|mm|cm)\b|['’\"”″])"
_WORD = r"(?:length|width|height|depth|long|wide|tall|high|deep)\b"
_ATOM = rf"{_NUM}(?:\s*-?\s*(?:{_UNIT}|{_WORD}))*"
_SEP = r"\s*(?:x|×|\*|by)\s*"
_SPAN = re.compile(rf"{_ATOM}(?:{_SEP}{_ATOM})+", re.IGNORECASE)
_SEP_SPLIT = re.compile(_SEP, re.IGNORECASE)
_GUSSET = re.compile(r"\+\s*\d|\bgusset\b", re.IGNORECASE)


def count_dimensions(sizes: str | None) -> int:
    """How many dimensions a stored/typed size carries (an optional
    +N gusset is not a separate dimension; a lone number -> 1; no
    number at all -> 0)."""
    s = (sizes or "")
    main = re.split(r"\+", s, maxsplit=1)[0]
    m = _SPAN.search(main)
    if m:
        return len(_SEP_SPLIT.split(m.group(0)))
    return 1 if re.search(r"\d", main) else 0


def has_gusset(sizes: str | None) -> bool:
    return bool(_GUSSET.search(sizes or ""))


@dataclass(frozen=True)
class SizeVerdict:
    ok: bool
    family: str | None = None
    dims: int = 0
    reason: str | None = None   # flat_extra | pouch_depth | box_too_many


_POUCH_3D = re.compile(
    rf"^({_NUM}(?:\s*{_UNIT})?{_SEP}{_NUM}(?:\s*{_UNIT})?){_SEP}({_NUM}(?:\s*{_UNIT})?)$",
    re.IGNORECASE,
)


def normalize_pouch_gusset(sizes: str | None, product: str | None) -> str | None:
    """For pouch/bag families, a 3-dimension size is width x height x GUSSET —
    store it as 'width x height + gusset' in the existing +N format ('3x3+5')."""
    if not sizes or not allows_gusset(product):
        return sizes
    if "+" in sizes:
        return sizes
    m = _POUCH_3D.match(sizes.strip())
    if m:
        w_h = m.group(1).strip()
        g_u = m.group(2).strip()
        return f"{w_h}+{g_u}"
    return sizes


def validate_size(product: str | None, sizes: str | None) -> SizeVerdict:
    """Is this size shaped right for this product's family?"""
    fam = family_of(product)
    dims = count_dimensions(sizes)
    if fam is None or not sizes:
        return SizeVerdict(True, fam.name if fam else None, dims)
    gusset = has_gusset(sizes)
    if dims >= 2 and fam.name == "flat" and (dims > fam.max_dims or gusset):
        return SizeVerdict(False, fam.name, dims, "flat_extra")
    if fam.name == "pouch":
        # A 3-dimension size without an existing gusset is width x height x gusset (valid).
        # More than 3 dimensions or a 3-dim size with an additional gusset is rejected.
        if dims > 3 or (dims > 2 and gusset):
            return SizeVerdict(False, fam.name, dims, "pouch_depth")
    if fam.name == "box" and dims > fam.max_dims:
        return SizeVerdict(False, fam.name, dims, "box_too_many")
    return SizeVerdict(True, fam.name, dims)


def _plural(product: str | None) -> str:
    word = (product or "this product").strip()
    if word.endswith(("x", "s", "ch", "sh")):
        return word + "es"
    return word + "s"


_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}


def rejection_text(verdict: SizeVerdict, product: str | None,
                   sizes: str | None) -> str:
    """The on-the-spot explanation. The re-ask (the family's own size
    question) is appended by the brain, in the visitor's language."""
    plural = _plural(product)
    # "+N" on a flat size is a third measurement too.
    total = verdict.dims + (1 if verdict.reason == "flat_extra"
                            and has_gusset(sizes) and verdict.dims == 2 else 0)
    n = _WORDS.get(total, str(total))
    shown = re.sub(r"\s+", " ", (sizes or "").strip())
    if verdict.reason == "flat_extra":
        return (f"That's {n} measurements ({shown}), but {plural} are flat "
                f"— they only have a width and a height, no depth.")
    if verdict.reason == "pouch_depth":
        return (f"That's {n} measurements ({shown}), but {plural} take at most "
                f"a width, height, and gusset (+N format).")
    return (f"That's {n} measurements ({shown}), but {plural} take at most "
            f"width x height x depth.")


# ---- family-driven helpers that replace per-product special-casing ----

def question_key(product: str | None) -> str:
    """script.QUESTIONS key of the size question for this product."""
    fam = family_of(product)
    return fam.question_key if fam else "sizes_flat"


def wants_depth_followup(product: str | None) -> bool:
    fam = family_of(product)
    return bool(fam and fam.depth_followup)


def allows_gusset(product: str | None) -> bool:
    fam = family_of(product)
    return bool(fam and fam.gusset)


def holds_contents(product: str | None) -> bool:
    fam = family_of(product)
    return bool(fam and fam.holds_contents)


def dimension_hint(product: str | None, sizes: str | None) -> str:
    """What the numbers in a size MEAN, for confirmations: the
    parenthetical after the size. Empty when there is nothing to say
    (labelled sizes, a lone number)."""
    s = sizes or ""
    if re.search(r"\b(?:length|width)\b", s, re.IGNORECASE):
        return ""
    dims = count_dimensions(s)
    if has_gusset(s) and allows_gusset(product) and dims == 2:
        return "width x height + gusset"
    if dims >= 3:
        return "width x height x depth"
    if dims == 2:
        return "width x height"
    return ""
