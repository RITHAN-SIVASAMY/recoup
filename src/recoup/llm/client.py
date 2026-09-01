"""The one Claude call in the recovery-message path (FR-9.5). Follows
`context/shared/03-guardrails.md`'s LLM contract exactly: PII-redact -> call
with a latency budget -> validate against the schema -> on invalid or
timeout, retry once -> on second failure, return `None` so the caller falls
back to the deterministic template body and records `degraded_mode`.

The LLM never decides or executes anything here — it drafts body text into
a template's variable slot; `execution/renderer.py` still runs the template
contract (sender identity, opt-out affordance, length cap) and
`llm/safety/prohibited_claims.py` on the result before anything is sent.
"""

from __future__ import annotations

import asyncio

from anthropic import AsyncAnthropic

from recoup.llm.redaction import redact_text
from recoup.llm.schemas import DraftedCopy, MessageBrief
from recoup.settings import get_settings

_SYSTEM_PROMPT = (
    "You draft a single short SMS/WhatsApp/email body for a payment-recovery "
    "reminder. Output ONLY the message body text, nothing else — no preamble, "
    "no quotes, no markdown. Be polite, factual, and brief (under 400 "
    "characters). Never mention legal action, credit scores, deadlines phrased "
    "as threats, or any third party (family, employer). Never invent an amount, "
    "date, or fact not given to you. Use the placeholder {{recovery_link}} "
    "exactly where a link to fix the payment should go — do not invent a URL."
)


def _build_prompt(brief: MessageBrief) -> str:
    raw = (
        f"Merchant: {brief.merchant_name}\n"
        f"Action: {brief.action_type} over {brief.channel}\n"
        f"Reason payment is at risk: {brief.root_cause or 'unknown'}\n"
        f"Amount at risk: INR {brief.amount_at_risk}\n"
        f"This is contact attempt number {brief.ladder_step} for this issue."
    )
    return redact_text(raw)


async def _call_once(
    client: AsyncAnthropic, brief: MessageBrief, *, timeout_s: float
) -> DraftedCopy:
    response = await asyncio.wait_for(
        client.messages.create(
            model=get_settings().anthropic_model_fast,
            max_tokens=200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(brief)}],
        ),
        timeout=timeout_s,
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    body = "".join(text_blocks).strip()
    return DraftedCopy(body=body)


async def draft_message(brief: MessageBrief, *, timeout_s: float = 8.0) -> DraftedCopy | None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None  # no key configured; degrade immediately, no wasted network attempt

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    for _attempt in range(2):  # one retry on invalid/timeout, per the guardrail contract
        try:
            return await _call_once(client, brief, timeout_s=timeout_s)
        except Exception:  # any provider/schema failure degrades, per the LLM guardrail contract
            continue
    return None
