"""Design-file uploads: validation + disk storage, no web framework
in here so the logic is testable without fastapi (the VM has no
fastapi installed; only Docker does).

Local scope (Oct 30): files live under uploads/<session_id>/ on the
api container's disk. No delivery, no CRM — the existing production
chatbot's connections handle everything downstream when this bot is
plugged in there.
"""

import os
import re
import uuid

# Site artwork formats (AI/PDF/EPS/ZIP) + image formats the vision
# step can describe. Anything else is refused, plainly.
ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp", "pdf", "ai", "eps", "zip"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}
MAX_BYTES = 10 * 1024 * 1024


def validate_upload(filename: str, size: int) -> str | None:
    """Error message, or None when the file is acceptable."""
    name = (filename or "").strip()
    if not name:
        return "No file was attached."
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXTS:
        return ("That file type is not supported — please send a PNG, "
                "JPG, PDF, AI, EPS or ZIP file.")
    if size > MAX_BYTES:
        return "That file is over 10MB — please send a smaller file."
    return None


def safe_filename(filename: str) -> str:
    """Basename, traversal-proof, collision-proof."""
    base = os.path.basename(filename or "design")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "design"
    if len(base) > 80:
        stem, dot, ext = base.rpartition(".")
        base = (stem[:70] + "." + ext) if dot else base[:80]
    return f"{uuid.uuid4().hex[:8]}-{base}"


def save_upload(base_dir: str, session_id: str, filename: str,
                data: bytes) -> str:
    """Write the file, return the stored name (meta keeps the name,
    never a path the visitor could walk)."""
    sid = re.sub(r"[^A-Za-z0-9_-]+", "_", session_id or "web-ui") or "web-ui"
    folder = os.path.join(base_dir, sid)
    os.makedirs(folder, exist_ok=True)
    stored = safe_filename(filename)
    with open(os.path.join(folder, stored), "wb") as fh:
        fh.write(data)
    return stored


def resolve_image(base_dir: str, session_id: str, name: str) -> str | None:
    """Disk path of a stored design IMAGE for the chat to show, or
    None. The name must be exactly a stored basename (the uuid
    prefix save_upload wrote) with an image extension, and the
    resolved path must stay inside its session folder — a
    traversal name ('../x', 'a/b') or a non-image file never
    resolves, so the serve route can never walk the disk."""
    if not name or name != os.path.basename(name):
        return None
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in IMAGE_EXTS:
        return None
    sid = re.sub(r"[^A-Za-z0-9_-]+", "_", session_id or "web-ui") or "web-ui"
    folder = os.path.realpath(os.path.join(base_dir, sid))
    path = os.path.realpath(os.path.join(folder, name))
    if not path.startswith(folder + os.sep):
        return None
    if not os.path.isfile(path):
        return None
    return path
