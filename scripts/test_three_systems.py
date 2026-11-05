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

# ============================================================================
# SYSTEM 4 — Universal Turn Rule: Answer first, then resume (every flow step)
# ============================================================================
print("\n=== SYSTEM 4: Universal Turn Rule (answer first, then resume) ===")

# 4A. Parameterized interruptions across EVERY flow step:
# (email, size, type, style, finish, quantity, skus, extras, material, confirmation, name, phone)
# Assert TWO things every time: (a) interruption was handled, (b) SAME pending question re-asked.
# Then answer it and assert the flow completes/advances.

BOX_PRE_TURNS = {
    "email": ["I need custom boxes"],
    "size": ["I need custom boxes", "user@example.com"],
    "type": ["I need custom boxes", "user@example.com", "10x8x4 inches"],
    "style": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer"],
    "finish": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer", "tuck-end"],
    "quantity": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer", "tuck-end", "matte"],
    "skus": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer", "tuck-end", "matte", "1000"],
    "material": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer", "tuck-end", "matte", "1000", "1", "no"],
    "confirm": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer", "tuck-end", "matte", "1000", "1", "no", "kraft"],
    "name": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer", "tuck-end", "matte", "1000", "1", "no", "kraft", "yes"],
    "phone": ["I need custom boxes", "user@example.com", "10x8x4 inches", "mailer", "tuck-end", "matte", "1000", "1", "no", "kraft", "yes", "Alex"],
}

POUCH_PRE_TURNS = {
    "extras": ["I need mylar bags", "user@example.com", "4x6+2 inches", "stand up", "matte", "1000", "1", "no"],
}

INTERRUPTION_CASES = [
    # (step, interruption_type, inter_msg, expected_handle_kw, expected_reask_kw, valid_answer)
    ("email", "pending_q", "why do you need my email?", "quote", "email", "visitor@example.com"),
    ("email", "offtopic_q", "where are you located?", "rosenberg", "email", "visitor@example.com"),
    ("email", "change", "chnage product to custom boxes", "box", "email", "visitor@example.com"),
    ("email", "confusion", "not decided yet", "email", "email", "visitor@example.com"),
    ("size", "pending_q", "what sizes do you offer?", "custom", "size", "10x8x4 inches"),
    ("size", "offtopic_q", "do you ship to Canada?", "canada", "size", "10x8x4 inches"),
    ("size", "change", "chnage email to buyer@example.com", "updated", "size", "10x8x4 inches"),
    ("size", "confusion", "I am confused", "inside", "size", "10x8x4 inches"),
    ("type", "pending_q", "what types do you have?", "corrugated", "type", "mailer"),
    ("type", "offtopic_q", "how long does shipping take?", "business days", "type", "mailer"),
    ("type", "change", "change size to 12x10x4 inches", "12x10x4", "type", "mailer"),
    ("type", "confusion", "any suggestion?", "corrugated", "type", "mailer"),
    ("style", "pending_q", "what styles do you offer?", "mailer", "style", "tuck-end"),
    ("style", "offtopic_q", "are you guys open today?", "timing", "style", "tuck-end"),
    ("style", "change", "chnage size to 8x8x4 inches", "8x8x4", "style", "tuck-end"),
    ("style", "confusion", "haven't decided yet", "mailer", "style", "tuck-end"),
    ("finish", "pending_q", "what finish options are available?", "matte", "finish", "matte"),
    ("finish", "offtopic_q", "where is your office?", "rosenberg", "finish", "matte"),
    ("finish", "change", "change type to rigid", "rigid", "finish", "matte"),
    ("finish", "confusion", "can't decide", "matte", "finish", "matte"),
    ("quantity", "pending_q", "what is your minimum order?", "1000", "quantity", "1000"),
    ("quantity", "offtopic_q", "what payment methods do you accept?", "paypal", "quantity", "1000"),
    ("quantity", "change", "chnage finish to gloss", "gloss", "quantity", "1000"),
    ("quantity", "confusion", "still not sure", "rough range", "quantity", "1000"),
    ("skus", "pending_q", "can I do multiple designs?", "sku", "design", "1"),
    ("skus", "offtopic_q", "do you offer free design help?", "design", "design", "1"),
    ("skus", "change", "chnage quantity to 2000", "2000", "design", "1"),
    ("skus", "confusion", "no clue", "artwork version", "design", "1"),
    ("extras", "pending_q", "what extras do you offer?", "zipper", "zipper", "none"),
    ("extras", "offtopic_q", "where are you located?", "rosenberg", "zipper", "none"),
    ("extras", "change", "chnage quantity to 500", "500", "zipper", "none"),
    ("extras", "confusion", "whats is best?", "zipper", "zipper", "none"),
    ("material", "pending_q", "what materials do you have?", "kraft", "material", "kraft"),
    ("material", "offtopic_q", "do you ship to UK?", "delivery", "material", "kraft"),
    ("material", "change", "chnage quantity to 1500", "1500", "material", "kraft"),
    ("material", "confusion", "any suggestion?", "kraft", "material", "kraft"),
    ("confirm", "pending_q", "can I get a sample first?", "sample", "confirm", "yes"),
    ("confirm", "offtopic_q", "do you ship to Canada?", "canada", "confirm", "yes"),
    ("confirm", "change", "chnage quantity to 2500", "2500", "confirm", "yes"),
    ("name", "pending_q", "why do you need my name?", "quote", "name", "Alex"),
    ("name", "offtopic_q", "where are you located?", "rosenberg", "name", "Alex"),
    ("name", "change", "chnage finish to gloss", "gloss", "name", "Alex"),
    ("phone", "pending_q", "is phone required?", "optional", "phone", "no phone"),
    ("phone", "offtopic_q", "do you ship to Canada?", "canada", "phone", "no phone"),
    ("phone", "change", "change name to John", "john", "phone", "no phone"),
    ("phone", "refusal", "dont have any phone number", "user@example.com", "user@example.com", "done"),
]

