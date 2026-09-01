"""The single choke point (Phase 06): verdict check -> idempotency guard ->
stage -> send -> delivery events. This is the only module that ever calls a
`ChannelPort` — nothing else in the codebase is allowed to.

`dispatch()` covers the first half: given the EV-priced candidates for a
case's current ladder step (`economics.ev.price_ladder_step`), it abandons if
none clear the floor, evaluates each EV-cleared candidate through the policy
engine (GOV-MONEY-01: every evaluation is logged as `policy.evaluated`, every
DENY also as `policy.denied`), and lets the bandit (FR-9.2) choose among
whichever channels came back ALLOW — never a wider set. The chosen action is
idempotency-guarded (GOV-MONEY-02) and staged (FR-7.2), never sent directly.

`promote_and_send()` covers the second half, called once a staged action's
undo window has actually elapsed (a real scheduler in production; a test
simply advances `now`): renders the message, sends it through resilience
(timeout, bounded retry with jitter, a circuit breaker — guardrail #6/
`context/shared/03-guardrails.md`), and logs the FR-9.7 delivery-state chain.
Payment-retry execution (`retry_charge`) needs Razorpay integration that
does not exist yet — Phase 07 — so it is staged like any other action but
`promote_and_send` refuses to "send" it rather than fake a result.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from redis.asyncio import Redis

from recoup.audit.event_store import EventStore
from recoup.domain.idempotency import idempotency_key
from recoup.domain.models import Actor, Case, Channel, ProposedAction, Verdict
from recoup.economics.ev import PricedCandidate, abandon_if_uneconomic
from recoup.execution import bandit
from recoup.execution.approvals import ApprovalStore, PendingApproval, request_approval
from recoup.execution.idempotency import RedisIdempotencyGuard
from recoup.execution.ports import ChannelPort, DeliveryReceipt, SendContext
from recoup.execution.renderer import Drafter, render_message
from recoup.execution.resilience import CircuitBreaker, retry_with_jitter
from recoup.execution.staging import (
    StagedAction,
    StagingStore,
    is_due_for_promotion,
    promote,
    stage,
)
from recoup.execution.templates import TemplateSet
from recoup.llm.client import draft_message
from recoup.policy.context import PolicyContext
from recoup.policy.evaluator import evaluate
from recoup.policy.schema import MerchantEconomics, MerchantStaging

_SYSTEM = Actor(kind="system", identifier="dispatcher")


def _verdict_payload(action: ProposedAction, verdict: Verdict) -> dict[str, Any]:
    return {
        "action_type": action.action_type,
        "channel": action.channel,
        "ladder_step": action.ladder_step,
        "decision": verdict.decision,
        "rule_id": verdict.rule_id,
        "reason": verdict.reason,
        "obligations": verdict.obligations,
    }


async def evaluate_and_log(
    event_store: EventStore, case: Case, action: ProposedAction, ctx: PolicyContext
) -> Verdict:
    verdict = evaluate(case, action, ctx)
    payload = _verdict_payload(action, verdict)
    actor = Actor(kind="system", identifier="policy-engine")

    await event_store.append(
        case_id=case.case_id,
        event_type="policy.evaluated",
        payload=payload,
        actor=actor,
        policy_version=verdict.policy_version,
    )
    if verdict.decision == "DENY":
        await event_store.append(
            case_id=case.case_id,
            event_type="policy.denied",
            payload=payload,
            actor=actor,
            policy_version=verdict.policy_version,
        )
    return verdict


DispatchOutcomeType = Literal[
    "exhausted", "abandoned", "staged", "require_approval", "denied", "duplicate_suppressed"
]


@dataclass(frozen=True)
class DispatchResult:
    outcome: DispatchOutcomeType
    staged_action: StagedAction | None = None
    pending_approval: PendingApproval | None = None


async def dispatch(
    event_store: EventStore,
    redis: Redis,
    idempotency_guard: RedisIdempotencyGuard,
    staging_store: StagingStore,
    approval_store: ApprovalStore,
    *,
    case: Case,
    priced: list[PricedCandidate],
    ctx: PolicyContext,
    economics: MerchantEconomics,
    staging_config: MerchantStaging,
    uplift: Decimal,
    uplift_segment: str | None,
    now: datetime,
    rng: random.Random | None = None,
) -> DispatchResult:
    if not priced:
        return DispatchResult("exhausted")
    if await abandon_if_uneconomic(event_store, case, priced, economics, ctx.policy.policy_version):
        return DispatchResult("abandoned")

    cleared = [c for c in priced if c.ev_inr >= economics.ev_floor_inr]

    allowed_by_channel: dict[Channel, tuple[PricedCandidate, Verdict]] = {}
    allowed_non_channel: tuple[PricedCandidate, Verdict] | None = None
    awaiting_approval: list[tuple[PricedCandidate, Verdict]] = []

    for candidate in cleared:
        verdict = await evaluate_and_log(event_store, case, candidate.action, ctx)
        if verdict.decision == "ALLOW":
            if candidate.action.channel is not None:
                allowed_by_channel[candidate.action.channel] = (candidate, verdict)
            else:
                allowed_non_channel = (candidate, verdict)
        elif verdict.decision == "REQUIRE_APPROVAL":
            awaiting_approval.append((candidate, verdict))
        # DENY: already fully logged by evaluate_and_log; nothing further here.

    chosen: tuple[PricedCandidate, Verdict] | None = None
    if allowed_by_channel:
        # FR-9.2: the bandit may only choose among arms that are already
        # ALLOW-verdicted and already EV-cleared — this dict has nothing else.
        permitted_arms = frozenset(allowed_by_channel.keys())
        arm = await bandit.select_arm(
            redis, segment=uplift_segment, permitted_arms=permitted_arms, now=now, rng=rng
        )
        chosen = allowed_by_channel[arm]
    elif allowed_non_channel is not None:
        chosen = allowed_non_channel

    if chosen is not None:
        candidate, verdict = chosen
        key = idempotency_key(
            case.case_id,
            candidate.action.action_type,
            candidate.action.ladder_step,
            verdict.policy_version,
        )
        acquired = await idempotency_guard.try_acquire(key)
        if not acquired:
            await event_store.append(
                case_id=case.case_id,
                event_type="action.suppressed_duplicate",
                payload={"idempotency_key": key, "action_type": candidate.action.action_type},
                actor=_SYSTEM,
                policy_version=verdict.policy_version,
            )
            return DispatchResult("duplicate_suppressed")

        staged = await stage(event_store, case, candidate.action, verdict, staging_config, now)
        await staging_store.save(staged)
        return DispatchResult("staged", staged_action=staged)

    if awaiting_approval:
        candidate, verdict = max(awaiting_approval, key=lambda pair: pair[0].ev_inr)
        pending = await request_approval(
            event_store, case, candidate.action, verdict, uplift=uplift, now=now
        )
        await approval_store.save(pending)
        return DispatchResult("require_approval", pending_approval=pending)

    return DispatchResult("denied")


async def promote_and_send(
    event_store: EventStore,
    staging_store: StagingStore,
    channel_port: ChannelPort,
    redis: Redis,
    *,
    case: Case,
    staged: StagedAction,
    templates: TemplateSet,
    merchant_name: str,
    uplift_segment: str | None,
    now: datetime,
    drafter: Drafter = draft_message,
    breaker: CircuitBreaker | None = None,
) -> DeliveryReceipt | None:
    if staged.channel is None:
        raise NotImplementedError(
            f"{staged.action_type!r} has no channel — payment-retry execution needs Razorpay "
            "integration (Phase 07); only channel-based contact actions promote in Phase 06"
        )
    if not is_due_for_promotion(staged, now=now):
        return None

    message, drafted_by_llm = await render_message(
        case=case,
        action_type=staged.action_type,
        channel=staged.channel,
        ladder_step=staged.ladder_step,
        merchant_name=merchant_name,
        templates=templates,
        drafter=drafter,
    )

    promoted = promote(staged)
    await staging_store.save(promoted)

    breaker = breaker or CircuitBreaker()
    context = SendContext(case_id=case.case_id, uplift_segment=uplift_segment)

    async def _attempt() -> DeliveryReceipt:
        return await channel_port.send(message, staged.idempotency_key, context)

    try:
        receipt = await breaker.call(lambda: retry_with_jitter(_attempt))
    except Exception as exc:
        await event_store.append(
            case_id=case.case_id,
            event_type="case.exception",
            payload={
                "stage": "channel_send",
                "action_type": staged.action_type,
                "channel": staged.channel,
                "error": str(exc),
            },
            actor=_SYSTEM,
            policy_version=staged.policy_version,
        )
        return None

    await event_store.append(
        case_id=case.case_id,
        event_type="action.sent",
        payload={
            "staged_action_id": staged.staged_action_id,
            "channel": staged.channel,
            "drafted_by_llm": drafted_by_llm,
            "latency_ms": receipt.latency_ms,
        },
        actor=_SYSTEM,
        policy_version=staged.policy_version,
    )

    if receipt.status == "bounced":
        await event_store.append(
            case_id=case.case_id,
            event_type="action.bounced",
            payload={},
            actor=_SYSTEM,
            policy_version=staged.policy_version,
        )
    elif receipt.status == "failed":
        await event_store.append(
            case_id=case.case_id,
            event_type="action.failed",
            payload={},
            actor=_SYSTEM,
            policy_version=staged.policy_version,
        )
    else:
        await event_store.append(
            case_id=case.case_id,
            event_type="action.delivered",
            payload={},
            actor=_SYSTEM,
            policy_version=staged.policy_version,
        )
        if receipt.engaged:
            await event_store.append(
                case_id=case.case_id,
                event_type="action.engaged",
                payload={},
                actor=_SYSTEM,
                policy_version=staged.policy_version,
            )
        if receipt.converted:
            await event_store.append(
                case_id=case.case_id,
                event_type="payment.recovered",
                payload={"via": "action_engagement", "staged_action_id": staged.staged_action_id},
                actor=_SYSTEM,
                policy_version=staged.policy_version,
            )

    await bandit.update_posterior(
        redis,
        uplift_segment,
        staged.channel,
        bandit.hour_bucket(now),
        success=receipt.engaged,
    )
    return receipt
