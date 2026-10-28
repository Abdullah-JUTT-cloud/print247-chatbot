"""Language detection — deterministic heuristic, no LLM call.

Why: the old bot thought in English and translated on output. That
pattern stays, but it needs to know WHAT to translate into first.
This is a first guess only: if it is wrong, the LLM answer step can
still reply in the visitor's language, because the visitor's own
message is in the prompt. Urdu in Arabic script and Roman Urdu are
included here — the old bot had neither.
"""
import re

_ARABIC = re.compile(r"[\u0600-\u06FF]")
_ROMAN_URDU = [
    "mujhe", "chahiye", "kitne", "kya", "hai", "kaise", "kab", "kahan",
    "price", "batao", "bataen", "chahte", "ho", "mera", "meri", "aur",
]
_SPANISH = [
    "necesito", "quiero", "cuánto", "cuanto", "precio", "gracias",
    "bolsas", "cajas", "etiquetas", "tamaño", "tamano",
]


# Old-bot word lists (visitorLanguage.ts), ported for French, German,
# Portuguese and Italian, plus non-Latin scripts. Existing behaviour
# is kept first: Arabic script is Urdu here (the old bot had no Urdu),
# and the short Spanish / Roman-Urdu lists above still win for those.
_WORDS = {
    "en": ("the and you your for with are is this that have can will our we to of in it be on not please thank thanks "
           "would like what how need want looking hello hi hey yes size box boxes bags labels much price quote").split(),
    "es": ("el la los las del que y en un una por para con es esta estan son su sus usted ustedes gracias hola buenas buenos "
           "buen dia dias tardes noches quiero quisiera queria necesito cuanto cuanta cuesta precio cajas caja bolsas bolsa "
           "etiquetas tambien puede pero como mas muy si mi tu te tienes tiene hablo habla espanol ingles entiendo saber "
           "favor cotizacion presupuesto tamano cantidad").split(),
    "fr": ("le la les des du et est un une pour avec vous nous je bonjour bonsoir merci votre vos sont dans pas que qui sur "
           "mais tres prix besoin voudrais boites boite sacs etiquettes parlez francais anglais combien devis").split(),
    "pt": ("o os as que e em um uma para com nao voce vc obrigado obrigada ola oi preciso quero tambem esta sao mais muito "
           "preco caixas caixa sacos etiquetas tudo bem fala falo portugues ingles orcamento quanto").split(),
    "de": ("der die das und ist ich sie wir nicht mit fur ein eine zu auf den dem danke hallo bitte haben konnen sind auch "
           "preis kartons tuten etiketten sprechen deutsch englisch angebot").split(),
    "it": ("il lo gli di che e un una per con non sono grazie ciao buongiorno vorrei anche prezzo molto della scatole "
           "buste etichette parla italiano inglese preventivo").split(),
}
_MARKS = {"es": re.compile(r"[ñ¿¡]"), "pt": re.compile(r"[ãõ]"), "de": re.compile(r"[ß]")}
_STATED = [
    ("en", re.compile(r"\b(?:in english|speak english|english please)\b", re.IGNORECASE)),
    ("es", re.compile(r"\b(?:no h?ablo ingl[eé]s|no s[eé] ingl[eé]s|^no ingl[eé]s\W*$|no entiendo(?: el)? ingl[eé]s|solo h?ablo espa[nñ]ol|h?ablas? espa[nñ]ol|en espa[nñ]ol|^espa[nñ]ol$)\b", re.IGNORECASE)),
    ("pt", re.compile(r"\b(?:fala portugu[eê]s|falo portugu[eê]s|em portugu[eê]s|n[aã]o falo ingl[eê]s)\b", re.IGNORECASE)),
    ("fr", re.compile(r"\b(?:parlez[- ]vous fran[cç]ais|je parle fran[cç]ais|en fran[cç]ais|je ne parle pas anglais)\b", re.IGNORECASE)),
    ("de", re.compile(r"\b(?:sprechen sie deutsch|auf deutsch|ich spreche (?:kein )?(?:deutsch|englisch))\b", re.IGNORECASE)),
    ("it", re.compile(r"\b(?:parla italiano|in italiano|non parlo inglese)\b", re.IGNORECASE)),
]
_GREETINGS = [
    ("es", re.compile(r"^(?:hola|buenas|buenos d[ií]as|buen d[ií]a)\b", re.IGNORECASE)),
    ("fr", re.compile(r"^(?:bonjour|bonsoir|salut)\b", re.IGNORECASE)),
    ("pt", re.compile(r"^(?:ol[aá]|oi|bom dia|boa tarde|boa noite)\b", re.IGNORECASE)),
    ("de", re.compile(r"^(?:hallo|guten tag|guten morgen)\b", re.IGNORECASE)),
    ("it", re.compile(r"^(?:ciao|buongiorno|buonasera)\b", re.IGNORECASE)),
]
_SCRIPTS = [
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("zh", re.compile(r"[一-鿿]")),
    ("ja", re.compile(r"[぀-ヿ]")),
    ("ko", re.compile(r"[가-힯]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
    ("he", re.compile(r"[֐-׿]")),
    ("th", re.compile(r"[฀-๿]")),
    ("el", re.compile(r"[Ͱ-Ͽ]")),
]


def detect_language(text: str) -> str:
    """Return 'en', 'es', 'ur' (Arabic script), 'ur-roman', or an
    old-bot code: 'fr', 'de', 'pt', 'it', 'ru', 'zh', 'ja', 'ko',
    'hi', 'he', 'th', 'el'. Deterministic replies stay in English;
    the LLM step answers in the returned code."""
    t = (text or "").strip()
    if not t:
        return "en"
    if _ARABIC.search(t):
        return "ur"
    low = t.lower()
    words = set(re.findall(r"[a-záéíóúñ]+", low))
    if words & set(_SPANISH):
        return "es"
    if words & set(_ROMAN_URDU):
        return "ur-roman"
    raw = re.sub(r"https?://\S+", " ", t)
    raw = re.sub(r"[\w.+-]+@[\w-]+\.[a-z.]+", " ", raw, flags=re.IGNORECASE)
    trimmed = raw.strip()
    for code, pat in _STATED:
        if pat.search(trimmed):
            return code
    letters = len(re.findall(r"[^\W\d_]", raw))
    if letters:
        for code, pat in _SCRIPTS:
            in_script = len(pat.findall(raw))
            if in_script >= 3 and in_script / max(letters, 1) > 0.3:
                return code
    for code, pat in _GREETINGS:
        if pat.search(trimmed) and (code != "de" or letters > 12):
            return code
    if letters < 6:
        return "en"
    tokens = [tok for tok in re.findall(r"[a-záéíóúñàâäèêëîïôöùûüç]+", raw.lower())
              if len(tok) > 1]
    score = {}
    for code, lst in _WORDS.items():
        s = set(lst)
        score[code] = sum(1 for tok in tokens if tok in s)
    for code, pat in _MARKS.items():
        score[code] = score.get(code, 0) + 2 * len(pat.findall(raw))
    best, best_score = max(((c, s) for c, s in score.items() if c != "en"),
                           key=lambda kv: kv[1], default=(None, 0))
    if best and best_score >= 3 and best_score >= 2 * score["en"]:
        return best
    if best and best_score >= 2 and score["en"] == 0:
        return best
    if score["en"] >= 2:
        return "en"
    return "en"
