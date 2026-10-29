"""Fact topics the company facts answer — ported from the old bot
(factQuestions.ts), with OUR answers, not the old script's.

The old check exists because a visitor who asked about the minimum,
the lead time and in-house manufacturing was asked for her quantity
instead — in live chat, and again on replay. So: the topic is found
in what they wrote, and the reply has to contain what answers it.
Only topics our KB covers are checked. A price, fees, samples terms
or shipping terms go in the quote, and there is nothing in a reply
to check that for.

One deliberate correction vs the old patterns: the old "where we
are" answer accepted Houston (the old script's base). Our site
says Rosenberg, TX — so a reply answering with Houston does NOT
count as answering, and volunteered "Houston" is never our fact.
"""
import re

from .repeated import SENTENCE_BREAK, is_question_sentence

# topic -> (asked pattern, answered pattern, volunteered pattern or
# None, retrieval query for the KB answer)
TOPICS = [
    ("the minimum order",
     re.compile(r"\b(moq|minimum (?:order|quantit|run|for|to start|on|is|are)|min\.? (?:order|quantit|run)|smallest (?:order|run|quantit)|least (?:amount|order|quantit)|same for (?:stickers|labels|boxes|bags|pouches)|how many (?:to start|minimum)|minimum\b)", re.I),
     re.compile(r"\b(moq|minimum|1,?000|500)\b", re.I),
     re.compile(r"\bmoq\b|\bminimum (?:order|is|of|run)\b", re.I),
     "minimum order"),
    ("the turnaround",
     re.compile(r"\b(lead ?times?|turn ?around|production time|how long (does|will|would|to)|timeline|how soon|how fast|how quickly|when (can|could|will) (you|i|we)|by (mon|tue|wed|thur|thu|fri|sat|sun)\w*day?\b|rush|urgent|asap)\b", re.I),
     re.compile(r"\bbusiness days\b", re.I),
     re.compile(r"\bbusiness days\b", re.I),
     "turnaround"),
    ("where we are",
     re.compile(r"\b(where are you|where is print247|where('?s| is) (your|the) (company|office|factory|headquarters)|located|location|based (in|out))\b", re.I),
     re.compile(r"\b(based|located|rosenberg)\b", re.I),
     re.compile(r"\brosenberg\b|\bbased in\b|\blocated in\b", re.I),
     "where are you located"),
    ("whether we make it in-house",
     re.compile(r"\b(in[- ]?house|outsourc|your own factory|manufacture (it|them|this) yourselves)", re.I),
     re.compile(r"\bin[- ]?house\b", re.I),
     None,
     "manufactured in-house"),
    ("what we make",
     re.compile(r"\b(?:what|which) (?:boxes|bags|pouches|stickers|labels|packaging|products?|styles?|options?|types?)\b.*\b(?:you (?:have|make|offer|do|provide)|do you (?:have|make|offer|do|provide)|are available)\b|\bwhat (?:kind|type|sort|style) of (?:boxes|bags|pouches|packaging|products?)\b|\bwhat (?:are|is|were) (?:my|the|our|your|there) (?:other )?(?:options?|choices?)\b|\bwhat options\b|\bwhat (?:do|can|could) you (?:offer|make|do|produce|provide|give)\b|\bwhat else (?:do|can) you\b|\bwhat are the choices\b", re.I),
     re.compile(r"\b(mailer|rigid|corrugated|shipping|folding|carton|stand[- ]?up|pouch|pouches|mylar|labels?|stickers?|custom)\b", re.I),
     None,
     "what products do you offer"),
    ("how to send or upload logo / artwork",
     re.compile(r"\b(?:how (?:do (?:i|you)|can (?:i|we)|should i)|where (?:do (?:i|we)|can (?:i|we)|should i))\b.*\b(?:get|send|upload|share|provide|attach|submit)\b.*\b(?:logo|artwork|files?|images?|design|photo)\b|\bhow do you get (?:my|our) (?:logo|artwork|design|file)\b|\bcan i (?:upload|send|share|attach) (?:my )?(?:logo|artwork|file|design|image)\b", re.I),
     re.compile(r"\b(?:upload|attach|send|share|email|review)\b.*\b(?:logo|artwork|chat|email|quote|file)\b", re.I),
     None,
     "upload artwork"),
    ("samples or proofs",
     re.compile(r"\b(?:can (?:i|we) (?:get|have|order) (?:a )?(?:samples?|proofs?)|do you (?:provide|send|do) (?:samples?|proofs?)|physical samples?|digital proofs?)\b", re.I),
     re.compile(r"\b(?:sample|proof|include|quote|team|rep)\b", re.I),
     None,
     "samples proofs"),
    ("design assistance / dielines",
     re.compile(r"\b(?:design (?:support|services?|help|assistance|team|work)|dielines?|templates?|designing|graphic design|can (?:you|u|y'?all|yall) (?:guys )?design|do (?:you|u|y'?all|yall) (?:guys )?(?:do|offer|provide|handle|have)[^.?!]{0,25}design|help with (?:design|artwork))\b", re.I),
     re.compile(r"\b(?:design support|in-?house (?:design|engineering|art)|design team|we (?:can|do|offer|provide|have)[^.?!]{0,30}design|dielines?|templates?)\b", re.I),
     None,
     "design support"),
    ("payment",
     re.compile(r"\b(payment methods?|how (can|do) (i|we) pay|pay (by|with|via|invoice)|credit card|accept (cards?|paypal|ach|wire|zelle))\b", re.I),
     re.compile(r"\b(ach|wire|zelle|visa|mastercard|amex|paypal|payment link)\b", re.I),
     re.compile(r"\b(ach|zelle|wire transfer|processing fee)\b", re.I),
     "payment methods"),
]


