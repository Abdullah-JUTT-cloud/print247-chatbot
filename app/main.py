"""Print247 new chatbot API — chat brain + chat UI + admin dashboard.

Endpoints:
  GET  /            -> chat UI (browser page, talks to POST /chat).
  GET  /admin       -> sessions-only admin page, READ-ONLY, behind
                       the admin login (Oct 30: ADMIN_USER +
                       ADMIN_PASSWORD from .env; no password set =
                       admin closed, never open). No drafts, no
                       approve flow, no KB editing: improvement
                       happens in code (user's call, Oct 29, 2026).
  GET  /admin/login -> login form (no JS). GET /admin/logout clears
                       the session cookie.
  GET  /admin/session/{id} -> full transcript of one session
                       (also behind the login).
  GET  /health      -> proves API + Mongo + Qdrant are reachable.
  POST /chat        -> the brain: language detect, slot extraction,
                       code guards, RAG retrieval, then a gpt-5-mini
                       answer when OPENAI_API_KEY is set, otherwise a
                       deterministic reply that never invents a fact.
  GET  /api/chat/history -> one session's saved chat, oldest first.
                       Stays open on purpose: the visitor chat UI
                       calls it to restore a conversation on
                       refresh, and session ids are client-side
                       randomUUIDs (unguessable). The admin LISTING
                       is the exposure, and that is behind login.

Every chat is logged to Mongo (chat_logs collection, fail-soft)
so the admin can see past conversations session by session,
plus monitoring (latency + flags: handoff, team_confirm, llm).
Logging never breaks a chat: if Mongo is down, the chat still
answers. Re-ingest runs from the terminal
(docker compose exec api python scripts/ingest.py), not from
the admin page.
"""
import datetime
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from pymongo import MongoClient
from qdrant_client import QdrantClient

from .admin_auth import (COOKIE, admin_config, check_credentials,
                         make_token, verify_token)
from .chat.brain import handle_message
from .chat.monitoring import monitoring_html, summarize_turns, turn_flags
from .chat.store import get_store
from .web import ADMIN_HTML, CHAT_HTML

app = FastAPI(title="print247-chatbot")
_store = get_store()


def _mongo_ok() -> bool:
    try:
        MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                    serverSelectionTimeoutMS=2000).admin.command("ping")
        return True
    except Exception:
        return False


def _qdrant_ok() -> bool:
    try:
        QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333")).get_collections()
        return True
    except Exception:
        return False


_MONGO_CLIENT = None


def _mongo_client():
    """One shared client (pooling) instead of a new TCP + handshake
    per logged turn. Creation is lazy in pymongo, so a down Mongo
    at import time is fine — operations still fail soft below."""
    global _MONGO_CLIENT
    if _MONGO_CLIENT is None:
        _MONGO_CLIENT = MongoClient(
            os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
            serverSelectionTimeoutMS=2000)
    return _MONGO_CLIENT


def _log_chat(payload_message: str, session_id: str | None, result: dict,
              reply_to: str | None = None, latency_ms: int | None = None) -> None:
    """Fail-soft: a logging failure must never break the chat."""
    try:
        _mongo_client().get_default_database()["chat_logs"].insert_one({
            "session_id": session_id, "message": payload_message,
            "reply": result.get("reply"), "sources": result.get("sources", []),
            "suggestions": result.get("suggestions", []),
            "reply_to": reply_to,
            "handoff": result.get("handoff"), "llm_used": result.get("llm_used"),
            "language": result.get("language"),
            "latency_ms": latency_ms, "flags": turn_flags(result),
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        })
    except Exception:
        pass


def _admin_check(request: Request) -> str | None:
    """Logged-in admin username, or None. No configured password
    means closed: _admin_guard turns that into the setup page."""
    _user, _password, _secret = admin_config()
    if not _password:
        return None
    name = verify_token(request.cookies.get(COOKIE), _secret)
    return name if name == _user else None


