"""CON-01: Recoup is recovery-only and strictly defensive. No pressure
tactics, no manufactured urgency, no false consequence, no shaming, no
third-party disclosure. Applied to every generated message — a violation
here fails the message, never gets softened, and never reaches a customer.

Pure and dependency-free; `tests/llm_eval/test_message_safety.py` runs this
against an adversarial suite of real model outputs (gated on a live API
key), but `check_message_safety` itself is deterministic and unit-testable
without one.
"""

from __future__ import annotations

import re

_PROHIBITED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blegal action\b", re.I), "false consequence: legal threat"),
    (re.compile(r"\b(court|lawsuit|sue|sued)\b", re.I), "false consequence: legal threat"),
    (re.compile(r"\barrest(ed)?\b", re.I), "false consequence: legal threat"),
    (
        re.compile(r"\b(cibil|credit score|credit report)\b", re.I),
        "false consequence: credit threat",
    ),
    (re.compile(r"\b(blacklist|blocklist)ed?\b", re.I), "false consequence: blacklisting threat"),
    (re.compile(r"\blast (chance|warning)\b", re.I), "manufactured urgency"),
    (re.compile(r"\bfinal (notice|warning)\b", re.I), "manufactured urgency"),
    (re.compile(r"\b(act|pay|respond) (now|immediately|today) or\b", re.I), "pressure tactic"),
    (re.compile(r"\burgent(ly)?\b", re.I), "manufactured urgency"),
    (re.compile(r"\b(shame|shameful|ashamed|embarrass(ed|ing)?)\b", re.I), "shaming"),
    (
        re.compile(r"\b(your (family|employer|neighbou?rs?|manager|boss))\b", re.I),
        "third-party disclosure",
    ),
)


def check_message_safety(body: str) -> list[str]:
    """Returns the list of violated reasons; empty means the message is clean."""
    return [reason for pattern, reason in _PROHIBITED_PATTERNS if pattern.search(body)]
