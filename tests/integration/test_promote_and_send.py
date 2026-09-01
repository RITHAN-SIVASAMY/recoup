"""`execution.dispatcher.promote_and_send()` against a real event store,
`staged_actions` table and Redis: the FR-9.7 delivery-state chain, resilience
around the channel call, and the DoD's full "stage -> send -> engage ->
recover" path.
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
from recoup.execution.dispatcher import promote_and_send
from recoup.execution.ports import DeliveryReceipt, RenderedMessage, SendContext
from recoup.execution.staging import StagingStore, stage
from recoup.execution.templates import TemplateLoader
from recoup.policy.schema import MerchantStaging
from recoup.settings import get_settings

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_STAGING = MerchantStaging(
    contact_undo_window=timedelta(seconds=60), money_undo_window=timedelta(minutes=5)
)
_TEMPLATES = TemplateLoader().load()


class _StubPort:
    def __init__(
        self, receipt: DeliveryReceipt | None = None, error: Exception | None = None
    ) -> None:
        self._receipt = receipt
        self._error = error
        self.calls: list[tuple[RenderedMessage, str, SendContext]] = []

    async def send(
        self, message: RenderedMessage, idempotency_key: str, context: SendContext
    ) -> DeliveryReceipt:
        self.calls.append((message, idempotency_key, context))
        if self._error is not None:
            raise self._error
        assert self._receipt is not None
        return self._receipt


def _receipt(**overrides: object) -> DeliveryReceipt:
    defaults: dict[str, object] = {
        "status": "delivered",
        "engaged": True,
        "converted": True,
        "sent_at": _NOW,
        "latency_ms": 120,
        "provider_ref": "stub-1",
    }
    defaults.update(overrides)
    return DeliveryReceipt(**defaults)  # type: ignore[arg-type]


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
        root_cause="insufficient_funds",
        created_at=_NOW,
        updated_at=_NOW,
        seq=1,
        tip_hash="h" * 64,
    )


def _action(action_type: str = "send_message", channel: str | None = "sms") -> ProposedAction:
    return ProposedAction(
        action_type=action_type,  # type: ignore[arg-type]
        channel=channel,  # type: ignore[arg-type]
        ladder_step=1,
        scheduled_for=_NOW,
        estimated_cost_inr=Decimal("0.20"),
        expected_value_inr=Decimal("10.00"),
    )


def _allow(policy_version: str = "v1") -> Verdict:
    return Verdict(
        decision="ALLOW", rule_id="RULE-ALLOW-DEFAULT", policy_version=policy_version, reason="ok"
    )


async def test_the_full_stage_send_engage_recover_path(engine: AsyncEngine, redis: Redis) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)
    staged = await stage(store, case, _action(), _allow(), _STAGING, _NOW)
    await staging_store.save(staged)

    later = _NOW + timedelta(seconds=61)  # past the 60s contact undo window
    port = _StubPort(receipt=_receipt(engaged=True, converted=True))

    receipt = await promote_and_send(
        store,
        staging_store,
        port,
        redis,
        case=case,
        staged=staged,
        templates=_TEMPLATES,
        merchant_name="Acme",
        uplift_segment="persuadable",
        now=later,
    )

    assert receipt is not None
    assert receipt.engaged is True
    assert receipt.converted is True
    assert len(port.calls) == 1

    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert event_types == [
        "case.created",
        "action.staged",
        "action.sent",
        "action.delivered",
        "action.engaged",
        "payment.recovered",
    ]

    promoted = await staging_store.get(staged.staged_action_id)
    assert promoted is not None
    assert promoted.status == "promoted"


async def test_promote_and_send_is_a_noop_before_the_undo_window_elapses(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)
    staged = await stage(store, case, _action(), _allow(), _STAGING, _NOW)
    port = _StubPort(receipt=_receipt())

    receipt = await promote_and_send(
        store,
        staging_store,
        port,
        redis,
        case=case,
        staged=staged,
        templates=_TEMPLATES,
        merchant_name="Acme",
        uplift_segment="persuadable",
        now=_NOW,  # still within the window
    )

    assert receipt is None
    assert port.calls == []
    events = await store.events_for(case.case_id)
    assert [e.event_type for e in events] == ["case.created", "action.staged"]


async def test_promoting_a_retry_charge_action_raises_rather_than_faking_a_payment(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)
    staged = await stage(
        store, case, _action("retry_charge", channel=None), _allow(), _STAGING, _NOW
    )
    port = _StubPort(receipt=_receipt())

    with pytest.raises(NotImplementedError, match="Razorpay"):
        await promote_and_send(
            store,
            staging_store,
            port,
            redis,
            case=case,
            staged=staged,
            templates=_TEMPLATES,
            merchant_name="Acme",
            uplift_segment="persuadable",
            now=_NOW + timedelta(minutes=6),
        )


async def test_a_bounced_delivery_writes_action_bounced_not_engaged(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)
    staged = await stage(store, case, _action(), _allow(), _STAGING, _NOW)
    port = _StubPort(receipt=_receipt(status="bounced", engaged=False, converted=False))

    await promote_and_send(
        store,
        staging_store,
        port,
        redis,
        case=case,
        staged=staged,
        templates=_TEMPLATES,
        merchant_name="Acme",
        uplift_segment="persuadable",
        now=_NOW + timedelta(seconds=61),
    )

    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert "action.bounced" in event_types
    assert "action.engaged" not in event_types
    assert "action.delivered" not in event_types


async def test_a_provider_failure_writes_case_exception_and_never_writes_action_sent(
    engine: AsyncEngine, redis: Redis
) -> None:
    store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = await _seeded_case(store)
    staged = await stage(store, case, _action(), _allow(), _STAGING, _NOW)
    port = _StubPort(error=RuntimeError("provider is down"))

    receipt = await promote_and_send(
        store,
        staging_store,
        port,
        redis,
        case=case,
        staged=staged,
        templates=_TEMPLATES,
        merchant_name="Acme",
        uplift_segment="persuadable",
        now=_NOW + timedelta(seconds=61),
    )

    assert receipt is None
    events = await store.events_for(case.case_id)
    event_types = [e.event_type for e in events]
    assert "case.exception" in event_types
    assert "action.sent" not in event_types
