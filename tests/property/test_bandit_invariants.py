"""FR-9.2's core constraint, property-tested: the bandit's chosen arm is
always a member of the policy-permitted set — never a channel that policy
denied or that was never offered to it. `thompson_select` only ever samples
from `permitted_arms`, so this is true by construction; the property test
is what makes that provable rather than merely asserted in a docstring.
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.domain.models import Channel
from recoup.execution.bandit import apply_channel_fatigue, thompson_select

pytestmark = pytest.mark.property

_CHANNELS: list[Channel] = ["sms", "whatsapp", "email", "voice"]

_channel_sets = st.sets(st.sampled_from(_CHANNELS), min_size=1, max_size=4).map(frozenset)
_posteriors = st.dictionaries(
    st.sampled_from(_CHANNELS),
    st.tuples(
        st.floats(min_value=0.01, max_value=1000, allow_nan=False),
        st.floats(min_value=0.01, max_value=1000, allow_nan=False),
    ),
    max_size=4,
)
_seeds = st.integers(min_value=0, max_value=2**32 - 1)


@given(permitted=_channel_sets, posteriors=_posteriors, seed=_seeds)
def test_the_chosen_arm_is_always_in_the_permitted_set(
    permitted: frozenset[Channel], posteriors: dict[Channel, tuple[float, float]], seed: int
) -> None:
    chosen = thompson_select(posteriors, permitted, random.Random(seed))
    assert chosen in permitted


@given(
    permitted=_channel_sets,
    denied=st.sets(st.sampled_from(_CHANNELS), max_size=4),
    seed=_seeds,
)
def test_a_denied_arm_outside_permitted_is_never_chosen_no_matter_its_posterior(
    permitted: frozenset[Channel], denied: set[Channel], seed: int
) -> None:
    # A "denied" arm gets a wildly favorable posterior — if it could ever leak
    # through, a generous Beta(1000, 1) would be the arm most likely to expose it.
    denied_only = frozenset(denied) - permitted
    posteriors = dict.fromkeys(denied_only, (1000.0, 1.0)) | dict.fromkeys(permitted, (1.0, 1.0))
    if not permitted:
        return  # nothing to select from; select_arm's ValueError path is covered separately
    chosen = thompson_select(posteriors, permitted, random.Random(seed))
    assert chosen not in denied_only


def test_selecting_from_an_empty_permitted_set_raises_rather_than_guessing() -> None:
    with pytest.raises(ValueError, match="no permitted arms"):
        thompson_select({}, frozenset(), random.Random(0))


@given(permitted=_channel_sets)
def test_channel_fatigue_never_widens_the_permitted_set(permitted: frozenset[Channel]) -> None:
    last_two_engaged = {arm: [False, False] for arm in permitted}
    narrowed = apply_channel_fatigue(permitted, last_two_engaged)
    assert narrowed <= permitted


@given(permitted=_channel_sets)
def test_channel_fatigue_never_empties_the_set_entirely(permitted: frozenset[Channel]) -> None:
    last_two_engaged = {arm: [False, False] for arm in permitted}
    narrowed = apply_channel_fatigue(permitted, last_two_engaged)
    assert len(narrowed) >= 1 or not permitted
