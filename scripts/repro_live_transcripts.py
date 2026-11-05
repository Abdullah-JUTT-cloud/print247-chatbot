"""Reproduce the 8 live transcripts on current local code to check current status."""
import sys
import os

sys.path.insert(0, ".")
from app.chat.brain import handle_message

def test_1_mylar_whats_is_best():
    sid = "repro-1-mylar"
    handle_message("I need mylar bags", session_id=sid)
    handle_message("test@example.com", session_id=sid)
    handle_message("4x6+2 inches", session_id=sid)
    handle_message("stand up", session_id=sid)
    handle_message("matte", session_id=sid)
    handle_message("1000", session_id=sid)
    handle_message("1", session_id=sid)
    handle_message("not yet", session_id=sid)
    # Now at extras turn:
    r = handle_message("whats is best?", session_id=sid)
    rep = r.get("reply", "")
    print(f"1. mylar 'whats is best?':\n  reply: {rep[:150]}...")
    assert "Rosenberg" not in rep, "Failed: answered with Rosenberg address!"
    assert any(w in rep.lower() for w in ["zipper", "notch", "valve", "extra"]), f"Failed: not in extras context: {rep}"
    assert "extra" in rep.lower() or "add" in rep.lower(), f"Failed: extras question not re-asked: {rep}"

def test_2_label_3d_refusal():
    sid = "repro-2-label"
    handle_message("I need labels", session_id=sid)
    handle_message("test@example.com", session_id=sid)
    r = handle_message("22*2*6", session_id=sid)
    rep = r.get("reply", "")
    print(f"2. label 22*2*6:\n  reply: {rep[:150]}...")
    assert "2 dimensions" in rep.lower() or "flat" in rep.lower() or "width x height" in rep.lower(), f"Failed: {rep}"

def test_3_hammad_cancel_delete():
    sid = "repro-3-hammad"
    handle_message("I need boxes", session_id=sid)
    r_cancel = handle_message("i dont need it", session_id=sid)
    print(f"3. Hammad cancel:\n  reply: {r_cancel.get('reply', '')[:150]}...")
    r_del = handle_message("delete save one", session_id=sid)
    print(f"3. Hammad delete:\n  reply: {r_del.get('reply', '')[:150]}...")
    assert "deleted" in r_del.get("reply", "").lower() or "cleared" in r_del.get("reply", "").lower(), f"Failed: {r_del}"

def test_4_whisky_confused():
    sid = "repro-4-whisky"
    handle_message("labels for whisky bottles", session_id=sid)
    handle_message("visitor@gmail.com", session_id=sid)
    handle_message("4 inches width 6 inches height", session_id=sid)
    r4 = handle_message("I am confused what do you suggest me", session_id=sid)
    print(f"4. Whisky confused turn 1:\n  reply: {r4.get('reply', '')[:150]}...")
    r5 = handle_message("I am confused what finish do I need, I can't decide between matte, gloss or soft touch", session_id=sid)
    print(f"4. Whisky confused turn 2:\n  reply: {r5.get('reply', '')[:150]}...")
    assert "for the team to confirm" in r5.get("reply", "").lower(), f"Failed: {r5}"

def test_5_cto_pizza_box():
    sid = "repro-5-cto"
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
        assert matched, f"Turn {turn_num} ({msg!r}) failed: got reply: {rep[:120]}..."
    print("5. CTO pizza-box 19-turn passed!")

def test_6_phone_refusal():
    sid = "repro-6-phone"
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
    # Now at phone:
    r = handle_message("dont have any phone number", session_id=sid)
    print(f"6. phone refusal:\n  reply: {r.get('reply', '')[:150]}...")
    assert "lead@example.com" in r.get("reply", ""), f"Failed: {r}"

def test_7_chnage_size_at_phone():
    sid = "repro-7-chnage-size"
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
    # Now at phone:
    r = handle_message("chnage size", session_id=sid)
    print(f"7. 'chnage size' at phone step:\n  reply: {r.get('reply', '')}...")
    # Expected: handles size change, asks for size!
    assert "size" in r.get("reply", "").lower(), f"Failed: did not ask for size! got: {r.get('reply')}"

def test_8_quote_summary():
    sid = "repro-8-qs"
    handle_message("I need boxes", session_id=sid)
    handle_message("lead@example.com", session_id=sid)
    handle_message("6x6x6 inches", session_id=sid)
    r = handle_message("what was my order", session_id=sid)
    print(f"8. quote summary:\n  reply: {r.get('reply', '')[:150]}...")
    assert "box" in r.get("reply", "").lower() and "6x6x6" in r.get("reply", ""), f"Failed: {r}"

if __name__ == "__main__":
    for fn in [test_1_mylar_whats_is_best, test_2_label_3d_refusal, test_3_hammad_cancel_delete,
               test_4_whisky_confused, test_5_cto_pizza_box, test_6_phone_refusal, test_7_chnage_size_at_phone, test_8_quote_summary]:
        try:
            fn()
            print(f"PASS {fn.__name__}\n")
        except Exception as e:
            print(f"FAIL {fn.__name__}: {e}\n")
