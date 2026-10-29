"""OKF -> Qdrant ingest.

How it works (this is the whole RAG 'training' step — there is no
fine-tuning here):
  1. Read every kb/**/*.md file.
  2. Split off the YAML frontmatter (id, title, source, last_reviewed).
  3. One file = one chunk, wherever possible. Splitting a fact across
     chunks is how a bot quotes half a MOQ rule, so we do NOT split
     small files. Only files over ~4000 chars are split on headings.
  4. Embed each chunk with OpenAI, upsert into Qdrant collection
     'print247_kb' with the file path + source as payload, so every
     answer can later say where it came from.

Run:  python scripts/ingest.py [--dry-run]
Dry-run prints what WOULD be indexed, without calling OpenAI/Qdrant.
Re-running is safe: same point id overwrites the old vector, so an
edited OKF file replaces (never duplicates) its old embedding.

Two guards that did not exist before Oct 29, 2026 (found when a
re-ingest put an UNAPPROVED session draft live in Qdrant):
  1. Files whose frontmatter says `status: draft` are NEVER indexed.
     A draft goes live only after the admin writes the verified fact
     and approves it (status: verified).
  2. Points whose source file is gone — deleted, or now a draft —
     are DELETED from Qdrant. Upsert alone never removes anything,
     so without this a deleted draft's point would stay live forever.
"""
import argparse
import glob
import hashlib
import os
import re
import sys

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
COLLECTION = "print247_kb"


def parse_okf(path: str):
    text = open(path, encoding="utf-8").read()
    m = FRONTMATTER.match(text)
    meta, body = (m.group(1), m.group(2)) if m else ("", text)
    return meta.strip(), body.strip()


def file_status(meta: str) -> str:
    m = re.search(r"(?m)^status:\s*(\S+)\s*$", meta or "")
    return m.group(1).lower() if m else ""


def chunks_for(body: str):
    if len(body) <= 4000:
        return [body]
    # Large file only: split on level-2 headings, keep each section whole.
    parts = re.split(r"(?m)^## ", body)
    return [("## " + p).strip() for p in parts if p.strip()]


def point_id(source: str, index: int) -> str:
    # Stable id: editing a file re-embeds over the same point, no duplicates.
    return hashlib.md5(f"{source}#{index}".encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # kb/README.md is the rulebook, not a fact — never index it.
    # Draft files are never indexed either: a session draft goes
    # live only after the admin writes the fact and approves it.
    all_files = sorted(p for p in glob.glob("kb/**/*.md", recursive=True)
                       if not p.endswith("/README.md"))
    files, skipped = [], []
    for path in all_files:
        meta, _body = parse_okf(path)
        if file_status(meta) == "draft":
            skipped.append(path)
        else:
            files.append(path)
    if not files:
        print("No kb/**/*.md files found. Run from the repo root.")
        return 1

    rows = []
    for path in files:
        meta, body = parse_okf(path)
        for i, chunk in enumerate(chunks_for(body)):
            rows.append((point_id(path, i), path, meta, chunk))
    print(f"{len(files)} OKF files -> {len(rows)} chunks")
    for path in skipped:
        print(f"  SKIP draft (not approved): {path}")
    for pid, path, meta, chunk in rows:
        print(f"  {path} [{pid[:8]}] {len(chunk)} chars")

    if args.dry_run:
        print("Dry-run: nothing sent to OpenAI or Qdrant.")
        return 0

    # Live path only (needs OPENAI_API_KEY + QDRANT_URL in .env).
    from dotenv import load_dotenv
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    load_dotenv()
    client = OpenAI()
    qdrant = QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    dim = 1536  # text-embedding-3-small default; change only with the model.
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(COLLECTION, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

    texts = [c for _, _, _, c in rows]
    embeddings = [e.embedding for e in
                  client.embeddings.create(input=texts, model=model).data]
    qdrant.upsert(COLLECTION, [PointStruct(id=pid, vector=vec, payload={"source": path, "meta": meta, "text": chunk})
                               for (pid, path, meta, chunk), vec in zip(rows, embeddings)])
    print(f"Upserted {len(rows)} points into {COLLECTION}.")

    # Stale-point cleanup: upsert never deletes, so a removed file
    # or a file turned back into a draft would otherwise stay live.
    live_sources = {path for _, path, _, _ in rows}
    stale_ids, offset = [], None
    while True:
        points, offset = qdrant.scroll(COLLECTION, limit=100, offset=offset,
                                       with_payload=["source"], with_vectors=False)
        for pt in points:
            if (pt.payload or {}).get("source") not in live_sources:
                stale_ids.append(pt.id)
        if offset is None:
            break
    if stale_ids:
        qdrant.delete(COLLECTION, points_selector=stale_ids)
        print(f"Deleted {len(stale_ids)} stale points (source file gone or now a draft).")
    else:
        print("No stale points.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
