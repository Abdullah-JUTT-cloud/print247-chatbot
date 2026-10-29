"""Value validation for quote fields — ported from the old bot
(quoteFields.ts: isPlaceholderValue, withoutTemplateBlanks,
isOurOwnMenu, isAQuestionNotAnAnswer, isNotAnAnswerFor).

Three real failures behind these:
- The model wrote "null", "not specified", "n/a" into fields, and
  each counted as answered, so the question was never asked again.
- The ads open WhatsApp with "Hi, I need a quote for custom boxes.
  Qty: __ Size: __", sent as-is: the read recorded quantity
  "Qty: __" and size "__", and a chat closed as complete with no
  size and no quantity.
- Asked "boxes, bags, or labels?" a visitor answered "Both", and
  the read wrote back our own menu as the product.
- Asked for a box size, a visitor wrote "What is a standard package
  size", and that question was recorded as the size.
"""
import re

_ACKNOWLEDGEMENT = re.compile(
    r"^(?:o+k+a*y*|okk*|okay+|yes+|yeah|yep|ya|sure|fine|alright|cool|good|great|perfect|thanks?|thank you|k+|hmm+|right|si|sí|vale)[\s.!]*$",
    re.IGNORECASE)
_HAS_A_NUMBER = re.compile(
    r"\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen|hundred|thousand|million|single|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|cien|mil)\b",
    re.IGNORECASE)
_NOT_SURE = re.compile(
    r"\b(?:not sure|unsure|don'?t know|no idea|no s[eé]|tbd|depends|recommend|whatever|cheap|none|not given|plain)\b",
    re.IGNORECASE)


def _menu_of(items: str) -> re.Pattern:
    between = r"(?:\s*[,/]\s*(?:or\s+)?|\s+or\s+)"
    return re.compile(rf"^(?:{items})(?:{between}(?:{items}))+$", re.IGNORECASE)


_PRODUCT_MENU = _menu_of(r"box(?:es)?|bags?|labels?|pouch(?:es)?|stickers?")
_FINISH_MENU = _menu_of(r"matte|gloss|soft ?touch")


def is_ad_prompt(text: str) -> bool:
    """Wording from an ad's own pre-filled question, recorded as an
    answer: 'approx size' as the size, 'dried fruit, nuts, etc' as
    the product. A value that is an example list ('…, etc') or the
    prompt's own words is not theirs."""
    return bool(
        re.match(r"^(?:approx(?:imate)?\.?\s*)?(?:size|sizes|qty|quantity|product|dimensions?)\??$",
                 (text or "").strip(), re.IGNORECASE)
        or re.search(r"\betc\.?\)?\s*$", text or "")
        or re.match(r"^product\s*\(", (text or "").strip(), re.IGNORECASE))


def is_our_own_menu(text: str) -> bool:
    """The list we offered them, recorded as the answer they gave.
    'Any size' and neighbours are here for the same reason: they are
    the visitor declining to specify, not a dimension, and stored as
    a size they stop the bot ever asking for a real one."""
    if not text:
        return False
    t = text.strip()
    return bool(
        _PRODUCT_MENU.match(t)
        or _FINISH_MENU.match(t)
        or re.match(r"^(?:any|any of them|whatever|anything|either|both|all of them|no preference|doesn'?t matter)(?:\s+(?:size|sizes|finish|material|one|is fine|works))?$",
                    t, re.IGNORECASE))


def without_template_blanks(value: str) -> str:
    """The ad's unfilled form taken out: 'Size: __16"×10"' keeps
    16"×10"; nothing left means nothing was said."""
    return re.sub(r"^[\s.,:;\-–—]+|[\s.,:;\-–—]+$", "",
                  re.sub(r"\s+", " ",
                         re.sub(r"\b(?:qty|quantity|size|sizes)\s*:",
                                " ", re.sub(r"_{2,}", " ", value or ""),
                                flags=re.IGNORECASE))).strip()


def is_placeholder_value(value: str | None) -> bool:
    """'null', 'not specified', 'n/a', our own menu, an ad prompt, or
    a value that is nothing but template blanks. 'not sure' (they
    told us they do not know) and 'not given' (we asked twice) are
    real answers and are NOT in this list."""
    text = (value or "").strip()
    return bool(
        re.match(r"^(null|undefined|none specified|not specified|unspecified|n/?a|not stated|not mentioned|not provided|unknown|tbd)$",
                 text, re.IGNORECASE)
        or is_our_own_menu(text)
        or is_ad_prompt(text)
        or (bool(text) and not without_template_blanks(text)))


def is_a_question_not_an_answer(value: str) -> bool:
    """A field value that is the visitor's own question, copied in
    as an answer. A size on file is one the bot is told never to ask
    for again — and the rep would be handed a question where the
    dimensions belong."""
    text = (value or "").strip()
    return bool(
        re.search(r"\?\s*$", text)
        or re.match(r"^(what|what's|whats|how|which|where|when|why|who|is|are|do|does|did|can|could|would|will|should)(?!\s+not\b)\s+\S+\s+\S+",
                    text, re.IGNORECASE))


def is_not_an_answer_for(key: str, value: str | None) -> bool:
    """A value that cannot be the answer for this field, whatever
    the read made of it. 'Okayy' became a size and closed a chat as
    complete with nothing to quote; 'Y si realizan diseños' (do you
    make designs?) became the number of designs. A count has a
    number in it, or says they do not know; an acknowledgement is
    never a size, a quantity, a count, a product or a finish.
    Extras and material are left alone: 'yes' to the zipper is an
    answer there."""
    text = (value or "").strip()
    if not text:
        return False
    if key in ("sizes", "quantity", "skus", "product", "finishes") \
            and _ACKNOWLEDGEMENT.match(text):
        return True
    if key in ("quantity", "skus") \
            and not _HAS_A_NUMBER.search(text) and not _NOT_SURE.search(text):
        return True
    return False
