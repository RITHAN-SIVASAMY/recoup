"""FR-14.5/14.6: the one Claude call behind grounded Q&A. Same guardrail
contract as `llm/client.py` and `llm/ptp.py` — PII-redact, call with a
latency budget, validate against the schema, retry once, degrade to `None`
on a second failure. This module only ever proposes an answer; whether its
citations are trustworthy is `audit/qa.py`'s job (it validates every citation
against the events actually retrieved before returning anything to a caller
— this function is not on the hook for that, deliberately, per the
authority table: the LLM answers "why did this happen?", code enforces
citations and refusal).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from anthropic import AsyncAnthropic

from recoup.domain.models import CaseEvent
from recoup.llm.redaction import redact_text
from recoup.llm.schemas import GroundedAnswer
from recoup.settings import get_settings

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "grounded_qa_system.v1.txt"
PROMPT_VERSION = "grounded_qa_system.v1"

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def prompt_hash() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()[:16]


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _format_event(event: CaseEvent) -> str:
    payload_summary = redact_text(json.dumps(event.payload, sort_keys=True, default=str))
    return (
        f"[event:{event.event_id}] {event.occurred_at.isoformat()} "
        f"{event.event_type} (actor={event.actor}) payload={payload_summary}"
    )


def _build_user_message(question: str, events: list[CaseEvent]) -> str:
    log_lines = "\n".join(_format_event(event) for event in events)
    return redact_text(f"Question: {question}\n\nLog entries:\n{log_lines}")


async def _call_once(
    client: AsyncAnthropic, question: str, events: list[CaseEvent], *, timeout_s: float
) -> GroundedAnswer:
    response = await asyncio.wait_for(
        client.messages.create(
            model=get_settings().anthropic_model_fast,
            max_tokens=500,
            system=_load_system_prompt(),
            messages=[{"role": "user", "content": _build_user_message(question, events)}],
        ),
        timeout=timeout_s,
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    raw = "".join(text_blocks).strip()
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        raise ValueError(f"no JSON object in model output: {raw!r}")
    return GroundedAnswer.model_validate(json.loads(match.group(0)))


async def answer_grounded_question(
    question: str, events: list[CaseEvent], *, timeout_s: float = 8.0
) -> GroundedAnswer | None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None  # no key configured; degrade immediately, no wasted network attempt

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    for _attempt in range(2):  # one retry on invalid/timeout, per the guardrail contract
        try:
            return await _call_once(client, question, events, timeout_s=timeout_s)
        except Exception:  # any provider/schema failure degrades, per the LLM guardrail contract
            continue
    return None


__all__ = ["PROMPT_VERSION", "answer_grounded_question", "prompt_hash"]
