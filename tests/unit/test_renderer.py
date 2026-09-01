"""FR-9.5/REG-COMM-05: the template contract always holds — sender identity,
opt-out affordance, length cap and CON-01 safety — regardless of whether the
LLM drafted the body or the deterministic fallback did.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from recoup.domain.models import Case
from recoup.execution.renderer import render_message
from recoup.execution.templates import TemplateLoader
from recoup.llm.schemas import DraftedCopy, MessageBrief

pytestmark = pytest.mark.unit

_TEMPLATES = TemplateLoader().load()
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def _case(**overrides: object) -> Case:
    defaults: dict[str, object] = {
        "case_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "merchant_id": "demo",
        "source_type": "payment_failure",
        "provider_event_id": "prov-1",
        "amount_at_risk": Decimal("499.00"),
        "customer_ref": "cust_test",
        "resolution_state": "pending",
        "cohort": "treatment",
        "root_cause": "insufficient_funds",
        "created_at": _NOW,
        "updated_at": _NOW,
        "seq": 1,
        "tip_hash": "h" * 64,
    }
    defaults.update(overrides)
    return Case(**defaults)  # type: ignore[arg-type]


async def test_uses_the_llm_drafted_body_when_available_and_safe() -> None:
    async def _drafter(brief: MessageBrief) -> DraftedCopy:
        return DraftedCopy(body="Hi, your payment needs attention. {{recovery_link}}")

    message, drafted_by_llm = await render_message(
        case=_case(),
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        merchant_name="Acme",
        templates=_TEMPLATES,
        drafter=_drafter,
    )

    assert drafted_by_llm is True
    assert "[recovery link]" in message.body
    assert message.sender_identity == "Acme via Recoup"
    assert message.opt_out_affordance == "Reply STOP to opt out."
    assert message.category == "transactional"


async def test_falls_back_to_the_deterministic_body_when_the_llm_is_unavailable() -> None:
    async def _drafter(brief: MessageBrief) -> None:
        return None

    message, drafted_by_llm = await render_message(
        case=_case(),
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        merchant_name="Acme",
        templates=_TEMPLATES,
        drafter=_drafter,
    )

    assert drafted_by_llm is False
    assert "499.00" in message.body
    assert message.sender_identity == "Acme via Recoup"


async def test_falls_back_when_the_drafted_body_fails_the_safety_check() -> None:
    async def _unsafe_drafter(brief: MessageBrief) -> DraftedCopy:
        return DraftedCopy(body="Pay now or face legal action. {{recovery_link}}")

    message, drafted_by_llm = await render_message(
        case=_case(),
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        merchant_name="Acme",
        templates=_TEMPLATES,
        drafter=_unsafe_drafter,
    )

    assert drafted_by_llm is False
    assert "legal action" not in message.body


async def test_the_body_is_never_longer_than_the_templates_cap() -> None:
    async def _long_drafter(brief: MessageBrief) -> DraftedCopy:
        return DraftedCopy(body="x" * 400)

    message, _ = await render_message(
        case=_case(),
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        merchant_name="Acme",
        templates=_TEMPLATES,
        drafter=_long_drafter,
    )

    template = _TEMPLATES.templates["send_message"]
    assert len(message.body) <= template.max_length
