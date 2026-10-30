"""Query normalization (Oct 30, user's call): spelling mistakes in
the visitor's query are fixed automatically, and an incomplete
utterance gets a "did you mean" confirmation instead of a wrong
answer or a bare team-confirm.

Two rules keep this safe:

1. Typo correction is CONSERVATIVE and deterministic (difflib,
   stdlib only): a word is corrected only when it is a near-miss
   (ratio >= 0.8, length >= 4) of a DOMAIN vocabulary word. Numbers,
   dimensions, names, and ordinary words are never touched:
   "cart" stays "cart" (0.75 to "card"), "code" stays "code",
   "100x150mm" is skipped (digits), "Rosenberg" matches nothing.
   The correction is used for MATCHING (intents, retrieval, slot
   extraction); the visitor's original words stay in history.

2. A "did you mean" confirmation fires ONLY when the bot would
   otherwise fail: the message is a fragment, retrieval finds
   nothing, and an interpretation exists (a product in context or
   in the fragment). Fragments that already match something
   ("for coffee" -> pouches, "matte" -> a finish answer) flow
   normally and are never interrupted by a confirmation.
"""

import difflib
import re
import unicodedata


def _plain(text: str) -> str:
    """Lowercased ASCII-folded text: 'sí' reads as 'si' so accent
    variants of answers never look like fragments."""
    return unicodedata.normalize(
        "NFKD", text or "").encode("ascii", "ignore").decode().lower()

# The full domain lexicon — every legitimate domain word is an
# entry, so it is SKIPPED by membership (never "corrected" away)
# and a typo of it corrects TO it. A partial lexicon is what
# broke things: "touch" was missing, so "Soft touch" became
# "Soft pouch" (touch -> pouch is 0.8), and "spot" was missing,
# so "spot UV" would have become "spout UV". Hyphenated forms
# are entries too ("stand-up" corrects "standup").
VOCAB = {
    # products
    "pouch", "pouches", "mylar", "label", "labels", "sticker", "stickers",
    "box", "boxes", "carton", "cartons", "banner", "banners", "card",
    "cards", "bag", "bags", "sign", "signs", "pack", "packs",
    # types / styles
    "mailer", "tuck-end", "folding", "corrugated", "rigid", "display",
    "metalized", "cosmetic", "pharmaceutical", "apparel", "stand-up",
    "flat-bottom", "flat", "spout", "child-resistant", "gusset",
    "dispenser", "kraft", "tuck", "straight", "reverse", "crash",
    "lock", "snap", "gable", "window", "cutouts", "hang", "tabs",
    "perforated", "double", "wall",
    # materials / finishes
    "vinyl", "paper", "film", "foil", "bopp", "holographic", "matte",
    "gloss", "lamination", "embossing", "soft-touch", "soft", "touch",
    "paperboard", "sbs", "zipper", "notch", "tear", "heat", "seal",
    "valve", "spot", "stamping", "gold", "copper", "rose", "drip",
    "white", "clear", "silver", "barrier", "high", "asset",
    "equipment", "transparent", "resistant", "waterproof", "outdoor",
    "security",
    # uses / contents
    "beverage", "whiskey", "wine", "coffee", "chocolate", "vape",
    "cbd",
    # business words
    "delivery", "shipping", "payment", "paypal", "zelle", "quantity",
    "design", "designs", "artwork", "sample", "samples", "quote",
    "turnaround", "refund", "packaging", "business",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z\-]*")

# Words that must NEVER be corrected: every word appearing in a
# retrieval exact-topic key (computed, so it stays in sync), plus
# two hand-found traps. A key word corrected into another word
# breaks routing: "stick" -> "sticker" (0.83) killed the
# labels-bottle key "stick to bottle"; "deliver" -> "delivery"
# (0.93) mangles the shipping key. Typos OF a key word still
# correct (NEVER is exact-match only).
try:
    from .retrieval import _EXACT_TOPICS as _TOPICS

    _KEY_WORDS = set()
    for _keys in _TOPICS.values():
        for _k in _keys:
            _kk = _k[2:] if _k.startswith("w:") else _k
            for _w in re.findall(r"[a-z]+", _kk):
                if len(_w) >= 4:
                    _KEY_WORDS.add(_w)
