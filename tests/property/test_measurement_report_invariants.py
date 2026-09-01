"""FR-13.6/13.10, property-tested: rule 9's honesty guardrail holds over
arbitrary generated batches, not just the hand-picked examples -- the
NOT-SIGNIFICANT marker appears exactly when it must, `cost_per_inr_recovered`
is undefined exactly when incremental recovery is non-positive, and the
whole report/render pipeline is a pure, deterministic function of its input.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.measurement.report import BatchInputs, build_report, render_headline_block

pytestmark = pytest.mark.property


def _inputs(n_treated: int, x_treated: int, n_control: int, x_control: int) -> BatchInputs:
    return BatchInputs(
        batch_id="b_prop",
        seed=1,
        n_cases_total=n_treated + n_control,
        at_risk_inr=Decimal("100000"),
        raw_recovered_inr=Decimal("50000"),
        n_treated=n_treated,
        x_treated=x_treated,
        n_control=n_control,
        x_control=x_control,
        mean_recovered_value_inr=Decimal("500"),
        treated_outcomes=[1.0] * x_treated + [0.0] * (n_treated - x_treated),
        treated_covariates=[0.5] * n_treated,
        control_outcomes=[1.0] * x_control + [0.0] * (n_control - x_control),
        control_covariates=[0.5] * n_control,
        spend_on_contact_inr=Decimal("500"),
        saved_by_not_contacting_inr=Decimal("0"),
        actions_blocked_by_policy={},
        contacts_per_resolved_case=[],
        max_touches_respected_rate=1.0,
        cases_in_exception_queue=0,
        exception_queue_all_triaged=True,
        audit_chain_verified=True,
        replay_equality_passed=True,
    )


@given(n_treated=st.integers(1, 200), n_control=st.integers(1, 200), data=st.data())
def test_the_not_significant_marker_appears_exactly_when_the_result_is_not_significant(
    n_treated: int, n_control: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(0, n_treated))
    x_control = data.draw(st.integers(0, n_control))
    report = build_report(_inputs(n_treated, x_treated, n_control, x_control))
    block = render_headline_block(report)

    if report.significance.significant:
        assert "NOT STATISTICALLY SIGNIFICANT" not in block
    else:
        assert "NOT STATISTICALLY SIGNIFICANT" in block


@given(n_treated=st.integers(1, 200), n_control=st.integers(1, 200), data=st.data())
def test_cost_per_rupee_recovered_is_defined_iff_incremental_is_positive(
    n_treated: int, n_control: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(0, n_treated))
    x_control = data.draw(st.integers(0, n_control))
    report = build_report(_inputs(n_treated, x_treated, n_control, x_control))

    if report.incremental_inr > 0:
        assert report.cost_per_inr_recovered is not None
    else:
        assert report.cost_per_inr_recovered is None


@given(n_treated=st.integers(1, 200), n_control=st.integers(1, 200), data=st.data())
def test_build_report_and_render_are_pure_and_deterministic(
    n_treated: int, n_control: int, data: st.DataObject
) -> None:
    x_treated = data.draw(st.integers(0, n_treated))
    x_control = data.draw(st.integers(0, n_control))
    inputs = _inputs(n_treated, x_treated, n_control, x_control)

    first = render_headline_block(build_report(inputs))
    second = render_headline_block(build_report(inputs))

    assert first == second
