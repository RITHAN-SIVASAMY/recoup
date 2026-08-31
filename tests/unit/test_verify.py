"""Tamper detection is a pure algorithm — tested with in-memory fixtures.

`case_events` is trigger-protected against UPDATE/DELETE (see the Phase 01 migration),
so an integration test cannot construct a tampered row in the real database without
permanently poisoning every future `make verify` run. Testing `verify_events` directly
against constructed fixtures gets the same coverage with none of that risk.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from recoup.audit.hashchain import GENESIS_HASH, compute_hash
from recoup.audit.verify import ChainEvent, verify_events
from recoup.domain.ids import new_ulid

pytestmark = pytest.mark.unit

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _chain(case_id: str, n: int) -> list[ChainEvent]:
    events: list[ChainEvent] = []
    prev_hash = GENESIS_HASH
    for seq in range(1, n + 1):
        payload = {"seq": seq}
        event_hash = compute_hash(prev_hash, payload, seq, _WHEN)
        events.append(
            ChainEvent(
                event_id=new_ulid(),
                case_id=case_id,
                seq=seq,
                occurred_at=_WHEN,
                payload=payload,
                prev_hash=prev_hash,
                hash=event_hash,
            )
        )
        prev_hash = event_hash
    return events


def test_verify_events_passes_an_untampered_chain() -> None:
    events = _chain(new_ulid(), 5)

    result = verify_events(events)

    assert result.verified is True
    assert result.events_checked == 5
    assert result.divergent_event_id is None


def test_verify_events_names_the_event_whose_payload_was_mutated() -> None:
    events = _chain(new_ulid(), 4)
    tampered = events.copy()
    # Simulate an attacker (or a bug) mutating one payload in place, after its hash
    # was computed — the stored hash no longer matches a recomputation.
    tampered[2] = ChainEvent(
        event_id=tampered[2].event_id,
        case_id=tampered[2].case_id,
        seq=tampered[2].seq,
        occurred_at=tampered[2].occurred_at,
        payload={"seq": 999},
        prev_hash=tampered[2].prev_hash,
        hash=tampered[2].hash,
    )

    result = verify_events(tampered)

    assert result.verified is False
    assert result.divergent_event_id == events[2].event_id
    assert result.reason is not None
    assert "hash" in result.reason
    # Everything before the tampered event was already confirmed intact.
    assert result.events_checked == 2


def test_verify_events_detects_a_deleted_case_via_the_broken_prev_hash_link() -> None:
    case_a = _chain(new_ulid(), 3)
    case_b = _chain(new_ulid(), 2)
    # Delete the middle event of case_a: seq 3 now claims prev_hash = seq-1's hash,
    # but the chain walker only ever sees the running tip, so removing seq 2 breaks
    # seq 3's prev_hash link against the last hash it actually observed (seq 1's).
    with_a_gap = [case_a[0], case_a[2], *case_b]

    result = verify_events(with_a_gap)

    assert result.verified is False
    assert result.divergent_event_id == case_a[2].event_id
    assert result.reason is not None
    assert "prev_hash" in result.reason
