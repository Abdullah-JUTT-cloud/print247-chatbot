"""Nov 2 live label transcripts — every glitch in them, fixed.

1. "2+2" at the size question was stored as quantity 2 (with the
   below-min note) while the size was still asked. "+" is not a
   size separator, so no size parses: it is a size attempt, not a
   quantity, and the size is re-asked with the format spelled out.
2. Bare "ok" after the material question re-asked the same
   question. It is an acknowledgment, not an answer: it now counts
   as no preference, like a decline.
3. "no prefrence" (typo) at a field question was not a decline,
   so the question was asked twice. "preference" is now in the
   typo vocabulary, so it corrects and the decline matches.
4. At confirmation, "no prefrence"/"no preference"/"nothing"/
   "go ahead" re-showed the confirmation verbatim (and "go ahead"
   even tripped the gibberish guard). Soft acceptances now
   complete the quote; bare "no" asks what to change instead of
   echoing.
5. Confirmation punctuation: the "?" used to land after the
   team-confirms sentence ("...directly? Note: ..."). It now
   closes the order spec, and the team sentence follows it.

Run from the repo root:  python scripts/test_nov2_transcript.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import _deterministic_reply, handle_message


def run(sid, msgs, **kw):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None, **kw)
    return r


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


def to_confirmation(sid):
    return run(sid, ["I need labels", "ab@gmail.com", "100x150mm",
                     "gloss", "200", "1 design",
                     "No, I need design help", "No preference"])

# --- 1. arithmetic size attempt ---
r = run("n2-plus", ["I need labels", "ab@gmail.com", "2+2"])
check("'2+2' at size question is not stored as quantity",
      not r["slots"].get("quantity") and "smaller runs" not in r["reply"]
      and "width x height" in r["reply"], r["reply"][:220])
r = handle_message("100x150mm", session_id="n2-plus", store=None)
check("a real size after '2+2' flows on to finishes",
      "finish" in r["reply"].lower(), r["reply"][:160])
r = run("n2-star", ["I need labels", "ab@gmail.com", "2*2"])
check("'2*2' still parses as a size and asks its unit",
      "inches" in r["reply"].lower(), r["reply"][:160])

# --- 2. bare "ok" at the material question ---
r = run("n2-ok", ["I need labels", "ab@gmail.com", "100x150mm",
                  "gloss", "200", "1 design",
                  "No, I need design help", "ok"])
check("'ok' at material question does not re-ask material",
      "material" not in r["reply"].lower()
      and "Just to confirm" in r["reply"], r["reply"][:220])

# --- 3. typo decline ---
r = run("n2-typo", ["I need labels", "ab@gmail.com", "100x150mm",
                    "gloss", "200", "1 design",
                    "No, I need design help", "no prefrence"])
check("'no prefrence' at material question is a decline",
      "material" not in r["reply"].lower()
      and "Just to confirm" in r["reply"], r["reply"][:220])

# --- 4. confirmation answers ---
for i, ans in enumerate(["no prefrence", "no preference", "nothing",
                         "go ahead", "looks good"]):
    r = to_confirmation(f"n2-conf{i}")
    r = handle_message(ans, session_id=f"n2-conf{i}", store=None)
    check(f"{ans!r} at confirmation completes, never echoes",
          "Just to confirm" not in r["reply"]
          and ("Perfect" in r["reply"] or "best name" in r["reply"]
               or "name" in r["reply"].lower()), r["reply"][:220])
r = to_confirmation("n2-no")
r = handle_message("no", session_id="n2-no", store=None)
check("'no' at confirmation asks what to change",
      "what would you like to change" in r["reply"].lower()
      and "Just to confirm" not in r["reply"], r["reply"][:200])
r = handle_message("change the finish to matte", session_id="n2-no",
                   store=None)
check("a correction after 'no' still works",
      "matte finish" in r["reply"], r["reply"][:220])

# --- 5. confirmation punctuation with a gave-up field ---
slots = {"product": "label", "sizes": "100x150mm", "finishes": "gloss",
         "quantity": "200", "skus": "1"}
text = _deterministic_reply("x", slots, [], [], "en", gave_up=["material"])
check("confirmation '?' closes the spec, team sentence after it",
      "? For material, the team will confirm it with you directly."
      in text and "directly? Note" not in text, text[:300])

print("NOV2-TRANSCRIPT: all passed")
