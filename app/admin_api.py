"""Admin operations: KB files, approval, ingest, tests, chat logs.

Every operation is deliberately small and reversible:
- Create writes a DRAFT file, never verified. The bot's retrieval
  reads kb files from disk, but the vector index only changes on
  re-ingest, so a draft cannot silently go live.
- Approve flips draft -> verified with today's date. It does NOT
  re-ingest by itself; the admin must press Re-ingest, so approval
  and deployment are two separate, visible steps.
- Logs are read-only here; approving a log entry means writing a
  new OKF file for it, not editing history.
"""
import datetime
import glob
import os
import re
import subprocess
import sys

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")


def _read_kb(path: str) -> tuple[dict, str]:
    text = open(path, encoding="utf-8").read()
    m = _FRONTMATTER.match(text)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta, m.group(2).strip()
    return meta, text


def list_kb() -> list[dict]:
    out = []
    for path in sorted(glob.glob("kb/**/*.md", recursive=True)):
        if path.endswith("/README.md"):
            continue
        meta, _ = _read_kb(path)
        out.append({"path": path, "id": meta.get("id", ""),
                    "title": meta.get("title", ""),
                    "status": meta.get("status", "unknown"),
                    "source": meta.get("source", "")})
    return out


def create_okf(file_id: str, title: str, category: str, source: str, body: str) -> dict:
    if not _SAFE_ID.match(file_id or ""):
        return {"ok": False, "error": "id must be lowercase letters, digits, - or _ only"}
    if category not in ("facts", "products", "materials", "policies"):
        return {"ok": False, "error": "unknown category"}
    path = f"kb/{category}/{file_id}.md"
    if os.path.exists(path):
        return {"ok": False, "error": f"{path} already exists"}
    os.makedirs(f"kb/{category}", exist_ok=True)
    text = (f"---\nid: {file_id}\ntitle: {title}\ncategory: {category}\n"
            f"source: {source}\nstatus: draft\nlast_reviewed: null\n---\n\n{body.strip()}\n")
    open(path, "w", encoding="utf-8").write(text)
    return {"ok": True, "path": path, "status": "draft"}


def approve_okf(file_id: str) -> dict:
    for path in glob.glob("kb/**/*.md", recursive=True):
        meta, body = _read_kb(path)
        if meta.get("id") == file_id:
            if meta.get("status") == "verified":
                return {"ok": True, "path": path, "status": "verified", "note": "already verified"}
            text = open(path, encoding="utf-8").read()
            text = text.replace("status: draft", "status: verified", 1)
            today = datetime.date.today().isoformat()
            text = re.sub(r"last_reviewed:.*", f"last_reviewed: {today}", text, count=1)
            open(path, "w", encoding="utf-8").write(text)
            return {"ok": True, "path": path, "status": "verified"}
    return {"ok": False, "error": f"no KB file with id {file_id}"}


def _run(cmd: list[str]) -> dict:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr)[-3000:]}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def run_ingest() -> dict:
    return _run([sys.executable, "scripts/ingest.py"])


def run_tests() -> dict:
    golden = _run([sys.executable, "scripts/test_golden.py"])
    chat = _run([sys.executable, "scripts/test_chat.py"])
    return {"ok": golden["ok"] and chat["ok"],
            "output": "== GOLDEN ==\n" + golden["output"] + "\n== CHAT ==\n" + chat["output"]}
