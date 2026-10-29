"""Code guards: arithmetic and policy the LLM is never asked to do.

Ported from the old bot (src/domain/minimumOrder.ts,
src/domain/salesScript.ts). The rule lives here because a prompt
rule is followed "most of the time" — and "most of the time" is how
a customer who said "80" got thanked for an order that cannot be
produced.

MOQ rule (CHANGED with the full old-brain port, Oct 29): the new
old-bot snapshot takes smaller runs (SAY_THE_MINIMUM = false) and
its composer forbids a flat refusal ("Lead with what we can do —
that we can look at their quantity — and give the minimum after
it"). So a below-minimum quantity is NO LONGER a refusal: the bot
states the minimum once, accepts the quantity, and the team
confirms the smaller run. moq_check is kept for reporting (is a
quantity below the minimum?) and for the confirmation note — it
no longer blocks a quote. Banners are exempt from the minimum
entirely, with the full banner family (pull-ups, roll-ups, pop-ups,
retractables, backdrops, x-stands), not just the word "banner".
"""
import re

from .script import is_banner_family

MINIMUM_ORDER = 1000

_HUMAN = re.compile(
    r"\b(human|agent|representative|rep|real person|call me|phone me)\b",
    re.IGNORECASE)
_POLICY_TOPICS = re.compile(
    r"\b(refund|return|cancel|reprint|payment terms|privacy|terms of service)\b",
    re.IGNORECASE)


def minimum_applies(product: str | None) -> bool:
    return not is_banner_family(product)


def moq_check(slots: dict) -> dict:
    """Return {'ok': bool, 'message': str|None}.

    ok=False now only REPORTS a below-minimum quantity (the brain
    states the minimum and carries on — it never refuses). No
    quantity yet -> ok. Banners -> ok (no minimum at all).
    """
    qty_raw = slots.get("quantity")
    if not qty_raw:
        return {"ok": True, "message": None}
    try:
        qty = int(float(str(qty_raw).replace(",", "")))
    except ValueError:
        return {"ok": True, "message": None}
    if not minimum_applies(slots.get("product")):
        return {"ok": True, "message": None}
    if qty >= MINIMUM_ORDER:
        return {"ok": True, "message": None}
    return {
        "ok": False,
        "message": (
            f"We can look at {qty} for you. Our standard MOQ is "
            f"{MINIMUM_ORDER} per size and per design, but we do smaller runs too."
        ),
    }


def handoff_reason(text: str, slots: dict) -> str | None:
    """Why this chat must go to a human, or None.

    Policy gap: print247.us publishes NO refund/return/cancellation
    policy, so the bot must never invent one — it hands off instead.
    """
    if _POLICY_TOPICS.search(text or ""):
        return "policy_question"
    if _HUMAN.search(text or ""):
        return "visitor_asked_for_human"
    return None


def is_complete(slots: dict) -> bool:
    """Quote-ready: product + sizes + quantity present. The MOQ no
    longer blocks (see module docstring); the full script gate is
    script.script_complete, which also requires finishes/skus/
    extras/material/style to be answered, given up, or not asked."""
    from .slots import missing_fields

    return not missing_fields(slots)
