#!/usr/bin/env python3
"""Test suite for dimension-unit guard, family size rules, and 0x0 refusal."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.chat.brain import handle_message
from app.chat.size_rules import validate_size, count_dimensions
from app.chat.slots import extract_from_message

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


def main() -> None:
    print("=" * 60)
    print("RUNNING SIZE & QUANTITY GUARD TEST SUITE")
    print("=" * 60)

    # 1. Dimension-unit guard: number next to inch/mm/cm/feet/ft is NEVER a quantity
    ex1 = extract_from_message("14 inch")
    check(
        "'14 inch' extracted as size or unit, NEVER quantity 14",
        ex1.get("quantity") != "14" and ex1.get("quantity") is None,
        f"got {ex1}",
    )

    ex2 = extract_from_message("I need boxes 10 inches by 8 inches")
    check(
        "'10 inches by 8 inches' has no quantity 10 or 8",
        ex2.get("quantity") is None,
        f"got {ex2}",
    )

    ex3 = extract_from_message("4x8 feet banners")
    check(
        "'4x8 feet banners' has no quantity 4 or 8",
        ex3.get("quantity") is None,
        f"got {ex3}",
    )

    # 2. 2+2 at size is not a quantity
    ex4 = extract_from_message("2+2")
    check(
        "'2+2' has no quantity 2 or 4",
        ex4.get("quantity") is None,
        f"got {ex4}",
    )

    # 3. 0x0 refused at size turn
    v_zero1 = validate_size("box", "0x0")
    check(
        "'0x0' on box rejected",
        not v_zero1.ok and v_zero1.reason == "zero_dimension",
        f"got {v_zero1}",
    )
    v_zero2 = validate_size("label", "0x4 inches")
    check(
        "'0x4 inches' on label rejected",
        not v_zero2.ok and v_zero2.reason == "zero_dimension",
        f"got {v_zero2}",
    )
    v_zero3 = validate_size("pouch", "5x0 mm")
    check(
        "'5x0 mm' on pouch rejected",
        not v_zero3.ok and v_zero3.reason == "zero_dimension",
        f"got {v_zero3}",
    )

    # Full conversation turn with 0x0 refusal
    sid_zero = "test-zero-size-turn-1"
    handle_message("I need boxes", session_id=sid_zero)
    handle_message("user@example.com", session_id=sid_zero)
    r_zero = handle_message("0x0", session_id=sid_zero)
    rep_z = r_zero.get("reply", "").lower()
    check(
        "0x0 refused at the size turn in chat",
        "greater than zero" in rep_z,
        f"got: {r_zero.get('reply')}",
    )

    # 4. Typed feet accepted and stored, never offered
    sid_feet = "test-typed-feet-1"
    handle_message("I need banners", session_id=sid_feet)
    handle_message("user@example.com", session_id=sid_feet)
    r_feet = handle_message("4x8 feet", session_id=sid_feet)
    check(
        "'4x8 feet' accepted as size and not converted to quantity",
        r_feet.get("slots", {}).get("sizes") == "4x8 feet" and r_feet.get("slots", {}).get("quantity") is None,
        f"got slots: {r_feet.get('slots')}",
    )

    # 5. Pouch 3-dim stored as width x height + gusset
    sid_pouch = "test-pouch-3d-1"
    handle_message("I need mylar bags", session_id=sid_pouch)
    handle_message("user@example.com", session_id=sid_pouch)
    r_pouch = handle_message("3x3x5 inches", session_id=sid_pouch)
    check(
        "'3x3x5 inches' on pouch stored in +N gusset format ('3x3+5 inches')",
        r_pouch.get("slots", {}).get("sizes") == "3x3+5 inches",
        f"got sizes: {r_pouch.get('slots', {}).get('sizes')}",
    )

    print("\n" + "=" * 60)
    print(f"RESULTS: {_passed} PASSED, {_failed} FAILED")
    print("=" * 60)
    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
