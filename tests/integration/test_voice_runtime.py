"""FR-10.4/FR-11.1 against a real event store: a full call writes every turn,
a captured PTP suspends the case (`awaiting_promise`), a distress/dispute/
legal utterance safe-exits and raises a human exception, and a low-confidence
extraction never becomes a silent promise.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.projection import project
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.llm.schemas import PTPExtraction
from recoup.voice.runtime import run_call

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seeded_case(store: EventStore) -> str:
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(amount_at_risk="499.00"),
        actor=SYSTEM,
    )
    return case_id


async def _confident_ptp(_transcript: str, _now: datetime) -> PTPExtraction:
    return PTPExtraction(
        has_commitment=True,
        amount_inr=Decimal("499.00"),
        promised_date=date(2026, 1, 10),
        confidence=0.92,
    )


async def _low_confidence_ptp(_transcript: str, _now: datetime) -> PTPExtraction:
    return PTPExtraction(has_commitment=True, amount_inr=None, promised_date=None, confidence=0.3)


async def test_a_call_that_captures_a_confident_ptp_suspends_the_case(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store)

    state = await run_call(
        store,
        case_id=case_id,
        merchant_name="Acme",
        utterances=[
            ("haan theek hai", 0.95),  # identify -> disclose
            ("haan samajh gaya", 0.95),  # disclose -> purpose
            ("haan bataiye", 0.95),  # purpose -> offer_resolution
            ("main pay kar dunga", 0.95),  # offer_resolution -> capture_ptp
            (
                "10 January tak 499 rupees de dunga",
                0.95,
            ),  # capture_ptp -> confirm (extractor stubbed)
            ("haan sahi hai", 0.95),  # confirm -> close
        ],
        now=_NOW,
        extractor=_confident_ptp,
    )

    assert state.node == "close"
    assert state.ptp is not None
    assert state.node_path[0] == "identify"
    assert state.node_path[1] == "disclose"  # disclosure is the second turn, always

    events = await store.events_for(case_id)
    event_types = [e.event_type for e in events]
    assert "voice.call_started" in event_types
    assert event_types.count("voice.turn") == 6
    assert "ptp.captured" in event_types
    assert "voice.call_ended" in event_types
    assert "case.exception" not in event_types

    case = project(events)
    assert case.resolution_state == "awaiting_promise"


async def test_opting_out_mid_call_ends_the_call_with_no_ptp(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store)

    state = await run_call(
        store,
        case_id=case_id,
        merchant_name="Acme",
        utterances=[
            ("haan", 0.95),
            ("theek hai", 0.95),
            ("haan", 0.95),
            ("please stop calling me", 0.95),
            ("ok", 0.95),  # acknowledging the opt-out confirmation; closes the call
        ],
        now=_NOW,
    )

    assert state.node == "close"
    assert state.node_path[-2] == "opt_out"
    assert state.ptp is None


async def test_a_distress_utterance_safe_exits_and_raises_a_human_exception(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store)

    state = await run_call(
        store,
        case_id=case_id,
        merchant_name="Acme",
        utterances=[("I can't take this anymore, I feel so hopeless", 0.95)],
        now=_NOW,
    )

    assert state.node == "safe_exit"
    events = await store.events_for(case_id)
    event_types = [e.event_type for e in events]
    assert "case.exception" in event_types
    exception_event = next(e for e in events if e.event_type == "case.exception")
    assert exception_event.payload["reason"] == "distress"


async def test_a_legal_keyword_at_any_node_safe_exits_the_call(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store)

    state = await run_call(
        store,
        case_id=case_id,
        merchant_name="Acme",
        utterances=[
            ("haan", 0.95),
            ("theek hai", 0.95),
            ("I'll talk to my lawyer about this", 0.95),
        ],
        now=_NOW,
    )

    assert state.node == "safe_exit"
    events = await store.events_for(case_id)
    assert any(e.event_type == "case.exception" and e.payload["reason"] == "legal" for e in events)


async def test_low_confidence_extraction_never_becomes_a_silent_promise(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store)

    state = await run_call(
        store,
        case_id=case_id,
        merchant_name="Acme",
        utterances=[
            ("haan", 0.95),
            ("theek hai", 0.95),
            ("haan bataiye", 0.95),
            ("main pay karunga", 0.95),
            ("shayad kabhi", 0.95),  # vague; extractor stubbed to low confidence
        ],
        now=_NOW,
        extractor=_low_confidence_ptp,
    )

    assert state.ptp is None
    assert state.needs_human_verification is True
    events = await store.events_for(case_id)
    assert not any(e.event_type == "ptp.captured" for e in events)
    exception_event = next(e for e in events if e.event_type == "case.exception")
    assert exception_event.payload["source"] == "voice_ptp"


async def test_silence_safe_exits_without_a_customer_utterance(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store)

    state = await run_call(
        store, case_id=case_id, merchant_name="Acme", utterances=[("", 0.0)], now=_NOW
    )

    assert state.node == "safe_exit"
    events = await store.events_for(case_id)
    turn_event = next(e for e in events if e.event_type == "voice.turn")
    assert turn_event.payload["guard_triggered"] == "silence"
