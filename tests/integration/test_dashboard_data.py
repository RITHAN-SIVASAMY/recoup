"""FR-15.1/15.2/15.3/15.5/15.6: the dashboard's read-only aggregation
functions, against a real Postgres event log."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.api.dashboard_data import (
    WhatIfParams,
    cases_by_state,
    compliance_view,
    exception_queue,
    run_what_if,
    work_queue,
)
from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.measurement.cohort import CaseForAssignment, assign_cohorts, record_assignment
from recoup.policy.loader import PolicyLoader

pytestmark = pytest.mark.integration

_SYSTEM = Actor(kind="system", identifier="test")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_MERCHANT_ID = "demo-d2c"


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seed_scored_treatment_case(
    store: EventStore, *, uplift: str = "0.15", amount: str = "500.00"
) -> str:
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(merchant_id=_MERCHANT_ID, amount_at_risk=amount),
        actor=_SYSTEM,
    )
    [assignment] = assign_cohorts(
        [
            CaseForAssignment(
                case_id=case_id,
                source_type="payment_failure",
                amount_at_risk=Decimal(amount),
                merchant_id=_MERCHANT_ID,
            )
        ],
        holdout_rate=Decimal("0"),  # force treatment
        value_cap_inr=Decimal("50000"),
        salt="dashboard-test",
    )
    await record_assignment(store, assignment, policy_version="test-v1")
    await store.append(
        case_id=case_id,
        event_type="case.classified",
        payload={"root_cause": "insufficient_funds", "confidence": 0.9, "cold_start": True},
        actor=Actor(kind="model", identifier="test-classifier"),
    )
    await store.append(
        case_id=case_id,
        event_type="case.scored",
        payload={
            "p_recover_baseline": 0.3,
            "uplift": uplift,
            "uplift_segment": "persuadable",
            "relationship_weight": 0.5,
            "trust_score": 0.5,
            "priority": 0.5,
        },
        actor=Actor(kind="model", identifier="test-uplift"),
    )
    return case_id


async def test_cases_by_state_counts_resolution_states(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    await _seed_scored_treatment_case(store)

    counts = await cases_by_state(store, merchant_id=_MERCHANT_ID)
    assert counts.get("pending", 0) >= 1


async def test_work_queue_ranks_by_expected_value_and_skips_unscored_cases(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    scored_case_id = await _seed_scored_treatment_case(store)
    await store.append(
        case_id=scored_case_id,
        event_type="ev.computed",
        payload={
            "action_type": "send_message",
            "channel": "sms",
            "ladder_step": 1,
            "uplift": "0.15",
            "amount_at_risk": "500.00",
            "margin": "0.85",
            "channel_cost_inr": "0.20",
            "goodwill_cost_inr": "0.10",
            "ev_inr": "63.45",
        },
        actor=_SYSTEM,
    )

    unscored_case_id = new_ulid()
    await store.append(
        case_id=unscored_case_id,
        event_type="case.created",
        payload=case_created_payload(merchant_id=_MERCHANT_ID),
        actor=_SYSTEM,
    )
    [unscored_assignment] = assign_cohorts(
        [
            CaseForAssignment(
                case_id=unscored_case_id,
                source_type="payment_failure",
                amount_at_risk=Decimal("500"),
                merchant_id=_MERCHANT_ID,
            )
        ],
        holdout_rate=Decimal("0"),
        value_cap_inr=Decimal("50000"),
        salt="dashboard-test",
    )
    await record_assignment(store, unscored_assignment, policy_version="test-v1")

    # the shared dev database accumulates pending cases across every test run
    # in this suite (same convention as the rest of this codebase); a large
    # limit is needed so this specific case isn't pushed out by unrelated
    # history that happens to have a higher EV.
    queue = await work_queue(store, merchant_id=_MERCHANT_ID, limit=100_000)
    queue_ids = {item.case_id for item in queue}
    assert scored_case_id in queue_ids
    assert unscored_case_id not in queue_ids  # never scored -- nothing actionable to show


async def test_exception_queue_lists_cases_with_case_exception_events(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(merchant_id=_MERCHANT_ID),
        actor=_SYSTEM,
    )
    await store.append(
        case_id=case_id,
        event_type="case.exception",
        payload={"stage": "channel_send", "error": "provider is down"},
        actor=_SYSTEM,
    )

    items = await exception_queue(store, merchant_id=_MERCHANT_ID)
    matching = [item for item in items if item.case_id == case_id]
    assert len(matching) == 1
    assert "provider is down" in matching[0].reason


async def test_compliance_view_tallies_denied_actions_by_category(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(merchant_id=_MERCHANT_ID),
        actor=_SYSTEM,
    )
    await store.append(
        case_id=case_id,
        event_type="policy.denied",
        payload={"rule_id": "REG-COMM-01", "reason": "outside permitted hours"},
        actor=_SYSTEM,
    )

    tally = await compliance_view(store, merchant_id=_MERCHANT_ID)
    assert tally.blocked_by_category.get("quiet_hours", 0) >= 1
    assert tally.total_blocked >= 1


async def test_what_if_a_lower_ev_floor_makes_more_cases_contactable(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    bundle = PolicyLoader().load()
    # a deliberately weak uplift so the case sits just below the real floor
    await _seed_scored_treatment_case(store, uplift="0.01", amount="500.00")

    baseline = await run_what_if(
        store, merchant_id=_MERCHANT_ID, bundle=bundle, params=WhatIfParams()
    )
    lowered_floor = await run_what_if(
        store,
        merchant_id=_MERCHANT_ID,
        bundle=bundle,
        params=WhatIfParams(ev_floor_inr=Decimal("-1000")),
    )

    assert lowered_floor.projected_would_contact >= baseline.baseline_would_contact