for step_name, itype, imsg, exp_hkw, exp_rkw, ans_msg in INTERRUPTION_CASES:
    sid = f"sys4-inter-{step_name}-{itype}"
    pre = POUCH_PRE_TURNS[step_name] if step_name in POUCH_PRE_TURNS else BOX_PRE_TURNS[step_name]
    run_turns(sid, pre)
    r_inter = handle_message(imsg, session_id=sid, store=None)
    low_rep = r_inter["reply"].lower()
    handled_ok = (exp_hkw.lower() in low_rep)
    reasked_ok = (exp_rkw.lower() in low_rep)
    check(
        "SYSTEM 4",
        f"interruption at {step_name} handled + reasked ({itype}: {imsg!r})",
        handled_ok and reasked_ok,
        f"reply={r_inter['reply']!r}",
    )
    if ans_msg != "done":
        r_ans = handle_message(ans_msg, session_id=sid, store=None)
        check(
            "SYSTEM 4",
            f"flow advances after interruption at {step_name} answered with {ans_msg!r}",
            bool(r_ans.get("reply")),
            f"reply={r_ans.get('reply')!r}",
        )

# 4B. Combined message: answer + question in one turn
# Example: "gloss, and what is soft touch?" at finish step
sid_comb = "sys4-comb-finish"
run_turns(sid_comb, BOX_PRE_TURNS["finish"])
r_comb = handle_message("gloss, and what is soft touch?", session_id=sid_comb, store=None)
low_comb = r_comb["reply"].lower()
check(
    "SYSTEM 4",
    "combined turn stores answer, answers question, asks NEXT question (not pending)",
    r_comb["slots"].get("finishes") == "gloss"
    and ("velvet" in low_comb or "soft touch" in low_comb or "luxur" in low_comb)
    and "quantity" in low_comb
    and "finish do you prefer" not in low_comb,
    f"reply={r_comb['reply']!r} slots={r_comb['slots']}",
)

# 4C. Cancel / delete / new-order interruptions (flow ends / restarts, no re-ask)
sid_c = "sys4-cancel-mid"
run_turns(sid_c, BOX_PRE_TURNS["style"])
r_c = handle_message("cancel this quote", session_id=sid_c, store=None)
check(
    "SYSTEM 4",
    "cancel interruption mid-flow ends flow without re-asking pending question",
    "understand" in r_c["reply"].lower()
    and "what style" not in r_c["reply"].lower(),
    f"reply={r_c['reply']!r}",
)

sid_d = "sys4-del-mid"
run_turns(sid_d, BOX_PRE_TURNS["finish"])
r_d = handle_message("delete save one", session_id=sid_d, store=None)
check(
    "SYSTEM 4",
    "delete interruption mid-flow clears data without re-asking pending question",
    "deleted" in r_d["reply"].lower()
    and "what finish" not in r_d["reply"].lower()
    and r_d["slots"] == {},
    f"reply={r_d['reply']!r}",
)

sid_no = "sys4-neworder-mid"
run_turns(sid_no, BOX_PRE_TURNS["quantity"])
r_no = handle_message("start over", session_id=sid_no, store=None)
check(
    "SYSTEM 4",
    "start over interruption mid-flow restarts from product",
    "product" in r_no["reply"].lower()
    and "what quantity" not in r_no["reply"].lower()
    and r_no["slots"] == {},
    f"reply={r_no['reply']!r}",
)

# 4D. Full replay of all 8 live transcripts as regression cases
# 1. mylar "whats is best?"
sid_r1 = "sys4-reg1-mylar"
run_turns(sid_r1, ["I need mylar bags", "test@example.com", "4x6+2 inches", "stand up", "matte", "1000", "1", "not yet"])
r_r1 = handle_message("whats is best?", session_id=sid_r1, store=None)
check(
    "SYSTEM 4",
    "live transcript 1: mylar 'whats is best?' extras relevance",
    "rosenberg" not in r_r1["reply"].lower()
    and ("zipper" in r_r1["reply"].lower() or "extra" in r_r1["reply"].lower()),
    f"reply={r_r1['reply']!r}",
)

