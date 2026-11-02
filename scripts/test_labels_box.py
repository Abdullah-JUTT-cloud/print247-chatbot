"""Labels-for-box task — section 13 queued task.

When a customer asks for labels or stickers for boxes/bags/pouches,
the ordered product is label (or sticker), not box or bag.
Labels and stickers sit before containers in product matching, so
container-noun adjuncts and prepositional phrases ("box labels",
"labels for boxes", "stickers for boxes", "labels for my box")
resolve to label/sticker, while pure container orders ("custom boxes")
remain boxes.

Run from repo root:  python scripts/test_labels_box.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message
from app.chat.slots import extract_from_message
from app.chat.capability import capability_product


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# 1. Deterministic slot extraction tests
cases = [
    ("I need labels for my box", "label"),
    ("labels for boxes", "label"),
    ("label for box", "label"),
    ("box labels", "label"),
    ("stickers for boxes", "sticker"),
    ("box stickers", "sticker"),
    ("custom boxes", "box"),
    ("mailer box", "box"),
    ("labels for mylar bags", "label"),
    ("pouch labels", "label"),
]
for text, want in cases:
    got = extract_from_message(text).get("product")
    check(f"slot: {text!r} -> {want!r}", got == want, f"got {got!r}")

# 2. Capability matching
cap_cases = [
    ("do you make labels for boxes?", "label"),
    ("can you make stickers for boxes?", "sticker"),
    ("do you make boxes for bottles?", "box"),
    ("can you make mylar bags?", "mylar bag"),
    ("do you make custom boxes?", "box"),
]
for q, want in cap_cases:
    got = capability_product(q)
    check(f"capability: {q!r} -> {want!r}", got == want, f"got {got!r}")

# 3. Full brain quote flow
r = handle_message("I need labels for my box", session_id="lfb-turn1", store=None)
check("brain: 'I need labels for my box' records product=label",
      r["slots"].get("product") == "label", f"slots={r.get('slots')}")
check("brain: reply acknowledges label, not box",
      "label" in r["reply"].lower() and "box." not in r["reply"].lower(),
      f"reply={r.get('reply')[:120]}")

r2 = handle_message("stickers for my boxes", session_id="lfb-turn2", store=None)
check("brain: 'stickers for my boxes' records product=sticker",
      r2["slots"].get("product") == "sticker", f"slots={r2.get('slots')}")
check("brain: reply acknowledges sticker",
      "sticker" in r2["reply"].lower(),
      f"reply={r2.get('reply')[:120]}")

print("All labels-for-box tests passed.")
