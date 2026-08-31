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


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_normalize(val) for val in value]
    return value


def canonical_json(value: Any) -> bytes:
    normalized = _normalize(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
