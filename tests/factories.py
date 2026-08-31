"""Small test-data builders shared across unit/property/integration tests."""

from __future__ import annotations

from typing import Any

from recoup.domain.ids import new_ulid


def case_created_payload(source_type: str = "payment_failure", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_type": source_type,
        "merchant_id": "demo-merchant",
        "provider_event_id": new_ulid(),
        "amount_at_risk": "499.00",
        "currency": "INR",
        "customer_ref": "cust_test",
    }
    payload.update(overrides)
    return payload
