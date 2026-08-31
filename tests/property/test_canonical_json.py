"""Property: canonical JSON (and therefore its hash) is invariant to key order."""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.domain.canonical import canonical_json

pytestmark = pytest.mark.property

_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.text(max_size=20),
)


@st.composite
def _flat_dict(draw: st.DrawFn) -> dict[str, object]:
    keys = draw(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=8, unique=True))
    return {key: draw(_json_scalars) for key in keys}


@given(payload=_flat_dict())
def test_canonical_json_is_invariant_to_key_order(payload: dict[str, object]) -> None:
    reordered = dict(reversed(list(payload.items())))
    left = hashlib.sha256(canonical_json(payload)).hexdigest()
    right = hashlib.sha256(canonical_json(reordered)).hexdigest()
    assert left == right


def test_canonical_json_serializes_decimal_as_a_string() -> None:
    encoded = canonical_json({"amount_inr": Decimal("199.50")})
    assert b'"199.50"' in encoded
