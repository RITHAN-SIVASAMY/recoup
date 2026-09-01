"""FR-7.1/7.4/7.5: the approval queue, staged-action cancellation, and the kill
switch — the human-authority surface over autonomous action. Thin by design:
all decision logic lives in `execution/approvals.py`, `execution/staging.py`
and `execution/killswitch.py`; this router only wires HTTP to it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis

from recoup.api.deps import (
    get_approval_store,
    get_event_store,
    get_policy,
    get_redis,
    get_staging_store,
)
from recoup.audit.event_store import EventStore
from recoup.audit.projection import project
from recoup.domain.models import Actor, Case
from recoup.execution import killswitch
from recoup.execution.approvals import ApprovalStore, grant, reject
from recoup.execution.staging import StagingStore, cancel_and_log
from recoup.policy.schema import PolicyBundle

router = APIRouter()

Human = Actor(
    kind="human", identifier="demo-ops"
)  # single-operator demo; real auth is out of scope here


async def _case_for(event_store: EventStore, case_id: str) -> Case:
    events = await event_store.events_for(case_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    return project(events)


@router.get("/approvals")
async def list_approvals(
    approval_store: Annotated[ApprovalStore, Depends(get_approval_store)],
    policy: Annotated[PolicyBundle, Depends(get_policy)],
) -> list[dict[str, object]]:
    pending = await approval_store.list_pending(policy.merchant.merchant_id)
    return [
        {
            "approval_id": p.approval_id,
            "case_id": p.case_id,
            "root_cause": p.root_cause,
            "action_type": p.action.action_type,
            "channel": p.action.channel,
            "uplift": p.uplift,
            "expected_value_inr": p.action.expected_value_inr,
            "estimated_cost_inr": p.action.estimated_cost_inr,
            "rule_id": p.verdict.rule_id,
            "reason": p.verdict.reason,
            "requested_at": p.requested_at,
        }
        for p in pending
    ]


@router.post("/approvals/{approval_id}/grant")
async def grant_approval(
    approval_id: str,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    approval_store: Annotated[ApprovalStore, Depends(get_approval_store)],
    staging_store: Annotated[StagingStore, Depends(get_staging_store)],
    policy: Annotated[PolicyBundle, Depends(get_policy)],
) -> dict[str, object]:
    pending = await approval_store.get(approval_id)
    if pending is None:
        raise HTTPException(status_code=404, detail=f"approval {approval_id} not found")
    case = await _case_for(event_store, pending.case_id)
    now = datetime.now(UTC)
    decided, staged = await grant(
        event_store, case, pending, policy.merchant.staging, actor=Human, now=now
    )
    await approval_store.save(decided)
    await staging_store.save(staged)
    return {
        "approval_id": decided.approval_id,
        "status": decided.status,
        "staged_action_id": staged.staged_action_id,
    }


@router.post("/approvals/{approval_id}/reject")
async def reject_approval(
    approval_id: str,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    approval_store: Annotated[ApprovalStore, Depends(get_approval_store)],
) -> dict[str, object]:
    pending = await approval_store.get(approval_id)
    if pending is None:
        raise HTTPException(status_code=404, detail=f"approval {approval_id} not found")
    case = await _case_for(event_store, pending.case_id)
    decided = await reject(event_store, case, pending, actor=Human, now=datetime.now(UTC))
    await approval_store.save(decided)
    return {"approval_id": decided.approval_id, "status": decided.status}


@router.post("/staged/{staged_action_id}/cancel")
async def cancel_staged_action(
    staged_action_id: str,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    staging_store: Annotated[StagingStore, Depends(get_staging_store)],
) -> dict[str, object]:
    staged = await staging_store.get(staged_action_id)
    if staged is None:
        raise HTTPException(status_code=404, detail=f"staged action {staged_action_id} not found")
    if staged.status != "staged":
        raise HTTPException(status_code=409, detail=f"staged action is already {staged.status!r}")
    cancelled = await cancel_and_log(
        event_store, staged, actor=Human, reason="manual_cancel", now=datetime.now(UTC)
    )
    await staging_store.save(cancelled)
    return {"staged_action_id": cancelled.staged_action_id, "status": cancelled.status}


@router.get("/killswitch")
async def killswitch_status(
    redis: Annotated[Redis, Depends(get_redis)],
    policy: Annotated[PolicyBundle, Depends(get_policy)],
) -> dict[str, bool]:
    engaged = await killswitch.is_engaged(redis, policy.merchant.merchant_id)
    return {"engaged": engaged}


@router.post("/killswitch/engage")
async def engage_killswitch(
    redis: Annotated[Redis, Depends(get_redis)],
    event_store: Annotated[EventStore, Depends(get_event_store)],
    staging_store: Annotated[StagingStore, Depends(get_staging_store)],
    policy: Annotated[PolicyBundle, Depends(get_policy)],
) -> dict[str, object]:
    merchant_id = policy.merchant.merchant_id
    now = datetime.now(UTC)
    await killswitch.engage(redis, merchant_id, actor=Human, now=now)
    cancelled = await killswitch.cancel_all_in_flight(
        event_store, staging_store, merchant_id, actor=Human, now=now
    )
    return {"engaged": True, "cancelled_staged_actions": len(cancelled)}


@router.post("/killswitch/disengage")
async def disengage_killswitch(
    redis: Annotated[Redis, Depends(get_redis)],
    policy: Annotated[PolicyBundle, Depends(get_policy)],
) -> dict[str, bool]:
    await killswitch.disengage(redis, policy.merchant.merchant_id)
    return {"engaged": False}
