# OKF knowledge base — READ THIS FIRST

One concept = one file. A file has YAML frontmatter on top (id, title,
category, source, status, last_reviewed) and plain facts below.

Rules:
- A fact without a source is not a fact — it does not go in here.
- `status: draft` files (like the two examples below) are EXAMPLES ONLY.
  They become canonical only after sales signs them off and the status
  flips to `verified` with a date.
- Never invent a price, policy, certification name, or delivery date.
  If it is not in a verified file, the bot must hand off, not guess.
- Editing a file + re-running `python scripts/ingest.py` is the whole
  "retraining" step. There is no model fine-tuning in this project.
