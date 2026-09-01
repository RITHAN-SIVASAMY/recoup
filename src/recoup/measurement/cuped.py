"""FR-13.8: CUPED (Controlled-experiment Using Pre-Existing Data) variance
reduction on the binary resolution outcome, using a pre-period covariate the
caller supplies per case. This module is deliberately agnostic about *what*
that covariate is — its only statistical requirement is that it be measured
before the outcome and be (in expectation) unaffected by treatment assignment,
so randomization keeps its distribution balanced across arms. In this build
the covariate report.py supplies is each case's baseline propensity-to-
resolve prediction (`p_recover_baseline`) from the trained, feature-only
model — never the generator's hidden ground truth, which would leak the
answer rather than genuinely reduce variance.

theta (the adjustment coefficient) is estimated once from the *pooled* sample
across both arms, not per arm — randomization guarantees the covariate's
distribution doesn't systematically differ by arm, so pooling gives a more
stable theta estimate than either arm alone could. Adjusting subtracts
`theta * (covariate - pooled_mean_covariate)` from each case's outcome, which
is mean-preserving over the pooled sample and, by construction (theta is the
OLS-optimal coefficient), can never increase the pooled variance versus the
unadjusted outcome.

The unadjusted two-proportion result (`stats.two_proportion_z_test`) is never
replaced by this — FR-13.8 requires it always be shown alongside, and
`report.py` is what enforces that, not this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

from scipy import stats as scipy_stats

from recoup.measurement.stats import ALPHA_TWO_SIDED, Z_ALPHA_TWO_SIDED


@dataclass(frozen=True)
class CupedResult:
    theta: float
    n_treated: int
    n_control: int
    mean_treated_adjusted: float
    mean_control_adjusted: float
    lift_adjusted: float  # mean_treated_adjusted - mean_control_adjusted
    se_adjusted: float
    ci_low_adjusted: float
    ci_high_adjusted: float
    p_value_adjusted: float
    significant_adjusted: bool


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _sample_variance(values: Sequence[float], mean_: float) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    return sum((v - mean_) ** 2 for v in values) / (n - 1)


def cuped_adjust(
    *,
    treated_outcomes: Sequence[float],
    treated_covariates: Sequence[float],
    control_outcomes: Sequence[float],
    control_covariates: Sequence[float],
) -> CupedResult:
    if len(treated_outcomes) != len(treated_covariates):
        raise ValueError("treated outcomes and covariates must be paired 1:1")
    if len(control_outcomes) != len(control_covariates):
        raise ValueError("control outcomes and covariates must be paired 1:1")
    if not treated_outcomes or not control_outcomes:
        raise ValueError("both arms must have at least one case to CUPED-adjust")

    pooled_outcomes = [*treated_outcomes, *control_outcomes]
    pooled_covariates = [*treated_covariates, *control_covariates]
    n_pooled = len(pooled_outcomes)

    x_bar = _mean(pooled_covariates)
    y_bar = _mean(pooled_outcomes)
    covariance = (
        sum(
            (x - x_bar) * (y - y_bar)
            for x, y in zip(pooled_covariates, pooled_outcomes, strict=True)
        )
        / (n_pooled - 1)
        if n_pooled > 1
        else 0.0
    )
    variance_x = _sample_variance(pooled_covariates, x_bar)
    theta = covariance / variance_x if variance_x > 0 else 0.0

    adj_treated = [
        y - theta * (x - x_bar) for x, y in zip(treated_covariates, treated_outcomes, strict=True)
    ]
    adj_control = [
        y - theta * (x - x_bar) for x, y in zip(control_covariates, control_outcomes, strict=True)
    ]

    mean_t = _mean(adj_treated)
    mean_c = _mean(adj_control)
    lift = mean_t - mean_c
    var_t = _sample_variance(adj_treated, mean_t)
    var_c = _sample_variance(adj_control, mean_c)
    se = sqrt(var_t / len(adj_treated) + var_c / len(adj_control))

    if se == 0.0:
        z = 0.0
        p_value = 1.0
    else:
        z = lift / se
        p_value = 2 * (1 - float(scipy_stats.norm.cdf(abs(z))))

    return CupedResult(
        theta=theta,
        n_treated=len(adj_treated),
        n_control=len(adj_control),
        mean_treated_adjusted=mean_t,
        mean_control_adjusted=mean_c,
        lift_adjusted=lift,
        se_adjusted=se,
        ci_low_adjusted=lift - Z_ALPHA_TWO_SIDED * se,
        ci_high_adjusted=lift + Z_ALPHA_TWO_SIDED * se,
        p_value_adjusted=p_value,
        significant_adjusted=p_value < ALPHA_TWO_SIDED,
    )