except Exception:
    _KEY_WORDS = set()
# "cares" -> "cards" (0.8) would turn a dismissive "who cares"
# into a business-cards pitch; "cart" -> "card" is the same trap
# class (found in the golden probe).
NEVER = _KEY_WORDS | {"cares", "cart",
                       # Oct 31 clock fix: "clock" was auto-corrected
                       # to "lock" (crash-lock/zip-lock vocab, ratio
                       # 0.89), which silently broke every clock-time
                       # question ("time on clock" -> "time on lock").
                       # Same class as the touch->pouch trap: a real
                       # English word must never become a domain term.
                       "clock"}

# Words that are never fragments on their own: answers, greetings,
# thanks — a bare "yes" must reach the script/contact logic, never
# a "did you mean" question.
_NOT_FRAGMENT = {
    "yes", "yeah", "yep", "ok", "okay", "sure", "no", "nope", "haan",
    "han", "ji", "si", "hi", "hello", "hey", "salam", "thanks", "shukriya",
    "bye",
}

_TRAILING = {"for", "and", "with", "in", "of", "to", "or", "ke", "ka", "ki"}
_LEADING_PREP = {"for", "with", "in"}

_PRODUCT_WORDS = {
    "box": "box", "boxes": "box",
    "pouch": "pouch", "pouches": "pouch", "mylar": "mylar",
    "label": "label", "labels": "label",
    "banner": "banner", "banners": "banner",
    "card": "business-cards", "cards": "business-cards",
}

_PLURAL = {
    "box": "boxes", "pouch": "pouches", "mylar": "mylar pouches",
    "label": "labels", "banner": "banners",
    "business-cards": "business cards",
}


def correct_query(text: str) -> str:
    """Replace near-miss domain words with the vocabulary word.
    Everything else (numbers, dimensions, names, real words) passes
    through untouched."""

    def _fix(m):
        w = m.group(0)
        lw = w.lower()
        if len(lw) < 4 or lw in VOCAB or lw in NEVER:
            return w
        # sorted() so a tie between two vocab words resolves the
        # same way on every run (a set would order ties randomly).
        best = difflib.get_close_matches(lw, sorted(VOCAB), n=1, cutoff=0.8)
        return best[0] if best else w

    return _WORD.sub(_fix, text or "")


def is_fragment(text: str) -> bool:
    """True when the message is an incomplete utterance: trailing
    off ("I need boxes for..."), a dangling word ("boxes for"), a
    leading prepositional fragment ("for candles"), or a single
    content word. Numbers, dimensions, answers, and greetings are
    never fragments."""
    t = _plain(text).strip()
    if not t:
        return False
    if any(ch.isdigit() for ch in t):
        return False
    if t.endswith("...") or t.endswith("…"):
        return True
    words = re.findall(r"[a-z']+", t)
    if not words:
        return False
    if len(words) == 1 and words[0] in _NOT_FRAGMENT:
        return False
    if words[-1] in _TRAILING:
        return True
    if len(words) <= 3 and words[0] in _LEADING_PREP:
        return True
    if len(words) == 1:
        return True
    return False


def _content_words(text: str) -> list[str]:
    """Fragment words with trailing markers, dangling words, and a
    leading preposition stripped — the part worth interpreting."""
    t = (text or "").strip().lower()
    t = re.sub(r"\.{3,}|…+$", "", t).strip()
    words = re.findall(r"[a-z][a-z\-']*", t)
    while words and words[-1] in _TRAILING:
        words.pop()
    while words and words[0] in _LEADING_PREP:
        words.pop(0)
    return words


def interpret_fragment(text: str, product: str | None) -> tuple[str, str] | None:
    """Build (display, question) for a fragment, or None when no
    confident interpretation exists. The product comes from the
    session context, else from a product word inside the fragment.
    Without a product there is no interpretation — the normal
    fallback (product question) is the honest response there."""
    words = _content_words(text)
    if not words:
        return None
    prod = product
    if not prod:
        for w in words:
            if w in _PRODUCT_WORDS:
                prod = _PRODUCT_WORDS[w]
                break
    if not prod:
        return None
    content = [w for w in words if w not in _PRODUCT_WORDS]
    if not content:
        return None
    plural = _PLURAL.get(prod, prod + "s")
    display = f"{plural} for {' '.join(content)}"
    return display, f"do you make {display}?"


