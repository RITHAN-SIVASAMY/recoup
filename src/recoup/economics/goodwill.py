"""FR-4.1/FR-8: the goodwill cost curve — rising with contact count, and higher
for higher-relationship (higher-LTV proxy) customers. Pure — no I/O.
"""

from __future__ import annotations

from decimal import Decimal

from recoup.policy.schema import GoodwillCurve

_TWO_DP = Decimal("0.01")


def goodwill_cost(contacts_sent: int, curve: GoodwillCurve, relationship_weight: float) -> Decimal:
    """`contacts_sent` is the count *before* this one (0 for the first contact).

    `relationship_weight` (from `understanding.relationship.score_relationship`,
    0..1) scales the curve 0.5x-1.5x: a five-year loyal customer costs more
    goodwill to over-contact than a stranger, matching FR-8's relationship-aware
    prioritization.
    """
    if contacts_sent < 0:
        raise ValueError(f"contacts_sent must be >= 0, got {contacts_sent}")
    if not 0.0 <= relationship_weight <= 1.0:
        raise ValueError(f"relationship_weight must be in [0, 1], got {relationship_weight}")

    growth = (Decimal(1) + curve.growth_rate) ** contacts_sent
    ltv_multiplier = Decimal(str(0.5 + relationship_weight))
    return (curve.base_inr * growth * ltv_multiplier).quantize(_TWO_DP)
