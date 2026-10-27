"""Print247 new chatbot API — SETUP SKELETON (no chat brain yet).

Endpoints:
  GET  /health  -> proves API + Mongo + Qdrant are reachable.
  POST /chat    -> placeholder only. It does NOT answer yet; the chat
                   engine (slots + guards + RAG) is the next build step.
                   Returning a fake answer here would be worse than none.
"""
import os

from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from qdrant_client import QdrantClient

app = FastAPI(title="print247-chatbot")


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


@app.post("/chat")
def chat(payload: ChatIn):
    # Placeholder on purpose: the next step wires language detect, slot
    # extraction, code guards, RAG retrieval, and the main model here.
    return {
        "reply": "Setup theek hai, lekin chat brain abhi nahi bana. Agla step: KB freeze + chat engine.",
        "received": payload.message,
    }
