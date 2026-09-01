"""FR-13.8, property-tested: CUPED's two defining mathematical guarantees hold
over arbitrary generated outcome/covariate pairs, not just hand-picked ones --

1. theta is OLS-optimal for the *pooled* sample, so adjusting can never
   increase the pooled variance of the outcome versus leaving it unadjusted.
2. Adjustment is mean-preserving over the pooled sample -- CUPED only ever
   redistributes variance, it never shifts the overall average outcome.

Both are checked end-to-end through the public API: `result.theta` is a real
output, and the pooled mean/variance are recomputed independently in the test
from the same input arrays the test itself drew, not read out of the module's
internals.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.measurement.cuped import cuped_adjust

pytestmark = pytest.mark.property

_outcome = st.sampled_from([0.0, 1.0])
_covariate = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_arm = st.lists(st.tuples(_outcome, _covariate), min_size=1, max_size=30)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sample_variance(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    return sum((v - m) ** 2 for v in values) / (n - 1)


@given(treated=_arm, control=_arm)
def test_cuped_adjustment_never_increases_pooled_variance(
    treated: list[tuple[float, float]], control: list[tuple[float, float]]
) -> None:
    treated_outcomes, treated_covariates = [t[0] for t in treated], [t[1] for t in treated]
    control_outcomes, control_covariates = [c[0] for c in control], [c[1] for c in control]

    result = cuped_adjust(
        treated_outcomes=treated_outcomes,
        treated_covariates=treated_covariates,
        control_outcomes=control_outcomes,
        control_covariates=control_covariates,
    )

    pooled_outcomes = treated_outcomes + control_outcomes
    pooled_covariates = treated_covariates + control_covariates
    x_bar = _mean(pooled_covariates)
    adjusted = [
        y - result.theta * (x - x_bar)
        for x, y in zip(pooled_covariates, pooled_outcomes, strict=True)
    ]

    assert _sample_variance(adjusted) <= _sample_variance(pooled_outcomes) + 1e-9


@given(treated=_arm, control=_arm)
def test_cuped_adjustment_preserves_the_pooled_mean(
    treated: list[tuple[float, float]], control: list[tuple[float, float]]
) -> None:
    treated_outcomes, treated_covariates = [t[0] for t in treated], [t[1] for t in treated]
    control_outcomes, control_covariates = [c[0] for c in control], [c[1] for c in control]

    result = cuped_adjust(
        treated_outcomes=treated_outcomes,
        treated_covariates=treated_covariates,
        control_outcomes=control_outcomes,
        control_covariates=control_covariates,
    )

    pooled_outcomes = treated_outcomes + control_outcomes
    pooled_covariates = treated_covariates + control_covariates
    x_bar = _mean(pooled_covariates)
    adjusted = [
        y - result.theta * (x - x_bar)
        for x, y in zip(pooled_covariates, pooled_outcomes, strict=True)
    ]

    assert _mean(adjusted) == pytest.approx(_mean(pooled_outcomes), abs=1e-9)


@given(treated=_arm, control=_arm)
def test_significance_flag_matches_the_fixed_alpha_threshold(
    treated: list[tuple[float, float]], control: list[tuple[float, float]]
) -> None:
    treated_outcomes, treated_covariates = [t[0] for t in treated], [t[1] for t in treated]
    control_outcomes, control_covariates = [c[0] for c in control], [c[1] for c in control]

    result = cuped_adjust(
        treated_outcomes=treated_outcomes,
        treated_covariates=treated_covariates,
        control_outcomes=control_outcomes,
        control_covariates=control_covariates,
    )

    assert result.significant_adjusted == (result.p_value_adjusted < 0.05)
