"""FR-9.2: the constrained contextual bandit. Thompson sampling over Beta
posteriors per `(segment, channel, hour_bucket)` — but `thompson_select`'s
signature makes the constraint structural, not conventional: it takes
`permitted_arms` and can only ever return a member of that set, because it
is the only set it samples from. There is no code path here that can widen
the action set past what policy already allowed and EV already cleared.

FR-9.3's channel fatigue (suppress a channel ignored twice consecutively) is
applied *before* sampling, as a further narrowing of `permitted_arms` — never
a way to add a channel back in.
"""

from __future__ import annotations

import random
from datetime import datetime

from redis.asyncio import Redis

from recoup.domain.models import Channel

_KEY_PREFIX = "recoup:bandit:"
_PRIOR_ALPHA = 1.0
_PRIOR_BETA = 1.0


def hour_bucket(now: datetime) -> int:
    return now.hour


def _key(segment: str | None, channel: Channel, bucket: int, field: str) -> str:
    return f"{_KEY_PREFIX}{segment or 'none'}:{channel}:{bucket}:{field}"


def thompson_select(
    posteriors: dict[Channel, tuple[float, float]],
    permitted_arms: frozenset[Channel],
    rng: random.Random,
) -> Channel:
    if not permitted_arms:
        raise ValueError("no permitted arms to select from")
    samples = {
        arm: rng.betavariate(*posteriors.get(arm, (_PRIOR_ALPHA, _PRIOR_BETA)))
        for arm in permitted_arms
    }
    return max(samples, key=lambda arm: samples[arm])


def apply_channel_fatigue(
    permitted_arms: frozenset[Channel], last_two_engaged: dict[Channel, list[bool]]
) -> frozenset[Channel]:
    """`last_two_engaged` maps a channel to its most-recent-first engagement
    outcomes for this customer. A channel ignored (not engaged) on its last
    two contacts is suppressed — unless that would suppress every arm, since
    a narrowed-to-empty set is not a valid choice set for the bandit."""
    surviving = frozenset(
        arm
        for arm in permitted_arms
        if not (len(last_two_engaged.get(arm, [])) >= 2 and not any(last_two_engaged[arm][:2]))
    )
    return surviving if surviving else permitted_arms


async def get_posteriors(
    redis: Redis, segment: str | None, arms: frozenset[Channel], bucket: int
) -> dict[Channel, tuple[float, float]]:
    posteriors: dict[Channel, tuple[float, float]] = {}
    for arm in arms:
        raw_alpha = await redis.get(_key(segment, arm, bucket, "alpha"))
        raw_beta = await redis.get(_key(segment, arm, bucket, "beta"))
        alpha = float(raw_alpha) if raw_alpha is not None else _PRIOR_ALPHA
        beta = float(raw_beta) if raw_beta is not None else _PRIOR_BETA
        posteriors[arm] = (alpha, beta)
    return posteriors


async def update_posterior(
    redis: Redis, segment: str | None, channel: Channel, bucket: int, *, success: bool
) -> None:
    field = "alpha" if success else "beta"
    key = _key(segment, channel, bucket, field)
    prior = _PRIOR_ALPHA if field == "alpha" else _PRIOR_BETA
    current = await redis.get(key)
    new_value = (float(current) if current is not None else prior) + 1
    await redis.set(key, str(new_value))


async def select_arm(
    redis: Redis,
    *,
    segment: str | None,
    permitted_arms: frozenset[Channel],
    now: datetime,
    last_two_engaged: dict[Channel, list[bool]] | None = None,
    rng: random.Random | None = None,
) -> Channel:
    narrowed = apply_channel_fatigue(permitted_arms, last_two_engaged or {})
    bucket = hour_bucket(now)
    posteriors = await get_posteriors(redis, segment, narrowed, bucket)
    return thompson_select(posteriors, narrowed, rng or random.Random())
