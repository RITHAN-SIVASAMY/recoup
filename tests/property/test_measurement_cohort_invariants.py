"""FR-13.2/13.4, property-tested: no matter what batch of cases is generated,
an excluded case can never land in control, every case is assigned exactly
once, and assignment is a pure deterministic function of its inputs."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.measurement.cohort import CaseForAssignment, assign_cohorts

pytestmark = pytest.mark.property

_source_types = st.sampled_from(
    ["payment_failure", "checkout_abandonment", "mandate_failure", "receivable_overdue"]
)
_merchants = st.sampled_from(["demo-d2c", "demo-subscription", "demo-b2b"])
_error_reasons = st.sampled_from([None, "insufficient_funds", "risk_declined", "card_expired"])
_amounts = st.decimals(
    min_value=Decimal("1"), max_value=Decimal("600000"), places=2, allow_nan=False
)

_case = st.builds(
    CaseForAssignment,
    case_id=st.uuids().map(str),
    source_type=_source_types,
    amount_at_risk=_amounts,
    merchant_id=_merchants,
    error_reason=_error_reasons,
)
_batch = st.lists(_case, min_size=0, max_size=60, unique_by=lambda c: c.case_id)
_holdout_rate = st.decimals(min_value=Decimal("0"), max_value=Decimal("1"), places=2)


@given(cases=_batch, holdout_rate=_holdout_rate)
def test_an_excluded_case_never_lands_in_control(
    cases: list[CaseForAssignment], holdout_rate: Decimal
) -> None:
    assignments = assign_cohorts(
        cases, holdout_rate=holdout_rate, value_cap_inr=Decimal("50000"), salt="prop-salt"
    )
    for assignment in assignments:
        if assignment.excluded_from_control:
            assert assignment.cohort == "treatment"


@given(cases=_batch, holdout_rate=_holdout_rate)
def test_every_case_is_assigned_exactly_once(
    cases: list[CaseForAssignment], holdout_rate: Decimal
) -> None:
    assignments = assign_cohorts(
        cases, holdout_rate=holdout_rate, value_cap_inr=Decimal("50000"), salt="prop-salt"
    )
    assert sorted(a.case_id for a in assignments) == sorted(c.case_id for c in cases)


@given(cases=_batch, holdout_rate=_holdout_rate)
def test_assignment_is_a_pure_function_of_its_inputs(
    cases: list[CaseForAssignment], holdout_rate: Decimal
) -> None:
    first = assign_cohorts(
        cases, holdout_rate=holdout_rate, value_cap_inr=Decimal("50000"), salt="prop-salt"
    )
    second = assign_cohorts(
        cases, holdout_rate=holdout_rate, value_cap_inr=Decimal("50000"), salt="prop-salt"
    )
    assert [(a.case_id, a.cohort, a.excluded_from_control) for a in first] == [
        (a.case_id, a.cohort, a.excluded_from_control) for a in second
    ]


@given(cases=_batch, holdout_rate=_holdout_rate)
def test_a_case_above_the_value_cap_is_never_control(
    cases: list[CaseForAssignment], holdout_rate: Decimal
) -> None:
    value_cap = Decimal("50000")
    assignments = assign_cohorts(
        cases, holdout_rate=holdout_rate, value_cap_inr=value_cap, salt="prop-salt"
    )
    by_id = {c.case_id: c for c in cases}
    for assignment in assignments:
        if by_id[assignment.case_id].amount_at_risk > value_cap:
            assert assignment.cohort == "treatment"
