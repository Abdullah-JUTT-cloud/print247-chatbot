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
              "free nationwide" in r["reply"] and "UPS" in r["reply"]
              and "team will confirm" in r["reply"]
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
    ("do you ship free?", "UPS"),
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
              "free nationwide" in r["reply"] and "UPS" in r["reply"]
              and "team will confirm" in r["reply"],
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

print(f"EVAL: {PASSES[0]} passed, {len(FAILURES)} failed")
for f in FAILURES:
    print("FAIL " + f)
if FAILURES:
    sys.exit(1)
print("All synthetic eval cases passed.")
