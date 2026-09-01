"""The ground-truth resolution roll: deterministic per (seed, case_id), and
picks the right probability depending on whether the case was contacted."""

from __future__ import annotations

import pytest

from recoup.data.generate import GroundTruth
from recoup.data.simulate import resolution_probability, simulate_resolved

pytestmark = pytest.mark.unit

_GT = GroundTruth(
    provider_event_id="prov-1",
    p_self_heal=0.20,
    p_recover_by_channel={"sms": 0.30, "whatsapp": 0.40, "email": 0.15, "voice": 0.55},
)


def test_an_uncontacted_case_uses_self_heal_probability() -> None:
    assert resolution_probability(_GT, None) == 0.20


def test_a_contacted_case_uses_its_channels_probability() -> None:
    assert resolution_probability(_GT, "voice") == 0.55
    assert resolution_probability(_GT, "email") == 0.15


def test_simulate_resolved_is_deterministic_for_the_same_seed_and_case() -> None:
    first = simulate_resolved(case_id="case-1", seed=42, probability=0.5)
    second = simulate_resolved(case_id="case-1", seed=42, probability=0.5)
    assert first == second


def test_simulate_resolved_never_true_at_zero_probability() -> None:
    for i in range(200):
        assert simulate_resolved(case_id=f"case-{i}", seed=1, probability=0.0) is False


def test_simulate_resolved_always_true_at_probability_one() -> None:
    for i in range(200):
        assert simulate_resolved(case_id=f"case-{i}", seed=1, probability=1.0) is True


def test_different_cases_can_get_different_outcomes_at_the_same_probability() -> None:
    outcomes = {simulate_resolved(case_id=f"case-{i}", seed=7, probability=0.5) for i in range(50)}
    assert outcomes == {True, False}  # some resolve, some don't -- not a constant function
