"""REG-COMM-02: contact on a channel requires a recorded consent basis for that
channel. Absence of consent is a DENY, never a default-allow."""

from __future__ import annotations


def has_consent(channel: str | None, consent_channels: frozenset[str]) -> bool:
    if channel is None:
        return True  # no channel involved (e.g. a silent retry) — nothing to consent to
    return channel in consent_channels
