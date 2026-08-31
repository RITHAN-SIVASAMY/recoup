"""Checkout abandonment: file-driven per the Phase 02 cut line, not a live beacon.

Consumes a batch of checkout session records (however they were collected —
a periodic export, a synthetic batch) and normalizes the ones that are still
unpaid past `idle_threshold_minutes`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from recoup.ingestion.models import NormalizedIntake

DEFAULT_IDLE_THRESHOLD_MINUTES = 30


def scan_for_abandoned(
    sessions: list[dict[str, Any]],
    *,
    now: datetime,
    idle_threshold_minutes: int = DEFAULT_IDLE_THRESHOLD_MINUTES,
    default_merchant_id: str,
) -> list[NormalizedIntake]:
    threshold = timedelta(minutes=idle_threshold_minutes)
    abandoned = []
    for session in sessions:
        if session.get("paid", False):
            continue
        created_at: datetime = session["created_at"]
        if now - created_at < threshold:
            continue  # still within the grace window; not abandoned yet
        abandoned.append(
            NormalizedIntake(
                source_type="checkout_abandonment",
                provider_event_id=session["order_id"],
                merchant_id=session.get("merchant_id", default_merchant_id),
                amount_at_risk=Decimal(str(session["amount"])),
                currency=session.get("currency", "INR"),
                customer_ref=session.get("customer_ref", session["order_id"]),
                occurred_at=created_at,
                detail={"initiated_method": session.get("method")},
            )
        )
    return abandoned
