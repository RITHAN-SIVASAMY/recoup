"""Idempotency for staged actions: the deterministic key plus a Redis SETNX guard.

The key formula itself lives in `domain/idempotency.py` — `policy/` needs it too
and may only import `domain`. The event store has its own idempotency mechanism
(a unique DB index on `case_events.idempotency_key`, see `audit/event_store.py`)
for deduplicating event appends; this module is the corresponding primitive for
actions (retry, message, call) once the execution layer lands in Phase 05/06 —
the Redis guard is the fast path, and a DB unique index is always the backstop.
"""

from __future__ import annotations

from redis.asyncio import Redis

from recoup.domain.idempotency import idempotency_key

__all__ = ["RedisIdempotencyGuard", "idempotency_key"]


class RedisIdempotencyGuard:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def try_acquire(self, key: str, ttl_seconds: int = 86_400) -> bool:
        acquired = await self._redis.set(key, "1", nx=True, ex=ttl_seconds)
        return bool(acquired)
