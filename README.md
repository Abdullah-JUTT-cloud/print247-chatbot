# print247-chatbot — NEW separate customer chatbot (setup step)

Status: SETUP ONLY. The chat brain (slots + guards + RAG + personas) is
the next build step. This repo currently proves the stack runs.

## Stack
Python + FastAPI (API) | MongoDB (chats + quote specs) | Qdrant (OKF search)
| OpenAI gpt-5-mini (answers) + gpt-5-nano (small jobs). All in Docker.

## Run it
```bash
cp .env.example .env   # fill in OPENAI_API_KEY only; never commit .env
docker compose up --build
curl http://localhost:8000/health
```

## What is in here, file by file
- `docker-compose.yml` — the whole stack: api + mongo + qdrant, with
  named volumes so data survives container restarts.
- `Dockerfile` — API image only (Python 3.12-slim + requirements).
- `app/main.py` — FastAPI app: `/health` checks Mongo + Qdrant;
  `/chat` is a placeholder that says the brain is not built yet.
  It deliberately does NOT fake an answer.
- `scripts/ingest.py` — OKF -> Qdrant. One file = one chunk, stable
  point ids so re-runs overwrite instead of duplicating. `--dry-run`
  shows what would be indexed without calling OpenAI.
- `kb/` — OKF knowledge base. `kb/README.md` is the rulebook;
  `kb/facts/moq.md` and `kb/facts/turnaround.md` are DRAFT examples,
  not verified facts, until sales signs them off.
- `.env.example` — variable names only, no values. `.env` is gitignored.

## What is NOT in here (on purpose)
- No old chatbot answers as training data. Old chats are patterns only.
- No customer emails/phones. The scrubbed dataset stays out of Git.
- No secrets, no tokens, no `.env`.
- No SalesIQ/Zoho coupling yet — the new widget comes with the chat engine.
