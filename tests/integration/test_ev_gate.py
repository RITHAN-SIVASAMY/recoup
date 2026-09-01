"""FR-4.2/4.3 against a real event store: `ev.computed` for every candidate,
`case.abandoned_uneconomic` with the full ledger when nothing clears the floor.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, Case
from recoup.economics.ev import select_action_or_abandon
from recoup.policy.loader import PolicyLoader

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_BUNDLE = PolicyLoader().load()
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_LADDER = _BUNDLE.ladders.ladders["checkout_abandonment"]  # step 1: send_message, [whatsapp, sms]


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seeded_case(store: EventStore, *, amount_at_risk: str) -> Case:
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(
            source_type="checkout_abandonment", amount_at_risk=amount_at_risk
        ),
        actor=SYSTEM,
    )
    return Case(
        case_id=case_id,
        merchant_id="demo-merchant",
        source_type="checkout_abandonment",
        provider_event_id="prov-1",
        amount_at_risk=Decimal(amount_at_risk),
        customer_ref="cust_test",
        resolution_state="pending",
        cohort="treatment",
        root_cause="checkout_abandonment",
        created_at=_NOW,
        updated_at=_NOW,
        seq=1,
        tip_hash="h" * 64,
    )


async def test_a_high_ev_case_selects_the_cheapest_channel_that_clears_the_floor(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store, amount_at_risk="100.00")

    action = await select_action_or_abandon(
        store,
        case=case,
        ladder=_LADDER,
        ladder_step_reached=0,
        uplift=Decimal("0.10"),
        relationship_weight=0.5,
        contacts_sent=0,
        economics=_BUNDLE.merchant.economics,
        policy_version=_BUNDLE.policy_version,
        now=_NOW,
    )

    assert action is not None
    assert action.action_type == "send_message"
    assert action.channel == "sms"  # cheaper than whatsapp, so higher EV
    assert action.expected_value_inr > _BUNDLE.merchant.economics.ev_floor_inr

    events = await store.events_for(case.case_id)
    ev_events = [e for e in events if e.event_type == "ev.computed"]
    assert len(ev_events) == 2  # one per channel candidate (whatsapp, sms)
    assert all(e.payload["channel"] in {"whatsapp", "sms"} for e in ev_events)
    assert not any(e.event_type == "case.abandoned_uneconomic" for e in events)


async def test_a_low_ev_case_abandons_with_the_full_ledger_recorded(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store, amount_at_risk="50.00")

    action = await select_action_or_abandon(
        store,
        case=case,
        ladder=_LADDER,
        ladder_step_reached=0,
        uplift=Decimal("0.01"),
        relationship_weight=0.5,
        contacts_sent=0,
        economics=_BUNDLE.merchant.economics,
        policy_version=_BUNDLE.policy_version,
        now=_NOW,
    )

    assert action is None

    events = await store.events_for(case.case_id)
    abandoned = [e for e in events if e.event_type == "case.abandoned_uneconomic"]
    assert len(abandoned) == 1
    ledger = abandoned[0].payload["ledger"]
    assert len(ledger) == 2  # whatsapp and sms candidates, both priced and rejected
    assert all(
        Decimal(entry["ev_inr"]) < _BUNDLE.merchant.economics.ev_floor_inr for entry in ledger
    )


async def test_an_exhausted_ladder_proposes_nothing_and_writes_no_events(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store, amount_at_risk="100.00")

    action = await select_action_or_abandon(
        store,
        case=case,
        ladder=_LADDER,
        ladder_step_reached=len(_LADDER.steps),  # past the last step
        uplift=Decimal("0.50"),
        relationship_weight=0.5,
        contacts_sent=0,
        economics=_BUNDLE.merchant.economics,
        policy_version=_BUNDLE.policy_version,
        now=_NOW,
    )

    assert action is None
    events = await store.events_for(case.case_id)
    assert [e.event_type for e in events] == ["case.created"]
