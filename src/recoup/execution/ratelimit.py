"""SEC-DATA-04: recovery links are rate-limited. A fixed-window counter in
Redis — the same coordination store the idempotency guard and kill switch
already use — deliberately simple rather than a new dependency for one
public, low-traffic endpoint.
"""

from __future__ import annotations

from datetime import timedelta

from redis.asyncio import Redis

_KEY_PREFIX = "recoup:ratelimit:"


async def check_rate_limit(redis: Redis, key: str, *, limit: int, window: timedelta) -> bool:
    """Returns True if the request is allowed, False if `key` has already
    hit `limit` requests within the current window."""
    redis_key = f"{_KEY_PREFIX}{key}"
    count = int(await redis.incr(redis_key))
    if count == 1:
        await redis.expire(redis_key, int(window.total_seconds()))
    return count <= limit
