"""Model-based slot read — the second half of the old bot's
extractor (extractor.ts + contactExtractor.ts model read).

The old extractor reads every message twice: code first, then the
model for what code cannot parse ("the big ones for coffee" is a
size no regex knows). Our wave-1 port only had the code half, so a
message code could not parse left every field missing and the bot
re-asked blindly.

Rules carried over, and tightened for our channel:
- Runs ONLY when code extraction found nothing new and the message
  is not a question, not an intent, not a pleasantry. One nano call
  per such turn, never on every turn.
- Every value the model returns is validated by CODE before it is
  stored (product from the known list, sizes from the dimension
  pattern, quantity from quantity_in, finishes from finish_in,
  skus from the design-count pattern, extras/material/style from
  known words). A guessed value is worse than an empty one, so an
  unvalidated value is dropped, never stored.
- The contact half of the old model read (guessing a name from
  free text) is deliberately NOT ported: a guessed contact is
  worse than an empty one, and our deterministic contact flow
  asks for it instead.
"""
import json
import os
import re

_STYLE_WORDS = [
    ("side gusset", "side gusset"),
    ("pinch bottom", "pinch bottom"),
    ("flat-bottom", "flat-bottom"),
    ("flat bottom", "flat-bottom"),
    ("stand-up", "stand-up"),
    ("stand up", "stand-up"),
    ("standup", "stand-up"),
    ("spout", "spout"),
    ("3-side", "flat"),
    ("flat", "flat"),
]


def _validate(raw: dict) -> dict:
    """Code validation for every model-returned value."""
    from .finishes_norm import finish_in, normalise_finish
    from .quantity_parse import quantity_in
    from .slots import _MATERIALS, _PRODUCTS, _SIZE, _skus_in, _EXTRAS

    out: dict = {}
    product = str(raw.get("product") or "").lower()
    for label, keys in _PRODUCTS:
        if any(k in product for k in keys):
            out["product"] = label
            break
    size = str(raw.get("sizes") or "")
    m = _SIZE.search(size.lower())
    if m:
        out["sizes"] = m.group(0).strip()
    finish = str(raw.get("finishes") or "")
    if finish:
        f = normalise_finish(finish)
        if f and f != "none":
            out["finishes"] = f
        else:
            slip = finish_in(finish.lower())
            if slip:
                out["finishes"] = slip
    qty = raw.get("quantity")
    if qty is not None:
        q = quantity_in(str(qty))
        if q is not None:
            out["quantity"] = str(q)
    skus = str(raw.get("skus") or "")
    s = _skus_in(skus) if skus else None
    if s:
        out["skus"] = s
    elif re.fullmatch(r"\d+", skus.strip()):
        out["skus"] = skus.strip()
    extras = str(raw.get("extras") or "").lower()
    found = [label for label, keys in _EXTRAS if any(k in extras for k in keys)]
    if found:
        out["extras"] = ", ".join(found)
    material = str(raw.get("material") or "").lower()
    for mat in _MATERIALS:
        if re.search(rf"\b{re.escape(mat)}\b", material):
            out["material"] = mat
            break
    style = str(raw.get("style") or "").lower()
    for word, label in _STYLE_WORDS:
        if word in style:
            out["style"] = label
            break
    return out


def llm_extract(message: str, asked: str | None = None,
                product: str | None = None) -> dict:
    """One gpt-5-nano read of a message code could not parse, or {}
    when no key is set, the call fails, or nothing validates.
    `asked` is the bot's question the visitor is answering and
    `product` the current quote's product: without them a bare
    "22" is ambiguous (quantity or designs?); with them the model
    reads it in context. Every value is still validated by code."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key or not (message or "").strip() or len(message) > 500:
        return {}
    _ctx = ""
    if asked:
        _ctx += f" The bot just asked the visitor: '{asked[:200]}'."
    if product:
        _ctx += f" The current quote is for {product}."
    try:
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=os.environ.get("HELPER_MODEL", "gpt-5-nano"),
            messages=[
                {"role": "system",
                 "content": (
                     "Read ONLY the visitor message below. Return a JSON object "
                     "with any of these fields the message literally states: "
                     "product, sizes, finishes, quantity, skus, extras, material, "
                     "style. Omit any field not stated. Never guess, never add "
                     "units or numbers that are not there." + _ctx +
                     " Return JSON only.")},
                {"role": "user", "content": message},
            ],
            timeout=10,
        )
        raw = json.loads(resp.choices[0].message.content.strip())
        return _validate(raw if isinstance(raw, dict) else {})
    except Exception:
        return {}
