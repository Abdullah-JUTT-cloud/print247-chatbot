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
  1. ONLY files whose frontmatter says `status: verified` or
     `status: learned` are indexed (Oct 30 audit allowlist). Drafts
     — and files with no recognised status — are NEVER indexed.
     A draft goes live only after the admin writes the verified fact
     and approves it (status: verified).
  2. Points whose source file is gone — deleted, or now a draft —
     are DELETED from Qdrant. Upsert alone never removes anything,
     so without this a deleted draft's point would stay live forever.
  3. Embeddings go in batches (Oct 31 fix): the whole KB in one
     call is ~334k tokens, over OpenAI's 300k-per-request limit,
     and fails with nothing upserted. Batches stay under ~100k
     estimated tokens, and each batch is upserted as it goes.
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
    chunks = [("## " + p).strip() for p in parts if p.strip()]
    # Dedupe pass (Oct 30): a "Not stated on page" footer chunk
    # (89 chars: price / MOQ / turnaround not stated) repeats
    # verbatim in 50+ articles. It states no fact, only absences,
    # and as a Qdrant point it is a duplicate embedding that can
    # fill a top-k slot. Skip footer-only chunks at ingest; the
    # file's real sections still index, and absence is already
    # the bot's default (team-confirm) when no fact is found.
    return [c for c in chunks
            if not (c.startswith("## Not stated on page") and len(c) < 200)]


def point_id(source: str, index: int) -> str:
    # Stable id: editing a file re-embeds over the same point, no duplicates.
    return hashlib.md5(f"{source}#{index}".encode()).hexdigest()


def estimate_tokens(text: str) -> int:
    """Rough token estimate, deliberately pessimistic: ~3 chars per
    token for English/markdown (real ratio is closer to 4). Used only
    to size batches, never for billing or limits."""
    return len(text) // 3 + 20


def batch_texts(texts: list, max_tokens: int = 100_000, max_texts: int = 100):
    """Split texts into batches that stay well under OpenAI's
    300,000-token-per-request limit. A single call with the whole KB
    (1,224 chunks, ~334,000 tokens) fails with BadRequestError 400,
    and nothing is upserted at all — that was the Oct 31 ingest
    failure. Batches are capped at 100,000 estimated tokens AND
    100 texts, so even if the estimate is 2-3x low, a batch stays
    under the limit. Order is preserved, so batch embeddings line
    up with batch rows."""
    batch, batch_tokens = [], 0
    for text in texts:
        est = estimate_tokens(text)
        if batch and (batch_tokens + est > max_tokens or len(batch) >= max_texts):
            yield batch
            batch, batch_tokens = [], 0
        batch.append(text)
        batch_tokens += est
    if batch:
        yield batch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # kb/README.md is the rulebook, not a fact — never index it.
    # Allowlist (Oct 30 audit): only verified or learned files are
    # indexed. A draft goes live only after approval flips its
    # status to verified — never by landing in kb/ unreviewed.
    all_files = sorted(p for p in glob.glob("kb/**/*.md", recursive=True)
                       if not p.endswith("/README.md"))
    files, skipped = [], []
    for path in all_files:
        meta, _body = parse_okf(path)
        if file_status(meta) not in ("verified", "learned"):
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

    # Batched embeddings + batched upserts (Oct 31 fix): one call
    # for the whole KB exceeds OpenAI's 300k-token request limit
    # (334k tokens) and upserts NOTHING. Batches upsert as they go,
    # so a failure mid-run leaves earlier batches saved, and a
    # re-run is idempotent (same point ids overwrite).
    total = 0
    offset = 0
    batches = list(batch_texts([c for _, _, _, c in rows]))
    for bi, batch in enumerate(batches, 1):
        batch_rows = rows[offset:offset + len(batch)]
        offset += len(batch)
        print(f"Embedding batch {bi}/{len(batches)} "
              f"({len(batch)} texts, ~{sum(estimate_tokens(t) for t in batch)} tokens est)")
        embeddings = [e.embedding for e in
                      client.embeddings.create(input=batch, model=model).data]
        assert len(embeddings) == len(batch_rows), \
            f"embedding count {len(embeddings)} != batch size {len(batch_rows)}"
        qdrant.upsert(COLLECTION, [PointStruct(id=pid, vector=vec, payload={"source": path, "meta": meta, "text": chunk})
                                   for (pid, path, meta, chunk), vec in zip(batch_rows, embeddings)])
        total += len(batch_rows)
        print(f"  Upserted batch {bi}/{len(batches)} ({total}/{len(rows)} points so far).")
    print(f"Upserted {total} points into {COLLECTION}.")

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
