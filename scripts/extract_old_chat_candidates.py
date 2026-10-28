"""Extract approval-gated candidates from old chats — NOT training.

What this does (the safe reuse path, see
workspace/print247-chatbot-study/old-chats-analysis.md):
  1. Read the old JSON chats (zoho_raw.json, local study copy).
  2. Keep only engaged chats (at least one visitor message).
  3. Keep only AI answers that contain a phrase already in the
     current KB (MOQ 1000, turnaround 12-15, free shipping,
     samples 3-4 days). Everything else is discarded, with a reason.
  4. Scrub PII from every kept text: emails, phone-like numbers,
     URLs, and long digit runs are replaced before anything is
     written out. No name, email, phone, chat ID or rep identity
     ever reaches the output file.
  5. Deduplicate by normalised visitor question and write a
     CANDIDATES file, one per question, marked status: pending.

What this does NOT do: it does not ingest anything into Qdrant,
does not fine-tune anything, and does not approve anything. A
candidate becomes a golden test or an OKF file only after a human
approves it in Git. Run:

  python scripts/extract_old_chat_candidates.py <zoho_raw.json> <out.md>
"""
import ast
import json
import re
import sys
from collections import Counter

KB_PHRASES = {
    "1000": "kb/facts/moq.md",
    "12-15": "kb/facts/turnaround.md",
    "12 to 15": "kb/facts/turnaround.md",
    "free shipping": "kb/policies/shipping.md",
    "3-4 business days": "kb/facts/samples.md",
    "3 to 4 business days": "kb/facts/samples.md",
}


def parse_messages(chat):
    m = chat.get("messages")
    if isinstance(m, list):
        return [x for x in m if isinstance(x, dict)]
    if isinstance(m, str):
        try:
            v = ast.literal_eval(m)
            return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
        except Exception:
            return []
    return []


def scrub(text: str) -> str:
    text = re.sub(r"\S+@\S+", "[email]", text)
    text = re.sub(r"https?://\S+", "[link]", text)
    text = re.sub(r"\b\d{7,}\b", "[phone]", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/extract_old_chat_candidates.py <zoho_raw.json> <out.md>")
        return 1
    chats = json.load(open(sys.argv[1], encoding="utf-8"))
    candidates = {}
    discarded = Counter()
    for chat in chats:
        msgs = parse_messages(chat)
        visitors = [m for m in msgs if m.get("author") == "visitor"]
        ais = [m for m in msgs if m.get("author") == "ai"]
        if not visitors or not ais:
            discarded["no_visitor_or_no_ai"] += 1
            continue
        question = scrub(visitors[0].get("text", "")).lower()
        if not question or "[email]" in question or "[phone]" in question:
            discarded["question_has_pii_or_empty"] += 1
            continue
        key = question[:120]
        for ai in ais:
            text = ai.get("text", "") or ""
            low = text.lower()
            if "$" in text:
                discarded["ai_answer_has_price"] += 1
                continue
            if "houston" in low or "24/7" in low:
                discarded["ai_answer_risky_token"] += 1
                continue
            source = next((s for p, s in KB_PHRASES.items() if p in low), None)
            if not source:
                discarded["ai_answer_not_kb_consistent"] += 1
                continue
            candidates.setdefault(key, {"question": key, "kb_source": source, "count": 0})
            candidates[key]["count"] += 1
            break

    out = ["# Old-chat candidates — PENDING human approval",
           "",
           "Every entry below is a real visitor question whose old AI "
           "answer matched a current KB phrase. Nothing here is approved, "
           "ingested, or used by the bot until a human approves it.",
           "",
           f"Total chats read: {len(chats)}",
           f"Candidates (distinct questions): {len(candidates)}",
           f"Discarded: {dict(discarded)}",
           ""]
    for c in sorted(candidates.values(), key=lambda x: -x["count"]):
        out.append(f"- [{c['count']}x] Q: {c['question']}")
        out.append(f"  KB source: {c['kb_source']} | status: pending")
    open(sys.argv[2], "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"{len(candidates)} candidates -> {sys.argv[2]}")
    print(f"Discarded: {dict(discarded)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
