"""Size-unit rules — ported from the old bot (sizeUnit.ts).

A size nobody can read ('50x30' — millimetres for a label, inches for
a box) is worse than a size not yet given. The guess is written onto
the size marked '(assumed)', never presented as something they said,
so anybody who meant the other one can correct it in a word and the
rep quoting it can see the assumption rather than inheriting it
silently. Capacities count as units (12oz, 500ml); 'cmyk' is not
centimetres and 'milk' is not mils.
"""
import re

ASSUMED = "(assumed)"
_UNIT_WORD = re.compile(
    r"(?<![a-z])(mm|millimet(?:er|re)s?|cm|centimet(?:er|re)s?|mtr|met(?:er|re)s?|m|in|inch|inches|ft|feet|foot|yd|yards?|oz|ounces?|ml|millilit(?:er|re)s?|l|ltr|lit(?:er|re)s?|g|gm|grams?|grammes?|kg|kilos?|kilograms?|gsm|gallons?|lb|lbs|pounds?|pt|pints?|qt|quarts?|micron|microns|mil)(?![a-z])",
    re.IGNORECASE)
_UNIT_MARK = re.compile(r"[\"”″'’]")
_NAMED_SIZE = re.compile(r"^\s*(a\d|b\d|letter|legal|tabloid)\b", re.IGNORECASE)
_A_LABEL = re.compile(r"\b(label|sticker|decal)", re.IGNORECASE)
_A_BANNER = re.compile(r"\b(banner|pull[- ]?up|roll[- ]?up|pop[- ]?up|retractable|backdrop|x[- ]?stand|step and repeat)", re.IGNORECASE)
_MEASUREMENT = r"\d+(?:\.\d+)?\s*(?:[\"”″]|in(?:ch(?:es)?)?\b|mm\b|cm\b)?"
_JOIN = r"\s*(?:[x×*]|by)\s*"
_DIMENSIONS = re.compile(
    f"{_MEASUREMENT}{_JOIN}{_MEASUREMENT}(?:{_JOIN}{_MEASUREMENT})?(?:\\s*(?:inch(?:es)?|in\\b|mm\\b|cm\\b|[\"”″]))?",
    re.IGNORECASE)


def size_missing_unit(value: str | None) -> bool:
    size = (value or "").strip()
    if not size or not re.search(r"\d", size):
        return False
    if _NAMED_SIZE.search(size):
        return False
    return not _UNIT_WORD.search(size) and not _UNIT_MARK.search(size)


def guess_unit(value: str | None, product: str | None = None) -> str:
    """The unit a size was almost certainly meant in, or '' when there
    is nothing to go on. Banners quote in feet at the sizes people ask
    for; labels run small, so their millimetre threshold is lower."""
    size = (value or "").strip()
    if not size_missing_unit(size):
        return ""
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", size) if float(n) > 0]
    if not numbers:
        return ""
    biggest = max(numbers)
    what = product or ""
    if _A_BANNER.search(what) or _A_BANNER.search(size):
        return "ft" if biggest <= 12 else "inches"
    return "mm" if biggest >= (20 if (_A_LABEL.search(what) or _A_LABEL.search(size)) else 30) else "inches"


def tidy_size(value: str | None) -> str:
    """The measurements alone, when the read handed back the whole
    sentence ('5x7, one that can stand on the shelf' -> '5x7').
    Left as-is when there are no joined-up measurements to keep."""
    size = (value or "").strip()
    found = _DIMENSIONS.search(size)
    if not found:
        return size
    kept = found.group(0).strip()
    leftover = without_assumed_mark(size.replace(found.group(0), " "))
    if not re.sub(r"[\s,.;:()-]+", "", leftover):
        return size
    if not _UNIT_WORD.search(kept):
        unit = re.search(r"(?<![a-z])(inches|inch|in|mm|cm|ft|feet)\s*$", leftover, re.IGNORECASE)
        if unit:
            kept = f"{kept} {unit.group(1)}"
    return f"{kept}{f' {ASSUMED}' if unit_was_assumed(size) else ''}"


def size_with_assumed_unit(value: str, unit: str) -> str:
    return re.sub(r"\s+", " ", f"{(value or '').strip()} {unit} {ASSUMED}").strip()


def unit_was_assumed(value: str | None) -> bool:
    return ASSUMED in (value or "")


def without_assumed_mark(value: str | None) -> str:
    return re.sub(rf"\s*{re.escape(ASSUMED)}", "", value or "").strip()


def with_corrected_unit(value: str, unit: str) -> str:
    """Their correction to a unit we assumed: 'no, mm' replaces it."""
    return _UNIT_WORD.sub(unit, without_assumed_mark(value), count=1).strip()


def apply_unit_answer(value: str, unit: str) -> str:
    """A bare unit answer ('mm') applied to a size: replaces an
    existing unit, or appends one when the size had none. This is a
    confirmed unit, never marked (assumed)."""
    clean = without_assumed_mark(value)
    if _UNIT_WORD.search(clean):
        return _UNIT_WORD.sub(unit, clean, count=1).strip()
    return f"{clean} {unit}".strip()


def unit_answer(text: str | None) -> str:
    """The unit, when a message is nothing but a unit ('mm' in answer
    to 'is that inches, cm or mm?')."""
    m = re.match(
        r"^(mm|cm|in|inch|inches|millimet(?:er|re)s?|centimet(?:er|re)s?|ft|feet)\s*[.!]?$",
        (text or "").strip(), re.IGNORECASE)
    return m.group(1).lower() if m else ""


def size_is_not_a_size(value: str | None) -> bool:
    """A 'size' with no numbers that talks about what is standard or
    typical is the customer's own question wearing the clothes of a
    value ('standard package size' was once recorded as the size)."""
    size = (value or "").strip()
    if not size or re.search(r"\d", size):
        return False
    if _NAMED_SIZE.search(size):
        return False
    return bool(re.search(r"\b(standard|typical|usual|average|recommend(?:ed|ation)?|normal|common)\b", size, re.IGNORECASE))


def size_is_a_pack_count(value: str | None) -> bool:
    """'2 count', '10 ct', '5-pack', '30 per bag' — how many go inside,
    not the size. A value with joined-up measurements ('4x6, 2 count')
    still has a size in it and is kept."""
    size = without_assumed_mark(value or "").strip()
    if not size or _DIMENSIONS.search(size):
        return False
    return bool(re.search(r"\b\d+\s*(?:ct|count|pack)\b|\b\d+\s+per\s+bag\b", size, re.IGNORECASE))


def size_is_really_a_quantity(sizes: str | None, quantity: str | None) -> bool:
    """A single number recorded as a size that equals the quantity is
    the quantity wearing a size's clothes."""
    if not sizes or not quantity:
        return False
    nums = re.findall(r"\d+(?:\.\d+)?", sizes)
    return len(nums) == 1 and nums[0].lstrip("0") == str(quantity).lstrip("0")


def size_is_a_capacity(value: str | None) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:oz|ounces?|ml|millilit(?:er|re)s?|l|ltr|lit(?:er|re)s?|g|gm|grams?|kg)\b", value or "", re.IGNORECASE))


def already_asked_the_unit(bot_messages: list) -> bool:
    return any(re.search(r"\binches, cm or mm\b|\binch, cm, or mm\b", m or "", re.IGNORECASE)
               for m in bot_messages)
