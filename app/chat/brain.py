"""The chat brain: one pipeline, in this order, every message.

  1. Language detect (heuristic).
  2. Slot extraction + merge with the session's collected slots.
  3. Code guards: MOQ arithmetic, handoff triggers.
  4. RAG retrieval: exact topic first, then vector, then keyword.
  5. Answer:
       - handoff needed  -> say so, do not invent. POLICY RULE
         (narrowed, Oct 2026): a policy question is answered from
         the policy OKF file when retrieval finds one; handoff
         happens ONLY when no policy file covers the question.
       - MOQ failed     -> state the minimum, do not accept silently.
       - OPENAI key set -> gpt-5-mini writes the reply, using ONLY
         the retrieved OKF facts + slots + guard verdicts. It is told
         to say "confirm with the team" when a fact is not in them.
       - no key         -> deterministic reply: next missing-field
         question, or a retrieved fact. This is honest, not a fake
         sales answer, and it lets the whole pipeline be tested
         without spending a cent.

State: slots live in Mongo per session_id when Mongo is up; if it
is down, the chat still works for this message (state just does not
persist). A missing database must never break a visitor's chat.
"""
import os

from . import guards
from .language import detect_language
from .retrieval import retrieve
from .slots import extract_from_message, merge_slots, missing_fields

QUESTIONS = {
    "product": "What product are you looking for — for example mylar bags, pouches, boxes, or labels?",
    "sizes": "What size do you need? Width x height x depth, in inches or mm.",
    "quantity": "How many units do you need?",
}

def _suggestions(slots: dict, missing: list[str], reply: str = "") -> list[str]:
    """Clickable next steps shown under every bot reply.

    They follow the quote flow, not a random list: if the product
    is missing, suggest products; if sizes are missing, suggest
    sizes; if quantity is missing, suggest quantities; otherwise
    suggest the most-asked fact questions. The UI renders these as
    chips, so a visitor can continue in one tap instead of typing.

    Special case: a confirmation reply ("Just to confirm — do you
    want …?") gets Yes / Change chips, not generic fact questions
    — generic chips under a confirmation were a dead end in the
    first live transcript, because tapping one abandoned the quote.
    """
    low_reply = (reply or "").lower()
    if "just to confirm" in low_reply or "do you want" in low_reply:
        return ["Yes, that's correct", "Change quantity", "Change size"]
    if "product" in missing:
        return ["I need mylar bags", "I need custom boxes", "I need labels"]
    if "sizes" in missing:
        return ["Size 4x6 inches", "Size 100x150mm", "Not sure about size"]
    if "quantity" in missing:
        return ["1000 units", "5000 units", "Not sure about quantity"]
    return ["What is the minimum order?", "Is shipping free?",
            "What is your refund policy?"]


def _slot_sources(slots: dict) -> list[str]:
    """Clean sources for a slot-collection step.

    Keyword fallback ranked unrelated files here (a "Size 4x6
    inches" message returned banners.md, because it mentions size
    a lot). When the bot is just collecting the next field, the
    honest sources are the product file and the sizes file, not
    whatever the keyword search happened to rank.
    """
    out: list[str] = []
    product = (slots.get("product") or "").lower()
    if "mylar" in product or "pouch" in product:
        out.append("kb/products/pouches.md")
    elif "box" in product:
        out.append("kb/products/boxes.md")
    elif "label" in product or "sticker" in product:
        out.append("kb/products/labels.md")
    elif "banner" in product:
        out.append("kb/products/banners.md")
    elif "business card" in product:
        out.append("kb/products/business-cards.md")
    if slots.get("sizes"):
        out.append("kb/facts/sizes.md")
    return out


_POLICY_BEYOND_HANDOFF = (
    "That is a good question, and I do not want to give you a wrong "
    "answer: that detail is not in our published policy, so I am "
    "passing this to our team. They will confirm it directly. "
    "In the meantime, is there anything else about your order I can help with?"
)


def _load_session(store, session_id: str | None) -> dict:
    if not session_id or store is None:
        return {}
    try:
        return store.load(session_id) or {}
    except Exception:
        return {}


