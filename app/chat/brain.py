"""The chat brain: one pipeline, in this order, every message.

  1. Language detect (heuristic).
  2. Old-bot intents in code (job, pitch, human, catalog, samples,
     price objection, done, later) — pure intent messages never
     merge slots.
  3. Slot extraction + merge with the session's collected slots:
     code first, then one gpt-5-nano read when code found nothing
     (validated by code before anything is stored). A question is
     never an answer: a visitor's question sentence fills no slot.
  4. Code guards: handoff triggers, below-minimum note (the old
     brain never refuses a smaller run — it states the minimum
     once and lets the team confirm it).
  5. The sales script, one question at a time, in the team's order:
     product -> sizes -> style -> finishes -> quantity -> skus ->
     extras -> material (family trims apply; plain orders never get
     a designs question). A fact question is answered FIRST, then
     the script question — never the other way round.
  6. RAG retrieval: exact topic first, then vector, then keyword.
  7. Answer:
       - handoff needed  -> say so, do not invent. POLICY RULE
         (narrowed, Oct 2026): a policy question is answered from
         the policy OKF file when retrieval finds one; handoff
         happens ONLY when no policy file covers the question.
       - OPENAI key set -> gpt-5-mini writes the reply, using ONLY
         the retrieved OKF facts + slots + guard verdicts, then the
         composer validator fixes it in code (or falls back to the
         deterministic reply when it is unsalvageable).
       - no key         -> deterministic reply: next script
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
from .attempts import (MAX_ASKS, apply_ask_outcome, ask_outcome, asks_what_is_usual,
                       says_they_do_not_know, visitor_is_asking, wants_to_stop)
from .complete import get_chat_complete_message, when_the_team_replies
from .erp_eligibility import quantity_is_per_design, quantity_is_total
from .composer import fix_reply
from .contacts import (CONTACT_FIELDS, contact_field_by_key, email_in, has_reachable_contact,
                       is_contact_value_usable, is_our_reps_name, is_placeholder_name,
                       missing_contact_fields, phones_in, REP_NAMES)
from .capability import (capability_fact, capability_product, capability_source)
from .qualifiers import qualifier_caveat, unlisted_qualifiers
from .learn import save_learned
from .websearch import web_search
from .fact_topics import asks_bare_fact_topic, fact_topics_asked, topic_query
from .finished import (NOTED_AFTER_THE_QUOTE, NOT_SENT_YET, SIGN_OFFS,
                       asks_if_it_arrived, is_pleasantry)
from .i18n import tr as _tr
from .intents import (ALREADY_CUSTOMER_MESSAGE, ANSWER_TO_A_CATALOG, ANSWER_TO_A_PRICE_OBJECTION,
                      ANSWER_TO_ARE_YOU_A_BOT, ANSWER_TO_SAMPLES, BYE_ANSWER, DONE_WITH_US_MESSAGE,
                      HARM_ANSWER, HOW_ARE_YOU_ANSWER, JOB_MESSAGE, LATER_MESSAGE, LIED_ANSWER,
                      NO_EMAIL_THEN_PHONE, PITCH_MESSAGE, SHARED_FILE_ANSWER, THANKS_ANSWER,
                      TRUST_ANSWER, YES_SEND_YOUR_NUMBER, asks_about_trust, asks_for_a_catalog,
                      asks_for_samples, asks_how_are_you, asks_only_if_we_are_a_bot,
                      chat_is_a_pitch, chat_is_not_a_customer, claims_harm, claims_we_lied,
                      is_already_a_customer, is_dismissal, is_done_with_us, is_looking_for_work,
                      objects_to_the_price, offers_a_phone_number, puts_it_off_for_now,
                      rep_named_in, says_bye, says_thanks, shared_a_file, wants_a_person,
                      wants_it_in_the_chat, asks_for_suggestion, suggestion_product,
                      suggestion_use)
from .language import detect_language
from .llm_extract import llm_extract
from .price_questions import PRICING_COMES_WITH_THE_QUOTE, asks_about_price
from .quantity_parse import minimum_already_stated, wants_smaller_run
from .quote_value import is_our_own_menu, without_template_blanks
from .repeated import SENTENCE_BREAK, repeats_the_question
from .retrieval import retrieve
from .script import (BELOW_MIN_NOTE, is_banner_family, per_design_quantity,
                     question_for, script_complete, script_missing, wants_plain_packaging)
from .size_unit import apply_unit_answer, size_missing_unit, unit_answer
from .slots import (_PRODUCTS, _find, extract_from_message, fuzzy_product,
                     merge_slots, missing_fields)

# A decline of a script field ("no", "none", "no preference"): the
# field is recorded as "none"/"1" and the script moves on, instead
# of looping on it. Product/sizes/quantity declines are NOT answers
# — those fields are re-asked until given up.
_DECLINE = re.compile(
    r"^\s*(?:no|none|nope|nah|not needed|no preference|doesn'?t matter|don'?t need (?:it|one|any)?|no thanks?)\s*[.!]*\s*$",
    re.IGNORECASE)
_YES = re.compile(r"^\s*(?:yes|yeah|yep|ya|sure|please|ok(?:ay)?)\s*[.!]*\s*$", re.IGNORECASE)
_BARE_NUMBER = re.compile(r"^\s*(\d+)\s*$")
_BARE_SPELLED = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                 "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}

def _question(field: str, slots: dict, language: str) -> str:
    """The script question for a field, in the visitor's language
    when a translation exists (i18n.py), else the team's English."""
    if field == "style":
        key = "q_style_boxes" if "box" in (slots.get("product") or "").lower() else "q_style_bags"
        english = question_for(field, slots)
        return _tr(key, language, english)
    if field == "type":
        # The type question is the product file's own list sentence
        # (same text the types branch answers with), not the bare
        # "Which type would you like?" fallback.
        _tl = _type_list_sentence(slots.get("product") or "box")
        return (_tl + " Which type would you like?") if _tl else question_for(field, slots)
    if field == "quantity" and per_design_quantity(slots):
        return _tr("q_per_design", language, "How many units do you need per design?")
    key = {"product": "q_product", "sizes": "q_sizes", "finishes": "q_finishes",
           "quantity": "q_quantity_banner" if is_banner_family(slots.get("product")) else "q_quantity",
           "skus": "q_skus", "extras": "q_extras", "material": "q_material"}.get(field, "")
    english = question_for(field, slots)
    return _tr(key, language, english) if key else english


def _contact_question(field: str, language: str) -> str:
    english = contact_field_by_key(field)["question"]
    return _tr("q_" + field, language, english)


def _suggestions(slots: dict, missing: list[str], reply: str = "", language: str = "en") -> list[str]:
    """Clickable next steps shown under every bot reply.

    They follow the script, not a random list: the first missing
    script field decides the chips. The UI renders these as chips,
    so a visitor can continue in one tap instead of typing.

    Special case: a confirmation reply ("Just to confirm — do you
    want …?") gets Yes / Change chips, not generic fact questions
    — generic chips under a confirmation were a dead end in the
    first live transcript, because tapping one abandoned the quote.
    """
    low_reply = (reply or "").lower()
    if "just to confirm" in low_reply or "do you want" in low_reply \
            or "confirm kar lun" in low_reply or "solo para confirmar" in low_reply:
        return [_tr("yes_correct", language, "Yes, that's correct"),
                _tr("change_quantity", language, "Change quantity"),
                _tr("change_size", language, "Change size")]
    if "product" in missing:
        return [_tr("chip_mylar", language, "I need mylar bags"),
                _tr("chip_boxes", language, "I need custom boxes"),
                _tr("chip_labels", language, "I need labels")]
    if "sizes" in missing:
        return [_tr("chip_size_4x6", language, "Size 4x6 inches"),
                _tr("chip_size_mm", language, "Size 100x150mm"),
                _tr("chip_not_sure_size", language, "Not sure about size")]
    if "type" in missing:
        # Checked BEFORE style: both are in missing until the type
        # is answered, and the type chips must win while it is.
        return ["Corrugated", "Rigid", "Mailer", "Folding carton"]
    if "style" in missing:
        # Chips follow the product family, like _question() already
        # does: pouch styles under a box question were the "mylar
        # bag suggestions" in the Oct 29 live transcript.
        if "box" in (slots.get("product") or "").lower():
            return ["Mailer", "Tuck-end", "Rigid", "Folding carton"]
        return ["Flat", "Stand-up", "Flat-bottom"]
    if "finishes" in missing:
        return ["Matte", "Gloss", "Soft touch", "No preference"]
    if "quantity" in missing:
        return [_tr("chip_qty_1000", language, "1000 units"),
                _tr("chip_qty_5000", language, "5000 units"),
                _tr("chip_not_sure_qty", language, "Not sure about quantity")]
    if "skus" in missing:
        return ["1 design", "2 designs", "3 designs"]
    if "extras" in missing:
        return ["Zipper and tear notch", "No extras"]
    if "material" in missing:
        return ["Kraft", "No preference"]
    return [_tr("chip_moq", language, "What is the minimum order?"),
            _tr("chip_shipping", language, "Is shipping free?"),
            _tr("chip_refund", language, "What is your refund policy?")]


_OWN_DATA_Q = re.compile(
    r"what(?:'s| is) my (email|e-mail|mail|phone|number|name)\b"
    # An order/quote question must END on the field: "what is my
    # order status?" and "where is my order?" are tracking questions
    # for a past order and must still reach the existing-customer
    # handoff, not the draft-quote summary.
    r"|what(?:'s| is) my (order|quote|details)\s*[.?!]?\s*$"
    r"|\bmy (email|e-mail|mail|phone|number|name)\b[^.?!]*\?"
    r"|what (did you add|you added|did i give|did i share|have you added|did you save)\b"
    r"|which (email|phone|number|name)\b[^.?!]*\b(gave|shared|provided|sent)\b"
    r"|\bthe (email|phone|number|name)\b[^.?!]*\b(i gave|i shared|i provided)\b",
    re.IGNORECASE)
_OWN_DATA_FIELD = {"email": "email", "e-mail": "email", "mail": "email",
                   "phone": "phone", "number": "phone", "name": "name",
                   "order": "order", "quote": "order", "details": "order"}


_CANCEL_PATTERNS = re.compile(
    r"\bmy\s+mind\b[^.?!]{0,25}\bch[a-z]+nged\b"
    r"|\bch[a-z]+nged\s+my\s+mind\b"
    r"|\b(don'?t|dont|do not|no longer)\s+nee+d\b"
    r"|\b(don'?t|dont|do not)\s+want\b"
    r"|\bcancel\b|\bnever mind\b|\bforget it\b|\bnot interested\b",
    re.IGNORECASE)
# A field refusal is not a cancellation: "i dont need a zipper"
# refuses the extra, "i dont want to share my phone" refuses the
# contact field — neither cancels the quote.
_CANCEL_GUARD = re.compile(
    r"\b(zipper|tear\s*notch|notch|matte|gloss|soft\s*touch|kraft|foil|vinyl|"
    r"corrugated|cardboard|window|spout|handle|pet|plastic|paper|phone|email|"
    r"number|share|give|tell|personal|private|contact|call|message|inches|cm|mm|"
    r"size|style|finish|material|quantity|units|pcs)\b",
    re.IGNORECASE)


def is_cancellation(text: str) -> bool:
    """The visitor abandons the quote ("my mind changed", "i dont
    need", "cancel") — not a field refusal (guarded above) and not a
    bare "no" (which at confirmation means "not correct", not "go
    away"). Typo-tolerant: "chnaged", "neeed" still match."""
    if not text or _CANCEL_GUARD.search(text or ""):
        return False
    return bool(_CANCEL_PATTERNS.search(text or ""))


def _own_data_answer(message: str, slots: dict, contact: dict) -> str | None:
    """An answer about the VISITOR's own submitted info, from the
    session — never from the KB. "What is my email?" must return
    the email the visitor gave, not the company's Support@ address;
    "my email which i gave you?" must never return a boxes FAQ;
    "what you added?" must list what is stored, not the catalog.
    Returns None when the message is not an own-data question, so
    normal flow is untouched. A missing value is answered honestly
    ("I don't have it saved"), never with a KB fact. Question-
    shaped patterns only: "my email is bob@x.com" is a statement
    giving the email, not a question about it, and falls through
    to normal extraction."""
    m = _OWN_DATA_Q.search(message or "")
    if not m:
        return None
    _field_word = next((g for g in m.groups() if g), None)
    _key = (_field_word or "").lower()
    if _key in _OWN_DATA_FIELD:
        _field = _OWN_DATA_FIELD[_key]
        if _field == "order":
            _spec = _spec_parts(slots, None, None) if slots.get("product") else ""
            return f"Your order: {_spec}." if _spec else \
                "You don't have an order saved yet in this chat."
        _val = (contact or {}).get(_field)
        if _val and is_contact_value_usable(_field, _val):
            return f"Your {_field} is {_val}."
        return f"I don't have your {_field} saved in this chat yet."
    # The "what did you add" shape: list everything actually stored.
    _have = []
    _c = contact or {}
    if _c.get("name") and is_contact_value_usable("name", _c.get("name")):
        _have.append(f"name {_c['name']}")
    if _c.get("email") and is_contact_value_usable("email", _c.get("email")):
        _have.append(f"email {_c['email']}")
    if _c.get("phone") and is_contact_value_usable("phone", _c.get("phone")):
        _have.append(f"phone {_c['phone']}")
    _spec = _spec_parts(slots, None, None) if slots.get("product") else ""
    if _spec:
        _have.append(f"order: {_spec}")
    if not _have:
        return "I don't have anything saved for you yet in this chat."
    return "Here's what I have saved for you: " + "; ".join(_have) + "."


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


_SESSION_FALLBACK: dict = {}


def _load_session(store, session_id: str | None) -> dict:
    """Slots live in the store when it works; otherwise in-process,
    exactly like meta. The old code returned {} here when the store
    was None or down while meta still persisted in-process — so a
    multi-turn chat lost its slots but kept its answered-fields,
    and the script could "confirm" a spec that was never collected.
    Slots and meta must persist or fail together."""
    if not session_id:
        return {}
    if store is not None:
        try:
            return store.load(session_id) or {}
        except Exception:
            pass
    return _SESSION_FALLBACK.get(session_id, {})


def _save_session(store, session_id: str | None, slots: dict) -> None:
    if not session_id:
        return
    if store is not None:
        try:
            store.save(session_id, slots)
            return
        except Exception:
            pass
    _SESSION_FALLBACK[session_id] = slots


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
    "style": "Which style would you like?",
    "finishes": "Which finish would you prefer — matte, gloss or soft touch?",
    "quantity": "What quantity are you looking to order for your first run?",
    "per_design": "How many units per design do you need?",
    "skus": "How many designs or SKUs is that in total?",
    "extras": "Should I add a zipper and tear notch?",
    "material": "Any particular material or special feature in mind?",
    "name": "May I have your name?",
    "email": "Which email should I send the quote to?",
    "phone": "What phone number can the team reach you on?",
}


def _next_question_text(slots: dict, missing: list[str], language: str = "en") -> str:
    if not missing:
        return ""
    return _question(missing[0], slots, language)


