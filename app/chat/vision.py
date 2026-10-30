"""Design-image vision: look at an uploaded design and say what is
visibly in it — nothing more.

Rules (Oct 30, user's call: "dekh kar bataye bhi"):
- Describe ONLY what is visible: layout, colours, readable text,
  logo/picture presence. Never guess a brand, never invent text
  that cannot be read, never estimate price, printability or
  quality from the image.
- The description is a visitor-facing note, NEVER a KB fact: it is
  not cited as a source, not stored in the KB, and not used to
  answer other questions.
- Fail-soft like SRAG: no key, no model, any error, a non-image
  file (PDF/AI/ZIP design files are stored, never described) ->
  None. A missing description must never break the chat or the
  upload; the file is still saved with the quote.
"""

import os

IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}

VISION_PROMPT = (
    "Describe ONLY what is visibly in this design image, in 2-3 short "
    "sentences: the layout, the main colours, any text you can actually "
    "read, and whether there is a logo or picture. Do not guess the brand "
    "or company, do not invent text you cannot read, do not comment on "
    "price, print quality or printability. If the image is unclear or "
    "blank, say so plainly."
)


def describe_image(data: bytes, mime: str, llm_fn=None) -> str | None:
    """One-shot vision description, or None when unavailable.

    llm_fn(data, mime) -> str is injected (tests stub it, main.py
    passes the OpenAI one). No llm_fn, empty data or a non-image
    mime -> None without calling anything.
    """
    if not data or (mime or "").lower() not in IMAGE_MIMES:
        return None
    if llm_fn is None:
        return None
    try:
        out = (llm_fn(data, mime) or "").strip()
    except Exception:
        return None
    return out or None


def openai_vision_fn(data: bytes, mime: str) -> str:
    """Real vision call (gpt-5-mini, image input). Raises on any
    failure — describe_image turns that into None."""
    import base64

    from openai import OpenAI

    b64 = base64.b64encode(data).decode("ascii")
    client = OpenAI()
    resp = client.chat.completions.create(
        model=os.environ.get("VISION_MODEL", "gpt-5-mini"),
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        timeout=30,
    )
    return (resp.choices[0].message.content or "").strip()
