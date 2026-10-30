"""SRAG pre-display check tests (Oct 30).

srag_check unit tests use stub llm_fns (same pattern as the
llm_extract stubs). Chain tests monkeypatch brain.srag_check:
the VM has no API key, so the real check skips there — the stub
proves the wiring (fail -> clarification, yes -> re-answer).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("OPENAI_API_KEY", None)

from app.chat import brain as B
from app.chat.srag import srag_check, strip_internal_notes

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name} :: {detail}")


# --- strip_internal_notes ---
dirty = ("Label materials: white paper, vinyl. Script note: the internal "
         "sales script lists PP white vinyl as the label stock option. "
         "Vinyl is weatherproof.")
clean = strip_internal_notes(dirty)
check("script-note sentence stripped",
      "Script note" not in clean and "internal sales script" not in clean
      and "Label materials" in clean and "weatherproof" in clean, clean)
check("context-note sentence stripped",
      "Context note" not in strip_internal_notes(
          "Office hours are 9 to 5. Context note: do not merge claims."))
check("internal sales-script meta sentence stripped, fact kept",
      "Internal sales-script" not in strip_internal_notes(
          "Site methods: Visa. Internal sales-script facts (state as script "
          "rules, not site claims): payments ACH, Wire and Zelle. Cards work.")
      and "Visa" in strip_internal_notes(
          "Site methods: Visa. Internal sales-script facts (state as script "
          "rules, not site claims): payments ACH, Wire and Zelle. Cards work."))
check("old-sales-script fact citation kept, not stripped",
      "old sales script" in strip_internal_notes(
          "Banners have no minimum in the old sales script."))

# --- srag_check with stubs ---
CANDS = ["Yes — we print beverage and bottle labels, including wine labels.",
         "Clear labels are made from durable BOPP film."]
check("stub ok passes",
      srag_check("do you offer bottle labels?", CANDS, {},
                 llm_fn=lambda q, c, x: {"answers": True,
                                         "sentence": CANDS[0]})["answers"] is True)


def _fail_fn(q, c, x):
    return {"answers": False, "sentence": None,
            "clarification": "Do you mean labels that stick on bottles?",
            "topic": "bottle labels"}


_f = srag_check("do you offer labels which stick to bottles?", CANDS, {},
                llm_fn=_fail_fn)
check("stub fail gives clarification + topic",
      _f["answers"] is False
      and _f["clarification"] == "Do you mean labels that stick on bottles?"
      and _f["topic"] == "bottle labels", str(_f))
check("ok with invented sentence downgrades to fail",
      srag_check("q?", CANDS, {},
                 llm_fn=lambda q, c, x: {"answers": True,
                                         "sentence": "Invented fact."})["answers"] is False)
check("fail without a question gets generic clarification",
      "?" in srag_check("q?", CANDS, {},
                        llm_fn=lambda q, c, x: {"answers": False})["clarification"])
check("no key skips (answers True)",
      srag_check("q?", CANDS, {})["answers"] is True)
check("empty candidates skip",
      srag_check("q?", [], {})["answers"] is True)

# --- chain: fail -> clarification -> yes -> re-answer ---
_orig = B.srag_check
_calls = {"n": 0}


def _chain_stub(question, candidates, context):
    _calls["n"] += 1
    if _calls["n"] == 1:
        return {"answers": False, "sentence": None,
                "clarification": "Do you mean labels that stick on bottles?",
                "topic": "bottle labels"}
    return {"answers": True, "sentence": candidates[0] if candidates else None,
            "clarification": None, "topic": None}


B.srag_check = _chain_stub
try:
    sid = "srag-chain"
    for m in ["I need labels", "100x150mm", "Matte", "400", "1 design"]:
        B.handle_message(m, session_id=sid, store=None)
    r = B.handle_message(
        "do you offer labels which stick to bottles like stickers?",
        session_id=sid, store=None)
    check("failed check serves clarification, never the dump",
          "Do you mean labels that stick on bottles?" in r["reply"]
          and "custom labels, special stickers" not in r["reply"],
          r["reply"][:250])
    r2 = B.handle_message("yes", session_id=sid, store=None)
    check("yes after clarification re-answers from bottle file",
          "bottle label" in r2["reply"].lower()
          and "Do you have any specific material" in r2["reply"],
          r2["reply"][:250])
finally:
    B.srag_check = _orig

# --- chain: non-affirmative after clarification clears state ---
B.srag_check = lambda q, c, x: {"answers": False, "sentence": None,
                                "clarification": "Do you mean bottle labels?",
                                "topic": "bottle labels"}
try:
    sid2 = "srag-clear"
    for m in ["I need labels", "100x150mm", "Matte", "400", "1 design"]:
        B.handle_message(m, session_id=sid2, store=None)
    r = B.handle_message("do you offer bottle labels?", session_id=sid2,
                         store=None)
    check("clarification asked on failure (2)",
          "Do you mean bottle labels?" in r["reply"], r["reply"][:200])
    r2 = B.handle_message("Kraft", session_id=sid2, store=None)
    check("material answer after clarification flows normally",
          "kraft" in str(r2["slots"]).lower(), str(r2["slots"]))
finally:
    B.srag_check = _orig

print(f"SRAG: {len(FAILURES)} failed")
if FAILURES:
    sys.exit(1)
print("All SRAG cases passed.")