def fragment_product(text: str, product: str | None) -> str | None:
    """The product an interpretation would use: the session product,
    else a product word inside the fragment. Kept separate from
    interpret_fragment so the trigger can store it for the yes
    handler without changing interpret_fragment's return shape."""
    if product:
        return product
    for w in _content_words(text):
        if w in _PRODUCT_WORDS:
            return _PRODUCT_WORDS[w]
    return None


# Words that keep a message from looking like gibberish even when
# it names no product: question words + business words. A real
# question ("what is your return policy?") has no vocab word.
_COMMON_WORDS = {
    "i", "need", "want", "do", "does", "you", "make", "have", "get",
    "can", "could", "would", "will", "please", "thanks", "thank", "hi",
    "hello", "hey", "yes", "no", "my", "order", "price", "much", "how",
    "what", "when", "where", "is", "are", "for", "with", "in", "on",
    "to", "a", "an", "the", "this", "that", "it", "me", "us", "we",
    "your", "our", "about", "return", "policy", "shipping", "delivery",
    "payment", "pay", "cost", "time", "long", "take", "arrive", "open",
    "close", "hours", "located", "company", "name", "email", "phone",
    "stop", "bye", "ok", "okay", "sure", "si", "minimum", "moq",
    "sample", "samples", "quote", "size", "sizes", "quantity", "finish",
    "material", "style", "type", "design", "designs", "color", "colour",
    "help", "info", "information", "details", "website", "store", "shop",
    # Number + unit words: a spelled quantity ("fifteen thousand",
    # "two thousand units") is an answer, never mash.
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
    "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
    "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "thousand", "million",
    "unit", "units", "pcs", "pieces",
}
_UNIT_WORDS = {"mm", "cm", "inches", "inch", "in", "feet", "ft", "oz",
               "ml", "kg", "g", "lb", "lbs", "pt"}
# Spanish is the supported second language: its words are not in
# the English vocab, so a Spanish message must never read as mash.
_SPANISH_WORDS = {
    "necesito", "quiero", "quisiera", "cajas", "caja", "bolsas",
    "bolsa", "para", "grandes", "grande", "pequeno", "pequena",
    "pequenos", "pulgadas", "centimetros", "milimetros", "gracias",
    "hola", "etiquetas", "botellas",
}


def is_gibberish(text: str) -> bool:
    """True when no word in the message is recognizable: no domain
    word (exact or near, ratio >= 0.7), no common word, no unit,
    no Spanish word. Random keyboard mash ("jfdlsnvipojfn ...")
    must get a clarification, never a product pitch — the live
    stack once answered mash with a food-box suggestion. At least
    one word of length >= 4 must be present: short noise ("xyz")
    falls through to the normal product question instead. Any
    digit exempts the message outright: quantities and dimensions
    ("15 thousand", "4x6") are answers, never mash."""
    if re.search(r"\d", text or ""):
        return False
    tokens = re.findall(r"[a-z]+", _plain(text))
    if not tokens or not any(len(t) >= 4 for t in tokens):
        return False
    for tok in tokens:
        if tok in _COMMON_WORDS or tok in _UNIT_WORDS \
                or tok in _SPANISH_WORDS or tok in VOCAB:
            return False
        if any(difflib.SequenceMatcher(None, tok, v).ratio() >= 0.7
               for v in VOCAB):
            return False
    return True


def is_use_fragment(text: str) -> bool:
    """Trigger gate for did-you-mean: a USE/purpose phrase, not a
    bare word. Bare single words are answers (a name, a unit,
    'stop', 'sí') or non-answers the pending question re-asks —
    the trigger must never swallow them (it did, and broke the
    contact flow, the stop flow, the unit question, and the
    Spanish switch answer). A leading preposition ('for candles')
    or a dangling one ('boxes for') is a new piece of
    information, not an answer to the pending question."""
    t = _plain(text).strip()
    if not t or any(ch.isdigit() for ch in t):
        return False
    words = re.findall(r"[a-z']+", t)
    if not words:
        return False
    if words[0] in _LEADING_PREP:
        return True
    if words[-1] in _TRAILING:
        return True
    return False
