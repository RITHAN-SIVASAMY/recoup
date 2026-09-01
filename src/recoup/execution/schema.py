"""SQLAlchemy ORM for `staged_actions` — execution's own table.

Not `cases`/`case_events`: a staged action is durable, cancellable ops state
(FR-7.2), not case history. Its `stage`/`cancel` transitions are still each
mirrored into the hash-chained event log via `action.staged`/`action.cancelled`
CaseEvents (see `execution/staging.py`) — this table exists only so a pending
action can be looked up and cancelled by ID, or listed for the kill switch to
drain, without replaying every case's full event history on every request.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StagedActionRow(Base):
    __tablename__ = "staged_actions"

    staged_action_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(26), index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str | None] = mapped_column(String(16))
    ladder_step: Mapped[int]
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    estimated_cost_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    policy_version: Mapped[str] = mapped_column(String(64))
    staged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    promote_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="staged")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[dict[str, str] | None] = mapped_column(JSONB)


class LinkRedemptionRow(Base):
    """FR-12.1/SEC-DATA-04: a recovery link is single-use for any
    state-changing action (paid, opted out, remind-later set) — this is the
    durable record that makes a second attempt with the same token refuse."""

    __tablename__ = "link_redemptions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(26), index=True)
    action: Mapped[str] = mapped_column(String(32))
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerOptOutRow(Base):
    """REG-COMM-03: opt-out propagates immediately, permanently, and across
    *all* cases for that customer — this table is the durable, fast lookup
    (one row per customer_ref) that makes that check O(1) instead of a full
    event-log scan for every case a customer might ever have."""

    __tablename__ = "customer_opt_outs"

    customer_ref: Mapped[str] = mapped_column(String(128), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    opted_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_case_id: Mapped[str] = mapped_column(String(26))


class PendingApprovalRow(Base):
    __tablename__ = "pending_approvals"

    approval_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(26), index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str | None] = mapped_column(String(16))
    ladder_step: Mapped[int]
    estimated_cost_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    expected_value_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    uplift: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    root_cause: Mapped[str | None] = mapped_column(String(64))
    rule_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(512))
    policy_version: Mapped[str] = mapped_column(String(64))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[dict[str, str] | None] = mapped_column(JSONB)
