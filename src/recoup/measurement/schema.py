"""SQLAlchemy ORM for `holdout_looks` — the append-only audit trail FR-13.5
requires ("every look is logged"). A look is a batch-level fact, so unlike
`case_events` it is not FK'd to any single case.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class HoldoutLookRow(Base):
    __tablename__ = "holdout_looks"

    look_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    look_index: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    information_fraction: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    z_boundary: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    alpha_spent: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    z_observed: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    lift: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    ci_low: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    ci_high: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    action: Mapped[str] = mapped_column(String(16))
    rate_before: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    rate_after: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    policy_version: Mapped[str] = mapped_column(String(64))
