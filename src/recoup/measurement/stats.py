"""FR-13.6/13.7: the pre-registered analysis, exactly as fixed in
`docs/05-EVALUATION-PROTOCOL.md` §2-3 before any batch was run — a
two-proportion z-test on resolution rate, its 95% CI on the absolute lift,
and the minimum detectable effect for the batch actually run.

Every function here is pure: no I/O, no randomness, no wall-clock — the same
(n_t, x_t, n_c, x_c) always produces the same report. `TwoProportionResult.
significant` is the *only* place a yes/no verdict is computed, fixed at
alpha=0.05 two-sided with no parameter to loosen it — nothing downstream may
recompute or restate significance under a different threshold to make a
marginal result read differently (rule 9: no code path may make a null look
like a win).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from scipy import stats as scipy_stats

ALPHA_TWO_SIDED = 0.05
POWER = 0.80

Z_ALPHA_TWO_SIDED = float(scipy_stats.norm.ppf(1 - ALPHA_TWO_SIDED / 2))
_Z_BETA_80_POWER = float(scipy_stats.norm.ppf(POWER))


@dataclass(frozen=True)
class TwoProportionResult:
    n_treated: int
    n_control: int
    x_treated: int  # resolved count, treated arm
    x_control: int  # resolved count, control arm
    p_treated: float
    p_control: float
    lift: float  # p_treated - p_control, the absolute-lift point estimate
    se: float
    z: float
    p_value: float
    ci_low: float
    ci_high: float
    significant: bool  # p_value < ALPHA_TWO_SIDED — fixed, not configurable
    mde: float  # minimum detectable effect at 80% power for n_t/n_c as run


def _rate(x: int, n: int) -> float:
    return x / n


def _minimum_detectable_effect(*, n_treated: int, n_control: int, baseline_rate: float) -> float:
    variance_term = baseline_rate * (1 - baseline_rate) * (1 / n_treated + 1 / n_control)
    return (Z_ALPHA_TWO_SIDED + _Z_BETA_80_POWER) * sqrt(variance_term)


def two_proportion_z_test(
    *, n_treated: int, x_treated: int, n_control: int, x_control: int
) -> TwoProportionResult:
    if n_treated <= 0 or n_control <= 0:
        raise ValueError("both arms must have at least one case to test")
    if not (0 <= x_treated <= n_treated) or not (0 <= x_control <= n_control):
        raise ValueError("resolved count cannot exceed arm size or be negative")

    p_t = _rate(x_treated, n_treated)
    p_c = _rate(x_control, n_control)
    lift = p_t - p_c
    se = sqrt(p_t * (1 - p_t) / n_treated + p_c * (1 - p_c) / n_control)

    if se == 0.0:
        # Every case in both arms resolved identically (all-0% or all-100% in
        # both arms) — there is genuinely zero variance to test. Report a null
        # result honestly rather than dividing by zero or fabricating a p-value.
        z = 0.0
        p_value = 1.0
    else:
        z = lift / se
        p_value = 2 * (1 - float(scipy_stats.norm.cdf(abs(z))))

    mde = _minimum_detectable_effect(n_treated=n_treated, n_control=n_control, baseline_rate=p_c)

    return TwoProportionResult(
        n_treated=n_treated,
        n_control=n_control,
        x_treated=x_treated,
        x_control=x_control,
        p_treated=p_t,
        p_control=p_c,
        lift=lift,
        se=se,
        z=z,
        p_value=p_value,
        ci_low=lift - Z_ALPHA_TWO_SIDED * se,
        ci_high=lift + Z_ALPHA_TWO_SIDED * se,
        significant=p_value < ALPHA_TWO_SIDED,
        mde=mde,
    )
