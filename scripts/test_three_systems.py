#!/usr/bin/env python3
"""Parameterized tests for the three core systems:

- SYSTEM 1: Family-aware dimension validation (one validator, all products)
- SYSTEM 2: Unified "don't know" handler for every script field
- SYSTEM 3: Post-completion intent routing (finished chat is a state, not a dead end)

All test cases use unseen variants (never the example transcript values).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("OPENAI_API_KEY", None)

from app.chat.brain import handle_message
from app.chat.field_options import options_for
from app.chat.size_rules import count_dimensions, family_of, validate_size

_passed = 0
_failed = 0
_by_system = {"SYSTEM 1": [], "SYSTEM 2": [], "SYSTEM 3": []}


def check(system: str, name: str, cond: bool, detail: str = ""):
    global _passed, _failed
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] [{system}] {name}" + (f" — {detail}" if detail and not cond else ""))
    _by_system.setdefault(system, []).append((name, cond))
    if cond:
        _passed += 1
    else:
        _failed += 1


def run_turns(sid: str, turns: list[str]) -> list[dict]:
    out = []
    for t in turns:
        out.append(handle_message(t, session_id=sid, store=None))
    return out


# ============================================================================
# SYSTEM 1 — Family-aware dimension validation (parameterized, unseen variants)
# ============================================================================
print("\n=== SYSTEM 1: Family-aware dimension validation ===")

# 1A. Flat families (sticker, business card, banner): 3-dim rejected at input
# turn, before unit question, before storing, and never reaches confirmation
# as "width x height x depth".
FLAT_3D_CASES = [
    ("sticker", "I need custom stickers", "3x5x2 inches", "3x5 inches"),
    ("sticker-unitless", "I need stickers", "7*4*2", "7x4 inches"),
    ("business card", "I need business cards", "3.5x2x1 inches", "3.5x2 inches"),
    ("business card-by", "I want business cards", "90 by 50 by 10 mm", "90x50 mm"),
    ("banner", "I need vinyl banners", "4x8x2 feet", "4x8 feet"),
    ("banner-unitless", "I want pull-up banners", "33*79*12", "33x79 inches"),
]

for tag, order_msg, bad_size, good_size in FLAT_3D_CASES:
    steps = run_turns(f"sys1-flat-{tag}", [order_msg, "visitor@gmail.com", bad_size])
    r_bad = steps[-1]
    check(
        "SYSTEM 1",
        f"flat 3-dim rejected ({tag}: {bad_size!r})",
        "sizes" not in r_bad["slots"]
        and "sizes" in r_bad["missing"]
        and "flat" in r_bad["reply"].lower()
        and "width x height" in r_bad["reply"].lower()
        and "is that in inches" not in r_bad["reply"].lower()
        and "just to confirm" not in r_bad["reply"].lower(),
        f"reply={r_bad['reply']!r} slots={r_bad['slots']} missing={r_bad['missing']}",
    )
    # After giving a valid 2-dim size, it is accepted and never labeled "width x height x depth".
    r_good = handle_message(good_size, session_id=f"sys1-flat-{tag}", store=None)
    check(
        "SYSTEM 1",
        f"flat 2-dim recovery accepted ({tag}: {good_size!r})",
        bool(r_good["slots"].get("sizes"))
        and "sizes" not in r_good["missing"]
        and "width x height x depth" not in r_good["reply"].lower(),
        f"reply={r_good['reply']!r} slots={r_good['slots']}",
    )

# 1B. Box: 2-dim accepted (with depth follow-up unchanged) and 3-dim accepted.
BOX_2D_CASES = [
    ("box-2d-in", "I need custom boxes", "10x8 inches", "No need", "10x8 inches"),
    ("box-2d-add-depth", "I need mailer boxes", "12x9 inches", "4 inches", "12x9x4 inches"),
]
for tag, order_msg, sz_msg, followup_msg, expected_sz in BOX_2D_CASES:
    steps = run_turns(f"sys1-{tag}", [order_msg, "visitor@gmail.com", sz_msg])
    r_sz = steps[-1]
    check(
        "SYSTEM 1",
        f"box 2-dim accepted + depth follow-up ({tag}: {sz_msg!r})",
        r_sz["slots"].get("sizes") == sz_msg
        and "depth" in r_sz["reply"].lower(),
        f"reply={r_sz['reply']!r} slots={r_sz['slots']}",
    )
    r_after = handle_message(followup_msg, session_id=f"sys1-{tag}", store=None)
    check(
        "SYSTEM 1",
        f"box depth follow-up resolved ({tag}: {followup_msg!r} -> {expected_sz!r})",
        r_after["slots"].get("sizes") == expected_sz,
        f"reply={r_after['reply']!r} slots={r_after['slots']}",
    )

BOX_3D_CASES = [
    ("box-3d-in", "I need custom boxes", "10x8x5 inches"),
    ("box-3d-mm", "I want rigid boxes", "200x150x80 mm"),
]
for tag, order_msg, sz_msg in BOX_3D_CASES:
    steps = run_turns(f"sys1-{tag}", [order_msg, "visitor@gmail.com", sz_msg])
    r_sz = steps[-1]
    check(
        "SYSTEM 1",
        f"box 3-dim accepted directly ({tag}: {sz_msg!r})",
        r_sz["slots"].get("sizes") == sz_msg
        and "sizes" not in r_sz["missing"]
        and "need a depth" not in r_sz["reply"].lower(),
        f"reply={r_sz['reply']!r} slots={r_sz['slots']}",
    )

# 1C. Pouch/bag: width x height + optional gusset (+N format) accepted;
# 3-dim "depth" rejected.
POUCH_GUSSET_CASES = [
    ("pouch-gusset-in", "I need stand-up pouches", "6x9+3 inches", "6x9+3 inches"),
    ("mylar-gusset-mm", "I want mylar bags", "120x180+40 mm", "120x180+40 mm"),
]
for tag, order_msg, sz_msg, expected_sz in POUCH_GUSSET_CASES:
    steps = run_turns(f"sys1-{tag}", [order_msg, "visitor@gmail.com", sz_msg])
    r_sz = steps[-1]
    check(
        "SYSTEM 1",
        f"pouch size with +N gusset accepted ({tag}: {sz_msg!r})",
        r_sz["slots"].get("sizes") == expected_sz
        and "sizes" not in r_sz["missing"],
        f"reply={r_sz['reply']!r} slots={r_sz['slots']}",
    )

POUCH_3D_GUSSET_CASES = [
    ("pouch-3d-in", "I need stand-up pouches", "6x9x3 inches", "6x9+3 inches"),
    ("mylar-3d-star", "I want mylar bags", "5*8*2 inches", "5*8+2 inches"),
    ("mylar-3d-unitless", "I need mylar bags", "3x3x5", "3x3+5"),
]
for tag, order_msg, sz_msg, expected_sz in POUCH_3D_GUSSET_CASES:
    steps = run_turns(f"sys1-{tag}", [order_msg, "visitor@gmail.com", sz_msg])
    r_sz = steps[-1]
    check(
        "SYSTEM 1",
        f"pouch 3-dim converted to +N gusset format ({tag}: {sz_msg!r} -> {expected_sz!r})",
        r_sz["slots"].get("sizes") == expected_sz
        and "sizes" not in r_sz["missing"] or (sz_msg == "3x3x5" and "sizes" in r_sz["slots"]),
        f"reply={r_sz['reply']!r} slots={r_sz['slots']}",
    )

# 4-dim pouch size (more than width x height x gusset) is rejected
r_4d = run_turns("sys1-pouch-4d", ["I need stand-up pouches", "visitor@gmail.com", "6x9x3x2 inches"])[-1]
check(
    "SYSTEM 1",
    "pouch 4-dim rejected ('6x9x3x2 inches')",
    "sizes" not in r_4d["slots"]
    and "sizes" in r_4d["missing"]
    and "gusset" in r_4d["reply"].lower(),
    f"reply={r_4d['reply']!r} slots={r_4d['slots']}",
)


# 1D. Size-unit clarification: offered units are inches, cm, mm ONLY (no feet in text or chips).
# Asserted across at least two products (flat and box), plus typed 'feet' behavior.
UNIT_CLARIFICATION_CASES = [
    ("sticker-flat", "I need custom stickers", "4x6", "Got it — 4x6. Is that in inches, cm, or mm?"),
    ("box", "I need custom boxes", "10x8", "Got it — 10x8. Is that in inches, cm, or mm?"),
    ("business-card-flat", "I need business cards", "3.5x2", "Got it — 3.5x2. Is that in inches, cm, or mm?"),
]
for tag, order_msg, sz_msg, expected_q in UNIT_CLARIFICATION_CASES:
    steps = run_turns(f"sys1-unit-{tag}", [order_msg, "visitor@gmail.com", sz_msg])
    r_uq = steps[-1]
    low_reply = r_uq["reply"].lower()
    check(
        "SYSTEM 1",
        f"unit question contains inches/cm/mm and NO feet ({tag}: {sz_msg!r})",
        expected_q in r_uq["reply"]
        and "inches" in low_reply and "cm" in low_reply and "mm" in low_reply
        and "feet" not in low_reply
        and r_uq["suggestions"] == ["Inches", "Cm", "Mm"]
        and "Feet" not in r_uq["suggestions"] and "feet" not in r_uq["suggestions"],
        f"reply={r_uq['reply']!r} chips={r_uq['suggestions']}",
    )

# Typed 'feet' behavior: accepted and stored as before, does not become quantity
steps_typed_feet = run_turns("sys1-typed-feet-banner", ["I need vinyl banners", "visitor@gmail.com", "4x8 feet"])
r_tf = steps_typed_feet[-1]
check(
    "SYSTEM 1",
    "typed feet stored as size and not converted to quantity (banner: '4x8 feet')",
    r_tf["slots"].get("sizes") == "4x8 feet"
    and r_tf["slots"].get("quantity") != "4"
    and r_tf["slots"].get("quantity") != "8"
    and "is that in inches" not in r_tf["reply"].lower(),
    f"slots={r_tf['slots']} reply={r_tf['reply']!r}",
)

# Answering 'feet' to the unit clarification question is accepted and stored as '<size> feet'
r_ans_feet = handle_message("feet", session_id="sys1-unit-box", store=None)
check(
    "SYSTEM 1",
    "answering feet to unit clarification attaches feet to size (box: '10x8' -> '10x8 feet')",
    r_ans_feet["slots"].get("sizes") == "10x8 feet"
    and r_ans_feet["slots"].get("quantity") != "10"
    and r_ans_feet["slots"].get("quantity") != "8",
    f"slots={r_ans_feet['slots']} reply={r_ans_feet['reply']!r}",
)


# ============================================================================
# SYSTEM 2 — Unified "don't know" handler for every script field
# ============================================================================
print("\n=== SYSTEM 2: Unified 'don't know' handler across all script fields ===")

# Parameterized across finish, style, type, extras, quantity (plus sizes, skus, material)
DONT_KNOW_CASES = [
    ("finish",
        "finishes",
        ["I need stand-up pouches", "visitor@gmail.com", "6x9+3 inches"],
        "no idea",
        "not sure",
        ["matte", "gloss", "soft touch"],
        "What finish do you prefer",
    ),
    (
        "style",
        "style",
        ["I need mylar bags", "visitor@gmail.com", "5x7 inches"],
        "i don't know",
        "no idea",
        ["stand-up", "flat", "flat-bottom"],
        "What style",
    ),
    (
        "type",
        "type",
        ["I need custom boxes", "visitor@gmail.com", "10x8x4 inches"],
        "no idea",
        "dunno",
        ["corrugated", "cardboard", "rigid"],
        "Which type would you like",
    ),
    (
        "extras",
        "extras",
        [
            "I need stand-up pouches", "visitor@gmail.com", "6x9+3 inches",
            "Matte", "2000 units", "1 design", "No, I need design help",
        ],
        "no idea",
        "not sure",
        ["zipper", "tear notch"],
        "Do you want me to add a zipper and tear notch",
    ),
    (
        "quantity",
        "quantity",
        ["I need vinyl stickers", "visitor@gmail.com", "4x4 inches", "Gloss"],
        "no idea",
        "still not sure",
        ["short-run", "bulk", "rough range"],
        "What quantity are you looking to order",
    ),
    (
        "sizes",
        "sizes",
        ["I need business cards", "visitor@gmail.com"],
        "no idea",
        "not sure",
        ["leave the size", "width x height", "3.5", "2"],
        "What size do you need",
    ),
    (
        "skus",
        "skus",
        ["I need vinyl stickers", "visitor@gmail.com", "4x4 inches", "Matte", "1500 units"],
        "no idea",
        "not sure",
        ["artwork", "design"],
        "How many total designs",
    ),
    (
        "material",
        "material",
        [
            "I need pull-up banners", "visitor@gmail.com", "33.5x79 inches",
            "Matte", "500 units", "1 design", "No, I need design help",
        ],
        "no idea",
        "don't know",
        ["vinyl"],
        "Do you have any specific material",
    ),
]

for label, field_key, setup_turns, first_dk, second_dk, expected_hints, reask_sub in DONT_KNOW_CASES:
    sid = f"sys2-dk-{label}"
    run_turns(sid, setup_turns)
    # 1st don't-know: suggests KB options + re-asks the field, NEVER jumps to confirmation
    r1 = handle_message(first_dk, session_id=sid, store=None)
    low1 = r1["reply"].lower()
    has_kb_hint = any(h.lower() in low1 for h in expected_hints)
    has_reask = reask_sub.lower() in low1
    not_confirm = "just to confirm" not in low1
    still_missing = field_key in r1["missing"]
    check(
        "SYSTEM 2",
        f"1st don't-know on {label} suggests KB options + re-asks ({first_dk!r})",
        has_kb_hint and has_reask and not_confirm and still_missing,
        f"reply={r1['reply']!r} missing={r1['missing']}",
    )
    # 2nd refusal on the same field: marks it gave_up, states team will confirm, and moves on
    r2 = handle_message(second_dk, session_id=sid, store=None)
    low2 = r2["reply"].lower()
    moved_on = field_key not in r2["missing"]
    team_confirms = "for the team to confirm" in low2
    check(
        "SYSTEM 2",
        f"2nd refusal on {label} marks gave_up and moves on ({second_dk!r})",
        moved_on and team_confirms,
        f"reply={r2['reply']!r} missing={r2['missing']}",
    )


# ============================================================================
# SYSTEM 3 — Post-completion intent routing (parameterized across >=2 products)
# ============================================================================
print("\n=== SYSTEM 3: Post-completion intent routing ===")

COMPLETED_PRODUCT_SCRIPTS = {
    "sticker": [
        "I need custom stickers", "nora@gmail.com", "3x3 inches",
        "Matte", "2000 units", "1 design", "No, I need design help",
        "Vinyl", "Yes, that's correct", "Nora", "5559876543",
    ],
    "box": [
        "I need custom boxes", "leo@gmail.com", "8x6x4 inches",
        "Corrugated", "Mailer", "Gloss", "1500 units", "1 design",
        "No, I need design help", "Kraft", "Yes, that's correct",
        "Leo", "5552345678",
    ],
    "pouch": [
        "I need stand-up pouches", "maya@gmail.com", "5x8+2 inches",
        "Stand-up", "Soft touch", "3000 units", "1 design",
        "No, I need design help", "yes", "Kraft", "Yes, that's correct",
        "Maya", "5553456789",
    ],
}

# Verify each product script reaches completion cleanly
for prod_key, turns in COMPLETED_PRODUCT_SCRIPTS.items():
    res = run_turns(f"sys3-verify-{prod_key}", turns)[-1]
    check(
        "SYSTEM 3",
        f"setup reaches completed state for {prod_key}",
        res.get("handoff") == "complete",
        f"handoff={res.get('handoff')} reply={res['reply']!r}",
    )

# 3A. Cancellation after completion (at least 2 products, multiple phrasings):
# "I understand" + future-follow-up line (quote stays with team), NEVER saved summary.
for prod_key, cancel_msg in [
    ("sticker", "i dont need it"),
    ("box", "cancel"),
    ("pouch", "changed my mind"),
]:
    sid = f"sys3-cancel-{prod_key}"
    run_turns(sid, COMPLETED_PRODUCT_SCRIPTS[prod_key])
    rc = handle_message(cancel_msg, session_id=sid, store=None)
    lowc = rc["reply"].lower()
    check(
        "SYSTEM 3",
        f"post-completion cancel on {prod_key} ({cancel_msg!r})",
        "i understand" in lowc
        and "team" in lowc
        and "change your mind" in lowc
        and "here's what i have saved for you" not in lowc,
        f"reply={rc['reply']!r}",
    )

# 3B. Delete after completion (at least 2 products, multiple phrasings):
# Clears saved session/meta/contact and confirms once; subsequent own-data check finds nothing saved.
for prod_key, del_msg in [
    ("sticker", "delete"),
    ("box", "delete save"),
    ("pouch", "delete my data"),
]:
    sid = f"sys3-delete-{prod_key}"
    run_turns(sid, COMPLETED_PRODUCT_SCRIPTS[prod_key])
    rd = handle_message(del_msg, session_id=sid, store=None)
    lowd = rd["reply"].lower()
    check(
        "SYSTEM 3",
        f"post-completion delete confirms & clears once on {prod_key} ({del_msg!r})",
        "deleted" in lowd
        and rd["slots"] == {}
        and (rd.get("contact") or {}) == {}
        and "here's what i have saved for you" not in lowd,
        f"reply={rd['reply']!r} slots={rd['slots']} contact={rd.get('contact')}",
    )
    # Later own-data check must find nothing saved
    ro1 = handle_message("what did you save?", session_id=sid, store=None)
    ro2 = handle_message("what is my email?", session_id=sid, store=None)
    check(
        "SYSTEM 3",
        f"own-data check after delete finds nothing saved ({prod_key})",
        "don't have anything saved" in ro1["reply"].lower()
        and "don't have your email saved" in ro2["reply"].lower(),
        f"ro1={ro1['reply']!r} ro2={ro2['reply']!r}",
    )

# 3C. Bye after completion (at least 2 products)
for prod_key, bye_msg in [
    ("sticker", "bye"),
    ("box", "goodbye"),
    ("pouch", "thanks though, bye"),
]:
    sid = f"sys3-bye-{prod_key}"
    run_turns(sid, COMPLETED_PRODUCT_SCRIPTS[prod_key])
    rb = handle_message(bye_msg, session_id=sid, store=None)
    lowb = rb["reply"].lower()
    check(
        "SYSTEM 3",
        f"post-completion bye on {prod_key} ({bye_msg!r})",
        ("goodbye" in lowb or "stopping by" in lowb)
        and "here's what i have saved for you" not in lowb,
        f"reply={rb['reply']!r}",
    )

# 3D. New order after completion (at least 2 products):
# Resets old product/slots/answered_fields and starts the new product's script.
for prod_key, new_order_msg, expected_new_prod in [
    ("sticker", "I need 500 mailer boxes", "box"),
    ("box", "I want custom business cards", "business card"),
    ("pouch", "start over", None),
]:
    sid = f"sys3-neworder-{prod_key}"
    run_turns(sid, COMPLETED_PRODUCT_SCRIPTS[prod_key])
    rn = handle_message(new_order_msg, session_id=sid, store=None)
    lown = rn["reply"].lower()
    if expected_new_prod:
        check(
            "SYSTEM 3",
            f"post-completion new order on {prod_key} -> {expected_new_prod} ({new_order_msg!r})",
            rn["slots"].get("product") == expected_new_prod
            and "sizes" not in rn["slots"]
            and "sizes" in rn["missing"]
            and "size" in lown
            and "here's what i have saved for you" not in lown,
            f"reply={rn['reply']!r} slots={rn['slots']} missing={rn['missing']}",
        )
    else:
        check(
            "SYSTEM 3",
            f"post-completion start over on {prod_key} ({new_order_msg!r})",
            rn["slots"] == {}
            and "product" in rn["missing"]
            and "what product" in lown,
            f"reply={rn['reply']!r} slots={rn['slots']} missing={rn['missing']}",
        )

# 3E. Fact question after completion (at least 2 products):
# Answered from KB without dumping the saved summary.
for prod_key, fact_q, expected_sub in [
    ("sticker", "how long does shipping take?", "business days"),
    ("box", "what is your minimum order quantity?", "1000"),
    ("pouch", "where are you located?", "rosenberg"),
]:
    sid = f"sys3-fact-{prod_key}"
    run_turns(sid, COMPLETED_PRODUCT_SCRIPTS[prod_key])
    rf = handle_message(fact_q, session_id=sid, store=None)
    lowf = rf["reply"].lower()
    check(
        "SYSTEM 3",
        f"post-completion fact question on {prod_key} ({fact_q!r})",
        expected_sub in lowf
        and "here's what i have saved for you" not in lowf,
        f"reply={rf['reply']!r}",
    )

# 3F. Saved summary ONLY appears on explicit own-data question, never on unmatched messages.
for prod_key, unmatched_msg in [
    ("sticker", "hmm"),
    ("box", "just checking in"),
]:
    sid = f"sys3-unmatched-{prod_key}"
    run_turns(sid, COMPLETED_PRODUCT_SCRIPTS[prod_key])
    ru = handle_message(unmatched_msg, session_id=sid, store=None)
    lowu = ru["reply"].lower()
    check(
        "SYSTEM 3",
        f"unmatched post-completion message gets short clarification, never data dump ({prod_key}: {unmatched_msg!r})",
        "here's what i have saved for you" not in lowu
        and "already with our team" in lowu,
        f"reply={ru['reply']!r}",
    )
    # Explicit own-data question DOES return the saved summary
    ro = handle_message("what did you save?", session_id=sid, store=None)
    check(
        "SYSTEM 3",
        f"explicit own-data question returns saved summary ({prod_key})",
        "here's what i have saved for you" in ro["reply"].lower(),
        f"reply={ro['reply']!r}",
    )

print("\n=== Summary by System ===")
for sys_name, items in _by_system.items():
    p = sum(1 for _, ok in items if ok)
    print(f"  {sys_name}: {p}/{len(items)} passed")
print(f"\nTotal: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
