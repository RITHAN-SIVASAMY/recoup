"""FR-15: read-only aggregation over the live cases/case_events tables for
the merchant dashboard. Nothing here writes, and nothing here re-runs the
batch pipeline -- it reads whatever the event log currently says, whether
it got there via `make demo` or real traffic.

The batch summary's statistical headline (incremental ₹, CI, z, p, MDE,
CUPED) is read from the most recent `make demo` report on disk rather than
recomputed live: `measurement.report.build_report` already computes it
precisely from a well-defined batch, and re-deriving an equally precise
number from raw events on every dashboard load would either duplicate that
logic or be less rigorous than it. "Cases by state" and the compliance
tally *are* computed live, because those are just counts over whatever
currently exists -- there is no equivalent pre-computed source for them.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from recoup.audit.event_store import EventStore
from recoup.domain.models import Case
from recoup.economics.ev import expected_value
from recoup.policy.categories import category_for
from recoup.policy.schema import PolicyBundle

_CONCURRENCY = 15
_REPORTS_DIR = Path("data/reports")


async def _gather_bounded[T](
    coros: Iterable[Awaitable[T]], *, limit: int = _CONCURRENCY
) -> list[T]:
    semaphore = asyncio.Semaphore(limit)

    async def _run(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(*(_run(c) for c in coros))


def latest_batch_report() -> dict[str, object] | None:
    if not _REPORTS_DIR.exists():
        return None
    json_files = sorted(_REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        return None
    data: dict[str, object] = json.loads(json_files[0].read_text(encoding="utf-8"))
    return data


async def cases_by_state(
    event_store: EventStore, *, merchant_id: str | None = None
) -> dict[str, int]:
    cases = await event_store.all_cases(merchant_id=merchant_id)
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.resolution_state] = counts.get(case.resolution_state, 0) + 1
    return counts


@dataclass(frozen=True)
class WorkQueueItem:
    case_id: str
    root_cause: str | None
    amount_at_risk: Decimal
    uplift: float | None
    uplift_segment: str | None
    expected_value_inr: Decimal | None
    reason: str
    updated_at: datetime


async def _work_queue_item(event_store: EventStore, case: Case) -> WorkQueueItem | None:
    events = await event_store.events_for(case.case_id)
    scored = next((e for e in events if e.event_type == "case.scored"), None)
    if scored is None:
        return None  # not yet scored -- nothing actionable to show yet
    ev_events = [e for e in events if e.event_type == "ev.computed"]
    best_ev = max(ev_events, key=lambda e: Decimal(str(e.payload["ev_inr"]))) if ev_events else None
    uplift = float(scored.payload["uplift"])
    segment = scored.payload.get("uplift_segment")
    reason = (
        f"{segment or 'unscored'} segment, {uplift:+.1%} uplift on ₹{case.amount_at_risk} at risk"
    )
    return WorkQueueItem(
        case_id=case.case_id,
        root_cause=case.root_cause,
        amount_at_risk=case.amount_at_risk,
        uplift=uplift,
        uplift_segment=segment,
        expected_value_inr=Decimal(str(best_ev.payload["ev_inr"])) if best_ev else None,
        reason=reason,
        updated_at=case.updated_at,
    )


async def work_queue(
    event_store: EventStore, *, merchant_id: str | None = None, limit: int = 50
) -> list[WorkQueueItem]:
    cases = await event_store.all_cases(merchant_id=merchant_id)
    pending = [c for c in cases if c.resolution_state == "pending" and c.cohort == "treatment"]
    items = await _gather_bounded(_work_queue_item(event_store, c) for c in pending)
    ranked = sorted(
        (item for item in items if item is not None),
        key=lambda item: item.expected_value_inr or Decimal("-999999999"),
        reverse=True,
    )
    return ranked[:limit]


@dataclass(frozen=True)
class ComplianceTally:
    blocked_by_category: dict[str, int]
    total_blocked: int


async def compliance_view(
    event_store: EventStore, *, merchant_id: str | None = None, sample_size: int = 300
) -> ComplianceTally:
    cases = await event_store.all_cases(merchant_id=merchant_id)
    case_ids = [c.case_id for c in cases[:sample_size]]
    all_events = await _gather_bounded(event_store.events_for(cid) for cid in case_ids)
    blocked: dict[str, int] = {}
    for events in all_events:
        for event in events:
            if event.event_type != "policy.denied":
                continue
            category = category_for(str(event.payload.get("rule_id", "")))
            blocked[category] = blocked.get(category, 0) + 1
    return ComplianceTally(blocked_by_category=blocked, total_blocked=sum(blocked.values()))


@dataclass(frozen=True)
class ExceptionQueueItem:
    case_id: str
    root_cause: str | None
    amount_at_risk: Decimal
    reason: str
    occurred_at: datetime


@dataclass(frozen=True)
class WhatIfParams:
    ev_floor_inr: Decimal | None = None
    channel_cost_inr: Decimal | None = None  # a single hypothetical per-message cost
    approval_threshold_inr: Decimal | None = None
    max_contacts: int | None = None


@dataclass(frozen=True)
class WhatIfProjection:
    cases_considered: int
    baseline_would_contact: int
    projected_would_contact: int
    newly_contactable: int  # would start clearing the EV floor that didn't before
    newly_uneconomic: int  # would stop clearing the EV floor that did before
    newly_requires_approval: int
    no_longer_requires_approval: int
    newly_over_contact_cap: int


async def run_what_if(
    event_store: EventStore,
    *,
    merchant_id: str | None = None,
    bundle: PolicyBundle,
    params: WhatIfParams,
) -> WhatIfProjection:
    """FR-15.5: replays the historical log through a hypothetical policy --
    a *projection*, never a measurement (this phase's own guardrail). It
    deliberately never estimates a projected ₹ recovered: whether a
    newly-contactable case would actually have resolved is unknowable
    without the case's real-world counterfactual, which no amount of
    replaying the log can supply. What it *can* honestly report is how
    many verdicts would flip -- which cases would newly clear or fail the
    EV floor, newly need approval, or newly exceed the contact cap -- since
    those are pure functions of numbers already on record.
    """
    economics = bundle.merchant.economics
    ev_floor = params.ev_floor_inr if params.ev_floor_inr is not None else economics.ev_floor_inr
    channel_cost = (
        params.channel_cost_inr
        if params.channel_cost_inr is not None
        else min(economics.channel_costs_inr.values())
    )
    approval_threshold = (
        params.approval_threshold_inr
        if params.approval_threshold_inr is not None
        else bundle.merchant.approval.value_threshold_inr
    )
    max_contacts = (
        params.max_contacts
        if params.max_contacts is not None
        else bundle.regulatory.contact_fatigue.max_contacts
    )

    cases = await event_store.all_cases(merchant_id=merchant_id)
    scored_cases = [c for c in cases if c.cohort == "treatment"]

    considered = 0
    baseline_contact = projected_contact = 0
    newly_contactable = newly_uneconomic = 0
    newly_needs_approval = no_longer_needs_approval = 0
    newly_over_cap = 0

    for case in scored_cases:
        events = await event_store.events_for(case.case_id)
        scored = next((e for e in events if e.event_type == "case.scored"), None)
        if scored is None:
            continue
        considered += 1
        uplift = Decimal(str(scored.payload["uplift"]))
        contacts_sent = sum(1 for e in events if e.event_type == "action.sent")

        baseline_ev = expected_value(
            uplift=uplift,
            amount_at_risk=case.amount_at_risk,
            margin=economics.margin,
            channel_cost_inr=min(economics.channel_costs_inr.values()),
            goodwill_cost_inr=Decimal("0"),
        )
        projected_ev = expected_value(
            uplift=uplift,
            amount_at_risk=case.amount_at_risk,
            margin=economics.margin,
            channel_cost_inr=channel_cost,
            goodwill_cost_inr=Decimal("0"),
        )
        baseline_clears = baseline_ev >= economics.ev_floor_inr
        projected_clears = projected_ev >= ev_floor

        if baseline_clears:
            baseline_contact += 1
        if projected_clears:
            projected_contact += 1
        if projected_clears and not baseline_clears:
            newly_contactable += 1
        if baseline_clears and not projected_clears:
            newly_uneconomic += 1

        baseline_needs_approval = baseline_ev >= bundle.merchant.approval.value_threshold_inr
        projected_needs_approval = projected_ev >= approval_threshold
        if projected_needs_approval and not baseline_needs_approval:
            newly_needs_approval += 1
        if baseline_needs_approval and not projected_needs_approval:
            no_longer_needs_approval += 1

        was_under_original_cap = contacts_sent < bundle.regulatory.contact_fatigue.max_contacts
        now_over_projected_cap = contacts_sent >= max_contacts
        if now_over_projected_cap and was_under_original_cap:
            newly_over_cap += 1

    return WhatIfProjection(
        cases_considered=considered,
        baseline_would_contact=baseline_contact,
        projected_would_contact=projected_contact,
        newly_contactable=newly_contactable,
        newly_uneconomic=newly_uneconomic,
        newly_requires_approval=newly_needs_approval,
        no_longer_requires_approval=no_longer_needs_approval,
        newly_over_contact_cap=newly_over_cap,
    )


async def exception_queue(
    event_store: EventStore, *, merchant_id: str | None = None, sample_size: int = 300
) -> list[ExceptionQueueItem]:
    cases = await event_store.all_cases(merchant_id=merchant_id)
    items: list[ExceptionQueueItem] = []
    for case in cases[:sample_size]:
        events = await event_store.events_for(case.case_id)
        exception_events = [e for e in events if e.event_type == "case.exception"]
        if not exception_events:
            continue
        latest = exception_events[-1]
        reason = str(latest.payload.get("error") or latest.payload.get("reason") or "unspecified")
        items.append(
            ExceptionQueueItem(
                case_id=case.case_id,
                root_cause=case.root_cause,
                amount_at_risk=case.amount_at_risk,
                reason=reason,
                occurred_at=latest.occurred_at,
            )
        )
    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items
