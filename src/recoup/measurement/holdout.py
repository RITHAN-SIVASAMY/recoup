"""FR-13.5/§6: the adaptive holdout controller.

Starts at the merchant's configured `default_holdout_rate` (20%). After each
measurement window ("look"), a sequential test with an O'Brien-Fleming-type
alpha-spending function decides whether the accumulated evidence is strong
enough that repeated peeking hasn't inflated the false-positive rate past
the pre-registered 0.05. The boundary and its exact spending function are
the closed-form Lan-DeMets O'Brien-Fleming approximation:

    z_boundary(t)  = z_alpha_final / sqrt(t)
    alpha_spent(t) = 2 * (1 - Phi(z_boundary(t)))

where `t` is the information fraction (cases observed so far / planned batch
size) and `z_alpha_final` is the same two-sided critical value the final,
full-information look would use. At t=1 this recovers the ordinary
single-look z-test exactly (`alpha_spent(1) == 0.05`); at small t the
boundary is far stricter, which is what stops an early lucky-looking look
from being declared a win.

Once a look's |z| crosses its boundary, the effect is "established" and the
holdout decays toward `holdout_floor_rate` (half the remaining gap to the
floor per subsequent look, so it approaches but never undercuts the floor).
If a later look's lift estimate falls outside the confidence interval
recorded at establishment, the holdout re-expands immediately back to
`default_holdout_rate` and has to re-earn establishment from scratch.

Every look -- decayed, re-expanded, or unchanged -- is written to the
append-only `holdout_looks` table via `record_look`, never only kept in
memory, so a reviewer can replay the exact sequence of decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import sqrt
from typing import Literal

from scipy import stats as scipy_stats
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.domain.ids import new_ulid
from recoup.measurement.schema import HoldoutLookRow
from recoup.measurement.stats import Z_ALPHA_TWO_SIDED, TwoProportionResult

LookAction = Literal["no_change", "established", "decayed", "re_expanded"]

_DECAY_MULTIPLIER = Decimal("0.5")
_MIN_INFORMATION_FRACTION = 1e-6


@dataclass(frozen=True)
class HoldoutState:
    current_rate: Decimal
    established: bool = False
    established_ci: tuple[float, float] | None = None
    look_count: int = 0


@dataclass(frozen=True)
class HoldoutLook:
    look_index: int
    information_fraction: float
    z_boundary: float
    alpha_spent: float
    z_observed: float
    lift: float
    ci_low: float
    ci_high: float
    action: LookAction
    rate_before: Decimal
    rate_after: Decimal


def information_fraction(cases_observed: int, planned_total_cases: int) -> float:
    if planned_total_cases <= 0:
        raise ValueError("planned_total_cases must be positive")
    if cases_observed < 0:
        raise ValueError("cases_observed cannot be negative")
    return min(1.0, max(_MIN_INFORMATION_FRACTION, cases_observed / planned_total_cases))


def obrien_fleming_boundary(t: float) -> float:
    return Z_ALPHA_TWO_SIDED / sqrt(t)


def alpha_spent(t: float) -> float:
    boundary = obrien_fleming_boundary(t)
    return 2 * (1 - float(scipy_stats.norm.cdf(boundary)))


def _decay(rate: Decimal, floor_rate: Decimal) -> Decimal:
    return floor_rate + (rate - floor_rate) * _DECAY_MULTIPLIER


def next_look(
    state: HoldoutState,
    *,
    result: TwoProportionResult,
    cases_observed: int,
    planned_total_cases: int,
    default_rate: Decimal,
    floor_rate: Decimal,
) -> tuple[HoldoutState, HoldoutLook]:
    t = information_fraction(cases_observed, planned_total_cases)
    boundary = obrien_fleming_boundary(t)
    spent = alpha_spent(t)
    crossed = abs(result.z) >= boundary

    look_index = state.look_count + 1
    rate_before = state.current_rate

    def _look(action: LookAction, rate_after: Decimal) -> HoldoutLook:
        return HoldoutLook(
            look_index=look_index,
            information_fraction=t,
            z_boundary=boundary,
            alpha_spent=spent,
            z_observed=result.z,
            lift=result.lift,
            ci_low=result.ci_low,
            ci_high=result.ci_high,
            action=action,
            rate_before=rate_before,
            rate_after=rate_after,
        )

    if state.established and state.established_ci is not None:
        ci_lo, ci_hi = state.established_ci
        if not (ci_lo <= result.lift <= ci_hi):
            new_state = HoldoutState(
                current_rate=default_rate,
                established=False,
                established_ci=None,
                look_count=look_index,
            )
            return new_state, _look("re_expanded", default_rate)

    if crossed and not state.established:
        new_rate = _decay(rate_before, floor_rate)
        new_state = HoldoutState(
            current_rate=new_rate,
            established=True,
            established_ci=(result.ci_low, result.ci_high),
            look_count=look_index,
        )
        return new_state, _look("established", new_rate)

    if state.established:
        new_rate = _decay(rate_before, floor_rate)
        new_state = HoldoutState(
            current_rate=new_rate,
            established=True,
            established_ci=state.established_ci,
            look_count=look_index,
        )
        return new_state, _look("decayed", new_rate)

    new_state = HoldoutState(
        current_rate=rate_before, established=False, established_ci=None, look_count=look_index
    )
    return new_state, _look("no_change", rate_before)


async def record_look(
    engine: AsyncEngine,
    look: HoldoutLook,
    *,
    batch_id: str,
    now: datetime,
    policy_version: str,
) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session, session.begin():
        session.add(
            HoldoutLookRow(
                look_id=new_ulid(),
                batch_id=batch_id,
                look_index=look.look_index,
                recorded_at=now,
                information_fraction=Decimal(str(look.information_fraction)),
                z_boundary=Decimal(str(look.z_boundary)),
                alpha_spent=Decimal(str(look.alpha_spent)),
                z_observed=Decimal(str(look.z_observed)),
                lift=Decimal(str(look.lift)),
                ci_low=Decimal(str(look.ci_low)),
                ci_high=Decimal(str(look.ci_high)),
                action=look.action,
                rate_before=look.rate_before,
                rate_after=look.rate_after,
                policy_version=policy_version,
            )
        )
