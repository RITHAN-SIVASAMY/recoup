"""The Razorpay webhook route against a real Postgres.

Uses `httpx.AsyncClient` over `ASGITransport` rather than Starlette's `TestClient`:
`TestClient` drives the app from a separate portal-thread event loop, and handing an
asyncpg connection across that boundary to *this* loop breaks outright on Windows
(`ProactorEventLoop`'s transport ends up with no proactor at all). Running the request
on the same loop as the test — and overriding the app's DB dependencies to use this
test's own `engine` fixture instead of `api.deps`'s process-cached one — avoids both
problems at once.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.api.deps import get_event_store, get_session
from recoup.api.main import app
from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.ingestion.dlq import list_exceptions
from recoup.settings import get_settings

pytestmark = pytest.mark.integration

WEBHOOK_SECRET = "test-webhook-secret-for-integration-tests"


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


def _signed_headers(body: bytes) -> dict[str, str]:
    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"x-razorpay-signature": signature}


def _payment_failed_body(payment_id: str) -> bytes:
    return json.dumps(
        {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": 250000,
                        "currency": "INR",
                        "order_id": "order_webhook_test",
                        "method": "upi",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "insufficient funds",
                        "error_reason": "insufficient_funds",
                        "contact": "+919999999999",
                        "notes": {},
                        "created_at": 1750000000,
                    }
                }
            },
        }
    ).encode("utf-8")


async def test_replaying_one_webhook_100_times_produces_one_case_and_99_suppressions(
    async_client: AsyncClient, engine: AsyncEngine
) -> None:
    body = _payment_failed_body(f"pay_replay_test_{new_ulid()}")
    headers = _signed_headers(body)

    responses = [
        await async_client.post("/webhooks/razorpay", content=body, headers=headers)
        for _ in range(100)
    ]

    assert all(r.status_code == 200 for r in responses)
    case_ids = {r.json()["case_id"] for r in responses}
    assert case_ids == {responses[0].json()["case_id"]}  # every delivery agreed on one case
    assert responses[0].json()["status"] == "created"
    assert all(r.json()["status"] == "duplicate" for r in responses[1:])

    case_id = responses[0].json()["case_id"]
    events = await EventStore(engine).events_for(case_id)
    created = [e for e in events if e.event_type == "case.created"]
    suppressed = [e for e in events if e.event_type == "event.duplicate_suppressed"]
    assert len(created) == 1
    assert len(suppressed) == 99


async def test_invalid_signature_is_rejected_but_still_returns_200(
    async_client: AsyncClient,
) -> None:
    body = _payment_failed_body("pay_bad_sig")

    response = await async_client.post(
        "/webhooks/razorpay", content=body, headers={"x-razorpay-signature": "0" * 64}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["reason"] == "invalid_signature"


async def test_malformed_json_lands_in_the_dlq_with_200(async_client: AsyncClient) -> None:
    body = b"{not valid json"
    headers = _signed_headers(body)

    response = await async_client.post("/webhooks/razorpay", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "malformed_json" in response.json()["reason"]


async def test_unhandled_event_type_is_ignored_but_archived(async_client: AsyncClient) -> None:
    body = json.dumps({"event": "refund.processed", "payload": {}}).encode("utf-8")
    headers = _signed_headers(body)

    response = await async_client.post("/webhooks/razorpay", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "unhandled_event_type" in response.json()["reason"]


async def test_exception_queue_lists_the_rejected_deliveries(
    async_client: AsyncClient, engine: AsyncEngine
) -> None:
    body = b"{not valid json"
    headers = _signed_headers(body)
    await async_client.post("/webhooks/razorpay", content=body, headers=headers)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        entries = await list_exceptions(session)

    assert len(entries) > 0
