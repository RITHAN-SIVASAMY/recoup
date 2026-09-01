"""FR-13.5/§6: the O'Brien-Fleming boundary/spending functions and the
adaptive controller's four decision branches (no_change, established,
decayed, re_expanded)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from recoup.measurement.holdout import (
    HoldoutState,
    alpha_spent,
    information_fraction,
    next_look,
    obrien_fleming_boundary,
)
from recoup.measurement.stats import ALPHA_TWO_SIDED, two_proportion_z_test

pytestmark = pytest.mark.unit

_DEFAULT_RATE = Decimal("0.20")
_FLOOR_RATE = Decimal("0.05")


def test_information_fraction_is_clamped_to_one_at_full_or_over_enrollment() -> None:
    assert information_fraction(500, 500) == 1.0
    assert information_fraction(600, 500) == 1.0  # over-enrolled batches don't exceed t=1


def test_information_fraction_rejects_a_non_positive_plan() -> None:
    with pytest.raises(ValueError, match="planned_total_cases"):
        information_fraction(10, 0)


def test_boundary_at_full_information_equals_the_ordinary_fixed_sample_critical_value() -> None:
    assert obrien_fleming_boundary(1.0) == pytest.approx(1.959963984540054, rel=1e-9)


def test_alpha_spent_at_full_information_equals_the_nominal_alpha() -> None:
    assert alpha_spent(1.0) == pytest.approx(ALPHA_TWO_SIDED, abs=1e-9)


def test_the_boundary_is_stricter_at_low_information_than_at_full_information() -> None:
    assert obrien_fleming_boundary(0.25) > obrien_fleming_boundary(1.0)
    assert alpha_spent(0.25) < alpha_spent(1.0)


def test_a_weak_early_result_produces_no_change() -> None:
    # n=20/20 with a modest lift -- nowhere near the strict early boundary.
    result = two_proportion_z_test(n_treated=20, x_treated=11, n_control=20, x_control=9)
    state = HoldoutState(current_rate=_DEFAULT_RATE)

    new_state, look = next_look(
        state,
        result=result,
        cases_observed=40,
        planned_total_cases=500,
        default_rate=_DEFAULT_RATE,
        floor_rate=_FLOOR_RATE,
    )

    assert look.action == "no_change"
    assert new_state.current_rate == _DEFAULT_RATE
    assert new_state.established is False


def test_a_strong_result_at_full_information_establishes_and_decays() -> None:
    result = two_proportion_z_test(n_treated=400, x_treated=248, n_control=100, x_control=40)
    state = HoldoutState(current_rate=_DEFAULT_RATE)

    new_state, look = next_look(
        state,
        result=result,
        cases_observed=500,
        planned_total_cases=500,
        default_rate=_DEFAULT_RATE,
        floor_rate=_FLOOR_RATE,
    )

    assert look.action == "established"
    assert new_state.established is True
    assert _FLOOR_RATE < new_state.current_rate < _DEFAULT_RATE
    assert new_state.established_ci == (result.ci_low, result.ci_high)


def test_repeated_strong_looks_keep_decaying_toward_but_never_below_the_floor() -> None:
    result = two_proportion_z_test(n_treated=400, x_treated=248, n_control=100, x_control=40)
    state = HoldoutState(current_rate=_DEFAULT_RATE, established=True, established_ci=(0.0, 1.0))

    for _ in range(40):  # enough halvings that the remaining gap is far below the tolerance
        state, look = next_look(
            state,
            result=result,
            cases_observed=500,
            planned_total_cases=500,
            default_rate=_DEFAULT_RATE,
            floor_rate=_FLOOR_RATE,
        )
        assert look.action == "decayed"
        assert state.current_rate >= _FLOOR_RATE

    assert float(state.current_rate) == pytest.approx(float(_FLOOR_RATE), abs=1e-6)


def test_a_lift_that_drifts_outside_the_established_band_re_expands_immediately() -> None:
    # established_ci deliberately excludes the new look's lift, forcing drift.
    state = HoldoutState(current_rate=_FLOOR_RATE, established=True, established_ci=(0.30, 0.40))
    result = two_proportion_z_test(n_treated=100, x_treated=50, n_control=100, x_control=48)
    assert not (0.30 <= result.lift <= 0.40)

    new_state, look = next_look(
        state,
        result=result,
        cases_observed=500,
        planned_total_cases=500,
        default_rate=_DEFAULT_RATE,
        floor_rate=_FLOOR_RATE,
    )

    assert look.action == "re_expanded"
    assert new_state.current_rate == _DEFAULT_RATE
    assert new_state.established is False
    assert new_state.established_ci is None


def test_look_index_increments_across_successive_calls() -> None:
    result = two_proportion_z_test(n_treated=20, x_treated=11, n_control=20, x_control=9)
    state = HoldoutState(current_rate=_DEFAULT_RATE)

    state, first = next_look(
        state,
        result=result,
        cases_observed=40,
        planned_total_cases=500,
        default_rate=_DEFAULT_RATE,
        floor_rate=_FLOOR_RATE,
    )
    _, second = next_look(
        state,
        result=result,
        cases_observed=80,
        planned_total_cases=500,
        default_rate=_DEFAULT_RATE,
        floor_rate=_FLOOR_RATE,
    )

    assert first.look_index == 1
    assert second.look_index == 2
