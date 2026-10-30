"""Retrieval priority tests (Oct 30, kb_v2 fix): curated OKF files
outrank supplementary catalog-/know-/site- files, and the
did-you-mean / gibberish gates use curated retrieval only.

Run from the repo root: python3 scripts/test_retrieval_priority.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ".")

from app.chat.retrieval import (
    _dedup_hits, _keyword_search, curated_first, is_supplementary_source,
    retrieve_curated)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name} :: {detail}")


# --- supplementary detection ---
check("catalog- is supplementary",
      is_supplementary_source("kb/products/catalog-coffee-bags.md"))
check("know- is supplementary",
      is_supplementary_source("kb/facts/know-mylar-bags-pouches-what-is-a-stand-up-pouch.md"))
check("site- is supplementary",
      is_supplementary_source("kb/policies/site-privacy-policy.md"))
check("curated pouches is not supplementary",
      not is_supplementary_source("kb/products/pouches.md"))
check("learned files are not supplementary",
      not is_supplementary_source("kb/learned/fact-from-session-1.md"))

# --- keyword ordering: curated wins even with a lower raw score ---
rows = [
    {"source": "kb/products/catalog-coffee-bags.md",
     "text": "coffee coffee coffee coffee coffee foil foil foil"},
    {"source": "kb/products/pouches.md",
     "text": "coffee pouches foil"},
]
hits = _keyword_search("coffee foil", rows)
check("curated first despite lower score",
      hits and hits[0]["source"] == "kb/products/pouches.md", str(hits))

# --- keyword ordering: supplementary still answers when curated scores 0 ---
rows2 = [
    {"source": "kb/products/catalog-envelope.md",
     "text": "envelopes paper envelope mail"},
    {"source": "kb/products/pouches.md",
     "text": "mylar pouches foil"},
]
hits2 = _keyword_search("envelopes", rows2)
check("supplementary answers a curated gap",
      hits2 and hits2[0]["source"] == "kb/products/catalog-envelope.md", str(hits2))

# --- curated_first is a stable partition ---
mixed = [
    {"source": "kb/products/catalog-a.md", "text": "x"},
    {"source": "kb/products/pouches.md", "text": "x"},
    {"source": "kb/facts/site-faq.md", "text": "x"},
    {"source": "kb/facts/moq.md", "text": "x"},
]
ordered = curated_first(mixed)
check("curated_first partitions, order kept inside groups",
      [h["source"] for h in ordered] == [
          "kb/products/pouches.md", "kb/facts/moq.md",
          "kb/products/catalog-a.md", "kb/facts/site-faq.md"],
      str([h["source"] for h in ordered]))

# --- dedup guard (Oct 30 dedupe pass) ---
dup_hits = [
    {"source": "kb/facts/a.md", "text": "## Not stated on page\n- Price.\n- MOQ."},
    {"source": "kb/facts/b.md", "text": "## Not stated on page\n- Price.\n- MOQ."},
    {"source": "kb/facts/c.md", "text": "Real fact about pouches."},
]
check("identical text kept once, first copy wins",
      [h["source"] for h in _dedup_hits(dup_hits)] == ["kb/facts/a.md", "kb/facts/c.md"],
      str([h["source"] for h in _dedup_hits(dup_hits)]))
check("keyword search backfills past a duplicate",
      [h["source"] for h in _keyword_search("price pouch", [
          {"source": "kb/facts/a.md", "text": "price price pouch"},
          {"source": "kb/facts/b.md", "text": "price price pouch"},
          {"source": "kb/facts/c.md", "text": "price pouch sizes"},
          {"source": "kb/facts/d.md", "text": "price pouch boxes"},
      ])] == ["kb/facts/a.md", "kb/facts/c.md", "kb/facts/d.md"])

# --- ingest skips footer-only chunks ---
try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "ingest_mod", os.path.join(os.path.dirname(__file__), "ingest.py"))
    _ing = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_ing)
    _body = ("# Title\n\n" + ("Real section text. " * 300) + "\n\n"
             "## Not stated on page\n- Price.\n- Minimum order quantity.\n"
             "- Turnaround or production days.\n")
    _chunks = _ing.chunks_for(_body)
    check("ingest drops footer-only chunk, keeps real sections",
          all(not c.startswith("## Not stated on page") for c in _chunks)
          and len(_chunks) >= 1, str([len(c) for c in _chunks]))
except Exception as e:  # noqa: BLE001 - test must report, never crash
    check("ingest footer-skip runs", False, repr(e))

# --- retrieve_curated needs the real kb tree; it must not crash
# when run in a repo without the supplementary files, and must
# return curated hits for a known curated question.
try:
    cur = retrieve_curated("what is the minimum order quantity?")
    check("retrieve_curated returns curated moq file",
          any(h["source"].endswith("moq.md") for h in cur), str([h["source"] for h in cur]))
except Exception as e:  # noqa: BLE001 - test must report, never crash
    check("retrieve_curated runs without crashing", False, repr(e))

print(f"RETRIEVAL-PRIORITY: {len(FAILURES)} failed")
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All retrieval-priority cases passed.")
