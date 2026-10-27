"""Chat brain package.

Why this is split into small files, not one big main.py:
each piece is a rule the old bot learned the hard way, and a rule
that lives in code (not in a prompt) cannot be talked out of by a
clever customer message. The LLM writes sentences; the code below
decides what is true, what is missing, and when to hand off.
"""
