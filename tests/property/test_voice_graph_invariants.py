"""CON-02/FR-10.1, property-tested: disclosure is provably unskippable —
no sequence of customer intents can ever reach `purpose` (or anything past
it) without the walk having passed through `disclose` first — and every
node/intent combination, including ones with no specific route defined,
always resolves to a real graph edge, never a crash or an invented node
(FR-10.5's "never improvise").
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.voice.graph import (
    ALLOWED_TRANSITIONS,
    START_NODE,
    TERMINAL_NODES,
    CustomerIntent,
    GraphNode,
    next_node,
)

pytestmark = pytest.mark.property

_ALL_NODES: list[GraphNode] = list(ALLOWED_TRANSITIONS.keys())
_ALL_INTENTS: list[CustomerIntent] = [
    "acknowledges",
    "wants_to_pay",
    "has_objection",
    "wants_opt_out",
    "wants_human",
    "confirms",
    "other",
]
_PRE_DISCLOSURE_NODES: frozenset[GraphNode] = frozenset(
    {"purpose", "offer_resolution", "capture_ptp", "confirm"}
)


@given(intent=st.sampled_from(_ALL_INTENTS))
def test_identify_can_never_jump_straight_to_purpose_or_beyond(intent: CustomerIntent) -> None:
    result = next_node("identify", intent)
    assert result not in _PRE_DISCLOSURE_NODES


@given(intent_sequence=st.lists(st.sampled_from(_ALL_INTENTS), min_size=1, max_size=12))
def test_disclosure_is_unskippable_over_any_walk(intent_sequence: list[CustomerIntent]) -> None:
    node: GraphNode = START_NODE
    visited: list[GraphNode] = [node]
    for intent in intent_sequence:
        if node in TERMINAL_NODES:
            break
        node = next_node(node, intent)
        visited.append(node)
        if node in _PRE_DISCLOSURE_NODES:
            assert (
                "disclose" in visited
            ), f"reached {node!r} without ever passing through disclose; path was {visited}"


@given(node=st.sampled_from(_ALL_NODES), intent=st.sampled_from(_ALL_INTENTS))
def test_every_node_intent_pair_resolves_to_a_real_edge_never_a_crash(
    node: GraphNode, intent: CustomerIntent
) -> None:
    result = next_node(node, intent)
    assert result in ALLOWED_TRANSITIONS  # a real node
    if node in TERMINAL_NODES:
        return  # terminal nodes have no outgoing edges; nothing to route
    assert result in ALLOWED_TRANSITIONS[node] or result == "safe_exit"


@given(node=st.sampled_from(_ALL_NODES))
def test_an_unrecognized_intent_never_fabricates_a_confirmed_commitment(node: GraphNode) -> None:
    # "other" (an out-of-graph utterance) never fabricates progress toward a
    # commitment by itself — reaching "confirm" always requires the
    # extractor's own explicit override in voice/runtime.py, never routing.
    assert next_node(node, "other") != "confirm"
