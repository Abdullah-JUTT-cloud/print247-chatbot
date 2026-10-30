# print247-chatbot — NEW separate customer chatbot for print247.us

Status: BUILT. Custom sales-chat engine: deterministic quote
collection + RAG over OKF knowledge + LLM answers guarded by code
+ a pre-display relevance check (SRAG). It competes with the old
bot and a colleague's bot; cutover only on an eval win.

## Stack
Python + FastAPI (API) | MongoDB (chats + quote specs) | Qdrant (OKF search)
| OpenAI gpt-5-mini (answers) + gpt-5-nano (small jobs + SRAG check)
| text-embedding-3-small. All in Docker.

## Run it
```bash
cp .env.example .env   # fill in OPENAI_API_KEY only; never commit .env
docker compose up --build
curl http://localhost:8000/health
```
Admin login: set ADMIN_PASSWORD in .env first (no password = admin
closed). Rebuild picks up code changes; knowledge changes need
`docker compose exec api python scripts/ingest.py`.

## What is in here, file by file
- `app/main.py` — FastAPI app: `/` chat UI, `/chat`, `/api/chat/history`
  (open by design: session ids are unguessable UUIDs), `/health`,
  `/admin` (login-guarded sessions + monitoring + learned-facts review).
- `app/chat/brain.py` — the conversation engine: intents, slot
  extraction (code first, nano second, code validates), business
  rules, script order, retrieval, LLM replies, composer validation,
  SRAG pre-display check with clarification loop.
- `app/chat/slots.py` — product/quote detail extraction + size,
  quantity, capacity, gusset parsing.
- `app/chat/script.py` — sales question sequence per product family.
- `app/chat/guards.py` — hard business constraints + handoff rules.
- `app/chat/retrieval.py` — exact-topic + Qdrant vector + keyword
  retrieval. Only `status: verified` or `status: learned` files are
  ever served; drafts and unknown statuses are filtered everywhere.
- `app/chat/llm_extract.py` — nano extraction + plausibility validation.
- `app/chat/composer.py` — LLM reply validation and repair.
- `app/chat/srag.py` — pre-display relevance check + internal-note strip.
- `app/chat/store.py` — MongoDB session state (in-process fallback).
- `app/chat/learn.py` — web-searched answers cached as `kb/learned/*.md`
  (status: learned) + Qdrant, served but listed in /admin for review.
- `app/chat/monitoring.py` — turn flags + summary + learned review queue.
- `app/admin_auth.py` — no-JS admin login (HMAC cookie, 12h).
- `app/chat_ui.py` — the chat UI (unique session id from first load).
- `scripts/ingest.py` — OKF -> Qdrant. One file = one chunk, stable
  point ids, stale-point cleanup. `--dry-run` previews without OpenAI.
- `kb/` — OKF knowledge base (`kb/README.md` is the rulebook). All
  fact files are `status: verified`; learned files live in `kb/learned/`.
- `scripts/test_*.py` + `eval/golden.json` — 657 eval cases + unit
  suites. Run every suite twice before pushing.
- `.env.example` — variable names only, no values. `.env` is gitignored.

## What is NOT in here (on purpose, or planned)
- No old chatbot answers as training data. Old chats are patterns and
  eval material only; the scrubbed dataset stays out of Git.
- No customer emails/phones in the repo.
- No secrets, no tokens, no `.env`.
- No CRM/ERP/email/WhatsApp lead delivery yet — the bot collects the
  quote and contact, then marks it complete for the team. Delivery is
  the next build phase, with a reference number per lead.
- No embed widget yet — the UI is served by FastAPI; a standalone
  widget.js is planned for print247.us.
