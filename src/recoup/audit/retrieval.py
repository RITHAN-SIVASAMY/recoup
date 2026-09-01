"""ADR-0005: Postgres full-text search + structured filters, not a vector
database. Retrieval is deterministic and explainable — the same question
against the same event log always retrieves the same events in the same
order, and the filter that produced them is part of the result, not hidden
inside an embedding.

Query expansion over the event-type vocabulary (ADR-0005's own mitigation
for FTS's weakness on paraphrase) is `expand_query_to_event_types`: a
question mentioning "called" or "contacted" narrows the search toward
`voice.*`/`action.*` events even if the exact word never appears in any
payload.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.schema import CaseEventRow, event_row_to_domain
from recoup.domain.models import CaseEvent

# question keyword -> event types it should narrow the search toward. Not
# exhaustive by design — an unmatched question just falls back to plain FTS
# over the case's full history, which is still a real, explainable filter.
_EVENT_TYPE_SYNONYMS: dict[str, frozenset[str]] = {
    "contact": frozenset(
        {"action.sent", "action.delivered", "action.engaged", "voice.call_started"}
    ),
    "contacted": frozenset(
        {"action.sent", "action.delivered", "action.engaged", "voice.call_started"}
    ),
    "message": frozenset({"action.sent", "action.delivered", "action.engaged"}),
    "messaged": frozenset({"action.sent", "action.delivered", "action.engaged"}),
    "sms": frozenset({"action.sent", "action.delivered", "action.engaged"}),
    "whatsapp": frozenset({"action.sent", "action.delivered", "action.engaged"}),
    "email": frozenset({"action.sent", "action.delivered", "action.engaged"}),
    "call": frozenset({"voice.call_started", "voice.turn", "voice.call_ended"}),
    "called": frozenset({"voice.call_started", "voice.turn", "voice.call_ended"}),
    "phone": frozenset({"voice.call_started", "voice.turn", "voice.call_ended"}),
    "pay": frozenset({"payment.recovered"}),
    "paid": frozenset({"payment.recovered"}),
    "payment": frozenset({"payment.recovered", "ev.computed"}),
    "promise": frozenset({"ptp.captured", "ptp.kept", "ptp.partial", "ptp.broken"}),
    "promised": frozenset({"ptp.captured", "ptp.kept", "ptp.partial", "ptp.broken"}),
    "denied": frozenset({"policy.denied"}),
    "blocked": frozenset({"policy.denied"}),
    "rejected": frozenset({"policy.denied", "approval.rejected"}),
    "approved": frozenset({"approval.granted"}),
    "approval": frozenset({"approval.requested", "approval.granted", "approval.rejected"}),
    "cancelled": frozenset({"action.cancelled"}),
    "canceled": frozenset({"action.cancelled"}),
    "opt-out": frozenset({"customer.opted_out"}),
    "opted": frozenset({"customer.opted_out"}),
    "unsubscribe": frozenset({"customer.opted_out"}),
    "abandoned": frozenset({"case.abandoned_uneconomic"}),
    "expensive": frozenset({"ev.computed", "case.abandoned_uneconomic"}),
    "cost": frozenset({"ev.computed"}),
    "classified": frozenset({"case.classified"}),
    "reason": frozenset({"case.classified"}),
    "cause": frozenset({"case.classified"}),
    "reminder": frozenset({"case.remind_later"}),
    "link": frozenset({"link.viewed", "link.method_switched"}),
    "viewed": frozenset({"link.viewed"}),
    "exception": frozenset({"case.exception"}),
    "escalated": frozenset({"case.exception"}),
}


def expand_query_to_event_types(question: str) -> frozenset[str]:
    lowered = question.lower()
    matched: set[str] = set()
    for keyword, event_types in _EVENT_TYPE_SYNONYMS.items():
        if keyword in lowered:
            matched.update(event_types)
    return frozenset(matched)


@dataclass(frozen=True)
class RetrievalFilter:
    case_id: str | None = None
    event_types: frozenset[str] | None = None
    since: datetime | None = None
    until: datetime | None = None
    query_text: str | None = None


@dataclass(frozen=True)
class RetrievalResult:
    events: Sequence[CaseEvent]
    filter_used: RetrievalFilter


async def retrieve(
    engine: AsyncEngine, filt: RetrievalFilter, *, limit: int = 25
) -> RetrievalResult:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    stmt = select(CaseEventRow)

    if filt.case_id is not None:
        stmt = stmt.where(CaseEventRow.case_id == filt.case_id)
    if filt.event_types:
        stmt = stmt.where(CaseEventRow.event_type.in_(filt.event_types))
    if filt.since is not None:
        stmt = stmt.where(CaseEventRow.occurred_at >= filt.since)
    if filt.until is not None:
        stmt = stmt.where(CaseEventRow.occurred_at <= filt.until)

    if filt.query_text:
        document = func.to_tsvector(
            "english", cast(CaseEventRow.payload, Text) + " " + CaseEventRow.event_type
        )
        tsquery = func.plainto_tsquery("english", filt.query_text)
        stmt = stmt.where(document.op("@@")(tsquery))
        stmt = stmt.order_by(func.ts_rank(document, tsquery).desc(), CaseEventRow.seq)
    else:
        stmt = stmt.order_by(CaseEventRow.seq)

    stmt = stmt.limit(limit)

    async with sessionmaker() as session:
        rows = (await session.scalars(stmt)).all()

    return RetrievalResult(events=[event_row_to_domain(row) for row in rows], filter_used=filt)
