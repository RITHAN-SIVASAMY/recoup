"""Normalize a Razorpay subscription/e-mandate status-change webhook.

Envelope shape:
    {"event": "subscription.halted", "payload": {"subscription": {"entity": {...}}}}
Treated as a distinct source per FR-1.3 — never folded into a generic payment failure,
since the right recovery ladder (re-authorize the mandate) is completely different.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from recoup.ingestion.models import NormalizedIntake


def normalize(raw: dict[str, Any], *, default_merchant_id: str) -> NormalizedIntake:
    entity = raw["payload"]["subscription"]["entity"]
    notes = entity.get("notes") or {}
    amount_paise = entity.get("amount", 0)

    return NormalizedIntake(
        source_type="mandate_failure",
        provider_event_id=f"{entity['id']}:{entity.get('status', 'unknown')}",
        merchant_id=notes.get("merchant_id", default_merchant_id),
        amount_at_risk=Decimal(amount_paise) / Decimal(100),
        currency=entity.get("currency", "INR"),
        customer_ref=entity.get("customer_id", entity["id"]),
        occurred_at=datetime.fromtimestamp(entity["created_at"], tz=UTC),
        detail={
            "plan_id": entity.get("plan_id"),
            "status": entity.get("status"),
            "charge_at": entity.get("charge_at"),
        },
    )
