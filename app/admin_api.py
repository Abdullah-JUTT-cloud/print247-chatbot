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
    """Drafts first: the admin's job is approving drafts, so the
    files waiting for approval sit on top, verified files below."""
    out = []
    for path in sorted(glob.glob("kb/**/*.md", recursive=True)):
        if path.endswith("/README.md"):
            continue
        meta, _ = _read_kb(path)
        out.append({"path": path, "id": meta.get("id", ""),
                    "title": meta.get("title", ""),
                    "status": meta.get("status", "unknown"),
                    "source": meta.get("source", "")})
    out.sort(key=lambda f: (f["status"] != "draft", f["path"]))
    return out


def draft_from_session(session_id: str, messages: list[dict]) -> dict:
    """ONE draft file for ONE whole conversation (session), not
    one file per message. The old per-message rows were the
    confusion: a session is a single chat, so its draft is a
    single file containing the full Q&A, with one combined
    verified-fact placeholder for the admin to write.

    The admin's only job after this: read it, write the fact,
    approve it, re-ingest. Nothing else is asked of them.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (session_id or "chat").lower()).strip("-")[:20] or "chat"
    file_id = f"fact-from-session-{slug}"
    if os.path.exists(f"kb/facts/{file_id}.md"):
        return {"ok": False, "error": f"already drafted for this session: {file_id}"}
    lines = []
    sources: list[str] = []
    for m in messages:
        lines.append(f"Visitor: {m.get('message', '')}")
        lines.append(f"Bot: {m.get('reply', '')}")
        lines.append("")
        for s in m.get("sources", []) or []:
            if s not in sources:
                sources.append(s)
    body = (
        "Full chat (one session, one conversation):\n\n" + "\n".join(lines) +
        f"\nSources the bot used in this chat: {', '.join(sources) or 'none'}\n\n"
        "VERIFIED FACT — admin must write this before approving:\n"
        "- [Write the ONE fact this chat taught us, in your own words, "
        "with its source. Delete this line if there is no new fact. "
        "Do not approve a file that still contains this placeholder.]\n"
    )
    result = create_okf(file_id, f"From chat session: {session_id}", "facts",
                        "chat session (admin to confirm source)", body)
    result["id"] = file_id
    result["next"] = "Read it, write the fact, Approve, Re-ingest."
    return result


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
            # Safety: a draft-from-chat file still holding its
            # placeholder cannot be approved — the admin must write
            # the verified fact first, or it would be trained on.
            if "VERIFIED FACT — admin must write" in body:
                return {"ok": False, "error": "write the verified fact first — this draft still has the placeholder"}
            text = open(path, encoding="utf-8").read()
            text = text.replace("status: draft", "status: verified", 1)
            today = datetime.date.today().isoformat()
            text = re.sub(r"last_reviewed:.*", f"last_reviewed: {today}", text, count=1)
            open(path, "w", encoding="utf-8").write(text)
            return {"ok": True, "path": path, "status": "verified"}
    return {"ok": False, "error": f"no KB file with id {file_id}"}


def _find_kb_path(file_id: str) -> str | None:
    for path in glob.glob("kb/**/*.md", recursive=True):
        meta, _ = _read_kb(path)
        if meta.get("id") == file_id:
            return path
    return None


def get_kb_file(file_id: str) -> dict:
    """Full file content for the admin View panel: read before you
    approve. The bot never sees this endpoint's output, only the
    file after re-ingest."""
    path = _find_kb_path(file_id)
    if not path:
        return {"ok": False, "error": f"no KB file with id {file_id}"}
    meta, body = _read_kb(path)
    return {"ok": True, "path": path, "id": file_id, "title": meta.get("title", ""),
            "status": meta.get("status", ""), "source": meta.get("source", ""),
            "body": body}


def save_kb_file(file_id: str, body: str) -> dict:
    """Save an edited draft. Only the body is edited here, never
    the id/status — approval stays a separate, explicit step."""
    path = _find_kb_path(file_id)
    if not path:
        return {"ok": False, "error": f"no KB file with id {file_id}"}
    text = open(path, encoding="utf-8").read()
    m = _FRONTMATTER.match(text)
    if m:
        text = text[: m.start(2)] + body.strip() + "\n"
    else:
        text = body.strip() + "\n"
    open(path, "w", encoding="utf-8").write(text)
    return {"ok": True, "path": path}


def draft_from_chat(message: str, reply: str = "", sources: list | None = None) -> dict:
    """NEW FEATURE: turn a previous chat into a ready draft OKF file.

    The draft is pre-filled with the visitor's question, what the
    bot replied, and which sources it used — but the verified fact
    itself is left as an explicit placeholder for the admin to
    write. That is the whole point: the admin reads, writes the
    correct fact with its source, verifies it, and only then
    approves. A draft is never trained on: training happens only
    at Re-ingest, after approval.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (message or "").lower()).strip("-")[:40] or "chat"
    file_id = f"fact-from-chat-{slug}"
    base = file_id
    n = 2
    while os.path.exists(f"kb/facts/{file_id}.md"):
        file_id = f"{base}-{n}"
        n += 1
    body = (
        f"Visitor question: {message}\n\n"
        f"Bot reply was: {reply}\n\n"
        f"Sources the bot used: {', '.join(sources or []) or 'none'}\n\n"
        "VERIFIED FACT — admin must write this before approving:\n"
        "- [Write the correct fact here, in your own words, with its source. "
        "Delete this line and the bot reply above if they are not the fact. "
        "Do not approve a file that still contains this placeholder.]\n"
    )
    result = create_okf(file_id, f"From chat: {message[:60]}", "facts",
                        "chat log (admin to confirm source)", body)
    result["id"] = file_id
    result["next"] = "View it, read it, write the verified fact, then Approve, then Re-ingest."
    return result


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
