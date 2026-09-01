"""The Phase 05 demo hooks over real HTTP: approve a card then cancel the
staged action before it sends; hit the kill switch and watch it engage.
Same `httpx.AsyncClient` + `ASGITransport` pattern as `test_webhook.py`, for
the same Windows/asyncpg event-loop reason documented there.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.factories import case_created_payload

from recoup.api.deps import (
    get_approval_store,
    get_event_store,
    get_redis,
    get_session,
    get_staging_store,
)
from recoup.api.main import app
from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.projection import project
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, ProposedAction, Verdict
from recoup.execution.approvals import ApprovalStore, request_approval
from recoup.execution.staging import StagingStore
from recoup.settings import get_settings

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


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

    def _override_get_event_store() -> EventStore:
        return EventStore(engine)

    def _override_get_staging_store() -> StagingStore:
        return StagingStore(engine)

    def _override_get_approval_store() -> ApprovalStore:
        return ApprovalStore(engine)

    def _override_get_redis() -> Redis:
        return redis_client

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_event_store] = _override_get_event_store
    app.dependency_overrides[get_staging_store] = _override_get_staging_store
    app.dependency_overrides[get_approval_store] = _override_get_approval_store
    app.dependency_overrides[get_redis] = _override_get_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await redis_client.aclose()


async def test_approving_then_cancelling_a_staged_action_over_http(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id, event_type="case.created", payload=case_created_payload(), actor=SYSTEM
    )

    case = project(await store.events_for(case_id))
    action = ProposedAction(
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        scheduled_for=_NOW,
        estimated_cost_inr=Decimal("0.20"),
        expected_value_inr=Decimal("500.00"),
    )
    verdict = Verdict(
        decision="REQUIRE_APPROVAL",
        rule_id="RULE-APPROVAL-VALUE",
        policy_version="v1",
        reason="above threshold",
    )
    pending = await request_approval(store, case, action, verdict, uplift=Decimal("0.2"), now=_NOW)
    await ApprovalStore(engine).save(pending)

    grant_response = await async_client.post(f"/approvals/{pending.approval_id}/grant")
    assert grant_response.status_code == 200
    staged_action_id = grant_response.json()["staged_action_id"]

    staged = await StagingStore(engine).get(staged_action_id)
    assert staged is not None
    assert staged.status == "staged"

    cancel_response = await async_client.post(f"/staged/{staged_action_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    cancelled = await StagingStore(engine).get(staged_action_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    # never sends: cancelling twice is refused, proving there's no second path to "sent"
    second_cancel = await async_client.post(f"/staged/{staged_action_id}/cancel")
    assert second_cancel.status_code == 409


async def test_the_kill_switch_engages_and_disengages_over_http(async_client: AsyncClient) -> None:
    # This flips the real "demo" merchant's kill switch in the shared dev Redis,
    # so it must always end disengaged even if an assertion fails partway through.
    try:
        status_before = await async_client.get("/killswitch")
        assert status_before.json()["engaged"] is False

        engaged = await async_client.post("/killswitch/engage")
        assert engaged.status_code == 200
        assert engaged.json()["engaged"] is True

        status_during = await async_client.get("/killswitch")
        assert status_during.json()["engaged"] is True
    finally:
        disengaged = await async_client.post("/killswitch/disengage")
        assert disengaged.json()["engaged"] is False
