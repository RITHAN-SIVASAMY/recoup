"""ULID identifiers — sortable by creation time. Stored and validated as strings."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints
from ulid import ULID as _ULID

# Crockford base32, first char 0-7 (keeps the 48-bit timestamp from overflowing 128 bits).
_ULID_PATTERN = r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"

Ulid = Annotated[str, StringConstraints(pattern=_ULID_PATTERN, min_length=26, max_length=26)]


def new_ulid() -> str:
    return str(_ULID())
