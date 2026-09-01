"""Guardrail #6/`context/shared/03-guardrails.md`'s failure-handling contract:
every external call gets an explicit timeout, bounded retry with jitter, and
a per-provider circuit breaker — applied around every `ChannelPort.send()`
call in `execution/dispatcher.py`. Never mutates case state before the call
succeeds: retries happen entirely before any event is written.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


class CircuitOpenError(Exception):
    """Raised instead of attempting a call while a provider's breaker is open."""


@dataclass
class CircuitBreaker:
    """Closed -> Open after `failure_threshold` consecutive failures ->
    Half-open after `reset_after` elapses, allowing one trial call."""

    failure_threshold: int = 5
    reset_after: timedelta = field(default_factory=lambda: timedelta(seconds=30))
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: datetime | None = field(default=None, init=False)

    def _is_open(self, now: datetime) -> bool:
        if self._opened_at is None:
            return False
        return (
            now - self._opened_at < self.reset_after
        )  # past reset_after: half-open, allow a trial call

    async def call[T](self, fn: Callable[[], Awaitable[T]], *, now: datetime | None = None) -> T:
        now = now or datetime.now(UTC)
        if self._is_open(now):
            raise CircuitOpenError("circuit is open; provider recently failed repeatedly")
        try:
            result = await fn()
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._opened_at = now
            raise
        else:
            self._consecutive_failures = 0
            self._opened_at = None
            return result


async def retry_with_jitter[T](
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay_s: float = 0.1,
    timeout_s: float = 8.0,
    rng: random.Random | None = None,
) -> T:
    rng = rng or random.Random()
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await asyncio.wait_for(fn(), timeout=timeout_s)
        except Exception as exc:  # retry loop must catch broadly, per the failure-handling contract
            last_error = exc
            if attempt < max_attempts - 1:
                delay = base_delay_s * (2**attempt) * (1 + rng.random())
                await asyncio.sleep(delay)
    assert last_error is not None  # the loop always raises or returns
    raise last_error
