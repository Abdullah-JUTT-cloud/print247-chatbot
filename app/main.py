"""Print247 new chatbot API — chat brain + chat UI + admin dashboard.

Endpoints:
  GET  /            -> chat UI (browser page, talks to POST /chat).
  GET  /admin       -> admin dashboard (DEV ONLY, no login yet —
                       see app/web.py security note before public use).
  GET  /health      -> proves API + Mongo + Qdrant are reachable.
  POST /chat        -> the brain: language detect, slot extraction,
                       code guards, RAG retrieval, then a gpt-5-mini
                       answer when OPENAI_API_KEY is set, otherwise a
                       deterministic reply that never invents a fact.
  GET  /api/admin/kb, POST /api/admin/okf,
  POST /api/admin/okf/{id}/approve, POST /api/admin/ingest,
  POST /api/admin/test, GET /api/admin/logs
                     -> admin operations (see app/admin_api.py).

Every chat is logged to Mongo (chat_logs collection, fail-soft)
so the admin can see new and unanswered questions. Logging never
breaks a chat: if Mongo is down, the chat still answers.
"""
import datetime
import os

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from pymongo import MongoClient
from qdrant_client import QdrantClient

from . import admin_api
from .chat.brain import handle_message
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


def _log_chat(payload_message: str, session_id: str | None, result: dict,
              reply_to: str | None = None) -> None:
    """Fail-soft: a logging failure must never break the chat."""
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        client.get_default_database()["chat_logs"].insert_one({
            "session_id": session_id, "message": payload_message,
            "reply": result.get("reply"), "sources": result.get("sources", []),
            "suggestions": result.get("suggestions", []),
            "reply_to": reply_to,
            "handoff": result.get("handoff"), "llm_used": result.get("llm_used"),
            "language": result.get("language"),
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        })
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
def chat_ui():
    return CHAT_HTML


def _kb_rows_html() -> str:
    """Server-rendered KB table (SSR). The old admin relied only on
    JS fetches: if JS never ran in the browser, the page sat on
    Loading forever even though the server was healthy (proven by
    the user's own logs: GET /admin 200, but no /api/* request ever
    arrived). SSR rows mean the data is visible even with JS dead;
    the JS loads then overwrite them with fresh data when it runs."""
    import html as _html
    try:
        files = admin_api.list_kb()
    except Exception:
        return "<p class='warn'>KB list server par nahi ban saki.</p>"
    if not files:
        return "<p>No KB files found.</p>"
    btn = ("style=\"background:#f97316;color:#111827;padding:7px 14px;border-radius:8px;"
           "text-decoration:none;font-weight:700;display:inline-block\"" )
    rows = "".join(
        f"<tr><td>{_html.escape(f['path'])}</td><td>{_html.escape(f['status'])}</td>"
        f"<td><a href=\"/admin/kb/{_html.escape(f['id'])}\" {btn}>View</a>"
        + (f" <form method=\"post\" action=\"/admin/kb/{_html.escape(f['id'])}/approve\" "
           f"style=\"display:inline\"><button>Approve</button></form>"
           if f['status'] == 'draft' else "") + "</td></tr>"
        for f in files)
    return ("<table><tr><th>File</th><th>Status</th><th>Action</th></tr>"
            + rows + "</table>")


def _session_rows_html() -> str:
    import html as _html
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        col = client.get_default_database()["chat_logs"]
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
                 f"<td><a href=\"/admin/session/{sid}\" {btn}>Chat dekho</a> "
                 f"<form method=\"post\" action=\"/admin/draft-from-session\" "
                 f"style=\"display:inline\"><input type=\"hidden\" name=\"session_id\" "
                 f"value=\"{sid}\"><button>Draft KB</button></form></td></tr>")
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
    client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                         serverSelectionTimeoutMS=2000)
    col = client.get_default_database()["chat_logs"]
    if session_id:
        return list(col.find({"session_id": session_id}).sort("created_at", 1))
    return list(col.find().sort("created_at", -1).limit(500))


@app.get("/admin", response_class=HTMLResponse)
def admin_ui():
    import re as _re
    html = (ADMIN_HTML.replace("{{KB_ROWS}}", _kb_rows_html())
                      .replace("{{SESSION_ROWS}}", _session_rows_html()))
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


