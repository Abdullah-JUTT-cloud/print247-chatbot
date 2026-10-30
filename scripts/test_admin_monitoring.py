"""Admin login + monitoring + retrieval-cache tests.

Pure-stdlib modules only (admin_auth, monitoring, retrieval), so
these run in the VM without fastapi. The FastAPI wiring in main.py
(login routes, guards, cookie) is verified by py_compile, not by
import — fastapi lives only in Docker.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["ADMIN_PASSWORD"] = "test-pass-123"

from app.admin_auth import (admin_config, check_credentials, make_token,
                            verify_token)
from app.chat import retrieval as R
from app.chat.monitoring import monitoring_html, summarize_turns, turn_flags

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name} :: {detail}")


# --- admin_auth ---
u, p, s = admin_config()
check("admin config reads env password", (u, p) == ("admin", "test-pass-123"))
check("correct credentials pass", check_credentials("admin", "test-pass-123", u, p))
check("wrong password fails", not check_credentials("admin", "wrong", u, p))
check("no configured password never passes",
      not check_credentials("admin", "test-pass-123", u, None))
tok = make_token("admin", s)
check("token verifies", verify_token(tok, s) == "admin")
check("tampered token rejected", verify_token(tok + "x", s) is None)
check("wrong secret rejected", verify_token(tok, "other-secret") is None)
check("expired token rejected", verify_token(make_token("admin", s, ttl=-10), s) is None)

# --- monitoring ---
check("handoff flag", turn_flags({"handoff": "live_agent", "reply": "x"}) == ["handoff"])
check("complete is not a handoff",
      turn_flags({"handoff": "complete", "reply": "x"}) == [])
check("team-confirm flag",
      turn_flags({"reply": "the team can confirm it."}) == ["team_confirm"])
check("llm flag", turn_flags({"llm_used": True, "reply": "hi"}) == ["llm"])
docs = [
    {"session_id": "s1", "message": "hi", "reply": "hello", "handoff": None,
     "llm_used": False, "latency_ms": 120},
    {"session_id": "s1", "message": "wooden boxes?", "reply": "the team can confirm",
     "handoff": None, "llm_used": True, "latency_ms": 340},
    {"session_id": "s2", "message": "stop", "reply": "bye", "handoff": "live_agent",
     "llm_used": False, "latency_ms": 80},
]
sm = summarize_turns(docs)
check("summary counts", sm["total"] == 3 and sm["sessions"] == 2
      and sm["handoffs"] == 1 and sm["team_confirms"] == 1
      and sm["llm_turns"] == 1, str(sm))
check("summary avg latency", sm["avg_latency_ms"] == 180, str(sm))
check("summary flagged turns", len(sm["flagged"]) == 2, str(sm))
h = monitoring_html(sm)
check("monitoring html renders counts + links",
      "Team-confirm" in h and "Chat dekho" in h)

# --- retrieval cache ---
rows1 = R._read_kb_files()
rows2 = R._read_kb_files()
check("cache hit returns same rows", rows1 is rows2 and len(rows1) > 30)
open("kb/zz-cache-probe.md", "w").write("---\nstatus: verified\n---\nProbe file for cache test.\n")
try:
    rows3 = R._read_kb_files()
    check("new file invalidates cache",
          any(r["source"].endswith("zz-cache-probe.md") for r in rows3))
finally:
    os.remove("kb/zz-cache-probe.md")
rows4 = R._read_kb_files()
check("deleted file leaves cache",
      not any(r["source"].endswith("zz-cache-probe.md") for r in rows4))
check("time pre-check routes delivery-time-for-boxes to turnaround",
      R.retrieve("what is the delivery time for boxes?")[0]["source"].endswith(
          "turnaround.md"))
check("dimension 'how long' does not route to turnaround",
      not R.retrieve("how long are your labels")[0]["source"].endswith(
          "turnaround.md"))

print(f"ADMIN/MONITORING: {len(FAILURES)} failed")
if FAILURES:
    sys.exit(1)
print("All admin/monitoring/cache cases passed.")
