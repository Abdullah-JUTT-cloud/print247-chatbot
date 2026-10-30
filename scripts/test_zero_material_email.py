"""Zero sizes, doubled material question, email step 2 — Nov 1 transcripts.

1. "0 x 0" was stored and confirmed ("Got it — 0 x 0. Is that in
   inches...") in front of a senior. A zero side cannot be
   printed: it must never be stored, with or without a unit.
2. The material question doubled: after the image handler asked
   it, a bare "no" got the same question again, because the
   handler never recorded last_asked. One "no" must settle it.
3. "stickers for my jars" stated a product but matched no order
   phrase, so email step 2 never fired. A product just stored
   from a plain need statement counts — but never a fact/price
   question that merely names a product.

Run from the repo root:  python scripts/test_zero_material_email.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat import brain as B
from app.chat.brain import handle_message


def run(sid, msgs, **kw):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None, **kw)
    return r


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# --- 1. zero sizes ---
r = run("zm-zero", ["stickers for my jars", "ali@test.com", "0 x 0"])
check("0 x 0 is refused, never confirmed with a unit question",
      "zero side" in r["reply"] and "Is that in inches" not in r["reply"]
      and not r["slots"].get("sizes"), r["reply"][:200])
r = handle_message("4x6 inches", session_id="zm-zero", store=None)
check("a real size after the refusal flows on to finishes",
      "finish" in r["reply"].lower() and r["slots"].get("sizes") == "4x6 inches",
      r["reply"][:200])
r = run("zm-zero-unit", ["i need labels", "ali@test.com", "0 x 0 inches"])
check("0 x 0 with a unit is refused the same way",
      "zero side" in r["reply"] and not r["slots"].get("sizes"),
      r["reply"][:200])
r = run("zm-zero-box", ["i need boxes", "ali@test.com", "5x0 inches"])
check("a zero side inside a box size is refused too",
      "zero side" in r["reply"] and not r["slots"].get("sizes"),
      r["reply"][:200])

# --- 2. material question must not double (yes-branch + no-branch) ---
FLOW = ["hi i am looking for labels", "hammadnadir75@gmail.com", "3x4 mm",
        "Gloss", "5000 units", "2 designs", "Per design"]
run("zm-mat-yes", FLOW)
B._META_FALLBACK["zm-mat-yes"]["design_files"] = [
    {"name": "7894988.jpg", "mime": "image/jpeg", "description": "coffee"}]
B._META_FALLBACK["zm-mat-yes"]["awaiting_design_image"] = True
r = handle_message("ok", session_id="zm-mat-yes", store=None)
check("ok after upload asks material once",
      "already attached" in r["reply"] and "material" in r["reply"].lower(),
      r["reply"][:200])
r = handle_message("no", session_id="zm-mat-yes", store=None)
check("one no to material goes straight to confirmation, no re-ask",
      "Just to confirm" in r["reply"]
      and "Any particular material" not in r["reply"], r["reply"][:260])
run("zm-mat-no", FLOW)
r = handle_message("no", session_id="zm-mat-no", store=None)
check("no to the image question asks material once",
      "free design support" in r["reply"] and "material" in r["reply"].lower(),
      r["reply"][:200])
r = handle_message("no", session_id="zm-mat-no", store=None)
check("one no to material after design-help goes to confirmation",
      "Just to confirm" in r["reply"]
      and "Any particular material" not in r["reply"], r["reply"][:260])

# --- 3. email step 2 for plain need statements, never for questions ---
r = run("zm-email-frag", ["stickers for my jars"])
check("stickers for my jars asks email at step 2",
      "best email" in r["reply"], r["reply"][:160])
r = run("zm-email-bare", ["mylar bags"])
check("a bare product word asks email at step 2",
      "best email" in r["reply"], r["reply"][:160])
r = run("zm-email-q", ["do you make stickers?"])
check("do you make stickers is answered, never email-hijacked",
      "best email" not in r["reply"], r["reply"][:160])
r = run("zm-email-tell", ["tell me about stickers"])
check("tell me about stickers is not email-hijacked",
      "best email" not in r["reply"], r["reply"][:160])
r = run("zm-email-job", ["Looking for a work from home job"])
check("job enquiry still deflected, never treated as an order",
      "best email" not in r["reply"], r["reply"][:160])

print("ZERO-MATERIAL-EMAIL: all passed")
