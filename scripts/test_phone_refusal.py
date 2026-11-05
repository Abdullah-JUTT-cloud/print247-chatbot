import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from app.chat import brain as B
from app.chat.field_options import options_for

PHRASINGS = [
    "dont have any phone number",
    "no phone",
    "I don't have a phone",
    "don't want to share",
    "skip",
    "no",
    # Additional real-world variants
    "dont have a phone",
    "i have no phone",
    "haven't got a phone",
    "no phone number",
    "don't have one",
    "wont share phone",
    "prefer not to share",
    "i cannot share my phone number",
]

BASE_FLOW = [
    "I need labels for whisky bottles",
    "client@example.com",
    "4x6 inches",
    "gloss",
    "1000",
    "1 design",
    "no extras",
    "vinyl",
    "Yes, that's correct",
    "John Doe",
]


def test_phone_refusals():
    print("Testing phone refusal phrasings...")
    for phrase in PHRASINGS:
        sid = "phone-refuse-" + uuid.uuid4().hex[:8]
        replies = []
        for step in BASE_FLOW:
            r = B.handle_message(step, session_id=sid, store=None)
            replies.append(r["reply"])

        # At this point, the bot just asked for the phone
        assert "phone" in replies[-1].lower(), f"Expected phone question in last reply, got: {replies[-1]}"

        # Visitor gives refusal / inability phrase
        r_refuse = B.handle_message(phrase, session_id=sid, store=None)
        replies.append(r_refuse["reply"])

        # 1. Must close with email follow-up line
        reply_low = r_refuse["reply"].lower()
        assert "client@example.com" in r_refuse["reply"], (
            f"Phrase '{phrase}': expected client email in close reply, got: {r_refuse['reply']}"
        )
        assert "follow up with you at" in reply_low, (
            f"Phrase '{phrase}': expected follow up line in close reply, got: {r_refuse['reply']}"
        )

        # 2. Phone question must appear EXACTLY ONCE in entire chat
        phone_q_count = sum(
            1 for rep in replies
            if ("phone number in case" in rep.lower() or "phone number can the team reach" in rep.lower())
        )
        assert phone_q_count == 1, (
            f"Phrase '{phrase}': expected phone question to appear exactly once, but appeared {phone_q_count} times"
        )

        # 3. Verified contact state
        contact = r_refuse.get("contact") or {}
        assert contact.get("email") == "client@example.com", f"Expected email in contact: {contact}"
        assert contact.get("name") == "John Doe", f"Expected name in contact: {contact}"
        assert not contact.get("phone"), f"Expected phone not in contact, got: {contact.get('phone')}"

        # 4. Never ask for phone again in this chat
        r_after = B.handle_message("thanks", session_id=sid, store=None)
        assert "phone number" not in r_after["reply"].lower(), (
            f"Phrase '{phrase}': asked for phone again after close: {r_after['reply']}"
        )

        print(f"  ✓ '{phrase}' closed at once with email follow-up; phone asked exactly once")


def test_valid_phone_stored():
    print("Testing valid phone handling...")
    sid = "phone-valid-" + uuid.uuid4().hex[:8]
    for step in BASE_FLOW:
        B.handle_message(step, session_id=sid, store=None)

    r_phone = B.handle_message("555-123-4567", session_id=sid, store=None)
    contact = r_phone.get("contact") or {}
    assert contact.get("phone") == "555-123-4567", f"Expected phone 555-123-4567, got {contact.get('phone')}"
    assert r_phone.get("handoff") == "complete", f"Expected handoff complete, got {r_phone.get('handoff')}"
    print("  ✓ Valid phone number correctly stored and chat completed")


def test_phone_question_never_repeats_verbatim():
    print("Testing phone question non-repetition...")
    sid = "phone-norepeat-" + uuid.uuid4().hex[:8]
    r_last = None
    for step in BASE_FLOW:
        r_last = B.handle_message(step, session_id=sid, store=None)

    first_phone_q = r_last["reply"]
    assert "phone" in first_phone_q.lower()

    # Visitor says something that is neither phone nor refusal
    r_again = B.handle_message("what is this for?", session_id=sid, store=None)
    second_phone_q = r_again["reply"]

    assert first_phone_q != second_phone_q, (
        f"Phone question repeated verbatim!\nQ1: {first_phone_q}\nQ2: {second_phone_q}"
    )
    print("  ✓ Phone question never repeated verbatim twice in a row")


def test_material_suggestion_text_and_chips_match():
    print("Testing material suggestion text and chips option match...")
    sid = "mat-match-" + uuid.uuid4().hex[:8]
    steps = [
        "I need labels for whisky bottles",
        "client@example.com",
        "4x6 inches",
        "gloss",
        "1000",
        "1 design",
        "no extras",
    ]
    for step in steps:
        B.handle_message(step, session_id=sid, store=None)

    # Trigger indecision at material field
    r = B.handle_message("I am confused what do you suggest me", session_id=sid, store=None)

    reply_text = r["reply"]
    chips = r.get("suggestions", [])

    # The text suggests Vinyl and Paper for labels
    assert "Vinyl" in reply_text and "Paper" in reply_text, f"Expected Vinyl and Paper in reply: {reply_text}"
    assert "Kraft" not in reply_text, f"Kraft should not be in sticker material reply: {reply_text}"

    # Chips must list the SAME options (Vinyl and Paper), NOT Kraft!
    assert "Kraft" not in chips, f"Chips must not offer Kraft instead: {chips}"
    assert "Vinyl" in chips, f"Expected Vinyl in chips: {chips}"
    assert "Paper" in chips, f"Expected Paper in chips: {chips}"

    # Verify options in text match options in chips
    material_chips = [c for c in chips if c != "No preference"]
    assert material_chips == ["Vinyl", "Paper"], f"Expected ['Vinyl', 'Paper'], got {material_chips}"
    print("  ✓ Material suggestion text and chips list the same options (Vinyl, Paper; no Kraft)")


if __name__ == "__main__":
    test_phone_refusals()
    test_valid_phone_stored()
    test_phone_question_never_repeats_verbatim()
    test_material_suggestion_text_and_chips_match()
    print("\nALL PHONE REFUSAL AND OPTIONS MATCH TESTS PASSED!")
