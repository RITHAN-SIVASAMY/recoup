"""ULID identifiers — sortable by creation time. Stored and validated as strings."""

from __future__ import annotations

import hashlib
from typing import Annotated

from pydantic import StringConstraints
from ulid import ULID as _ULID

# Crockford base32, first char 0-7 (keeps the 48-bit timestamp from overflowing 128 bits).
_ULID_PATTERN = r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"

Ulid = Annotated[str, StringConstraints(pattern=_ULID_PATTERN, min_length=26, max_length=26)]


def new_ulid() -> str:
    return str(_ULID())


def deterministic_ulid(key: str) -> str:
    """A ULID-shaped ID derived only from `key` -- no wall-clock time, no OS
    entropy. For seeded synthetic-data paths (the demo batch) only: real
    ingestion must keep using `new_ulid()`, since a predictable case ID would
    be a real-world footgun. `& 0x3F` on the first byte keeps the value within
    the same first-char-0-7 constraint `new_ulid()`'s output satisfies."""
    digest = hashlib.sha256(key.encode()).digest()[:16]
    masked = bytes([digest[0] & 0x3F]) + digest[1:]
    return str(_ULID.from_bytes(masked))
