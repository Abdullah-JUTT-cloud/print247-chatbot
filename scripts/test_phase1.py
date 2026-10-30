"""Phase 1 tests (Oct 30): SRAG on capability answers + fact-chain
prune, conversation summary, retrieval rerank.

SRAG chain tests monkeypatch brain.srag_check (VM has no key, so
the real check skips there) — the same stub pattern as the
llm_extract stubs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("OPENAI_API_KEY", None)

from app.chat import brain as B
from app.chat.retrieval import _nano_rerank, _order_hybrid

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name} :: {detail}")


# --- rerank ---
_vec = [{"source": "kb/products/boxes.md", "text": "Boxes fact."}]
_kw = [{"source": "kb/products/labels.md", "text": "Labels fact."}]
_calls = {"n": 0}


def _kw_wins(q, a, b):
    _calls["n"] += 1
    return 1


def _vec_wins(q, a, b):
    _calls["n"] += 1
    return 0


out = _order_hybrid("q", _vec, _kw, _kw_wins)
check("rerank keyword win moves keyword top",
      out[0]["source"] == "kb/products/labels.md", str(out))
out = _order_hybrid("q", _vec, _kw, _vec_wins)
check("rerank vector win keeps vector top",
      out[0]["source"] == "kb/products/boxes.md", str(out))
_calls["n"] = 0
out = _order_hybrid("q", _vec, [{"source": "kb/products/boxes.md", "text": "x"}],
                    _kw_wins)
check("same file on top skips rerank call", _calls["n"] == 0, str(_calls))


def _boom(q, a, b):
    raise RuntimeError("rerank down")


out = _order_hybrid("q", _vec, _kw, _boom)
check("rerank failure keeps vector order",
      out[0]["source"] == "kb/products/boxes.md", str(out))
check("nano rerank without key keeps vector order",
      _nano_rerank("q", "a", "b") == 0)

# --- conversation summary ---
meta = {"visitor_messages": ["I need labels", "100x150mm", "Matte",
                             "do you offer bottle labels?"],
        "last_bot_question": "Do you have any specific material in mind?"}
slots = {"product": "label", "sizes": "100x150mm", "finishes": "matte"}
s = B._conversation_summary(meta, slots)
check("summary has slots", "product=label" in s and "sizes=100x150mm" in s, s)
check("summary excludes the current message",
      "do you offer bottle labels?" not in s, s)
check("summary has earlier messages + last question",
      "100x150mm" in s and "specific material" in s, s)
check("empty summary", B._conversation_summary({}, {}) == "")

# --- llm messages: summary is user-role, never system ---
msgs = B._llm_messages("SYS", "hello?", summary="Quote so far: product=label.")
check("llm messages system first",
      msgs[0]["role"] == "system" and msgs[0]["content"] == "SYS", str(msgs))
check("summary is a user message, not system",
      len(msgs) == 3 and msgs[1]["role"] == "user"
      and "product=label" in msgs[1]["content"]
      and "product=label" not in msgs[0]["content"], str(msgs))
check("no summary means two messages",
      len(B._llm_messages("SYS", "hello?")) == 2)

# --- capability prune: rigid boxes for watches ---
_orig = B.srag_check
B.srag_check = lambda q, c, x: {"answers": True, "sentence": c[0],
                                "clarification": None, "topic": None}
try:
    r = B.handle_message("do you make rigid boxes for watches?",
                         session_id="p1-cap", store=None)
    check("capability prune keeps the verified Yes only",
          r["reply"].startswith("Yes — we make rigid boxes.")
          and "pharmaceutical" not in r["reply"].lower()
          and "What size do you need?" in r["reply"],
          r["reply"][:300])
finally:
    B.srag_check = _orig

# --- capability fail falls through to the chain (never a bad Yes) ---
_calls2 = {"n": 0}


def _fail_then_pass(q, c, x):
    _calls2["n"] += 1
    if _calls2["n"] == 1:
        return {"answers": False, "sentence": None,
                "clarification": "Do you mean rigid boxes?",
                "topic": "rigid boxes"}
    return {"answers": True, "sentence": "CHAIN-ANSWER-SENTENCE",
            "clarification": None, "topic": None}


B.srag_check = _fail_then_pass
try:
    r = B.handle_message("do you make rigid boxes for watches?",
                         session_id="p1-fall", store=None)
    check("capability fail falls through to chain re-answer",
          "CHAIN-ANSWER-SENTENCE" in r["reply"]
          and "Do you mean rigid boxes?" not in r["reply"],
          r["reply"][:300])
    check("capability fall-through keeps stored product",
          r["slots"].get("product") == "box", str(r["slots"]))
finally:
    B.srag_check = _orig

# --- fact-chain prune: bottle question keeps one sentence + question ---
B.srag_check = lambda q, c, x: {"answers": True, "sentence": c[0],
                                "clarification": None, "topic": None}
try:
    sid = "p1-chain"
    for m in ["I need labels", "100x150mm", "Matte", "400", "1 design"]:
        B.handle_message(m, session_id=sid, store=None)
    r = B.handle_message(
        "do you offer labels which stick to bottles like stickers?",
        session_id=sid, store=None)
    check("fact-chain prune drops the second sentence, keeps the question",
          "Tell us your bottle size" not in r["reply"]
          and "Do you have any specific material" in r["reply"],
          r["reply"][:300])
finally:
    B.srag_check = _orig

print(f"PHASE1: {len(FAILURES)} failed")
if FAILURES:
    sys.exit(1)
print("All Phase 1 cases passed.")
