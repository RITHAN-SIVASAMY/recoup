"""The deterministic idempotency-key formula: sha256(case_id || action_type ||
ladder_step || policy_version) — FR-7.6.

Pure and dependency-free (beyond `domain.canonical`), which is exactly why it
lives here rather than in `execution/`: the policy engine needs to compute this
same key to enforce "one idempotency key -> at most one executed action" as a
policy-level invariant (defense in depth alongside the DB-level guarantee in
`audit/event_store.py`), and `policy` may only import `domain`
(see the import-linter contract in pyproject.toml). `execution/idempotency.py`
re-exports this for the Redis-backed guard, which does need I/O and belongs there.
"""

from __future__ import annotations

import hashlib

from recoup.domain.canonical import canonical_json


def idempotency_key(case_id: str, action_type: str, ladder_step: int, policy_version: str) -> str:
    material = canonical_json(
        {
            "case_id": case_id,
            "action_type": action_type,
            "ladder_step": ladder_step,
            "policy_version": policy_version,
        }
    )
    return hashlib.sha256(material).hexdigest()
