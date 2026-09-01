"""FR-7.2 against a real event store + `staged_actions` table: `stage()` writes
`action.staged` and is durably lookup-able; `cancel_and_log()` writes
`action.cancelled` and refuses to double-cancel.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, Case, ProposedAction, Verdict
from recoup.execution.staging import StagingStore, cancel_and_log, stage
from recoup.policy.schema import MerchantStaging

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


async def _seeded_case(store: EventStore) -> Case:
    case_id = new_ulid()
    await store.append(
        case_id=case_id, event_type="case.created", payload=case_created_payload(), actor=SYSTEM
    )
    return Case(
        case_id=case_id,
        merchant_id="demo-merchant",
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


def _action(action_type: str = "send_message") -> ProposedAction:
    return ProposedAction(
        action_type=action_type,  # type: ignore[arg-type]
        channel="sms" if action_type != "retry_charge" else None,
        ladder_step=1,
        scheduled_for=_NOW,
        estimated_cost_inr=Decimal("0.20"),
        expected_value_inr=Decimal("10.00"),
    )


def _allow_verdict(policy_version: str = "v1") -> Verdict:
    return Verdict(
        decision="ALLOW", rule_id="RULE-ALLOW-DEFAULT", policy_version=policy_version, reason="ok"
    )


async def test_stage_writes_action_staged_and_is_durably_retrievable(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)

    staged = await stage(store, case, _action(), _allow_verdict(), _STAGING, _NOW)
    await staging_store.save(staged)

    events = await store.events_for(case.case_id)
    assert [e.event_type for e in events] == ["case.created", "action.staged"]
    assert events[-1].payload["staged_action_id"] == staged.staged_action_id

    fetched = await staging_store.get(staged.staged_action_id)
    assert fetched is not None
    assert fetched.status == "staged"
    assert fetched.promote_at == _NOW + timedelta(seconds=60)


async def test_stage_uses_the_5_minute_window_for_a_money_moving_action(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)

    staged = await stage(store, case, _action("retry_charge"), _allow_verdict(), _STAGING, _NOW)

    assert staged.promote_at == _NOW + timedelta(minutes=5)


async def test_stage_refuses_a_non_allow_verdict(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    deny = Verdict(
        decision="DENY", rule_id="REG-COMM-01", policy_version="v1", reason="quiet hours"
    )

    with pytest.raises(ValueError, match="only an ALLOW verdict"):
        await stage(store, case, _action(), deny, _STAGING, _NOW)


async def test_cancel_and_log_writes_action_cancelled_and_updates_the_store(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)
    staged = await stage(store, case, _action(), _allow_verdict(), _STAGING, _NOW)
    await staging_store.save(staged)

    cancelled = await cancel_and_log(
        store, staged, actor=HUMAN, reason="manual_cancel", now=_NOW + timedelta(seconds=5)
    )
    await staging_store.save(cancelled)

    events = await store.events_for(case.case_id)
    assert events[-1].event_type == "action.cancelled"
    assert events[-1].actor == HUMAN

    fetched = await staging_store.get(staged.staged_action_id)
    assert fetched is not None
    assert fetched.status == "cancelled"


async def test_cancelling_an_already_cancelled_action_raises(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    staged = await stage(store, case, _action(), _allow_verdict(), _STAGING, _NOW)
    cancelled = await cancel_and_log(store, staged, actor=HUMAN, reason="manual_cancel", now=_NOW)

    with pytest.raises(ValueError, match="cannot cancel"):
        await cancel_and_log(store, cancelled, actor=HUMAN, reason="manual_cancel", now=_NOW)


async def test_list_in_flight_only_returns_staged_actions_for_the_merchant(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)
    staged = await stage(store, case, _action(), _allow_verdict(), _STAGING, _NOW)
    await staging_store.save(staged)
    cancelled = await cancel_and_log(store, staged, actor=HUMAN, reason="manual_cancel", now=_NOW)
    await staging_store.save(cancelled)

    other_case = await _seeded_case(store)
    other_staged = await stage(store, other_case, _action(), _allow_verdict(), _STAGING, _NOW)
    await staging_store.save(other_staged)

    in_flight = await staging_store.list_in_flight("demo-merchant")
    in_flight_ids = {a.staged_action_id for a in in_flight}
    assert other_staged.staged_action_id in in_flight_ids
    assert staged.staged_action_id not in in_flight_ids  # already cancelled
