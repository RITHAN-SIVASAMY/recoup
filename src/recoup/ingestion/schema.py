"""SQLAlchemy ORM for ingestion's own tables: dedupe mapping, raw archive, DLQ.

None of these are `cases`/`case_events` — ingestion never writes case state directly,
only ever through `EventStore.append` (see `ingestion/ingest.py`).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProviderEventRow(Base):
    """The dedupe map: (source, provider_event_id) -> the case it produced, reserved atomically."""

    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("source", "provider_event_id", name="uq_provider_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64))
    provider_event_id: Mapped[str] = mapped_column(String(128))
    case_id: Mapped[str] = mapped_column(String(26))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RawEventRow(Base):
    """Every inbound delivery, archived before parsing — signature failures included."""

    __tablename__ = "raw_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    headers: Mapped[dict[str, str]] = mapped_column(JSONB)
    raw_body: Mapped[str] = mapped_column(Text)
    signature_valid: Mapped[bool] = mapped_column(Boolean)


class DlqEntryRow(Base):
    """Anything that could not be verified, parsed, or normalized. Never dropped."""

    __tablename__ = "dlq_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_event_id: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(256))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
