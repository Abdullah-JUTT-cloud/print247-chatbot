"""Product extraction for '<product A> for <product B>' pattern.

When a visitor says 'i need labels for my pizza box', the product they are
ordering is labels, and 'pizza box' is what the labels are used for.
Similarly, 'boxes for my labels' is ordering boxes, and 'labels' is the use.
Single-product messages ('i need pizza boxes') and mid-quote product switches
must remain completely intact.

Run from repo root:  python scripts/test_product_for_use.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message
from app.chat.slots import extract_from_message, find_product


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# 1. Deterministic slot extraction tests
cases = [
    ("i need labels for my pizza box", "label"),
    ("i need stickers for my jars", "sticker"),
    ("i need boxes for my candles", "box"),
    ("i need pizza boxes", "box"),
    ("i need mylar bags for coffee", "mylar bag"),
    ("i need boxes for my labels", "box"),
    ("i need pouches for my stickers", "pouch"),
    ("for my pizza box, i need labels", "label"),
]
for text, want in cases:
    got = extract_from_message(text).get("product")
    check(f"slot: {text!r} -> {want!r}", got == want, f"got {got!r}")

# 2. Brain flow tests (fresh sessions)
r = handle_message("i need labels for my pizza box", session_id="pfu-label-pizza-box", store=None)
check("brain: 'i need labels for my pizza box' stores product=label",
      r["slots"].get("product") == "label",
      f"slots={r.get('slots')}")
check("brain: reply asks email for a label quote, not box",
      "label" in r["reply"].lower() and "box." not in r["reply"].lower() and "email" in r["reply"].lower(),
      f"reply={r.get('reply')!r}")

r = handle_message("i need stickers for my jars", session_id="pfu-stickers-jars", store=None)
check("brain: 'i need stickers for my jars' stores product=sticker",
      r["slots"].get("product") == "sticker" and "email" in r["reply"].lower(),
      f"slots={r.get('slots')} reply={r.get('reply')!r}")

r = handle_message("i need boxes for my candles", session_id="pfu-boxes-candles", store=None)
check("brain: 'i need boxes for my candles' stores product=box",
      r["slots"].get("product") == "box" and "email" in r["reply"].lower(),
      f"slots={r.get('slots')} reply={r.get('reply')!r}")

r = handle_message("i need pizza boxes", session_id="pfu-pizza-boxes", store=None)
check("brain: 'i need pizza boxes' stores product=box (no regression)",
      r["slots"].get("product") == "box" and "email" in r["reply"].lower(),
      f"slots={r.get('slots')} reply={r.get('reply')!r}")

r = handle_message("i need mylar bags for coffee", session_id="pfu-mylar-coffee", store=None)
check("brain: 'i need mylar bags for coffee' stores product=mylar bag",
      r["slots"].get("product") == "mylar bag" and "email" in r["reply"].lower(),
      f"slots={r.get('slots')} reply={r.get('reply')!r}")

# 3. Mid-quote switch flow test: box quote -> "i need labels" -> switch confirmation -> "yes i want to switch to labels"
sid_switch = "pfu-switch-box-to-label"
r_t1 = handle_message("i need boxes", session_id=sid_switch, store=None)
check("switch t1: stores product=box", r_t1["slots"].get("product") == "box")

r_t2 = handle_message("i need labels", session_id=sid_switch, store=None)
check("switch t2: asks switch confirmation",
      "switch to label" in r_t2["reply"].lower() and "box" in r_t2["reply"].lower(),
      f"reply={r_t2.get('reply')!r}")

r_t3 = handle_message("yes i want to switch to labels", session_id=sid_switch, store=None)
check("switch t3: switches to label and asks size question",
      r_t3["slots"].get("product") == "label"
      and "switching" in r_t3["reply"].lower()
      and "size" in r_t3["reply"].lower(),
      f"slots={r_t3.get('slots')} reply={r_t3.get('reply')!r}")

print("All product-for-use tests passed.")
