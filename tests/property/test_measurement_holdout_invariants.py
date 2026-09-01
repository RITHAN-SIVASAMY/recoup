"""FR-13.5, property-tested: whatever sequence of looks the controller sees,
the resulting rate never leaves [floor_rate, default_rate], and `established`
is only ever true immediately after a look that actually crossed its
boundary or a look that continued a still-valid established run."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.measurement.holdout import HoldoutState, next_look
from recoup.measurement.stats import two_proportion_z_test

pytestmark = pytest.mark.property

_DEFAULT_RATE = Decimal("0.20")
_FLOOR_RATE = Decimal("0.05")

_arm = st.integers(min_value=1, max_value=500)


@given(
    n_treated=_arm,
    n_control=_arm,
    cases_observed=st.integers(min_value=1, max_value=500),
    data=st.data(),
)
def test_rate_after_a_single_look_never_leaves_the_configured_band(
    n_treated: int, n_control: int, cases_observed: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(min_value=0, max_value=n_treated))
    x_control = data.draw(st.integers(min_value=0, max_value=n_control))
    result = two_proportion_z_test(
        n_treated=n_treated, x_treated=x_treated, n_control=n_control, x_control=x_control
    )
    state = HoldoutState(current_rate=_DEFAULT_RATE)

    _, look = next_look(
        state,
        result=result,
        cases_observed=cases_observed,
        planned_total_cases=500,
        default_rate=_DEFAULT_RATE,
        floor_rate=_FLOOR_RATE,
    )

    assert _FLOOR_RATE <= look.rate_after <= _DEFAULT_RATE


@given(
    n_treated=_arm,
    n_control=_arm,
    cases_observed=st.integers(min_value=1, max_value=500),
    data=st.data(),
)
def test_established_action_only_fires_when_the_boundary_was_actually_crossed(
    n_treated: int, n_control: int, cases_observed: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(min_value=0, max_value=n_treated))
    x_control = data.draw(st.integers(min_value=0, max_value=n_control))
    result = two_proportion_z_test(
        n_treated=n_treated, x_treated=x_treated, n_control=n_control, x_control=x_control
    )
    state = HoldoutState(current_rate=_DEFAULT_RATE)

    _, look = next_look(
        state,
        result=result,
        cases_observed=cases_observed,
        planned_total_cases=500,
        default_rate=_DEFAULT_RATE,
        floor_rate=_FLOOR_RATE,
    )

    if look.action == "established":
        assert abs(look.z_observed) >= look.z_boundary


@given(
    n_treated=_arm,
    n_control=_arm,
    cases_observed=st.integers(min_value=1, max_value=500),
    data=st.data(),
)
def test_look_never_decreases_the_rate_below_the_floor_over_many_repeated_looks(
    n_treated: int, n_control: int, cases_observed: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(min_value=0, max_value=n_treated))
    x_control = data.draw(st.integers(min_value=0, max_value=n_control))
    result = two_proportion_z_test(
        n_treated=n_treated, x_treated=x_treated, n_control=n_control, x_control=x_control
    )
    state = HoldoutState(current_rate=_DEFAULT_RATE)

    for _ in range(20):
        state, _look = next_look(
            state,
            result=result,
            cases_observed=cases_observed,
            planned_total_cases=500,
            default_rate=_DEFAULT_RATE,
            floor_rate=_FLOOR_RATE,
        )
        assert _FLOOR_RATE <= state.current_rate <= _DEFAULT_RATE
