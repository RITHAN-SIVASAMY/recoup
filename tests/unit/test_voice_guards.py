"""CON-03/FR-10.5/FR-10.6: distress, dispute, legal keywords, low ASR
confidence, and silence all trigger a guard — never improvise past them.
"""

from __future__ import annotations

import pytest

from recoup.voice.guards import MIN_ASR_CONFIDENCE, check_guards

pytestmark = pytest.mark.unit


def test_silence_triggers_the_silence_guard() -> None:
    trigger = check_guards(None, asr_confidence=None, silence=True)
    assert trigger is not None
    assert trigger.reason == "silence"


def test_an_empty_utterance_triggers_the_silence_guard() -> None:
    trigger = check_guards("   ", asr_confidence=0.9)
    assert trigger is not None
    assert trigger.reason == "silence"


def test_low_asr_confidence_triggers_before_any_keyword_scan() -> None:
    trigger = check_guards("haan main pay kar dunga", asr_confidence=MIN_ASR_CONFIDENCE - 0.01)
    assert trigger is not None
    assert trigger.reason == "low_confidence"


def test_sufficient_confidence_does_not_trigger_on_ordinary_speech() -> None:
    assert check_guards("haan main Friday tak pay kar dunga", asr_confidence=0.9) is None


@pytest.mark.parametrize(
    ("utterance", "expected_reason"),
    [
        ("I can't take this anymore, I feel so hopeless", "distress"),
        ("this is fraudulent, I never ordered this", "dispute"),
        ("maine nahi kiya yeh transaction, galat charge hai", "dispute"),
        ("I'm going to call my lawyer about this", "legal"),
        ("this is harassment, stop calling me", "hostility"),
    ],
)
def test_flags_the_correct_guard_category(utterance: str, expected_reason: str) -> None:
    trigger = check_guards(utterance, asr_confidence=0.95)
    assert trigger is not None
    assert trigger.reason == expected_reason


def test_a_calm_ordinary_reply_never_triggers_any_guard() -> None:
    assert check_guards("theek hai, main dekh leta hoon", asr_confidence=0.9) is None


def test_a_polite_opt_out_request_never_triggers_the_hostility_guard() -> None:
    # Regression: "stop calling me" used to be in the hostility pattern list
    # and swallowed every opt-out request into a safe-exit apology instead
    # of voice/intent.py's calm wants_opt_out routing (FR-10.3).
    assert check_guards("please stop calling me", asr_confidence=0.95) is None
    assert check_guards("can you please stop calling me about this", asr_confidence=0.95) is None
