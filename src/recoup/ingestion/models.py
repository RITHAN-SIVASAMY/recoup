"""The common shape every normalizer produces: one Case, regardless of source."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from recoup.domain.models import SourceType

_TWO_DP = Decimal("0.01")


class NormalizedIntake(BaseModel):
    """What a normalizer hands to `ingest()`. Not a Case yet — `ingest()` owns creating one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: SourceType
    provider_event_id: str
    merchant_id: str
    amount_at_risk: Decimal
    currency: str = "INR"
    customer_ref: str
    occurred_at: datetime
    detail: dict[str, Any] = {}  # source-specific fields (decline_code, method, ...)

    @field_validator("amount_at_risk")
    @classmethod
    def _quantize_to_two_decimal_places(cls, value: Decimal) -> Decimal:
        # Money is always 2dp end to end — a paise-derived Decimal (e.g. 2500 vs
        # 2500.00) must stringify identically everywhere it's serialized, or
        # replay equality sees two representations of the same value as a diff.
        return value.quantize(_TWO_DP, rounding=ROUND_HALF_UP)

    def to_case_created_payload(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "provider_event_id": self.provider_event_id,
            "merchant_id": self.merchant_id,
            "amount_at_risk": str(self.amount_at_risk),
            "currency": self.currency,
            "customer_ref": self.customer_ref,
            **self.detail,
        }
