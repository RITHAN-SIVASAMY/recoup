"""The one feature-extraction function, shared by training and inference.

`ml/features.py` (offline training) and `understanding/classify.py` etc. (online
scoring) must never compute features differently — that's train/serve skew, and
it would silently invalidate every metric in the model cards. This module is the
single source of truth for both; `ml/train_*.py` imports it rather than
reimplementing it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from recoup.data.merchants import MERCHANT_PROFILES

CATEGORICAL_COLUMNS = [
    "source_type",
    "merchant_id",
    "error_reason",
    "mandate_status",
    "method",
    "issuer",
]
NUMERIC_COLUMNS = [
    "amount_at_risk",
    "relative_amount",
    "hour_of_day",
    "day_of_week",
    "consecutive_failures",
]
FEATURE_COLUMNS = CATEGORICAL_COLUMNS + NUMERIC_COLUMNS

# Stands in for real per-merchant config (FRD §8.3's Merchant entity) until that
# exists — for this build, the demo generator's profiles are the only merchant
# configuration there is, so scoring reuses them directly rather than duplicating
# the numbers here where they'd silently drift.
_AMOUNT_RANGE_BY_MERCHANT: dict[str, tuple[Decimal, Decimal]] = {
    profile.merchant_id: profile.amount_range_inr for profile in MERCHANT_PROFILES
}
_DEFAULT_RANGE = (Decimal("0"), Decimal("100000"))


def relative_amount(merchant_id: str, amount_at_risk: float) -> float:
    low, high = _AMOUNT_RANGE_BY_MERCHANT.get(merchant_id, _DEFAULT_RANGE)
    low_f, high_f = float(low), float(high)
    if high_f <= low_f:
        return 0.5
    return max(0.0, min(1.0, (amount_at_risk - low_f) / (high_f - low_f)))


def extract_features(
    *,
    source_type: str,
    merchant_id: str,
    amount_at_risk: Decimal | float,
    occurred_at: datetime,
    detail: dict[str, Any],
) -> dict[str, Any]:
    is_mandate = source_type == "mandate_failure"
    amount = float(amount_at_risk)
    return {
        "source_type": source_type,
        "merchant_id": merchant_id,
        "amount_at_risk": amount,
        "relative_amount": relative_amount(merchant_id, amount),
        "hour_of_day": occurred_at.hour,
        "day_of_week": occurred_at.weekday(),
        "error_reason": detail.get("error_reason", "n/a"),
        "mandate_status": detail.get("status", "n/a") if is_mandate else "n/a",
        "consecutive_failures": detail.get("consecutive_failures", 0),
        "method": detail.get("method") or detail.get("initiated_method") or "n/a",
        "issuer": detail.get("issuer", "n/a"),
    }
