"""RAG retrieval — exact-match first, vector second, never guess.

Order matters, and it is deliberate:
  1. Exact topic match (MOQ, turnaround, shipping...): a fact that
     is asked about directly must come from its own OKF file, not
     from whichever chunk scored highest.
  2. Qdrant vector search over OKF chunks (needs OPENAI_API_KEY and
     a real ingest run, not --dry-run).
  3. Keyword fallback over the kb/*.md files on disk — this is what
     makes the bot usable in local dev before any embedding exists.
  No match at any step -> empty list. The brain then says "confirm
  with the team" instead of inventing an answer.
"""
import glob
import os
import re

_EXACT_TOPICS = {
    "moq": ["minimum", "moq", "minimum order", "minimum quantity"],
    "turnaround": ["turnaround", "how long", "delivery time", "lead time"],
    "shipping": ["shipping", "ship"],
    "samples": ["sample"],
}

_COLLECTION = "print247_kb"


def _read_kb_files() -> list[dict]:
    rows = []
    for path in sorted(glob.glob("kb/**/*.md", recursive=True)):
        if path.endswith("/README.md"):
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        rows.append({"source": path, "text": text})
    return rows


def _keyword_search(text: str, rows: list[dict]) -> list[dict]:
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3]
    scored = []
    for row in rows:
        body = row["text"].lower()
        score = sum(body.count(w) for w in set(words))
        if score:
            scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    return [{"source": r["source"], "text": r["text"][:1500]} for _, r in scored[:3]]


def retrieve(text: str, top_k: int = 3) -> list[dict]:
    low = (text or "").lower()
    rows = _read_kb_files()

    # Step 1: exact topic — the file whose name IS the topic wins.
    for topic, keys in _EXACT_TOPICS.items():
        if any(k in low for k in keys):
            for row in rows:
                if topic in row["source"]:
                    return [{"source": row["source"], "text": row["text"][:1500]}]

    # Step 2: vector search, only if configured (skipped silently in dev).
    if os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            from qdrant_client import QdrantClient

            client = OpenAI()
            qdrant = QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))
            if qdrant.collection_exists(_COLLECTION):
                vec = client.embeddings.create(
                    input=[text],
                    model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
                ).data[0].embedding
                hits = qdrant.search(_COLLECTION, query_vector=vec, limit=top_k)
                out = []
                for h in hits:
                    p = h.payload or {}
                    out.append({"source": p.get("source", "qdrant"), "text": p.get("text", "")[:1500]})
                if out:
                    return out
        except Exception:
            pass  # Fall through to keyword search — never fail the chat.

    # Step 3: keyword fallback over OKF files on disk.
    return _keyword_search(text, rows)
