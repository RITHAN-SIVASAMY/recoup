"""FR-13.1/13.2, against a real Postgres event log: `record_assignment`
appends `case.cohort_assigned` and it folds correctly into the projected
`Case.cohort`; and the DB-level control-integrity guard (0008's trigger)
makes it structurally impossible for a `staged_actions` row to attach to a
control-cohort case, independent of the policy engine's own RULE-CTRL-001.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.projection import project
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.execution.staging import StagedAction, StagingStore
from recoup.measurement.cohort import CaseForAssignment, assign_cohorts, record_assignment

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_SYSTEM = Actor(kind="system", identifier="test")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seed_case(store: EventStore, *, amount_at_risk: str = "500.00") -> str:
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(amount_at_risk=amount_at_risk),
        actor=_SYSTEM,
    )
    return case_id


async def _seed_and_assign_control(engine: AsyncEngine, store: EventStore) -> str:
    case_id = await _seed_case(store)
    [assignment] = assign_cohorts(
        [
            CaseForAssignment(
                case_id=case_id,
                source_type="payment_failure",
                amount_at_risk=Decimal("500"),
                merchant_id="demo-d2c",
            )
        ],
        holdout_rate=Decimal("1.0"),  # forces control -- nothing to leave to chance
        value_cap_inr=Decimal("50000"),
        salt="integration-salt",
    )
    assert assignment.cohort == "control"
    await record_assignment(store, assignment, policy_version="test-policy-v1")
    return case_id


async def test_cohort_assignment_folds_into_the_projected_case(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seed_and_assign_control(engine, store)

    events = await store.events_for(case_id)
    cohort_events = [e for e in events if e.event_type == "case.cohort_assigned"]
    assert len(cohort_events) == 1
    assert cohort_events[0].payload["cohort"] == "control"

    case = project(events)
    assert case.cohort == "control"


async def test_a_control_case_can_never_get_a_staged_action_row(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seed_and_assign_control(engine, store)

    staging_store = StagingStore(engine)
    doomed = StagedAction(
        staged_action_id=new_ulid(),
        case_id=case_id,
        merchant_id="demo-d2c",
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        idempotency_key=new_ulid(),
        estimated_cost_inr=Decimal("0.20"),
        policy_version="test-policy-v1",
        staged_at=_NOW,
        promote_at=_NOW,
    )

    with pytest.raises(DBAPIError, match="control cohort"):
        await staging_store.save(doomed)
