"""Exactly-once ingestion: (source, provider_event_id) uniqueness, reserved atomically."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from recoup.ingestion.schema import ProviderEventRow


async def reserve_or_get_case_id(
    session: AsyncSession, *, source: str, provider_event_id: str, new_case_id: str
) -> tuple[str, bool]:
    """Atomically claim (source, provider_event_id) for `new_case_id`.

    Returns (case_id, is_new). If another delivery already claimed this
    provider_event_id — a genuine duplicate, or a race against a concurrent
    first delivery — returns that case's id with is_new=False instead.
    """
    stmt = (
        insert(ProviderEventRow)
        .values(
            source=source,
            provider_event_id=provider_event_id,
            case_id=new_case_id,
            first_seen_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["source", "provider_event_id"])
        .returning(ProviderEventRow.case_id)
    )
    result = await session.execute(stmt)
    claimed_case_id = result.scalar_one_or_none()
    if claimed_case_id is not None:
        return claimed_case_id, True

    existing_case_id = await session.scalar(
        select(ProviderEventRow.case_id).where(
            ProviderEventRow.source == source,
            ProviderEventRow.provider_event_id == provider_event_id,
        )
    )
    if existing_case_id is None:
        raise RuntimeError(
            f"dedupe race for ({source!r}, {provider_event_id!r}): insert lost but no "
            "existing row found"
        )
    return existing_case_id, False
