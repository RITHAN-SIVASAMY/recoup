"""Integration: the compose-provided Postgres and Redis are reachable."""

from __future__ import annotations

import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine

from recoup.settings import get_settings

pytestmark = pytest.mark.integration


async def test_postgres_is_reachable() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql("SELECT 1")
            assert result.scalar() == 1
    finally:
        await engine.dispose()


async def test_redis_is_reachable() -> None:
    settings = get_settings()
    client = redis.from_url(settings.redis_url)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()
