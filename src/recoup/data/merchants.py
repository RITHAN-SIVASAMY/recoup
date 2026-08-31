"""Merchant profiles: different businesses see a different mix of revenue at risk."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MerchantProfile:
    merchant_id: str
    label: str
    source_type_weights: dict[str, float]  # sums to 1.0
    amount_range_inr: tuple[Decimal, Decimal]


MERCHANT_PROFILES: tuple[MerchantProfile, ...] = (
    MerchantProfile(
        merchant_id="demo-d2c",
        label="D2C retail",
        source_type_weights={
            "payment_failure": 0.60,
            "checkout_abandonment": 0.35,
            "mandate_failure": 0.05,
        },
        amount_range_inr=(Decimal("199"), Decimal("4999")),
    ),
    MerchantProfile(
        merchant_id="demo-subscription",
        label="Subscription / SaaS",
        source_type_weights={
            "mandate_failure": 0.55,
            "payment_failure": 0.35,
            "checkout_abandonment": 0.10,
        },
        amount_range_inr=(Decimal("99"), Decimal("1999")),
    ),
    MerchantProfile(
        merchant_id="demo-b2b",
        label="B2B receivables",
        source_type_weights={
            "receivable_overdue": 0.80,
            "payment_failure": 0.20,
        },
        amount_range_inr=(Decimal("10000"), Decimal("500000")),
    ),
)