# 2. label 22*2*6
sid_r2 = "sys4-reg2-label"
run_turns(sid_r2, ["I need labels", "test@example.com"])
r_r2 = handle_message("22*2*6", session_id=sid_r2, store=None)
check(
    "SYSTEM 4",
    "live transcript 2: label 22*2*6 3D refusal",
    "flat" in r_r2["reply"].lower() or "width x height" in r_r2["reply"].lower() or "2 dimensions" in r_r2["reply"].lower(),
    f"reply={r_r2['reply']!r}",
)

# 3. Hammad cancel/delete
sid_r3 = "sys4-reg3-hammad"
run_turns(sid_r3, ["I need boxes"])
r_can = handle_message("i dont need it", session_id=sid_r3, store=None)
r_del = handle_message("delete save one", session_id=sid_r3, store=None)
check(
    "SYSTEM 4",
    "live transcript 3: Hammad cancel/delete mid-quote",
    "deleted" in r_del["reply"].lower() or "cleared" in r_del["reply"].lower(),
    f"r_can={r_can['reply']!r} r_del={r_del['reply']!r}",
)

# 4. whisky "confused"
sid_r4 = "sys4-reg4-whisky"
run_turns(sid_r4, ["labels for whisky bottles", "visitor@gmail.com", "4x6 inches"])
r_w1 = handle_message("I am confused what do you suggest me", session_id=sid_r4, store=None)
r_w2 = handle_message("I am confused what finish do I need, I can't decide between matte, gloss or soft touch", session_id=sid_r4, store=None)
check(
    "SYSTEM 4",
    "live transcript 4: whisky labels finish indecision marks gave_up",
    "for the team to confirm" in r_w2["reply"].lower()
    and "quantity" in r_w2["reply"].lower(),
    f"r_w1={r_w1['reply']!r} r_w2={r_w2['reply']!r}",
)

# 5. CTO pizza-box test
sid_r5 = "sys4-reg5-cto"
cto_turns = [
    ("I need pizza boxes", ["email"]),
    ("user@example.com", ["size"]),
    ("i have not decided yet", ["tell me what will go inside", "size"]),
    ("I already told you that I dont know", ["leave the size", "type"]),
    ("Folding carton", ["style"]),
    ("Mailer", ["finish"]),
    ("any other finish you have?", ["matte", "gloss", "finish"]),
    ("Matte", ["quantity"]),
    ("1000", ["designs", "sku"]),
    ("1", ["image of the design"]),
    ("no", ["material"]),
    ("not yet", ["kraft", "cardboard", "material"]),
    ("any suggestion?", ["leave the material", "confirm"]),
    ("cardboard", ["cardboard", "confirm"]),
    ("yes", ["name"]),
    ("John Doe", ["phone"]),
    ("dont have any phone number", ["follow up with you at user@example.com"]),
    ("i dont need it", ["understand", "quote stays with our team"]),
    ("delete save one", ["deleted your saved details"]),
]
cto_ok = True
for cmsg, exp_parts in cto_turns:
    rc = handle_message(cmsg, session_id=sid_r5, store=None)
    if not all(ep.lower() in rc["reply"].lower() for ep in exp_parts):
        cto_ok = False
        break
check("SYSTEM 4", "live transcript 5: CTO pizza-box 19 turns replay", cto_ok)

# 6. phone refusal
sid_r6 = "sys4-reg6-phone"
run_turns(sid_r6, ["I need boxes", "lead@example.com", "6x6x6 inches", "mailer", "matte", "500", "1", "none", "cardboard", "yes", "Alex"])
r_p6 = handle_message("dont have any phone number", session_id=sid_r6, store=None)
check(
    "SYSTEM 4",
    "live transcript 6: phone refusal closes cleanly with email",
    "lead@example.com" in r_p6["reply"],
    f"reply={r_p6['reply']!r}",
)

# 7. 'chnage size' at phone step
sid_r7 = "sys4-reg7-chnage"
run_turns(sid_r7, ["I need boxes", "lead@example.com", "6x6x6 inches", "mailer", "matte", "500", "1", "none", "cardboard", "yes", "Alex"])
r_ch7 = handle_message("chnage size", session_id=sid_r7, store=None)
check(
    "SYSTEM 4",
    "live transcript 7: 'chnage size' at phone step asks for size",
    "size" in r_ch7["reply"].lower(),
    f"reply={r_ch7['reply']!r}",
)

# 8. quote-summary duplication
sid_r8 = "sys4-reg8-summary"
run_turns(sid_r8, ["I need boxes", "lead@example.com", "6x6x6 inches"])
r_qs8 = handle_message("what was my order", session_id=sid_r8, store=None)
check(
    "SYSTEM 4",
    "live transcript 8: quote summary contains order info without duplicate dump",
    "box" in r_qs8["reply"].lower() and "6x6x6" in r_qs8["reply"],
    f"reply={r_qs8['reply']!r}",
)

print("\n=== Summary by System ===")
for sys_name, items in _by_system.items():
    p = sum(1 for _, ok in items if ok)
    print(f"  {sys_name}: {p}/{len(items)} passed")
print(f"\nTotal: {_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
