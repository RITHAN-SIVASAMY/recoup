"""Idempotency for staged actions: a deterministic key plus a Redis SETNX guard.

The event store has its own idempotency mechanism (a unique DB index on
`case_events.idempotency_key`, see `audit/event_store.py`) for deduplicating
event appends. This module is the corresponding primitive for actions
(retry, message, call) once the execution layer lands in Phase 05/06 — the
Redis guard is the fast path, and a DB unique index is always the backstop.
"""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis

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


class RedisIdempotencyGuard:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def try_acquire(self, key: str, ttl_seconds: int = 86_400) -> bool:
        acquired = await self._redis.set(key, "1", nx=True, ex=ttl_seconds)
        return bool(acquired)
