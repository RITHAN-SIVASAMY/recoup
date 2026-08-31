"""Normalize a Razorpay `payment.failed` webhook into a NormalizedIntake.

Envelope shape (Razorpay's public webhook format):
    {"event": "payment.failed", "payload": {"payment": {"entity": {...}}}}
`entity.amount` is in paise; `entity.created_at` is a Unix timestamp.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from recoup.ingestion.models import NormalizedIntake


def normalize(raw: dict[str, Any], *, default_merchant_id: str) -> NormalizedIntake:
    entity = raw["payload"]["payment"]["entity"]
    notes = entity.get("notes") or {}

    return NormalizedIntake(
        source_type="payment_failure",
        provider_event_id=entity["id"],
        merchant_id=notes.get("merchant_id", default_merchant_id),
        amount_at_risk=Decimal(entity["amount"]) / Decimal(100),
        currency=entity.get("currency", "INR"),
        customer_ref=entity.get("contact") or entity.get("email") or entity["id"],
        occurred_at=datetime.fromtimestamp(entity["created_at"], tz=UTC),
        detail={
            "order_id": entity.get("order_id"),
            "method": entity.get("method"),
            "error_code": entity.get("error_code"),
            "error_description": entity.get("error_description"),
            "error_reason": entity.get("error_reason"),
        },
    )
