"""FR-9.6/ADR-0006: the default `ChannelPort`. Seeded and deterministic — the
same `idempotency_key` always produces the same delivery outcome, so the
whole system is demonstrable and testable without spending a rupee or
messaging a real person. Response rates are per-channel, per-uplift-segment
(a `persuadable` case is more likely to engage than a `sleeping_dog` one),
which is what makes Phase 10's measurement experiments meaningful at all —
a simulator with flat, segment-blind response rates would produce zero
signal for uplift to detect.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import UTC, datetime

from recoup.domain.models import Channel
from recoup.execution.ports import DeliveryReceipt, RenderedMessage, SendContext

# engagement (open+click) rate by channel and uplift segment; `None` covers a
# case that hasn't been segmented (e.g. degraded mode, understanding skipped).
_ENGAGEMENT_RATES: dict[Channel, dict[str | None, float]] = {
    "sms": {
        "persuadable": 0.35,
        "sure_thing": 0.55,
        "lost_cause": 0.05,
        "sleeping_dog": 0.10,
        None: 0.20,
    },
    "whatsapp": {
        "persuadable": 0.45,
        "sure_thing": 0.60,
        "lost_cause": 0.08,
        "sleeping_dog": 0.12,
        None: 0.25,
    },
    "email": {
        "persuadable": 0.15,
        "sure_thing": 0.30,
        "lost_cause": 0.02,
        "sleeping_dog": 0.05,
        None: 0.10,
    },
    "voice": {
        "persuadable": 0.50,
        "sure_thing": 0.65,
        "lost_cause": 0.10,
        "sleeping_dog": 0.15,
        None: 0.30,
    },
}
_BOUNCE_RATE = 0.02
_FAILURE_RATE = 0.01
_LATENCY_MS_RANGE = (50, 400)

# P(customer completes payment | they engaged). `sure_thing` converts almost
# regardless of the nudge; `persuadable` is where the nudge causally matters;
# `lost_cause`/`sleeping_dog` rarely convert even having opened the message.
_CONVERSION_GIVEN_ENGAGED: dict[str | None, float] = {
    "persuadable": 0.6,
    "sure_thing": 0.9,
    "lost_cause": 0.1,
    "sleeping_dog": 0.2,
    None: 0.4,
}


def _seeded_rng(idempotency_key: str) -> random.Random:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


class SimulatorChannelPort:
    """`simulate_delay` is off by default so tests run instantly; the live
    demo can turn it on for a visually realistic SSE stream."""

    def __init__(self, *, simulate_delay: bool = False) -> None:
        self._simulate_delay = simulate_delay

    async def send(
        self, message: RenderedMessage, idempotency_key: str, context: SendContext
    ) -> DeliveryReceipt:
        rng = _seeded_rng(idempotency_key)
        latency_ms = rng.randint(*_LATENCY_MS_RANGE)
        if self._simulate_delay:
            await asyncio.sleep(latency_ms / 1000)

        roll = rng.random()
        if roll < _FAILURE_RATE:
            return DeliveryReceipt(
                status="failed",
                sent_at=datetime.now(UTC),
                latency_ms=latency_ms,
                provider_ref=f"sim-{idempotency_key[:12]}",
            )
        if roll < _FAILURE_RATE + _BOUNCE_RATE:
            return DeliveryReceipt(
                status="bounced",
                sent_at=datetime.now(UTC),
                latency_ms=latency_ms,
                provider_ref=f"sim-{idempotency_key[:12]}",
            )

        engagement_rate = _ENGAGEMENT_RATES[message.channel].get(context.uplift_segment, 0.15)
        engaged = rng.random() < engagement_rate
        converted = engaged and rng.random() < _CONVERSION_GIVEN_ENGAGED.get(
            context.uplift_segment, 0.4
        )
        return DeliveryReceipt(
            status="delivered",
            engaged=engaged,
            converted=converted,
            sent_at=datetime.now(UTC),
            latency_ms=latency_ms,
            provider_ref=f"sim-{idempotency_key[:12]}",
        )
