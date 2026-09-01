"""FR-13.6/13.9/13.10: the headline block matches §9's layout and numbers,
Indian-style ₹ grouping is exact, and a non-significant result is never
rendered without its explicit marker (rule 9)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from recoup.measurement.report import (
    BatchInputs,
    BreakdownRow,
    build_report,
    format_inr_whole,
    render_headline_block,
    to_json,
    to_markdown,
)
from recoup.measurement.stats import two_proportion_z_test

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("0"), "₹ 0"),
        (Decimal("100"), "₹ 100"),
        (Decimal("999"), "₹ 999"),
        (Decimal("1000"), "₹ 1,000"),
        (Decimal("100000"), "₹ 1,00,000"),
        (Decimal("391200"), "₹ 3,91,200"),
        (Decimal("1248300"), "₹ 12,48,300"),
        (Decimal("-500"), "₹ -500"),
    ],
)
def test_indian_digit_grouping(amount: Decimal, expected: str) -> None:
    assert format_inr_whole(amount) == expected


def _sample_inputs(*, significant: bool) -> BatchInputs:
    if significant:
        n_treated, x_treated, n_control, x_control = 400, 248, 100, 40
    else:
        n_treated, x_treated, n_control, x_control = 40, 12, 10, 3

    return BatchInputs(
        batch_id="b_test",
        seed=42,
        n_cases_total=n_treated + n_control,
        at_risk_inr=Decimal("1248300"),
        raw_recovered_inr=Decimal("391200"),
        n_treated=n_treated,
        x_treated=x_treated,
        n_control=n_control,
        x_control=x_control,
        mean_recovered_value_inr=Decimal("500"),
        treated_outcomes=[1.0] * x_treated + [0.0] * (n_treated - x_treated),
        treated_covariates=[0.5] * n_treated,
        control_outcomes=[1.0] * x_control + [0.0] * (n_control - x_control),
        control_covariates=[0.5] * n_control,
        spend_on_contact_inr=Decimal("1842"),
        saved_by_not_contacting_inr=Decimal("42600"),
        actions_blocked_by_policy={"quiet_hours": 14, "opt_out": 9, "mandate": 11, "cap": 3},
        contacts_per_resolved_case=[1, 2, 2, 1, 3],
        max_touches_respected_rate=1.0,
        cases_in_exception_queue=6,
        exception_queue_all_triaged=True,
        audit_chain_verified=True,
        replay_equality_passed=True,
    )


def test_a_significant_batch_renders_without_the_not_significant_marker() -> None:
    report = build_report(_sample_inputs(significant=True))
    block = render_headline_block(report)

    assert report.significance.significant is True
    assert "NOT STATISTICALLY SIGNIFICANT" not in block
    assert "RECOUP · BATCH b_test · seed 42 · 500 cases" in block
    assert "At risk                        ₹ 12,48,300" in block
    assert "MDE =" in block


def test_a_non_significant_batch_always_carries_the_marker_next_to_mde() -> None:
    report = build_report(_sample_inputs(significant=False))
    block = render_headline_block(report)

    assert report.significance.significant is False
    assert "NOT STATISTICALLY SIGNIFICANT" in block
    assert "MDE =" in block  # the honest bound is still printed even though the result is null


def test_cost_per_rupee_recovered_is_undefined_not_zero_when_incremental_is_non_positive() -> None:
    inputs = _sample_inputs(significant=False)
    # force zero lift: identical resolution rates
    inputs = BatchInputs(
        **{
            **inputs.__dict__,
            "n_treated": 100,
            "x_treated": 50,
            "n_control": 100,
            "x_control": 50,
            "treated_outcomes": [1.0] * 50 + [0.0] * 50,
            "treated_covariates": [0.5] * 100,
            "control_outcomes": [1.0] * 50 + [0.0] * 50,
            "control_covariates": [0.5] * 100,
        }
    )
    report = build_report(inputs)

    assert report.incremental_inr == Decimal("0")
    assert report.cost_per_inr_recovered is None
    block = render_headline_block(report)
    assert "undefined (no incremental recovery)" in block


def test_json_export_round_trips_the_key_headline_numbers() -> None:
    import json

    report = build_report(_sample_inputs(significant=True))
    payload = json.loads(to_json(report))

    assert payload["batch_id"] == "b_test"
    assert payload["significant"] is True
    assert payload["n_treated"] == 400
    assert payload["n_control"] == 100
    assert Decimal(payload["incremental_inr"]) == report.incremental_inr


def test_markdown_export_contains_the_headline_and_breakdown_table() -> None:
    inputs = _sample_inputs(significant=True)
    breakdown_result = two_proportion_z_test(
        n_treated=100, x_treated=40, n_control=30, x_control=10
    )
    inputs = BatchInputs(
        **{
            **inputs.__dict__,
            "breakdowns": [
                BreakdownRow(dimension="root_cause", key="payment_failure", result=breakdown_result)
            ],
        }
    )
    report = build_report(inputs)
    markdown = to_markdown(report)

    assert "Incremental recovered" in markdown
    assert "| root_cause | payment_failure |" in markdown


def test_negative_lift_is_reported_without_softening() -> None:
    inputs = _sample_inputs(significant=False)
    inputs = BatchInputs(
        **{
            **inputs.__dict__,
            "n_treated": 100,
            "x_treated": 20,
            "n_control": 100,
            "x_control": 40,
            "treated_outcomes": [1.0] * 20 + [0.0] * 80,
            "treated_covariates": [0.5] * 100,
            "control_outcomes": [1.0] * 40 + [0.0] * 60,
            "control_covariates": [0.5] * 100,
        }
    )
    report = build_report(inputs)

    assert report.significance.lift < 0
    assert report.incremental_inr < 0
    block = render_headline_block(report)
    assert "-" in block  # a negative figure is printed plainly, never hidden or floored at 0
