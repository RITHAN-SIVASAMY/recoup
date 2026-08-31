"""Raw-payload archive and the dead-letter queue. Nothing inbound is ever dropped."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recoup.ingestion.schema import DlqEntryRow, RawEventRow


async def archive_raw_event(
    session: AsyncSession,
    *,
    source: str,
    headers: dict[str, str],
    raw_body: str,
    signature_valid: bool,
) -> int:
    row = RawEventRow(
        source=source,
        received_at=datetime.now(UTC),
        headers=headers,
        raw_body=raw_body,
        signature_valid=signature_valid,
    )
    session.add(row)
    await session.flush()
    return row.id


async def enqueue_dlq(
    session: AsyncSession, *, source: str, reason: str, raw_event_id: int | None = None
) -> int:
    row = DlqEntryRow(
        raw_event_id=raw_event_id,
        source=source,
        reason=reason,
        received_at=datetime.now(UTC),
        resolved=False,
    )
    session.add(row)
    await session.flush()
    return row.id


async def list_exceptions(
    session: AsyncSession, *, include_resolved: bool = False
) -> list[DlqEntryRow]:
    stmt = select(DlqEntryRow).order_by(DlqEntryRow.received_at.desc())
    if not include_resolved:
        stmt = stmt.where(DlqEntryRow.resolved.is_(False))
    return list((await session.scalars(stmt)).all())
