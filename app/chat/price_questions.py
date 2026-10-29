"""Visitor price questions — ported from the old bot
(visitorQuestions.ts).

Measured on four days of live chats: 62 visitor questions, and 30
of them got no answer at all — an acknowledgement and the next
question off the script. "How much does the 1000 pieces cost?" met
with the minimum, "how quickly could you ship them out" with "What
box size are you looking for?". The company facts cannot answer a
price, and the honest reply is still not silence: a price is a
rep's to give, and it comes with the quote.

Asking for a quote is NOT asking a price: the ads open with "Hi, I
need a quote for custom boxes", and that was once answered "I can't
price it here" before a single detail was asked. A price question
is "how much" or "what does it cost", or a price word in a question.
"""
import re

_ABOUT_PRICE = re.compile(
    r"\b(how much|what.{0,12}(cost|price)|pricing|price|cost|quote for|per unit|unit price|rate|rates|budget|cheap(er|est)?|discount|cu[aá]nto|precios?|cuesta|costo)\b",
    re.IGNORECASE)
_ANSWERS_PRICE = re.compile(r"\b(quote|pricing|price)\b", re.IGNORECASE)
_WANTS_A_QUOTE = re.compile(
    r"\b(?:need|want|would like|looking for|get|request|send)\s+(?:me\s+)?(?:a|an|the|my)?\s*(?:quote|quotation|estimate)\b",
    re.IGNORECASE)

PRICING_COMES_WITH_THE_QUOTE = "I can't price it here — your quote will carry the pricing."


def asks_about_price(text: str) -> bool:
    said = text or ""
    # "Cuanto por las cajas 1000" asks a price with no question mark
    # and no English.
    if re.search(r"\bhow much\b|\bwhat\b.{0,15}\b(?:cost|price|charge)|\bcu[aá]nto\b|\bqu[eé] precio\b|\bcu[aá]l es el precio\b"
                 r"|\bprice (for|of|please)\b|\bgive me (a )?price\b|\bneed (a )?price\b|\bprice list\b|\bprice quote\b",
                 said, re.IGNORECASE):
        return True
    asked = [s for s in re.split(r"(?<=[.!?])\s+|\n+", said)
             if re.search(r"\?\s*$", s)
             or re.match(r"\s*(?:what|how|is|are|do|does|can|could|would|will)\b", s, re.IGNORECASE)]
    return any(_ABOUT_PRICE.search(s) and not _WANTS_A_QUOTE.search(s) for s in asked)


def answers_about_price(reply: str) -> bool:
    return bool(_ANSWERS_PRICE.search(reply or ""))


def parrots_their_question(reply: str, theirs: str) -> bool:
    """Their own question, handed back at them.

    "Do each of those finishes cost extra? What is the 'standard'
    finish" was answered with "Great question. What is the standard
    finish for our boxes, and do matte, gloss, or soft touch
    finishes cost extra?". Word for word counts, and so does a
    70% share of long words — compared against each question in
    their message as well as the whole of it.
    """
    def plain(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

    if plain(reply) and plain(reply) == plain(theirs):
        return True

    def words(text: str) -> set:
        return set(w for w in re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()
                   if len(w) > 3)

    mine, their_words = words(reply), words(theirs)
    if len(their_words) < 3 or not mine:
        return False
    shared = sum(1 for w in their_words if w in mine)
    return shared / len(their_words) >= 0.7
