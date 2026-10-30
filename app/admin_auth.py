"""Admin login helpers — pure stdlib, no FastAPI import, so the VM
can unit-test them (fastapi lives only in Docker).

Design (Oct 30, user: "admin panel pay login laga do"):
- One admin account from the environment: ADMIN_USER (default
  "admin") + ADMIN_PASSWORD. No password configured = admin is
  CLOSED (fail closed), never open.
- Login is a plain server-rendered HTML form (no JS, like the
  rest of the admin pages) that sets a signed cookie. The cookie
  is HMAC-SHA256 over "username|expiry", keyed by ADMIN_SECRET
  (or the password itself when no separate secret is set — a
  forged cookie then still needs the password).
- Cookie scope is Path=/admin, HttpOnly, SameSite=Lax, 12h.
- /api/chat/history stays open on purpose: the visitor chat UI
  calls it to restore a conversation on refresh, and session ids
  are client-side randomUUIDs (unguessable). The admin LISTING
  (/admin) and transcripts (/admin/session/{id}) are the
  exposure, and those are behind this login.
"""

import base64
import hashlib
import hmac
import os
import time

COOKIE = "admin_session"
TTL_SECONDS = 43200  # 12 hours


def admin_config() -> tuple[str, str | None, str | None]:
    """(username, password, signing secret) from the environment.
    Password None means admin is not configured -> closed."""
    user = os.environ.get("ADMIN_USER", "admin")
    password = os.environ.get("ADMIN_PASSWORD") or None
    secret = os.environ.get("ADMIN_SECRET") or password
    return user, password, secret


def check_credentials(username: str | None, password: str | None,
                      expected_user: str | None,
                      expected_password: str | None) -> bool:
    """Constant-time check. No configured password never passes."""
    if not expected_password:
        return False
    return (hmac.compare_digest(username or "", expected_user or "")
            and hmac.compare_digest(password or "", expected_password))


def make_token(username: str, secret: str | None,
               ttl: int = TTL_SECONDS, now: float | None = None) -> str:
    expiry = int(now if now is not None else time.time()) + ttl
    payload = f"{username}|{expiry}".encode()
    sig = hmac.new((secret or "").encode(), payload,
                   hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload).decode() + "." + sig


def verify_token(token: str | None, secret: str | None) -> str | None:
    """Username when the token is intact and unexpired, else None."""
    try:
        b64, sig = (token or "").rsplit(".", 1)
        payload = base64.urlsafe_b64decode(b64.encode())
        expect = hmac.new((secret or "").encode(), payload,
                          hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        username, expiry = payload.decode().rsplit("|", 1)
        if int(expiry) < time.time():
            return None
        return username
    except Exception:
        return None
