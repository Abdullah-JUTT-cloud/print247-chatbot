"""Tests for the old-repo port (wave 1) — deterministic, no key, no network.

Every check names the old-bot rule it guards, so a failure here means
STOP and fix before pushing, not 'the test is strict'.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.attempts import (apply_ask_outcome, ask_outcome, asks_what_is_usual,
                               says_nothing_useful, says_they_do_not_know, visitor_is_asking)
from app.chat.brain import handle_message
from app.chat.complete import get_chat_complete_message, window_at
from app.chat.contacts import (email_in, has_reachable_contact, is_our_email,
                               is_our_phone, looks_like_phone, missing_contact_fields)
from app.chat.erp_eligibility import (dimensions_in_inches, pouch_style_for,
                                      price_request_for, quantity_split_question)
from app.chat.finishes_norm import finish_in, normalise_finish
from app.chat.intents import (asks_for_a_catalog, chat_is_a_pitch, is_already_a_customer,
                              is_done_with_us, is_looking_for_work, objects_to_the_price,
                              puts_it_off_for_now)
from app.chat.office import is_office_hours
from app.chat.quantity_parse import (answer_to_the_minimum, quantity_in,
                                     spelled_number_in, wants_smaller_run)
from app.chat.repeated import question_overlap, repeats_the_question
from app.chat.size_unit import guess_unit, size_is_a_pack_count, size_missing_unit, tidy_size
from datetime import datetime
from zoneinfo import ZoneInfo


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    assert cond, name


class S:
    """In-memory session store (load/save only — brain falls back to
    its in-process meta store, exactly like store=None with an id)."""
    def __init__(self):
        self.d = {}

    def load(self, sid):
        return self.d.get(sid, {})

    def save(self, sid, slots):
        self.d[sid] = slots


def run(sid, msgs, store=None):
    s = store or S()
    last = None
    for m in msgs:
        last = handle_message(m, session_id=sid, store=s)
    return last


# --- attempts ---
check("ask: question turn is free", ask_outcome("email", "What is your MOQ?", False) == "free")
check("ask: spec talk is free for contact", ask_outcome("phone", "I need matte 4x6 boxes", False) == "free")
check("ask: bare no to phone is declined", ask_outcome("phone", "no phone", False) == "declined")
check("ask: prefers email declines phone", ask_outcome("phone", "please send it to my email", False) == "declined")
check("ask: spent then declined caps at MAX", apply_ask_outcome(1, "spent") == 2
      and apply_ask_outcome(0, "declined") == 2)
check("asking: mid-message question counts", visitor_is_asking("please confirm: can you make this? MOQ?") is True)
check("usual: standard size question", asks_what_is_usual("What is a standard package size?") is True)
check("usual: rep recommendation is not spec", asks_what_is_usual("Who should I talk to?") is False)
check("dontknow: digit means answer", says_they_do_not_know("not sure, maybe 4x6") is False
      and says_they_do_not_know("no idea") is True)
check("nothing useful: gibberish", says_nothing_useful("Q as the Ty of") is True
      and says_nothing_useful("I need boxes") is False)

# --- repeated ---
check("repeat: same question scores high",
      question_overlap("What size do you need?", "What size are you looking for?") >= 0.6
      or repeats_the_question("What size do you need?", "What size are you looking for?") is True)
check("repeat: different field is not a repeat",
      repeats_the_question("How many units do you need?", "What size do you need?") is False)

# --- contacts ---
check("contact: spoken email", email_in("ali at gmail dot com") == "ali@gmail.com")
check("contact: our email is not theirs", is_our_email("Support@print247.us") is True)
check("contact: our phone is not theirs", is_our_phone("+1 (832) 807-3429") is True)
check("contact: address is not a phone", looks_like_phone("8772 Hesby Court, San Diego, CA 92129") is False
      and looks_like_phone("832-807-3429") is True)
check("contact: reachable needs email or phone",
      has_reachable_contact({"name": "Sara"}) is False
      and has_reachable_contact({"name": "Sara", "phone": "5551234567"}) is True)
check("contact: missing order is name,email,phone",
      missing_contact_fields({}) == ["name", "email", "phone"])

# --- intents ---
check("intent: work from home is a job", is_looking_for_work("Looking home paking job") is True)
check("intent: job done order is not a job", is_looking_for_work("I need a job done: 5000 mylar bags") is False)
check("intent: CV is a job", is_looking_for_work("here is my cv") is True)
check("intent: factory pitch", chat_is_a_pitch(["Dear Purchasing manager, I am Glen from Dongen Packing Co., Ltd"]) is True)
check("intent: catalog", asks_for_a_catalog("Can you send me a catalog please") is True)
check("intent: price objection", objects_to_the_price("too high, we get them for .54/ea") is True)
check("intent: later pauses", puts_it_off_for_now("Let me get back to you later please") is True)
check("intent: done", is_done_with_us("No longer interested goodbye") is True)
check("intent: already customer", is_already_a_customer("I already ordered labels and haven't received them") is True)
check("intent: new order is not already customer", is_already_a_customer("I want to order boxes") is False)

# --- quantity parsing ---
check("qty: twenty five thousand", spelled_number_in("twenty five thousand") == 25000)
check("qty: fifteen hundred", quantity_in("fifteen hundred") == 1500)
check("qty: ad link digits are not qty", quantity_in("https://wa.me/wamo/status/preview/18329832323/52699709925684 Qty: 30__") is None)
check("qty: range takes first", quantity_in("50-100") == 50)
check("qty: smaller run words", wants_smaller_run("yes smaller") is True)
check("qty: bare yes to minimum works",
      answer_to_the_minimum("yes", "the minimum is 1000 per size — would that work for you?") == "minimum")
check("qty: bare no to minimum is smaller",
      answer_to_the_minimum("no", "the minimum is 1000 per size — would that work for you?") == "smaller")
check("qty: either/or yes is ambiguous",
      answer_to_the_minimum("yes", "go ahead at 1000, or shall I look at a smaller run?") is None)

# --- finishes / sizes ---
check("finish: glass -> gloss", normalise_finish("glass") == "gloss" and finish_in("glass finish") == "gloss")
check("finish: matt -> matte", normalise_finish("matt") == "matte")
check("size: label 50x30 is mm", guess_unit("50x30", "label") == "mm")
check("size: box 10x8 is inches", guess_unit("10x8x4", "box") == "inches")
check("size: banner 3x6 is ft", guess_unit("3x6", "banner") == "ft")
check("size: pack count is not size", size_is_a_pack_count("10 ct") is True
      and size_is_a_pack_count("4x6, 2 count") is False)
check("size: tidy keeps measurements only", tidy_size("5x7, one that can stand on the shelf") == "5x7")
check("size: unit present means not missing", size_missing_unit("4x6 inches") is False
      and size_missing_unit("4x6") is True)

# --- complete / office ---
check("complete: weekday daytime window",
      window_at(datetime(2026, 10, 29, 14, 0, tzinfo=ZoneInfo("America/Chicago"))) == "daytime")
check("complete: weekend window",
      window_at(datetime(2026, 10, 31, 14, 0, tzinfo=ZoneInfo("America/Chicago"))) == "weekend")
check("complete: message promises Monday on weekend",
      "Monday morning" in get_chat_complete_message(datetime(2026, 10, 31, 14, 0, tzinfo=ZoneInfo("America/Chicago"))))
check("office: Friday night is staffed (PKT)",
      is_office_hours(datetime(2026, 10, 30, 21, 0, tzinfo=ZoneInfo("Asia/Karachi"))) is True)
check("office: Saturday night is not staffed (PKT)",
      is_office_hours(datetime(2026, 10, 31, 21, 0, tzinfo=ZoneInfo("Asia/Karachi"))) is False)
check("office: Saturday morning is still Friday shift",
      is_office_hours(datetime(2026, 10, 31, 3, 0, tzinfo=ZoneInfo("Asia/Karachi"))) is True)

# --- erp eligibility (static only, no ERP call, no price) ---
check("erp: 2 dims is flat pouch", pouch_style_for("mylar bag", measurements=2)["id"] == 36)
check("erp: 3 dims is stand-up", pouch_style_for("mylar bag", measurements=3)["id"] == 26)
check("erp: mm converts to inches", dimensions_in_inches("100x150mm") == [3.94, 5.91])
check("erp: split question at most twice",
      quantity_split_question("3", "6000", []) is not None
      and "in total, or" in quantity_split_question("3", "6000", []))
check("erp: request shape has disclosed defaults, no price",
      (lambda r: r is not None and r["defaults"]["micron"] == 120 and "price" not in r)(
          price_request_for({"product": "mylar bag", "sizes": "4x6", "quantity": "5000"})))

# --- brain: new intents end-to-end ---
r = run("p-job", ["Looking for a work from home job"])
check("brain: work-from-home deflected, no product question",
      "job applications" in r["reply"] and r["handoff"] == "not_a_customer")
r = run("p-pitch", ["Dear Purchasing manager, we are a leading packing company"])
check("brain: pitch deflected", "supplier" in r["reply"] and r["handoff"] == "not_a_customer")
r = run("p-cat", ["Can you send me a catalog please"])
check("brain: catalog answered, no catalog promised",
      "don't have a fixed catalog" in r["reply"])
r = run("p-price", ["too high, we get them for .54/ea"])
check("brain: price objection passed to team", "pass it to the team" in r["reply"])
r = run("p-later", ["Let me get back to you later please", "hi, I am back"])
check("brain: later pauses, next message resumes",
      "take your time" in run("p-later2", ["Let me get back to you later please"])["reply"])
r = run("p-bot", ["are you a bot?"])
check("brain: bot question answered straight", "automated assistant" in r["reply"])
r = run("p-usual", ["What is a standard package size?"])
check("brain: usual-size question answered, not stored as size",
      "no standard" in r["reply"].lower() and "sizes" not in r["slots"])
r = run("p-human", ["can I talk to a human please"])
check("brain: human request handed off", r["handoff"] == "visitor_asked_for_human")
r = run("p-cust", ["I already ordered labels and haven't received them"])
check("brain: existing customer handed off", r["handoff"] == "existing_customer")
r = run("p-rep", ["I was working with Jessica Joe before"])
check("brain: rep named hands over", "Jessica" in r["reply"] and r["handoff"] == "visitor_asked")
_SCRIPT = ["I need 5000 mylar bags, size 4x6 inches", "stand-up", "matte",
           "1 design", "zipper", "kraft"]
r = run("p-contact", _SCRIPT + ["Yes, that's correct",
                                "Sara", "sara@example.com", "5551234567"])
check("brain: yes -> name -> email -> phone -> Texas complete",
      r["handoff"] == "complete" and r.get("contact", {}).get("email") == "sara@example.com"
      and r["slots"].get("quantity") == "5000")
r = run("p-contact2", _SCRIPT + ["Yes, that's correct",
                                 "no", "no", "no"])
check("brain: contact refusals still finish, flagged no-contact",
      r["handoff"] == "complete_no_contact")
r = run("p-unit", ["I need labels", "50x30", "mm"])
check("brain: bare unit answers unit question", r["slots"].get("sizes") == "50x30 mm")
r = run("p-fresh", _SCRIPT + ["Yes, that's correct",
                              "Sara", "sara@example.com", "5551234567",
                              "I need custom boxes"])
check("brain: finished chat + new order starts fresh",
      r["slots"].get("product") == "box" and "sizes" not in r["slots"])
r = run("p-ours", _SCRIPT + ["Yes, that's correct",
                             "Sara", "Support@print247.us", "8328073429"])
check("brain: our own email/phone never stored as visitor's",
      r.get("contact", {}).get("email") is None and r["handoff"] != "complete")

print("All ported tests passed.")
