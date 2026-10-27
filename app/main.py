"""Print247 new chatbot API — chat brain wired in.

Endpoints:
  GET  /health  -> proves API + Mongo + Qdrant are reachable.
  POST /chat    -> the brain: language detect, slot extraction,
                   code guards, RAG retrieval, then a gpt-5-mini
                   answer when OPENAI_API_KEY is set, otherwise a
                   deterministic reply that never invents a fact.

Test without a key:
  curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \\
       -d '{"message": "I need 5000 mylar bags, size 4x6 inches", "session_id": "test1"}'
"""
import os

from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from qdrant_client import QdrantClient

from .chat.brain import handle_message
from .chat.store import get_store

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


@app.get("/health")
def health():
    return {"api": "ok", "mongo": _mongo_ok(), "qdrant": _qdrant_ok()}


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None


@app.post("/chat")
def chat(payload: ChatIn):
    return handle_message(payload.message, payload.session_id, _store)
