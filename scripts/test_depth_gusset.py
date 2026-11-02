"""Stand-up pouch depth = gusset — Nov 3 mylar transcript.

A stand-up pouch stands up because of its bottom gusset, so a
2-number size is incomplete — but nothing ever asked about it
(the size question is width x height only, and the box depth
trigger is box-only). The visitor had to challenge it ("they
have depth isnt it?") and got a banners MOQ sentence back.

Fixes: after a stand-up style lands, the bot asks about the
gusset once (before finishes); a gusset answer joins as +N
(4x6+2); a depth question is answered from the glossary truth
instead of retrieval. Flat pouches have no gusset and never get
the question.

Run from the repo root:  python scripts/test_depth_gusset.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message


def run(sid, msgs, **kw):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None, **kw)
    return r


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


def to_style(sid, style="Stand-up"):
    return run(sid, ["I need mylar bags", "ab@gmail.com", "4x6 inches",
                     style])


# --- the transcript flow: gusset asked right after stand-up style ---
r = to_style("dg-trigger")
check("stand-up style triggers the gusset question, not finishes",
      "gusset" in r["reply"].lower()
      and "width x height enough" in r["reply"], r["reply"][:220])
r = handle_message("Add gusset", session_id="dg-trigger", store=None)
check("'Add gusset' asks for the number",
      "What gusset do you need" in r["reply"], r["reply"][:200])
r = handle_message("2 inches", session_id="dg-trigger", store=None)
check("gusset value joins as +N and flow moves to finishes",
      r["slots"].get("sizes") == "4x6+2 inches"
      and "finish" in r["reply"].lower(), f"{r['slots']} :: {r['reply'][:200]}")
r = to_style("dg-no")
r = handle_message("No need", session_id="dg-no", store=None)
check("'No need' keeps width x height and moves to finishes",
      r["slots"].get("sizes") == "4x6 inches"
      and "finish" in r["reply"].lower(), r["reply"][:200])

# --- the reported question, answered instead of a banners sentence ---
r = run("dg-q", ["I need mylar bags", "ab@gmail.com", "4x6 inches",
                 "Stand-up", "Matte", "they have depth isnt it?"])
check("'they have depth isnt it?' gets a yes + gusset offer, no MOQ",
      "Yes" in r["reply"] and "bottom gusset" in r["reply"]
      and "Banners" not in r["reply"]
      and "minimum" not in r["reply"], r["reply"][:260])

# --- flat pouches never get the gusset question ---
r = to_style("dg-flat", "Flat")
check("flat style goes straight to finishes, no gusset question",
      "finish" in r["reply"].lower()
      and "gusset" not in r["reply"].lower(), r["reply"][:200])
r = run("dg-flatq", ["I need mylar bags", "ab@gmail.com", "4x6 inches",
                     "Flat", "they have depth isnt it?"])
check("flat + depth question: no gusset, no MOQ sentence",
      "no gusset" in r["reply"].lower()
      and "Banners" not in r["reply"], r["reply"][:260])

# --- a size already carrying +gusset skips the trigger ---
r = run("dg-given", ["I need mylar bags", "ab@gmail.com", "5x8+3 inches",
                     "Stand-up"])
check("size with +gusset skips the gusset question",
      "finish" in r["reply"].lower()
      and "gusset" not in r["reply"].lower()
      and r["slots"].get("sizes") == "5x8+3 inches",
      f"{r['slots']} :: {r['reply'][:200]}")

print("DEPTH-GUSSET: all passed")
