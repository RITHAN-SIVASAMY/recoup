"""Unit tests for Razorpay webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from recoup.ingestion.signature import verify_razorpay_signature

pytestmark = pytest.mark.unit

SECRET = "whsec_test"
BODY = b'{"event":"payment.failed"}'


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_accepts_a_correctly_signed_payload() -> None:
    assert verify_razorpay_signature(BODY, _sign(BODY, SECRET), SECRET) is True


def test_rejects_a_wrong_signature() -> None:
    assert verify_razorpay_signature(BODY, "0" * 64, SECRET) is False


def test_rejects_a_signature_computed_with_the_wrong_secret() -> None:
    assert verify_razorpay_signature(BODY, _sign(BODY, "other-secret"), SECRET) is False


def test_rejects_a_missing_signature_header() -> None:
    assert verify_razorpay_signature(BODY, None, SECRET) is False


def test_rejects_when_no_secret_is_configured() -> None:
    assert verify_razorpay_signature(BODY, _sign(BODY, ""), "") is False


def test_signature_check_is_sensitive_to_body_tampering() -> None:
    signature = _sign(BODY, SECRET)
    tampered = BODY.replace(b"payment.failed", b"payment.captured")
    assert verify_razorpay_signature(tampered, signature, SECRET) is False
