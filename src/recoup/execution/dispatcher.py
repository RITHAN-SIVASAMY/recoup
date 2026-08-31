"""Evaluate and log — GOV-MONEY-01: no action executes without a logged policy verdict.

`policy.evaluate()` stays pure (no I/O, per the import-linter contract: policy may
only import domain). This is the one place a `Verdict` gets attached to the audit
trail: every evaluation is logged as `policy.evaluated`, and every DENY is *also*
logged as `policy.denied` so the compliance view is a query over the event log,
not a special-cased log file (phase-04-policy-engine.md's own wording). Full
staging/dispatch — actually sending anything — is Phase 05/06 scope; this module
is deliberately just the evaluate-and-log seam they'll build on.
"""

from __future__ import annotations

from typing import Any

from recoup.audit.event_store import EventStore
from recoup.domain.models import Actor, Case, ProposedAction, Verdict
from recoup.policy.context import PolicyContext
from recoup.policy.evaluator import evaluate


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
