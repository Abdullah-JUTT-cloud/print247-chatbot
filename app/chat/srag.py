"""SRAG — pre-display relevance check (Oct 30, user's call).

The user's flow, implemented: the visitor's question is read in
conversation context (current product + the bot's pending
question), RAG retrieves OKF facts, and BEFORE any fact answer
reaches the frontend a small model checks it: does this answer
actually answer the question? If not, the bot does NOT serve the
generic dump — it asks one clarifying question, step by step,
and the visitor's confirmation re-answers with the pinned topic.

History: Oct 29 the colleague's LLM-SRAG idea was answered with
a CODE-level validation only (product-family retrieval check),
with true LLM SRAG held for "if wrong-product answers persist".
They persisted — Oct 30 transcript: "do you offer labels which
stick to bottles like stickers?" got the generic labels list
twice. Trigger met, so this module exists now.

Rules:
- Only fact answers are checked (script questions, confirmations
  and contact turns are not "AI data" to verify).
- No API key, or any checker failure, means SKIP (answers=True):
  a chat must never break because the checker is down. The check
  is a guard, not a gate.
- The checker's verdict is itself validated by code: a "yes"
  must name one of the candidate sentences verbatim, or it
  downgrades to "no".
- Internal-note sentences ("Script note:", "Context note:",
  "internal sales script") are stripped from replies before the
  check and before display: the live model once quoted the sales
  script's PP-white-vinyl note into a visitor reply.
"""

import json
import os
import re

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_INTERNAL_NOTE = re.compile(
    r"^\s*(script note|context note)\b|internal sales[- ]script|state as script rules",
    re.IGNORECASE)
# NOTE: "old sales script" citations are NOT stripped — they carry
# facts ("Banners have no minimum in the old sales script"). Only
# meta sentences about the script itself are internal language.


def strip_internal_notes(reply: str) -> str:
    """Drop internal-note sentences from a reply, keep the rest."""
    parts = [s for s in re.split(_SENTENCE_BREAK, reply or "") if s.strip()]
    kept = [s for s in parts if not _INTERNAL_NOTE.search(s)]
    return " ".join(kept).strip()


def _nano_check(question: str, candidates: list[str], context: dict) -> dict:
    """One gpt-5-nano relevance read, mirroring llm_extract."""
    from openai import OpenAI

    client = OpenAI()
    numbered = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(candidates))
    ctx = ""
    if context.get("product"):
        ctx += f" The current quote is for {context['product']}."
    if context.get("pending"):
        ctx += f" The bot was asking about {context['pending']}."
    resp = client.chat.completions.create(
        model=os.environ.get("HELPER_MODEL", "gpt-5-nano"),
        messages=[
            {"role": "system",
             "content": (
                 "You check whether a chatbot answer actually answers the "
                 "visitor's question. Return a JSON object: {answers: "
                 "true/false — true ONLY if some candidate directly answers "
                 "the question, not merely mentions the topic; sentence: the "
                 "exact candidate that answers, or null; topic: a short "
                 "phrase naming what the visitor seems to be asking about "
                 "(e.g. 'bottle labels'), or null; clarification: a short "
                 "question to ask the visitor when answers is false, to pin "
                 "down what they mean, or null}." + ctx +
                 " Candidates:\n" + numbered + " Return JSON only.")},
            {"role": "user", "content": question},
        ],
        timeout=10,
    )
    raw = json.loads(resp.choices[0].message.content.strip())
    return raw if isinstance(raw, dict) else {}


def srag_check(question: str, candidates: list[str], context: dict | None = None,
               llm_fn=None) -> dict:
    """{"answers", "sentence", "clarification", "topic"}.

    llm_fn(question, candidates, context) -> dict is injectable for
    tests (same pattern as llm_extract stubs). Without an injectable
    and without an API key, the check is skipped (answers=True).
    """
    skip = {"answers": True, "sentence": None, "clarification": None,
            "topic": None}
    cands = [c.strip() for c in (candidates or []) if c and c.strip()]
    if not cands or not (question or "").strip():
        return skip
    if llm_fn is None:
        if not os.environ.get("OPENAI_API_KEY"):
            return skip
        llm_fn = _nano_check
    try:
        raw = llm_fn(question, cands, context or {})
    except Exception:
        return skip
    if not isinstance(raw, dict):
        return skip
    answers = raw.get("answers") is True
    sentence = raw.get("sentence")
    if answers:
        # A "yes" must name a real candidate verbatim, or it is a
        # guess and downgrades to "no".
        if not isinstance(sentence, str) or sentence.strip() not in cands:
            answers = False
            sentence = None
        else:
            sentence = sentence.strip()
    clarification = raw.get("clarification")
    if not answers:
        if not isinstance(clarification, str) or "?" not in clarification:
            clarification = ("Just to be sure I get this right, could you "
                             "say a bit more about what you need?")
    topic = raw.get("topic")
    if not isinstance(topic, str):
        topic = None
    return {"answers": answers, "sentence": sentence,
            "clarification": clarification if not answers else None,
            "topic": (topic or "").strip() or None}
