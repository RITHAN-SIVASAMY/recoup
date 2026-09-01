"""Deterministic, bounded intent classification — the graph decides where a
call goes, never the classifier's own judgment beyond a fixed label set.
"""

from __future__ import annotations

import pytest

from recoup.voice.intent import classify_intent

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("please stop calling me", "wants_opt_out"),
        ("mujhe is baare mein call mat karo", "wants_opt_out"),
        ("can I talk to a human please", "wants_human"),
        ("mujhe ek insaan se baat karni hai", "wants_human"),
        ("I can't pay right now, there's a problem", "has_objection"),
        ("haan main payment kar doonga", "wants_to_pay"),
        ("yes that's correct", "confirms"),
        ("thik hai, sahi hai", "confirms"),
        ("sure, fine", "acknowledges"),
    ],
)
def test_classifies_the_expected_intent(utterance: str, expected: str) -> None:
    assert classify_intent(utterance) == expected


def test_an_unrelated_utterance_classifies_as_other() -> None:
    assert classify_intent("what's the weather like today") == "other"


def test_opt_out_takes_priority_over_a_co_occurring_objection() -> None:
    assert classify_intent("stop, I can't pay anyway, there's a problem") == "wants_opt_out"