def _missing_contact(meta: dict, contact: dict) -> list:
    """Missing contact fields, excluding ones the visitor declined or
    exhausted (old rule: a refusal retires the field at once — the
    field must not be asked a third time under another name)."""
    retired = set(meta.get("contact_retired") or [])
    wanted = [f["key"] for f in CONTACT_FIELDS if f["key"] not in retired]
    return missing_contact_fields(contact, wanted)


def _with_next_question(answer: str, slots: dict, missing: list[str], language: str = "en") -> str:
    q = _next_question_text(slots, missing, language)
    return f"{answer} {q}" if q else answer


# Suggestion answers, every word KB-grounded: jerky sizes and
# finishes from kb/products/beef-jerky-bags.md, food-box board
# weights and the food-and-beverage line from kb/products/boxes.md,
# coffee pouches from kb/products/pouches.md. Nothing here is
# invented for a use the KB does not cover.
_SUGGESTION_ANSWERS = {
    ("jerky", "mylar bag"):
        "For pieces of dry meat (beef jerky), we suggest food-grade mylar pouches "
        "with resealable zippers — popular sizes are 5x8+3 for snack retail (2-3 oz) "
        "and 6x9+3.5 for standard retail (3-5 oz).",
    ("jerky", "box"):
        "For beef jerky boxes, food boxes work — 14pt to 16pt lightweight, "
        "18pt to 20pt standard, 24pt heavy duty.",
    ("coffee", "mylar bag"):
        "For coffee, we suggest coffee pouches.",
    ("coffee", "box"):
        "For coffee, food and beverage boxes work — 14pt to 16pt lightweight, "
        "18pt to 20pt standard, 24pt heavy duty.",
    # Generic food (dry fruits, nuts, snacks...): no use-specific
    # page exists, so no sizes are named — only the grounded
    # category facts (food-grade mylar for food, food-box weights).
    ("food", "mylar bag"):
        "For food items like this, we suggest food-grade mylar pouches "
        "with resealable zippers.",
    ("food", "box"):
        "For food items like this, food boxes work — 14pt to 16pt lightweight, "
        "18pt to 20pt standard, 24pt heavy duty.",
}
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
        # Never cut mid-sentence: the old word cut left capability
        # replies ending in "(see facts/moq.md for context" with
        # the closing "notes)." dropped. Prefer the last sentence
        # end inside the window, else the last space.
        cut = t[:800]
        sent_end = max(cut.rfind(". "), cut.rfind(".\n"),
                       cut.rfind("! "), cut.rfind("? "))
        if sent_end > 600:
            cut = cut[:sent_end + 1]
        else:
            last_space = cut.rfind(" ")
            if last_space > 600:
                cut = cut[:last_space]
        return cut
    return t


_DIRECT_STOPWORDS = {
    "what", "where", "when", "how", "why", "who", "do", "does", "did",
    "can", "could", "will", "would", "is", "are", "was", "were", "you",
    "your", "we", "our", "the", "a", "an", "i", "me", "my", "it", "in",
    "on", "at", "to", "for", "of", "with", "about", "tell", "give",
    "please", "there", "here", "any", "us", "get", "got",
}


def _direct_answer(question: str, text: str) -> str:
    """Short answer to THIS question, from the grounded file.

    The old behaviour returned the file's whole first paragraph, so
    'where are you located?' dumped address + phone + email +
    channels + founded year in one reply. A visitor asks one thing
    and gets the best-matching sentence back, plus the next
    scoring sentence after it when one exists — that second
    sentence is what carries the completion of the answer
    ('two seconds' for sealing, 'team will confirm' for delivery
    abroad). The script question still follows. Sentences from
    the internal 'Context notes' guard section are never
    candidates, and neither is any 'do not …' guard sentence.
    Falls back to the first sentence when nothing scores.
    """
    cleaned = _clean_fact_text(text)
    # Cut at the first context-note marker, singular or plural:
    # support-hours.md writes "Context note (" and its guard
    # sentences otherwise outscore the real answer ("office hours"
    # appears twice in the guard, once in the answer itself).
    cleaned = cleaned.split("Context note")[0].strip()
    sentences = [s.strip() for s in re.split(SENTENCE_BREAK, cleaned)
                 if s.strip()]
    sentences = [s for s in sentences
                 if "do not" not in s.lower()
                 and "without sales confirmation" not in s.lower()
                 # Policy files open with a meta header line ("Refund
                 # and Returns summary, from the published page.") —
                 # a title, not an answer; it would otherwise outscore
                 # the real sentence by matching two topic words.
                 and "summary, from the" not in s.lower()]
    if not sentences:
        return ""
    qlow = question.lower()
    q = set(re.findall(r"[a-z]+", qlow)) - _DIRECT_STOPWORDS
    if "where" in qlow or any("locat" in w for w in q):
        q |= {"based", "address", "facility", "office", "headquarters",
              "headquarter"}
    if q & {"phone", "call", "number", "telephone"}:
        q |= {"phone", "telephone"}
    if q & {"email", "mail"}:
        q |= {"email"}
    if q & {"ship", "shipping", "deliver", "delivery"}:
        q |= {"shipping", "delivery", "ships", "deliver"}
    if q & {"price", "cost", "charge", "pricing"}:
        q |= {"price", "pricing"}
    if q & {"minimum", "moq", "order"}:
        q |= {"minimum", "moq", "units"}
    if q & {"refund", "return"}:
        q |= {"refund", "return"}
    if q & {"sample", "samples"}:
        q |= {"sample", "samples"}
    if q & {"payment", "payments", "pay", "accept"}:
        q |= {"payment", "payments", "accepted"}
    if q & {"time", "long", "turnaround", "take"}:
        q |= {"turnaround", "days"}
    # A country word means "outside the USA" even when the country
    # itself is not listed in the shipping file ("do you deliver to
    # Brazil?"): without this, the free-nationwide sentence
    # outscores the outside-USA caveat and Brazil gets told
    # shipping is free. USA words never trigger it (inside, not
    # outside).
    _countries = ("pakistan", "india", "china", "uk", "england", "canada",
                  "australia", "germany", "france", "uae", "dubai",
                  "bangladesh", "sri lanka", "nepal", "nigeria", "kenya",
                  "south africa", "brazil", "mexico", "japan", "korea",
                  "turkey", "saudi arabia", "qatar", "italy", "spain",
                  "netherlands", "europe")
    if any(re.search(rf"\b{re.escape(c)}\b", qlow) for c in _countries):
        q |= {"outside", "abroad", "country"}

    def _norm(words):
        # Plural-insensitive matching, applied to both sides:
        # returns/return, samples/sample, payments/payment all match.
        return {w[:-1] if len(w) > 3 and w.endswith("s") else w
                for w in words}

    q = _norm(q)
    # A number in a sentence only breaks ties when the question is
    # about numbers (price, time, quantity, phone): "3D Raised UV"
    # made the EXTRA finishes sentence outscore the main finishes
    # list for a plain finishes question (Oct 30). For other
    # questions the first best-scoring sentence wins, and the next
    # scoring sentence after it is appended as completion.
    _digit_matters = bool(q & {"price", "cost", "pricing", "time",
                               "turnaround", "days", "minimum", "moq",
                               "units", "many", "much", "quantity",
                               "long", "number", "phone", "call",
                               "telephone"})
    scored = []
    for s in sentences:
        words = _norm(set(re.findall(r"[a-z0-9]+", s.lower())))
        # Ties break toward the sentence carrying a number: policy,
        # time and price answers live in the numbered sentence, not
        # in a header line like "Refund and Returns summary".
        scored.append((s, (len(q & words),
                           _digit_matters and any(ch.isdigit() for ch in s))))
    best_idx, (best, best_score) = 0, (sentences[0], (-1, 0))
    for i, (s, score) in enumerate(scored):
        if score > best_score:
            best_idx, best, best_score = i, s, score
    if best_score[0] < 1:
        # Nothing in the file actually answers this question: lead
        # with the file's opening sentence (usually its summary)
        # instead of a sentence that merely carries a number —
        # "5-7 mil for sharp products" as an answer to "best
        # material for coffee" misleads more than it helps.
        result = sentences[0]
    else:
        result = best
        for s, score in scored[best_idx + 1:]:
            if score[0] >= 1:
                result = best + " " + s
                break
    # KB files wrap lines mid-sentence, so a reply could read "the
    # team\nwill confirm" and fail a plain substring check (and look
    # broken to a visitor). Collapse all whitespace in the answer.
    return " ".join(result.split())


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


_TYPE_FILES = {"box": "kb/products/boxes.md",
               "pouch": "kb/products/pouches.md",
               "mylar bag": "kb/products/pouches.md",
               "label": "kb/products/labels.md",
               "sticker": "kb/products/labels.md",
               "banner": "kb/products/banners.md",
               "business card": "kb/products/business-cards.md"}
# Types a visitor can pick from a chip (every one parses: corrugated
# is a material, the rest are styles).
_TYPE_CHIPS = {"box": ["Corrugated", "Rigid", "Mailer", "Folding carton"],
               "pouch": ["Stand-up", "Flat", "Flat-bottom"],
               "mylar bag": ["Stand-up", "Flat", "Flat-bottom"]}
# Type words a visitor can name, canonical value first, longest
# phrases first so "flat-bottom" never also counts as "flat".
_TYPE_VOCAB = {
    # Every item the bot's own type list offers must parse here:
    # "cosmetic boxes" was offered by the type question but had no
    # vocab entry, so the bot re-asked instead of storing it
    # (Oct 30 transcript). Same gap for CBD, pharmaceutical,
    # apparel and food and beverage.
    "box": [("folding carton", "folding carton"), ("folding", "folding carton"),
            ("tuck-end", "tuck-end"), ("tuck end", "tuck-end"),
            ("corrugated", "corrugated"), ("rigid", "rigid"),
            ("mailer", "mailer"), ("display", "display"),
            ("metalized", "metalized"), ("die-cut", "die-cut"),
            ("diecut", "die-cut"), ("gable", "gable"),
            ("cosmetic", "cosmetic"), ("cbd", "cbd"),
            ("pharmaceutical", "pharmaceutical"), ("apparel", "apparel"),
            ("food and beverage", "food and beverage"),
            ("food", "food and beverage")],
    "pouch": [("flat-bottom", "flat-bottom"), ("flat bottom", "flat-bottom"),
              ("stand-up", "stand-up"), ("stand up", "stand-up"),
              ("standup", "stand-up"), ("spout", "spout"),
              ("child-resistant", "child-resistant"), ("3-side", "flat"),
              ("flat", "flat")],
    "mylar bag": [("flat-bottom", "flat-bottom"), ("flat bottom", "flat-bottom"),
                  ("stand-up", "stand-up"), ("stand up", "stand-up"),
                  ("standup", "stand-up"), ("spout", "spout"),
                  ("child-resistant", "child-resistant"), ("3-side", "flat"),
                  ("flat", "flat")],
}


def _type_list_sentence(product: str) -> str:
    """The product file's type-list sentence ("Custom boxes include
    ..."), or "" when the file has no include sentence. This is the
    answer to a types question — never _direct_answer's best
    sentence, whose digit tie-break preferred board specs over the
    list (Oct 30 transcript)."""
    _path = _TYPE_FILES.get(product or "")
    if not _path:
        return ""
    try:
        _raw = open(_path, encoding="utf-8").read()
    except OSError:
        return ""
    _m = re.match(r"^---\n.*?\n---\n(.*)$", _raw, re.DOTALL)
    _text = _clean_fact_text((_m.group(1).strip() if _m else _raw.strip()))
    for _s in [s.strip() for s in re.split(SENTENCE_BREAK, _text) if s.strip()]:
        if "includ" in _s.lower():
            return _s
    return ""


def _named_types(text: str, product: str) -> list[str]:
    """Distinct type words named in the message, canonical values,
    for the product's family. Empty when the product has no type
    vocabulary (labels, banners, business cards). "flat-bottom"
    suppresses "flat": the hyphen is a word boundary, so "flat"
    would otherwise match inside "flat-bottom" and fake two types."""
    _out: list[str] = []
    for _phrase, _canon in _TYPE_VOCAB.get(product or "", []):
        if re.search(rf"\b{re.escape(_phrase)}\b", (text or "").lower()) \
                and _canon not in _out:
            _out.append(_canon)
    if "flat-bottom" in _out and "flat" in _out:
        _out.remove("flat")
    return _out


def _spec_parts(slots: dict, gave_up: list | None = None, qty_split: str | None = None) -> str:
    """The collected spec as one readable line for confirmations:
    product, size, style, finish, quantity (per design + total when
    multi-design, or the total when the visitor said "in total"),
    designs, extras, material — plus the fields the team still has
    to confirm, so the confirmation never lies by omission about
    what is still open."""
    parts = []
    if slots.get("product"):
        parts.append(str(slots.get("product")))
    if slots.get("sizes"):
        _sz = str(slots.get("sizes"))
        # A bare "4x6" never says which number is the width: the
        # bot's own size question asks "Width x height x depth",
        # so a bare size follows that order — but the confirmation
        # must SHOW the assumption, or the customer can never catch
        # it being backwards. Sizes that already carry their labels
        # (length/width words) are shown as-is.
        if "length" not in _sz.lower() and "width" not in _sz.lower():
            _n = len(re.findall(r"\d+(?:\.\d+)?", _sz))
            if _n >= 3:
                _sz = f"{_sz} (width x height x depth)"
            elif _n == 2:
                _sz = f"{_sz} (width x height)"
        parts.append(f"size {_sz}")
    if slots.get("type"):
        parts.append(f"{slots.get('type')} type")
    if slots.get("style") and slots.get("style") != "none":
        parts.append(f"{slots.get('style')} style")
    if slots.get("finishes") and slots.get("finishes") != "none":
        parts.append(f"{slots.get('finishes')} finish")
    try:
        n_designs = int(slots.get("skus", "1"))
    except (TypeError, ValueError):
        n_designs = 1
    if slots.get("quantity"):
        if n_designs > 1 and qty_split == "total":
            parts.append(f"{slots.get('quantity')} units total, {n_designs} designs")
        elif n_designs > 1:
            try:
                total = int(slots.get("quantity", "0")) * n_designs
            except (TypeError, ValueError):
                total = slots.get("quantity")
            parts.append(f"{slots.get('quantity')} units per design, {n_designs} designs "
                         f"(total {total} units)")
        else:
            parts.append(f"{slots.get('quantity')} units")
    if slots.get("extras") and slots.get("extras") != "none":
        parts.append(f"extras {slots.get('extras')}")
    if slots.get("material") and slots.get("material") != "none":
        parts.append(f"{slots.get('material')} material")
    # Unlisted qualifiers the visitor named ("wooden") are open
    # items, not part of the order: the confirmation must show them
    # as team-to-confirm, or the quote silently implies they are
    # included (Oct 30).
    if slots.get("notes"):
        parts.append(f"{slots.get('notes')} — team to confirm")
    text = ", ".join(parts)
    if gave_up:
        text += f". For {', '.join(gave_up)}, the team will confirm it with you directly"
    return text


def _below_min_note(slots: dict, language: str) -> str:
    """Below-minimum note for confirmations (old composer rule:
    never hand the rep a number nobody has answered)."""
    try:
        qty = int(float(str(slots.get("quantity", "0")).replace(",", "")))
    except (TypeError, ValueError):
        return ""
    if qty and qty < 1000 and guards.minimum_applies(slots.get("product")):
        return " " + _tr("below_min_note", language,
                         "Note: {qty} is below our usual minimum of 1000 per size — "
                         "the team will confirm the smaller run with you.", qty=qty)
    return ""


