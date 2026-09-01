"""SEC-DATA-02: no raw phone number, email, or name reaches an outbound prompt."""

from __future__ import annotations

import pytest

from recoup.llm.redaction import redact_text

pytestmark = pytest.mark.unit


def test_redacts_an_email_address() -> None:
    result = redact_text("Contact priya.sharma@example.com about this.")
    assert "priya.sharma@example.com" not in result
    assert "[REDACTED_EMAIL]" in result


def test_redacts_an_indian_mobile_number() -> None:
    result = redact_text("Call 9876543210 to confirm.")
    assert "9876543210" not in result
    assert "[REDACTED_PHONE]" in result


def test_redacts_an_indian_mobile_number_with_country_code() -> None:
    result = redact_text("Call +91 9876543210 to confirm.")
    assert "9876543210" not in result


def test_redacts_an_honorific_name() -> None:
    result = redact_text("Please inform Mr. Rajesh Kumar of the update.")
    assert "Rajesh Kumar" not in result
    assert "[REDACTED_NAME]" in result


def test_leaves_ordinary_business_text_untouched() -> None:
    text = "Your payment of INR 499.00 for order failed due to insufficient funds."
    assert redact_text(text) == text
