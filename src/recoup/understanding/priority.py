"""FR-3.7: priority = uplift x amount_at_risk x urgency_decay x relationship_weight.

`urgency_decay` is an exponential decay on case age — a documented default (7-day
half-life), not a learned parameter: the longer a case has sat un-acted-on, the
less likely a customer still remembers or cares about the original failure, so an
older case should rank lower than an equally-valuable fresh one, all else equal.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal

URGENCY_HALF_LIFE_DAYS = 7.0


def urgency_decay(occurred_at: datetime, *, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    age_days = max((now - occurred_at).total_seconds() / 86_400, 0.0)
    return math.exp(-age_days / URGENCY_HALF_LIFE_DAYS)


def priority_score(
    *,
    uplift: float,
    amount_at_risk: Decimal | float,
    occurred_at: datetime,
    relationship_weight: float,
    now: datetime | None = None,
) -> float:
    return (
        uplift * float(amount_at_risk) * urgency_decay(occurred_at, now=now) * relationship_weight
    )
