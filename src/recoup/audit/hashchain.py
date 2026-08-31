"""Pure hash-chain math: hash = sha256(prev_hash || canonical(payload) || seq || occurred_at)."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from recoup.domain.canonical import canonical_json

GENESIS_HASH = hashlib.sha256(b"recoup-genesis").hexdigest()


def compute_hash(prev_hash: str, payload: dict[str, Any], seq: int, occurred_at: datetime) -> str:
    material = (
        prev_hash.encode("utf-8")
        + canonical_json(payload)
        + str(seq).encode("utf-8")
        + occurred_at.isoformat().encode("utf-8")
    )
    return hashlib.sha256(material).hexdigest()
