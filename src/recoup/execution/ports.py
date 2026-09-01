"""FR-9.6: the channel interface every adapter — simulator or live — implements.

`ChannelPort` is deliberately the only surface `execution/dispatcher.py` is
allowed to call to make something happen outside this process; a live Twilio/
WhatsApp/Resend adapter (Phase 06's cut line — optional) is a drop-in second
implementation of this same protocol, never a special case in the dispatcher.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from recoup.domain.models import Channel

DeliveryStatus = Literal["delivered", "bounced", "failed"]


class RenderedMessage(BaseModel):
    """The template contract's output (REG-COMM-05): sender identity and an
    opt-out affordance are always present, enforced by `execution/renderer.py`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    body: str
    sender_identity: str
    opt_out_affordance: str
    category: str


class DeliveryReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DeliveryStatus
    engaged: bool = False
    converted: bool = False
    sent_at: datetime
    latency_ms: int
    provider_ref: str


class SendContext(BaseModel):
    """Case features a deterministic simulator needs for realistic per-segment
    response curves (FR-9.6) — irrelevant to a live provider, which is free to
    ignore it; not part of the message itself, so it never reaches the wire."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    uplift_segment: str | None = None


class ChannelPort(Protocol):
    async def send(
        self, message: RenderedMessage, idempotency_key: str, context: SendContext
    ) -> DeliveryReceipt: ...
