"""FR-9.5 / REG-COMM-05: turns a permitted `ProposedAction` into a
`RenderedMessage` that satisfies the template contract — sender identity and
an opt-out affordance are always present, length is always within the
template's cap, and the body always passes `llm/safety/prohibited_claims.py`
— regardless of whether Claude drafted the body or the deterministic
fallback did. The LLM never sees this case's PII (`llm/schemas.MessageBrief`
carries no contact details) and never decides whether to send anything; it
only proposes text for one variable slot.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from recoup.domain.models import ActionType, Case, Channel
from recoup.execution.ports import RenderedMessage
from recoup.execution.templates import MessageTemplate, TemplateSet, template_for
from recoup.llm.client import draft_message
from recoup.llm.safety.prohibited_claims import check_message_safety
from recoup.llm.schemas import DraftedCopy, MessageBrief

Drafter = Callable[[MessageBrief], Awaitable[DraftedCopy | None]]

_RECOVERY_LINK_PLACEHOLDER = "{{recovery_link}}"
_RECOVERY_LINK_STUB = "[recovery link]"  # real signed links land in Phase 07


def _fallback_body(action_type: ActionType, amount_at_risk: Decimal) -> str:
    return (
        f"We noticed an issue with a payment of INR {amount_at_risk}. "
        f"Please use the link below to resolve it. {_RECOVERY_LINK_PLACEHOLDER}"
    )


def _fill_and_cap(body: str, template: MessageTemplate) -> str:
    filled = body.replace(_RECOVERY_LINK_PLACEHOLDER, _RECOVERY_LINK_STUB)
    if len(filled) > template.max_length:
        filled = filled[: template.max_length - 1].rstrip() + "…"
    return filled


async def render_message(
    *,
    case: Case,
    action_type: ActionType,
    channel: Channel,
    ladder_step: int,
    merchant_name: str,
    templates: TemplateSet,
    drafter: Drafter = draft_message,
) -> tuple[RenderedMessage, bool]:
    """Returns `(message, drafted_by_llm)` — the second value is what a caller
    records as `degraded_mode` when it's `False`."""
    template = template_for(action_type, templates)
    brief = MessageBrief(
        merchant_name=merchant_name,
        action_type=action_type,
        channel=channel,
        root_cause=case.root_cause,
        amount_at_risk=case.amount_at_risk,
        ladder_step=ladder_step,
    )

    drafted = await drafter(brief)
    drafted_by_llm = drafted is not None
    body = drafted.body if drafted is not None else _fallback_body(action_type, case.amount_at_risk)

    if check_message_safety(body):
        # A safety violation is never "sent anyway, flagged" — it is treated
        # exactly like an unavailable model: fall back to the safe default.
        body = _fallback_body(action_type, case.amount_at_risk)
        drafted_by_llm = False

    message = RenderedMessage(
        channel=channel,
        body=_fill_and_cap(body, template),
        sender_identity=template.sender_identity.format(merchant_name=merchant_name),
        opt_out_affordance=template.opt_out_affordance,
        category=template.category,
    )
    return message, drafted_by_llm
