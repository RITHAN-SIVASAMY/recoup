"""FR-11.3/11.4: promise-keeping follow-through and the trust score it
feeds. A kept promise makes Recoup more patient with that customer next
time; a broken one makes it less so (within policy bounds — this score
*informs* `understanding/relationship.py`'s aggressiveness input, it never
grants an exemption from any regulatory rule). Durable per customer_ref,
the same pattern `execution.optout.OptOutStore` already established: a
promise on one case should still matter on that customer's next case.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore
from recoup.domain.models import Actor
from recoup.understanding.relationship import NEUTRAL_TRUST_SCORE
from recoup.understanding.schema import TrustScoreRow

_EVENT_TYPE: dict[str, str] = {"kept": "ptp.kept", "partial": "ptp.partial", "broken": "ptp.broken"}

PtpOutcome = Literal["kept", "partial", "broken"]

_SCORE_FLOOR = 0.0
_SCORE_CEILING = 1.0
_OUTCOME_DELTA: dict[PtpOutcome, float] = {"kept": 0.15, "partial": -0.05, "broken": -0.25}


def _clamp(score: float) -> float:
    return max(_SCORE_FLOOR, min(_SCORE_CEILING, score))


DEFAULT_GRACE = timedelta(days=2)


def is_within_grace(
    promised_date: datetime, *, now: datetime, grace: timedelta = DEFAULT_GRACE
) -> bool:
    """FR-11.2: escalation stays suspended through `promised_date + grace`.
    A broken promise shortens next time's grace (FR-11.4) — callers with a
    real trust score should pass a narrower `grace` for a low-trust customer
    rather than always using the default."""
    return now <= promised_date + grace


class TrustScoreStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def score_for(self, customer_ref: str) -> float:
        async with self._sessionmaker() as session:
            row = await session.get(TrustScoreRow, customer_ref)
            return row.score if row is not None else NEUTRAL_TRUST_SCORE

    async def record_outcome(
        self, customer_ref: str, outcome: PtpOutcome, *, now: datetime
    ) -> float:
        async with self._sessionmaker() as session, session.begin():
            row = await session.get(TrustScoreRow, customer_ref)
            current = row.score if row is not None else NEUTRAL_TRUST_SCORE
            new_score = _clamp(current + _OUTCOME_DELTA[outcome])
            if row is None:
                session.add(
                    TrustScoreRow(customer_ref=customer_ref, score=new_score, updated_at=now)
                )
            else:
                row.score = new_score
                row.updated_at = now
            return new_score


async def record_ptp_outcome(
    event_store: EventStore,
    trust_store: TrustScoreStore,
    *,
    case_id: str,
    customer_ref: str,
    outcome: PtpOutcome,
    now: datetime,
) -> float:
    """Writes the FR-11.3 follow-through event and updates the FR-11.4 trust
    score in one call — the two are inseparable: an outcome that isn't
    scored isn't really "followed through" on."""
    new_score = await trust_store.record_outcome(customer_ref, outcome, now=now)
    await event_store.append(
        case_id=case_id,
        event_type=_EVENT_TYPE[outcome],
        payload={"customer_ref": customer_ref, "new_trust_score": new_score},
        actor=Actor(kind="system", identifier="ptp-follow-through"),
    )
    return new_score
