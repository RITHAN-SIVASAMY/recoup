"""FR-13.1/13.3/13.4: stratified assignment, exclusions, and amount banding."""

from __future__ import annotations

from decimal import Decimal

import pytest

from recoup.measurement.cohort import (
    CaseForAssignment,
    Stratum,
    amount_band,
    assign_cohorts,
    stratum_for,
)

pytestmark = pytest.mark.unit

_SALT = "test-salt-v1"
_VALUE_CAP = Decimal("50000")


@pytest.mark.parametrize(
    ("amount", "expected_band"),
    [
        (Decimal("1"), "under_1k"),
        (Decimal("999.99"), "under_1k"),
        (Decimal("1000"), "1k_10k"),
        (Decimal("9999.99"), "1k_10k"),
        (Decimal("10000"), "10k_1l"),
        (Decimal("99999.99"), "10k_1l"),
        (Decimal("100000"), "over_1l"),
        (Decimal("500000"), "over_1l"),
    ],
)
def test_amount_band_boundaries(amount: Decimal, expected_band: str) -> None:
    assert amount_band(amount) == expected_band


def test_stratum_for_uses_source_type_and_merchant_id_as_the_pre_scoring_proxies() -> None:
    case = CaseForAssignment(
        case_id="c1",
        source_type="payment_failure",
        amount_at_risk=Decimal("500"),
        merchant_id="demo-d2c",
    )
    assert stratum_for(case) == Stratum(
        root_cause_proxy="payment_failure", amount_band="under_1k", merchant_segment="demo-d2c"
    )


def test_a_case_above_the_value_cap_is_always_treatment_and_excluded() -> None:
    cases = [
        CaseForAssignment(
            case_id="high-value",
            source_type="receivable_overdue",
            amount_at_risk=Decimal("500000"),
            merchant_id="demo-b2b",
        )
    ]
    [assignment] = assign_cohorts(
        cases, holdout_rate=Decimal("1.0"), value_cap_inr=_VALUE_CAP, salt=_SALT
    )
    # holdout_rate=1.0 would put every eligible case in control -- proving this
    # case is exempt regardless of the rate, not just lucky under a low rate.
    assert assignment.cohort == "treatment"
    assert assignment.excluded_from_control is True
    assert assignment.exclusion_reason is not None


def test_a_risk_declined_case_is_always_treatment_and_excluded() -> None:
    cases = [
        CaseForAssignment(
            case_id="risky",
            source_type="payment_failure",
            amount_at_risk=Decimal("500"),
            merchant_id="demo-d2c",
            error_reason="risk_declined",
        )
    ]
    [assignment] = assign_cohorts(
        cases, holdout_rate=Decimal("1.0"), value_cap_inr=_VALUE_CAP, salt=_SALT
    )
    assert assignment.cohort == "treatment"
    assert assignment.excluded_from_control is True
    assert "risk_declined" in (assignment.exclusion_reason or "")


def test_a_normal_decline_reason_is_not_treated_as_legal_risk() -> None:
    cases = [
        CaseForAssignment(
            case_id="ordinary",
            source_type="payment_failure",
            amount_at_risk=Decimal("500"),
            merchant_id="demo-d2c",
            error_reason="insufficient_funds",
        )
    ]
    [assignment] = assign_cohorts(
        cases, holdout_rate=Decimal("1.0"), value_cap_inr=_VALUE_CAP, salt=_SALT
    )
    assert assignment.excluded_from_control is False
    assert assignment.cohort == "control"  # rate=1.0 and not excluded -> must be control


def test_a_stratum_splits_at_exactly_the_configured_rate_not_merely_in_expectation() -> None:
    cases = [
        CaseForAssignment(
            case_id=f"case-{i:03d}",
            source_type="payment_failure",
            amount_at_risk=Decimal("500"),
            merchant_id="demo-d2c",
        )
        for i in range(100)
    ]
    assignments = assign_cohorts(
        cases, holdout_rate=Decimal("0.20"), value_cap_inr=_VALUE_CAP, salt=_SALT
    )
    n_control = sum(1 for a in assignments if a.cohort == "control")
    assert n_control == 20  # exactly 20% of this single 100-case stratum, deterministically


def test_assignment_is_deterministic_across_repeated_calls_with_the_same_salt() -> None:
    cases = [
        CaseForAssignment(
            case_id=f"case-{i:03d}",
            source_type="checkout_abandonment",
            amount_at_risk=Decimal("500"),
            merchant_id="demo-d2c",
        )
        for i in range(50)
    ]
    first = assign_cohorts(
        cases, holdout_rate=Decimal("0.20"), value_cap_inr=_VALUE_CAP, salt=_SALT
    )
    second = assign_cohorts(
        cases, holdout_rate=Decimal("0.20"), value_cap_inr=_VALUE_CAP, salt=_SALT
    )
    assert [(a.case_id, a.cohort) for a in first] == [(a.case_id, a.cohort) for a in second]


def test_a_different_salt_produces_a_different_split() -> None:
    cases = [
        CaseForAssignment(
            case_id=f"case-{i:03d}",
            source_type="checkout_abandonment",
            amount_at_risk=Decimal("500"),
            merchant_id="demo-d2c",
        )
        for i in range(50)
    ]
    a = assign_cohorts(cases, holdout_rate=Decimal("0.20"), value_cap_inr=_VALUE_CAP, salt=_SALT)
    b = assign_cohorts(
        cases, holdout_rate=Decimal("0.20"), value_cap_inr=_VALUE_CAP, salt="other-salt"
    )
    assert [x.cohort for x in a] != [x.cohort for x in b]


def test_invalid_holdout_rate_raises() -> None:
    with pytest.raises(ValueError, match="holdout_rate"):
        assign_cohorts([], holdout_rate=Decimal("1.5"), value_cap_inr=_VALUE_CAP, salt=_SALT)
