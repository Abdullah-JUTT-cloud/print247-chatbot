"""Synthetic adversarial eval: template families x phrasings, run
through the real brain, asserted on slots and reply text.

Every failure here is a wrong answer a visitor could hit live. The
families come from the old chats' failure modes (re-asked finishes,
ignored refusals, dodged questions, menu echoes, template blanks)
plus the Oct 29 live transcript (soft touch, contact pestering,
China delivery). A family that fails systematically gets a code fix,
not a weaker assertion.
"""
import itertools
import re
import sys

sys.path.insert(0, ".")
from app.chat.brain import handle_message

FAILURES = []
PASSES = [0]


def run(sid, msgs):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None)
    return r


def check(name, ok, detail=""):
    if ok:
        PASSES[0] += 1
    else:
        FAILURES.append(f"{name} :: {detail}")


# --- 1. finishes: every form, bare and in a sentence ---
FINISH_CASES = [
    ("matte", "matte"), ("Matte", "matte"), ("matt", "matte"),
    ("I want matte", "matte"), ("matte finish", "matte"),
    ("gloss", "gloss"), ("glossy", "gloss"), ("I want gloss", "gloss"),
    ("Soft touch", "soft touch"), ("soft-touch", "soft touch"),
    ("softtouch", "soft touch"), ("soft touch finish", "soft touch"),
    ("I prefer soft touch", "soft touch"),
    ("spot uv", "spot uv"), ("foil stamping", "foil stamping"),
    ("embossing", "embossing"), ("no finish", "none"),
]
for i, (msg, want) in enumerate(FINISH_CASES):
    r = run(f"ev-fin-{i}", ["I need mylar bags", "4x6 inches", "stand-up", msg])
    check(f"finish {msg!r}", r["slots"].get("finishes") == want
          and "finish" not in r["reply"].lower(),
          f"got finishes={r['slots'].get('finishes')!r} reply={r['reply'][:100]!r}")

# --- 2. negations: a rejected option must never be stored ---
NEG_CASES = [
    ("not matte", "finishes", "matte"),
    ("I don't want matte", "finishes", "matte"),
    ("no gloss", "finishes", "gloss"),
    ("anything but gloss", "finishes", "gloss"),
]
for i, (msg, field, banned) in enumerate(NEG_CASES):
    r = run(f"ev-neg-{i}", ["I need mylar bags", "4x6 inches", "stand-up", msg])
    check(f"negation {msg!r}", r["slots"].get(field) != banned,
          f"stored {field}={r['slots'].get(field)!r}")
for i, msg in enumerate(["without zipper", "no zipper", "no window",
                         "I don't want a tear notch"]):
    r = run(f"ev-nege-{i}", ["I need mylar bags", "4x6 inches", "stand-up",
                             "matte", "5000 units", "1 design", msg])
    stored = r["slots"].get("extras") or ""
    bad = any(w in stored for w in
              (["zipper"] if "zipper" in msg else
               ["window"] if "window" in msg else ["tear notch"]))
    check(f"negation extras {msg!r}", not bad, f"stored extras={stored!r}")

# --- 3. contact declines and stops: never re-ask, never pester ---
# Global stops close the flow outright. Field declines ("no thanks"
# to the name question) retire that field and move on — that is the
# old design, and it is bounded: a second decline retires the next
# field, and exhaustion closes the flow. What must never happen is
# the SAME question twice after a refusal.
GLOBAL_STOPS = [
    "NO I DONT WANT NOW", "I SAID I DONT WANT NOW....", "I don't want now",
    "not now", "stop", "stop asking", "leave me alone", "don't contact me",
    "no more questions", "not interested", "I don't want to share",
]
for i, msg in enumerate(GLOBAL_STOPS):
    sid = f"ev-stop-{i}"
    run(sid, ["I need custom boxes", "100x150mm", "flat-bottom", "gloss",
              "1000 units", "1 design", "no preference",
              "Yes, that's correct"])
    r = handle_message(msg, session_id=sid, store=None)
    check(f"stop {msg!r}",
          "?" not in r["reply"] and "email" not in r["reply"].lower()
          and "phone" not in r["reply"].lower(),
          f"reply={r['reply'][:120]!r}")
for i, msg in enumerate(["no thanks", "later"]):
    sid = f"ev-decl-{i}"
    run(sid, ["I need custom boxes", "100x150mm", "flat-bottom", "gloss",
              "1000 units", "1 design", "no preference",
              "Yes, that's correct"])
    r = handle_message(msg, session_id=sid, store=None)
    check(f"field decline {msg!r} moves on, never repeats",
          "Could I take your name?" not in r["reply"],
          f"reply={r['reply'][:120]!r}")

# --- 4. delivery scope: every country, grounded, never promised ---
COUNTRIES = ["china", "india", "uk", "canada", "australia", "germany",
             "france", "uae", "pakistan", "mexico", "brazil", "japan"]
for c in COUNTRIES:
    for ph in [f"can you deliver in {c}?", f"do you ship to {c}?",
               f"delivery to {c}?"]:
        r = run(f"ev-ship-{c}", [ph])
        check(f"delivery {ph}",
              "outside the USA" in r["reply"] and "team will confirm" in r["reply"]
              and "free nationwide" not in r["reply"]
              and f"deliver to {c}" not in r["reply"].lower()
              and f"ship to {c}" not in r["reply"].lower(),
              f"reply={r['reply'][:130]!r}")

# --- 5. quantities: spellings, separators, units ---
QTY_CASES = [
    ("15 thousand", "15000"), ("fifteen thousand", "15000"),
    ("1000 units", "1000"), ("1,000 units", "1000"), ("5000 pcs", "5000"),
    ("10000 pieces", "10000"), ("80 units", "80"), ("250", "250"),
    ("two thousand", "2000"), ("ten thousand units", "10000"),
]
for i, (msg, want) in enumerate(QTY_CASES):
    r = run(f"ev-qty-{i}", ["I need mylar bags", "4x6 inches", "stand-up",
                            "matte", msg])
    check(f"quantity {msg!r}", r["slots"].get("quantity") == want,
          f"got {r['slots'].get('quantity')!r}")

# --- 6. designs: counts in words and forms ---
SKU_CASES = [("3 designs", "3"), ("three designs", "3"), ("2 types", "2"),
             ("1 design", "1"), ("single design", "1"), ("5 SKUs", "5"),
             ("4 different designs", "4")]
for i, (msg, want) in enumerate(SKU_CASES):
    r = run(f"ev-sku-{i}", ["I need mylar bags", "4x6 inches", "stand-up",
                            "matte", "5000 units", msg])
    check(f"designs {msg!r}", r["slots"].get("skus") == want,
          f"got {r['slots'].get('skus')!r} reply={r['reply'][:100]!r}")

# --- 7. sizes: separators and units ---
SIZE_CASES = ["4x6 inches", "4 x 6 inches", "4 by 6 inches", "100x150mm",
              "10*14", "4x6", "100 x 150 mm"]
for i, msg in enumerate(SIZE_CASES):
    r = run(f"ev-size-{i}", ["I need mylar bags", msg])
    check(f"size {msg!r}", bool(r["slots"].get("sizes")),
          f"got {r['slots'].get('sizes')!r} reply={r['reply'][:100]!r}")

# --- 8. price questions: the line, never a figure ---
for i, msg in enumerate(["what's the price?", "how much does it cost?",
                         "price for 5000 bags", "what is the cost of boxes?",
                         "give me a price"]):
    r = run(f"ev-price-{i}", [msg])
    check(f"price {msg!r}",
          "can't price it here" in r["reply"]
          and not any(f"${n}" in r["reply"] for n in range(10)),
          f"reply={r['reply'][:130]!r}")

# --- 9. bare topics: short questions get the fact, not the script ---
TOPIC_CASES = [
    ("moq", "1000"), ("what is the moq?", "1000"),
    ("turnaround", "business days"), ("how long does it take?", "business days"),
    ("where are you located?", "Rosenberg"),
    ("do you ship free?", "free nationwide"),
    ("what payment methods?", "PayPal"),
    ("samples?", "sample"),
]
for i, (msg, needle) in enumerate(TOPIC_CASES):
    r = run(f"ev-topic-{i}", [msg])
    check(f"topic {msg!r}", needle.lower() in r["reply"].lower(),
          f"reply={r['reply'][:130]!r}")

# --- 10. deflections: jobs, pitches, partnerships are not orders ---
for i, msg in enumerate(["i need a job", "are you hiring?",
                         "I want to work with you",
                         "we are a supplier from China, let's partner"]):
    r = run(f"ev-defl-{i}", [msg])
    check(f"deflection {msg!r}",
          "product" not in r["reply"].lower() or "email" in r["reply"].lower(),
          f"reply={r['reply'][:130]!r}")

# --- 11. adversarial: echoes, blanks, questions-as-answers ---
r = run("ev-adv-1", ["boxes, bags, or labels"])
check("menu echo is not an answer", r["slots"].get("product") is None,
      f"stored product={r['slots'].get('product')!r}")
r = run("ev-adv-2", ["Qty: __ Size: __"])
check("template blanks stored nothing",
      not r["slots"].get("quantity") and not r["slots"].get("sizes"),
      f"slots={r['slots']!r}")
