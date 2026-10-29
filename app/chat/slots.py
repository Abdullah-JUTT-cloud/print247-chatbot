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

FIELDS = ["product", "material", "sizes", "finishes", "quantity", "extras", "skus", "style"]
# "style" is a script question, not one of the old 7 quote fields:
# the bag/box style question ("Flat, Standup or which one?") is
# asked after sizes, and its answer is stored here, never guessed.
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
    ("bag", ["bag", "bags", "bolsa", "bolsas"]),
    ("box", ["box", "boxes", "carton", "cartons", "caja", "cajas"]),
    ("label", ["label", "labels", "etiqueta", "etiquetas"]),
    ("sticker", ["sticker", "stickers"]),
    ("business card", ["business card", "business cards"]),
    ("banner", ["banner", "banners"]),
]

_MATERIALS = [
    "kraft", "pet", "mpet", "pe", "foil", "vinyl", "cardboard",
    "corrugated", "matte bopp", "sbs", "plastic", "paper",
    # Rigid chipboard is a real box material (boxes.md: 32-80pt):
    # "plain rigid box" as a material answer must store it, not loop.
    "rigid",
]

_FINISHES = [
    ("spot uv", ["spot uv"]),
    ("foil stamping", ["foil stamping", "gold foil", "foil"]),
    ("embossing", ["embossing"]),
    ("matte", ["matte"]),
    ("gloss", ["gloss", "glossy"]),
    ("soft touch", ["soft touch", "soft-touch", "softtouch"]),
    ("none", ["no finish", "without finish"]),
]

_EXTRAS = [
    ("zipper", ["zipper", "ziplock", "zip lock"]),
    ("tear notch", ["tear notch"]),
    ("hang hole", ["hang hole"]),
    ("window", ["window"]),
]

_PACK_COUNT = re.compile(
    r"\b\d+\s*(?:ct|count|pack|capsules?)\b", re.IGNORECASE)
# NOTE: "pcs"/"pieces" were in this list and are NOT here on purpose:
# "5000 pcs" is an order quantity, not a pack format — stripping it
# left the quantity empty. "10 ct" / "10pack" stay stripped: those
# are pack formats inside a product description, not quantities.
_SIZE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:x|×|by|\*)\s*\d+(?:\.\d+)?"
    r"(?:\s*(?:x|×|by|\*)\s*\d+(?:\.\d+)?)?\s*(?:inches?|in\b|mm|cm|feet|ft\b)?",
    re.IGNORECASE)
# Spelled-out dimensions ("10 inches length and 6 inches width",
# "6 inches wide, 10 inches long"): _SIZE needs an x/by/* between
# the numbers, so this phrasing fell through — and then "10" leaked
# into quantity while the size stayed missing (live transcript,
# Oct 29). Same shape, both orders, hyphen tolerated ("10-inch
# length"). Stored WITH its labels + unit, never bare NxM: a bare
# "10x6" never says which number is the length, and the rep (or the
# confirmation) would have to guess (Oct 30).
_LW = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*-?\s*(inches?|in\b|mm|cm)?\s*(?:length|long)\b"
    r"\s*(?:and|,)?\s*"
    r"(\d+(?:\.\d+)?)\s*-?\s*(inches?|in\b|mm|cm)?\s*(?:width|wide)\b"
    r"|\b(\d+(?:\.\d+)?)\s*-?\s*(inches?|in\b|mm|cm)?\s*(?:width|wide)\b"
    r"\s*(?:and|,)?\s*"
    r"(\d+(?:\.\d+)?)\s*-?\s*(inches?|in\b|mm|cm)?\s*(?:length|long)\b",
    re.IGNORECASE)
_UNIT_WORD = {"in": " inches", "inch": " inches", "inches": " inches",
              "mm": " mm", "cm": " cm"}
# A unit on EACH measurement ("1 feet by 2 feet", "10 inches x 6
# inches", "1 ft x 2 ft"): _SIZE only allows the unit at the very
# end, so the first number leaked into quantity while the size
# stayed missing (live transcript, Oct 30). Matching units
# normalize to NxM + unit; differing units keep the raw span
# verbatim — "1 feet by 20 inches" must never become "1x20 feet".
_EACH_UNIT = r"(?:feet|foot|inches|inch|mm|cm|ft|in|['’\"”″])"
_SIZE_EACH = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(" + _EACH_UNIT + r")\s*(?:x|×|by|\*)\s*"
    r"(\d+(?:\.\d+)?)\s*(" + _EACH_UNIT + r")?"
    r"(?:\s*(?:x|×|by|\*)\s*(\d+(?:\.\d+)?)\s*(" + _EACH_UNIT + r")?)?",
    re.IGNORECASE)
