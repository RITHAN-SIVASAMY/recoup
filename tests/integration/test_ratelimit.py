"""SEC-DATA-04: recovery links are rate-limited, against real Redis."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from redis.asyncio import Redis

from recoup.domain.ids import new_ulid
from recoup.execution.ratelimit import check_rate_limit
from recoup.settings import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url)
    yield client
    await client.aclose()


async def test_requests_within_the_limit_are_allowed(redis: Redis) -> None:
    key = f"ratelimit-test-{new_ulid()}"
    for _ in range(3):
        assert await check_rate_limit(redis, key, limit=3, window=timedelta(seconds=30)) is True


async def test_a_request_past_the_limit_is_refused(redis: Redis) -> None:
    key = f"ratelimit-test-{new_ulid()}"
    for _ in range(3):
        await check_rate_limit(redis, key, limit=3, window=timedelta(seconds=30))
    assert await check_rate_limit(redis, key, limit=3, window=timedelta(seconds=30)) is False


async def test_different_keys_have_independent_budgets(redis: Redis) -> None:
    key_a = f"ratelimit-test-{new_ulid()}"
    key_b = f"ratelimit-test-{new_ulid()}"
    for _ in range(3):
        await check_rate_limit(redis, key_a, limit=3, window=timedelta(seconds=30))
    assert await check_rate_limit(redis, key_b, limit=3, window=timedelta(seconds=30)) is True
