"""FR-8.1: LTV, relationship risk, and trust score.

Explicitly a documented heuristic, not a trained model — CLAUDE.md rule 7 and the
uplift ADR's fallback clause both say the same thing: never present a heuristic as
a model. FR-8.1's real inputs (historical order value, tenure, payment reliability,
support history, contract size, renewal proximity) all require repeat-customer
history this synthetic batch does not have — every `customer_ref` here is unique.
`relationship_weight` stands in as a crude, honest proxy (relative deal size)
until real customer history exists to train something better; `trust_score`
defaults to a neutral prior because promise-to-pay tracking (FR-11, Phase 08)
doesn't exist yet to have earned or lost any trust.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from recoup.understanding.features import relative_amount

_B2B_MERCHANT_ID = "demo-b2b"
_B2B_WEIGHT_BONUS = 0.15
NEUTRAL_TRUST_SCORE = 0.5


@dataclass(frozen=True)
class RelationshipScore:
    relationship_weight: float  # 0..1, higher = more generous/patient treatment
    trust_score: float  # 0..1, promise-keeping reliability; neutral until observed
    heuristic: bool = True  # always True in this build — see module docstring


def score_relationship(*, merchant_id: str, amount_at_risk: Decimal | float) -> RelationshipScore:
    weight = relative_amount(merchant_id, float(amount_at_risk))
    if merchant_id == _B2B_MERCHANT_ID:
        weight = min(1.0, weight + _B2B_WEIGHT_BONUS)
    return RelationshipScore(relationship_weight=weight, trust_score=NEUTRAL_TRUST_SCORE)
