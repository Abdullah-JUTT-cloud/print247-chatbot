"""ERP pouch-pricing eligibility — STATIC port of the old bot
(erpPricing.ts), WITHOUT the ERP call itself.

Standing decision (unchanged): ERP instant pricing stays out of the KB
and out of visitor replies for now. The old bot priced only flat (36),
stand-up (26) and flat-bottom (25) pouches with house defaults hidden
from the visitor (PET+MPET+PE, 120 micron, white ink, full-colour
front, matte, shipment service 9) — the #1 accuracy risk. This module
answers only 'could this chat be priced, and with what disclosed
assumptions?', so the team can see eligibility on the spec brief
without the bot ever inventing a price for a visitor.

Total-vs-each: the old bot asks 'in total, or of each design?' at most
twice before pricing, because pricing 6000 bags across 3 SKUs per
design (18,000 bags) for a customer who meant 6000 in all is a
five-figure mistake. The new bot already asks per-design quantity
up front, which answers the same question earlier; these helpers
exist for transcripts where the scope was never stated.
"""
import re

POUCH_STYLES = {
    "flat": {"id": 36, "name": "flat pouch (lays flat, sealed on 3 sides)", "dimensions": 2},
    "standUp": {"id": 26, "name": "stand-up pouch (stands on its own)", "dimensions": 3},
    "flatBottom": {"id": 25, "name": "flat bottom bag (box-shaped base)", "dimensions": 3},
}
HOUSE_DEFAULTS = {
    "material": "PET + MPET + PE", "material_id": 55, "micron": 120,
    "print": "white ink, full-colour front", "finish": "matte", "shipment_service_id": 9,
}
MICRONS = [50, 70, 80, 90, 100, 110, 120, 130, 140, 150, 200]
STYLE_QUESTION = (
    "Got it. Which style would you like: a flat pouch that lays flat, a stand-up pouch that stands on its own, "
    "or a flat bottom bag with a box-shaped base?")
ASKS_TOTAL_OR_EACH = re.compile(r"\bin total, or\b", re.IGNORECASE)
_PER_DESIGN = re.compile(r"\bper design\b|\bof each\b|\beach design\b", re.IGNORECASE)
_IN_TOTAL = re.compile(r"\bin total\b|\btotal\b", re.IGNORECASE)
_POUCH_WORDS = re.compile(r"\b(pouch|pouches|mylar|stand-up|standup|flat bottom|gusset)\b", re.IGNORECASE)
_STYLE_WORDS = [
    ("flatBottom", re.compile(r"\bflat bottom\b|\bbox[- ]?bottom\b", re.IGNORECASE)),
    ("standUp", re.compile(r"\bstand[- ]?up\b|\bstands on (?:the )?shelf\b|\bstand on (?:the )?shelf\b", re.IGNORECASE)),
    ("flat", re.compile(r"\blays flat\b|\bflat pouch\b|\b3[- ]?side seal\b", re.IGNORECASE)),
]


def could_be_a_pouch(product: str | None, messages: list | None = None) -> bool:
    if product and _POUCH_WORDS.search(product):
        return True
    return any(_POUCH_WORDS.search(m or "") for m in (messages or []))


def pouch_style_for(product: str | None, messages: list | None = None, measurements: int = 0):
    """Style from their words, else from the size: two measurements is
    a flat pouch, three is a stand-up. None when unknowable."""
    if not could_be_a_pouch(product, messages):
        return None
    said = " ".join([product or ""] + list(messages or []))
    for key, pat in _STYLE_WORDS:
        if pat.search(said):
            return POUCH_STYLES[key]
    if measurements >= 3:
        return POUCH_STYLES["standUp"]
    if measurements == 2:
        return POUCH_STYLES["flat"]
    return None


def dimensions_in_inches(sizes: str | None):
    """'4 x 6 x 2 in', '100x150mm', '4\" x 6\"' -> inches, or None."""
    text = (sizes or "").lower()
    labelled = {}
    for side, value, unit in re.findall(
            r"\b(w|h|g|width|height|gusset|depth)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(inch(?:es)?|in\b|\"|mm|cm)?",
            text):
        s = "g" if side in ("depth", "g") else side[0]
        u = (unit or "in").lower()
        inches = float(value) / 25.4 if u == "mm" else float(value) / 2.54 if u == "cm" else float(value)
        if s not in labelled or u.startswith("in") or u == '"':
            labelled[s] = inches
    if "w" in labelled and "h" in labelled:
        dims = [labelled["w"], labelled["h"]] + ([labelled["g"]] if "g" in labelled else [])
        return [round(d, 2) for d in dims]
    # A trailing unit belongs to the whole size: '100x150mm' is two
    # millimetre measurements, not 100 inches by 150 millimetres.
    gm = re.search(r"(mm|cm|inch(?:es)?|in\b|\")\s*$", text)
    global_unit = (gm.group(1).lower() if gm else "")
    nums = []
    for part in re.split(r"[x×*]|by", text):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(mm|cm|inch(?:es)?|in\b|\"|)?", part)
        if m:
            v = float(m.group(1))
            u = (m.group(2) or global_unit).lower()
            nums.append(round(v / 25.4, 2) if u == "mm" else round(v / 2.54, 2) if u == "cm" else v)
    return nums or None


def quantity_is_per_design(quantity: str | None, messages: list | None = None) -> bool:
    if _PER_DESIGN.search(quantity or ""):
        return True
    return any(_PER_DESIGN.search(m or "") for m in (messages or []))


def quantity_is_total(quantity: str | None, messages: list | None = None) -> bool:
    if _IN_TOTAL.search(quantity or ""):
        return True
    return any(_IN_TOTAL.search(m or "") for m in (messages or []))


def quantity_split_question(skus: str | None, quantity: str | None, messages: list | None = None):
    """'is that N in total, or N of each of your D designs?' — at most
    twice, and only when the scope was never stated."""
    try:
        designs = int(skus or "1")
    except ValueError:
        designs = 1
    if designs < 2 or not quantity:
        return None
    if quantity_is_per_design(quantity, messages) or quantity_is_total(quantity, messages):
        return None
    asked = sum(1 for m in (messages or []) if ASKS_TOTAL_OR_EACH.search(m or ""))
    if asked >= 2:
        return None
    n = f"{int(float(str(quantity).replace(',', ''))):,}"
    if asked == 0:
        return f"Just to price it right: is that {n} in total, or {n} of each of your {designs} designs?"
    return f"Sorry, one more check: {n} in total, or {n} of each design?"


def price_request_for(slots: dict, messages: list | None = None):
    """The ERP request shape, or None when this chat cannot be priced
    yet. Needs a pouch style, a readable size with every measurement
    the style takes, and a quantity. Returns the request WITH the
    house defaults disclosed — never a price."""
    style = pouch_style_for(slots.get("product"), messages,
                            len(dimensions_in_inches(slots.get("sizes")) or []))
    if not style:
        return None
    dims = dimensions_in_inches(slots.get("sizes"))
    if not dims or len(dims) < style["dimensions"]:
        return None
    if not slots.get("quantity"):
        return None
    return {"style": style, "dimensions_inches": dims, "quantity": slots["quantity"],
            "defaults": HOUSE_DEFAULTS, "note": "ERP call itself is intentionally not made (standing decision)."}
