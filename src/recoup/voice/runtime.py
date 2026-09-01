"""FR-10.4: the turn loop and its audit trail. `advance_call` is the pure(ish)
core — no event-store I/O, only the one LLM call PTP extraction needs, and
fully injectable for tests — that decides where a call goes next; `run_call`
is the thin orchestrator that actually writes every turn, the PTP capture,
and any escalation exception through `EventStore.append`, so the transcript,
node path and outcome are hash-chained into the case's history by
construction, never by convention (FR-10.4's exact wording).

The offline/scripted path this module runs by default (a list of customer
utterances known in advance) is the phase's own cut line: "if live telephony
is fragile, render the call offline as an audio artifact against the same
graph" — `run_call` works identically whether utterances come from a script
or a real ASR stream turn by turn; nothing here assumes which.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from recoup.audit.event_store import EventStore
from recoup.domain.models import Actor, PromiseToPay
from recoup.llm.ptp import extract_ptp
from recoup.llm.schemas import PTPExtraction
from recoup.voice.graph import (
    START_NODE,
    SYSTEM_SCRIPTS,
    TERMINAL_NODES,
    CustomerIntent,
    GraphNode,
    next_node,
)
from recoup.voice.guards import check_guards
from recoup.voice.intent import classify_intent

PTP_CONFIDENCE_THRESHOLD = 0.7
_SYSTEM = Actor(kind="system", identifier="voice-runtime")
_MODEL_PTP = Actor(kind="model", identifier="claude-ptp-extractor")
_ESCALATING_GUARDS = frozenset({"distress", "dispute", "legal"})

IntentClassifier = Callable[[str], CustomerIntent]
PtpExtractor = Callable[[str, datetime], Awaitable[PTPExtraction | None]]


@dataclass(frozen=True)
class Turn:
    node: GraphNode
    system_utterance: str
    customer_utterance: str | None = None
    asr_confidence: float | None = None
    intent: CustomerIntent | None = None
    guard_triggered: str | None = None


@dataclass(frozen=True)
class CallState:
    case_id: str
    merchant_name: str
    node: GraphNode
    turns: tuple[Turn, ...]
    ptp: PromiseToPay | None = None
    needs_human_verification: bool = False

    @property
    def ended(self) -> bool:
        return self.node in TERMINAL_NODES

    @property
    def transcript(self) -> str:
        lines: list[str] = []
        for turn in self.turns:
            lines.append(f"assistant: {turn.system_utterance}")
            if turn.customer_utterance:
                lines.append(f"customer: {turn.customer_utterance}")
        return "\n".join(lines)

    @property
    def node_path(self) -> list[GraphNode]:
        return [turn.node for turn in self.turns]


def _render_script(node: GraphNode, *, merchant_name: str, ptp: PromiseToPay | None) -> str:
    if node == "confirm" and ptp is not None:
        summary = f"aap {ptp.amount_inr} rupees {ptp.date.date().isoformat()} tak pay karenge"
        return SYSTEM_SCRIPTS[node].format(ptp_summary=summary)
    return SYSTEM_SCRIPTS[node].format(merchant_name=merchant_name)


def start_call(case_id: str, merchant_name: str) -> CallState:
    first = Turn(
        node=START_NODE,
        system_utterance=_render_script(START_NODE, merchant_name=merchant_name, ptp=None),
    )
    return CallState(case_id=case_id, merchant_name=merchant_name, node=START_NODE, turns=(first,))


def _to_promise(extraction: PTPExtraction, *, now: datetime) -> PromiseToPay | None:
    if (
        not extraction.has_commitment
        or extraction.amount_inr is None
        or extraction.promised_date is None
    ):
        return None
    return PromiseToPay(
        amount_inr=extraction.amount_inr,
        date=datetime.combine(extraction.promised_date, datetime.min.time(), tzinfo=UTC),
        condition=extraction.condition,
        confidence=extraction.confidence,
    )


async def advance_call(
    state: CallState,
    *,
    customer_utterance: str | None,
    asr_confidence: float | None,
    silence: bool = False,
    now: datetime,
    classify: IntentClassifier = classify_intent,
    extractor: PtpExtractor = extract_ptp,
) -> CallState:
    """One turn: fills in the customer's reply to `state.node`'s script,
    decides the next node, and — if that reply is at `capture_ptp` — asks
    the extractor whether it contains an actual commitment. Never mutates
    `state`; always returns a new one."""
    if state.ended:
        return state

    current_turn = state.turns[-1]
    guard = check_guards(customer_utterance, asr_confidence=asr_confidence, silence=silence)

    if guard is not None:
        completed = replace(
            current_turn,
            customer_utterance=customer_utterance,
            asr_confidence=asr_confidence,
            guard_triggered=guard.reason,
        )
        return _transition(
            state, completed, "safe_exit", ptp=state.ptp, needs_human=state.needs_human_verification
        )

    assert customer_utterance is not None  # guard already handled the silence/None case
    intent = classify(customer_utterance)

    ptp = state.ptp
    needs_human = state.needs_human_verification
    target = next_node(state.node, intent)

    if state.node == "capture_ptp" and target not in {"opt_out", "human_transfer"}:
        extraction = await extractor(customer_utterance, now)
        if extraction is None:
            needs_human = True
            target = "objection"
        elif not extraction.has_commitment:
            target = "objection" if target == "confirm" else target
        elif extraction.confidence < PTP_CONFIDENCE_THRESHOLD:
            needs_human = True
            target = "objection"
        else:
            candidate = _to_promise(extraction, now=now)
            if candidate is None:
                needs_human = True
                target = "objection"
            else:
                ptp = candidate
                target = "confirm"

    completed = replace(
        current_turn,
        customer_utterance=customer_utterance,
        asr_confidence=asr_confidence,
        intent=intent,
    )
    return _transition(state, completed, target, ptp=ptp, needs_human=needs_human)


def _transition(
    state: CallState,
    completed_turn: Turn,
    target: GraphNode,
    *,
    ptp: PromiseToPay | None,
    needs_human: bool,
) -> CallState:
    turns = (*state.turns[:-1], completed_turn)
    if target not in TERMINAL_NODES:
        next_turn = Turn(
            node=target,
            system_utterance=_render_script(target, merchant_name=state.merchant_name, ptp=ptp),
        )
        turns = (*turns, next_turn)
    else:
        close_line = SYSTEM_SCRIPTS[target]
        turns = (*turns, Turn(node=target, system_utterance=close_line))
    return replace(state, node=target, turns=turns, ptp=ptp, needs_human_verification=needs_human)


async def run_call(
    event_store: EventStore,
    *,
    case_id: str,
    merchant_name: str,
    utterances: list[tuple[str, float]],
    now: datetime,
    classify: IntentClassifier = classify_intent,
    extractor: PtpExtractor = extract_ptp,
    audio_artifact_ref: str | None = None,
) -> CallState:
    """Runs a full call from a known list of `(utterance, asr_confidence)`
    pairs — the offline/scripted path (cut line) — writing every turn,
    escalating exception, and PTP capture to the event log as it goes.
    Stops early the moment the graph reaches a terminal node, exactly as a
    real turn-by-turn call would."""
    state = start_call(case_id, merchant_name)
    await event_store.append(
        case_id=case_id,
        event_type="voice.call_started",
        payload={"node": state.node, "audio_artifact_ref": audio_artifact_ref},
        actor=_SYSTEM,
    )

    for utterance, confidence in utterances:
        if state.ended:
            break
        turn_index = len(state.turns) - 1
        state = await advance_call(
            state,
            customer_utterance=utterance,
            asr_confidence=confidence,
            now=now,
            classify=classify,
            extractor=extractor,
        )
        completed = state.turns[turn_index]
        await event_store.append(
            case_id=case_id,
            event_type="voice.turn",
            payload={
                "node": completed.node,
                "system_utterance": completed.system_utterance,
                "customer_utterance": completed.customer_utterance,
                "asr_confidence": completed.asr_confidence,
                "intent": completed.intent,
                "guard_triggered": completed.guard_triggered,
            },
            actor=_SYSTEM,
        )
        if completed.guard_triggered in _ESCALATING_GUARDS:
            await event_store.append(
                case_id=case_id,
                event_type="case.exception",
                payload={
                    "source": "voice_guard",
                    "reason": completed.guard_triggered,
                    "node": completed.node,
                },
                actor=_SYSTEM,
            )

    if state.ptp is not None:
        await event_store.append(
            case_id=case_id,
            event_type="ptp.captured",
            payload={
                "amount_inr": state.ptp.amount_inr,
                "date": state.ptp.date,
                "condition": state.ptp.condition,
                "confidence": state.ptp.confidence,
            },
            actor=_MODEL_PTP,
        )
    elif state.needs_human_verification:
        await event_store.append(
            case_id=case_id,
            event_type="case.exception",
            payload={"source": "voice_ptp", "reason": "low_confidence_or_ambiguous_commitment"},
            actor=_SYSTEM,
        )

    await event_store.append(
        case_id=case_id,
        event_type="voice.call_ended",
        payload={
            "final_node": state.node,
            "node_path": state.node_path,
            "transcript": state.transcript,
            "audio_artifact_ref": audio_artifact_ref,
            "ptp_captured": state.ptp is not None,
        },
        actor=_SYSTEM,
    )
    return state
