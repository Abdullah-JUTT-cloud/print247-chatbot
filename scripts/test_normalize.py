"""Normalization tests (Oct 30): typo auto-fix + fragment detection
+ "did you mean" interpretation."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.chat.normalize import (correct_query, interpret_fragment,
                                is_fragment)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name} :: {detail}")


# --- typo correction ---
check("lables -> labels", correct_query("I need lables") == "I need labels",
      correct_query("I need lables"))
check("buissness -> business",
      correct_query("buissness cards") == "business cards",
      correct_query("buissness cards"))
check("bannars -> banners",
      correct_query("do you make bannars?") == "do you make banners?",
      correct_query("do you make bannars?"))
check("mattee -> matte", correct_query("mattee finish") == "matte finish",
      correct_query("mattee finish"))
check("myalr -> mylar", correct_query("myalr bags") == "mylar bags",
      correct_query("myalr bags"))
check("standup -> stand-up",
      correct_query("standup pouches") == "stand-up pouches",
      correct_query("standup pouches"))
# --- never mangled ---
check("dimensions untouched", correct_query("100x150mm") == "100x150mm")
check("cart never becomes card", correct_query("is there a cart?") == "is there a cart?")
check("cares never becomes cards",
      correct_query("who cares") == "who cares")
check("code untouched", correct_query("discount code") == "discount code")
check("names untouched", correct_query("Rosenberg") == "Rosenberg")
check("ordinary words untouched",
      correct_query("what sizes do you offer?") == "what sizes do you offer?",
      correct_query("what sizes do you offer?"))
check("correct words untouched",
      correct_query("I need boxes") == "I need boxes")

# --- fragments ---
check("trailing ellipsis is a fragment", is_fragment("I need boxes for..."))
check("dangling word is a fragment", is_fragment("boxes for"))
check("leading preposition is a fragment", is_fragment("for candles"))
check("single content word is a fragment", is_fragment("candles"))
check("number is never a fragment", not is_fragment("400"))
check("dimension is never a fragment", not is_fragment("4x6"))
check("yes is never a fragment", not is_fragment("yes"))
check("greeting is never a fragment", not is_fragment("hi"))
check("full sentence is not a fragment", not is_fragment("I need boxes"))
check("full question is not a fragment",
      not is_fragment("what is your MOQ?"))

# --- interpretation ---
check("fragment + context product interprets",
      interpret_fragment("for candles", "box")
      == ("boxes for candles", "do you make boxes for candles?"),
      str(interpret_fragment("for candles", "box")))
check("fragment + mylar context interprets",
      interpret_fragment("for coffee", "mylar")
      == ("mylar pouches for coffee", "do you make mylar pouches for coffee?"),
      str(interpret_fragment("for coffee", "mylar")))
check("no product and no product word means no interpretation",
      interpret_fragment("for candles", None) is None)
check("pure product fragment means no interpretation",
      interpret_fragment("boxes for...", "box") is None)
check("empty fragment means no interpretation",
      interpret_fragment("for...", "box") is None)

# Trigger gate: only use/purpose phrases qualify. Bare single
# words are answers (a name, a unit, 'stop', 'sí') or non-answers
# the pending question re-asks — the trigger must never swallow
# them (it did, and broke the contact flow, stop, the unit
# question, and the Spanish switch answer).
from app.chat.normalize import fragment_product, is_use_fragment
check("leading-prep phrase is a use fragment",
      is_use_fragment("for candles"))
check("dangling-prep phrase is a use fragment",
      is_use_fragment("boxes for"))
check("single word is never a use fragment",
      not is_use_fragment("Abdullah") and not is_use_fragment("stop")
      and not is_use_fragment("mm") and not is_use_fragment("sí"))
check("fragment product resolves from session first",
      fragment_product("for candles", "box") == "box")
check("fragment product resolves from a product word",
      fragment_product("for candle boxes", None) == "box")

print(f"NORMALIZE: {len(FAILURES)} failed")
if FAILURES:
    sys.exit(1)
print("All normalization cases passed.")
