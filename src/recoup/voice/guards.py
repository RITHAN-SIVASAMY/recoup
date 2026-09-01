"""FR-10.5/FR-10.6/CON-03: safe degradation. Low ASR confidence, silence,
hostility, or distress/dispute/legal keywords all force `safe_exit`
(`voice/graph.py`) before the turn ever reaches intent routing — "never
improvise" means the guard check runs first, unconditionally, on every
turn, not just when something looks obviously wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

GuardReason = Literal["low_confidence", "silence", "hostility", "distress", "dispute", "legal"]

MIN_ASR_CONFIDENCE = 0.55

_DISTRESS_PATTERNS = (
    r"\b(suicide|khudkushi|marne wala|kill myself|can'?t (take|handle) (it|this) anymore)\b",
    r"\b(depress(ed|ion)|hopeless|helpless)\b",
)
_DISPUTE_PATTERNS = (
    r"\b(never (ordered|bought|took)|fraud(ulent)?|not my (order|charge|transaction))\b",
    r"\b(dispute|chargeback|galat charge|maine nahi kiya)\b",
)
_LEGAL_PATTERNS = (r"\b(lawyer|advocate|wakeel|legal action|court|consumer forum|sue|police)\b",)
_HOSTILITY_PATTERNS = (
    # deliberately NOT "stop calling me" — that's a calm opt-out request
    # (voice/intent.py's wants_opt_out), not hostility; conflating the two
    # would make FR-10.3's "opt-out, honoured in-call" force a safe-exit
    # apology instead of a clean opt-out for anyone who asks politely.
    r"\b(shut up|chup ho jao|bakwas|harass(ment|ing)?)\b",
)


@dataclass(frozen=True)
class GuardTrigger:
    reason: GuardReason
    detail: str


def _matches_any(patterns: tuple[str, ...], text: str) -> str | None:
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def check_guards(
    utterance: str | None, *, asr_confidence: float | None, silence: bool = False
) -> GuardTrigger | None:
    """Returns the reason a turn must safe-exit, or `None` if it's clear to
    proceed to normal intent routing. Checked in a fixed order — silence and
    confidence first, since a garbled or empty utterance can't be reliably
    scanned for keywords at all."""
    if silence or not utterance or not utterance.strip():
        return GuardTrigger("silence", "no usable customer utterance")
    if asr_confidence is not None and asr_confidence < MIN_ASR_CONFIDENCE:
        return GuardTrigger(
            "low_confidence", f"ASR confidence {asr_confidence:.2f} below threshold"
        )

    if hit := _matches_any(_DISTRESS_PATTERNS, utterance):
        return GuardTrigger("distress", hit)
    if hit := _matches_any(_DISPUTE_PATTERNS, utterance):
        return GuardTrigger("dispute", hit)
    if hit := _matches_any(_LEGAL_PATTERNS, utterance):
        return GuardTrigger("legal", hit)
    if hit := _matches_any(_HOSTILITY_PATTERNS, utterance):
        return GuardTrigger("hostility", hit)
    return None
