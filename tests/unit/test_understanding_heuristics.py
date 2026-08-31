"""Unit tests for the pure, model-free scoring pieces: segmentation, priority, relationship."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from recoup.understanding.priority import priority_score, urgency_decay
from recoup.understanding.relationship import NEUTRAL_TRUST_SCORE, score_relationship
from recoup.understanding.uplift import segment_for

pytestmark = pytest.mark.unit


def test_segment_sleeping_dog_wins_even_with_a_high_baseline() -> None:
    assert segment_for(baseline_propensity=0.9, uplift=-0.10) == "sleeping_dog"


def test_segment_sure_thing_needs_a_high_baseline_and_non_negative_uplift() -> None:
    assert segment_for(baseline_propensity=0.75, uplift=0.01) == "sure_thing"


def test_segment_lost_cause_is_low_baseline_and_weak_uplift() -> None:
    assert segment_for(baseline_propensity=0.20, uplift=0.02) == "lost_cause"


def test_segment_persuadable_is_the_meaningful_positive_uplift_case() -> None:
    assert segment_for(baseline_propensity=0.20, uplift=0.30) == "persuadable"


def test_urgency_decay_is_one_at_zero_age() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert urgency_decay(now, now=now) == pytest.approx(1.0)


def test_urgency_decay_falls_toward_zero_as_a_case_ages() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    fresh = urgency_decay(now, now=now)
    old = urgency_decay(now - timedelta(days=30), now=now)
    assert 0.0 < old < fresh


def test_priority_score_is_zero_when_uplift_is_zero() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    score = priority_score(
        uplift=0.0,
        amount_at_risk=Decimal("5000"),
        occurred_at=now,
        relationship_weight=0.8,
        now=now,
    )
    assert score == 0.0


def test_priority_score_scales_with_amount_and_relationship_weight() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    small = priority_score(
        uplift=0.2, amount_at_risk=Decimal("100"), occurred_at=now, relationship_weight=0.5, now=now
    )
    large = priority_score(
        uplift=0.2,
        amount_at_risk=Decimal("1000"),
        occurred_at=now,
        relationship_weight=0.5,
        now=now,
    )
    assert large > small


def test_relationship_weight_is_bounded_and_b2b_gets_a_bonus() -> None:
    d2c = score_relationship(merchant_id="demo-d2c", amount_at_risk=Decimal("4999"))
    b2b = score_relationship(merchant_id="demo-b2b", amount_at_risk=Decimal("10000"))

    assert 0.0 <= d2c.relationship_weight <= 1.0
    assert 0.0 <= b2b.relationship_weight <= 1.0
    assert d2c.trust_score == NEUTRAL_TRUST_SCORE  # no promise-to-pay history exists yet
