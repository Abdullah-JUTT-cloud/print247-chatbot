"""Golden-set test v1 — deterministic, no LLM key, no network.

Run from the repo root:  python scripts/test_golden.py
Each case is a real-style question. The expected answer is NOT old
AI text: it is a phrase from the current KB file, and the test
requires (a) the bot's sources include that KB file, and
(b) the reply contains that phrase. A hallucinated price or fact
cannot pass, because the phrase must come from the retrieved KB
chunk the deterministic reply returns.

A failure here means STOP and fix before pushing, not "the test
is strict". The golden set grows only by human-approved candidates
(see scripts/extract_old_chat_candidates.py).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message

cases = json.load(open("eval/golden.json", encoding="utf-8"))["cases"]
failed = 0
for case in cases:
    r = handle_message(case["question"], store=None)
    ok_source = any(case["expected_source"] in s for s in r["sources"])
    ok_phrase = case["expected_phrase"].lower() in r["reply"].lower()
    ok = ok_source and ok_phrase
    print(("PASS " if ok else "FAIL ") + case["question"]
          + f" | sources={r['sources']} | phrase_ok={ok_phrase}")
    if not ok:
        failed += 1
print(f"{len(cases) - failed}/{len(cases)} golden cases passed.")
sys.exit(1 if failed else 0)
