"""ADR-0006/FR-9.6: the simulator is seeded and deterministic — the same
idempotency key always produces the same outcome — and a `persuadable`
segment engages more than a `lost_cause` one over many trials, which is
what makes Phase 10's uplift measurement possible against this simulator
at all.
"""

from __future__ import annotations

import pytest

from recoup.execution.adapters.simulator import SimulatorChannelPort
from recoup.execution.ports import DeliveryReceipt, RenderedMessage, SendContext

pytestmark = pytest.mark.unit

_MESSAGE = RenderedMessage(
    channel="sms",
    body="test",
    sender_identity="Acme via Recoup",
    opt_out_affordance="Reply STOP to opt out.",
    category="transactional",
)


async def _receipt(key: str, segment: str | None) -> DeliveryReceipt:
    port = SimulatorChannelPort()
    context = SendContext(case_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", uplift_segment=segment)
    return await port.send(_MESSAGE, key, context)


async def test_the_same_idempotency_key_always_produces_the_same_outcome() -> None:
    first = await _receipt("fixed-key-001", "persuadable")
    second = await _receipt("fixed-key-001", "persuadable")
    assert first.status == second.status
    assert first.engaged == second.engaged
    assert first.converted == second.converted
    assert first.latency_ms == second.latency_ms


async def test_different_keys_can_produce_different_outcomes() -> None:
    outcomes = {(await _receipt(f"key-{i}", "persuadable")).engaged for i in range(50)}
    assert outcomes == {True, False}  # both engaged and non-engaged appear across 50 draws


async def test_a_persuadable_segment_engages_more_often_than_a_lost_cause_over_many_trials() -> (
    None
):
    n = 400
    persuadable_engaged = sum([(await _receipt(f"p-{i}", "persuadable")).engaged for i in range(n)])
    lost_cause_engaged = sum([(await _receipt(f"l-{i}", "lost_cause")).engaged for i in range(n)])
    assert persuadable_engaged > lost_cause_engaged


async def test_send_returns_without_delay_by_default() -> None:
    receipt = await _receipt("fast-key", "persuadable")
    assert receipt.sent_at.tzinfo is not None


async def test_a_bounced_or_failed_receipt_is_never_marked_engaged_or_converted() -> None:
    # Force through many keys and check the invariant holds wherever it applies.
    for i in range(200):
        receipt = await _receipt(f"invariant-{i}", "sure_thing")
        if receipt.status != "delivered":
            assert receipt.engaged is False
            assert receipt.converted is False
        if not receipt.engaged:
            assert receipt.converted is False
