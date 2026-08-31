"""arq worker configuration — task functions land in later phases."""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from recoup.settings import get_settings
from recoup.workers.tasks import poll_mandate_status_task

_settings = get_settings()


async def _poll_mandate_status(ctx: dict[Any, Any], *args: Any, **kwargs: Any) -> int:
    # A thin same-module wrapper: importing the task directly into `cron()` trips a
    # mypy quirk matching cross-module functions against arq's WorkerCoroutine Protocol.
    return await poll_mandate_status_task(ctx, *args, **kwargs)


class WorkerSettings:
    functions: ClassVar[list[object]] = []
    cron_jobs: ClassVar[list[object]] = [
        cron(_poll_mandate_status, minute=set(range(0, 60, 15)))  # every 15 minutes
    ]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
