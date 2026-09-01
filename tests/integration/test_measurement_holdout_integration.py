"""FR-13.5/§6, against a real Postgres: `record_look` durably persists every
look, and the append-only trigger (migration 0009) makes the audit trail
tamper-evident the same way `case_events` is."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import create_engine
from recoup.domain.ids import new_ulid
from recoup.measurement.holdout import HoldoutState, next_look, record_look
from recoup.measurement.schema import HoldoutLookRow
from recoup.measurement.stats import two_proportion_z_test

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def test_record_look_persists_every_field(engine: AsyncEngine) -> None:
    result = two_proportion_z_test(n_treated=400, x_treated=248, n_control=100, x_control=40)
    state = HoldoutState(current_rate=Decimal("0.20"))
    _, look = next_look(
        state,
        result=result,
        cases_observed=500,
        planned_total_cases=500,
        default_rate=Decimal("0.20"),
        floor_rate=Decimal("0.05"),
    )
    batch_id = f"b_test_integration_{new_ulid()}"

    await record_look(engine, look, batch_id=batch_id, now=_NOW, policy_version="test-policy-v1")

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        rows = (
            await session.scalars(select(HoldoutLookRow).where(HoldoutLookRow.batch_id == batch_id))
        ).all()

    assert len(rows) == 1
    row = rows[0]
    assert row.look_index == 1
    assert row.action == "established"
    assert float(row.rate_before) == pytest.approx(0.20)
    assert float(row.rate_after) == pytest.approx(float(look.rate_after))
    assert row.policy_version == "test-policy-v1"


async def test_holdout_looks_is_append_only(engine: AsyncEngine) -> None:
    result = two_proportion_z_test(n_treated=20, x_treated=11, n_control=20, x_control=9)
    state = HoldoutState(current_rate=Decimal("0.20"))
    _, look = next_look(
        state,
        result=result,
        cases_observed=40,
        planned_total_cases=500,
        default_rate=Decimal("0.20"),
        floor_rate=Decimal("0.05"),
    )
    batch_id = f"b_test_immutability_{new_ulid()}"
    await record_look(engine, look, batch_id=batch_id, now=_NOW, policy_version="test-policy-v1")

    with pytest.raises(DBAPIError, match="append-only"):
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE holdout_looks SET action = 'tampered' WHERE batch_id = :batch_id"),
                {"batch_id": batch_id},
            )
