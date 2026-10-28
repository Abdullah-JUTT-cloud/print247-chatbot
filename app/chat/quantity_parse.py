"""Quantity parsing — ported from the old bot (minimumOrder.ts).

Rules that used to be prompt guesses and are now code:
- Links and email addresses are not quantities (a WhatsApp ad link's
  digits were once read as an order of thousands).
- The FIRST number in a range counts ('50-100' asks whether 50 is
  possible). '2k' is two thousand, not two.
- Words: 'fifty', 'two hundred', 'fifteen hundred', 'twenty five
  thousand'. Bare 'one'/'two' are NOT quantities on their own — the
  rules below know 'one design' from 'one box'.
- A quantity under the minimum, once stated, is answered once, not
  haggled over every turn (minimum_already_stated / wants_smaller_run /
  answer_to_the_minimum / asked_to_go_below_minimum).

POLICY NOTE (kept from the new bot, NOT the new old-bot snapshot):
the old snapshot flipped SAY_THE_MINIMUM_ON_A_LOW_QUANTITY to false
('the team takes orders under 1000'), but the site-published MOQ is
1000 per size and sales has not signed off a sub-1000 policy, so the
new bot still states the minimum. Only the parsing + answer-reading
machinery is ported; the policy decision stays with sales.
"""
import re

MINIMUM_ORDER = 1000
_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
          "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
          "couple": 2, "few": 3}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_QUANTITIES = {"single": 1, "one": 1, "two": 2, "couple": 2, "three": 3,
                    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                    "nine": 9, "ten": 10}
_STATES_THE_MINIMUM = re.compile(r"\bmoq\b|\bminimum\b|\b1,?000 per\b", re.IGNORECASE)
_WANTS_LESS = re.compile(
    r"\b(?:smaller|less|lesser|lower|fewer|reduce[d]?|not that many|too many|under (?:the )?(?:minimum|moq|1,?000)|below (?:the )?(?:minimum|moq|1,?000))\b"
    r"|\bcan(?:'|’)?t (?:do|afford|manage) (?:that|1,?000)\b",
    re.IGNORECASE)
_BARE_QUANTITY = re.compile(
    r"^[^a-z]*(?:just|only|still|about|around)?\s*[\d,.\s]+\s*(?:pcs|pieces|units|boxes|bags|labels|stickers|pouches)?[^a-z]*$",
    re.IGNORECASE)
_ASKS_IF_THE_MINIMUM_WORKS = re.compile(
    r"\b(?:would|does|will)\b[^?]{0,40}\bwork\b|\bwork(?:s)? for you\b|\bis that (?:ok|okay|fine|alright|workable)\b"
    r"|\bare you (?:ok|okay|fine) with\b|\bhappy with that\b|\bcan you (?:do|manage) that\b",
    re.IGNORECASE)
_BARE_YES = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|sure|ok(?:ay)?|fine|perfect|great|agreed|that works|works for me|sounds good|go ahead|let'?s do it|no problem)\b[\s.!,]*$",
    re.IGNORECASE)
_BARE_NO = re.compile(
    r"^\s*(?:no|nope|nah|not really|afraid not|unfortunately not|that'?s? too (?:many|much)|too many|too much)\b[\s.!,]*$",
    re.IGNORECASE)


def spelled_number_in(text: str) -> int | None:
    """A quantity written in words, or None. Only a run with a tens
    word, 'hundred' or 'thousand' in it counts."""
    words = [w for w in re.split(r"[^a-z]+", (text or "").lower().replace("-", " ")) if w]
    best = None
    for i in range(len(words)):
        total, current, big, used = 0, 0, False, 0
        for w in words[i:]:
            if w in _UNITS:
                current += _UNITS[w]
            elif w in _TENS:
                current += _TENS[w]
                big = True
            elif w == "hundred":
                current = (current or 1) * 100
                big = True
            elif w == "thousand":
                total += (current or 1) * 1000
                current = 0
                big = True
            elif w == "and" and used > 0:
                continue
            elif w in ("a", "an") and used == 0:
                continue
            else:
                break
            used += 1
        value = total + current
        if used and big and value > 0:
            best = max(best or 0, value)
    return best


