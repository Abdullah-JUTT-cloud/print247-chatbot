"""Email must be proper at step 2 — Nov 1 live test.

"I need labels" -> email question -> "ab" was accepted and the
bot moved on to sizes, so the quote ran with no email at all.
A wrong email is now corrected and re-asked, never spent; a
refusal still insists once, then retires; a spec answer still
spends the ask as before.

Run from the repo root:  python scripts/test_email_validation.py
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


# --- the reported case: "ab" ---
r = run("ev-ab", ["I need labels", "ab"])
check("'ab' is corrected and re-asked, never advanced to sizes",
      "doesn't look like a valid email" in r["reply"]
      and "best email" in r["reply"], r["reply"][:200])
r = handle_message("ali@test.com", session_id="ev-ab", store=None)
check("a proper email after the correction flows on to sizes",
      "What size" in r["reply"], r["reply"][:160])

# --- other wrong-email shapes ---
for i, bad in enumerate(["ab@gmail", "gmail.com", "abdullah"]):
    r = run(f"ev-bad{i}", ["I need labels", bad])
    check(f"{bad!r} is corrected, not spent",
          "doesn't look like a valid email" in r["reply"], r["reply"][:200])
r = run("ev-good", ["I need labels", "ab@gmail.com"])
check("a proper email is accepted at once",
      "What size" in r["reply"], r["reply"][:160])

# --- refusals still work (decline checked before bad-email) ---
r = run("ev-ref", ["I need labels", "no"])
check("'no' still insists, not corrected as a bad email",
      "I need an email to send your quote" in r["reply"]
      and "doesn't look like a valid email" not in r["reply"],
      r["reply"][:200])
r = handle_message("I prefer not to share my email",
                   session_id="ev-ref", store=None)
check("second refusal retires email and the quote continues",
      "What size" in r["reply"], r["reply"][:200])

# --- spec answers still spend the ask (unchanged behavior) ---
r = run("ev-spec", ["I need labels", "matte"])
check("a spec word on the email turn still spends the ask",
      "doesn't look like a valid email" not in r["reply"]
      and "What size" in r["reply"], r["reply"][:200])

print("EMAIL-VALIDATION: all passed")
