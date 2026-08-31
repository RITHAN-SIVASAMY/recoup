"""SQLAlchemy ORM for `case_events` and `cases`.

Import this only from within `audit/` — an architecture test
(tests/unit/test_architecture_boundaries.py) fails the build if any other
package imports `CaseRow`, because `EventStore.append` must be the only
write path for case state.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from recoup.domain.models import Actor, Case, CaseEvent, Cohort, ResolutionState, SourceType


class Base(DeclarativeBase):
    pass


class CaseRow(Base):
    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64))
    resolution_state: Mapped[str] = mapped_column(String(32))
    cohort: Mapped[str | None] = mapped_column(String(16))
    root_cause: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seq: Mapped[int] = mapped_column(Integer, default=0)
    tip_hash: Mapped[str | None] = mapped_column(String(64))


class CaseEventRow(Base):
    __tablename__ = "case_events"
    __table_args__ = (
        UniqueConstraint("case_id", "seq", name="uq_case_events_case_seq"),
        UniqueConstraint("idempotency_key", name="uq_case_events_idempotency_key"),
    )

    event_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(26), ForeignKey("cases.case_id"))
    seq: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[dict[str, str]] = mapped_column(JSONB)
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    policy_version: Mapped[str | None] = mapped_column(String(64))
    model_versions: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))


def event_row_to_domain(row: CaseEventRow) -> CaseEvent:
    return CaseEvent(
        event_id=row.event_id,
        case_id=row.case_id,
        seq=row.seq,
        occurred_at=row.occurred_at,
        recorded_at=row.recorded_at,
        actor=Actor.model_validate(row.actor),
        event_type=row.event_type,
        payload=row.payload,
        policy_version=row.policy_version,
        model_versions=row.model_versions,
        prev_hash=row.prev_hash,
        hash=row.hash,
    )


def case_row_to_domain(row: CaseRow) -> Case:
    if row.seq < 1 or row.tip_hash is None:
        raise ValueError(f"case {row.case_id} has no case.created event yet; not a valid Case")
    return Case(
        case_id=row.case_id,
        source_type=cast(SourceType, row.source_type),
        resolution_state=cast(ResolutionState, row.resolution_state),
        cohort=cast("Cohort | None", row.cohort),
        root_cause=row.root_cause,
        created_at=row.created_at,
        updated_at=row.updated_at,
        seq=row.seq,
        tip_hash=row.tip_hash,
    )
