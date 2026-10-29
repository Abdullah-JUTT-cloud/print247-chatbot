"""Live web search for the chat path (Oct 29, philosophy: BOTH).

The bot uses its own packaging knowledge first, and searches the
internet live when the KB has nothing on a domain question — it
never answers "not in our data" for something in the company's
business. Uses the company OpenAI key (no cost constraint) via
the Responses API web-search tool; SEARCH_MODEL defaults to
gpt-4o-mini (known web-search support) and can be overridden by
env. Returns None on ANY failure (no key, old client without the
Responses API, API error) so the caller always falls back
gracefully. This module never crashes chat and never imports at
module level anything that needs a key.
"""

import os


def web_search(query: str) -> dict | None:
    """Search the web for `query`. Returns {"answer": str, "urls":
    [{"title": str, "url": str}]} or None when nothing usable came
    back. The answer is the model's searched summary; urls are the
    citations it attached to it."""
    if not (query or "").strip():
        return None
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        resp = OpenAI().responses.create(
            model=os.environ.get("SEARCH_MODEL", "gpt-4o-mini"),
            tools=[{"type": "web_search"}],
            input=(f"Search the web for: {query.strip()}. Summarise the "
                   "most relevant facts in 2-4 short sentences."),
        )
        answer, urls = "", []
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", "") != "message":
                continue
            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", "") != "output_text":
                    continue
                answer += getattr(part, "text", "") or ""
                for ann in getattr(part, "annotations", []) or []:
                    if getattr(ann, "type", "") == "url_citation":
                        urls.append({"title": getattr(ann, "title", "") or "",
                                     "url": getattr(ann, "url", "") or ""})
        answer = answer.strip()
        if not answer:
            return None
        seen, uniq = set(), []
        for u in urls:
            if u["url"] and u["url"] not in seen:
                seen.add(u["url"])
                uniq.append(u)
        return {"answer": answer, "urls": uniq}
    except Exception:
        return None
