"""Tests for the full old-brain port (wave 2) — deterministic, no
key, no network.

Run from the repo root:  python scripts/test_brain2.py
Every check names the old-bot rule it guards, so a failure here
means STOP and fix before pushing, not "the test is strict".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message
from app.chat.composer import fix_reply
from app.chat.fact_topics import asks_bare_fact_topic
from app.chat.i18n import tr as itr
from app.chat.llm_extract import llm_extract
from app.chat.price_questions import asks_about_price
from app.chat.quote_value import (is_a_question_not_an_answer,
                                  is_our_own_menu, is_placeholder_value,
                                  without_template_blanks)
from app.chat.script import script_missing


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name
          + ((" :: " + detail) if detail and not cond else ""))
    assert cond, name


def run(sid, msgs):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None)
    return r


_SCRIPT = ["I need 5000 mylar bags, size 4x6 inches", "stand-up", "matte",
           "1 design", "zipper", "kraft"]

# --- full script: confirmation carries the whole spec ---
r = run("b2-script", _SCRIPT)
check("script: confirmation lists style, finish, qty, extras, material",
      "stand-up style" in r["reply"] and "matte finish" in r["reply"]
      and "5000 units" in r["reply"] and "extras zipper" in r["reply"]
      and "kraft material" in r["reply"] and r["missing"] == [])
r = run("b2-script-yes", _SCRIPT + ["Yes, that's correct"])
check("script: yes after full script starts contact flow",
      "Could I take your name?" in r["reply"])

# --- finishes: soft touch in all its spellings, never re-asked ---
for _form in ["Soft touch", "soft-touch", "softtouch", "soft touch finish"]:
    r = run("b2-soft-" + _form.replace(" ", "-"),
            ["I need mylar bags", "4x6 inches", "stand-up", _form])
    check(f"finish: '{_form}' stored, no re-ask",
          r["slots"].get("finishes") == "soft touch"
          and "finish" not in r["reply"].lower())

# --- contact flow: a refusal ends it, never re-asks the same field ---
r = run("b2-stop", ["I need custom boxes", "100x150mm", "flat-bottom", "gloss",
                    "1000 units", "3 designs", "in total", "no preference",
                    "Yes, that's correct", "NO I DONT WANT NOW"])
check("stop: first refusal closes contact flow, no email question",
      "stop here" in r["reply"] and "email" not in r["reply"].lower())
r = handle_message("I SAID I DONT WANT NOW....", session_id="b2-stop", store=None)
check("stop: repeated refusal gets a goodbye, not a question",
      "email" not in r["reply"].lower() and "?" not in r["reply"])
r = run("b2-stop-mid", ["I need mylar bags", "4x6 inches", "stop"])
check("stop: mid-quote stop pauses, does not ask the next field",
      "stop asking" in r["reply"] and "style" not in r["reply"].lower())
r = run("b2-stop-spec", ["I need mylar bags", "4x6 inches", "stand-up",
                         "I don't want matte"])
check("stop: 'I don't want matte' is a finish answer, not a stop",
      r["slots"].get("finishes") in (None, "matte") and "stop asking" not in r["reply"])

# --- capability questions: Yes + product stored + size asked ---
for _msg, _prod in [
    ("do you make 13 inch pizza boxes", "box"),
    ("ok do you maqke corrogated boxes", "box"),
    ("ok do you make corrogated boxes", "box"),
    ("do you make lables", "label"),
    ("do you make milar bags", "mylar bag"),
    ("do you make business cards", "business card"),
    ("can you print stickers", "sticker"),
]:
    r = run("b2-cap-" + _msg.replace(" ", "-")[:30], [_msg])
    check(f"capability '{_msg}'",
          r["reply"].startswith("Yes") and r["slots"].get("product") == _prod
          and "What product are you looking for" not in r["reply"]
          and ("What size" in r["reply"] or "What style" in r["reply"]),
          f"reply={r['reply'][:110]!r} slots={r['slots']!r}")
r = run("b2-cap-pizza-size", ["do you make 13 inch pizza boxes"])
check("capability pizza: stated size stored, style asked next",
      r["slots"].get("sizes") == "13 inch"
      and "What style of box" in r["reply"]
      and "(see facts/moq.md for context" not in r["reply"],
      f"slots={r['slots']!r} reply={r['reply'][-100:]!r}")
r = run("b2-cap-unknown", ["do you make t-shirts"])
check("capability unknown product gets no Yes",
      not r["reply"].startswith("Yes") and r["slots"].get("product") is None,
      f"reply={r['reply'][:110]!r}")

# --- direct answers: one sentence for the asked fact, never a dump ---
for _msg, _want, _banned in [
    ("where are you located?", "Rosenberg", ["807-3429", "Support@"]),
    ("what is your phone number?", "807-3429", ["Cottonwood"]),
    ("what is your email address?", "Support@", ["Cottonwood"]),
    ("What is your refund policy?", "5 business days", ["summary"]),
    ("What payment methods do you accept?", "Visa", []),
    ("Is shipping free?", "free nationwide", []),
]:
    r = run("b2-direct-" + _msg.replace(" ", "-")[:30], [_msg])
    check(f"direct answer '{_msg}'",
          _want in r["reply"]
          and all(b not in r["reply"] for b in _banned),
          f"reply={r['reply'][:160]!r}")

# --- trust, hostility, small talk: never a KB fact dump ---
for _msg, _want, _banned in [
    ("you guys are fake and scam right?", "real company",
     ["Minimum order quantity", "1000"]),
    ("are you legit?", "real company", ["Minimum order quantity"]),
    ("is this company real?", "real company", ["Minimum order quantity"]),
    ("tum fake ho", "real company", ["Minimum order quantity"]),
    ("you are liars", "wrong answer", ["Minimum order quantity"]),
    ("you scammed me", "order number", ["Minimum order quantity"]),
    ("thanks", "welcome", ["Minimum order quantity"]),
    ("bye", "Goodbye", ["Minimum order quantity"]),
    ("how are you?", "doing well", ["Minimum order quantity"]),
    ("are you human?", "not a person", []),
    ("are you a bot?", "automated assistant", []),
]:
    r = run("b2-trust-" + _msg.replace(" ", "-")[:30], [_msg])
    check(f"conversational '{_msg}'",
          _want.lower() in r["reply"].lower()
          and all(b not in r["reply"] for b in _banned),
          f"reply={r['reply'][:160]!r}")
r = run("b2-trust-order-wins", ["thanks, I need 500 mylar bags"])
check("trust guard: order beats thanks",
      r["slots"].get("product") == "mylar bag"
      and r["slots"].get("quantity") == "500",
      f"slots={r['slots']!r}")
r = run("b2-trust-product-q", ["is this box real cardboard?"])
check("trust guard: product question is not a trust question",
      "real company" not in r["reply"],
      f"reply={r['reply'][:120]!r}")

# --- location + foreign country: plain not-here answer ---
for _msg, _disp in [("where it located in pakistan", "Pakistan"),
                    ("are you located in india?", "India"),
                    ("do you have an office in china?", "China")]:
    r = run("b2-loc-" + _disp, [_msg])
    check(f"location '{_msg}'",
          "Rosenberg" in r["reply"]
          and f"don't have a location in {_disp}" in r["reply"],
          f"reply={r['reply'][:130]!r}")

# --- delivery scope: US published, international goes to the team ---
for _q in ["can you deliver in china?", "do you ship to india?",
           "delivery to canada?", "can you deliver to the uk?"]:
    r = run("b2-ship", [_q])
    check(f"delivery: '{_q}' grounded, never promised",
          "free nationwide" in r["reply"] and "UPS" in r["reply"]
          and "team will confirm" in r["reply"])

# --- multi-design quantity scope: total vs per design ---
r = run("b2-split", ["I need 5000 mylar bags, size 4x6 inches", "stand-up", "matte",
                     "3 designs"])
check("split: qty given before designs is clarified, not assumed",
      "in total, or 5,000 of each" in r["reply"])
r = run("b2-split-per", ["I need 5000 mylar bags, size 4x6 inches", "stand-up", "matte",
                         "3 designs", "per design", "zipper", "kraft"])
check("split: per-design answer confirms per design + total",
      "5000 units per design, 3 designs (total 15000 units)" in r["reply"])
r = run("b2-split-total", ["I need 5000 mylar bags, size 4x6 inches", "stand-up", "matte",
                           "3 designs", "in total", "zipper", "kraft"])
check("split: total answer confirms total, never multiplies",
      "5000 units total, 3 designs" in r["reply"])
r = run("b2-split-nodup", ["I need 3 designs of mylar bags", "4x6 inches", "stand-up",
                           "matte", "5000 units"])
check("split: answer to a per-design question is never re-asked",
      "in total, or" not in r["reply"])

# --- below-minimum: accepted, minimum stated, smaller run noted ---
r = run("b2-moq", ["I need 80 boxes", "4x6 inches"])
check("moq: below-minimum accepted, note on confirmation path",
      r["slots"].get("quantity") == "80")
r = run("b2-smaller", ["I need 80 boxes", "4x6 inches", "can you do a smaller run"])
check("moq: smaller run put to the team, never refused",
      "I'll put 80 to the team" in r["reply"])

# --- price question: pricing comes with the quote, never a figure ---
check("price: 'how much' is a price question", asks_about_price("How much does 1000 pieces cost?"))
check("price: 'I need a quote' is NOT a price question",
      not asks_about_price("Hi, I need a quote for custom boxes"))
r = run("b2-price", ["How much does 1000 pieces cost?"])
check("price: answered with pricing line + product question",
      "your quote will carry the pricing" in r["reply"]
      and "What product" in r["reply"])

# --- bare fact topic: "Moq" alone is answered, not stored as skus ---
check("bare: 'Moq' is a bare fact topic", asks_bare_fact_topic("Moq") == "the minimum order")
r = run("b2-bare", ["I need mylar bags", "Moq"])
check("bare: answered from moq file, skus untouched",
      "1000" in r["reply"] and r["slots"].get("skus") in (None, "1")
      and "What size" in r["reply"])

# --- plain packaging: skus never asked ---
r = run("b2-plain", ["I need a plain white box", "10x8x4 inches", "flat",
                     "matte", "1000 units", "kraft"])
check("plain: confirmation with no designs question asked",
      r["missing"] == [] and "design" not in r["reply"].lower())

# --- a question is never an answer; our own menu is not an answer ---
r = run("b2-qna", ["Do you make 4x6 mylar bags?"])
check("qna: capability question stores product+size, asks style next",
      r["slots"].get("product") == "mylar bag"
      and r["slots"].get("sizes") == "4x6"
      and r["reply"].startswith("Yes")
      and "What style of Mylar bag" in r["reply"])
r = run("b2-menu", ["boxes, bags, or labels"])
check("menu: own menu echoed back stores no product",
      "product" not in r["slots"])
check("menu: unit check", is_our_own_menu("boxes, bags, or labels"))
check("question: unit check",
      is_a_question_not_an_answer("What is a standard package size?"))
check("placeholder: unit check",
      is_placeholder_value("not specified") and is_placeholder_value("Qty: __")
      and not is_placeholder_value("not sure"))
check("blanks: unit check",
      without_template_blanks("Size: __16\"×10\"") == "16\"×10\"")

# --- template blanks through the brain ---
r = run("b2-blanks", ["Hi, I need a quote for custom boxes. Qty: __ Size: __"])
check("blanks: brain stores neither quantity nor size",
      "quantity" not in r["slots"] and "sizes" not in r["slots"])

# --- finished chat: sign-off, not-yet, noted — never the close twice ---
r = run("b2-fin", _SCRIPT + ["Yes, that's correct", "Sara", "sara@example.com",
                             "5551234567", "thanks"])
check("finished: pleasantry gets a sign-off, not the close again",
      "talk soon" in r["reply"] and "Thanks for sharing" not in r["reply"])
r = run("b2-fin2", _SCRIPT + ["Yes, that's correct", "Sara", "sara@example.com",
                              "5551234567", "did you email me"])
check("finished: arrived question gets 'not yet' + window",
      r["reply"].startswith("Not yet"))
r = run("b2-fin3", _SCRIPT + ["Yes, that's correct", "Sara", "sara@example.com",
                              "5551234567", "actually make it matte"])
check("finished: new detail is noted, chat stays finished",
      r["reply"].startswith("Noted"))

# --- phone digits never overwrite the quantity ---
r = run("b2-phone", _SCRIPT + ["Yes, that's correct", "Sara", "sara@example.com",
                               "5551234567"])
check("phone: contact phone keeps quantity 5000",
      r["slots"].get("quantity") == "5000" and r["handoff"] == "complete")

# --- session language sticks across turns ---
r = run("b2-es", ["Necesito bolsas mylar", "4x6 pulgadas"])
check("i18n: Spanish sticks, sizes question in Spanish",
      r["language"] == "es" and r["reply"].startswith("¿Qué estilo")
      and r["slots"].get("sizes") == "4x6 inches")
check("i18n: unit check",
      itr("q_sizes", "es", "What size?").startswith("¿Qué tamaño")
      and itr("q_sizes", "ur-roman", "What size?").startswith("Size kya"))

# --- composer: unsalvageable replies fall back, others are repaired ---
_ctx = {"visitor_text": "How much does it cost?", "visitor_texts": ["How much does it cost?"],
        "visitor_asking": True, "last_bot_text": "", "slots": {"product": "box"},
        "answered_fields": ["product"], "contact": {}, "is_banner": False,
        "is_plain": False, "minimum_due": False, "asked_price": True,
        "asked_usual": False, "asked_arrived": False, "unclear": False}
check("composer: quote announcement is unsalvageable",
      fix_reply("I'll prepare a quote for you.", _ctx, "What size?", lambda t: None) is None)
check("composer: dodged price gets the pricing line inserted",
      "your quote will carry the pricing" in (
          fix_reply("Got it. What size do you need?", _ctx, "What size?", lambda t: None) or ""))
_ctx2 = dict(_ctx, visitor_text="I need boxes", visitor_texts=["I need boxes"],
             visitor_asking=False, asked_price=False,
             slots={"product": "box"}, answered_fields=["product"])
check("composer: asking for what we have is replaced by next question",
      fix_reply("What product are you looking for?", _ctx2, "What size?", lambda t: None)
      == "What size?")

# --- LLM extraction without a key never invents anything ---
check("llm-extract: no key means no extraction", llm_extract("the big ones for coffee") == {})

# --- script_missing never mistakes defaults for answers ---
check("script: defaults do not count as answered",
      "skus" in script_missing({"product": "box", "skus": "1", "extras": "none"},
                               {"answered_fields": []}))

print("All wave-2 brain tests passed.")
