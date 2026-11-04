"""Regression test for vague recommendations during the extras step."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chat.brain import handle_message


messages = [
    "I need mylar bags",
    "ab@gmail.com",
    "Size 4x6 inches",
    "Flat",
    "Matte",
    "1000 units",
    "1 design",
    "not yet",
    "whats is best?",
]

result = None
for message in messages:
    result = handle_message(
        message, session_id="vague-extras-regression-fresh", store=None)

reply = result["reply"]
assert all(word not in reply for word in ("Cottonwood", "Rosenberg", "1631")), reply
assert all(not source.endswith("/contact.md") for source in result["sources"]), result["sources"]
assert ("zipper" in reply.lower() and "tear notch" in reply.lower()) \
    or "best for what" in reply.lower(), reply
assert result["missing"][0] == "extras", result["missing"]

print("PASS vague extras recommendation stays in extras context")
