"""FR-12.3: Razorpay test-mode Payment Links, behind the same simulator-first
port pattern ADR-0006 established for messaging channels (FR-9.6's own
wording — "adapters for live providers sit behind the same interface" —
generalizes past just SMS/WhatsApp/email/voice). `SimulatorPaymentLinkPort`
is the default: no real Razorpay credentials are configured in this
environment, so the recovery page's "pay" affordance resolves entirely
within this process rather than redirecting to an external domain, and is
fully demoable and testable without spending a rupee. `RazorpayPaymentLinkPort`
is real, working code against Razorpay's REST API, exercised in tests via a
mocked HTTP transport (never a live network call from a test).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


@dataclass(frozen=True)
class PaymentLinkResult:
    checkout_url: str
    provider_ref: str


class PaymentLinkPort(Protocol):
    async def create(
        self,
        *,
        case_id: str,
        reference_id: str,
        amount_inr: Decimal,
        description: str,
        callback_url: str,
    ) -> PaymentLinkResult: ...


class SimulatorPaymentLinkPort:
    """The checkout URL points back into our own app — a clearly-labelled
    "simulate payment" step — rather than a real Razorpay-hosted page."""

    def __init__(self, public_base_url: str) -> None:
        self._public_base_url = public_base_url.rstrip("/")

    async def create(
        self,
        *,
        case_id: str,
        reference_id: str,
        amount_inr: Decimal,
        description: str,
        callback_url: str,
    ) -> PaymentLinkResult:
        return PaymentLinkResult(
            checkout_url=callback_url,  # the recovery page renders its own simulated-pay step
            provider_ref=f"sim-payment-link-{case_id}",
        )


class RazorpayPaymentLinkPort:
    """Real Razorpay Payment Links API (test mode). `client` is injectable so
    tests can pass an `httpx.AsyncClient` built on `httpx.MockTransport` —
    the request-building and response-parsing logic is exercised for real,
    with zero live network calls."""

    def __init__(
        self, key_id: str, key_secret: str, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._client = client or httpx.AsyncClient(base_url=RAZORPAY_API_BASE, timeout=8.0)

    async def create(
        self,
        *,
        case_id: str,
        reference_id: str,
        amount_inr: Decimal,
        description: str,
        callback_url: str,
    ) -> PaymentLinkResult:
        response = await self._client.post(
            "/payment_links",
            auth=(self._key_id, self._key_secret),
            json={
                "amount": int(amount_inr * 100),  # paise
                "currency": "INR",
                "description": description,
                "reference_id": reference_id,
                "callback_url": callback_url,
                "callback_method": "get",
            },
        )
        response.raise_for_status()
        body = response.json()
        return PaymentLinkResult(checkout_url=body["short_url"], provider_ref=body["id"])
