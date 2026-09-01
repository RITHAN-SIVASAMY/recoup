"""SQLAlchemy ORM for `understanding`'s own durable state: the trust score
(FR-11.4), a per-customer value that outlives any single case — same
pattern as `execution.optout`'s `CustomerOptOutRow`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TrustScoreRow(Base):
    __tablename__ = "trust_scores"

    customer_ref: Mapped[str] = mapped_column(String(128), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
