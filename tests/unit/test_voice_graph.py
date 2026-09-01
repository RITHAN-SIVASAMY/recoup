"""CON-02: disclosure is a mandatory, unskippable node. See also
tests/property/test_voice_graph_invariants.py for the general (Hypothesis)
proof over arbitrary intent sequences — this is the specific, named test
docs/06-COMPLIANCE-MATRIX.md cites as CON-02's proof.
"""

from __future__ import annotations

import pytest

from recoup.voice.graph import ALLOWED_TRANSITIONS, START_NODE, next_node

pytestmark = pytest.mark.unit


def test_disclosure_is_unskippable() -> None:
    # identify's only real edges are disclose or an early exit (opt-out,
    # human transfer, safe-exit) — "purpose" and everything past it is not
    # reachable from identify under any intent, for any reason.
    assert START_NODE == "identify"
    identify_edges = ALLOWED_TRANSITIONS["identify"]
    assert "disclose" in identify_edges
    assert "purpose" not in identify_edges
    assert "offer_resolution" not in identify_edges
    assert "capture_ptp" not in identify_edges
    assert "confirm" not in identify_edges

    for intent in ("acknowledges", "wants_to_pay", "has_objection", "confirms", "other"):
        assert next_node("identify", intent) in {"disclose", "safe_exit"}  # type: ignore[arg-type]


def test_disclosure_is_the_only_way_to_reach_purpose() -> None:
    disclose_edges = ALLOWED_TRANSITIONS["disclose"]
    assert "purpose" in disclose_edges
    for node, edges in ALLOWED_TRANSITIONS.items():
        if node != "disclose":
            assert "purpose" not in edges, f"{node!r} can reach purpose without disclose"
