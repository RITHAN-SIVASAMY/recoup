"""`execution.dispatcher.dispatch()` against a real event store, Redis and the
staged_actions/pending_approvals tables — every branch of the choke point:
abandon, deny, require-approval, duplicate-suppress, and the bandit-staged
happy path.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, Case
from recoup.economics.ev import price_ladder_step
from recoup.execution.approvals import ApprovalStore
from recoup.execution.dispatcher import dispatch
from recoup.execution.idempotency import RedisIdempotencyGuard
from recoup.execution.staging import StagingStore
from recoup.policy.context import PolicyContext
from recoup.policy.loader import PolicyLoader
from recoup.settings import get_settings

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_BUNDLE = PolicyLoader().load()
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)  # a Friday, within business hours
_LADDER = _BUNDLE.ladders.ladders["checkout_abandonment"]  # step 1: send_message, [whatsapp, sms]


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


async def _seeded_case(store: EventStore, *, amount_at_risk: str = "500.00") -> Case:
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


def _ctx(**overrides: object) -> PolicyContext:
    defaults: dict[str, object] = {
        "now": _NOW,
        "policy": _BUNDLE,
        "cohort": "treatment",
        "root_cause": "checkout_abandonment",
        "resolution_state": "pending",
        "consent_channels": frozenset({"sms", "whatsapp", "email", "voice"}),
    }
    defaults.update(overrides)
    return PolicyContext(**defaults)  # type: ignore[arg-type]


async def _price(store: EventStore, case: Case, **overrides: object) -> list:
    defaults: dict[str, object] = {
        "case": case,
        "ladder": _LADDER,
        "ladder_step_reached": 0,
        "uplift": Decimal("0.10"),
        "relationship_weight": 0.5,
        "contacts_sent": 0,
        "economics": _BUNDLE.merchant.economics,
        "policy_version": _BUNDLE.policy_version,
        "now": _NOW,
    }
    defaults.update(overrides)
    return await price_ladder_step(store, **defaults)  # type: ignore[arg-type]


async def test_an_allowed_case_gets_staged_via_the_bandit(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    priced = await _price(store, case)

    result = await dispatch(
        store,
        redis,
        RedisIdempotencyGuard(redis),
        StagingStore(engine),
        ApprovalStore(engine),
        case=case,
        priced=priced,
        ctx=_ctx(),
        economics=_BUNDLE.merchant.economics,
        staging_config=_BUNDLE.merchant.staging,
        uplift=Decimal("0.10"),
        uplift_segment="persuadable",
        now=_NOW,
        rng=random.Random(0),
    )

    assert result.outcome == "staged"
    assert result.staged_action is not None
    assert result.staged_action.channel in {"sms", "whatsapp"}

    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert "policy.evaluated" in event_types
    assert "action.staged" in event_types
    assert "policy.denied" not in event_types


async def test_a_low_ev_case_is_abandoned_before_any_policy_evaluation(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store, amount_at_risk="50.00")
    priced = await _price(store, case, uplift=Decimal("0.01"))

    result = await dispatch(
        store,
        redis,
        RedisIdempotencyGuard(redis),
        StagingStore(engine),
        ApprovalStore(engine),
        case=case,
        priced=priced,
        ctx=_ctx(),
        economics=_BUNDLE.merchant.economics,
        staging_config=_BUNDLE.merchant.staging,
        uplift=Decimal("0.01"),
        uplift_segment="lost_cause",
        now=_NOW,
    )

    assert result.outcome == "abandoned"
    events = await store.events_for(case.case_id)
    assert any(e.event_type == "case.abandoned_uneconomic" for e in events)
    assert not any(e.event_type == "policy.evaluated" for e in events)


async def test_a_denied_case_reports_denied_and_nothing_is_staged(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    priced = await _price(store, case)

    result = await dispatch(
        store,
        redis,
        RedisIdempotencyGuard(redis),
        StagingStore(engine),
        ApprovalStore(engine),
        case=case,
        priced=priced,
        ctx=_ctx(cohort="control"),  # RULE-CTRL-001 denies everything
        economics=_BUNDLE.merchant.economics,
        staging_config=_BUNDLE.merchant.staging,
        uplift=Decimal("0.10"),
        uplift_segment="persuadable",
        now=_NOW,
    )

    assert result.outcome == "denied"
    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert event_types.count("policy.denied") == len(priced)
    assert "action.staged" not in event_types


async def test_a_high_value_case_requires_approval_instead_of_staging(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store, amount_at_risk="500000.00")
    priced = await _price(store, case)

    result = await dispatch(
        store,
        redis,
        RedisIdempotencyGuard(redis),
        StagingStore(engine),
        ApprovalStore(engine),
        case=case,
        priced=priced,
        ctx=_ctx(),
        economics=_BUNDLE.merchant.economics,
        staging_config=_BUNDLE.merchant.staging,
        uplift=Decimal("0.10"),
        uplift_segment="persuadable",
        now=_NOW,
    )

    assert result.outcome == "require_approval"
    assert result.pending_approval is not None
    events = await store.events_for(case.case_id)
    assert any(e.event_type == "approval.requested" for e in events)


async def test_a_duplicate_dispatch_is_suppressed_and_never_double_staged(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    case = await _seeded_case(store)
    priced = await _price(store, case)
    guard = RedisIdempotencyGuard(redis)
    staging_store = StagingStore(engine)
    approval_store = ApprovalStore(engine)

    first = await dispatch(
        store,
        redis,
        guard,
        staging_store,
        approval_store,
        case=case,
        priced=priced,
        ctx=_ctx(),
        economics=_BUNDLE.merchant.economics,
        staging_config=_BUNDLE.merchant.staging,
        uplift=Decimal("0.10"),
        uplift_segment="persuadable",
        now=_NOW,
        rng=random.Random(0),
    )
    assert first.outcome == "staged"

    # re-price (a second scoring pass on the same case+step) and dispatch again
    priced_again = await _price(store, case)
    second = await dispatch(
        store,
        redis,
        guard,
        staging_store,
        approval_store,
        case=case,
        priced=priced_again,
        ctx=_ctx(),
        economics=_BUNDLE.merchant.economics,
        staging_config=_BUNDLE.merchant.staging,
        uplift=Decimal("0.10"),
        uplift_segment="persuadable",
        now=_NOW,
        rng=random.Random(0),
    )
    assert second.outcome == "duplicate_suppressed"

    events = await store.events_for(case.case_id)
    assert [e.event_type for e in events].count("action.staged") == 1
