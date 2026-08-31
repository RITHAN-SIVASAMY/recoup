"""arq worker configuration — task functions land in later phases."""

from __future__ import annotations

from typing import ClassVar

from arq.connections import RedisSettings

from recoup.settings import get_settings

_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[object]] = []
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
