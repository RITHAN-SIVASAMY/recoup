"""A small generated batch, ingested through the real pipeline into Postgres.

Seeds are drawn from OS entropy at test-run time, not hardcoded: `generate_batch`
is deterministic *given* a seed, but the dev database is shared and persistent
across runs of this suite, so a fixed literal seed collides with itself on rerun
(this bit us once already — see the incident log).
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine
from recoup.data.generate import generate_batch
from recoup.ingestion.ingest import ingest

pytestmark = pytest.mark.integration

_entropy = random.SystemRandom()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def test_generated_batch_ingests_into_real_cases(engine: AsyncEngine) -> None:
    batch = generate_batch(seed=_entropy.randint(1, 2**31 - 1), n_cases=12)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)

    case_ids = []
    for intake in batch.intake:
        async with session_factory() as session:
            result = await ingest(session, event_store, intake)
        case_ids.append(result.case_id)
        assert result.created is True  # first time this seed has ever been ingested

    assert len(set(case_ids)) == len(batch.intake)  # every case is distinct

    for case_id, intake in zip(case_ids, batch.intake, strict=True):
        events = await event_store.events_for(case_id)
        assert events[0].event_type == "case.created"
        assert events[0].payload["source_type"] == intake.source_type
        assert events[0].payload["merchant_id"] == intake.merchant_id


async def test_reingesting_the_same_seed_is_fully_deduped(engine: AsyncEngine) -> None:
    batch = generate_batch(seed=_entropy.randint(1, 2**31 - 1), n_cases=5)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)

    async def _ingest_all() -> list[bool]:
        created = []
        for intake in batch.intake:
            async with session_factory() as session:
                result = await ingest(session, event_store, intake)
            created.append(result.created)
        return created

    first_run = await _ingest_all()
    second_run = await _ingest_all()

    assert all(first_run)  # every case is new the first time
    assert not any(second_run)  # every case is a duplicate the second time
