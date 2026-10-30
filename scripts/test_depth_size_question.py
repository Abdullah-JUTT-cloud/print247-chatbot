"""Depth wording + zero-size re-ask — Nov 1 live tests.

1. The size question said "Width x height x depth" for EVERY
   product, so label/sticker visitors were asked for a depth
   they do not have. (The depth follow-up itself was already
   box-only; the question text was the leak.) Now only boxes
   get the depth wording; every other family gets width x height.
2. The zero-size refusal jumped to finishes: clearing the slot
   value was not enough, because extraction had already put
   "sizes" in answered_fields, so script_missing skipped it. A
   refused size must be un-answered too, so the size is re-asked.

Run from the repo root:  python scripts/test_depth_size_question.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat import brain as B
from app.chat.brain import handle_message
from app.chat.script import question_for


def run(sid, msgs, **kw):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None, **kw)
    return r


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# --- 1. question text by family ---
check("box size question keeps depth wording",
      "depth" in question_for("sizes", {"product": "box"}))
for fam in ["label", "sticker", "business card", "banner", "mylar bag", "pouch"]:
    check(f"{fam} size question has no depth wording",
          "depth" not in question_for("sizes", {"product": fam})
          and "Width x height" in question_for("sizes", {"product": fam}))
check("spanish label size question is flat",
      "profundidad" not in B._question("sizes", {"product": "label"}, "es")
      and "Ancho x alto" in B._question("sizes", {"product": "label"}, "es"))
check("spanish box size question keeps depth",
      "profundidad" in B._question("sizes", {"product": "box"}, "es"))
check("ur-roman label size question is flat",
      "depth" not in B._question("sizes", {"product": "label"}, "ur-roman"))

# --- 1b. live flows ---
r = run("dq-label", ["i need stckers", "ab@gmail.com"])
check("live label size question has no depth",
      "depth" not in r["reply"] and "Width x height" in r["reply"],
      r["reply"][:160])
r = run("dq-box", ["i need boxes", "ab@gmail.com"])
check("live box size question keeps depth",
      "depth" in r["reply"], r["reply"][:160])
r = run("dq-box", ["4x6 inches"])
check("2-dim box size still asks the depth follow-up",
      "need a depth" in r["reply"], r["reply"][:200])
r = run("dq-box", ["No need"])
check("no depth continues to the box type question",
      "type" in r["reply"].lower(), r["reply"][:200])

# --- 2. zero-size refusal re-asks the size, not finishes ---
r = run("dq-zero", ["i need stckers", "ab@gmail.com", "0x0"])
check("0x0 refusal re-asks the size question",
      "zero side" in r["reply"] and "What size" in r["reply"]
      and "finish" not in r["reply"].lower()
      and not r["slots"].get("sizes"), r["reply"][:220])
r = handle_message("4x6 inches", session_id="dq-zero", store=None)
check("a real size after the refusal flows on to finishes",
      "finish" in r["reply"].lower()
      and r["slots"].get("sizes") == "4x6 inches", r["reply"][:200])

print("DEPTH-SIZE-QUESTION: all passed")
