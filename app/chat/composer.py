"""Reply validator + code fix — ported from the old bot
(chatComposer.ts problemsWith).

Each rule here was a rule in the old prompt first, and each was
broken anyway, several in a single chat: a question already
answered asked again word for word, a detail already held asked
for again, a visitor question dodged with the next script question,
a price question answered with the minimum, the visitor's own
question handed back. So the old bot checks the written reply in
code, rewrites it once when time allows, and otherwise fixes it in
code.

Our improvement on that: no second model call. The fix in code IS
the reply — a deterministic fallback when the reply is unsalvageable
(announces a quote, promises to check, goes off-script, parrots the
visitor, echoes gibberish, asks ahead of product), and a surgical
repair otherwise (strip volunteered facts, insert the missing
answer before the question, replace a repeated question with the
next script question, append the missing question).
"""
import re

from .fact_topics import (SENTENCE_BREAK, fact_questions_unanswered,
                          facts_volunteered, with_answers_before_question,
                          without_volunteered_facts)
from .price_questions import PRICING_COMES_WITH_THE_QUOTE, answers_about_price, parrots_their_question
from .repeated import (fields_asked_about, is_question_sentence,
                       question_in, question_sentences, repeats_the_question)
from .script import asks_about_the_quote

ANNOUNCES_THE_QUOTE = re.compile(
    r"\b(?:i['’]?ll|i will|let me|i['’]?m going to|i am going to|we['’]?ll|we will)\b[^.!?]{0,40}\b(?:prepare|preparing|put together|work up|draw up|start|get|send|have)\b[^.!?]{0,30}\bquote\b|"
    r"\bquote (?:is|will be) (?:ready|prepared|on its way|coming)\b|"
    r"\bthat['’]?s (?:everything|all) (?:i|we) need\b",
    re.IGNORECASE)
PROMISES_TO_CHECK = re.compile(
    r"\b(?:i['’]?ll|i will|let me|we['’]?ll|we will|i['’]?m going to)\s+(?:\w+\s+){0,2}?(?:confirm|check|look into|find out|verify|double-check|get back to you)\b",
    re.IGNORECASE)
REFUSES_TO_GO_ON = re.compile(
    r"\bcan(?:not|['’]t)\s+(?:proceed|continue|go ahead|move forward)\b",
    re.IGNORECASE)
_MINIMUM_STATED = re.compile(r"\b1,?000\b|\bmoq\b|\bminimum (?:order |run )?(?:is|of)\b", re.IGNORECASE)
_ANSWERS_WHAT_IS_USUAL = re.compile(
    r"\bno (?:single |one )?standard\b|\bnot standard\b|\bdepends\b|\bmade to fit\b|\bfit what\b|\bgoes inside\b|\bcustom\b|\bany size\b",
    re.IGNORECASE)
_SAYS_IT_HAS_NOT_GONE = re.compile(
    r"\bnot (yet|been sent|gone)\b|\bhasn'?t (gone|been sent|arrived)\b|\bno(t)? yet\b|\bin the morning\b|\bshortly\b|\bstill (being )?(prepar|writ|work)",
    re.IGNORECASE)
_JUST_A_COURTESY = re.compile(
    r"^(?:got it|great|perfect|thanks?|thank you|understood|sure|noted|nice to meet you|good to meet you|pleasure|awesome|excellent|no problem|of course|absolutely|certainly|okay|ok)\b(?:\s+(?:for|to)\b[^.?!]*|\s+[A-Z][\w'’-]*)?[\s,.!?—-]*$",
    re.IGNORECASE)

_BANNER_NO_MINIMUM = "Banners have no minimum — we make one, two or more."

_FIELD_PATTERNS = [
    ("product", re.compile(r"\bwhat (?:product|are you looking to have made)\b|\bboxes, bags or labels\b", re.IGNORECASE)),
    ("style", re.compile(r"\bstyle\b", re.IGNORECASE)),
]


def fields_in_question(question: str) -> list[str]:
    """fields_asked_about plus product/style, which the old helper
    does not label but the validator still has to see."""
    found = list(fields_asked_about(question or ""))
    for key, pat in _FIELD_PATTERNS:
        if pat.search(question or "") and key not in found:
            found.append(key)
    return found


def _answer_part(reply: str) -> str:
    """The reply minus its questions, minus courtesy-only sentences,
    minus a leading acknowledgement. A reply whose answer part is
    under 15 characters has not answered anything."""
    statements = [s for s in re.split(SENTENCE_BREAK, reply or "")
                  if not is_question_sentence(s)]
    statements = [s for s in statements if not _JUST_A_COURTESY.match(s.strip())]
    text = " ".join(statements).strip()
    return re.sub(r"^(got it|great|perfect|thanks|thank you|understood|sure|noted)[,.! ]*",
                  "", text, flags=re.IGNORECASE).strip()


