"""Learned-facts cache (Oct 29): a web-searched answer is SAVED so
the next visitor never waits for a search again.

FILE FIRST, Qdrant second. The learned fact is written as a KB
file (kb/learned/<slug>.md, status: learned, with the query, date
and source URLs in frontmatter), and only then is its point
upserted into Qdrant. File-first matters because the fixed
ingest DELETES points whose source file is gone — a Qdrant-only
point would be wiped by the next re-ingest. If the file write
fails, nothing is upserted (no orphan point). If Qdrant is
unreachable, the file still exists, so the next re-ingest indexes
it (eventual consistency); the function still returns True
because the fact is durably saved.

The point scheme mirrors scripts/ingest.py exactly: collection
print247_kb, id = md5(f"{source}#0"), payload {source, meta,
text}, one chunk (learned answers stay short). A later re-ingest
therefore re-embeds OVER the same point, never duplicates it.
"""

import hashlib
import os
import re
from datetime import date

COLLECTION = "print247_kb"


def slug_for(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (query or "").lower()).strip("-")
    return slug[:80] or "learned"


def learned_path(query: str, kb_dir: str = "kb") -> str:
    return os.path.join(kb_dir, "learned", slug_for(query) + ".md")


def learned_source(query: str, kb_dir: str = "kb") -> str:
    """The source string ingest.py will see for this file (relative
    path from the repo root when kb_dir is the default "kb")."""
    return learned_path(query, kb_dir).replace(os.sep, "/")


def save_learned(query: str, answer: str, urls, kb_dir: str = "kb") -> bool:
    """Save a searched answer as a learned KB fact. Returns True
    when the file was written, False otherwise."""
    if not (query or "").strip() or not (answer or "").strip():
        return False
    path = learned_path(query, kb_dir)
    source = learned_source(query, kb_dir)
    meta = (f"id: learned-{slug_for(query)}\n"
            f"title: Learned: {query.strip()}\n"
            f"category: learned\n"
            f"source: {', '.join(u.get('url', '') for u in (urls or []) if u.get('url')) or 'web-search'}\n"
            f"status: learned\n"
            f"learned_from: {query.strip()}\n"
            f"learned_on: {date.today().isoformat()}")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"---\n{meta}\n---\n\n{answer.strip()}\n")
    except OSError:
        return False
    try:
        _upsert_point(source, meta, answer.strip())
    except Exception:
        pass  # file exists; next re-ingest indexes it
    return True


def _upsert_point(source: str, meta: str, text: str) -> None:
    """Mirror of scripts/ingest.py's single-chunk upsert. Raises
    (caught by the caller) when no key or Qdrant is unreachable."""
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct
    if not os.environ.get("OPENAI_API_KEY"):
        return
    vec = OpenAI().embeddings.create(
        model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        input=text).data[0].embedding
    pid = hashlib.md5(f"{source}#0".encode()).hexdigest()
    QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333")).upsert(
        COLLECTION, [PointStruct(id=pid, vector=vec,
                                 payload={"source": source, "meta": meta, "text": text})])
