"""Early email (step 2) + greeting-back + MOQ-never-volunteered.

Oct 30 user rules:
- Email is step 2: product first, email second, then the quote chat
  continues. It was NOT happening before (contact came only after
  confirmation) — this suite proves it now happens.
- MOQ is never volunteered: not with the quantity question, not
  with a below-minimum quantity, not in a confirmation, not in a
  "not sure" reply. Only when the visitor asks about it.
- Greeting-only ("good morning") gets a greeting back, then the
  product question — never just the product question alone.

Run from the repo root:  python scripts/test_early_email_greeting.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message


def run(sid, msgs):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None)
    return r


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# --- Greeting back ---
r = run("ee-greet-am", ["good morning"])
check("good morning gets greeting back + product question",
      r["reply"].startswith("Good morning!") and "What product" in r["reply"],
      r["reply"][:120])
r = run("ee-greet-hi", ["hi"])
check("hi gets greeting back + product question",
      r["reply"].startswith("Hi there!") and "What product" in r["reply"],
      r["reply"][:120])
r = run("ee-greet-order", ["good morning, I need boxes"])
check("greeting + order is an order, not a greeting-only turn",
      "email" in r["reply"].lower() and r["slots"].get("product") == "box",
      r["reply"][:120])

# --- Early email: step 2 ---
r = run("ee-step2", ["I need mylar bags"])
check("order turn 1 asks email at step 2",
      "email" in r["reply"].lower() and r["slots"].get("product") == "mylar bag",
      r["reply"][:120])
r = run("ee-step2-then", ["I need mylar bags", "ali@test.com"])
check("after email, chat continues to size question",
      "What size" in r["reply"],
      r["reply"][:120])
r = run("ee-volunteered", ["I need mylar bags, email ali@test.com"])
check("email volunteered with order is not asked again",
      "email" not in r["reply"].lower() or "What size" in r["reply"],
      r["reply"][:120])
r = run("ee-refuse-once", ["I need mylar bags", "I prefer not to share my email"])
check("first email refusal insists with reason, not retires",
      "I need an email" in r["reply"],
      r["reply"][:120])
r = run("ee-refuse-twice", ["I need mylar bags", "I prefer not to share my email",
                            "no"])
check("second email refusal retires it and script continues",
      "What size" in r["reply"] and "email" not in r["reply"].lower(),
      r["reply"][:120])
r = run("ee-fact-not-hijacked", ["How quick can I have labels shipped?"])
check("fact question naming a product is answered, not email-hijacked",
      "email" not in r["reply"].lower(),
      r["reply"][:120])

# --- MOQ never volunteered ---
r = run("ee-moq-below", ["I need 300 boxes", "ali@test.com"])
check("below-min quantity: smaller runs, no 1000",
      "We can look at 300" in r["reply"] and "1000" not in r["reply"],
      r["reply"][:200])
r = run("ee-moq-asked", ["What is the minimum order?"])
check("MOQ still answered when the visitor asks",
      "1000" in r["reply"],
      r["reply"][:120])
r = run("ee-moq-notsure", ["I need boxes", "ali@test.com", "4x6 inches",
                           "mailer", "matte", "not sure"])
check("not-sure quantity never volunteers the minimum",
      "1000" not in r["reply"],
      r["reply"][:200])

print("EARLY-EMAIL-GREETING: all passed")