_EACH_CANON = {"feet": "feet", "foot": "feet", "ft": "feet",
               "inches": "inches", "inch": "inches", "in": "inches",
               "mm": "mm", "cm": "cm",
               "'": "feet", "’": "feet",
               '"': "inches", "”": "inches", "″": "inches"}
# Named paper sizes are sizes, not quantities: "A4" must never leak
# its 4 into quantity (old NAMED_SIZE guard, same idea). Only A/B
# sizes are stored as sizes — "letter"/"legal" also name document
# kinds, so they are stripped from quantity search only, never
# stored as a size.
_PAPER_SIZE = re.compile(r"\b[AB]\d\b", re.IGNORECASE)
_NAMED_SIZE = re.compile(r"\b(?:a\d|b\d|letter|legal|tabloid)\b", re.IGNORECASE)
# Capacities are not quantities: "12oz pouch" is a capacity, not
# an order of 12 (old UNIT_WORD capacity note, same idea).
_CAPACITY = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:oz|ounces?|ml|millilit(?:er|re)s?|l|ltr|"
    r"lit(?:er|re)s?|g|gm|grams?|grammes?|kg|kilos?|kilograms?)\b",
    re.IGNORECASE)


def _each_unit_size(low: str) -> str | None:
    m = _SIZE_EACH.search(low)
    if not m:
        return None
    n1, u1, n2, u2, n3, u3 = m.groups()
    units = [_EACH_CANON.get((u or "").lower()) for u in (u1, u2, u3)]
    units = [u for u in units if u]
    if units and len(set(units)) == 1:
        dims = "x".join(d for d in (n1, n2, n3) if d is not None)
        return f"{dims} {units[0]}"
    return m.group(0).strip()


def _lw_size(low: str) -> str | None:
    m = _LW.search(low)
    if not m:
        return None
    gs = m.groups()
    if gs[0] is not None:
        n1, u1, n2, u2 = gs[0], gs[1], gs[2], gs[3]
        labels = ("length", "width")
    else:
        n1, u1, n2, u2 = gs[4], gs[5], gs[6], gs[7]
        labels = ("width", "length")
    unit = _UNIT_WORD.get((u1 or u2 or "").lower().strip(), "")
    return f"{n1} {labels[0]} x {n2} {labels[1]}{unit}"
# A rejected option must never be stored as the choice: "not matte"
# stored matte, "without zipper" stored zipper. The negation is
# checked right before the label, so "zipper, no window" still keeps
# the zipper and only drops the window.
def mylar_like(text: str) -> bool:
    """A token that is 'mylar' misspelled ('milar', 'mylarr',
    'maylar'): 'milar bags' must be a mylar bag, not a plain bag —
    the exact table matches 'bags' first and would call it 'bag'."""
    import difflib

    for token in re.findall(r"[a-z]+", (text or "").lower()):
        if len(token) < 4:
            continue
        if sorted(token) == sorted("mylar"):
            return True
        if difflib.SequenceMatcher(None, token, "mylar").ratio() >= 0.8:
            return True
    return False


def _word_match(token: str, word: str) -> float:
    """Similarity of one token to one alias word: 1.0 on a
    transposition (sorted letters equal — 'lables' vs 'labels' is
    0.83 by difflib, same letters, two swapped), else difflib."""
    import difflib

    if sorted(token) == sorted(word):
        return 1.0
    return difflib.SequenceMatcher(None, token, word).ratio()


def fuzzy_product(text: str) -> str | None:
    """A misspelled product, matched when the exact table misses:
    'lables' -> label, 'milar bags' -> mylar bag, 'puches' ->
    pouch. Single-word aliases match one token (ratio >= 0.85).
    Multi-word aliases need EVERY word matched by some token —
    otherwise a style answer hijacks the product: 'flat-bottom'
    matched the word 'flat' in 'flat pouch', and 'stand-up'
    matched 'stand' in 'stand up pouch', flipping boxes and mylar
    bags into pouches mid-flow. Only when the exact table found
    nothing — so a real word never loses to a near-miss."""
    low = (text or "").lower()
    tokens = [t for t in re.findall(r"[a-z]+", low) if len(t) >= 4]
    tokens_all = re.findall(r"[a-z]+", low)
    best = None
    for canonical, aliases in _PRODUCTS:
        for alias in aliases:
            words = alias.split()
            if len(words) == 1:
                if len(words[0]) < 4:
                    continue
                for token in tokens:
                    r = _word_match(token, words[0])
                    if r >= 0.85 and (best is None or r > best[0]):
                        best = (r, canonical)
            else:
                rs = []
                for word in words:
                    if len(word) < 4:
                        rs.append(1.0 if word in tokens_all else 0.0)
                    else:
                        rs.append(max((_word_match(t, word) for t in tokens),
                                      default=0.0))
                if rs and min(rs) >= 0.8:
                    r = min(rs)
                    if best is None or r > best[0]:
                        best = (r, canonical)
    return best[1] if best else None


