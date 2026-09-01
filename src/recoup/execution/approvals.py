"""FR-7.1/FR-7.5/FR-7.7: the approval queue and the decision card.

A `REQUIRE_APPROVAL` verdict does not stage anything by itself — a human must
`grant` it first. Granting synthesizes an ALLOW-equivalent verdict (same
`policy_version`, so the idempotency key is unchanged) and stages it through
the exact same `execution.staging.stage()` every auto-approved action goes
through: an approved action is still cancellable in its undo window, per
FR-7.2's "nothing leaves the system without passing through a cancellable
state" — approval is not a bypass of staging, it is what unlocks it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore
from recoup.domain.ids import new_ulid
from recoup.domain.models import ActionType, Actor, Case, Channel, ProposedAction, Verdict
from recoup.execution.schema import PendingApprovalRow
from recoup.execution.staging import StagedAction, stage
from recoup.policy.schema import MerchantStaging

ApprovalStatus = Literal["pending", "approved", "rejected"]


@dataclass(frozen=True)
class PendingApproval:
    approval_id: str
    case_id: str
    merchant_id: str
    action: ProposedAction
    verdict: Verdict
    uplift: Decimal
    root_cause: str | None
    requested_at: datetime
    status: ApprovalStatus = "pending"
    decided_at: datetime | None = None
    decided_by: Actor | None = None


async def request_approval(
    event_store: EventStore,
    case: Case,
    action: ProposedAction,
    verdict: Verdict,
    *,
    uplift: Decimal,
    now: datetime,
) -> PendingApproval:
    if verdict.decision != "REQUIRE_APPROVAL":
        raise ValueError(
            f"only a REQUIRE_APPROVAL verdict needs an approval, got {verdict.decision!r}"
        )

    pending = PendingApproval(
        approval_id=new_ulid(),
        case_id=case.case_id,
        merchant_id=case.merchant_id,
        action=action,
        verdict=verdict,
        uplift=uplift,
        root_cause=case.root_cause,
        requested_at=now,
    )
    await event_store.append(
        case_id=case.case_id,
        event_type="approval.requested",
        payload={
            "approval_id": pending.approval_id,
            "action_type": action.action_type,
            "channel": action.channel,
            "ladder_step": action.ladder_step,
            "root_cause": case.root_cause,
            "uplift": uplift,
            "expected_value_inr": action.expected_value_inr,
            "estimated_cost_inr": action.estimated_cost_inr,
            "rule_id": verdict.rule_id,
            "reason": verdict.reason,
        },
        actor=Actor(kind="system", identifier="approval-queue"),
        policy_version=verdict.policy_version,
    )
    return pending


async def grant(
    event_store: EventStore,
    case: Case,
    pending: PendingApproval,
    staging_config: MerchantStaging,
    *,
    actor: Actor,
    now: datetime,
) -> tuple[PendingApproval, StagedAction]:
    if pending.status != "pending":
        raise ValueError(f"cannot grant an approval in status {pending.status!r}")
    if actor.kind != "human":
        raise ValueError("only a human actor may grant an approval (FR-7.1)")

    decided = replace(pending, status="approved", decided_at=now, decided_by=actor)
    await event_store.append(
        case_id=case.case_id,
        event_type="approval.granted",
        payload={"approval_id": pending.approval_id},
        actor=actor,
        policy_version=pending.verdict.policy_version,
    )
    allow_verdict = pending.verdict.model_copy(
        update={
            "decision": "ALLOW",
            "rule_id": "RULE-HUMAN-APPROVED",
            "reason": "Approved by a human reviewer.",
        }
    )
    staged = await stage(event_store, case, pending.action, allow_verdict, staging_config, now)
    return decided, staged


async def reject(
    event_store: EventStore, case: Case, pending: PendingApproval, *, actor: Actor, now: datetime
) -> PendingApproval:
    if pending.status != "pending":
        raise ValueError(f"cannot reject an approval in status {pending.status!r}")
    if actor.kind != "human":
        raise ValueError("only a human actor may reject an approval (FR-7.1)")

    decided = replace(pending, status="rejected", decided_at=now, decided_by=actor)
    await event_store.append(
        case_id=case.case_id,
        event_type="approval.rejected",
        payload={"approval_id": pending.approval_id},
        actor=actor,
        policy_version=pending.verdict.policy_version,
    )
    return decided


def _row_to_domain(row: PendingApprovalRow) -> PendingApproval:
    action = ProposedAction(
        action_type=cast(ActionType, row.action_type),
        channel=cast("Channel | None", row.channel),
        ladder_step=row.ladder_step,
        scheduled_for=row.requested_at,
        estimated_cost_inr=row.estimated_cost_inr,
        expected_value_inr=row.expected_value_inr,
    )
    verdict = Verdict(
        decision="REQUIRE_APPROVAL",
        rule_id=row.rule_id,
        policy_version=row.policy_version,
        reason=row.reason,
    )
    return PendingApproval(
        approval_id=row.approval_id,
        case_id=row.case_id,
        merchant_id=row.merchant_id,
        action=action,
        verdict=verdict,
        uplift=row.uplift,
        root_cause=row.root_cause,
        requested_at=row.requested_at,
        status=cast(ApprovalStatus, row.status),
        decided_at=row.decided_at,
        decided_by=Actor.model_validate(row.decided_by) if row.decided_by else None,
    )


class ApprovalStore:
    """Durable index over pending approvals — the queue `api/approvals.py` lists from."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def save(self, pending: PendingApproval) -> None:
        async with self._sessionmaker() as session, session.begin():
            row = await session.get(PendingApprovalRow, pending.approval_id)
            if row is None:
                row = PendingApprovalRow(approval_id=pending.approval_id)
                session.add(row)
            row.case_id = pending.case_id
            row.merchant_id = pending.merchant_id
            row.action_type = pending.action.action_type
            row.channel = pending.action.channel
            row.ladder_step = pending.action.ladder_step
            row.estimated_cost_inr = pending.action.estimated_cost_inr
            row.expected_value_inr = pending.action.expected_value_inr
            row.uplift = pending.uplift
            row.root_cause = pending.root_cause
            row.rule_id = pending.verdict.rule_id
            row.reason = pending.verdict.reason
            row.policy_version = pending.verdict.policy_version
            row.requested_at = pending.requested_at
            row.status = pending.status
            row.decided_at = pending.decided_at
            row.decided_by = (
                pending.decided_by.model_dump(mode="json") if pending.decided_by else None
            )

    async def get(self, approval_id: str) -> PendingApproval | None:
        async with self._sessionmaker() as session:
            row = await session.get(PendingApprovalRow, approval_id)
            return _row_to_domain(row) if row is not None else None

    async def list_pending(self, merchant_id: str) -> Sequence[PendingApproval]:
        async with self._sessionmaker() as session:
            rows = await session.scalars(
                select(PendingApprovalRow).where(
                    PendingApprovalRow.merchant_id == merchant_id,
                    PendingApprovalRow.status == "pending",
                )
            )
            return [_row_to_domain(row) for row in rows]
