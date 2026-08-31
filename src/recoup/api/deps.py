"""FastAPI dependency wiring: one engine, sessions and an EventStore per request."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine


@lru_cache
def get_engine() -> AsyncEngine:
    return create_engine()


def get_event_store() -> EventStore:
    return EventStore(get_engine())


async def get_session() -> AsyncIterator[AsyncSession]:
    sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
