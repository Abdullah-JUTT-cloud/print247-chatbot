"""Code guards: arithmetic and policy the LLM is never asked to do.

Ported from the old bot (src/domain/minimumOrder.ts,
src/domain/salesScript.ts). The rule lives here because a prompt
rule is followed "most of the time" — and "most of the time" is how
a customer who said "80" got thanked for an order that cannot be
produced.

MOQ rule (CHANGED Oct 30, user rule): the bot NEVER volunteers
the minimum — not with a below-minimum quantity, not in a
confirmation. A below-minimum quantity is NO LONGER a refusal:
the bot accepts the quantity, says it does smaller runs, and the
team confirms the smaller run. The 1000 figure appears only when
the visitor asks about the minimum themselves. moq_check is kept
for reporting (is a quantity below the minimum?) — it no longer
blocks a quote and its message no longer states the minimum.
Banners are exempt from the minimum entirely, with the full banner
family (pull-ups, roll-ups, pop-ups, retractables, backdrops,
x-stands), not just the word "banner".
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
    accepts it and carries on — it never refuses, and never states
    the minimum unless asked). No quantity yet -> ok. Banners ->
    ok (no minimum at all).
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
            f"We can look at {qty} for you. We do smaller runs too."
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
