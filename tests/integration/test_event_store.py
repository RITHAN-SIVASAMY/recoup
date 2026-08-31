"""EventStore against a real Postgres: idempotency, concurrency, replay equality,
and the DB-level append-only guarantee.

Every case_id here is freshly generated per test, so committed rows are harmless,
valid, permanent additions to the dev database rather than throwaway fixtures —
consistent with case_events being genuinely append-only.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from itertools import pairwise

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.verify import verify_chain, verify_replay_equality
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.execution.idempotency import idempotency_key

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def test_append_and_events_for_round_trip(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = new_ulid()

    created = await store.append(
        case_id=case_id,
        event_type="case.created",
        payload={"source_type": "payment_failure"},
        actor=SYSTEM,
    )
    second = await store.append(
        case_id=case_id,
        event_type="case.exception",
        payload={"reason": "test"},
        actor=SYSTEM,
    )

    events = await store.events_for(case_id)

    assert [e.event_id for e in events] == [created.event_id, second.event_id]
    assert second.prev_hash == created.hash
    assert second.seq == 2


async def test_duplicate_idempotency_key_produces_exactly_one_effect(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload={"source_type": "payment_failure"},
        actor=SYSTEM,
    )
    key = idempotency_key(case_id, "retry_charge", 1, "policy-v1")

    first = await store.append(
        case_id=case_id,
        event_type="action.staged",
        payload={"ladder_step": 1},
        actor=SYSTEM,
        idempotency_key=key,
    )
    second = await store.append(
        case_id=case_id,
        event_type="action.staged",
        payload={"ladder_step": 1},
        actor=SYSTEM,
        idempotency_key=key,
    )

    assert first.event_id == second.event_id
    events = await store.events_for(case_id)
    assert len(events) == 2  # case.created + exactly one action.staged, not two


async def test_concurrent_appends_to_one_case_produce_a_gapless_seq_with_no_lost_update(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)  # one shared pool, as in production
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload={"source_type": "payment_failure"},
        actor=SYSTEM,
    )

    async def _append(n: int) -> None:
        await store.append(
            case_id=case_id,
            event_type="case.exception",
            payload={"worker": n},
            actor=SYSTEM,
        )

    await asyncio.gather(*(_append(n) for n in range(8)))

    events = await store.events_for(case_id)
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, len(events) + 1))  # gapless, no duplicates, no gaps
    assert len(events) == 9  # 1 case.created + 8 concurrent appends, none lost

    # Each event's prev_hash must equal the immediately preceding event's hash.
    for prior, current in pairwise(events):
        assert current.prev_hash == prior.hash


async def test_replay_equality_holds_after_real_appends(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload={"source_type": "receivable_overdue"},
        actor=SYSTEM,
    )
    await store.append(case_id=case_id, event_type="case.exception", payload={}, actor=SYSTEM)

    assert await verify_replay_equality(engine) is True


async def test_verify_chain_passes_after_real_appends(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload={"source_type": "checkout_abandonment"},
        actor=SYSTEM,
    )

    result = await verify_chain(engine)

    assert result.verified is True


async def test_case_events_rejects_a_direct_update(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    event = await store.append(
        case_id=case_id,
        event_type="case.created",
        payload={"source_type": "payment_failure"},
        actor=SYSTEM,
    )

    with pytest.raises(DBAPIError, match="append-only"):
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE case_events SET payload = '{}' WHERE event_id = :event_id"),
                {"event_id": event.event_id},
            )
