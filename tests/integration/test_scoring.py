"""End-to-end scoring: ingest a real case, then score it, against a real Postgres.

Skipped when `ml/artifacts/` doesn't exist (run `make train` first) — CI's `tests`
job and `models` job are separate runners with no shared filesystem state, so this
suite cannot assume training already happened, the way `models` (which runs the
three ml/train_*.py scripts itself before anything that needs their output) can.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.ingestion.ingest import ingest
from recoup.ingestion.models import NormalizedIntake
from recoup.understanding.score import score_case

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not Path("ml/artifacts/classifier/model.joblib").exists(),
        reason="ml/artifacts/ not present — run `make train` first",
    ),
]


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def test_score_case_appends_classified_and_scored_events_with_model_versions(
    engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    intake = NormalizedIntake(
        source_type="payment_failure",
        provider_event_id=f"pay_score_{new_ulid()}",
        merchant_id="demo-d2c",
        amount_at_risk="1999.00",
        customer_ref="cust_score_test",
        occurred_at=datetime.now(UTC),
        detail={
            "error_reason": "insufficient_funds",
            "method": "upi",
            "issuer": "HDFC Bank",
            "order_id": "order_score_test",
        },
    )

    async with session_factory() as session:
        result = await ingest(session, event_store, intake)

    await score_case(event_store, result.case_id)

    events = await event_store.events_for(result.case_id)
    event_types = [e.event_type for e in events]
    assert "case.classified" in event_types
    assert "case.scored" in event_types

    classified = next(e for e in events if e.event_type == "case.classified")
    scored = next(e for e in events if e.event_type == "case.scored")

    assert classified.model_versions is not None
    assert classified.model_versions["classifier"]
    assert classified.payload["root_cause"] in {
        "insufficient_funds",
        "bank_soft_decline",
        "unknown",
    }
    assert 0.0 <= classified.payload["confidence"] <= 1.0

    assert scored.model_versions is not None
    assert scored.model_versions["uplift"]
    assert scored.payload["uplift_segment"] in {
        "persuadable",
        "sure_thing",
        "lost_cause",
        "sleeping_dog",
    }
    assert 0.0 <= scored.payload["p_recover_baseline"] <= 1.0


async def test_score_case_on_checkout_abandonment_is_deterministic_not_modelled(
    engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    intake = NormalizedIntake(
        source_type="checkout_abandonment",
        provider_event_id=f"co_score_{new_ulid()}",
        merchant_id="demo-d2c",
        amount_at_risk="799.00",
        customer_ref="cust_score_abandon",
        occurred_at=datetime.now(UTC),
        detail={"initiated_method": "upi"},
    )

    async with session_factory() as session:
        result = await ingest(session, event_store, intake)

    await score_case(event_store, result.case_id)

    events = await event_store.events_for(result.case_id)
    classified = next(e for e in events if e.event_type == "case.classified")

    assert classified.payload["root_cause"] == "checkout_abandonment"
    assert classified.payload["confidence"] == 1.0
    assert classified.model_versions is None  # no model was involved
