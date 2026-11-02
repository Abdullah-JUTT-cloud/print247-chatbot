"""Meta-references + full AI context — Nov 3 live test.

The visitor quoted the bot's own "inside the pack" line back at
it ("how can anything go in the lables?", "you said ...,
elaborate it") and got two dodges: a guessed question ("Do you
want to know what content can go on a label?") and an ack +
size question that never answered anything. Two causes:

1. The bot did not recognise talk about its own previous
   message, so the turns fell through to script/fact handling.
2. The LLM summary carried only the last bot QUESTION, never
   what the bot actually said — so the model could not see the
   line being quoted and guessed instead.

Fixes: the summary now carries the last bot replies too; a
meta-reference is routed to the answer path; and the pack
confusion for flat products is corrected in code, plainly,
before any guessing can happen.

Run from the repo root:  python scripts/test_meta_context.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import (_conversation_summary, _is_meta_reference,
                            handle_message)


def run(sid, msgs, **kw):
    r = None
    for m in msgs:
        r = handle_message(m, session_id=sid, store=None, **kw)
    return r


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# --- detector ---
check("meta: 'you said ... elaborate' detected",
      _is_meta_reference("you said (tell me what will go inside the pack) "
                         "i am asking you to elaborate it"))
check("meta: 'how can anything go in' detected",
      _is_meta_reference("how can anything go in the labels?"))
check("meta: ordinary answers are not meta",
      not _is_meta_reference("4x6 inches")
      and not _is_meta_reference("no preference")
      and not _is_meta_reference("i need labels"))

# --- summary carries bot replies now ---
meta = {"visitor_messages": ["I need labels", "not sure"],
        "last_bot_question": "What size do you need?",
        "bot_replies": ["Got it — label. What is the best email to send "
                        "the quote to?",
                        "No problem — tell me what will go inside the pack, "
                        "or pick a common size to start with."]}
s = _conversation_summary(meta, {"product": "label"})
check("summary includes earlier bot replies",
      "inside the pack" in s and "Earlier bot replies" in s, s)
check("empty summary still empty",
      _conversation_summary({}, {}) == "")

# --- the reported turns, answered instead of dodged ---
r = run("mc-1", ["I need labels", "ab@gmail.com", "not sure",
                 "how can anything go in the lables?"])
check("challenge about 'go in labels' gets a plain correction",
      "my mistake" in r["reply"]
      and "Nothing goes inside a label" in r["reply"]
      and "What size" in r["reply"]
      and "Do you want to know" not in r["reply"], r["reply"][:260])
r = run("mc-2", ["I need labels", "ab@gmail.com", "not sure",
                 "you said (tell me what will go inside the pack) "
                 "i am asking you to ellaborate it"])
check("quoted 'inside the pack' + elaborate gets correction, no ack dodge",
      "my mistake" in r["reply"]
      and "Nothing goes inside a label" in r["reply"]
      and "What size" in r["reply"]
      and not r["reply"].startswith("Got it"), r["reply"][:260])

print("META-CONTEXT: all passed")
