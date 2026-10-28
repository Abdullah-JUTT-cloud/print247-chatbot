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
    if facts:
        return facts[0]["text"].strip()[:800]
    return "Thanks — I have your details. A team member will confirm the quote shortly."


def _llm_reply(message: str, language: str, slots: dict, facts: list[dict]) -> str | None:
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
        system = (
            "You are a Print247 sales assistant. Reply in the visitor's "
            f"language ({language}). Use ONLY the facts below and the "
            "collected order details. If a fact is not in them, say you "
            "will confirm with the team — never guess, never invent a "
            "price, policy, or date. Copy numbers verbatim. Keep it short, "
            "one question at a time.\n\n"
            f"FACTS:\n{fact_block}\n\nCOLLECTED: {slots}"
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


def handle_message(message: str, session_id: str | None = None, store=None) -> dict:
    language = detect_language(message)
    prior = _load_session(store, session_id)
    slots = merge_slots(prior, extract_from_message(message))

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
            }
    if reason and reason != "policy_question":
        _save_session(store, session_id, slots)
        return {
            "reply": "Of course — I am connecting you with a team member who can help directly.",
            "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": [],
            "handoff": reason, "llm_used": False,
        }

    moq = guards.moq_check(slots)
    if not facts:
        facts = retrieve(message)
    sources = [f["source"] for f in facts]
    missing = missing_fields(slots)

    if not moq["ok"]:
        _save_session(store, session_id, slots)
        return {
            "reply": moq["message"], "language": language, "slots": slots,
            "missing": missing, "sources": sources,
            "handoff": None, "llm_used": False,
        }

    reply = _llm_reply(message, language, slots, facts)
    llm_used = reply is not None
    if not llm_used:
        reply = _deterministic_reply(message, slots, facts, missing)
    _save_session(store, session_id, slots)

    result = {
        "reply": reply, "language": language, "slots": slots,
        "missing": missing, "sources": sources,
        "handoff": "complete" if guards.is_complete(slots) else None,
        "llm_used": llm_used,
    }
    return result
