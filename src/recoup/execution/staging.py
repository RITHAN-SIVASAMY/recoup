"""FR-7.2: staged actions. Nothing leaves the system without first passing
through a cancellable state.

`StagedAction` is only ever constructed by `stage()`, and `stage()` refuses
anything but an `ALLOW` verdict — so "every executed action was staged first"
is true by construction, the same technique `policy.Verdict` uses (see
`policy/evaluator.py`'s module docstring), not merely a convention callers are
trusted to follow. Promotion (staged -> ready to actually send) is a pure
predicate here; real dispatch is `execution/`'s channel adapters, Phase 06.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore
from recoup.domain.idempotency import idempotency_key
from recoup.domain.ids import new_ulid
from recoup.domain.models import ActionType, Actor, Case, Channel, ProposedAction, Verdict
from recoup.execution.schema import StagedActionRow
from recoup.policy.schema import MerchantStaging

StagedActionStatus = Literal["staged", "cancelled", "promoted"]

_MONEY_MOVING_ACTIONS: frozenset[ActionType] = frozenset({"retry_charge"})


@dataclass(frozen=True)
class StagedAction:
    staged_action_id: str
    case_id: str
    merchant_id: str
    action_type: ActionType
    channel: Channel | None
    ladder_step: int
    idempotency_key: str
    estimated_cost_inr: Decimal
    policy_version: str
    staged_at: datetime
    promote_at: datetime
    status: StagedActionStatus = "staged"
    cancelled_at: datetime | None = None
    cancelled_by: Actor | None = None


def _undo_window(action_type: ActionType, staging: MerchantStaging) -> timedelta:
    return (
        staging.money_undo_window
        if action_type in _MONEY_MOVING_ACTIONS
        else staging.contact_undo_window
    )


async def stage(
    event_store: EventStore,
    case: Case,
    action: ProposedAction,
    verdict: Verdict,
    staging: MerchantStaging,
    now: datetime,
) -> StagedAction:
    if verdict.decision != "ALLOW":
        raise ValueError(f"only an ALLOW verdict may be staged, got {verdict.decision!r}")

    key = idempotency_key(
        case.case_id, action.action_type, action.ladder_step, verdict.policy_version
    )
    promote_at = now + _undo_window(action.action_type, staging)
    staged = StagedAction(
        staged_action_id=new_ulid(),
        case_id=case.case_id,
        merchant_id=case.merchant_id,
        action_type=action.action_type,
        channel=action.channel,
        ladder_step=action.ladder_step,
        idempotency_key=key,
        estimated_cost_inr=action.estimated_cost_inr,
        policy_version=verdict.policy_version,
        staged_at=now,
        promote_at=promote_at,
    )
    await event_store.append(
        case_id=case.case_id,
        event_type="action.staged",
        payload={
            "staged_action_id": staged.staged_action_id,
            "action_type": staged.action_type,
            "channel": staged.channel,
            "ladder_step": staged.ladder_step,
            "estimated_cost_inr": staged.estimated_cost_inr,
            "promote_at": staged.promote_at,
        },
        actor=Actor(kind="system", identifier="staging-buffer"),
        policy_version=verdict.policy_version,
        idempotency_key=key,
    )
    return staged


def cancel(staged: StagedAction, *, actor: Actor, now: datetime) -> StagedAction:
    if staged.status != "staged":
        raise ValueError(f"cannot cancel a staged action in status {staged.status!r}")
    return replace(staged, status="cancelled", cancelled_at=now, cancelled_by=actor)


async def cancel_and_log(
    event_store: EventStore, staged: StagedAction, *, actor: Actor, reason: str, now: datetime
) -> StagedAction:
    cancelled = cancel(staged, actor=actor, now=now)
    await event_store.append(
        case_id=staged.case_id,
        event_type="action.cancelled",
        payload={"staged_action_id": staged.staged_action_id, "reason": reason},
        actor=actor,
        policy_version=staged.policy_version,
    )
    return cancelled


def is_due_for_promotion(staged: StagedAction, *, now: datetime) -> bool:
    return staged.status == "staged" and now >= staged.promote_at


def promote(staged: StagedAction) -> StagedAction:
    if staged.status != "staged":
        raise ValueError(f"cannot promote a staged action in status {staged.status!r}")
    return replace(staged, status="promoted")


def _row_to_domain(row: StagedActionRow) -> StagedAction:
    return StagedAction(
        staged_action_id=row.staged_action_id,
        case_id=row.case_id,
        merchant_id=row.merchant_id,
        action_type=cast(ActionType, row.action_type),
        channel=cast("Channel | None", row.channel),
        ladder_step=row.ladder_step,
        idempotency_key=row.idempotency_key,
        estimated_cost_inr=row.estimated_cost_inr,
        policy_version=row.policy_version,
        staged_at=row.staged_at,
        promote_at=row.promote_at,
        status=cast(StagedActionStatus, row.status),
        cancelled_at=row.cancelled_at,
        cancelled_by=Actor.model_validate(row.cancelled_by) if row.cancelled_by else None,
    )


class StagingStore:
    """Durable lookup for `StagedAction`s: cancel-by-ID, list-in-flight-for-a-merchant.

    The event log (`action.staged`/`action.cancelled`) is still the source of
    truth; this is a queryable index over it, matching `EventStore`/`cases`'
    own event-sourced-projection relationship.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def save(self, staged: StagedAction) -> None:
        async with self._sessionmaker() as session, session.begin():
            row = await session.get(StagedActionRow, staged.staged_action_id)
            if row is None:
                row = StagedActionRow(staged_action_id=staged.staged_action_id)
                session.add(row)
            row.case_id = staged.case_id
            row.merchant_id = staged.merchant_id
            row.action_type = staged.action_type
            row.channel = staged.channel
            row.ladder_step = staged.ladder_step
            row.idempotency_key = staged.idempotency_key
            row.estimated_cost_inr = staged.estimated_cost_inr
            row.policy_version = staged.policy_version
            row.staged_at = staged.staged_at
            row.promote_at = staged.promote_at
            row.status = staged.status
            row.cancelled_at = staged.cancelled_at
            row.cancelled_by = (
                staged.cancelled_by.model_dump(mode="json") if staged.cancelled_by else None
            )

    async def get(self, staged_action_id: str) -> StagedAction | None:
        async with self._sessionmaker() as session:
            row = await session.get(StagedActionRow, staged_action_id)
            return _row_to_domain(row) if row is not None else None

    async def list_in_flight(self, merchant_id: str) -> Sequence[StagedAction]:
        async with self._sessionmaker() as session:
            rows = await session.scalars(
                select(StagedActionRow).where(
                    StagedActionRow.merchant_id == merchant_id,
                    StagedActionRow.status == "staged",
                )
            )
            return [_row_to_domain(row) for row in rows]
