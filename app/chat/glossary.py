"""Technical-term explanations (Oct 30 senior transcript): when the
visitor asks what a term means, the bot must EXPLAIN it and re-ask
the pending question — never answer with a list, never advance past
the unclear step.

Terms are plain packaging definitions, not company claims: no
prices, no policies, nothing the KB would contradict. KB-grounded
extras (hang-hole types, zipper types) live in the variant map in
brain.py, not here.
"""

import re

_TERMS = [
    (("flat-bottom", "flat bottom"),
     "Flat-bottom pouches have a flat, boxy base, so they stand "
     "stable on a shelf and hold more, like a small box.",
     "kb/products/pouches.md"),
    (("stand-up", "stand up", "standup"),
     "A stand-up pouch has a bottom gusset, so it stands upright on "
     "a shelf on its own.",
     "kb/products/pouches.md"),
    (("flat",),
     "A flat pouch lies flat when empty — flat pouches have no "
     "gusset, so they take less space but do not stand up on their "
     "own.",
     "kb/products/pouches.md"),
    (("sku", "skus"),
     "SKU stands for Stock Keeping Unit. On an order, one SKU means "
     "one design variant: one artwork, in one size, with one set of "
     "finishes.",
     "kb/facts/sku.md"),
    (("moq",),
     "MOQ is the minimum order quantity — 1000 units per size for "
     "most products.",
     "kb/facts/moq.md"),
    (("gusset",),
     "A gusset is the extra folded material at the side or bottom "
     "that lets a pouch expand. So 5x8+3 means 5x8 inches plus a "
     "3-inch gusset.",
     "kb/products/pouches-mylar-sizes.md"),
    (("degassing valve", "valve"),
     "A degassing valve lets gas out of a coffee pouch without "
     "letting air in, so the coffee stays fresh.",
     None),
    (("hang hole",),
     "A hang hole is a punched hole at the top of a pouch so it can "
     "hang on a pegboard hook in a shop.",
     None),
    (("tear notch",),
     "A tear notch is a small cut at the edge so the pouch can be "
     "torn open by hand.",
     None),
    (("zipper", "ziplock", "zip lock"),
     "A zipper is a resealable closure, so the customer can open "
     "and close the pouch again.",
     None),
    (("soft touch", "soft-touch", "softtouch"),
     "Soft touch is a smooth, velvety feel on the pouch surface.",
     None),
    (("matte",),
     "Matte is a dull, non-shiny finish.",
     None),
    (("gloss", "glossy"),
     "Gloss is a shiny finish.",
     None),
    (("kraft",),
     "Kraft is unbleached brown paper or board — a natural look.",
     None),
    (("metallized", "metalized"),
     "Metallized means a thin metallic foil layer for high barrier "
     "protection — it keeps food fresh longer.",
     None),
    (("euro hole",),
     "A Euro hole is a slot-shaped hole for retail hooks.",
     None),
    (("sombrero",),
     "A sombrero hole is a rounded slot, wider than a round punch, "
     "for retail hooks.",
     None),
]

# "What is this?" after a terms list: explain the pending field's
# terms instead of asking what they mean (the visitor means the
# list they were just shown).
_THIS_BY_FIELD = {
    "style": ("flat-bottom", "stand-up", "flat"),
    "skus": ("sku",),
    "sizes": ("gusset",),
    "finishes": ("matte", "gloss", "soft touch"),
}


def _by_alias(alias: str) -> tuple[str, str | None] | None:
    for aliases, text, source in _TERMS:
        if alias in aliases:
            return text, source
    return None


def explain_term(text: str, pending_field: str | None = None) \
        -> tuple[str, list[str]] | None:
    """(Explanation, KB sources) for a 'what is X?' question, or
    None when the message is not a term question at all (the caller
    falls through to normal flow). A listing question ("what matte
    finishes do you have?") is NOT a definition — the listing guard
    keeps it out. A bare 'what is this?' resolves through the
    pending field's terms; with no pending context it asks what
    they mean instead of falling through to a random retrieval hit.
    Sources matter: the golden set requires the KB file behind a
    definition, so terms with a KB file cite it."""
    low = (text or "").lower().strip()
    for aliases, expl, source in _TERMS:
        for alias in aliases:
            pat = rf"\b{re.escape(alias)}\b"
            if not re.search(pat, low):
                continue
            if re.search(rf"\bwhat\s+(?:is|are)\b[^?]*{pat}", low):
                return expl, ([source] if source else [])
            if re.search(rf"\bwhat\s+does\b[^?]*{pat}[^?]*\bmean", low):
                return expl, ([source] if source else [])
            if re.search(rf"{pat}\s+means?\b", low):
                return expl, ([source] if source else [])
            if re.search(rf"\bmean\w*\s+by\s+{pat}", low):
                return expl, ([source] if source else [])
            if re.search(rf"\b(?:explain|define)\b[^?]*{pat}", low):
                return expl, ([source] if source else [])
            if low.startswith("what") and not re.search(
                    r"\b(offer|provide|have|give|show|list|kinds?|types?|options?|do you)\b",
                    low):
                return expl, ([source] if source else [])
    if re.search(r"\bwhat (?:is|are) (?:this|these|that|those|it)\b", low) \
            or re.search(r"\bwhat does (?:this|that) mean\b", low) \
            or low.strip("?.! ") in ("what is this", "what is that",
                                     "what does this mean"):
        keys = _THIS_BY_FIELD.get(pending_field or "")
        if keys:
            lines = []
            srcs = []
            for k in keys:
                found = _by_alias(k)
                if found:
                    lines.append(found[0])
                    if found[1] and found[1] not in srcs:
                        srcs.append(found[1])
            if lines:
                return " ".join(lines), srcs
        # No term list in context: ask what they mean instead of
        # falling through to a random retrieval hit (a fresh "what
        # is this?" once answered with a campaign shipping line).
        return ("Could you say which one you mean? For example, a "
                "pouch style, a size, or a material."), []
    return None