def _save_session(store, session_id: str | None, slots: dict) -> None:
    if not session_id or store is None:
        return
    try:
        store.save(session_id, slots)
    except Exception:
        pass


_FACT_WORDS = ["minimum", "moq", "turnaround", "shipping", "sample",
               "how long", "delivery", "lead time"]


def _deterministic_reply(message: str, slots: dict, facts: list[dict], missing: list[str]) -> str:
    """No-LLM reply. Only uses OKF text and slot questions — it can
    never invent a price, a policy, or a fact.

    Order matters: an ORDER statement ("I need 2 banners") must get
    the next missing-field question, not a fact chunk that merely
    mentions a keyword. Only a real fact question ("?", or a fact
    word like turnaround) gets the fact text first.
    """
    low = message.lower()
    is_fact_question = "?" in message or any(w in low for w in _FACT_WORDS)
    if facts and is_fact_question:
        return facts[0]["text"].strip()[:800]
    if missing:
        return QUESTIONS[missing[0]]
    # Quote complete and no fact question: ask for confirmation, not
    # a raw KB chunk. (The old fallback returned facts[0] here, which
    # was a whole file including its frontmatter — the ugliest reply
    # in the live transcript's no-LLM path.)
    if not missing:
        return (f"Just to confirm — do you want {slots.get('quantity')} "
                f"{slots.get('product')}, size {slots.get('sizes')}, "
                f"{slots.get('skus', '1')} SKU with {slots.get('extras', 'none')} extras?")
    if facts:
        return facts[0]["text"].strip()[:800]
    return "Thanks — I have your details. A team member will confirm the quote shortly."


