"""Pydantic schemas at the LLM boundary (FR-9.5). `MessageBrief` is the only
case information that ever reaches a prompt — deliberately narrow: no
`customer_ref`, no raw contact details, nothing `llm/redaction.py` would need
to catch. `DraftedCopy` is what a draft call must validate against before
`execution/renderer.py` will use it; anything else falls back to the
deterministic template body (guardrail: "on invalid or timeout ... fall back
to the deterministic path and set degraded_mode").
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from recoup.domain.models import ActionType, Channel


class MessageBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    merchant_name: str
    action_type: ActionType
    channel: Channel
    root_cause: str | None
    amount_at_risk: Decimal
    ladder_step: int


class DraftedCopy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    body: str = Field(min_length=1, max_length=480)
