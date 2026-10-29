"""Visitor-intent checks — ported from the old bot (notACustomer.ts and
the intent functions at the top of salesiq/chatEngine.ts, NEW snapshot).

Every check here is code, not a prompt rule, for the same reason the
old bot moved them into code: a model gets these right most of the
time, and the times it does not are exactly the times somebody is
being talked at by a machine that plainly is not listening.
"""
import re

# --- Not a customer (notACustomer.ts) ---
_WANTS_A_JOB = re.compile(
    r"\b(?:looking|look|searching|search|hunting|need|needs|needed|want|wanted|apply|applying|application|interested)\b[^.?!]{0,30}\b(?:for\s+)?(?:a\s+|any\s+|some\s+)?(?:job|jobs|work|employment|vacancy|vacancies|position|hiring|career)\b"
    r"|\b(?:job|work|employment)\s+(?:opportunit|openings?|vacanc|application)"
    r"|\b(?:are|you)\s+(?:you\s+)?hiring\b|\bany\s+(?:job|work|vacanc|opening)",
    re.IGNORECASE)
_WANTS_TO_WORK_FROM_HOME = re.compile(
    r"\b(?:work|working|job|jobs)\s+(?:from|at)\s+home\b|\bwork\s*from\s*home\b"
    r"|\bhome\s*(?:based\s*)?(?:packing|packaging|assembly)\s*(?:job|jobs|work)\b"
    r"|\b(?:packing|packaging|assembly)\s+(?:job|jobs|work)\b",
    re.IGNORECASE)
_SENDING_A_CV = re.compile(r"\b(?:my\s+)?(?:cv|resume|résumé|curriculum vitae)\b", re.IGNORECASE)
# A customer sentence outranks the job checks: "I need a job done:
# 5000 mylar bags" is an order. Nothing is turned away on a word when
# the enquiry itself is sitting right there.
_IS_REALLY_AN_ENQUIRY = re.compile(
    r"\b(?:quote|quotation|pricing|price|order|mylar|pouch(?:es)?|bags?|boxe?s?|labels?|stickers?|packaging|banners?|cartons?|mailers?|sleeves?|print(?:ing|ed)?)\b",
    re.IGNORECASE)
_PITCHING_TO_US = re.compile(
    r"\bdear\s+(?:purchasing|procurement|buyer|sir|madam|sir/madam)\b|\bpurchasing\s+manager\b|\bco\.?,?\s*ltd\b"
    r"|\b(?:we|our company)\s+(?:are|is)\s+(?:one of the leading|a leading|a professional)\b"
    r"|\bwe\s+(?:operate|run|own)\s+an?\s+[\w\s-]{0,30}(?:converting|printing|manufacturing|production)\s+(?:facility|factory|plant)\b"
    r"|\b(?:our|my)\s+(?:factory|company)\s+(?:can|could)\s+(?:produce|supply|offer|provide)\b"
    r"|\bbusiness\s+opportunit(?:y|ies)\b|\bdecision[\s-]?maker\b|\bsponsor(?:ship|ed|ing)?\b|\binfluencer\b|\bbrand\s+ambassador\b"
    r"|\b(?:advertise|promote)\s+(?:your|ur)\s+(?:products?|brand|company)\b"
    r"|\bwe(?:['’]re| are)\s+(?:\w+\s+){0,2}partnered with\b|\bexclusively partnered\b"
    r"|\bwe help (?:small (?:to medium[- ]sized )?)?(?:businesses|brands|companies)\b"
    r"|\b(?:our|my) (?:agency|marketing services|seo services)\b|\bwould love to (?:partner|collaborate)\b"
    r"|\blet'?s (?:partner|collaborate|work together)\b|\blooking to (?:partner|collaborate)\b"
    r"|\bwe are a supplier\b|\bpartnership\b|\bwant to (?:partner|collaborate)\b",
    re.IGNORECASE)
PITCH_MESSAGE = (
    "Thanks for getting in touch! This chat is for custom packaging and printing quotes, "
    "so I'm not able to help with supplier, partnership or promotion requests here. "
    "Please email Support@print247.us and the right team will pick it up.")
JOB_MESSAGE = (
    "Thanks for getting in touch! This chat is only for custom packaging and printing orders, "
    "so I can't help with job applications here. If it's about working with us, please "
    "email Support@print247.us and the right team will pick it up.")


def is_looking_for_work(text: str) -> bool:
    said = (text or "").strip()
    if not said:
        return False
    if _WANTS_A_JOB.search(said) or _WANTS_TO_WORK_FROM_HOME.search(said) or _SENDING_A_CV.search(said):
        return not _IS_REALLY_AN_ENQUIRY.search(said)
    return False


def chat_is_a_pitch(messages: list) -> bool:
    return any(_PITCHING_TO_US.search(t or "") for t in messages)