@app.get("/admin/kb/{file_id}", response_class=HTMLResponse)
def admin_kb_page(file_id: str):
    import html as _html
    d = admin_api.get_kb_file(file_id)
    if not d.get("ok"):
        return _admin_shell("File nahi mili",
                            f"<p class=\"warn\">{_html.escape(d.get('error', 'not found'))}</p>")
    body = _html.escape(d["body"])
    return _admin_shell(f"KB file: {d['path']}",
        f"<p class=\"help\">Status: {d['status']} | Source: {_html.escape(d['source'])}</p>"
        f"<pre>{body}</pre>"
        f"<h2>Fact likho / Save karo</h2>"
        f"<form method=\"post\" action=\"/admin/kb/{file_id}/save\">"
        f"<textarea name=\"body\" rows=\"16\">{body}</textarea><br>"
        f"<button>Save edits</button></form>"
        f"<form method=\"post\" action=\"/admin/kb/{file_id}/approve\">"
        f"<button>Approve this file</button></form>"
        f"<p class=\"help\">Approve tabhi karo jab placeholder (VERIFIED FACT) "
        f"ki jagah asal fact likh diya ho. Approve ke baad Re-ingest dabao.</p>")


@app.post("/admin/kb/{file_id}/save")
def admin_kb_save(file_id: str, body: str = Form(...)):
    admin_api.save_kb_file(file_id, body)
    return RedirectResponse(url=f"/admin/kb/{file_id}", status_code=303)


@app.post("/admin/kb/{file_id}/approve", response_class=HTMLResponse)
def admin_kb_approve(file_id: str):
    import html as _html
    r = admin_api.approve_okf(file_id)
    if not r.get("ok"):
        return _admin_shell("Approve nahi hua",
            f"<p class=\"warn\">{_html.escape(r.get('error', 'unknown'))}</p>"
            f"<p><a href=\"/admin/kb/{file_id}\">Wapas file par</a></p>")
    return RedirectResponse(url=f"/admin/kb/{file_id}", status_code=303)


@app.post("/admin/kb/create")
def admin_kb_create(id: str = Form(...), title: str = Form(...),
                    category: str = Form(...), source: str = Form(...),
                    body: str = Form(...)):
    r = admin_api.create_okf(id, title, category, source, body)
    if not r.get("ok"):
        import html as _html
        return _admin_shell("Create nahi hua",
            f"<p class=\"warn\">{_html.escape(r.get('error', 'unknown'))}</p>")
    return RedirectResponse(url=f"/admin/kb/{r.get('id', id)}", status_code=303)


@app.get("/admin/session/{session_id}", response_class=HTMLResponse)
def admin_session_page(session_id: str):
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
        f"<pre>{chr(10).join(lines)}</pre>"
        f"<form method=\"post\" action=\"/admin/draft-from-session\">"
        f"<input type=\"hidden\" name=\"session_id\" value=\"{_html.escape(session_id)}\">"
        f"<button>Is chat se Draft KB banao</button></form>")


@app.post("/admin/draft-from-session", response_class=HTMLResponse)
def admin_draft_from_session_page(session_id: str = Form(...)):
    import html as _html
    try:
        docs = _mongo_docs(session_id)
        msgs = [{"message": d.get("message"), "reply": d.get("reply", ""),
                 "sources": d.get("sources", [])} for d in docs]
        r = admin_api.draft_from_session(session_id, msgs)
    except Exception as e:
        r = {"ok": False, "error": str(e)}
    if not r.get("ok"):
        return _admin_shell("Draft nahi bana",
            f"<p class=\"warn\">{_html.escape(r.get('error', 'unknown'))}</p>")
    return RedirectResponse(url=f"/admin/kb/{r['id']}", status_code=303)


@app.post("/admin/auto-draft-all", response_class=HTMLResponse)
def admin_auto_draft_all_page():
    import html as _html
    try:
        sessions = _group_sessions(_mongo_docs())
        created, skipped = [], []
        for s in sessions:
            r = admin_api.draft_from_session(s["session_id"], s["messages"])
            (created if r.get("ok") else skipped).append(s["session_id"])
        body = (f"<p>Ban gaye: {len(created)}</p><pre>{_html.escape(chr(10).join(created))}</pre>"
                f"<p>Pehle se drafted (skip): {len(skipped)}</p>"
                f"<pre>{_html.escape(chr(10).join(skipped))}</pre>")
    except Exception as e:
        body = f"<p class=\"warn\">{_html.escape(str(e))}</p>"
    return _admin_shell("Auto-draft result", body)


@app.post("/admin/ingest", response_class=HTMLResponse)
def admin_ingest_page():
    import html as _html
    r = admin_api.run_ingest()
    return _admin_shell("Re-ingest result",
        f"<p>{'OK' if r.get('ok') else 'FAIL'}</p><pre>{_html.escape(r.get('output', ''))}</pre>")


