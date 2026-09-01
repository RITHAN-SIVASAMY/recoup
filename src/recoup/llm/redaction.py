"""SEC-DATA-02 / guardrail #9: no raw phone number, email, or name reaches an
outbound LLM prompt. Pure regex scrubbing — no I/O, callable with no event
loop, and applied before every prompt is built (see `llm/client.py`).

Recoup's own domain model has no free-text phone/email/name field on `Case`
(only an opaque `customer_ref`), so this is a defense-in-depth safety net
against any accidental leakage upstream, not an unredaction of known fields.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?91[-\s]?)?\b[6-9]\d{9}\b")
_HONORIFIC_NAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?"
)


def redact_text(text: str) -> str:
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    redacted = _HONORIFIC_NAME_RE.sub("[REDACTED_NAME]", redacted)
    return redacted