r = run("ev-adv-3", ["Do you make 4x6 mylar bags?"])
check("capability question stores stated size, asks style next",
      r["slots"].get("sizes") == "4x6"
      and "What style of Mylar bag" in r["reply"],
      f"slots={r['slots']!r} reply={r['reply'][:110]!r}")
r = run("ev-adv-4", ["Do you print in 24 hours?"])
check("24 hours is turnaround, not quantity",
      r["slots"].get("quantity") is None and "business days" in r["reply"],
      f"slots={r['slots']!r} reply={r['reply'][:120]!r}")
r = run("ev-adv-5", ["asdasd qwerty zz"])
check("gibberish does not crash", bool(r["reply"]),
      f"reply={r['reply'][:80]!r}")

# --- 12. full flows: confirmation carries every part ---
FLOW_CASES = [
    ["I need mylar bags", "4x6 inches", "stand-up", "matte", "5000 units",
     "3 designs", "per design", "zipper", "kraft"],
    ["I need custom boxes", "100x150mm", "corrugated", "mailer", "gloss",
     "1000 units", "3 designs", "in total", "no preference"],
]
for i, msgs in enumerate(FLOW_CASES):
    prod = msgs[0].replace("I need ", "")
    qty = msgs[4]
    r = run(f"ev-flow-{i}", msgs)
    check(f"full flow {i} confirms everything",
          "Just to confirm" in r["reply"]
          and ("box" in r["reply"] or prod.split()[0] in r["reply"])
          and qty.split()[0] in r["reply"],
          f"reply={r['reply'][:200]!r}")

# --- 13. combinatorial expansion: same families, every phrasing ---
for _fi, f in enumerate(["matte", "gloss", "soft touch", "spot uv", "foil stamping", "embossing"]):
    for _ti, tmpl in enumerate(["{f}", "I want {f}", "{f} finish", "prefer {f}", "{f} please"]):
        msg = tmpl.format(f=f)
        r = run(f"ev-cf-{_fi}-{_ti}",
                ["I need mylar bags", "4x6 inches", "stand-up", msg])
        check(f"combo finish {msg!r}", r["slots"].get("finishes") == f,
              f"got {r['slots'].get('finishes')!r}")
for _ni, n in enumerate(["80", "500", "1000", "5000", "15000", "100000"]):
    for _si, suf in enumerate(["units", "pcs", "pieces", ""]):
        msg = (n + " " + suf).strip()
        r = run(f"ev-cq-{_ni}-{_si}",
                ["I need mylar bags", "4x6 inches", "stand-up", "matte", msg])
        check(f"combo qty {msg!r}", r["slots"].get("quantity") == n,
              f"got {r['slots'].get('quantity')!r}")
for _di, d in enumerate(["4x6", "10x14", "100x150", "3x3x5", "10*14"]):
    for _ui, u in enumerate(["inches", "mm", ""]):
        msg = (d + " " + u).strip()
        r = run(f"ev-cs-{_di}-{_ui}", ["I need mylar bags", msg])
        check(f"combo size {msg!r}", bool(r["slots"].get("sizes")),
              f"got {r['slots'].get('sizes')!r}")
for _nfi, f in enumerate(["matte", "gloss", "soft touch"]):
    for _nti, tmpl in enumerate(["not {f}", "no {f}", "don't want {f}", "anything but {f}"]):
        msg = tmpl.format(f=f)
        r = run(f"ev-cneg-{_nfi}-{_nti}",
                ["I need mylar bags", "4x6 inches", "stand-up", msg])
        check(f"combo neg finish {msg!r}",
              r["slots"].get("finishes") != f,
              f"stored {r['slots'].get('finishes')!r}")
for _pi, msg in enumerate(["price?", "what is the price?", "how much?", "how much for boxes?",
            "price for 5000 mylar bags", "give me a price", "need price",
            "price please", "what does it cost?", "how much does it cost?"]):
    r = run(f"ev-cprice-{_pi}", [msg])
    check(f"combo price {msg!r}", "can't price it here" in r["reply"],
          f"reply={r['reply'][:120]!r}")
for _sci, c in enumerate(["china", "india", "canada", "germany"]):
    for _sti, tmpl in enumerate(["do you deliver to {c}", "shipping to {c}?", "ship to {c}"]):
        msg = tmpl.format(c=c)
        r = run(f"ev-cship-{_sci}-{_sti}", [msg])
        check(f"combo delivery {msg!r}",
              "outside the USA" in r["reply"] and "team will confirm" in r["reply"]
              and "free nationwide" not in r["reply"],
              f"reply={r['reply'][:120]!r}")

# --- 14. capability questions: every phrasing x product x typo ---
CAP_PRODUCTS = [
    ("pizza boxes", "box"), ("corrugated boxes", "box"),
    ("mylar bags", "mylar bag"), ("stand-up pouches", "pouch"),
    ("labels", "label"), ("stickers", "sticker"), ("banners", "banner"),
    ("business cards", "business card"), ("boxes", "box"), ("bags", "bag"),
    ("lables", "label"), ("puches", "pouch"), ("milar bags", "mylar bag"),
]
CAP_TEMPLATES = [
    "do you make {p}", "can you make {p}", "do you print {p}",
    "can you print {p}", "do you offer {p}", "do you do {p}",
    "can you produce {p}", "do you sell {p}", "do you make {p}?",
    "ok do you make {p}", "hi, do you make {p}", "do you maqke {p}",
    "do u make {p}", "do you mak {p}",
]
for _ci, (prod_text, want) in enumerate(CAP_PRODUCTS):
    for _ti, tmpl in enumerate(CAP_TEMPLATES):
        msg = tmpl.format(p=prod_text)
        r = run(f"ev-cap-{_ci}-{_ti}", [msg])
        check(f"capability {msg!r}",
              r["reply"].startswith("Yes")
              and r["slots"].get("product") == want
              and "What product are you looking for" not in r["reply"]
              and "What size" in r["reply"],
              f"reply={r['reply'][:110]!r} slots={r['slots']!r}")

# --- 15. location x country: the not-here answer, every phrasing ---
LOC_COUNTRIES = [
    ("pakistan", "Pakistan"), ("india", "India"), ("china", "China"),
    ("uk", "the UK"), ("canada", "Canada"), ("australia", "Australia"),
    ("germany", "Germany"), ("uae", "the UAE"),
]
LOC_TEMPLATES = [
    "where are you located in {c}?", "are you located in {c}?",
    "do you have an office in {c}?", "where it located in {c}",
    "is there a branch in {c}?", "do you have a location in {c}?",
]
for _li, (c, disp) in enumerate(LOC_COUNTRIES):
    for _ti, tmpl in enumerate(LOC_TEMPLATES):
        msg = tmpl.format(c=c)
        r = run(f"ev-loc-{_li}-{_ti}", [msg])
        check(f"location {msg!r}",
              "Rosenberg" in r["reply"]
              and f"don't have a location in {disp}" in r["reply"],
              f"reply={r['reply'][:130]!r}")

# --- 16. human / robot questions + product typos as orders ---
for msg in ["are you human", "are you a robot", "are you a real person",
            "am i talking to a bot?", "are you ai"]:
    r = run(f"ev-human-{msg[:8]}", [msg])
    check(f"human {msg!r}", "automated assistant" in r["reply"],
          f"reply={r['reply'][:120]!r}")
for msg, want in [("I need milar bags", "mylar bag"),
                  ("I need mylarr bags", "mylar bag"),
                  ("I need labls", "label"),
                  ("I need lables", "label"),
                  ("I need puches", "pouch"),
                  ("I need business cards", "business card")]:
    r = run(f"ev-typo-{msg}", [msg])
    check(f"typo order {msg!r}",
          r["slots"].get("product") == want and "What size" in r["reply"],
          f"slots={r['slots']!r} reply={r['reply'][:100]!r}")

# --- 17. trust, hostility, small talk: never a fact dump ---
for msg, want in [
    ("you guys are fake and scam right?", "real company"),
    ("are you fake?", "real company"),
    ("is this a scam?", "real company"),
    ("are you legit?", "real company"),
    ("is this company real?", "real company"),
    ("tum fake ho", "real company"),
    ("ye scam hai", "real company"),
    ("you are liars", "wrong answer"),
    ("you are lying", "wrong answer"),
    ("you scammed me", "order number"),
    ("you cheated me", "order number"),
    ("thanks", "welcome"),
    ("thank you", "welcome"),
    ("bye", "Goodbye"),
    ("how are you?", "doing well"),
]:
    r = run(f"ev-trust-{msg[:12]}", [msg])
    check(f"conversational {msg!r}",
          want.lower() in r["reply"].lower()
          and "Minimum order quantity" not in r["reply"],
          f"reply={r['reply'][:140]!r}")

# --- 18. colleague-research battery (Oct 29, 2026): the old bot's
# dominant failure classes, from the colleague's 2,046-chat rule
# flags + 300-chat judge run. Most were already handled; the ones
# that were not got code fixes in this same round (file-share
# branch, WFH carve-out, soft-dismissal branch, bare-number
# clarification, capability option guard, product-scoped
# re-ranking, contact "free" fix). Each case below locks the
# behavior, so the old bot's exact failure shapes can never
# silently come back.
for msgs, want in [
    (["I need mylar bags", "what is a SKU?"], "one SKU means one design"),
    (["I need boxes", "can I visit your facility?"], "Rosenberg"),
    (["I need mylar bags", "do you deliver to Canada?"], "team will confirm"),
    (["I need boxes", "how long does production take?"], "12 to 15 business days"),
]:
    r = run(f"ev-col-ans-{msgs[-1][:10]}", msgs)
    check(f"answer-first {msgs[-1]!r}", want.lower() in r["reply"].lower(),
          f"reply={r['reply'][:140]!r}")
