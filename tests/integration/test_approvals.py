"""FR-7.1/7.5/7.7 against a real event store: a REQUIRE_APPROVAL verdict queues
for a human; granting stages the action (still cancellable), rejecting stages
nothing.
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
from recoup.execution.approvals import grant, reject, request_approval
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
        amount_at_risk=Decimal("20000.00"),
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
        expected_value_inr=Decimal("500.00"),
    )


def _require_approval_verdict() -> Verdict:
    return Verdict(
        decision="REQUIRE_APPROVAL",
        rule_id="RULE-APPROVAL-VALUE",
        policy_version="v1",
        reason="above the value threshold",
    )


async def test_request_approval_writes_approval_requested(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)

    pending = await request_approval(
        store, case, _action(), _require_approval_verdict(), uplift=Decimal("0.15"), now=_NOW
    )

    assert pending.status == "pending"
    events = await store.events_for(case.case_id)
    assert events[-1].event_type == "approval.requested"
    assert events[-1].payload["rule_id"] == "RULE-APPROVAL-VALUE"


async def test_granting_an_approval_stages_the_action(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    pending = await request_approval(
        store, case, _action(), _require_approval_verdict(), uplift=Decimal("0.15"), now=_NOW
    )

    decided, staged = await grant(store, case, pending, _STAGING, actor=HUMAN, now=_NOW)

    assert decided.status == "approved"
    assert staged.status == "staged"
    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert event_types == [
        "case.created",
        "approval.requested",
        "approval.granted",
        "action.staged",
    ]


async def test_rejecting_an_approval_stages_nothing(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    pending = await request_approval(
        store, case, _action(), _require_approval_verdict(), uplift=Decimal("0.15"), now=_NOW
    )

    decided = await reject(store, case, pending, actor=HUMAN, now=_NOW)

    assert decided.status == "rejected"
    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert event_types == ["case.created", "approval.requested", "approval.rejected"]
    assert "action.staged" not in event_types


async def test_only_a_human_actor_may_grant_or_reject(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    pending = await request_approval(
        store, case, _action(), _require_approval_verdict(), uplift=Decimal("0.15"), now=_NOW
    )

    with pytest.raises(ValueError, match="human"):
        await grant(store, case, pending, _STAGING, actor=SYSTEM, now=_NOW)
    with pytest.raises(ValueError, match="human"):
        await reject(store, case, pending, actor=SYSTEM, now=_NOW)


async def test_granting_twice_raises(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    pending = await request_approval(
        store, case, _action(), _require_approval_verdict(), uplift=Decimal("0.15"), now=_NOW
    )
    decided, _ = await grant(store, case, pending, _STAGING, actor=HUMAN, now=_NOW)

    with pytest.raises(ValueError, match="cannot grant"):
        await grant(store, case, decided, _STAGING, actor=HUMAN, now=_NOW)
