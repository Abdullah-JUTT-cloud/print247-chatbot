"""Deterministic tests for the chat brain — no API key, no network.

Run from the repo root:  python scripts/test_chat.py
Every check is a rule the old bot broke in production, so a failure
here means STOP and fix before pushing, not "the test is strict".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message
from app.chat.slots import extract_from_message, merge_slots


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    assert cond, name


# 1. Normal quote: product + size + quantity extracted, nothing missing.
r = handle_message("I need 5000 mylar bags, size 4x6 inches", store=None)
check("mylar bag + size + qty extracted", r["slots"].get("product") == "mylar bag"
      and r["slots"].get("sizes") == "4x6 inches" and r["slots"].get("quantity") == "5000")
check("complete when all required present", r["handoff"] == "complete")

# 2. Pack count is NOT quantity or size: "10 ct" must not fill either.
s = extract_from_message("I want a 10 ct gummy pouch")
check("pack count ignored", "quantity" not in s and "sizes" not in s)

# 3. MOQ: 80 is below 1000 and must be refused in code, not accepted.
r = handle_message("I need 80 boxes", store=None)
check("MOQ blocks 80", "minimum order is 1000" in r["reply"].lower())

# 4. Banners are exempt from MOQ.
r = handle_message("I need 2 banners", store=None)
check("banner exempt from MOQ", "minimum order" not in r["reply"].lower())

# 5. Template blank is not an answer: quantity stays missing.
s = merge_slots({}, extract_from_message("Hi, I need a quote for custom boxes. Qty: __ Size: __"))
check("template blanks ignored", "quantity" not in s and "sizes" not in s)

# 6. Placeholder words never count as answered.
s = merge_slots({"product": "box"}, {"material": "not specified"})
check("placeholder material ignored", "material" not in s)

# 7. Policy gap hands off instead of inventing a refund policy.
r = handle_message("What is your refund policy?", store=None)
check("refund question hands off", r["handoff"] == "policy_question"
      and "not published" in r["reply"].lower())

# 8. Roman Urdu is detected, and a missing-field question is asked.
r = handle_message("mujhe mylar bags chahiye", store=None)
check("roman urdu detected", r["language"] == "ur-roman")
check("asks next missing field", bool(r["missing"]))

# 9. No LLM key -> no fake answer, llm_used is False.
check("no fake LLM answer without key", r["llm_used"] is False)

print("All chat brain tests passed.")
