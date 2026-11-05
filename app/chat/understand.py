"""LLM-first structured turn understanding for Print247 chatbot.

Meaning is decided by the LLM (gpt-5-nano with strict JSON schema output).
Python decides only validation and state transitions.
A labeled DEGRADED fallback is used only when no OPENAI_API_KEY is available
in offline test environments.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from typing import Any

INTENTS: tuple[str, ...] = (
    "answer",
    "dont_know",
    "change_field",
    "cancel",
    "delete",
    "stop",
    "bye",
    "thanks",
    "new_order",
    "ask_field_info",
    "ask_product_info",
    "capability",
    "own_data",
    "greeting",
    "handoff_request",
    "unclear",
)

TARGET_FIELDS: tuple[str, ...] = (
    "",
    "product",
    "email",
    "sizes",
    "type",
    "style",
    "finishes",
    "quantity",
    "skus",
    "extras",
    "material",
    "name",
    "phone",
)

_CACHE: dict[tuple[str, str, str, bool, bool], dict[str, Any]] = {}


def load_env_file(env_path: str | None = None, override: bool = False) -> bool:
    """Load key=value pairs from .env into os.environ using stdlib only."""
    if env_path is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env_path = os.path.join(root, ".env")
    if not os.path.isfile(env_path):
        return False
    loaded = False
    try:
        with open(env_path, encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and (override or k not in os.environ):
                    os.environ[k] = v
                    loaded = True
    except OSError:
        return False
    return loaded


def _api_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip() or None
    # Auto-load .env when invoked interactively or from python -c
    argv0 = os.path.basename(sys.argv[0]) if sys.argv else ""
    if argv0 in ("", "-c"):
        load_env_file()
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            return key.strip() or None
    return None


_JSON_SCHEMA: dict[str, Any] = {
    "name": "turn_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": list(INTENTS),
            },
            "target_field": {
                "type": "string",
                "enum": list(TARGET_FIELDS),
            },
            "new_value": {
                "type": "string",
            },
            "confidence": {
                "type": "number",
            },
        },
        "required": ["intent", "target_field", "new_value", "confidence"],
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = (
    "You classify a visitor's message in a custom packaging and printing quote chat.\n"
    "You are given:\n"
    "- message: the visitor's current turn text\n"
    "- pending_field: the specification field currently being asked (or 'none')\n"
    "- stored_product: the product currently in the quote (or 'none')\n"
    "- slots: specification values collected so far\n"
    "- complete: whether the quote is already completed\n"
    "- recent_history: recent conversation turns\n\n"
    "1. ask_field_info: The visitor asks about the pending field — including asking to see other or alternative options, what choices or varieties exist, definitions of options, why the field is needed, or whether it is required (such as 'can I see other options?', 'what else can I choose from?', 'are there other options available?', asking why an email/phone/name is needed, or whether a field is required). Any inquiry asking to see options or asking about the pending field itself is ask_field_info, NEVER dont_know.\n"
    "2. dont_know: The visitor expresses uncertainty, indecision, hesitation, states they have not chosen yet, "
    "cannot decide, or asks the assistant to suggest, advise, or recommend (such as asking what the assistant recommends, "
    "asking for guidance, needing direction, or requesting input on what works well). "
    "Asking for recommendations, advice, suggestions, or which option to choose is ALWAYS dont_know, NEVER ask_field_info. "
    "Set target_field to pending_field (or the field they mention).\n"
    "3. change_field: The visitor explicitly asks to alter, modify, update, change, revise, or switch a specification field. "
    "Simply stating or providing a value (such as an email address, a dimension, a quantity, or a finish) "
    "is 'answer', NEVER 'change_field'. "
    "Canonical field names: "
    "'sizes' (dimensions), "
    "'quantity' (strictly number of units/boxes/bags/pieces/order run size), "
    "'skus' (number of designs/artworks/variants/designs count — revising designs or artworks is ALWAYS 'skus', NEVER 'quantity'), "
    "'finishes' (matte/gloss/coatings), "
    "'material' (cardboard/kraft/corrugated/paper/stock), "
    "'style' (mailer/tuck-end/stand-up/flat), "
    "'type' (box/pouch type), "
    "'extras' (zipper/notch/add-ons). "
    "Set target_field to one of these canonical field names. Set new_value ONLY if the visitor explicitly states the replacement "
    "value inside the current message (e.g. 'matte', '500', '4x6 inches'); if no replacement value is "
    "stated in the current message, new_value MUST be '' (never copy old values from slots and never write "
    "'undefined' or the whole sentence).\n"
    "4. cancel: The visitor wants to abandon, withdraw, or call off the quote/order, or states they "
    "do not need, do not want, or no longer require the order or quote. "
    "Stating they do not need or no longer want the quote/order is ALWAYS cancel "
    "(only declining a specific feature like extras or phone while that feature is currently pending is answer).\n"
    "5. delete: The visitor asks to erase, wipe, remove, purge, or clear their stored session/data/details.\n"
    "6. stop: The visitor asks the bot to pause or stop asking questions right now.\n"
    "7. bye: The visitor is ending the chat or saying farewell.\n"
    "8. thanks: The visitor is expressing gratitude.\n"
    "9. new_order: The visitor explicitly asks to reset, restart, or start over from the beginning. "
    "Simply stating a product or order requirement is an order specification answering what product is needed, "
    "so it is 'answer', NEVER 'new_order'.\n"
    "10. ask_product_info: The visitor asks a general company, policy, turnaround, shipping, MOQ, or "
    "location question unrelated to listing options for the pending field.\n"
    "11. capability: The visitor asks whether the company can manufacture or print a product or material.\n"
    "12. own_data: The visitor asks what specifications, contact details, or order summary the bot has "
    "recorded for them. (Note: if they state they already said they do not know a field, classify as "
    "dont_know, NEVER own_data.)\n"
    "13. greeting: A pure greeting.\n"
    "14. handoff_request: The visitor asks for a human representative or asks about tracking an existing "
    "past order.\n"
    "15. answer: The visitor is providing a value, option name, choice, preference, confirmation, refusal/decline "
    "of an optional field (such as replying 'none', 'no', 'no need', 'skip', 'neither', 'ok', having no phone number, "
    "or declining extras/add-ons). Declining an optional add-on or saying 'none'/'no' to extras or phone is "
    "ALWAYS 'answer', NEVER 'ask_field_info'. Choosing or naming an option is ALWAYS 'answer', NEVER 'ask_field_info' or 'change_field'.\n"
    "16. unclear: Random keystrokes or unintelligible text that has no discernible meaning.\n"
)


def _call_openai_structured(
    api_key: str,
    user_payload: str,
    timeout: float = 8.0,
) -> dict[str, Any] | None:
    model = os.environ.get("HELPER_MODEL", "gpt-5-nano")
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
    # Try OpenAI Python SDK first if installed
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            reasoning_effort="minimal",
            response_format={"type": "json_schema", "json_schema": _JSON_SCHEMA},
        )
        raw = (resp.choices[0].message.content or "").strip()
        return json.loads(raw)
    except ImportError:
        pass
    except Exception:
        return None

    # Stdlib urllib fallback when the openai pip package is not installed
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "reasoning_effort": "minimal",
            "response_format": {"type": "json_schema", "json_schema": _JSON_SCHEMA},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = (data["choices"][0]["message"]["content"] or "").strip()
        return json.loads(raw)
    except Exception:
        return None


_FIELD_MAP: dict[str, str] = {
    "finish": "finishes",
    "finishes": "finishes",
    "lamination": "finishes",
    "coating": "finishes",
    "size": "sizes",
    "sizes": "sizes",
    "dimension": "sizes",
    "dimensions": "sizes",
    "quantity": "quantity",
    "quantities": "quantity",
    "qty": "quantity",
    "material": "material",
    "materials": "material",
    "stock": "material",
    "style": "style",
    "styles": "style",
    "type": "type",
    "types": "type",
    "design": "skus",
    "designs": "skus",
    "sku": "skus",
    "skus": "skus",
    "artwork": "skus",
    "extra": "extras",
    "extras": "extras",
    "addon": "extras",
    "addons": "extras",
    "add-on": "extras",
    "add-ons": "extras",
    "email": "email",
    "phone": "phone",
    "name": "name",
    "product": "product",
}


def _detect_field_token(tokens: list[str], default_field: str | None) -> str:
    for tok in tokens:
        mapped = _FIELD_MAP.get(tok)
        if mapped:
            return mapped
    return default_field if default_field in TARGET_FIELDS else ""


# DEGRADED NO-KEY FALLBACK (used ONLY when OPENAI_API_KEY is absent in offline tests)
def _degraded_no_key_fallback(
    message: str,
    pending_field: str | None,
    slots: dict[str, Any] | None,
) -> dict[str, Any]:
    text = (message or "").strip()
    low = text.lower()
    from .normalize import is_gibberish
    if is_gibberish(text) and pending_field not in ("name", "email", "phone") and not (slots and slots.get("_awaiting_contact")):
        return {
            "intent": "unclear",
            "target_field": "",
            "new_value": "",
            "confidence": 0.9,
            "degraded": True,
        }
    tokens = re.findall(r"[a-z0-9']+", low)
    stems5 = {t[:5] for t in tokens}
    token_set = set(tokens)
    target = _detect_field_token(tokens, pending_field)

    # 1. Delete (data/record removal stems)
    if stems5 & {"delet", "erase", "purge", "scrub", "wipe"} or (
        {"remove", "clear", "forget"} & token_set
        and bool(stems5 & {"save", "saved", "data", "detai", "info", "quote", "recor", "sessi", "histo"})
    ):
        return {
            "intent": "delete",
            "target_field": "",
            "new_value": "",
            "confidence": 0.7,
            "degraded": True,
        }

    # 2. Cancel (order abandonment stems)
    has_cancel_stem = bool(stems5 & {"cance", "scrap", "aband", "withd"})
    neg_need = bool(
        re.search(r"\b(?:do\s*not|don'?t|no\s+longer|not)\s+(?:need|want|require|proceed|interested)\b", low)
        and (token_set & {"it", "this", "order", "quote", "anymore", "proceed", "ordering"} or len(tokens) <= 5)
        and pending_field not in ("extras", "finishes", "material", "style", "phone", "email")
    )
    changed_mind = ("mind" in token_set and bool(stems5 & {"chang"})) or (
        "call" in token_set and "off" in token_set
    ) or ("drop" in token_set and bool(token_set & {"request", "order", "quote", "this"}))
    if has_cancel_stem or neg_need or changed_mind:
        return {
            "intent": "cancel",
            "target_field": "",
            "new_value": "",
            "confidence": 0.7,
            "degraded": True,
        }

    # 3. Change field
    if (
        stems5 & {"chang", "chnag", "chnge", "chg", "modif", "updat", "revis"}
        or ("switch" in token_set and bool(token_set & set(_FIELD_MAP)))
    ) and any(t in _FIELD_MAP for t in tokens) and "?" not in text:
        new_val = ""
        m_to = re.search(r"\bto\s+([a-z0-9x×.*+\s-]+)$", low)
        if m_to:
            new_val = m_to.group(1).strip()
        return {
            "intent": "change_field",
            "target_field": target,
            "new_value": new_val,
            "confidence": 0.7,
            "degraded": True,
        }

    # 4. Don't know / indecision / asking for recommendation on a pending field
    if pending_field:
        dk_stems = {"dunno", "unsur", "undec", "confu", "sugge", "recom", "advic", "advis", "whate"}
        has_dk_stem = bool(stems5 & dk_stems)
        neg_mental = bool(
            (token_set & {"no", "not", "dont", "don't", "havent", "haven't", "cant", "can't", "cannot"})
            and (
                stems5 & {"know", "sure", "idea", "clue", "decid", "pick", "picke", "choos", "chose", "figur"}
                or token_set & {"yet", "sure", "idea", "clue", "torn"}
            )
        )
        ask_bot_pick = bool(
            ("torn" in token_set)
            or ("beats" in token_set and "me" in token_set)
            or ("up" in token_set and "to" in token_set and "you" in token_set)
            or ("hard" in token_set and "say" in token_set)
            or (stems5 & {"choos", "pick"} and bool(token_set & {"help", "you", "for", "me", "whichever"}))
            or ("best" in token_set and bool(token_set & {"which", "what", "whats", "what's"}))
        )
        if has_dk_stem or neg_mental or ask_bot_pick:
            return {
                "intent": "dont_know",
                "target_field": target or pending_field,
                "new_value": "",
                "confidence": 0.7,
                "degraded": True,
            }

    # 5. Ask field info (alternatives / questions about pending field)
    if pending_field or (slots and slots.get("product")):
        asks_field_info = bool(
            (token_set & {"other", "others", "else", "alternatives", "additional", "besides", "variations", "rest", "why", "need", "required", "require", "mandatory", "optional", "options", "choices", "offer", "available"})
            and (
                "?" in text
                or bool(token_set & {"any", "what", "which", "do", "have", "offer", "options", "choices", "show", "why", "is"})
                or len(tokens) <= 3
            )
        )
        if asks_field_info:
            return {
                "intent": "ask_field_info",
                "target_field": target or (pending_field or ""),
                "new_value": "",
                "confidence": 0.7,
                "degraded": True,
            }

    return {
        "intent": "answer",
        "target_field": pending_field if pending_field in TARGET_FIELDS else "",
        "new_value": "",
        "confidence": 0.5,
        "degraded": True,
    }


def classify_turn(
    message: str,
    pending_field: str | None = None,
    slots: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify the visitor's message with full pending-field and product context."""
    text = (message or "").strip()
    if not text:
        return {
            "intent": "unclear",
            "target_field": "",
            "new_value": "",
            "confidence": 1.0,
            "degraded": False,
        }

    slots_dict = dict(slots or {})
    product = str(slots_dict.get("product") or "")
    pend_str = str(pending_field or "")
    is_complete = bool(slots_dict.get("_complete"))
    awaiting_contact = bool(slots_dict.get("_awaiting_contact"))

    key = _api_key()
    if not key:
        return _degraded_no_key_fallback(text, pending_field, slots_dict)

    cache_key = (text.lower(), pend_str, product, is_complete, awaiting_contact)
    if cache_key in _CACHE:
        return dict(_CACHE[cache_key])

    hist_slice = (history or [])[-4:]
    payload = json.dumps(
        {
            "message": text,
            "pending_field": pend_str or "none",
            "stored_product": product or "none",
            "slots": {k: v for k, v in slots_dict.items() if not str(k).startswith("_")},
            "complete": is_complete,
            "recent_history": hist_slice,
        },
        ensure_ascii=False,
    )

    parsed = _call_openai_structured(key, payload)
    if parsed and parsed.get("intent") in INTENTS:
        t_field = parsed.get("target_field") or ""
        if t_field not in TARGET_FIELDS:
            t_field = _FIELD_MAP.get(t_field.lower(), "")
        if parsed["intent"] == "change_field":
            low_txt = text.lower()
            _change_words = ("change", "chnage", "switch", "update", "modify", "revise", "adjust", "instead", "rather", "make it", "replace", "different")
            if not any(w in low_txt for w in _change_words):
                parsed["intent"] = "answer"
            elif re.search(r"\b(designs?|artworks?|skus?)\b", low_txt):
                t_field = "skus"
            elif re.search(r"\b(quantit(?:y|ies))\b", low_txt):
                t_field = "quantity"
            elif re.search(r"\b(finish(?:es)?|coating|lamination)\b", low_txt):
                t_field = "finishes"
            elif re.search(r"\b(size|sizes|dimension|dimensions)\b", low_txt):
                t_field = "sizes"
            elif re.search(r"\b(material|materials|stock)\b", low_txt):
                t_field = "material"
            elif re.search(r"\b(style|styles)\b", low_txt):
                t_field = "style"
            elif re.search(r"\b(type|types)\b", low_txt):
                t_field = "type"
            elif re.search(r"\b(extra|extras|add-?ons?)\b", low_txt):
                t_field = "extras"
        if not t_field and parsed["intent"] in ("dont_know", "ask_field_info") and pend_str in TARGET_FIELDS:
            t_field = pend_str
        new_val = str(parsed.get("new_value") or "").strip()
        if new_val.lower() == "undefined":
            new_val = ""
        if parsed["intent"] == "change_field" and new_val:
            low_nv = new_val.lower().strip()
            if low_nv in ("change", "chnage", "modify", "update", "switch", "revise") or any(low_nv.startswith(p) for p in ("change ", "chnage ", "modify ", "update ", "switch ", "revise ")):
                new_val = ""
            elif low_nv in _FIELD_MAP or low_nv in TARGET_FIELDS:
                new_val = ""
        result = {
            "intent": parsed["intent"],
            "target_field": t_field,
            "new_value": new_val,
            "confidence": float(parsed.get("confidence", 0.9)),
            "degraded": False,
        }
        _CACHE[cache_key] = result
        return dict(result)

    return _degraded_no_key_fallback(text, pending_field, slots_dict)
