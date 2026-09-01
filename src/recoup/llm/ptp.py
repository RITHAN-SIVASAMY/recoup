"""FR-11.1: promise-to-pay extraction. Same guardrail contract as
`llm/client.py` — PII-redact, call with a latency budget, validate against
the schema, retry once, degrade to `None` on a second failure — but this
call returns the *raw* extraction (`PTPExtraction.has_commitment` and
`.confidence`) rather than deciding anything; whether a low-confidence
extraction becomes a real `PromiseToPay` or routes to a human is
`voice/runtime.py`'s call, per the authority table (LLM extracts, code
thresholds and gates — never the reverse).
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime

from anthropic import AsyncAnthropic

from recoup.llm.redaction import redact_text
from recoup.llm.schemas import PTPExtraction
from recoup.settings import get_settings

_SYSTEM_PROMPT_TEMPLATE = (
    "Today's date is {today}. You extract a structured promise-to-pay from a "
    "customer's own words in a payment-recovery conversation. Resolve any "
    'relative date ("kal"/tomorrow, "agle hafte"/next week, "Friday ko") '
    "against today's date. Output ONLY a single JSON object, nothing else — "
    "no markdown, no preamble. Schema: "
    '{{"has_commitment": bool, "amount_inr": number|null, "promised_date": '
    '"YYYY-MM-DD"|null, "condition": string|null, "confidence": number 0-1}}. '
    "has_commitment is false if the customer did not actually commit to a date "
    "or amount (vague reassurance, a refusal, or a question is NOT a commitment). "
    "confidence must be low (<0.5) if the date or amount is ambiguous, relative "
    'and hard to resolve (e.g. "soon", "in a few days"), or contradictory. '
    "Never invent a date or amount that was not stated or clearly implied."
)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _build_prompt(transcript: str) -> str:
    return redact_text(f"Conversation transcript:\n{transcript}")


async def _call_once(
    client: AsyncAnthropic, transcript: str, *, now: datetime, timeout_s: float
) -> PTPExtraction:
    response = await asyncio.wait_for(
        client.messages.create(
            model=get_settings().anthropic_model_fast,
            max_tokens=200,
            system=_SYSTEM_PROMPT_TEMPLATE.format(today=now.date().isoformat()),
            messages=[{"role": "user", "content": _build_prompt(transcript)}],
        ),
        timeout=timeout_s,
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    raw = "".join(text_blocks).strip()
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        raise ValueError(f"no JSON object in model output: {raw!r}")
    return PTPExtraction.model_validate(json.loads(match.group(0)))


async def extract_ptp(
    transcript: str, now: datetime, *, timeout_s: float = 8.0
) -> PTPExtraction | None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None  # no key configured; degrade immediately, no wasted network attempt

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    for _attempt in range(2):  # one retry on invalid/timeout, per the guardrail contract
        try:
            return await _call_once(client, transcript, now=now, timeout_s=timeout_s)
        except Exception:  # any provider/schema failure degrades, per the LLM guardrail contract
            continue
    return None
