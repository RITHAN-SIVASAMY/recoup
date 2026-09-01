"""FR-7.4 against real Redis + Postgres: engaging halts new autonomous action
and cancels every in-flight staged action, scoped to the engaging merchant only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, Case, ProposedAction, Verdict
from recoup.execution import killswitch
from recoup.execution.staging import StagingStore, stage
from recoup.policy.schema import MerchantStaging
from recoup.settings import get_settings

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
HUMAN = Actor(kind="human", identifier="ops-1")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_STAGING = MerchantStaging(
    contact_undo_window=timedelta(seconds=60), money_undo_window=timedelta(minutes=5)
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url)
    yield client
    await client.aclose()


async def _seeded_case(store: EventStore, merchant_id: str) -> Case:
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(merchant_id=merchant_id),
        actor=SYSTEM,
    )
    return Case(
        case_id=case_id,
        merchant_id=merchant_id,
        source_type="payment_failure",
        provider_event_id="prov-1",
        amount_at_risk=Decimal("499.00"),
        customer_ref="cust_test",
        resolution_state="pending",
        cohort="treatment",
        root_cause=None,
        created_at=_NOW,
        updated_at=_NOW,
        seq=1,
        tip_hash="h" * 64,
    )


def _action() -> ProposedAction:
    return ProposedAction(
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        scheduled_for=_NOW,
        estimated_cost_inr=Decimal("0.20"),
        expected_value_inr=Decimal("10.00"),
    )


def _allow() -> Verdict:
    return Verdict(decision="ALLOW", rule_id="RULE-ALLOW-DEFAULT", policy_version="v1", reason="ok")


async def test_is_engaged_is_false_by_default(redis: Redis) -> None:
    merchant_id = f"kstest-{new_ulid()}"
    assert await killswitch.is_engaged(redis, merchant_id) is False


async def test_engage_and_disengage_toggle_is_engaged(redis: Redis) -> None:
    merchant_id = f"kstest-{new_ulid()}"
    await killswitch.engage(redis, merchant_id, actor=HUMAN, now=_NOW)
    assert await killswitch.is_engaged(redis, merchant_id) is True

    await killswitch.disengage(redis, merchant_id)
    assert await killswitch.is_engaged(redis, merchant_id) is False


async def test_cancel_all_in_flight_drains_only_the_engaging_merchants_staged_actions(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    merchant_id = f"kstest-{new_ulid()}"
    other_merchant_id = f"kstest-{new_ulid()}"

    case = await _seeded_case(store, merchant_id)
    staged = await stage(store, case, _action(), _allow(), _STAGING, _NOW)
    await staging_store.save(staged)

    other_case = await _seeded_case(store, other_merchant_id)
    other_staged = await stage(store, other_case, _action(), _allow(), _STAGING, _NOW)
    await staging_store.save(other_staged)

    cancelled = await killswitch.cancel_all_in_flight(
        store, staging_store, merchant_id, actor=HUMAN, now=_NOW
    )

    assert [c.staged_action_id for c in cancelled] == [staged.staged_action_id]
    assert (await staging_store.get(staged.staged_action_id)).status == "cancelled"  # type: ignore[union-attr]
    assert (await staging_store.get(other_staged.staged_action_id)).status == "staged"  # type: ignore[union-attr]

    events = await store.events_for(case.case_id)
    assert events[-1].event_type == "action.cancelled"
    assert events[-1].payload["reason"] == "killswitch_engaged"


async def test_cancel_all_in_flight_is_idempotent_when_called_twice(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    merchant_id = f"kstest-{new_ulid()}"
    case = await _seeded_case(store, merchant_id)
    staged = await stage(store, case, _action(), _allow(), _STAGING, _NOW)
    await staging_store.save(staged)

    first = await killswitch.cancel_all_in_flight(
        store, staging_store, merchant_id, actor=HUMAN, now=_NOW
    )
    second = await killswitch.cancel_all_in_flight(
        store, staging_store, merchant_id, actor=HUMAN, now=_NOW
    )

    assert len(first) == 1
    assert len(second) == 0  # already cancelled; list_in_flight only returns status=="staged"
