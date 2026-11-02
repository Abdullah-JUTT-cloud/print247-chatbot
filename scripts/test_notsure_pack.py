""""Not sure" about size — Nov 3 live test.

A label visitor who said "not sure" about size was asked "what
will go inside the pack?" — a label never has anything inside
it. Flat families (label, sticker, card, banner) now get a
leave-it-to-the-team wording; containers (box, bag, pouch) keep
the pack question. And a second "not sure" gives the field up
instead of repeating the same reply forever (the size chips
include a "Not sure" chip, inviting a second tap).

Run from the repo root:  python scripts/test_notsure_pack.py
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


# --- the reported case: labels never hear about a pack ---
r = run("nsp-label", ["I need labels", "ab@gmail.com", "not sure"])
check("label 'not sure' size never mentions a pack",
      "pack" not in r["reply"].lower()
      and "team to confirm" in r["reply"], r["reply"][:200])
r = run("nsp-sticker", ["I need stickers", "ab@gmail.com", "not sure"])
check("sticker 'not sure' size never mentions a pack",
      "pack" not in r["reply"].lower(), r["reply"][:200])

# --- containers keep the pack question ---
r = run("nsp-pouch", ["I need mylar bags", "ab@gmail.com", "not sure"])
check("pouch 'not sure' size still asks what goes inside",
      "inside the pack" in r["reply"], r["reply"][:200])
r = run("nsp-box", ["I need boxes", "ab@gmail.com", "not sure"])
check("box 'not sure' size still asks what goes inside",
      "inside the pack" in r["reply"], r["reply"][:200])

# --- second "not sure" gives up and moves on, no echo loop ---
r = run("nsp-label2", ["I need labels", "ab@gmail.com",
                       "not sure", "not sure"])
check("label second 'not sure' size moves on to finishes",
      "finish" in r["reply"].lower()
      and "inside the pack" not in r["reply"], r["reply"][:220])
r = run("nsp-qty2", ["I need labels", "ab@gmail.com", "100x150mm",
                     "gloss", "not sure", "not sure"])
check("second 'not sure' quantity moves on to designs",
      "design" in r["reply"].lower(), r["reply"][:220])
r = run("nsp-pick", ["I need labels", "ab@gmail.com",
                     "not sure", "4x6 inches"])
check("picking a size chip after 'not sure' still works",
      "finish" in r["reply"].lower(), r["reply"][:200])

print("NOTSURE-PACK: all passed")
