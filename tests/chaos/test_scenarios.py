"""FR-16.1/16.2: the ten chaos scenarios, each proving zero duplicate
customer contact, zero duplicate charge attempts, zero lost cases, and a
truthful exception-queue entry -- not merely "it didn't crash". The
implementations live in `recoup.chaos.scenarios` so the exact same code a
future dashboard "Break it" control (FR-16.7) calls live is what this suite
asserts on; nothing here reimplements the injection logic.

Scenarios 1 (duplicate webhook), 3 (malformed payload) and 9 (clock skew)
are proven by `tests/chaos/test_ingestion_chaos.py` at the HTTP/DLQ boundary
those scenarios actually need; `run_duplicate_webhook` here re-proves the
same property at the ingest() layer as a second, independent witness rather
than a duplicate of that test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from recoup.audit.event_store import create_engine
from recoup.chaos.scenarios import (
    run_duplicate_webhook,
    run_llm_invalid_schema,
    run_llm_timeout,
    run_out_of_order_events,
    run_poisoned_model_output,
    run_provider_5xx,
    run_provider_timeout,
    run_worker_crash_mid_action,
)
from recoup.settings import get_settings

pytestmark = pytest.mark.chaos


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url)
    yield client
    await client.aclose()


async def test_duplicate_webhook(engine: AsyncEngine) -> None:
    result = await run_duplicate_webhook(engine)
    assert result.passed, result.outcomes


async def test_out_of_order_events(engine: AsyncEngine, redis: Redis) -> None:
    result = await run_out_of_order_events(engine, redis)
    assert result.passed, result.outcomes


async def test_provider_5xx(engine: AsyncEngine, redis: Redis) -> None:
    result = await run_provider_5xx(engine, redis)
    assert result.passed, result.outcomes


async def test_provider_timeout(engine: AsyncEngine, redis: Redis) -> None:
    result = await run_provider_timeout(engine, redis)
    assert result.passed, result.outcomes


async def test_worker_crash_mid_action(engine: AsyncEngine, redis: Redis) -> None:
    result = await run_worker_crash_mid_action(engine, redis)
    assert result.passed, result.outcomes


async def test_llm_timeout(engine: AsyncEngine) -> None:
    result = await run_llm_timeout(engine)
    assert result.passed, result.outcomes


async def test_llm_invalid_schema(engine: AsyncEngine) -> None:
    result = await run_llm_invalid_schema(engine)
    assert result.passed, result.outcomes


async def test_poisoned_model_output(engine: AsyncEngine) -> None:
    result = await run_poisoned_model_output(engine)
    assert result.passed, result.outcomes
