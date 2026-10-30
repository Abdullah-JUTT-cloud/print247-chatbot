"""Quote-file questions + clock-time questions — Oct 31 transcripts.

Issue A (01:41 transcript): "which image is added in my quote?"
matched NO own-data pattern, fell to retrieval, and got the
quote-flow process recited twice. "add this in my quote" after an
upload got no confirmation either, and the closing message listed
no files at all.
Issue B (01:43 transcript): "what time is it?" got a shipping
sentence, and the correction ("i asked you about time on clock")
got the finished-chat stored-data dump. Root causes: no clock
branch at all, AND typo correction turned "clock" into "lock"
(crash-lock/zip-lock vocab), so even a clock branch on the
corrected text would have missed it.

Run from the repo root:  python scripts/test_quote_files_time.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat import brain as B
from app.chat.brain import handle_message
from app.chat.normalize import correct_query


def run(sid, msgs, **kw):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None, **kw)
    return r


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


_TIME = re.compile(r"\d{1,2}:\d{2} [AP]M")

# --- Issue B: clock ---
check("typo correction no longer turns clock into lock",
      correct_query("i asked you about time on clock")
      == "i asked you about time on clock")
r = run("qf-clock", ["what time is it?"], tz="Asia/Karachi")
check("what time is it answers from the clock, in visitor tz",
      bool(_TIME.search(r["reply"])) and "PKT" in r["reply"]
      and "Shipping" not in r["reply"], r["reply"][:120])
r = run("qf-clock-corr", ["i asked you about time on clock"], tz="Asia/Karachi")
check("correction about time on clock answers from the clock, not a data dump",
      bool(_TIME.search(r["reply"])) and "saved for you" not in r["reply"],
      r["reply"][:120])
r = run("qf-clock-hours", ["what time do you close?"])
check("what time do you close stays on office hours, not the clock",
      "5:00 pm" in r["reply"] and "right now" not in r["reply"],
      r["reply"][:160])
r = run("qf-clock-bad-tz", ["what time is it?"], tz="Not/AZone")
check("garbage timezone falls back to server time, never crashes",
      bool(_TIME.search(r["reply"])), r["reply"][:120])

# --- Issue A: design files as own data ---
FLOW = ["i need labels", "ali@test.com", "100x150mm", "gloss", "300", "1 design"]
FILES = [{"name": "7894986.ai", "mime": "application/pdf", "description": None},
         {"name": "7894988.jpg", "mime": "image/jpeg", "description": "coffee label"}]
run("qf-files", FLOW)
B._META_FALLBACK["qf-files"]["design_files"] = FILES
r = handle_message("which image is added in my quote?",
                   session_id="qf-files", store=None)
check("which image is in my quote lists both files, no process recital",
      "7894986.ai" in r["reply"] and "7894988.jpg" in r["reply"]
      and "dieline" not in r["reply"], r["reply"][:200])
r = handle_message("what did you add?", session_id="qf-files", store=None)
check("what did you add now includes design files",
      "7894986.ai" in r["reply"] and "7894988.jpg" in r["reply"],
      r["reply"][:200])
r = handle_message("add this in my quote", session_id="qf-files", store=None)
check("add this in my quote confirms the attached files",
      "attached to your quote" in r["reply"]
      and "7894986.ai" in r["reply"], r["reply"][:200])
r = run("qf-nofiles", FLOW)
r = handle_message("which image is added in my quote?",
                   session_id="qf-nofiles", store=None)
check("no files attached is answered honestly, not with a KB fact",
      "don't have any design files" in r["reply"], r["reply"][:160])

# --- Issue A: closing message lists the files ---
run("qf-close", FLOW + ["no", "no", "No preference"])
B._META_FALLBACK["qf-close"]["design_files"] = FILES
r = run("qf-close", ["yes", "adbullah", "no"])
check("closing message lists both design files",
      "7894986.ai" in r["reply"] and "7894988.jpg" in r["reply"]
      and "I have your order" in r["reply"], r["reply"][:260])

# --- Server-side pieces (source-checked; fastapi absent in VM) ---
main_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "app", "main.py"), encoding="utf-8").read()
check("upload route names the whole attached set from the second file on",
      "Your quote now has" in main_src)
check("chat route carries the visitor timezone",
      "tz=payload.tz" in main_src)
ui_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "app", "chat_ui.py"), encoding="utf-8").read()
check("UI sends its timezone with every chat message",
      "resolvedOptions().timeZone" in ui_src)

print("QUOTE-FILES-TIME: all passed")
