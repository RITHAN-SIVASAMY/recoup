"""SEC-DATA-04, property-tested: no single-character mutation of a validly
signed recovery link token ever verifies. This is what "HMAC-signed" is
actually for — the property test is what proves tampering resistance holds
for arbitrary tokens and arbitrary mutations, not just the one example in
tests/unit/test_links.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.execution.links import generate_link_token, verify_link_token

pytestmark = pytest.mark.property

_SECRET = "test-signing-secret"
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)

_case_ids = st.text(alphabet="0123456789ABCDEFGHJKMNPQRSTVWXYZ", min_size=26, max_size=26)
_ladder_steps = st.integers(min_value=1, max_value=10)


@given(case_id=_case_ids, ladder_step=_ladder_steps)
def test_a_genuinely_generated_token_always_verifies(case_id: str, ladder_step: int) -> None:
    token = generate_link_token(
        case_id, ladder_step, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    payload = verify_link_token(token, secret=_SECRET, now=_NOW)
    assert payload is not None
    assert payload.case_id == case_id
    assert payload.ladder_step == ladder_step


@given(
    case_id=_case_ids,
    ladder_step=_ladder_steps,
    mutation_index=st.integers(min_value=0),
    replacement=st.characters(min_codepoint=33, max_codepoint=126),
)
def test_mutating_any_single_character_never_still_verifies(
    case_id: str, ladder_step: int, mutation_index: int, replacement: str
) -> None:
    token = generate_link_token(
        case_id, ladder_step, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    index = mutation_index % len(token)
    if token[index] == replacement:
        return  # not actually a mutation; nothing to prove here
    mutated = token[:index] + replacement + token[index + 1 :]
    assert verify_link_token(mutated, secret=_SECRET, now=_NOW) is None
