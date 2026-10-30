"""Deterministic replies in the visitor's language — the
deterministic half of the old bot's replyLanguage.ts.

The old bot translates its output sentence by sentence into the
visitor's language. Our LLM answers already do that through the
prompt; these are the DETERMINISTIC strings (script questions,
contact questions, MOQ/price notes, confirmation, finished-chat
lines, chips), which used to be English-only even when the visitor
wrote in Spanish or Roman Urdu.

Covered: es (Spanish — the largest non-English visitor group for a
US packaging shop) and ur-roman (Roman Urdu, the user's own test
language). Every other detected language falls back to English
deterministic text, while LLM answers still translate.
"""
import re

_STRINGS = {
    "q_product": {
        "es": "¿Qué producto busca? Por ejemplo, bolsas mylar, pouches, cajas o etiquetas.",
        "ur-roman": "Aap ko kya banwana hai? Masalan mylar bags, pouches, boxes ya labels?",
    },
    "q_sizes": {
        "es": "¿Qué tamaño necesita? Ancho x alto x profundidad, en pulgadas o mm.",
        "ur-roman": "Size kya chahiye? Width x height x depth, inches ya mm mein.",
    },
    "q_style_bags": {
        "es": "¿Qué estilo de bolsa Mylar necesita: plana, vertical o cuál?",
        "ur-roman": "Mylar bag ka kaunsa style chahiye: flat, stand-up ya koi aur?",
    },
    "q_style_boxes": {
        "es": "¿Qué estilo de caja necesita?",
        "ur-roman": "Box ka kaunsa style chahiye?",
    },
    "q_finishes": {
        "es": "¿Qué acabado prefiere: mate, brillo o tacto suave?",
        "ur-roman": "Finish kaunsi pasand hai: matte, gloss ya soft touch?",
    },
    "q_quantity": {
        # Oct 30 user rule: never volunteer the MOQ — the question
        # is just the question, in every language.
        "es": "¿Qué cantidad quiere pedir en su primer pedido?",
        "ur-roman": "Pehli order mein kitni quantity chahiye?",
    },
    "q_quantity_banner": {
        "es": "¿Qué cantidad quiere pedir en su primer pedido?",
        "ur-roman": "Pehli order mein kitni quantity chahiye?",
    },
    "q_per_design": {
        "es": "¿Cuántas unidades necesita por diseño?",
        "ur-roman": "Har design ke liye kitni units chahiye?",
    },
    "q_skus": {
        "es": "¿Cuántos diseños o SKUs tiene en total?",
        "ur-roman": "Total kitne designs ya SKUs hain?",
    },
    "q_design_image": {
        "es": "¿Tienes una imagen del diseño que quieres imprimir?",
        "ur-roman": "Kya aap ke paas design ki image hai jo print karwani hai?",
    },
    "q_extras": {
        "es": "¿Quiere que agregue un cierre y una muesca de rasgado?",
        "ur-roman": "Zipper aur tear notch add kar dun?",
    },
    "q_material": {
        "es": "¿Tiene algún material o característica especial en mente?",
        "ur-roman": "Koi khaas material ya special feature zehen mein hai?",
    },
    "q_name": {
        "es": "¿Me puede dar su nombre?",
        "ur-roman": "Aap ka naam kya hai?",
    },
    "q_email": {
        "es": "¿A qué correo debo enviar la cotización?",
        "ur-roman": "Quote kis email par bhejun?",
    },
    "q_phone": {
        "es": "¿A qué número de teléfono puede contactarlo el equipo?",
        "ur-roman": "Team aap ko kis phone number par contact kare?",
    },
    "moq_note": {
        "es": "Podemos revisar {qty} para usted. También hacemos tiradas más pequeñas.",
        "ur-roman": "Hum {qty} dekh sakte hain aap ke liye. Chhoti runs bhi kar lete hain.",
    },
    "smaller_run_note": {
        "es": "Le pasaré {qty} al equipo y le confirmaremos.",
        "ur-roman": "Main {qty} team ko de dunga aur aap ko confirm kar dunga.",
    },
    "price_line": {
        "es": "No puedo ponerle precio aquí: su cotización incluirá el precio.",
        "ur-roman": "Main yahan price nahi bata sakta — aap ki quote mein price hogi.",
    },
    "perfect_intro": {
        "es": "Perfecto — su solicitud de cotización está lista:",
        "ur-roman": "Perfect — aap ki quote request tayyar hai:",
    },
    "confirm_intro": {
        "es": "Solo para confirmar: ¿quiere",
        "ur-roman": "Confirm kar lun — kya aap chahte hain",
    },
    "below_min_note": {
        "es": "Nota: el equipo confirmará la tirada más pequeña con usted.",
        "ur-roman": "Note: team aap se chhoti run confirm karegi.",
    },
    "noted": {
        "es": "Anotado: lo agregué a su solicitud.",
        "ur-roman": "Noted — main ne ye aap ki request mein add kar diya hai.",
    },
    "not_sent": {
        "es": "Todavía no: la cotización no ha salido.",
        "ur-roman": "Abhi nahi — quote abhi send nahi hui.",
    },
    "signoff_a": {
        "es": "De nada, hablamos pronto.",
        "ur-roman": "Koi baat nahi — phir baat hogi.",
    },
    "signoff_b": {
        "es": "Genial, hablamos pronto.",
        "ur-roman": "Zaroor — phir baat hogi.",
    },
    "no_standard": {
        "es": "No hay un tamaño estándar: todo se hace a medida de lo que va dentro.",
        "ur-roman": "Koi standard size nahi hai — har cheez andar ki cheez ke hisaab se banti hai.",
    },
    "not_sure_sizes": {
        "es": "No hay problema: dime qué va dentro del paquete, o elige un tamaño común para empezar.",
        "ur-roman": "Koi baat nahi — batao andar kya hoga, ya ek common size choose kar lo shuru ke liye.",
    },
    "not_sure_quantity": {
        "es": "No hay problema: dime un rango aproximado y trabajaremos con eso.",
        "ur-roman": "Koi baat nahi — koi andaza de dein, usi se kaam kar lenge.",
    },
    "yes_correct": {
        "es": "Sí, es correcto",
        "ur-roman": "Ji, ye theek hai",
    },
    "change_quantity": {
        "es": "Cambiar cantidad",
        "ur-roman": "Quantity change karein",
    },
    "change_size": {
        "es": "Cambiar tamaño",
        "ur-roman": "Size change karein",
    },
    "chip_mylar": {
        "es": "Necesito bolsas mylar",
        "ur-roman": "Mujhe mylar bags chahiye",
    },
    "chip_boxes": {
        "es": "Necesito cajas personalizadas",
        "ur-roman": "Mujhe custom boxes chahiye",
    },
    "chip_labels": {
        "es": "Necesito etiquetas",
        "ur-roman": "Mujhe labels chahiye",
    },
    "chip_size_4x6": {
        "es": "Tamaño 4x6 pulgadas",
        "ur-roman": "Size 4x6 inches",
    },
    "purpose_q": {
        "es": "¿Para qué necesita el {product}?",
        "ur-roman": "Ye {product} kis kaam ke liye chahiye?",
    },
    "chip_purpose_shipping": {
        "es": "Envío",
        "ur-roman": "Shipping",
    },
    "chip_food": {
        "es": "Comida",
        "ur-roman": "Food",
    },
    "chip_gifts": {
        "es": "Regalos",
        "ur-roman": "Gifts",
    },
    "chip_retail": {
        "es": "Venta",
        "ur-roman": "Retail",
    },
    "chip_size_mm": {
        "es": "Tamaño 100x150mm",
        "ur-roman": "Size 100x150mm",
    },
    "chip_not_sure_size": {
        "es": "No estoy seguro del tamaño",
        "ur-roman": "Size ka nahi pata",
    },
    "chip_qty_1000": {
        "es": "1000 unidades",
        "ur-roman": "1000 units",
    },
    "chip_qty_5000": {
        "es": "5000 unidades",
        "ur-roman": "5000 units",
    },
    "chip_not_sure_qty": {
        "es": "No estoy seguro de la cantidad",
        "ur-roman": "Quantity ka nahi pata",
    },
    "chip_moq": {
        "es": "¿Cuál es el pedido mínimo?",
        "ur-roman": "Minimum order kya hai?",
    },
    "chip_shipping": {
        "es": "¿El envío es gratis?",
        "ur-roman": "Shipping free hai?",
    },
    "chip_refund": {
        "es": "¿Cuál es su política de reembolso?",
        "ur-roman": "Refund policy kya hai?",
    },
}

# English fallbacks live in the caller (the existing English text);
# this table only overrides es / ur-roman.
_FALLBACK_LANGS = ("en",)


def get(key: str, language: str, **fmt) -> str | None:
    """Translated string, or None when the language has no override
    (caller keeps its English text)."""
    if not language or language in _FALLBACK_LANGS:
        return None
    table = _STRINGS.get(key) or {}
    text = table.get(language)
    if text is None:
        return None
    for k, v in fmt.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def tr(key: str, language: str, english: str, **fmt) -> str:
    """Translated string, or the English text when untranslated."""
    out = get(key, language, **fmt)
    if out is not None:
        return out
    for k, v in fmt.items():
        english = english.replace("{" + k + "}", str(v))
    return english
