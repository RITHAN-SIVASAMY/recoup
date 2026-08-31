"""Property test: any non-negative seed round-trips through Settings unchanged."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.settings import Settings

pytestmark = pytest.mark.property


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_seed_field_accepts_any_non_negative_int(seed: int) -> None:
    assert Settings(_env_file=None, recoup_seed=seed).recoup_seed == seed
