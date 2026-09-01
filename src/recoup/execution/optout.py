"""REG-COMM-03: opt-out is honoured immediately, permanently, and across all
cases for that customer. `PolicyContext.opted_out` has been a caller-supplied
input since Phase 04 (`policy/evaluator.py` only ever checks what it's
given); this module is where that fact actually gets recorded and queried,
first exercised by the recovery page's one-tap opt-out (FR-12.4).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore
from recoup.domain.models import Actor
from recoup.execution.schema import CustomerOptOutRow


class OptOutStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def is_opted_out(self, customer_ref: str) -> bool:
        async with self._sessionmaker() as session:
            row = await session.get(CustomerOptOutRow, customer_ref)
            return row is not None

    async def record(
        self, customer_ref: str, *, merchant_id: str, source_case_id: str, now: datetime
    ) -> bool:
        """Returns True if this call recorded the opt-out, False if the
        customer had already opted out (idempotent: never a second row,
        never an error on a repeat opt-out)."""
        async with self._sessionmaker() as session, session.begin():
            existing = await session.get(CustomerOptOutRow, customer_ref)
            if existing is not None:
                return False
            session.add(
                CustomerOptOutRow(
                    customer_ref=customer_ref,
                    merchant_id=merchant_id,
                    opted_out_at=now,
                    source_case_id=source_case_id,
                )
            )
            return True


async def opt_out_and_log(
    event_store: EventStore,
    optout_store: OptOutStore,
    *,
    case_id: str,
    customer_ref: str,
    merchant_id: str,
    now: datetime,
) -> bool:
    recorded = await optout_store.record(
        customer_ref, merchant_id=merchant_id, source_case_id=case_id, now=now
    )
    if recorded:
        await event_store.append(
            case_id=case_id,
            event_type="customer.opted_out",
            payload={"customer_ref": customer_ref},
            actor=Actor(kind="human", identifier="customer"),
        )
    return recorded