def chat_is_not_a_customer(messages: list) -> bool:
    """Whole-chat check: one customer sentence anywhere clears it."""
    said = [t.strip() for t in messages if (t or "").strip()]
    if not said:
        return False
    if any(_IS_REALLY_AN_ENQUIRY.search(t) for t in said):
        return False
    return any(is_looking_for_work(t) for t in said) or chat_is_a_pitch(said)


# --- Human / bot questions (chatEngine.ts) ---
_WANTS_HUMAN = re.compile(
    r"\b(human|person|agent|representative|rep\b|real (?:person|human)|someone else|speak to (?:a|an|someone|sales|support|rep)|talk to (?:a|an|someone|sales|support|rep)|operator|manager|customer service|live support|live chat|live agent)\b"
    r"|\b(?:don'?t|do not|not|no|stop|hate)\s+(?:want\s+to\s+)?(?:talk(?:ing)?\s*(?:to)?\s+|speak(?:ing)?\s*(?:to)?\s+|chat(?:ting)?\s*(?:with)?\s+)?(?:an?\s+)?(?:ai|bot|robot|automated|machine)\b"
    r"|\b(?:are you|is this)\s+(?:an?\s+)?(?:ai|bot|robot)\b",
    re.IGNORECASE)
_ASKS_IF_BOT = re.compile(
    r"\b(?:are you|r u|is this|am i (?:talking|speaking|chatting) (?:to|with))\s+(?:an?\s+|the\s+)?(?:real\s+)?(?:ai|bot|robot|chat ?bot|automated|machine|human|person)\b",
    re.IGNORECASE)
ANSWER_TO_ARE_YOU_A_BOT = (
    "I'm Print247's automated assistant. I'll take down what you need, and our team will follow up with your quote.")


def wants_a_person(text: str) -> bool:
    """Email addresses stripped first: 'human.e2e@example.com' typed in
    answer to the email question is not a request for a human."""
    return bool(_WANTS_HUMAN.search(re.sub(r"\S+@\S+", " ", text or "")))


def asks_if_we_are_a_bot(text: str) -> bool:
    return bool(_ASKS_IF_BOT.search(text or ""))


def asks_only_if_we_are_a_bot(text: str) -> bool:
    if not asks_if_we_are_a_bot(text):
        return False
    without = re.sub(
        r"\b(?:are you|r u|is this|am i (?:talking|speaking|chatting) (?:to|with))\b[^.?!]*[.?!]?",
        " ", text or "", flags=re.IGNORECASE)
    return not wants_a_person(without)


# --- Catalog / samples / price objection (chatEngine.ts, NEW snapshot) ---
_ASKS_FOR_A_CATALOG = re.compile(
    r"\b(?:catalog(?:ue)?s?|cat[aá]logo|brochures?|price ?list|lookbook)\b"
    r"|\b(?:photos?|pictures?|pics|images?|examples?|samples? of your work|fotos?|im[aá]genes|ejemplos?)\b[^.?!]{0,30}\b(?:products?|productos?|boxes|bags|labels|work|trabajos?|cajas|bolsas|etiquetas|you (?:make|have|do))\b"
    r"|\b(?:mandarme|enviarme|send me|show me)\s+(?:some\s+)?(?:fotos?|photos?|pictures?|examples?|ejemplos?)\b",
    re.IGNORECASE)
_ASKS_FOR_SAMPLES = re.compile(r"\b(?:free\s+)?samples?\b|\bmuestras?\b", re.IGNORECASE)
_OBJECTS_TO_THE_PRICE = re.compile(
    r"\b(?:too (?:high|expensive|much|pricey)|(?:price|pricing|cost)s? (?:is |are )?(?:too )?(?:high|expensive|steep)|we (?:get|pay|buy) (?:them|it|these|those)? ?(?:for|at)\b|cheaper (?:elsewhere|somewhere|than)|better price|muy caro)",
    re.IGNORECASE)
ANSWER_TO_A_CATALOG = (
    "We don't have a fixed catalog: everything is made to order in your size and design, "
    "and you can see photos and examples of our work at print247.us.")
ANSWER_TO_SAMPLES = "I've noted your sample request for the team, and they'll confirm what we can send."
ANSWER_TO_A_PRICE_OBJECTION = (
    "Thanks for telling me your current price. I'll pass it to the team so they can see what we can do on the quote.")


def asks_for_a_catalog(text: str) -> bool:
    return bool(_ASKS_FOR_A_CATALOG.search(text or ""))


def asks_for_samples(text: str) -> bool:
    return bool(_ASKS_FOR_SAMPLES.search(text or ""))


def objects_to_the_price(text: str) -> bool:
    return bool(_OBJECTS_TO_THE_PRICE.search(text or ""))


# --- Done / later / phone (chatEngine.ts) ---
_DONE_WITH_US = re.compile(
    r"\b(?:(?:no longer|not|am not|i'?m not)\s+interested\b(?!\s+in\b)|never\s?mind|forget (?:it|about it)|leave me alone|stop (?:messaging|texting|contacting|calling)|unsubscribe|don'?t (?:contact|message|text|call) me|ya no me interesa)|\b(?:good\s?bye|bye[\s-]bye)\b",
    re.IGNORECASE)
