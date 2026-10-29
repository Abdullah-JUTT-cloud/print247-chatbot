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
    ["I need custom boxes", "100x150mm", "flat-bottom", "gloss", "1000 units",
     "3 designs", "in total", "no preference"],
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
check("PET labels not confirmed",
      "can't confirm" in r["reply"] and not r["reply"].startswith("Yes"),
      f"reply={r['reply'][:140]!r}")

# Capability guard: a Yes must never confirm an unlisted option.
r = run("ev-col-handle", ["do you make mylar bags with a handle?"])
check("handle on a mylar bag not confirmed",
      "can't confirm" in r["reply"] and "handle" in r["reply"],
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-spout", ["do you make spout pouches?"])
check("spout pouch gallery-only, never a bare Yes",
      "gallery" in r["reply"] and not r["reply"].startswith("Yes"),
      f"reply={r['reply'][:140]!r}")
r = run("ev-col-petbag", ["do you make PET mylar bags?"])
check("PET mylar bags not confirmed (not in our KB)",
      "can't confirm" in r["reply"] and "pet" in r["reply"].lower(),
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
      r["slots"].get("sizes") == "10x6 inches" and not r["slots"].get("quantity")
      and "style" in r["reply"].lower(),
      f"reply={r['reply'][:100]!r} slots={r['slots']}")
r = run("ev-live-lw-rev", ["I need mylar bags", "6 inches width and 10 inches length"])
check("live width-first phrasing stores stated order",
      r["slots"].get("sizes") == "6x10 inches" and not r["slots"].get("quantity"),
      f"slots={r['slots']}")
r = run("ev-live-lw-long", ["I need mylar bags", "10 inches long and 6 inches wide"])
check("live long/wide phrasing stores size",
      r["slots"].get("sizes") == "10x6 inches" and not r["slots"].get("quantity"),
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

print(f"EVAL: {PASSES[0]} passed, {len(FAILURES)} failed")
for f in FAILURES:
    print("FAIL " + f)
if FAILURES:
    sys.exit(1)
print("All synthetic eval cases passed.")
