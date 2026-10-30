"""Fixes for the Oct 31 01:19 live transcript (user pasted it, 3 issues).

1. "im looking for sticker labels" never asked email at step 2:
   the step-2 email trigger only accepted _is_order phrases, so it
   skipped the turn and the bot went straight to size. "looking
   for" counts ONLY in that trigger (where a product is already
   known) — never in global _is_order, or "Looking for a work
   from home job" would stop being deflected as a job enquiry.
2. After the design file was uploaded, a bare "yes" got
   "please attach it with the paperclip button" again: the upload
   does not clear awaiting_design_image, and the yes-handler never
   checked design_files.
3. "We can look at 300 for you. We do smaller runs too." repeated
   on a later question turn: minimum_already_stated only matches
   "moq"/"minimum"/"1,000 per", none of which the new note
   contains — so the guard never tripped. below_min_noted now
   tracks it directly.

Run from the repo root:  python scripts/test_transcript_fixes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat import brain as B
from app.chat.brain import handle_message


def run(sid, msgs):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None)
    return r


def steps(sid, msgs):
    out = []
    for m in msgs:
        out.append(handle_message(m, session_id=sid, store=None)["reply"])
    return out


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# --- Fix 1: "looking for" is an order, email at step 2 ---
r = run("tf-lookfor", ["hi", "im looking for sticker labels"])
check("looking-for order asks email at step 2",
      "email" in r["reply"].lower() and r["slots"].get("product") == "label",
      r["reply"][:120])
r = run("tf-lookfor-then", ["im looking for sticker labels", "ali@test.com"])
check("after email, looking-for chat continues to size question",
      "What size" in r["reply"], r["reply"][:120])
r = run("tf-lookfor-q", ["im looking for sticker labels, what sizes do you have?"])
check("looking-for + question mark is not email-hijacked",
      "email" not in r["reply"].lower(), r["reply"][:120])

# --- Fix 2: yes after upload does not re-ask for the file ---
flow = ["im looking for sticker labels", "ali@test.com", "100x150mm",
        "gloss", "300", "2 designs", "in total"]
replies = steps("tf-img", flow)
check("flow reaches the design-image question",
      "image of the design" in replies[-1], replies[-1][:120])
meta = B._META_FALLBACK["tf-img"]
check("image question leaves awaiting_design_image set",
      meta.get("awaiting_design_image") is True)
# Upload stores dict entries (see app/main.py); seed one.
meta["design_files"] = [{"name": "certified_4.webp", "mime": "image/webp",
                         "description": "abstract emblem"}]
r = handle_message("yes", session_id="tf-img", store=None)
check("yes with file attached never says paperclip",
      "paperclip" not in r["reply"].lower(), r["reply"][:160])
check("yes with file attached acknowledges the attached file",
      "already attached" in r["reply"], r["reply"][:160])
check("yes with file attached still asks the next question",
      "material" in r["reply"].lower(), r["reply"][:160])

# --- Fix 3: below-min note appears exactly once in the whole flow ---
replies = steps("tf-note", [
    "im looking for sticker labels", "ali@test.com", "100x150mm",
    "gloss", "300", "2 designs", "in total", "no", "no", "No preference",
])
joined = "\n".join(replies)
check("below-min note shown exactly once across the full flow",
      joined.count("We can look at 300") == 1,
      f"count={joined.count('We can look at 300')}")
check("no 1000 minimum anywhere in the flow",
      "1000" not in joined)

print("TRANSCRIPT-FIXES: all passed")
