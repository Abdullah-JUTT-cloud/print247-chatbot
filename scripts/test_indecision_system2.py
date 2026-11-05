#!/usr/bin/env python3
"""Parameterized tests for System 2 Indecision & Don't-Know Detection Gap.

Tests:
1. Reproduction transcript from user request:
   ["labels for whisky bottles", email, "4 inches width 6 inches height",
    "I am confused what do you suggest me",
    "I am confused what finish do I need, I can't decide between matte, gloss or soft touch"]
2. Parameterized matrix across fields:
   (finish, material, style, type, extras, quantity, sizes)
   x phrasings:
   (confused, can't decide, what do you suggest, which is best, help me choose, no idea, not sure)

Verifies:
- 1st indecision -> KB-grounded suggestion + re-ask, never a bare summary repeat
- 2nd indecision on same field -> gave_up marked ("for the team to confirm") and moves on
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("OPENAI_API_KEY", None)

from app.chat.brain import handle_message

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = ""):
    global _passed, _failed
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if cond:
        _passed += 1
    else:
        _failed += 1


def run_turns(sid: str, turns: list[str]) -> list[dict]:
    out = []
    for t in turns:
        out.append(handle_message(t, session_id=sid, store=None))
    return out


print("\n=== Part 1: Reproduction Transcript Test ===")
repro_sid = "test-repro-system2-gap"
repro_turns = [
    "labels for whisky bottles",
    "visitor@gmail.com",
    "4 inches width 6 inches height",
    "I am confused what do you suggest me",
    "I am confused what finish do I need, I can't decide between matte, gloss or soft touch",
]

repro_results = run_turns(repro_sid, repro_turns)
r1, r2, r3, r4, r5 = repro_results

# Turn 3: 4 inches width 6 inches height parsed into size, asks finish
check(
    "Turn 3 extracts sizes correctly without leaking quantity",
    r3["slots"].get("sizes") == "4 width x 6 height inches"
    and r3["slots"].get("quantity") is None
    and "finishes" in r3["missing"]
    and "matte, gloss or soft touch" in r3["reply"].lower(),
    f"slots={r3['slots']} reply={r3['reply']!r}",
)

# Turn 4: 1st indecision on finish -> KB options with one-line diffs + re-ask, NOT bare summary repeat
low4 = r4["reply"].lower()
check(
    "Turn 4 (1st indecision) suggests finish options from KB with differences + re-asks",
    "matte" in low4 and "gloss" in low4 and "soft touch" in low4
    and "what finish do you prefer" in low4
    and "here's where we are" not in low4
    and "finishes" in r4["missing"]
    and r4["slots"].get("finishes") is None,
    f"reply={r4['reply']!r} missing={r4['missing']}",
)

# Turn 5: 2nd indecision on finish -> gave_up marked and moves to quantity
low5 = r5["reply"].lower()
check(
    "Turn 5 (2nd indecision) gives up finish for team to confirm and moves to quantity",
    "for the team to confirm" in low5
    and "quantity" in low5
    and "finishes" not in r5["missing"]
    and "here's where we are" not in low5,
    f"reply={r5['reply']!r} missing={r5['missing']}",
)


print("\n=== Part 2: Parameterized Fields x Phrasings Matrix ===")

FIELDS_CONFIG = [
    (
        "finish",
        "finishes",
        ["I need stand-up pouches", "visitor@gmail.com", "6x9+3 inches"],
        ["matte", "gloss", "soft touch"],
        "What finish do you prefer",
    ),
    (
        "material",
        "material",
        [
            "I need pull-up banners", "visitor@gmail.com", "33.5x79 inches",
            "Matte", "500 units", "1 design", "No, I need design help",
        ],
        ["vinyl"],
        "Do you have any specific material",
    ),
    (
        "style",
        "style",
        ["I need mylar bags", "visitor@gmail.com", "5x7 inches"],
        ["stand-up", "flat", "flat-bottom"],
        "What style",
    ),
    (
        "type",
        "type",
        ["I need custom boxes", "visitor@gmail.com", "10x8x4 inches"],
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
        ["zipper", "tear notch"],
        "Do you want me to add a zipper and tear notch",
    ),
    (
        "quantity",
        "quantity",
        ["I need vinyl stickers", "visitor@gmail.com", "4x4 inches", "Gloss"],
        ["short-run", "bulk", "rough range"],
        "What quantity are you looking to order",
    ),
    (
        "sizes",
        "sizes",
        ["I need business cards", "visitor@gmail.com"],
        ["leave the size", "width x height", "3.5", "2"],
        "What size do you need",
    ),
]

PHRASINGS = [
    ("confused", "I am confused"),
    ("cant_decide", "I can't decide"),
    ("what_suggest", "what do you suggest?"),
    ("which_best", "which is best?"),
    ("help_choose", "help me choose"),
    ("no_idea", "no idea"),
    ("not_sure", "not sure"),
]

for field_label, field_key, setup_turns, expected_hints, reask_sub in FIELDS_CONFIG:
    for phrase_label, first_phrase in PHRASINGS:
        case_id = f"sys2-{field_label}-{phrase_label}"
        run_turns(case_id, setup_turns)

        # 1st Indecision:
        r_first = handle_message(first_phrase, session_id=case_id, store=None)
        low_first = r_first["reply"].lower()
        has_hint = any(h.lower() in low_first for h in expected_hints)
        has_reask = reask_sub.lower() in low_first
        not_bare_repeat = "here's where we are" not in low_first
        still_pending = field_key in r_first["missing"]

        check(
            f"1st indecision on {field_label} with {phrase_label!r} ({first_phrase!r})",
            has_hint and has_reask and not_bare_repeat and still_pending,
            f"reply={r_first['reply'][:120]!r} missing={r_first['missing']}",
        )

        # 2nd Indecision:
        second_phrase = "can't decide" if phrase_label != "cant_decide" else "I am still confused"
        r_second = handle_message(second_phrase, session_id=case_id, store=None)
        low_second = r_second["reply"].lower()
        team_confirms = "for the team to confirm" in low_second
        advanced = field_key not in r_second["missing"]
        not_bare_repeat_2 = "here's where we are" not in low_second

        check(
            f"2nd indecision on {field_label} with {phrase_label!r} advances and marks gave_up",
            team_confirms and advanced and not_bare_repeat_2,
            f"reply={r_second['reply'][:120]!r} missing={r_second['missing']}",
        )

print(f"\nTotal: {_passed} passed, {_failed} failed")
if _failed > 0:
    sys.exit(1)
