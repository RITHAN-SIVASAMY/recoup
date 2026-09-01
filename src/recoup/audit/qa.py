"""FR-14.5/14.6/CON-04: grounded Q&A over the audit log. `ask()` is the one
place an answer is allowed to reach a caller, and it enforces both halves of
the contract no LLM call is trusted to enforce on its own:

1. Every citation in the answer must reference an event that was actually
   retrieved and shown to the model — not merely a real event ID somewhere
   in the database, and not merely present in one of the two fields
   (`answer`'s inline `[event:...]` markers and the structured `citations`
   list must agree exactly). Any mismatch is treated as a hallucination,
   never a partial answer.
2. If retrieval finds nothing for the case at all, or the model is
   unavailable or fails twice, the caller gets a deterministic, ungrounded
   answer: a plain structured summary of whatever *was* retrieved, or an
   explicit refusal naming what's missing — never silence, never a guess.

The "old answer explains with the prompt that produced it" property (this
phase's own wording) is `QAAnswer.prompt_version`/`prompt_hash` — the
answer object's own provenance, not a permanent case event; asking a
question doesn't change case state, so it doesn't belong in the event log
the way `link.viewed` (a customer's own action) does.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from recoup.audit.retrieval import RetrievalFilter, expand_query_to_event_types, retrieve
from recoup.domain.ids import Ulid
from recoup.domain.models import CaseEvent
from recoup.llm.qa import PROMPT_VERSION, answer_grounded_question, prompt_hash
from recoup.llm.schemas import GroundedAnswer

Drafter = Callable[[str, list[CaseEvent]], Awaitable[GroundedAnswer | None]]

_CITATION_RE = re.compile(r"\[event:([0-7][0-9A-HJKMNP-TV-Z]{25})\]")


@dataclass(frozen=True)
class QAAnswer:
    answer: str
    citations: tuple[str, ...]
    refused: bool
    refusal_reason: str | None
    degraded_mode: bool
    prompt_version: str
    prompt_hash: str
    retrieved_event_ids: tuple[str, ...]


def _extract_inline_citations(answer_text: str) -> set[str]:
    return set(_CITATION_RE.findall(answer_text))


def citations_are_valid(declared: set[str], inline: set[str], valid_ids: set[str]) -> bool:
    """The hallucination guard: the model's two citation surfaces must agree
    exactly with each other, and every citation must be an event ID that was
    actually retrieved and shown to the model — never merely a real ID
    somewhere in the database."""
    return bool(declared) and declared == inline and declared.issubset(valid_ids)


def _summary_line(event: CaseEvent) -> str:
    return f"[event:{event.event_id}] {event.occurred_at.isoformat()} — {event.event_type}"


def _deterministic_summary(
    events: list[CaseEvent], *, refused: bool, refusal_reason: str | None
) -> QAAnswer:
    if not events:
        return QAAnswer(
            answer="",
            citations=(),
            refused=True,
            refusal_reason=refusal_reason or "no events are logged for this case",
            degraded_mode=False,
            prompt_version=PROMPT_VERSION,
            prompt_hash=prompt_hash(),
            retrieved_event_ids=(),
        )
    lines = [_summary_line(event) for event in events]
    answer = "The model was unavailable; here is the raw retrieved log instead:\n" + "\n".join(
        lines
    )
    return QAAnswer(
        answer=answer,
        citations=tuple(event.event_id for event in events),
        refused=refused,
        refusal_reason=refusal_reason,
        degraded_mode=True,
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash(),
        retrieved_event_ids=tuple(event.event_id for event in events),
    )


async def ask(
    engine: AsyncEngine,
    *,
    case_id: Ulid,
    question: str,
    now: datetime,
    drafter: Drafter = answer_grounded_question,
) -> QAAnswer:
    event_types = expand_query_to_event_types(question)

    result = await retrieve(
        engine,
        RetrievalFilter(case_id=case_id, event_types=event_types or None, query_text=question),
    )
    if not result.events and event_types:
        result = await retrieve(engine, RetrievalFilter(case_id=case_id, query_text=question))
    if not result.events:
        result = await retrieve(engine, RetrievalFilter(case_id=case_id))

    events = list(result.events)
    if not events:
        return _deterministic_summary(
            [], refused=True, refusal_reason=f"No events at all are logged for case {case_id}."
        )

    raw = await drafter(question, events)
    if raw is None:
        return _deterministic_summary(events, refused=False, refusal_reason=None)

    if raw.refused:
        if raw.citations or _extract_inline_citations(raw.answer):
            # a refusal that still cites something is self-contradictory —
            # treat it as untrustworthy output, same as a hallucination.
            return _deterministic_summary(events, refused=False, refusal_reason=None)
        return QAAnswer(
            answer="",
            citations=(),
            refused=True,
            refusal_reason=raw.refusal_reason or "the log does not contain enough to answer this",
            degraded_mode=False,
            prompt_version=PROMPT_VERSION,
            prompt_hash=prompt_hash(),
            retrieved_event_ids=tuple(event.event_id for event in events),
        )

    valid_ids = {event.event_id for event in events}
    declared = set(raw.citations)
    inline = _extract_inline_citations(raw.answer)
    if not citations_are_valid(declared, inline, valid_ids):
        return _deterministic_summary(events, refused=False, refusal_reason=None)

    return QAAnswer(
        answer=raw.answer,
        citations=tuple(sorted(declared)),
        refused=False,
        refusal_reason=None,
        degraded_mode=False,
        prompt_version=PROMPT_VERSION,
        prompt_hash=prompt_hash(),
        retrieved_event_ids=tuple(event.event_id for event in events),
    )
