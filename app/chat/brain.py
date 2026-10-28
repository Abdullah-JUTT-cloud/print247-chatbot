"""The chat brain: one pipeline, in this order, every message.

  1. Language detect (heuristic).
  2. Slot extraction + merge with the session's collected slots.
  3. Code guards: MOQ arithmetic, handoff triggers.
  4. RAG retrieval: exact topic first, then vector, then keyword.
  5. Answer:
       - handoff needed  -> say so, do not invent. POLICY RULE
         (narrowed, Oct 2026): a policy question is answered from
         the policy OKF file when retrieval finds one; handoff
         happens ONLY when no policy file covers the question.
       - MOQ failed     -> state the minimum, do not accept silently.
       - OPENAI key set -> gpt-5-mini writes the reply, using ONLY
         the retrieved OKF facts + slots + guard verdicts. It is told
         to say "confirm with the team" when a fact is not in them.
       - no key         -> deterministic reply: next missing-field
         question, or a retrieved fact. This is honest, not a fake
         sales answer, and it lets the whole pipeline be tested
         without spending a cent.

State: slots live in Mongo per session_id when Mongo is up; if it
is down, the chat still works for this message (state just does not
persist). A missing database must never break a visitor's chat.
"""
import os
import re

from . import guards
from .attempts import MAX_ASKS, apply_ask_outcome, ask_outcome, asks_what_is_usual, says_they_do_not_know
from .complete import get_chat_complete_message, when_the_team_replies
from .contacts import (CONTACT_FIELDS, contact_field_by_key, email_in, has_reachable_contact,
                       is_contact_value_usable, is_our_reps_name, is_placeholder_name,
                       missing_contact_fields, phones_in, REP_NAMES)
from .intents import (ALREADY_CUSTOMER_MESSAGE, ANSWER_TO_A_CATALOG, ANSWER_TO_A_PRICE_OBJECTION,
                      ANSWER_TO_ARE_YOU_A_BOT, ANSWER_TO_SAMPLES, DONE_WITH_US_MESSAGE, JOB_MESSAGE,
                      LATER_MESSAGE, NO_EMAIL_THEN_PHONE, PITCH_MESSAGE, YES_SEND_YOUR_NUMBER,
                      asks_for_a_catalog, asks_for_samples, asks_only_if_we_are_a_bot,
                      chat_is_a_pitch, chat_is_not_a_customer, is_already_a_customer,
                      is_done_with_us, is_looking_for_work, objects_to_the_price,
                      offers_a_phone_number, puts_it_off_for_now, rep_named_in,
                      wants_a_person, wants_it_in_the_chat)
from .language import detect_language
from .repeated import repeats_the_question
from .retrieval import retrieve
from .size_unit import apply_unit_answer, unit_answer
from .slots import extract_from_message, merge_slots, missing_fields

QUESTIONS = {
    "product": "What product are you looking for — for example mylar bags, pouches, boxes, or labels?",
    "sizes": "What size do you need? Width x height x depth, in inches or mm.",
    "quantity": "How many units do you need?",
}

def _suggestions(slots: dict, missing: list[str], reply: str = "") -> list[str]:
    """Clickable next steps shown under every bot reply.

    They follow the quote flow, not a random list: if the product
    is missing, suggest products; if sizes are missing, suggest
    sizes; if quantity is missing, suggest quantities; otherwise
    suggest the most-asked fact questions. The UI renders these as
    chips, so a visitor can continue in one tap instead of typing.

    Special case: a confirmation reply ("Just to confirm — do you
    want …?") gets Yes / Change chips, not generic fact questions
    — generic chips under a confirmation were a dead end in the
    first live transcript, because tapping one abandoned the quote.
    """
    low_reply = (reply or "").lower()
    if "just to confirm" in low_reply or "do you want" in low_reply:
        return ["Yes, that's correct", "Change quantity", "Change size"]
    if "product" in missing:
        return ["I need mylar bags", "I need custom boxes", "I need labels"]
    if "sizes" in missing:
        return ["Size 4x6 inches", "Size 100x150mm", "Not sure about size"]
    if "quantity" in missing:
        return ["1000 units", "5000 units", "Not sure about quantity"]
    return ["What is the minimum order?", "Is shipping free?",
            "What is your refund policy?"]


