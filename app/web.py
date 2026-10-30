"""Chat UI + Admin sessions page — plain HTML, no build step.

Why no framework: the user asked for speed and a working page
now, not a React build pipeline. The chat page is served by
FastAPI itself and talks to POST /chat.

Admin, since Oct 29, 2026 (user's call): sessions ONLY, read-only.
No drafts, no approve flow, no KB editing, no re-ingest button —
improvement happens in code, not by learning from chats. The old
draft/approve code was removed; its history stays in git if it is
ever needed again. Re-ingest runs from the terminal:
docker compose exec api python scripts/ingest.py

SECURITY NOTE: since Oct 30, 2026 /admin IS behind a login
(ADMIN_USER + ADMIN_PASSWORD from .env; no password set = admin
closed, never open). It is still read-only: no drafts, no
approve flow, no KB editing. /api/chat/history stays open on
purpose — the visitor chat UI needs it to restore a conversation
on refresh, and session ids are client-side randomUUIDs.
"""

from .chat_ui import CHAT_HTML

ADMIN_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Print247 Admin — Chats</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:30px auto;padding:0 16px;background:#0a0a0a;color:#e5e7eb}
h1,h2{color:#f9fafb}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #374151;padding:8px;text-align:left;vertical-align:top}
th{background:#1f2937}
a{color:#fb923c}
.help{color:#9ca3af;font-size:14px}.warn{color:#fbbf24}h2{margin-top:32px}
code{background:#1f2937;padding:2px 6px;border-radius:6px}</style></head>
<body><h1>Print247 Admin — Chats</h1><p id="serverstatus" class="help">Server check ho raha hai…</p>
<p class="help">Sirf chats dekh sakte ho — har row ek poori conversation hai.
Yahan se koi draft, approve, KB edit ya re-ingest nahi hota;
improvement code se hoti hai. Re-ingest ke liye terminal me
<code>docker compose exec api python scripts/ingest.py</code> chalao.</p>

<div id="monitoring">{{MONITORING}}</div>
<div id="learned">{{LEARNED}}</div>
<p><a href="/admin/logout">Logout</a></p>
<h2>Chats — har session ek hi chat hai</h2>
<p class="help">Har row poori baat-cheet hai, har message alag row nahi.
<b>Chat dekho</b> par poori conversation khulti hai.</p>
<div id="sessions">{{SESSION_ROWS}}</div>
</body></html>"""
