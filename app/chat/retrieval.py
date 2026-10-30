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
import json
import os
import re

_EXACT_TOPICS = {
    # Order matters: specific topics first. "How long do samples
    # take?" contains "how long", so samples must be checked BEFORE
    # the generic turnaround keys, or it always loses to turnaround.
    # Product topics BEFORE overview: "what finishes do you offer?"
    # must hit finishes.md, not the general overview. Overview keys
    # are general phrases only, so a specific product still wins.
    # Campaign-specific topics FIRST: a generic "pouches" or "boxes"
    # question must not land on a campaign file just because its
    # name contains the word, and a specific mylar/jerky/box question
    # must land on its campaign file, not the general one.
    # Bottle/wine/spirit labels BEFORE the generic labels topic:
    # "whiskey bottle labels" used to fall through to the generic
    # labels file, which contains no wine/whiskey/beverage word at
    # all, so the bot dumped a generic list instead of answering yes.
    "labels-bottle": ["wine label", "wine labels", "whiskey", "whisky",
                      "spirit label", "spirit bottle", "beverage label",
                      "beverage labels", "bottle label", "bottle labels",
                      # Use phrasings, never bare "bottle": "boxes for
                      # bottles" is a BOX question and must still
                      # reach boxes.md, while "labels which stick to
                      # bottles" is a bottle-label question (Oct 30
                      # transcript: the generic labels list answered
                      # it because no key matched "stick to bottles").
                      "labels for bottle", "label for bottle",
                      "stick to bottle", "stick on bottle"],
    "pouches-mylar-sizes": ["mylar size", "mylar sizes", "mylar pouch size",
                            "mylar pouch sizes"],
    "beef-jerky-bags": ["beef jerky", "jerky bag", "jerky bags"],
    "boxes-campaign-materials": ["box material", "box materials", "box board"],
    "pouches-mylar-styles": ["mylar style", "mylar styles", "mylar pouch style"],
    "pouches-mylar-materials-finishes": ["mylar finish", "mylar finishes",
                                         "mylar material", "mylar materials"],
    "pouches-mylar-filling-use": ["seal a mylar", "seal mylar", "heat-seal",
                                  "heat seal", "oxygen absorber"],
    "boxes-campaign-styles": ["box styles", "types of boxes", "box style"],
    "sku": ["sku", "skus", "stock keeping unit"],
    "finishes": ["finish", "finishes", "lamination"],
    "pouches": ["pouch", "pouches", "mylar"],
    "boxes": ["box", "boxes", "carton"],
    "labels": ["label", "labels", "sticker"],
    "banners": ["banner", "banners"],
    "business-cards": ["business card", "business cards"],
    "print-products": ["flyer", "brochure", "postcard"],
    # "What do you offer" in general maps to the overview file, not
    # to a single category — a general question answered with one
    # category only was the bug in the first UI demo.
    "overview": ["what things", "what do you offer", "what do you sell",
                 "what products do you"],
    "moq": ["minimum", "moq", "minimum order", "minimum quantity"],
    "samples": ["sample"],
    "turnaround": ["turnaround", "how long", "delivery time", "lead time", "24 hours", "24 hour"],
    # payments BEFORE shipping (Oct 30 COD fix): "can i pay on
    # delivery" matches both ("pay" and "delivery"), and the
    # payment question must win — shipping.md has no payment
    # answer, so the old order sent COD questions to shipping,
    # SRAG failed twice, and the visitor got a bare team-confirm.
    # Shipping questions carry no pay-word, so this move cannot
    # steal them.
    "payments": ["payment", "pay", "visa", "paypal", "ach", "zelle",
                 "cash on delivery", "pay on delivery", "w:cod"],
    "shipping": ["shipping", "ship", "deliver", "delivery"],
    "refund": ["refund", "return", "cancel"],
    "privacy": ["privacy", "personal data"],
    "terms": ["terms and conditions", "terms"],
    "support-hours": ["support hours", "office hours", "open", "working hours", "24/7", "24-7"],
    "artwork": ["artwork", "file format", "bleed"],
    "proof-approval": ["proof", "approve", "approval"],
    "quote-flow": ["quote", "get a quote"],
    "contact": ["contact", "address", "phone", "location", "located",
                "where are you", "based in", "headquarter", "office"],
    "pricing-approach": ["price", "cost", "pricing"],
}

_COLLECTION = "print247_kb"


# Keyword retrieval used to re-read every KB file on every turn
# (40+ files per retrieve() call, and a turn can retrieve more
# than once). Cache keyed by (path, mtime): KB edits still go
# live without re-ingest — a changed mtime invalidates that file
# — but unchanged files are not re-read. Callers slice text into
# new dicts, so cached rows are never mutated.
_KB_CACHE: dict = {"sig": None, "rows": []}