def _deterministic_reply(message: str, slots: dict, facts: list[dict], missing: list[str],
                         language: str = "en", gave_up: list | None = None,
                         qty_split: str | None = None) -> str:
    """No-LLM reply. Only uses OKF text and slot questions — it can
    never invent a price, a policy, or a fact.

    Order matters (old withAnswersBeforeQuestion): a fact question
    is answered FIRST, then the script question — never the other
    way round. An ORDER statement ("I need 2 banners") gets the next
    script question, not a fact chunk that merely mentions a keyword.
    """
    low = message.lower()
    is_fact_question = ("?" in message or any(w in low for w in _FACT_WORDS)
                        or bool(fact_topics_asked(message)))
    next_q = _next_question_text(slots, missing, language)
    if is_fact_question and not facts:
        # Old composer rule: never "I'll confirm/check" — either the
        # facts answer it or it goes in the quote.
        text = ("I don't want to give you a wrong answer on that — that detail "
                "is not in our published facts, so I'll include it in your quote "
                "for the team.")
        return f"{text} {next_q}" if next_q else text
    if facts and is_fact_question:
        text = _direct_answer(message, facts[0]["text"]) or \
            _fact_reply_text(facts[0]["text"])
        # Capability question about a real product ("Can you print
        # boxes?") deserves a Yes first, not a bare list. Restricted
        # to kb/products files, so a turnaround/policy question can
        # never be falsely turned into a Yes. REFERENCE, NOT
        # WHITELIST (Oct 29): the KB listing is not the limit of
        # what the company makes — a packaging company makes the
        # product family, so options the files do not name (PET
        # labels, a handle, a spout pouch in the gallery) still get
        # a Yes here; the open-question LLM path adds general
        # packaging detail. "Team will confirm" is reserved for
        # truly out-of-domain requests and company hard facts the
        # KB does not hold, never for a packaging option.
        is_capability = low.startswith(("can you", "do you", "can i", "could you"))
        if is_capability and "/products/" in facts[0]["source"] \
                and not text.lower().startswith("yes"):
            text = "Yes — " + (text[0].lower() + text[1:] if text else text)
        return f"{text} {next_q}" if next_q else text
    if missing:
        return next_q
    # Script complete and no fact question: ask for confirmation, not
    # a raw KB chunk. (The old fallback returned facts[0] here, which
    # was a whole file including its frontmatter — the ugliest reply
    # in the live transcript's no-LLM path.)
    if not missing:
        intro = _tr("confirm_intro", language, "Just to confirm — do you want")
        return (f"{intro} {_spec_parts(slots, gave_up, qty_split)}?"
                f"{_below_min_note(slots, language)}")
    if facts:
        return _direct_answer(message, facts[0]["text"]) or \
            _fact_reply_text(facts[0]["text"])
    return "Thanks — I have your details. A team member will confirm the quote shortly."


def _llm_reply(message: str, language: str, slots: dict, facts: list[dict],
               reply_to: str | None = None) -> str | None:
    """gpt-5-mini answer, or None if no key / call fails.

    REFERENCE, NOT WHITELIST (Oct 29): the KB chunks below are the
    reference for the company's offerings and the source of truth
    for its HARD facts (MOQ, turnaround, location, hours, payments,
    policies) — those override general knowledge and are copied
    verbatim. But packaging-domain questions (product types,
    materials, finishes, styles, uses, how things work) are answered
    from the model's own packaging knowledge too: the company's
    listings are a reference, not the limit of what it makes. Only
    company-specific facts absent from the KB (other locations,
    team details, exact prices, dates) are off-limits — those go to
    the team with the quote, never invented. The composer rules are
    ALSO enforced in code afterwards, because a prompt rule is
    followed "most of the time".
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
            "state quantity per design and the total. The facts below are your "
            "REFERENCE for what the company offers, and the source of truth for its "
            "hard facts (minimum order, turnaround, location, support hours, payments, "
            "policies) — state those exactly, copy numbers verbatim. For "
            "packaging-domain questions (product types, materials, finishes, styles, "
            "uses, how things work), use your own packaging knowledge freely and answer "
            "gracefully: the company's listings are a reference, not the limit of what "
            "it makes — a packaging company makes the product family. Never invent a "
            "company-specific fact (another location, team details, an exact price, a "
            "date): if it is not in the facts below, say the team will confirm it with "
            "the quote. Never state a price figure. Keep it short.\n"
            "SCRIPT (ask one question at a time, in this order): product, size, "
            "style (bags/boxes), finish, quantity, designs/SKUs, extras (bags only: "
            "zipper and tear notch), material. Never ask for a detail already "
            "collected, never ask two things at once, never repeat a question, "
            "never ask designs/SKUs for a plain (unprinted) order.\n"
            "ALWAYS answer the visitor's own question first, in one short sentence, "
            "then ask your one script question. A price question is answered "
            "'your quote will carry the pricing' — never a figure, never the "
            "minimum as the answer. Banners have no minimum — never state one "
            "for them. A below-minimum quantity is never refused: say we can look "
            "at it, state the usual minimum of 1000 per size, and carry on.\n"
            "NEVER: say you will prepare, get or send a quote; say you will "
            "confirm, check or find something out; say you cannot go on without "
            "something; ask about proofs, artwork files, PDFs, approval links, "
            "quote layout, delivery addresses or carriers (a rep sorts those out); "
            "hand the visitor's own question back to them.\n\n"
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


def _kb_first_sentence(topic: str) -> str | None:
    """First sentence of the KB answer for a fact topic, for the
    composer's answer-before-question repair."""
    try:
        facts = retrieve(topic_query(topic))
    except Exception:
        return None
    if not facts:
        return None
    text = _fact_reply_text(facts[0]["text"])
    first = re.split(SENTENCE_BREAK, text)[0].strip() if text else ""
    return first or None


