"""arq task wrappers — thin adapters between the arq context and the ingestion functions."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine
from recoup.ingestion.mandate_poller import NullMandateStatusSource, poll_mandate_status
from recoup.settings import get_settings


async def poll_mandate_status_task(_ctx: dict[Any, Any], *_args: Any, **_kwargs: Any) -> int:
    """Cron entry point: reconciliation poll for mandate/subscription status changes."""
    settings = get_settings()
    engine = create_engine(settings)
    try:
        event_store = EventStore(engine)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            results = await poll_mandate_status(
                session,
                event_store,
                NullMandateStatusSource(),
                default_merchant_id=settings.merchant_id,
            )
        return len(results)
    finally:
        await engine.dispose()