def _slot_sources(slots: dict) -> list[str]:
    """Clean sources for a slot-collection step.

    Keyword fallback ranked unrelated files here (a "Size 4x6
    inches" message returned banners.md, because it mentions size
    a lot). When the bot is just collecting the next field, the
    honest sources are the product file and the sizes file, not
    whatever the keyword search happened to rank.
    """
    out: list[str] = []
    product = (slots.get("product") or "").lower()
    if "mylar" in product or "pouch" in product:
        out.append("kb/products/pouches.md")
    elif "box" in product:
        out.append("kb/products/boxes.md")
    elif "label" in product or "sticker" in product:
        out.append("kb/products/labels.md")
    elif "banner" in product:
        out.append("kb/products/banners.md")
    elif "business card" in product:
        out.append("kb/products/business-cards.md")
    if slots.get("sizes"):
        out.append("kb/facts/sizes.md")
    return out


_POLICY_BEYOND_HANDOFF = (
    "That is a good question, and I do not want to give you a wrong "
    "answer: that detail is not in our published policy, so I am "
    "passing this to our team. They will confirm it directly. "
    "In the meantime, is there anything else about your order I can help with?"
)


def _load_session(store, session_id: str | None) -> dict:
    if not session_id or store is None:
        return {}
    try:
        return store.load(session_id) or {}
    except Exception:
        return {}


def _save_session(store, session_id: str | None, slots: dict) -> None:
    if not session_id or store is None:
        return
    try:
        store.save(session_id, slots)
    except Exception:
        pass


_META_FALLBACK: dict = {}


def _load_meta(store, session_id: str | None) -> dict:
    """Per-session brain state: asks counts, last asked field, last
    bot question, contact collected, paused/done/complete flags,
    visitor messages (for whole-chat checks). Stored in Mongo when
    the store supports it, else in-process (tests, store=None)."""
    if not session_id:
        return {}
    if store is not None:
        try:
            load_meta = getattr(store, "load_meta", None)
            if callable(load_meta):
                return load_meta(session_id) or {}
        except Exception:
            pass
    return _META_FALLBACK.get(session_id, {})


def _save_meta(store, session_id: str | None, meta: dict) -> None:
    if not session_id:
        return
    if store is not None:
        try:
            save_meta = getattr(store, "save_meta", None)
            if callable(save_meta):
                save_meta(session_id, meta)
                return
        except Exception:
            pass
    _META_FALLBACK[session_id] = meta


def _session_rep(session_id: str | None) -> str | None:
    """The rep the UI greeting shows for this session (same hash as
    app/chat_ui.py repName()), so a visitor greeting their own rep
    by first name is never mistaken for naming a different rep."""
    if not session_id:
        return None
    h = 0
    for ch in session_id:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return REP_NAMES[h % len(REP_NAMES)]


_QUESTION_VARIANTS = {
    "product": "What are you looking to have made — boxes, bags or labels?",
    "sizes": "What size are you looking for?",
    "quantity": "What quantity are you looking to order for your first run?",
    "per_design": "How many units per design do you need?",
    "name": "May I have your name?",
    "email": "Which email should I send the quote to?",
    "phone": "What phone number can the team reach you on?",
}


def _next_question_text(slots: dict, missing: list[str]) -> str:
    if not missing:
        return ""
    if missing[0] == "quantity":
        try:
            if int(slots.get("skus", "1")) > 1:
                return _QUESTION_VARIANTS["per_design"]
        except (TypeError, ValueError):
            pass
    return QUESTIONS[missing[0]]


def _missing_contact(meta: dict, contact: dict) -> list:
    """Missing contact fields, excluding ones the visitor declined or
    exhausted (old rule: a refusal retires the field at once — the
    field must not be asked a third time under another name)."""
    retired = set(meta.get("contact_retired") or [])
    wanted = [f["key"] for f in CONTACT_FIELDS if f["key"] not in retired]
    return missing_contact_fields(contact, wanted)


def _with_next_question(answer: str, slots: dict, missing: list[str]) -> str:
    q = _next_question_text(slots, missing)
    return f"{answer} {q}" if q else answer


_FACT_WORDS = ["minimum", "moq", "turnaround", "shipping", "sample",
               "how long", "delivery", "lead time"]


def _clean_fact_text(text: str) -> str:
    """Strip the YAML frontmatter (--- id: … ---) from a KB file
    before showing it. The old code returned the raw file, so a
    visitor could see '--- id: fact-moq' at the top of a reply."""
    t = (text or "").strip()
    if t.startswith("---\n"):
        end = t.find("\n---", 4)
        if end != -1:
            t = t[end + 4:].strip()
    if len(t) > 800:
        # Never cut mid-word: the old 800-char cut left replies
        # ending in "bu" for "but". Back off to the last space.
        cut = t[:800]
        last_space = cut.rfind(" ")
        if last_space > 600:
            cut = cut[:last_space]
        return cut
    return t


