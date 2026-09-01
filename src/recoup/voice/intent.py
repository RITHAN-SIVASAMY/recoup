"""A bounded, keyword-based customer-intent classifier. Deliberately not an
LLM call: the graph (`voice/graph.py`) is what may decide where a call goes,
and an intent classifier that can only ever return one of a fixed six
labels keeps that decision-making inside code, never inside a model's own
judgment — consistent with the authority table's "choose... never LLM".
"""

from __future__ import annotations

import re

from recoup.voice.graph import CustomerIntent

# Checked in this order: consent/safety intents always take priority over
# conversational ones, so "stop, I can't pay anyway" still opts them out.
_PATTERNS: tuple[tuple[CustomerIntent, tuple[str, ...]], ...] = (
    (
        "wants_opt_out",
        (r"\bstop\b", r"\bopt.?out\b", r"\bdon'?t call\b", r"\bmat\s+karo\b", r"\bband\s+karo\b"),
    ),
    (
        "wants_human",
        (r"\bhuman\b", r"\bagent\b", r"\breal person\b", r"\bmanager\b", r"\binsaan\b"),
    ),
    (
        "has_objection",
        (
            r"\bcan'?t\b",
            r"\bwon'?t\b",
            r"\bproblem\b",
            r"\bissue\b",
            r"\bnahi\s+ho",
            r"\bmushkil\b",
        ),
    ),
    (
        "wants_to_pay",
        (r"\bpay(ing)?\b", r"\bpayment\b", r"\bkar\s?doonga\b", r"\bkarunga\b", r"\bde\s?doonga\b"),
    ),
    (
        "confirms",
        (r"\byes\b", r"\bhaan\b", r"\bok(ay)?\b", r"\bth[ie]k\b", r"\bcorrect\b", r"\bsahi\b"),
    ),
    ("acknowledges", (r"\backnowledg", r"\bsamajh\b", r"\bsure\b", r"\bfine\b")),
)


def classify_intent(utterance: str) -> CustomerIntent:
    lowered = utterance.lower()
    for intent, patterns in _PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return intent
    return "other"