def allowed_kb_status(status: str) -> bool:
    """Knowledge governance (Oct 30 audit): only reviewed or
    learned facts are retrievable. Drafts — and files with no
    recognised status — are never served, from any path. Learned
    facts stay retrievable by design (the web-search cache); the
    admin page lists them for human review."""
    return (status or "").strip().lower() in ("verified", "learned")


def _frontmatter_status(text: str) -> str:
    """Status value from the OKF frontmatter block, or ''."""
    head = text or ""
    if head.startswith("---"):
        end = head.find("\n---", 3)
        head = head[:end] if end != -1 else head[:800]
    else:
        head = head[:800]
    m = re.search(r"(?m)^status:\s*(\S+)\s*$", head)
    return m.group(1).lower() if m else ""


def _read_kb_files() -> list[dict]:
    paths = [p for p in sorted(glob.glob("kb/**/*.md", recursive=True))
             if not p.endswith("/README.md")]
    try:
        sig = tuple((p, os.path.getmtime(p)) for p in paths)
    except OSError:
        sig = None
    if sig is not None and sig == _KB_CACHE["sig"]:
        return _KB_CACHE["rows"]
    rows = []
    for path in paths:
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        if not allowed_kb_status(_frontmatter_status(text)):
            continue
        rows.append({"source": path, "text": text})
    if sig is not None:
        _KB_CACHE["sig"] = sig
        _KB_CACHE["rows"] = rows
    return rows


_SUPPLEMENTARY_PREFIXES = ("catalog-", "know-", "site-")


def is_supplementary_source(source: str) -> bool:
    """True for kb_v2 supplementary files (Oct 30, 2026): every one
    of them is named catalog-*, know-* or site-*. The original 39
    curated OKF files, and learned files, use other names, so they
    are never supplementary by this rule."""
    name = (source or "").split("/")[-1]
    return name.startswith(_SUPPLEMENTARY_PREFIXES)


def curated_first(hits: list[dict]) -> list[dict]:
    """Stable partition: curated hits first (original order kept
    inside each group), supplementary hits after. With 469 extra
    files in the tree, raw score alone lets a long encyclopaedia
    article outrank the short curated file that actually answers
    the question — that broke golden 162->142 on the first all-469
    load. Curated files are the authority; supplementary files
    fill the gaps curated files do not cover."""
    return [h for h in hits if not is_supplementary_source(h["source"])] + \
        [h for h in hits if is_supplementary_source(h["source"])]


def _keyword_search(text: str, rows: list[dict]) -> list[dict]:
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3]
    scored = []
    for row in rows:
        body = row["text"].lower()
        score = sum(body.count(w) for w in set(words))
        if score:
            scored.append((score, row))
    # Curated first, then by score inside each group. When at least
    # three curated files score, the top 3 are exactly the old
    # top 3; when none score, supplementary files answer the
    # question (envelopes, SBS, spot UV — the gaps kb_v2 fills).
    scored.sort(key=lambda x: (1 if is_supplementary_source(x[1]["source"]) else 0, -x[0]))
    return [{"source": r["source"], "text": r["text"][:1500]} for _, r in scored[:3]]


def _topic_file(rows: list[dict], topic: str) -> list[dict]:
    for row in rows:
        if row["source"].split("/")[-1] == f"{topic}.md":
            return [{"source": row["source"], "text": row["text"][:1500]}]
    for row in rows:
        if topic in row["source"]:
            return [{"source": row["source"], "text": row["text"][:1500]}]
    return []


def _topic_matches(keys: list[str], low: str) -> bool:
    """Exact-topic key match. A key prefixed with "w:" matches on
    word boundaries only — "w:cod" matches "is cod available" but
    NOT "discount code" or "postcode" (bare substring "cod" would)."""
    for k in keys:
        if k.startswith("w:"):
            if re.search(r"\b" + re.escape(k[2:]) + r"\b", low):
                return True
        elif k in low:
            return True
    return False


def _nano_rerank(question: str, a_text: str, b_text: str) -> int:
    """0 = first candidate wins, 1 = second wins. Fail-soft: no key
    or any failure keeps the first (vector) order."""
    if not os.environ.get("OPENAI_API_KEY"):
        return 0
    try:
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=os.environ.get("HELPER_MODEL", "gpt-5-nano"),
            messages=[
                {"role": "system",
                 "content": (
                     "Two knowledge passages may answer a visitor question. Return a JSON "
                     "object {winner: 1 or 2} for the passage that better answers the "
                     "question. Return JSON only.")},
                {"role": "user",
                 "content": f"Question: {question}\n\n[1] {a_text[:800]}\n\n[2] {b_text[:800]}"},
            ],
            timeout=10,
        )
        raw = json.loads(resp.choices[0].message.content.strip())
        return 1 if isinstance(raw, dict) and raw.get("winner") == 2 else 0
    except Exception:
        return 0