def check_reply(reply: str, ctx: dict) -> list[str]:
    """Problem list for a reply, in the old problemsWith wording
    (shortened). Empty list = clean."""
    problems: list[str] = []
    slots = ctx.get("slots") or {}
    answered = set(ctx.get("answered_fields") or [])
    contact = ctx.get("contact") or {}
    visitor_text = ctx.get("visitor_text") or ""
    last_bot = ctx.get("last_bot_text") or ""
    is_banner = bool(ctx.get("is_banner"))
    is_plain = bool(ctx.get("is_plain"))
    minimum_due = bool(ctx.get("minimum_due"))

    def _has(field: str) -> bool:
        if field in ("name", "email", "phone"):
            return bool(contact.get(field))
        if field in answered:
            return True
        v = slots.get(field)
        return bool(v and str(v).strip() and str(v).strip().lower() not in
                    ("null", "not specified", "n/a", "none specified"))

    if ANNOUNCES_THE_QUOTE.search(reply or ""):
        problems.append("announces the quote")
    if PROMISES_TO_CHECK.search(reply or ""):
        problems.append("promises to check/confirm something")
    if REFUSES_TO_GO_ON.search(reply or ""):
        problems.append("refuses to go on without something")
    if is_banner and _MINIMUM_STATED.search(reply or ""):
        problems.append("states a minimum for banners")
    # A price figure must never reach a visitor (standing rule:
    # "your quote will carry the pricing"). The LLM path is now
    # used for open suggestions, so this guardrail has to live in
    # code, not just in the prompt — a prompt rule is followed
    # "most of the time".
    if re.search(r"\$\s*\d", reply or ""):
        problems.append("states a price")
    question = question_in(reply or "")
    asked_fields = fields_in_question(question)
    if is_plain and "skus" in asked_fields:
        problems.append("asks designs of a plain order")
    if not (slots.get("product")) and asked_fields \
            and any(f in ("sizes", "finishes", "quantity", "skus", "extras", "material", "style")
                    for f in asked_fields):
        problems.append("asks ahead of product")
    if len(set(asked_fields)) >= 2 or len(question_sentences(reply or "")) >= 2:
        problems.append("asks two things at once")
    if last_bot:
        last_first = (last_bot.split(".")[0] or "").strip().lower()
        this_first = ((reply or "").split(".")[0] or "").strip().lower()
        if last_first and this_first and len(last_first) > 8 and last_first == this_first:
            problems.append("repeats the opening acknowledgement")
        if repeats_the_question(reply or "", last_bot):
            problems.append("repeats the last question")
    held = next((f for f in asked_fields if _has(f)), None)
    if held:
        problems.append(f"asks for {held}, which we already have")
    if ctx.get("visitor_asking") and len(_answer_part(reply or "")) < 15:
        problems.append("dodges their question")
    if ctx.get("asked_price") and not answers_about_price(reply or ""):
        problems.append("dodges the price")
    if question and (parrots_their_question(question, visitor_text)
                     or any(parrots_their_question(question, s)
                            for s in question_sentences(visitor_text))):
        problems.append("parrots their question")
    if ctx.get("unclear") and visitor_text and visitor_text.strip().lower() in (reply or "").lower():
        problems.append("echoes their unusable words")
    if ctx.get("asked_usual") and not _ANSWERS_WHAT_IS_USUAL.search(reply or ""):
        problems.append("dodges what is usual")
    if ctx.get("asked_arrived") and not _SAYS_IT_HAS_NOT_GONE.search(reply or ""):
        problems.append("dodges whether it arrived")
    if question and asks_about_the_quote(question):
        problems.append("asks an off-script question")
    if question and not asked_fields and not ctx.get("asked_usual"):
        problems.append("asks something that is not on the script")
    if not question:
        problems.append("asks nothing")
    if ctx.get("visitor_asking"):
        missed = fact_questions_unanswered(visitor_text, reply or "")
        if missed:
            problems.append(f"leaves unanswered: {', '.join(missed)}")
    recited = facts_volunteered(ctx.get("visitor_texts") or [visitor_text],
                                reply or "", minimum_due=minimum_due)
    if recited:
        problems.append(f"recites unasked facts: {', '.join(recited)}")
    return problems


def fix_reply(reply: str, ctx: dict, next_question: str, fact_answer) -> str | None:
    """Repair a reply in code, or None when it is unsalvageable and
    the caller must fall back to the deterministic reply.

    fact_answer(topic) -> first sentence of the KB answer, or None.
    """
    problems = check_reply(reply, ctx)
    if not problems:
        return reply
    fatal = ("announces the quote", "promises to check/confirm something",
             "refuses to go on without something", "asks an off-script question",
             "asks something that is not on the script", "parrots their question",
             "echoes their unusable words", "asks ahead of product",
             "states a price")
    if any(p in problems for p in fatal):
        return None
    fixed = reply or ""
    if "states a minimum for banners" in problems:
        sentences = [s for s in re.split(SENTENCE_BREAK, fixed) if not _MINIMUM_STATED.search(s)]
        fixed = " ".join(sentences).strip()
        if "no minimum" not in fixed.lower():
            fixed = (fixed + " " + _BANNER_NO_MINIMUM).strip()
    recited = facts_volunteered(ctx.get("visitor_texts") or [ctx.get("visitor_text") or ""],
                                fixed, minimum_due=bool(ctx.get("minimum_due")))
    if recited:
        fixed = without_volunteered_facts(fixed, recited)
    answers: list[str] = []
    if "dodges the price" in problems:
        answers.append(PRICING_COMES_WITH_THE_QUOTE)
    missed = fact_questions_unanswered(ctx.get("visitor_text") or "", fixed) \
        if ctx.get("visitor_asking") else []
    for topic in missed:
        sentence = fact_answer(topic)
        if sentence:
            answers.append(sentence)
    if "dodges their question" in problems and not answers:
        return None
    if answers:
        fixed = with_answers_before_question(fixed, answers)
    question = question_in(fixed)
    needs_new_question = any(p in problems for p in (
        "asks two things at once", "repeats the last question",
        "asks designs of a plain order")) \
        or any(p.startswith("asks for ") for p in problems)
    if needs_new_question and next_question:
        answer = _answer_part(fixed)
        fixed = (answer + " " + next_question).strip() if answer else next_question
    elif "asks nothing" in problems and next_question:
        fixed = (fixed + " " + next_question).strip()
    return fixed
