"""Chaos suite placeholder — real failure-injection scenarios need the execution layer."""

from __future__ import annotations

import pytest


@pytest.mark.chaos
@pytest.mark.skip(
    reason="Chaos scenarios need the execution layer (Phase 06) and are built out in Phase 11."
)
def test_chaos_suite_not_yet_implemented() -> None:
    pass
