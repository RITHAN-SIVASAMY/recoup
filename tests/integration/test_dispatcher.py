"""GOV-MONEY-01 against a real event store: every evaluation is logged as
policy.evaluated, and DENY is additionally logged as policy.denied — the
compliance view is a query over case_events, not a special log.
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
from recoup.domain.models import Actor, Case, ProposedAction
from recoup.execution.dispatcher import evaluate_and_log
from recoup.policy.context import PolicyContext
from recoup.policy.loader import PolicyLoader

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_BUNDLE = PolicyLoader().load()
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)  # a Friday, within business hours


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seeded_case(store: EventStore, **overrides: object) -> Case:
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(**overrides),  # type: ignore[arg-type]
        actor=SYSTEM,
    )
    return Case(
        case_id=case_id,
        merchant_id="demo-merchant",
        source_type="payment_failure",
        provider_event_id="prov-1",
        amount_at_risk=Decimal("499.00"),
        customer_ref="cust_test",
        resolution_state="pending",
        cohort="control",
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
        estimated_cost_inr=Decimal("1.00"),
        expected_value_inr=Decimal("100.00"),
    )


async def test_a_deny_writes_both_policy_evaluated_and_policy_denied(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)  # cohort="control" -> RULE-CTRL-001 DENY
    ctx = PolicyContext(
        now=_NOW,
        policy=_BUNDLE,
        cohort=case.cohort,
        root_cause=case.root_cause,
        resolution_state=case.resolution_state,
    )

    verdict = await evaluate_and_log(store, case, _action(), ctx)

    assert verdict.decision == "DENY"
    assert verdict.rule_id == "RULE-CTRL-001"

    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert event_types == ["case.created", "policy.evaluated", "policy.denied"]
    assert events[-1].payload["rule_id"] == "RULE-CTRL-001"
    assert events[-1].policy_version == _BUNDLE.policy_version


async def test_an_allow_writes_only_policy_evaluated(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    ctx = PolicyContext(
        now=_NOW,
        policy=_BUNDLE,
        cohort="treatment",
        root_cause="checkout_abandonment",  # step 1 == send_message over sms/whatsapp
        resolution_state="pending",
        consent_channels=frozenset({"sms"}),
    )

    verdict = await evaluate_and_log(store, case, _action(), ctx)

    assert verdict.decision == "ALLOW"

    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert event_types == ["case.created", "policy.evaluated"]
    assert "policy.denied" not in event_types