def _fact_reply_text(text: str) -> str:
    """One-paragraph answer when the file opens with a real answer
    (bottle labels open with 'Yes — we print…'), otherwise the
    full cleaned text. This kills the old 'whole file dump' reply
    without losing facts from summary-style files."""
    cleaned = _clean_fact_text(text)
    first = cleaned.split("\n\n")[0].strip()
    # Only a first paragraph that IS an answer (starts with Yes, or
    # carries a number) wins. Quote-flow's first paragraph is a
    # flow description with no number — its answer ("2 to 3 business
    # days") lives in paragraph 2, so that file must fall back to
    # the full text, or the golden case for it breaks.
    if (150 <= len(first) <= 800
            and (first.lower().startswith("yes")
                 or any(ch.isdigit() for ch in first))):
        return first
    return cleaned


def _deterministic_reply(message: str, slots: dict, facts: list[dict], missing: list[str]) -> str:
    """No-LLM reply. Only uses OKF text and slot questions — it can
    never invent a price, a policy, or a fact.

    Order matters: an ORDER statement ("I need 2 banners") must get
    the next missing-field question, not a fact chunk that merely
    mentions a keyword. Only a real fact question ("?", or a fact
    word like turnaround) gets the fact text first.
    """
    low = message.lower()
    is_fact_question = "?" in message or any(w in low for w in _FACT_WORDS)
    if is_fact_question and not facts:
        return ("I don't want to give you a wrong answer on that — that detail "
                "is not in our published facts, so I will confirm with the team.")
    if facts and is_fact_question:
        text = _fact_reply_text(facts[0]["text"])
        # Capability question about a real product ("Can you print
        # boxes?") deserves a Yes first, not a bare list. Restricted
        # to kb/products files, so a turnaround/policy question can
        # never be falsely turned into a Yes.
        is_capability = low.startswith(("can you", "do you", "can i", "could you"))
        if is_capability and "/products/" in facts[0]["source"] and not text.lower().startswith("yes"):
            text = "Yes — " + (text[0].lower() + text[1:] if text else text)
        return text
    if missing:
        # Multi-design order: quantity is PER DESIGN (the question the
        # competitor's human rep asks: "How much quantity per design?").
        if missing[0] == "quantity":
            try:
                if int(slots.get("skus", "1")) > 1:
                    return "How many units do you need per design?"
            except (TypeError, ValueError):
                pass
        return QUESTIONS[missing[0]]
    # Quote complete and no fact question: ask for confirmation, not
    # a raw KB chunk. (The old fallback returned facts[0] here, which
    # was a whole file including its frontmatter — the ugliest reply
    # in the live transcript's no-LLM path.)
    if not missing:
        try:
            n_designs = int(slots.get("skus", "1"))
        except (TypeError, ValueError):
            n_designs = 1
        if n_designs > 1:
            try:
                total = int(slots.get("quantity", "0")) * n_designs
            except (TypeError, ValueError):
                total = slots.get("quantity")
            return (f"Just to confirm — do you want {slots.get('quantity')} "
                    f"{slots.get('product')} per design, {n_designs} designs "
                    f"(total {total} units), size {slots.get('sizes')}, "
                    f"with {slots.get('extras', 'none')} extras?")
        return (f"Just to confirm — do you want {slots.get('quantity')} "
                f"{slots.get('product')}, size {slots.get('sizes')}, "
                f"{slots.get('skus', '1')} SKU with {slots.get('extras', 'none')} extras?")
    if facts:
        return _fact_reply_text(facts[0]["text"])
    return "Thanks — I have your details. A team member will confirm the quote shortly."


