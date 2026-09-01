"""Unit tests for the pure economics functions: costs, goodwill, fatigue."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from recoup.economics.costs import channel_cost, human_review_cost
from recoup.economics.fatigue import is_fatigued, remaining_contact_budget
from recoup.economics.goodwill import goodwill_cost
from recoup.policy.schema import ContactFatigue, GoodwillCurve, MerchantEconomics

pytestmark = pytest.mark.unit

_ECONOMICS = MerchantEconomics(
    ev_floor_inr=Decimal("5.00"),
    margin=Decimal("0.85"),
    channel_costs_inr={
        "sms": Decimal("0.20"),
        "whatsapp": Decimal("0.35"),
        "email": Decimal("0.05"),
    },
    human_review_cost_inr=Decimal("25.00"),
    goodwill=GoodwillCurve(base_inr=Decimal("0.50"), growth_rate=Decimal("0.6")),
)


def test_channel_cost_looks_up_the_configured_price() -> None:
    assert channel_cost("send_message", "sms", _ECONOMICS) == Decimal("0.20")
    assert channel_cost("send_message", "email", _ECONOMICS) == Decimal("0.05")


def test_channel_cost_is_zero_for_a_non_contact_action() -> None:
    assert channel_cost("retry_charge", None, _ECONOMICS) == Decimal("0")
    assert channel_cost("stop", None, _ECONOMICS) == Decimal("0")


def test_channel_cost_defaults_to_zero_for_an_unpriced_channel() -> None:
    assert channel_cost("voice_call", "voice", _ECONOMICS) == Decimal("0")


def test_human_review_cost_reads_the_configured_value() -> None:
    assert human_review_cost(_ECONOMICS) == Decimal("25.00")


def test_goodwill_cost_rises_with_contact_count() -> None:
    first = goodwill_cost(0, _ECONOMICS.goodwill, relationship_weight=0.5)
    second = goodwill_cost(1, _ECONOMICS.goodwill, relationship_weight=0.5)
    third = goodwill_cost(2, _ECONOMICS.goodwill, relationship_weight=0.5)
    assert first < second < third


def test_goodwill_cost_is_higher_for_a_higher_relationship_weight() -> None:
    low_ltv = goodwill_cost(1, _ECONOMICS.goodwill, relationship_weight=0.0)
    high_ltv = goodwill_cost(1, _ECONOMICS.goodwill, relationship_weight=1.0)
    assert high_ltv > low_ltv


def test_goodwill_cost_rejects_a_negative_contact_count() -> None:
    with pytest.raises(ValueError, match="contacts_sent"):
        goodwill_cost(-1, _ECONOMICS.goodwill, relationship_weight=0.5)


def test_goodwill_cost_rejects_an_out_of_range_relationship_weight() -> None:
    with pytest.raises(ValueError, match="relationship_weight"):
        goodwill_cost(0, _ECONOMICS.goodwill, relationship_weight=1.5)


_FATIGUE = ContactFatigue(max_contacts=3, window=timedelta(days=30))


def test_remaining_contact_budget_counts_down() -> None:
    assert remaining_contact_budget(0, _FATIGUE) == 3
    assert remaining_contact_budget(2, _FATIGUE) == 1
    assert remaining_contact_budget(3, _FATIGUE) == 0


def test_remaining_contact_budget_never_goes_negative() -> None:
    assert remaining_contact_budget(10, _FATIGUE) == 0


def test_is_fatigued_flips_at_the_cap() -> None:
    assert is_fatigued(2, _FATIGUE) is False
    assert is_fatigued(3, _FATIGUE) is True
    assert is_fatigued(4, _FATIGUE) is True
