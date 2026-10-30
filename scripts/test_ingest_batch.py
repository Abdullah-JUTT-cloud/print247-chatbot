"""Ingest batching tests — no API key, no network.

Oct 31 failure: ingest sent the whole KB (1,224 chunks, ~334,000
tokens) in ONE OpenAI embeddings call and got BadRequestError 400
(max 300,000 tokens per request), with NOTHING upserted. These
tests prove batch_texts keeps every batch well under that limit
and covers every chunk, in order.

Run from the repo root:  python scripts/test_ingest_batch.py
"""
import glob
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_spec = importlib.util.spec_from_file_location(
    "ingest", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest.py"))
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {info}"))
    assert cond, name


# Real KB chunks, same selection as ingest.py main().
files = sorted(p for p in glob.glob("kb/**/*.md", recursive=True)
               if not p.endswith("/README.md"))
rows = []
for path in files:
    meta, body = ingest.parse_okf(path)
    if ingest.file_status(meta) not in ("verified", "learned"):
        continue
    for i, chunk in enumerate(ingest.chunks_for(body)):
        rows.append((path, chunk))
texts = [c for _, c in rows]
check("real KB loads chunks", len(texts) > 1000, f"got {len(texts)}")
batches = list(ingest.batch_texts(texts))
flat = [t for b in batches for t in b]
check("batching covers every chunk, in order", flat == texts)
check("every batch under 100k estimated tokens",
      all(sum(ingest.estimate_tokens(t) for t in b) <= 100_000 for b in batches),
      f"max batch est = {max(sum(ingest.estimate_tokens(t) for t in b) for b in batches)}")
check("every batch at most 100 texts",
      all(len(b) <= 100 for b in batches))
check("batching actually splits (more than one batch)",
      len(batches) >= 4, f"batches={len(batches)}")
total_est = sum(ingest.estimate_tokens(t) for t in texts)
check("whole KB estimate exceeds the old single-call limit (why it failed)",
      total_est > 300_000, f"est={total_est}")

# A single oversized text is never dropped or split by batching.
big = ["x" * 100_000]
check("single large text stays in exactly one batch",
      list(ingest.batch_texts(big)) == [big])
check("empty input gives no batches",
      list(ingest.batch_texts([])) == [])

print("INGEST-BATCH: all passed")