def _perfect_reply(slots: dict, language: str = "en", gave_up: list | None = None,
                   qty_split: str | None = None) -> str:
    """Quote-ready message. Multi-design orders state per-design
    quantity and total, or the confirmation lies by omission."""
    intro = _tr("perfect_intro", language, "Perfect — your quote request is ready:")
    return (f"{intro} {_spec_parts(slots, gave_up, qty_split)}. "
            f"A team member will confirm the price and turnaround {when_the_team_replies()}."
            f"{_below_min_note(slots, language)}")


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
    # Session language (old replyLanguageFor): the language of the
    # CONVERSATION, not just this message. A Spanish visitor whose
    # second message is only "4x6 pulgadas" must not flip back to
    # English mid-quote — once a non-English language is detected,
    # it sticks, unless they explicitly switch to English.
    if language != "en":
        meta["language"] = language
    elif "in english" in low or "english please" in low:
        meta.pop("language", None)
    else:
        language = meta.get("language") or language
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
                                          "quote for", "buy",
                                          # Spanish order phrases: "Necesito
                                          # cajas" is an order, not a
                                          # confirmation answer.
                                          "necesito", "quiero", "quisiera"))

    def _intent_result(reply, handoff=None, suggestions=None, contact=None):
        # Old max-turns rule (12 AI messages): count bot replies here
        # and in the final branch; the contact flow is bounded by its
        # 3 fields x 2 asks, so it cannot hit the cap on its own.
        meta["ai_count"] = meta.get("ai_count", 0) + 1
        _save_session(store, session_id, prior)
        _save_meta(store, session_id, meta)
        _res = {"reply": reply, "language": language, "slots": prior,
                "missing": script_missing(prior, meta), "sources": [],
                "handoff": handoff, "llm_used": False,
                "suggestions": suggestions if suggestions is not None else []}
        # Callers that answer from stored data (own-data) carry the
        # contact through; other intent results keep the old shape.
        if contact is not None:
            _res["contact"] = contact
        return _res

    if is_looking_for_work(message) or chat_is_a_pitch([message]):
        return _intent_result(JOB_MESSAGE if is_looking_for_work(message) else PITCH_MESSAGE,
                              handoff="not_a_customer")
    # Bot-only question FIRST: 'are you a bot?' also matches the
    # human-request pattern, and the old bot used to hand those chats
    # over by mistake. Curiosity is not a request for somebody else.
    if asks_only_if_we_are_a_bot(message):
        return _intent_result(_with_next_question(ANSWER_TO_ARE_YOU_A_BOT, prior,
                                                 script_missing(prior, meta), language))
    if wants_a_person(message):
        return _intent_result("Of course — I am connecting you with a team member who can help directly.",
                              handoff="visitor_asked_for_human")
    # Trust, hostility and small talk, before retrieval: a "?" must
    # never turn "are you fake?" into a KB fact dump again. Harm
    # first ("you scammed me" is a complaint, not a quiz), then
    # lied-to, then trust questions, then plain small talk. All
    # guarded by not _is_order, so "thanks, I need 500 bags" still
    # flows into the order.
    if not _is_order and claims_harm(message):
        return _intent_result(HARM_ANSWER, handoff="existing_customer")
    if not _is_order and claims_we_lied(message):
        return _intent_result(LIED_ANSWER)
    if not _is_order and asks_about_trust(message):
        return _intent_result(_with_next_question(TRUST_ANSWER, prior,
                                                 script_missing(prior, meta), language))
    # Small talk only while the chat is open: after completion the
    # finished branch owns pleasantries (sign-off, never the close
    # again), and these branches run before it.
    # Soft dismissal first: "thanks though" contains "thanks", and
    # the plain thanks branch below would push the next script
    # question after a polite goodbye. Guarded like bye (an order
    # statement still wins: "thanks, but I want a bigger size").
    if not _is_order and not meta.get("complete") and is_dismissal(message):
        return _intent_result(BYE_ANSWER)
    if not _is_order and not meta.get("complete") and says_thanks(message):
        return _intent_result(_with_next_question(THANKS_ANSWER, prior,
                                                 script_missing(prior, meta), language))
    if not _is_order and not meta.get("complete") and says_bye(message):
        return _intent_result(BYE_ANSWER)
    if not _is_order and not meta.get("complete") and asks_how_are_you(message):
        return _intent_result(_with_next_question(HOW_ARE_YOU_ANSWER, prior,
                                                 script_missing(prior, meta), language))
    _named = rep_named_in(message, _session_rep(session_id))
    if _named:
        first = _named.split()[0]
        return _intent_result(f"Yes, {first} is on our team. I'm passing you to {first} now.",
                              handoff="visitor_asked")
    # Cancellation BEFORE everything that would re-ask: "no i dont
    # need now my mind chnaged" at confirmation used to fall through
    # to the main flow, which re-asked the confirmation — then the
    # 12-message cap bricked the chat and every later question got
    # a handoff (Oct 30 transcript). Cancelling clears the draft
    # and invites a fresh start, without pushing a new question.
    # A STOP ("NO I DONT WANT NOW") is not a cancellation: it keeps
    # its own "stop here" handling in the contact flow.
    if not meta.get("complete") and is_cancellation(message) \
            and not wants_to_stop(message):
        _save_session(store, session_id, {})
        _save_meta(store, session_id, {})
        return {
            "reply": "No problem at all — if you change your mind, just tell me what you need.",
            "language": language, "slots": {}, "missing": ["product"],
            "sources": [], "handoff": None, "llm_used": False,
            "suggestions": [],
        }
    # Own-data questions BEFORE the already-customer and catalog
    # branches: "what you added?" matched the catalog intent and
    # dumped the whole catalog, and "what is my order?" matched
    # already-customer and handed off (Oct 29 transcript). The
    # visitor's own info comes from the session, never from a KB
    # file. Mid-quote, the answer carries the next script question;
    # finished, it stands alone.
    _own = _own_data_answer(message, prior, meta.get("contact") or {})
    if _own is not None:
        if meta.get("complete"):
            return _intent_result(_own, contact=meta.get("contact") or {})
        _omissing = script_missing(prior, meta)
        _oq = _next_question_text(prior, _omissing, language)
        _oreply = f"{_own} {_oq}" if _oq else _own
        return _intent_result(_oreply,
                              suggestions=_suggestions(prior, _omissing, _oreply, language),
                              contact=meta.get("contact") or {})
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
        return _intent_result(_with_next_question(ANSWER_TO_A_CATALOG, prior,
                                                 script_missing(prior, meta), language))
    if not _is_order and asks_for_samples(message) and "?" not in message:
        # A sample REQUEST ('send me samples') is noted for the team;
        # a sample QUESTION ('do you offer samples?') falls through
        # to the KB fact answer below.
        return _intent_result(_with_next_question(ANSWER_TO_SAMPLES, prior,
                                                 script_missing(prior, meta), language))
    # A file shared mid-quote is an acknowledgment, not an answer:
    # note it for the team and carry on with the script question.
    # No _is_order guard on purpose — artwork shared while a size
    # was asked still needs the size re-asked, not silence.
    if shared_a_file(message):
        return _intent_result(_with_next_question(SHARED_FILE_ANSWER, prior,
                                                 script_missing(prior, meta), language))
    # A suggestion request is answered with a recommendation, not
    # the next script question. THE ARCHITECTURE FLIP (Oct 29):
    # deterministic maps can never cover "thousands of relevant
    # things" — a list is not understanding, and patching it one
    # word at a time never finishes. So understanding is the LLM's
    # job now (it reads meaning, including typos), and code keeps
    # only the guardrails: the product must be one of ours, facts
    # come from the KB, no price, no invented claim — the composer
    # validator enforces all of it, or the reply falls back. The
    # maps below are only the fast path for known uses and the
    # no-key fallback, never the ceiling.
    if asks_for_suggestion(message):
        _s_use = suggestion_use(message, meta.get("visitor_messages") or [])
        _s_prod = suggestion_product(message, prior.get("product"))
        _s_ans = _SUGGESTION_ANSWERS.get((_s_use, _s_prod)) if _s_use else None
        if _s_prod:
            prior["product"] = _s_prod
            meta.setdefault("answered_fields", [])
            if "product" not in meta["answered_fields"]:
                meta["answered_fields"].append("product")
            # A size stated inside the suggestion ("suggest me a
            # 4x6 bag for coffee") is stored, never re-asked.
            from .slots import _SIZE as _SIZE_RE
            _sm = _SIZE_RE.search(message)
            if _sm:
                prior["sizes"] = _sm.group(0).strip()
            else:
                _single = re.search(
                    r"\b\d+(?:\.\d+)?\s*(?:inches|inch|in\b|mm|cm)\b",
                    message, re.IGNORECASE)
                if _single:
                    prior["sizes"] = _single.group(0).strip()
            if prior.get("sizes") and "sizes" not in meta["answered_fields"]:
                meta["answered_fields"].append("sizes")
        if _s_ans:
            _s_reply = _with_next_question(_s_ans, prior,
                                           script_missing(prior, meta), language)
            meta["last_bot_question"] = _s_reply
            meta["last_asked"] = (script_missing(prior, meta) or [None])[0]
            return _intent_result(_s_reply)
        # Unmapped use: do NOT fall through to the bare script
        # question — that ignored the suggestion entirely. First
        # try the LLM with the KB leash + composer validation.
        _s_facts = retrieve(message)
        _s_llm = _llm_reply(message, language, prior, _s_facts,
                            reply_to=meta.get("last_bot_question"))
        if _s_llm and "__" not in _s_llm:
            _s_missing = script_missing(prior, meta)
            _s_next = _next_question_text(prior, _s_missing, language)
            try:
                _s_qty = int(float(str(prior.get("quantity", "0")).replace(",", "")))
            except (TypeError, ValueError):
                _s_qty = 0
            _s_ctx = {
                "visitor_text": message,
                "visitor_texts": visitor_messages,
                "visitor_asking": visitor_is_asking(message),
                "last_bot_text": meta.get("last_bot_question", ""),
                "slots": prior,
                "answered_fields": meta.get("answered_fields") or [],
                "contact": meta.get("contact") or {},
                "is_banner": is_banner_family(prior.get("product")),
                "is_plain": wants_plain_packaging(visitor_messages),
                "minimum_due": bool(_s_qty and _s_qty < 1000),
                "asked_price": asks_about_price(message),
                "asked_usual": asks_what_is_usual(message),
                "asked_arrived": asks_if_it_arrived(message),
                "unclear": False,
            }
            _s_fixed = fix_reply(_s_llm, _s_ctx, _s_next, _kb_first_sentence)
            if _s_fixed is not None:
                meta["ai_count"] = meta.get("ai_count", 0) + 1
                meta["last_bot_question"] = _s_fixed
                meta["last_asked"] = _s_missing[0] if _s_missing else None
                meta.setdefault("bot_replies", []).append(_s_fixed)
                meta["bot_replies"] = meta["bot_replies"][-20:]
                _save_session(store, session_id, prior)
                _save_meta(store, session_id, meta)
                return {"reply": _s_fixed, "language": language, "slots": prior,
                        "missing": script_missing(prior, meta),
                        "sources": [f["source"] for f in _s_facts],
                        "handoff": None, "llm_used": True, "suggestions": []}
        # No key, LLM failed, or the reply was unfixable: never
        # invent a suggestion — but never ignore the request
        # either. Show the product's own KB overview, then the
        # script question. Without a product word, fall through to
        # the normal flow (which asks the product).
        if _s_prod:
            _ov_raw = capability_fact(_s_prod)
            if _ov_raw:
                _s_missing = script_missing(prior, meta)
                _s_reply = _with_next_question(_fact_reply_text(_ov_raw), prior,
                                               _s_missing, language)
                meta["last_bot_question"] = _s_reply
                meta["last_asked"] = _s_missing[0] if _s_missing else None
                _save_session(store, session_id, prior)
                _save_meta(store, session_id, meta)
                return {"reply": _s_reply, "language": language, "slots": prior,
                        "missing": script_missing(prior, meta),
                        "sources": [capability_source(_s_prod)],
                        "handoff": None, "llm_used": False, "suggestions": []}
    if objects_to_the_price(message):
        return _intent_result(_with_next_question(ANSWER_TO_A_PRICE_OBJECTION, prior,
                                                 script_missing(prior, meta), language))
    if offers_a_phone_number(message):
        meta["awaiting_contact"] = True
        meta["last_asked"] = "phone"
        return _intent_result(YES_SEND_YOUR_NUMBER)
    if wants_it_in_the_chat(message) and meta.get("last_asked") == "email":
        meta["last_asked"] = "phone"
        meta.setdefault("asks", {})["email"] = MAX_ASKS
        return _intent_result(NO_EMAIL_THEN_PHONE)
    # A bare number answering a size question ("10" after "What size
    # do you need?") is NOT a quantity: storing it as quantity 10
    # silently corrupts the quote while the size stays missing.
    # Ask which unit the size is in; a visitor who meant quantity
    # says so ("10 units") and the normal quantity path stores it.
    _last_q = (meta.get("last_bot_question") or "").lower()
    if "size" in _last_q and "quantity" not in _last_q \
            and not prior.get("quantity") and not prior.get("sizes"):
        # A single dimension ("10 inches") is a size fragment, not
        # a quantity either: ask for the other dimension instead
        # of storing 10 as the order quantity.
        _single_dim = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*(inches?|in\b|mm|cm|feet|ft\b)",
            message.strip() or "", re.IGNORECASE)
        if _single_dim:
            return _intent_result(
                f"Got it — {_single_dim.group(1)} {_single_dim.group(2)} for the size — "
                "what is the other dimension (length x width)?")
        if re.fullmatch(r"[\d,\s.]+", message.strip() or ""):
            return _intent_result(f"Got it — {message.strip()} inches or mm for the size?")
    # A correction, not an answer ("bro i want boxes, you gave me
    # mylar bag suggestions"): the visitor restates the product and
    # complains about the last reply. The old flow treated this as
    # a statement, dumped the product file and re-asked the field —
    # no acknowledgement, same wrong chips. Acknowledge, re-align
    # to the product, and ask the pending field with correct chips.
    # Guarded tight: complaint words + product restatement + no
    # spec word (a style/finish/size in the message is new
    # information, and the normal flow must extract it).
    _prior_prod = (prior.get("product") or "").lower()
    _restates = ((_prior_prod == "box" and re.search(r"\bboxes?\b", low))
                 or ("mylar" in _prior_prod and re.search(r"\bmylar\b|\bbags?\b", low))
                 or ("label" in _prior_prod and re.search(r"\blabels?\b", low))
                 or ("banner" in _prior_prod and re.search(r"\bbanners?\b", low)))
    _complains = any(w in low for w in
                     ("wrong", "gave me", "suggestion", "not what", "i said",
                      "incorrect", "mistake"))
    _has_spec = bool(re.search(
        r"\b(mailer|tuck|rigid|folding|flat|stand-up|flat-bottom|matte|gloss|"
        r"soft touch|window|zipper|kraft)\b|\d", low))
    if _restates and _complains and not _has_spec and not meta.get("complete"):
        _plural = {"box": "boxes", "mylar bag": "mylar bags", "label": "labels",
                   "banner": "banners", "business card": "business cards"}.get(
                       prior.get("product") or "", prior.get("product") or "")
        _cmissing = script_missing(prior, meta)
        _cq = _next_question_text(prior, _cmissing, language)
        _cack = f"You're right — sorry about that. Let's stick to {_plural}."
        _creply = f"{_cack} {_cq}" if _cq else _cack
        meta["last_bot_question"] = _creply
        return _intent_result(_creply,
                              suggestions=_suggestions(prior, _cmissing, _creply, language))
    _start_over = low in ("start over", "new order", "start again", "reset",
                          "new quote", "start fresh")
    # Finished quote picked back up (old whatToDoWithFinishedChat /
    # closingLineFor): NOT a fresh enquiry. A pleasantry gets a
    # sign-off (never the same one twice), "did you email me" gets
    # "not yet", a question gets answered and the chat stays
    # finished, a new detail is noted. Only a new order statement
    # restarts (handled below), and start-over restarts too.
    if meta.get("complete") and not _is_order and not _start_over:
        # The finished branch used to drop the stored contact from
        # every return, so post-completion turns could not see the
        # email the visitor had given — own-data questions fell
        # back to KB facts (Oct 29 transcript).
        _fcontact = meta.get("contact") or {}
        _last_bot = meta.get("last_bot_question", "")
        if wants_to_stop(message):
            # A repeated refusal after the chat closed is a goodbye,
            # not a new detail to note.
            _sign = _tr("signoff_b", language, SIGN_OFFS[1]) \
                if _tr("signoff_a", language, SIGN_OFFS[0]) in _last_bot else \
                _tr("signoff_a", language, SIGN_OFFS[0])
            _save_session(store, session_id, prior)
            _save_meta(store, session_id, meta)
            return {"reply": _sign, "language": language, "slots": prior,
                    "missing": script_missing(prior, meta), "sources": [],
                    "handoff": None, "llm_used": False, "suggestions": [],
                    "contact": _fcontact}
        if is_pleasantry(message):
            _last_sign = _tr("signoff_b", language, SIGN_OFFS[1]) \
                if _tr("signoff_a", language, SIGN_OFFS[0]) in _last_bot else \
                _tr("signoff_a", language, SIGN_OFFS[0])
            _save_session(store, session_id, prior)
            _save_meta(store, session_id, meta)
            return {"reply": _last_sign, "language": language, "slots": prior,
                    "missing": script_missing(prior, meta), "sources": [],
                    "handoff": None, "llm_used": False, "suggestions": [],
                    "contact": _fcontact}
        if asks_if_it_arrived(message):
            if language in ("es", "ur-roman"):
                _reply = _tr("not_sent", language, NOT_SENT_YET)
            else:
                _reply = (f"Not yet — the quote has not gone out. "
                          f"You will have it {when_the_team_replies()}.")
            _save_session(store, session_id, prior)
            _save_meta(store, session_id, meta)
            return {"reply": _reply, "language": language, "slots": prior,
                    "missing": script_missing(prior, meta), "sources": [],
                    "handoff": None, "llm_used": False, "suggestions": [],
                    "contact": _fcontact}
        if "?" in message or visitor_is_asking(message):
            _facts = retrieve(message)
            _reply = (_direct_answer(message, _facts[0]["text"]) or
                      _fact_reply_text(_facts[0]["text"])) if _facts else \
                ("I don't want to give you a wrong answer on that — I'll include "
                 "it in your quote for the team.")
            _save_session(store, session_id, prior)
            _save_meta(store, session_id, meta)
            return {"reply": _reply, "language": language, "slots": prior,
                    "missing": script_missing(prior, meta),
                    "sources": [f["source"] for f in _facts],
                    "handoff": None, "llm_used": False, "suggestions": [],
                    "contact": _fcontact}
        # A finished chat + a new statement: only claim an addition
        # when something was actually added. The old code returned
        # "Noted — I've added that" for EVERY statement, including
        # "i gave you email" with no email in it (Oct 29 transcript).
        try:
            _extra = extract_from_message(without_template_blanks(message))
        except Exception:
            _extra = {}
        _slots2 = merge_slots(prior, _extra)
        _new_contact = {}
        _em = email_in(message)
        if _em and is_contact_value_usable("email", _em):
            _new_contact["email"] = _em
        _ph = phones_in(message)
        if _ph and is_contact_value_usable("phone", _ph[0]):
            _new_contact["phone"] = _ph[0]
        if _new_contact:
            _fcontact = dict(_fcontact)
            _fcontact.update(_new_contact)
            meta["contact"] = _fcontact
            _added = " and ".join(f"{k} {v}" for k, v in _new_contact.items())
            _nreply = f"Noted — I've added {_added} to your request."
        elif _extra:
            _nreply = _tr("noted", language, NOTED_AFTER_THE_QUOTE)
        else:
            # Nothing new in this message: say what is actually
            # stored instead of falsely claiming an addition.
            _nreply = _own_data_answer("what did you add?", _slots2, _fcontact)
        _save_session(store, session_id, _slots2)
        _save_meta(store, session_id, meta)
        return {"reply": _nreply,
                "language": language, "slots": _slots2,
                "missing": script_missing(_slots2, meta), "sources": [],
                "handoff": None, "llm_used": False, "suggestions": [],
                "contact": _fcontact}
    # Extraction must never crash the chat: a parser bug used to turn
    # into a 500 and the visitor saw "Message didn't send" (the
    # "15 thousand" case: float("15 thousand") raised ValueError).
    # Template blanks are stripped first: "Qty: __ Size: __" from an
    # ad pre-fill is not an answer to anything.
    try:
        extracted = extract_from_message(without_template_blanks(message))
    except Exception:
        extracted = {}
    # A question is never an answer (old isAQuestionNotAnAnswer):
    # "Do you make 4x6 mylar bags?" must not fill product or sizes —
    # it gets a capability answer, then the script asks product.
    # An order statement ("I need…") still extracts.
    if visitor_is_asking(message) and not _is_order:
        extracted = {}
    # Our own menu echoed back ("boxes, bags, or labels") is not an
    # answer either — re-ask instead of storing it.
    _menu_echo = is_our_own_menu(message.strip())
    if _menu_echo:
        extracted = {}
    # Model read for what code could not parse (old extractor's
    # second half), validated by code before anything is stored.
    # Expanded (Oct 30): code finding the WRONG thing used to block
    # the model entirely. Now the model also runs when code did not
    # fill the PENDING field, with the bot's question as context —
    # and it only ever fills gaps, never overwrites code.
    _bare_skus = False
    _pend_pre = (script_missing(prior, meta) or [None])[0]
    _llm: dict = {}
    _code_product = extracted.get("product")
    if (not extracted or (_pend_pre and _pend_pre not in extracted)) \
            and not visitor_is_asking(message) and not _menu_echo:
        try:
            _llm = llm_extract(message, asked=meta.get("last_bot_question"),
                               product=prior.get("product"))
            for _k, _v in _llm.items():
                if _k not in extracted:
                    extracted[_k] = _v
        except Exception:
            pass
    # An LLM product guess must never silently switch the quote:
    # code-found switches go through the switch clarification, and
    # a model guess from a message with no product word is not an
    # explicit switch (Oct 30: cards became a box style question).
    # Only when code found no product at all can the model's
    # product be the quote's product — and even then, never over
    # an existing quote's product.
    if _code_product is None and prior.get("product") \
            and _llm.get("product") and _llm["product"] != prior["product"]:
        extracted.pop("product", None)
    # When the model fills the PENDING field, its read of the
    # message is holistic, and code's quantity from that same
    # message is suspect: a code quantity the model did not return
    # is almost always a leaked dimension ("1 feet by 2 feet" ->
    # the code's quantity=1), not a real order. Drop it — a re-ask
    # is cheaper than a corrupt quote. And when the model DID
    # return a quantity stated explicitly ("500 units") while code
    # grabbed a leaked number instead, the explicit one wins.
    # Word-based code values (product, material, style) are never
    # touched: they don't leak from dimension spans.
    if _pend_pre and _pend_pre in _llm:
        if "quantity" in extracted and "quantity" not in _llm:
            extracted.pop("quantity", None)
        elif "quantity" in _llm and _llm["quantity"] != extracted.get("quantity"):
            _mq = str(_llm["quantity"])
            if re.search(rf"\b{re.escape(_mq)}\b\s*(?:units?|pcs|pieces)\b",
                         (message or "").lower()):
                extracted["quantity"] = _mq
    # Box type before style (Oct 30): a type word must land in the
    # type field, not leak into style ("rigid") or material
    # ("corrugated") — otherwise the type question is answered and
    # the quote still has no type. Exceptions: the style question
    # itself (a style word there is a style answer), a type already
    # stored, and questions (a question is never an answer).
    _tprod = extracted.get("product") or prior.get("product")
    if _tprod == "box" and not prior.get("type") and _pend_pre != "style" \
            and not (visitor_is_asking(message) and not _is_order):
        _twords = _named_types(message, "box")
        if _twords:
            extracted["type"] = _twords[0]
            if extracted.get("style") == _twords[0]:
                extracted.pop("style", None)
            if extracted.get("material") == _twords[0]:
                extracted.pop("material", None)
    # Bare number answering the designs question ("22" after "How
    # many designs?") is a design count, not a quantity: code's
    # quantity reader grabs it first and corrupts the quote (Oct 30
    # transcript: quantity became 22, then the split question asked
    # "22 of each of your 22 designs?"). Reinterpret it before
    # anything else sees it; the prior quantity survives via merge.
    if _pend_pre == "skus" and re.fullmatch(r"[\d,\s.]+", (message or "").strip() or ""):
        _num = re.sub(r"[,\s.]", "", message.strip())
        if _num.isdigit():
            extracted["skus"] = str(int(_num))
            extracted.pop("quantity", None)
            _bare_skus = True
    # Size-phrase guard (Oct 30): when the bot asked for size and
    # the visitor answers with a size phrase no pattern parsed
    # (spelled-out numbers, inch/foot marks, odd joins), no number
    # in it may become the quantity — the old failure was
    # quantity=1 + a size re-ask for "1 feet by 2 feet". Only fires
    # when sizes are still missing after extraction, so a real
    # quantity stated alongside a parsed size is untouched.
    if _pend_pre == "sizes" and "sizes" not in extracted and "quantity" in extracted:
        _size_flavored = (
            re.search(r"\d\s*(?:feet|foot|ft|inches|inch|in|mm|cm)\b", low)
            or re.search(r"\d\s*['’\"”″]", low)
            or re.search(r"\d\s*(?:x|×|by|\*)\s*\d", low)
            or re.search(r"\d\s*(?:oz|ounces?|ml|millilit(?:er|re)s?|g|gm|grams?|kg|l)\b", low)
            or re.search(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:feet|foot|ft|inches|inch|in|mm|cm)\b", low))
        if _size_flavored:
            extracted.pop("quantity", None)
    slots = merge_slots(prior, extracted)
    # A contact answer is not an order: while awaiting contact, a
    # phone number ("5551234567") must never overwrite the quantity
    # — digits answered to the phone question are a phone number,
    # not a new order. Only a real order statement merges while
    # awaiting contact (the name_is_order free turn below).
    if meta.get("awaiting_contact") and not _is_order:
        slots = prior
        extracted = {}
    # Track what the visitor actually said: script_missing must not
    # mistake merge defaults (skus="1", extras="none") for answers —
    # the old script asks "How many designs?" even though skus
    # defaults to 1, because the default is what the rep is handed,
    # not what the visitor said.
    if extracted:
        meta.setdefault("answered_fields", [])
        for _k in extracted:
            if _k not in meta["answered_fields"]:
                meta["answered_fields"].append(_k)
    # Plain packaging: no designs exist, so skus is 1 and never asked.
    if wants_plain_packaging(visitor_messages):
        slots["skus"] = "1"
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
    _phone_volunteered = False
    for _ph in phones_in(message):
        if is_contact_value_usable("phone", _ph):
            contact["phone"] = _ph
            _phone_volunteered = True
            break
    meta["contact"] = contact
    # Same class of bug mid-quote: "my number is 5551234567" shares a
    # phone number, not a quantity. When a phone number was just
    # stored from this message and the message carries no quantity
    # wording, the quantity slot must not move this turn.
    if _phone_volunteered and not re.search(r"\b(units?|pieces?|pcs|qty|quantity|order)\b", low):
        if prior.get("quantity"):
            slots["quantity"] = prior["quantity"]
        else:
            slots.pop("quantity", None)
    # A bare unit answers a unit question ('mm' after 'inches, cm or
    # mm?'): put it onto the size in code, like the old bot did.
    _unit = unit_answer(message)
    if _unit and slots.get("sizes"):
        slots["sizes"] = apply_unit_answer(slots["sizes"], _unit)
    # "Stop everything" beats any pending question. The old decline
    # list only retired one field, so "NO I DONT WANT NOW" was
    # answered with the email question, and "I SAID I DONT WANT
    # NOW" — which matched no decline pattern at all — was answered
    # with the email question AGAIN. A stop now closes the flow
    # once, gracefully, and never re-asks. Mid-quote it just pauses
    # the script: the visitor's next message continues it.
    if wants_to_stop(message) and not _is_order and not extracted:
        if meta.get("awaiting_contact"):
            meta["awaiting_contact"] = False
            meta["complete"] = True
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {
                "reply": ("No problem at all — I'll stop here. Your request is saved "
                          "in this chat, and the team will follow up with you here "
                          f"{when_the_team_replies()}. Just come back anytime."),
                "language": language, "slots": slots,
                "missing": missing_fields(slots), "sources": _slot_sources(slots),
                "handoff": "complete_no_contact", "llm_used": False,
                "suggestions": [], "contact": contact,
            }
        if slots:
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {
                "reply": ("Got it — I'll stop asking. Your details so far are saved "
                          "here; just say the word anytime you want to continue."),
                "language": language, "slots": slots,
                "missing": script_missing(slots, meta),
                "sources": _slot_sources(slots), "handoff": None, "llm_used": False,
                "suggestions": [],
            }

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
                # "My name is Abdullah" answers with a name, not with
                # the sentence: extract it, so the sentence itself is
                # never stored as the name.
                _m = re.search(r"\bmy name is\s+(.+)$", message.strip(), re.IGNORECASE)
                _candidate = (_m.group(1).strip(" .!") if _m else message.strip()) or None
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
                _q = _contact_question(_next, language)
                if language == "en" and repeats_the_question(_q, meta.get("last_bot_question", "")):
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
                # it below, keep the contact question pending. But a
                # bare spec word ("kraft") is not a question — the
                # old "free" fall-through re-showed the confirmation
                # and the email was never re-asked. Re-ask the field.
                if not visitor_is_asking(message) and "?" not in message:
                    meta["last_asked"] = _field
                    _save_session(store, session_id, slots)
                    _save_meta(store, session_id, meta)
                    return {
                        "reply": _contact_question(_field, language), "language": language,
                        "slots": slots, "missing": missing_fields(slots),
                        "sources": _slot_sources(slots), "handoff": None,
                        "llm_used": False, "suggestions": [], "contact": contact,
                    }
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
                    # The close must describe the contact actually
                    # stored: the old hardcoded "I don't have an
                    # email or phone number" lied when an email HAD
                    # been given and only the phone was refused
                    # (Oct 29 transcript). Reachable channels only,
                    # validated, never a stored-but-invalid value.
                    _reach = []
                    if contact.get("email") and is_contact_value_usable(
                            "email", contact.get("email")):
                        _reach.append(f"at {contact['email']}")
                    if contact.get("phone") and is_contact_value_usable(
                            "phone", contact.get("phone")):
                        _reach.append(f"on {contact['phone']}")
                    if _reach:
                        _close = ("Thanks — I have your order. Our team will follow up "
                                  f"with you {' and '.join(_reach)}. "
                                  f"They will confirm the price and turnaround {when_the_team_replies()}.")
                    else:
                        _close = ("Thanks — I have your order. Since I don't have an email or "
                                  "phone number, our team will follow up with you here in this chat. "
                                  f"They will confirm the price and turnaround {when_the_team_replies()}.")
                    _save_session(store, session_id, slots)
                    _save_meta(store, session_id, meta)
                    return {
                        "reply": _close,
                        "language": language, "slots": slots, "missing": missing_fields(slots),
                        "sources": _slot_sources(slots), "handoff": "complete_no_contact",
                        "llm_used": False, "suggestions": [], "contact": contact,
                    }
                if _next != _field:
                    meta["last_asked"] = _next
                    _q = _contact_question(_next, language)
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
                    "reply": _contact_question(_field, language), "language": language,
                    "slots": slots, "missing": missing_fields(slots),
                    "sources": _slot_sources(slots), "handoff": None,
                    "llm_used": False, "suggestions": [], "contact": contact,
                }
    # --- New product mid-quote (Oct 30 transcript): a fresh order
    # statement for a DIFFERENT product used to merge silently into
    # the pending quote (banner + the label quote's finish/qty = a
    # frankenstein confirmation). Two cases:
    #  (a) correction phrasing ("the labels should be stickers"):
    #      update the product at once, acknowledge, continue;
    #  (b) plain new order ("I need a vinyl banner"): ask first —
    #      switching discards the pending quote, so the visitor
    #      confirms the switch before anything is lost.
    # A message that merely ANSWERS the pending field (a style chip
    # that is also a product word) is never a switch.
    _ps = meta.get("pending_switch")
    if _ps and not meta.get("complete") and not meta.get("awaiting_contact"):
        _ps_new = _ps["product"]
        _ps_old = prior.get("product") or ""
        _to_new = ("switch" in low or "cambiar" in low
                   or low.strip() in ("yes", "yeah", "yep", "sure", "ok", "okay", "sí", "si")
                   or extracted.get("product") == _ps_new)
        _to_old = ("keep" in low or "mantener" in low
                   or low.strip() in ("no", "nope", "nah")
                   or (extracted.get("product") and extracted.get("product") == _ps_old))
        if _to_new and not _to_old:
            _held = _ps["slots"]
            _nslots = merge_slots({}, _held)
            meta.pop("pending_switch", None)
            meta["answered_fields"] = [k for k in _held]
            meta["gave_up"] = []
            meta["qty_split"] = None
            meta["last_asked"] = None
            _nmiss = script_missing(_nslots, meta)
            _nq = _next_question_text(_nslots, _nmiss, language)
            _nreply = _tr("switch_done", language, "Got it — switching to {new}.",
                          new=_ps_new) + (f" {_nq}" if _nq else "")
            _save_session(store, session_id, _nslots)
            _save_meta(store, session_id, meta)
            return {"reply": _nreply, "language": language, "slots": _nslots,
                    "missing": _nmiss, "sources": _slot_sources(_nslots),
                    "handoff": None, "llm_used": False,
                    "suggestions": _suggestions(_nslots, _nmiss, _nreply, language)}
        if _to_old:
            meta.pop("pending_switch", None)
            _omiss = script_missing(prior, meta)
            _oq3 = _next_question_text(prior, _omiss, language)
            _oreply3 = _tr("switch_keep", language, "No problem — keeping the {old} quote.",
                           old=_ps_old) + (f" {_oq3}" if _oq3 else "")
            _save_session(store, session_id, prior)
            _save_meta(store, session_id, meta)
            return {"reply": _oreply3, "language": language, "slots": prior,
                    "missing": _omiss, "sources": _slot_sources(prior),
                    "handoff": None, "llm_used": False,
                    "suggestions": _suggestions(prior, _omiss, _oreply3, language)}
        _old_pending = (script_missing(prior, meta) or [None])[0]
        if _old_pending and _old_pending in extracted:
            # An answer to the old quote's pending field is an
            # implicit keep: drop the switch state, normal flow
            # handles the answer.
            meta.pop("pending_switch", None)
        # Anything else (a question, an unrelated message): the
        # switch stays open, normal flow answers it.
    elif not meta.get("complete") and not meta.get("awaiting_contact") \
            and prior.get("product"):
        # Correction first: the target comes from the phrase itself,
        # NOT from extraction — extraction returns the FIRST product
        # word in the message, so "the labels should be stickers"
        # extracts "label", the very thing being corrected.
        _corr = None
        if "instead of" in low:
            _seg = low.split("instead of", 1)[1].split(",")[-1]
            _corr = _find(_seg, _PRODUCTS)
        if _corr is None:
            _cm = re.search(
                r"(?:should be|make it|change (?:it )?to|switch to)"
                r"\s+(?:a\s+|an\s+|the\s+)?([a-z][a-z\- ]*?)"
                r"(?:\s+for\b|[.!?]|$)",
                low)
            _corr = _find(_cm.group(1), _PRODUCTS) if _cm else None
        if _corr and _corr != prior["product"]:
            slots["product"] = _corr
            if "product" not in meta.setdefault("answered_fields", []):
                meta["answered_fields"].append("product")
            _cmiss = script_missing(slots, meta)
            if not _cmiss:
                _creply = (_tr("switch_done", language, "Got it — switching to {new}.",
                               new=_corr)
                           + " Just to confirm — do you want "
                           + _spec_parts(slots, meta.get("gave_up") or [],
                                         meta.get("qty_split")) + "?")
            else:
                _cq2 = _next_question_text(slots, _cmiss, language)
                _creply = _tr("switch_done", language, "Got it — switching to {new}.",
                              new=_corr) + (f" {_cq2}" if _cq2 else "")
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {"reply": _creply, "language": language, "slots": slots,
                    "missing": _cmiss, "sources": _slot_sources(slots),
                    "handoff": None, "llm_used": False,
                    "suggestions": _suggestions(slots, _cmiss, _creply, language)}
        _pend_pre2 = (script_missing(prior, meta) or [None])[0]
        if extracted.get("product") and extracted["product"] != prior["product"] \
                and not (_pend_pre2 and _pend_pre2 in extracted) and _is_order:
            meta["pending_switch"] = {"product": extracted["product"],
                                      "slots": dict(extracted)}
            _save_session(store, session_id, prior)
            _save_meta(store, session_id, meta)
            return {"reply": _tr("switch_check", language,
                                 "Just to check — you were getting {old} — "
                                 "do you want to switch to {new}, or keep the {old} quote?",
                                 old=prior["product"], new=extracted["product"]),
                    "language": language, "slots": prior,
                    "missing": script_missing(prior, meta), "sources": _slot_sources(prior),
                    "handoff": None, "llm_used": False,
                    "suggestions": [f"Switch to {extracted['product']}",
                                    f"Keep {prior['product']}"]}
    # Two types named in one message ("Corrugated Boxes, Rigid
    # Boxes") are not a choice: storing both (rigid style +
    # corrugated material) and jumping to size skips the
    # confirmation the visitor expects (Oct 30 transcript). Ask
    # which one, store neither from this message — the type fields
    # revert to what the quote had before it.
    _mt_prod = extracted.get("product") or prior.get("product") or slots.get("product")
    _mt = _named_types(message, _mt_prod) if _mt_prod else []
    if len(_mt) >= 2 and not visitor_is_asking(message) and "?" not in message \
            and not meta.get("awaiting_contact"):
        for _f in ("style", "material", "type"):
            if _f in extracted and slots.get(_f) in _mt:
                if prior.get(_f) is not None:
                    slots[_f] = prior[_f]
                else:
                    slots.pop(_f, None)
                if _f not in prior:
                    meta["answered_fields"] = [a for a in meta.get("answered_fields", [])
                                               if a != _f]
        _mt_names = " or ".join(_mt)
        _mt_chips = [c[0].upper() + c[1:] for c in _mt]
        _mt_reply = f"Which type would you like — {_mt_names}?"
        meta["last_bot_question"] = _mt_reply
        meta.setdefault("bot_replies", []).append(_mt_reply)
        meta["bot_replies"] = meta["bot_replies"][-20:]
        _save_session(store, session_id, slots)
        _save_meta(store, session_id, meta)
        return {"reply": _mt_reply, "language": language, "slots": slots,
                "missing": script_missing(slots, meta),
                "sources": _slot_sources(slots), "handoff": None, "llm_used": False,
                "suggestions": _mt_chips}
    if _start_over:
        _save_session(store, session_id, {})
        _save_meta(store, session_id, {})
        return {
            "reply": "Sure — starting fresh. What product are you looking for?",
            "language": language, "slots": {}, "missing": ["product"],
            "sources": [], "handoff": None, "llm_used": False,
            "suggestions": _suggestions({}, ["product"], language=language),
        }

    # An unlisted qualifier inside an order ("i need wodden ones"
    # for cards): the quote continues with the known product, but
    # the visitor's qualifier must not vanish silently (Oct 30: the
    # cards quote became a box style question). Note it once per
    # product, then ask the pending question.
    if not visitor_is_asking(message) and not meta.get("awaiting_contact") \
            and slots.get("product"):
        _oquals = unlisted_qualifiers(message, slots["product"])
        _noted = set(meta.get("qualifier_noted") or [])
        _new_quals = [q for q in _oquals
                      if f"{slots['product']}:{q}" not in _noted]
        if _new_quals:
            meta["qualifier_noted"] = sorted(
                _noted | {f"{slots['product']}:{q}" for q in _new_quals})
            _pnotes = sorted(q.split(":", 1)[1] for q in meta["qualifier_noted"]
                             if q.startswith(f"{slots['product']}:"))
            slots["notes"] = ", ".join(_pnotes)
            _qmissing = script_missing(slots, meta)
            _qq = _next_question_text(slots, _qmissing, language)
            _qreply = qualifier_caveat(slots["product"], _new_quals) \
                + (f" {_qq}" if _qq else "")
            meta["last_bot_question"] = _qreply
            meta.setdefault("bot_replies", []).append(_qreply)
            meta["bot_replies"] = meta["bot_replies"][-20:]
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {"reply": _qreply, "language": language, "slots": slots,
                    "missing": script_missing(slots, meta),
                    "sources": _slot_sources(slots), "handoff": None,
                    "llm_used": False,
                    "suggestions": _suggestions(
                        slots, script_missing(slots, meta),
                        language=language)}
    # Confirmation chips must actually work: "Change quantity" clears
    # that slot and re-asks it, instead of the bot treating the tap
    # as a new message and repeating the confirmation.
    if "change quantity" in low:
        slots.pop("quantity", None)
        _save_session(store, session_id, slots)
        return {
            "reply": _question("quantity", slots, language), "language": language, "slots": slots,
            "missing": script_missing(slots, meta), "sources": _slot_sources(slots),
            "handoff": None, "llm_used": False,
            "suggestions": _suggestions(slots, ["quantity"], language=language),
        }
    if "change size" in low:
        slots.pop("sizes", None)
        _save_session(store, session_id, slots)
        return {
            "reply": _question("sizes", slots, language), "language": language, "slots": slots,
            "missing": script_missing(slots, meta), "sources": _slot_sources(slots),
            "handoff": None, "llm_used": False,
            "suggestions": _suggestions(slots, ["sizes"], language=language),
        }
    if low in ("yes", "yes, that's correct", "yes thats correct",
               "yes, that's right", "confirm", "confirmed", "correct") \
            and script_complete(slots, meta):
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
        _gave_up = meta.get("gave_up") or []
        if _next_contact is None and has_reachable_contact(_contact):
            meta["awaiting_contact"] = False
            meta["complete"] = True
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {
                "reply": _perfect_reply(slots, language, _gave_up, meta.get("qty_split")) + " " + get_chat_complete_message(),
                "language": language, "slots": slots,
                "missing": script_missing(slots, meta), "sources": _slot_sources(slots),
                "handoff": "complete", "llm_used": False, "suggestions": [],
                "contact": _contact,
            }
        # Old script order: quote details first, contact after. The
        # confirmation summary stays, then the first contact question.
        meta["awaiting_contact"] = True
        meta["last_asked"] = _next_contact or "name"
        _q = _contact_question(meta["last_asked"], language)
        meta["last_bot_question"] = _q
        _save_session(store, session_id, slots)
        _save_meta(store, session_id, meta)
        return {
            "reply": _perfect_reply(slots, language, _gave_up, meta.get("qty_split")) + " " + _q,
            "language": language, "slots": slots,
            "missing": script_missing(slots, meta), "sources": _slot_sources(slots),
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
                "suggestions": _suggestions(slots, script_missing(slots, meta), language=language),
            }
    if reason and reason != "policy_question":
        _save_session(store, session_id, slots)
        return {
            "reply": "Of course — I am connecting you with a team member who can help directly.",
            "language": language, "slots": slots,
            "missing": script_missing(slots, meta), "sources": [],
            "handoff": reason, "llm_used": False,
            "suggestions": _suggestions(slots, script_missing(slots, meta), language=language),
        }

    # Attribute questions name their product ("box materials?",
    # "which materials do you use in Envelopes??"). Two cases:
    # - Unknown product (envelopes): retrieval would serve another
    #   product's file as if it were the answer (box materials for
    #   an envelopes question, Oct 30), and the live model composes
    #   generic materials as if they were ours. Say so plainly and
    #   do NOT funnel into a quote.
    # - Known product, no quote yet: like the types branch, the
    #   question names the product, so store it — answering box
    #   materials and then asking "what product?" is the old
    #   annoyance. Never overrides an existing quote's product: a
    #   cross-family question keeps the quote.
    _attr_word = re.search(r"\b(materials?|finish(?:es)?|styles?|types?)\b", low)
    # Questions only: a finish VALUE ("matte finish") or a stated
    # material ("coffee material is mylar") is an answer, not an
    # attribute question — firing here broke both (Oct 30).
    if _attr_word and ("?" in message or visitor_is_asking(message)):
        # Bare "mylar" is a family word, not an alias — "mylar
        # finishes" is a pouch question, not an unknown product.
        # And a typo'd product ("buissness cards") must count as
        # known: the old block echoed the typo as a fake product
        # ("Buissness aren't a listed product", Oct 30). fuzzy
        # matching is the same fallback the capability branch uses
        # for "lables".
        _fuzzy_prod = None
        try:
            _fuzzy_prod = fuzzy_product(low)
        except Exception:
            _fuzzy_prod = None
        _known = bool(re.search(r"\bmylar\b", low)) or _fuzzy_prod is not None or any(
            re.search(rf"\b{re.escape(a)}\b", low)
            for _, _aliases in _PRODUCTS for a in _aliases)
        if not _known:
            _tm = re.search(r"\b(?:materials?|finish(?:es)?|styles?|types?)\b"
                            r".*?\b(?:in|for|of)\b\s+([a-z]+)", low) \
                or re.search(r"\b([a-z]+)\s+(?:materials?|finish(?:es)?|styles?|types?)\b",
                             low)
            if _tm:
                _tgt = _tm.group(1)
                # The word before the attribute is often the question
                # word itself ("what finishes") — that is no target.
                _tgt_stop = {"what", "which", "who", "where", "when", "why",
                             "how", "do", "you", "your", "our", "any", "all",
                             "the", "a", "an", "this", "that", "it", "offer",
                             "offers", "available", "best"}
                # A use ("coffee", "candles") is grounded, not a
                # product: "material for coffee" is a mylar answer,
                # never a team-confirm about coffee (Oct 30).
                from .intents import _SUGGEST_USES
                _use_words = {k for _keys, _ in _SUGGEST_USES for k in _keys}
                _use_words |= {"food", "candles", "candle"}
                _sing = _tgt[:-1] if _tgt.endswith("s") and len(_tgt) > 3 else _tgt
                if _tgt not in _tgt_stop and _tgt not in _use_words \
                        and _sing not in _use_words \
                        and not any(_sing == a or _tgt == a
                                    for _, _aliases in _PRODUCTS for a in _aliases):
                    _plural = _tgt.endswith("s")
                    _ureply = (
                        f"{_tgt[0].upper() + _tgt[1:]} {'are' if _plural else 'is'}n't "
                        f"a listed product with published {_attr_word.group(1)} — "
                        f"the team can confirm whether we make {_tgt} and in what "
                        f"{_attr_word.group(1)}. We list boxes, bags, pouches, "
                        f"labels, stickers, business cards and banners — did you "
                        f"mean one of those?")
                    _save_session(store, session_id, slots)
                    _save_meta(store, session_id, meta)
                    return {"reply": _ureply, "language": language, "slots": slots,
                            "missing": script_missing(slots, meta), "sources": [],
                            "handoff": None, "llm_used": False,
                            "suggestions": _suggestions(
                                slots, script_missing(slots, meta),
                                language=language)}
        elif not slots.get("product"):
            _best = None
            for _canon, _aliases in _PRODUCTS:
                for _al in _aliases:
                    if re.search(rf"\b{re.escape(_al)}\b", low):
                        if _best is None or len(_al) > len(_best[1]):
                            _best = (_canon, _al)
            if _best is None and _fuzzy_prod:
                _best = (_fuzzy_prod, _fuzzy_prod)
            if _best is None and re.search(r"\bmylar\b", low):
                _best = ("mylar bag", "mylar")
            if _best:
                slots["product"] = _best[0]
                meta.setdefault("answered_fields", [])
                if "product" not in meta["answered_fields"]:
                    meta["answered_fields"].append("product")
    if not facts:
        facts = retrieve(message)
    # Product family of the chosen product, for the two guards
    # below. _named_families = families the message itself names:
    # naming another family ("what about box materials?" mid-bag-
    # quote) disables both guards, so a cross-family question
    # still reaches the other family's facts.
    _prod = slots.get("product")
    _fam_map = {"mylar bag": ("pouches", "mylar"), "pouch": ("pouches", "mylar"),
                "bag": ("pouches", "mylar"), "stand-up pouch": ("pouches", "mylar"),
                "flat pouch": ("pouches", "mylar"), "flat-bottom pouch": ("pouches", "mylar"),
                "box": ("boxes",), "label": ("labels",), "sticker": ("labels",),
                "business card": ("business-cards",), "banner": ("banners",)}
    _fam_tokens = _fam_map.get(_prod) if _prod else None
    _prod_family = ("pouch" if _prod in ("mylar bag", "pouch", "bag", "stand-up pouch",
                                         "flat pouch", "flat-bottom pouch")
                    else _prod)
    _named_families = set()
    for _alias, _alias_fam in (("box", "box"), ("boxes", "box"),
                               ("mylar", "pouch"), ("pouch", "pouch"),
                               ("pouches", "pouch"), ("bag", "pouch"),
                               ("bags", "pouch"), ("label", "label"),
                               ("labels", "label"), ("sticker", "label"),
                               ("stickers", "label"), ("banner", "banner"),
                               ("business card", "business card")):
        if re.search(rf"\b{_alias}\b", low):
            _named_families.add(_alias_fam)
    _same_family_only = bool(_fam_tokens and (not _named_families
                                              or _named_families == {_prod_family}))
    # RETRIEVAL VALIDATION (Oct 29, the code-level answer to SRAG):
    # with a product chosen, facts from ANOTHER product's files are
    # dropped when same-family facts exist — "what styles do you
    # have?" ranked pouches-mylar-styles FIRST for a box visitor,
    # which is how mylar types reached a box answer. Neutral facts
    # (policies, sizes, MOQ — no family token in the path) always
    # survive, and when no same-family fact exists the original
    # order stands, so a general question never loses its answer.
    if _same_family_only:
        _ALL_FAMILY_TOKENS = ("pouches", "mylar", "boxes", "labels",
                              "banners", "business-cards")
        if any(t in f["source"] for f in facts for t in _fam_tokens):
            facts = [f for f in facts
                     if any(t in f["source"] for t in _fam_tokens)
                     or not any(t in f["source"] for t in _ALL_FAMILY_TOKENS)]
    # Product-scoped answers: with a product already chosen, an
    # attribute question (material/style/finish) must not be
    # answered from another product's file — "what material is best
    # for coffee?" with mylar bags chosen once came back with BOX
    # materials. Re-rank, never filter: if no same-product fact
    # exists, the original order stands.
    if _prod and re.search(r"\b(?:materials?|finish(?:es)?|styles?)\b", low):
        if _same_family_only:
            facts = sorted(facts, key=lambda f: 0
                           if any(t in f["source"] for t in _fam_tokens) else 1)
            # Re-ranking cannot help when NO same-product fact was
            # retrieved at all (keyword search returned only the
            # other product's files). Then fetch the family's own
            # attribute file directly, so the answer still comes
            # from the right product instead of the wrong one.
            if not any(t in f["source"] for f in facts for t in _fam_tokens):
                _attr_kind = ("material" if "material" in low else
                              "finish" if "finish" in low else "style")
                _attr_files = {
                    "material": {"pouch": "kb/materials/pouches-mylar-materials-finishes.md",
                                 "box": "kb/materials/boxes-campaign-materials.md",
                                 "label": "kb/products/labels.md",
                                 "business card": "kb/products/business-cards.md",
                                 "banner": "kb/products/banners.md"},
                    "style": {"pouch": "kb/products/pouches-mylar-styles.md",
                              "box": "kb/products/boxes-campaign-styles.md",
                              "label": "kb/products/labels.md",
                              "business card": "kb/products/business-cards.md",
                              "banner": "kb/products/banners.md"},
                    "finish": {"pouch": "kb/materials/pouches-mylar-materials-finishes.md",
                               "box": "kb/materials/finishes.md",
                               "label": "kb/products/labels.md",
                               "business card": "kb/products/business-cards.md",
                               "banner": "kb/products/banners.md"},
                }[_attr_kind].get(_prod_family)
                if _attr_files:
                    try:
                        _raw = open(_attr_files, encoding="utf-8").read()
                        _m = re.match(r"^---\n.*?\n---\n(.*)$", _raw, re.DOTALL)
                        facts = [{"source": _attr_files,
                                  "text": (_m.group(1).strip() if _m else _raw.strip())}] + facts
                    except OSError:
                        pass
    sources = [f["source"] for f in facts]
    missing = script_missing(slots, meta)
    _gave_up = list(meta.get("gave_up") or [])

    # The purpose question's answer is context, not a script field:
    # store it and acknowledge it briefly with the next question.
    # Answering it from the KB ("shipping" -> the shipping policy)
    # is noise: the visitor did not ask about policy, they answered
    # what the product is for. Only when the answer did not itself
    # fill the next field (a size in the answer goes through the
    # normal flow instead). Never a trap: the flag clears after
    # this one turn either way.
    if meta.get("awaiting_purpose") and (message or "").strip():
        meta["purpose"] = message.strip()
        meta["awaiting_purpose"] = False
        if missing and missing[0] == "sizes" and not slots.get("sizes"):
            _p = message.strip()
            _ack = f"Got it — {_p}." if len(_p.split()) <= 3 else "Got it."
            _pq2 = _next_question_text(slots, missing, language)
            _preply = f"{_ack} {_pq2}" if _pq2 else _ack
            meta["ai_count"] = meta.get("ai_count", 0) + 1
            meta["last_bot_question"] = _preply
            meta.setdefault("bot_replies", []).append(_preply)
            meta["bot_replies"] = meta["bot_replies"][-20:]
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {"reply": _preply, "language": language, "slots": slots,
                    "missing": script_missing(slots, meta),
                    "sources": _slot_sources(slots), "handoff": None, "llm_used": False,
                    "suggestions": _suggestions(slots, missing, _preply, language)}

    def _final_return(reply, handoff=None, llm_used=False, srcs=None,
                      suggestions=None):
        _save_session(store, session_id, slots)
        _save_meta(store, session_id, meta)
        return {"reply": reply, "language": language, "slots": slots,
                "missing": script_missing(slots, meta),
                "sources": srcs if srcs is not None else _slot_sources(slots),
                "handoff": handoff, "llm_used": llm_used,
                "suggestions": suggestions if suggestions is not None
                else _suggestions(slots, script_missing(slots, meta),
                                  reply=reply, language=language)}

    def _confirmation_text() -> str:
        intro = _tr("confirm_intro", language, "Just to confirm — do you want")
        return (f"{intro} {_spec_parts(slots, _gave_up, meta.get('qty_split'))}?"
                f"{_below_min_note(slots, language)}")

    # Types question ("what box types do you offer?", "what type of
    # boxes do you have?"): answer with the product's type LIST
    # from its own file, never _direct_answer's best sentence —
    # its digit tie-break picked "Box board is generally 12 to
    # 24pt" and "Pharmaceutical boxes primarily use..." over the
    # list (Oct 30 transcript). The question names the product, so
    # the product is stored; style products then ask WHICH type
    # (chips that all parse) instead of jumping to size, and other
    # products continue with the normal next question.
    _types_prod = None
    # "what KIND of finishes" is a finishes question, not a types
    # question: the generic kind/type trigger must yield to an
    # explicit attribute word, or the finishes question gets the
    # include-list sentence instead of the finishes (Oct 30).
    if re.search(r"\b(types?|kinds?)\b", low) \
            and not re.search(r"\b(materials?|finish(?:es)?|styles?)\b", low) \
            and ("?" in message or visitor_is_asking(message)):
        for _w, _p in (("business cards", "business card"),
                       ("business card", "business card"),
                       ("boxes", "box"), ("box", "box"),
                       ("cajas", "box"), ("caja", "box"),
                       ("pouches", "pouch"), ("pouch", "pouch"),
                       ("mylar", "mylar bag"),
                       ("labels", "label"), ("label", "label"),
                       ("stickers", "sticker"), ("sticker", "sticker"),
                       ("banners", "banner"), ("banner", "banner")):
            if re.search(rf"\b{_w}\b", low):
                _types_prod = _p
                break
        if not _types_prod:
            _types_prod = slots.get("product") or prior.get("product")
    if _types_prod:
        _types_list = _type_list_sentence(_types_prod)
        if _types_list:
            _cur = slots.get("product")
            if _cur and _cur != _types_prod:
                # Cross-family question mid-quote: answer the list,
                # keep the quote untouched (no silent overwrite).
                _tmiss = script_missing(slots, meta)
                _tq = _next_question_text(slots, _tmiss, language)
                return _final_return(
                    _types_list + (f" {_tq}" if _tq else ""),
                    srcs=[_TYPE_FILES[_types_prod]])
            slots["product"] = _types_prod
            if "product" not in meta.setdefault("answered_fields", []):
                meta["answered_fields"].append("product")
            _tchips = _TYPE_CHIPS.get(_types_prod)
            # Type already answered (the script asks it before
            # style since Oct 30): a repeat types question gets
            # the list and the pending question, not a second
            # "Which type would you like?" that derails the flow.
            if _tchips and slots.get("type"):
                _tchips = None
            if _tchips:
                _treply = _types_list + " Which type would you like?"
                return _final_return(_treply, srcs=[_TYPE_FILES[_types_prod]],
                                     suggestions=_tchips)
            _tmiss = script_missing(slots, meta)
            _tq = _next_question_text(slots, _tmiss, language)
            _treply = _types_list + (f" {_tq}" if _tq else "")
            return _final_return(_treply, srcs=[_TYPE_FILES[_types_prod]])

    # Styles question, mirroring the types branch: "what styles do
    # you offer" used to be answered from the campaign styles file,
    # whose cards (gift/kraft/square/cosmetic/apparel boxes) are
    # categories, not styles — while the bot's own style question
    # asks Mailer/Tuck-end/Rigid/Folding carton (Oct 30 transcript).
    # Answer with the style vocab itself, then the pending question.
    _styles_prod = None
    if re.search(r"\bstyles?\b", low) \
            and ("?" in message or visitor_is_asking(message)):
        for _w, _p in (("boxes", "box"), ("box", "box"),
                       ("pouches", "pouch"), ("pouch", "pouch"),
                       ("mylar", "mylar bag"), ("bags", "mylar bag"),
                       ("bag", "mylar bag")):
            if re.search(rf"\b{_w}\b", low):
                _styles_prod = _p
                break
        if not _styles_prod:
            _styles_prod = slots.get("product") or prior.get("product")
    if _styles_prod in ("box", "pouch", "mylar bag"):
        _slist = {"box": "Box styles: Mailer, Tuck-end, Rigid, Folding carton.",
                  "pouch": "Mylar bag styles: Flat, Stand-up, Flat-bottom.",
                  "mylar bag": "Mylar bag styles: Flat, Stand-up, Flat-bottom."}[_styles_prod]
        _smiss = script_missing(slots, meta)
        _sq = _next_question_text(slots, _smiss, language)
        return _final_return(_slist + (f" {_sq}" if _sq else ""), srcs=[])

    # Multi-design quantity scope (old quantity_split_question):
    # "5000 units, 3 designs" does not say whether 5000 is the total
    # or per design — and a quantity given before the designs were
    # known is just as ambiguous. Ask it (at most twice, the old
    # cap), then default to per-design, the standing rule. Scope is
    # read from VISITOR words only: the bot's own quantity question
    # carries the MOQ line ("1000 per size and per design"), which
    # would falsely count as the visitor stating per-design. An
    # answer to a per-design question counts as stated via the
    # asked_per_design flag set when that question went out.
    try:
        _n_designs = int(slots.get("skus", "1"))
    except (TypeError, ValueError):
        _n_designs = 1
    if _n_designs > 1 and slots.get("quantity") and not meta.get("split_resolved"):
        _scope_total = quantity_is_total(slots.get("quantity"), visitor_messages) \
            or "total" in low
        _scope_each = quantity_is_per_design(slots.get("quantity"), visitor_messages) \
            or meta.get("asked_per_design") or "per design" in low or "each" in low
        if _scope_total and not _scope_each:
            meta["split_resolved"] = True
            meta["qty_split"] = "total"
        elif _scope_each:
            meta["split_resolved"] = True
            meta["qty_split"] = "per_design"
        elif meta.get("split_asked", 0) >= 2:
            meta["split_resolved"] = True
            meta["qty_split"] = "per_design"
        else:
            _asked_n = meta.get("split_asked", 0)
            meta["split_asked"] = _asked_n + 1
            _n_fmt = f"{int(float(str(slots.get('quantity')).replace(',', ''))):,}"
            if _asked_n == 0:
                _split_q = (f"Just to price it right: is that {_n_fmt} in total, "
                            f"or {_n_fmt} of each of your {_n_designs} designs?")
            else:
                _split_q = (f"Sorry, one more check: {_n_fmt} in total, "
                            f"or {_n_fmt} of each design?")
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {"reply": _split_q, "language": language, "slots": slots,
                    "missing": script_missing(slots, meta),
                    "sources": _slot_sources(slots), "handoff": None, "llm_used": False,
                    "suggestions": ["In total", "Per design"]}

    # Capability question ("do you make pizza boxes?", with or
    # without "?", typos included): the old question-not-answer
    # rule sent this to the product question — the bot asked what
    # the visitor had just told it. A capability question about a
    # product we make IS the choice of product: answer Yes from the
    # product file, store the product, and ask the next question
    # (size, or quantity when the size was stated in the question).
    # Unknown products fall through: never a Yes we cannot stand by.
    _cap = capability_product(message) if not slots.get("product") else None
    if _cap:
        _ctext_raw = capability_fact(_cap)
        if _ctext_raw:
            slots["product"] = _cap
            meta.setdefault("answered_fields", [])
            if "product" not in meta["answered_fields"]:
                meta["answered_fields"].append("product")
            # A size stated inside the capability question ("13 inch
            # pizza boxes", "4x6 mylar bags") is stored, and the next
            # question becomes quantity — the competitor does exactly
            # this, and re-asking a stated size is the annoyance in
            # the Oct 29 transcript. Deliberate exception to the old
            # question-not-answer rule, which is superseded here:
            # the Yes still comes first, nothing is skipped silently.
            from .slots import _SIZE as _SIZE_RE
            _sm = _SIZE_RE.search(message)
            if _sm:
                slots["sizes"] = _sm.group(0).strip()
            else:
                _single = re.search(
                    r"\b\d+(?:\.\d+)?\s*(?:inches|inch|in\b|mm|cm)\b",
                    message, re.IGNORECASE)
                if _single:
                    slots["sizes"] = _single.group(0).strip()
            if slots.get("sizes") and "sizes" not in meta["answered_fields"]:
                meta["answered_fields"].append("sizes")
            # A named box type gets a specific Yes, not the generic
            # file dump: "corrugated" (and its typo "corrogated")
            # must be answered as corrugated boxes.
            _box_variant = None
            if _cap == "box":
                for _typo, _disp in (("corrogated", "corrugated"),
                                     ("corrugated", "corrugated"),
                                     ("rigid", "rigid"),
                                     ("folding", "folding"),
                                     ("mailer", "mailer"),
                                     ("display", "display"),
                                     ("cosmetic", "cosmetic"),
                                     ("cbd", "CBD"),
                                     ("pharmaceutical", "pharmaceutical"),
                                     ("apparel", "apparel"),
                                     ("kraft", "kraft"),
                                     ("metalized", "metalized")):
                    if re.search(rf"\b{_typo}\b", low):
                        _box_variant = _disp
                        break
            _ctext = _fact_reply_text(_ctext_raw)
            # REFERENCE, NOT WHITELIST (Oct 29): a packaging company
            # makes the product family — an option the files do not
            # name (PET, a handle, a spout pouch shown in the
            # gallery) still gets a Yes. The old "can't confirm"
            # guard is gone by design; "team will confirm" survives
            # only for out-of-domain requests and company hard facts
            # the KB does not hold.
            if _box_variant:
                _ctext = f"Yes — we make {_box_variant} boxes. " + _ctext
            elif not _ctext.lower().startswith("yes"):
                _ctext = "Yes — " + (_ctext[0].lower() + _ctext[1:] if _ctext else _ctext)
            # Subcategory grounding (Oct 30): a qualifier the
            # product's own files never name ("wodden" for cards)
            # must be named as unlisted, not swallowed by the Yes.
            _quals = unlisted_qualifiers(message, _cap)
            _qcaveat = qualifier_caveat(_cap, _quals) if _quals else ""
            if _quals:
                meta.setdefault("qualifier_noted", [])
                for _q in _quals:
                    _qk = f"{_cap}:{_q}"
                    if _qk not in meta["qualifier_noted"]:
                        meta["qualifier_noted"].append(_qk)
                _pnotes = sorted(q.split(":", 1)[1] for q in meta["qualifier_noted"]
                                 if q.startswith(f"{_cap}:"))
                slots["notes"] = ", ".join(_pnotes)
            _cmissing = script_missing(slots, meta)
            _cq = _next_question_text(slots, _cmissing, language)
            meta["last_asked"] = _cmissing[0] if _cmissing else None
            _creply = _ctext + (f" {_qcaveat}" if _qcaveat else "") \
                + (f" {_cq}" if _cq else "")
            meta["last_bot_question"] = _creply
            return _final_return(_creply, srcs=[capability_source(_cap)])

    # Location + a foreign country ("where it located in pakistan"):
    # dumping the footer address never answers it — the visitor is
    # asking whether we are THERE. We are in Rosenberg, Texas, USA,
    # and no other location is published, so say so plainly.
    _loc_trigger = any(w in low for w in
                       ("located", "location", "office in", "branch in",
                        "facility in", "based in"))
    _countries = {"pakistan": "Pakistan", "india": "India", "china": "China",
                  "uk": "the UK", "england": "the UK", "canada": "Canada",
                  "australia": "Australia", "germany": "Germany",
                  "france": "France", "uae": "the UAE", "dubai": "the UAE",
                  "bangladesh": "Bangladesh", "sri lanka": "Sri Lanka",
                  "nepal": "Nepal", "nigeria": "Nigeria", "kenya": "Kenya",
                  "south africa": "South Africa", "brazil": "Brazil",
                  "mexico": "Mexico", "japan": "Japan", "korea": "Korea",
                  "turkey": "Turkey", "saudi arabia": "Saudi Arabia",
                  "qatar": "Qatar", "italy": "Italy", "spain": "Spain",
                  "netherlands": "the Netherlands", "europe": "Europe"}
    _mentioned = [d for c, d in _countries.items()
                  if re.search(rf"\b{re.escape(c)}\b", low)]
    if _loc_trigger and _mentioned:
        _lm = script_missing(slots, meta)
        _lq = _next_question_text(slots, _lm, language)
        _ltext = ("We're based in Rosenberg, Texas, USA — we don't have "
                  f"a location in {_mentioned[0]}.")
        meta["last_asked"] = _lm[0] if _lm else None
        meta["last_bot_question"] = (_ltext + " " + _lq) if _lq else _ltext
        return _final_return((_ltext + " " + _lq) if _lq else _ltext,
                             srcs=["kb/facts/contact.md"])
    if _loc_trigger and re.search(r"\b(usa|america|united states|us)\b", low):
        _lm = script_missing(slots, meta)
        _lq = _next_question_text(slots, _lm, language)
        _ltext = "Yes — we're based in Rosenberg, Texas, USA."
        meta["last_asked"] = _lm[0] if _lm else None
        meta["last_bot_question"] = (_ltext + " " + _lq) if _lq else _ltext
        return _final_return((_ltext + " " + _lq) if _lq else _ltext,
                             srcs=["kb/facts/contact.md"])

    # Price question (old visitorQuestions): a price is a rep's to
    # give, and it comes with the quote — never a figure, never the
    # minimum as the answer. Answer it, then the script question
    # (or the confirmation, when the script is complete). But a
    # price question about a DIFFERENT product ("How much do mailer
    # boxes cost?" while a banner quote is pending) must not drag
    # the pending confirmation back in (Oct 30 transcript).
    if asks_about_price(message):
        _price_line = _tr("price_line", language, PRICING_COMES_WITH_THE_QUOTE)
        try:
            _price_prod = extract_from_message(message).get("product")
        except Exception:
            _price_prod = None
        if _price_prod and prior.get("product") and _price_prod != prior["product"]:
            return _final_return(_price_line)
        if not missing:
            return _final_return(_price_line + " " + _confirmation_text())
        return _final_return(_price_line + " " + _next_question_text(slots, missing, language))

    # Bare fact topic ("Moq" alone): answer it, then the script
    # question. Without this, "MOQ" typed in answer to the designs
    # question went onto the lead as the number of designs.
    _bare = asks_bare_fact_topic(message)
    if _bare and not _is_order:
        _bfacts = retrieve(topic_query(_bare))
        if _bfacts:
            _text = _direct_answer(message, _bfacts[0]["text"]) or \
                _fact_reply_text(_bfacts[0]["text"])
            _q = _next_question_text(slots, missing, language)
            _tail = (" " + _q) if _q else ((" " + _confirmation_text()) if not missing else "")
            return _final_return(_text + _tail, srcs=[f["source"] for f in _bfacts])

    # "Did you email me?" (old dodgesHasItArrived): the one true
    # answer is that it has not gone out yet, and when it will.
    if asks_if_it_arrived(message):
        if meta.get("complete"):
            _reply = (f"Not yet — the quote has not gone out. "
                      f"You will have it {when_the_team_replies()}.")
            return _final_return(_reply, srcs=[])
        _q = _next_question_text(slots, missing, language)
        _reply = _tr("not_sent", language, NOT_SENT_YET)
        return _final_return(_reply + (" " + _q if _q else ""), srcs=[])

    # Smaller run after the minimum was stated: put it to the team
    # (old ignoresTheSmallerRun) — never repeat the minimum at them,
    # never turn them down.
    if wants_smaller_run(message) and minimum_already_stated(meta.get("bot_replies") or []) \
            and not _bare_skus:
        _q = _next_question_text(slots, missing, language)
        _reply = _tr("smaller_run_note", language,
                     "I'll put {qty} to the team and come back to you on it.",
                     qty=slots.get("quantity"))
        return _final_return(_reply + (" " + _q if _q else ""))

    # "Not sure" used to loop forever: the bot re-asked the same
    # question because no answer was ever collected. For sizes and
    # quantity, offer a starting point; for finishes/extras/material/
    # style/skus, "not sure" IS an answer (old NOT_SURE) — record the
    # default and move on instead of looping.
    if ("not sure" in low or says_they_do_not_know(message)) and missing:
        _first = missing[0]
        if _first == "sizes":
            return _final_return(
                _tr("not_sure_sizes", language,
                    "No problem — tell me what will go inside the pack, "
                    "or pick a common size to start with."),
                srcs=_slot_sources(slots) or sources)
        if _first == "quantity":
            return _final_return(
                _tr("not_sure_quantity", language,
                    "No problem — most orders start at the minimum of 1000 units "
                    "per size. Would you like to start with 1000, or a rough range?"),
                srcs=_slot_sources(slots) or sources)
        if _first in ("finishes", "extras", "material", "style", "skus"):
            slots[_first] = "1" if _first == "skus" else "none"
            meta.setdefault("answered_fields", [])
            if _first not in meta["answered_fields"]:
                meta["answered_fields"].append(_first)
            _missing2 = script_missing(slots, meta)
            if not _missing2:
                return _final_return(_confirmation_text())
            return _final_return(_next_question_text(slots, _missing2, language))

    # Below-minimum note (old composer: lead with what we can do,
    # give the minimum after it, never a flat refusal). Prepended to
    # the next question reply below, once — the quantity question
    # itself already states the MOQ, so it never repeats.
    _moq_note = ""
    try:
        _qty = int(float(str(slots.get("quantity", "0")).replace(",", "")))
    except (TypeError, ValueError):
        _qty = 0
    if _qty and _qty < 1000 and guards.minimum_applies(slots.get("product")) \
            and not minimum_already_stated(meta.get("bot_replies") or []):
        _moq_note = _tr("moq_note", language, BELOW_MIN_NOTE, qty=_qty)

    # Per-field answer handling for the last script question:
    # a decline ("no"/"none") of finishes/extras/material/style is
    # recorded as "none" (skus: "1"); "yes" to the extras question
    # means zipper + tear notch; a bare number answers the skus
    # question. Product/sizes/quantity declines are NOT answers —
    # those fields are re-asked until given up.
    _last = meta.get("last_asked")
    if _last in ("finishes", "extras", "material", "style", "skus") \
            and not visitor_is_asking(message):
        if _DECLINE.match(message.strip()):
            slots[_last] = "1" if _last == "skus" else "none"
            meta.setdefault("answered_fields", [])
            if _last not in meta["answered_fields"]:
                meta["answered_fields"].append(_last)
        elif _last == "extras" and _YES.match(message.strip()):
            slots["extras"] = "zipper, tear notch"
            meta.setdefault("answered_fields", [])
            if "extras" not in meta["answered_fields"]:
                meta["answered_fields"].append("extras")
        elif _last == "skus":
            _m = _BARE_NUMBER.match(message.strip())
            if _m:
                slots["skus"] = _m.group(1)
            elif message.strip().lower() in _BARE_SPELLED:
                slots["skus"] = _BARE_SPELLED[message.strip().lower()]
            if slots.get("skus"):
                meta.setdefault("answered_fields", [])
                if "skus" not in meta["answered_fields"]:
                    meta["answered_fields"].append("skus")
        missing = script_missing(slots, meta)
        _gave_up = list(meta.get("gave_up") or [])

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
    #   with the OKF leash, then the composer validator fixes it in
    #   code (or falls back to deterministic when unsalvageable).
    is_fact_question = ("?" in message or any(w in low for w in _FACT_WORDS)
                        or bool(fact_topics_asked(message)))
    # A vague size word ("i need large box") with no purpose stated:
    # the bot cannot recommend a type without knowing the use, so
    # it asks what the product is for FIRST, then size — once per
    # session. A "for ..." phrase in the message already states the
    # purpose, and a question ("do you make large boxes?") is
    # answered, never purpose-trapped. The purpose is context in
    # meta, never a script field, so it can never block the quote.
    _VAGUE_SIZE_WORDS = ("large", "small", "medium", "big", "little",
                         "huge", "tiny", "jumbo", "mini",
                         # Spanish vague sizes: "cajas grandes" gets
                         # the purpose question too, not just size.
                         "grande", "grandes", "pequeño", "pequeña",
                         "pequeños", "mediano", "mediana")
    if not meta.get("purpose") and not meta.get("purpose_asked") \
            and slots.get("product") and not slots.get("sizes") \
            and not is_fact_question \
            and any(re.search(rf"\b{w}\b", low) for w in _VAGUE_SIZE_WORDS) \
            and not re.search(r"\bfor\b", low):
        meta["purpose_asked"] = True
        meta["awaiting_purpose"] = True
        _pq = _tr("purpose_q", language, "What do you need the {product} for?",
                  product=slots["product"])
        meta["ai_count"] = meta.get("ai_count", 0) + 1
        meta["last_bot_question"] = _pq
        meta.setdefault("bot_replies", []).append(_pq)
        meta["bot_replies"] = meta["bot_replies"][-20:]
        _save_session(store, session_id, slots)
        _save_meta(store, session_id, meta)
        return {"reply": _pq, "language": language, "slots": slots,
                "missing": script_missing(slots, meta),
                "sources": _slot_sources(slots), "handoff": None, "llm_used": False,
                "suggestions": [_tr("chip_purpose_shipping", language, "Shipping"),
                                _tr("chip_food", language, "Food"),
                                _tr("chip_gifts", language, "Gifts"),
                                _tr("chip_retail", language, "Retail")]}
    # A size span without a unit ("3x4") is not a usable size yet:
    # ask inches, cm or mm — once per size value, never a trap. A
    # bare unit answer is applied by the extraction above, so
    # answering completes the size and the script moves on. If the
    # visitor ignores the question, the next message proceeds
    # normally (the size stays unitless for the team to confirm).
    if slots.get("sizes") and size_missing_unit(slots.get("sizes")) \
            and meta.get("unit_asked_for") != slots.get("sizes") \
            and re.search(r"\d+(?:\.\d+)?\s*(?:x|×|by|\*)\s*\d+", message,
                          re.IGNORECASE):
        meta["unit_asked_for"] = slots["sizes"]
        _uq = f"Got it — {slots['sizes']}. Is that in inches, cm, mm, or feet?"
        meta["ai_count"] = meta.get("ai_count", 0) + 1
        meta["last_bot_question"] = _uq
        meta.setdefault("bot_replies", []).append(_uq)
        meta["bot_replies"] = meta["bot_replies"][-20:]
        _save_session(store, session_id, slots)
        _save_meta(store, session_id, meta)
        return {"reply": _uq, "language": language, "slots": slots,
                "missing": script_missing(slots, meta),
                "sources": _slot_sources(slots), "handoff": None, "llm_used": False,
                "suggestions": ["Inches", "Cm", "Mm", "Feet"]}
    # Asking what is usual ('what is a standard size?') is a question
    # about the field, not an answer to it: answer it first, then
    # re-ask the field. There is no standard — everything is made to
    # fit what goes inside.
    if asks_what_is_usual(message) and missing:
        reply = (_tr("no_standard", language,
                     "There's no standard one — everything is made to fit what goes inside.")
                 + " " + _next_question_text(slots, missing, language))
        llm_used = False
        sources = _slot_sources(slots)
    elif not is_fact_question or (is_fact_question and len(facts) == 1):
        # Ask-attempt accounting (old askAttempts.ts): an attempt is
        # spent only when the visitor had a go and the field is still
        # missing. Exhausted fields are skipped for the next question
        # instead of being asked a third time. Product is never given
        # up — nothing else on the script may be asked before it.
        _last = meta.get("last_asked")
        _asks = dict(meta.get("asks") or {})
        if _last in ("product", "sizes", "style", "finishes", "quantity",
                     "skus", "extras", "material"):
            _have_now = _last not in script_missing(slots, meta)
            _asks[_last] = apply_ask_outcome(_asks.get(_last, 0),
                                             ask_outcome(_last, message, _have_now))
            meta["asks"] = _asks
            if _asks[_last] >= MAX_ASKS and _last != "product" \
                    and _last in script_missing(slots, meta):
                meta.setdefault("gave_up", [])
                if _last not in meta["gave_up"]:
                    meta["gave_up"].append(_last)
                missing = script_missing(slots, meta)
                _gave_up = list(meta["gave_up"])
        _askable = [f for f in missing if _asks.get(f, 0) < MAX_ASKS]
        if missing and not _askable:
            if "product" in missing:
                reply = _QUESTION_VARIANTS["product"]
                llm_used = False
                sources = _slot_sources(slots)
                meta["last_asked"] = "product"
                meta["last_bot_question"] = reply
                meta.setdefault("bot_replies", []).append(reply)
                meta["bot_replies"] = meta["bot_replies"][-20:]
                _save_session(store, session_id, slots)
                _save_meta(store, session_id, meta)
                return {"reply": reply, "language": language, "slots": slots,
                        "missing": missing, "sources": sources,
                        "handoff": None, "llm_used": False,
                        "suggestions": _suggestions(slots, missing, reply=reply,
                                                    language=language)}
            _reply = ("Thanks — I've got " + ", ".join(
                f"{k}: {slots[k]}" for k in ("product", "sizes", "quantity",
                                             "finishes", "material", "style")
                if slots.get(k))
                + f". For {', '.join(missing)}, the team will confirm it with you directly.")
            _save_session(store, session_id, slots)
            _save_meta(store, session_id, meta)
            return {"reply": _reply, "language": language, "slots": slots,
                    "missing": missing, "sources": _slot_sources(slots),
                    "handoff": "needs_followup", "llm_used": False,
                    "suggestions": _suggestions(slots, missing, language=language)}
        reply = _deterministic_reply(message, slots, facts, _askable or missing,
                                     language, _gave_up, meta.get("qty_split"))
        llm_used = False
        _asked_field = _askable[0] if _askable else (missing[0] if missing else None)
        if _asked_field and not is_fact_question:
            # Pure question reply: slot sources, and the repeat guard
            # (old repeatedQuestion.ts) — never send a question
            # already asked, reword it instead.
            sources = _slot_sources(slots)
            # Repeat guard (English variants only): for a translated
            # session, repeating the translated question beats
            # switching language mid-chat for a rewording.
            if language == "en" and repeats_the_question(reply, meta.get("last_bot_question", "")):
                reply = _QUESTION_VARIANTS.get(_asked_field, reply) \
                    if _asked_field != "quantity" or not per_design_quantity(slots) \
                    else _QUESTION_VARIANTS["per_design"]
            meta["last_asked"] = _asked_field
            # A quantity answer to a per-design question IS per-design
            # by construction — the split question must never re-ask it.
            meta["asked_per_design"] = bool(_asked_field == "quantity"
                                            and per_design_quantity(slots))
        elif not is_fact_question:
            sources = _slot_sources(slots) or sources
    else:
        # LIVE SEARCH + LEARN (Oct 29, "both"): a fact question
        # with zero KB facts is searched on the web instead of
        # answered "not in our data" — and the searched answer is
        # SAVED as a learned KB fact (kb/learned/*.md + Qdrant
        # point) so the next visitor gets it from the cache, fast,
        # with no search. Price questions never search: no figure
        # may reach a visitor, from any source.
        _searched = None
        if not facts and not asks_about_price(message):
            _searched = web_search(message)
            if _searched:
                facts = [{"source": "web-search", "text": _searched["answer"]}]
        reply = _llm_reply(message, language, slots, facts, reply_to=reply_to)
        llm_used = reply is not None
        if not llm_used:
            reply = _deterministic_reply(message, slots, facts, missing, language, _gave_up,
                                     meta.get("qty_split"))
        # Composer validator (old chatComposer.ts problemsWith): a
        # reply carrying template blanks is fixed in code, not sent.
        if llm_used and "__" in (reply or ""):
            reply = _deterministic_reply(message, slots, facts, missing, language, _gave_up,
                                     meta.get("qty_split"))
            llm_used = False
        if llm_used:
            _next_q = _next_question_text(slots, missing, language)
            _ctx = {
                "visitor_text": message,
                "visitor_texts": visitor_messages,
                "visitor_asking": visitor_is_asking(message),
                "last_bot_text": meta.get("last_bot_question", ""),
                "slots": slots,
                "answered_fields": meta.get("answered_fields") or [],
                "contact": meta.get("contact") or {},
                "is_banner": is_banner_family(slots.get("product")),
                "is_plain": wants_plain_packaging(visitor_messages),
                "minimum_due": bool(_qty and _qty < 1000),
                "asked_price": asks_about_price(message),
                "asked_usual": asks_what_is_usual(message),
                "asked_arrived": asks_if_it_arrived(message),
                "unclear": False,
            }
            _fixed = fix_reply(reply, _ctx, _next_q, _kb_first_sentence)
            if _fixed is None:
                reply = _deterministic_reply(message, slots, facts, missing, language, _gave_up,
                                     meta.get("qty_split"))
                llm_used = False
            else:
                reply = _fixed
                # Only a reply that actually reached the visitor is
                # worth learning: a composer-rejected search answer
                # is never cached.
                if _searched:
                    save_learned(message, _searched["answer"], _searched["urls"])
                    sources = [u["url"] for u in _searched["urls"] if u.get("url")]
    # Below-minimum note, once, on a question reply that does not
    # already state the minimum (the quantity question does).
    if _moq_note and "?" in (reply or "") and "MOQ" not in reply and "minimum" not in reply.lower():
        reply = _moq_note + " " + reply
    # No turn cap: the old 12-message rule handed off mid-conversation
    # and, before the one-time fix, bricked the chat outright. User
    # directive (Oct 30): if the chat is flowing, let it flow — no
    # limit, no forced handoff. Handoffs still happen for real
    # reasons (guards, existing-customer, contact completion), never
    # for message count.
    meta["ai_count"] = meta.get("ai_count", 0) + 1
    _handoff = None
    meta["last_bot_question"] = reply
    meta.setdefault("bot_replies", []).append(reply)
    meta["bot_replies"] = meta["bot_replies"][-20:]
    _save_session(store, session_id, slots)
    _save_meta(store, session_id, meta)

    return {
        "reply": reply, "language": language, "slots": slots,
        "missing": script_missing(slots, meta), "sources": sources,
        "handoff": _handoff,
        "llm_used": llm_used,
        "suggestions": _suggestions(slots, script_missing(slots, meta),
                                    reply=reply, language=language),
    }
