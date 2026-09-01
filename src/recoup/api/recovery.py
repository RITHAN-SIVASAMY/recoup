"""FR-12: the public recovery microsite's API. Thin by design — all decision
logic lives in `execution/recovery.py`; this router verifies rate limits and
translates `RecoveryLinkError`s into friendly HTTP responses, never a 500.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis

from recoup.api.deps import (
    get_event_store,
    get_link_redemption_store,
    get_optout_store,
    get_payment_link_port,
    get_redis,
)
from recoup.audit.event_store import EventStore
from recoup.execution import recovery
from recoup.execution.links import LinkRedemptionStore
from recoup.execution.optout import OptOutStore
from recoup.execution.payment_links import PaymentLinkPort
from recoup.execution.ratelimit import check_rate_limit
from recoup.ingestion.signature import verify_razorpay_signature
from recoup.settings import get_settings

router = APIRouter(prefix="/api/recovery")
webhook_router = APIRouter()

_RATE_LIMIT = 30
_RATE_WINDOW = timedelta(minutes=1)


async def _enforce_rate_limit(request: Request, redis: Redis, token: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed = await check_rate_limit(
        redis, f"{token}:{client_ip}", limit=_RATE_LIMIT, window=_RATE_WINDOW
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="too many requests, please slow down")


def _map_error(exc: recovery.RecoveryLinkError) -> HTTPException:
    if isinstance(exc, recovery.RecoveryLinkAlreadyUsedError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=410, detail=str(exc))


class FixOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    headline: str
    explanation: str


class RecoveryContextOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    amount_at_risk: str
    root_cause: str | None
    fix: FixOut
    test_mode: bool


class PaymentLinkOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    checkout_url: str
    provider_ref: str


class RemindLaterIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    remind_at: date


class MethodSwitchIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    to_channel: str


@router.get("/{token}")
async def get_recovery_context(
    token: str,
    request: Request,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    redemption_store: Annotated[LinkRedemptionStore, Depends(get_link_redemption_store)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> RecoveryContextOut:
    await _enforce_rate_limit(request, redis, token)
    try:
        ctx = await recovery.resolve_link(
            token,
            event_store=event_store,
            redemption_store=redemption_store,
            secret=get_settings().link_signing_secret,
            now=datetime.now(UTC),
        )
    except recovery.RecoveryLinkError as exc:
        raise _map_error(exc) from exc

    return RecoveryContextOut(
        case_id=ctx.case.case_id,
        amount_at_risk=str(ctx.case.amount_at_risk),
        root_cause=ctx.case.root_cause,
        fix=FixOut(kind=ctx.fix.kind, headline=ctx.fix.headline, explanation=ctx.fix.explanation),
        test_mode=get_settings().razorpay_mode == "test",
    )


@router.post("/{token}/pay")
async def create_payment(
    token: str,
    request: Request,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    redemption_store: Annotated[LinkRedemptionStore, Depends(get_link_redemption_store)],
    payment_link_port: Annotated[PaymentLinkPort, Depends(get_payment_link_port)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PaymentLinkOut:
    await _enforce_rate_limit(request, redis, token)
    now = datetime.now(UTC)
    settings = get_settings()
    try:
        ctx = await recovery.resolve_link(
            token,
            event_store=event_store,
            redemption_store=redemption_store,
            secret=settings.link_signing_secret,
            now=now,
        )
        result = await recovery.complete_payment(
            token,
            event_store=event_store,
            redemption_store=redemption_store,
            payment_link_port=payment_link_port,
            secret=settings.link_signing_secret,
            amount_inr=ctx.case.amount_at_risk,
            callback_url=f"{settings.public_base_url}/r/{token}/simulate-payment",
            now=now,
        )
    except recovery.RecoveryLinkError as exc:
        raise _map_error(exc) from exc
    return PaymentLinkOut(checkout_url=result.checkout_url, provider_ref=result.provider_ref)


@router.post("/{token}/simulate-payment")
async def simulate_payment(
    token: str,
    request: Request,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    redemption_store: Annotated[LinkRedemptionStore, Depends(get_link_redemption_store)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, str]:
    """Only meaningful with the simulator payment-link adapter — a real
    Razorpay payment is confirmed by `webhooks/razorpay/payment-link`
    instead, never by the browser calling this directly."""
    await _enforce_rate_limit(request, redis, token)
    try:
        await recovery.confirm_payment(
            token,
            event_store=event_store,
            redemption_store=redemption_store,
            secret=get_settings().link_signing_secret,
            provider_ref=f"sim-{token[:12]}",
            now=datetime.now(UTC),
        )
    except recovery.RecoveryLinkError as exc:
        raise _map_error(exc) from exc
    return {"status": "recovered"}


@router.post("/{token}/opt-out")
async def opt_out(
    token: str,
    request: Request,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    redemption_store: Annotated[LinkRedemptionStore, Depends(get_link_redemption_store)],
    optout_store: Annotated[OptOutStore, Depends(get_optout_store)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, str]:
    await _enforce_rate_limit(request, redis, token)
    try:
        await recovery.record_opt_out(
            token,
            event_store=event_store,
            redemption_store=redemption_store,
            optout_store=optout_store,
            secret=get_settings().link_signing_secret,
            now=datetime.now(UTC),
        )
    except recovery.RecoveryLinkError as exc:
        raise _map_error(exc) from exc
    return {"status": "opted_out"}


@router.post("/{token}/remind-later")
async def remind_later(
    token: str,
    body: RemindLaterIn,
    request: Request,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    redemption_store: Annotated[LinkRedemptionStore, Depends(get_link_redemption_store)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, str]:
    await _enforce_rate_limit(request, redis, token)
    try:
        await recovery.record_remind_later(
            token,
            event_store=event_store,
            redemption_store=redemption_store,
            secret=get_settings().link_signing_secret,
            remind_at=body.remind_at,
            now=datetime.now(UTC),
        )
    except recovery.RecoveryLinkError as exc:
        raise _map_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "remind_later", "remind_at": body.remind_at.isoformat()}


@router.post("/{token}/method-switch")
async def method_switch(
    token: str,
    body: MethodSwitchIn,
    request: Request,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, str]:
    await _enforce_rate_limit(request, redis, token)
    try:
        await recovery.switch_method(
            token,
            event_store=event_store,
            secret=get_settings().link_signing_secret,
            to_channel=body.to_channel,
            now=datetime.now(UTC),
        )
    except recovery.RecoveryLinkError as exc:
        raise _map_error(exc) from exc
    return {"status": "ok"}


@webhook_router.post("/webhooks/razorpay/payment-link")
async def razorpay_payment_link_webhook(
    request: Request,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    redemption_store: Annotated[LinkRedemptionStore, Depends(get_link_redemption_store)],
) -> dict[str, str]:
    """The real Razorpay success callback (FR-12.3) — closes the loop for a
    live payment link the same way `simulate-payment` closes it for the
    simulator: through `execution.recovery.confirm_payment`, the one place
    a case may be marked recovered from this flow. Always returns 200 so a
    signature failure or a race with an already-consumed link never causes
    Razorpay to retry into a storm (same discipline as `ingestion/webhook.py`)."""
    settings = get_settings()
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    if not verify_razorpay_signature(raw_body, signature, settings.razorpay_webhook_secret):
        return {"status": "rejected", "reason": "invalid signature"}

    payload = await request.json()
    payment_link = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    token = payment_link.get("reference_id")
    provider_ref = payment_link.get("id", "")
    if not token:
        return {"status": "rejected", "reason": "missing reference_id"}

    try:
        await recovery.confirm_payment(
            token,
            event_store=event_store,
            redemption_store=redemption_store,
            secret=settings.link_signing_secret,
            provider_ref=provider_ref,
            now=datetime.now(UTC),
        )
    except recovery.RecoveryLinkError:
        return {"status": "rejected", "reason": "link invalid, expired, or already used"}
    return {"status": "ok"}