def _llm_reply(message: str, language: str, slots: dict, facts: list[dict],
               reply_to: str | None = None) -> str | None:
    """gpt-5-mini answer, or None if no key / call fails.

    The prompt is the leash: facts come ONLY from the retrieved OKF
    chunks below. No chunk about it -> the model must say it will
    confirm with the team, never guess. Numbers are copied verbatim.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI()
        fact_block = "\n\n".join(
            f"[{f['source']}] {f['text']}" for f in facts) or "No OKF fact retrieved."
        reply_ctx = (f"\nThe visitor is replying to this earlier bot message: "
                     f"{reply_to}. Answer in that context.\n"
                     if reply_to else "")
        system = (
            "You are a Print247 sales assistant. Reply in the visitor's "
            f"language ({language}). Use ONLY the facts below and the "
            "collected order details. If a fact is not in them, say you "
            "will confirm with the team — never guess, never invent a "
            "price, policy, or date. Copy numbers verbatim. Keep it short, "
            "one question at a time.\n\n"
            f"FACTS:\n{fact_block}\n\nCOLLECTED: {slots}{reply_ctx}"
        )
        resp = client.chat.completions.create(
            model=os.environ.get("CHAT_MODEL", "gpt-5-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            timeout=30,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def handle_message(message: str, session_id: str | None = None, store=None,
                   reply_to: str | None = None) -> dict:
    """reply_to is the bot message the visitor tapped Reply on. It
    is context for the LLM and is logged; it never changes slots
    by itself. Session slots are the real context memory: they are
    loaded, merged, and saved on every message, so a side question
    (shipping, SKU) mid-quote never wipes the collected order."""
    language = detect_language(message)
    prior = _load_session(store, session_id)
    slots = merge_slots(prior, extract_from_message(message))
    low = message.lower().strip()

    # Confirmation chips must actually work: "Change quantity" clears
    # that slot and re-asks it, instead of the bot treating the tap
    # as a new message and repeating the confirmation.
    if "change quantity" in low:
        slots.pop("quantity", None)
        _save_session(store, session_id, slots)
        return {
            "reply": QUESTIONS["quantity"], "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": _slot_sources(slots),
            "handoff": None, "llm_used": False,
            "suggestions": ["1000 units", "5000 units", "Not sure about quantity"],
        }
    if "change size" in low:
        slots.pop("sizes", None)
        _save_session(store, session_id, slots)
        return {
            "reply": QUESTIONS["sizes"], "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": _slot_sources(slots),
            "handoff": None, "llm_used": False,
            "suggestions": ["Size 4x6 inches", "Size 100x150mm", "Not sure about size"],
        }
    if low in ("yes", "yes, that's correct", "yes thats correct",
               "yes, that's right", "confirm", "confirmed", "correct") \
            and guards.is_complete(slots):
        _save_session(store, session_id, slots)
        return {
            "reply": (f"Perfect — your quote request is ready: {slots.get('product')}, "
                      f"{slots.get('sizes')}, {slots.get('quantity')} units, "
                      f"{slots.get('skus', '1')} SKU, extras {slots.get('extras', 'none')}. "
                      "A team member will confirm the price and turnaround shortly."),
            "language": language, "slots": slots, "missing": [],
            "sources": _slot_sources(slots), "handoff": "complete", "llm_used": False,
            "suggestions": ["What is the minimum order?", "Is shipping free?",
                            "What is your refund policy?"],
        }

    reason = guards.handoff_reason(message, slots)
    facts: list[dict] = []
    if reason == "policy_question":
        # Narrowed handoff: if a policy OKF file covers the question,
        # answer from it (normal path below) instead of handing off.
        facts = retrieve(message)
        if not any(f["source"].startswith("kb/policies/") for f in facts):
            _save_session(store, session_id, slots)
            return {
                "reply": _POLICY_BEYOND_HANDOFF, "language": language,
                "slots": slots, "missing": missing_fields(slots),
                "sources": [], "handoff": reason, "llm_used": False,
                "suggestions": _suggestions(slots, missing_fields(slots)),
            }
    if reason and reason != "policy_question":
        _save_session(store, session_id, slots)
        return {
            "reply": "Of course — I am connecting you with a team member who can help directly.",
            "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": [],
            "handoff": reason, "llm_used": False,
            "suggestions": _suggestions(slots, missing_fields(slots)),
        }

    moq = guards.moq_check(slots)
    if not facts:
        facts = retrieve(message)
    sources = [f["source"] for f in facts]
    missing = missing_fields(slots)

    # "Not sure" used to loop forever: the bot re-asked the same
    # MOQ question because no quantity was ever collected. Instead,
    # offer the MOQ as a starting point (quantity) or a common size
    # (sizes), so the visitor can move forward in one tap.
    if "not sure" in low and missing:
        if "quantity" in missing:
            _save_session(store, session_id, slots)
            return {
                "reply": ("No problem — most orders start at the minimum of 1000 units "
                          "per size. Would you like to start with 1000, or a rough range?"),
                "language": language, "slots": slots, "missing": missing,
                "sources": _slot_sources(slots) or sources,
                "handoff": None, "llm_used": False,
                "suggestions": ["1000 units", "5000 units", "More than 5000"],
            }
        if "sizes" in missing:
            _save_session(store, session_id, slots)
            return {
                "reply": ("No problem — tell me what will go inside the pack, "
                          "or pick a common size to start with."),
                "language": language, "slots": slots, "missing": missing,
                "sources": _slot_sources(slots) or sources,
                "handoff": None, "llm_used": False,
                "suggestions": ["Size 4x6 inches", "Size 100x150mm",
                                "I will send artwork later"],
            }

    if not moq["ok"]:
        _save_session(store, session_id, slots)
        return {
            "reply": moq["message"], "language": language, "slots": slots,
            "missing": missing, "sources": sources,
            "handoff": None, "llm_used": False,
            "suggestions": _suggestions(slots, missing),
        }

    reply = _llm_reply(message, language, slots, facts, reply_to=reply_to)
    llm_used = reply is not None
    if not llm_used:
        reply = _deterministic_reply(message, slots, facts, missing)
        # Slot-collection steps get clean sources (see _slot_sources);
        # fact questions keep their retrieved sources.
        is_fact_question = "?" in message or any(w in low for w in _FACT_WORDS)
        if missing and not is_fact_question:
            sources = _slot_sources(slots) or sources
    _save_session(store, session_id, slots)

    result = {
        "reply": reply, "language": language, "slots": slots,
        "missing": missing, "sources": sources,
        "handoff": "complete" if guards.is_complete(slots) else None,
        "llm_used": llm_used,
        "suggestions": _suggestions(slots, missing, reply=reply),
    }
    return result
