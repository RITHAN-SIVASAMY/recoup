"""FR-12's public API over real HTTP: view -> pay -> simulate-payment ->
recovered; reuse refused; the Razorpay success webhook closes the loop.
Same `httpx.AsyncClient` + `ASGITransport` + full dependency-override
pattern as `test_webhook.py`/`test_approvals_api.py`, for the same Windows/
asyncpg cross-event-loop reason documented there (INC-006/INC-016).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.factories import case_created_payload

from recoup.api.deps import (
    get_event_store,
    get_link_redemption_store,
    get_optout_store,
    get_payment_link_port,
    get_redis,
    get_session,
)
from recoup.api.main import app
from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.projection import project
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.execution.links import LinkRedemptionStore, generate_link_token
from recoup.execution.optout import OptOutStore
from recoup.execution.payment_links import SimulatorPaymentLinkPort
from recoup.settings import get_settings

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
WEBHOOK_SECRET = "test-webhook-secret-for-recovery-tests"


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
    redis_client = Redis.from_url(get_settings().redis_url)

    async def _override_get_session() -> AsyncIterator[object]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_event_store] = lambda: EventStore(engine)
    app.dependency_overrides[get_link_redemption_store] = lambda: LinkRedemptionStore(engine)
    app.dependency_overrides[get_optout_store] = lambda: OptOutStore(engine)
    app.dependency_overrides[get_payment_link_port] = lambda: SimulatorPaymentLinkPort(
        get_settings().public_base_url
    )
    app.dependency_overrides[get_redis] = lambda: redis_client
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await redis_client.aclose()


async def _seeded_case(engine: AsyncEngine) -> str:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(amount_at_risk="499.00"),
        actor=SYSTEM,
    )
    await store.append(
        case_id=case_id,
        event_type="case.classified",
        payload={"root_cause": "card_expired_or_invalid", "confidence": 0.9},
        actor=SYSTEM,
    )
    return case_id


def _token(case_id: str) -> str:
    settings = get_settings()
    return generate_link_token(
        case_id,
        1,
        secret=settings.link_signing_secret,
        ttl=timedelta(hours=72),
        now=datetime.now(UTC),
    )


async def test_viewing_a_valid_link_returns_the_cause_specific_fix(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    case_id = await _seeded_case(engine)
    token = _token(case_id)

    response = await async_client.get(f"/api/recovery/{token}")

    assert response.status_code == 200
    body = response.json()
    assert body["fix"]["kind"] == "update_card"
    assert body["test_mode"] is True


async def test_an_unknown_token_is_refused_with_a_friendly_status_not_a_500(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get("/api/recovery/not-a-real-token")
    assert response.status_code == 410


async def test_the_full_pay_then_simulate_payment_flow_recovers_the_case(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    case_id = await _seeded_case(engine)
    token = _token(case_id)

    pay_response = await async_client.post(f"/api/recovery/{token}/pay")
    assert pay_response.status_code == 200
    checkout_url = pay_response.json()["checkout_url"]
    assert token in checkout_url

    confirm_response = await async_client.post(f"/api/recovery/{token}/simulate-payment")
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "recovered"

    store = EventStore(engine)
    events = await store.events_for(case_id)
    assert events[-1].event_type == "payment.recovered"

    # single-use: a second attempt is refused, never a duplicate payment.recovered
    second_attempt = await async_client.post(f"/api/recovery/{token}/simulate-payment")
    assert second_attempt.status_code == 409


async def test_opting_out_over_http_is_reflected_immediately(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    case_id = await _seeded_case(engine)
    token = _token(case_id)

    response = await async_client.post(f"/api/recovery/{token}/opt-out")
    assert response.status_code == 200
    assert response.json()["status"] == "opted_out"

    optout_store = OptOutStore(engine)
    store = EventStore(engine)
    case = project(await store.events_for(case_id))
    assert await optout_store.is_opted_out(case.customer_ref) is True


async def test_remind_later_over_http_accepts_a_valid_future_date(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    case_id = await _seeded_case(engine)
    token = _token(case_id)

    remind_at = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()
    response = await async_client.post(
        f"/api/recovery/{token}/remind-later", json={"remind_at": remind_at}
    )
    assert response.status_code == 200
    assert response.json()["remind_at"] == remind_at


async def test_the_razorpay_webhook_confirms_a_real_payment_link(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    case_id = await _seeded_case(engine)
    token = _token(case_id)

    body = json.dumps(
        {
            "payload": {
                "payment_link": {
                    "entity": {"id": "plink_live_123", "reference_id": token, "status": "paid"}
                }
            }
        }
    ).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    response = await async_client.post(
        "/webhooks/razorpay/payment-link",
        content=body,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    store = EventStore(engine)
    events = await store.events_for(case_id)
    assert events[-1].event_type == "payment.recovered"


async def test_the_razorpay_webhook_rejects_an_invalid_signature(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    case_id = await _seeded_case(engine)
    token = _token(case_id)
    body = json.dumps(
        {"payload": {"payment_link": {"entity": {"id": "plink_x", "reference_id": token}}}}
    ).encode()

    response = await async_client.post(
        "/webhooks/razorpay/payment-link",
        content=body,
        headers={
            "x-razorpay-signature": "not-a-real-signature",
            "content-type": "application/json",
        },
    )

    assert response.status_code == 200  # never a retry storm — always 200
    assert response.json()["status"] == "rejected"
    store = EventStore(engine)
    events = await store.events_for(case_id)
    assert events[-1].event_type != "payment.recovered"
