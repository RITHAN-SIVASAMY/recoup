"""FR-10.1/CON-02: the bounded Hinglish dialogue graph. A finite state
machine with an explicit edge list — there is no code path that can reach
`purpose` (or anything past it) without first passing through `disclose`,
which is what makes disclosure "provably unskippable" rather than merely
policy: `disclose` is the only non-exit edge out of `identify`, full stop.
Opt-out and human-transfer are reachable from every non-terminal node
(FR-10.3: "honoured within the same call", not just when first offered).
No open-ended negotiation: every node's outgoing edges are fixed here, and
`next_node` refuses any edge not listed.
"""

from __future__ import annotations

from typing import Literal

GraphNode = Literal[
    "identify",
    "disclose",
    "purpose",
    "offer_resolution",
    "capture_ptp",
    "objection",
    "opt_out",
    "human_transfer",
    "confirm",
    "close",
    "safe_exit",
]

CustomerIntent = Literal[
    "acknowledges",
    "wants_to_pay",
    "has_objection",
    "wants_opt_out",
    "wants_human",
    "confirms",
    "other",
]

START_NODE: GraphNode = "identify"
TERMINAL_NODES: frozenset[GraphNode] = frozenset({"close", "safe_exit"})


def _edges(*nodes: GraphNode) -> frozenset[GraphNode]:
    return frozenset(nodes)


_EXITS: tuple[GraphNode, ...] = ("opt_out", "human_transfer", "safe_exit")

# The graph itself. Every node's real allowed next-nodes — nothing outside
# this set is ever reachable, regardless of what an LLM or a guard proposes.
ALLOWED_TRANSITIONS: dict[GraphNode, frozenset[GraphNode]] = {
    "identify": _edges("disclose", *_EXITS),
    "disclose": _edges("purpose", *_EXITS),
    "purpose": _edges("offer_resolution", *_EXITS),
    "offer_resolution": _edges("capture_ptp", "objection", *_EXITS),
    "capture_ptp": _edges("confirm", "objection", *_EXITS),
    "objection": _edges("offer_resolution", "close", *_EXITS),
    "opt_out": _edges("close"),
    "human_transfer": _edges("close"),
    "confirm": _edges("close"),
    "close": _edges(),
    "safe_exit": _edges(),
}

# Hinglish (code-mixed) scripted lines per node — natural, not translated
# word-for-word; disclosure and opt-out phrasing exists precisely because
# CON-02 requires it every call, not just when asked.
SYSTEM_SCRIPTS: dict[GraphNode, str] = {
    "identify": "Namaste! Main {merchant_name} ki taraf se baat kar raha hoon.",
    "disclose": (
        "Main ek automated assistant hoon, {merchant_name} ke liye kaam karta hoon. "
        "Aap kisi bhi time 'stop' bol kar opt-out kar sakte hain, ya 'human' bol kar "
        "kisi insaan se baat kar sakte hain."
    ),
    "purpose": "Aapke ek recent payment mein kuch issue aaya tha, uske baare mein baat karni thi.",
    "offer_resolution": (
        "Kya aap ise abhi resolve karna chahenge, ya koi date bata sakte hain jab aap pay kar payenge?"
    ),
    "capture_ptp": "Theek hai, please bataiye aap kab tak aur kitna pay kar payenge.",
    "objection": "Samajh sakta hoon. Kya aap bata sakte hain kya dikkat aa rahi hai?",
    "opt_out": "Bilkul, hum aapko is baare mein dobara contact nahi karenge.",
    "human_transfer": "Zaroor, main aapko ek team member se connect kar raha hoon.",
    "confirm": "Toh confirm kar raha hoon — {ptp_summary}. Sahi hai?",
    "close": "Dhanyavaad, aapka time dene ke liye. Have a good day!",
    "safe_exit": (
        "Mujhe maaf kijiye, main is baare mein aage madad nahi kar sakta. "
        "Main aapko ek link ya callback arrange kar deta hoon."
    ),
}

_SCRIPTED_ADVANCE: dict[GraphNode, GraphNode] = {
    "identify": "disclose",
    "disclose": "purpose",
    "purpose": "offer_resolution",
    "confirm": "close",
    "opt_out": "close",
    "human_transfer": "close",
}
_INTENT_ROUTES: dict[GraphNode, dict[CustomerIntent, GraphNode]] = {
    "offer_resolution": {
        "wants_to_pay": "capture_ptp",
        "acknowledges": "capture_ptp",
        "confirms": "capture_ptp",
        "has_objection": "objection",
        "other": "safe_exit",
    },
    "capture_ptp": {
        "acknowledges": "confirm",
        "confirms": "confirm",
        "wants_to_pay": "confirm",
        "has_objection": "objection",
        "other": "objection",
    },
    "objection": {
        "confirms": "offer_resolution",
        "acknowledges": "offer_resolution",
        "other": "safe_exit",
    },
}


def next_node(current: GraphNode, intent: CustomerIntent) -> GraphNode:
    """Pure routing: `current`'s real edges only, never anything an intent
    alone could talk its way into. Guards (`voice/guards.py`) override this
    entirely and force `safe_exit` before this function is ever consulted."""
    allowed = ALLOWED_TRANSITIONS[current]

    if intent == "wants_opt_out" and "opt_out" in allowed:
        return "opt_out"
    if intent == "wants_human" and "human_transfer" in allowed:
        return "human_transfer"

    proposed = _INTENT_ROUTES.get(current, {}).get(intent) or _SCRIPTED_ADVANCE.get(
        current, "safe_exit"
    )
    return proposed if proposed in allowed else "safe_exit"
