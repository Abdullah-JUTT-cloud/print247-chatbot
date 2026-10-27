"""Code guards: arithmetic and policy the LLM is never asked to do.

Ported from the old bot (src/domain/minimumOrder.ts,
src/domain/salesScript.ts). The rule lives here because a prompt
rule is followed "most of the time" — and "most of the time" is how
a customer who said "80" got thanked for an order that cannot be
produced.

MOQ rule (PENDING sales sign-off, see kb/facts/moq.md):
  minimum 1000 per size, banners exempt. The old code's "500 each
  for multiple designs" rule is NOT applied here — it is unresolved
  in the sales-team questions, and applying an unconfirmed discount
  rule would be inventing policy.
"""
import re

MINIMUM_ORDER = 1000

_BANNER = re.compile(r"\bbanners?\b", re.IGNORECASE)
_HUMAN = re.compile(
    r"\b(human|agent|representative|rep|real person|call me|phone me)\b",
    re.IGNORECASE)
_POLICY_TOPICS = re.compile(
    r"\b(refund|return|cancel|reprint|payment terms|privacy|terms of service)\b",
    re.IGNORECASE)


def minimum_applies(product: str | None) -> bool:
    return not (product and _BANNER.search(product))


def moq_check(slots: dict) -> dict:
    """Return {'ok': bool, 'message': str|None}.

    ok=False only when a real quantity below the minimum was given
    and the minimum applies. No quantity yet -> ok (nothing to check).
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
            f"Our minimum order is {MINIMUM_ORDER} units per size, "
            f"so {qty} units is below the minimum. "
            f"Would {MINIMUM_ORDER} units work, or a different size?"
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
    """Quote-ready: product + sizes + quantity, MOQ satisfied."""
    from .slots import missing_fields

    return not missing_fields(slots) and moq_check(slots)["ok"]
