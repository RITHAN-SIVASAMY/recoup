"""ADR-0005: `expand_query_to_event_types` is a pure keyword lookup — no
network, no model call. It only ever narrows retrieval; an unmatched
question must fall back to the full-text search rather than filtering
everything out.
"""

from __future__ import annotations

import pytest

from recoup.audit.retrieval import expand_query_to_event_types

pytestmark = pytest.mark.unit


def test_a_question_with_no_known_keyword_expands_to_nothing() -> None:
    assert expand_query_to_event_types("what is the weather today") == frozenset()


def test_call_keyword_expands_to_voice_event_types() -> None:
    result = expand_query_to_event_types("Did anyone call the customer?")
    assert "voice.call_started" in result
    assert "voice.call_ended" in result


def test_promise_keyword_expands_to_ptp_event_types() -> None:
    result = expand_query_to_event_types("What did the customer promise to pay?")
    assert "ptp.captured" in result
    assert "ptp.broken" in result


def test_matching_is_case_insensitive() -> None:
    assert expand_query_to_event_types("WAS THE CUSTOMER CALLED") == expand_query_to_event_types(
        "was the customer called"
    )


def test_multiple_keywords_union_their_event_types() -> None:
    result = expand_query_to_event_types("was a payment promised")
    assert "payment.recovered" in result
    assert "ptp.captured" in result
