"""Unit tests: every normalizer produces the same NormalizedIntake shape."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from recoup.ingestion.normalizers import checkout_abandoned, mandate_failed, payment_failed
from recoup.ingestion.normalizers import receivable_overdue as receivable

pytestmark = pytest.mark.unit


def test_payment_failed_normalizer_extracts_amount_from_paise() -> None:
    raw = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_ABC123",
                    "amount": 150000,
                    "currency": "INR",
                    "order_id": "order_XYZ",
                    "method": "card",
                    "error_code": "GATEWAY_ERROR",
                    "error_description": "insufficient funds",
                    "error_reason": "insufficient_funds",
                    "contact": "+919999999999",
                    "notes": {},
                    "created_at": 1750000000,
                }
            }
        },
    }

    intake = payment_failed.normalize(raw, default_merchant_id="demo")

    assert intake.source_type == "payment_failure"
    assert intake.provider_event_id == "pay_ABC123"
    assert intake.merchant_id == "demo"
    assert intake.amount_at_risk == Decimal("1500.00")
    assert intake.customer_ref == "+919999999999"
    assert intake.detail["error_reason"] == "insufficient_funds"


def test_payment_failed_normalizer_prefers_merchant_id_from_notes() -> None:
    raw = {
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "amount": 100,
                    "notes": {"merchant_id": "merchant-42"},
                    "created_at": 1750000000,
                }
            }
        }
    }

    intake = payment_failed.normalize(raw, default_merchant_id="demo")

    assert intake.merchant_id == "merchant-42"


def test_mandate_failed_normalizer_is_a_distinct_source_from_payment_failure() -> None:
    raw = {
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_1",
                    "status": "halted",
                    "customer_id": "cust_1",
                    "plan_id": "plan_1",
                    "amount": 99900,
                    "created_at": 1750000000,
                    "notes": {},
                }
            }
        }
    }

    intake = mandate_failed.normalize(raw, default_merchant_id="demo")

    assert intake.source_type == "mandate_failure"
    assert intake.provider_event_id == "sub_1:halted"
    assert intake.amount_at_risk == Decimal("999.00")
    assert intake.detail["status"] == "halted"


def test_checkout_abandoned_skips_sessions_still_within_the_idle_window() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    sessions = [
        {
            "order_id": "order_fresh",
            "customer_ref": "cust_1",
            "amount": "100.00",
            "created_at": now,
            "paid": False,
        },
        {
            "order_id": "order_stale",
            "customer_ref": "cust_2",
            "amount": "200.00",
            "created_at": datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
            "paid": False,
        },
        {
            "order_id": "order_paid",
            "customer_ref": "cust_3",
            "amount": "300.00",
            "created_at": datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
            "paid": True,
        },
    ]

    abandoned = checkout_abandoned.scan_for_abandoned(
        sessions, now=now, idle_threshold_minutes=30, default_merchant_id="demo"
    )

    assert [intake.provider_event_id for intake in abandoned] == ["order_stale"]
    assert abandoned[0].source_type == "checkout_abandonment"


def test_receivable_overdue_normalizer_computes_days_overdue() -> None:
    row = {
        "invoice_id": "INV-001",
        "amount": "50000.00",
        "customer_ref": "acct_1",
        "due_date": datetime(2025, 12, 1, tzinfo=UTC),
        "terms": "net-30",
    }
    now = datetime(2026, 1, 1, tzinfo=UTC)

    intake = receivable.normalize(row, default_merchant_id="demo", now=now)

    assert intake.source_type == "receivable_overdue"
    assert intake.provider_event_id == "INV-001"
    assert intake.detail["days_overdue"] == 31