def _negated_labels(text: str, labels: list[str]) -> set[str]:
    low = (text or "").lower()
    out = set()
    for label in labels:
        if re.search(r"\b(?:not|no|without|never|anything but|except|dont|don't|do not)"
                     r"(?:\s+want)?\s+(?:a\s+|an\s+|the\s+)?"
                     + re.escape(label) + r"\b", low):
            out.add(label)
    return out
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
    # Length/width spans too: "10 inches length and 6 inches width"
    # otherwise leaks its 10 into quantity while the size is lost.
    # Each-unit spans ("1 feet by 2 feet"), named sizes ("A4") and
    # capacities ("12oz") are stripped for the same reason.
    cleaned = _LW.sub(" ", cleaned)
    cleaned = _SIZE_EACH.sub(" ", cleaned)
    cleaned = _SIZE.sub(" ", cleaned)
    cleaned = _NAMED_SIZE.sub(" ", cleaned)
    cleaned = _CAPACITY.sub(" ", cleaned)
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

# Pouch/box styles from the campaign KB (mylar styles file). The
# gallery-only "spout pouch" is NOT offered by the bot as a choice,
# but a visitor who asks for it outright has their style recorded
# for the team — refusing their own words would be worse.
_STYLE_WORDS = [
    ("side gusset", "side gusset"),
    ("pinch bottom", "pinch bottom"),
    ("flat-bottom", "flat-bottom"),
    ("flat bottom", "flat-bottom"),
    ("stand-up", "stand-up"),
    ("stand up", "stand-up"),
    ("standup", "stand-up"),
    ("spout", "spout"),
    ("3-side", "flat"),
    # Box style chips the bot itself offers (Oct 30 transcript):
    # NONE of these parsed, so the box style question looped twice
    # and gave up on every box quote. A chip the bot shows must
    # always be a value the parser accepts.
    ("mailer", "mailer"),
    ("tuck-end", "tuck-end"),
    ("tuck end", "tuck-end"),
    ("folding carton", "folding carton"),
    ("folding", "folding carton"),
    ("rigid", "rigid"),
]


def _style_in(text: str) -> str | None:
    low = (text or "").lower()
    for word, label in _STYLE_WORDS:
        if word in low:
            return label
    return None


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
    # Spanish units read as their English equivalents ("4x6
    # pulgadas" is 4x6 inches, not a unit-less size).
    low = (text or "").lower().replace("pulgadas", "inches").replace(
        "centímetros", "cm").replace("centimetros", "cm").replace(
        "milímetros", "mm").replace("milimetros", "mm")
    out: dict = {}
    product = _find(low, _PRODUCTS) or fuzzy_product(low)
    if product == "bag" and mylar_like(low):
        product = "mylar bag"
    if product:
        out["product"] = product
    for mat in _MATERIALS:
        if re.search(rf"\b{re.escape(mat)}\b", low):
            if mat in _negated_labels(text, [mat]):
                continue
            out["material"] = mat
            break
    lw = _lw_size(low)
    if lw:
        out["sizes"] = lw
    else:
        each = _each_unit_size(low)
        if each:
            out["sizes"] = each
        else:
            size = _SIZE.search(low)
            if size and not _PACK_COUNT.search(low.split("x")[0] if "x" in low else low):
                out["sizes"] = size.group(0).strip()
            else:
                paper = _PAPER_SIZE.search(low)
                if paper:
                    out["sizes"] = paper.group(0).upper()
    finish = _find(low, _FINISHES)
    if finish:
        out["finishes"] = normalise_finish(finish)
    elif re.search(r"\bmate\b", low):
        # Spanish "mate" = matte. Word-boundary only: "material"
        # contains "mate" and must never become a finish.
        out["finishes"] = "matte"
    else:
        slip = finish_in(low)
        if slip:
            out["finishes"] = slip
    if out.get("finishes") and out["finishes"] in _negated_labels(text, [out["finishes"]]):
        # "not matte" is a rejection, not a choice — leave the finish
        # open so the bot asks again instead of recording matte.
        out.pop("finishes")
    qty = _quantity_in(text)
    if qty:
        out["quantity"] = qty
    extras = [label for label, keys in _EXTRAS if any(k in low for k in keys)]
    if extras:
        neg = _negated_labels(text, extras)
        extras = [e for e in extras if e not in neg]
        if extras:
            out["extras"] = ", ".join(extras)
        elif not (out.get("product") or out.get("sizes") or out.get("quantity")):
            # A bare rejection ("without zipper") answers the extras
            # question with "none". But "I need bags, no window"
            # carries an order too — there the extras question is
            # still open, so nothing is stored for it.
            out["extras"] = "none"
    skus = _skus_in(text)
    if skus:
        out["skus"] = skus
    style = _style_in(text)
    if style:
        out["style"] = style
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
