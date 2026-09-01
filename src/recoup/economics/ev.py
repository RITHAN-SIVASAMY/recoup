"""FR-4.2/4.3: expected value and the EV gate.

`expected_value` is the pure arithmetic (`docs/01-FRD.md` FR-4.2, exactly):
`EV = uplift * amount_at_risk * margin - channel_cost - goodwill_cost(contact_n)`.

`price_ladder_step` is the one I/O-touching orchestrator: for every channel
the case's current ladder step permits, it prices a candidate and writes an
`ev.computed` event with the full inputs (economics/ev.py owns this per
context/phase-05-economics-and-authority.md's own checklist — unlike
`policy/evaluate()`, Economics is not import-linter-restricted to `domain`
only). `select_action_or_abandon` (Phase 05's original entry point) picks the
highest-EV candidate from it and abandons if nothing clears the floor;
`price_ladder_step` is also called directly by Phase 06's dispatcher, which
needs the *full* priced candidate list so its bandit can choose among every
EV-cleared, policy-permitted arm rather than only the single EV-argmax one
(FR-9.2) — both paths write each `ev.computed` event exactly once, since
pricing only ever happens inside this one function.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from recoup.audit.event_store import EventStore
from recoup.domain.models import Actor, Case, Channel, ProposedAction
from recoup.economics.costs import channel_cost
from recoup.economics.goodwill import goodwill_cost
from recoup.policy.schema import Ladder, MerchantEconomics

_SYSTEM = Actor(kind="system", identifier="economics-engine")


def expected_value(
    *,
    uplift: Decimal,
    amount_at_risk: Decimal,
    margin: Decimal,
    channel_cost_inr: Decimal,
    goodwill_cost_inr: Decimal,
) -> Decimal:
    return (uplift * amount_at_risk * margin) - channel_cost_inr - goodwill_cost_inr


@dataclass(frozen=True)
class PricedCandidate:
    action: ProposedAction
    ev_inr: Decimal
    channel_cost_inr: Decimal
    goodwill_cost_inr: Decimal


def _build_candidates(
    case: Case, ladder: Ladder, ladder_step_reached: int, now: datetime
) -> list[ProposedAction]:
    step_index = ladder_step_reached
    if step_index < 0 or step_index >= len(ladder.steps):
        return []
    step = ladder.steps[step_index]
    scheduled_for = now + step.wait_before
    channels: list[Channel | None] = list(step.channels) if step.channels else [None]
    return [
        ProposedAction(
            action_type=step.action,
            channel=channel,
            ladder_step=step_index + 1,
            scheduled_for=scheduled_for,
            estimated_cost_inr=Decimal("0"),
            expected_value_inr=Decimal("0"),
        )
        for channel in channels
    ]


async def price_ladder_step(
    event_store: EventStore,
    *,
    case: Case,
    ladder: Ladder,
    ladder_step_reached: int,
    uplift: Decimal,
    relationship_weight: float,
    contacts_sent: int,
    economics: MerchantEconomics,
    policy_version: str,
    now: datetime,
) -> list[PricedCandidate]:
    bare_candidates = _build_candidates(case, ladder, ladder_step_reached, now)
    priced: list[PricedCandidate] = []
    for candidate in bare_candidates:
        cost = channel_cost(candidate.action_type, candidate.channel, economics)
        goodwill = (
            goodwill_cost(contacts_sent, economics.goodwill, relationship_weight)
            if candidate.channel is not None
            else Decimal("0")
        )
        ev = expected_value(
            uplift=uplift,
            amount_at_risk=case.amount_at_risk,
            margin=economics.margin,
            channel_cost_inr=cost,
            goodwill_cost_inr=goodwill,
        )
        priced.append(
            PricedCandidate(
                action=candidate.model_copy(
                    update={"estimated_cost_inr": cost, "expected_value_inr": ev}
                ),
                ev_inr=ev,
                channel_cost_inr=cost,
                goodwill_cost_inr=goodwill,
            )
        )
        await event_store.append(
            case_id=case.case_id,
            event_type="ev.computed",
            payload={
                "action_type": candidate.action_type,
                "channel": candidate.channel,
                "ladder_step": candidate.ladder_step,
                "uplift": uplift,
                "amount_at_risk": case.amount_at_risk,
                "margin": economics.margin,
                "channel_cost_inr": cost,
                "goodwill_cost_inr": goodwill,
                "ev_inr": ev,
            },
            actor=_SYSTEM,
            policy_version=policy_version,
        )
    return priced


async def abandon_if_uneconomic(
    event_store: EventStore,
    case: Case,
    priced: list[PricedCandidate],
    economics: MerchantEconomics,
    policy_version: str,
) -> bool:
    """Writes `case.abandoned_uneconomic` with the full ledger and returns
    True iff every priced candidate is below the EV floor (or there were none
    at all — an exhausted ladder proposes nothing and abandons nothing; see
    the caller, which only reaches here with a non-empty `priced`)."""
    if not priced or max(c.ev_inr for c in priced) >= economics.ev_floor_inr:
        return False
    await event_store.append(
        case_id=case.case_id,
        event_type="case.abandoned_uneconomic",
        payload={
            "ev_floor_inr": economics.ev_floor_inr,
            "ledger": [
                {
                    "action_type": c.action.action_type,
                    "channel": c.action.channel,
                    "ev_inr": c.ev_inr,
                    "channel_cost_inr": c.channel_cost_inr,
                    "goodwill_cost_inr": c.goodwill_cost_inr,
                }
                for c in priced
            ],
        },
        actor=_SYSTEM,
        policy_version=policy_version,
    )
    return True


async def select_action_or_abandon(
    event_store: EventStore,
    *,
    case: Case,
    ladder: Ladder,
    ladder_step_reached: int,
    uplift: Decimal,
    relationship_weight: float,
    contacts_sent: int,
    economics: MerchantEconomics,
    policy_version: str,
    now: datetime,
) -> ProposedAction | None:
    priced = await price_ladder_step(
        event_store,
        case=case,
        ladder=ladder,
        ladder_step_reached=ladder_step_reached,
        uplift=uplift,
        relationship_weight=relationship_weight,
        contacts_sent=contacts_sent,
        economics=economics,
        policy_version=policy_version,
        now=now,
    )
    if not priced:
        return None
    if await abandon_if_uneconomic(event_store, case, priced, economics, policy_version):
        return None
    return max(priced, key=lambda c: c.ev_inr).action
