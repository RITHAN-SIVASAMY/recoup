"""FR-11.3/11.4 against a real Postgres: promise-keeping follow-through
updates a durable, per-customer trust score that outlives any one case.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.understanding.relationship import NEUTRAL_TRUST_SCORE
from recoup.understanding.trust import TrustScoreStore, record_ptp_outcome

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seeded_case(store: EventStore, customer_ref: str) -> str:
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(customer_ref=customer_ref),
        actor=SYSTEM,
    )
    return case_id


async def test_a_new_customer_starts_at_the_neutral_trust_score(engine: AsyncEngine) -> None:
    store = TrustScoreStore(engine)
    customer_ref = f"cust-{new_ulid()}"
    assert await store.score_for(customer_ref) == NEUTRAL_TRUST_SCORE


async def test_a_kept_promise_raises_the_trust_score(engine: AsyncEngine) -> None:
    event_store = EventStore(engine)
    trust_store = TrustScoreStore(engine)
    customer_ref = f"cust-{new_ulid()}"
    case_id = await _seeded_case(event_store, customer_ref)

    new_score = await record_ptp_outcome(
        event_store,
        trust_store,
        case_id=case_id,
        customer_ref=customer_ref,
        outcome="kept",
        now=_NOW,
    )

    assert new_score > NEUTRAL_TRUST_SCORE
    assert await trust_store.score_for(customer_ref) == new_score
    events = await event_store.events_for(case_id)
    assert events[-1].event_type == "ptp.kept"


async def test_a_broken_promise_lowers_the_trust_score(engine: AsyncEngine) -> None:
    event_store = EventStore(engine)
    trust_store = TrustScoreStore(engine)
    customer_ref = f"cust-{new_ulid()}"
    case_id = await _seeded_case(event_store, customer_ref)

    new_score = await record_ptp_outcome(
        event_store,
        trust_store,
        case_id=case_id,
        customer_ref=customer_ref,
        outcome="broken",
        now=_NOW,
    )

    assert new_score < NEUTRAL_TRUST_SCORE
    events = await event_store.events_for(case_id)
    assert events[-1].event_type == "ptp.broken"


async def test_the_trust_score_persists_and_accumulates_across_multiple_cases(
    engine: AsyncEngine,
) -> None:
    event_store = EventStore(engine)
    trust_store = TrustScoreStore(engine)
    customer_ref = f"cust-{new_ulid()}"

    first_case = await _seeded_case(event_store, customer_ref)
    after_first = await record_ptp_outcome(
        event_store,
        trust_store,
        case_id=first_case,
        customer_ref=customer_ref,
        outcome="kept",
        now=_NOW,
    )

    second_case = await _seeded_case(event_store, customer_ref)
    after_second = await record_ptp_outcome(
        event_store,
        trust_store,
        case_id=second_case,
        customer_ref=customer_ref,
        outcome="kept",
        now=_NOW,
    )

    assert after_second > after_first  # a second kept promise, same customer, compounds
    assert await trust_store.score_for(customer_ref) == after_second


async def test_the_trust_score_never_exceeds_1_or_drops_below_0(engine: AsyncEngine) -> None:
    event_store = EventStore(engine)
    trust_store = TrustScoreStore(engine)
    customer_ref = f"cust-{new_ulid()}"

    for _ in range(20):
        case_id = await _seeded_case(event_store, customer_ref)
        score = await record_ptp_outcome(
            event_store,
            trust_store,
            case_id=case_id,
            customer_ref=customer_ref,
            outcome="kept",
            now=_NOW,
        )
        assert 0.0 <= score <= 1.0
