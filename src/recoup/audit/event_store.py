"""Append-only event store. `EventStore.append` is the only way case state changes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from recoup.audit.hashchain import GENESIS_HASH, compute_hash
from recoup.audit.projection import fold
from recoup.audit.schema import CaseEventRow, CaseRow, case_row_to_domain, event_row_to_domain
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, Case, CaseEvent
from recoup.settings import Settings, get_settings


class EventStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def append(
        self,
        *,
        case_id: str,
        event_type: str,
        payload: dict[str, Any],
        actor: Actor,
        occurred_at: datetime | None = None,
        policy_version: str | None = None,
        model_versions: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> CaseEvent:
        occurred_at = occurred_at or datetime.now(UTC)
        recorded_at = datetime.now(UTC)

        async with self._sessionmaker() as session, session.begin():
            if idempotency_key is not None:
                existing_row = await session.scalar(
                    select(CaseEventRow).where(CaseEventRow.idempotency_key == idempotency_key)
                )
                if existing_row is not None:
                    return event_row_to_domain(existing_row)

            case_row = await session.scalar(
                select(CaseRow).where(CaseRow.case_id == case_id).with_for_update()
            )
            if case_row is None:
                if event_type != "case.created":
                    raise ValueError(
                        f"case {case_id} does not exist; the first event for a case "
                        f"must be case.created, got {event_type!r}"
                    )
                case_row = CaseRow(
                    case_id=case_id,
                    source_type="unknown",
                    resolution_state="pending",
                    cohort=None,
                    root_cause=None,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                    seq=0,
                    tip_hash=None,
                )
                session.add(case_row)
                await session.flush()
                case_row = await session.scalar(
                    select(CaseRow).where(CaseRow.case_id == case_id).with_for_update()
                )
                assert case_row is not None

            current_case: Case | None = None if case_row.seq < 1 else case_row_to_domain(case_row)

            new_seq = case_row.seq + 1
            prev_hash = case_row.tip_hash or GENESIS_HASH
            event_hash = compute_hash(prev_hash, payload, new_seq, occurred_at)

            event_row = CaseEventRow(
                event_id=new_ulid(),
                case_id=case_id,
                seq=new_seq,
                occurred_at=occurred_at,
                recorded_at=recorded_at,
                actor=actor.model_dump(mode="json"),
                event_type=event_type,
                payload=payload,
                policy_version=policy_version,
                model_versions=model_versions,
                prev_hash=prev_hash,
                hash=event_hash,
                idempotency_key=idempotency_key,
            )
            session.add(event_row)

            try:
                await session.flush()
            except IntegrityError:
                if idempotency_key is None:
                    raise
                # Lost the race to a concurrent append with the same idempotency key.
                await session.rollback()
                async with self._sessionmaker() as retry_session:
                    retry_row = await retry_session.scalar(
                        select(CaseEventRow).where(CaseEventRow.idempotency_key == idempotency_key)
                    )
                if retry_row is None:
                    raise
                return event_row_to_domain(retry_row)

            domain_event = event_row_to_domain(event_row)
            updated_case = fold(current_case, domain_event)
            case_row.source_type = updated_case.source_type
            case_row.resolution_state = updated_case.resolution_state
            case_row.cohort = updated_case.cohort
            case_row.root_cause = updated_case.root_cause
            case_row.updated_at = updated_case.updated_at
            case_row.seq = new_seq
            case_row.tip_hash = event_hash

        return domain_event

    async def events_for(self, case_id: str, until: datetime | None = None) -> list[CaseEvent]:
        stmt = select(CaseEventRow).where(CaseEventRow.case_id == case_id)
        if until is not None:
            stmt = stmt.where(CaseEventRow.occurred_at <= until)
        stmt = stmt.order_by(CaseEventRow.seq)

        async with self._sessionmaker() as session:
            rows = (await session.scalars(stmt)).all()
        return [event_row_to_domain(row) for row in rows]


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    return create_async_engine((settings or get_settings()).database_url)
