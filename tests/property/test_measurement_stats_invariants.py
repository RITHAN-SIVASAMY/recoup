"""FR-13.6/13.7, property-tested: the statistical primitives hold their basic
mathematical guarantees over arbitrary arm sizes and outcome counts, not just
the hand-picked examples in `test_measurement_stats.py`."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.measurement.stats import two_proportion_z_test

pytestmark = pytest.mark.property

_arm = st.integers(min_value=1, max_value=2000)


@given(n_treated=_arm, n_control=_arm, data=st.data())
def test_the_ci_always_contains_the_point_estimate(
    n_treated: int, n_control: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(min_value=0, max_value=n_treated))
    x_control = data.draw(st.integers(min_value=0, max_value=n_control))

    result = two_proportion_z_test(
        n_treated=n_treated, x_treated=x_treated, n_control=n_control, x_control=x_control
    )

    assert result.ci_low <= result.lift <= result.ci_high


@given(n_treated=_arm, n_control=_arm, data=st.data())
def test_p_value_and_se_stay_within_their_valid_ranges(
    n_treated: int, n_control: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(min_value=0, max_value=n_treated))
    x_control = data.draw(st.integers(min_value=0, max_value=n_control))

    result = two_proportion_z_test(
        n_treated=n_treated, x_treated=x_treated, n_control=n_control, x_control=x_control
    )

    assert 0.0 <= result.p_value <= 1.0
    assert result.se >= 0.0
    # mde is 0 only in the degenerate case where the control rate itself is 0%
    # or 100% (the normal-approximation variance term vanishes); otherwise positive.
    assert result.mde >= 0.0


@given(n_treated=_arm, n_control=_arm, data=st.data())
def test_significant_is_never_true_when_p_value_is_at_or_above_alpha(
    n_treated: int, n_control: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(min_value=0, max_value=n_treated))
    x_control = data.draw(st.integers(min_value=0, max_value=n_control))

    result = two_proportion_z_test(
        n_treated=n_treated, x_treated=x_treated, n_control=n_control, x_control=x_control
    )

    if result.significant:
        assert result.p_value < 0.05
    else:
        assert result.p_value >= 0.05 or result.p_value == 1.0


@given(n_control=_arm, x_control=st.integers(min_value=1, max_value=1999), small=_arm, big=_arm)
def test_mde_shrinks_as_treated_sample_size_grows(
    n_control: int, x_control: int, small: int, big: int
) -> None:
    x_control = min(x_control, n_control - 1) if n_control > 1 else 0
    n_small, n_big = min(small, big), max(small, big) + 1  # ensure n_big > n_small strictly

    result_small = two_proportion_z_test(
        n_treated=n_small, x_treated=0, n_control=n_control, x_control=x_control
    )
    result_big = two_proportion_z_test(
        n_treated=n_big, x_treated=0, n_control=n_control, x_control=x_control
    )

    assert result_big.mde <= result_small.mde
