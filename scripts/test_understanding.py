#!/usr/bin/env python3
"""Comprehensive understanding & anti-hardcode test suite.

Verifies:
1. Structured intent classification across paraphrase families (min 5 each, all classify identically).
2. Held-out paraphrases unseen during development.
3. Anti-hardcode proof: zero matches for test paraphrases inside app/ code.
4. Full regression replays of the live transcripts:
   - CTO pizza-box full transcript (18 turns)
   - 3D label size refusal at the size turn
   - Vague "whats is best?" at extras turn
   - Post-completion cancel & delete
   - Phone refusal ("dont have any phone number")
   - Whisky labels finish indecision
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.chat.brain import handle_message
from app.chat.understand import classify_turn, load_env_file

load_env_file()

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    tag = "PASS" if cond else "FAIL"
    msg = f"  [{tag}] {name}"
    if not cond and detail:
        msg += f" — {detail}"
    print(msg)
    if cond:
        _passed += 1
    else:
        _failed += 1


# ---------------------------------------------------------------------------
# Section 1: Anti-Hardcode Proof
# ---------------------------------------------------------------------------
def test_anti_hardcode_proof() -> None:
    print("\n--- ANTI-HARDCODE PROOF (Zero matches in app/) ---")
    test_phrases = [
        "i have not decided yet",
        "I already told you that I dont know",
        "I dont know",
        "not yet",
        "any suggestion?",
        "what do you suggest",
        "which is best",
        "help me choose",
        "can't decide",
        "confused",
        "haven't picked one",
        "you choose for me",
        "I'm torn",
        "no clue",
        "whatever you recommend",
        "any other finish you have?",
        "do you guys offer any other finish type?",
        "what other sizes?",
        "something else?",
        "i dont need it",
        "delete save one",
        "dont have any phone number",
    ]

    for phrase in test_phrases:
        clean = phrase.strip("?").lower()
        res = subprocess.run(
            ["grep", "-rni", "--exclude-dir=.git", "--exclude-dir=scripts", clean, os.path.join(ROOT, "app")],
            capture_output=True,
            text=True,
        )
        matches = [line for line in res.stdout.strip().splitlines() if line]
        check(
            f"Zero occurrences of {phrase!r} in app/ code",
            len(matches) == 0,
            f"Found in: {matches[:3]}",
        )


# ---------------------------------------------------------------------------
# Section 2: Paraphrase Families & Classification Invariance
# ---------------------------------------------------------------------------
def test_paraphrase_families() -> None:
    print("\n--- PARAPHRASE FAMILIES (OpenAI + RAG Understanding) ---")

    # 1. dont_know family (15 required + held-out)
    dont_know_family = [
        "i have not decided yet",
        "I already told you that I dont know",
        "I dont know",
        "not yet",
        "any suggestion?",
        "what do you suggest",
        "which is best",
        "help me choose",
        "can't decide",
        "confused",
        "haven't picked one",
        "you choose for me",
        "I'm torn",
        "no clue",
        "whatever you recommend",
        # Held-out
        "i am completely undecided",
        "haven't made up my mind",
        "you tell me what works best",
        "still figuring it out",
        "no idea honestly",
    ]
    for text in dont_know_family:
        clf = classify_turn(text, pending_field="finishes", slots={"product": "box"})
        check(
            f"dont_know: {text!r} -> dont_know",
            clf["intent"] == "dont_know",
            f"got {clf['intent']}",
        )

    # 2. ask_field_info family (4 required + held-out)
    ask_field_info_family = [
        "any other finish you have?",
        "do you guys offer any other finish type?",
        "what other sizes?",
        "something else?",
        # Held-out
        "are there different options available?",
        "what alternative choices do you offer?",
        "can I see other options?",
        "what else can I choose from?",
        "are there other finishes besides these?",
    ]
    for text in ask_field_info_family:
        clf = classify_turn(text, pending_field="finishes", slots={"product": "box"})
        check(
            f"ask_field_info: {text!r} -> ask_field_info",
            clf["intent"] == "ask_field_info",
            f"got {clf['intent']}",
        )

    # 3. cancel family (min 5 + held-out)
    cancel_family = [
        "i dont need it",
        "cancel this quote",
        "no longer interested",
        "please scrap it",
        "i want to withdraw my order",
        # Held-out
        "call off the order",
        "nevermind don't want it",
        "drop my quote request",
        "i changed my mind, don't need this anymore",
        "forget the order, cancel please",
    ]
    for text in cancel_family:
        clf = classify_turn(text, pending_field="none", slots={"product": "box", "_complete": True})
        check(
            f"cancel: {text!r} -> cancel",
            clf["intent"] == "cancel",
            f"got {clf['intent']}",
        )

    # 4. delete family (min 5 + held-out)
    delete_family = [
        "delete save one",
        "delete my saved details",
        "erase all my data",
        "wipe my information",
        "purge my record",
        # Held-out
        "scrub my session data",
        "clear everything you stored",
        "delete all my records please",
        "remove my stored data from chat",
        "forget all my saved details",
    ]
    for text in delete_family:
        clf = classify_turn(text, pending_field="none", slots={"product": "box", "_complete": True})
        check(
            f"delete: {text!r} -> delete",
            clf["intent"] == "delete",
            f"got {clf['intent']}",
        )

    # 5. change_field family (min 5 + held-out)
    change_field_family = [
        ("change finish to matte", "finishes"),
        ("i want to change quantity", "quantity"),
        ("update size to 4x6", "sizes"),
        ("modify the material", "material"),
        ("can we revise the designs count", "skus"),
        # Held-out
        ("change size", "sizes"),
        ("switch finish to gloss", "finishes"),
        ("revise quantity to 2000", "quantity"),
        ("i need to adjust my dimensions", "sizes"),
        ("update style", "style"),
    ]
    for text, exp_field in change_field_family:
        clf = classify_turn(text, pending_field="quantity", slots={"product": "box", "finishes": "gloss"})
        check(
            f"change_field: {text!r} -> change_field ({exp_field})",
            clf["intent"] == "change_field" and clf.get("target_field") == exp_field,
            f"got intent={clf['intent']}, target_field={clf.get('target_field')}",
        )


# ---------------------------------------------------------------------------
# Section 3: Live Transcript Regressions
# ---------------------------------------------------------------------------
def test_regression_cto_pizza_box() -> None:
    print("\n--- REGRESSION: CTO Pizza-Box 18-Turn Flow ---")
    sid = "reg-cto-pizza-box-1"
    flow = [
        ("I need pizza boxes", ["email", "quote"]),
        ("user@example.com", ["size", "width"]),
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
        ("i dont need it", ["I understand", "quote stays with our team"]),
        ("delete save one", ["deleted your saved details"]),
    ]

    for turn_num, (msg, expected_phrases) in enumerate(flow, 1):
        res = handle_message(msg, session_id=sid, store=None)
        rep = res.get("reply", "")
        low_rep = rep.lower()
        matched = all(exp.lower() in low_rep for exp in expected_phrases)
        check(
            f"Turn {turn_num} ({msg!r}) contains {expected_phrases}",
            matched,
            f"got reply: {rep[:120]}...",
        )


def test_regression_3d_label_size_refusal() -> None:
    print("\n--- REGRESSION: 3D Label Size Refusal at Size Turn ---")
    sid = "reg-3d-label-1"
    handle_message("I need labels", session_id=sid)
    handle_message("test@example.com", session_id=sid)
    # Label family allows exactly 2 dimensions (flat). 22*2*6 has 3 dimensions.
    r3 = handle_message("22*2*6", session_id=sid)
    rep = r3.get("reply", "").lower()
    check(
        "Label 22*2*6 refused as 3-dimensional at the size turn",
        "2 dimensions" in rep or "width x height" in rep or "no depth" in rep or "labels are flat" in rep or "2 dimensions only" in rep or "flat product" in rep,
        f"got: {r3.get('reply')}",
    )


def test_regression_vague_extras_relevance() -> None:
    print("\n--- REGRESSION: Vague Mid-Quote Extras Relevance ---")
    sid = "reg-vague-extras-1"
    handle_message("I need mylar bags", session_id=sid)
    handle_message("shopper@example.com", session_id=sid)
    handle_message("4x6x2.5 inches", session_id=sid)
    handle_message("stand up", session_id=sid)
    handle_message("matte", session_id=sid)
    handle_message("1000", session_id=sid)
    handle_message("1", session_id=sid)
    handle_message("no", session_id=sid)  # design image
    # Now extras turn: bot asks about zipper and tear notch
    r_vague = handle_message("whats is best?", session_id=sid)
    rep = r_vague.get("reply", "").lower()
    # Must NOT contain company address / Rosenberg
    check(
        "Vague 'whats is best?' at extras does NOT answer with Rosenberg address",
        "rosenberg" not in rep and "avenue" not in rep and "77471" not in rep,
        f"got: {r_vague.get('reply')}",
    )
    # Must be grounded in extras context (zipper / tear notch / options)
    check(
        "Vague 'whats is best?' at extras answers in pending extras context",
        "zipper" in rep or "tear notch" in rep or "reseal" in rep or "options" in rep,
        f"got: {r_vague.get('reply')}",
    )


def test_regression_post_completion_cancel_delete() -> None:
    print("\n--- REGRESSION: Post-Completion Cancel & Delete ---")
    sid = "reg-post-complete-1"
    handle_message("I need boxes", session_id=sid)
    handle_message("buyer@example.com", session_id=sid)
    handle_message("10x10x10 inches", session_id=sid)
    handle_message("mailer", session_id=sid)
    handle_message("gloss", session_id=sid)
    handle_message("1000", session_id=sid)
    handle_message("1", session_id=sid)
    handle_message("no", session_id=sid)
    handle_message("corrugated", session_id=sid)
    handle_message("yes", session_id=sid)  # confirm
    handle_message("Alice", session_id=sid)  # name
    handle_message("no phone", session_id=sid)  # phone refusal -> quote complete!

    # 1. Post-completion cancel
    rc = handle_message("i dont need it", session_id=sid)
    rep_c = rc.get("reply", "").lower()
    check(
        "Cancel reply contains 'I understand' and future follow-up",
        "understand" in rep_c and ("team" in rep_c or "follow up" in rep_c or "change your mind" in rep_c),
        f"got: {rc.get('reply')}",
    )
    check(
        "Cancel reply does NOT loop the saved order summary",
        "just to confirm" not in rep_c and "your quote request is ready" not in rep_c,
        f"got: {rc.get('reply')}",
    )

    # 2. Post-completion delete
    rd = handle_message("delete save one", session_id=sid)
    rep_d = rd.get("reply", "").lower()
    check(
        "Delete reply confirms deletion of saved details",
        "deleted" in rep_d or "cleared" in rep_d or "wiped" in rep_d,
        f"got: {rd.get('reply')}",
    )

    # 3. Subsequent check finds no saved order
    ro = handle_message("what was my order?", session_id=sid)
    rep_o = ro.get("reply", "").lower()
    check(
        "After delete, own-data check reports no saved quote",
        "no saved" in rep_o or "don't have" in rep_o or "starting fresh" in rep_o or "no details" in rep_o or "no active quote" in rep_o or "haven't started" in rep_o,
        f"got: {ro.get('reply')}",
    )


def test_regression_phone_refusal() -> None:
    print("\n--- REGRESSION: Optional Phone Refusal Handled Promptly ---")
    sid = "reg-phone-refusal-1"
    handle_message("I need bags", session_id=sid)
    handle_message("lead@example.com", session_id=sid)
    handle_message("5x7 inches", session_id=sid)
    handle_message("flat", session_id=sid)
    handle_message("matte", session_id=sid)
    handle_message("1000", session_id=sid)
    handle_message("1", session_id=sid)
    handle_message("no", session_id=sid)
    handle_message("none", session_id=sid)
    handle_message("kraft", session_id=sid)
    handle_message("yes", session_id=sid)
    handle_message("Sam", session_id=sid)
    r_phone = handle_message("dont have any phone number", session_id=sid)
    rep = r_phone.get("reply", "").lower()
    check(
        "Phone refusal does NOT repeat the phone question",
        "phone number" not in rep or "follow up" in rep,
        f"got: {r_phone.get('reply')}",
    )
    check(
        "Phone refusal closes cleanly with email confirmation",
        "lead@example.com" in rep and ("follow up" in rep or "team" in rep),
        f"got: {r_phone.get('reply')}",
    )


def test_regression_whisky_confused() -> None:
    print("\n--- REGRESSION: Whisky Labels Finish Indecision ---")
    sid = "reg-whisky-confused-1"
    handle_message("labels for whisky bottles", session_id=sid)
    handle_message("visitor@gmail.com", session_id=sid)
    handle_message("4x6 inches", session_id=sid)
    handle_message("I am confused what do you suggest me", session_id=sid)
    r5 = handle_message("I am confused what finish do I need, I can't decide between matte, gloss or soft touch", session_id=sid)
    rep = r5.get("reply", "").lower()
    check(
        "Whisky labels finish indecision marks gave_up and moves to quantity",
        "for the team to confirm" in rep and "quantity" in rep,
        f"got: {r5.get('reply')}",
    )


def test_regression_chnage_size_at_phone() -> None:
    print("\n--- REGRESSION: 'chnage size' at Phone Step ---")
    sid = "reg-chnage-size-phone-1"
    handle_message("I need boxes", session_id=sid)
    handle_message("lead@example.com", session_id=sid)
    handle_message("6x6x6 inches", session_id=sid)
    handle_message("mailer", session_id=sid)
    handle_message("matte", session_id=sid)
    handle_message("500", session_id=sid)
    handle_message("1", session_id=sid)
    handle_message("none", session_id=sid)
    handle_message("cardboard", session_id=sid)
    handle_message("yes", session_id=sid)
    handle_message("Alex", session_id=sid)
    r = handle_message("chnage size", session_id=sid)
    rep = r.get("reply", "").lower()
    check(
        "Typo 'chnage size' at phone step asks for size",
        "size" in rep,
        f"got: {r.get('reply')}",
    )


def test_regression_quote_summary() -> None:
    print("\n--- REGRESSION: Quote Summary Request Mid-Quote ---")
    sid = "reg-quote-summary-1"
    handle_message("I need boxes", session_id=sid)
    handle_message("lead@example.com", session_id=sid)
    handle_message("6x6x6 inches", session_id=sid)
    r = handle_message("what was my order", session_id=sid)
    rep = r.get("reply", "").lower()
    check(
        "Mid-quote 'what was my order' gives requirement details without duplication",
        "box" in rep and "6x6x6" in rep,
        f"got: {r.get('reply')}",
    )


def test_regression_combined_turn() -> None:
    print("\n--- REGRESSION: Combined Message (Answer + Question) ---")
    sid = "reg-combined-turn-1"
    handle_message("I need custom boxes", session_id=sid)
    handle_message("user@example.com", session_id=sid)
    handle_message("10x8x4 inches", session_id=sid)
    handle_message("mailer", session_id=sid)
    handle_message("tuck-end", session_id=sid)
    r = handle_message("gloss, and what is soft touch?", session_id=sid)
    rep = r.get("reply", "").lower()
    check(
        "Combined message stores answer, answers question, asks NEXT question",
        r["slots"].get("finishes") == "gloss"
        and ("soft touch" in rep or "velvet" in rep or "luxur" in rep)
        and "quantity" in rep
        and "finish do you prefer" not in rep,
        f"reply={r.get('reply')!r} slots={r.get('slots')}",
    )


def main() -> None:
    print("=" * 60)
    print("RUNNING UNDERSTANDING & ANTI-HARDCODE TEST SUITE")
    print("=" * 60)

    test_anti_hardcode_proof()
    test_paraphrase_families()
    test_regression_cto_pizza_box()
    test_regression_3d_label_size_refusal()
    test_regression_vague_extras_relevance()
    test_regression_post_completion_cancel_delete()
    test_regression_phone_refusal()
    test_regression_whisky_confused()
    test_regression_chnage_size_at_phone()
    test_regression_quote_summary()
    test_regression_combined_turn()

    print("\n" + "=" * 60)
    print(f"RESULTS: {_passed} PASSED, {_failed} FAILED")
    print("=" * 60)
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
