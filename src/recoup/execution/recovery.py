"""FR-12: the recovery flow behind the public microsite. Everything here is
what `api/recovery.py` (the thin HTTP layer) calls — link verification and
single-use enforcement, cause-specific content (FR-12.2), and the three
terminal actions a customer can take (pay, opt out, remind me later),
each redeeming the link exactly once (FR-12.1) and feeding straight back
into the event log as bandit/uplift training signal (FR-12.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from recoup.audit.event_store import EventStore
from recoup.audit.projection import project
from recoup.domain.models import ActionType, Actor, Case
from recoup.execution.links import LinkPayload, LinkRedemptionStore, verify_link_token
from recoup.execution.optout import OptOutStore, opt_out_and_log
from recoup.execution.payment_links import PaymentLinkPort, PaymentLinkResult

_CUSTOMER = Actor(kind="human", identifier="customer")

RecoveryFixKind = Literal[
    "retry", "update_card", "reauthorize", "resume_cart", "pay_invoice", "contact_support"
]


@dataclass(frozen=True)
class RecoveryFix:
    kind: RecoveryFixKind
    headline: str
    explanation: str
    action_type: ActionType


_FIXES: dict[str, RecoveryFix] = {
    "card_expired_or_invalid": RecoveryFix(
        "update_card",
        "Your card needs updating",
        "The card on file has expired or is no longer valid. Update it to complete this payment.",
        "send_message",
    ),
    "insufficient_funds": RecoveryFix(
        "retry",
        "Your last payment attempt didn't go through",
        "There wasn't enough balance available at the time. Pay now, or ask us to remind you later.",
        "send_message",
    ),
    "otp_timeout_or_auth_abandon": RecoveryFix(
        "retry",
        "Your payment was interrupted",
        "The verification step timed out before it finished. Try again with the same payment method.",
        "send_message",
    ),
    "mandate_revoked": RecoveryFix(
        "reauthorize",
        "Your subscription needs re-authorizing",
        "Your bank cancelled the standing instruction for this subscription. Re-authorize it to continue.",
        "send_reauth_link",
    ),
    "mandate_insufficient_balance": RecoveryFix(
        "retry",
        "Your subscription payment didn't go through",
        "There wasn't enough balance for the scheduled payment. Pay now to keep your subscription active.",
        "send_message",
    ),
    "mandate_technical_failure": RecoveryFix(
        "retry",
        "Your subscription payment failed",
        "A technical issue interrupted the scheduled payment. We'll retry automatically, or you can pay now.",
        "send_message",
    ),
    "checkout_abandonment": RecoveryFix(
        "resume_cart",
        "Pick up where you left off",
        "Looks like something interrupted your checkout. Your order is still here whenever you're ready.",
        "send_message",
    ),
    "receivable_overdue": RecoveryFix(
        "pay_invoice",
        "An invoice is overdue",
        "This invoice is past its due date. Review the details and pay when convenient.",
        "send_message",
    ),
    "bank_soft_decline": RecoveryFix(
        "retry",
        "Your payment was declined",
        "Your bank declined this attempt. It's often temporary — try again or use a different method.",
        "send_message",
    ),
    "network_or_gateway_error": RecoveryFix(
        "retry",
        "A connection issue interrupted your payment",
        "A temporary network issue got in the way. Please try again.",
        "send_message",
    ),
    "issuer_risk_block": RecoveryFix(
        "contact_support",
        "Your bank placed a hold on this payment",
        "Your card issuer flagged this attempt for review. Please contact your bank, or try a different method.",
        "send_message",
    ),
}
_DEFAULT_FIX = RecoveryFix(
    "contact_support",
    "We noticed an issue with a recent payment",
    "Something interrupted this payment. Use the option below to resolve it.",
    "send_message",
)


def fix_for(root_cause: str | None) -> RecoveryFix:
    return _FIXES.get(root_cause or "", _DEFAULT_FIX)


class RecoveryLinkError(Exception):
    """Raised for an invalid, expired, or already-redeemed link — the
    caller renders a friendly page, never a 500 (FR-12's own wording)."""


class RecoveryLinkExpiredError(RecoveryLinkError):
    pass


class RecoveryLinkAlreadyUsedError(RecoveryLinkError):
    pass


@dataclass(frozen=True)
class RecoveryContext:
    case: Case
    fix: RecoveryFix
    ladder_step: int


async def resolve_link(
    token: str,
    *,
    event_store: EventStore,
    redemption_store: LinkRedemptionStore,
    secret: str,
    now: datetime,
) -> RecoveryContext:
    payload = verify_link_token(token, secret=secret, now=now)
    if payload is None:
        raise RecoveryLinkExpiredError("this link is invalid or has expired")
    if await redemption_store.is_redeemed(token):
        raise RecoveryLinkAlreadyUsedError("this link has already been used")

    events = await event_store.events_for(payload.case_id)
    if not events:
        raise RecoveryLinkExpiredError("this link is invalid or has expired")
    case = project(events)

    await event_store.append(
        case_id=case.case_id,
        event_type="link.viewed",
        payload={"ladder_step": payload.ladder_step},
        actor=_CUSTOMER,
    )
    return RecoveryContext(case=case, fix=fix_for(case.root_cause), ladder_step=payload.ladder_step)


async def _redeem_or_raise(
    token: str,
    payload: LinkPayload,
    redemption_store: LinkRedemptionStore,
    *,
    action: str,
    now: datetime,
) -> None:
    redeemed = await redemption_store.redeem(token, case_id=payload.case_id, action=action, now=now)
    if not redeemed:
        raise RecoveryLinkAlreadyUsedError("this link has already been used")


async def switch_method(
    token: str,
    *,
    event_store: EventStore,
    secret: str,
    to_channel: str,
    now: datetime,
) -> None:
    """Looking at a different fix doesn't consume the link — only a
    terminal action (pay, opt out, remind later) does."""
    payload = verify_link_token(token, secret=secret, now=now)
    if payload is None:
        raise RecoveryLinkExpiredError("this link is invalid or has expired")
    await event_store.append(
        case_id=payload.case_id,
        event_type="link.method_switched",
        payload={"to": to_channel},
        actor=_CUSTOMER,
    )


async def complete_payment(
    token: str,
    *,
    event_store: EventStore,
    redemption_store: LinkRedemptionStore,
    payment_link_port: PaymentLinkPort,
    secret: str,
    amount_inr: Decimal,
    callback_url: str,
    now: datetime,
) -> PaymentLinkResult:
    payload = verify_link_token(token, secret=secret, now=now)
    if payload is None:
        raise RecoveryLinkExpiredError("this link is invalid or has expired")
    if await redemption_store.is_redeemed(token):
        raise RecoveryLinkAlreadyUsedError("this link has already been used")

    return await payment_link_port.create(
        case_id=payload.case_id,
        reference_id=token,
        amount_inr=amount_inr,
        description=f"Recoup recovery — case {payload.case_id}",
        callback_url=callback_url,
    )


async def confirm_payment(
    token: str,
    *,
    event_store: EventStore,
    redemption_store: LinkRedemptionStore,
    secret: str,
    provider_ref: str,
    now: datetime,
) -> None:
    """Shared by the simulator's "simulate payment" step and the real
    Razorpay success webhook — the only two callers that may ever mark a
    case `recovered` from this flow."""
    payload = verify_link_token(token, secret=secret, now=now)
    if payload is None:
        raise RecoveryLinkExpiredError("this link is invalid or has expired")
    await _redeem_or_raise(token, payload, redemption_store, action="paid", now=now)
    await event_store.append(
        case_id=payload.case_id,
        event_type="payment.recovered",
        payload={"via": "recovery_link", "provider_ref": provider_ref},
        actor=_CUSTOMER,
    )


async def record_opt_out(
    token: str,
    *,
    event_store: EventStore,
    redemption_store: LinkRedemptionStore,
    optout_store: OptOutStore,
    secret: str,
    now: datetime,
) -> None:
    payload = verify_link_token(token, secret=secret, now=now)
    if payload is None:
        raise RecoveryLinkExpiredError("this link is invalid or has expired")
    await _redeem_or_raise(token, payload, redemption_store, action="opted_out", now=now)

    events = await event_store.events_for(payload.case_id)
    case = project(events)
    await opt_out_and_log(
        event_store,
        optout_store,
        case_id=case.case_id,
        customer_ref=case.customer_ref,
        merchant_id=case.merchant_id,
        now=now,
    )


async def record_remind_later(
    token: str,
    *,
    event_store: EventStore,
    redemption_store: LinkRedemptionStore,
    secret: str,
    remind_at: date,
    now: datetime,
) -> None:
    payload = verify_link_token(token, secret=secret, now=now)
    if payload is None:
        raise RecoveryLinkExpiredError("this link is invalid or has expired")
    if remind_at <= now.astimezone(UTC).date():
        raise ValueError("remind_at must be a future date")
    if remind_at > now.astimezone(UTC).date() + timedelta(days=90):
        raise ValueError("remind_at is too far in the future")

    await _redeem_or_raise(token, payload, redemption_store, action="remind_later", now=now)
    await event_store.append(
        case_id=payload.case_id,
        event_type="case.remind_later",
        payload={"remind_at": remind_at.isoformat()},
        actor=_CUSTOMER,
    )