def _order_hybrid(question: str, vec_out: list[dict], kw_hits: list[dict],
                  rerank_fn=None) -> list[dict]:
    """Merge vector hits + keyword fills, reranking when the two
    tops disagree (Phase 1, accuracy over speed). rerank_fn(a, b)
    -> 0/1 is injectable for tests; the default is the real nano
    call, which fails soft to vector order. Same file on top:
    no rerank call at all."""
    out = list(vec_out or [])
    seen = {o["source"] for o in out}
    for k in (kw_hits or []):
        if k["source"] not in seen:
            out.append(k)
            seen.add(k["source"])
    if out and kw_hits and kw_hits[0]["source"] != out[0]["source"]:
        fn = rerank_fn or (lambda q, a, b: _nano_rerank(
            q, a.get("text", ""), b.get("text", "")))
        try:
            win = fn(question, out[0], kw_hits[0])
        except Exception:
            win = 0
        if win == 1:
            kw_top = kw_hits[0]
            out = [kw_top] + [o for o in out if o["source"] != kw_top["source"]]
    return out


def retrieve_curated(text: str, top_k: int = 3) -> list[dict]:
    """Retrieval over curated files only. Used by the did-you-mean
    and gibberish gates: those gates ask "does the curated KB have
    any foothold for this fragment?" — a supplementary article
    merely mentioning a word is not a foothold, and with 469 extra
    files retrieval is almost never empty, so the gates silently
    stopped firing (eval fragment cases, Oct 30)."""
    return retrieve(text, top_k=top_k, curated_only=True)


def retrieve(text: str, top_k: int = 3, rerank_fn=None, curated_only: bool = False) -> list[dict]:
    low = (text or "").lower()
    rows = _read_kb_files()
    if curated_only:
        rows = [r for r in rows if not is_supplementary_source(r["source"])]

    # Step 0: time-intent pre-check. A speed/delivery question about
    # a product ("delivery time for boxes", "how quick can labels
    # ship") must reach turnaround.md — the product topics in step 1
    # otherwise win on the product word and _direct_answer can only
    # pick a product sentence (the SBS paperboard bug, Oct 30).
    # Samples first (existing rule: "how long do samples take" is a
    # samples question). Bare "how long" stays out: "how long are
    # your labels" is a dimension question, not a time question.
    for _pre_topic, _pre_keys in (
            ("samples", ("sample",)),
            ("turnaround", ("turnaround", "how quick", "how fast",
                            "how soon", "delivery time", "lead time"))):
        if any(k in low for k in _pre_keys):
            _hit = _topic_file(rows, _pre_topic)
            if _hit:
                return _hit

    # Step 1: exact topic — the file whose name IS the topic wins.
    # Exact basename first, substring second: with campaign files
    # like pouches-mylar-sizes.md in the tree, a plain substring
    # match would return the campaign file for a general "pouches"
    # question (facts/ sorts before products/, and
    # pouches-mylar-campaign-context.md would win over pouches.md).
    for topic, keys in _EXACT_TOPICS.items():
        if _topic_matches(keys, low):
            for row in rows:
                if row["source"].split("/")[-1] == f"{topic}.md":
                    return [{"source": row["source"], "text": row["text"][:1500]}]
            for row in rows:
                if topic in row["source"]:
                    return [{"source": row["source"], "text": row["text"][:1500]}]

    # Step 2: vector search, only if configured (skipped silently in dev).
    # Curated-only mode skips it outright: Qdrant holds supplementary
    # points after a full re-ingest, and the gates must answer from
    # curated files alone.
    if os.environ.get("OPENAI_API_KEY") and not curated_only:
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
                    # Vector points carry their file's frontmatter in
                    # payload["meta"]: same allowlist as the file
                    # path, so a draft point could never be served
                    # even if one were written by mistake.
                    if not allowed_kb_status(_frontmatter_status(p.get("meta", ""))):
                        continue
                    out.append({"source": p.get("source", "qdrant"), "text": p.get("text", "")[:1500]})
                out = _order_hybrid(text, out, _keyword_search(text, rows),
                                    rerank_fn)
                if out:
                    return curated_first(out)[:top_k]
        except Exception:
            pass  # Fall through to keyword search — never fail the chat.

    # Step 3: keyword fallback over OKF files on disk.
    return _keyword_search(text, rows)