r = run("ev-col-coffee", ["I need mylar bags", "what material is best for coffee?"])
check("answer-first coffee material is mylar, not box",
      "Box materials" not in r["reply"]
      and ("film" in r["reply"].lower() or "foil" in r["reply"].lower()
           or "kraft" in r["reply"].lower()),
      f"reply={r['reply'][:140]!r}")

# Unusable answers: a non-answer must never be stored as the field.
r = run("ev-col-vague", ["I need mylar bags", "any size"])
check("unusable vague size re-asked, not stored",
      not r["slots"].get("sizes") and "size" in r["reply"].lower(),
      f"slots={r['slots']} reply={r['reply'][:100]!r}")
r = run("ev-col-phoneqty", ["I need mylar bags", "4x6", "stand-up", "matte",
                            "call me at 5551234567"])
check("unusable phone-as-quantity not stored",
      not r["slots"].get("quantity") and "phone" in r["reply"].lower(),
      f"slots={r['slots']} reply={r['reply'][:100]!r}")
r = run("ev-col-fin", ["I need mylar bags", "4x6", "stand-up", "Bag's"])
check("unusable non-answer as finish re-asked, not stored",
      not r["slots"].get("finishes") and "finish" in r["reply"].lower(),
      f"slots={r['slots']} reply={r['reply'][:100]!r}")
r = run("ev-col-bare10", ["I need mylar bags", "10"])
check("unusable bare number as size answer clarified, not quantity",
      not r["slots"].get("quantity") and "inches or mm" in r["reply"],
      f"slots={r['slots']} reply={r['reply'][:100]!r}")
r = run("ev-col-emailmat", ["I need mylar bags", "4x6", "stand-up", "matte", "100",
                            "2 designs", "zipper", "kraft", "yes", "yes", "Ali", "kraft"])
check("unusable material word as email answer re-asks email",
      "email" in r["reply"].lower() and "kraft@" not in r["reply"]
      and "Just to confirm" not in r["reply"],
      f"reply={r['reply'][:140]!r}")

