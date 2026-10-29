"""Web-search + learned-cache tests (Oct 29, 2026).

Covers the "both + cache" design: live search when the KB has
nothing, LLM knowledge via the flipped prompt, and the searched
answer SAVED as a learned KB fact (file first, Qdrant second)
so the next visitor gets it fast with no search. Runs WITHOUT
an API key or Qdrant: the search and upsert paths are stubbed
or fail gracefully, and the file cache is exercised in a tmp
dir — never in the real kb/.
"""
import hashlib
import os
import sys
import tempfile
import types
from unittest import mock

sys.path.insert(0, ".")

from app.chat import brain as B
from app.chat.brain import handle_message
from app.chat.learn import learned_path, learned_source, save_learned, _upsert_point
from app.chat.websearch import web_search

PASSES = [0]
FAILURES = []


def check(name, ok, detail=""):
    if ok:
        PASSES[0] += 1
    else:
        FAILURES.append(f"{name} :: {detail}")


# --- learn.py: file cache ---
with tempfile.TemporaryDirectory() as td:
    ok = save_learned("What is corrugated board?",
                      "Corrugated board is fluted paperboard used for shipping boxes.",
                      [{"title": "Corrugated fiberboard",
                        "url": "https://example.com/corrugated"}],
                      kb_dir=td)
    p = learned_path("What is corrugated board?", kb_dir=td)
    body = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    check("learned file written with status learned + source + date",
          ok and os.path.exists(p) and "status: learned" in body
          and "https://example.com/corrugated" in body
          and "learned_from: What is corrugated board?" in body
          and "fluted paperboard" in body,
          f"ok={ok} body={body[:200]!r}")
    check("learned source path is kb-style relative",
          learned_source("What is corrugated board?", kb_dir="kb")
          == "kb/learned/what-is-corrugated-board.md",
          learned_source("What is corrugated board?", kb_dir="kb"))
    check("empty query/answer not saved",
          save_learned("", "x", [], kb_dir=td) is False
          and save_learned("q", "  ", [], kb_dir=td) is False)
    _blocker = os.path.join(td, "blocker")
    open(_blocker, "w").write("not a dir")
    check("unwritable kb dir fails clean, no orphan point",
          save_learned("q2", "a", [], kb_dir=os.path.join(_blocker, "kb")) is False)

# --- learn.py: Qdrant upsert mirrors ingest.py exactly ---
_captured = {}


class _FakeEmb:
    def create(self, model, input):
        assert model == "text-embedding-3-small"
        _c = types.SimpleNamespace(embedding=[0.1, 0.2])
        return types.SimpleNamespace(data=[_c])


class _FakeOpenAI:
    def __init__(self):
        self.embeddings = _FakeEmb()


class _FakeQdrant:
    def __init__(self, url):
        _captured["url"] = url

    def upsert(self, collection, points):
        _captured["collection"] = collection
        _captured["points"] = points


_fake_openai = types.ModuleType("openai")
_fake_openai.OpenAI = _FakeOpenAI
_fake_qdrant = types.ModuleType("qdrant_client")
_fake_qdrant.QdrantClient = _FakeQdrant
_fake_models = types.ModuleType("qdrant_client.models")


class _FakePoint:
    def __init__(self, id, vector, payload):
        self.id, self.vector, self.payload = id, vector, payload


_fake_models.PointStruct = _FakePoint
_fake_qdrant.models = _fake_models
with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
    with mock.patch.dict(sys.modules, {"openai": _fake_openai,
                                       "qdrant_client": _fake_qdrant,
                                       "qdrant_client.models": _fake_models}):
        _upsert_point("kb/learned/what-is-corrugated-board.md",
                      "id: learned-x\nstatus: learned",
                      "Corrugated board is fluted paperboard.")
_src = "kb/learned/what-is-corrugated-board.md"
check("upsert uses ingest collection + md5 point id + payload",
      _captured.get("collection") == "print247_kb"
      and len(_captured.get("points", [])) == 1
      and _captured["points"][0].id == hashlib.md5(f"{_src}#0".encode()).hexdigest()
      and _captured["points"][0].payload["source"] == _src
      and "fluted paperboard" in _captured["points"][0].payload["text"],
      f"captured={str(_captured)[:300]}")

# --- websearch.py: no key / empty query never crashes, returns None ---
with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
    check("web search without a key returns None",
          web_search("corrugated boxes") is None)
check("web search with empty query returns None",
      web_search("   ") is None)

# --- brain wiring: zero KB facts -> search -> compose -> save learned ---
_orig_retrieve = B.retrieve
_orig_search = B.web_search
_orig_llm = B._llm_reply
_orig_save = B.save_learned
_calls = {}


def _fake_retrieve(q):
    return []


def _fake_search(q):
    _calls.setdefault("search", []).append(q)
    return {"answer": "Corrugated board is a fluted paperboard used for shipping boxes.",
            "urls": [{"title": "Corrugated fiberboard",
                      "url": "https://example.com/corrugated"}]}


def _fake_llm(message, language, slots, facts, reply_to=None):
    return facts[0]["text"] if facts else None


def _fake_save(query, answer, urls, kb_dir="kb"):
    _calls.setdefault("saved", []).append((query, answer, urls))
    return True


try:
    B.retrieve = _fake_retrieve
    B.web_search = _fake_search
    B._llm_reply = _fake_llm
    B.save_learned = _fake_save
    r = handle_message("what is corrugated board?", session_id="learn-wire", store=None)
    check("zero-fact question searched, composed, learned, llm_used",
          "fluted paperboard" in r["reply"] and r["llm_used"] is True
          and len(_calls.get("saved", [])) == 1
          and _calls["saved"][0][1].startswith("Corrugated board")
          and r["sources"] == ["https://example.com/corrugated"],
          f"reply={r['reply'][:160]!r} sources={r['sources']} saved={_calls.get('saved')}")
    _calls.clear()
    r = handle_message("what is the price of corrugated boxes?",
                       session_id="learn-noprice", store=None)
    check("price question never triggers a web search",
          "search" not in _calls,
          f"calls={_calls} reply={r['reply'][:120]!r}")
finally:
    B.retrieve = _orig_retrieve
    B.web_search = _orig_search
    B._llm_reply = _orig_llm
    B.save_learned = _orig_save

print(f"LEARN: {PASSES[0]} passed, {len(FAILURES)} failed")
for f in FAILURES:
    print("FAIL " + f)
if FAILURES:
    raise SystemExit(1)