def quantity_in(value: str | None) -> int | None:
    """The number in what they said, or None."""
    text = re.sub(r"https?://\S+|www\.\S+|\S+@\S+", " ", value or "").strip().lower()
    if not text:
        return None
    # Design counts are not quantities (when no unit/product word).
    if (re.search(r"\b(one|single|two|\d+)\s*(?:designs?|skus?|artworks?|variants?)\b", text)
            and not re.search(r"\b(boxes?|bags?|labels?|pouches?|units?|pcs?|pieces?)\b", text)):
        return None
    m = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|million)?\b", text)
    if m:
        n = float(m.group(1).replace(",", ""))
        mult = (m.group(2) or "").lower()
        if mult in ("k", "thousand"):
            n *= 1000
        elif mult == "million":
            n *= 1000000
        return int(n)
    return spelled_number_in(text)


def tidy_quantity(value: str | None) -> str:
    """'15000' -> '15,000'; words and blanks pass through."""
    q = quantity_in(value)
    return f"{q:,}" if q is not None else (value or "")


def below_minimum(value: str | None) -> bool:
    q = quantity_in(value)
    return q is not None and q < MINIMUM_ORDER


def quantity_is_a_pack_count(quantity: str | None, visitor_said: list) -> bool:
    """True if the recorded quantity is really a pack count ('10 ct')
    that the visitor also mentioned as a pack count."""
    if not quantity:
        return False
    joined = " ".join(visitor_said or [])
    return bool(re.search(r"\b\d+\s*(?:ct|count|pack)\b", joined, re.IGNORECASE))


def minimum_already_stated(bot_messages: list) -> bool:
    return any(_STATES_THE_MINIMUM.search(m or "") for m in bot_messages)


def wants_smaller_run(text: str) -> bool:
    said = (text or "").strip()
    if not said:
        return False
    if _WANTS_LESS.search(said):
        return True
    return bool(_BARE_QUANTITY.match(said)) and below_minimum(said)


def answer_to_the_minimum(their_reply: str, our_question: str) -> str | None:
    """'smaller' | 'minimum' | None. A bare yes/no only counts against
    a question that states the minimum AND asks if it works AND has no
    'or' (an either/or 'yes' means nothing). Nothing is guessed."""
    said = (their_reply or "").strip()
    if not said:
        return None
    if wants_smaller_run(said):
        return "smaller"
    named = quantity_in(said)
    if named is not None and named >= MINIMUM_ORDER:
        return "minimum"
    question = our_question or ""
    answerable = (_STATES_THE_MINIMUM.search(question)
                  and _ASKS_IF_THE_MINIMUM_WORKS.search(question)
                  and not re.search(r"\bor\b", question, re.IGNORECASE))
    if not answerable:
        return None
    if _BARE_YES.match(said):
        return "minimum"
    if _BARE_NO.match(said):
        return "smaller"
    return None


def asked_to_go_below_minimum(messages: list) -> bool:
    """Transcript check: after we stated the minimum, did the visitor's
    last standing answer ask for the smaller run? Only what they said
    AFTER we said it counts; the last answer wins."""
    stated = next((i for i, m in enumerate(messages)
                   if m.get("from_us") and _STATES_THE_MINIMUM.search(m.get("text", ""))), -1)
    if stated == -1:
        return False
    standing = None
    for at in range(stated + 1, len(messages)):
        if messages[at].get("from_us"):
            continue
        asked = next((m.get("text", "") for m in reversed(messages[:at]) if m.get("from_us")), "")
        answer = answer_to_the_minimum(messages[at].get("text", ""), asked)
        if answer:
            standing = answer
    return standing == "smaller"
