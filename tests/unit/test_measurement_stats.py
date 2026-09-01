"""FR-13.6/13.7: the two-proportion z-test, CI and MDE against hand- and
independently-computed values, plus the boundary cases the honesty guardrail
depends on (rule 9: no code path may make a null look like a win)."""

from __future__ import annotations

import math

import pytest
from scipy import stats as scipy_stats

from recoup.measurement.stats import ALPHA_TWO_SIDED, two_proportion_z_test

pytestmark = pytest.mark.unit


def test_a_clear_lift_is_correctly_computed_and_flagged_significant() -> None:
    # n_t=100 x_t=60 (60%), n_c=100 x_c=40 (40%) -- independently recomputed below,
    # not by re-deriving the module's own formula, so a transcription bug in the
    # implementation (wrong sign, wrong denominator) would still be caught.
    p_t, p_c = 0.60, 0.40
    expected_se = math.sqrt(p_t * (1 - p_t) / 100 + p_c * (1 - p_c) / 100)
    expected_z = (p_t - p_c) / expected_se
    expected_p = 2 * (1 - scipy_stats.norm.cdf(abs(expected_z)))

    result = two_proportion_z_test(n_treated=100, x_treated=60, n_control=100, x_control=40)

    assert result.lift == pytest.approx(0.20)
    assert result.se == pytest.approx(expected_se)
    assert result.z == pytest.approx(expected_z)
    assert result.p_value == pytest.approx(expected_p)
    assert result.significant is True
    assert result.ci_low < result.lift < result.ci_high
    assert result.ci_low > 0  # the whole 95% interval excludes zero


def test_identical_resolution_rates_produce_zero_lift_and_no_significance() -> None:
    result = two_proportion_z_test(n_treated=200, x_treated=80, n_control=100, x_control=40)

    assert result.lift == pytest.approx(0.0)
    assert result.p_value == pytest.approx(1.0)
    assert result.significant is False


def test_zero_variance_in_both_arms_reports_a_null_without_dividing_by_zero() -> None:
    result = two_proportion_z_test(n_treated=50, x_treated=0, n_control=50, x_control=0)

    assert result.se == 0.0
    assert result.z == 0.0
    assert result.p_value == 1.0
    assert result.significant is False


def test_significance_flag_matches_the_fixed_alpha_threshold_exactly() -> None:
    result = two_proportion_z_test(n_treated=100, x_treated=60, n_control=100, x_control=40)
    assert result.significant == (result.p_value < ALPHA_TWO_SIDED)


def test_a_marginal_result_is_never_rounded_into_significance() -> None:
    # Small n, small lift -- deliberately underpowered so p should land above 0.05.
    result = two_proportion_z_test(n_treated=20, x_treated=6, n_control=20, x_control=4)
    assert result.significant is False
    assert result.p_value >= ALPHA_TWO_SIDED
    assert result.mde > 0  # the honest bound is still reported even though the result is null


@pytest.mark.parametrize(
    ("n_treated", "x_treated", "n_control", "x_control"),
    [
        (0, 0, 10, 5),
        (10, 5, 0, 0),
        (10, 11, 10, 5),  # more resolved than cases
        (10, -1, 10, 5),
    ],
)
def test_invalid_inputs_raise_rather_than_silently_producing_a_number(
    n_treated: int, x_treated: int, n_control: int, x_control: int
) -> None:
    with pytest.raises(ValueError, match=r"."):
        two_proportion_z_test(
            n_treated=n_treated, x_treated=x_treated, n_control=n_control, x_control=x_control
        )
