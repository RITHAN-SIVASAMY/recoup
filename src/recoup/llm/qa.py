"""FR-14.5/14.6: the one Groq call behind grounded Q&A. Same guardrail
contract as `llm/client.py` and `llm/ptp.py` — PII-redact, call with a
latency budget, validate against the schema, retry once, degrade to `None`
on a second failure. This module only ever proposes an answer; whether its
citations are trustworthy is `audit/qa.py`'s job (it validates every citation
against the events actually retrieved before returning anything to a caller
— this function is not on the hook for that, deliberately, per the
authority table: the LLM answers "why did this happen?", code enforces
citations and refusal).

Provider: Groq's OpenAI-compatible chat completions endpoint, not Anthropic
— see docs/adr/0009-groq-grounded-qa.md. `audit/qa.py`'s citation/refusal
enforcement is provider-agnostic by construction (the `Drafter` callable
type), so this is the only module this swap touches.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx

from recoup.domain.models import CaseEvent
from recoup.llm.redaction import redact_text
from recoup.llm.schemas import GroundedAnswer
from recoup.settings import get_settings

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "grounded_qa_system.v1.txt"
PROMPT_VERSION = "grounded_qa_system.v1"

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
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
    client: httpx.AsyncClient,
    api_key: str,
    question: str,
    events: list[CaseEvent],
    *,
    timeout_s: float,
) -> GroundedAnswer:
    response = await client.post(
        _GROQ_CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": get_settings().groq_model,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _load_system_prompt()},
                {"role": "user", "content": _build_user_message(question, events)},
            ],
        },
        timeout=timeout_s,
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"].strip()
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        raise ValueError(f"no JSON object in model output: {raw!r}")
    data = json.loads(match.group(0))
    # audit/qa.py requires the structured `citations` list to match the bare
    # event IDs inside the answer's own [event:...] markers, exactly -- some
    # Groq-hosted models echo citations pre-wrapped as "event:<id>" instead
    # of the bare id, which would otherwise make every correct answer look
    # like a hallucination and silently degrade it.
    if isinstance(data.get("citations"), list):
        data["citations"] = [
            c.removeprefix("event:").strip("[]") if isinstance(c, str) else c
            for c in data["citations"]
        ]
    return GroundedAnswer.model_validate(data)


async def answer_grounded_question(
    question: str, events: list[CaseEvent], *, timeout_s: float = 8.0
) -> GroundedAnswer | None:
    settings = get_settings()
    if not settings.groq_api_key:
        return None  # no key configured; degrade immediately, no wasted network attempt

    async with httpx.AsyncClient() as client:
        for _attempt in range(2):  # one retry on invalid/timeout, per the guardrail contract
            try:
                return await _call_once(
                    client, settings.groq_api_key, question, events, timeout_s=timeout_s
                )
            except Exception:  # any provider/schema failure degrades, per the guardrail contract
                continue
    return None


__all__ = ["PROMPT_VERSION", "answer_grounded_question", "prompt_hash"]
