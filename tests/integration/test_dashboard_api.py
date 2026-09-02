"""FR-15/16.7 over real HTTP: the dashboard's read endpoints and the live
"Break it" control. Same `httpx.AsyncClient` + `ASGITransport` pattern as
`test_approvals_api.py`, for the same Windows/asyncpg event-loop reason.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.api.deps import get_engine, get_event_store, get_redis
from recoup.api.main import app
from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
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
    redis_client = cast(Redis, Redis.from_url(get_settings().redis_url))

    def _override_get_engine() -> AsyncEngine:
        return engine

    def _override_get_event_store() -> EventStore:
        return EventStore(engine)

    def _override_get_redis() -> Redis:
        return redis_client

    app.dependency_overrides[get_engine] = _override_get_engine
    app.dependency_overrides[get_event_store] = _override_get_event_store
    app.dependency_overrides[get_redis] = _override_get_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await redis_client.aclose()


async def test_batch_summary_returns_cases_by_state_and_chain_status(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get("/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert "cases_by_state" in body
    assert "audit_chain_verified" in body
    assert "batch_report" in body  # None is a valid, honest value if no batch has run


async def test_work_queue_returns_a_list(async_client: AsyncClient) -> None:
    response = await async_client.get("/dashboard/queue")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_case_timeline_404s_for_an_unknown_case(async_client: AsyncClient) -> None:
    response = await async_client.get(f"/dashboard/cases/{new_ulid()}/timeline")
    assert response.status_code == 404


async def test_case_timeline_renders_a_real_cases_events(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id, event_type="case.created", payload=case_created_payload(), actor=SYSTEM
    )

    response = await async_client.get(f"/dashboard/cases/{case_id}/timeline")
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["case_id"] == case_id
    assert body["events"][0]["event_type"] == "case.created"
    assert isinstance(body["case"]["amount_at_risk"], str)  # never silently float-converted


async def test_compliance_view_returns_a_tally(async_client: AsyncClient) -> None:
    response = await async_client.get("/dashboard/compliance")
    assert response.status_code == 200
    body = response.json()
    assert "blocked_by_category" in body
    assert "total_blocked" in body


async def test_model_transparency_serves_real_metrics(async_client: AsyncClient) -> None:
    response = await async_client.get("/dashboard/models")
    assert response.status_code == 200
    models = response.json()["models"]
    assert models["classifier"]["available"] is True
    assert "macro_f1" in models["classifier"]["metrics"]


async def test_grounded_qa_refuses_a_question_the_log_cannot_answer(
    engine: AsyncEngine, async_client: AsyncClient
) -> None:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id, event_type="case.created", payload=case_created_payload(), actor=SYSTEM
    )

    response = await async_client.post(
        "/dashboard/qa", json={"case_id": case_id, "question": "what is the customer's mood"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is True or body["degraded_mode"] is True


async def test_chaos_scenario_list_names_all_ten(async_client: AsyncClient) -> None:
    response = await async_client.get("/dashboard/chaos/scenarios")
    assert response.status_code == 200
    assert len(response.json()) == 10


async def test_running_a_live_chaos_scenario_reports_pass(async_client: AsyncClient) -> None:
    response = await async_client.post("/dashboard/chaos/duplicate_webhook")
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["narrative"]


async def test_running_an_unknown_chaos_scenario_404s(async_client: AsyncClient) -> None:
    response = await async_client.post("/dashboard/chaos/not_a_real_scenario")
    assert response.status_code == 404


async def test_what_if_returns_a_labelled_projection(async_client: AsyncClient) -> None:
    response = await async_client.post("/dashboard/what-if", json={"ev_floor_inr": "-1000"})
    assert response.status_code == 200
    body = response.json()
    assert body["is_projection"] is True
