"""Ingestion under stress: replay storms, malformed payloads, clock skew, and races.

"Out-of-order" and "late success retires an in-flight recovery" (per the phase-02
context file) need the execution layer (Phase 05/06) to mean anything — there is no
in-flight recovery yet to retire. What's tested here is what's actually buildable at
this phase: the two Definition-of-Done scenarios (100x replay, malformed payload),
plus timestamp-skew robustness and a genuine concurrent-delivery race.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.api.deps import get_event_store, get_session
from recoup.api.main import app
from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.ingestion.dlq import list_exceptions
from recoup.ingestion.ingest import ingest
from recoup.ingestion.models import NormalizedIntake
from recoup.settings import get_settings

pytestmark = pytest.mark.chaos

WEBHOOK_SECRET = "chaos-test-webhook-secret"


@pytest.fixture(autouse=True)
def _configure_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", WEBHOOK_SECRET, raising=False)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


@pytest.fixture
async def async_client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_session() -> AsyncIterator[object]:
        async with sessionmaker() as session:
            yield session

    def _override_get_event_store() -> EventStore:
        return EventStore(engine)

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_event_store] = _override_get_event_store
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_100x_replay_is_a_pure_noop_after_the_first_delivery(engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    intake = NormalizedIntake(
        source_type="payment_failure",
        provider_event_id=f"pay_chaos_{new_ulid()}",
        merchant_id="demo",
        amount_at_risk="499.00",
        customer_ref="cust_chaos",
        occurred_at=datetime.now(UTC),
    )

    case_ids = set()
    for _ in range(100):
        async with session_factory() as session:
            result = await ingest(session, event_store, intake)
        case_ids.add(result.case_id)

    assert len(case_ids) == 1  # exactly one case, no matter how many replays
    events = await event_store.events_for(case_ids.pop())
    event_types = [e.event_type for e in events]
    assert event_types.count("case.created") == 1
    assert event_types.count("event.duplicate_suppressed") == 99
    assert set(event_types) == {"case.created", "event.duplicate_suppressed"}  # zero actions


async def test_concurrent_first_deliveries_of_the_same_event_still_produce_one_case(
    engine: AsyncEngine,
) -> None:
    """A genuine race, not a sequential replay: N deliveries arrive at once."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    intake = NormalizedIntake(
        source_type="payment_failure",
        provider_event_id=f"pay_race_{new_ulid()}",
        merchant_id="demo",
        amount_at_risk="250.00",
        customer_ref="cust_race",
        occurred_at=datetime.now(UTC),
    )

    async def _deliver() -> str:
        async with session_factory() as session:
            result = await ingest(session, event_store, intake)
        return result.case_id

    case_ids = await asyncio.gather(*(_deliver() for _ in range(10)))

    assert len(set(case_ids)) == 1
    events = await event_store.events_for(case_ids[0])
    assert [e.event_type for e in events].count("case.created") == 1


async def test_malformed_payload_lands_in_dlq_and_exception_queue_with_http_200(
    async_client: AsyncClient, engine: AsyncEngine
) -> None:
    body = b'{"event": "payment.failed", "payload": {broken'
    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    response = await async_client.post(
        "/webhooks/razorpay", content=body, headers={"x-razorpay-signature": signature}
    )

    assert response.status_code == 200  # never triggers the provider's retry storm
    assert response.json()["status"] == "rejected"

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        exceptions = await list_exceptions(session)
    assert any("malformed_json" in entry.reason for entry in exceptions)


@pytest.mark.parametrize(
    "skew",
    [
        timedelta(days=365 * 5),  # clock five years fast
        -timedelta(days=365 * 5),  # clock five years slow
        timedelta(seconds=0),
    ],
)
async def test_ingestion_survives_extreme_clock_skew_in_the_provider_timestamp(
    engine: AsyncEngine, skew: timedelta
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    skewed_occurred_at = datetime.now(UTC) + skew
    intake = NormalizedIntake(
        source_type="payment_failure",
        provider_event_id=f"pay_skew_{new_ulid()}",
        merchant_id="demo",
        amount_at_risk="100.00",
        customer_ref="cust_skew",
        occurred_at=skewed_occurred_at,
    )

    async with session_factory() as session:
        result = await ingest(session, event_store, intake)

    events = await event_store.events_for(result.case_id)
    # occurred_at (provider time, however skewed) and recorded_at (our clock) are kept
    # distinct — the whole point of having both fields — and neither one crashes ingestion.
    assert events[0].occurred_at == skewed_occurred_at
    assert abs(events[0].recorded_at - datetime.now(UTC)) < timedelta(minutes=1)
