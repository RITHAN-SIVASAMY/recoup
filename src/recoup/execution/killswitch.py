"""FR-7.4: the global kill switch. One control halts all autonomous action
instantly and cancels every in-flight staged action.

State lives in Redis (`recoup:killswitch:<merchant_id>`), the same coordination
store `RedisIdempotencyGuard` already uses — this is ops-transient state, not
case history, so it does not belong in the hash-chained event log. Its *effect*
is what gets permanently audited: `disengage_and_cancel_in_flight` writes a real
`action.cancelled` event, with the engaging actor, on every case whose staged
action it cancels (see `execution/staging.py`), which is where FR-7.4's "logged
with actor and timestamp" requirement is actually satisfied per case.
"""

from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis

from recoup.audit.event_store import EventStore
from recoup.domain.canonical import canonical_json
from recoup.domain.models import Actor
from recoup.execution.staging import StagedAction, StagingStore, cancel_and_log

_KEY_PREFIX = "recoup:killswitch:"


def _key(merchant_id: str) -> str:
    return f"{_KEY_PREFIX}{merchant_id}"


async def is_engaged(redis: Redis, merchant_id: str) -> bool:
    raw = await redis.get(_key(merchant_id))
    return raw is not None


async def engage(
    redis: Redis, merchant_id: str, *, actor: Actor, now: datetime | None = None
) -> None:
    now = now or datetime.now(UTC)
    payload = {"actor": actor.model_dump(mode="json"), "engaged_at": now}
    await redis.set(_key(merchant_id), canonical_json(payload))


async def disengage(redis: Redis, merchant_id: str) -> None:
    await redis.delete(_key(merchant_id))


async def cancel_all_in_flight(
    event_store: EventStore,
    staging_store: StagingStore,
    merchant_id: str,
    *,
    actor: Actor,
    now: datetime,
) -> list[StagedAction]:
    """Cancel every action of `merchant_id` still in `staged` status — the
    "cancels in-flight staged actions" half of FR-7.4. `list_in_flight` only
    ever returns `status == "staged"` rows, so nothing here can double-cancel
    an action another request already cancelled or promoted."""
    cancelled = []
    for staged in await staging_store.list_in_flight(merchant_id):
        result = await cancel_and_log(
            event_store, staged, actor=actor, reason="killswitch_engaged", now=now
        )
        await staging_store.save(result)
        cancelled.append(result)
    return cancelled
