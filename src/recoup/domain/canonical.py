"""Canonical JSON: sorted keys, no whitespace, UTF-8, Decimal as string.

One implementation, used by both the hash chain and any future dedupe key —
never reimplement this elsewhere.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


def normalize(value: Any) -> Any:
    """Recursively convert to JSON-native primitives (Decimal/datetime/BaseModel included).

    Callers that build event payloads containing Decimal or datetime values should run
    them through this before persisting — it's what keeps a payload's in-memory
    representation identical to what comes back after a JSONB round trip.
    """
    if isinstance(value, BaseModel):
        return normalize(value.model_dump(mode="json"))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): normalize(val) for key, val in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [normalize(val) for val in value]
    return value


def canonical_json(value: Any) -> bytes:
    normalized = normalize(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