@app.post("/admin/test", response_class=HTMLResponse)
def admin_test_page():
    import html as _html
    r = admin_api.run_tests()
    return _admin_shell("Tests result",
        f"<p>{'OK' if r.get('ok') else 'FAIL'}</p><pre>{_html.escape(r.get('output', ''))}</pre>")


@app.get("/health")
def health():
    return {"api": "ok", "mongo": _mongo_ok(), "qdrant": _qdrant_ok()}


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    reply_to: str | None = None


@app.post("/chat")
def chat(payload: ChatIn):
    result = handle_message(payload.message, payload.session_id, _store,
                            reply_to=payload.reply_to)
    _log_chat(payload.message, payload.session_id, result, payload.reply_to)
    return result


@app.get("/api/chat/history")
def chat_history(session_id: str):
    """Saved chat for one session, oldest first. This is what makes
    a refresh keep the conversation: the UI restores these rows
    instead of starting from an empty screen. A New chat uses a
    new session_id, so its history starts empty on purpose."""
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        col = client.get_default_database()["chat_logs"]
        docs = list(col.find({"session_id": session_id}).sort("created_at", 1).limit(200))
        return [{"message": d.get("message"), "reply": d.get("reply", ""),
                 "sources": d.get("sources", []),
                 "suggestions": d.get("suggestions", []),
                 "reply_to": d.get("reply_to")} for d in docs]
    except Exception:
        return []


@app.get("/api/admin/kb")
def admin_kb():
    return admin_api.list_kb()


class OkfIn(BaseModel):
    id: str
    title: str
    category: str
    source: str
    body: str


@app.post("/api/admin/okf")
def admin_create_okf(payload: OkfIn):
    return admin_api.create_okf(payload.id, payload.title, payload.category,
                                payload.source, payload.body)


@app.get("/api/admin/kb/{file_id}")
def admin_get_kb(file_id: str):
    return admin_api.get_kb_file(file_id)


class SaveOkfIn(BaseModel):
    body: str


@app.post("/api/admin/okf/{file_id}/save")
def admin_save_okf(file_id: str, payload: SaveOkfIn):
    return admin_api.save_kb_file(file_id, payload.body)


@app.post("/api/admin/okf/{file_id}/approve")
def admin_approve_okf(file_id: str):
    return admin_api.approve_okf(file_id)


class DraftFromLogIn(BaseModel):
    message: str
    reply: str = ""
    sources: list[str] = []


@app.post("/api/admin/draft-from-log")
def admin_draft_from_log(payload: DraftFromLogIn):
    return admin_api.draft_from_chat(payload.message, payload.reply, payload.sources)


@app.post("/api/admin/ingest")
def admin_ingest():
    return admin_api.run_ingest()


@app.post("/api/admin/test")
def admin_test():
    return admin_api.run_tests()


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


@app.get("/api/admin/logs")
def admin_logs():
    """Sessions, not messages: one row per conversation. The old
    version returned one row per message, which made one chat look
    like dozens of separate chats."""
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        col = client.get_default_database()["chat_logs"]
        docs = list(col.find().sort("created_at", -1).limit(500))
        return _group_sessions(docs)[:25]
    except Exception:
        return []


class DraftFromSessionIn(BaseModel):
    session_id: str


@app.post("/api/admin/draft-from-session")
def admin_draft_from_session(payload: DraftFromSessionIn):
    """Automatically draft ONE KB file from a whole session: the
    server pulls the session's chat from Mongo, so the admin does
    not paste or type anything — just Approve after writing the fact."""
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        col = client.get_default_database()["chat_logs"]
        docs = list(col.find({"session_id": payload.session_id}).sort("created_at", 1))
        if not docs:
            return {"ok": False, "error": "no chats found for this session"}
        msgs = [{"message": d.get("message"), "reply": d.get("reply", ""),
                 "sources": d.get("sources", [])} for d in docs]
        return admin_api.draft_from_session(payload.session_id, msgs)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/admin/auto-draft-all")
def admin_auto_draft_all():
    """One draft per session, automatically, skipping sessions
    that already have a draft. The admin then approves each draft
    in the KB list — no per-message work at all."""
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        col = client.get_default_database()["chat_logs"]
        docs = list(col.find().sort("created_at", -1).limit(500))
        sessions = _group_sessions(docs)
        created, skipped = [], []
        for s in sessions:
            r = admin_api.draft_from_session(s["session_id"], s["messages"])
            (created if r.get("ok") else skipped).append(s["session_id"])
        return {"ok": True, "created": created, "skipped_already_drafted": skipped}
    except Exception as e:
        return {"ok": False, "error": str(e)}
