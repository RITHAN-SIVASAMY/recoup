"""One function every source funnels through: normalized intake -> one Case, exactly once."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from recoup.audit.event_store import EventStore
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.ingestion.dedupe import reserve_or_get_case_id
from recoup.ingestion.models import NormalizedIntake

_CASE_READY_RETRIES = 20
_CASE_READY_DELAY_SECONDS = 0.05


@dataclass(frozen=True)
class IngestResult:
    case_id: str
    created: bool  # False means this delivery was a duplicate; nothing new happened


async def ingest(
    session: AsyncSession,
    event_store: EventStore,
    intake: NormalizedIntake,
    *,
    case_id_override: str | None = None,
) -> IngestResult:
    """`case_id_override` exists only for the seeded synthetic-batch path
    (`demo.py`), so that a fixed seed reproduces identical case IDs -- and
    therefore identical downstream per-case RNG draws -- run to run. Real
    ingestion never passes it and keeps minting genuinely random IDs."""
    case_id, is_new = await reserve_or_get_case_id(
        session,
        source=intake.source_type,
        provider_event_id=intake.provider_event_id,
        new_case_id=case_id_override or new_ulid(),
    )
    await session.commit()

    if is_new:
        await event_store.append(
            case_id=case_id,
            event_type="case.created",
            payload=intake.to_case_created_payload(),
            actor=Actor(kind="provider", identifier=intake.source_type),
            occurred_at=intake.occurred_at,
        )
        return IngestResult(case_id=case_id, created=True)

    # We lost the reservation race to a concurrent first delivery of this same event.
    # The winner's case.created may not have landed yet — wait for it rather than
    # racing EventStore's own "case must exist" invariant.
    await _wait_for_case_to_exist(event_store, case_id)
    await event_store.append(
        case_id=case_id,
        event_type="event.duplicate_suppressed",
        payload={
            "source_type": intake.source_type,
            "provider_event_id": intake.provider_event_id,
        },
        actor=Actor(kind="system", identifier="ingestion"),
    )
    return IngestResult(case_id=case_id, created=False)


async def _wait_for_case_to_exist(event_store: EventStore, case_id: str) -> None:
    for _ in range(_CASE_READY_RETRIES):
        if await event_store.events_for(case_id):
            return
        await asyncio.sleep(_CASE_READY_DELAY_SECONDS)
    raise TimeoutError(f"case {case_id} was reserved but never created (dedupe race)")
