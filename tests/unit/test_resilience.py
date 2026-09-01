"""Guardrail #6: explicit timeout, bounded retry with jitter, circuit breaker."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from recoup.execution.resilience import CircuitBreaker, CircuitOpenError, retry_with_jitter

pytestmark = pytest.mark.unit


async def test_retry_with_jitter_returns_on_first_success() -> None:
    calls = 0

    async def _ok() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await retry_with_jitter(_ok, max_attempts=3, base_delay_s=0.001)
    assert result == "ok"
    assert calls == 1


async def test_retry_with_jitter_retries_then_succeeds() -> None:
    calls = 0

    async def _flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("transient")
        return "ok"

    result = await retry_with_jitter(
        _flaky, max_attempts=3, base_delay_s=0.001, rng=random.Random(0)
    )
    assert result == "ok"
    assert calls == 2


async def test_retry_with_jitter_raises_the_last_error_after_exhausting_attempts() -> None:
    async def _always_fails() -> str:
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError, match="permanent"):
        await retry_with_jitter(_always_fails, max_attempts=2, base_delay_s=0.001)


async def test_circuit_breaker_opens_after_the_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_after=timedelta(seconds=30))
    now = datetime(2026, 1, 1, tzinfo=UTC)

    async def _fails() -> None:
        raise RuntimeError("down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(_fails, now=now)

    with pytest.raises(CircuitOpenError):
        await breaker.call(_fails, now=now)


async def test_circuit_breaker_half_opens_after_reset_after_elapses() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_after=timedelta(seconds=30))
    now = datetime(2026, 1, 1, tzinfo=UTC)

    async def _fails() -> None:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await breaker.call(_fails, now=now)
    with pytest.raises(CircuitOpenError):
        await breaker.call(_fails, now=now)

    later = now + timedelta(seconds=31)

    async def _ok() -> str:
        return "ok"

    result = await breaker.call(_ok, now=later)
    assert result == "ok"


async def test_circuit_breaker_resets_the_failure_count_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_after=timedelta(seconds=30))
    now = datetime(2026, 1, 1, tzinfo=UTC)

    async def _fails() -> None:
        raise RuntimeError("down")

    async def _ok() -> str:
        return "ok"

    with pytest.raises(RuntimeError):
        await breaker.call(_fails, now=now)
    await breaker.call(_ok, now=now)

    with pytest.raises(RuntimeError):
        await breaker.call(_fails, now=now)
    # only one consecutive failure after the reset — breaker should still be closed
    result = await breaker.call(_ok, now=now)
    assert result == "ok"