def asks_bare_fact_topic(text: str) -> str | None:
    """A message that is nothing but the name of a fact topic.

    "Moq" — typed on its own, in answer to "how many total designs
    or SKUs do you have?", by a visitor who wanted the figure
    before committing. It is a question, but with no question mark
    and no question word nothing saw one: the reply was "Got it.",
    the minimum was never given, and "MOQ" went onto the lead as
    the number of designs. Deliberately narrow: a few words, no
    digits, and the whole message has to be the topic.
    """
    said = re.sub(r"[?.!,;:\s]+$", "", (text or "").strip())
    if not said or re.search(r"\d", said):
        return None
    if len(said.split()) > 3:
        return None
    for name, asked, _answered, _vol, _q in TOPICS:
        if asked.search(said):
            return name
    return None


def topic_query(topic_name: str) -> str:
    for name, _a, _b, _c, query in TOPICS:
        if name == topic_name:
            return query
    return topic_name


def fact_topics_asked(text: str) -> list[str]:
    return [name for name, asked, _a, _v, _q in TOPICS if asked.search(text or "")]


def _statements_only(reply: str) -> str:
    """Only the part of a reply that is not itself a question counts
    as an answer. Asked "Do you guys print in house?", the old
    writer replied "Do you want us to print in house for boxes, bags,
    or labels?" — the words were there and nothing was answered."""
    return " ".join(
        s for s in re.split(SENTENCE_BREAK, reply or "")
        if not is_question_sentence(s))


def fact_questions_unanswered(visitor_text: str, reply: str) -> list[str]:
    statements = _statements_only(reply)
    # A whole sentence of courtesy is not an answer either.
    statements = re.sub(
        r"^(got it|great|perfect|thanks|thank you|understood|sure|noted)[,.! ]*",
        "", statements, flags=re.I).strip()
    return [name for name, asked, answered, _v, _q in TOPICS
            if asked.search(visitor_text or "") and not answered.search(statements)]


def facts_volunteered(visitor_said: list, reply: str, minimum_due: bool = False) -> list[str]:
    """Facts a reply recites that nobody asked about. The minimum is
    exempt when the quantity is under it, because then saying it is
    the job."""
    asked = "\n".join(str(t or "") for t in visitor_said)
    out = []
    for name, asked_re, _ans, volunteered, _q in TOPICS:
        if volunteered and volunteered.search(reply or "") \
                and not asked_re.search(asked) \
                and not (name == "the minimum order" and minimum_due):
            out.append(name)
    return out


def without_volunteered_facts(reply: str, topics: list[str]) -> str:
    patterns = [vol for name, _a, _b, vol, _q in TOPICS
                if name in topics and vol]
    return " ".join(
        s for s in re.split(SENTENCE_BREAK, reply or "")
        if not any(p.search(s) for p in patterns)).strip()


def with_answers_before_question(reply: str, answers: list[str]) -> str:
    """The answers put in front of the reply's question, after its
    acknowledgement. Answer first, then ask — never the other way."""
    sentences = re.split(SENTENCE_BREAK, reply or "")
    at = next((i for i, s in enumerate(sentences) if "?" in s), -1)
    if at < 0:
        return " ".join([*sentences, *answers])
    return " ".join([*sentences[:at], *answers, *sentences[at:]])