_LATER = re.compile(
    r"\b(?:(?:get|come|reach|circle)\s+back\s+(?:to\s+you\s+)?(?:later|tomorrow|soon|next week)|(?:talk|chat|speak)\s+(?:to\s+you\s+)?later|i(?:['’]ll| will)\s+(?:get back|come back|reach out|message you|let you know)\b|busy (?:right )?now|not (?:right )?now|later please)\b",
    re.IGNORECASE)
_OFFERS_A_NUMBER = re.compile(
    r"\b(?:can|could|may|shall|should)\s+i\s+(?:just\s+)?(?:give|send|share|leave|pass|text)\s+(?:you\s+)?(?:my\s+)?(?:phone|number|cell|mobile|whats\s?app|contact)|\bcall me\b"
    r"|\b(?:te|le)?\s*puedo\s+(?:pasar|dar|enviar|mandar)(?:te|le)?\s+(?:mi\s+)?(?:n[uú]mero|tel[eé]fono|cel(?:ular)?|whats\s?app)",
    re.IGNORECASE)
_WANTS_IT_HERE = re.compile(
    r"\b(?:send|give|tell|share|post)\s+(?:it|that|them|the (?:quote|price|pricing))?\s*(?:to me\s+)?(?:right\s+)?here\b"
    r"|\b(?:in|on|over|through)\s+(?:the|this)\s+chat\b|^\s*(?:just\s+)?here\W*$",
    re.IGNORECASE)
LATER_MESSAGE = "No problem, take your time. Just message us here whenever you're ready and we'll pick up where we left off."
DONE_WITH_US_MESSAGE = "Understood, thanks for your time. If you need packaging later, just message us here."
YES_SEND_YOUR_NUMBER = "Yes, please. What's the best phone number to reach you on?"
NO_EMAIL_THEN_PHONE = (
    "No problem. I can't send the full quote in this chat, so a phone number works instead. "
    "What's the best number to reach you on?")


def is_done_with_us(text: str) -> bool:
    return bool(_DONE_WITH_US.search(text or "")) and "?" not in (text or "")


def puts_it_off_for_now(text: str) -> bool:
    return bool(_LATER.search(text or "")) and "?" not in (text or "") and not re.search(r"\d", text or "")


def offers_a_phone_number(text: str) -> bool:
    return bool(_OFFERS_A_NUMBER.search(text or ""))


def wants_it_in_the_chat(text: str) -> bool:
    return bool(_WANTS_IT_HERE.search(text or ""))


# --- Already a customer (chatEngine.ts) ---
_ALREADY_A_CUSTOMER = re.compile(
    r"\b(i (already )?(purchased|ordered|bought|placed an order)|my (order|invoice|shipment|delivery|package|tracking)|(haven'?t|have not|hasn'?t|has not|still (haven'?t|not)) (received|got|arrived)|where is my|order (status|number)|already (have|received) (them|it|those)|refund|damaged|wrong (item|order|size)|previous order|last order|reorder|(was|been|am) (working|dealing|speaking|talking) with|\bMIA\b|(no|not) (response|responding|replying|reply)|gone quiet|stopped (responding|replying)|(still )?waiting (for|on) (your |the |my |a )?(feedback|reply|response|quote|answer|update)|any update|(didn'?t|did not|haven'?t|have not|never) (get|got|receive|received) (the |my |a |your )?quote|mi cotizaci[oó]n|(sent|send) you (the|my) (quote|details|artwork))\b",
    re.IGNORECASE)
ALREADY_CUSTOMER_MESSAGE = (
    "Thanks for telling me — let me pass this to a team member who can look into your existing order.")


def is_already_a_customer(text: str) -> bool:
    """Deliberately narrow: 'order' alone is not enough (plenty of new
    enquiries say 'I want to order'); it needs past tense, a delivery
    that has not arrived, or a complaint about an existing order."""
    return bool(_ALREADY_A_CUSTOMER.search(text or ""))


# --- Rep named (repPool.ts: repNamedIn, deterministic half) ---
def rep_named_in(text: str, session_rep: str | None = None):
    """A rep named by the visitor, other than the rep already on this
    chat. A full name always counts; a first name counts only when the
    session's own rep is known and different — otherwise 'Hi Frank'
    to a bot introduced as Frank would wrongly hand the chat over."""
    from .contacts import REP_NAMES
    low = (text or "").lower()
    for rep in REP_NAMES:
        if session_rep and rep.lower() == session_rep.lower():
            continue
        if re.search(rf"\b{re.escape(rep.lower())}\b", low):
            return rep
        if session_rep and re.search(rf"\b{re.escape(rep.split()[0].lower())}\b", low):
            return rep
    return None
