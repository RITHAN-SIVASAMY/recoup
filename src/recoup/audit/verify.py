"""Walk the hash chain and report the first divergent event, if any. Behind `make verify`.

`verify_events` is the pure algorithm (no I/O) so tamper-detection can be unit-tested
with in-memory fixtures — the DB is append-only and trigger-protected, so an
integration test cannot construct a tampered row without real, permanent damage.
`verify_chain` is the thin DB-fetching wrapper used at runtime.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.hashchain import GENESIS_HASH, compute_hash
from recoup.audit.projection import diff_against_stored, rebuild_all
from recoup.audit.schema import CaseEventRow, CaseRow, case_row_to_domain, event_row_to_domain


@dataclass(frozen=True)
class ChainEvent:
    event_id: str
    case_id: str
    seq: int
    occurred_at: datetime
    payload: dict[str, Any]
    prev_hash: str
    hash: str


@dataclass(frozen=True)
class ChainVerifyResult:
    verified: bool
    events_checked: int
    divergent_event_id: str | None = None
    reason: str | None = None


def verify_events(events: Sequence[ChainEvent]) -> ChainVerifyResult:
    tips: dict[str, str] = {}
    checked = 0
    for event in events:
        expected_prev = tips.get(event.case_id, GENESIS_HASH)
        if event.prev_hash != expected_prev:
            return ChainVerifyResult(
                False, checked, event.event_id, "prev_hash does not chain from the prior event"
            )
        expected_hash = compute_hash(event.prev_hash, event.payload, event.seq, event.occurred_at)
        if event.hash != expected_hash:
            return ChainVerifyResult(
                False, checked, event.event_id, "stored hash does not match the recomputed hash"
            )
        tips[event.case_id] = event.hash
        checked += 1

    return ChainVerifyResult(True, checked)


async def verify_chain(engine: AsyncEngine) -> ChainVerifyResult:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        rows = (
            await session.scalars(
                select(CaseEventRow).order_by(CaseEventRow.case_id, CaseEventRow.seq)
            )
        ).all()

    events = [
        ChainEvent(
            row.event_id,
            row.case_id,
            row.seq,
            row.occurred_at,
            row.payload,
            row.prev_hash,
            row.hash,
        )
        for row in rows
    ]
    return verify_events(events)


async def verify_replay_equality(engine: AsyncEngine) -> bool:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        event_rows = (
            await session.scalars(
                select(CaseEventRow).order_by(CaseEventRow.case_id, CaseEventRow.seq)
            )
        ).all()
        case_rows = (await session.scalars(select(CaseRow))).all()

    events = [event_row_to_domain(row) for row in event_rows]
    stored = {row.case_id: case_row_to_domain(row) for row in case_rows if row.seq >= 1}
    result = diff_against_stored(rebuild_all(events), stored)
    return result.matches
