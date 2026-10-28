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

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
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


def _log_chat(payload_message: str, session_id: str | None, result: dict) -> None:
    """Fail-soft: a logging failure must never break the chat."""
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        client.get_default_database()["chat_logs"].insert_one({
            "session_id": session_id, "message": payload_message,
            "reply": result.get("reply"), "sources": result.get("sources", []),
            "handoff": result.get("handoff"), "llm_used": result.get("llm_used"),
            "language": result.get("language"),
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        })
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
def chat_ui():
    return CHAT_HTML


@app.get("/admin", response_class=HTMLResponse)
def admin_ui():
    return ADMIN_HTML


@app.get("/health")
def health():
    return {"api": "ok", "mongo": _mongo_ok(), "qdrant": _qdrant_ok()}


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None


@app.post("/chat")
def chat(payload: ChatIn):
    result = handle_message(payload.message, payload.session_id, _store)
    _log_chat(payload.message, payload.session_id, result)
    return result


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


@app.post("/api/admin/okf/{file_id}/approve")
def admin_approve_okf(file_id: str):
    return admin_api.approve_okf(file_id)


@app.post("/api/admin/ingest")
def admin_ingest():
    return admin_api.run_ingest()


@app.post("/api/admin/test")
def admin_test():
    return admin_api.run_tests()


@app.get("/api/admin/logs")
def admin_logs():
    """Latest chats with no sources or with a handoff first — the
    questions the KB does not answer yet. Falls back to latest 25
    chats if Mongo is empty or down."""
    try:
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/print247_chatbot"),
                             serverSelectionTimeoutMS=2000)
        col = client.get_default_database()["chat_logs"]
        docs = list(col.find().sort("created_at", -1).limit(100))
        unanswered = [d for d in docs if not d.get("sources") or d.get("handoff")]
        chosen = unanswered[:25] if unanswered else docs[:25]
        return [{"message": d.get("message"), "sources": d.get("sources", []),
                 "handoff": d.get("handoff")} for d in chosen]
    except Exception:
        return []