def _llm_reply(message: str, language: str, slots: dict, facts: list[dict],
               reply_to: str | None = None) -> str | None:
    """gpt-5-mini answer, or None if no key / call fails.

    The prompt is the leash: facts come ONLY from the retrieved OKF
    chunks below. No chunk about it -> the model must say it will
    confirm with the team, never guess. Numbers are copied verbatim.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI()
        fact_block = "\n\n".join(
            f"[{f['source']}] {f['text']}" for f in facts) or "No OKF fact retrieved."
        reply_ctx = (f"\nThe visitor is replying to this earlier bot message: "
                     f"{reply_to}. Answer in that context.\n"
                     if reply_to else "")
        system = (
            "You are a Print247 sales assistant. Reply in the visitor's "
            f"language ({language}). If skus is more than 1, quantity means "
            "PER DESIGN: ask for quantity per design and, when confirming, "
            "state quantity per design and the total. Use ONLY the facts below and the "
            "collected order details. If a fact is not in them, say you "
            "will confirm with the team — never guess, never invent a "
            "price, policy, or date. Copy numbers verbatim. Keep it short, "
            "one question at a time.\n\n"
            f"FACTS:\n{fact_block}\n\nCOLLECTED: {slots}{reply_ctx}"
        )
        resp = client.chat.completions.create(
            model=os.environ.get("CHAT_MODEL", "gpt-5-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            timeout=30,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def _perfect_reply(slots: dict) -> str:
    """Quote-ready message. Multi-design orders state per-design
    quantity and total, or the confirmation lies by omission."""
    try:
        n = int(slots.get("skus", "1"))
    except (TypeError, ValueError):
        n = 1
    if n > 1:
        try:
            total = int(slots.get("quantity", "0")) * n
        except (TypeError, ValueError):
            total = slots.get("quantity")
        return (f"Perfect — your quote request is ready: {slots.get('product')}, "
                f"{slots.get('sizes')}, {slots.get('quantity')} units per design, "
                f"{n} designs (total {total} units), extras {slots.get('extras', 'none')}. "
                f"A team member will confirm the price and turnaround {when_the_team_replies()}.")
    return (f"Perfect — your quote request is ready: {slots.get('product')}, "
            f"{slots.get('sizes')}, {slots.get('quantity')} units, "
            f"{slots.get('skus', '1')} SKU, extras {slots.get('extras', 'none')}. "
            f"A team member will confirm the price and turnaround {when_the_team_replies()}.")


def handle_message(message: str, session_id: str | None = None, store=None,
                   reply_to: str | None = None) -> dict:
    """reply_to is the bot message the visitor tapped Reply on. It
    is context for the LLM and is logged; it never changes slots
    by itself. Session slots are the real context memory: they are
    loaded, merged, and saved on every message, so a side question
    (shipping, SKU) mid-quote never wipes the collected order."""
    language = detect_language(message)
    prior = _load_session(store, session_id)
    meta = _load_meta(store, session_id)
    low = message.lower().strip()
    # Whole-chat memory for the checks below (capped, visitor only).
    visitor_messages = list(meta.get("visitor_messages") or [])
    visitor_messages.append(message)
    meta["visitor_messages"] = visitor_messages[-50:]
    # Paused ('later') or ended ('done') chats: a new message picks
    # the paused chat up where it left off, and restarts an ended one.
    if meta.get("paused"):
        meta["paused"] = False
    if meta.get("done"):
        meta["done"] = False
        prior = {}
        meta["contact"] = {}
        meta["asks"] = {}
    # --- Old-bot intents, in code before any slot work. A pure intent
    # message never merges slots: 'photos of your boxes' must not
    # become product=box, and a job enquiry must never become a quote.
    _is_order = any(ph in low for ph in ("i need", "i want", "i'd like",
                                          "i would like", "order", "get a quote",
                                          "quote for", "buy"))

    def _intent_result(reply, handoff=None, suggestions=None):
        _save_session(store, session_id, prior)
        _save_meta(store, session_id, meta)
        return {"reply": reply, "language": language, "slots": prior,
                "missing": missing_fields(prior), "sources": [],
                "handoff": handoff, "llm_used": False,
                "suggestions": suggestions if suggestions is not None else []}

    if is_looking_for_work(message) or chat_is_a_pitch([message]):
        return _intent_result(JOB_MESSAGE if is_looking_for_work(message) else PITCH_MESSAGE,
                              handoff="not_a_customer")
    # Bot-only question FIRST: 'are you a bot?' also matches the
    # human-request pattern, and the old bot used to hand those chats
    # over by mistake. Curiosity is not a request for somebody else.
    if asks_only_if_we_are_a_bot(message):
        return _intent_result(_with_next_question(ANSWER_TO_ARE_YOU_A_BOT, prior, missing_fields(prior)))
    if wants_a_person(message):
        return _intent_result("Of course — I am connecting you with a team member who can help directly.",
                              handoff="visitor_asked_for_human")
    _named = rep_named_in(message, _session_rep(session_id))
    if _named:
        first = _named.split()[0]
        return _intent_result(f"Yes, {first} is on our team. I'm passing you to {first} now.",
                              handoff="visitor_asked")
    # A policy QUESTION ('what is your refund policy?') matches the
    # already-customer pattern on the word 'refund' alone — it must
    # fall through to the policy KB answer, not a handoff. A real
    # complaint ('my order arrived damaged') still hands off.
    if is_already_a_customer(message) and not (
            "?" in message and re.search(r"\bpolic(?:y|ies)\b|what is your|what's your", low)):
        return _intent_result(ALREADY_CUSTOMER_MESSAGE, handoff="existing_customer")
    if is_done_with_us(message):
        meta["done"] = True
        return _intent_result(DONE_WITH_US_MESSAGE, handoff="done_with_us")
    if puts_it_off_for_now(message):
        meta["paused"] = True
        return _intent_result(LATER_MESSAGE)
    if not _is_order and asks_for_a_catalog(message):
        return _intent_result(_with_next_question(ANSWER_TO_A_CATALOG, prior, missing_fields(prior)))
    if not _is_order and asks_for_samples(message) and "?" not in message:
        # A sample REQUEST ('send me samples') is noted for the team;
        # a sample QUESTION ('do you offer samples?') falls through
        # to the KB fact answer below.
        return _intent_result(_with_next_question(ANSWER_TO_SAMPLES, prior, missing_fields(prior)))
    if objects_to_the_price(message):
        return _intent_result(_with_next_question(ANSWER_TO_A_PRICE_OBJECTION, prior, missing_fields(prior)))
    if offers_a_phone_number(message):
        meta["awaiting_contact"] = True
        meta["last_asked"] = "phone"
        return _intent_result(YES_SEND_YOUR_NUMBER)
    if wants_it_in_the_chat(message) and meta.get("last_asked") == "email":
        meta["last_asked"] = "phone"
        meta.setdefault("asks", {})["email"] = MAX_ASKS
        return _intent_result(NO_EMAIL_THEN_PHONE)
    # Extraction must never crash the chat: a parser bug used to turn
    # into a 500 and the visitor saw "Message didn't send" (the
    # "15 thousand" case: float("15 thousand") raised ValueError).
    try:
        extracted = extract_from_message(message)
    except Exception:
        extracted = {}
    _is_fact_q = "?" in message or any(w in low for w in _FACT_WORDS)
    _is_order = any(ph in low for ph in ("i need", "i want", "i'd like",
                                          "i would like", "order", "get a quote",
                                          "quote for", "buy"))
    if _is_fact_q and not _is_order:
        # A question's numbers/sizes are what it ASKS about, not an
        # order spec — drop them so no guard ever fires on them.
        extracted.pop("quantity", None)
        extracted.pop("sizes", None)
    slots = merge_slots(prior, extracted)
    # Finished chat + a new order statement = a new enquiry, not a
    # continuation with stale size/quantity (old whatToDoWithFinishedChat).
    if meta.get("complete") and _is_order and not meta.get("awaiting_contact"):
        slots = merge_slots({}, extracted)
        prior = {}
        meta["complete"] = False
    # Contact volunteered mid-chat (deterministic half of the old
    # contactExtractor): an email or phone-shaped value is kept, ours
    # never is. A name is only taken when it was asked for (below).
    contact = dict(meta.get("contact") or {})
    _em = email_in(message)
    if _em and is_contact_value_usable("email", _em):
        contact["email"] = _em
    for _ph in phones_in(message):
        if is_contact_value_usable("phone", _ph):
            contact["phone"] = _ph
            break
    meta["contact"] = contact
    # A bare unit answers a unit question ('mm' after 'inches, cm or
    # mm?'): put it onto the size in code, like the old bot did.
    _unit = unit_answer(message)
    if _unit and slots.get("sizes"):
        slots["sizes"] = apply_unit_answer(slots["sizes"], _unit)
    # --- Contact flow (old contactFields.ts): asked after the job
    # details, in name -> email -> phone order, MAX_ASKS=2 per field,
    # a refusal retires the field at once, and the chat only finishes
    # when at least one reachable contact exists or both are exhausted.
    if meta.get("awaiting_contact"):
        _field = meta.get("last_asked")
        if _field not in ("name", "email", "phone"):
            _field = (_missing_contact(meta, contact) or [None])[0]
        if _field:
            _candidate = None
            if _field == "email":
                _candidate = email_in(message) or None
            elif _field == "phone":
                _phones = phones_in(message)
                _candidate = _phones[0] if _phones else None
            else:
                _candidate = message.strip() or None
            _usable = bool(_candidate) and is_contact_value_usable(_field, _candidate)
            if _field == "name" and _candidate and is_our_reps_name(_candidate, visitor_messages):
                _usable = False
            # An order statement is never a name answer ('I need mylar
            # bags' while awaiting a name must not become name='I need
            # mylar bags'): treat it as a free turn and let the quote
            # flow below handle it, contact question still pending.
            _name_is_order = _field == "name" and (_is_order or bool(extracted))
            if _name_is_order:
                _usable = False
            _outcome = ask_outcome(_field, message, _usable)
            if _name_is_order:
                _outcome = "free"
            if _usable:
                contact[_field] = _candidate
                meta["contact"] = contact
                meta.setdefault("asks", {})[_field] = 0
                _next = (_missing_contact(meta, contact) or [None])[0]
                if _next is None:
                    meta["awaiting_contact"] = False
                    meta["complete"] = True
                    _save_session(store, session_id, slots)
                    _save_meta(store, session_id, meta)
                    return {
                        "reply": get_chat_complete_message(), "language": language,
                        "slots": slots, "missing": missing_fields(slots),
                        "sources": _slot_sources(slots), "handoff": "complete",
                        "llm_used": False, "suggestions": [], "contact": contact,
                    }
                meta["last_asked"] = _next
                _q = contact_field_by_key(_next)["question"]
                if repeats_the_question(_q, meta.get("last_bot_question", "")):
                    _q = _QUESTION_VARIANTS[_next]
                meta["last_bot_question"] = _q
                _save_session(store, session_id, slots)
                _save_meta(store, session_id, meta)
                return {
                    "reply": _q, "language": language, "slots": slots,
                    "missing": missing_fields(slots), "sources": _slot_sources(slots),
                    "handoff": None, "llm_used": False, "suggestions": [], "contact": contact,
                }
            if _outcome == "free":
                # They asked us something instead of answering: answer
                # it below, keep the contact question pending.
                meta["last_asked"] = _field
                _save_meta(store, session_id, meta)
            else:
                meta.setdefault("asks", {})[_field] = apply_ask_outcome(
                    meta.setdefault("asks", {}).get(_field, 0), _outcome)
                if _outcome == "declined" or meta["asks"][_field] >= MAX_ASKS:
                    meta.setdefault("contact_retired", []).append(_field)
                _next = (_missing_contact(meta, contact) or [None])[0]
                if _next is None:
                    meta["awaiting_contact"] = False
                    meta["complete"] = True
                    _save_session(store, session_id, slots)
                    _save_meta(store, session_id, meta)
                    return {
                        "reply": ("Thanks — I have your order. Since I don't have an email or "
                                  "phone number, our team will follow up with you here in this chat. "
                                  f"They will confirm the price and turnaround {when_the_team_replies()}."),
                        "language": language, "slots": slots, "missing": missing_fields(slots),
                        "sources": _slot_sources(slots), "handoff": "complete_no_contact",
                        "llm_used": False, "suggestions": [], "contact": contact,
                    }
                if _next != _field:
                    meta["last_asked"] = _next
                    _q = contact_field_by_key(_next)["question"]
                    meta["last_bot_question"] = _q
                    _save_session(store, session_id, slots)
                    _save_meta(store, session_id, meta)
                    return {
                        "reply": _q, "language": language, "slots": slots,
                        "missing": missing_fields(slots), "sources": _slot_sources(slots),
                        "handoff": None, "llm_used": False, "suggestions": [], "contact": contact,
                    }
                _save_session(store, session_id, slots)
                _save_meta(store, session_id, meta)
                return {
                    "reply": contact_field_by_key(_field)["question"], "language": language,
                    "slots": slots, "missing": missing_fields(slots),
                    "sources": _slot_sources(slots), "handoff": None,
                    "llm_used": False, "suggestions": [], "contact": contact,
                }
    if low in ("start over", "new order", "start again", "reset",
               "new quote", "start fresh"):
        _save_session(store, session_id, {})
        _save_meta(store, session_id, {})
        return {
            "reply": "Sure — starting fresh. What product are you looking for?",
            "language": language, "slots": {}, "missing": ["product"],
            "sources": [], "handoff": None, "llm_used": False,
            "suggestions": ["I need mylar bags", "I need custom boxes",
                            "I need labels", "What do you offer?"],
        }

    # Confirmation chips must actually work: "Change quantity" clears
    # that slot and re-asks it, instead of the bot treating the tap
    # as a new message and repeating the confirmation.
    if "change quantity" in low:
        slots.pop("quantity", None)
        _save_session(store, session_id, slots)
        return {
            "reply": QUESTIONS["quantity"], "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": _slot_sources(slots),
            "handoff": None, "llm_used": False,
            "suggestions": ["1000 units", "5000 units", "Not sure about quantity"],
        }
    if "change size" in low:
        slots.pop("sizes", None)
        _save_session(store, session_id, slots)
        return {
            "reply": QUESTIONS["sizes"], "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": _slot_sources(slots),
            "handoff": None, "llm_used": False,
            "suggestions": ["Size 4x6 inches", "Size 100x150mm", "Not sure about size"],
        }
    if low in ("yes", "yes, that's correct", "yes thats correct",
               "yes, that's right", "confirm", "confirmed", "correct") \
            and guards.is_complete(slots):
        # Whole-chat not-a-customer check: a job seeker who later
        # typed an order word is still not a lead if the chat as a
        # whole never became an enquiry.
        if chat_is_not_a_customer(visitor_messages):
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {
                "reply": JOB_MESSAGE if any(is_looking_for_work(m) for m in visitor_messages) else PITCH_MESSAGE,
                "language": language, "slots": slots,
                "missing": missing_fields(slots), "sources": [],
                "handoff": "not_a_customer", "llm_used": False, "suggestions": [],
            }
        _contact = dict(meta.get("contact") or {})
        _next_contact = (_missing_contact(meta, _contact) or [None])[0]
        if _next_contact is None and has_reachable_contact(_contact):
            meta["awaiting_contact"] = False
            meta["complete"] = True
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {
                "reply": _perfect_reply(slots) + " " + get_chat_complete_message(),
                "language": language, "slots": slots,
                "missing": missing_fields(slots), "sources": _slot_sources(slots),
                "handoff": "complete", "llm_used": False, "suggestions": [],
                "contact": _contact,
            }
        # Old script order: quote details first, contact after. The
        # confirmation summary stays, then the first contact question.
        meta["awaiting_contact"] = True
        meta["last_asked"] = _next_contact or "name"
        _q = contact_field_by_key(meta["last_asked"])["question"]
        meta["last_bot_question"] = _q
        _save_session(store, session_id, slots)
        _save_meta(store, session_id, meta)
        return {
            "reply": _perfect_reply(slots) + " " + _q,
            "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": _slot_sources(slots),
            "handoff": None, "llm_used": False, "suggestions": [],
            "contact": _contact,
        }
    reason = guards.handoff_reason(message, slots)
    facts: list[dict] = []
    if reason == "policy_question":
        # Narrowed handoff: if a policy OKF file covers the question,
        # answer from it (normal path below) instead of handing off.
        facts = retrieve(message)
        if not any(f["source"].startswith("kb/policies/") for f in facts):
            _save_session(store, session_id, slots)
            return {
                "reply": _POLICY_BEYOND_HANDOFF, "language": language,
                "slots": slots, "missing": missing_fields(slots),
                "sources": [], "handoff": reason, "llm_used": False,
                "suggestions": _suggestions(slots, missing_fields(slots)),
            }
    if reason and reason != "policy_question":
        _save_session(store, session_id, slots)
        return {
            "reply": "Of course — I am connecting you with a team member who can help directly.",
            "language": language, "slots": slots,
            "missing": missing_fields(slots), "sources": [],
            "handoff": reason, "llm_used": False,
            "suggestions": _suggestions(slots, missing_fields(slots)),
        }

    moq = guards.moq_check(slots)
    if not facts:
        facts = retrieve(message)
    sources = [f["source"] for f in facts]
    missing = missing_fields(slots)

    # "Not sure" used to loop forever: the bot re-asked the same
    # MOQ question because no quantity was ever collected. Instead,
    # offer the MOQ as a starting point (quantity) or a common size
    # (sizes), so the visitor can move forward in one tap.
    # ORDER FIX: sizes must be checked BEFORE quantity. Slot order is
    # product -> sizes -> quantity, so after "Not sure about size"
    # both sizes AND quantity are missing — the old quantity-first
    # check fired and offered quantity chips for a size question.
    if ("not sure" in low or says_they_do_not_know(message)) and missing:
        if "sizes" in missing:
            _save_session(store, session_id, slots)
            return {
                "reply": ("No problem — tell me what will go inside the pack, "
                          "or pick a common size to start with."),
                "language": language, "slots": slots, "missing": missing,
                "sources": _slot_sources(slots) or sources,
                "handoff": None, "llm_used": False,
                "suggestions": ["Size 4x6 inches", "Size 100x150mm",
                                "I will send artwork later"],
            }
        if "quantity" in missing:
            _save_session(store, session_id, slots)
            return {
                "reply": ("No problem — most orders start at the minimum of 1000 units "
                          "per size. Would you like to start with 1000, or a rough range?"),
                "language": language, "slots": slots, "missing": missing,
                "sources": _slot_sources(slots) or sources,
                "handoff": None, "llm_used": False,
                "suggestions": ["1000 units", "5000 units", "More than 5000"],
            }

    if not moq["ok"]:
        _bot_said = meta.get("bot_replies") or []
        if any("minimum order is 1000" in b for b in _bot_said):
            _reply = ("As mentioned, the minimum is 1000 units per size — would 1000 units "
                      "work for you, or should I note the smaller run for the team?")
        else:
            _reply = moq["message"]
        meta.setdefault("bot_replies", []).append(_reply)
        _save_session(store, session_id, slots)
        _save_meta(store, session_id, meta)
        return {
            "reply": _reply, "language": language, "slots": slots,
            "missing": missing, "sources": sources,
            "handoff": None, "llm_used": False,
            "suggestions": _suggestions(slots, missing),
        }

    # ANSWER ROUTING — the fix for the live box/SKU transcript:
    # - Slot collection (no fact question) NEVER goes to the LLM.
    #   The LLM was inventing extra questions ("what depth should
    #   the box be?") while the brain already had sizes filled and
    #   the chips asked for quantity — text and chips disagreed.
    #   The deterministic next-question is the only honest reply.
    # - An exact-topic fact question (one file returned, e.g. SKU)
    #   also skips the LLM: the LLM once refused a definition that
    #   was sitting in its own fact block. The KB text itself is
    #   the answer, verbatim, frontmatter stripped.
    # - Only a multi-file / open fact question goes to the LLM,
    #   with the OKF leash, and falls back to deterministic.
    is_fact_question = "?" in message or any(w in low for w in _FACT_WORDS)
    # Asking what is usual ('what is a standard size?') is a question
    # about the field, not an answer to it: answer it first, then
    # re-ask the field. There is no standard — everything is made to
    # fit what goes inside.
    if asks_what_is_usual(message) and missing:
        reply = ("There's no standard one — everything is made to fit what goes inside. "
                 + _next_question_text(slots, missing))
        llm_used = False
        sources = _slot_sources(slots)
    elif not is_fact_question or (is_fact_question and len(facts) == 1):
        # Ask-attempt accounting (old askAttempts.ts): an attempt is
        # spent only when the visitor had a go and the field is still
        # missing. Exhausted fields are skipped for the next question
        # instead of being asked a third time.
        _last = meta.get("last_asked")
        _asks = dict(meta.get("asks") or {})
        if _last in ("product", "sizes", "quantity"):
            _have_now = not missing_fields(slots) or _last not in missing_fields(slots)
            _asks[_last] = apply_ask_outcome(_asks.get(_last, 0),
                                             ask_outcome(_last, message, _have_now))
            meta["asks"] = _asks
        _askable = [f for f in missing if _asks.get(f, 0) < MAX_ASKS]
        if missing and not _askable:
            _reply = ("Thanks — I've got " + ", ".join(
                f"{k}: {slots[k]}" for k in ("product", "sizes", "quantity") if slots.get(k))
                + f". For {', '.join(missing)}, the team will confirm it with you directly.")
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {"reply": _reply, "language": language, "slots": slots,
                    "missing": missing, "sources": _slot_sources(slots),
                    "handoff": "needs_followup", "llm_used": False,
                    "suggestions": _suggestions(slots, missing)}
        reply = _deterministic_reply(message, slots, facts, _askable or missing)
        llm_used = False
        if reply in set(QUESTIONS.values()) | {"How many units do you need per design?"}:
            sources = _slot_sources(slots)
            # Repeat guard (old repeatedQuestion.ts): never send a
            # question already asked — reword it instead.
            if repeats_the_question(reply, meta.get("last_bot_question", "")):
                _field = _askable[0] if _askable else missing[0]
                reply = _QUESTION_VARIANTS.get(_field, reply) \
                    if _field != "quantity" or int(slots.get("skus", "1")) <= 1 \
                    else _QUESTION_VARIANTS["per_design"]
            meta["last_asked"] = _askable[0] if _askable else None
        elif not is_fact_question:
            sources = _slot_sources(slots) or sources
    else:
        reply = _llm_reply(message, language, slots, facts, reply_to=reply_to)
        llm_used = reply is not None
        if not llm_used:
            reply = _deterministic_reply(message, slots, facts, missing)
        # Composer validator (old chatComposer.ts problemsWith): a
        # reply carrying template blanks is fixed in code, not sent.
        if llm_used and "__" in (reply or ""):
            reply = _deterministic_reply(message, slots, facts, missing)
            llm_used = False
    meta["last_bot_question"] = reply
    meta.setdefault("bot_replies", []).append(reply)
    meta["bot_replies"] = meta["bot_replies"][-20:]
    _save_session(store, session_id, slots)
    _save_meta(store, session_id, meta)

    result = {
        "reply": reply, "language": language, "slots": slots,
        "missing": missing, "sources": sources,
        "handoff": "complete" if guards.is_complete(slots) else None,
        "llm_used": llm_used,
        "suggestions": _suggestions(slots, missing, reply=reply),
    }
    return result
