"""FR-12.3: the real Razorpay Payment Links request/response handling,
exercised against `httpx.MockTransport` — zero live network calls, but the
actual request-building and response-parsing code runs for real.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from recoup.execution.payment_links import RAZORPAY_API_BASE, RazorpayPaymentLinkPort

pytestmark = pytest.mark.unit


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url=RAZORPAY_API_BASE)


async def test_create_sends_the_amount_in_paise_with_basic_auth() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth_header"] = request.headers.get("authorization")
        captured["body"] = request.content
        return httpx.Response(
            200, json={"id": "plink_test123", "short_url": "https://rzp.io/i/test123"}
        )

    port = RazorpayPaymentLinkPort(
        "rzp_test_key", "rzp_test_secret", client=_client(httpx.MockTransport(handler))
    )

    result = await port.create(
        case_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        reference_id="tok_abc123",
        amount_inr=Decimal("499.50"),
        description="Recoup recovery — case 01ARZ3NDEKTSV4RRFFQ69G5FAV",
        callback_url="https://recoup.example/r/tok_abc123",
    )

    assert result.checkout_url == "https://rzp.io/i/test123"
    assert result.provider_ref == "plink_test123"
    assert captured["auth_header"] is not None
    assert b'"amount":49950' in captured["body"]  # type: ignore[operator]
    assert b'"reference_id":"tok_abc123"' in captured["body"]  # type: ignore[operator]


async def test_create_raises_on_a_non_2xx_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"description": "invalid key"}})

    port = RazorpayPaymentLinkPort(
        "bad_key", "bad_secret", client=_client(httpx.MockTransport(handler))
    )

    with pytest.raises(httpx.HTTPStatusError):
        await port.create(
            case_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            reference_id="tok_abc123",
            amount_inr=Decimal("100.00"),
            description="test",
            callback_url="https://recoup.example/r/tok_abc123",
        )
