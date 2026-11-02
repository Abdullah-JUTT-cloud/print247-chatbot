"""Change-a-field + what-type-of-attribute — Nov 3 live test,
fixed globally (every field, every attribute), not just finish.

1. "i want to change finish.." (no new value) was ignored on
   VM and, on live, the LLM ack invented a "hanging finish" and
   moved on to quantity. A change request now re-asks that
   field — never invents a value, never acks-and-continues.
   A new value in the same message ("change finish to matte")
   keeps the normal correction flow.
2. "what type of finish do you provide?" was deflected as an
   unknown product ("Finish isn't a listed product..."). An
   attribute word is never a product: finishes get the script's
   own offer, materials/styles fall through to fact handling
   instead of the fake-product reply.

Run from the repo root:  python scripts/test_change_attribute.py
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


def to_quantity(sid):
    return run(sid, ["I need labels", "ab@gmail.com", "6x4 inches", "gloss"])


# --- 1. change-a-field re-asks the field ---
r = to_quantity("ca-finish")
r = handle_message("i want to change finish..", session_id="ca-finish",
                   store=None)
check("'change finish' re-asks finishes, invents nothing",
      "What finish do you prefer" in r["reply"]
      and "hanging" not in r["reply"].lower()
      and not r["slots"].get("finishes"), r["reply"][:200])
r = handle_message("matte", session_id="ca-finish", store=None)
check("the new finish then flows on to quantity",
      "quantity" in r["reply"].lower()
      and r["slots"].get("finishes") == "matte", r["reply"][:200])
r = to_quantity("ca-qty")
r = handle_message("i want to change quantity", session_id="ca-qty",
                   store=None)
check("'change quantity' re-asks quantity",
      "What quantity" in r["reply"], r["reply"][:200])
r = to_quantity("ca-mat")
r = handle_message("change the finish to matte", session_id="ca-mat",
                   store=None)
check("'change finish to matte' keeps the correction flow",
      "matte" in r["reply"].lower()
      and "What finish" not in r["reply"], r["reply"][:200])
r = to_quantity("ca-size")
r = handle_message("change size to 4x6 inches", session_id="ca-size",
                   store=None)
check("'change size to 4x6' keeps the new size, no re-ask",
      r["slots"].get("sizes") == "4x6 inches"
      and "What size" not in r["reply"], r["reply"][:200])

# --- 2. what-type-of-attribute ---
r = to_quantity("ca-typef")
r = handle_message("what type of finish do you provide?",
                   session_id="ca-typef", store=None)
check("'what type of finish' answers the finishes, not a deflection",
      "matte, gloss, and soft touch" in r["reply"]
      and "isn't a listed product" not in r["reply"]
      and "What quantity" in r["reply"], r["reply"][:260])
r = to_quantity("ca-typem")
r = handle_message("what type of material do you provide?",
                   session_id="ca-typem", store=None)
check("'what type of material' never deflects as a fake product",
      "isn't a listed product" not in r["reply"], r["reply"][:260])
r = to_quantity("ca-types")
r = handle_message("what types of boxes do you offer?",
                   session_id="ca-types", store=None)
check("product types questions still work",
      "boxes" in r["reply"].lower(), r["reply"][:200])

print("CHANGE-ATTRIBUTE: all passed")
