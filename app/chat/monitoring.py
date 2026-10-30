"""Monitoring — pure functions over chat_logs rows, no FastAPI or
Mongo import, so the VM can unit-test them.

What it watches (Oct 30, user: "monitoring bhi krdo"):
- handoff: the bot gave up the chat to a human path (anything but
  a clean "complete").
- team_confirm: the reply says "team can/will confirm" — the bot
  could not answer from the KB. This is the knowledge-gap signal:
  every team_confirm is a candidate for a KB entry or an eval case.
- llm: the turn used the LLM path (vs deterministic code).
- latency_ms: measured around handle_message in main.py.

The admin page renders a summary of the last 500 logged turns
plus the newest 20 flagged turns. No new infrastructure: the
logs already exist (chat_logs), this only reads them.
"""

import html as _html


def turn_flags(result: dict | None) -> list[str]:
    """Flags for one turn's result dict (or one chat_logs row)."""
    result = result or {}
    flags = []
    handoff = result.get("handoff")
    if handoff and handoff != "complete":
        flags.append("handoff")
    reply = str(result.get("reply") or "").lower()
    if "team can confirm" in reply or "team will confirm" in reply:
        flags.append("team_confirm")
    if result.get("llm_used"):
        flags.append("llm")
    return flags


def summarize_turns(docs: list) -> dict:
    """Counts + newest flagged turns. Docs are expected newest
    first (Mongo sort created_at -1, as main.py fetches them)."""
    total = len(docs)
    sessions = len({d.get("session_id") for d in docs})
    handoffs = team = llm = 0
    latencies: list[float] = []
    flagged: list[dict] = []
    for d in docs:
        flags = turn_flags(d)
        if "handoff" in flags:
            handoffs += 1
        if "team_confirm" in flags:
            team += 1
        if "llm" in flags:
            llm += 1
        lat = d.get("latency_ms")
        if isinstance(lat, (int, float)):
            latencies.append(float(lat))
        if ("handoff" in flags or "team_confirm" in flags) \
                and len(flagged) < 20:
            flagged.append({
                "session_id": d.get("session_id") or "unknown",
                "message": str(d.get("message") or "")[:120],
                "reply": str(d.get("reply") or "")[:160],
                "flags": flags,
            })
    avg = (sum(latencies) / len(latencies)) if latencies else None
    return {"total": total, "sessions": sessions, "handoffs": handoffs,
            "team_confirms": team, "llm_turns": llm,
            "avg_latency_ms": round(avg) if avg is not None else None,
            "flagged": flagged}


def monitoring_html(summary: dict) -> str:
    """Server-rendered monitoring section for /admin (no JS)."""
    avg = summary.get("avg_latency_ms")
    avg_txt = f"{avg} ms" if avg is not None else "n/a (purane logs)"
    parts = [
        "<h2>Monitoring — aakhri 500 turns</h2>",
        f"<p>Turns: {summary['total']} | Sessions: {summary['sessions']} | "
        f"Handoffs: {summary['handoffs']} | Team-confirm: "
        f"{summary['team_confirms']} | LLM turns: {summary['llm_turns']} | "
        f"Avg latency: {avg_txt}</p>",
        "<p class=\"help\">Team-confirm matlab bot KB se jawab nahi de saka — "
        "ye knowledge gaps hain, inko KB ya eval case banana chahiye. "
        "Handoff matlab chat human path par gayi.</p>",
    ]
    if not summary["flagged"]:
        parts.append("<p class=\"help\">Koi flagged turn nahi — na handoff, na team-confirm.</p>")
    else:
        rows = ""
        for f in summary["flagged"]:
            sid = _html.escape(f["session_id"])
            rows += (f"<tr><td>{_html.escape(f['message'])}"
                     f"<br><small>{sid}</small></td>"
                     f"<td>{','.join(f['flags'])}</td>"
                     f"<td>{_html.escape(f['reply'])}</td>"
                     f"<td><a href=\"/admin/session/{sid}\">Chat dekho</a></td></tr>")
        parts.append("<table><tr><th>Visitor message</th><th>Flag</th>"
                     "<th>Bot reply</th><th>Action</th></tr>" + rows + "</table>")
    return "".join(parts)