def _admin_guard(request: Request):
    """None when access is allowed, else the response to return:
    the setup page when no password is configured (fail closed),
    else a redirect to the login form."""
    _user, password, _secret = admin_config()
    if not password:
        return _admin_shell(
            "Admin band hai",
            "<p class=\"warn\">ADMIN_PASSWORD .env me set nahi hai. "
            ".env me <code>ADMIN_PASSWORD=...</code> likho, phir "
            "<code>docker compose up --build -d</code> chalao — tab "
            "tak admin kisi ko nahi khulega.</p>")
    if not _admin_check(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None


def _login_html(error: str | None = None) -> str:
    err = f"<p class=\"warn\">{error}</p>" if error else ""
    return (f"<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>Admin Login</title><style>body{{font-family:system-ui,sans-serif;"
            f"max-width:480px;margin:60px auto;padding:0 16px;background:#0a0a0a;"
            f"color:#e5e7eb}}input{{width:100%;padding:10px;margin:6px 0;background:#1f2937;"
            f"border:1px solid #374151;color:#e5e7eb;border-radius:8px}}"
            f"button{{padding:10px 18px;background:#f97316;color:#111827;border:none;"
            f"border-radius:8px;font-weight:700;cursor:pointer}}"
            f".warn{{color:#fbbf24}}</style></head><body><h1>Admin Login</h1>{err}"
            f"<form method=\"post\" action=\"/admin/login\">"
            f"<label>Username<br><input name=\"username\" value=\"admin\"></label>"
            f"<label>Password<br><input type=\"password\" name=\"password\"></label>"
            f"<button type=\"submit\">Login karo</button></form></body></html>")


@app.get("/", response_class=HTMLResponse)
def chat_ui():
    return CHAT_HTML


def _session_rows_html() -> str:
    """Server-rendered session table (SSR): one row per
    conversation, no JS needed. Sessions only — no draft, approve
    or KB actions anywhere on this page anymore."""
    import html as _html
    try:
        col = _mongo_client().get_default_database()["chat_logs"]
        docs = list(col.find().sort("created_at", -1).limit(500))
        sessions = _group_sessions(docs)[:25]
    except Exception:
        return "<p class='warn'>Chats server par nahi ban sake (Mongo down ho sakta hai).</p>"
    if not sessions:
        return "<p>No chats yet — send a chat from the chat page first.</p>"
    btn = ("style=\"background:#f97316;color:#111827;padding:7px 14px;border-radius:8px;"
           "text-decoration:none;font-weight:700;display:inline-block\"" )
    rows = ""
    for s in sessions:
        sid = _html.escape(s['session_id'])
        rows += (f"<tr><td>{_html.escape(str(s['first_message']))}"
                 f"<br><small>{sid}</small></td>"
                 f"<td>{s['count']}</td>"
                 f"<td><a href=\"/admin/session/{sid}\" {btn}>Chat dekho</a></td></tr>")
    return ("<table><tr><th>Chat (pehla message)</th><th>Messages</th><th>Action</th></tr>"
            + rows + "</table>")


def _admin_shell(title: str, body: str) -> str:
    """Full no-JS page: black theme, back link, escaped body."""
    return (f"<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title><style>body{{font-family:system-ui,sans-serif;"
            f"max-width:960px;margin:30px auto;padding:0 16px;background:#0a0a0a;"
            f"color:#e5e7eb}}h1,h2{{color:#f9fafb}}a{{color:#fb923c}}"
            f"button{{padding:7px 14px;margin:2px;cursor:pointer;background:#f97316;"
            f"color:#111827;border:none;border-radius:8px;font-weight:700}}"
            f"textarea,input{{width:100%;padding:8px;margin:4px 0;background:#1f2937;"
            f"border:1px solid #374151;color:#e5e7eb;border-radius:8px}}"
            f"pre{{background:#1f2937;color:#e5e7eb;padding:12px;white-space:pre-wrap}}"
            f".warn{{color:#fbbf24}}.help{{color:#9ca3af}}</style></head>"
            f"<body><h1>{title}</h1>{body}"
            f"<p><a href=\"/admin\">Wapas Admin par</a></p></body></html>")


def _mongo_docs(session_id: str | None = None) -> list:
    col = _mongo_client().get_default_database()["chat_logs"]
    if session_id:
        return list(col.find({"session_id": session_id}).sort("created_at", 1))
    return list(col.find().sort("created_at", -1).limit(500))


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if _admin_check(request):
        return RedirectResponse("/admin", status_code=303)
    return _login_html()


@app.post("/admin/login")
async def admin_login(request: Request):
    form = await request.form()
    user, password, secret = admin_config()
    if check_credentials(str(form.get("username", "")),
                         str(form.get("password", "")),
                         user, password):
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie(COOKIE, make_token(user, secret),
                        httponly=True, samesite="lax", path="/admin",
                        max_age=43200)
        return resp
    return _login_html("Ghalat username ya password.")


@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/admin")
    return resp


@app.get("/admin", response_class=HTMLResponse)
def admin_ui(request: Request):
    guard = _admin_guard(request)
    if guard is not None:
        return guard
    import re as _re
    try:
        docs = _mongo_docs()
        monitoring = monitoring_html(summarize_turns(docs))
    except Exception:
        monitoring = "<p class='warn'>Monitoring nahi ban saka (Mongo down ho sakta hai).</p>"
    html = ADMIN_HTML.replace("{{MONITORING}}", monitoring)
    html = html.replace("{{SESSION_ROWS}}", _session_rows_html())
    try:
        mongo, qdrant = _mongo_ok(), _qdrant_ok()
        health = (f"Server: {'OK' if mongo and qdrant else 'MASLA'} "
                  f"(api=ok, mongo={mongo}, qdrant={qdrant}) — "
                  f"ye server se likha hua hai, JS ke baghair.")
    except Exception:
        health = "Server: check nahi ho saka."
    return _re.sub(r'<p id="serverstatus"[^>]*>.*?</p>',
                   f'<p id="serverstatus" class="help">{health}</p>',
                   html, count=1)


@app.get("/admin/session/{session_id}", response_class=HTMLResponse)
def admin_session_page(request: Request, session_id: str):
    guard = _admin_guard(request)
    if guard is not None:
        return guard
    import html as _html
    try:
        docs = _mongo_docs(session_id)
    except Exception as e:
        return _admin_shell("Chat nahi mili", f"<p class=\"warn\">{_html.escape(str(e))}</p>")
    if not docs:
        return _admin_shell("Chat nahi mili", "<p>No chats found for this session.</p>")
    lines = []
    for d in docs:
        lines.append(f"Visitor: {_html.escape(str(d.get('message', '')))}")
        lines.append(f"Bot: {_html.escape(str(d.get('reply', '')))}")
        lines.append("")
    return _admin_shell(f"Poori chat: {session_id}",
        f"<pre>{chr(10).join(lines)}</pre>")


@app.get("/health")
def health():
    return {"api": "ok", "mongo": _mongo_ok(), "qdrant": _qdrant_ok()}


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    reply_to: str | None = None


@app.post("/chat")
def chat(payload: ChatIn):
    started = time.monotonic()
    result = handle_message(payload.message, payload.session_id, _store,
                            reply_to=payload.reply_to)
    latency_ms = round((time.monotonic() - started) * 1000)
    _log_chat(payload.message, payload.session_id, result, payload.reply_to,
              latency_ms=latency_ms)
    return result


@app.get("/api/chat/history")
def chat_history(session_id: str):
    """Saved chat for one session, oldest first. This is what makes
    a refresh keep the conversation: the UI restores these rows
    instead of starting from an empty screen. A New chat uses a
    new session_id, so its history starts empty on purpose."""
    try:
        col = _mongo_client().get_default_database()["chat_logs"]
        docs = list(col.find({"session_id": session_id}).sort("created_at", 1).limit(200))
        return [{"message": d.get("message"), "reply": d.get("reply", ""),
                 "sources": d.get("sources", []),
                 "suggestions": d.get("suggestions", []),
                 "reply_to": d.get("reply_to")} for d in docs]
    except Exception:
        return []


def _group_sessions(docs: list) -> list[dict]:
    """One row per session (one conversation), not one row per
    message. Messages inside a session stay in order, oldest first."""
    sessions: dict[str, dict] = {}
    order: list[str] = []

    def _sort_key(x: dict):
        # created_at can be missing, a string, or a naive datetime in
        # old logs — any of those used to crash the whole /logs call
        # (and the admin page then sat on Loading forever, because
        # the old JS had no error path). Normalize, never crash.
        v = x.get("created_at")
        if isinstance(v, datetime.datetime):
            return v if v.tzinfo else v.replace(tzinfo=datetime.timezone.utc)
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

    for d in sorted(docs, key=_sort_key):
        sid = d.get("session_id") or "unknown"
        if sid not in sessions:
            sessions[sid] = {"session_id": sid, "messages": [], "sources": [],
                             "has_handoff": False, "started_at": str(d.get("created_at", ""))}
            order.append(sid)
        sessions[sid]["messages"].append({
            "message": d.get("message"), "reply": d.get("reply", ""),
            "sources": d.get("sources", []), "handoff": d.get("handoff")})
        for s in d.get("sources", []) or []:
            if s not in sessions[sid]["sources"]:
                sessions[sid]["sources"].append(s)
        if d.get("handoff") and d.get("handoff") != "complete":
            sessions[sid]["has_handoff"] = True
    out = []
    for sid in reversed(order):  # latest session first
        s = sessions[sid]
        msgs = s["messages"]
        out.append({"session_id": sid, "count": len(msgs),
                    "first_message": msgs[0]["message"] if msgs else "",
                    "last_message": msgs[-1]["message"] if msgs else "",
                    "started_at": s["started_at"], "sources": s["sources"],
                    "has_handoff": s["has_handoff"], "messages": msgs})
    return out



