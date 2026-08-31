"""Razorpay webhook signature verification: HMAC-SHA256 of the raw body."""

from __future__ import annotations

import hashlib
import hmac


def verify_razorpay_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
