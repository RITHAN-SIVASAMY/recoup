"""FR-4.1: the per-action cost model. Pure — no I/O, callable with no event loop.

`channel_cost` prices what it costs to *attempt* a candidate action; `retry_charge`
and `stop` carry no per-message cost, matching the FRD's list (SMS, WhatsApp
template, email, voice minute) which is contact-channel costs only.
`human_review_cost_inr` is priced separately (FR-7.5's decision card) rather than
folded into `EV`, since whether an action needs review is a policy-layer verdict
that Economics (which runs before Policy in the pipeline, see 03-ARCHITECTURE.md
§3) does not yet know.
"""

from __future__ import annotations

from decimal import Decimal

from recoup.domain.models import ActionType, Channel
from recoup.policy.schema import MerchantEconomics


def channel_cost(
    action_type: ActionType, channel: Channel | None, economics: MerchantEconomics
) -> Decimal:
    if channel is None:
        return Decimal("0")
    return economics.channel_costs_inr.get(channel, Decimal("0"))


def human_review_cost(economics: MerchantEconomics) -> Decimal:
    return economics.human_review_cost_inr
