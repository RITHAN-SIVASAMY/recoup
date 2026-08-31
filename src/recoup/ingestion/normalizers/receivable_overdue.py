"""Normalize one overdue-receivable row (CSV or API) into a NormalizedIntake."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from recoup.ingestion.models import NormalizedIntake


def normalize(row: dict[str, Any], *, default_merchant_id: str, now: datetime) -> NormalizedIntake:
    due_date: datetime = row["due_date"]
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=UTC)

    return NormalizedIntake(
        source_type="receivable_overdue",
        provider_event_id=str(row["invoice_id"]),
        merchant_id=row.get("merchant_id", default_merchant_id),
        amount_at_risk=Decimal(str(row["amount"])),
        currency=row.get("currency", "INR"),
        customer_ref=str(row["customer_ref"]),
        occurred_at=due_date,
        detail={
            "invoice_id": str(row["invoice_id"]),
            "due_date": due_date.date().isoformat(),
            "terms": row.get("terms"),
            "days_overdue": max((now - due_date).days, 0),
        },
    )
