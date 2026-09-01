"""FastAPI dependency wiring: one engine, sessions and an EventStore per request."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import cast

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine
from recoup.execution.approvals import ApprovalStore
from recoup.execution.staging import StagingStore
from recoup.policy.loader import PolicyLoader
from recoup.policy.schema import PolicyBundle
from recoup.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_engine()


def get_event_store() -> EventStore:
    return EventStore(get_engine())


def get_staging_store() -> StagingStore:
    return StagingStore(get_engine())


def get_approval_store() -> ApprovalStore:
    return ApprovalStore(get_engine())


@lru_cache
def get_redis() -> Redis:
    return cast(Redis, Redis.from_url(get_settings().redis_url))


def get_policy(merchant_id: str | None = None) -> PolicyBundle:
    settings = get_settings()
    return PolicyLoader(
        Path(settings.policy_dir), merchant_id=merchant_id or settings.merchant_id
    ).load()


async def get_session() -> AsyncIterator[AsyncSession]:
    sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
