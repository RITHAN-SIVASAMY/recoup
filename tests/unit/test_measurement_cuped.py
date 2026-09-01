"""FR-13.8: CUPED variance reduction against hand-computed and boundary cases."""

from __future__ import annotations

import pytest

from recoup.measurement.cuped import cuped_adjust

pytestmark = pytest.mark.unit


def test_a_perfectly_correlated_covariate_drives_variance_to_zero() -> None:
    # outcome == covariate exactly -> theta=1, every adjusted value collapses
    # to the pooled mean, so the arms' adjusted means become identical to
    # the pooled mean's contribution and se collapses toward zero.
    result = cuped_adjust(
        treated_outcomes=[1.0, 0.0, 1.0, 0.0],
        treated_covariates=[1.0, 0.0, 1.0, 0.0],
        control_outcomes=[1.0, 0.0, 1.0, 0.0],
        control_covariates=[1.0, 0.0, 1.0, 0.0],
    )
    assert result.theta == pytest.approx(1.0)
    assert result.se_adjusted == pytest.approx(0.0, abs=1e-9)


def test_a_covariate_with_zero_variance_falls_back_to_no_adjustment() -> None:
    # every case has the same covariate value -> Var(X) = 0 -> theta = 0 ->
    # adjusted outcomes equal the raw outcomes exactly.
    result = cuped_adjust(
        treated_outcomes=[1.0, 0.0, 1.0],
        treated_covariates=[0.5, 0.5, 0.5],
        control_outcomes=[0.0, 0.0, 1.0],
        control_covariates=[0.5, 0.5, 0.5],
    )
    assert result.theta == 0.0
    assert result.mean_treated_adjusted == pytest.approx(2 / 3)
    assert result.mean_control_adjusted == pytest.approx(1 / 3)


def test_an_uncorrelated_covariate_leaves_the_lift_estimate_unchanged() -> None:
    # covariate identical for every case in both arms (no within- or
    # across-arm variation at all) means theta is undefined by variance but
    # forced to 0 by the zero-variance guard, so lift_adjusted == raw lift.
    treated_outcomes = [1.0, 1.0, 0.0, 1.0]
    control_outcomes = [0.0, 1.0, 0.0, 0.0]
    result = cuped_adjust(
        treated_outcomes=treated_outcomes,
        treated_covariates=[1.0] * 4,
        control_outcomes=control_outcomes,
        control_covariates=[1.0] * 4,
    )
    raw_lift = sum(treated_outcomes) / 4 - sum(control_outcomes) / 4
    assert result.lift_adjusted == pytest.approx(raw_lift)


@pytest.mark.parametrize(
    ("treated_outcomes", "treated_covariates", "control_outcomes", "control_covariates"),
    [
        ([1.0, 0.0], [0.5], [1.0], [0.5]),  # mismatched treated pairing
        ([1.0], [0.5], [1.0, 0.0], [0.5]),  # mismatched control pairing
        ([], [], [1.0], [0.5]),  # empty treated arm
        ([1.0], [0.5], [], []),  # empty control arm
    ],
)
def test_malformed_inputs_raise_rather_than_silently_misaligning(
    treated_outcomes: list[float],
    treated_covariates: list[float],
    control_outcomes: list[float],
    control_covariates: list[float],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        cuped_adjust(
            treated_outcomes=treated_outcomes,
            treated_covariates=treated_covariates,
            control_outcomes=control_outcomes,
            control_covariates=control_covariates,
        )
