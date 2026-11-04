"""Tests for quote summary vs past-order handoff:
1. Mid-quote or completed quote requests for requirements/order details
   must reply with the collected spec summary from session slots
   (product, sizes, type, style, finishes, quantity, skus, material, email if given)
   and continue with the next missing question (or confirmation if complete).
   They must NEVER route to the past-order/team-member handoff.
2. Genuine status questions ("where is my order", "track my order") still hand off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message


def test_full_box_flow_quote_summary():
    # full box flow then "what was my order (requirement details)?"
    # -> reply lists the stored spec and contains no "team member" handoff
    sid = "test-qs-full-box"
    msgs = [
        "I need boxes",
        "10x6x4 inches",
        "mailer",
        "matte",
        "500 units",
        "1",
        "corrugated",
        "ali@example.com",
        "yes",
        "Abdullah",
        "5551234567"
    ]
    for m in msgs:
        handle_message(m, session_id=sid)

    r = handle_message("what was my order (requirement details)?", session_id=sid)
    reply_low = r["reply"].lower()

    # Must list stored spec
    assert "box" in reply_low, f"expected 'box' in reply: {r['reply']}"
    assert "10x6x4" in r["reply"], f"expected size in reply: {r['reply']}"
    assert "mailer" in reply_low, f"expected mailer in reply: {r['reply']}"
    assert "matte" in reply_low, f"expected matte in reply: {r['reply']}"
    assert "500" in r["reply"], f"expected 500 in reply: {r['reply']}"
    assert "corrugated" in reply_low, f"expected corrugated in reply: {r['reply']}"

    # Must contain NO team-member existing-order handoff
    assert r["handoff"] is None, f"expected handoff None, got: {r['handoff']}"
    assert "look into your existing order" not in reply_low, f"handed off wrongly: {r['reply']}"
    assert "pass this to a team member who can look into" not in reply_low, f"handed off wrongly: {r['reply']}"
    print("PASS: full box flow then 'what was my order (requirement details)?' -> spec listed, no handoff")


def test_where_is_my_order_no_quote_in_progress():
    # "where is my order?" with no quote in progress -> handoff still works (no regression)
    sid = "test-qs-where-is-order-fresh"
    r = handle_message("where is my order?", session_id=sid)
    assert r["handoff"] == "existing_customer", f"expected existing_customer handoff, got: {r['handoff']}"
    assert "look into your existing order" in r["reply"].lower(), (
        f"expected existing order message, got: {r['reply']}"
    )
    print("PASS: 'where is my order?' with no quote in progress -> handoff still works (no regression)")


def test_mid_quote_summary_phrasings():
    # Mid-quote requests with various requirement/order summary phrasings
    phrasings = [
        "what was my order",
        "my order details",
        "my requirements",
        "requirement details",
        "what did I order",
        "show my requirements/quote",
    ]
    for i, phrase in enumerate(phrasings):
        sid = f"test-qs-mid-{i}"
        handle_message("I need custom boxes", session_id=sid)
        handle_message("test@example.com", session_id=sid)
        handle_message("10x12 inches", session_id=sid)

        r = handle_message(phrase, session_id=sid)
        reply_low = r["reply"].lower()

        assert r["handoff"] is None, f"expected handoff None for {phrase!r}, got: {r['handoff']}"
        assert "look into your existing order" not in reply_low, f"handed off wrongly for {phrase!r}: {r['reply']}"
        assert "box" in reply_low, f"expected product in reply for {phrase!r}: {r['reply']}"
        assert "10x12" in r["reply"], f"expected size in reply for {phrase!r}: {r['reply']}"
        # Continues with next missing question (type / style / quantity)
        assert any(k in reply_low for k in ["type", "style", "finish", "quantity", "what"]), (
            f"expected next question in reply for {phrase!r}: {r['reply']}"
        )
        print(f"PASS: mid-quote phrasing {phrase!r} -> spec listed, no handoff, continues flow")


def test_where_is_my_order_mid_quote():
    # Genuine tracking questions like 'where is my order' or 'track my order' still hand off
    sid = "test-qs-where-mid"
    handle_message("I need boxes", session_id=sid)
    r = handle_message("where is my order?", session_id=sid)
    assert r["handoff"] == "existing_customer", f"expected existing_customer handoff, got: {r['handoff']}"
    assert "look into your existing order" in r["reply"].lower()
    print("PASS: 'where is my order?' mid-quote -> still hands off to team member")


if __name__ == "__main__":
    test_full_box_flow_quote_summary()
    test_where_is_my_order_no_quote_in_progress()
    test_mid_quote_summary_phrasings()
    test_where_is_my_order_mid_quote()
    print("ALL quote summary tests PASSED!")
