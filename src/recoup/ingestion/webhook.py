"""The Razorpay webhook route. Verify, archive, dedupe, enqueue — no business logic.

Always returns 200: the DLQ, not the HTTP status, is where "we couldn't handle this"
goes, so a misbehaving payload can never trigger the provider's retry storm.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from recoup.api.deps import get_event_store, get_session
from recoup.audit.event_store import EventStore
from recoup.ingestion.dlq import archive_raw_event, enqueue_dlq
from recoup.ingestion.ingest import ingest
from recoup.ingestion.models import NormalizedIntake
from recoup.ingestion.normalizers import mandate_failed, payment_failed
from recoup.ingestion.signature import verify_razorpay_signature
from recoup.settings import get_settings

router = APIRouter()

Normalizer = Callable[..., NormalizedIntake]

_NORMALIZERS: dict[str, Normalizer] = {
    "payment.failed": payment_failed.normalize,
    "subscription.halted": mandate_failed.normalize,
    "subscription.pending": mandate_failed.normalize,
    "subscription.cancelled": mandate_failed.normalize,
}


async def _reject(
    session: AsyncSession, *, source: str, reason: str, raw_event_id: int
) -> dict[str, str]:
    await enqueue_dlq(session, source=source, reason=reason, raw_event_id=raw_event_id)
    await session.commit()
    return {"status": "rejected", "reason": reason}


@router.post("/webhooks/razorpay")
async def receive_razorpay_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    event_store: Annotated[EventStore, Depends(get_event_store)],
) -> dict[str, Any]:
    settings = get_settings()
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    signature_valid = verify_razorpay_signature(
        raw_body, signature, settings.razorpay_webhook_secret
    )

    raw_event_id = await archive_raw_event(
        session,
        source="razorpay",
        headers=dict(request.headers),
        raw_body=raw_body.decode("utf-8", errors="replace"),
        signature_valid=signature_valid,
    )
    await session.commit()

    if not signature_valid:
        return await _reject(
            session, source="razorpay", reason="invalid_signature", raw_event_id=raw_event_id
        )

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        return await _reject(
            session,
            source="razorpay",
            reason=f"malformed_json: {exc}",
            raw_event_id=raw_event_id,
        )

    event_type = payload.get("event")
    normalizer = _NORMALIZERS.get(event_type)
    if normalizer is None:
        return await _reject(
            session,
            source="razorpay",
            reason=f"unhandled_event_type: {event_type!r}",
            raw_event_id=raw_event_id,
        )

    try:
        intake = normalizer(payload, default_merchant_id=settings.merchant_id)
    except (KeyError, TypeError, ValueError) as exc:
        return await _reject(
            session,
            source="razorpay",
            reason=f"normalize_error: {exc}",
            raw_event_id=raw_event_id,
        )

    result = await ingest(session, event_store, intake)
    return {
        "status": "created" if result.created else "duplicate",
        "case_id": result.case_id,
    }