# Label materials: PET is a bag film, never a label stock.
r = run("ev-col-labelmat", ["I need labels", "what materials do you use for labels?"])
check("label materials from the labels file, no PET",
      ("paper" in r["reply"].lower() or "vinyl" in r["reply"].lower()
       or "film" in r["reply"].lower()) and "PET" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-labelpet", ["I need labels", "can I get PET labels?"])
check("PET labels get a Yes (reference, not whitelist)",
      r["reply"].startswith("Yes") and "can't confirm" not in r["reply"],
      f"reply={r['reply'][:140]!r}")

# REFERENCE, NOT WHITELIST (Oct 29): the old capability guard
# ("can't confirm" for options the files do not name) is deleted.
# A packaging company makes the product family, so PET, a handle
# and a spout pouch all get a Yes now.
r = run("ev-col-handle", ["do you make mylar bags with a handle?"])
check("handle on a mylar bag gets a Yes",
      r["reply"].startswith("Yes") and "can't confirm" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-spout", ["do you make spout pouches?"])
check("spout pouch gets a Yes (gallery item, company makes it)",
      r["reply"].startswith("Yes") and "can't confirm" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-petbag", ["do you make PET mylar bags?"])
check("PET mylar bags get a Yes (PET is a standard pouch film)",
      r["reply"].startswith("Yes") and "can't confirm" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-kraftbag", ["do you make kraft bags?"])
check("kraft bags still a Yes (kraft is listed)",
      r["reply"].startswith("Yes"), f"reply={r['reply'][:140]!r}")
r = run("ev-col-window", ["do you make boxes with a window?"])
check("window boxes still a Yes (window is a listed box style)",
      r["reply"].startswith("Yes"), f"reply={r['reply'][:140]!r}")

# Out of scope: job / work-from-home / order tracking.
r = run("ev-col-wfh", ["I want to work from home packing boxes"])
check("work-from-home packing boxes is a job enquiry, not an order",
      r.get("handoff") == "not_a_customer" and "job" in r["reply"].lower(),
      f"handoff={r.get('handoff')} reply={r['reply'][:100]!r}")
r = run("ev-col-wfh2", ["do you have work from home jobs?"])
check("work-from-home jobs deflected",
      r.get("handoff") == "not_a_customer", f"reply={r['reply'][:100]!r}")
r = run("ev-col-track", ["where is my order?"])
check("order tracking hands off to existing-customer",
      r.get("handoff") == "existing_customer", f"reply={r['reply'][:100]!r}")
r = run("ev-col-job", ["are you hiring?"])
check("job enquiry deflected",
      r.get("handoff") == "not_a_customer", f"reply={r['reply'][:100]!r}")

# File shared: acknowledged + script continues, never silence.
r = run("ev-col-share", ["I need mylar bags", "here is my artwork"])
check("shared artwork acknowledged, size re-asked",
      "noted your file" in r["reply"] and "size" in r["reply"].lower(),
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-share2", ["I just sent you my logo"])
check("shared logo acknowledged, product asked",
      "noted your file" in r["reply"] and "product" in r["reply"].lower(),
      f"reply={r['reply'][:140]!r}")

# Soft dismissal: "thanks though" closes, plain "thanks" carries on.
r = run("ev-col-softbye", ["I need mylar bags", "thanks though"])
check("soft dismissal closes, no script question pushed",
      "Goodbye" in r["reply"] and "?" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-thanks", ["I need mylar bags", "thanks"])
check("plain thanks still carries on",
      "welcome" in r["reply"].lower() and "size" in r["reply"].lower(),
      f"reply={r['reply'][:140]!r}")

# One question per message, no re-introduction, no markdown leak.
_replies = []
for _m in ["hi", "I need mylar bags", "4x6", "stand-up", "matte", "100"]:
    _replies.append(handle_message(_m, session_id="ev-col-locks", store=None)["reply"])
check("one question per message across a script",
      all(_r.count("?") <= 1 for _r in _replies),
      f"replies={[(_r.count('?'), _r[:60]) for _r in _replies]}")
check("no re-introduction with a rep name mid-chat",
      not any(re.search(r"Hi,? I'?m [A-Z][a-z]+", _r) for _r in _replies),
      f"replies={_replies}")
check("no markdown leaks into chat replies",
      all("**" not in _r and not _r.lstrip().startswith("#") for _r in _replies),
      f"replies={_replies}")

# --- 19. live-transcript battery (Oct 29, 2026): four bugs from a
# real visitor session, verbatim where they matter ---
r = run("ev-live-shipfree", ["Is shipping free?"])
check("live shipping-free is just the free sentence, no country caveat",
      "free nationwide" in r["reply"].lower()
      and "your country" not in r["reply"]
      and "outside the USA" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-live-shipbrazil", ["do you deliver to Brazil?"])
check("live unlisted-country delivery gets the outside-USA caveat",
      "outside the USA" in r["reply"] and "team will confirm" in r["reply"]
      and "free nationwide" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-live-shipcanada", ["do you deliver to Canada?"])
check("live Canada delivery gets caveat + team-confirm",
      "team will confirm" in r["reply"] and "Canada" in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-live-lw", ["I need mylar bags", "10 inches length and 6 inches width"])
check("live length/width phrasing stores size, not quantity",
      r["slots"].get("sizes") == "10 length x 6 width inches" and not r["slots"].get("quantity")
      and "style" in r["reply"].lower(),
      f"reply={r['reply'][:100]!r} slots={r['slots']}")
r = run("ev-live-lw-rev", ["I need mylar bags", "6 inches width and 10 inches length"])
check("live width-first phrasing stores stated order",
      r["slots"].get("sizes") == "6 width x 10 length inches" and not r["slots"].get("quantity"),
      f"slots={r['slots']}")
r = run("ev-live-lw-long", ["I need mylar bags", "10 inches long and 6 inches wide"])
check("live long/wide phrasing stores size",
      r["slots"].get("sizes") == "10 length x 6 width inches" and not r["slots"].get("quantity"),
      f"slots={r['slots']}")
r = run("ev-live-by", ["I need mylar bags", "10 by 6 inches"])
check("live by-phrasing still stores size, not quantity",
      r["slots"].get("sizes") and not r["slots"].get("quantity")
      and "style" in r["reply"].lower(),
      f"slots={r['slots']}")
r = run("ev-live-dim", ["I need mylar bags", "10 inches"])
check("live single dimension asks for the other dimension, not quantity",
      "other dimension" in r["reply"] and not r["slots"].get("quantity"),
      f"reply={r['reply'][:100]!r}")
r = run("ev-live-sug1", ["suggest me a bag for my poduct which is peices of dry meat"])
check("live jerky-bag suggestion recommends, then asks size",
      "food-grade" in r["reply"] and "resealable" in r["reply"]
      and "size" in r["reply"].lower() and r["slots"].get("product") == "mylar bag",
      f"reply={r['reply'][:140]!r}")
r = run("ev-live-sug3", ["suggest me a bag for my poduct which is peices of dry meat",
                         "10 by 6 inches",
                         "i said you to suggest me which type of boxes is best for me??"])
check("live boxes suggestion uses session context, switches product",
      "food boxes" in r["reply"] and r["slots"].get("product") == "box",
      f"reply={r['reply'][:140]!r} slots={r['slots']}")
r = run("ev-live-sug4", ["you have to suggest beef jerky boxes you are not trained well"])
check("live direct jerky-boxes suggestion",
      "food boxes" in r["reply"] and r["slots"].get("product") == "box",
      f"reply={r['reply'][:140]!r}")
r = run("ev-live-sug-coffee", ["suggest me a bag for coffee"])
check("live coffee-bag suggestion",
      "coffee pouches" in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-live-sug-nous", ["suggest me a bag"])
check("live suggestion without a use invents nothing",
      "food-grade" not in r["reply"] and "size" in r["reply"].lower(),
      f"reply={r['reply'][:140]!r}")

# --- 20. suggestion food fallback (Oct 29, 2026): "dry fuits"
# got no suggestion at all because the use map had no food entry
# and the typo beat exact matching ---
r = run("ev-sug-dryfuits", ["suggest me a bag for my poduct which is peices of dry fuits"])
check("suggestion dry-fruits typo suggests food-grade pouches, then size",
      "food-grade" in r["reply"] and "resealable" in r["reply"]
      and "size" in r["reply"].lower() and r["slots"].get("product") == "mylar bag",
      f"reply={r['reply'][:140]!r}")
r = run("ev-sug-nuts", ["suggest me a bag for nuts"])
check("suggestion nuts suggests food-grade pouches",
      "food-grade" in r["reply"] and "size" in r["reply"].lower(),
      f"reply={r['reply'][:140]!r}")
r = run("ev-sug-frutis", ["suggest me a bag for dry frutis"])
check("suggestion transposed frutis still suggests",
      "food-grade" in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-sug-foodbox", ["suggest me a box for dry fruits"])
check("suggestion dry-fruit boxes suggests food boxes",
      "food boxes" in r["reply"] and r["slots"].get("product") == "box",
      f"reply={r['reply'][:140]!r}")
r = run("ev-sug-plastic", ["suggest me a bag for pieces of plastic"])
check("suggestion non-food pieces invents no food claim",
      "food-grade" not in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-sug-coffee2", ["suggest me a bag for my coffee"])
check("suggestion coffee stays specific, not generic food",
      "coffee pouches" in r["reply"],
      f"reply={r['reply'][:140]!r}")

# --- 21. large-box flow (Oct 29, 2026, live transcript): a vague
# "i need large box" must ask purpose FIRST, then size; a bare
# "3x4" must ask inches/cm/mm (never stored unitless, never
# quantity); style chips and style answers must be BOX types,
# never pouch types; a complaint about wrong suggestions must be
# acknowledged, not fact-dumped. ---
r = run("ev-box-purpose", ["i need large box"])
check("vague large box asks purpose first, not size/style",
      "for?" in r["reply"] and "sizes" in r["missing"],
      f"reply={r['reply'][:140]!r} missing={r['missing']}")
r = run("ev-box-purpose-ans", ["i need large box", "shipping"])
check("purpose answer acknowledged, then size asked, no policy dump",
      r["reply"].startswith("Got it") and "What size do you need?" in r["reply"]
      and "free nationwide" not in r["reply"],
      f"reply={r['reply'][:160]!r}")
r = run("ev-box-unit", ["i need large box", "shipping", "3x4"])
check("bare 3x4 asks inches/cm/mm/feet, stored pending, never quantity",
      "inches, cm, mm, or feet" in r["reply"] and r["slots"].get("sizes") == "3x4"
      and not r["slots"].get("quantity"),
      f"reply={r['reply'][:140]!r} slots={r['slots']}")
r = run("ev-box-unit-ans", ["i need large box", "shipping", "3x4", "mm"])
check("unit answer completes size, type asked with BOX chips",
      r["slots"].get("sizes") == "3x4 mm"
      and "Which type would you like?" in r["reply"]
      and r["suggestions"] == ["Corrugated", "Rigid", "Mailer", "Folding carton"],
      f"reply={r['reply'][:140]!r} chips={r['suggestions']} slots={r['slots']}")
r = run("ev-box-complaint", ["i need large box", "shipping", "3x4", "mm",
                             "bro i want boxes you gave me mylar bag suggestions"])
check("complaint acknowledged, type re-asked with box chips, no dump",
      "sorry about that" in r["reply"]
      and "Which type would you like?" in r["reply"]
      and "stand-up" not in r["reply"]
      and r["suggestions"] == ["Corrugated", "Rigid", "Mailer", "Folding carton"],
      f"reply={r['reply'][:160]!r} chips={r['suggestions']}")
r = run("ev-box-pouch-chips", ["i need mylar bags", "4x6 inches"])
check("pouch style chips unchanged (Flat/Stand-up/Flat-bottom)",
      r["suggestions"] == ["Flat", "Stand-up", "Flat-bottom"],
      f"chips={r['suggestions']}")
r = run("ev-box-styles-q", ["i need boxes", "10x12 inches", "what styles do you have?"])
check("styles question with product=box answered from box facts only",
      "stand-up" not in r["reply"].lower() and "flat-bottom" not in r["reply"].lower(),
      f"reply={r['reply'][:200]!r}")
r = run("ev-box-cap-vague", ["do you make large boxes?"])
check("capability question with vague size answered Yes, not purpose-trapped",
      r["reply"].startswith("Yes"),
      f"reply={r['reply'][:140]!r}")
r = run("ev-box-purpose-stated", ["i need large box for shipping"])
check("purpose already stated -> size asked, no purpose question",
      "What size do you need?" in r["reply"] and "for?" not in r["reply"],
      f"reply={r['reply'][:160]!r}")
r = run("ev-box-suggest-ok", ["suggest me a bag for screws"])
check("real suggestion requests still work after complaint guard",
      "size" in r["reply"].lower(),
      f"reply={r['reply'][:140]!r}")

# --- 22. contact + own-data system (Oct 29, 2026, live transcript):
# the systemic rule, not one patch: validate EVERY field answer
# before advancing; never claim what is not stored; own-data
# questions always come from the session, never from the KB.
# The transcript: "i can provide my name" was stored AS the name,
# a clear phone refusal was re-asked, the close lied "no email"
# while an email was stored, "i gave you email" got a false
# "Noted — added", "what you added" dumped the catalog,
# "what is my email?" returned the COMPANY's address, and
# "my email which i gave you?" returned a boxes FAQ. ---
def _steps(sid, msgs):
    out = []
    for m in msgs:
        out.append(handle_message(m, session_id=sid, store=None))
    return out


_QUOTE = ["I need mylar bags", "Size 4x6 inches", "Stand-up", "No preference",
          "1000 units", "3 designs", "Per design", "yes add a tear notch", "Kraft",
          "Yes, that's correct"]
_s = _steps("ev-own-full", _QUOTE + [
    "i can provide my name", "Abdullah", "abdu@gmail.com",
    "i cant share my personal phone number",
    "i gave you email", "what you added/", "what is my email?",
    "my email which i gave you?"])
check("willingness sentence is not stored as a name, name re-asked",
      "Could I take your name?" in _s[10]["reply"]
      and (_s[10].get("contact") or {}).get("name") != "i can provide my name",
      f"reply={_s[10]['reply'][:120]!r} contact={_s[10].get('contact')}")
check("real name stored, email asked next",
      (_s[11].get("contact") or {}).get("name") == "Abdullah"
      and "email" in _s[11]["reply"].lower(),
      f"reply={_s[11]['reply'][:120]!r} contact={_s[11].get('contact')}")
check("first clear phone refusal closes at once, email named, no lie",
      _s[13].get("handoff") == "complete_no_contact"
      and "abdu@gmail.com" in _s[13]["reply"]
      and "don't have an email" not in _s[13]["reply"],
      f"reply={_s[13]['reply'][:160]!r}")
check("'i gave you email' with no value gets honest list, never false added",
      "Noted — I've added" not in _s[14]["reply"]
      and "abdu@gmail.com" in _s[14]["reply"],
      f"reply={_s[14]['reply'][:160]!r}")
check("'what you added' lists stored data, never the catalog",
      "Print247 offers" not in _s[15]["reply"]
      and "abdu@gmail.com" in _s[15]["reply"],
      f"reply={_s[15]['reply'][:160]!r}")
check("'what is my email?' returns the visitor's email, not the company's",
      "abdu@gmail.com" in _s[16]["reply"]
      and "Support@print247.us" not in _s[16]["reply"],
      f"reply={_s[16]['reply'][:160]!r}")
check("'my email which i gave you?' returns the visitor's email, not a FAQ",
      "abdu@gmail.com" in _s[17]["reply"]
      and "Boxes campaign FAQs" not in _s[17]["reply"],
      f"reply={_s[17]['reply'][:200]!r}")
r = run("ev-own-nameis", _QUOTE + ["My name is Abdullah"])
check("'My name is Abdullah' stores Abdullah, not the sentence",
      (r.get("contact") or {}).get("name") == "Abdullah",
      f"contact={r.get('contact')}")
r = run("ev-own-refuse2", _QUOTE + ["Abdullah", "abdu@gmail.com",
                                    "i cannot share my phone number"])
check("'cannot share' first refusal closes at once with the email named",
      r.get("handoff") == "complete_no_contact"
      and "abdu@gmail.com" in r["reply"]
      and "don't have an email" not in r["reply"],
      f"reply={r['reply'][:160]!r}")
r = run("ev-own-nocontact", _QUOTE + ["no", "no", "no"])
check("all three fields refused -> honest no-contact close",
      r.get("handoff") == "complete_no_contact"
      and "here in this chat" in r["reply"],
      f"reply={r['reply'][:160]!r}")
r = run("ev-own-newemail", _QUOTE + ["Abdullah", "abdu@gmail.com",
                                     "i cant share my phone number",
                                     "my new email is bob@x.com"])
check("finished chat + a real email in the message stores it and says so",
      "Noted — I've added email bob@x.com" in r["reply"]
      and (r.get("contact") or {}).get("email") == "bob@x.com",
      f"reply={r['reply'][:160]!r} contact={r.get('contact')}")
r = run("ev-own-midquote", ["I need mylar bags", "4x6 inches", "what is my order?"])
check("mid-quote 'what is my order?' answered from slots + script continues",
      "mylar bag" in r["reply"] and "4x6" in r["reply"]
      and "What style" in r["reply"],
      f"reply={r['reply'][:200]!r}")

# --- 23. box-quote disaster round (Oct 30, 2026, live transcript):
# every box style chip looped (none parsed), the quantity question
# stated the MOQ unasked (senior: MOQ only when asked), "plain
# rigid box" looped the material question, a mind-changed
# cancellation re-asked the confirmation, and the 12-message cap
# then bricked the chat so every later question got a handoff. ---
_s = _steps("ev-boxfix-full", [
    "i need large box", "Shipping", "40x90", "Inches", "Folding carton",
    "Mailer", "No preference", "1000 units", "none", "plain rigid box",
    "Kraft", "no i dont need now my mind chnaged", "i dont neeed",
    "What is your refund policy?"])
check("box type chip parses first try, style asked next",
      _s[4]["slots"].get("type") == "folding carton"
      and "What style of box do you need?" in _s[4]["reply"],
      f"reply={_s[4]['reply'][:140]!r} slots={_s[4]['slots']}")
check("box style chip parses first try, finish asked next",
      _s[5]["slots"].get("style") == "mailer"
      and "What finish" in _s[5]["reply"],
      f"reply={_s[5]['reply'][:140]!r} slots={_s[5]['slots']}")
check("quantity question states no MOQ until asked",
      "What quantity are you looking to order for your first run?" in _s[6]["reply"]
      and "MOQ" not in _s[6]["reply"] and "1000" not in _s[6]["reply"],
      f"reply={_s[6]['reply'][:160]!r}")
check("'plain rigid box' stores rigid material, confirmation follows",
      _s[9]["slots"].get("material") == "rigid"
      and "Just to confirm" in _s[9]["reply"],
      f"reply={_s[9]['reply'][:160]!r} slots={_s[9]['slots']}")
check("material correction at confirmation re-confirms with the new value",
      _s[10]["slots"].get("material") == "kraft"
      and "kraft material" in _s[10]["reply"],
      f"reply={_s[10]['reply'][:160]!r}")
check("mind-changed cancels gracefully, draft cleared, no handoff",
      "No problem at all" in _s[11]["reply"]
      and _s[11]["slots"] == {} and _s[11].get("handoff") is None,
      f"reply={_s[11]['reply'][:140]!r}")
check("repeated refusal after cancel stays graceful, never a handoff",
      "No problem at all" in _s[12]["reply"]
      and _s[12].get("handoff") is None,
      f"reply={_s[12]['reply'][:140]!r}")
check("refund policy answered after cancel, never the handoff loop",
      "5 business days" in _s[13]["reply"]
      and _s[13].get("handoff") is None,
      f"reply={_s[13]['reply'][:160]!r}")
for _chip, _want in [("Mailer", "mailer"), ("Tuck-end", "tuck-end"),
                     ("Rigid", "rigid"), ("Folding carton", "folding carton")]:
    # Type is asked before style now: the chip is answered after a
    # type pick, so it lands in style, not type.
    r = run(f"ev-boxchip-{_want}",
            ["i need boxes", "10x12 inches", "Corrugated", _chip])
    check(f"box chip {_chip!r} parses as style {_want}",
          r["slots"].get("style") == _want and "What finish" in r["reply"],
          f"reply={r['reply'][:120]!r} slots={r['slots']}")
r = run("ev-boxfix-moqasked", ["What is the minimum order?"])
check("MOQ still answered when the visitor asks",
      "1000" in r["reply"],
      f"reply={r['reply'][:160]!r}")
r = run("ev-boxfix-belowmin", ["I need boxes", "10x12 inches", "mailer",
                               "matte", "300 units"])
check("sub-1000 quantity still accepted with the once-only note",
      "We can look at 300" in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-boxfix-fieldrefusal", ["I need mylar bags", "4x6 inches", "stand-up",
                                   "matte", "1000 units", "1 design",
                                   "i dont need a zipper"])
check("field refusal ('dont need a zipper') is not a cancellation",
      "No problem at all" not in r["reply"] and r.get("handoff") is None,
      f"reply={r['reply'][:160]!r}")
_s = _steps("ev-boxfix-cap", [
    "Is shipping free?", "What is the turnaround time?", "Where are you located?",
    "What are your support hours?", "What payment methods do you accept?",
    "Do you offer samples?", "What is the minimum order?", "What sizes do you offer?",
    "What finishes do you offer?", "What materials do you offer?",
    "Do you offer free design support?", "What is your proof approval process?",
    "What is your refund policy?"])
check("12-message cap REMOVED (Oct 30 directive): no handoff at any turn",
      all(_t.get("handoff") is None for _t in _s)
      and "5 business days" in _s[12]["reply"],
      f"handoffs={[t.get('handoff') for t in _s]} last={_s[12]['reply'][:120]!r}")

# ---------- section 24: Oct 30 transcript round (no cap, no merges) ----------
_s = _steps("ev-s24-switch", ["I need custom labels for my honey jars", "Size 4x6 inches",
                               "Soft touch", "I need a vinyl banner 4x8 feet for my shop"])
check("new order mid-quote asks before switching, old quote untouched",
      "switch to banner" in _s[3]["reply"] and "keep the label quote" in _s[3]["reply"]
      and _s[3]["slots"].get("product") == "label"
      and _s[3]["suggestions"] == ["Switch to banner", "Keep label"],
      f"reply={_s[3]['reply'][:160]!r} chips={_s[3]['suggestions']}")
r = run("ev-s24-switch-yes", ["I need custom labels for my honey jars", "Size 4x6 inches",
                               "Soft touch", "I need a vinyl banner 4x8 feet for my shop",
                               "Switch to banner"])
check("switch confirmed: held banner slots become the new quote, no merge",
      r["slots"].get("product") == "banner" and r["slots"].get("sizes") == "4x8 feet"
      and r["slots"].get("material") == "vinyl" and "switching to banner" in r["reply"]
      and "What finish" in r["reply"],
      f"reply={r['reply'][:160]!r} slots={r['slots']}")
r = run("ev-s24-switch-no", ["I need custom labels for my honey jars", "Size 4x6 inches",
                              "Soft touch", "I need a vinyl banner 4x8 feet for my shop",
                              "Keep labels"])
check("switch declined: old label quote resumes at its pending field",
      r["slots"].get("product") == "label" and "keeping the label quote" in r["reply"]
      and "What quantity" in r["reply"],
      f"reply={r['reply'][:160]!r} slots={r['slots']}")
r = run("ev-s24-switch-implicit", ["I need custom labels for my honey jars",
                                    "Size 4x6 inches",
                                    "I need a vinyl banner 4x8 feet for my shop", "Matte"])
check("answer to the old pending field is an implicit keep",
      r["slots"].get("product") == "label" and r["slots"].get("finishes") == "matte"
      and "What quantity" in r["reply"],
      f"reply={r['reply'][:160]!r} slots={r['slots']}")
r = run("ev-s24-corr-sticker", ["I need custom labels for my honey jars",
                                 "Size 4x6 inches", "Soft touch", "300", "1 design",
                                 "the labels should be stickers"])
check("correction phrase updates the product (stickers, not the first word labels)",
      r["slots"].get("product") == "sticker" and "switching to sticker" in r["reply"]
      and "material" in r["reply"],
      f"reply={r['reply'][:160]!r} slots={r['slots']}")
r = run("ev-s24-corr-banner", ["I need custom labels for my honey jars",
                                "Size 4x6 inches", "Soft touch", "300", "1 design", "Kraft",
                                "make it a banner"])
check("correction at confirmation re-confirms with the new product",
      r["slots"].get("product") == "banner" and "Just to confirm" in r["reply"]
      and "banner, size 4x6 inches" in r["reply"],
      f"reply={r['reply'][:180]!r} slots={r['slots']}")
r = run("ev-s24-bareskus", ["I need standup pouchs for coffe", "Size 4x6 inches", "Matte",
                             "30", "22"])
check("bare number at the designs question is designs, not quantity",
      r["slots"].get("skus") == "22" and r["slots"].get("quantity") == "30"
      and "30 in total, or 30 of each" in r["reply"],
      f"reply={r['reply'][:180]!r} slots={r['slots']}")
r = run("ev-s24-pricediff", ["I need a vinyl banner", "4x8 feet", "matte", "1000 units",
                              "1 design", "vinyl", "How much do 500 mailer boxes cost?"])
check("price question about another product does not drag the confirmation back",
      "can't price it here" in r["reply"] and "Just to confirm" not in r["reply"],
      f"reply={r['reply'][:180]!r}")
_s = _steps("ev-s24-suggest", ["suggest me a box for coffee", "Suggest me a box for candles"])
check("unmapped use (candles) never reuses a stale use (coffee) from history",
      "coffee" not in _s[1]["reply"].lower(),
      f"reply={_s[1]['reply'][:180]!r}")
r = run("ev-s24-feet", ["I need a vinyl banner 4x8 feet for my shop"])
check("feet stated with the size is stored, no unit question",
      r["slots"].get("sizes") == "4x8 feet" and "What finish" in r["reply"],
      f"reply={r['reply'][:160]!r} slots={r['slots']}")
r = run("ev-s24-feetchip", ["I need a vinyl banner", "4x8"])
check("unit question offers feet as a chip",
      "feet" in r["reply"].lower() and "Feet" in r["suggestions"],
      f"reply={r['reply'][:160]!r} chips={r['suggestions']}")
r = run("ev-s24-espurpose", ["Necesito cajas grandes para ropa"])
check("spanish vague size asks purpose in spanish with spanish chips",
      "¿Para qué" in r["reply"] and "Envío" in r["suggestions"],
      f"reply={r['reply'][:160]!r} chips={r['suggestions']}")
r = run("ev-s24-esswitch", ["I need pouches", "4x6 inches", "Necesito cajas", "sí"])
check("spanish switch answer (sí) switches to the new product",
      r["slots"].get("product") == "box",
      f"reply={r['reply'][:160]!r} slots={r['slots']}")
from app.chat.llm_extract import llm_extract as _llm_extract
check("llm_extract accepts the new context kwargs (no key in VM -> {})",
      _llm_extract("22", asked="How many designs?", product="pouch") == {},
      "llm_extract with context kwargs did not return {}")

# ---------- section 25: Oct 30 types-question round ----------
r = run("ev-s25-boxtypes", ["what box types do you offer?"])
check("box types question answers with the type list, not a board spec",
      "corrugated boxes" in r["reply"] and "folding cartons" in r["reply"]
      and "12 to 24pt" not in r["reply"]
      and "Which type would you like?" in r["reply"]
      and r["suggestions"] == ["Corrugated", "Rigid", "Mailer", "Folding carton"]
      and r["slots"].get("product") == "box",
      f"reply={r['reply'][:200]!r} chips={r['suggestions']}")
r = run("ev-s25-boxtypes2", ["what type of boxes do you have?"])
check("box types variant never picks the pharmaceutical sentence",
      "Pharmaceutical boxes primarily" not in r["reply"]
      and "corrugated boxes" in r["reply"],
      f"reply={r['reply'][:200]!r}")
_s = _steps("ev-s25-multitype", ["what box types do you offer?",
                                  "i asked about box types like Corrugated Boxes, Rigid Boxes",
                                  "Rigid"])
check("two types named at once ask which one, store neither",
      "Which type would you like" in _s[1]["reply"]
      and "corrugated or rigid" in _s[1]["reply"]
      and _s[1]["suggestions"] == ["Corrugated", "Rigid"]
      and "style" not in _s[1]["slots"] and "material" not in _s[1]["slots"],
      f"reply={_s[1]['reply'][:160]!r} slots={_s[1]['slots']}")
check("type pick after the which-one question stores type, goes to size",
      "What size do you need?" in _s[2]["reply"]
      and _s[2]["slots"].get("type") == "rigid",
      f"reply={_s[2]['reply'][:160]!r} slots={_s[2]['slots']}")
r = run("ev-s25-pouchtypes", ["what type of mylar bags do you have?"])
check("mylar types question lists pouch types with pouch chips",
      "stand-up pouches" in r["reply"]
      and r["suggestions"] == ["Stand-up", "Flat", "Flat-bottom"],
      f"reply={r['reply'][:200]!r} chips={r['suggestions']}")
r = run("ev-s25-labeltypes", ["what type of labels do you have?"])
check("label types question lists labels, then the normal size question",
      "Labels and stickers include" in r["reply"]
      and "What size do you need?" in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-s25-crossfam", ["I need custom labels for my honey jars", "Size 4x6 inches",
                             "what type of boxes do you have?"])
check("cross-family types question keeps the quote untouched",
      "corrugated boxes" in r["reply"] and r["slots"].get("product") == "label"
      and "What finish" in r["reply"],
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s25-flatbottom", ["I need flat-bottom pouches", "4x6 inches"])
check("flat-bottom alone never counts as two types",
      "Which type would you like" not in r["reply"]
      and "What finish" in r["reply"],
      f"reply={r['reply'][:160]!r}")

# ---------- section 26: Oct 30 size-phrase guard round ----------
_s = _steps("ev-s26-reported", ["which box types do you offer?", "Corrugated",
                                 "1 feet by 2 feet"])
check("reported failure: each-unit size parses, no quantity leak, style asked",
      _s[2]["slots"].get("sizes") == "1x2 feet"
      and "quantity" not in _s[2]["slots"]
      and "What style of box" in _s[2]["reply"],
      f"reply={_s[2]['reply'][:160]!r} slots={_s[2]['slots']}")
_s = _steps("ev-s26-eachunit", ["I need custom boxes", "10 inches by 6 inches"])
check("each-unit inches normalize to NxM inches",
      _s[1]["slots"].get("sizes") == "10x6 inches",
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-mixed", ["I need custom boxes", "1 feet by 20 inches"])
check("mixed units keep the raw span, never convert inches to feet",
      _s[1]["slots"].get("sizes") == "1 feet by 20 inches",
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-3d", ["I need custom boxes", "1 feet by 2 feet by 3 feet"])
check("three each-unit measurements normalize to NxMxN feet",
      _s[1]["slots"].get("sizes") == "1x2x3 feet",
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-marks", ["I need custom boxes", "1' by 2'"])
check("inch/foot marks parse as feet",
      _s[1]["slots"].get("sizes") == "1x2 feet",
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-capacity", ["I need mylar bags", "12oz"])
check("capacity never becomes a quantity",
      "quantity" not in _s[1]["slots"],
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-a4", ["I need labels", "A4"])
check("A4 stores as the size, its 4 never becomes a quantity",
      _s[1]["slots"].get("sizes") == "A4"
      and "quantity" not in _s[1]["slots"],
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-sizeqty", ["I need custom boxes", "10 x 12 inches, 500 units"])
check("size + quantity together: size stored, quantity kept, no leak",
      "10" in (_s[1]["slots"].get("sizes") or "")
      and _s[1]["slots"].get("quantity") == "500",
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-realqty", ["I need custom boxes", "1000 units"])
check("a real quantity while size is pending is kept, not guard-dropped",
      _s[1]["slots"].get("quantity") == "1000",
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-spelled", ["I need custom boxes", "one feet by two feet"])
check("spelled-out size phrase never leaks a quantity",
      "quantity" not in _s[1]["slots"],
      f"slots={_s[1]['slots']}")
_s = _steps("ev-s26-legal", ["I need boxes for legal documents, 1000 units"])
check("'legal' is a document kind, never a size; quantity still read",
      "sizes" not in _s[0]["slots"]
      and _s[0]["slots"].get("quantity") == "1000",
      f"slots={_s[0]['slots']}")

# ---------- section 27: Oct 30 model-first round ----------
from app.chat import brain as _B
from app.chat.llm_extract import _validate as _llm_validate
check("model size '1 feet by 2 feet' validates to normalized 1x2 feet",
      _llm_validate({"sizes": "1 feet by 2 feet"}).get("sizes") == "1x2 feet",
      f"got={_llm_validate({'sizes': '1 feet by 2 feet'})}")
check("model size in unknown phrasing is kept when dimension-like",
      _llm_validate({"sizes": "roughly one feet by two feet"}).get("sizes")
      == "roughly one feet by two feet",
      f"got={_llm_validate({'sizes': 'roughly one feet by two feet'})}")
check("model size with no dimension content is still dropped",
      "sizes" not in _llm_validate({"sizes": "the big ones"}),
      f"got={_llm_validate({'sizes': 'the big ones'})}")
_orig_llm = _B.llm_extract


def _fake_llm(message, asked=None, product=None):
    _m = (message or "").strip().lower()
    if _m == "1 foot wide, 2 foot tall":
        return {"sizes": "1x2 feet"}
    if _m == "1 foot wide, 2 foot tall, 500 units":
        return {"sizes": "1x2 feet", "quantity": "500"}
    return {}


_B.llm_extract = _fake_llm
try:
    _s = _steps("ev-s27-modeldrop", ["I need custom boxes", "1 foot wide, 2 foot tall"])
    check("model filling size drops code's leaked quantity=1",
          _s[1]["slots"].get("sizes") == "1x2 feet"
          and "quantity" not in _s[1]["slots"]
          and "Which type would you like?" in _s[1]["reply"],
          f"reply={_s[1]['reply'][:120]!r} slots={_s[1]['slots']}")
    _s = _steps("ev-s27-modelqty", ["I need custom boxes",
                                    "1 foot wide, 2 foot tall, 500 units"])
    check("model's explicit quantity beats code's leaked number",
          _s[1]["slots"].get("sizes") == "1x2 feet"
          and _s[1]["slots"].get("quantity") == "500",
          f"slots={_s[1]['slots']}")
finally:
    _B.llm_extract = _orig_llm
_s = _steps("ev-s27-conflabel", ["I need mylar bags", "4x6 inches", "Stand-up",
                                  "No preference", "1000 units", "1 design",
                                  "No preference", "Kraft", "Yes, that's correct"])
check("confirmation shows bare size with width x height labels",
      "size 4x6 inches (width x height)" in _s[-2]["reply"],
      f"reply={_s[-2]['reply'][:300]!r}")
_s = _steps("ev-s27-lwlabel", ["I need mylar bags", "10 inches length and 6 inches width",
                               "Stand-up", "No preference", "1000 units", "1 design",
                               "No preference", "Kraft", "Yes, that's correct"])
check("length/width size keeps its labels in the confirmation",
      "size 10 length x 6 width inches" in _s[-2]["reply"],
      f"reply={_s[-2]['reply'][:300]!r}")

# ---------- section 28: Oct 30 category -> subcategory round ----------
_s = _steps("ev-s28-envelope", ["which materials do you use in Envelopes??"])
check("unknown-product materials question never serves another product's file",
      "team can confirm" in _s[0]["reply"]
      and "Envelopes aren't a listed product" in _s[0]["reply"]
      and "What size" not in _s[0]["reply"]
      and "kraft paperboard" not in _s[0]["reply"],
      f"reply={_s[0]['reply'][:200]!r}")
_s = _steps("ev-s28-woodencards",
            ["do you have wodden Custom NFC Business Cards??", "i need wodden ones"])
check("wooden cards: product stored, wooden named as unlisted, no box switch",
      _s[0]["slots"].get("product") == "business card"
      and "Wooden isn't in our listed business card options" in _s[0]["reply"]
      and "What size do you need?" in _s[0]["reply"]
      and _s[1]["slots"].get("product") == "business card"
      and "What style of box" not in _s[1]["reply"],
      f"r0={_s[0]['reply'][-200:]!r} r1={_s[1]['reply'][:120]!r} slots={_s[1]['slots']}")
_s = _steps("ev-s28-boxmat", ["what materials do you use in boxes?"])
check("known-product materials question stores the product, asks size not product",
      _s[0]["slots"].get("product") == "box"
      and "What size do you need?" in _s[0]["reply"],
      f"reply={_s[0]['reply'][:200]!r} slots={_s[0]['slots']}")
_orig_llm = _B.llm_extract


def _fake_llm_box(message, asked=None, product=None):
    if (message or "").strip().lower() == "i need wodden ones":
        return {"product": "box"}
    return {}


_B.llm_extract = _fake_llm_box
try:
    _s = _steps("ev-s28-llmswitch", ["do you have business cards?", "i need wodden ones"])
    check("LLM product guess never silently switches an existing quote",
          _s[1]["slots"].get("product") == "business card"
          and "What style of box" not in _s[1]["reply"],
          f"reply={_s[1]['reply'][:160]!r} slots={_s[1]['slots']}")
finally:
    _B.llm_extract = _orig_llm
for _q, _prod in (("do you have corrugated boxes?", "box"),
                  ("do you have spout pouches?", "pouch"),
                  ("do you have vinyl banners?", "banner"),
                  ("do you have kraft business cards?", "business card")):
    r = run("ev-s28-listed-" + _prod, [_q])
    check(f"listed qualifier for {_prod} gets no unlisted caveat",
          "isn't in our listed" not in r["reply"]
          and r["slots"].get("product") == _prod,
          f"reply={r['reply'][:200]!r} slots={r['slots']}")
for _q, _prod in (("do you have wooden boxes?", "box"),
                  ("do you have wooden pouches?", "pouch"),
                  ("do you have metal labels?", "label"),
                  ("do you have wooden banners?", "banner")):
    r = run("ev-s28-unlisted-" + _prod, [_q])
    check(f"unlisted qualifier for {_prod} is named, not swallowed by Yes",
          "isn't in our listed" in r["reply"]
          and r["slots"].get("product") == _prod,
          f"reply={r['reply'][-200:]!r} slots={r['slots']}")
_s = _steps("ev-s28-confirm", ["do you have wodden Custom NFC Business Cards??",
                                "4x6 inches", "No preference", "1000 units",
                                "1 design", "No preference"])
check("confirmation carries the open qualifier as team-to-confirm",
      "wooden — team to confirm" in _s[5]["reply"]
      and "size 4x6 inches (width x height)" in _s[5]["reply"],
      f"reply={_s[5]['reply'][:300]!r}")

# ---------- section 29: Oct 30 typo + finishes round ----------
r = run("ev-s29-typo-fin", ["what kind of finishes do you provide for buissness cards?"])
check("typo'd product in finishes question is fuzzy-matched, never echoed as fake product",
      "Buissness" not in r["reply"]
      and r["slots"].get("product") == "business card"
      and "Gloss UV" in r["reply"],
      f"reply={r['reply'][:300]!r} slots={r['slots']}")
r = run("ev-s29-fin", ["what kind of finishes do you provide for Business cards?"])
check("business card finishes question returns the finishes lists, not the include sentence",
      "Gloss UV" in r["reply"] and "Softouch Lamination" in r["reply"]
      and "Spot Foil" in r["reply"]
      and "What size do you need?" in r["reply"],
      f"reply={r['reply'][:300]!r}")
r = run("ev-s29-lables", ["what finishes do you provide for lables?"])
check("typo'd labels in finishes question stores label, never short-circuits",
      r["slots"].get("product") == "label"
      and "isn't a listed product" not in r["reply"],
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s29-kindfin", ["what kind of finishes do you provide for boxes?"])
check("'kind of finishes' is a finishes question, not a types question",
      "Which type would you like?" not in r["reply"],
      f"reply={r['reply'][:200]!r}")

# ---------- section 30: Oct 30 type-before-style round ----------
r = _steps("ev-s30-flow", ["hi i need boxes", "Size 4x6 inches", "Corrugated", "Mailer", "Matte", "1000 units", "1 design", "No preference"])
check("box flow asks type after size, before style",
      "Which type would you like?" in r[1]["reply"]
      and "What style of box do you need?" in r[2]["reply"]
      and r[2]["slots"].get("type") == "corrugated"
      and "material" not in r[2]["slots"]
      and r[3]["slots"].get("style") == "mailer"
      and "corrugated type, mailer style" in r[7]["reply"],
      f"turns={[t['reply'][:120] for t in r]} slots={r[7]['slots']}")
r = run("ev-s30-vol", ["I need corrugated boxes"])
check("volunteered box type stores type, not material",
      r["slots"].get("type") == "corrugated" and "material" not in r["slots"],
      f"slots={r['slots']}")
r = _steps("ev-s30-rigid", ["hi i need boxes", "4x6 inches", "Rigid"])
check("'Rigid' as a type answer stores type only, never style+material",
      r[2]["slots"].get("type") == "rigid"
      and "style" not in r[2]["slots"] and "material" not in r[2]["slots"]
      and "What style of box do you need?" in r[2]["reply"],
      f"slots={r[2]['slots']}")
r = _steps("ev-s30-two", ["hi i need boxes", "4x6 inches", "Corrugated Boxes, Rigid Boxes"])
check("two types in one message stores neither and asks which one",
      "Which type would you like" in r[2]["reply"]
      and "type" not in r[2]["slots"],
      f"reply={r[2]['reply'][:150]!r} slots={r[2]['slots']}")

# ---------- section 31: Oct 30 styles + full type vocab round ----------
for _tv, _tc in [("cosmetic boxes", "cosmetic"), ("CBD boxes", "cbd"),
                 ("pharmaceutical boxes", "pharmaceutical"),
                 ("apparel boxes", "apparel"),
                 ("food and beverage boxes", "food and beverage")]:
    r = _steps(f"ev-s31-type-{_tc}", ["i need boxes", "4x6 inches", _tv])
    check(f"type list item {_tv!r} parses, style asked next",
          r[2]["slots"].get("type") == _tc
          and "What style of box do you need?" in r[2]["reply"],
          f"reply={r[2]['reply'][:150]!r} slots={r[2]['slots']}")
r = run("ev-s31-styles", ["i need boxes", "4x6 inches", "metalized boxes",
                          "what styles do you offer"])
check("box styles question lists real styles, never campaign cards",
      "Mailer" in r["reply"] and "Tuck-end" in r["reply"]
      and "Folding carton" in r["reply"]
      and "gift boxes" not in r["reply"] and "kraft boxes" not in r["reply"]
      and "square boxes" not in r["reply"]
      and "What style of box do you need?" in r["reply"],
      f"reply={r['reply'][:250]!r}")
r = run("ev-s31-pouchstyles", ["i need mylar bags", "4x6 inches",
                               "what styles do you offer"])
check("pouch styles question lists pouch styles",
      "Stand-up" in r["reply"] and "Flat-bottom" in r["reply"],
      f"reply={r['reply'][:200]!r}")

# ---------- section 32: Oct 30 eval growth (real old-chat phrasings)
# + admin/monitoring/perf round ----------
# Real visitor questions from old-chat-candidates.md (359 scrubbed
# candidates) that exposed 7 gaps: location phrasing, hours
# sentence, time-intent routing, bare "mylar", lb/valve and
# gusset quantity leaks, first-person "can i get" orders.
r = run("ev-s32-loc1", ["where is your company based out of"])
check("location 'based out of' gives Rosenberg, never terms text",
      "Rosenberg" in r["reply"] and "subject to acceptance" not in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-s32-loc2", ["where you from?"])
check("location 'where you from' gives Rosenberg, never campaign line",
      "Rosenberg" in r["reply"] and "campaign" not in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-s32-loc3", ["where are you loctad"])
check("location typo still gives Rosenberg (regression)",
      "Rosenberg" in r["reply"], f"reply={r['reply'][:200]!r}")
for _hq in ["What are your support hours?", "are you guys open",
            "what time do you close?", "are you open today?"]:
    r = run(f"ev-s32-hours-{_hq[:12]}", [_hq])
    check(f"hours question {_hq!r} gives timings, never frontmatter",
          "Monday to Friday, 09:00" in r["reply"] and "---" not in r["reply"],
          f"reply={r['reply'][:200]!r}")
r = run("ev-s32-time1", ["how quick can i have labels shipped to me"])
check("shipping-speed question gives turnaround, never label list",
      "12 to 15 business days" in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-s32-time2", ["what is the delivery time for boxes?"])
check("delivery time for boxes gives turnaround, never SBS sentence",
      "12 to 15 business days" in r["reply"] and "SBS" not in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-s32-time3", ["how long are your labels"])
check("dimension 'how long' is not a time question",
      "12 to 15 business days" not in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-s32-mylar", ["i only need 300 mylar packs with my own design in 2 colors"])
check("bare 'mylar packs' stores mylar bag + below-min note",
      r["slots"].get("product") == "mylar bag"
      and r["slots"].get("quantity") == "300"
      and "We can look at 300" in r["reply"],
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-lb", ["1lb flat bottom coffee bags with a 1 way degasing valve"])
check("1lb + 1-way valve leak no quantity",
      r["slots"].get("product") == "bag"
      and r["slots"].get("style") == "flat-bottom"
      and r["slots"].get("quantity") is None,
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-gusset", ["6\" × 9\" + 3\" gusset stand up pouches"])
check("gusset joins size, never leaks as quantity",
      r["slots"].get("sizes") == "6x9+3 inches"
      and r["slots"].get("style") == "stand-up"
      and r["slots"].get("quantity") is None,
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-gusset2", ["5x8+3 pouch"])
check("shop format 5x8+3 parses as one size, no quantity leak",
      r["slots"].get("sizes") == "5x8+3"
      and r["slots"].get("quantity") is None,
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-get", ["can i get just 1 single customized box"])
check("'can i get' is an order: box + quantity 1 + below-min note",
      r["slots"].get("product") == "box"
      and r["slots"].get("quantity") == "1"
      and "We can look at 1" in r["reply"],
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-oz", ["i need 8 oz coffee bags 100"])
check("8 oz stripped, real quantity 100 kept (regression)",
      r["slots"].get("quantity") == "100",
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-sub", ["i need 500 custom boxes for candles"])
check("sub-1000 boxes accepted with note + size question",
      "We can look at 500" in r["reply"] and "What size" in r["reply"],
      f"reply={r['reply'][:200]!r}")
r = run("ev-s32-soap", ["soap box 4” x 3.5” x 1.5”"])
check("curly-quote each-unit size parses",
      r["slots"].get("sizes") == "4x3.5x1.5 inches",
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-choc", ["do you make chocolate boxes"])
check("chocolate boxes: Yes + box stored",
      r["reply"].startswith("Yes") and r["slots"].get("product") == "box",
      f"reply={r['reply'][:200]!r} slots={r['slots']}")
r = run("ev-s32-burger", ["burger boxes"])
check("burger boxes are boxes, never deflected",
      r["slots"].get("product") == "box" and "What size" in r["reply"],
      f"reply={r['reply'][:200]!r} slots={r['slots']}")

# ---------- section 33: Oct 30 SRAG + bottle-label routing round ----------
# Live transcript (Nancy session): "do you offer labels which stick
# to bottles like stickers?" got the generic labels list twice —
# no labels-bottle key matched "stick to bottles", and the live
# model quoted the sales script's PP-white-vinyl note into the
# reply. Fixes: use-phrased labels-bottle keys (never bare
# "bottle", so "boxes for bottles" still reaches boxes.md).
r = _steps("ev-s33-bottle", ["I need labels", "100x150mm", "Matte", "400",
                             "1 design",
                             "do you offer labels which stick to bottles like stickers?"])
check("bottle-label question mid-quote answers bottle labels, not generic list",
      "bottle label" in r[5]["reply"].lower()
      and "Do you have any specific material" in r[5]["reply"]
      and "custom labels, special stickers" not in r[5]["reply"],
      f"reply={r[5]['reply'][:250]!r}")
r = run("ev-s33-boxbottle", ["do you make boxes for bottles?"])
check("boxes-for-bottles question never reaches the bottle-labels file",
      "wine" not in r["reply"].lower(),
      f"reply={r['reply'][:250]!r}")
r = run("ev-s33-bottle2", ["do you make bottle labels?"])
check("'do you make bottle labels' answers yes for bottle labels",
      "bottle label" in r["reply"].lower(),
      f"reply={r['reply'][:250]!r}")

# ---------- section 34: Oct 30 COD / pay-on-delivery round ----------
# Live transcript: "can i pay on delivery??" got a COD
# clarification, then "yes" got a bare team-confirm. Cause:
# shipping ("delivery") shadowed payments ("pay") in the
# exact-topic order, so both turns retrieved shipping.md, which
# has no payment answer. Fixes: payments before shipping,
# "cash on delivery" / "pay on delivery" / word-boundary "cod"
# keys, and a COD sentence in payments.md (listed methods only
# — no invented policy).
r = run("ev-s34-pod", ["can i pay on delivery?"])
check("pay-on-delivery answers from payments.md, COD sentence present",
      "Cash on delivery" in r["reply"]
      and "kb/facts/payments.md" in r["sources"],
      f"reply={r['reply'][:250]!r} srcs={r['sources']}")
r = run("ev-s34-cod", ["is COD available?"])
check("bare COD word routes to payments.md, not discount-code trap",
      "Cash on delivery" in r["reply"]
      and "kb/facts/payments.md" in r["sources"],
      f"reply={r['reply'][:250]!r} srcs={r['sources']}")
r = run("ev-s34-cash", ["do you offer cash on delivery?"])
check("cash-on-delivery phrasing answers from payments.md",
      "Cash on delivery" in r["reply"]
      and "kb/facts/payments.md" in r["sources"],
      f"reply={r['reply'][:250]!r} srcs={r['sources']}")
r = run("ev-s34-code", ["do you offer discount codes?"])
check("discount codes never route to payments.md (word-boundary guard)",
      "kb/facts/payments.md" not in r["sources"],
      f"reply={r['reply'][:250]!r} srcs={r['sources']}")
r = run("ev-s34-ship", ["do you ship to Canada?"])
check("payments-before-shipping does not steal shipping questions",
      "kb/policies/shipping.md" in r["sources"],
      f"reply={r['reply'][:250]!r} srcs={r['sources']}")

# ---------- section 35: Oct 30 typo auto-fix + did-you-mean ----------
# User's call: spelling mistakes are fixed automatically, and an
# incomplete utterance gets a relevant answer plus a confirmation
# ("did you mean ...?") instead of a wrong answer or a bare
# team-confirm. Typos are corrected for matching only (vocab
# near-misses); the confirm fires only for fragments with no KB
# foothold and a real interpretation (product in context).
r = run("ev-s35-lables", ["I need lables"])
check("typo 'lables' flows as labels quote",
      r["slots"].get("product") == "label" and "What size" in r["reply"],
      f"reply={r['reply'][:250]!r} slots={r['slots']}")
r = run("ev-s35-bannars", ["do you make bannars?"])
check("typo 'bannars' answers banners",
      "Yes" in r["reply"] and "banner" in r["reply"].lower(),
      f"reply={r['reply'][:250]!r}")
r = _steps("ev-s35-frag", ["I need boxes", "for candles"])
check("fragment mid-quote asks did-you-mean, never guesses",
      "did you mean boxes for candles?" in r[1]["reply"].lower(),
      f"reply={r[1]['reply'][:250]!r}")
r = _steps("ev-s35-fragyes", ["I need boxes", "for candles", "yes"])
check("yes after did-you-mean answers the confirmed question",
      "Yes" in r[2]["reply"] and "candle" in r[2]["reply"].lower()
      and "What size" in r[2]["reply"],
      f"reply={r[2]['reply'][:250]!r}")
r = _steps("ev-s35-fragno", ["I need boxes", "for candles", "no"])
check("no after did-you-mean re-asks instead of guessing",
      "say a bit more" in r[2]["reply"].lower(),
      f"reply={r[2]['reply'][:250]!r}")
r = _steps("ev-s35-coffee", ["I need pouches", "for coffee"])
check("fragment with a KB foothold never gets a did-you-mean",
      "did you mean" not in r[1]["reply"].lower()
      and "What size" in r[1]["reply"],
      f"reply={r[1]['reply'][:250]!r}")
r = run("ev-s35-scam", ["scammed"])
check("complaint word never gets a did-you-mean",
      "did you mean" not in r["reply"].lower(),
      f"reply={r['reply'][:250]!r}")

print(f"EVAL: {PASSES[0]} passed, {len(FAILURES)} failed")
for f in FAILURES:
    print("FAIL " + f)
if FAILURES:
    sys.exit(1)
print("All synthetic eval cases passed.")
