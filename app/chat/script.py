"""The sales script — ported from the old bot (salesScript.ts +
chatComposer.ts SCRIPT_ORDER).

The old brain asks one question at a time, in the team's order, and
never asks for something it already has, never asks two things at
once, and never asks a designs question for a plain (unprinted)
order. The family scripts are the team's own wording; the generic
order is what a code fix falls back to when the family is unclear.

Script order (generic): product -> sizes -> style -> finishes ->
quantity -> skus -> extras -> material.
Family trims: boxes skip extras (extras are a bag thing — the old
weHave rule); labels and banners skip style and extras.

A field counts as answered when the visitor said it (tracked in
meta["answered_fields"]), when it was given up after MAX_ASKS, or
when the family never asks it. skus/extras defaults ("1"/"none")
are injected by merge_slots and must NOT count as answered — the
old bot asks "How many designs?" even though skus defaults to 1,
because the default is what the rep is handed, not what the
visitor said.
"""
import re

_BANNER = re.compile(
    r"\b(banners?|pull[- ]?ups?|roll[- ]?ups?|"
    r"pop[- ]?ups?(?!\s*(?:box|boxes|card|cards|book|books|carton|cartons|mailer|mailers)\b)|"
    r"retractables?|backdrops?|step[- ]and[- ]repeat|x[- ]?stands?)\b",
    re.IGNORECASE)
_BAG = re.compile(
    r"\b(bag|bags|pouch|pouches|mylar|film|foil|roll|rolls|sachet|stand ?-?up|doypack|gusset)\b",
    re.IGNORECASE)

_PLAIN = re.compile(
    r"\b(plain|blank|unprinted|un-printed|non-printed|not printed|"
    r"no[- ]print(?:ing)?|without (?:any )?(?:print(?:ing)?|logo|branding)|"
    r"no (?:logo|branding)|no[- ]design(?!\s+(?:yet|ready|file|files|done)\b))\b",
    re.IGNORECASE)

# A question about the quote's paperwork, not the job: proofs,
# artwork files, PDFs, approval links, quote layout, delivery
# addresses, carriers. A rep sorts those out; the bot never asks.
_ABOUT_THE_QUOTE = re.compile(
    r"\b(proofs?|artwork|file names?|naming|attachments?|pdfs?|approval|"
    r"carriers?|shipping method|delivery address|ship(?:ping)? to|"
    r"line items?|grouped|grouping|organi[sz]ed?|layout|invoice|payment link)\b",
    re.IGNORECASE)

QUESTIONS = {
    "product": "What product are you looking for — for example mylar bags, pouches, boxes, or labels?",
    "sizes": "What size do you need? Width x height x depth, in inches or mm.",
    "style_bags": "What style of Mylar bag do you need: Flat, Standup or which one?",
    "style_boxes": "What style of box do you need?",
    "finishes": "What finish do you prefer: matte, gloss or soft touch?",
    "quantity": "What quantity are you looking to order for your first run?",
    "quantity_banner": "What quantity are you looking to order for your first run?",
    "skus": "How many total designs or SKU's do you have?",
    "extras": "Do you want me to add a zipper and tear notch?",
    "material": "Do you have any specific material or special features in mind?",
}

# The MOQ line the old script states WITH the quantity question on
# live chat: a visitor who has not been told it answers "maybe 50",
# which is not an order anybody can quote. Banners never get it.
MOQ_LINE = "Our standard MOQ is 1000 per size and per design, but we do smaller runs too."

# Below-minimum handling (new old-bot snapshot: SAY_THE_MINIMUM =
# false — the team takes smaller runs). Never a refusal: lead with
# what we can do, state the minimum after it.
BELOW_MIN_NOTE = "We can look at {qty} for you. " + MOQ_LINE


def is_banner_family(product: str | None) -> bool:
    return bool(product and _BANNER.search(product))


def is_bag_family(product: str | None) -> bool:
    if is_banner_family(product):
        return False
    return bool(product and _BAG.search(product))


def wants_plain_packaging(visitor_said: list) -> bool:
    """Plain = no print, no artwork, nothing on it. 'No design yet'
    is NOT plain — that visitor wants printing, they just have no
    artwork ready. Read from visitor words only, never bot words."""
    return any(_PLAIN.search(str(t or "")) for t in visitor_said)


def asks_about_the_quote(question: str) -> bool:
    return bool(_ABOUT_THE_QUOTE.search(question or ""))


def family_order(product: str | None) -> list[str]:
    """Script fields in order for this product family."""
    if not product:
        return ["product"]
    low = product.lower()
    if is_banner_family(product):
        return ["product", "sizes", "finishes", "quantity", "skus", "material"]
    if "box" in low:
        return ["product", "sizes", "style", "finishes", "quantity", "skus", "material"]
    if "label" in low or "sticker" in low:
        return ["product", "sizes", "finishes", "quantity", "skus", "material"]
    if is_bag_family(product):
        return ["product", "sizes", "style", "finishes", "quantity", "skus", "extras", "material"]
    return ["product", "sizes", "finishes", "quantity", "skus", "material"]


def _is_placeholder(value) -> bool:
    from .slots import is_placeholder

    return is_placeholder(value)


def script_missing(slots: dict, meta: dict) -> list[str]:
    """Unanswered script fields, in order.

    product/sizes/quantity: present in slots (they have no defaults).
    style/finishes/material: present in slots OR marked answered OR
    given up. skus: marked answered OR given up OR plain packaging
    (plain = no designs exist, so skus is 1 and never asked).
    extras: marked answered OR given up OR not a bag family.
    """
    product = slots.get("product")
    order = family_order(product)
    answered = set(meta.get("answered_fields") or [])
    gave_up = set(meta.get("gave_up") or [])
    plain = wants_plain_packaging(meta.get("visitor_messages") or [])
    missing = []
    for field in order:
        if field in gave_up:
            continue
        if field == "skus" and plain:
            continue
        if field == "extras" and not is_bag_family(product):
            continue
        if field in answered:
            continue
        if field in ("product", "sizes", "quantity", "style", "finishes", "material"):
            if not _is_placeholder(slots.get(field)):
                continue
        missing.append(field)
    return missing


def script_complete(slots: dict, meta: dict) -> bool:
    return not script_missing(slots, meta)


def question_for(field: str, slots: dict) -> str:
    """The script question for a field, with the family's wording."""
    if field == "style":
        return QUESTIONS["style_boxes"] if "box" in (slots.get("product") or "").lower() \
            else QUESTIONS["style_bags"]
    if field == "quantity":
        base = QUESTIONS["quantity_banner"] if is_banner_family(slots.get("product")) \
            else QUESTIONS["quantity"]
        # Old live-chat rule: state the MOQ with the quantity
        # question (banners exempt), so nobody answers "maybe 50".
        if is_banner_family(slots.get("product")):
            return base
        return base + " " + MOQ_LINE
    return QUESTIONS[field]


def per_design_quantity(slots: dict) -> bool:
    try:
        return int(slots.get("skus", "1")) > 1
    except (TypeError, ValueError):
        return False
