"""arq cron: reconciliation poll for mandate/subscription status changes.

Webhooks are the primary path for FR-1.3; this poller is the safety net for
deliveries a webhook missed. `NullMandateStatusSource` is the default because
there is no live Razorpay account wired into this environment — a real
`RazorpaySubscriptionAPISource` is a live-mode-only adapter behind the same
protocol, never a hard dependency (ADR-0006: simulator-first).
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from recoup.audit.event_store import EventStore
from recoup.ingestion.ingest import IngestResult, ingest
from recoup.ingestion.normalizers.mandate_failed import normalize


class MandateStatusSource(Protocol):
    async def poll_changed_subscriptions(self) -> list[dict[str, Any]]: ...


class NullMandateStatusSource:
    """The production-safe default: no live credentials configured, nothing to poll."""

    async def poll_changed_subscriptions(self) -> list[dict[str, Any]]:
        return []


async def poll_mandate_status(
    session: AsyncSession,
    event_store: EventStore,
    source: MandateStatusSource,
    *,
    default_merchant_id: str,
) -> list[IngestResult]:
    changed = await source.poll_changed_subscriptions()
    results = []
    for raw in changed:
        intake = normalize(raw, default_merchant_id=default_merchant_id)
        results.append(await ingest(session, event_store, intake))
    return results
